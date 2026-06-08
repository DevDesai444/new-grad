"""Happy-path tests for the Greenhouse adapter using a recorded fixture.

Per CONTEXT.md D-07: only happy-path here. SchemaDrift / SiteBlocked branches are
defined and raised in code but not exercised by Phase 1 tests — except for two
single-line smoke tests below that confirm the typed exceptions actually fire
(documented W-1 deviation in STATE.md).
"""
import json
from pathlib import Path

import httpx
import pytest
import respx

from src.adapters.base import SchemaDrift, SiteBlocked
from src.adapters.greenhouse import GreenhouseAdapter
from src.models import CompanyConfig

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "greenhouse_stripe.json"


@pytest.fixture()
def stripe_fixture():
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def stripe_company():
    return CompanyConfig(
        name="stripe",
        url="https://boards.greenhouse.io/stripe",
        hint=None,
    )


def test_matches_boards_greenhouse_io():
    assert GreenhouseAdapter.matches("https://boards.greenhouse.io/stripe") is True


def test_matches_job_boards_greenhouse_io():
    assert GreenhouseAdapter.matches("https://job-boards.greenhouse.io/stripe") is True


def test_does_not_match_lever():
    assert GreenhouseAdapter.matches("https://jobs.lever.co/notion") is False


def test_extract_board_token_simple():
    assert (
        GreenhouseAdapter._extract_board_token("https://boards.greenhouse.io/stripe")
        == "stripe"
    )


def test_extract_board_token_with_trailing_slash():
    assert (
        GreenhouseAdapter._extract_board_token("https://boards.greenhouse.io/stripe/")
        == "stripe"
    )


def test_extract_board_token_with_subpath():
    assert (
        GreenhouseAdapter._extract_board_token(
            "https://boards.greenhouse.io/stripe/jobs/123"
        )
        == "stripe"
    )


@respx.mock
def test_fetch_happy_path(stripe_fixture, stripe_company):
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=stripe_fixture))
    adapter = GreenhouseAdapter()
    raw_postings = adapter.fetch(stripe_company)

    assert len(raw_postings) == len(stripe_fixture["jobs"])
    for rp in raw_postings:
        assert rp.source_adapter == "greenhouse"
        assert rp.source_company == "stripe"
        assert "id" in rp.raw
        assert rp.raw["__dedup_key"].startswith("gh:stripe:")
        assert rp.raw["__board_token"] == "stripe"


@respx.mock
def test_fetch_emits_stable_dedup_key(stripe_fixture, stripe_company):
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=stripe_fixture))
    raw_postings = GreenhouseAdapter().fetch(stripe_company)
    keys = [rp.raw["__dedup_key"] for rp in raw_postings]
    expected = [f"gh:stripe:{job['id']}" for job in stripe_fixture["jobs"]]
    assert keys == expected


@respx.mock
def test_fetch_raises_site_blocked_on_403(stripe_company):
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"
    ).mock(return_value=httpx.Response(403, text="Forbidden"))
    with pytest.raises(SiteBlocked):
        GreenhouseAdapter().fetch(stripe_company)


@respx.mock
def test_fetch_raises_schema_drift_on_missing_jobs_key(stripe_company):
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json={"meta": {"total": 0}}))
    with pytest.raises(SchemaDrift):
        GreenhouseAdapter().fetch(stripe_company)
