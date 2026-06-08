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

## Bug-B upgrade (2026-06-08, debug session `playwright-timeout-cname-bugs`)

The vanilla HEAD/GET-redirect-chain approach fails for two classes of
CNAME→ATS URLs that the user's companies.txt contains:

  1. **Body-embedded ATS** — sites that 200-OK their landing page directly
     but embed a Workday tenant URL in the HTML (e.g., careers.arrow.com →
     200, body contains `https://arrow.wd1.myworkdayjobs.com/en-US/AC`).
     HEAD-chain misses these because there is no HTTP redirect.

  2. **CDN-blocked landing** — sites whose landing page returns Cloudflare/
     Imperva 403 to non-browser clients (e.g., careers.servicenow.com,
     jobs.gartner.com — both actually SmartRecruiters-hosted under the hood).
     HEAD-chain returns the original URL on 403; the SmartRecruitersAdapter's
     strict-match `matches()` then fails and dispatch falls through to
     PlaywrightAdapter.

Two strategies added (run AFTER the HEAD/GET chain, only when it didn't
already produce a definitively-matched ATS URL):

  (A) **Body-scan** — fetch the resolved URL with a realistic browser UA
      and grep the HTML for `https://<tenant>.wd<N>.myworkdayjobs.com/...`
      Workday tenant URLs. If one is found, return it.

  (B) **SmartRecruiters probe** — derive a candidate SR identifier from the
      hostname (`careers.servicenow.com` → `ServiceNow`, `jobs.gartner.com`
      → `Gartner` — title-cased, no separators) and HEAD-probe
      `https://jobs.smartrecruiters.com/<Identifier>`. If it 301-redirects
      to `https://careers.smartrecruiters.com/<Identifier>`, return that
      (the SmartRecruitersAdapter's `matches()` will then dispatch correctly).

Both strategies are best-effort and no-raise: any failure logs at INFO and
returns the original URL (preserving D-01b's discipline).

Adapter coverage NOT recoverable by these strategies (deferred to
follow-up work, per debug session SUMMARY):
  - Phenom People (Adobe), iCIMS (ARM), Avature (Bloomberg, Lenovo),
    Oracle HCM Cloud (JPMorgan), Eightfold (Micron).
  None of these have an existing adapter in src/adapters/; writing them
  is per-ATS work tracked separately.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("scan")

# Honest scraper UA — preferable to spoofing real Chrome at this layer (per
# threat-model T-03-01-06 in 03-01-PLAN.md). Adapter-level scrapes (Workday,
# Playwright) use realistic browser UAs; HEAD pre-flight does not.
_USER_AGENT = (
    "new-grad-tracker/0.1 (+https://github.com/DevDesai444/new-grad)"
)

# Bug-B body-scan needs a realistic UA — many landing pages (Cloudflare-
# fronted in particular) return a stub or 403 to non-browser UAs. We use
# this UA for the body-scan GET only; HEAD/streaming-GET pre-flight stays
# on the honest scraper UA.
_BODY_SCAN_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
_DEFAULT_TIMEOUT_S = 5.0

# Bug-B: bounded body-scan — never read more than this many bytes from a
# remote response. Most landing pages embed the Workday URL in the first
# 100-200 KB; bounding at 1 MB caps per-company resolver cost.
_BODY_SCAN_MAX_BYTES = 1_048_576  # 1 MiB

# Bug-B: Workday tenant URL pattern (matches `https://<tenant>.wd<N>.
# myworkdayjobs.com/<path>` with the path component required so we don't
# return a bare host that the WorkdayAdapter can't parse). Locale segment
# (en-US/) is optional and falls into the trailing path capture.
_WORKDAY_URL_BODY_PATTERN = re.compile(
    r"https://"
    r"(?:[a-z0-9-]+)\.wd(?:\d+)\.myworkdayjobs\.com"
    r"/[A-Za-z0-9_\-/]+"
)

# Bug-B: SmartRecruiters probe host — when the SR identifier derives from
# the original hostname, we HEAD-probe this URL pattern. SR consistently
# 301-redirects `jobs.smartrecruiters.com/<Identifier>` to
# `careers.smartrecruiters.com/<Identifier>` (both forms valid; matches()
# matches the latter).
_SR_PROBE_HOST = "jobs.smartrecruiters.com"


def _scan_body_for_workday(body: str) -> str | None:
    """Return the first Workday tenant URL embedded in `body`, or None.

    Bug-B helper. The match must include a non-empty path component so the
    returned URL can be parsed by WorkdayAdapter (which requires
    `<tenant>.wd<N>.myworkdayjobs.com/<site>`).

    Defensive: never raises (caller wraps; we still guard internally for
    cases like exotic regex inputs).
    """
    if not body:
        return None
    try:
        m = _WORKDAY_URL_BODY_PATTERN.search(body)
    except Exception:
        return None
    if m is None:
        return None
    # Strip trailing punctuation/whitespace the regex may have captured.
    return m.group(0).rstrip("./,;\"'")


def _candidate_sr_identifier(url: str) -> str | None:
    """Derive a SmartRecruiters identifier from `url`'s hostname.

    Bug-B helper. Recognized hostname patterns:
      careers.<service>.com -> <Service> (title-cased)
      jobs.<service>.com    -> <Service> (title-cased)
      careers.<service>.io  -> <Service>

    Examples:
      careers.servicenow.com -> "ServiceNow"
      jobs.gartner.com       -> "Gartner"
      careers.zoom.us        -> None  (TLD .us not recognized)

    Returns None when the hostname doesn't match a derivable pattern.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    # Only attempt derivation for `careers.X.com` / `jobs.X.com` / .io / .net
    # — these are the patterns the user's CNAME URLs follow.
    m = re.fullmatch(
        r"(?:careers|jobs)\.([a-z0-9-]+)\.(?:com|io|net)", host
    )
    if m is None:
        return None
    base = m.group(1)
    # SmartRecruiters identifiers are case-preserved by the platform
    # (`ServiceNow`, `Gartner`, `Notion`). Use the user's expected form:
    # the leading letter capitalized, rest of the leading word preserved,
    # camel-casing for embedded hyphens. For simple lowercase service
    # names we get a title-cased result; for hyphenated names we strip
    # the hyphen and title-case each segment.
    parts = base.split("-")
    # Special-case: known camel-case identifiers the platform uses.
    # Per the debug session's recon table, "servicenow" -> "ServiceNow"
    # and "gartner" -> "Gartner". The generic title-case rule handles
    # the latter; for the camel-case form we apply a small known table.
    _CAMEL_OVERRIDES = {
        "servicenow": "ServiceNow",
    }
    if base in _CAMEL_OVERRIDES:
        return _CAMEL_OVERRIDES[base]
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _smartrecruiters_probe(url: str, timeout_s: float) -> str | None:
    """Probe SmartRecruiters for an organization matching `url`'s host.

    Bug-B helper. Returns a `https://careers.smartrecruiters.com/<Identifier>`
    URL if SR knows the organization AND has at least one active posting,
    else None.

    Strategy:
      1. Derive a candidate identifier from `url`'s hostname.
      2. HEAD `https://jobs.smartrecruiters.com/<Identifier>` with
         `follow_redirects=True`. SR's `jobs.` host 301s to
         `careers.smartrecruiters.com/<Identifier>` for ANY string and
         400s for unknown ones (so the HEAD alone is too permissive — it
         returns 200 for orgs that don't actually use SR).
      3. **Verify via the postings API** —
         `https://api.smartrecruiters.com/v1/companies/<Identifier>/postings?limit=1`
         returns `{"totalFound": N, ...}`. Only when `N > 0` do we accept
         the SR identifier as the org's real ATS. This filters out the
         many "Adobe / Bloomberg / JPMorgan / Lenovo / etc." organizations
         that have SR landing pages but actually use a different ATS
         (Phenom / Avature / Oracle HCM). False positives there would
         cause the orchestrator to report `0 postings ok` for companies
         we genuinely don't know how to scrape — misleading.

    Defensive: never raises. Returns None on any HTTP error, timeout, or
    non-matching response.
    """
    candidate = _candidate_sr_identifier(url)
    if not candidate:
        return None
    probe_url = f"https://{_SR_PROBE_HOST}/{candidate}"
    headers = {"User-Agent": _USER_AGENT}
    # Step 2: HEAD probe to confirm SR knows the URL pattern.
    try:
        r = httpx.head(
            probe_url,
            follow_redirects=True,
            timeout=timeout_s,
            headers=headers,
        )
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        logger.info(
            "resolve_url:sr_probe %s failed (%s)",
            probe_url, type(e).__name__,
        )
        return None
    if r.status_code != 200:
        return None
    final = str(r.url)
    # Require the canonical SR careers host so SmartRecruitersAdapter.matches()
    # will fire downstream.
    if "careers.smartrecruiters.com" not in final.lower():
        return None

    # Step 3: verify the org actually has postings on SR. Without this check
    # SR returns a "Careers at X" stub for any string, leading us to dispatch
    # to SmartRecruitersAdapter for companies that don't actually use SR.
    api_url = (
        f"https://api.smartrecruiters.com/v1/companies/{candidate}"
        f"/postings?limit=1"
    )
    try:
        api_r = httpx.get(api_url, timeout=timeout_s, headers=headers)
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        logger.info(
            "resolve_url:sr_probe %s API check failed (%s)",
            api_url, type(e).__name__,
        )
        return None
    if api_r.status_code != 200:
        return None
    try:
        payload = api_r.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    total = payload.get("totalFound")
    if not isinstance(total, int) or total <= 0:
        # Org has no active postings — likely not their real ATS (Adobe,
        # Bloomberg, JPMorgan, Lenovo all match this pattern). Skip.
        logger.info(
            "resolve_url:sr_probe %s API totalFound=%r — not their real ATS",
            candidate, total,
        )
        return None
    return final


# Bug-B: known-ATS hostname fingerprints. When the HEAD chain already
# landed on one of these, the corresponding adapter's strict-match
# `matches()` will fire downstream — no body-scan or SR-probe is needed
# (saves a wasted GET / SR HEAD per company).
_KNOWN_ATS_HOST_SUBSTRINGS = (
    ".myworkdayjobs.com",
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "careers.smartrecruiters.com",
    "jobs.apple.com",
)


def _resolved_matches_known_ats(resolved_url: str) -> bool:
    """Return True if `resolved_url`'s host already matches a known ATS.

    Bug-B helper. When True, the body-scan + SR-probe extensions are
    skipped (the matching adapter's strict `matches()` will fire downstream
    on the existing resolved URL).
    """
    low = resolved_url.lower()
    return any(s in low for s in _KNOWN_ATS_HOST_SUBSTRINGS)


def _fetch_body_for_scan(url: str, timeout_s: float) -> str | None:
    """Fetch `url` with a realistic browser UA, bounded by _BODY_SCAN_MAX_BYTES.

    Bug-B helper. Returns the (text) body or None on any error.

    The realistic UA is required because many landing pages (Cloudflare,
    Imperva, Akamai) return a stub challenge or 403 to the honest scraper
    UA. The body-scan only looks for ATS hostname patterns in the response —
    SEC-03 / Pitfall 17 still applies (we do not log body content; only
    log the URL + status + match-or-not result).

    Defensive: never raises. Returns None on any error including non-text
    content-type, oversized body, network failure, timeout.
    """
    headers = {
        "User-Agent": _BODY_SCAN_USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.stream(
            "GET",
            url,
            follow_redirects=True,
            timeout=timeout_s,
            headers=headers,
        ) as r:
            if r.status_code != 200:
                return None
            # Only scan HTML — JSON / image bodies cannot embed an ATS URL
            # in a meaningful way and pulling them is wasteful.
            ct = r.headers.get("content-type", "").lower()
            if "html" not in ct and "text" not in ct:
                return None
            # Bounded read; stop after _BODY_SCAN_MAX_BYTES.
            chunks: list[bytes] = []
            total = 0
            for chunk in r.iter_bytes():
                chunks.append(chunk)
                total += len(chunk)
                if total >= _BODY_SCAN_MAX_BYTES:
                    break
            try:
                return b"".join(chunks).decode("utf-8", errors="replace")
            except Exception:
                return None
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        logger.info(
            "resolve_url:body_scan %s failed (%s)",
            url, type(e).__name__,
        )
        return None


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

    ## Bug-B (2026-06-08) extension

    After the HEAD/GET chain settles, we attempt two additional strategies
    to surface a known-ATS URL for CNAME→ATS sites that don't redirect
    cleanly via HTTP:

      (A) Body-scan: if the chain landed on a 200 HTML response, fetch the
          body (bounded to 1 MiB) and search for a Workday tenant URL
          (`https://<tenant>.wd<N>.myworkdayjobs.com/<path>`). If found,
          return it. Resolves careers.arrow.com → arrow.wd1.myworkdayjobs.com
          and similar body-embedded Workday cases.

      (B) SmartRecruiters probe: derive a candidate identifier from the
          hostname and HEAD-probe `https://jobs.smartrecruiters.com/<id>`.
          If SR knows the organization, returns the 301-redirected
          `careers.smartrecruiters.com/<id>` URL. Resolves
          careers.servicenow.com → careers.smartrecruiters.com/ServiceNow
          and jobs.gartner.com → careers.smartrecruiters.com/Gartner even
          though both landing pages return 403 to non-browser clients.

    Both extension strategies are best-effort and no-raise. Failure returns
    the previously-resolved URL (or the original on full failure).

    Args:
        url: The raw URL from companies.txt (Phase 1 CompanyConfig.url).
        timeout_s: Per-request timeout in seconds (default 5.0).

    Returns:
        The final URL after following 301/302/303/307/308 redirects + any
        Bug-B extension match, or the original `url` on full failure.
    """
    headers = {"User-Agent": _USER_AGENT}
    resolved = url  # default: return original on any failure
    chain_status: int | None = None
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
                    resolved = str(g.url)
                    chain_status = g.status_code
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                logger.info(
                    "resolve_url: %s GET-fallback failed (%s), returning original",
                    url,
                    type(e).__name__,
                )
                # Fall through to Bug-B extensions on the original URL.
                resolved = url
        elif 200 <= r.status_code < 400:
            resolved = str(r.url)
            chain_status = r.status_code
        else:
            # 4xx (other than 405/501) or 5xx — keep `resolved = url` and
            # fall through to the SR-probe (Bug-B), which handles the
            # Cloudflare-403 ServiceNow / Gartner case.
            logger.info(
                "resolve_url: %s returned HTTP %d, attempting Bug-B fallbacks",
                url,
                r.status_code,
            )
            chain_status = r.status_code
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        # Per CONTEXT.md D-01b + SEC-03 / Pitfall 17: log class name + URL
        # only, never exception attributes (could include request headers or
        # response bodies). Mirrors the orchestrator's logging discipline.
        logger.info(
            "resolve_url: %s failed (%s), attempting Bug-B fallbacks",
            url,
            type(e).__name__,
        )
        # Fall through to Bug-B extensions; they're best-effort and may
        # surface a useful URL even when the HEAD chain failed entirely.

    # Bug-B extension (A): body-scan when the chain landed on a successful
    # response. Skip when the chain already produced a known-ATS host
    # (saves a wasted GET when, e.g., the HEAD chain already landed on
    # `<tenant>.wd<N>.myworkdayjobs.com`).
    if (
        chain_status is not None
        and 200 <= chain_status < 400
        and not _resolved_matches_known_ats(resolved)
    ):
        body = _fetch_body_for_scan(resolved, timeout_s)
        if body is not None:
            wd = _scan_body_for_workday(body)
            if wd is not None:
                logger.info(
                    "resolve_url: %s body-scan found Workday URL %s",
                    url, wd,
                )
                return wd

    # Bug-B extension (B): SmartRecruiters probe — runs when the HEAD chain
    # didn't already produce a known-ATS URL. Covers the Cloudflare-403 case
    # (servicenow, gartner) AND acts as a secondary check when body-scan
    # didn't find a Workday URL.
    if not _resolved_matches_known_ats(resolved):
        sr = _smartrecruiters_probe(url, timeout_s)
        if sr is not None:
            logger.info(
                "resolve_url: %s SmartRecruiters-probe found %s",
                url, sr,
            )
            return sr

    return resolved


__all__ = [
    "resolve_url",
    "_scan_body_for_workday",
    "_candidate_sr_identifier",
    "_smartrecruiters_probe",
    "_fetch_body_for_scan",
    "_resolved_matches_known_ats",
    "_BODY_SCAN_MAX_BYTES",
    "_KNOWN_ATS_HOST_SUBSTRINGS",
    "_WORKDAY_URL_BODY_PATTERN",
]
