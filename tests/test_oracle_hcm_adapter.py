"""Oracle HCM Fusion adapter tests — Bug F.

Tests:
  1. matches_oraclecloud_host                       — match-positive
  2. matches_full_path                              — match-positive (with /sites)
  3. does_not_match_workday                         — match-negative
  4. does_not_match_smartrecruiters                 — match-negative
  5. fetch_uses_resolved_url                        — Bug C invariant
  6. fetch_happy_path_single_page
  7. fetch_paginates_until_short_page
  8. fetch_raises_schema_drift_on_missing_items
  9. fetch_raises_schema_drift_on_wrong_items_type
 10. fetch_raises_site_blocked_on_403
 11. fetch_raises_site_blocked_on_429
 12. fetch_raises_site_blocked_on_5xx
 13. fetch_propagates_generic_exception
 14. fetch_raises_schema_drift_on_malformed_url
 15. extract_tenant_and_site_falls_back_to_default
"""
from __future__ import annotations

import httpx
import pytest
import respx

from src.adapters.base import SchemaDrift, SiteBlocked
from src.adapters.oracle_hcm import OracleHCMAdapter
from src.models import CompanyConfig


def _make_response(req_count: int, site: str = "CX_1001") -> dict:
    """Synthesize a minimal Oracle HCM response with N requisitions."""
    return {
        "items": [
            {
                "TotalJobsCount": req_count,
                "Limit": 25,
                "Offset": 0,
                "SiteNumber": site,
                "requisitionList": [
                    {
                        "Id": f"REQ_{i}",
                        "Title": f"Engineer {i}",
                        "PostedDate": "2026-06-08",
                        "PrimaryLocation": "New York, NY, United States",
                        "ShortDescriptionStr": "Short description",
                        "Organization": "Engineering",
                        "JobFamily": "Software",
                    }
                    for i in range(req_count)
                ],
            }
        ]
    }


@pytest.fixture()
def jpm_company():
    return CompanyConfig(
        name="jpmorgan",
        url="https://careers.jpmorgan.com",
        resolved_url=(
            "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/"
            "sites/CX_1001"
        ),
        hint=None,
    )


# --- matches() ---------------------------------------------------------------

def test_matches_oraclecloud_host():
    assert (
        OracleHCMAdapter.matches("https://jpmc.fa.oraclecloud.com") is True
    )


def test_matches_full_path():
    assert (
        OracleHCMAdapter.matches(
            "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/"
            "en/sites/CX_1001"
        )
        is True
    )


def test_does_not_match_workday():
    assert (
        OracleHCMAdapter.matches(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
        )
        is False
    )


def test_does_not_match_smartrecruiters():
    assert (
        OracleHCMAdapter.matches(
            "https://careers.smartrecruiters.com/Notion"
        )
        is False
    )


def test_extract_tenant_and_site_falls_back_to_default():
    """When the resolved URL has no `/sites/<X>` segment, fall back to CX_1."""
    tenant, site = OracleHCMAdapter._extract_tenant_and_site(
        "https://jpmc.fa.oraclecloud.com"
    )
    assert tenant == "jpmc"
    assert site == "CX_1"


def test_extract_tenant_and_site_full_url():
    tenant, site = OracleHCMAdapter._extract_tenant_and_site(
        "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/"
        "sites/CX_1001"
    )
    assert tenant == "jpmc"
    assert site == "CX_1001"


def test_extract_tenant_and_site_raises_on_non_oracle_host():
    with pytest.raises(SchemaDrift):
        OracleHCMAdapter._extract_tenant_and_site(
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
        )


# --- fetch() happy path ------------------------------------------------------

