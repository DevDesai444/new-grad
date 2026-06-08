"""PlaywrightAdapter tests — ADP-09 + ADP-10 (Phase 3 Plan 03-02).

Covers:
  - matches() catch-all (3 cases: http/https URLs, non-http scheme)
  - _parse_hint_kwargs (4 cases: bare, stealth=false, timeout_s, both)
  - _id_from_posting (3 cases: id field present, alternate keys, sha256 fallback)
  - XHR-intercept happy path (Playwright `page.route()` mocks the XHR call)
  - DOM-fallback happy path (XHR mock absent; HTML response served via route)
  - PlaywrightTimeout when both XHR + DOM fail (blank page)
  - Dedup-key shape `pw:<host>:<id>` (XHR-id and sha256 fallback)
  - Stealth on by default (D-04); opt-out via hint
  - Trace=off by default (D-06); retain-on-failure with SCRAPER_DEBUG_TRACE env var
  - Registry catch-all-last invariant (`ADAPTERS[-1].name == 'playwright'`)

Test technique:
  PlaywrightAdapter.fetch accepts a documented test seam kwarg
  `_test_route_handler: Callable[[BrowserContext], None] | None = None`. In
  tests we pass a closure that calls `context.route(...)` to intercept the
  outgoing fetch('/api/jobs') call — no real network is ever hit. Tests use
  Playwright runtime (~2s overhead per test) but ALL stay local.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.adapters.base import PlaywrightTimeout
from src.adapters.playwright_fallback import (
    _DEFAULT_TIMEOUT_S,
    PlaywrightAdapter,
    _id_from_posting,
    _parse_hint_kwargs,
)
from src.models import CompanyConfig

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- matches() — catch-all behavior ------------------------------------------


def test_matches_returns_true_for_http_url():
    assert PlaywrightAdapter.matches("http://example.com") is True


def test_matches_returns_true_for_https_url():
    assert (
        PlaywrightAdapter.matches("https://www.anthropic.com/careers") is True
    )


def test_matches_returns_false_for_non_http_scheme():
    assert PlaywrightAdapter.matches("ftp://example.com") is False
    assert PlaywrightAdapter.matches("javascript:void(0)") is False


# --- _parse_hint_kwargs — Phase 3 D-04/D-05 hint metadata --------------------


def test_parse_hint_kwargs_none():
    assert _parse_hint_kwargs(None) == {}


def test_parse_hint_kwargs_bare_playwright():
    assert _parse_hint_kwargs("playwright") == {}


def test_parse_hint_kwargs_stealth_false():
    assert _parse_hint_kwargs("playwright:stealth=false") == {
        "stealth": "false"
    }


def test_parse_hint_kwargs_timeout_s_30():
    assert _parse_hint_kwargs("playwright:timeout_s=30") == {
        "timeout_s": "30"
    }


def test_parse_hint_kwargs_both():
    assert _parse_hint_kwargs("playwright:stealth=false,timeout_s=30") == {
        "stealth": "false",
        "timeout_s": "30",
    }


# --- _id_from_posting — dedup-key id extraction ------------------------------


def test_id_from_posting_uses_id_field_when_present():
    pid = _id_from_posting({"id": "j-100"}, "https://x.example/jobs/j-100")
    assert pid == "j-100"


def test_id_from_posting_uses_alternate_keys():
    # jobId / positionId / postingId / uuid all accepted
    assert _id_from_posting({"jobId": "abc"}, "u") == "abc"
    assert _id_from_posting({"positionId": "xyz"}, "u") == "xyz"
    assert _id_from_posting({"postingId": "p1"}, "u") == "p1"
    assert _id_from_posting({"uuid": "u-1"}, "u") == "u-1"


def test_id_from_posting_falls_back_to_sha256_when_no_id():
    pid = _id_from_posting({}, "https://x.example/jobs/no-id-here")
    # 16-char hex prefix
    assert re.match(r"^[a-f0-9]{16}$", pid), f"bad sha256 prefix: {pid!r}"


# --- Playwright runtime tests (use page.route() to mock; no real network) ----


def _xhr_fixture() -> dict:
    return json.loads((_FIXTURES_DIR / "anthropic_sample.json").read_text())


def _dom_fixture() -> str:
    return (_FIXTURES_DIR / "anthropic_sample.html").read_text()


def _make_xhr_route(payload: dict):
    """Return a route handler that fulfills /api/jobs with JSON payload."""
    def handler(context):
        context.route(
            "**/api/jobs",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload),
            ),
        )
    return handler


def _make_dom_route(html: str):
    """Return a route handler that fulfills the page itself with HTML, no XHR fires."""
    def handler(context):
        context.route(
            "**/*",
            lambda route: (
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=html,
                )
                if route.request.resource_type == "document"
                else route.fulfill(status=204, body="")
            ),
        )
    return handler


def _make_blank_route():
    """Return a route handler that serves a blank page — no XHR, no selector match."""
    def handler(context):
        context.route(
            "**/*",
            lambda route: (
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="<html><body><p>nothing here</p></body></html>",
                )
                if route.request.resource_type == "document"
                else route.fulfill(status=204, body="")
            ),
        )
    return handler


@pytest.fixture()
def anthropic_company():
    return CompanyConfig(
        name="anthropic",
        url="https://www.anthropic.com/careers",
        hint="playwright:timeout_s=10",
    )


def test_fetch_xhr_intercept_happy_path(anthropic_company):
    """XHR-intercept path: route fulfills /api/jobs with the fixture JSON.

    Adapter MUST extract 4 RawPostings, all with source_adapter='playwright'
    and dedup_keys matching `pw:<host>:<id>` shape.
    """
    payload = _xhr_fixture()

    # We need an HTML page that triggers fetch('/api/jobs') on load — adapter
    # navigates to company.url. We intercept BOTH the navigation (serve a tiny
    # HTML that fires the XHR) AND the XHR itself.
    def handler(context):
        context.route(
            "**/api/jobs",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload),
            ),
        )
        # Serve the navigation document with a script that fires the XHR.
        context.route(
            "https://www.anthropic.com/careers",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body="""<html><body><script>
                  fetch('/api/jobs').then(r => r.json()).then(d => {
                    window.__data = d;
                  });
                </script></body></html>""",
            ),
        )

    raw = PlaywrightAdapter().fetch(
        anthropic_company, _test_route_handler=handler,
    )
    assert len(raw) == 4
    pattern = re.compile(r"^pw:[^:]+:[^:]+$")
    for rp in raw:
        assert rp.source_adapter == "playwright"
        assert rp.source_company == "anthropic"
        key = rp.raw["__dedup_key"]
        assert pattern.match(key), f"bad dedup key shape: {key!r}"
        assert rp.raw["__extraction_path"] == "xhr"


def test_fetch_dedup_key_uses_xhr_id_when_present(anthropic_company):
    """Dedup key contains the XHR's `id` field — not a hash."""
    payload = _xhr_fixture()

    def handler(context):
        context.route(
            "**/api/jobs",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload),
            ),
        )
        context.route(
            "https://www.anthropic.com/careers",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body="<html><body><script>fetch('/api/jobs').then(r=>r.json());</script></body></html>",
            ),
        )

    raw = PlaywrightAdapter().fetch(
        anthropic_company, _test_route_handler=handler,
    )
    keys = [rp.raw["__dedup_key"] for rp in raw]
    # Each posting's id is in the dedup key.
    assert any("j-100" in k for k in keys), keys
    assert any("j-101" in k for k in keys), keys


