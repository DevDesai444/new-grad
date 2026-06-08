"""Orchestrator entry point — `python -m src.main`.

ARCHITECTURE.md §Pattern 2 (per-company try/except isolation).
RUN-01: single run_started_at captured here, threaded everywhere downstream.
RUN-02: run summary to stdout + $GITHUB_STEP_SUMMARY.
ADP-12: per-company errors are logged + isolated, never abort the whole run.
Pitfall 17: NEVER format full tracebacks — exception attributes may carry
            request headers (Authorization tokens, cookies). Log type + str only.

Exit codes:
    0  success (run completed; sanity gate passed; commit-back may or may not happen)
    1  SanityGateAborted (state + README NOT written; investigate before next run)
    2  UnknownSchemaVersion on load (forward-incompatible seen.json)

Per-company errors NEVER cause non-zero exit (ADP-12).
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.adapters.base import (
    InvalidCredential,
    MissingCredential,
    PlaywrightTimeout,
    SchemaDrift,
    SiteBlocked,
)
from src.config_loader import load_companies
from src.filter import is_early_career, is_us_location_acceptable
from src.models import CompanyConfig, Posting
from src.normalizer import normalize
from src.registry import NoAdapterFound, get_adapter
from src.renderer import write_readme
from src.state_merger import merge_state
from src.state_store import (
    SanityGateAborted,
    UnknownSchemaVersion,
    load_state,
    sanity_gate,
    save_state_atomic,
)
from src.url_resolver import resolve_url

# Use stdlib logging — GitHub Actions captures stdout/stderr.
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, stream=sys.stdout)
logger = logging.getLogger("scan")


def _scrape_one(
    company: CompanyConfig,
    run_started_at: datetime,
) -> tuple[list[Posting], str]:
    """Fetch + normalize + filter for one company.

    Returns (filtered_postings, outcome) where outcome is one of:
      "ok"           — fetch + normalize succeeded; postings may be empty.
      "blocked"      — SiteBlocked; orchestrator routes to any_blocked=True.
      "no-adapter"   — NoAdapterFound; CFG-05 skip path.
      "error: <Cls>" — anything else (SchemaDrift, MissingCredential,
                       InvalidCredential, PlaywrightTimeout, generic).

    ADP-12 + Pitfall 17 — never re-raises; never logs request headers; never
    formats a full traceback (could leak Authorization headers or cookies).
    """
    # Step 1: resolve adapter.
    try:
        adapter = get_adapter(company)
    except NoAdapterFound as e:
        # CFG-05 — log + skip; not an error condition in Phase 1.
        logger.info("scrape:%s no adapter (CFG-05 skip): %s", company.name, e)
        return [], "no-adapter"

    # Step 2: fetch raw postings.
    try:
        raw_postings = adapter.fetch(company)
    except SiteBlocked as e:
        logger.warning("scrape:%s SiteBlocked: %s", company.name, e)
        return [], "blocked"
    except (
        SchemaDrift, PlaywrightTimeout, MissingCredential, InvalidCredential,
    ) as e:
        logger.error("scrape:%s %s: %s", company.name, type(e).__name__, e)
        return [], f"error: {type(e).__name__}"
    except Exception as e:
        # ADP-12 + Pitfall 17 — log class + str(e) ONLY. Never the full traceback
        # which could include request headers / response bodies / auth tokens.
        logger.error("scrape:%s generic %s: %s", company.name, type(e).__name__, e)
        return [], f"error: {type(e).__name__}"

    # Step 3: normalize + filter each posting (one-bad-posting isolation).
    # Filter order per Phase 4 CONTEXT.md D-03a:
    #   is_early_career (FILT-01/02 title gate)
    #     → is_us_location_acceptable (FILT-07 US-only region gate)
    #       → state merge.
    # Dropped non-US postings are NEVER stored in seen.json (STATE-04's
    # "never delete" still applies to entries already stored before
    # FILT-07 shipped — see CONTEXT.md D-03a).
    postings: list[Posting] = []
    for rp in raw_postings:
        try:
            p = normalize(rp, run_started_at)
        except Exception as e:
            logger.warning(
                "scrape:%s normalize failed for one posting (%s): %s",
                company.name, type(e).__name__, e,
            )
            continue
        if not is_early_career(p):
            continue  # FILT-01/02 title-keyword gate.
        if not is_us_location_acceptable(p):
            # FILT-07 — log + drop. INFO not WARNING: a non-US posting is
            # not a bug; it's correctly filtered. The log line makes the
            # filter behavior visible in Actions logs so the user can
            # verify drops without instrumenting.
            logger.info(
                "scrape:%s drop FILT-07 non-US: %s (%s)",
                company.name, p.title, p.location,
            )
            continue
        postings.append(p)
    return postings, "ok"


def _compute_summary(
    prior: dict,
    merged: dict,
    outcomes: dict[str, str],
) -> dict[str, Any]:
    """RUN-02 / RUN-04 — compute counts for the run summary line."""
    prior_keys = set(prior.get("postings", {}).keys())
    merged_postings = merged.get("postings", {})
    merged_keys = set(merged_postings.keys())

    new_keys = merged_keys - prior_keys

    # "Closed" = was still_listed=True in prior, is still_listed=False in merged.
    closed = 0
    for key, rec in merged_postings.items():
        if not rec.get("still_listed", False) and key in prior_keys:
            prior_rec = prior["postings"].get(key, {})
            if prior_rec.get("still_listed", True) is True:
                closed += 1

    open_count = sum(1 for r in merged_postings.values() if r.get("still_listed", False))

    new_by_company: dict[str, int] = {}
    for key in new_keys:
        co = merged_postings[key].get("company", "?")
        new_by_company[co] = new_by_company.get(co, 0) + 1

    return {
        "new_count": len(new_keys),
        "closed_count": closed,
        "open_count": open_count,
        "new_by_company": new_by_company,
        "outcomes": outcomes,
    }


def _emit_summary(summary: dict[str, Any]) -> str:
    """Format the summary as Markdown and emit to stdout + $GITHUB_STEP_SUMMARY.

    Returns the formatted text (useful for tests and the post-step commit
    message in the workflow).
    """
    new_co = summary["new_by_company"]
    new_str = ", ".join(f"{co} ({n})" for co, n in sorted(new_co.items()))
    lines = [
        "## Scan summary",
        "",
        f"- **+{summary['new_count']} new**"
        + (f" ({new_str})" if new_str else ""),
        f"- **{summary['closed_count']} closed**",
        f"- **{summary['open_count']} total open**",
    ]
    if summary.get("aborted"):
        lines.append(f"- **ABORTED**: {summary['aborted']}")
    lines += [
        "",
        "### Per-company outcomes",
        "",
        "| Company | Outcome |",
        "| --- | --- |",
    ]
    for co, outcome in sorted(summary["outcomes"].items()):
        lines.append(f"| {co} | {outcome} |")
    text = "\n".join(lines)
    print(text)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        try:
            with open(step_summary, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError as e:
            logger.warning("could not write GITHUB_STEP_SUMMARY: %s", e)
    return text


def main(
    companies_path: Path = Path("companies.txt"),
    state_path: Path = Path("seen.json"),
    readme_path: Path = Path("README.md"),
) -> int:
    """Orchestrator entry point.

    Exit codes:
        0 — success
        1 — SanityGateAborted (state + README NOT written)
        2 — UnknownSchemaVersion on load_state
    """
    # RUN-01 — single canonical clock for the entire run.
    # Note: `timezone.utc` is used here (not `datetime.UTC`) because the plan's
    # acceptance criteria require this literal substring. Behavior is identical.
    run_started_at = datetime.now(timezone.utc)  # noqa: UP017
    logger.info("scan starting at %s UTC", run_started_at.isoformat())

    # Load prior state first so an UnknownSchemaVersion never lets us silently
    # overwrite a forward-incompatible seen.json.
    try:
        prior = load_state(state_path)
    except UnknownSchemaVersion as e:
        logger.error("UnknownSchemaVersion — refusing to run: %s", e)
        return 2

    companies = load_companies(companies_path)
    logger.info("loaded %d companies from %s", len(companies), companies_path)

    all_fresh: list[Posting] = []
    outcomes: dict[str, str] = {}
    any_blocked = False
    for company in companies:
        # Plan 03-01 (CONTEXT.md D-01b): pre-flight resolve to handle the
        # CNAME→Workday case (~18 of 31 user URLs). resolve_url's contract is
        # no-raise (returns original on any error), but wrap defensively per
        # Pitfall 1 / one-bad-line isolation discipline — if a future bug
        # causes a raise, log + continue with original URL.
        try:
            company.resolved_url = resolve_url(company.url)
            if company.resolved_url != company.url:
                logger.info(
                    "resolve:%s %s -> %s",
                    company.name, company.url, company.resolved_url,
                )
        except Exception as e:
            # Defense in depth — Pitfall 17: log class name only.
            logger.warning(
                "resolve:%s unexpected %s — using original url",
                company.name, type(e).__name__,
            )
            company.resolved_url = None

        fresh, outcome = _scrape_one(company, run_started_at)
        outcomes[company.name] = outcome
        if outcome == "blocked":
            any_blocked = True
        all_fresh.extend(fresh)
        logger.info(
            "scrape:%s outcome=%s postings=%d",
            company.name, outcome, len(fresh),
        )

    merged = merge_state(prior, all_fresh, run_started_at)

    # STATE-06 / D-06 — sanity gate before any disk write.
    # "new_count" for the gate is the count of postings that are still_listed=True
    # in merged — i.e., the visible-postings count. If a mass-block drops this
    # below 0.9x prior, abort.
    prior_count = len(prior.get("postings", {}))
    still_listed_count = sum(
        1 for r in merged.get("postings", {}).values() if r.get("still_listed", False)
    )
    try:
        sanity_gate(prior_count, still_listed_count, any_blocked)
    except SanityGateAborted as e:
        logger.error(
            "SANITY GATE ABORTED — NOT writing state or README: %s", e,
        )
        # Emit a partial summary so the failure surfaces in step summary too.
        partial_summary = _compute_summary(prior, merged, outcomes)
        partial_summary["aborted"] = str(e)
        _emit_summary(partial_summary)
        return 1

    save_state_atomic(merged, state_path)
    write_readme(merged, readme_path, run_started_at)

    summary = _compute_summary(prior, merged, outcomes)
    _emit_summary(summary)
    logger.info("scan complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
