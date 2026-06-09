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

import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.filter import extract_experience_range
from src.locations import normalize_location
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


# ----- FILT-03 JD-scan: per-adapter description readers. -----
# Each adapter's response uses a different key path for the job-description
# text. These helpers know where to look. Output is passed to
# extract_experience_range() in src/filter.py. Per CONTEXT.md D-02, the
# output is display-only — it populates Posting.experience_min/max but
# does NOT gate inclusion (is_early_career in src/filter.py is title-only).


def _read_greenhouse_description(raw: dict) -> str:
    """Greenhouse `content` is HTML; JD-scan regexes handle either form."""
    return raw.get("content") or ""


def _read_lever_description(raw: dict) -> str:
    """Lever exposes `descriptionPlain` (preferred) and `description` (HTML)."""
    return raw.get("descriptionPlain") or raw.get("description") or ""


def _read_ashby_description(raw: dict) -> str:
    """Ashby exposes `descriptionPlain` (preferred) and `descriptionHtml`."""
    return raw.get("descriptionPlain") or raw.get("descriptionHtml") or ""


def _read_smartrecruiters_description(raw: dict) -> str:
    """SR nests description deep: jobAd.sections.jobDescription.text."""
    job_ad = raw.get("jobAd") or {}
    if not isinstance(job_ad, dict):
        return ""
    sections = job_ad.get("sections") or {}
    if not isinstance(sections, dict):
        return ""
    jd = sections.get("jobDescription") or {}
    if not isinstance(jd, dict):
        return ""
    return jd.get("text") or ""


def _read_workday_description(raw: dict) -> str:
    """Workday CXS /jobs endpoint does NOT return description text per posting.

    The adapter can stash description in `__description` if a future enhancement
    fetches the per-posting detail page; until then this returns empty string
    and JD-scan yields (None, None) for Workday postings.
    """
    return raw.get("__description") or ""


def _read_apple_description(raw: dict) -> str:
    """Apple exposes `jobSummary` (newer) or `postingDescription` (older)."""
    return raw.get("jobSummary") or raw.get("postingDescription") or ""


def _read_playwright_description(raw: dict) -> str:
    """Playwright extracts description text when the XHR or DOM exposes it.

    The adapter stashes `description` (XHR-path) or leaves "" (DOM-path
    when no description selector matched). JD-scan handles "" → (None, None).
    """
    return raw.get("description") or ""


# ----- Phase 4 Plan 04-01 — per-adapter salary extraction (D-01 verbatim). ----
# Each helper reads a source-specific JSON path; output is COPIED VERBATIM into
# Posting.salary (no parsing, no currency conversion). Empty / missing /
# non-dict shapes return "" so the renderer's placeholder-coalesce (D-01a)
# can render "—" uniformly.

_GREENHOUSE_SALARY_METADATA_NAMES = frozenset({
    "salary", "salary range", "compensation range",
    "pay range", "base pay range",
})


def _extract_greenhouse_salary(raw: dict) -> str:
    """D-01: verbatim salary from raw['metadata'] (list of name/value dicts).

    Iterates the metadata list and returns the FIRST non-empty `value` whose
    `name.lower()` matches a known salary label. Returns "" if none match.
    Defensive against non-list metadata and non-dict entries.
    """
    metadata = raw.get("metadata") or []
    if not isinstance(metadata, list):
        return ""
    for entry in metadata:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip().lower()
        value = entry.get("value")
        if name in _GREENHOUSE_SALARY_METADATA_NAMES and value:
            return str(value).strip()
    return ""


