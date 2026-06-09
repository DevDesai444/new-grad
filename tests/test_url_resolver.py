"""Unit tests for src/url_resolver.py (Phase 3 Plan 03-01 + Bug-B 2026-06-08).

Covers CONTEXT.md D-01b — the pre-flight URL redirect resolver that unblocks
the ~18-of-31 CNAME→Workday URLs in the user's actual companies.txt.

Contract (D-01b):
- HEAD-first with follow_redirects=True; fall back to streaming GET on 405/501.
- Per-request 5s timeout (default).
- NEVER raises — returns the original URL on ANY error (timeout, network,
  unexpected status). Orchestrator dispatches with original URL on failure.
- Never reads response body for the redirect-chain phase (HEAD or streaming
  GET that closes immediately).

Bug-B (2026-06-08) extensions:
- After the redirect chain settles, if the resolved URL is NOT already a
  known-ATS host, try a bounded body-scan GET for `<tenant>.wd<N>.
  myworkdayjobs.com` references in the HTML.
- And/or try a SmartRecruiters HEAD-probe on a hostname-derived candidate
  identifier (`careers.servicenow.com` → `https://jobs.smartrecruiters.com/
  ServiceNow` → 301 → `https://careers.smartrecruiters.com/ServiceNow`).
- Both extensions are best-effort and no-raise. Tests below mock either
  a 404 or omit the GET mock entirely — the resolver continues regardless.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from src.url_resolver import resolve_url


@respx.mock
def test_resolve_url_no_redirect_passthrough():
    """200 HEAD with no redirect → returns input URL unchanged (identity).

    Bug-B (2026-06-08): the body-scan GET runs after the HEAD chain; mock
    it returning 404 so the no-Workday-found path triggers cleanly. The
    SR-probe does not fire here (host `example.com` is not `careers.X.Y`
    or `jobs.X.Y`).
    """
    url = "https://example.com/foo"
    respx.head(url).mock(return_value=httpx.Response(200))
    # Bug-B body-scan — return 404 so the no-match path runs.
    respx.get(url).mock(return_value=httpx.Response(404))
    assert resolve_url(url) == url


@respx.mock
def test_resolve_url_single_302_follow():
    """One 302 hop (CNAME→Workday shape per D-01b) returns the terminal URL."""
    src = "https://careers.amd.com/"
    dst = "https://amd.wd1.myworkdayjobs.com/External"
    respx.head(src).mock(
        return_value=httpx.Response(302, headers={"Location": dst})
    )
    respx.head(dst).mock(return_value=httpx.Response(200))
    assert resolve_url(src) == dst


@respx.mock
def test_resolve_url_chained_301_then_302():
    """Multi-hop redirect chain (301 → 302 → 200) returns terminal URL."""
    src = "https://careers.example.com/"
    mid = "https://www.example.com/jobs"
    dst = "https://example.wd5.myworkdayjobs.com/Careers"
    respx.head(src).mock(
        return_value=httpx.Response(301, headers={"Location": mid})
    )
    respx.head(mid).mock(
        return_value=httpx.Response(302, headers={"Location": dst})
    )
    respx.head(dst).mock(return_value=httpx.Response(200))
    assert resolve_url(src) == dst


@respx.mock
def test_resolve_url_head_405_falls_back_to_get():
    """HEAD returns 405 (method not allowed) → fall back to streaming GET."""
    src = "https://strict.example.com/"
    dst = "https://target.example.com/final"
    respx.head(src).mock(return_value=httpx.Response(405))
    # Streaming GET follows redirect to dst.
    respx.get(src).mock(
        return_value=httpx.Response(302, headers={"Location": dst})
    )
    respx.get(dst).mock(return_value=httpx.Response(200))
    assert resolve_url(src) == dst


@respx.mock
def test_resolve_url_timeout_returns_original():
    """httpx.TimeoutException → return original URL (graceful degradation per D-01b)."""
    url = "https://slow.example.com/"
    respx.head(url).mock(side_effect=httpx.TimeoutException("timed out"))
    # Streaming GET fallback should also fail/timeout.
    respx.get(url).mock(side_effect=httpx.TimeoutException("timed out"))
    assert resolve_url(url) == url


@respx.mock
def test_resolve_url_connect_error_returns_original():
    """httpx.ConnectError → return original URL (graceful degradation per D-01b)."""
    url = "https://nonexistent.example.invalid/"
    respx.head(url).mock(side_effect=httpx.ConnectError("dns fail"))
    respx.get(url).mock(side_effect=httpx.ConnectError("dns fail"))
    assert resolve_url(url) == url


@respx.mock
def test_resolve_url_5xx_returns_original():
    """5xx HEAD response → returns original (5xx is not a redirect signal)."""
    url = "https://broken.example.com/"
    respx.head(url).mock(return_value=httpx.Response(503))
    assert resolve_url(url) == url


@respx.mock
def test_resolve_url_preserves_query_and_fragment_when_no_redirect():
    """When no redirect: resolver does NOT canonicalize (that's normalizer's job per NORM-06).

    Bug-B body-scan GET is mocked with a 404 so the no-Workday-found path
    runs cleanly. SR-probe does not fire (host `example.com` is not a
    `careers.X.Y` / `jobs.X.Y` shape).
    """
    url = "https://example.com/jobs?team=eng#anchor"
    respx.head(url).mock(return_value=httpx.Response(200))
    # The httpx HEAD strips the fragment; GET will hit the resolved URL
    # (which httpx normalized to `https://example.com/jobs?team=eng`).
    respx.get("https://example.com/jobs").mock(return_value=httpx.Response(404))
    # Note: httpx may strip the fragment from the request URL itself (fragments
    # are client-side only), but the returned URL should still match the input
    # bytes if no redirect occurred. We assert the path + query are preserved.
    result = resolve_url(url)
    assert result.startswith("https://example.com/jobs")
    assert "team=eng" in result


# ============================================================================
# Bug-B (2026-06-08) — body-scan + SmartRecruiters probe extensions
# ============================================================================


from src.url_resolver import (
    _candidate_sr_identifier,
    _resolved_matches_known_ats,
    _scan_body_for_workday,
)


# --- _scan_body_for_workday: pure-function unit tests ----------------------


def test_scan_body_for_workday_finds_embedded_tenant_url():
    """Bug-B: HTML containing a Workday tenant URL returns that URL."""
    body = (
        "<html><body>"
        '<a href="https://arrow.wd1.myworkdayjobs.com/en-US/AC">Apply</a>'
        "</body></html>"
    )
    assert (
        _scan_body_for_workday(body)
        == "https://arrow.wd1.myworkdayjobs.com/en-US/AC"
    )


def test_scan_body_for_workday_stops_at_site_segment_drops_login_suffix():
    """Bug C regression — Workday HTML often embeds the unauthenticated
    redirect URL `<tenant>.wdN.myworkdayjobs.com/<locale>/<site>/login`
    (observed live on careers.arrow.com and careers.micron.com). The
    body-scan must capture only up through `<site>` — the `/login` suffix
    breaks WorkdayAdapter's URL regex and causes SchemaDrift.
    """
    body = (
        "<html><body>"
        '<a href="https://arrow.wd1.myworkdayjobs.com/en-US/AC/login">Login</a>'
        "</body></html>"
    )
    assert (
        _scan_body_for_workday(body)
        == "https://arrow.wd1.myworkdayjobs.com/en-US/AC"
    )


def test_scan_body_for_workday_requires_path_component():
    """Bug-B: a bare host without a path is NOT a valid Workday URL.

    The WorkdayAdapter requires `<tenant>.wd<N>.myworkdayjobs.com/<site>`
    (path segment present). Body-scan must reject path-less matches so the
    adapter dispatch downstream doesn't raise SchemaDrift.
    """
    body = "<a>https://nvidia.wd5.myworkdayjobs.com</a>"
    assert _scan_body_for_workday(body) is None


def test_scan_body_for_workday_returns_none_for_empty_body():
    """Bug-B: defensive — empty body returns None."""
    assert _scan_body_for_workday("") is None


def test_scan_body_for_workday_first_match_wins():
    """Bug-B: when multiple tenant URLs are in the body, the FIRST one is returned."""
    body = (
        "first: https://aaa.wd1.myworkdayjobs.com/SiteA "
        "second: https://bbb.wd2.myworkdayjobs.com/SiteB"
    )
    assert (
        _scan_body_for_workday(body)
        == "https://aaa.wd1.myworkdayjobs.com/SiteA"
    )


# --- _candidate_sr_identifier: hostname-derivation unit tests --------------


def test_candidate_sr_identifier_extracts_servicenow():
    """Bug-B: `careers.servicenow.com` derives the camel-cased `ServiceNow`."""
    assert (
        _candidate_sr_identifier("https://careers.servicenow.com")
        == "ServiceNow"
    )


def test_candidate_sr_identifier_extracts_gartner():
    """Bug-B: `jobs.gartner.com` derives `Gartner` via title-casing."""
    assert _candidate_sr_identifier("https://jobs.gartner.com") == "Gartner"


def test_candidate_sr_identifier_rejects_non_career_hosts():
    """Bug-B: hostnames that aren't `careers.X.Y` or `jobs.X.Y` return None.

    Prevents the SR-probe from firing on unrelated hosts (e.g., the
    `example.com` URLs used in the existing test suite).
    """
    assert _candidate_sr_identifier("https://example.com") is None
    assert _candidate_sr_identifier("https://www.foo.com/jobs") is None


def test_candidate_sr_identifier_rejects_unknown_tlds():
    """Bug-B: only `.com`, `.io`, `.net` TLDs are recognized."""
    assert _candidate_sr_identifier("https://careers.acme.co.uk") is None
    assert _candidate_sr_identifier("https://jobs.foo.dev") is None


def test_candidate_sr_identifier_handles_hyphenated_name():
    """Bug-B: hyphens in the base are stripped and segments title-cased."""
    assert (
        _candidate_sr_identifier("https://careers.big-co.com")
        == "BigCo"
    )


# --- _resolved_matches_known_ats: ATS-host-fingerprint unit tests ----------


def test_resolved_matches_known_ats_workday():
    """Bug-B: any `*.myworkdayjobs.com` URL matches."""
    assert _resolved_matches_known_ats(
        "https://amd.wd1.myworkdayjobs.com/External"
    ) is True


def test_resolved_matches_known_ats_smartrecruiters():
    """Bug-B: `careers.smartrecruiters.com/...` matches."""
    assert _resolved_matches_known_ats(
        "https://careers.smartrecruiters.com/ServiceNow"
    ) is True


def test_resolved_matches_known_ats_non_ats_returns_false():
    """Bug-B: arbitrary URLs do not match."""
    assert _resolved_matches_known_ats("https://example.com/jobs") is False
    assert _resolved_matches_known_ats("https://careers.adobe.com") is False


def test_resolved_matches_known_ats_all_supported_hosts():
    """Bug-B: every adapter's host fingerprint matches."""
    for url in (
        "https://amd.wd1.myworkdayjobs.com/External",
        "https://boards.greenhouse.io/notion",
        "https://jobs.lever.co/anthropic",
        "https://jobs.ashbyhq.com/notion",
        "https://careers.smartrecruiters.com/ServiceNow",
        "https://jobs.apple.com/en-us/details/123/swe",
    ):
        assert _resolved_matches_known_ats(url) is True, url


