"""Unit tests for src/state_merger.py.

Covers STATE-04 (add-only merge; first_seen preserved; never delete keys) and
STATE-05 (keys missing from current scan keep last_seen unchanged + flip
still_listed to False).

Phase 4 Plan 04-03 D-04 / D-04b / D-04d:
- merge_state emits schema_version: 2 and carries source_health through.
- classify_outcome maps orchestrator outcome strings → (status, fail_count, is_success).
- update_source_health mutates state["source_health"][company] in place per
  D-04b classification rules (3+ consecutive SiteBlocked → "blocked").
"""
from __future__ import annotations

from datetime import UTC, datetime

from src.models import Posting
from src.state_merger import classify_outcome, merge_state, update_source_health

_RUN = datetime(2026, 6, 7, 14, 0, 0, tzinfo=UTC)
_EARLIER = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)


def _p(key: str, title: str = "X", **overrides) -> Posting:
    return Posting(
        dedup_key=key,
        company=overrides.get("company", "X"),
        title=title,
        location=overrides.get("location", ""),
        salary=overrides.get("salary"),
        experience_min=overrides.get("experience_min"),
        experience_max=overrides.get("experience_max"),
        posting_url=overrides.get("posting_url", f"https://x/{key}"),
        posted_date=overrides.get("posted_date"),
        first_seen=overrides.get("first_seen", _RUN),
        last_seen=overrides.get("last_seen", _RUN),
        still_listed=True,
        source_adapter="greenhouse",
    )


def test_merge_empty_prior_inserts_fresh():
    prior = {"schema_version": 1, "last_run_utc": None, "postings": {}}
    merged = merge_state(prior, [_p("gh:x:1"), _p("gh:x:2")], _RUN)
    assert set(merged["postings"].keys()) == {"gh:x:1", "gh:x:2"}
    assert merged["postings"]["gh:x:1"]["first_seen"] == _RUN.isoformat()
    assert merged["postings"]["gh:x:1"]["last_seen"] == _RUN.isoformat()
    assert merged["postings"]["gh:x:1"]["still_listed"] is True


def test_merge_preserves_first_seen_on_existing_key():
    prior = {
        "schema_version": 1,
        "last_run_utc": _EARLIER.isoformat(),
        "postings": {
            "gh:x:1": {
                "company": "X",
                "title": "Old",
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": "https://x/1",
                "posted_date": None,
                "first_seen": _EARLIER.isoformat(),
                "last_seen": _EARLIER.isoformat(),
                "still_listed": True,
                "source_adapter": "greenhouse",
            }
        },
    }
    merged = merge_state(prior, [_p("gh:x:1", title="New")], _RUN)
    assert merged["postings"]["gh:x:1"]["first_seen"] == _EARLIER.isoformat()
    assert merged["postings"]["gh:x:1"]["last_seen"] == _RUN.isoformat()
    assert merged["postings"]["gh:x:1"]["title"] == "New"
    assert merged["postings"]["gh:x:1"]["still_listed"] is True


def test_merge_flips_still_listed_for_missing_keys():
    """STATE-05: keys present in prior but absent from fresh keep last_seen + flip flag."""
    prior = {
        "schema_version": 1,
        "last_run_utc": _EARLIER.isoformat(),
        "postings": {
            "gh:x:1": {
                "still_listed": True,
                "first_seen": _EARLIER.isoformat(),
                "last_seen": _EARLIER.isoformat(),
            },
            "gh:x:2": {
                "still_listed": True,
                "first_seen": _EARLIER.isoformat(),
                "last_seen": _EARLIER.isoformat(),
            },
        },
    }
    merged = merge_state(prior, [_p("gh:x:1")], _RUN)
    assert merged["postings"]["gh:x:1"]["still_listed"] is True
    assert merged["postings"]["gh:x:2"]["still_listed"] is False
    assert merged["postings"]["gh:x:2"]["last_seen"] == _EARLIER.isoformat()


def test_merge_empty_fresh_flips_all_to_not_listed():
    prior = {
        "schema_version": 1,
        "last_run_utc": _EARLIER.isoformat(),
        "postings": {
            "gh:x:1": {
                "still_listed": True,
                "first_seen": _EARLIER.isoformat(),
                "last_seen": _EARLIER.isoformat(),
            }
        },
    }
    merged = merge_state(prior, [], _RUN)
    assert merged["postings"]["gh:x:1"]["still_listed"] is False
    # STATE-04 — key not deleted
    assert "gh:x:1" in merged["postings"]


def test_merge_emits_schema_version_2():
    """Plan 04-03 D-04 — merge_state always emits the current SCHEMA_VERSION (2)."""
    prior = {"schema_version": 1, "last_run_utc": None, "postings": {}}
    merged = merge_state(prior, [], _RUN)
    assert merged["schema_version"] == 2