def _normalize_lever(rp: RawPosting, run_started_at: datetime) -> Posting:
    """Lever-specific normalization (ADP-04).

    Per <adapter_specifications> in 02-01-PLAN.md:
      title:        raw["text"]
      location:     raw["categories"]["location"]
      posting_url:  canonicalize_url(raw["hostedUrl"])
      posted_date:  raw["createdAt"] (epoch ms) → UTC datetime
    """
    raw = rp.raw
    dedup_key = raw["__dedup_key"]
    title = (raw.get("text") or "").strip()
    categories = raw.get("categories") or {}
    location = normalize_location(
        (categories.get("location") or "").strip()
        if isinstance(categories, dict)
        else ""
    )
    posting_url = canonicalize_url(raw.get("hostedUrl") or "")
    # Lever createdAt is epoch milliseconds (int). Convert to UTC datetime.
    created_ms = raw.get("createdAt")
    if isinstance(created_ms, (int, float)) and created_ms > 0:
        posted_date = datetime.fromtimestamp(created_ms / 1000.0, tz=UTC)
    else:
        posted_date = None

    # FILT-03 JD-scan (CONTEXT.md D-02 — display-only; never gates inclusion).
    exp_min, exp_max = extract_experience_range(_read_lever_description(raw))

    # D-01 — salary verbatim. Lever prefers nested salaryRange.text, falls
    # back to flat raw["salary"]. Defensive against salaryRange: None.
    salary_range = raw.get("salaryRange") or {}
    salary = (
        (salary_range.get("text") if isinstance(salary_range, dict) else None)
        or raw.get("salary")
        or ""
    )

    company = rp.source_company
    if company.islower():
        company = company.capitalize()

    return Posting(
        dedup_key=dedup_key,
        company=company,
        title=title,
        location=location,
        salary=salary,
        experience_min=exp_min,
        experience_max=exp_max,
        posting_url=posting_url,
        posted_date=posted_date,
        first_seen=run_started_at,
        last_seen=run_started_at,
        still_listed=True,
        source_adapter=rp.source_adapter,
    )


def _normalize_ashby(rp: RawPosting, run_started_at: datetime) -> Posting:
    """Ashby-specific normalization (ADP-05).

    Per <adapter_specifications> in 02-01-PLAN.md:
      title:        raw["title"]
      location:     coalesce(raw["locationName"], raw["location"]["name"])
      posting_url:  canonicalize_url(raw["jobUrl"])
      posted_date:  _parse_iso_to_utc(raw["publishedAt"])
    """
    raw = rp.raw
    dedup_key = raw["__dedup_key"]
    title = (raw.get("title") or "").strip()
    # Coalesce: some tenants return flat "locationName", others {"location": {"name": ...}}.
    location_name = raw.get("locationName")
    if not location_name:
        loc = raw.get("location") or {}
        location_name = loc.get("name") if isinstance(loc, dict) else None
    location = normalize_location((location_name or "").strip())
    posting_url = canonicalize_url(raw.get("jobUrl") or "")
    posted_date = _parse_iso_to_utc(raw.get("publishedAt"))

    # FILT-03 JD-scan (CONTEXT.md D-02 — display-only; never gates inclusion).
    exp_min, exp_max = extract_experience_range(_read_ashby_description(raw))

    # D-01 — salary verbatim. Ashby exposes compensation.compensationTierSummary
    # when includeCompensation=true is in the URL (already wired in
    # src/adapters/ashby.py). Defensive against compensation: None / non-dict.
    compensation = raw.get("compensation") or {}
    if isinstance(compensation, dict):
        salary = compensation.get("compensationTierSummary") or ""
    else:
        salary = ""

    company = rp.source_company
    if company.islower():
        company = company.capitalize()

    return Posting(
        dedup_key=dedup_key,
        company=company,
        title=title,
        location=location,
        salary=salary,
        experience_min=exp_min,
        experience_max=exp_max,
        posting_url=posting_url,
        posted_date=posted_date,
        first_seen=run_started_at,
        last_seen=run_started_at,
        still_listed=True,
        source_adapter=rp.source_adapter,
    )


def _normalize_smartrecruiters(rp: RawPosting, run_started_at: datetime) -> Posting:
    """SmartRecruiters-specific normalization (ADP-06).

    Per <adapter_specifications> in 02-01-PLAN.md:
      title:        raw["name"]       (SR calls the title "name")
      location:     compose city+country (either may be missing)
      posting_url:  canonicalize_url(raw["ref"])  (defensive https:// prefix if relative)
      posted_date:  _parse_iso_to_utc(raw["releasedDate"])

    Note: rp.source_adapter == "smartrecruiters" (full word) while dedup_key prefix
    is "sr:" (short). The split is documented in src/adapters/smartrecruiters.py.
    """
    raw = rp.raw
    dedup_key = raw["__dedup_key"]
    title = (raw.get("name") or "").strip()

    loc = raw.get("location") or {}
    if isinstance(loc, dict):
        city = (loc.get("city") or "").strip()
        country = (loc.get("country") or "").strip()
    else:
        city = country = ""
    if city and country:
        composed = f"{city}, {country}"
    else:
        composed = city or country
    location = normalize_location(composed)

    # SR's "ref" is sometimes relative; defensive https:// prefix if needed.
    ref = (raw.get("ref") or "").strip()
    if ref and not ref.startswith(("http://", "https://")):
        ref = f"https://{ref.lstrip('/')}"
    posting_url = canonicalize_url(ref) if ref else ""

    posted_date = _parse_iso_to_utc(raw.get("releasedDate"))

    # FILT-03 JD-scan (CONTEXT.md D-02 — display-only; never gates inclusion).
    exp_min, exp_max = extract_experience_range(
        _read_smartrecruiters_description(raw),
    )

    # D-01 — SmartRecruiters /postings endpoint does not expose a public salary
    # field; intentionally empty until SR ever ships one.
    salary = ""

    company = rp.source_company
    if company.islower():
        company = company.capitalize()

    return Posting(
        dedup_key=dedup_key,
        company=company,
        title=title,
        location=location,
        salary=salary,
        experience_min=exp_min,
        experience_max=exp_max,
        posting_url=posting_url,
        posted_date=posted_date,
        first_seen=run_started_at,
        last_seen=run_started_at,
        still_listed=True,
        source_adapter=rp.source_adapter,
    )