# --- resolve_url: body-scan extension end-to-end --------------------------


@respx.mock
def test_resolve_url_body_scan_finds_workday_in_arrow_landing():
    """Bug-B end-to-end: careers.arrow.com lands 200 with Workday URL in body.

    Pre-fix: resolver returned `https://careers.arrow.com/us/en` (200 from
    the HEAD chain after the 303 redirect), WorkdayAdapter.matches() failed
    because host is `careers.arrow.com` not `*.myworkdayjobs.com`, dispatch
    fell through to PlaywrightAdapter which then timed out per Bug-A.

    Post-fix: body-scan finds the embedded `arrow.wd1.myworkdayjobs.com/en-US/AC`
    URL and returns IT, so WorkdayAdapter.matches() fires downstream.
    """
    src_url = "https://careers.arrow.com/"
    landing_url = "https://careers.arrow.com/us/en"
    workday_url = "https://arrow.wd1.myworkdayjobs.com/en-US/AC"

    # HEAD chain: 303 → landing → 200.
    respx.head(src_url).mock(
        return_value=httpx.Response(303, headers={"Location": landing_url})
    )
    respx.head(landing_url).mock(return_value=httpx.Response(200))

    # Body-scan GET on the landing URL — returns HTML containing the Workday URL.
    respx.get(landing_url).mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            text=(
                f"<html><body>"
                f"<p>Search jobs at Arrow</p>"
                f'<a href="{workday_url}">View openings</a>'
                f"</body></html>"
            ),
        )
    )

    result = resolve_url(src_url)
    assert result == workday_url, (
        f"Bug-B body-scan should have returned the embedded Workday URL, "
        f"got: {result!r}"
    )


