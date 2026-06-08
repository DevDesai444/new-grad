---
phase: 02-ats-breadth-jd-scan
plan: 03
subsystem: adapters + filter + retroactive-tests
tags: [adapter, apple, jd-scan, regex, filter, experience-range, pagination, early-termination, requirements-edit, d-02-softening]

requires:
  - phase: 02-01
    provides: Lever/Ashby/SmartRecruiters adapters + normalizer dispatch + registry append-only contract
  - phase: 02-02
    provides: Workday adapter + D-04 pagination pattern (early-termination + 25-page cold-start cap + sort-monotonicity sanity check)
  - phase: 01
    provides: Adapter ABC + typed exceptions + Greenhouse adapter (now retroactively completes its D-03 error-path coverage)

provides:
  - Apple Jobs adapter (ADP-08) with D-04 pagination
  - JD-scan extraction layer (FILT-03) — extract_experience_range pure function
  - 6-normalizer JD-scan wire-up (greenhouse + lever + ashby + smartrecruiters + workday + apple)
  - is_early_career simplification per CONTEXT.md D-02 (title-gate-only; FILT-04 experience clause REMOVED)
  - Retroactive Greenhouse D-03 error-path tests (closes Phase 1 W-1 / D-07 debt)
  - REQUIREMENTS.md FILT-04 strikethrough with D-02 footnote

affects: [phase-03-playwright-fallback, phase-04-salary-source-health]

tech-stack:
  added: []   # No new deps — uses existing httpx, respx, pydantic, pytest
  patterns:
    - Single-org dedup-key format (`apple:<id>`) — first adapter without per-company prefix (D-01a)
    - Bounded-input pure-function regex extraction (5000-char cap mitigates T-02-03-03 catastrophic backtracking)
    - Per-adapter description reader helpers (_read_<adapter>_description) — centralizes source-specific JD path
    - REQUIREMENTS.md strikethrough convention (~~**ID**~~ + footnote → CONTEXT.md reference) — matches Phase 1 INFRA-05 precedent

key-files:
  created:
    - src/adapters/apple.py
    - tests/fixtures/apple_sample.json
    - tests/test_apple_adapter.py
  modified:
    - src/filter.py
    - src/normalizer.py
    - src/registry.py
    - tests/test_filter.py
    - tests/test_normalizer.py
    - tests/test_greenhouse_adapter.py
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Apple dedup key has NO per-company prefix (`apple:<positionId>` not `apple:apple:<positionId>`) — single-org ATS per CONTEXT.md D-01a. Locked by test_apple_dedup_key_has_no_company_prefix regex `^apple:[^:]+$`."
  - "is_early_career simplified to title-gate-only per D-02 — JD-scan output is display-only and never gates inclusion. Phase 1 FILT-04 clause removed; the Phase 1 test that asserted the old behavior was rewritten as the D-02 invariant test."
  - "REQUIREMENTS.md FILT-04 strikethrough preserves the [x] checkbox — the Phase 1 implementation literally satisfied it; the softening is a SEMANTIC change documented in the footnote, not an unship."
  - "Apple sort-monotonicity violation logs WARNING + suppresses early-termination for the rest of the run (degrades to cap-only) — same pattern as Workday from Plan 02-02."
  - "Workday __description field is read by _read_workday_description; current Workday CXS /jobs endpoint does NOT return per-posting description, so JD-scan yields (None, None) for Workday. The hook is wired so a future per-posting detail fetch starts populating Experience automatically with zero normalizer changes."

patterns-established:
  - "extract_experience_range precedence: numeric range > open-min (X+ years) > entry signals (entry-level / recent graduate / no experience required / new grad). First match wins per pattern; precedence is enforced by ordering the searches."
  - "Per-adapter description readers (one helper per adapter in src/normalizer.py) — keeps the JD-scan wire-up in each helper to one line: `exp_min, exp_max = extract_experience_range(_read_<adapter>_description(raw))`. Future schema changes inside a single adapter's response shape touch only that adapter's reader."
  - "Retroactive D-03 test convention: source adapter code UNCHANGED; tests target the existing error ladder. The 4 new Greenhouse tests + the 2 existing Phase 1 smoke tests now match the 6-test set shipped with the 5 newer adapters in Plans 02-01 and 02-02."

requirements-completed:
  - ADP-08
  - FILT-03

# Metrics
duration: ~30min
completed: 2026-06-08
---

# Phase 2 Plan 02-03: Apple Adapter + JD-Scan + Retroactive Greenhouse D-03 Tests Summary

