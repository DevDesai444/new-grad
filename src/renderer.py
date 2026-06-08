"""Renderer: pure function from state dict -> README string.

Requirements covered: OUT-01..08 and NORM-07 (Pitfall 13 — Markdown escaping).

Per ARCHITECTURE.md §Patterns: the renderer is the ONLY component that writes
README.md, and it ONLY rewrites content between SENTINEL_BEGIN / SENTINEL_END
sentinels — preserving the rest of the README authored by the user.

The renderer is pure (idempotency contract OUT-07): same `state` + same
`run_started_at` MUST produce byte-identical output. The defensive default value
for `run_started_at` in `render_readme` (the current UTC time) is only used when
the caller omits it — main.py always passes one in explicitly.
"""
from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

SENTINEL_BEGIN = "<!-- BEGIN JOBS -->"
SENTINEL_END = "<!-- END JOBS -->"

EMPTY_PLACEHOLDER = "(no matching postings yet)"

# OUT-02 — column order locked. Renderer never reorders or renames these.
_HEADER_ROW = "| Company | Position | Location | Salary | Experience | Posting | Age |"
_SEP_ROW = "| --- | --- | --- | --- | --- | --- | --- |"

# NORM-07 / Pitfall 13 — invisible Unicode codepoints to strip outright.
# Codepoints handled: u200b ZWSP, u200c ZWNJ, u200d ZWJ, ufeff BOM, u2060 WJ.
_INVISIBLE_UNICODE_STRIP = (
    "​",  # u200b ZWSP — zero-width space
    "‌",  # u200c ZWNJ — zero-width non-joiner
    "‍",  # u200d ZWJ  — zero-width joiner
    "﻿",  # ufeff BOM  — byte-order mark
    "⁠",  # u2060 WJ   — word joiner
)

# Characters to replace with a regular space. u00a0 NBSP plus whitespace controls.
_REPLACE_WITH_SPACE = (
    " ",  # u00a0 NBSP — non-breaking space
    "\n",
    "\r",
    "\t",
)


def escape_markdown_cell(text: str | None) -> str:
    """Escape a single cell for a GitHub-flavored Markdown table.

    - Strips invisible Unicode (u200b, u200c, u200d, ufeff, u2060).
    - Replaces u00a0 NBSP / newline / carriage-return / tab with a regular space.
    - Escapes literal `|` to `\\|` so it does not break the table column count.
    - Collapses consecutive whitespace to a single space and trims edges.
    - `None` / empty → `""`.
    NORM-07. Pitfall 13.
    """
    if text is None:
        return ""
    s = str(text)
    for ch in _INVISIBLE_UNICODE_STRIP:
        s = s.replace(ch, "")
    for ch in _REPLACE_WITH_SPACE:
        s = s.replace(ch, " ")
    s = s.replace("|", "\\|")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def format_age(reference_time: datetime | None, run_started_at: datetime) -> str:
    """Return human-readable age: 'now', 'Nm', 'Nh', 'Nd', 'Nw', 'Nmo', 'Ny'.

    OUT-04. Returns '' when reference_time is None. Clamps negative ages to 0
    (Pitfall 10 defensive: a future-dated posting must not produce a negative
    duration). Naive datetimes are assumed UTC (defensive).
    """
    if reference_time is None:
        return ""
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)
    if run_started_at.tzinfo is None:
        run_started_at = run_started_at.replace(tzinfo=UTC)
    delta = run_started_at - reference_time
    seconds = max(int(delta.total_seconds()), 0)
    minutes = seconds // 60
    hours = seconds // 3600
    days = seconds // 86400
    weeks = days // 7
    months = days // 30
    years = days // 365
    if years >= 1:
        return f"{years}y"
    if months >= 2:
        return f"{months}mo"
    if weeks >= 1:
        return f"{weeks}w"
    if days >= 1:
        return f"{days}d"
    if hours >= 1:
        return f"{hours}h"
    if minutes >= 1:
        return f"{minutes}m"
    return "now"


