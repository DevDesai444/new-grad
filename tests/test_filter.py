"""Unit tests for src/filter.py.

Covers:
- FILT-01..02: title-keyword include/exclude logic.
- FILT-05: ambiguous-title bias toward inclusion.
- FILT-06: pure function (no I/O, no datetime).
- FILT-03: JD-scan extract_experience_range — Phase 2 Plan 02-03.
- Phase 2 D-02 invariant: is_early_career is TITLE-ONLY; experience_min is
  display-only and does NOT gate inclusion (REQUIREMENTS.md FILT-04 was
  softened per .planning/phases/02-ats-breadth-jd-scan/02-CONTEXT.md D-02).
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.filter import extract_experience_range, is_early_career
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


# --- Phase 2 D-02: experience_min is DISPLAY-ONLY (does NOT gate inclusion) ---


def test_is_early_career_ignores_experience_min_per_d02():
    """D-02 invariant: title-pass posting with experience_min=7 is STILL kept.

    Phase 1 rejected this case (FILT-04 ceiling). Phase 2 D-02 softens that:
    the JD-scan output populates Posting.experience_min/max for display in
    the Experience column, but is_early_career uses the title gate alone.
    See REQUIREMENTS.md FILT-04 strikethrough + footnote pointing to
    .planning/phases/02-ats-breadth-jd-scan/02-CONTEXT.md D-02.
    """
    p = _make_posting("New Grad SWE", experience_min=7)
    assert is_early_career(p) is True


def test_is_early_career_does_not_depend_on_experience_min_at_ceiling():
    p = _make_posting("Backend Developer", experience_min=5)
    assert is_early_career(p) is True


def test_is_early_career_does_not_depend_on_experience_min_below_ceiling():
    p = _make_posting("Backend Developer", experience_min=3)
    assert is_early_career(p) is True


def test_experience_min_none_allows_ambiguous_title():
    """FILT-05: ambiguous title + no experience signal -> include."""
    p = _make_posting("Backend Developer", experience_min=None)
    assert is_early_career(p) is True


def test_is_early_career_excludes_senior_regardless_of_experience_min():
    """Title exclude still wins even when experience_min looks junior."""
    p = _make_posting("Senior Engineer", experience_min=0)
    assert is_early_career(p) is False


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


# --- FILT-03: extract_experience_range (Plan 02-03) ---------------------------


def test_extract_empty_string():
    assert extract_experience_range("") == (None, None)


def test_extract_none():
    """Defensive: function accepts None even though type hint is str | None."""
    assert extract_experience_range(None) == (None, None)


def test_extract_numeric_range_dash():
    assert extract_experience_range("0-3 years of experience") == (0, 3)


def test_extract_numeric_range_to():
    assert extract_experience_range("3 to 5 years required") == (3, 5)


def test_extract_numeric_range_en_dash():
    assert extract_experience_range("5–7 years experience") == (5, 7)


def test_extract_numeric_range_em_dash():
    assert extract_experience_range("5—7 years experience") == (5, 7)


def test_extract_open_min():
    assert extract_experience_range("5+ years required") == (5, None)


def test_extract_open_min_two_digits():
    assert extract_experience_range("10+ years of relevant experience") == (
        10, None,
    )


def test_extract_entry_level():
    assert extract_experience_range("Entry-level role for new graduates") == (
        0, None,
    )


def test_extract_entry_level_no_hyphen():
    assert extract_experience_range("This is an entry level position") == (
        0, None,
    )


def test_extract_recent_graduate():
    assert extract_experience_range(
        "Recent graduate or equivalent encouraged",
    ) == (0, None)


def test_extract_no_experience_required():
    assert extract_experience_range("No experience required") == (0, None)


def test_extract_new_grad():
    assert extract_experience_range("New grad SWE position") == (0, None)


def test_extract_new_graduate_variant():
    assert extract_experience_range("New graduate program") == (0, None)


def test_extract_no_match_year_without_years_keyword():
    """Year mention without `years` suffix does NOT match (T-02-03-07 mitigation)."""
    assert extract_experience_range("Founded in 2010 by veterans") == (
        None, None,
    )


def test_extract_no_match_unrelated_text():
    assert extract_experience_range(
        "Join our team in beautiful San Francisco",
    ) == (None, None)


def test_extract_range_takes_precedence_over_open_min():
    """Numeric range is most specific — wins over `X+ years` if both present."""
    assert extract_experience_range(
        "5-7 years; alternatively 3+ years with bootcamp",
    ) == (5, 7)


def test_extract_open_min_takes_precedence_over_entry():
    """Open-min wins over entry signal if both present."""
    assert extract_experience_range(
        "5+ years preferred. Entry-level applicants also considered.",
    ) == (5, None)


def test_extract_truncation_caps_at_5000_chars():
    """Cap to 5000 chars; `5+ years` past the cap should NOT match.

    Mitigates T-02-03-03 (regex catastrophic backtracking on huge HTML).
    """
    huge = ("X" * 100_000) + " 5+ years"
    assert extract_experience_range(huge) == (None, None)


def test_extract_within_truncation_window_still_matches():
    """A signal at position 4999 (within the cap) still matches."""
    prefix = "X" * 4900
    assert extract_experience_range(prefix + " 0-3 years experience") == (0, 3)
