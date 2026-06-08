"""Unit tests for src/renderer.py.

Covers OUT-01..08 and NORM-07/Pitfall 13 (Markdown escaping).

The OUT-07 idempotency test is mandatory: render_readme twice with same input
must produce byte-identical output.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.renderer import (
    EMPTY_PLACEHOLDER,
    SENTINEL_BEGIN,
    SENTINEL_END,
    _format_experience,
    escape_markdown_cell,
    format_age,
    render_readme,
)

_RUN = datetime(2026, 6, 7, 14, 0, 0, tzinfo=UTC)


# --- escape_markdown_cell (NORM-07 / Pitfall 13) -------------------------------

def test_escape_pipe():
    assert escape_markdown_cell("a | b") == "a \\| b"


def test_escape_newline_to_space():
    assert escape_markdown_cell("line1\nline2") == "line1 line2"


def test_escape_carriage_return_to_space():
    assert escape_markdown_cell("line1\r\nline2") == "line1 line2"


def test_escape_strips_zero_width_space():
    assert escape_markdown_cell("New​Grad") == "NewGrad"


def test_escape_strips_zwnj_zwj_bom_wj():
    assert escape_markdown_cell("a‌b‍c﻿d⁠e") == "abcde"


def test_escape_nbsp_to_space():
    assert escape_markdown_cell("Remote (US)") == "Remote (US)"


def test_escape_empty_and_none():
    assert escape_markdown_cell("") == ""
    assert escape_markdown_cell(None) == ""


def test_escape_collapses_whitespace():
    assert escape_markdown_cell("  multiple   spaces  ") == "multiple spaces"


def test_escape_tab_to_space():
    assert escape_markdown_cell("a\tb") == "a b"


# --- format_age (OUT-04) -------------------------------------------------------

def test_format_age_minutes():
    ref = _RUN - timedelta(minutes=30)
    assert format_age(ref, _RUN) == "30m"


def test_format_age_hours():
    ref = _RUN - timedelta(hours=3)
    assert format_age(ref, _RUN) == "3h"


def test_format_age_days():
    ref = _RUN - timedelta(days=2)
    assert format_age(ref, _RUN) == "2d"


def test_format_age_weeks():
    ref = _RUN - timedelta(weeks=3)
    assert format_age(ref, _RUN) == "3w"


def test_format_age_months():
    ref = _RUN - timedelta(days=90)  # 3 months
    assert format_age(ref, _RUN) == "3mo"


def test_format_age_years():
    ref = _RUN - timedelta(days=400)
    assert format_age(ref, _RUN) == "1y"


def test_format_age_none_returns_empty():
    assert format_age(None, _RUN) == ""


def test_format_age_now_under_one_minute():
    ref = _RUN - timedelta(seconds=30)
    assert format_age(ref, _RUN) == "now"


def test_format_age_future_clamped():
    """Defensive: future-dated postings should not produce negative durations."""
    ref = _RUN + timedelta(hours=4)
    result = format_age(ref, _RUN)
    assert result in ("now", "0m")


def test_format_age_naive_input_assumed_utc():
    """A naive datetime is treated as UTC (defensive)."""
    ref_naive = datetime(2026, 6, 7, 11, 0, 0)  # 3h before naive run
    run_naive = datetime(2026, 6, 7, 14, 0, 0)
    assert format_age(ref_naive, run_naive) == "3h"


# --- _format_experience (OUT-05) ----------------------------------------------

def test_format_experience_blank():
    assert _format_experience(None, None) == ""


def test_format_experience_range():
    assert _format_experience(0, 5) == "0y-5y"


def test_format_experience_max_only():
    assert _format_experience(None, 3) == "<=3y"


def test_format_experience_min_only():
    assert _format_experience(2, None) == ">=2y"


# --- render_readme (OUT-01, OUT-02, OUT-03, OUT-06, OUT-07, OUT-08) ----------

def test_render_empty_state_shows_placeholder(tmp_path):
    """OUT-08: empty postings → '(no matching postings yet)' between sentinels."""
    readme = tmp_path / "README.md"
    readme.write_text(
        f"intro text\n\n{SENTINEL_BEGIN}\nold content\n{SENTINEL_END}\n\noutro\n"
    )
    out = render_readme(
        {"schema_version": 1, "last_run_utc": None, "postings": {}}, readme, _RUN
    )
    assert EMPTY_PLACEHOLDER in out
    assert "intro text" in out
    assert "outro" in out
    assert "old content" not in out


def test_render_missing_sentinels_raises(tmp_path):
    """OUT-01: missing sentinels → explicit ValueError (no blind append)."""
    readme = tmp_path / "README.md"
    readme.write_text("no sentinels here")
    with pytest.raises(ValueError):
        render_readme(
            {"schema_version": 1, "last_run_utc": None, "postings": {}}, readme, _RUN
        )


def test_render_only_replaces_between_sentinels(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        f"BEFORE\n\n{SENTINEL_BEGIN}\nold\n{SENTINEL_END}\n\nAFTER\n"
    )
    out = render_readme(
        {"schema_version": 1, "last_run_utc": None, "postings": {}}, readme, _RUN
    )
    assert out.startswith("BEFORE")
    assert out.endswith("AFTER\n")


def test_render_idempotent_byte_equal(tmp_path):
    """OUT-07 — calling render_readme twice with same input must be byte-identical."""
    readme = tmp_path / "README.md"
    readme.write_text(f"intro\n\n{SENTINEL_BEGIN}\nold\n{SENTINEL_END}\n\noutro\n")
    state = {
        "schema_version": 1,
        "last_run_utc": _RUN.isoformat(),
        "postings": {
            "gh:x:1": {
                "company": "Apple",
                "title": "SWE New Grad",
                "location": "Cupertino, CA",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": "https://x/1",
                "posted_date": "2026-06-01T00:00:00+00:00",
                "first_seen": _RUN.isoformat(),
                "last_seen": _RUN.isoformat(),
                "still_listed": True,
                "source_adapter": "greenhouse",
            }
        },
    }
    out1 = render_readme(state, readme, _RUN)
    out2 = render_readme(state, readme, _RUN)
    assert out1 == out2, "OUT-07 idempotency violated"


def test_render_table_has_required_columns(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
    state = {
        "schema_version": 1,
        "last_run_utc": None,
        "postings": {
            "k": {
                "company": "X",
                "title": "Y",
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": "https://x/1",
                "posted_date": None,
                "first_seen": _RUN.isoformat(),
                "last_seen": _RUN.isoformat(),
                "still_listed": True,
                "source_adapter": "greenhouse",
            }
        },
    }
    out = render_readme(state, readme, _RUN)
    # OUT-02 — exact column header, exact order.
    assert "| Company | Position | Location | Salary | Experience | Posting | Age |" in out


def test_render_sort_order_posted_date_desc(tmp_path):
    """OUT-06: sorted by posted_date DESC, then company ASC."""
    readme = tmp_path / "README.md"
    readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
    state = {
        "schema_version": 1,
        "last_run_utc": None,
        "postings": {
            "gh:z:1": {
                "company": "Zebra",
                "title": "T",
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": "https://z/1",
                "posted_date": "2026-06-05T00:00:00+00:00",  # newer
                "first_seen": _RUN.isoformat(),
                "last_seen": _RUN.isoformat(),
                "still_listed": True,
                "source_adapter": "greenhouse",
            },
            "gh:a:1": {
                "company": "Anthropic",
                "title": "T",
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": "https://a/1",
                "posted_date": "2026-06-01T00:00:00+00:00",  # older
                "first_seen": _RUN.isoformat(),
                "last_seen": _RUN.isoformat(),
                "still_listed": True,
                "source_adapter": "greenhouse",
            },
        },
    }
    out = render_readme(state, readme, _RUN)
    # Zebra has newer posted_date so should appear FIRST.
    assert out.index("Zebra") < out.index("Anthropic")


def test_render_sort_none_posted_date_last(tmp_path):
    """OUT-06: postings with posted_date=None sort LAST."""
    readme = tmp_path / "README.md"
    readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
    state = {
        "schema_version": 1,
        "last_run_utc": None,
        "postings": {
            "gh:n:1": {
                "company": "NoDate",
                "title": "T",
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": "https://n/1",
                "posted_date": None,
                "first_seen": _RUN.isoformat(),
                "last_seen": _RUN.isoformat(),
                "still_listed": True,
                "source_adapter": "greenhouse",
            },
            "gh:y:1": {
                "company": "HasDate",
                "title": "T",
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": "https://y/1",
                "posted_date": "2026-01-01T00:00:00+00:00",
                "first_seen": _RUN.isoformat(),
                "last_seen": _RUN.isoformat(),
                "still_listed": True,
                "source_adapter": "greenhouse",
            },
        },
    }
    out = render_readme(state, readme, _RUN)
    assert out.index("HasDate") < out.index("NoDate")


def test_render_table_contains_apply_link(tmp_path):
    """OUT-03: Posting column is `[Apply](canonical_url)`."""
    readme = tmp_path / "README.md"
    readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
    state = {
        "schema_version": 1,
        "last_run_utc": None,
        "postings": {
            "k": {
                "company": "X",
                "title": "Y",
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": "https://x.example/job/1",
                "posted_date": None,
                "first_seen": _RUN.isoformat(),
                "last_seen": _RUN.isoformat(),
                "still_listed": True,
                "source_adapter": "greenhouse",
            }
        },
    }
    out = render_readme(state, readme, _RUN)
    assert "[Apply](https://x.example/job/1)" in out


def test_render_escapes_pipe_in_title(tmp_path):
    """Markdown injection defense — a pipe in title must not break the table."""
    readme = tmp_path / "README.md"
    readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
    state = {
        "schema_version": 1,
        "last_run_utc": None,
        "postings": {
            "k": {
                "company": "X",
                "title": "Engineer | Junior",  # pipe inside the cell
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": "https://x/1",
                "posted_date": None,
                "first_seen": _RUN.isoformat(),
                "last_seen": _RUN.isoformat(),
                "still_listed": True,
                "source_adapter": "greenhouse",
            }
        },
    }
    out = render_readme(state, readme, _RUN)
    assert "Engineer \\| Junior" in out


# --- Phase 4 Plan 04-01 — salary cell handling (D-01a + D-01b) ----------------
# D-01a: empty / None / non-numeric placeholder strings render as '—'.
# D-01b: salary cell truncated at 80 chars with ellipsis.

from src.renderer import _coalesce_salary, _truncate_cell  # noqa: E402


class TestCoalesceSalaryHelper:
    """D-01a — unit tests for the pure _coalesce_salary helper."""

    def test_none_to_em_dash(self):
        assert _coalesce_salary(None) == "—"

    def test_empty_to_em_dash(self):
        assert _coalesce_salary("") == "—"

    def test_whitespace_only_to_em_dash(self):
        assert _coalesce_salary("   ") == "—"

    @pytest.mark.parametrize(
        "placeholder",
        [
            "competitive", "Competitive", "COMPETITIVE",
            "doe", "DOE", "Doe",
            "tbd", "TBD",
            "not disclosed", "Not Disclosed",
            "n/a", "N/A", "na", "NA",
            "null", "Null",
            "to be determined", "To Be Determined",
            "negotiable", "Negotiable",
            "depends on experience", "Depends On Experience",
            "tbc", "TBC",
            "—",
        ],
    )
    def test_placeholder_strings_coalesce_to_em_dash(self, placeholder):
        assert _coalesce_salary(placeholder) == "—"

    def test_real_salary_passes_through(self):
        assert _coalesce_salary("$120k") == "$120k"

    def test_real_salary_range_passes_through(self):
        assert _coalesce_salary("$120,000 - $160,000") == "$120,000 - $160,000"

    def test_pound_sterling_passes_through(self):
        assert _coalesce_salary("£60,000 - £80,000") == "£60,000 - £80,000"

    def test_strips_whitespace_around_real_value(self):
        assert _coalesce_salary("  $140K  ") == "$140K"


class TestTruncateCellHelper:
    """D-01b — 80-char cell truncation with ellipsis."""

    def test_short_string_unchanged(self):
        assert _truncate_cell("short") == "short"

    def test_exactly_80_chars_unchanged(self):
        s = "x" * 80
        assert _truncate_cell(s) == s
        assert len(_truncate_cell(s)) == 80

    def test_81_chars_truncated_to_80_with_ellipsis(self):
        s = "x" * 81
        out = _truncate_cell(s)
        assert len(out) == 80
        assert out.endswith("…")

    def test_100_chars_truncated_to_80_with_ellipsis(self):
        s = "y" * 100
        out = _truncate_cell(s)
        assert len(out) == 80
        assert out.endswith("…")

    def test_custom_limit(self):
        assert _truncate_cell("abcdefghij", limit=5) == "abcd…"


class TestSalaryCellRendering:
    """D-01a + D-01b — end-to-end render cell behavior."""

    def _state_with_salary(self, salary):
        return {
            "schema_version": 1,
            "last_run_utc": None,
            "postings": {
                "k": {
                    "company": "X",
                    "title": "T",
                    "location": "SF",
                    "salary": salary,
                    "experience_min": None,
                    "experience_max": None,
                    "posting_url": "https://x/1",
                    "posted_date": None,
                    "first_seen": _RUN.isoformat(),
                    "last_seen": _RUN.isoformat(),
                    "still_listed": True,
                    "source_adapter": "greenhouse",
                },
            },
        }

    def test_render_salary_empty_renders_em_dash(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
        out = render_readme(self._state_with_salary(""), readme, _RUN)
        # Cell content shows "—" — assert it appears within the table row.
        assert " | — | " in out

    def test_render_salary_none_renders_em_dash(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
        out = render_readme(self._state_with_salary(None), readme, _RUN)
        assert " | — | " in out

    @pytest.mark.parametrize(
        "placeholder",
        ["Competitive", "DOE", "TBD", "Not disclosed", "Negotiable"],
    )
    def test_render_salary_placeholder_coalesces_to_em_dash(
        self, tmp_path, placeholder,
    ):
        readme = tmp_path / "README.md"
        readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
        out = render_readme(self._state_with_salary(placeholder), readme, _RUN)
        assert " | — | " in out
        assert placeholder not in out

    def test_render_salary_verbatim_passes_through(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
        out = render_readme(
            self._state_with_salary("$120k–$160k"), readme, _RUN,
        )
        assert "$120k–$160k" in out

    def test_render_salary_long_value_truncated_to_80_chars_with_ellipsis(
        self, tmp_path,
    ):
        readme = tmp_path / "README.md"
        readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
        long_salary = "$" + "1" * 100  # 101 chars
        out = render_readme(self._state_with_salary(long_salary), readme, _RUN)
        # The rendered cell must contain a truncated form ending with the
        # ellipsis character. Cell content sits between " | " delimiters.
        # Row shape: "| Company | Title | Location | <salary> | ..."
        # splitting on " | " yields: ['| Company', 'Title', 'Location',
        # '<salary>', 'experience', '[Apply](...)', 'age |']
        # so salary lives at index 3.
        rows = [line for line in out.splitlines() if line.startswith("| X |")]
        assert rows, "expected at least one data row starting with '| X |'"
        cells = rows[0].split(" | ")
        salary_cell = cells[3]
        assert salary_cell.endswith("…")
        # The cell is <= 80 chars by D-01b.
        assert len(salary_cell) <= 80

    def test_render_salary_pipe_in_value_is_escaped_after_coalesce(
        self, tmp_path,
    ):
        """A real salary like '$100k | bonus' should escape the pipe."""
        readme = tmp_path / "README.md"
        readme.write_text(f"{SENTINEL_BEGIN}\n\n{SENTINEL_END}")
        out = render_readme(
            self._state_with_salary("$100k | bonus"), readme, _RUN,
        )
        assert "$100k \\| bonus" in out
