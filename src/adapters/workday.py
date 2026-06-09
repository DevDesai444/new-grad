"""Workday CXS adapter — ADP-07.

Endpoint: POST https://<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs
Auth: none (public Workday CXS endpoints).

Per CONTEXT.md D-01: a Workday careers URL
  https://nvidia.wd5.myworkdayjobs.com/[en-US/]NVIDIAExternalCareerSite
is regex-parsed into (tenant, wd-number, site) directly — no `#adapter=` hint
required. The locale segment (e.g., `en-US/`) is OPTIONAL.

Per CONTEXT.md D-04 (Task 2 of Plan 02-02 — extends Task 1's single-page fetch):
  - Cold-start cap = 25 pages = 500 postings max on first run.
  - Early-termination if the last posting on a page is already in `seen.json`.
  - Sort-monotonicity sanity check: if a tenant ignores `sortBy`, fall back to cap.

Per Pitfall 5: use a realistic project-identifying User-Agent — default httpx UA
("python-httpx/<version>") is on every commercial bot-management blocklist; 403
on Workday tenants is the dominant failure mode and a realistic UA is the
single most effective mitigation.

Per Pitfall 6: schema assertions on the response (`jobPostings` present + list).
Per Pitfall 10: epoch-millisecond date handling (Workday `postedOn` field).

Dedup key: `wd:<tenant>:<job_req_id>` where `<job_req_id>` is the posting's
`bulletFields[0]` (JOB_REQ_ID) if present, else the last URL slug of `externalPath`.

postedOn has THREE known wire forms per Workday version:
  1. Epoch milliseconds (int/float)               -> datetime.fromtimestamp(ms/1000, tz=UTC)
  2. ISO-8601 string ("2026-06-01T14:00:00Z")      -> _parse_iso_to_utc
  3. Relative string ("Posted Today", "Posted N Days Ago", "Posted N+ Days Ago", "Posted Yesterday")
     -> arithmetic relative to run_started_at; "N+" semantic is LOWER bound.
"""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import UTC, datetime, timedelta
from typing import ClassVar, NamedTuple
from urllib.parse import urlparse

import httpx

from src.adapters.base import Adapter, SchemaDrift, SiteBlocked
from src.models import CompanyConfig, RawPosting
from src.normalizer import _parse_iso_to_utc

logger = logging.getLogger("scan")

_TIMEOUT_S = 20.0
_PAGE_SIZE = 20
_COLD_START_CAP_PAGES = 25  # D-04 hard ceiling on cold start; ~500 postings max.
_USER_AGENT = (
    "new-grad-tracker/0.1 (+https://github.com/DevDesai444/new-grad)"
)

# D-01 (CONTEXT.md <specifics>): tenant + wd-number + optional locale + site.
_WORKDAY_URL_RE = re.compile(
    r"^https?://"
    r"(?P<tenant>[a-z0-9-]+)\.wd(?P<wd_num>\d+)\.myworkdayjobs\.com/"
    r"(?:[a-z]{2}-[A-Z]{2}/)?"
    r"(?P<site>[A-Za-z0-9_-]+)/?$",
)

# Relative-string postedOn forms — order matters for "Yesterday" before the N-Days
# pattern (the N-days regex would not match "Yesterday" because no digit, but we
# leave explicit branches for clarity).
_RELATIVE_PATTERNS: tuple[
    tuple[re.Pattern[str], object], ...
] = (
    (re.compile(r"^posted\s+today\s*$", re.IGNORECASE), lambda m, now: now),
    (
        re.compile(r"^posted\s+yesterday\s*$", re.IGNORECASE),
        lambda m, now: now - timedelta(days=1),
    ),
    (
        re.compile(r"^posted\s+(\d+)\+?\s*days?\s+ago\s*$", re.IGNORECASE),
        lambda m, now: now - timedelta(days=int(m.group(1))),
    ),
)


class WorkdayURLParts(NamedTuple):
    """Parsed tenant + wd-number + site segments from a Workday careers URL."""

    tenant: str
    wd_num: str
    site: str


