"""Unit tests for src/registry.py.

Covers ADP-02 (URL-pattern dispatch, Greenhouse-only in Phase 1) and CFG-03
(explicit #adapter= hint overrides URL match).
"""
from __future__ import annotations

from src.adapters.greenhouse import GreenhouseAdapter
from src.models import CompanyConfig
from src.registry import ADAPTERS, get_adapter


def test_greenhouse_in_adapters_list():
    assert GreenhouseAdapter in ADAPTERS


def test_get_adapter_for_greenhouse_url():
    c = CompanyConfig(name="stripe", url="https://boards.greenhouse.io/stripe")
    a = get_adapter(c)
    assert isinstance(a, GreenhouseAdapter)


def test_get_adapter_for_job_boards_greenhouse_url():
    c = CompanyConfig(name="stripe", url="https://job-boards.greenhouse.io/stripe")
    a = get_adapter(c)
    assert isinstance(a, GreenhouseAdapter)


def test_unknown_http_url_dispatches_to_playwright_catch_all():
    """Phase 3 Plan 03-02 — PlaywrightAdapter is now the http(s) catch-all,
    so http(s) URLs that no specific adapter recognizes route to it instead
    of raising NoAdapterFound. Replaces the Phase 1 `test_unknown_url_raises`
    assertion (NoAdapterFound for any unknown URL) per CONTEXT.md D-01c.
    """
    from src.adapters.playwright_fallback import PlaywrightAdapter

    c = CompanyConfig(name="x", url="https://unknown.example.com")
    a = get_adapter(c)
    assert isinstance(a, PlaywrightAdapter)


def test_hint_overrides_url_match():
    """CFG-03 — `#adapter=greenhouse` routes a non-matching URL to Greenhouse."""
    c = CompanyConfig(
        name="x", url="https://unknown.example.com", hint="greenhouse"
    )
    a = get_adapter(c)
    assert isinstance(a, GreenhouseAdapter)


def test_hint_with_colon_metadata_still_resolves():
    """Hint syntax allows `name:metadata` (e.g. `workday:tenant=foo`)."""
    c = CompanyConfig(
        name="x",
        url="https://unknown.example.com",
        hint="greenhouse:something=extra",
    )
    a = get_adapter(c)
    assert isinstance(a, GreenhouseAdapter)


def test_unrecognized_hint_falls_back_to_url_match():
    """Hint that doesn't match any adapter → fall through to URL match."""
    c = CompanyConfig(
        name="stripe",
        url="https://boards.greenhouse.io/stripe",
        hint="future-ats-not-in-registry",
    )
    a = get_adapter(c)
    assert isinstance(a, GreenhouseAdapter)


def test_unrecognized_hint_no_url_match_dispatches_to_playwright():
    """Phase 3 Plan 03-02 — unrecognized hint falls through to URL match;
    any http(s) URL now hits the PlaywrightAdapter catch-all. Replaces the
    Phase 1 NoAdapterFound assertion per CONTEXT.md D-01c.
    """
    from src.adapters.playwright_fallback import PlaywrightAdapter

    c = CompanyConfig(
        name="x",
        url="https://unknown.example.com",
        hint="future-ats-not-in-registry",
    )
    a = get_adapter(c)
    assert isinstance(a, PlaywrightAdapter)


# --- Phase 3 Plan 03-01 — resolved_url dispatch (CONTEXT.md D-01b) ------------


def test_get_adapter_uses_resolved_url_when_set():
    """D-01b — CNAME→Workday case: company.url is a generic CNAME that no
    adapter matches; company.resolved_url is the canonical Workday tenant URL.
    Registry must dispatch on the resolved URL, returning WorkdayAdapter.
    """
    from src.adapters.workday import WorkdayAdapter

    c = CompanyConfig(
        name="amd",
        url="https://careers.amd.com/",
        resolved_url="https://amd.wd1.myworkdayjobs.com/External",
    )
    a = get_adapter(c)
    assert isinstance(a, WorkdayAdapter)


def test_get_adapter_falls_back_to_url_when_resolved_url_none():
    """Phase 1/2 semantics preserved — when resolved_url is None, dispatch
    uses company.url unchanged. Greenhouse URL still resolves to Greenhouse.
    """
    c = CompanyConfig(
        name="stripe",
        url="https://boards.greenhouse.io/stripe",
        resolved_url=None,
    )
    a = get_adapter(c)
    assert isinstance(a, GreenhouseAdapter)


def test_get_adapter_explicit_hint_overrides_resolved_url():
    """CFG-03 hint precedence holds — explicit hint wins over resolved_url
    match. Even if resolved_url would dispatch to Workday, a `greenhouse`
    hint routes to GreenhouseAdapter.
    """
    c = CompanyConfig(
        name="weirdco",
        url="https://careers.weirdco.com/",
        hint="greenhouse",
        resolved_url="https://weirdco.wd1.myworkdayjobs.com/External",
    )
    a = get_adapter(c)
    assert isinstance(a, GreenhouseAdapter)


# --- Phase 3 Plan 03-02 — Playwright catch-all (D-01c) ----------------------


def test_playwright_adapter_is_last_in_list():
    """D-01c — catch-all MUST be the LAST entry in ADAPTERS so all specific
    adapters' matches() get first crack.
    """
    assert ADAPTERS[-1].name == "playwright"


def test_playwright_dispatches_only_when_no_other_matches():
    """An arbitrary http(s) URL with no specific ATS match → PlaywrightAdapter."""
    from src.adapters.playwright_fallback import PlaywrightAdapter

    c = CompanyConfig(
        name="anthropic", url="https://www.anthropic.com/careers",
    )
    a = get_adapter(c)
    assert isinstance(a, PlaywrightAdapter)


def test_greenhouse_url_still_dispatches_to_greenhouse_not_playwright():
    """Specific adapter wins over catch-all (D-01c ordering invariant)."""
    from src.adapters.playwright_fallback import PlaywrightAdapter

    c = CompanyConfig(name="stripe", url="https://boards.greenhouse.io/stripe")
    a = get_adapter(c)
    assert isinstance(a, GreenhouseAdapter)
    assert not isinstance(a, PlaywrightAdapter)


def test_workday_resolved_url_still_dispatches_to_workday_not_playwright():
    """CNAME→Workday via resolved_url still wins over catch-all Playwright."""
    from src.adapters.playwright_fallback import PlaywrightAdapter
    from src.adapters.workday import WorkdayAdapter

    c = CompanyConfig(
        name="amd",
        url="https://careers.amd.com/",
        resolved_url="https://amd.wd1.myworkdayjobs.com/External",
    )
    a = get_adapter(c)
    assert isinstance(a, WorkdayAdapter)
    assert not isinstance(a, PlaywrightAdapter)


def test_no_adapter_found_eliminated_by_catch_all():
    """With PlaywrightAdapter as catch-all, NoAdapterFound is no longer raised
    for any http(s) URL. The Phase 1 NoAdapterFound contract still holds for
    non-http schemes (the catch-all matches http/https only).
    """
    from src.adapters.playwright_fallback import PlaywrightAdapter

    c = CompanyConfig(name="some", url="https://random-unknown.example/jobs")
    a = get_adapter(c)
    assert isinstance(a, PlaywrightAdapter)
