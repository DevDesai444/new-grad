"""Unit tests for src/filter.py.

Covers FILT-01..06: title-keyword include/exclude logic, experience_min ceiling,
FILT-05 ambiguous-bias-toward-inclusion. Pure function — no I/O, no datetime.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.filter import is_early_career
from src.models import Posting

_NOW = datetime(2026, 6, 7, 14, 0, 0, tzinfo=UTC)


def _make_posting(title: str, **overrides) -> Posting:
    return Posting(
        dedup_key=overrides.get("dedup_key", "gh:x:1"),
        company="X",
        title=title,
        location="",
        salary=None,
        experience_min=overrides.get("experience_min", None),
        experience_max=overrides.get("experience_max", None),
        posting_url="https://x/jobs/1",
        posted_date=None,
        first_seen=_NOW,
        last_seen=_NOW,
        still_listed=True,
        source_adapter="greenhouse",
    )


# --- title gate: parametrized over the canonical case-list ---------------------

@pytest.mark.parametrize(
    "title,expected",
    [
        # Positive (FILT-01)
        ("Software Engineer, New Grad", True),
        ("New Grad Software Engineer", True),
        ("Junior Backend Developer", True),
        ("Associate Software Engineer", True),
        ("Entry-Level Data Scientist", True),
        ("Early Career Analyst", True),
        ("University Recruiting — Software Engineer", True),
        ("Recent Graduate Engineer", True),
        ("SDE I", True),
        ("Software Engineer I", True),
        ("Class of 2026 Software Engineer", True),
        # Negative (FILT-02)
        ("Senior Staff Engineer", False),
        ("Sr. Backend Developer", False),
        ("Staff Engineer", False),
        ("Principal Architect", False),
        ("Engineering Manager", False),
        ("Director of Engineering", False),
        ("Head of Platform", False),
        ("Software Engineer II", False),
        ("Software Engineer III", False),
        ("Software Engineer 2", False),
        ("Software Engineer 5", False),
        # Conflict — exclude wins
        ("Engineering Manager, New Grad Programs", False),
        # FILT-05 ambiguous -> include (bias toward inclusion)
        ("Backend Developer", True),
        ("Software Engineer", True),
    ],
)
def test_title_gate(title, expected):
    p = _make_posting(title)
    assert is_early_career(p) is expected, f"{title!r} expected {expected}"


# --- FILT-04: experience ceiling -----------------------------------------------

def test_experience_min_above_ceiling_overrides_title_pass():
    """Even with a `New Grad` title, experience_min > 5 rejects (FILT-04)."""
    p = _make_posting("New Grad SWE", experience_min=7)
    assert is_early_career(p) is False


def test_experience_min_at_ceiling_allows():
    """experience_min == 5 is allowed (ceiling is <=5 inclusive)."""
    p = _make_posting("Backend Developer", experience_min=5)
    assert is_early_career(p) is True


def test_experience_min_below_ceiling_allows():
    p = _make_posting("Backend Developer", experience_min=3)
    assert is_early_career(p) is True


def test_experience_min_none_allows_ambiguous_title():
    """FILT-05: ambiguous title + no experience signal -> include."""
    p = _make_posting("Backend Developer", experience_min=None)
    assert is_early_career(p) is True


# --- Purity sanity --------------------------------------------------------------

def test_is_early_career_is_deterministic():
    p = _make_posting("Backend Developer")
    a = is_early_career(p)
    b = is_early_career(p)
    assert a is b


def test_is_early_career_returns_bool():
    p = _make_posting("Backend Developer")
    result = is_early_career(p)
    assert isinstance(result, bool)