def _normalize_workday(rp: RawPosting, run_started_at: datetime) -> Posting:
    """Workday-specific normalization (ADP-07).

    Per <adapter_specifications> in 02-02-PLAN.md:
      title:        raw["title"]
      location:     raw["locationsText"]
      posting_url:  canonicalize_url(raw["__posting_url"])  (already tenant-prefixed)
      posted_date:  raw["__posted_date_utc"]                (already resolved by adapter
                                                             across all 3 wire forms;
                                                             defensive: if it round-tripped
                                                             through JSON as an ISO string,
                                                             reparse)

    The Workday CXS jobs endpoint does NOT return per-posting description text,
    so `experience_min` / `experience_max` are left None — JD-scan (FILT-03 in
    Plan 02-03) will look up description text separately if/when it lands.
    """
    raw = rp.raw
    dedup_key = raw["__dedup_key"]
    title = (raw.get("title") or "").strip()
    location = normalize_location((raw.get("locationsText") or "").strip())
    posting_url = canonicalize_url(raw.get("__posting_url") or "")
    # Adapter already resolved postedOn -> UTC datetime; just read it.
    # Defensive: if for some reason it's a string in raw (test fixture round-trip
    # via JSON could turn datetime -> ISO string), reparse.
    posted_date = raw.get("__posted_date_utc")
    if isinstance(posted_date, str):
        posted_date = _parse_iso_to_utc(posted_date)

    # FILT-03 JD-scan (CONTEXT.md D-02 — display-only; never gates inclusion).
    # Workday CXS /jobs endpoint doesn't return description text per-posting,
    # so this is usually empty string → (None, None). The hook is wired so
    # a future enhancement that stashes raw["__description"] (e.g., from a
    # per-posting detail fetch) starts populating Experience automatically.
    exp_min, exp_max = extract_experience_range(_read_workday_description(raw))

    # D-01 — Workday CXS /jobs endpoint does not expose salary; intentionally
    # empty. Future per-posting detail fetch could stash raw["__salary"]
    # (mirroring the Plan 02-03 __description hook).
    salary = ""

    company = rp.source_company
    if company.islower():
        company = company.capitalize()

    return Posting(
        dedup_key=dedup_key,
        company=company,
        title=title,
        location=location,
        salary=salary,
        experience_min=exp_min,
        experience_max=exp_max,
        posting_url=posting_url,
        posted_date=posted_date,
        first_seen=run_started_at,
        last_seen=run_started_at,
        still_listed=True,
        source_adapter=rp.source_adapter,
    )