@respx.mock
def test_resolve_url_body_scan_skipped_when_chain_lands_on_workday():
    """Bug-B: if the HEAD chain already produced a known-ATS URL, body-scan
    must NOT run (saves a wasted GET per company).

    We assert this by NOT mocking any GET — if body-scan fires, respx will
    raise AllMockedAssertionError.
    """
    src_url = "https://careers.amd.com/"
    workday_url = "https://amd.wd1.myworkdayjobs.com/External"
    respx.head(src_url).mock(
        return_value=httpx.Response(302, headers={"Location": workday_url})
    )
    respx.head(workday_url).mock(return_value=httpx.Response(200))
    # NO respx.get(...) — body-scan must not fire.

    assert resolve_url(src_url) == workday_url


@respx.mock
def test_resolve_url_body_scan_handles_no_workday_match_gracefully():
    """Bug-B: a 200 HTML body with no Workday URL leaves the resolved URL unchanged."""
    src_url = "https://careers.adobe.com/"
    landing_url = "https://careers.adobe.com/us/en"
    respx.head(src_url).mock(
        return_value=httpx.Response(303, headers={"Location": landing_url})
    )
    respx.head(landing_url).mock(return_value=httpx.Response(200))
    respx.get(landing_url).mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text="<html><body>No ATS link here, just Phenom assets.</body></html>",
        )
    )
    # SR-probe candidate is `Adobe` — must not match any SR org.
    respx.head("https://jobs.smartrecruiters.com/Adobe").mock(
        return_value=httpx.Response(404)
    )

    # No Workday URL found in body; SR-probe finds nothing → returns the
    # HEAD-chain-resolved URL (the landing page).
    result = resolve_url(src_url)
    assert result == landing_url


