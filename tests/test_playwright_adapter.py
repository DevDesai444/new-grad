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

from src.adapters.base import (
    InvalidCredential,
    MissingCredential,
    PlaywrightTimeout,
)
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


# --- Bug A (2026-06-08) — timeout-stacking regression ------------------------


def test_fetch_total_wall_clock_bounded_by_timeout_s():
    """Bug-A regression: wall-clock for the worst path (XHR never fires, no DOM
    selector matches) must be bounded by `timeout_s` plus small overhead, NOT
    a multiple of it.

    Pre-fix behavior:
      The adapter allocated the full `timeout_ms` to each of THREE separate
      Playwright operations (initial nav, XHR-intercept block, DOM-fallback
      nav). On the worst path this stacked to 2-3x `timeout_s` (observed
      ~120s on a 60s declared budget in production run 27160706571).

    Post-fix behavior:
      The adapter computes a single monotonic deadline at entry and every
      Playwright op draws from `remaining_ms()`. Total wall-clock is
      bounded by `timeout_s` + Playwright lifecycle overhead (browser
      launch ~1s, context creation, etc.).

    We use a 3s timeout and assert wall-clock under 10s. Pre-fix this test
    would observe ~9-12s wall-clock (3x stacking + Playwright startup);
    post-fix observes ~4-5s.

    Headless Chromium startup overhead is the dominant non-Playwright
    contribution. The pre-fix multiple of timeout would push wall-clock
    well above the 10s ceiling on a 3s budget.
    """
    import time
    company = CompanyConfig(
        name="bounded",
        url="https://www.bounded.example/careers",
        hint="playwright:timeout_s=3",
    )
    handler = _make_blank_route()
    t0 = time.monotonic()
    with pytest.raises(PlaywrightTimeout):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)
    elapsed = time.monotonic() - t0
    # 3s declared timeout + ~5s overhead (Chromium launch + context + page
    # creation + final exception construction). Pre-fix the stacking would
    # push this well above 10s on any reasonable machine.
    assert elapsed < 10.0, (
        f"Bug-A regression: wall-clock {elapsed:.2f}s exceeded ceiling "
        f"of 10s on a 3s declared timeout — timeout stacking is back."
    )


def test_fetch_does_not_stack_timeouts_for_dom_fallback():
    """Bug-A regression: the DOM-fallback path (entered when XHR never fires)
    must NOT double the wall-clock relative to a hypothetical XHR-only run.

    We assert the same ceiling as `test_fetch_total_wall_clock_bounded_by_timeout_s`
    because both paths share the same `timeout_s` budget.
    """
    import time
    # DOM-fallback path: serve a page with no XHR and no matching selector.
    # _make_blank_route serves "<html><body><p>nothing here</p></body></html>"
    # which forces XHR-intercept timeout then DOM-fallback timeout.
    company = CompanyConfig(
        name="dom-fallback-bounded",
        url="https://www.dombounded.example/careers",
        hint="playwright:timeout_s=3",
    )
    handler = _make_blank_route()
    t0 = time.monotonic()
    with pytest.raises(PlaywrightTimeout):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)
    elapsed = time.monotonic() - t0
    assert elapsed < 10.0, (
        f"Bug-A regression: DOM-fallback path wall-clock {elapsed:.2f}s "
        f"exceeded 10s ceiling on a 3s declared timeout."
    )


def test_min_op_timeout_ms_constant_is_reasonable():
    """Bug-A: the per-op clamp floor must be:
      (a) > 0 so Playwright doesn't reject the timeout
      (b) small enough that an exhausted budget terminates promptly

    100ms is the chosen value. This test locks that policy into the suite
    so a future tweak is intentional rather than accidental.
    """
    from src.adapters.playwright_fallback import _MIN_OP_TIMEOUT_MS
    assert 1 < _MIN_OP_TIMEOUT_MS <= 1000, (
        f"_MIN_OP_TIMEOUT_MS={_MIN_OP_TIMEOUT_MS} is outside the reasonable "
        f"range (1, 1000]; revisit Bug-A fix policy."
    )


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


# ============================================================================
# Phase 3 Plan 03-03 — Credential workflow (SEC-01/02/04 + D-02 + D-02c)
# ============================================================================

# HTML fixtures for credential tests — kept inline so they live with the tests
# that consume them.

_LOGIN_PERSISTENT_HTML = (
    "<html><body>"
    "<form>"
    "<input type='email' name='email' />"
    "<input type='password' name='password' />"
    "<button type='submit' "
    "onclick=\"event.preventDefault(); return false;\">Sign in</button>"
    "</form>"
    "</body></html>"
)

_LOGIN_THEN_REDIRECT_HTML = (
    "<html><body>"
    "<form id='login'>"
    "<input type='email' name='email' />"
    "<input type='password' name='password' />"
    "<button type='submit' "
    "onclick=\"event.preventDefault(); "
    "document.getElementById('login').style.display='none';\">Sign in</button>"
    "</form>"
    "</body></html>"
)