**Apple Jobs adapter with D-04 pagination (early-termination + 25-page cold-start cap), JD-scan regex extraction populating Experience column across all 6 adapters, is_early_career simplification per CONTEXT.md D-02 (title-gate-only), 4 retroactive Greenhouse D-03 error-path tests closing Phase 1 W-1/D-07 debt, and REQUIREMENTS.md FILT-04 strikethrough — Phase 2 execute-complete with all 6 REQ-IDs closed.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-08T08:14:00Z (approximate)
- **Completed:** 2026-06-08T08:25:00Z (approximate)
- **Tasks:** 3 (TDD: tests written and failing before each implementation step)
- **Files modified:** 10 (3 created + 7 modified)
- **Cumulative tests:** 298 (249 baseline + 49 new across 3 tasks)

## Accomplishments

- **Apple adapter (ADP-08) closed end-to-end.** New `src/adapters/apple.py` matches any `jobs.apple.com` URL (subpath ignored — single-org ATS per D-01a), POSTs `https://jobs.apple.com/api/role/search`, coalesces `results`/`searchResults` and `id`/`positionId` shapes, implements D-04 pagination with newest-first sort + early-termination on `seen_keys` overlap + 25-page cold-start cap + sort-monotonicity sanity fallback. Dedup key format is `apple:<positionId>` with NO per-company prefix (other adapters: `<ats>:<company>:<id>`).
- **JD-scan extraction (FILT-03) closed end-to-end.** `extract_experience_range(description)` in `src/filter.py` is a pure function returning `(experience_min, experience_max)` from job-description text — handles numeric ranges (`X-Y years`, `X to Y years`, en-dash and em-dash variants), open-min (`X+ years`), and entry signals (`entry-level` / `recent graduate` / `no experience required` / `new grad`). Caps input at 5000 chars to mitigate T-02-03-03 (regex catastrophic backtracking). All 6 per-adapter normalizers (greenhouse, lever, ashby, smartrecruiters, workday, apple) now call this on the source-specific description field and populate `Posting.experience_min`/`experience_max`.
- **D-02 display-only invariant locked.** `is_early_career(posting)` simplified to title-gate-only — the Phase 1 FILT-04 `experience_min > 5 → reject` clause is removed. A posting titled "Software Engineer, New Grad" with description "5+ years required" is now KEPT in the table with `experience_min=5` displayed in the Experience column. Test `test_is_early_career_ignores_experience_min_per_d02` locks this. The body of `is_early_career` contains zero references to `experience_min`.
- **Retroactive Greenhouse D-03 error-path tests landed.** 4 new tests appended to `tests/test_greenhouse_adapter.py` (wrong jobs type, 429, 5xx, generic propagation) — Greenhouse now has parity D-03 6-test set with the 5 newer adapters. `src/adapters/greenhouse.py` is intentionally unchanged. Phase 1 W-1 plan-checker warning and D-07 deferred-test debt formally closed.
- **REQUIREMENTS.md FILT-04 strikethrough with D-02 footnote.** Matches Phase 1 INFRA-05 precedent — strike-through syntax `~~**FILT-04**~~` is git-diff-visible and Markdown-renderer-visible; explicit footnote points to `.planning/phases/02-ats-breadth-jd-scan/02-CONTEXT.md D-02`.
- **Phase 2 execute-complete.** All 6 phase REQ-IDs closed (ADP-04, ADP-05, ADP-06, ADP-07, ADP-08, FILT-03). companies.txt accepts URLs from any of 6 ATSes; the hourly orchestrator scrapes them all and populates the Experience column per FILT-03/D-02; per-company isolation (ADP-12) holds.

## Task Commits

