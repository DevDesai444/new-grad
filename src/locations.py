"""Location normalization + US/non-US classification (NORM-03 + FILT-07 helper).

Pure functions per the project's pure-core/impure-edges discipline. No I/O,
no datetime imports. All regex compiled at module load.

Per Phase 4 CONTEXT.md:
- D-02:  normalize_location collapses Remote variants to canonical form;
         non-Remote strings unchanged (D-02b — no deep city canonicalization).
- D-02a: is_us_location implements 8-rule classifier in declared order.
- D-02c: city lists are intentionally not exhaustive (~30 each); ambiguous
         cases default to True (bias toward inclusion per FILT-05).

Consumed by:
- src/normalizer.py (Phase 4 Plan 04-01 — every per-adapter helper routes
  location through normalize_location).
- src/filter.py is_us_location_acceptable (Phase 4 Plan 04-02 — FILT-07).
"""
from __future__ import annotations

import re

# ----- D-02 / D-02a — curated lookup tables (Claude's Discretion seed) -----

_US_STATE_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
})

# US country tokens — case-insensitive substring match.
_US_COUNTRY_TOKENS = (
    "USA", "U.S.A.", "U.S.", "United States",
)

# US tech-hub city seeds — case-insensitive substring match. ~30 entries.
# Per D-02c — tunable; bias-toward-inclusion at the gate means missing entries
# fall through to rule 7 (True) rather than misclassifying as non-US.
_US_CITIES = (
    "San Francisco", "New York", "Seattle", "Boston", "Cupertino",
    "Mountain View", "Palo Alto", "San Jose", "Sunnyvale", "Redmond",
    "Cambridge", "Austin", "Denver", "Chicago", "Atlanta",
    "Los Angeles", "San Diego", "Washington", "Pittsburgh", "Detroit",
    "Phoenix", "Portland", "Minneapolis", "Salt Lake City", "Raleigh",
    "Durham", "Madison", "Ann Arbor", "Bellevue", "Brooklyn",
)

# Non-US tokens — case-insensitive substring match. ~45 entries covering the
# major non-US tech hubs + country names. A match short-circuits rule 6 to False.
_NON_US_TOKENS = (
    "London", "Berlin", "Munich", "Paris", "Amsterdam", "Dublin",
    "Bangalore", "Bengaluru", "Hyderabad", "Mumbai", "Pune", "Singapore",
    "Tokyo", "Seoul", "Shanghai", "Beijing", "Hong Kong", "Sydney",
    "Melbourne", "Toronto", "Vancouver", "Montreal", "Mexico City",
    "São Paulo", "Sao Paulo", "Tel Aviv", "Stockholm", "Copenhagen",
    "Zurich", "Madrid", "Barcelona", "Warsaw", "Buenos Aires",
    "United Kingdom", "Canada", "Germany", "India", "Japan",
    "Australia", "France", "Brazil", "Mexico", "Bahrain", "Ireland",
    "UK", "EU", "Europe",
)

# ----- Remote variant patterns (D-02) -----

# Remote-with-US — matches:
#   "Remote, US" / "Remote - US" / "Remote — US" / "Remote / US" / "Remote (US)"
#   "Remote, USA" / "Remote (USA)" / "Remote / USA"
#   "Remote, U.S." / "Remote (U.S.)" / "Remote, U.S.A." / "Remote (U.S.A.)"
#   "Remote - United States" / "Remote (United States)" / "Remote, United States"
#   "REMOTE / US" (case-insensitive)
_REMOTE_US_PATTERNS = [
    re.compile(
        r"^\s*remote\s*[,\-—()/\s]+\s*"
        r"(us|usa|u\.s\.|u\.s\.a\.|united\s+states)"
        r"\s*\)?\s*$",
        re.IGNORECASE,
    ),
    # Bare "Remote" with nothing after — bias toward US per D-02 (user is in US).
    re.compile(r"^\s*remote\s*$", re.IGNORECASE),
]

# Remote-with-non-US — matches Remote + a non-US country/region token.
_REMOTE_NON_US_PATTERNS = [
    re.compile(
        r"^\s*remote\s*[,\-—()/\s]+\s*("
        r"uk|u\.k\.|united\s+kingdom|"
        r"eu|europe|emea|apac|latam|"
        r"india|germany|france|canada|japan|china|brazil|mexico|australia|"
        r"singapore|netherlands|spain|ireland|italy|sweden|switzerland"
        r")\s*\)?\s*$",
        re.IGNORECASE,
    ),
]

# Standalone US state code — token-bounded match. Built dynamically from
# _US_STATE_CODES so additions to the set propagate automatically.
_US_STATE_REGEX = re.compile(
    r"\b(" + "|".join(sorted(_US_STATE_CODES)) + r")\b"
)


def normalize_location(raw: str | None) -> str:
    """Collapse Remote variants to canonical form; otherwise unchanged.

    Returns "" for None / empty / whitespace-only inputs.
    Returns "Remote (US)" for any Remote-US-shape variant (or bare "Remote").
    Returns "Remote (non-US)" for any Remote-non-US-shape variant.
    Returns raw.strip() for everything else (D-02b — no deep canonicalization).
    """
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    for pat in _REMOTE_US_PATTERNS:
        if pat.match(s):
            return "Remote (US)"
    for pat in _REMOTE_NON_US_PATTERNS:
        if pat.match(s):
            return "Remote (non-US)"
    return s


def is_us_location(raw: str | None) -> bool:
    """Classify a location string as US (True) or non-US (False).

    Bias toward inclusion (FILT-05) — empty / ambiguous → True.

    Rules in declared order (D-02a):
      1. Empty / whitespace → True.
      2. After normalize_location: "Remote (US)" → True;
                                   "Remote (non-US)" → False.
      3. Standalone US state code token → True.
      4. US country token (USA / U.S.A. / U.S. / United States) → True.
      5. Known US city substring → True.
      6. Known non-US city/country substring → False.
      7. Otherwise → True.
    """
    # Rule 1 — empty / None / whitespace-only.
    if raw is None or not raw.strip():
        return True

    # Rule 2 — Remote canonical (via normalize_location).
    normalized = normalize_location(raw)
    if normalized == "Remote (US)":
        return True
    if normalized == "Remote (non-US)":
        return False

    # Rule 3 — standalone uppercase US state code token.
    if _US_STATE_REGEX.search(raw):
        return True

    # Rule 4 — case-insensitive US country token substring.
    lower = raw.lower()
    for tok in _US_COUNTRY_TOKENS:
        if tok.lower() in lower:
            return True

    # Rule 5 — known US city substring.
    for city in _US_CITIES:
        if city.lower() in lower:
            return True

    # Rule 6 — known non-US substring (any token from the curated list).
    for tok in _NON_US_TOKENS:
        if tok.lower() in lower:
            return False

    # Rule 7 — fallback bias toward inclusion (FILT-05).
    return True
