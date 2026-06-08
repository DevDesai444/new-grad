"""Apple adapter tests — ADP-08 + CONTEXT.md D-01a / D-03 / D-04.

Tests:
  1-3:   matches() — happy + subpath + does-not-match-greenhouse
  4-5:   happy path (single page) + dedup-key shape (no per-company prefix)
  6-7:   SchemaDrift on missing keys + wrong-type array
  8-10:  SiteBlocked on 403 / 429 / 5xx
  11:    Generic exception propagation (httpx.NetworkError -> httpx.HTTPError)
  12:    Skip malformed entries (no id/positionId)
  13:    D-04 single-page short-circuit (total ≤ pageSize -> 1 respx call)
  14:    D-04 early-termination by seen_keys overlap
  15:    D-04 cold-start 25-page cap
  16:    D-04 sort-monotonicity sanity warning (caplog assertion)
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx
import pytest
import respx

from src.adapters.apple import AppleAdapter
from src.adapters.base import SchemaDrift, SiteBlocked
from src.models import CompanyConfig

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "apple_sample.json"
_API = "https://jobs.apple.com/api/role/search"


@pytest.fixture()
def apple_fixture():
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def apple_company():
    return CompanyConfig(
        name="Apple",
        url="https://jobs.apple.com/en-us/search",
        hint=None,
    )


# --- matches() ----------------------------------------------------------------


def test_matches_jobs_apple_com():
    assert AppleAdapter.matches("https://jobs.apple.com/en-us/search") is True


def test_matches_jobs_apple_com_subpath():
    # Any subpath under jobs.apple.com matches — Apple is single-org, adapter
    # ignores the URL path and POSTs the broad search endpoint.
    assert (
        AppleAdapter.matches(
            "https://jobs.apple.com/en-us/details/200593841"
        )
        is True
    )


def test_does_not_match_greenhouse():
    assert (
        AppleAdapter.matches("https://boards.greenhouse.io/stripe") is False
    )


# --- D-03 happy + error paths -------------------------------------------------


@respx.mock
def test_fetch_happy_path_single_page(apple_fixture, apple_company):
    respx.post(_API).mock(return_value=httpx.Response(200, json=apple_fixture))
    raw = AppleAdapter().fetch(apple_company)
    # 5 entries minus 1 malformed (no id/positionId) = 4 returned.
    assert len(raw) == 4
    for rp in raw:
        assert rp.source_adapter == "apple"
        assert rp.source_company == "Apple"
        assert rp.raw["__dedup_key"].startswith("apple:")


@respx.mock
def test_apple_dedup_key_has_no_company_prefix(apple_fixture, apple_company):
    """D-01a invariant: dedup key is `apple:<id>` — NO per-company prefix.

    Other adapters' keys look like `gh:stripe:123` or `wd:nvidia:R-101`. Apple
    skips the company segment because it's a single org. Regex: exactly one
    colon (between `apple` and the id).
    """
    respx.post(_API).mock(return_value=httpx.Response(200, json=apple_fixture))
    raw = AppleAdapter().fetch(apple_company)
    pattern = re.compile(r"^apple:[^:]+$")
    for rp in raw:
        assert pattern.match(rp.raw["__dedup_key"]), (
            f"Bad key shape (extra prefix?): {rp.raw['__dedup_key']!r}"
        )


@respx.mock
def test_fetch_raises_schema_drift_on_missing_keys(apple_company):
    # Neither `results` nor `searchResults` present.
    respx.post(_API).mock(
        return_value=httpx.Response(
            200, json={"page": 0, "pageSize": 20},
        )
    )
    with pytest.raises(SchemaDrift):
        AppleAdapter().fetch(apple_company)


@respx.mock
def test_fetch_raises_schema_drift_on_wrong_type(apple_company):
    # `searchResults` present but not a list.
    respx.post(_API).mock(
        return_value=httpx.Response(
            200, json={"searchResults": "not a list", "total": 0},
        )
    )
    with pytest.raises(SchemaDrift):
        AppleAdapter().fetch(apple_company)


@respx.mock
def test_fetch_raises_site_blocked_on_403(apple_company):
    respx.post(_API).mock(return_value=httpx.Response(403, text="Forbidden"))
    with pytest.raises(SiteBlocked):
        AppleAdapter().fetch(apple_company)


@respx.mock
def test_fetch_raises_site_blocked_on_429(apple_company):
    respx.post(_API).mock(
        return_value=httpx.Response(429, text="Too Many Requests"),
    )
    with pytest.raises(SiteBlocked):
        AppleAdapter().fetch(apple_company)


@respx.mock
def test_fetch_raises_site_blocked_on_5xx(apple_company):
    respx.post(_API).mock(
        return_value=httpx.Response(503, text="Service Unavailable"),
    )
    with pytest.raises(SiteBlocked):
        AppleAdapter().fetch(apple_company)


@respx.mock
def test_fetch_propagates_generic_exception(apple_company):
    respx.post(_API).mock(side_effect=httpx.NetworkError("dns failure"))
    with pytest.raises(httpx.HTTPError):
        AppleAdapter().fetch(apple_company)


@respx.mock
def test_fetch_skips_malformed_entries(apple_fixture, apple_company):
    """Fixture's 5th entry has no id/positionId — adapter skips, doesn't abort."""
    respx.post(_API).mock(return_value=httpx.Response(200, json=apple_fixture))
    raw = AppleAdapter().fetch(apple_company)
    pids = [rp.raw.get("__position_id") for rp in raw]
    assert all(pid for pid in pids), pids
    assert len(raw) == 4


# --- D-04 pagination ----------------------------------------------------------


@respx.mock
def test_single_page_short_circuit(apple_fixture, apple_company):
    """Fixture has 5 entries (<20 pageSize) → adapter must NOT call page 1."""
    route = respx.post(_API).mock(
        return_value=httpx.Response(200, json=apple_fixture),
    )
    AppleAdapter().fetch(apple_company)
    assert route.call_count == 1


@respx.mock
def test_early_termination_on_seen_keys(apple_company, monkeypatch):
    """When the LAST posting on page 0 is in seen_keys, stop after page 0.

    Mock returns a FULL pageSize (20) so the short-page branch doesn't fire.
    Inter-page sleep is monkeypatched to noop to keep tests fast.
    """
    monkeypatch.setattr("src.adapters.apple.time.sleep", lambda s: None)

    full_page_postings = []
    for i in range(20):
        full_page_postings.append({
            "id": f"30000{i:04d}",
            "positionId": f"30000{i:04d}",
            "postingTitle": f"Engineer {i}",
            "transformedPostingTitle": f"engineer-{i}",
            # Monotonically decreasing dates so sort-monotonicity passes.
            "postingDate": f"2026-06-{(20 - i):02d}T00:00:00Z",
            "locations": [{"name": "Cupertino, CA"}],
            "jobSummary": "",
        })
    full_page = {
        "searchResults": full_page_postings,
        "total": 100,
        "page": 0,
        "pageSize": 20,
    }
    route = respx.post(_API).mock(
        return_value=httpx.Response(200, json=full_page),
    )
    # Last posting (i=19) has positionId "300000019" → key "apple:300000019".
    seen_keys = {"apple:300000019"}
    AppleAdapter().fetch(apple_company, seen_keys=seen_keys)
    assert route.call_count == 1  # stopped after page 0


@respx.mock
def test_cold_start_25_page_cap(apple_company, monkeypatch):
    """No seen_keys overlap + every page returns full pageSize → cap at 25."""
    monkeypatch.setattr("src.adapters.apple.time.sleep", lambda s: None)

    def make_page(page_idx: int):
        # Each subsequent page has OLDER dates (sort=desc) so monotonicity
        # holds. Tail of page N is older than head of page N+1's first... wait,
        # for monotonicity to PASS we need page N+1's first ≤ page N's last.
        # Use a strictly-decreasing date sequence across pages.
        postings = []
        for i in range(20):
            pid = f"{page_idx:03d}{i:04d}"
            # Compute a date that decreases with page+i (lexically too).
            # Day = 30 - page_idx (clamped); time-of-day decreases with i.
            day = max(1, 30 - page_idx)
            hour = max(0, 23 - i)
            postings.append({
                "id": pid,
                "positionId": pid,
                "postingTitle": f"Engineer {pid}",
                "transformedPostingTitle": f"engineer-{pid}",
                "postingDate": f"2026-06-{day:02d}T{hour:02d}:00:00Z",
                "locations": [{"name": "Cupertino, CA"}],
                "jobSummary": "",
            })
        return {
            "searchResults": postings,
            "total": 1000,
            "page": page_idx,
            "pageSize": 20,
        }

    def handler(request):
        body = json.loads(request.content)
        return httpx.Response(200, json=make_page(body["page"]))

    route = respx.post(_API).mock(side_effect=handler)
    AppleAdapter().fetch(apple_company, seen_keys=set())
    # Exactly 25 pages (0-indexed pages 0..24), then stop.
    assert route.call_count == 25


@respx.mock
def test_sort_monotonicity_warning(apple_company, monkeypatch, caplog):
    """Page 1's first newer than page 0's last → log WARNING containing 'sort'."""
    monkeypatch.setattr("src.adapters.apple.time.sleep", lambda s: None)
    caplog.set_level(logging.WARNING, logger="scan")

    # Page 0: dates decrease from 2026-06-20 to 2026-06-01.
    page_0 = {
        "searchResults": [
            {
                "id": f"a{i}",
                "positionId": f"a{i}",
                "postingTitle": "E",
                "transformedPostingTitle": "e",
                "postingDate": f"2026-06-{max(1, 20 - i):02d}T00:00:00Z",
                "locations": [{"name": "X"}],
                "jobSummary": "",
            }
            for i in range(20)
        ],
        "total": 100,
        "page": 0,
        "pageSize": 20,
    }
    # Page 1: FIRST posting is 2026-06-30 — NEWER than page 0's last (2026-06-01).
    page_1 = {
        "searchResults": [
            {
                "id": "b0",
                "positionId": "b0",
                "postingTitle": "E",
                "transformedPostingTitle": "e",
                "postingDate": "2026-06-30T00:00:00Z",  # NEWER → trips check
                "locations": [{"name": "X"}],
                "jobSummary": "",
            },
        ] + [
            {
                "id": f"b{i}",
                "positionId": f"b{i}",
                "postingTitle": "E",
                "transformedPostingTitle": "e",
                "postingDate": "2026-05-01T00:00:00Z",
                "locations": [{"name": "X"}],
                "jobSummary": "",
            }
            for i in range(1, 20)
        ],
        "total": 100,
        "page": 1,
        "pageSize": 20,
    }

    def handler(request):
        body = json.loads(request.content)
        return httpx.Response(200, json=page_0 if body["page"] == 0 else page_1)

    respx.post(_API).mock(side_effect=handler)
    AppleAdapter().fetch(apple_company, seen_keys=set())
    # At least one WARNING record mentioning "sort".
    matches = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "sort" in r.message.lower()
    ]
    assert matches, (
        f"Expected WARNING with 'sort' in message; got: "
        f"{[(r.levelname, r.message) for r in caplog.records]}"
    )