@respx.mock
def test_resolve_url_body_scan_handles_non_html_content_type():
    """Bug-B: non-HTML responses (JSON, image) are NOT body-scanned."""
    src_url = "https://api.foo.com/jobs"
    respx.head(src_url).mock(return_value=httpx.Response(200))
    respx.get(src_url).mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            text='{"jobs": []}',
        )
    )
    # SR-probe for `api.foo.com` — pattern doesn't match (`api` not `careers`/`jobs`).
    assert resolve_url(src_url) == src_url


# --- resolve_url: SmartRecruiters-probe extension end-to-end ---------------


@respx.mock
def test_resolve_url_sr_probe_rescues_servicenow_403():
    """Bug-B end-to-end: careers.servicenow.com returns 403 (Cloudflare).

    Pre-fix: HEAD chain returned 403 → resolver returned original URL →
    SmartRecruitersAdapter.matches() failed (host is `careers.servicenow.com`
    not `careers.smartrecruiters.com`) → dispatch fell through to PlaywrightAdapter.

    Post-fix: SR-probe HEADs `https://jobs.smartrecruiters.com/ServiceNow`,
    which SR 301-redirects to `https://careers.smartrecruiters.com/ServiceNow`,
    then GET-verifies via the postings API that totalFound > 0 (ServiceNow
    has 472 active postings on SR at recon time).
    Resolver returns the canonical SR URL → SmartRecruitersAdapter fires.
    """
    src_url = "https://careers.servicenow.com/"
    sr_url = "https://careers.smartrecruiters.com/ServiceNow"
    api_url = "https://api.smartrecruiters.com/v1/companies/ServiceNow/postings"

    respx.head(src_url).mock(return_value=httpx.Response(403))
    # SR probe HEAD: jobs.X → careers.X
    respx.head("https://jobs.smartrecruiters.com/ServiceNow").mock(
        return_value=httpx.Response(301, headers={"Location": sr_url})
    )
    respx.head(sr_url).mock(return_value=httpx.Response(200))
    # SR probe API verification: totalFound > 0 confirms the org genuinely uses SR.
    respx.get(api_url).mock(
        return_value=httpx.Response(
            200,
            json={"offset": 0, "limit": 1, "totalFound": 472, "content": []},
        )
    )

    result = resolve_url(src_url)
    assert result == sr_url