_LOGIN_BLANK_HTML = (
    "<html><body>"
    "<p>career page, no login required</p>"
    "<div data-testid='job-card'>"
    "<h3>SWE New Grad</h3><p class='location'>Remote</p>"
    "<a href='/jobs/1'>Apply</a>"
    "</div>"
    "</body></html>"
)


def _make_html_route(html: str):
    """Route handler that serves the same HTML for every navigation request."""
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


# --- _company_to_secret_prefix — SEC-02 secret-naming convention ------------


def test_company_to_secret_prefix_uppercase_simple():
    """Plan 03-03 D-02a — simple company name uppercased."""
    assert PlaywrightAdapter._company_to_secret_prefix("amd") == "AMD"
    assert PlaywrightAdapter._company_to_secret_prefix("Anthropic") == "ANTHROPIC"


def test_company_to_secret_prefix_hyphens_become_underscores():
    """Plan 03-03 D-02a — hyphens map to underscores so env var names are
    POSIX-shell-safe.
    """
    assert (
        PlaywrightAdapter._company_to_secret_prefix("acme-corp") == "ACME_CORP"
    )
    assert (
        PlaywrightAdapter._company_to_secret_prefix("samsung-sra")
        == "SAMSUNG_SRA"
    )


def test_company_to_secret_prefix_spaces_become_underscores():
    """Plan 03-03 D-02a — spaces map to underscores for env var names."""
    assert (
        PlaywrightAdapter._company_to_secret_prefix("Big Co Inc")
        == "BIG_CO_INC"
    )


# --- _detect_login_form — heuristic --------------------------------------


