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
        # Posting URL is the tenant-rooted absolute form of externalPath.
        assert rp.raw["__posting_url"].startswith(
            "https://nvidia.wd5.myworkdayjobs.com/"
        )
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