def test_merge_emits_schema_version_2_from_v2_prior():
    """A v2 prior is also emitted as v2 (no downgrade, no version preservation pre-bump)."""
    prior = {
        "schema_version": 2,
        "last_run_utc": None,
        "postings": {},
        "source_health": {},
    }
    merged = merge_state(prior, [], _RUN)
    assert merged["schema_version"] == 2


def test_merge_updates_last_run_utc():
    prior = {"schema_version": 1, "last_run_utc": _EARLIER.isoformat(), "postings": {}}
    merged = merge_state(prior, [], _RUN)
    assert merged["last_run_utc"] == _RUN.isoformat()


def test_merge_never_deletes_keys():
    """STATE-04 — even after many runs with empty fresh, prior keys remain."""
    prior = {
        "schema_version": 1,
        "last_run_utc": _EARLIER.isoformat(),
        "postings": {
            "gh:x:1": {"still_listed": True},
            "gh:x:2": {"still_listed": True},
            "gh:x:3": {"still_listed": True},
        },
    }
    merged_a = merge_state(prior, [], _RUN)
    merged_b = merge_state(merged_a, [], _RUN)
    assert set(merged_b["postings"].keys()) == {"gh:x:1", "gh:x:2", "gh:x:3"}


def test_merge_fresh_only_inserts_with_run_started_at():
    """Brand-new keys in fresh get first_seen = last_seen = run_started_at."""
    prior = {"schema_version": 1, "last_run_utc": None, "postings": {}}
    merged = merge_state(prior, [_p("gh:x:new")], _RUN)
    record = merged["postings"]["gh:x:new"]
    assert record["first_seen"] == _RUN.isoformat()
    assert record["last_seen"] == _RUN.isoformat()
    assert record["still_listed"] is True


# --- Phase 4 Plan 04-03 — classify_outcome (D-04b) ----------------------------

# Fixed timestamps for clarity — no datetime.now() in tests (RUN-01 discipline).
T1 = datetime(2026, 6, 1, tzinfo=UTC)
T2 = datetime(2026, 6, 2, tzinfo=UTC)
T3 = datetime(2026, 6, 3, tzinfo=UTC)


def test_classify_outcome_ok_returns_zero_fails():
    """D-04b — outcome 'ok' resets consecutive_failures to 0 regardless of prior."""
    assert classify_outcome("ok", 0) == ("ok", 0, True)
    assert classify_outcome("ok", 5) == ("ok", 0, True)
    assert classify_outcome("ok", 99) == ("ok", 0, True)


def test_classify_outcome_blocked_below_threshold_returns_error():
    """D-04b — 'blocked' with <3 consecutive fails maps to status 'error'
    (the 3-consecutive threshold is the bar for the user-visible 'blocked' label).
    """
    assert classify_outcome("blocked", 0) == ("error", 1, False)
    assert classify_outcome("blocked", 1) == ("error", 2, False)


def test_classify_outcome_blocked_at_threshold_returns_blocked():
    """D-04b — 3+ consecutive 'blocked' outcomes promote status to 'blocked'."""
    assert classify_outcome("blocked", 2) == ("blocked", 3, False)
    assert classify_outcome("blocked", 5) == ("blocked", 6, False)
    assert classify_outcome("blocked", 99) == ("blocked", 100, False)


def test_classify_outcome_schema_drift_returns_schema_drift():
    """D-04b — any 'error: SchemaDrift' outcome is classified as 'schema-drift'."""
    assert classify_outcome("error: SchemaDrift", 0) == ("schema-drift", 1, False)
    assert classify_outcome("error: SchemaDrift", 7) == ("schema-drift", 8, False)


def test_classify_outcome_generic_error_returns_error():
    """D-04b — all other failure outcomes (PlaywrightTimeout, InvalidCredential,
    MissingCredential, generic Exception) classify as 'error'.
    """
    assert classify_outcome("error: PlaywrightTimeout", 0) == ("error", 1, False)
    assert classify_outcome("error: InvalidCredential", 0) == ("error", 1, False)
    assert classify_outcome("error: MissingCredential", 0) == ("error", 1, False)
    assert classify_outcome("error: RuntimeError", 0) == ("error", 1, False)


def test_classify_outcome_no_adapter_returns_error():
    """D-04b — CFG-05 'no-adapter' counts as a scan failure for health tracking
    (no postings collected → cannot distinguish 'company is healthy' from 'we have
    no way to check'; conservatively treat as error).
    """
    assert classify_outcome("no-adapter", 0) == ("error", 1, False)
    assert classify_outcome("no-adapter", 4) == ("error", 5, False)


# --- update_source_health (D-04 / D-04d) --------------------------------------


