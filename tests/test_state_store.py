"""Unit tests for src/state_store.py.

Covers STATE-01..08:
- Atomic write via os.replace + .bak before overwrite (STATE-02).
- .bak fallback on JSON decode failure (STATE-03).
- schema_version validation; refuses unknown future versions (STATE-08).
- Sanity gate per CONTEXT.md D-06 — always engages; cold-start trivially passes;
  prior=1+new=0 boundary aborts; any_blocked=True excuses the gate (STATE-06).
- orjson OPT_SORT_KEYS produces byte-deterministic output (STATE-07).
"""
from __future__ import annotations

import orjson
import pytest

from src.state_store import (
    EMPTY_STATE,
    SCHEMA_VERSION,
    SanityGateAborted,
    UnknownSchemaVersion,
    load_state,
    sanity_gate,
    save_state_atomic,
)

# --- load_state ----------------------------------------------------------------

def test_load_missing_returns_empty_state(tmp_path):
    state = load_state(tmp_path / "absent.json")
    assert state["schema_version"] == SCHEMA_VERSION
    assert state["postings"] == {}
    assert state["last_run_utc"] is None


def test_load_returns_independent_copy_of_empty_state(tmp_path):
    """Modifying the returned dict must not mutate the module-level EMPTY_STATE."""
    state = load_state(tmp_path / "absent.json")
    state["postings"]["x"] = {"company": "X"}
    state2 = load_state(tmp_path / "absent.json")
    assert state2["postings"] == {}


def test_load_valid_state(tmp_path):
    payload = {
        "schema_version": 1,
        "last_run_utc": "2026-06-07T14:00:00+00:00",
        "postings": {
            "gh:stripe:1": {
                "company": "Stripe",
                "title": "New Grad",
                "still_listed": True,
            }
        },
    }
    p = tmp_path / "seen.json"
    p.write_bytes(orjson.dumps(payload))
    state = load_state(p)
    assert state["postings"]["gh:stripe:1"]["company"] == "Stripe"
    assert state["schema_version"] == 1


def test_load_corrupted_falls_back_to_bak(tmp_path):
    good = {
        "schema_version": 1,
        "last_run_utc": None,
        "postings": {"k": {"company": "X"}},
    }
    bak = tmp_path / "seen.json.bak"
    bak.write_bytes(orjson.dumps(good))
    main = tmp_path / "seen.json"
    main.write_text("{not-json")
    state = load_state(main)
    assert state["postings"]["k"]["company"] == "X"


def test_load_both_corrupted_returns_empty(tmp_path):
    (tmp_path / "seen.json").write_text("garbage")
    (tmp_path / "seen.json.bak").write_text("garbage")
    state = load_state(tmp_path / "seen.json")
    assert state == EMPTY_STATE


def test_load_corrupted_main_no_bak_returns_empty(tmp_path):
    (tmp_path / "seen.json").write_text("not json at all")
    state = load_state(tmp_path / "seen.json")
    assert state == EMPTY_STATE


def test_load_unknown_future_schema_raises(tmp_path):
    payload = {"schema_version": 99, "last_run_utc": None, "postings": {}}
    p = tmp_path / "seen.json"
    p.write_bytes(orjson.dumps(payload))
    with pytest.raises(UnknownSchemaVersion):
        load_state(p)


def test_load_missing_schema_version_treated_as_corrupt(tmp_path):
    payload = {"last_run_utc": None, "postings": {}}  # no schema_version
    p = tmp_path / "seen.json"
    p.write_bytes(orjson.dumps(payload))
    # Falls through to EMPTY_STATE (no .bak, no schema version means treat as corrupt)
    state = load_state(p)
    assert state == EMPTY_STATE


def test_load_missing_postings_treated_as_corrupt(tmp_path):
    payload = {"schema_version": 1, "last_run_utc": None}  # missing postings
    p = tmp_path / "seen.json"
    p.write_bytes(orjson.dumps(payload))
    state = load_state(p)
    assert state == EMPTY_STATE


