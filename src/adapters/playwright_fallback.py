"""Playwright fallback adapter — ADP-09 + ADP-10 (Phase 3 Plan 03-02).

Catch-all for sites without a dedicated ATS adapter (Anthropic, Vercel,
Linear, Tesla, custom corporate portals). Registered LAST in
src/registry.py ADAPTERS so all 6 ATS-specific adapters' matches() get
first crack.

Strategy per CONTEXT.md D-01a:
  1. XHR-intercept FIRST via page.expect_response (captures the JSON
     job-data call: /api/jobs, /api/v1/openings, /api/positions).
     Fastest + most reliable; bypasses DOM hydration timing (Pitfall 8).
  2. DOM-selector fallback via page.wait_for_selector + selectolax HTML
     parse. Slower but covers sites with unpredictable XHR shapes.
  3. Both paths fail -> raise PlaywrightTimeout (Phase 1 typed exception).

Per CONTEXT.md D-04: playwright-stealth ON by default; opt-out via
hint `#adapter=playwright:stealth=false`.

Per CONTEXT.md D-05: 60s default navigation timeout; per-site override
via `#adapter=playwright:timeout_s=N`.

Per CONTEXT.md D-06 + Pitfall 4 / Pitfall 17: trace='off' in production.
Setting SCRAPER_DEBUG_TRACE=1 env var enables retain-on-failure trace
(local debug only - workflow YAML does NOT set this env var).

Dedup key: `pw:<host>:<id>` where <id> is the posting's stable XHR
field (id / jobId / positionId) if present, else
sha256(canonicalize_url(posting_url))[:16]. NEVER raw URL (Pitfall 9).

Per Pitfall 17 / SEC-03: exception messages include adapter + company +
URL ONLY - never response body, never request headers, never trace
file paths. The full traceback is never captured.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from collections.abc import Callable
from typing import ClassVar
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from src.adapters.base import (
    Adapter,
    InvalidCredential,
    MissingCredential,
    PlaywrightTimeout,
)
from src.models import CompanyConfig, RawPosting

logger = logging.getLogger("scan")

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
_DEFAULT_TIMEOUT_S = 60.0  # D-05
_VIEWPORT = {"width": 1920, "height": 1080}
_DEBUG_TRACE_ENV = "SCRAPER_DEBUG_TRACE"  # D-06 escape hatch
_TRACE_DIR = ".playwright-trace"  # gitignored per Plan 03-01

# XHR predicate keywords - adapter captures any /api/ response containing
# any of these in its URL. Heuristic; refine per-site if needed.
_XHR_KEYWORDS = ("jobs", "openings", "positions", "careers", "roles")

# Minimum per-operation timeout (ms) used when the remaining budget falls
# below this floor. Bug-A fix (2026-06-08): the adapter is deadline-bounded
# overall, but Playwright sync ops reject `timeout=0` or sub-millisecond
# values awkwardly — clamp every requested timeout to this minimum so an
# almost-exhausted budget still raises a clean PlaywrightTimeoutError.
_MIN_OP_TIMEOUT_MS = 100

# DOM-fallback selectors - tried in order; first match wins.
_DOM_SELECTORS = (
    "[data-testid='job-card']",
    "[data-testid='posting']",
    ".job-listing",
    ".career-card",
    "article.job",
    "li.job",
)


def _parse_hint_kwargs(hint: str | None) -> dict[str, str]:
    """Parse 'playwright:k1=v1,k2=v2' into a dict.

    Returns empty dict for None / bare 'playwright' / unparseable input.
    Per Phase 1 CFG-03 + Phase 3 D-04/D-05 hint metadata format.
    """
    if not hint or ":" not in hint:
        return {}
    _name, meta = hint.split(":", 1)
    out: dict[str, str] = {}
    for pair in meta.split(","):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _id_from_posting(posting: dict, posting_url: str) -> str:
    """Extract stable ID; fall back to sha256(url)[:16].

    Per CONTEXT.md <specifics> + Pitfall 9: NEVER use raw URL as the dedup key.
    """
    for k in ("id", "jobId", "positionId", "postingId", "uuid"):
        v = posting.get(k)
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    # No stable ID - hash the URL.
    return hashlib.sha256(posting_url.encode("utf-8")).hexdigest()[:16]


def _get_stealth_class():
    """Indirection so tests can monkeypatch the Stealth class without importing
    playwright_stealth at collection time on machines that lack it.
    """
    from playwright_stealth import Stealth
    return Stealth


def _record_trace_started() -> None:
    """Test-observable hook: invoked once when context.tracing.start() runs.

    Production behavior: no-op. Tests monkeypatch this to detect trace activation
    without inspecting Playwright internals.
    """
    return None


class PlaywrightAdapter(Adapter):
    """Catch-all Playwright adapter for non-ATS career pages - ADP-09 + ADP-10.

    Always registered LAST in ADAPTERS. matches() returns True for any
    http(s) URL - the 6 ATS adapters' specific matches() fire first.

    Phase 3 Plan 03-03: optional credential flow for sites that gate postings
    behind a login form. When `<input type='password'>` is detected after the
    initial navigation, the adapter reads SCRAPER_<COMPANY_UPPERCASE>_<KIND>
    env vars (SEC-01 / SEC-02 / D-02a), fills the form, submits, and waits
    briefly. If the form persists after submit, raises InvalidCredential.
    Per SEC-03 / Pitfall 17 / D-02c: NEVER logs credential values; uses
    `raise ... from None` to suppress chained tracebacks that could leak
    DOM text through __cause__.
    """

    name: ClassVar[str] = "playwright"

    # Phase 3 Plan 03-03 — credential helpers + selectors. Kept as class
    # constants so tests + downstream consumers can reference them.
    _LOGIN_WAIT_MS: ClassVar[int] = 3000  # D-02c — bounded post-submit wait
    _EMAIL_SELECTOR: ClassVar[str] = (
        "input[type='email'], input[name='email'], input[name='username']"
    )
    _PASSWORD_SELECTOR: ClassVar[str] = "input[type='password']"
    _SUBMIT_SELECTOR: ClassVar[str] = (
        "button[type='submit'], input[type='submit'], "
        "button:has-text('Sign in'), button:has-text('Log in')"
    )

    @classmethod
    def matches(cls, url: str) -> bool:
        return url.startswith(("http://", "https://"))

    @staticmethod
    def _detect_login_form(page) -> bool:
        """Heuristic: page has at least one `<input type='password'>` element.

        Returns True if a password input is present; False otherwise. Tolerant
        of any locator error — a malformed page must NEVER abort the scrape
        (per Pitfall 1 / ADP-12).
        """
        try:
            return page.locator(
                PlaywrightAdapter._PASSWORD_SELECTOR
            ).count() > 0
        except Exception:
            return False

    @staticmethod
    def _company_to_secret_prefix(company_name: str) -> str:
        """Convert company name to `SCRAPER_<NAME>_<KIND>` prefix per SEC-02.

        Uppercases the name; replaces hyphens and spaces with underscores so
        the result is POSIX-shell-safe as an env-var name. Per CONTEXT.md D-02a.

          'amd'         -> 'AMD'
          'acme-corp'   -> 'ACME_CORP'
          'Big Co Inc'  -> 'BIG_CO_INC'
        """
        return company_name.upper().replace("-", "_").replace(" ", "_")

    def _attempt_login(self, page, company: CompanyConfig) -> None:
        """Read SCRAPER_<COMPANY>_<KIND> env vars; fill form; submit; verify.

        Per CONTEXT.md D-02 / D-02a (eager prompt + separate per-kind secrets)
        and D-02c + SEC-03 + Pitfall 17 (structural ban on credential-value
        logging — exception messages contain ONLY company name + env var
        NAMES, never the values).

        Raises:
            MissingCredential: either EMAIL or PASSWORD env var is unset.
            InvalidCredential: login form persists after submit + brief wait,
                OR the fill/click selector failed (which typically means the
                site changed its login UI — same user-visible outcome).
        """
        prefix = self._company_to_secret_prefix(company.name)
        email_var = f"SCRAPER_{prefix}_EMAIL"
        password_var = f"SCRAPER_{prefix}_PASSWORD"
        email = os.environ.get(email_var)
        password = os.environ.get(password_var)
        if not email or not password:
            # Note: we log the env var NAMES, never the values. NAMES are
            # public information (they appear in README SEC-06 + CLAUDE.md).
            raise MissingCredential(
                f"Playwright {company.name}: missing env var "
                f"{email_var} or {password_var}"
            )

        try:
            page.fill(self._EMAIL_SELECTOR, email)
            page.fill(self._PASSWORD_SELECTOR, password)
            page.click(self._SUBMIT_SELECTOR)
        except Exception as e:
            # SEC-03 + D-02c: NEVER include exception attrs (DOM text may
            # contain the typed email or other PII). `from None` suppresses
            # the chained traceback that could leak through __cause__.
            raise InvalidCredential(
                f"Playwright {company.name}: login fill/submit failed "
                f"({type(e).__name__})"
            ) from None

        # Bounded wait — 3s is enough for most auth pages to advance.
        page.wait_for_timeout(self._LOGIN_WAIT_MS)

        # D-02c — SEC-03: message says NOTHING about WHICH credential was tried.
        if self._detect_login_form(page):
            raise InvalidCredential(
                f"Playwright {company.name}: login form still present "
                "after submit (wrong credentials, anti-bot challenge, "
                "or selector drift)"
            )

    def fetch(
        self,
        company: CompanyConfig,
        seen_keys: set[str] | None = None,
        _test_route_handler: Callable | None = None,
    ) -> list[RawPosting]:
        """Fetch postings via XHR-intercept-first + DOM-selector fallback.

        Args:
          company: CompanyConfig. Reads company.resolved_url or company.url
                   as the navigation target. Hint metadata controls stealth
                   + timeout (D-04 / D-05).
          seen_keys: optional set of already-seen dedup keys. Currently unused
                     by this adapter (most SPAs don't paginate); accepted for
                     signature symmetry with paginated ATS adapters.
          _test_route_handler: TEST-ONLY seam. A callable that receives the
                     BrowserContext and may install context.route() mocks.
                     Mirrors the Phase 2 `seen_keys` precedent: a single
                     documented optional kwarg with a test-injection role.
                     Production code MUST NOT pass this.

        Raises:
          PlaywrightTimeout: navigation + both XHR-intercept and DOM-selector
                             timed out. Exception message is sanitized per
                             SEC-03 / Pitfall 17 - includes only adapter +
                             company + URL + timeout-seconds.
        """
        hint_kw = _parse_hint_kwargs(company.hint)
        stealth_enabled = hint_kw.get("stealth", "true").lower() != "false"
        try:
            timeout_s = float(hint_kw.get("timeout_s", _DEFAULT_TIMEOUT_S))
        except (ValueError, TypeError):
            timeout_s = _DEFAULT_TIMEOUT_S

        target_url = company.resolved_url or company.url
        host = (urlparse(target_url).hostname or "unknown").lower()
        trace_enabled = os.environ.get(_DEBUG_TRACE_ENV) == "1"  # D-06

        # Bug-A fix (2026-06-08): deadline-based timeout budget.
        #
        # Previously every Playwright op (initial page.goto, expect_response,
        # the goto inside it, DOM-fallback page.goto, and the per-selector
        # wait_for_selector loop) received the FULL `timeout_ms`. On the
        # worst path (XHR never fires AND no DOM selector matches) wall-clock
        # stacked to 2-3x the declared timeout — production runs at 60s
        # default were observed taking ~120s per site.
        #
        # Fix: compute a single monotonic deadline at entry. Every Playwright
        # op consumes from the same budget via `remaining_ms()`. Total wall-
        # clock is now bounded by `timeout_s` + O(ms) bookkeeping overhead.
        #
        # Per constraint #5: deadline-based (monotonic + arithmetic), NOT
        # signal-based — Python signals do not interact cleanly with the
        # Playwright sync runner.
        deadline = time.monotonic() + timeout_s

        def remaining_ms() -> int:
            """Milliseconds left until deadline, clamped to a minimum floor.

            Clamping to `_MIN_OP_TIMEOUT_MS` ensures Playwright operations
            receive a positive timeout even when the budget is nearly
            exhausted — they will then raise a clean PlaywrightTimeoutError
            within ~100ms rather than rejecting `timeout=0` awkwardly.
            """
            left = int((deadline - time.monotonic()) * 1000)
            return max(_MIN_OP_TIMEOUT_MS, left)

        # Import here so module loads on machines without Chromium installed.
        from playwright.sync_api import (
            TimeoutError as PlaywrightTimeoutError,
        )
        from playwright.sync_api import sync_playwright

        postings_raw: list[dict] = []
        extraction_path = "xhr"  # for logging which path succeeded

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport=_VIEWPORT,
                )
                if stealth_enabled:
                    # D-04: playwright-stealth 2.x API.
                    stealth_cls = _get_stealth_class()
                    stealth_cls().apply_stealth_sync(context)

                # TEST seam: allow tests to inject context.route() mocks
                # BEFORE any navigation fires.
                if _test_route_handler is not None:
                    _test_route_handler(context)

                if trace_enabled:
                    # D-06 - retain-on-failure only when SCRAPER_DEBUG_TRACE=1
                    context.tracing.start(
                        screenshots=True, snapshots=True, sources=False,
                    )
                    _record_trace_started()

                page = context.new_page()
                # Bug-A fix: default navigation timeout uses the remaining
                # budget at this moment; further per-op timeouts re-derive
                # the remaining budget at call time.
                page.set_default_navigation_timeout(remaining_ms())

                # Plan 03-03 credential gate. Do an initial navigation so the
                # page DOM is queryable for the login-form heuristic. If
                # detected, authenticate; downstream XHR/DOM extraction
                # continues against the now-authenticated page (we re-issue
                # navigation inside expect_response so a fresh XHR can fire).
                #
                # The initial navigation here is bounded by the same
                # navigation budget; a navigation timeout still surfaces as
                # PlaywrightTimeout downstream (both extraction paths fail).
                try:
                    page.goto(target_url, timeout=remaining_ms())
                except PlaywrightTimeoutError:
                    # Initial nav failed - let the XHR-intercept block also
                    # try (it might race a redirect successfully). Don't
                    # raise here; the downstream block decides.
                    pass
                if self._detect_login_form(page):
                    # _attempt_login raises MissingCredential / InvalidCredential
                    # on failure; both are typed exceptions the orchestrator
                    # catches per ADP-12 isolation.
                    self._attempt_login(page, company)

                try:
                    # D-01a path A: XHR intercept first.
                    # Bug-A fix: every Playwright op below draws from the
                    # shared `remaining_ms()` budget. The expect_response
                    # context manager and the goto inside it share the same
                    # ~remaining budget — Playwright stops the whichever
                    # fires first, so this is safe.
                    try:
                        with page.expect_response(
                            lambda r: (
                                r.status == 200
                                and "/api/" in r.url.lower()
                                and any(
                                    kw in r.url.lower()
                                    for kw in _XHR_KEYWORDS
                                )
                            ),
                            timeout=remaining_ms(),
                        ) as resp_info:
                            page.goto(target_url, timeout=remaining_ms())
                        response = resp_info.value
                        try:
                            data = response.json()
                        except Exception:
                            data = None
                        if data is not None:
                            postings_raw = self._parse_xhr_payload(data)
                        extraction_path = "xhr"
                    except PlaywrightTimeoutError:
                        # D-01a path B: DOM fallback. By this point the XHR
                        # path consumed most of `timeout_s`; `remaining_ms()`
                        # is now small — clamped to _MIN_OP_TIMEOUT_MS.
                        # Total wall-clock remains bounded by `timeout_s`.
                        extraction_path = "dom"
                        try:
                            page.goto(target_url, timeout=remaining_ms())
                        except PlaywrightTimeoutError:
                            # Navigation itself timed out - both paths dead.
                            raise PlaywrightTimeout(
                                f"Playwright {company.name}: navigation "
                                f"timed out after {timeout_s}s "
                                f"(url={target_url})"
                            ) from None
                        selector = None
                        # Each selector probe gets a fraction of the
                        # remaining budget at the moment of this loop;
                        # first match wins.
                        budget_for_selectors = remaining_ms()
                        per_selector_timeout = max(
                            _MIN_OP_TIMEOUT_MS,
                            budget_for_selectors // max(1, len(_DOM_SELECTORS)),
                        )
                        for sel in _DOM_SELECTORS:
                            try:
                                page.wait_for_selector(
                                    sel, timeout=per_selector_timeout,
                                )
                                selector = sel
                                break
                            except PlaywrightTimeoutError:
                                continue
                        if selector is None:
                            raise PlaywrightTimeout(
                                f"Playwright {company.name}: neither "
                                f"XHR-intercept nor any DOM selector matched "
                                f"within {timeout_s}s (url={target_url})"
                            ) from None
                        html = page.content()
                        postings_raw = self._parse_html_selector(
                            html, selector, target_url,
                        )
                finally:
                    if trace_enabled:
                        # D-06 trace path - store in gitignored
                        # `.playwright-trace/`. Failure to write the trace
                        # must NEVER break the scrape.
                        os.makedirs(_TRACE_DIR, exist_ok=True)
                        try:
                            context.tracing.stop(
                                path=f"{_TRACE_DIR}/{host}.zip",
                            )
                        except Exception as e:
                            logger.warning(
                                "trace:%s stop failed (%s)",
                                host, type(e).__name__,
                            )
                    context.close()
            finally:
                browser.close()

        logger.info(
            "playwright:%s extracted %d postings via %s path",
            company.name, len(postings_raw), extraction_path,
        )

        result: list[RawPosting] = []
        for p in postings_raw:
            posting_url = p.get("posting_url", "") or target_url
            pid = _id_from_posting(p, posting_url)
            dedup_key = f"pw:{host}:{pid}"
            enriched = dict(p)
            enriched["__dedup_key"] = dedup_key
            enriched["__host"] = host
            enriched["__extraction_path"] = extraction_path
            result.append(
                RawPosting(
                    source_company=company.name,
                    source_adapter=self.name,
                    raw=enriched,
                )
            )
        return result

    def _parse_xhr_payload(self, data) -> list[dict]:
        """Coalesce common shapes: {jobs:[..]}, {openings:[..]}, {results:[..]}, [..].

        Returns a list of posting dicts (each with title / location /
        posting_url / postingDate / description keys). Empty list when no
        recognizable shape. Defensive: never raises (Phase 1 SchemaDrift
        discipline lives at the contract layer, but Playwright is a catch-all
        - be tolerant).

        Also normalizes per-posting field names so the downstream
        normalizer's generic shape can read them consistently. We preserve
        the original keys too (the normalizer coalesces date keys).
        """
        items: list[dict]
        if isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            for key in (
                "jobs", "openings", "positions", "postings", "results", "data",
            ):
                v = data.get(key)
                if isinstance(v, list):
                    items = [item for item in v if isinstance(item, dict)]
                    break
            else:
                items = []
        else:
            return []

        # Mirror common XHR field aliases into the canonical names used by
        # _normalize_playwright. Preserve originals for the normalizer's
        # date-key coalesce.
        normalized: list[dict] = []
        for it in items:
            out = dict(it)
            if "posting_url" not in out:
                out["posting_url"] = (
                    out.get("postingUrl")
                    or out.get("url")
                    or out.get("absolute_url")
                    or ""
                )
            normalized.append(out)
        return normalized

    def _parse_html_selector(
        self, html: str, selector: str, base_url: str,
    ) -> list[dict]:
        """Parse HTML via selectolax; extract title + location + posting_url per card.

        Defensive: skip cards missing required fields; never raises.
        """
        tree = HTMLParser(html)
        results: list[dict] = []
        for node in tree.css(selector):
            title_node = (
                node.css_first("h3")
                or node.css_first("h2")
                or node.css_first(".job-title")
                or node.css_first(".title")
            )
            title = title_node.text(strip=True) if title_node else ""
            if not title:
                continue
            loc_node = (
                node.css_first(".location")
                or node.css_first("[data-testid='location']")
            )
            location = loc_node.text(strip=True) if loc_node else ""
            link_node = node.css_first("a")
            href = ""
            if link_node is not None:
                href = link_node.attributes.get("href", "") or ""
            posting_url = urljoin(base_url, href) if href else base_url
            results.append({
                "title": title,
                "location": location,
                "posting_url": posting_url,
                "description": "",
            })
        return results


__all__ = [
    "PlaywrightAdapter",
    "_parse_hint_kwargs",
    "_id_from_posting",
    "_DEFAULT_TIMEOUT_S",
    "_MIN_OP_TIMEOUT_MS",
    "_DEBUG_TRACE_ENV",
    "_USER_AGENT",
    "_get_stealth_class",
    "_record_trace_started",
]
# Plan 03-03 credential helpers are class methods on PlaywrightAdapter:
#   PlaywrightAdapter._detect_login_form
#   PlaywrightAdapter._company_to_secret_prefix
#   PlaywrightAdapter._attempt_login