def test_fetch_dedup_key_falls_back_to_sha256_when_no_id(anthropic_company):
    """XHR returns postings with no id field → dedup_key uses sha256(url) hex prefix."""
    payload = {
        "jobs": [
            {
                "title": "Engineer",
                "location": "Remote",
                "postingUrl": "https://www.anthropic.com/careers/no-id",
                "postingDate": "2026-06-01T00:00:00Z",
                "description": "",
            },
        ],
    }

    def handler(context):
        context.route(
            "**/api/jobs",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload),
            ),
        )
        context.route(
            "https://www.anthropic.com/careers",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body="<html><body><script>fetch('/api/jobs').then(r=>r.json());</script></body></html>",
            ),
        )

    raw = PlaywrightAdapter().fetch(
        anthropic_company, _test_route_handler=handler,
    )
    assert len(raw) == 1
    key = raw[0].raw["__dedup_key"]
    # pw:<host>:<16-hex-chars>
    assert re.match(r"^pw:[^:]+:[a-f0-9]{16}$", key), key


def test_fetch_dom_fallback_when_no_xhr(anthropic_company):
    """When no /api/jobs XHR fires, adapter falls back to DOM-selector parsing.

    Serves the fixture HTML containing 3 [data-testid='job-card'] elements.
    """
    html = _dom_fixture()

    def handler(context):
        # Serve ANY navigation with the HTML; do NOT fire any XHR.
        context.route(
            "**/*",
            lambda route: (
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=html,
                )
                if route.request.resource_type == "document"
                else route.fulfill(status=204, body="")
            ),
        )

    raw = PlaywrightAdapter().fetch(
        anthropic_company, _test_route_handler=handler,
    )
    assert len(raw) == 3
    for rp in raw:
        assert rp.source_adapter == "playwright"
        assert rp.raw["__extraction_path"] == "dom"


