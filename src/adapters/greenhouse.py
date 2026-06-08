"""Greenhouse public boards adapter.

Endpoint: https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true
Auth: none.
Per REQUIREMENTS.md ADP-03 and PITFALLS.md Pitfall 5: dedup key is `gh:<board_token>:<job_id>`
extracted from the ATS response — NEVER URL-based (URLs gain tracking params; IDs are stable).

Per CONTEXT.md D-07: Phase 1 only ships happy-path tests. SchemaDrift / SiteBlocked branches
exist in the code below; Phase 2 will add fixture-mutation tests that exercise them.
"""
from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

import httpx

from src.adapters.base import Adapter, SchemaDrift, SiteBlocked
from src.models import CompanyConfig, RawPosting

# Both hostnames are in production use at Stripe / others (2025-2026)
_GREENHOUSE_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io")

# Default HTTP timeout — generous because GitHub Actions runners hit ATS endpoints over
# the open internet and Greenhouse occasionally takes ~10s for large boards.
_TIMEOUT_S = 20.0


class GreenhouseAdapter(Adapter):
    """Adapter for Greenhouse public boards API."""

    name: ClassVar[str] = "greenhouse"

    @classmethod
    def matches(cls, url: str) -> bool:
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return False
        return host.lower() in _GREENHOUSE_HOSTS

    @staticmethod
    def _extract_board_token(url: str) -> str:
        """Extract the board token from a Greenhouse boards URL.

        Supported forms:
          https://boards.greenhouse.io/stripe          -> "stripe"
          https://boards.greenhouse.io/stripe/         -> "stripe"
          https://job-boards.greenhouse.io/stripe      -> "stripe"
          https://boards.greenhouse.io/stripe/jobs/123 -> "stripe"
        """
        parsed = urlparse(url)
        # First non-empty path segment is the board token.
        segments = [s for s in parsed.path.split("/") if s]
        if not segments:
            raise ValueError(f"Cannot extract Greenhouse board token from URL: {url}")
        return segments[0]

    def fetch(self, company: CompanyConfig) -> list[RawPosting]:
        board_token = self._extract_board_token(company.resolved_url or company.url)
        api_url = (
            f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        )

        try:
            response = httpx.get(api_url, timeout=_TIMEOUT_S)
        except httpx.HTTPError:
            # Network-layer failure — not blocked, not drift; let orchestrator's
            # per-company catch-all log it (ADP-12). Per SEC-03 / Pitfall 17, we
            # deliberately do NOT capture exception attributes that might include
            # request headers — the orchestrator logs only the exception type + URL.
            raise

        # Pitfall 5 / ADP-11 — distinguish blocked from empty.
        if response.status_code in (403, 429):
            raise SiteBlocked(
                f"Greenhouse {company.name}: HTTP {response.status_code} from {api_url}"
            )
        if response.status_code >= 500:
            raise SiteBlocked(
                f"Greenhouse {company.name}: HTTP {response.status_code} (server error) "
                f"from {api_url}"
            )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as e:
            raise SchemaDrift(
                f"Greenhouse {company.name}: response body is not JSON"
            ) from e

        # Pitfall 6 — schema assertion.
        if not isinstance(payload, dict) or "jobs" not in payload:
            got = (
                list(payload.keys())
                if isinstance(payload, dict)
                else type(payload).__name__
            )
            raise SchemaDrift(
                f"Greenhouse {company.name}: missing top-level 'jobs' key "
                f"(got keys: {got})"
            )
        if not isinstance(payload["jobs"], list):
            raise SchemaDrift(
                f"Greenhouse {company.name}: 'jobs' is not a list "
                f"(got {type(payload['jobs']).__name__})"
            )

        result: list[RawPosting] = []
        for job in payload["jobs"]:
            if not isinstance(job, dict) or "id" not in job:
                # Skip individual malformed entries rather than killing the whole company.
                continue
            # Stable dedup key per Pitfall 5 / ADP-03.
            dedup_key = f"gh:{board_token}:{job['id']}"
            # Stash the dedup_key inside raw so the normalizer reads it without re-computing.
            enriched = dict(job)
            enriched["__dedup_key"] = dedup_key
            enriched["__board_token"] = board_token
            result.append(
                RawPosting(
                    source_company=company.name,
                    source_adapter=self.name,
                    raw=enriched,
                )
            )

        return result
