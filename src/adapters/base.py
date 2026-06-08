"""Adapter ABC and typed exceptions.

Per REQUIREMENTS.md ADP-01: every adapter implements matches(url) -> bool and
fetch(company) -> list[RawPosting].

Per REQUIREMENTS.md ADP-11 + SEC-05: four typed exception classes are defined
here. SiteBlocked and SchemaDrift are raised by ATS adapters when distinguishing
"site blocked us" / "site changed shape" from "site has zero matching jobs".
PlaywrightTimeout is reserved for Phase 3. MissingCredential is reserved for
Phase 3 credentialed-scrape flow but defined now so the orchestrator's
per-company isolation (ADP-12) can route on it from day one.

Per CONTEXT.md D-07: Phase 1 only happy-path-tests these. The SchemaDrift /
SiteBlocked branches in greenhouse.py are coded but not exercised by Phase 1
unit tests — Phase 2 will add fixture-mutation tests for all adapters at once.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from src.models import CompanyConfig, RawPosting


class SiteBlocked(Exception):
    """Raised by an adapter when the source returned a block signal
    (HTTP 403, CAPTCHA HTML, response too short, rate-limit headers).

    Distinct from "zero results" — state_merger MUST NOT mark a company's
    postings as still_listed=False on a SiteBlocked outcome (PITFALLS.md Pitfall 5).
    """


class SchemaDrift(Exception):
    """Raised by an adapter when the source's response shape changed
    (missing top-level key, unexpected type, pydantic validation failure).

    Distinct from "site blocked us" — surfaces in health footer (Phase 4) so the
    user knows which adapter to repair.
    """


class PlaywrightTimeout(Exception):
    """Raised by Playwright fallback (Phase 3) on per-page navigation timeout.

    Defined here in Phase 1 so the orchestrator's catch-all can switch on it.
    Phase 1 Greenhouse adapter never raises this.
    """


class MissingCredential(Exception):
    """Raised by a credentialed adapter (Phase 3) when an expected
    `os.environ["SCRAPER_<COMPANY>_<KIND>"]` is unset.

    Per SEC-05: this is logged and isolated per-company; other companies in the
    same run continue to scan. Defined here so the orchestrator's per-company
    try/except has all error types in scope from day one.
    """


class InvalidCredential(Exception):
    """Raised by Playwright adapter (Phase 3 Plan 03-03) when login credentials
    are PRESENT in env vars (`SCRAPER_<COMPANY>_<KIND>`) but the login form
    rejects them — heuristic: form still visible after submit + brief wait.
    Distinct from MissingCredential (env var unset).

    Per SEC-03 / Pitfall 17 / CONTEXT.md D-02c: exception message includes
    COMPANY + URL only — NEVER credential values, NEVER response body, NEVER
    request headers. Orchestrator's per-company isolation (ADP-12) catches
    alongside MissingCredential and continues scanning other companies.
    """


class Adapter(ABC):
    """Abstract base for all scraping adapters.

    Subclasses set `name: ClassVar[str]` (e.g., "greenhouse", "lever") and
    implement `matches` + `fetch`. The registry uses `matches` for URL-pattern
    dispatch; the orchestrator calls `fetch` inside a per-company try/except.
    """

    name: ClassVar[str]

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        """Return True if this adapter handles this careers URL.

        Implementations should be cheap — substring or hostname match, no I/O.
        """

    @abstractmethod
    def fetch(self, company: CompanyConfig) -> list[RawPosting]:
        """Fetch the source's current postings.

        Per ADP-11, raise:
        - SiteBlocked for 403 / CAPTCHA / rate-limit-shaped responses
        - SchemaDrift when the expected top-level fields are absent / wrong type
        - generic Exception subclasses for transport / unknown failures
        """
