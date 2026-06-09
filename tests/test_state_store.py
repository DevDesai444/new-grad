"""Unit tests for src/state_store.py.

Covers STATE-01..08:
- Atomic write via os.replace + .bak before overwrite (STATE-02).
- .bak fallback on JSON decode failure (STATE-03).
- schema_version validation; refuses unknown future versions (STATE-08).
- Sanity gate per CONTEXT.md D-06 — always engages; cold-start trivially passes;
  prior=1+new=0 boundary aborts; any_blocked=True excuses the gate (STATE-06).
- orjson OPT_SORT_KEYS produces byte-deterministic output (STATE-07).

Phase 4 Plan 04-03 — D-04 / D-04a:
- SCHEMA_VERSION bumped 1 → 2; EMPTY_STATE gains `source_health: {}`.
- `load_state` auto-migrates v1 → v2 in memory (adds empty source_health).
- `save_state_atomic` writes v2 only; refuses v != SCHEMA_VERSION.
- v3+ still raises UnknownSchemaVersion (STATE-08 invariant preserved).
"""
from __future__ import annotations

import shutil
from pathlib import Path

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

_FIXTURE_V1 = Path("tests/fixtures/seen_v1_sample.json")
_FIXTURE_V2 = Path("tests/fixtures/seen_v2_sample.json")

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
    """Loading a v1-on-disk payload auto-migrates to v2 in memory (Phase 4 D-04a)."""
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
    # Plan 04-03 D-04a — loader auto-migrates v1 → SCHEMA_VERSION (currently 2).
    assert state["schema_version"] == SCHEMA_VERSION
    # The migration also adds an empty source_health block.
    assert state["source_health"] == {}


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
        {
            "schema_version": SCHEMA_VERSION,
            "last_run_utc": None,
            "postings": {"a": {}},
            "source_health": {},
        },
        p,
    )
    assert p.exists()
    loaded = orjson.loads(p.read_bytes())
    assert loaded["postings"] == {"a": {}}


def test_save_atomic_creates_bak_when_overwriting(tmp_path):
    p = tmp_path / "seen.json"
    save_state_atomic(
        {
            "schema_version": SCHEMA_VERSION,
            "last_run_utc": None,
            "postings": {"a": {}},
            "source_health": {},
        },
        p,
    )
    save_state_atomic(
        {
            "schema_version": SCHEMA_VERSION,
            "last_run_utc": None,
            "postings": {"a": {}, "b": {}},
            "source_health": {},
        },
        p,
    )
    bak = tmp_path / "seen.json.bak"
    assert bak.exists()
    # .bak holds the PRIOR state.
    bak_loaded = orjson.loads(bak.read_bytes())
    assert "b" not in bak_loaded["postings"]


def test_save_atomic_no_tmp_remains(tmp_path):
    p = tmp_path / "seen.json"
    save_state_atomic(
        {
            "schema_version": SCHEMA_VERSION,
            "last_run_utc": None,
            "postings": {},
            "source_health": {},
        },
        p,
    )
    assert not (tmp_path / "seen.json.tmp").exists()


def test_save_atomic_byte_deterministic(tmp_path):
    """STATE-07: orjson OPT_SORT_KEYS must produce identical bytes for identical input."""
    state = {
        "schema_version": SCHEMA_VERSION,
        "last_run_utc": "2026-06-07T14:00:00+00:00",
        "postings": {
            "z": {"a": 1, "b": 2},
            "a": {"c": 3, "d": 4},
        },
        "source_health": {},
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
        # Bug H (2026-06-09): threshold lowered from 0.9 to 0.5. These cases
        # are calibrated to the new floor.
        (100, 49, True),   # 49 < 50 → raise
        (100, 50, False),  # 50 == 50 → pass (strict <)
        (100, 75, False),  # 75 > 50 → pass (was True under 0.9)
        (100, 90, False),  # 90 > 50 → pass
        (100, 91, False),
        (10, 5, False),    # 5 == 5.0 → pass
        (10, 4, True),     # 4 < 5.0 → raise
    ],
)
def test_sanity_gate_threshold(prior, new, expect_raise):
    if expect_raise:
        with pytest.raises(SanityGateAborted):
            sanity_gate(prior, new, False)
    else:
        sanity_gate(prior, new, False)


def test_sanity_gate_bypass_env_var(monkeypatch):
    """Bug H — SCRAPER_BYPASS_SANITY_GATE=1 skips the gate even on huge drops."""
    monkeypatch.setenv("SCRAPER_BYPASS_SANITY_GATE", "1")
    sanity_gate(1000, 10, False)  # 10 < 500 would normally raise; bypass overrides


def test_sanity_gate_bypass_only_when_exactly_1(monkeypatch):
    """Bug H — anything OTHER than the string '1' must NOT bypass.

    Defensive: empty, whitespace, '0', 'true', 'yes' all fall through to the
    real gate. Prevents accidental bypass via half-set env vars.
    """
    for bad_val in ("", " ", "0", "true", "yes", "Y", "TRUE"):
        monkeypatch.setenv("SCRAPER_BYPASS_SANITY_GATE", bad_val)
        with pytest.raises(SanityGateAborted):
            sanity_gate(100, 10, False)


def test_sanity_gate_any_blocked_excuses():
    """If a known adapter reported SiteBlocked, gate is skipped (Pitfall 5)."""
    sanity_gate(100, 10, True)  # no raise