# --- save_state_atomic ---------------------------------------------------------

def test_save_atomic_creates_file(tmp_path):
    p = tmp_path / "seen.json"
    save_state_atomic(
        {"schema_version": 1, "last_run_utc": None, "postings": {"a": {}}}, p
    )
    assert p.exists()
    loaded = orjson.loads(p.read_bytes())
    assert loaded["postings"] == {"a": {}}


def test_save_atomic_creates_bak_when_overwriting(tmp_path):
    p = tmp_path / "seen.json"
    save_state_atomic(
        {"schema_version": 1, "last_run_utc": None, "postings": {"a": {}}}, p
    )
    save_state_atomic(
        {"schema_version": 1, "last_run_utc": None, "postings": {"a": {}, "b": {}}}, p
    )
    bak = tmp_path / "seen.json.bak"
    assert bak.exists()
    # .bak holds the PRIOR state.
    bak_loaded = orjson.loads(bak.read_bytes())
    assert "b" not in bak_loaded["postings"]


def test_save_atomic_no_tmp_remains(tmp_path):
    p = tmp_path / "seen.json"
    save_state_atomic(
        {"schema_version": 1, "last_run_utc": None, "postings": {}}, p
    )
    assert not (tmp_path / "seen.json.tmp").exists()


def test_save_atomic_byte_deterministic(tmp_path):
    """STATE-07: orjson OPT_SORT_KEYS must produce identical bytes for identical input."""
    state = {
        "schema_version": 1,
        "last_run_utc": "2026-06-07T14:00:00+00:00",
        "postings": {
            "z": {"a": 1, "b": 2},
            "a": {"c": 3, "d": 4},
        },
    }
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    save_state_atomic(state, p1)
    save_state_atomic(state, p2)
    assert p1.read_bytes() == p2.read_bytes()


def test_save_atomic_rejects_wrong_schema_version(tmp_path):
    """Defensive: refusing to save a state with bogus schema_version protects callers."""
    with pytest.raises(ValueError):
        save_state_atomic(
            {"schema_version": 99, "last_run_utc": None, "postings": {}},
            tmp_path / "seen.json",
        )


# --- sanity_gate (CONTEXT.md D-06) --------------------------------------------

def test_sanity_gate_cold_start_passes():
    """prior=0 + new=0 trivially passes: 0 < 0.9 * 0 = 0 is False."""
    sanity_gate(0, 0, False)  # no raise


def test_sanity_gate_prior_one_new_one_passes():
    """prior=1, new=1: 1 < 0.9 is False → passes."""
    sanity_gate(1, 1, False)


def test_sanity_gate_prior_one_zero_new_raises():
    """CONTEXT.md D-06 boundary: prior=1 + zero-result scrape aborts (defensive)."""
    with pytest.raises(SanityGateAborted):
        sanity_gate(1, 0, False)


@pytest.mark.parametrize(
    "prior,new,expect_raise",
    [
        (100, 85, True),   # 85 < 90 → raise
        (100, 89, True),   # 89 < 90 → raise
        (100, 90, False),  # 90 == 90 → pass (strict <)
        (100, 91, False),
        (10, 9, False),    # 9 == 9.0 → pass
        (10, 8, True),     # 8 < 9.0 → raise
    ],
)
def test_sanity_gate_threshold(prior, new, expect_raise):
    if expect_raise:
        with pytest.raises(SanityGateAborted):
            sanity_gate(prior, new, False)
    else:
        sanity_gate(prior, new, False)


def test_sanity_gate_any_blocked_excuses():
    """If a known adapter reported SiteBlocked, gate is skipped (Pitfall 5)."""
    sanity_gate(100, 10, True)  # no raise


def test_sanity_gate_any_blocked_excuses_even_at_prior_one():
    """any_blocked=True excuses the gate at the D-06 boundary too."""
    sanity_gate(1, 0, True)  # no raise