def test_update_source_health_creates_default_on_first_encounter():
    """D-04d — first encounter of a company creates default entry then applies outcome."""
    state = {"source_health": {}}
    update_source_health(state, "Stripe", "ok", T1)
    entry = state["source_health"]["Stripe"]
    assert entry["status"] == "ok"
    assert entry["last_attempt_utc"] == T1.isoformat()
    assert entry["last_success_utc"] == T1.isoformat()
    assert entry["consecutive_failures"] == 0


def test_update_source_health_missing_block_initializes():
    """update_source_health installs source_health key if state lacks it (defensive)."""
    state = {}  # no source_health key
    update_source_health(state, "Apple", "ok", T1)
    assert "source_health" in state
    assert state["source_health"]["Apple"]["status"] == "ok"


def test_update_source_health_increments_consecutive_failures_across_runs():
    """D-04b — three consecutive 'blocked' outcomes promote status to 'blocked'."""
    state = {"source_health": {}}
    update_source_health(state, "Apple", "blocked", T1)
    assert state["source_health"]["Apple"]["status"] == "error"  # 1 fail
    assert state["source_health"]["Apple"]["consecutive_failures"] == 1
    update_source_health(state, "Apple", "blocked", T2)
    assert state["source_health"]["Apple"]["status"] == "error"  # 2 fails
    assert state["source_health"]["Apple"]["consecutive_failures"] == 2
    update_source_health(state, "Apple", "blocked", T3)
    assert state["source_health"]["Apple"]["status"] == "blocked"  # 3 fails → blocked
    assert state["source_health"]["Apple"]["consecutive_failures"] == 3
    # last_success_utc never set — three failures with no prior success.
    assert state["source_health"]["Apple"]["last_success_utc"] is None
    # last_attempt_utc tracks the most recent attempt.
    assert state["source_health"]["Apple"]["last_attempt_utc"] == T3.isoformat()


def test_update_source_health_resets_failures_on_success():
    """D-04b — a single 'ok' outcome wipes consecutive_failures to 0."""
    state = {
        "source_health": {
            "Stripe": {
                "last_attempt_utc": T1.isoformat(),
                "last_success_utc": None,
                "status": "blocked",
                "consecutive_failures": 5,
            }
        }
    }
    update_source_health(state, "Stripe", "ok", T2)
    entry = state["source_health"]["Stripe"]
    assert entry["status"] == "ok"
    assert entry["consecutive_failures"] == 0
    assert entry["last_attempt_utc"] == T2.isoformat()
    assert entry["last_success_utc"] == T2.isoformat()


def test_update_source_health_preserves_last_success_utc_on_failure():
    """D-04b — failures preserve the prior last_success_utc (only success bumps it)."""
    state = {
        "source_health": {
            "Apple": {
                "last_attempt_utc": T1.isoformat(),
                "last_success_utc": T1.isoformat(),
                "status": "ok",
                "consecutive_failures": 0,
            }
        }
    }
    update_source_health(state, "Apple", "blocked", T2)
    entry = state["source_health"]["Apple"]
    assert entry["last_success_utc"] == T1.isoformat()  # UNCHANGED
    assert entry["last_attempt_utc"] == T2.isoformat()  # bumped to most recent
    assert entry["consecutive_failures"] == 1
    assert entry["status"] == "error"  # 1 fail < 3


def test_update_source_health_schema_drift_status():
    """D-04b — schema-drift outcome surfaces as status='schema-drift'."""
    state = {"source_health": {}}
    update_source_health(state, "Apple", "error: SchemaDrift", T1)
    entry = state["source_health"]["Apple"]
    assert entry["status"] == "schema-drift"
    assert entry["consecutive_failures"] == 1
    assert entry["last_success_utc"] is None


def test_update_source_health_in_place_no_return():
    """update_source_health is an in-place mutator; returns None."""
    state = {"source_health": {}}
    result = update_source_health(state, "X", "ok", T1)
    assert result is None
    assert "X" in state["source_health"]


def test_merge_state_preserves_source_health_from_prior():
    """D-04 — merge_state carries source_health forward (shallow copy)."""
    prior = {
        "schema_version": 2,
        "last_run_utc": None,
        "postings": {},
        "source_health": {
            "Stripe": {
                "last_attempt_utc": T1.isoformat(),
                "last_success_utc": T1.isoformat(),
                "status": "ok",
                "consecutive_failures": 0,
            }
        },
    }
    merged = merge_state(prior, [], _RUN)
    assert "source_health" in merged
    assert merged["source_health"]["Stripe"]["status"] == "ok"
    # Shallow copy — mutating the merged source_health dict should not affect prior.
    merged["source_health"]["Apple"] = {"status": "blocked"}
    assert "Apple" not in prior["source_health"]


def test_merge_state_emits_empty_source_health_when_prior_lacks_one():
    """A v1-shaped prior (no source_health key) yields merged with source_health={}."""
    prior = {"schema_version": 1, "last_run_utc": None, "postings": {}}
    merged = merge_state(prior, [], _RUN)
    assert merged["source_health"] == {}