@respx.mock
def test_resolve_url_sr_probe_rescues_gartner_403():
    """Bug-B end-to-end: jobs.gartner.com 403 → SR-probe returns Gartner SR URL.

    Note: Gartner's SR org happens to have an active posting at recon time
    (the live API may return 0 if all roles close, in which case the probe
    correctly returns None and the resolver returns the original URL — but
    for this test we mock a positive totalFound to assert the happy path).
    """
    src_url = "https://jobs.gartner.com/"
    sr_url = "https://careers.smartrecruiters.com/Gartner"
    api_url = "https://api.smartrecruiters.com/v1/companies/Gartner/postings"

    respx.head(src_url).mock(return_value=httpx.Response(403))
    respx.head("https://jobs.smartrecruiters.com/Gartner").mock(
        return_value=httpx.Response(301, headers={"Location": sr_url})
    )
    respx.head(sr_url).mock(return_value=httpx.Response(200))
    respx.get(api_url).mock(
        return_value=httpx.Response(
            200, json={"offset": 0, "limit": 1, "totalFound": 5, "content": []},
        )
    )

    assert resolve_url(src_url) == sr_url


@respx.mock
def test_resolve_url_sr_probe_skipped_when_chain_finds_ats():
    """Bug-B: SR-probe must NOT fire when the HEAD chain already produced
    a known-ATS URL.

    We omit the SR-probe HEAD mock — if it fires, respx raises.
    """
    src_url = "https://careers.amd.com/"
    workday_url = "https://amd.wd1.myworkdayjobs.com/External"

    respx.head(src_url).mock(
        return_value=httpx.Response(302, headers={"Location": workday_url})
    )
    respx.head(workday_url).mock(return_value=httpx.Response(200))
    # NO respx.head("https://jobs.smartrecruiters.com/Amd") — must not fire.

    assert resolve_url(src_url) == workday_url


@respx.mock
def test_resolve_url_sr_probe_returns_404_does_not_raise():
    """Bug-B: when SR-probe gets a 404 (unknown org), resolver falls back to original.

    Defensive: the SR-probe is best-effort; a 404 means SR doesn't know this
    company; resolver returns the original URL unchanged.
    """
    src_url = "https://careers.unknown-co.com/"
    landing = "https://careers.unknown-co.com/landing"
    respx.head(src_url).mock(
        return_value=httpx.Response(302, headers={"Location": landing})
    )
    respx.head(landing).mock(return_value=httpx.Response(200))
    # Body-scan returns nothing.
    respx.get(landing).mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text="<html>no ats here</html>",
        )
    )
    # SR-probe 404s.
    respx.head("https://jobs.smartrecruiters.com/UnknownCo").mock(
        return_value=httpx.Response(404)
    )

    assert resolve_url(src_url) == landing


@respx.mock
def test_resolve_url_sr_probe_timeout_returns_chain_resolved():
    """Bug-B: SR-probe timing out does not raise; resolver returns chain-resolved URL."""
    src_url = "https://careers.timeoutco.com/"
    landing = "https://careers.timeoutco.com/landing"
    respx.head(src_url).mock(
        return_value=httpx.Response(302, headers={"Location": landing})
    )
    respx.head(landing).mock(return_value=httpx.Response(200))
    respx.get(landing).mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text="<html>nothing</html>",
        )
    )
    respx.head("https://jobs.smartrecruiters.com/Timeoutco").mock(
        side_effect=httpx.TimeoutException("probe timeout")
    )

    assert resolve_url(src_url) == landing


# --- end-to-end registry dispatch (per debug-session DoD verification) -----


