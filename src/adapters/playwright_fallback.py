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
from collections.abc import Callable
from typing import ClassVar
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from src.adapters.base import Adapter, PlaywrightTimeout
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
    """

    name: ClassVar[str] = "playwright"

    @classmethod
    def matches(cls, url: str) -> bool:
        return url.startswith(("http://", "https://"))

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
        timeout_ms = int(timeout_s * 1000)

        target_url = company.resolved_url or company.url
        host = (urlparse(target_url).hostname or "unknown").lower()
        trace_enabled = os.environ.get(_DEBUG_TRACE_ENV) == "1"  # D-06

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
                page.set_default_navigation_timeout(timeout_ms)

                try:
                    # D-01a path A: XHR intercept first.
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
                            timeout=timeout_ms,
                        ) as resp_info:
                            page.goto(target_url, timeout=timeout_ms)
                        response = resp_info.value
                        try:
                            data = response.json()
                        except Exception:
                            data = None
                        if data is not None:
                            postings_raw = self._parse_xhr_payload(data)
                        extraction_path = "xhr"
                    except PlaywrightTimeoutError:
                        # D-01a path B: DOM fallback.
                        extraction_path = "dom"
                        try:
                            page.goto(target_url, timeout=timeout_ms)
                        except PlaywrightTimeoutError:
                            # Navigation itself timed out - both paths dead.
                            raise PlaywrightTimeout(
                                f"Playwright {company.name}: navigation "
                                f"timed out after {timeout_s}s "
                                f"(url={target_url})"
                            ) from None
                        selector = None
                        # Each selector probe gets a fraction of remaining
                        # budget; first match wins.
                        per_selector_timeout = max(
                            500, timeout_ms // max(1, len(_DOM_SELECTORS))
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
    "_DEBUG_TRACE_ENV",
    "_USER_AGENT",
    "_get_stealth_class",
    "_record_trace_started",
]
