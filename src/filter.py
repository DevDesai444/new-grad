"""Title-keyword filter for early-career eligibility (0-5 yrs).

Pure function per FILT-06. No I/O. No datetime imports.

FILT-01 include keywords, FILT-02 exclude keywords. Excludes ALWAYS win on conflict.

Per Phase 2 CONTEXT.md D-02 (JD-scan is display-only): is_early_career now
gates by title ONLY. The FILT-04 experience clause (`experience_min <= 5`) is
REMOVED — see REQUIREMENTS.md FILT-04 strikethrough with footnote pointing to
this file's D-02 reference.

FILT-03 JD-scan: extract_experience_range() below extracts numeric ranges,
open-min ("X+ years"), and entry signals from job-description text. Output
populates Posting.experience_min/experience_max via the per-adapter normalizer
helpers; it NEVER gates inclusion. The Experience column in the rendered
README displays these numbers per OUT-05.
"""
from __future__ import annotations

import re

from src.models import Posting

# FILT-01 — Include keywords. Tested via re.search so word-boundary anchors apply.
_INCLUDE_PATTERNS = [
    re.compile(r"\bnew\s*grad(?:uate)?\b", re.IGNORECASE),
    re.compile(r"\bentry[- ]?level\b", re.IGNORECASE),
    re.compile(r"\bentry\b", re.IGNORECASE),
    re.compile(r"\bearly[- ]?career\b", re.IGNORECASE),
    re.compile(r"\bjunior\b", re.IGNORECASE),
    re.compile(r"\bassociate\b", re.IGNORECASE),
    re.compile(r"\buniversity\b", re.IGNORECASE),
    re.compile(r"\brecent\s+graduate\b", re.IGNORECASE),
    re.compile(r"\bclass\s+of\s+20\d{2}\b", re.IGNORECASE),
    # Level-I markers ("SDE I", "Software Engineer 1", "Analyst I")
    re.compile(
        r"\b(?:engineer|developer|analyst|scientist|swe|sde|associate)\s+(?:I|1)\b",
        re.IGNORECASE,
    ),
]

# FILT-02 — Exclude keywords. Excludes win on conflict.
_EXCLUDE_PATTERNS = [
    re.compile(r"\bsenior\b", re.IGNORECASE),
    re.compile(r"\bsr\.?\b", re.IGNORECASE),
    re.compile(r"\bstaff\b", re.IGNORECASE),
    re.compile(r"\bprincipal\b", re.IGNORECASE),
    re.compile(r"\blead\b", re.IGNORECASE),
    re.compile(r"\bmanager\b", re.IGNORECASE),
    re.compile(r"\bdirector\b", re.IGNORECASE),
    re.compile(r"\bhead\s+of\b", re.IGNORECASE),
    # Level-II+ markers ("SWE II", "Software Engineer III", "Engineer 3")
    re.compile(
        r"\b(?:engineer|developer|analyst|scientist|swe|sde)\s+(?:II|III|IV|V)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:engineer|developer|analyst|scientist|swe|sde)\s+[2-9]\b",
        re.IGNORECASE,
    ),
]


def _passes_title_gate(title: str) -> bool:
    """Excludes always win. Then includes. Then FILT-05 ambiguous-bias = True."""
    if any(pat.search(title) for pat in _EXCLUDE_PATTERNS):
        return False
    if any(pat.search(title) for pat in _INCLUDE_PATTERNS):
        return True
    # FILT-05 — bias toward inclusion on ambiguous title.
    return True


def is_early_career(posting: Posting) -> bool:
    """Title-gate ONLY. Per CONTEXT.md D-02 (Phase 2): JD-scan is display-only.

    The Phase 1 implementation also rejected when `posting.experience_min > 5`
    (FILT-04). That clause is REMOVED per D-02 — see REQUIREMENTS.md FILT-04
    strikethrough. JD-scan output now feeds the Experience column directly
    via the per-adapter normalizer helpers; it does NOT gate inclusion.
    """
    return _passes_title_gate(posting.title)


# ----- FILT-03: JD-scan (Plan 02-03 / CONTEXT.md D-02 — display-only). -----
# Pure function; called by every per-adapter normalizer in src/normalizer.py
# to populate Posting.experience_min / Posting.experience_max from the
# source's description text. Per D-02 the output NEVER gates inclusion
# (is_early_career above uses title-gate alone).

_JD_SCAN_MAX_CHARS = 5000  # bounded char cap — prevents regex DoS on 100KB HTML

# Numeric range — strictly more specific; runs first.
# Examples matched: "0-3 years", "3 to 5 years", "5–7 years", "5-7 yrs"
_RANGE_PATTERN = re.compile(
    r"\b(\d+)\+?\s*(?:to|-|–|—)\s*(\d+)\s*\+?\s*years?\b",
    re.IGNORECASE,
)

# Open-ended minimum — "5+ years".
_OPEN_MIN_PATTERN = re.compile(
    r"\b(\d+)\+\s*years?\b",
    re.IGNORECASE,
)

# Entry signals — sets (0, None).
_ENTRY_PATTERN = re.compile(
    r"\b(?:entry[- ]?level|recent\s+graduate|no\s+experience\s+required|new\s+grad(?:uate)?)\b",
    re.IGNORECASE,
)


def extract_experience_range(
    description: str | None,
) -> tuple[int | None, int | None]:
    """JD-scan: extract (experience_min, experience_max) from description text.

    FILT-03 + CONTEXT.md D-02 (display-only — NEVER gates inclusion).
    Pure function; no I/O. Returns (None, None) on no-match or empty input.

    Precedence: numeric range > open-min > entry signal.
    Caps input at _JD_SCAN_MAX_CHARS (5000) chars to bound regex cost
    (mitigates T-02-03-03: regex catastrophic backtracking on huge HTML).

    Examples:
      "0-3 years of experience"   -> (0, 3)
      "3 to 5 years required"     -> (3, 5)
      "5–7 years experience"      -> (5, 7)   (en-dash variant)
      "5+ years required"         -> (5, None)
      "10+ years"                 -> (10, None)
      "entry-level role"          -> (0, None)
      "recent graduate"           -> (0, None)
      "no experience required"    -> (0, None)
      "new grad SWE"              -> (0, None)
      "Founded in 2010"           -> (None, None)  (no `years?` suffix)
      ""                          -> (None, None)
      None                        -> (None, None)
    """
    if not description:
        return (None, None)
    text = description[:_JD_SCAN_MAX_CHARS]

    m = _RANGE_PATTERN.search(text)
    if m:
        try:
            return (int(m.group(1)), int(m.group(2)))
        except (TypeError, ValueError):
            pass  # fall through to next pattern

    m = _OPEN_MIN_PATTERN.search(text)
    if m:
        try:
            return (int(m.group(1)), None)
        except (TypeError, ValueError):
            pass

    if _ENTRY_PATTERN.search(text):
        return (0, None)

    return (None, None)