def test_registry_dispatch_for_arrow_after_resolver_upgrade():
    """Bug-B DoD: with the resolver fix, careers.arrow.com → WorkdayAdapter.

    This is the DoD verification command from the debug session, exercised
    against mocked responses so the test doesn't depend on a live network.
    """
    import respx as _respx
    from src.models import CompanyConfig
    from src.registry import get_adapter
    from src.adapters.workday import WorkdayAdapter

    src_url = "https://careers.arrow.com/"
    landing = "https://careers.arrow.com/us/en"
    workday = "https://arrow.wd1.myworkdayjobs.com/en-US/AC"

    with _respx.mock:
        _respx.head(src_url).mock(
            return_value=httpx.Response(303, headers={"Location": landing})
        )
        _respx.head(landing).mock(return_value=httpx.Response(200))
        _respx.get(landing).mock(
            return_value=httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text=(
                    f'<html><body><a href="{workday}">Apply</a></body></html>'
                ),
            )
        )
        c = CompanyConfig(name="arrow", url=src_url)
        c.resolved_url = resolve_url(c.url)

    # After Bug-B fix: resolved_url points to the Workday tenant URL.
    assert c.resolved_url == workday
    adapter = get_adapter(c)
    assert isinstance(adapter, WorkdayAdapter), (
        f"Bug-B DoD: arrow should dispatch to WorkdayAdapter after resolve, "
        f"got {type(adapter).__name__}"
    )


def test_registry_dispatch_for_servicenow_after_resolver_upgrade():
    """Bug-B DoD: with the resolver fix, careers.servicenow.com → SmartRecruitersAdapter."""
    import respx as _respx
    from src.models import CompanyConfig
    from src.registry import get_adapter
    from src.adapters.smartrecruiters import SmartRecruitersAdapter

    src_url = "https://careers.servicenow.com/"
    sr_url = "https://careers.smartrecruiters.com/ServiceNow"
    api_url = "https://api.smartrecruiters.com/v1/companies/ServiceNow/postings"

    with _respx.mock:
        _respx.head(src_url).mock(return_value=httpx.Response(403))
        _respx.head("https://jobs.smartrecruiters.com/ServiceNow").mock(
            return_value=httpx.Response(301, headers={"Location": sr_url})
        )
        _respx.head(sr_url).mock(return_value=httpx.Response(200))
        _respx.get(api_url).mock(
            return_value=httpx.Response(
                200, json={"offset": 0, "limit": 1, "totalFound": 472, "content": []},
            )
        )
        c = CompanyConfig(name="servicenow", url=src_url)
        c.resolved_url = resolve_url(c.url)

    assert c.resolved_url == sr_url
    adapter = get_adapter(c)
    assert isinstance(adapter, SmartRecruitersAdapter), (
        f"Bug-B DoD: servicenow should dispatch to SmartRecruitersAdapter, "
        f"got {type(adapter).__name__}"
    )


@respx.mock
def test_resolve_url_sr_probe_rejects_zero_postings_orgs():
    """Bug-B: SR returns a "Careers at X" stub for many strings — Adobe,
    Bloomberg, JPMorgan, Lenovo all 200 on the HEAD probe but have 0
    active postings (they actually use Phenom, Avature, Oracle HCM).
    The SR-probe must reject orgs with totalFound=0 so we don't
    misroute them.
    """
    src_url = "https://careers.adobe.com/"
    sr_url = "https://careers.smartrecruiters.com/Adobe"
    api_url = "https://api.smartrecruiters.com/v1/companies/Adobe/postings"

    # HEAD chain: 303 → landing → 200, body has no Workday URL.
    landing = "https://careers.adobe.com/us/en"
    respx.head(src_url).mock(
        return_value=httpx.Response(303, headers={"Location": landing})
    )
    respx.head(landing).mock(return_value=httpx.Response(200))
    respx.get(landing).mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "text/html"},
            text="<html><body>phenom assets here, no Workday</body></html>",
        )
    )
    # SR probe: HEAD returns 200 BUT API says 0 postings → SR-probe returns None.
    respx.head("https://jobs.smartrecruiters.com/Adobe").mock(
        return_value=httpx.Response(301, headers={"Location": sr_url})
    )
    respx.head(sr_url).mock(return_value=httpx.Response(200))
    respx.get(api_url).mock(
        return_value=httpx.Response(
            200, json={"offset": 0, "limit": 1, "totalFound": 0, "content": []},
        )
    )

    # Resolver returns the HEAD-chain-resolved landing URL (not the SR URL)
    # because the SR-probe correctly rejected the empty-org false positive.
    assert resolve_url(src_url) == landing