def _parse_workday_url(url: str) -> WorkdayURLParts:
    """Parse a Workday careers URL into (tenant, wd_num, site).

    Per CONTEXT.md D-01. Raises SchemaDrift with a diagnostic message naming
    WHICH piece is missing if the regex fails (a partial-match probe is used
    to tell the user whether the host or the path is the problem).
    """
    s = url.strip()
    m = _WORKDAY_URL_RE.match(s)
    if m is not None:
        return WorkdayURLParts(
            tenant=m.group("tenant"),
            wd_num=m.group("wd_num"),
            site=m.group("site"),
        )
    # Probe whether the host-portion matched — that tells us if "tenant + wd-number"
    # are present but the site/path is malformed.
    bare_re = re.compile(r"^https?://([a-z0-9-]+)\.wd(\d+)\.myworkdayjobs\.com/")
    if bare_re.match(s) is None:
        raise SchemaDrift(
            f"Workday URL did not match expected pattern "
            f"(missing tenant.wdN.myworkdayjobs.com host): {url}"
        )
    raise SchemaDrift(
        f"Workday URL did not match expected pattern "
        f"(tenant + wd-number parsed but site segment is missing or malformed): {url}"
    )


def _parse_workday_posted(value, run_started_at: datetime) -> datetime | None:
    """Parse Workday `postedOn` (epoch ms int | ISO string | relative string).

    Returns a UTC-aware datetime, or None for unknown / empty / malformed inputs.
    Per CONTEXT.md <specifics>:
      - epoch milliseconds (int/float)              -> datetime.fromtimestamp(ms/1000, tz=UTC)
      - ISO-8601 string                              -> _parse_iso_to_utc(...)
      - "Posted Today"                               -> run_started_at
      - "Posted Yesterday"                           -> run_started_at - 1d
      - "Posted N Days Ago" / "Posted N+ Days Ago"   -> run_started_at - N days
                                                        ("N+" is lower bound — at
                                                         least N days, but we don't
                                                         know the upper bound)
      - unknown                                      -> None (renderer falls back
                                                              to first_seen)
    """
    if value is None or value == "":
        return None
    # Form 1: epoch milliseconds. Note: bool is a subclass of int — exclude it.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
        except (ValueError, OSError, OverflowError):
            return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    # Form 2: ISO-8601 string.
    iso = _parse_iso_to_utc(s)
    if iso is not None:
        return iso
    # Forms 3-6: relative string.
    for pattern, fn in _RELATIVE_PATTERNS:
        m = pattern.match(s)
        if m is not None:
            return fn(m, run_started_at)
    # Form 7: unknown — let the renderer fall back to first_seen.
    return None


