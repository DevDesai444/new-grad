"""Workday adapter tests — ADP-07 + CONTEXT.md D-01 / D-03 / D-04.

Tests are organized in groups:

  matches() / URL parser (D-01):
    1. test_matches_workday_host
    2. test_does_not_match_lever
    3. test_parse_url_happy_with_locale
    4. test_parse_url_happy_no_locale
    5. test_parse_url_trailing_slash_ok
    6. test_parse_url_malformed_no_host
    7. test_parse_url_malformed_no_site

  fetch() single-page happy path:
    8. test_fetch_happy_path_single_page
    9. test_fetch_dedup_keys_use_wd_tenant_prefix

  postedOn multi-form parser:
    10. test_parse_postedon_epoch_ms
    11. test_parse_postedon_iso
    12. test_parse_postedon_today
    13. test_parse_postedon_yesterday
    14. test_parse_postedon_n_days_ago
    15. test_parse_postedon_n_plus_days_ago
    16. test_parse_postedon_unknown_returns_none

  Error paths (D-03):
    17. test_fetch_raises_schema_drift_on_missing_jobpostings_key
    18. test_fetch_raises_schema_drift_on_wrong_jobpostings_type
    19. test_fetch_raises_site_blocked_on_403
    20. test_fetch_raises_site_blocked_on_429
    21. test_fetch_propagates_generic_exception
    22. test_fetch_raises_schema_drift_on_malformed_url

  Headers / UA (Pitfall 5):
    23. test_fetch_sends_realistic_user_agent

Task 2 appends pagination + monotonicity + normalizer-roundtrip tests to this
same file.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from src.adapters.base import SchemaDrift, SiteBlocked
from src.adapters.workday import (
    WorkdayAdapter,
    _parse_workday_posted,
    _parse_workday_url,
)
from src.models import CompanyConfig

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "workday_sample.json"
_API = (
    "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/"
    "NVIDIAExternalCareerSite/jobs"
)


@pytest.fixture()
def workday_fixture():
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def nvidia_company():
    return CompanyConfig(
        name="nvidia",
        url="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        hint=None,
    )


@pytest.fixture()
def run_started_at():
    return datetime(2026, 6, 7, 14, 0, tzinfo=UTC)


# --- matches() ----------------------------------------------------------------


def test_matches_workday_host():
    assert (
        WorkdayAdapter.matches(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
        )
        is True
    )


def test_does_not_match_lever():
    assert WorkdayAdapter.matches("https://jobs.lever.co/notion") is False


# --- URL parser (D-01) --------------------------------------------------------


def test_parse_url_happy_with_locale():
    parts = _parse_workday_url(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"
    )
    assert parts.tenant == "nvidia"
    assert parts.wd_num == "5"
    assert parts.site == "NVIDIAExternalCareerSite"


def test_parse_url_happy_no_locale():
    parts = _parse_workday_url(
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
    )
    assert parts == ("nvidia", "5", "NVIDIAExternalCareerSite")


def test_parse_url_trailing_slash_ok():
    parts = _parse_workday_url(
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/"
    )
    assert parts == ("nvidia", "5", "NVIDIAExternalCareerSite")


def test_parse_url_microsoft_wd1():
    # Locked example from prompt: microsoft.wd1.myworkdayjobs.com/en-US/MSWeb
    parts = _parse_workday_url(
        "https://microsoft.wd1.myworkdayjobs.com/en-US/MSWeb"
    )
    assert parts == ("microsoft", "1", "MSWeb")


def test_parse_url_malformed_no_host():
    with pytest.raises(SchemaDrift, match="missing tenant"):
        _parse_workday_url("https://example.com/foo")


def test_parse_url_malformed_no_site():
    with pytest.raises(SchemaDrift, match="site segment is missing"):
        _parse_workday_url("https://nvidia.wd5.myworkdayjobs.com/")


# --- fetch() happy path (single page) -----------------------------------------


@respx.mock
def test_fetch_happy_path_single_page(workday_fixture, nvidia_company):
    respx.post(_API).mock(
        return_value=httpx.Response(200, json=workday_fixture)
    )
    raw_postings = WorkdayAdapter().fetch(nvidia_company)

    assert len(raw_postings) == 5
    for rp in raw_postings:
        assert rp.source_adapter == "workday"
        assert rp.source_company == "nvidia"
        assert rp.raw["__dedup_key"].startswith("wd:nvidia:")
        assert rp.raw["__tenant"] == "nvidia"
        # Bug G regression — posting URL MUST include `/en-US/<site>` between
        # host and externalPath. Without it, every Workday link 404s.
        assert rp.raw["__posting_url"].startswith(
            "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/"
        ), f"Workday URL missing /en-US/<site> prefix: {rp.raw['__posting_url']}"
        # All postedOn forms in the fixture should resolve to a UTC datetime.
        assert isinstance(rp.raw["__posted_date_utc"], datetime)
        assert rp.raw["__posted_date_utc"].tzinfo is not None


@respx.mock
def test_fetch_dedup_keys_use_wd_tenant_prefix(workday_fixture, nvidia_company):
    respx.post(_API).mock(
        return_value=httpx.Response(200, json=workday_fixture)
    )
    raw_postings = WorkdayAdapter().fetch(nvidia_company)
    keys = [rp.raw["__dedup_key"] for rp in raw_postings]
    expected = [
        f"wd:nvidia:{p['bulletFields'][0]}"
        for p in workday_fixture["jobPostings"]
    ]
    assert keys == expected
    # Regression: never `nvidia:` without `wd:` prefix.
    for k in keys:
        assert k.startswith("wd:")


# --- postedOn multi-form parser ----------------------------------------------


def test_parse_postedon_epoch_ms(run_started_at):
    # 1748707200000 ms = 2025-05-31T17:20:00 UTC (math: 1748707200 / 86400 = 20239
    # days since epoch -> 2025-05-31). The exact value is locked by the helper —
    # we assert the conversion is calendar-correct within 1 second.
    expected = datetime.fromtimestamp(1748707200000 / 1000.0, tz=UTC)
    got = _parse_workday_posted(1748707200000, run_started_at)
    assert got is not None
    assert abs((got - expected).total_seconds()) < 1.0


def test_parse_postedon_iso(run_started_at):
    got = _parse_workday_posted("2026-06-01T14:00:00+00:00", run_started_at)
    assert got == datetime(2026, 6, 1, 14, 0, tzinfo=UTC)


def test_parse_postedon_iso_z_suffix(run_started_at):
    got = _parse_workday_posted("2026-06-01T14:00:00Z", run_started_at)
    assert got == datetime(2026, 6, 1, 14, 0, tzinfo=UTC)


def test_parse_postedon_today(run_started_at):
    assert _parse_workday_posted("Posted Today", run_started_at) == run_started_at


def test_parse_postedon_yesterday(run_started_at):
    assert (
        _parse_workday_posted("Posted Yesterday", run_started_at)
        == run_started_at - timedelta(days=1)
    )


def test_parse_postedon_n_days_ago(run_started_at):
    assert (
        _parse_workday_posted("Posted 3 Days Ago", run_started_at)
        == run_started_at - timedelta(days=3)
    )


def test_parse_postedon_n_plus_days_ago(run_started_at):
    # "30+ Days Ago" is a LOWER bound (at least 30 days old).
    assert (
        _parse_workday_posted("Posted 30+ Days Ago", run_started_at)
        == run_started_at - timedelta(days=30)
    )


def test_parse_postedon_unknown_returns_none(run_started_at):
    assert _parse_workday_posted("tomorrow", run_started_at) is None
    assert _parse_workday_posted("", run_started_at) is None
    assert _parse_workday_posted(None, run_started_at) is None
    # bool is rejected (subclass of int but not a real epoch ms value).
    assert _parse_workday_posted(True, run_started_at) is None


# --- Error paths (D-03) -------------------------------------------------------


@respx.mock
def test_fetch_raises_schema_drift_on_missing_jobpostings_key(nvidia_company):
    respx.post(_API).mock(return_value=httpx.Response(200, json={"total": 0}))
    with pytest.raises(SchemaDrift, match="missing 'jobPostings' key"):
        WorkdayAdapter().fetch(nvidia_company)


@respx.mock
def test_fetch_raises_schema_drift_on_wrong_jobpostings_type(nvidia_company):
    respx.post(_API).mock(
        return_value=httpx.Response(
            200, json={"jobPostings": "not a list", "total": 1},
        )
    )
    with pytest.raises(SchemaDrift, match="'jobPostings' is not a list"):
        WorkdayAdapter().fetch(nvidia_company)


@respx.mock
def test_fetch_raises_site_blocked_on_403(nvidia_company):
    respx.post(_API).mock(return_value=httpx.Response(403, text="Forbidden"))
    with pytest.raises(SiteBlocked):
        WorkdayAdapter().fetch(nvidia_company)


@respx.mock
def test_fetch_raises_site_blocked_on_429(nvidia_company):
    respx.post(_API).mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )
    with pytest.raises(SiteBlocked):
        WorkdayAdapter().fetch(nvidia_company)


@respx.mock
def test_fetch_propagates_generic_exception(nvidia_company):
    respx.post(_API).mock(side_effect=httpx.NetworkError("dns failure"))
    with pytest.raises(httpx.HTTPError):
        WorkdayAdapter().fetch(nvidia_company)


def test_fetch_raises_schema_drift_on_malformed_url():
    bad_company = CompanyConfig(
        name="bad", url="https://broken.example/foo", hint=None,
    )
    with pytest.raises(SchemaDrift, match="missing tenant"):
        WorkdayAdapter().fetch(bad_company)


# --- Headers / UA (Pitfall 5) -------------------------------------------------


@respx.mock
def test_fetch_sends_realistic_user_agent(workday_fixture, nvidia_company):
    route = respx.post(_API).mock(
        return_value=httpx.Response(200, json=workday_fixture)
    )
    WorkdayAdapter().fetch(nvidia_company)
    assert route.called
    sent_headers = route.calls.last.request.headers
    assert "new-grad" in sent_headers.get("User-Agent", "")
    assert "python-httpx" not in sent_headers.get("User-Agent", "")
    assert sent_headers.get("Content-Type") == "application/json"
    assert sent_headers.get("Accept") == "application/json"


# ============================================================================
# Task 2: D-04 pagination + sort-monotonicity + normalizer dispatch tests.
# ============================================================================


def _make_posting(req_id: int, *, posted_on=1748707200000) -> dict:
    """Build a Workday-shaped posting dict with a unique bulletFields[0]."""
    return {
        "title": f"Software Engineer {req_id}",
        "externalPath": (
            f"/en-US/NVIDIAExternalCareerSite/job/Test/SWE_R-{req_id}"
        ),
        "locationsText": "US, CA, Santa Clara",
        "postedOn": posted_on,
        "bulletFields": [f"R-{req_id}"],
    }


def _make_page(req_ids: list[int], *, posted_on=1748707200000) -> dict:
    return {
        "total": len(req_ids),
        "jobPostings": [
            _make_posting(i, posted_on=posted_on) for i in req_ids
        ],
    }


# --- Pagination (D-04) -------------------------------------------------------


@respx.mock
def test_fetch_paginates_until_empty_page(nvidia_company, monkeypatch):
    """Page 0: 20 postings. Page 1: 20. Page 2: 0 -> stop. Return 40 total."""
    monkeypatch.setattr("src.adapters.workday.time.sleep", lambda s: None)
    page0 = _make_page(list(range(20)))
    page1 = _make_page(list(range(20, 40)))
    page2 = {"total": 40, "jobPostings": []}
    route = respx.post(_API).mock(side_effect=[
        httpx.Response(200, json=page0),
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ])
    raw = WorkdayAdapter().fetch(nvidia_company)
    assert len(raw) == 40
    # Three POST requests sent (page 0, 1, 2).
    assert route.call_count == 3


@respx.mock
def test_fetch_paginates_until_seen_keys_overlap(nvidia_company, monkeypatch):
    """When seen_keys hits the last-on-page key, stop without requesting next page."""
    monkeypatch.setattr("src.adapters.workday.time.sleep", lambda s: None)
    page0 = _make_page(list(range(20)))             # ids 0..19; last = R-19
    page1 = _make_page(list(range(20, 40)))         # ids 20..39; last = R-39
    page2 = _make_page(list(range(40, 60)))         # not expected to be reached
    route = respx.post(_API).mock(side_effect=[
        httpx.Response(200, json=page0),
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ])
    raw = WorkdayAdapter().fetch(
        nvidia_company, seen_keys={"wd:nvidia:R-39"}
    )
    # Pages 0 + 1 fully collected; page 2 NOT requested.
    assert len(raw) == 40
    assert route.call_count == 2


@respx.mock
def test_fetch_cold_start_cap_25_pages(nvidia_company, monkeypatch):
    """Cold start (no seen_keys) caps at 25 pages even if source has more."""
    monkeypatch.setattr("src.adapters.workday.time.sleep", lambda s: None)
    # Build 30 pages of 20 postings each (each posting must have a unique
    # bulletFields[0] so dedup keys don't collide).
    pages = [
        httpx.Response(
            200, json=_make_page(list(range(p * 20, (p + 1) * 20))),
        )
        for p in range(30)
    ]
    route = respx.post(_API).mock(side_effect=pages)
    raw = WorkdayAdapter().fetch(nvidia_company)
    assert len(raw) == 25 * 20  # 500 postings, hard cap
    assert route.call_count == 25


@respx.mock
def test_fetch_short_page_breaks_loop(nvidia_company, monkeypatch):
    """A page of fewer than _PAGE_SIZE postings ends pagination."""
    monkeypatch.setattr("src.adapters.workday.time.sleep", lambda s: None)
    # Single short page (5 postings) -> stop after 1 request.
    short_page = _make_page(list(range(5)))
    route = respx.post(_API).mock(side_effect=[
        httpx.Response(200, json=short_page),
    ])
    raw = WorkdayAdapter().fetch(nvidia_company)
    assert len(raw) == 5
    assert route.call_count == 1


# --- Sort-monotonicity check -------------------------------------------------


@respx.mock
def test_fetch_sort_monotonicity_violation_logs_warning(
    nvidia_company, monkeypatch, caplog,
):
    """If page N+1's first is newer than page N's last, log + suppress early-term."""
    import logging
    monkeypatch.setattr("src.adapters.workday.time.sleep", lambda s: None)
    # Page 0's last posting is "5 days ago"; page 1's first is "Posted Today"
    # (newer). Use string postedOn so the relative-form parser resolves them.
    # Build page 0 as 20 postings with explicit per-posting postedOn — the LAST
    # one is "5 Days Ago".
    page0_postings = [_make_posting(i, posted_on="Posted Today") for i in range(19)]
    page0_postings.append(_make_posting(19, posted_on="Posted 5 Days Ago"))
    page0 = {"total": 40, "jobPostings": page0_postings}

    # Page 1: first posting is "Posted Today" (newer than page 0's "5 Days Ago").
    page1_postings = [_make_posting(20, posted_on="Posted Today")]
    page1_postings.extend(
        _make_posting(i, posted_on="Posted 5 Days Ago")
        for i in range(21, 40)
    )
    page1 = {"total": 40, "jobPostings": page1_postings}

    # Page 2: empty -> stop normally.
    page2 = {"total": 40, "jobPostings": []}

    respx.post(_API).mock(side_effect=[
        httpx.Response(200, json=page0),
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ])

    with caplog.at_level(logging.WARNING, logger="scan"):
        raw = WorkdayAdapter().fetch(nvidia_company)

    # All 40 postings collected (no early break — we DON'T stop on monotonicity
    # violation; we only suppress further early-termination).
    assert len(raw) == 40

    # Warning logged with the canonical phrase.
    monotonicity_warnings = [
        rec for rec in caplog.records
        if rec.levelno == logging.WARNING
        and "sort-monotonicity violation" in rec.getMessage()
    ]
    assert len(monotonicity_warnings) == 1, (
        f"expected 1 monotonicity warning, got "
        f"{[r.getMessage() for r in caplog.records]}"
    )


# --- Normalizer dispatch -----------------------------------------------------


def test_normalize_workday_roundtrip(run_started_at):
    """Build a RawPosting with adapter-stashed metadata; verify normalize() output."""
    from src.models import RawPosting
    from src.normalizer import canonicalize_url, normalize

    posted = datetime(2026, 5, 31, 17, 20, tzinfo=UTC)
    raw = {
        "title": "Software Engineer, New Grad",
        "locationsText": "US, CA, Santa Clara",
        "externalPath": (
            "/en-US/NVIDIAExternalCareerSite/job/Santa-Clara/SWE_R-101"
        ),
        "postedOn": 1748707200000,
        "bulletFields": ["R-101"],
        "__dedup_key": "wd:nvidia:R-101",
        "__tenant": "nvidia",
        "__posting_url": (
            "https://nvidia.wd5.myworkdayjobs.com"
            "/en-US/NVIDIAExternalCareerSite/job/Santa-Clara/SWE_R-101"
        ),
        "__posted_date_utc": posted,
    }
    rp = RawPosting(
        source_company="nvidia",
        source_adapter="workday",
        raw=raw,
    )
    posting = normalize(rp, run_started_at)

    assert posting.dedup_key == "wd:nvidia:R-101"
    assert posting.title == "Software Engineer, New Grad"
    assert posting.location == "US, CA, Santa Clara"
    assert posting.posting_url == canonicalize_url(raw["__posting_url"])
    assert posting.posted_date == posted
    assert posting.experience_min is None
    assert posting.experience_max is None
    assert posting.source_adapter == "workday"
    # Company is title-cased from lowercase source value.
    assert posting.company == "Nvidia"
    assert posting.first_seen == run_started_at
    assert posting.last_seen == run_started_at
    assert posting.still_listed is True


def test_normalize_workday_missing_postedon_yields_none_date(run_started_at):
    """If __posted_date_utc is None, the normalized Posting has posted_date=None."""
    from src.models import RawPosting
    from src.normalizer import normalize

    raw = {
        "title": "Engineer",
        "locationsText": "Remote",
        "__dedup_key": "wd:nvidia:R-X",
        "__tenant": "nvidia",
        "__posting_url": (
            "https://nvidia.wd5.myworkdayjobs.com/job/X"
        ),
        "__posted_date_utc": None,
    }
    rp = RawPosting(
        source_company="nvidia",
        source_adapter="workday",
        raw=raw,
    )
    posting = normalize(rp, run_started_at)
    assert posting.posted_date is None


def test_normalize_workday_iso_string_round_trip(run_started_at):
    """Defensive: if __posted_date_utc round-trips through JSON as a string, reparse."""
    from src.models import RawPosting
    from src.normalizer import normalize

    raw = {
        "title": "Engineer",
        "locationsText": "Remote",
        "__dedup_key": "wd:nvidia:R-Y",
        "__tenant": "nvidia",
        "__posting_url": (
            "https://nvidia.wd5.myworkdayjobs.com/job/Y"
        ),
        "__posted_date_utc": "2026-06-01T14:00:00+00:00",
    }
    rp = RawPosting(
        source_company="nvidia",
        source_adapter="workday",
        raw=raw,
    )
    posting = normalize(rp, run_started_at)
    assert posting.posted_date == datetime(2026, 6, 1, 14, 0, tzinfo=UTC)


# --- Registry contract -------------------------------------------------------


def test_workday_registered_in_adapters_list():
    from src.registry import ADAPTERS

    names = [cls.name for cls in ADAPTERS]
    assert "workday" in names
    assert WorkdayAdapter in ADAPTERS


def test_workday_dispatch_via_registry(nvidia_company):
    """Registry returns a WorkdayAdapter instance for the Workday URL."""
    from src.registry import get_adapter

    adapter = get_adapter(nvidia_company)
    assert isinstance(adapter, WorkdayAdapter)


# --- Bug C regression: adapter must honor company.resolved_url ----------------

@respx.mock
def test_fetch_uses_resolved_url_when_set(workday_fixture):
    """Bug C regression — when `resolved_url` is populated (by url_resolver
    body-scan finding the Workday tenant URL inside a CNAME's HTML), the
    adapter MUST parse the RESOLVED URL, not the original `url`.

    Production failure mode this protects against:
      careers.arrow.com → resolver body-scan finds
      arrow.wd1.myworkdayjobs.com → adapter ignored the resolved URL and tried
      to regex-parse careers.arrow.com → SchemaDrift. Test asserts the adapter
      uses the resolved URL and successfully fetches.
    """
    company = CompanyConfig(
        name="nvidia",
        url="https://careers.example.com",  # original CNAME, NOT a Workday URL
        resolved_url=(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
        ),
        hint=None,
    )
    respx.post(_API).mock(
        return_value=httpx.Response(200, json=workday_fixture)
    )
    raw_postings = WorkdayAdapter().fetch(company)
    assert len(raw_postings) == 5
    for rp in raw_postings:
        assert rp.raw["__tenant"] == "nvidia"
        assert rp.raw["__dedup_key"].startswith("wd:nvidia:")

