"""URL-pattern adapter registry (ADP-02 + CFG-03).

Phase 1 ships only the Greenhouse adapter (CONTEXT.md D-05). Unknown URLs raise
NoAdapterFound; the orchestrator (Plan 03's main.py) catches and skips them per
CFG-05.

ADP-14 / ADP-15 — adding a new ATS = appending one entry to ADAPTERS. No other
code changes required (open/closed principle).
"""
from __future__ import annotations

from src.adapters.apple import AppleAdapter
from src.adapters.ashby import AshbyAdapter
from src.adapters.base import Adapter
from src.adapters.greenhouse import GreenhouseAdapter
from src.adapters.lever import LeverAdapter
from src.adapters.playwright_fallback import PlaywrightAdapter
from src.adapters.smartrecruiters import SmartRecruitersAdapter
from src.adapters.workday import WorkdayAdapter
from src.models import CompanyConfig


class NoAdapterFound(Exception):
    """Raised by get_adapter when no adapter matches and no fallback exists.

    Phase 1's orchestrator (Plan 03) catches this per-company and logs+skips
    (CFG-05). The run continues for other companies. As of Phase 3 Plan 03-02
    the PlaywrightAdapter catch-all matches any http(s) URL, so this exception
    only fires for malformed configs (e.g., non-http schemes that slip past
    CompanyConfig's url validator — defensive).
    """


# ADAPTERS is the ONLY list to mutate when adding a new ATS.
# Phase 2 Plan 02-01: LeverAdapter, AshbyAdapter, SmartRecruitersAdapter
# Phase 2 Plan 02-02: WorkdayAdapter
# Phase 2 Plan 02-03: AppleAdapter
# Phase 3 Plan 03-02: PlaywrightAdapter (catch-all — MUST be last per D-01c)
ADAPTERS: list[type[Adapter]] = [
    GreenhouseAdapter,
    LeverAdapter,
    AshbyAdapter,
    SmartRecruitersAdapter,
    WorkdayAdapter,
    AppleAdapter,
    PlaywrightAdapter,  # CATCH-ALL — must stay last per CONTEXT.md D-01c
]


def get_adapter(company: CompanyConfig) -> Adapter:
    """Return an Adapter instance for the given company.

    Resolution order (Plan 03-01 update — CONTEXT.md D-01b):
    1. Explicit `#adapter=<name>` hint on the companies.txt line wins (CFG-03).
       Hint value may be a bare name or "name:metadata" (the metadata after `:`
       is reserved for adapter-specific routing like `workday:tenant=foo`).
    2. Else URL-pattern match via Adapter.matches() against
       `company.resolved_url or company.url`. The orchestrator populates
       `resolved_url` via url_resolver.resolve_url() once per company per run,
       which unblocks the CNAME→Workday case (e.g., careers.amd.com →
       amd.wd1.myworkdayjobs.com).
    3. Else raise NoAdapterFound (Phase 3 Wave 2 appends PlaywrightAdapter
       as the catch-all, eliminating this branch for http(s) URLs).
    """
    if company.hint:
        hint_name = company.hint.split(":", 1)[0].strip().lower()
        for cls in ADAPTERS:
            if cls.name == hint_name:
                return cls()
        # Hint present but no match — fall through to URL match (defensive: a typo
        # or future-ATS hint should not prevent a recognizable URL from routing).

    # Plan 03-01: prefer resolved_url (set by orchestrator after resolve_url())
    # so CNAME→Workday URLs land on WorkdayAdapter instead of falling through.
    effective_url = company.resolved_url or company.url
    for cls in ADAPTERS:
        if cls.matches(effective_url):
            return cls()

    raise NoAdapterFound(
        f"No adapter matches url={company.url!r} "
        f"(resolved={company.resolved_url!r}) for company={company.name!r}. "
        "Phase 3 Wave 2 will add a Playwright catch-all."
    )
