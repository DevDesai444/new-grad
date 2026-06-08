"""Ashby public job-board adapter — ADP-05.

Endpoint: https://api.ashbyhq.com/posting-api/job-board/<org>?includeCompensation=true
Auth: none (public Ashby job boards).

Per CONTEXT.md D-01a: an Ashby careers URL `https://jobs.ashbyhq.com/<org>` resolves to
identifier `<org>` (first non-empty path segment). The adapter calls the public JSON API
and emits dedup keys of the form `ashby:<org>:<uuid>` where `<uuid>` is Ashby's posting
`id` — stable ID per PITFALLS.md Pitfall 5 (never URL-based).

Schema notes (per <adapter_specifications> in 02-01-PLAN.md):
- Top-level response is `{"jobs": [...]}`. Missing or wrong-typed `jobs` → SchemaDrift.
- Each job carries: `id` (uuid), `title`, `locationName` OR `location.name` (per-tenant
  variance — normalizer coalesces), `jobUrl`, `publishedAt` (ISO-8601 with offset),
  `descriptionPlain` (HTML fallback: `descriptionHtml`).

Per CONTEXT.md D-03: this module ships happy + 4 error-path tests + 2 matches() tests
+ stable-dedup-key test (see tests/test_ashby_adapter.py).
"""
from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

import httpx

from src.adapters.base import Adapter, SchemaDrift, SiteBlocked
from src.models import CompanyConfig, RawPosting

_HOST = "jobs.ashbyhq.com"
_TIMEOUT_S = 20.0


class AshbyAdapter(Adapter):
    """Adapter for Ashby public job-board JSON API."""

    name: ClassVar[str] = "ashby"

    @classmethod
    def matches(cls, url: str) -> bool:
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return False
        return host.lower() == _HOST

    @staticmethod
    def _extract_identifier(url: str) -> str:
        """Extract the Ashby org identifier from a careers URL.

        Supported forms:
          https://jobs.ashbyhq.com/notion         -> "notion"
          https://jobs.ashbyhq.com/notion/        -> "notion"
          https://jobs.ashbyhq.com/notion/abc-id  -> "notion"
        """
        parsed = urlparse(url)
        segments = [s for s in parsed.path.split("/") if s]
        if not segments:
            raise ValueError(f"Cannot extract Ashby identifier from URL: {url}")
        return segments[0]

    def fetch(self, company: CompanyConfig) -> list[RawPosting]:
        identifier = self._extract_identifier(company.resolved_url or company.url)
        api_url = (
            f"https://api.ashbyhq.com/posting-api/job-board/{identifier}"
            f"?includeCompensation=true"
        )

        try:
            response = httpx.get(api_url, timeout=_TIMEOUT_S)
        except httpx.HTTPError:
            raise

        # Pitfall 5 / ADP-11 — distinguish blocked from empty.
        if response.status_code in (403, 429):
            raise SiteBlocked(
                f"Ashby {company.name}: HTTP {response.status_code} from {api_url}"
            )
        if response.status_code >= 500:
            raise SiteBlocked(
                f"Ashby {company.name}: HTTP {response.status_code} (server error) "
                f"from {api_url}"
            )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as e:
            raise SchemaDrift(
                f"Ashby {company.name}: response body is not JSON"
            ) from e

        # Pitfall 6 — top-level shape assertion. Ashby returns {"jobs": [...]}.
        if not isinstance(payload, dict) or "jobs" not in payload:
            got = (
                list(payload.keys())
                if isinstance(payload, dict)
                else type(payload).__name__
            )
            raise SchemaDrift(
                f"Ashby {company.name}: missing top-level 'jobs' key (got: {got})"
            )
        if not isinstance(payload["jobs"], list):
            raise SchemaDrift(
                f"Ashby {company.name}: 'jobs' is not a list "
                f"(got {type(payload['jobs']).__name__})"
            )

        result: list[RawPosting] = []
        for job in payload["jobs"]:
            if not isinstance(job, dict) or "id" not in job:
                continue
            dedup_key = f"ashby:{identifier}:{job['id']}"
            enriched = dict(job)
            enriched["__dedup_key"] = dedup_key
            enriched["__identifier"] = identifier
            result.append(
                RawPosting(
                    source_company=company.name,
                    source_adapter=self.name,
                    raw=enriched,
                )
            )

        return result
