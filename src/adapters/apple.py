"""Apple Jobs ATS adapter — ADP-08.

Endpoint: POST https://jobs.apple.com/api/role/search
Auth: none (public).

Per CONTEXT.md D-01a: Apple is a SINGLE ORG — the dedup-key format is
`apple:<positionId>` with NO per-company prefix segment (cf. all other
adapters which use `<ats>:<company>:<id>`). Any subpath under jobs.apple.com
matches; the adapter ignores the URL path and POSTs the broad search endpoint.

Per CONTEXT.md D-03: ships full 6-test error-path set (happy + 2 SchemaDrift +
2 SiteBlocked + 1 generic propagation).

Per CONTEXT.md D-04: paginated with newest-first sort + early-termination on
seen.json overlap + 25-page cold-start safety cap + sort-monotonicity sanity
fallback. Mirrors the WorkdayAdapter pagination pattern.

Per CONTEXT.md <specifics>: request body is the minimal form
    {"query": "", "locale": "en-us", "page": N, "pageSize": 20,
     "sort": {"field": "postingDate", "order": "desc"}, "filters": {}}
This shape is MEDIUM-confidence per training data; lock it here and document
in code so future drift surfaces via SchemaDrift on the response check.

Response shape: Apple returns either `searchResults` (older shape) OR `results`
(newer shape). The adapter coalesces; raises SchemaDrift if BOTH are missing
or the present one is not a list.

Per Pitfall 5: realistic User-Agent (mirrors Workday adapter).
Per Pitfall 6: schema assertions on response — SchemaDrift on missing keys /
wrong types.
Per Pitfall 17 / SEC-03: exception messages include adapter name + company +
observed-keys list ONLY — never response body, never request headers.
"""
from __future__ import annotations

import logging
import random
import time
from typing import ClassVar
from urllib.parse import urlparse

import httpx

from src.adapters.base import Adapter, SchemaDrift, SiteBlocked
from src.models import CompanyConfig, RawPosting

logger = logging.getLogger("scan")

_HOST = "jobs.apple.com"
_API_URL = "https://jobs.apple.com/api/role/search"
_PAGE_SIZE = 20
_COLD_START_CAP_PAGES = 25  # D-04 hard ceiling — 25 × 20 = 500 postings max
_TIMEOUT_S = 30.0
_USER_AGENT = (
    "new-grad-tracker/0.1 (+https://github.com/DevDesai444/new-grad)"
)