def test_sanity_gate_any_blocked_excuses_even_at_prior_one():
    """any_blocked=True excuses the gate at the D-06 boundary too."""
    sanity_gate(1, 0, True)  # no raise


# --- Phase 4 Plan 04-03 — schema bump 1→2 + source_health (D-04 / D-04a) ------


def test_schema_version_is_two():
    """Plan 04-03 D-04 — SCHEMA_VERSION constant bumped from 1 to 2."""
    assert SCHEMA_VERSION == 2


def test_empty_state_includes_source_health():
    """Plan 04-03 D-04 — EMPTY_STATE gains a source_health: {} key."""
    assert "source_health" in EMPTY_STATE
    assert EMPTY_STATE["source_health"] == {}


def test_load_v1_state_auto_migrates_to_v2(tmp_path):
    """D-04a — loader auto-migrates a v1 file in memory to v2 with empty source_health."""
    target = tmp_path / "seen.json"
    shutil.copy(_FIXTURE_V1, target)
    state = load_state(target)
    assert state["schema_version"] == 2, state["schema_version"]
    assert state["source_health"] == {}
    # Postings round-trip untouched.
    assert "gh:stripe:42" in state["postings"]
    assert state["postings"]["gh:stripe:42"]["company"] == "Stripe"


def test_save_atomic_writes_schema_version_2(tmp_path):
    """Plan 04-03 D-04 — saver writes a v2 payload to disk."""
    state = {
        "schema_version": SCHEMA_VERSION,
        "last_run_utc": None,
        "postings": {},
        "source_health": {},
    }
    p = tmp_path / "seen.json"
    save_state_atomic(state, p)
    loaded = orjson.loads(p.read_bytes())
    assert loaded["schema_version"] == 2
    assert loaded["source_health"] == {}


def test_load_v1_then_save_round_trip_lands_v2(tmp_path):
    """D-04a — write v1 to disk → load → save → reload → on-disk is v2 with postings preserved."""
    target = tmp_path / "seen.json"
    shutil.copy(_FIXTURE_V1, target)
    state = load_state(target)
    save_state_atomic(state, target)
    state2 = load_state(target)
    assert state2["schema_version"] == 2
    assert "gh:stripe:42" in state2["postings"]
    # source_health is the empty dict the migration installed.
    assert state2["source_health"] == {}
    # On-disk bytes also declare v2 explicitly.
    on_disk = orjson.loads(target.read_bytes())
    assert on_disk["schema_version"] == 2
    assert "source_health" in on_disk


def test_load_v3_or_higher_still_raises_unknown_schema_version(tmp_path):
    """STATE-08 regression — v3 must still raise even after the v2 bump."""
    p = tmp_path / "seen.json"
    p.write_bytes(orjson.dumps({"schema_version": 3, "last_run_utc": None, "postings": {}}))
    with pytest.raises(UnknownSchemaVersion):
        load_state(p)


def test_load_v2_with_missing_source_health_defaults_to_empty(tmp_path):
    """Defensive — a v2 file on disk without source_health (partial-write recovery)
    must load cleanly with source_health defaulting to {} — no crash.
    """
    payload = {
        "schema_version": 2,
        "last_run_utc": "2026-06-07T14:00:00+00:00",
        "postings": {"gh:x:1": {"company": "X", "title": "Eng", "still_listed": True}},
        # source_health key intentionally absent
    }
    p = tmp_path / "seen.json"
    p.write_bytes(orjson.dumps(payload))
    state = load_state(p)
    assert state["schema_version"] == 2
    assert state["source_health"] == {}
    assert "gh:x:1" in state["postings"]


def test_load_v2_with_wrong_type_source_health_defaults_to_empty(tmp_path):
    """Defensive — source_health on disk is e.g. a list (corruption) → default to {}."""
    payload = {
        "schema_version": 2,
        "last_run_utc": None,
        "postings": {},
        "source_health": ["unexpected", "list", "shape"],
    }
    p = tmp_path / "seen.json"
    p.write_bytes(orjson.dumps(payload))
    state = load_state(p)
    assert state["source_health"] == {}


def test_load_v2_preserves_populated_source_health(tmp_path):
    """A v2 file with real source_health entries round-trips them through load_state."""
    payload = {
        "schema_version": 2,
        "last_run_utc": "2026-06-07T14:00:00+00:00",
        "postings": {},
        "source_health": {
            "Stripe": {
                "last_attempt_utc": "2026-06-07T14:00:00+00:00",
                "last_success_utc": "2026-06-07T14:00:00+00:00",
                "status": "ok",
                "consecutive_failures": 0,
            },
            "Apple": {
                "last_attempt_utc": "2026-06-07T14:00:00+00:00",
                "last_success_utc": "2026-06-03T14:00:00+00:00",
                "status": "blocked",
                "consecutive_failures": 120,
            },
        },
    }
    p = tmp_path / "seen.json"
    p.write_bytes(orjson.dumps(payload))
    state = load_state(p)
    assert state["source_health"]["Stripe"]["status"] == "ok"
    assert state["source_health"]["Apple"]["consecutive_failures"] == 120


def test_save_atomic_rejects_v1_after_bump(tmp_path):
    """After the v1→v2 bump, save_state_atomic refuses to write v1 — the migration
    in load_state guarantees callers always hand it v2.
    """
    with pytest.raises(ValueError):
        save_state_atomic(
            {"schema_version": 1, "last_run_utc": None, "postings": {}, "source_health": {}},
            tmp_path / "seen.json",
        )