@respx.mock
def test_resolve_url_sr_probe_rejects_malformed_api_response():
    """Bug-B: defensive — SR API returning non-JSON or missing totalFound
    keeps the SR-probe return-None (best-effort, no-raise contract).
    """
    src_url = "https://careers.malformed.com/"
    sr_url = "https://careers.smartrecruiters.com/Malformed"
    api_url = "https://api.smartrecruiters.com/v1/companies/Malformed/postings"

    respx.head(src_url).mock(return_value=httpx.Response(403))
    respx.head("https://jobs.smartrecruiters.com/Malformed").mock(
        return_value=httpx.Response(301, headers={"Location": sr_url})
    )
    respx.head(sr_url).mock(return_value=httpx.Response(200))
    # API returns 200 with non-dict payload.
    respx.get(api_url).mock(return_value=httpx.Response(200, json=["not", "a", "dict"]))

    # Resolver returns the original URL — SR-probe correctly returned None.
    assert resolve_url(src_url) == src_url


@respx.mock
def test_resolve_url_sr_probe_handles_api_5xx():
    """Bug-B: defensive — SR API returning 5xx leaves the SR-probe None."""
    src_url = "https://careers.api5xx.com/"
    sr_url = "https://careers.smartrecruiters.com/Api5xx"
    api_url = "https://api.smartrecruiters.com/v1/companies/Api5xx/postings"

    respx.head(src_url).mock(return_value=httpx.Response(403))
    respx.head("https://jobs.smartrecruiters.com/Api5xx").mock(
        return_value=httpx.Response(301, headers={"Location": sr_url})
    )
    respx.head(sr_url).mock(return_value=httpx.Response(200))
    respx.get(api_url).mock(return_value=httpx.Response(503))

    assert resolve_url(src_url) == src_url


# ============================================================================
# Bug D (2026-06-08) — known-ATS short-circuit
# ============================================================================
# When the input URL ALREADY matches a known non-catchall ATS hostname,
# resolve_url() must return it unmodified — no HEAD chain, no body scan, no
# SR probe. This prevents the resolver from "downgrading" jobs.apple.com to
# www.apple.com/careers/us/ (which AppleAdapter.matches() doesn't recognize,
# causing dispatch to fall through to PlaywrightAdapter and time out).


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.apple.com",
        "https://jobs.apple.com/en-us/details/12345",
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        "https://boards.greenhouse.io/stripe",
        "https://jobs.lever.co/notion",
        "https://jobs.ashbyhq.com/notion",
        "https://careers.smartrecruiters.com/ServiceNow",
    ],
)
def test_resolve_url_short_circuits_known_ats_hosts(url):
    """Bug D — input URL on a known ATS host returns unmodified.

    Critical: no HEAD/GET is issued (respx.mock would raise if it were —
    we don't mock any endpoint here).
    """
    with respx.mock(assert_all_called=False):
        assert resolve_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.apple.com",
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        "https://boards.greenhouse.io/stripe",
        "https://jobs.lever.co/notion",
        "https://jobs.ashbyhq.com/notion",
        "https://careers.smartrecruiters.com/ServiceNow",
    ],
)
def test_known_ats_routes_to_correct_adapter_after_resolver(url):
    """Bug D end-to-end — after resolver runs, get_adapter returns the
    expected non-catchall adapter (NOT PlaywrightAdapter)."""
    from src.models import CompanyConfig
    from src.registry import get_adapter
    from src.adapters.playwright_fallback import PlaywrightAdapter

    with respx.mock(assert_all_called=False):
        c = CompanyConfig(name="test", url=url)
        c.resolved_url = resolve_url(c.url)
        adapter = get_adapter(c)
        assert not isinstance(adapter, PlaywrightAdapter), (
            f"{url} dispatched to PlaywrightAdapter — known-ATS dispatch "
            f"regression. Adapter was {type(adapter).__name__}"
        )
