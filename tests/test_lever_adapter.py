"""Lever adapter tests — ADP-04 + CONTEXT.md D-03 (closes part of D-07 debt).

Tests:
  1. test_matches_jobs_lever_co            — match-positive
  2. test_does_not_match_greenhouse        — match-negative
  3. test_fetch_happy_path                 — synthetic fixture → list[RawPosting]
  4. test_fetch_emits_stable_dedup_key     — `lever:<co>:<uuid>` extracted from `id`
  5. test_fetch_raises_schema_drift_on_dict_instead_of_list   — wrong top-level shape
  6. test_fetch_raises_schema_drift_on_int_instead_of_list    — wrong top-level type
  7. test_fetch_raises_site_blocked_on_403
  8. test_fetch_raises_site_blocked_on_429
  9. test_fetch_propagates_generic_exception                  — httpx.NetworkError
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from src.adapters.base import SchemaDrift, SiteBlocked
from src.adapters.lever import LeverAdapter
from src.models import CompanyConfig

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lever_sample.json"
_API = "https://api.lever.co/v0/postings/notion?mode=json"


@pytest.fixture()
def lever_fixture():
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def notion_company():
    return CompanyConfig(
        name="notion",
        url="https://jobs.lever.co/notion",
        hint=None,
    )


# --- matches() ---------------------------------------------------------------

def test_matches_jobs_lever_co():
    assert LeverAdapter.matches("https://jobs.lever.co/notion") is True


def test_does_not_match_greenhouse():
    assert LeverAdapter.matches("https://boards.greenhouse.io/stripe") is False


# --- fetch() happy path ------------------------------------------------------

@respx.mock
def test_fetch_happy_path(lever_fixture, notion_company):
    respx.get(_API).mock(return_value=httpx.Response(200, json=lever_fixture))
    raw_postings = LeverAdapter().fetch(notion_company)

    assert len(raw_postings) == 3
    for rp in raw_postings:
        assert rp.source_adapter == "lever"
        assert rp.source_company == "notion"
        assert "id" in rp.raw
        assert rp.raw["__dedup_key"].startswith("lever:notion:")
        assert rp.raw["__identifier"] == "notion"


@respx.mock
def test_fetch_emits_stable_dedup_key(lever_fixture, notion_company):
    respx.get(_API).mock(return_value=httpx.Response(200, json=lever_fixture))
    raw_postings = LeverAdapter().fetch(notion_company)
    keys = [rp.raw["__dedup_key"] for rp in raw_postings]
    expected = [f"lever:notion:{p['id']}" for p in lever_fixture]
    assert keys == expected


# --- fetch() error paths (D-03) ----------------------------------------------

@respx.mock
def test_fetch_raises_schema_drift_on_dict_instead_of_list(notion_company):
    # Lever's response should be a top-level LIST. A dict is drift.
    respx.get(_API).mock(
        return_value=httpx.Response(200, json={"unexpected": "dict"})
    )
    with pytest.raises(SchemaDrift):
        LeverAdapter().fetch(notion_company)


@respx.mock
def test_fetch_raises_schema_drift_on_int_instead_of_list(notion_company):
    respx.get(_API).mock(return_value=httpx.Response(200, json=42))
    with pytest.raises(SchemaDrift):
        LeverAdapter().fetch(notion_company)


@respx.mock
def test_fetch_raises_site_blocked_on_403(notion_company):
    respx.get(_API).mock(return_value=httpx.Response(403, text="Forbidden"))
    with pytest.raises(SiteBlocked):
        LeverAdapter().fetch(notion_company)


@respx.mock
def test_fetch_raises_site_blocked_on_429(notion_company):
    respx.get(_API).mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )
    with pytest.raises(SiteBlocked):
        LeverAdapter().fetch(notion_company)


@respx.mock
def test_fetch_propagates_generic_exception(notion_company):
    respx.get(_API).mock(side_effect=httpx.NetworkError("dns failure"))
    # httpx.NetworkError is a subclass of httpx.HTTPError — adapter must not swallow.
    with pytest.raises(httpx.HTTPError):
        LeverAdapter().fetch(notion_company)