Each task was committed atomically (one commit per task, TDD steps batched per the project's outer-cadence convention established in Phase 1):

1. **Task 1: Apple adapter + D-04 pagination + normalizer dispatch + fixture + 16 tests** — `589f1da` (feat)
2. **Task 2: JD-scan (FILT-03) + wire all 6 normalizers + D-02 filter simplification + REQUIREMENTS.md FILT-04 strikethrough** — `c44f910` (feat)
3. **Task 3: Retroactive Greenhouse D-03 error-path tests** — `efba667` (test)

## Files Created/Modified

**Created:**
- `src/adapters/apple.py` — `AppleAdapter` with D-04 pagination (Apple Jobs API; single-org dedup key)
- `tests/fixtures/apple_sample.json` — synthetic 5-posting fixture (3 valid + 1 senior-reject + 1 malformed-skipped)
- `tests/test_apple_adapter.py` — 16 tests (matches() / D-03 6-test set / pagination including sort-monotonicity)

**Modified:**
- `src/filter.py` — `extract_experience_range` added; `is_early_career` simplified per D-02
- `src/normalizer.py` — 6 description-reader helpers added; all 6 per-adapter normalizers wire JD-scan; `_normalize_apple` + `_slugify` added; `_DISPATCH` extended with `apple` key
- `src/registry.py` — `AppleAdapter` import + ADAPTERS append (6th and final Phase 2 adapter)
- `tests/test_filter.py` — Phase 1 FILT-04 ceiling tests replaced with D-02 invariant test; 18 new JD-scan tests
- `tests/test_normalizer.py` — 8 JD-scan integration tests (one per adapter; Workday gets two: absent vs stashed `__description`)
- `tests/test_greenhouse_adapter.py` — 4 new D-03 error-path tests (wrong jobs type, 429, 5xx, generic propagation)
- `.planning/REQUIREMENTS.md` — FILT-04 struck through with D-02 footnote; ADP-08 + FILT-03 marked complete in top section + traceability table

## Decisions Made

- **Apple dedup key has NO per-company prefix** (D-01a). The orchestrator passes `company.name = "Apple"`, but the dedup key is just `apple:<positionId>`. Locked by `test_apple_dedup_key_has_no_company_prefix` (regex `^apple:[^:]+$`).
- **`is_early_career` body contains zero `experience_min` references.** The Phase 1 FILT-04 ceiling clause was simply removed; the docstring documents the change but the live code is just `return _passes_title_gate(posting.title)`.
- **Phase 1 FILT-04 ceiling test replaced, not deleted.** The old test `test_experience_min_above_ceiling_overrides_title_pass` asserted Phase 1's now-removed behavior. It was rewritten as `test_is_early_career_ignores_experience_min_per_d02` asserting the D-02 invariant — same test slot, inverted assertion, explicit docstring pointing to CONTEXT.md.
- **REQUIREMENTS.md FILT-04 keeps the `[x]` checkbox.** The Phase 1 implementation literally satisfied FILT-04 as written. The softening is a SEMANTIC change documented via strikethrough + footnote, not an unship — same convention as Phase 1 INFRA-05.
- **Workday `__description` hook is wired even though the current CXS /jobs response doesn't expose description.** `_read_workday_description` reads `raw["__description"]`; current value is empty string → JD-scan returns `(None, None)`. A future per-posting detail fetch that stashes description starts populating Experience automatically with zero normalizer changes.
- **Apple sort-monotonicity violation: log WARNING + suppress early-termination, do NOT abort.** Mirrors Workday from Plan 02-02 — same tradeoff: completeness over speed when source sort ordering breaks.
- **Inter-page sleep monkeypatched to noop in slow tests** (`monkeypatch.setattr("src.adapters.apple.time.sleep", lambda s: None)`). Matches Workday's pattern; keeps `test_cold_start_25_page_cap` and `test_early_termination_on_seen_keys` under ~100ms in production keeps real sleep for rate-limit hedging.

## Deviations from Plan

None — plan executed exactly as written. The 49 new tests are distributed slightly across the 3 tasks vs the plan's per-task budget (16 + 29 + 4 actual vs the plan's "~16 + ~21 + 4" budget), but the totals match (49 ≥ plan's ≥22 floor, plus 29 covers the plan's ≥21 budget for Task 2 since the FILT-04 ceiling test was rewritten as the D-02 invariant test rather than deleted).

A minor note on TDD ordering: tests were written first within each task per the `tdd="true"` requirement on the task type, but the commit cadence is "one commit per task" matching the established Phase 1 / Plan 02-01 / Plan 02-02 convention rather than separate RED/GREEN commits. This was documented in STATE.md "Decisions Made During Execution" for Phase 1 / Plan 01-01 and carries forward.

## Issues Encountered

- **Phase 1 FILT-04 ceiling test failure after Task 2 wired the simplified is_early_career.** Expected per D-02. The fix was to rewrite the test as the D-02 invariant (`test_is_early_career_ignores_experience_min_per_d02` asserts `is_early_career(experience_min=7) is True`), not to revert the simplification. Captured as the first explicit Phase 2 deviation rule case but ultimately not a deviation — the plan explicitly called for this simplification (CONTEXT.md D-02 + Task 2 acceptance criterion `is_early_career body contains zero experience_min references`).
- **`commit -m` with HEREDOC failed on bash quoting due to apostrophes in the body ("Phase 1's INFRA-05").** Switched to `commit -F /tmp/task2_commit_msg.txt` for Tasks 2 and 3. No content lost; commits applied cleanly.

## User Setup Required

None — no external service configuration required. Apple Jobs API is public (no auth).

## Phase 2 Execute-Complete Summary

**All 6 Phase 2 REQ-IDs are closed:**

| REQ-ID  | Description                                                | Plan(s) |
|---------|------------------------------------------------------------|---------|
| ADP-04  | Lever adapter (`lever:<company>:<id>`)                     | 02-01   |
| ADP-05  | Ashby adapter (`ashby:<org>:<id>`)                         | 02-01   |
| ADP-06  | SmartRecruiters adapter (`sr:<company>:<id>`)              | 02-01   |
| ADP-07  | Workday adapter (`wd:<tenant>:<id>` + D-04 pagination)     | 02-02   |
| ADP-08  | Apple adapter (`apple:<id>` + D-04 pagination)             | 02-03   |
| FILT-03 | JD-scan extract_experience_range + 6-adapter wire-up       | 02-03   |

