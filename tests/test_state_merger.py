"""Unit tests for src/state_merger.py.

Covers STATE-04 (add-only merge; first_seen preserved; never delete keys) and
STATE-05 (keys missing from current scan keep last_seen unchanged + flip
still_listed to False).
"""
from __future__ import annotations

from datetime import UTC, datetime

from src.models import Posting
from src.state_merger import merge_state

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


def test_merge_preserves_schema_version():
    prior = {"schema_version": 1, "last_run_utc": None, "postings": {}}
    merged = merge_state(prior, [], _RUN)
    assert merged["schema_version"] == 1


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
