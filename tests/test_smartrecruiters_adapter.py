"""SmartRecruiters adapter tests — ADP-06 + CONTEXT.md D-03.

Tests:
  1. test_matches_careers_smartrecruiters_com       — match-positive
  2. test_does_not_match_ashby                      — match-negative
  3. test_fetch_happy_path                          — synthetic fixture → list[RawPosting]
  4. test_fetch_emits_stable_dedup_key_with_sr_prefix — locks the deliberate
     `name="smartrecruiters"` vs dedup-prefix=`"sr:"` split (CONTEXT.md D-01a)
  5. test_fetch_raises_schema_drift_on_missing_content_key
  6. test_fetch_raises_schema_drift_on_wrong_content_type
  7. test_fetch_raises_site_blocked_on_403
  8. test_fetch_raises_site_blocked_on_429
  9. test_fetch_propagates_generic_exception        — httpx.NetworkError
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from src.adapters.base import SchemaDrift, SiteBlocked
from src.adapters.smartrecruiters import SmartRecruitersAdapter
from src.models import CompanyConfig

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "smartrecruiters_sample.json"
_API = "https://api.smartrecruiters.com/v1/companies/notion/postings"


@pytest.fixture()
def sr_fixture():
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def notion_company():
    return CompanyConfig(
        name="notion",
        url="https://careers.smartrecruiters.com/notion",
        hint=None,
    )


# --- matches() ---------------------------------------------------------------

def test_matches_careers_smartrecruiters_com():
    assert (
        SmartRecruitersAdapter.matches("https://careers.smartrecruiters.com/notion")
        is True
    )


def test_does_not_match_ashby():
    assert (
        SmartRecruitersAdapter.matches("https://jobs.ashbyhq.com/notion") is False
    )


# --- fetch() happy path ------------------------------------------------------

@respx.mock
def test_fetch_happy_path(sr_fixture, notion_company):
    respx.get(_API).mock(return_value=httpx.Response(200, json=sr_fixture))
    raw_postings = SmartRecruitersAdapter().fetch(notion_company)

    assert len(raw_postings) == 3
    for rp in raw_postings:
        # NB: Adapter.name is "smartrecruiters" (full); dedup prefix is "sr:" (short).
        # See module docstring + CONTEXT.md D-01a for the deliberate split.
        assert rp.source_adapter == "smartrecruiters"
        assert rp.source_company == "notion"
        assert "id" in rp.raw
        assert rp.raw["__dedup_key"].startswith("sr:")
        assert rp.raw["__identifier"] == "notion"


@respx.mock
def test_fetch_emits_stable_dedup_key_with_sr_prefix(sr_fixture, notion_company):
    """Locks the deliberate name vs prefix split: dedup prefix MUST be "sr:" and
    MUST NOT be "smartrecruiters:" (CONTEXT.md D-01a + ADP-06)."""
    respx.get(_API).mock(return_value=httpx.Response(200, json=sr_fixture))
    raw_postings = SmartRecruitersAdapter().fetch(notion_company)
    for rp in raw_postings:
        assert rp.raw["__dedup_key"].startswith("sr:"), rp.raw["__dedup_key"]
        assert not rp.raw["__dedup_key"].startswith("smartrecruiters:"), (
            rp.raw["__dedup_key"]
        )
    keys = [rp.raw["__dedup_key"] for rp in raw_postings]
    expected = [f"sr:notion:{p['id']}" for p in sr_fixture["content"]]
    assert keys == expected


# --- fetch() error paths (D-03) ----------------------------------------------

@respx.mock
def test_fetch_raises_schema_drift_on_missing_content_key(notion_company):
    respx.get(_API).mock(return_value=httpx.Response(200, json={"totalFound": 0}))
    with pytest.raises(SchemaDrift):
        SmartRecruitersAdapter().fetch(notion_company)


@respx.mock
def test_fetch_raises_schema_drift_on_wrong_content_type(notion_company):
    respx.get(_API).mock(
        return_value=httpx.Response(200, json={"content": "not a list"})
    )
    with pytest.raises(SchemaDrift):
        SmartRecruitersAdapter().fetch(notion_company)


@respx.mock
def test_fetch_raises_site_blocked_on_403(notion_company):
    respx.get(_API).mock(return_value=httpx.Response(403, text="Forbidden"))
    with pytest.raises(SiteBlocked):
        SmartRecruitersAdapter().fetch(notion_company)


@respx.mock
def test_fetch_raises_site_blocked_on_429(notion_company):
    respx.get(_API).mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )
    with pytest.raises(SiteBlocked):
        SmartRecruitersAdapter().fetch(notion_company)


@respx.mock
def test_fetch_propagates_generic_exception(notion_company):
    respx.get(_API).mock(side_effect=httpx.NetworkError("dns failure"))
    with pytest.raises(httpx.HTTPError):
        SmartRecruitersAdapter().fetch(notion_company)
