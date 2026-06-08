"""Ashby adapter tests — ADP-05 + CONTEXT.md D-03.

Tests:
  1. test_matches_jobs_ashbyhq_com           — match-positive
  2. test_does_not_match_lever               — match-negative
  3. test_fetch_happy_path                   — synthetic fixture → list[RawPosting]
  4. test_fetch_emits_stable_dedup_key       — `ashby:<org>:<uuid>`
  5. test_fetch_raises_schema_drift_on_missing_jobs_key
  6. test_fetch_raises_schema_drift_on_wrong_jobs_type
  7. test_fetch_raises_site_blocked_on_403
  8. test_fetch_raises_site_blocked_on_429
  9. test_fetch_propagates_generic_exception — httpx.NetworkError
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from src.adapters.ashby import AshbyAdapter
from src.adapters.base import SchemaDrift, SiteBlocked
from src.models import CompanyConfig

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ashby_sample.json"
_API = (
    "https://api.ashbyhq.com/posting-api/job-board/notion?includeCompensation=true"
)


@pytest.fixture()
def ashby_fixture():
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def notion_company():
    return CompanyConfig(
        name="notion",
        url="https://jobs.ashbyhq.com/notion",
        hint=None,
    )


# --- matches() ---------------------------------------------------------------

def test_matches_jobs_ashbyhq_com():
    assert AshbyAdapter.matches("https://jobs.ashbyhq.com/notion") is True


def test_does_not_match_lever():
    assert AshbyAdapter.matches("https://jobs.lever.co/notion") is False


# --- fetch() happy path ------------------------------------------------------

@respx.mock
def test_fetch_happy_path(ashby_fixture, notion_company):
    respx.get(_API).mock(return_value=httpx.Response(200, json=ashby_fixture))
    raw_postings = AshbyAdapter().fetch(notion_company)

    assert len(raw_postings) == 3
    for rp in raw_postings:
        assert rp.source_adapter == "ashby"
        assert rp.source_company == "notion"
        assert "id" in rp.raw
        assert rp.raw["__dedup_key"].startswith("ashby:notion:")
        assert rp.raw["__identifier"] == "notion"


@respx.mock
def test_fetch_emits_stable_dedup_key(ashby_fixture, notion_company):
    respx.get(_API).mock(return_value=httpx.Response(200, json=ashby_fixture))
    raw_postings = AshbyAdapter().fetch(notion_company)
    keys = [rp.raw["__dedup_key"] for rp in raw_postings]
    expected = [f"ashby:notion:{j['id']}" for j in ashby_fixture["jobs"]]
    assert keys == expected


# --- fetch() error paths (D-03) ----------------------------------------------

@respx.mock
def test_fetch_raises_schema_drift_on_missing_jobs_key(notion_company):
    respx.get(_API).mock(return_value=httpx.Response(200, json={"meta": {}}))
    with pytest.raises(SchemaDrift):
        AshbyAdapter().fetch(notion_company)


@respx.mock
def test_fetch_raises_schema_drift_on_wrong_jobs_type(notion_company):
    respx.get(_API).mock(
        return_value=httpx.Response(200, json={"jobs": "not a list"})
    )
    with pytest.raises(SchemaDrift):
        AshbyAdapter().fetch(notion_company)


@respx.mock
def test_fetch_raises_site_blocked_on_403(notion_company):
    respx.get(_API).mock(return_value=httpx.Response(403, text="Forbidden"))
    with pytest.raises(SiteBlocked):
        AshbyAdapter().fetch(notion_company)


@respx.mock
def test_fetch_raises_site_blocked_on_429(notion_company):
    respx.get(_API).mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )
    with pytest.raises(SiteBlocked):
        AshbyAdapter().fetch(notion_company)


@respx.mock
def test_fetch_propagates_generic_exception(notion_company):
    respx.get(_API).mock(side_effect=httpx.NetworkError("dns failure"))
    with pytest.raises(httpx.HTTPError):
        AshbyAdapter().fetch(notion_company)
