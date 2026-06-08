"""Normalizer: RawPosting -> Posting.

Pure function. No I/O, no datetime.now(). The caller (main.py) passes
run_started_at as the canonical "now" — RUN-01.

Dispatches on RawPosting.source_adapter to know how to read the source-specific
`raw` blob. Phase 1 only handles "greenhouse"; Phase 2 will extend.

Requirements covered:
- NORM-04: posted_date from Greenhouse `updated_at`; None when source omits.
- NORM-05: all dates normalized to UTC ISO 8601.
- NORM-06: URL canonicalization strips utm_*, gh_src, lever-source params;
           lowercases host; removes trailing slash; drops fragment.
"""
from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.models import Posting, RawPosting

# NORM-06 — tracking-param prefixes / exact names to strip during canonicalization.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = ("gh_src", "lever-source", "ref", "ref_src")


def canonicalize_url(url: str) -> str:
    """Strip tracking params, lowercase host, remove trailing slash, drop fragment.

    NORM-06 + PITFALLS.md Pitfall 9. Preserves path case (job slugs are
    case-sensitive on some ATSes).
    """
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    kept_params = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not (
            any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
            or k.lower() in _TRACKING_PARAM_EXACT
        )
    ]
    cleaned_query = urlencode(kept_params, doseq=True)
    # Strip trailing slash for non-root paths only — "/" stays "" after rstrip,
    # so an empty path is fine; a "/foo/" becomes "/foo".
    path = parsed.path.rstrip("/") if parsed.path != "/" else ""
    # Drop fragment (last urlunparse arg = empty string).
    return urlunparse(
        (parsed.scheme, netloc, path, parsed.params, cleaned_query, "")
    )


def _parse_iso_to_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string to a UTC-aware datetime.

    NORM-05. Returns None on parse failure or None/empty input (NORM-04).
    Naive datetimes are assumed UTC (defensive — Greenhouse always sends offset).
    """
    if not value:
        return None
    try:
        s = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt


def _normalize_greenhouse(rp: RawPosting, run_started_at: datetime) -> Posting:
    """Greenhouse-specific normalization.

    Salary + experience extraction is deferred to Phase 2/4. Phase 1 emits None
    for both fields (the filter's FILT-05 ambiguous-bias means this is still useful).
    """
    raw = rp.raw
    # Adapter (Plan 01) guaranteed __dedup_key is present.
    dedup_key = raw["__dedup_key"]
    title = (raw.get("title") or "").strip()
    location = ((raw.get("location") or {}).get("name") or "").strip()
    posting_url = canonicalize_url(raw.get("absolute_url") or "")
    posted_date = _parse_iso_to_utc(raw.get("updated_at"))

    company = rp.source_company
    # Cosmetic: title-case if the board token came in lowercase ("stripe" -> "Stripe").
    if company.islower():
        company = company.capitalize()

    return Posting(
        dedup_key=dedup_key,
        company=company,
        title=title,
        location=location,
        salary=None,
        experience_min=None,
        experience_max=None,
        posting_url=posting_url,
        posted_date=posted_date,
        first_seen=run_started_at,
        last_seen=run_started_at,
        still_listed=True,
        source_adapter=rp.source_adapter,
    )


_DISPATCH = {
    "greenhouse": _normalize_greenhouse,
}


def normalize(raw_posting: RawPosting, run_started_at: datetime) -> Posting:
    """Dispatch to the per-adapter normalizer for the given source_adapter.

    Raises ValueError if no normalizer is registered for this adapter — this is
    a programming error (registry added an adapter without adding a dispatcher).
    """
    fn = _DISPATCH.get(raw_posting.source_adapter)
    if fn is None:
        raise ValueError(
            f"No normalizer registered for source_adapter={raw_posting.source_adapter!r}. "
            "Add a handler in src/normalizer.py._DISPATCH."
        )
    return fn(raw_posting, run_started_at)