**Open-closed (ADP-14/15) re-proven across all 3 Phase 2 plans.** Zero edits to `src/main.py`, `src/models.py`, `src/state_store.py`, `src/state_merger.py`, `src/renderer.py`, `src/config_loader.py` across Plans 02-01 / 02-02 / 02-03. Each new adapter ships as a single file + a one-line registry append + a single normalizer dispatch entry. Each adapter file imports only `src.adapters.base` — no sibling cross-imports.

**Cumulative test growth across Phase 2:**

| After plan | Tests | Delta |
|------------|-------|-------|
| Phase 1 end | 187 | (baseline) |
| Plan 02-01 | 214 | +27 (Lever + Ashby + SmartRecruiters) |
| Plan 02-02 | 249 | +35 (Workday) |
| Plan 02-03 | 298 | +49 (Apple + JD-scan + retroactive Greenhouse) |

## Threat Flags

None — the new surface (Apple API, JD-scan regex, retroactive tests) is fully covered by the plan's `<threat_model>` register (T-02-03-01 through T-02-03-11). All `mitigate` dispositions are implemented and tested:

- T-02-03-01 (Apple schema drift) → `_extract_postings_array` coalesces `results`/`searchResults`; tested by SchemaDrift missing-keys + wrong-type cases.
- T-02-03-02 (Apple 403/429/5xx → SiteBlocked) → tested by 3 SiteBlocked cases.
- T-02-03-03 (regex DoS) → 5000-char cap; tested by `test_extract_truncation_caps_at_5000_chars`.
- T-02-03-04 (one-bad-posting) → `_extract_position_id` returns None for malformed; loop skips; tested by `test_fetch_skips_malformed_entries`.
- T-02-03-05 (header-leak in exception strings) → all SchemaDrift / SiteBlocked messages include adapter + company + observed-keys only.
- T-02-03-06 (sort-monotonicity violation) → logged WARNING + suppress early-term; tested by `test_sort_monotonicity_warning`.
- T-02-03-07 (false experience signal "founded in 2010") → ACCEPT per D-02 (display-only); negative test asserts no match.
- T-02-03-11 (REQUIREMENTS.md strikethrough discoverability) → strikethrough + footnote pointing to CONTEXT.md D-02 (grep-able + Markdown-renderer-visible).

## Next Phase Readiness

**Phase 2 is execute-complete.** Next steps:

1. **Verification gate:** `/gsd-verify-phase 2` (or equivalent) to formally verify all 6 REQ-IDs against the requirement statements and the Phase 2 ROADMAP success criteria.
2. **User go-live:** After Phase 2 verification, the user can add real URLs from any of the 6 supported ATSes to `companies.txt`. The hourly cron starts populating the README table with Experience-column data on the next run.
3. **Phase 3:** Playwright fallback adapter (ADP-09 / ADP-10) for ATSes not covered by the 6 HTTP adapters; credentialed adapters (SEC-01..06). The Apple adapter is the last HTTP-only adapter; Phase 3 introduces the Chromium dependency + playwright-stealth.

**Notes for future phases:**

- Workday `__description` populated by per-posting detail fetch is a natural Phase 4 enhancement (alongside salary extraction NORM-02 and Source Health OUT-09).
- Apple `api/role/search` body shape is locked here at MEDIUM-confidence per training data. If a future scan logs SchemaDrift from Apple, a live capture should be the first investigation step (see CONTEXT.md `<canonical_refs>` planner action item).

## Self-Check: PASSED

Verified after writing SUMMARY.md:
- `src/adapters/apple.py` exists (FOUND).
- `tests/fixtures/apple_sample.json` exists (FOUND).
- `tests/test_apple_adapter.py` exists (FOUND).
- Commit `589f1da` exists in `git log` (FOUND).
- Commit `c44f910` exists in `git log` (FOUND).
- Commit `efba667` exists in `git log` (FOUND).
- `pytest tests/ -q` exits 0 with 298 tests passing.
- `ruff check src/ tests/` exits 0.
- `python -c "from src.registry import ADAPTERS; assert len(ADAPTERS) == 6"` exits 0.
- `python -c "from src.normalizer import _DISPATCH; assert set(_DISPATCH.keys()) == {'greenhouse','lever','ashby','smartrecruiters','workday','apple'}"` exits 0.

---
*Phase: 02-ats-breadth-jd-scan*
*Plan 02-03 complete: 2026-06-08 — Phase 2 execute-complete (all 6 REQ-IDs closed)*