def _format_experience(exp_min: int | None, exp_max: int | None) -> str:
    """OUT-05: 'Xy-Yy' / '<=Yy' / '>=Xy' / blank."""
    if exp_min is not None and exp_max is not None:
        return f"{exp_min}y-{exp_max}y"
    if exp_max is not None:
        return f"<={exp_max}y"
    if exp_min is not None:
        return f">={exp_min}y"
    return ""


def _parse_iso(s: str | None) -> datetime | None:
    """Permissive ISO-8601 parse for record-shaped dates. Returns None on failure."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(
            s.replace("Z", "+00:00") if s.endswith("Z") else s
        )
    except (ValueError, TypeError):
        return None


def _table_row(record: dict, run_started_at: datetime) -> str:
    company = escape_markdown_cell(record.get("company"))
    title = escape_markdown_cell(record.get("title"))
    location = escape_markdown_cell(record.get("location"))
    salary = escape_markdown_cell(record.get("salary") or "—")
    experience = escape_markdown_cell(
        _format_experience(record.get("experience_min"), record.get("experience_max"))
    )
    posting_url = record.get("posting_url") or ""
    # OUT-03 — clickable link. URL is left raw (already canonicalized by normalizer).
    posting_link = f"[Apply]({posting_url})" if posting_url else ""
    # OUT-04 — Age from posted_date if known, else fall back to first_seen.
    reference = _parse_iso(record.get("posted_date")) or _parse_iso(
        record.get("first_seen")
    )
    age = escape_markdown_cell(format_age(reference, run_started_at))
    return (
        f"| {company} | {title} | {location} | {salary} | "
        f"{experience} | {posting_link} | {age} |"
    )


def _sort_key(record: dict) -> tuple:
    """OUT-06 — sort by posted_date DESC then company ASC.

    Records with posted_date=None sort LAST (after all dated postings).
    Sort is stable (Timsort) so equal-date entries keep input order within company.
    """
    posted = _parse_iso(record.get("posted_date"))
    if posted is None:
        # Tuple ordering: (1, 0) > (0, ...) → None entries pushed to end.
        primary_a = 1
        primary_b = 0.0
    else:
        primary_a = 0
        primary_b = -posted.timestamp()  # negate so newer (larger ts) sorts first
    company_lower = (record.get("company") or "").lower()
    return (primary_a, primary_b, company_lower)


def render_table(state: dict, run_started_at: datetime) -> str:
    """Return the table body (without sentinels). OUT-08 placeholder when empty."""
    postings = state.get("postings", {})
    if not postings:
        return EMPTY_PLACEHOLDER
    sorted_records = sorted(postings.values(), key=_sort_key)
    rows = [_table_row(rec, run_started_at) for rec in sorted_records]
    return "\n".join([_HEADER_ROW, _SEP_ROW] + rows)


def render_readme(
    state: dict,
    readme_path: Path = Path("README.md"),
    run_started_at: datetime | None = None,
) -> str:
    """Pure function — returns the NEW README content. Does NOT write to disk.

    OUT-01 — replaces ONLY the content between SENTINEL_BEGIN / SENTINEL_END.
    OUT-07 — idempotent: identical state + identical run_started_at → byte-identical.
    Raises ValueError if sentinels are not found (refuses to blindly append).
    """
    if run_started_at is None:
        run_started_at = datetime.now(UTC)
    table = render_table(state, run_started_at)
    current = readme_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"({re.escape(SENTINEL_BEGIN)})(.*?)({re.escape(SENTINEL_END)})",
        re.DOTALL,
    )
    replacement = f"{SENTINEL_BEGIN}\n\n{table}\n\n{SENTINEL_END}"
    new_content, count = pattern.subn(replacement, current, count=1)
    if count == 0:
        raise ValueError(
            f"renderer: sentinels {SENTINEL_BEGIN} / {SENTINEL_END} not found "
            f"in {readme_path}. Refusing to write."
        )
    return new_content


def write_readme(
    state: dict,
    readme_path: Path = Path("README.md"),
    run_started_at: datetime | None = None,
) -> None:
    """Render and write atomically (.tmp + os.replace) — same atomic-write
    discipline as state_store. Pure renderer is composed with a single I/O edge."""
    new_content = render_readme(state, readme_path, run_started_at)
    tmp = readme_path.with_suffix(readme_path.suffix + ".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    os.replace(tmp, readme_path)
