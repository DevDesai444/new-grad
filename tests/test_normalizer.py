"""Unit tests for src/normalizer.py.

Covers NORM-04 / NORM-05 / NORM-06: UTC date conversion, URL canonicalization,
and per-adapter dispatch. Pure function — no I/O, no datetime.now() inside
normalizer; the caller (main.py) passes run_started_at.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.models import RawPosting
from src.normalizer import _parse_iso_to_utc, canonicalize_url, normalize

_RUN_STARTED_AT = datetime(2026, 6, 7, 14, 0, 0, tzinfo=UTC)


# --- canonicalize_url ---------------------------------------------------------

def test_canonicalize_strips_utm_and_gh_src():
    out = canonicalize_url(
        "https://boards.greenhouse.io/stripe/jobs/123"
        "?utm_source=careers&gh_src=abc&keep=yes"
    )
    assert out == "https://boards.greenhouse.io/stripe/jobs/123?keep=yes"


def test_canonicalize_strips_lever_source():
    out = canonicalize_url(
        "https://jobs.lever.co/anthropic/abc?lever-source=referral&id=42"
    )
    # lever-source stripped, `id` kept.
    assert "lever-source" not in out
    assert "id=42" in out


def test_canonicalize_lowercases_host_preserves_path_case():
    out = canonicalize_url("https://Boards.Greenhouse.IO/Stripe/")
    assert out == "https://boards.greenhouse.io/Stripe"


def test_canonicalize_strips_trailing_slash_on_long_path():
    out = canonicalize_url("https://example.com/a/b/c/")
    assert out == "https://example.com/a/b/c"


def test_canonicalize_strips_fragment():
    out = canonicalize_url("https://example.com/x#section")
    assert "#" not in out
    assert "section" not in out


def test_canonicalize_handles_no_query_no_path():
    out = canonicalize_url("https://example.com")
    assert out == "https://example.com"


def test_canonicalize_strips_all_utm_prefixed_params():
    out = canonicalize_url(
        "https://x.example/y?utm_source=a&utm_medium=b&utm_campaign=c&keep=z"
    )
    assert "utm_" not in out
    assert "keep=z" in out


# --- _parse_iso_to_utc --------------------------------------------------------

def test_parse_iso_to_utc_with_negative_offset():
    dt = _parse_iso_to_utc("2026-06-01T14:00:00-04:00")
    assert dt is not None
    assert dt.isoformat() == "2026-06-01T18:00:00+00:00"
    assert dt.tzinfo is not None


def test_parse_iso_to_utc_trailing_z():
    dt = _parse_iso_to_utc("2026-06-01T14:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.isoformat() == "2026-06-01T14:00:00+00:00"


def test_parse_iso_to_utc_naive_assumed_utc():
    dt = _parse_iso_to_utc("2026-06-01T14:00:00")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_parse_iso_to_utc_none_input():
    assert _parse_iso_to_utc(None) is None


def test_parse_iso_to_utc_empty_string():
    assert _parse_iso_to_utc("") is None


def test_parse_iso_to_utc_invalid_string():
    assert _parse_iso_to_utc("not-a-date") is None


# --- normalize (Greenhouse) ---------------------------------------------------

def _load_fixture() -> dict:
    return json.loads(
        (Path(__file__).parent / "fixtures" / "greenhouse_stripe.json").read_text()
    )


def test_normalize_greenhouse_happy_path():
    fixture = _load_fixture()
    job = fixture["jobs"][0]
    rp = RawPosting(
        source_company="stripe",
        source_adapter="greenhouse",
        raw={
            **job,
            "__dedup_key": f"gh:stripe:{job['id']}",
            "__board_token": "stripe",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.dedup_key == f"gh:stripe:{job['id']}"
    assert p.source_adapter == "greenhouse"
    assert p.first_seen == _RUN_STARTED_AT
    assert p.last_seen == _RUN_STARTED_AT
    assert p.posted_date is not None
    assert p.posted_date.tzinfo is not None
    # First fixture entry has no utm/gh_src in URL, so canonicalize is a no-op.
    assert p.posting_url == job["absolute_url"]
    assert p.title == "Software Engineer, New Grad"
    assert p.location == "San Francisco, CA"


def test_normalize_reads_dedup_key_from_raw_not_url():
    """The normalizer must NOT re-compute dedup_key. Plan 01's adapter stashes it."""
    rp = RawPosting(
        source_company="stripe",
        source_adapter="greenhouse",
        raw={
            "id": 999,
            "title": "X",
            "updated_at": "2026-06-01T00:00:00Z",
            "location": {"name": "SF"},
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/999",
            "__dedup_key": "PRE_COMPUTED_SENTINEL",
            "__board_token": "stripe",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.dedup_key == "PRE_COMPUTED_SENTINEL"


def test_normalize_canonicalizes_url_with_utm_param():
    rp = RawPosting(
        source_company="stripe",
        source_adapter="greenhouse",
        raw={
            "id": 999,
            "title": "X",
            "updated_at": "2026-06-01T00:00:00Z",
            "location": {"name": "SF"},
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/999?utm_source=careers",
            "__dedup_key": "gh:stripe:999",
            "__board_token": "stripe",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert "utm_source" not in p.posting_url
    assert p.posting_url == "https://boards.greenhouse.io/stripe/jobs/999"


def test_normalize_sets_first_seen_equals_last_seen():
    rp = RawPosting(
        source_company="stripe",
        source_adapter="greenhouse",
        raw={
            "id": 1,
            "title": "T",
            "updated_at": "2026-06-01T00:00:00Z",
            "location": {"name": "X"},
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/1",
            "__dedup_key": "gh:stripe:1",
            "__board_token": "stripe",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.first_seen == _RUN_STARTED_AT
    assert p.last_seen == _RUN_STARTED_AT


def test_normalize_unknown_adapter_raises():
    rp = RawPosting(source_company="x", source_adapter="unknown_ats", raw={})
    with pytest.raises(ValueError):
        normalize(rp, _RUN_STARTED_AT)


def test_normalize_handles_missing_location():
    rp = RawPosting(
        source_company="stripe",
        source_adapter="greenhouse",
        raw={
            "id": 2,
            "title": "T",
            "updated_at": "2026-06-01T00:00:00Z",
            # location dict missing
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/2",
            "__dedup_key": "gh:stripe:2",
            "__board_token": "stripe",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.location == ""


def test_normalize_posted_date_none_when_updated_at_missing():
    rp = RawPosting(
        source_company="stripe",
        source_adapter="greenhouse",
        raw={
            "id": 3,
            "title": "T",
            # updated_at absent
            "location": {"name": "SF"},
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/3",
            "__dedup_key": "gh:stripe:3",
            "__board_token": "stripe",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.posted_date is None


# --- FILT-03 JD-scan integration: one per adapter (Plan 02-03 Task 2) ---------
# Each test asserts that the per-adapter normalizer reads the source-specific
# description field from raw and populates experience_min/experience_max via
# extract_experience_range. Per CONTEXT.md D-02 this is display-only — does
# NOT gate inclusion.


def test_normalize_greenhouse_populates_experience_from_content():
    """Greenhouse content `0-3 years of experience` → (0, 3)."""
    rp = RawPosting(
        source_company="stripe",
        source_adapter="greenhouse",
        raw={
            "id": 100,
            "title": "Associate Software Engineer",
            "updated_at": "2026-06-01T00:00:00Z",
            "location": {"name": "NYC"},
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/100",
            "content": "<p>0–3 years of experience. Entry-level role for new graduates.</p>",
            "__dedup_key": "gh:stripe:100",
            "__board_token": "stripe",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.experience_min == 0
    assert p.experience_max == 3


def test_normalize_lever_populates_experience_from_description_plain():
    """Lever descriptionPlain `0-2 years experience` → (0, 2)."""
    rp = RawPosting(
        source_company="notion",
        source_adapter="lever",
        raw={
            "id": "11111111-aaaa-bbbb-cccc-222222222222",
            "text": "Software Engineer, New Grad",
            "createdAt": 1748707200000,
            "categories": {"location": "SF"},
            "hostedUrl": "https://jobs.lever.co/notion/abc",
            "descriptionPlain": "Join our team. 0-2 years experience preferred.",
            "__dedup_key": "lever:notion:abc",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.experience_min == 0
    assert p.experience_max == 2


def test_normalize_ashby_populates_experience_from_description_plain():
    """Ashby descriptionPlain `5+ years required` → (5, None)."""
    rp = RawPosting(
        source_company="notion",
        source_adapter="ashby",
        raw={
            "id": "aaaa-bbbb-cccc",
            "title": "Software Engineer",
            "locationName": "Remote",
            "jobUrl": "https://jobs.ashbyhq.com/notion/abc",
            "publishedAt": "2026-06-01T00:00:00Z",
            "descriptionPlain": "Position requires 5+ years experience in distributed systems.",
            "__dedup_key": "ashby:notion:abc",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.experience_min == 5
    assert p.experience_max is None


def test_normalize_smartrecruiters_populates_experience_from_nested_text():
    """SR jobAd.sections.jobDescription.text `Entry-level` → (0, None)."""
    rp = RawPosting(
        source_company="notion",
        source_adapter="smartrecruiters",
        raw={
            "id": "sr-id-1",
            "name": "Associate Engineer",
            "location": {"city": "NYC", "country": "US"},
            "ref": "https://api.smartrecruiters.com/v1/companies/notion/postings/sr-id-1",
            "releasedDate": "2026-06-01T00:00:00.000Z",
            "jobAd": {
                "sections": {
                    "jobDescription": {
                        "text": "Entry-level role. We welcome recent graduates.",
                    },
                },
            },
            "__dedup_key": "sr:notion:sr-id-1",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.experience_min == 0
    assert p.experience_max is None


def test_normalize_workday_experience_none_when_description_absent():
    """Workday CXS doesn't return description per posting → (None, None)."""
    rp = RawPosting(
        source_company="nvidia",
        source_adapter="workday",
        raw={
            "title": "Software Engineer",
            "locationsText": "US, CA",
            "__posting_url": "https://nvidia.wd5.myworkdayjobs.com/job/R-1",
            "__posted_date_utc": None,
            "__dedup_key": "wd:nvidia:R-1",
            "__tenant": "nvidia",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    # Workday CXS /jobs doesn't expose description → JD-scan returns (None, None).
    assert p.experience_min is None
    assert p.experience_max is None


def test_normalize_workday_experience_populates_if_description_stashed():
    """If Workday adapter ever stashes raw['__description'], JD-scan fires."""
    rp = RawPosting(
        source_company="nvidia",
        source_adapter="workday",
        raw={
            "title": "Software Engineer",
            "locationsText": "US, CA",
            "__posting_url": "https://nvidia.wd5.myworkdayjobs.com/job/R-2",
            "__posted_date_utc": None,
            "__description": "3 to 5 years experience preferred.",
            "__dedup_key": "wd:nvidia:R-2",
            "__tenant": "nvidia",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.experience_min == 3
    assert p.experience_max == 5


def test_normalize_apple_populates_experience_from_job_summary():
    """Apple jobSummary `7+ years` → (7, None). Per D-02 still kept in table."""
    rp = RawPosting(
        source_company="Apple",
        source_adapter="apple",
        raw={
            "id": "200593844",
            "positionId": "200593844",
            "postingTitle": "Software Engineer, New Grad",
            "transformedPostingTitle": "swe-new-grad",
            "postingDate": "2026-06-02T10:00:00Z",
            "locations": [{"name": "Cupertino, CA"}],
            "jobSummary": "Title says new grad but the body requires 7+ years experience.",
            "__dedup_key": "apple:200593844",
            "__position_id": "200593844",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.experience_min == 7
    assert p.experience_max is None


def test_normalize_apple_populates_experience_from_entry_signal():
    """Apple jobSummary `Recent graduate` → (0, None)."""
    rp = RawPosting(
        source_company="Apple",
        source_adapter="apple",
        raw={
            "id": "200593841",
            "positionId": "200593841",
            "postingTitle": "Software Engineer, New Grad",
            "transformedPostingTitle": "swe-new-grad",
            "postingDate": "2026-06-05T10:00:00Z",
            "locations": [{"name": "Cupertino, CA"}],
            "jobSummary": "Join Apple as a new grad SWE. Recent graduate preferred.",
            "__dedup_key": "apple:200593841",
            "__position_id": "200593841",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.experience_min == 0
    assert p.experience_max is None
