"""Unit tests for src/registry.py.

Covers ADP-02 (URL-pattern dispatch, Greenhouse-only in Phase 1) and CFG-03
(explicit #adapter= hint overrides URL match).
"""
from __future__ import annotations

import pytest

from src.adapters.greenhouse import GreenhouseAdapter
from src.models import CompanyConfig
from src.registry import ADAPTERS, NoAdapterFound, get_adapter


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


def test_unknown_url_raises():
    c = CompanyConfig(name="x", url="https://unknown.example.com")
    with pytest.raises(NoAdapterFound):
        get_adapter(c)


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


def test_unrecognized_hint_no_url_match_raises():
    """Unrecognized hint AND non-matching URL → NoAdapterFound."""
    c = CompanyConfig(
        name="x",
        url="https://unknown.example.com",
        hint="future-ats-not-in-registry",
    )
    with pytest.raises(NoAdapterFound):
        get_adapter(c)


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
