"""Title-keyword filter for early-career eligibility (0-5 yrs).

Pure function per FILT-06. No I/O. No datetime imports.

FILT-01 include keywords, FILT-02 exclude keywords. Excludes ALWAYS win on conflict.

FILT-04: keep iff (title passes gate) AND (experience_min is None OR experience_min <= 5).
FILT-05: ambiguous title (no include hit + no exclude hit) -> INCLUDE
         (bias toward inclusion — user prefers extra noise over missed roles).
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

# FILT-04 — experience ceiling (years).
_EXPERIENCE_CEILING_YEARS = 5


def _passes_title_gate(title: str) -> bool:
    """Excludes always win. Then includes. Then FILT-05 ambiguous-bias = True."""
    if any(pat.search(title) for pat in _EXCLUDE_PATTERNS):
        return False
    if any(pat.search(title) for pat in _INCLUDE_PATTERNS):
        return True
    # FILT-05 — bias toward inclusion on ambiguous title.
    return True


def is_early_career(posting: Posting) -> bool:
    """Phase 1 filter: title-keyword gate + experience_min ceiling (FILT-04)."""
    if not _passes_title_gate(posting.title):
        return False
    if (
        posting.experience_min is not None
        and posting.experience_min > _EXPERIENCE_CEILING_YEARS
    ):
        return False
    return True