@respx.mock
def test_fetch_uses_resolved_url(jpm_company):
    """Bug C invariant — the adapter MUST derive its API call from
    resolved_url, not the original `careers.jpmorgan.com` URL."""
    api = (
        "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    # Match any querystring that includes our tenant/site.
    respx.get(url__startswith=api).mock(
        return_value=httpx.Response(200, json=_make_response(3))
    )
    raw_postings = OracleHCMAdapter().fetch(jpm_company)
    assert len(raw_postings) == 3
    for rp in raw_postings:
        assert rp.source_adapter == "oraclehcm"
        assert rp.raw["__dedup_key"].startswith("oraclehcm:jpmc:")
        assert rp.raw["__tenant"] == "jpmc"
        assert rp.raw["__site"] == "CX_1001"
        assert rp.raw["__posting_url"].startswith(
            "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/"
        )


@respx.mock
def test_fetch_paginates_until_short_page(jpm_company):
    """First page returns 25 items, second page returns 5 — adapter stops."""
    api = (
        "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    pages = [
        httpx.Response(200, json=_make_response(25)),
        httpx.Response(200, json=_make_response(5)),
    ]
    respx.get(url__startswith=api).mock(side_effect=pages)
    raw_postings = OracleHCMAdapter().fetch(jpm_company)
    assert len(raw_postings) == 30


# --- fetch() error paths -----------------------------------------------------

@respx.mock
def test_fetch_raises_schema_drift_on_missing_items(jpm_company):
    api = (
        "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    respx.get(url__startswith=api).mock(
        return_value=httpx.Response(200, json={"wrong": "shape"})
    )
    with pytest.raises(SchemaDrift):
        OracleHCMAdapter().fetch(jpm_company)


@respx.mock
def test_fetch_raises_schema_drift_on_wrong_items_type(jpm_company):
    api = (
        "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    respx.get(url__startswith=api).mock(
        return_value=httpx.Response(200, json={"items": [42]})  # not a dict
    )
    with pytest.raises(SchemaDrift):
        OracleHCMAdapter().fetch(jpm_company)


@respx.mock
def test_fetch_raises_site_blocked_on_403(jpm_company):
    api = (
        "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    respx.get(url__startswith=api).mock(
        return_value=httpx.Response(403, text="forbidden")
    )
    with pytest.raises(SiteBlocked):
        OracleHCMAdapter().fetch(jpm_company)


@respx.mock
def test_fetch_raises_site_blocked_on_429(jpm_company):
    api = (
        "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    respx.get(url__startswith=api).mock(
        return_value=httpx.Response(429, text="rate limit")
    )
    with pytest.raises(SiteBlocked):
        OracleHCMAdapter().fetch(jpm_company)


@respx.mock
def test_fetch_raises_site_blocked_on_5xx(jpm_company):
    api = (
        "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    respx.get(url__startswith=api).mock(
        return_value=httpx.Response(503, text="upstream down")
    )
    with pytest.raises(SiteBlocked):
        OracleHCMAdapter().fetch(jpm_company)


@respx.mock
def test_fetch_propagates_generic_exception(jpm_company):
    api = (
        "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/"
        "recruitingCEJobRequisitions"
    )
    respx.get(url__startswith=api).mock(side_effect=httpx.NetworkError("dns"))
    with pytest.raises(httpx.HTTPError):
        OracleHCMAdapter().fetch(jpm_company)


@respx.mock
def test_fetch_raises_schema_drift_on_malformed_url():
    """Adapter raises SchemaDrift when URL doesn't match `<tenant>.fa.oraclecloud.com`."""
    company = CompanyConfig(
        name="bad",
        url="https://wrong.example.com",
        resolved_url="https://wrong.example.com",
        hint=None,
    )
    with pytest.raises(SchemaDrift):
        OracleHCMAdapter().fetch(company)


# --- Registry / dispatch -----------------------------------------------------

def test_oraclehcm_registered_in_adapters_list():
    from src.registry import ADAPTERS

    assert OracleHCMAdapter in ADAPTERS


def test_oraclehcm_dispatch_via_registry(jpm_company):
    from src.registry import get_adapter

    adapter = get_adapter(jpm_company)
    assert isinstance(adapter, OracleHCMAdapter)


def test_playwright_stays_last_in_adapters():
    """ADP-15 / CONTEXT.md D-01c — PlaywrightAdapter MUST be last after we
    inserted OracleHCMAdapter."""
    from src.adapters.playwright_fallback import PlaywrightAdapter
    from src.registry import ADAPTERS

    assert ADAPTERS[-1] is PlaywrightAdapter
