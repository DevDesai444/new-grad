"""Lever public postings adapter — ADP-04.

Endpoint: https://api.lever.co/v0/postings/<company>?mode=json
Auth: none (public Lever boards).

Per CONTEXT.md D-01a: a Lever careers URL `https://jobs.lever.co/<company>` resolves to
identifier `<company>` (first non-empty path segment). The adapter calls the public JSON
API and emits dedup keys of the form `lever:<company>:<uuid>` where `<uuid>` is Lever's
posting `id` — stable ID per PITFALLS.md Pitfall 5 (never URL-based).

Schema notes (per <adapter_specifications> in 02-01-PLAN.md):
- Top-level response is a JSON **array** of posting dicts (NOT a dict). A dict at the
  top level is treated as SchemaDrift.
- Each posting carries: `id` (uuid), `text` (title), `categories.location`, `hostedUrl`,
  `createdAt` (epoch ms), `descriptionPlain` (HTML fallback: `description`).

Per CONTEXT.md D-03 (closes part of D-07 debt): this module ships happy + 5 error-path
tests + 2 matches() tests (see tests/test_lever_adapter.py).
"""
from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

import httpx

from src.adapters.base import Adapter, SchemaDrift, SiteBlocked
from src.models import CompanyConfig, RawPosting

_HOST = "jobs.lever.co"
_TIMEOUT_S = 20.0


class LeverAdapter(Adapter):
    """Adapter for Lever public postings JSON API."""

    name: ClassVar[str] = "lever"

    @classmethod
    def matches(cls, url: str) -> bool:
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return False
        return host.lower() == _HOST

    @staticmethod
    def _extract_identifier(url: str) -> str:
        """Extract the Lever company identifier from a careers URL.

        Supported forms:
          https://jobs.lever.co/notion              -> "notion"
          https://jobs.lever.co/notion/             -> "notion"
          https://jobs.lever.co/notion/abc-uuid     -> "notion"
        """
        parsed = urlparse(url)
        segments = [s for s in parsed.path.split("/") if s]
        if not segments:
            raise ValueError(f"Cannot extract Lever identifier from URL: {url}")
        return segments[0]

    def fetch(self, company: CompanyConfig) -> list[RawPosting]:
        identifier = self._extract_identifier(company.resolved_url or company.url)
        api_url = f"https://api.lever.co/v0/postings/{identifier}?mode=json"

        try:
            response = httpx.get(api_url, timeout=_TIMEOUT_S)
        except httpx.HTTPError:
            # Per SEC-03 / Pitfall 17: do not capture request headers — let the
            # orchestrator's per-company except-Exception log type+URL only.
            raise

        # Pitfall 5 / ADP-11 — distinguish blocked from empty.
        if response.status_code in (403, 429):
            raise SiteBlocked(
                f"Lever {company.name}: HTTP {response.status_code} from {api_url}"
            )
        if response.status_code >= 500:
            raise SiteBlocked(
                f"Lever {company.name}: HTTP {response.status_code} (server error) "
                f"from {api_url}"
            )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as e:
            raise SchemaDrift(
                f"Lever {company.name}: response body is not JSON"
            ) from e

        # Pitfall 6 — top-level type assertion. Lever returns a LIST, not a dict.
        if not isinstance(payload, list):
            raise SchemaDrift(
                f"Lever {company.name}: response is not a JSON list "
                f"(got {type(payload).__name__})"
            )

        result: list[RawPosting] = []
        for posting in payload:
            if not isinstance(posting, dict) or "id" not in posting:
                # Skip individual malformed entries rather than killing the whole company.
                continue
            dedup_key = f"lever:{identifier}:{posting['id']}"
            enriched = dict(posting)
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