def _normalize_greenhouse(rp: RawPosting, run_started_at: datetime) -> Posting:
    """Greenhouse-specific normalization.

    Salary + experience extraction is deferred to Phase 2/4. Phase 1 emits None
    for both fields (the filter's FILT-05 ambiguous-bias means this is still useful).
    """
    raw = rp.raw
    # Adapter (Plan 01) guaranteed __dedup_key is present.
    dedup_key = raw["__dedup_key"]
    title = (raw.get("title") or "").strip()
    location = normalize_location(
        ((raw.get("location") or {}).get("name") or "").strip(),
    )
    posting_url = canonicalize_url(raw.get("absolute_url") or "")
    posted_date = _parse_iso_to_utc(raw.get("updated_at"))

    # FILT-03 JD-scan (CONTEXT.md D-02 — display-only; never gates inclusion).
    # Greenhouse `content` is HTML; the JD-scan regex bounds at 5000 chars
    # and matches on plaintext substrings inside HTML tags fine (years/range
    # patterns are anchored on \b word boundaries — HTML angle brackets won't
    # interfere).
    exp_min, exp_max = extract_experience_range(
        _read_greenhouse_description(raw),
    )

    # D-01 — salary verbatim from raw["metadata"] (see _extract_greenhouse_salary).
    salary = _extract_greenhouse_salary(raw)

    company = rp.source_company
    # Cosmetic: title-case if the board token came in lowercase ("stripe" -> "Stripe").
    if company.islower():
        company = company.capitalize()

    return Posting(
        dedup_key=dedup_key,
        company=company,
        title=title,
        location=location,
        salary=salary,
        experience_min=exp_min,
        experience_max=exp_max,
        posting_url=posting_url,
        posted_date=posted_date,
        first_seen=run_started_at,
        last_seen=run_started_at,
        still_listed=True,
        source_adapter=rp.source_adapter,
    )


def _slugify(text: str) -> str:
    """Lowercase + replace runs of non-alphanumerics with single hyphen.

    Defensive helper for constructing Apple posting URLs when the response
    omits `transformedPostingTitle`. Caps length at 80 chars.
    """
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:80]


def _normalize_apple(rp: RawPosting, run_started_at: datetime) -> Posting:
    """Apple-specific normalization (ADP-08).

    Per CONTEXT.md D-01a + <apple_adapter_specifications> in 02-03-PLAN.md:
      title:        coalesce(raw["postingTitle"], raw["title"])
      location:     ", ".join(loc["name"] for loc in raw["locations"])
      posting_url:  canonicalize_url(
                       f"https://jobs.apple.com/en-us/details/{positionId}/{slug}")
                    where slug = raw["transformedPostingTitle"] or slugify(title)
      posted_date:  _parse_iso_to_utc(coalesce(raw["postingDate"],
                                               raw["postDateInGMT"]))

    Dedup key is `apple:<positionId>` (NO per-company prefix per D-01a) —
    already stashed in raw["__dedup_key"] by the adapter.

    Plan 02-03 Task 2 wires extract_experience_range into all 6 helpers; this
    Task 1 commit leaves experience_min/max=None (Task 2's diff is purely
    additive — replaces the None literals with extract_experience_range call).
    """
    raw = rp.raw
    dedup_key = raw["__dedup_key"]
    # Coalesce title — Apple response sometimes uses `postingTitle`, sometimes
    # `title`. First non-empty wins.
    title = (raw.get("postingTitle") or raw.get("title") or "").strip()

    # Compose location from list of {"name": "..."} entries, THEN normalize
    # (per Plan 04-01 Task 2 — compose first, normalize the composed string).
    locations = raw.get("locations") or []
    loc_names: list[str] = []
    if isinstance(locations, list):
        for loc in locations:
            if isinstance(loc, dict):
                nm = (loc.get("name") or "").strip()
                if nm:
                    loc_names.append(nm)
    location = normalize_location(", ".join(loc_names))

    # Construct posting URL from positionId + slug (Apple doesn't return a
    # fully-formed URL — we build it).
    position_id = raw.get("__position_id", "")
    slug = (
        raw.get("transformedPostingTitle")
        or _slugify(title)
        or "details"
    )
    posting_url_raw = (
        f"https://jobs.apple.com/en-us/details/{position_id}/{slug}"
    )
    posting_url = canonicalize_url(posting_url_raw)

    # Coalesce postingDate / postDateInGMT — both ISO-8601 strings.
    posted_raw = raw.get("postingDate") or raw.get("postDateInGMT")
    posted_date = _parse_iso_to_utc(posted_raw)

    # FILT-03 JD-scan (CONTEXT.md D-02 — display-only; never gates inclusion).
    exp_min, exp_max = extract_experience_range(_read_apple_description(raw))

    # D-01 — Apple's response shape drifts; try the three known shapes in order
    # per CONTEXT.md D-01 (postingPay.payRange.text, then top-level salaryRange,
    # then homeOffice). First non-empty wins. Defensive against postingPay: None
    # / non-dict.
    posting_pay = raw.get("postingPay") or {}
    pay_range = (
        posting_pay.get("payRange") if isinstance(posting_pay, dict) else None
    ) or {}
    salary = (
        (pay_range.get("text") if isinstance(pay_range, dict) else None)
        or raw.get("salaryRange")
        or raw.get("homeOffice")
        or ""
    )

    company = rp.source_company
    if company.islower():
        company = company.capitalize()

    return Posting(
        dedup_key=dedup_key,
        company=company,
        title=title,
        location=location,
        salary=salary,
        experience_min=exp_min,
        experience_max=exp_max,
        posting_url=posting_url,
        posted_date=posted_date,
        first_seen=run_started_at,
        last_seen=run_started_at,
        still_listed=True,
        source_adapter=rp.source_adapter,
    )