class WorkdayAdapter(Adapter):
    """Adapter for Workday CXS public job-board API — ADP-07.

    Per CONTEXT.md D-01: auto-parses tenant + wd-number + site from the raw
    careers URL (no metadata hint required from the user).

    Per CONTEXT.md D-04 (Task 2): paginated with early-termination + 25-page
    cold-start cap + sort-monotonicity sanity check. Task 1 ships single-page
    fetch only; Task 2 replaces ``fetch()`` with the pagination wrapper.

    Per Pitfall 5: realistic User-Agent + 403/429/5xx -> SiteBlocked.
    Per Pitfall 6: schema assertions on ``jobPostings`` -> SchemaDrift.
    Per Pitfall 17 / SEC-03: exception messages include adapter + company +
    observed-shape ONLY — never response body, never request headers.
    """

    name: ClassVar[str] = "workday"

    @classmethod
    def matches(cls, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        # Any host of the form <tenant>.wd<N>.myworkdayjobs.com matches.
        return host.endswith(".myworkdayjobs.com") and ".wd" in host

    def fetch(
        self,
        company: CompanyConfig,
        seen_keys: set[str] | None = None,
    ) -> list[RawPosting]:
        """Fetch all Workday postings for ``company``, paginating per D-04.

        Args:
          company: CompanyConfig with a Workday careers URL.
          seen_keys: optional set of dedup keys already in seen.json for this
                     company. When provided, pagination early-terminates as soon
                     as the last posting on a page is already known. When None
                     (Phase 1 Adapter.fetch contract), pagination runs to the
                     25-page cold-start cap.

        Raises:
          SchemaDrift: malformed URL OR malformed response (missing keys / wrong
                       types).
          SiteBlocked: HTTP 403 / 429 / 5xx from any page.

        Notes on D-04 algorithm:
          1. Cold-start cap = _COLD_START_CAP_PAGES (25) — hard ceiling on the
             very first scrape of a company (no seen_keys, no early-termination
             signal).
          2. Empty-page break — source has returned all results.
          3. Short-page break — fewer than _PAGE_SIZE postings means implicit
             end-of-results on most Workday tenants.
          4. Early-termination — when seen_keys is provided AND the last posting
             on the current page is already known, the rest of the (DESC-sorted)
             results are older + known, so we stop.
          5. Sort-monotonicity sanity check — if a tenant ignored our ``sortBy``
             implicit DESC ordering (Workday CXS body doesn't currently include
             an explicit sort key but the default is newest-first), we detect by
             comparing first-of-this-page vs last-of-previous-page. On violation
             we log a warning AND suppress early-termination for the remainder
             of this run (degrades to cap-only, which is correct + safe).
          6. Inter-page sleep — random 0.5-1.5s jitter between pages. This is
             monkey-patched to noop in slow tests; production keeps it.
        """
        parts = _parse_workday_url(company.resolved_url or company.url)
        api_url = (
            f"https://{parts.tenant}.wd{parts.wd_num}.myworkdayjobs.com"
            f"/wday/cxs/{parts.tenant}/{parts.site}/jobs"
        )
        # Capture a single run_started_at for this fetch — relative postedOn
        # forms ("Posted Today" etc.) need a stable reference within the call.
        run_started_at = datetime.now(UTC)

        collected: list[RawPosting] = []
        last_posted_per_page: list[datetime | None] = []
        suppress_early_term = False  # flipped True on sort-monotonicity violation

        for page_n in range(_COLD_START_CAP_PAGES):
            offset = page_n * _PAGE_SIZE
            page_postings = self._fetch_page_and_emit(
                api_url, parts, company,
                offset=offset, run_started_at=run_started_at,
            )
            if not page_postings:
                break  # source has no more results
            collected.extend(page_postings)

            # D-04 early-termination: if seen_keys is provided AND the last
            # posting on this page is already in it, the rest is older + known.
            if (
                seen_keys is not None
                and not suppress_early_term
                and page_postings[-1].raw["__dedup_key"] in seen_keys
            ):
                break

            # D-04 sort-monotonicity check (page 1 onwards). If the first posting
            # on this page is NEWER than the last posting on the previous page,
            # the tenant ignored sort ordering — log + degrade to cap-only.
            if page_n > 0 and last_posted_per_page:
                prev_last_date = last_posted_per_page[-1]
                curr_first_date = page_postings[0].raw.get("__posted_date_utc")
                if (
                    prev_last_date is not None
                    and curr_first_date is not None
                    and curr_first_date > prev_last_date
                ):
                    logger.warning(
                        "Workday %s: sort-monotonicity violation on page %d "
                        "(curr_first=%s newer than prev_last=%s) — tenant "
                        "ignored sortBy; falling back to cold-start cap",
                        company.name, page_n,
                        curr_first_date.isoformat(), prev_last_date.isoformat(),
                    )
                    suppress_early_term = True
            last_posted_per_page.append(
                page_postings[-1].raw.get("__posted_date_utc")
            )

            # Implicit end-of-results: short page (fewer than _PAGE_SIZE entries).
            if len(page_postings) < _PAGE_SIZE:
                break

            # Per CONTEXT.md Claude's-Discretion: brief inter-page sleep for
            # Workday only, to reduce 429 risk on tenants with strict rate limits.
            if page_n + 1 < _COLD_START_CAP_PAGES:
                time.sleep(random.uniform(0.5, 1.5))

        return collected

    def _fetch_page_and_emit(
        self,
        api_url: str,
        parts: WorkdayURLParts,
        company: CompanyConfig,
        offset: int,
        run_started_at: datetime,
    ) -> list[RawPosting]:
        """Issue a single CXS POST request and convert the page to RawPostings.

        Applies the full error ladder (403/429/5xx -> SiteBlocked;
        body-not-JSON -> SchemaDrift; missing/wrong-typed jobPostings ->
        SchemaDrift). httpx.HTTPError propagates uncaught.
        """
        body = {
            "limit": _PAGE_SIZE,
            "offset": offset,
            "searchText": "",
            "appliedFacets": {},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        try:
            response = httpx.post(
                api_url, json=body, headers=headers, timeout=_TIMEOUT_S,
            )
        except httpx.HTTPError:
            # Per SEC-03 / Pitfall 17: don't capture exception attributes that
            # might include request headers — orchestrator logs type+URL only.
            raise

        if response.status_code in (403, 429):
            raise SiteBlocked(
                f"Workday {company.name}: HTTP {response.status_code} from {api_url}"
            )
        if response.status_code >= 500:
            raise SiteBlocked(
                f"Workday {company.name}: HTTP {response.status_code} (server error) "
                f"from {api_url}"
            )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as e:
            raise SchemaDrift(
                f"Workday {company.name}: response body is not JSON"
            ) from e

        if not isinstance(payload, dict) or "jobPostings" not in payload:
            got = (
                list(payload.keys())
                if isinstance(payload, dict)
                else type(payload).__name__
            )
            raise SchemaDrift(
                f"Workday {company.name}: missing 'jobPostings' key (got: {got})"
            )
        if not isinstance(payload["jobPostings"], list):
            raise SchemaDrift(
                f"Workday {company.name}: 'jobPostings' is not a list "
                f"(got {type(payload['jobPostings']).__name__})"
            )

        result: list[RawPosting] = []
        for job in payload["jobPostings"]:
            if not isinstance(job, dict):
                continue
            # Dedup id: prefer bulletFields[0] (JOB_REQ_ID); fall back to
            # the last URL slug of externalPath (still source-stable).
            job_id: str | None = None
            bullets = job.get("bulletFields")
            if isinstance(bullets, list) and bullets:
                first_bullet = bullets[0]
                if first_bullet is not None:
                    job_id = str(first_bullet).strip() or None
            if not job_id:
                ext = job.get("externalPath") or ""
                if isinstance(ext, str) and "/" in ext:
                    job_id = ext.rstrip("/").split("/")[-1] or None
            if not job_id:
                # Skip individual malformed entries; don't kill the whole company.
                continue

            ext_path = job.get("externalPath") or ""
            # Bug G (2026-06-09): externalPath is JUST `/job/<location>/<title>_<id>`
            # — Workday requires the full URL to include the locale and site
            # segments (`/<locale>/<site>`) between host and externalPath, else
            # 404s. Hardcoding `/en-US` is acceptable for all US-presence
            # companies in the current companies.txt; future non-US-locale
            # tenants would need WorkdayURLParts to carry the locale.
            full_url = (
                f"https://{parts.tenant}.wd{parts.wd_num}.myworkdayjobs.com"
                f"/en-US/{parts.site}"
                f"{ext_path}"
            )
            dedup_key = f"wd:{parts.tenant}:{job_id}"
            posted_dt = _parse_workday_posted(job.get("postedOn"), run_started_at)

            enriched = dict(job)
            enriched["__dedup_key"] = dedup_key
            enriched["__tenant"] = parts.tenant
            enriched["__posting_url"] = full_url
            enriched["__posted_date_utc"] = posted_dt
            result.append(
                RawPosting(
                    source_company=company.name,
                    source_adapter=self.name,
                    raw=enriched,
                )
            )

        return result


# Re-export pagination knob constants so external callers + tests can import
# them without reaching into private module internals.
__all__ = [
    "WorkdayAdapter",
    "WorkdayURLParts",
    "_parse_workday_url",
    "_parse_workday_posted",
    "_COLD_START_CAP_PAGES",
    "_PAGE_SIZE",
    "_USER_AGENT",
]
