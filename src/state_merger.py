"""State merger: add-only merge of fresh postings into prior state.

Pure function. No I/O. No datetime.now() — uses run_started_at passed in (RUN-01).

Requirements covered:
- STATE-04: add-only merge; first_seen preserved; keys are NEVER deleted.
- STATE-05: keys missing from current scan keep last_seen unchanged and
            still_listed flips to False.

Per ARCHITECTURE.md §State Merger: this is the only component that knows about
time, and even then only via the run_started_at parameter — never datetime.now().

Phase 4 Plan 04-03 — D-04 / D-04b / D-04d:
- merge_state always emits schema_version: 2 and carries source_health forward.
- classify_outcome: pure mapping orchestrator outcome string → (status enum,
  new_consecutive_failures, is_success).
- update_source_health: in-place mutator of state["source_health"][company].
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.models import Posting
from src.state_store import SCHEMA_VERSION


def _posting_to_record(posting: Posting) -> dict[str, Any]:
    """Project a Posting model into the on-disk record shape (JSON-safe)."""
    return {
        "company": posting.company,
        "title": posting.title,
        "location": posting.location,
        "salary": posting.salary,
        "experience_min": posting.experience_min,
        "experience_max": posting.experience_max,
        "posting_url": posting.posting_url,
        "posted_date": posting.posted_date.isoformat() if posting.posted_date else None,
        "first_seen": posting.first_seen.isoformat(),
        "last_seen": posting.last_seen.isoformat(),
        "still_listed": posting.still_listed,
        "source_adapter": posting.source_adapter,
    }


def merge_state(
    prior: dict,
    fresh_postings: list[Posting],
    run_started_at: datetime,
) -> dict:
    """Merge fresh postings into prior state. Returns a NEW state dict.

    Pass 1 (prior keys):
      - In fresh → update record from fresh, preserve first_seen, set last_seen
        = run_started_at, still_listed = True.
      - Not in fresh → preserve all fields from prior, flip still_listed = False.
        (STATE-05 — last_seen stays at its prior value.)

    Pass 2 (fresh-only keys):
      - Insert with first_seen = last_seen = run_started_at, still_listed = True.

    STATE-04: prior keys are never deleted.
    """
    fresh_by_key = {p.dedup_key: p for p in fresh_postings}
    new_postings: dict[str, Any] = {}

    # Pass 1: keys in prior — update or flip still_listed.
    for key, prior_record in prior.get("postings", {}).items():
        if key in fresh_by_key:
            fresh = fresh_by_key[key]
            record = _posting_to_record(fresh)
            # Preserve first_seen from prior (STATE-04 preservation).
            record["first_seen"] = (
                prior_record.get("first_seen") or fresh.first_seen.isoformat()
            )
            record["last_seen"] = run_started_at.isoformat()
            record["still_listed"] = True
            new_postings[key] = record
        else:
            # STATE-05 — preserve all fields, flip still_listed.
            updated = dict(prior_record)
            updated["still_listed"] = False
            new_postings[key] = updated

    # Pass 2: keys in fresh that weren't in prior — insert as new.
    for key, posting in fresh_by_key.items():
        if key not in new_postings:
            record = _posting_to_record(posting)
            record["first_seen"] = run_started_at.isoformat()
            record["last_seen"] = run_started_at.isoformat()
            new_postings[key] = record

    return {
        # Plan 04-03 D-04 — always emit current SCHEMA_VERSION (2 as of Phase 4).
        # The load-time auto-migration in state_store ensures the in-memory state
        # is already v2 by the time merge_state runs; we re-assert here so a
        # caller that hand-builds state from elsewhere still produces v2 output.
        "schema_version": SCHEMA_VERSION,
        "last_run_utc": run_started_at.isoformat(),
        "postings": new_postings,
        # Plan 04-03 D-04 — carry source_health forward. Shallow copy so the
        # orchestrator's update_source_health mutations on `merged` don't leak
        # back into the prior dict (test_merge_state_preserves_source_health_from_prior).
        "source_health": dict(prior.get("source_health") or {}),
    }


# --- Phase 4 Plan 04-03 — Source Health helpers (D-04 / D-04b / D-04d) -------


def classify_outcome(
    outcome: str,
    prior_consecutive_failures: int,
) -> tuple[str, int, bool]:
    """Map orchestrator outcome string → (status_enum, new_fail_count, is_success).

    Per CONTEXT.md D-04b classification rules. Outcomes are produced by
    src.main._scrape_one's controlled vocabulary:

        "ok"                     → ("ok", 0, True)
        "blocked"                → ("blocked" if prior+1 >= 3 else "error",
                                    prior+1, False)
        "error: SchemaDrift"     → ("schema-drift", prior+1, False)
        "no-adapter"             → ("error", prior+1, False)
                                   (CFG-05 — no way to verify health)
        anything else            → ("error", prior+1, False)
                                   (PlaywrightTimeout / MissingCredential /
                                    InvalidCredential / generic Exception)

    Pure function — no mutation. Status enum values are the four documented
    surface forms: "ok" | "blocked" | "schema-drift" | "error".
    """
    if outcome == "ok":
        return ("ok", 0, True)
    new_fail = prior_consecutive_failures + 1
    if outcome == "blocked":
        return ("blocked" if new_fail >= 3 else "error", new_fail, False)
    if outcome.startswith("error: SchemaDrift"):
        return ("schema-drift", new_fail, False)
    return ("error", new_fail, False)


def update_source_health(
    state: dict,
    company_name: str,
    outcome: str,
    run_started_at: datetime,
) -> None:
    """Mutate state["source_health"][company_name] in place per D-04 / D-04b / D-04d.

    Default entry on first encounter:
        {"last_attempt_utc": None,
         "last_success_utc": None,
         "status": "ok",
         "consecutive_failures": 0}

    On every call:
      - last_attempt_utc = run_started_at.isoformat()
      - On success: last_success_utc = run_started_at.isoformat(),
                    status = "ok", consecutive_failures = 0
      - On failure: last_success_utc UNCHANGED, consecutive_failures += 1,
                    status set per classify_outcome (D-04b enum).

    Caller is the orchestrator (src/main.py); called per company AFTER
    merge_state and BEFORE save_state_atomic. Source Health data is persisted
    in seen.json but NOT rendered in the README (CONTEXT.md D-04c).
    """
    health = state.setdefault("source_health", {})
    entry = health.setdefault(
        company_name,
        {
            "last_attempt_utc": None,
            "last_success_utc": None,
            "status": "ok",
            "consecutive_failures": 0,
        },
    )
    status, new_fail, is_success = classify_outcome(
        outcome, entry.get("consecutive_failures", 0)
    )
    ts_iso = run_started_at.isoformat()
    entry["last_attempt_utc"] = ts_iso
    if is_success:
        entry["last_success_utc"] = ts_iso
    # last_success_utc UNCHANGED on failure per D-04d.
    entry["status"] = status
    entry["consecutive_failures"] = new_fail
