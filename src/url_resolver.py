"""URL redirect resolver (CONTEXT.md D-01b — Phase 3 Plan 03-01).

Unblocks the ~18-of-31 CNAME→Workday URLs in the user's companies.txt that
the WorkdayAdapter's strict `.myworkdayjobs.com` host regex would otherwise
miss. Cheap HEAD pre-flight; falls back to streaming GET when a site rejects
HEAD; returns the original URL on any error (graceful degradation — NEVER
raises to caller per D-01b).

Per Pitfall 17 / SEC-03: exception logging uses `type(e).__name__` ONLY —
never the full traceback, which could capture request headers (cookies,
session tokens). Mirrors the discipline in src/main.py and the Phase 2
adapters.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("scan")

# Honest scraper UA — preferable to spoofing real Chrome at this layer (per
# threat-model T-03-01-06 in 03-01-PLAN.md). Adapter-level scrapes (Workday,
# Playwright) use realistic browser UAs; HEAD pre-flight does not.
_USER_AGENT = (
    "new-grad-tracker/0.1 (+https://github.com/DevDesai444/new-grad)"
)
_DEFAULT_TIMEOUT_S = 5.0


def resolve_url(url: str, timeout_s: float = _DEFAULT_TIMEOUT_S) -> str:
    """Follow HTTP redirects from `url` and return the final URL.

    Tries HEAD first (cheap — body is not transferred). If the server returns
    405 (Method Not Allowed) or 501 (Not Implemented), falls back to streaming
    GET (which also does not pull the body — context-manager closes the
    connection before reading). On ANY error (timeout, network failure,
    unexpected 4xx/5xx status), returns the original `url` unchanged —
    adapter dispatch then proceeds with the unresolved URL and may fall
    through to Playwright catch-all (Plan 03-02).

    Per CONTEXT.md D-01b: this function NEVER raises to the caller. The
    orchestrator (src/main.py) wraps the call defensively anyway (defense in
    depth, Plan 03-01 Task 2), but the no-raise contract is owned here.

    Args:
        url: The raw URL from companies.txt (Phase 1 CompanyConfig.url).
        timeout_s: Per-request timeout in seconds (default 5.0).

    Returns:
        The final URL after following 301/302/303/307/308 redirects, or the
        original `url` on any error.
    """
    headers = {"User-Agent": _USER_AGENT}
    try:
        r = httpx.head(
            url,
            follow_redirects=True,
            timeout=timeout_s,
            headers=headers,
        )
        if r.status_code in (405, 501):
            # HEAD not allowed — fall back to streaming GET. The context
            # manager closes the connection before the body is consumed, so
            # we never actually read the response payload.
            try:
                with httpx.stream(
                    "GET",
                    url,
                    follow_redirects=True,
                    timeout=timeout_s,
                    headers=headers,
                ) as g:
                    return str(g.url)
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                logger.info(
                    "resolve_url: %s GET-fallback failed (%s), returning original",
                    url,
                    type(e).__name__,
                )
                return url
        if 200 <= r.status_code < 400:
            return str(r.url)
        # 4xx (other than 405/501) or 5xx — return original. The adapter
        # dispatch will either match the original URL or fall through to the
        # Playwright catch-all (Plan 03-02).
        logger.info(
            "resolve_url: %s returned HTTP %d, returning original",
            url,
            r.status_code,
        )
        return url
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        # Per CONTEXT.md D-01b + SEC-03 / Pitfall 17: log class name + URL
        # only, never exception attributes (could include request headers or
        # response bodies). Mirrors the orchestrator's logging discipline.
        logger.info(
            "resolve_url: %s failed (%s), returning original",
            url,
            type(e).__name__,
        )
        return url


__all__ = ["resolve_url"]
