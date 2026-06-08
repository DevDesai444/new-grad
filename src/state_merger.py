"""State merger: add-only merge of fresh postings into prior state.

Pure function. No I/O. No datetime.now() — uses run_started_at passed in (RUN-01).

Requirements covered:
- STATE-04: add-only merge; first_seen preserved; keys are NEVER deleted.
- STATE-05: keys missing from current scan keep last_seen unchanged and
            still_listed flips to False.

Per ARCHITECTURE.md §State Merger: this is the only component that knows about
time, and even then only via the run_started_at parameter — never datetime.now().
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.models import Posting


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
        "schema_version": prior.get("schema_version", 1),
        "last_run_utc": run_started_at.isoformat(),
        "postings": new_postings,
    }
