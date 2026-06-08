"""SmartRecruiters public postings adapter — ADP-06.

Endpoint: https://api.smartrecruiters.com/v1/companies/<company>/postings
Auth: none (public SR boards).

Per CONTEXT.md D-01a: a SR careers URL `https://careers.smartrecruiters.com/<company>`
resolves to identifier `<company>` (first non-empty path segment). The adapter calls the
public JSON API and emits dedup keys of the form `sr:<company>:<id>` where `<id>` is
SR's posting id — stable ID per PITFALLS.md Pitfall 5 (never URL-based).

**Naming split (deliberate, documented):**
  - Adapter.name = "smartrecruiters" — the full word; used as the dispatch key in
    `src/normalizer.py::_DISPATCH` and as `RawPosting.source_adapter`.
  - Dedup-key prefix = "sr:" — the SHORT form, per CONTEXT.md D-01a and
    `.planning/research/ARCHITECTURE.md` dedup-key conventions.
  These are intentionally different. `name` is the dispatch identifier, the prefix
  is the persistent on-disk format the user sees in `seen.json`. The test
  `test_fetch_emits_stable_dedup_key_with_sr_prefix` locks this into the suite.

Schema notes (per <adapter_specifications> in 02-01-PLAN.md):
- Top-level response is `{"content": [...], "totalFound": N}`. Missing or wrong-typed
  `content` → SchemaDrift.
- Each posting carries: `id`, `name` (SR's title field), `location.city`/`country`
  (either may be missing), `ref` (SR ATS-side URL, sometimes relative — normalizer
  prefixes `https://` defensively), `releasedDate` (ISO-8601),
  `jobAd.sections.jobDescription.text` (description).

Per CONTEXT.md D-03: this module ships happy + 4 error-path tests + dedup-key-split
regression + 2 matches() tests (see tests/test_smartrecruiters_adapter.py).
"""
from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

import httpx

from src.adapters.base import Adapter, SchemaDrift, SiteBlocked
from src.models import CompanyConfig, RawPosting

_HOST = "careers.smartrecruiters.com"
_TIMEOUT_S = 20.0


class SmartRecruitersAdapter(Adapter):
    """Adapter for SmartRecruiters public postings JSON API."""

    name: ClassVar[str] = "smartrecruiters"

    @classmethod
    def matches(cls, url: str) -> bool:
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return False
        return host.lower() == _HOST

    @staticmethod
    def _extract_identifier(url: str) -> str:
        """Extract the SR company identifier from a careers URL.

        Supported forms:
          https://careers.smartrecruiters.com/notion             -> "notion"
          https://careers.smartrecruiters.com/notion/            -> "notion"
          https://careers.smartrecruiters.com/notion/posting-id  -> "notion"
        """
        parsed = urlparse(url)
        segments = [s for s in parsed.path.split("/") if s]
        if not segments:
            raise ValueError(
                f"Cannot extract SmartRecruiters identifier from URL: {url}"
            )
        return segments[0]

    def fetch(self, company: CompanyConfig) -> list[RawPosting]:
        identifier = self._extract_identifier(company.resolved_url or company.url)
        api_url = (
            f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings"
        )

        try:
            response = httpx.get(api_url, timeout=_TIMEOUT_S)
        except httpx.HTTPError:
            raise

        # Pitfall 5 / ADP-11 — distinguish blocked from empty.
        if response.status_code in (403, 429):
            raise SiteBlocked(
                f"SmartRecruiters {company.name}: HTTP {response.status_code} "
                f"from {api_url}"
            )
        if response.status_code >= 500:
            raise SiteBlocked(
                f"SmartRecruiters {company.name}: HTTP {response.status_code} "
                f"(server error) from {api_url}"
            )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as e:
            raise SchemaDrift(
                f"SmartRecruiters {company.name}: response body is not JSON"
            ) from e

        # Pitfall 6 — top-level shape assertion. SR returns {"content": [...]}.
        if not isinstance(payload, dict) or "content" not in payload:
            got = (
                list(payload.keys())
                if isinstance(payload, dict)
                else type(payload).__name__
            )
            raise SchemaDrift(
                f"SmartRecruiters {company.name}: missing top-level 'content' key "
                f"(got: {got})"
            )
        if not isinstance(payload["content"], list):
            raise SchemaDrift(
                f"SmartRecruiters {company.name}: 'content' is not a list "
                f"(got {type(payload['content']).__name__})"
            )

        result: list[RawPosting] = []
        for posting in payload["content"]:
            if not isinstance(posting, dict) or "id" not in posting:
                continue
            # NB: SHORT prefix "sr:" per CONTEXT.md D-01a — NOT "smartrecruiters:".
            dedup_key = f"sr:{identifier}:{posting['id']}"
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