def test_detect_login_form_positive(monkeypatch):
    """Plan 03-03 — HTML with `<input type='password'>` -> _detect_login_form True.

    Runs against a real Playwright page so the locator matches the live DOM.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.set_content(_LOGIN_PERSISTENT_HTML)
            assert PlaywrightAdapter._detect_login_form(page) is True
        finally:
            browser.close()


def test_detect_login_form_negative_anthropic_fixture():
    """Plan 03-03 — anthropic_sample.html has no password input -> False."""
    from playwright.sync_api import sync_playwright

    html = (_FIXTURES_DIR / "anthropic_sample.html").read_text()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.set_content(html)
            assert PlaywrightAdapter._detect_login_form(page) is False
        finally:
            browser.close()


# --- MissingCredential when env vars unset (SEC-01) ---------------------


def test_attempt_login_raises_missing_credential_when_email_unset(monkeypatch):
    """Plan 03-03 — login form detected + EMAIL env var unset -> MissingCredential.

    Per CONTEXT.md D-02: env var name pattern is `SCRAPER_<COMPANY>_<KIND>`.
    """
    monkeypatch.delenv("SCRAPER_TESTCO_EMAIL", raising=False)
    monkeypatch.setenv("SCRAPER_TESTCO_PASSWORD", "irrelevant")

    company = CompanyConfig(
        name="testco",
        url="https://login.testco.example/careers",
        hint="playwright:timeout_s=3",
    )
    handler = _make_html_route(_LOGIN_PERSISTENT_HTML)
    with pytest.raises(MissingCredential):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)


def test_attempt_login_raises_missing_credential_when_password_unset(monkeypatch):
    """Plan 03-03 — login form detected + PASSWORD env var unset -> MissingCredential."""
    monkeypatch.setenv("SCRAPER_TESTCO_EMAIL", "x@y.example")
    monkeypatch.delenv("SCRAPER_TESTCO_PASSWORD", raising=False)

    company = CompanyConfig(
        name="testco",
        url="https://login.testco.example/careers",
        hint="playwright:timeout_s=3",
    )
    handler = _make_html_route(_LOGIN_PERSISTENT_HTML)
    with pytest.raises(MissingCredential):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)


# --- InvalidCredential when form persists after submit (D-02c) -----------


def test_attempt_login_raises_invalid_credential_when_form_persists(monkeypatch):
    """Plan 03-03 — login form still visible after submit -> InvalidCredential.

    Fixture's submit handler does `preventDefault(); return false;` so the form
    never advances. Both env vars set; failure is a credential-rejection
    heuristic, not a missing-env case.
    """
    monkeypatch.setenv("SCRAPER_TESTCO_EMAIL", "x@y.example")
    monkeypatch.setenv("SCRAPER_TESTCO_PASSWORD", "wrong-password")

    company = CompanyConfig(
        name="testco",
        url="https://login.testco.example/careers",
        hint="playwright:timeout_s=5",
    )
    handler = _make_html_route(_LOGIN_PERSISTENT_HTML)
    with pytest.raises(InvalidCredential):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)


def test_invalid_credential_message_never_includes_credential_values(monkeypatch):
    """Plan 03-03 D-02c / SEC-03 / Pitfall 17 — exception message must NOT
    include the email or password value, only the company name + URL +
    diagnostic context.
    """
    secret_email = "secret-leak-canary@example.com"
    secret_password = "PaSsW0rD-leak-canary"
    monkeypatch.setenv("SCRAPER_TESTCO_EMAIL", secret_email)
    monkeypatch.setenv("SCRAPER_TESTCO_PASSWORD", secret_password)

    company = CompanyConfig(
        name="testco",
        url="https://login.testco.example/careers",
        hint="playwright:timeout_s=5",
    )
    handler = _make_html_route(_LOGIN_PERSISTENT_HTML)
    with pytest.raises(InvalidCredential) as exc_info:
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)
    # The exception message MUST NOT contain the credential values.
    msg = str(exc_info.value)
    assert secret_email not in msg, (
        f"SEC-03 violation: email leaked into InvalidCredential message: {msg!r}"
    )
    assert secret_password not in msg, (
        f"SEC-03 violation: password leaked into InvalidCredential message: {msg!r}"
    )
    # Cause chain must also be suppressed (D-02c — `from None`).
    assert exc_info.value.__cause__ is None


# --- _company_to_secret_prefix wired through adapter ---------------------


def test_attempt_login_uses_uppercased_hyphen_translated_env_vars(monkeypatch):
    """Plan 03-03 D-02a — for `name='acme-corp'`, adapter must read
    `SCRAPER_ACME_CORP_EMAIL` and `SCRAPER_ACME_CORP_PASSWORD`. We set those
    (and ONLY those), confirm MissingCredential is NOT raised. Then the form
    persists, so InvalidCredential is raised — proving the adapter reached
    the form-fill path with credentials it could read.
    """
    monkeypatch.setenv("SCRAPER_ACME_CORP_EMAIL", "x@y.example")
    monkeypatch.setenv("SCRAPER_ACME_CORP_PASSWORD", "anything")
    # The lowercased / original name MUST NOT be the env var key.
    monkeypatch.delenv("SCRAPER_acme-corp_EMAIL", raising=False)
    monkeypatch.delenv("SCRAPER_acme-corp_PASSWORD", raising=False)

    company = CompanyConfig(
        name="acme-corp",
        url="https://login.acme-corp.example/careers",
        hint="playwright:timeout_s=5",
    )
    handler = _make_html_route(_LOGIN_PERSISTENT_HTML)
    # Adapter found the env vars (no MissingCredential), submitted, form
    # persisted, raised InvalidCredential.
    with pytest.raises(InvalidCredential):
        PlaywrightAdapter().fetch(company, _test_route_handler=handler)


# --- No login form -> regular fetch flow (regression) -------------------


def test_no_login_form_skips_credential_path():
    """Plan 03-03 — pages with NO login form proceed through normal XHR /
    DOM-fallback extraction. This is the common case; credential branch
    must be silent.
    """
    handler = _make_html_route(_LOGIN_BLANK_HTML)
    company = CompanyConfig(
        name="nologin",
        url="https://nologin.example/careers",
        hint="playwright:timeout_s=5",
    )
    # XHR predicate won't fire; DOM fallback selects [data-testid='job-card'].
    raw = PlaywrightAdapter().fetch(
        company, _test_route_handler=handler,
    )
    assert len(raw) == 1
    assert raw[0].raw["title"] == "SWE New Grad"


# --- SEC-03 grep audit — no credential values in raise statements -------


def test_sec03_grep_audit_no_credential_values_in_adapter_logging():
    """Plan 03-03 D-02c — structural enforcement: no logger.* / print / raise
    statement in playwright_fallback.py captures the RETURN VALUE of
    os.environ.get(...) (which is the credential VALUE) into log output.

    We grep for the pattern:
      `SCRAPER_..._(EMAIL|PASSWORD|USERNAME|API_KEY|OAUTH_TOKEN)\\s*=`
    in raise / logger / print lines. The convention is to LOG the env var NAME
    (e.g., "SCRAPER_TESTCO_EMAIL") but NEVER assign it to a local + then
    interpolate the local into a logger / raise.
    """
    src = Path("src/adapters/playwright_fallback.py").read_text()
    # Lines with raise / log / print AND a SCRAPER_*_<KIND>= assignment
    # would be the smoking gun. NO comment lines.
    leaky_lines = []
    for ln in src.splitlines():
        stripped = ln.strip()
        if stripped.startswith("#"):
            continue
        if not re.search(r"(raise |logger\.|print\()", stripped):
            continue
        if re.search(
            r"SCRAPER_[A-Z_]+_(EMAIL|PASSWORD|USERNAME|API_KEY|OAUTH_TOKEN)\s*=",
            stripped,
        ):
            leaky_lines.append(stripped)
    assert leaky_lines == [], (
        f"SEC-03 violation: credential VALUE assignment in raise/log/print: "
        f"{leaky_lines}"
    )


def test_sec03_no_traceback_format_exc_in_adapter():
    """Plan 03-03 D-02c — structural ban on `traceback.format_exc` in the
    Playwright adapter (mirrors Phase 1 + 2 + Plan 03-01 + Plan 03-02 discipline).
    """
    src = Path("src/adapters/playwright_fallback.py").read_text()
    assert src.count("traceback.format_exc") == 0, (
        "SEC-03 violation: traceback.format_exc found in playwright_fallback.py"
    )