class AppleAdapter(Adapter):
    """Adapter for Apple Jobs public role-search API — ADP-08.

    Per CONTEXT.md D-01a: dedup key has no per-company segment (Apple = single
    org). `matches()` accepts any `jobs.apple.com` URL (any subpath).

    Per CONTEXT.md D-04: paginated; sorts newest-first; early-terminates on
    seen.json overlap; falls back to 25-page cold-start cap; trips
    sort-monotonicity sanity check if Apple ignores the sort parameter.
    """

    name: ClassVar[str] = "apple"

    @classmethod
    def matches(cls, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        return host == _HOST

    def _build_body(self, page: int) -> dict:
        return {
            "query": "",
            "locale": "en-us",
            "page": page,
            "pageSize": _PAGE_SIZE,
            "sort": {"field": "postingDate", "order": "desc"},
            "filters": {},
        }

    def _extract_postings_array(
        self, payload: object, company: CompanyConfig,
    ) -> list:
        """Coalesce `results` (newer) and `searchResults` (older); validate.

        Raises SchemaDrift if neither key is present OR the value is not a
        list.
        """
        if not isinstance(payload, dict):
            raise SchemaDrift(
                f"Apple {company.name}: response is not a JSON object "
                f"(got {type(payload).__name__})"
            )
        array = payload.get("results")
        if array is None:
            array = payload.get("searchResults")
        if array is None:
            raise SchemaDrift(
                f"Apple {company.name}: response missing both 'results' and "
                f"'searchResults' keys (got: {list(payload.keys())})"
            )
        if not isinstance(array, list):
            raise SchemaDrift(
                f"Apple {company.name}: postings array is not a list "
                f"(got {type(array).__name__})"
            )
        return array

    @staticmethod
    def _extract_position_id(posting: dict) -> str | None:
        """Coalesce posting `positionId` / `id` (both observed in production).

        Returns None when both are missing/empty/whitespace — caller skips.
        """
        pid = posting.get("positionId") or posting.get("id")
        if pid is None:
            return None
        pid_str = str(pid).strip()
        return pid_str or None

    @staticmethod
    def _parse_posted_date_for_sanity(posting: dict) -> str | None:
        """Raw ISO string used ONLY by the D-04 sort-monotonicity check.

        ISO-8601 UTC strings lexically compare correctly, so we don't parse
        them to datetime here — that's normalizer's job.
        """
        return posting.get("postingDate") or posting.get("postDateInGMT")

    def fetch(
        self,
        company: CompanyConfig,
        seen_keys: set[str] | None = None,
    ) -> list[RawPosting]:
        """D-04 paginated fetch — newest-first with early-termination.

        Args:
          company: CompanyConfig with a `jobs.apple.com` URL (subpath ignored).
          seen_keys: optional set of dedup keys already in seen.json for Apple.
                     When provided, pagination early-terminates as soon as the
                     last posting on a page is already known. When None (the
                     Phase 1 Adapter.fetch signature), pagination still runs
                     to the 25-page cold-start cap.

        Raises:
          SchemaDrift: response body is not JSON, missing both
                       `results`/`searchResults` keys, or the array is not a
                       list.
          SiteBlocked: HTTP 403 / 429 / 5xx from any page.

        Notes (D-04 algorithm):
          1. Cold-start cap = _COLD_START_CAP_PAGES (25) — hard ceiling on the
             first scrape (no seen_keys overlap to trigger early-term).
          2. Empty-array break — source has returned all results.
          3. Short-page break — fewer than _PAGE_SIZE entries means EOF.
          4. Early-termination — last posting on page already in seen_keys.
          5. Sort-monotonicity sanity check — if page N+1's first posting is
             NEWER (by raw ISO postingDate, which lexically compares correctly
             for UTC) than page N's last, log WARNING and suppress
             early-termination for the rest of the run (degrade to cap-only).
          6. Inter-page sleep — random 0.5-1.5s jitter. Monkeypatched to noop
             in slow tests; production keeps it for rate-limit hedging.
        """
        seen_keys = seen_keys or set()
        result: list[RawPosting] = []
        prev_page_tail_date: str | None = None
        suppress_early_term = False

        for page_n in range(_COLD_START_CAP_PAGES):
            body = self._build_body(page_n)
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": _USER_AGENT,
            }
            try:
                response = httpx.post(
                    _API_URL, json=body, headers=headers, timeout=_TIMEOUT_S,
                )
            except httpx.HTTPError:
                # Per SEC-03 / Pitfall 17: never capture exception attrs that
                # might include request headers — orchestrator logs class+URL.
                raise

            if response.status_code in (403, 429):
                raise SiteBlocked(
                    f"Apple {company.name}: HTTP {response.status_code} "
                    f"from {_API_URL}"
                )
            if response.status_code >= 500:
                raise SiteBlocked(
                    f"Apple {company.name}: HTTP {response.status_code} "
                    f"(server error) from {_API_URL}"
                )
            response.raise_for_status()

            try:
                payload = response.json()
            except ValueError as e:
                raise SchemaDrift(
                    f"Apple {company.name}: response body is not JSON"
                ) from e

            postings_array = self._extract_postings_array(payload, company)

            if not postings_array:
                # Empty page — source has no more results.
                break

            # D-04 sort-monotonicity check (only meaningful from page 1+).
            # ISO-8601 UTC strings lexically compare correctly — no parse needed.
            if prev_page_tail_date is not None:
                first_dict = (
                    postings_array[0]
                    if isinstance(postings_array[0], dict)
                    else None
                )
                first_date = (
                    self._parse_posted_date_for_sanity(first_dict)
                    if first_dict is not None
                    else None
                )
                if (
                    first_date is not None
                    and first_date > prev_page_tail_date
                ):
                    if not suppress_early_term:
                        logger.warning(
                            "Apple %s: sort-monotonicity violation on page %d "
                            "(curr_first=%s newer than prev_last=%s) — Apple "
                            "ignored sort param; falling back to cold-start cap",
                            company.name, page_n,
                            first_date, prev_page_tail_date,
                        )
                    suppress_early_term = True

            page_keys_appended: list[str] = []
            for posting in postings_array:
                if not isinstance(posting, dict):
                    continue
                position_id = self._extract_position_id(posting)
                if position_id is None:
                    # Malformed entry — skip it without aborting the company
                    # (one-bad-posting isolation; mirrors Greenhouse/Workday).
                    continue
                dedup_key = f"apple:{position_id}"
                enriched = dict(posting)
                enriched["__dedup_key"] = dedup_key
                enriched["__position_id"] = position_id
                result.append(
                    RawPosting(
                        source_company=company.name,
                        source_adapter=self.name,
                        raw=enriched,
                    )
                )
                page_keys_appended.append(dedup_key)

            # Update sort-monotonicity tracker — last raw date on this page.
            last_dict = (
                postings_array[-1]
                if isinstance(postings_array[-1], dict)
                else None
            )
            prev_page_tail_date = (
                self._parse_posted_date_for_sanity(last_dict)
                if last_dict is not None
                else None
            )

            # D-04 early-termination: last appended key already in seen.json.
            # Suppressed if sort-monotonicity violation tripped.
            if (
                not suppress_early_term
                and page_keys_appended
                and page_keys_appended[-1] in seen_keys
            ):
                break

            # Short page = no more results.
            if len(postings_array) < _PAGE_SIZE:
                break

            # Brief inter-page sleep to reduce 429 risk on Apple. Tests
            # monkeypatch this to noop.
            if page_n + 1 < _COLD_START_CAP_PAGES:
                time.sleep(random.uniform(0.5, 1.5))

        return result


# Re-export pagination knobs so external callers + tests can import them
# without reaching into private module internals.
__all__ = [
    "AppleAdapter",
    "_COLD_START_CAP_PAGES",
    "_PAGE_SIZE",
    "_USER_AGENT",
    "_API_URL",
]
