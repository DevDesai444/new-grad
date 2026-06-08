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


# --- Phase 3 Plan 03-02 — PlaywrightAdapter normalizer (ADP-09) --------------


def test_normalize_playwright_xhr_path_with_id():
    """XHR-path raw blob (id, title, location, postingUrl, postingDate, description).

    Description has "0-3 years" → experience_min=0, experience_max=3 via
    extract_experience_range (FILT-03 / CONTEXT.md D-02 display-only).
    """
    rp = RawPosting(
        source_company="anthropic",
        source_adapter="playwright",
        raw={
            "id": "j-100",
            "title": "Software Engineer, New Grad",
            "location": "San Francisco, CA",
            "posting_url": "https://www.anthropic.com/careers/j-100",
            "postingDate": "2026-06-01T12:00:00Z",
            "description": "0-3 years of experience required.",
            "__dedup_key": "pw:anthropic.com:j-100",
            "__host": "anthropic.com",
            "__extraction_path": "xhr",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.dedup_key == "pw:anthropic.com:j-100"
    assert p.source_adapter == "playwright"
    assert p.title == "Software Engineer, New Grad"
    assert p.location == "San Francisco, CA"
    assert p.posting_url == "https://www.anthropic.com/careers/j-100"
    assert p.posted_date is not None
    assert p.posted_date.tzinfo is not None
    assert p.experience_min == 0
    assert p.experience_max == 3
    assert p.company == "Anthropic"


def test_normalize_playwright_dom_path_no_description():
    """DOM-path raw blob — no description → (None, None) from JD-scan."""
    rp = RawPosting(
        source_company="vercel",
        source_adapter="playwright",
        raw={
            "title": "Junior Frontend Engineer",
            "location": "Remote",
            "posting_url": "https://vercel.com/careers/jr-fe",
            "description": "",
            "__dedup_key": "pw:vercel.com:abc1234567890def0",
            "__host": "vercel.com",
            "__extraction_path": "dom",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.dedup_key == "pw:vercel.com:abc1234567890def0"
    assert p.experience_min is None
    assert p.experience_max is None
    # No date field → posted_date None.
    assert p.posted_date is None


def test_normalize_playwright_handles_missing_posted_date():
    """No postingDate / postedAt keys → posted_date=None."""
    rp = RawPosting(
        source_company="x",
        source_adapter="playwright",
        raw={
            "title": "Engineer",
            "location": "NYC",
            "posting_url": "https://x.example/jobs/1",
            "description": "",
            "__dedup_key": "pw:x.example:1",
            "__host": "x.example",
            "__extraction_path": "xhr",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.posted_date is None


def test_normalize_playwright_handles_alternate_date_keys():
    """`postedAt` (not `postingDate`) → still parsed."""
    rp = RawPosting(
        source_company="x",
        source_adapter="playwright",
        raw={
            "title": "Engineer",
            "location": "NYC",
            "posting_url": "https://x.example/jobs/1",
            "description": "",
            "postedAt": "2026-06-02T09:00:00Z",
            "__dedup_key": "pw:x.example:1",
            "__host": "x.example",
            "__extraction_path": "xhr",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert p.posted_date is not None
    assert p.posted_date.isoformat() == "2026-06-02T09:00:00+00:00"


def test_normalize_playwright_canonicalizes_url():
    """URL canonicalization fires (utm_* stripped, fragment removed)."""
    rp = RawPosting(
        source_company="x",
        source_adapter="playwright",
        raw={
            "title": "Engineer",
            "location": "NYC",
            "posting_url": (
                "https://x.example/jobs/1?utm_source=hn&keep=yes#section"
            ),
            "description": "",
            "__dedup_key": "pw:x.example:1",
            "__host": "x.example",
            "__extraction_path": "xhr",
        },
    )
    p = normalize(rp, _RUN_STARTED_AT)
    assert "utm_source" not in p.posting_url
    assert "section" not in p.posting_url
    assert "keep=yes" in p.posting_url


# --- Phase 4 Plan 04-01 — salary verbatim (D-01) per-adapter access paths ----
# Each adapter's normalizer helper populates Posting.salary from a source-
# specific JSON path. No parsing, no currency conversion. Empty / missing
# source field → salary == "" (the renderer coalesces "" to "—" per D-01a).


class TestSalaryVerbatimPerAdapter:
    """D-01 — every per-adapter helper populates Posting.salary verbatim."""

    def test_greenhouse_helper_populates_salary_from_metadata_label(self):
        """Greenhouse salary lives in raw['metadata'] list under name='Salary*'."""
        rp = RawPosting(
            source_company="stripe",
            source_adapter="greenhouse",
            raw={
                "id": 1,
                "title": "New Grad SWE",
                "location": {"name": "SF"},
                "absolute_url": "https://example.com",
                "updated_at": "2026-06-01T00:00:00Z",
                "metadata": [
                    {"name": "Department", "value": "Eng"},
                    {"name": "Salary Range", "value": "$120k–$160k"},
                ],
                "__dedup_key": "gh:stripe:1",
                "__board_token": "stripe",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == "$120k–$160k"

    def test_greenhouse_helper_salary_empty_when_no_metadata(self):
        """No metadata field → salary == ''."""
        rp = RawPosting(
            source_company="stripe",
            source_adapter="greenhouse",
            raw={
                "id": 2,
                "title": "T",
                "location": {"name": "SF"},
                "absolute_url": "https://example.com",
                "updated_at": "2026-06-01T00:00:00Z",
                "__dedup_key": "gh:stripe:2",
                "__board_token": "stripe",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == ""

    def test_greenhouse_helper_salary_empty_when_metadata_has_no_salary_entry(self):
        """metadata exists but contains no salary-named entry → ''."""
        rp = RawPosting(
            source_company="stripe",
            source_adapter="greenhouse",
            raw={
                "id": 3,
                "title": "T",
                "location": {"name": "SF"},
                "absolute_url": "https://example.com",
                "updated_at": "2026-06-01T00:00:00Z",
                "metadata": [
                    {"name": "Department", "value": "Eng"},
                    {"name": "Office", "value": "SF"},
                ],
                "__dedup_key": "gh:stripe:3",
                "__board_token": "stripe",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == ""

    def test_lever_helper_populates_salary_from_salary_range_text(self):
        """Lever raw['salaryRange']['text'] is preferred."""
        rp = RawPosting(
            source_company="notion",
            source_adapter="lever",
            raw={
                "id": "abc",
                "text": "New Grad SWE",
                "categories": {"location": "SF"},
                "hostedUrl": "https://jobs.lever.co/notion/abc",
                "createdAt": 1717200000000,
                "salaryRange": {"text": "$130,000 - $170,000 USD"},
                "__dedup_key": "lever:notion:abc",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == "$130,000 - $170,000 USD"

    def test_lever_helper_falls_back_to_flat_salary(self):
        """Lever raw['salary'] is fallback when salaryRange missing."""
        rp = RawPosting(
            source_company="notion",
            source_adapter="lever",
            raw={
                "id": "abc",
                "text": "New Grad SWE",
                "categories": {"location": "SF"},
                "hostedUrl": "https://jobs.lever.co/notion/abc",
                "createdAt": 1717200000000,
                "salary": "Competitive",
                "__dedup_key": "lever:notion:abc",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == "Competitive"

    def test_lever_helper_salary_empty_when_no_source_field(self):
        rp = RawPosting(
            source_company="notion",
            source_adapter="lever",
            raw={
                "id": "abc",
                "text": "T",
                "categories": {"location": "SF"},
                "hostedUrl": "https://jobs.lever.co/notion/abc",
                "createdAt": 1717200000000,
                "__dedup_key": "lever:notion:abc",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == ""

    def test_ashby_helper_populates_salary_from_compensation_tier_summary(self):
        """Ashby raw['compensation']['compensationTierSummary'] (per includeCompensation=true)."""
        rp = RawPosting(
            source_company="notion",
            source_adapter="ashby",
            raw={
                "id": "ashby-id",
                "title": "SWE",
                "locationName": "SF",
                "jobUrl": "https://jobs.ashbyhq.com/notion/ashby-id",
                "publishedAt": "2026-06-01T00:00:00Z",
                "compensation": {
                    "compensationTierSummary": "$140K - $180K • Equity",
                },
                "__dedup_key": "ashby:notion:ashby-id",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == "$140K - $180K • Equity"

    def test_ashby_helper_salary_empty_when_compensation_none(self):
        """Defensive — compensation: None → salary == ''."""
        rp = RawPosting(
            source_company="notion",
            source_adapter="ashby",
            raw={
                "id": "ashby-id",
                "title": "SWE",
                "locationName": "SF",
                "jobUrl": "https://jobs.ashbyhq.com/notion/ashby-id",
                "publishedAt": "2026-06-01T00:00:00Z",
                "compensation": None,
                "__dedup_key": "ashby:notion:ashby-id",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == ""

    def test_smartrecruiters_helper_salary_always_empty(self):
        """SR /postings endpoint does not expose salary — always ''."""
        rp = RawPosting(
            source_company="notion",
            source_adapter="smartrecruiters",
            raw={
                "id": "sr-id",
                "name": "SWE",
                "location": {"city": "NYC", "country": "US"},
                "ref": "https://api.smartrecruiters.com/v1/companies/notion/postings/sr-id",
                "releasedDate": "2026-06-01T00:00:00.000Z",
                "__dedup_key": "sr:notion:sr-id",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == ""

    def test_workday_helper_salary_always_empty(self):
        """Workday CXS /jobs endpoint does not expose salary — always ''."""
        rp = RawPosting(
            source_company="nvidia",
            source_adapter="workday",
            raw={
                "title": "SWE",
                "locationsText": "US, CA",
                "__posting_url": "https://nvidia.wd5.myworkdayjobs.com/job/R-1",
                "__posted_date_utc": None,
                "__dedup_key": "wd:nvidia:R-1",
                "__tenant": "nvidia",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == ""

    def test_apple_helper_populates_salary_from_posting_pay_range(self):
        """Apple raw['postingPay']['payRange']['text'] is preferred."""
        rp = RawPosting(
            source_company="Apple",
            source_adapter="apple",
            raw={
                "id": "200500000",
                "positionId": "200500000",
                "postingTitle": "SWE",
                "transformedPostingTitle": "swe",
                "postingDate": "2026-06-02T10:00:00Z",
                "locations": [{"name": "Cupertino, CA"}],
                "postingPay": {"payRange": {"text": "$135,000 - $200,000"}},
                "__dedup_key": "apple:200500000",
                "__position_id": "200500000",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == "$135,000 - $200,000"

    def test_apple_helper_salary_empty_when_no_known_fields(self):
        rp = RawPosting(
            source_company="Apple",
            source_adapter="apple",
            raw={
                "id": "200500001",
                "positionId": "200500001",
                "postingTitle": "SWE",
                "transformedPostingTitle": "swe",
                "postingDate": "2026-06-02T10:00:00Z",
                "locations": [{"name": "Cupertino, CA"}],
                "__dedup_key": "apple:200500001",
                "__position_id": "200500001",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == ""

    def test_playwright_helper_populates_salary_from_raw_salary(self):
        """Playwright raw['salary'] when XHR/DOM extracted it."""
        rp = RawPosting(
            source_company="anthropic",
            source_adapter="playwright",
            raw={
                "id": "j-100",
                "title": "SWE",
                "location": "SF",
                "posting_url": "https://anthropic.com/careers/j-100",
                "postingDate": "2026-06-01T12:00:00Z",
                "description": "",
                "salary": "$150,000 base + equity",
                "__dedup_key": "pw:anthropic.com:j-100",
                "__host": "anthropic.com",
                "__extraction_path": "xhr",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == "$150,000 base + equity"

    def test_playwright_helper_salary_empty_when_no_field(self):
        rp = RawPosting(
            source_company="anthropic",
            source_adapter="playwright",
            raw={
                "title": "SWE",
                "location": "SF",
                "posting_url": "https://anthropic.com/careers/j-100",
                "description": "",
                "__dedup_key": "pw:anthropic.com:j-100",
                "__host": "anthropic.com",
                "__extraction_path": "dom",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.salary == ""


# --- Phase 4 Plan 04-01 — location routed through normalize_location (D-02) ---


class TestLocationNormalizationPerAdapter:
    """D-02 — every per-adapter helper routes location through normalize_location."""

    def test_greenhouse_routes_location_through_normalize(self):
        rp = RawPosting(
            source_company="stripe",
            source_adapter="greenhouse",
            raw={
                "id": 10,
                "title": "T",
                "location": {"name": "Remote, US"},
                "absolute_url": "https://example.com",
                "updated_at": "2026-06-01T00:00:00Z",
                "__dedup_key": "gh:stripe:10",
                "__board_token": "stripe",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.location == "Remote (US)"

    def test_lever_routes_location_through_normalize(self):
        rp = RawPosting(
            source_company="notion",
            source_adapter="lever",
            raw={
                "id": "abc",
                "text": "T",
                "categories": {"location": "Remote, US"},
                "hostedUrl": "https://jobs.lever.co/notion/abc",
                "createdAt": 1717200000000,
                "__dedup_key": "lever:notion:abc",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.location == "Remote (US)"

    def test_ashby_routes_location_through_normalize(self):
        rp = RawPosting(
            source_company="notion",
            source_adapter="ashby",
            raw={
                "id": "x",
                "title": "T",
                "locationName": "Remote (UK)",
                "jobUrl": "https://jobs.ashbyhq.com/notion/x",
                "publishedAt": "2026-06-01T00:00:00Z",
                "__dedup_key": "ashby:notion:x",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.location == "Remote (non-US)"

    def test_smartrecruiters_routes_location_through_normalize(self):
        """SR composes 'city, country' — composed string is normalized.

        Note: SR's typical 'city, country' shape does not match the Remote-form
        patterns, so this test verifies passthrough of a non-Remote value via
        normalize_location. The bare 'Remote' case is exercised by other adapters."""
        rp = RawPosting(
            source_company="notion",
            source_adapter="smartrecruiters",
            raw={
                "id": "x",
                "name": "T",
                "location": {"city": "San Francisco", "country": "US"},
                "ref": "https://api.smartrecruiters.com/v1/companies/notion/postings/x",
                "releasedDate": "2026-06-01T00:00:00.000Z",
                "__dedup_key": "sr:notion:x",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        # Composed "San Francisco, US" is not a Remote-form variant — passthrough.
        assert p.location == "San Francisco, US"

    def test_workday_routes_location_through_normalize(self):
        rp = RawPosting(
            source_company="nvidia",
            source_adapter="workday",
            raw={
                "title": "T",
                "locationsText": "Remote (USA)",
                "__posting_url": "https://nvidia.wd5.myworkdayjobs.com/job/R-1",
                "__posted_date_utc": None,
                "__dedup_key": "wd:nvidia:R-1",
                "__tenant": "nvidia",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.location == "Remote (US)"

    def test_apple_composes_then_normalizes_location(self):
        """Apple location is composed from list of dicts before normalize."""
        rp = RawPosting(
            source_company="Apple",
            source_adapter="apple",
            raw={
                "id": "200500010",
                "positionId": "200500010",
                "postingTitle": "T",
                "transformedPostingTitle": "t",
                "postingDate": "2026-06-02T10:00:00Z",
                "locations": [{"name": "Remote"}],  # single-element composed → "Remote"
                "__dedup_key": "apple:200500010",
                "__position_id": "200500010",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        # Composed "Remote" → bare-Remote rule → "Remote (US)".
        assert p.location == "Remote (US)"

    def test_playwright_routes_location_through_normalize(self):
        rp = RawPosting(
            source_company="anthropic",
            source_adapter="playwright",
            raw={
                "title": "T",
                "location": "Remote, US",
                "posting_url": "https://anthropic.com/careers/x",
                "description": "",
                "__dedup_key": "pw:anthropic.com:x",
                "__host": "anthropic.com",
                "__extraction_path": "xhr",
            },
        )
        p = normalize(rp, _RUN_STARTED_AT)
        assert p.location == "Remote (US)"
