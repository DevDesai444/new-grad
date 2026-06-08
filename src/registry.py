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
from src.adapters.smartrecruiters import SmartRecruitersAdapter
from src.adapters.workday import WorkdayAdapter
from src.models import CompanyConfig


class NoAdapterFound(Exception):
    """Raised by get_adapter when no adapter matches and no fallback exists.

    Phase 1's orchestrator (Plan 03) catches this per-company and logs+skips
    (CFG-05). The run continues for other companies. Phase 3 will add a
    Playwright catch-all that takes precedence over this error path.
    """


# ADAPTERS is the ONLY list to mutate when adding a new ATS.
# Phase 2 Plan 02-01: LeverAdapter, AshbyAdapter, SmartRecruitersAdapter
# Phase 2 Plan 02-02: WorkdayAdapter
# Phase 2 Plan 02-03: AppleAdapter
# Phase 3 will append: PlaywrightAdapter (always last — catch-all)
ADAPTERS: list[type[Adapter]] = [
    GreenhouseAdapter,
    LeverAdapter,
    AshbyAdapter,
    SmartRecruitersAdapter,
    WorkdayAdapter,
    AppleAdapter,
]


def get_adapter(company: CompanyConfig) -> Adapter:
    """Return an Adapter instance for the given company.

    Resolution order:
    1. Explicit `#adapter=<name>` hint on the companies.txt line wins (CFG-03).
       Hint value may be a bare name or "name:metadata" (the metadata after `:`
       is reserved for adapter-specific routing like `workday:tenant=foo`).
    2. Else URL-pattern match via Adapter.matches(); first hit wins.
    3. Else raise NoAdapterFound.
    """
    if company.hint:
        hint_name = company.hint.split(":", 1)[0].strip().lower()
        for cls in ADAPTERS:
            if cls.name == hint_name:
                return cls()
        # Hint present but no match — fall through to URL match (defensive: a typo
        # or future-ATS hint should not prevent a recognizable URL from routing).

    for cls in ADAPTERS:
        if cls.matches(company.url):
            return cls()

    raise NoAdapterFound(
        f"No adapter matches url={company.url!r} for company={company.name!r}. "
        "Phase 1 only supports Greenhouse; other ATSes land in Phase 2."
    )