def _normalize_playwright(rp: RawPosting, run_started_at: datetime) -> Posting:
    """Playwright generic normalization (ADP-09 — Phase 3 Plan 03-02).

    The Playwright adapter emits a tolerant raw shape (XHR or DOM origin):
      title:        raw["title"]
      location:     raw["location"] (may be empty)
      posting_url:  canonicalize_url(raw["posting_url"])
      posted_date:  coalesce raw["postingDate"], raw["postedAt"],
                    raw["created_at"], raw["publishedAt"] (any ISO-8601 form)
      description:  raw["description"] → JD-scan via _read_playwright_description

    Per CONTEXT.md D-01c (catch-all): the raw shape is intentionally
    generic — sites that prove worth their own adapter (per ADP-14) move
    out of Playwright and into a dedicated module.
    """
    raw = rp.raw
    dedup_key = raw["__dedup_key"]
    title = (raw.get("title") or "").strip()
    location = normalize_location((raw.get("location") or "").strip())
    posting_url = canonicalize_url(raw.get("posting_url") or "")
    # Coalesce common date field names across SPA sites.
    posted_raw = (
        raw.get("postingDate")
        or raw.get("postedAt")
        or raw.get("created_at")
        or raw.get("publishedAt")
    )
    posted_date = _parse_iso_to_utc(posted_raw)

    # FILT-03 JD-scan (CONTEXT.md D-02 — display-only; never gates inclusion).
    exp_min, exp_max = extract_experience_range(
        _read_playwright_description(raw),
    )

    # D-01 — salary verbatim. Best-effort per D-01 note: when XHR/DOM extraction
    # captured a salary string, use it; otherwise "".
    salary = raw.get("salary") or ""

    company = rp.source_company
    if company.islower():
        company = company.capitalize()

    return Posting(
        dedup_key=dedup_key,
        company=company,
        title=title,
        location=location,
        salary=salary,
        experience_min=exp_min,
        experience_max=exp_max,
        posting_url=posting_url,
        posted_date=posted_date,
        first_seen=run_started_at,
        last_seen=run_started_at,
        still_listed=True,
        source_adapter=rp.source_adapter,
    )


def _normalize_oraclehcm(
    rp: RawPosting, run_started_at: datetime
) -> Posting:
    """Normalize an Oracle HCM Fusion requisition raw posting (Bug F)."""
    raw = rp.raw
    dedup_key = raw["__dedup_key"]
    title = (raw.get("Title") or "").strip()
    location = normalize_location((raw.get("PrimaryLocation") or "").strip())
    posting_url = canonicalize_url(raw.get("__posting_url") or "")
    posted_raw = raw.get("PostedDate")  # ISO-8601 date like "2026-06-08"
    posted_date = _parse_iso_to_utc(posted_raw)
    exp_min, exp_max = extract_experience_range(
        raw.get("ShortDescriptionStr") or ""
        + " "
        + (raw.get("ExternalQualificationsStr") or "")
        + " "
        + (raw.get("ExternalResponsibilitiesStr") or "")
    )
    company = rp.source_company
    if company.islower():
        company = company.capitalize()
    return Posting(
        dedup_key=dedup_key,
        company=company,
        title=title,
        location=location,
        salary="",
        experience_min=exp_min,
        experience_max=exp_max,
        posting_url=posting_url,
        posted_date=posted_date,
        first_seen=run_started_at,
        last_seen=run_started_at,
        still_listed=True,
        source_adapter=rp.source_adapter,
    )


_DISPATCH = {
    "greenhouse": _normalize_greenhouse,
    "lever": _normalize_lever,
    "ashby": _normalize_ashby,
    "smartrecruiters": _normalize_smartrecruiters,
    "workday": _normalize_workday,
    "apple": _normalize_apple,
    "oraclehcm": _normalize_oraclehcm,
    "playwright": _normalize_playwright,  # Phase 3 Plan 03-02 — catch-all SPA
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