def test_fetch_raises_playwright_timeout_when_both_paths_fail():
    """Blank page (no XHR, no matching selector) → PlaywrightTimeout within timeout."""
    company = CompanyConfig(
        name="empty",
        url="https://www.empty.example/careers",
        hint="playwright:timeout_s=3",  # short timeout for fast test
    )
    handler = _make_blank_route()
    with pytest.raises(PlaywrightTimeout):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)


# --- Stealth on by default + opt-out ----------------------------------------


def test_fetch_stealth_enabled_by_default(anthropic_company, monkeypatch):
    """D-04 — stealth ON by default. Monkeypatch the Stealth class to record calls."""
    from src.adapters import playwright_fallback as pf

    called = {"applied": False}

    class _SentinelStealth:
        def apply_stealth_sync(self, ctx):
            called["applied"] = True

    monkeypatch.setattr(pf, "_get_stealth_class", lambda: _SentinelStealth)

    handler = _make_blank_route()
    company = CompanyConfig(
        name="x", url="https://www.x.example/careers",
        hint="playwright:timeout_s=2",
    )
    # Use blank route — adapter will timeout but stealth WILL have been called.
    with pytest.raises(PlaywrightTimeout):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)
    assert called["applied"] is True, "Stealth must be applied by default (D-04)"


def test_fetch_stealth_disabled_by_hint(monkeypatch):
    """D-04 — `#adapter=playwright:stealth=false` opts out; Stealth NOT applied."""
    from src.adapters import playwright_fallback as pf

    called = {"applied": False}

    class _SentinelStealth:
        def apply_stealth_sync(self, ctx):
            called["applied"] = True

    monkeypatch.setattr(pf, "_get_stealth_class", lambda: _SentinelStealth)

    handler = _make_blank_route()
    company = CompanyConfig(
        name="x", url="https://www.x.example/careers",
        hint="playwright:stealth=false,timeout_s=2",
    )
    with pytest.raises(PlaywrightTimeout):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)
    assert called["applied"] is False, (
        "Stealth must NOT be applied when hint=stealth=false (D-04 opt-out)"
    )


# --- Trace policy (D-06) ----------------------------------------------------


def test_fetch_trace_off_by_default(monkeypatch):
    """D-06 — production trace='off'. SCRAPER_DEBUG_TRACE unset → tracing.start NOT called."""
    monkeypatch.delenv("SCRAPER_DEBUG_TRACE", raising=False)

    from src.adapters import playwright_fallback as pf

    tracing_calls = {"started": False}
    real_record = pf._record_trace_started

    def _spy():
        tracing_calls["started"] = True
        real_record()

    monkeypatch.setattr(pf, "_record_trace_started", _spy)

    handler = _make_blank_route()
    company = CompanyConfig(
        name="x", url="https://www.x.example/careers",
        hint="playwright:timeout_s=2",
    )
    with pytest.raises(PlaywrightTimeout):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)
    assert tracing_calls["started"] is False, (
        "tracing.start must NOT be called when SCRAPER_DEBUG_TRACE unset"
    )


def test_fetch_trace_retain_on_failure_when_debug_env_set(monkeypatch):
    """D-06 — SCRAPER_DEBUG_TRACE=1 enables retain-on-failure trace."""
    monkeypatch.setenv("SCRAPER_DEBUG_TRACE", "1")

    from src.adapters import playwright_fallback as pf

    tracing_calls = {"started": False}
    real_record = pf._record_trace_started

    def _spy():
        tracing_calls["started"] = True
        real_record()

    monkeypatch.setattr(pf, "_record_trace_started", _spy)

    handler = _make_blank_route()
    company = CompanyConfig(
        name="x", url="https://www.x.example/careers",
        hint="playwright:timeout_s=2",
    )
    with pytest.raises(PlaywrightTimeout):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)
    assert tracing_calls["started"] is True, (
        "tracing.start MUST be called when SCRAPER_DEBUG_TRACE=1"
    )


# --- Registry catch-all-last invariant (cross-cutting smoke check) ----------


def test_playwright_adapter_is_last_in_adapters_list():
    """D-01c — catch-all MUST be last in src/registry.ADAPTERS so all specific
    adapters' matches() get first crack.
    """
    from src.registry import ADAPTERS
    assert ADAPTERS[-1].name == "playwright"


def test_default_timeout_is_60s():
    """D-05 — default navigation timeout is 60s."""
    assert _DEFAULT_TIMEOUT_S == 60.0
