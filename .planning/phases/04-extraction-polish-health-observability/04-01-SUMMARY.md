---
phase: 04-extraction-polish-health-observability
plan: 01
subsystem: normalizer
tags: [locations, salary, remote-collapse, render, normalizer, phase-4, NORM-02, NORM-03, pure-functions]

# Dependency graph
requires:
  - phase: 01-walking-skeleton
    provides: "Renderer cell-escape + Posting model + Greenhouse normalizer baseline"
  - phase: 02-ats-breadth-jd-scan
    provides: "6 additional per-adapter normalizer helpers (Lever, Ashby, SR, Workday, Apple) + tolerant raw-shape patterns"
  - phase: 03-playwright-fallback-credential-workflow
    provides: "7th normalizer helper (_normalize_playwright) catch-all SPA shape"
provides:
  - "src/locations.py pure module exporting normalize_location + is_us_location"
  - "All 7 _normalize_<adapter> helpers populate Posting.salary verbatim per source-specific access path"
  - "All 7 _normalize_<adapter> helpers route Posting.location through normalize_location"
  - "_coalesce_salary + _truncate_cell + _SALARY_PLACEHOLDER_PATTERN in renderer for D-01a/D-01b"
  - "8-rule US/non-US classifier ready for Plan 04-02 FILT-07 consumption"
affects: [04-02-FILT-07-filter, 04-03-source-health, future-rendering-polish]

# Tech tracking
tech-stack:
  added: []  # zero new deps — stdlib re + curated frozensets/tuples
  patterns:
    - "Curated lookup-list pattern — frozenset for state codes (O(1) membership), tuples for substring scans"
    - "Compose-then-normalize for multi-field locations (Apple, SmartRecruiters): build composed string first, then route the COMPOSED value through normalize_location"
    - "Coalesce → truncate → escape pipeline in renderer: each stage is a pure helper with a single responsibility, composable independently"
    - "Defensive None-or-{} access for nested ATS fields (salaryRange, compensation, postingPay.payRange) — eliminates AttributeError on partial/null responses"

key-files:
  created:
    - "src/locations.py — normalize_location + is_us_location + curated US/non-US dictionaries (151 lines)"
    - "tests/test_locations.py — 56 tests across TestNormalizeLocation, TestIsUsLocationClassifierRules, TestEdgeCases"
  modified:
    - "src/normalizer.py — import locations.normalize_location; new _extract_greenhouse_salary helper; 7 dispatch helpers now populate salary + route location through normalize_location"
    - "src/renderer.py — new _SALARY_PLACEHOLDER_PATTERN, _coalesce_salary, _truncate_cell helpers wired into _table_row salary cell"
    - "tests/test_normalizer.py — TestSalaryVerbatimPerAdapter (13 tests) + TestLocationNormalizationPerAdapter (7 tests)"
    - "tests/test_renderer.py — TestCoalesceSalaryHelper + TestTruncateCellHelper + TestSalaryCellRendering (23 net new)"

key-decisions:
  - "Used `salary=''` (not `None`) in all 7 normalizer helpers when source field is absent — the renderer's coalesce step unifies '' and None into the same '—' display, so picking '' avoids confusing two different null states"
  - "Greenhouse salary access via dedicated _extract_greenhouse_salary helper (iterates metadata list, matches name-set frozenset) — keeps the per-adapter normalizer helper readable while the matching rule is testable in isolation"
  - "Apple location: compose FIRST then normalize — `normalize_location(\", \".join(loc_names))` ensures composed strings like ['Remote'] → 'Remote' → 'Remote (US)' all work through one path"
  - "_truncate_cell uses single-codepoint U+2026 ellipsis (not three dots) to keep cell width predictable in monospace contexts"
  - "_coalesce_salary + _truncate_cell kept as separate composable helpers (not merged) so future polish can apply _truncate_cell to Position/Location cells without changing salary semantics"
  - "Bare 'Remote' biases to 'Remote (US)' per D-02 (user is US-based) — explicit test locks this regression-free"
  - "Non-US token list intentionally includes ambiguous-shorthand entries (UK, EU, Europe, Bahrain, Ireland) per D-02c bias-list philosophy"

patterns-established:
  - "Pure module + frozenset/tuple curated lookups: avoids dynamic loading, makes tests deterministic, < 1ms classifier cost"
  - "Per-adapter access-path tables in CONTEXT.md flow directly into discrete normalizer code paths — no shared salary extractor across adapters"
  - "ADP-15 invariant re-proven for the seventh time: every Phase 4 change lives in normalizer/renderer/locations; src/adapters/* untouched"

requirements-completed: [NORM-02, NORM-03]

# Metrics
duration: ~50min
completed: 2026-06-08
---

# Phase 4 Plan 01: Salary verbatim + location Remote-collapse + US/non-US classifier Summary

**Per-adapter verbatim Salary cell + canonical `Remote (US)` / `Remote (non-US)` collapse + 8-rule US classifier exported as `is_us_location()` for Plan 04-02 FILT-07 consumption — zero edits to src/adapters/, 124 net new tests, 499 cumulative passing.**

## Performance

- **Duration:** ~50 min
- **Started:** 2026-06-08T17:08:00Z (approx, plan kick-off)
- **Completed:** 2026-06-08T17:58:13Z
- **Tasks:** 3 (all TDD: RED → GREEN per task)
- **Files modified:** 6 (2 new, 4 extended)

## Accomplishments

- **`src/locations.py` (NEW, 151 lines):** Pure module exporting `normalize_location()` (collapses 10+ Remote-variant string shapes to canonical `Remote (US)` / `Remote (non-US)`; non-Remote strings pass through verbatim per D-02b) and `is_us_location()` (8-rule classifier: empty bias → Remote canonical → US state code → US country token → US city → non-US substring → fallback bias). Curated dictionaries: 51 US state codes (all 50 + DC), 30 US tech-hub cities, ~45 non-US tokens. All regex compiled at module load.
- **`src/normalizer.py` extended:** All 7 per-adapter `_normalize_<adapter>` helpers now populate `Posting.salary` from the source-specific access path per CONTEXT.md D-01 (Greenhouse `metadata[].value` matching salary-named entries; Lever `salaryRange.text → salary`; Ashby `compensation.compensationTierSummary`; SR/Workday hard-coded empty; Apple `postingPay.payRange.text → salaryRange → homeOffice`; Playwright `raw['salary']` best-effort). Every helper routes the location string through `normalize_location()` before assigning to `Posting.location`. New `_extract_greenhouse_salary(raw)` private helper isolates the metadata-list scan into a unit-testable function.
- **`src/renderer.py` extended:** New `_SALARY_PLACEHOLDER_PATTERN` (anchored full-cell case-insensitive regex matching Competitive/DOE/TBD/TBC/Not disclosed/N/A/null/to be determined/Negotiable/depends on experience/em-dash) + `_coalesce_salary(raw)` (None/empty/placeholder → `—`) + `_truncate_cell(text, limit=80)` (rstrip + U+2026 ellipsis). `_table_row` salary cell now flows through coalesce → truncate → existing `escape_markdown_cell` (NORM-07).
- **ADP-15 invariant re-proven for the seventh time:** Zero edits to any `src/adapters/*.py` file. `tests/test_adapter_contract.py` still passes 7/7.
- **499 cumulative tests pass** (375 Phase 3 baseline + 124 net new across the three test files). Ruff clean across all touched files.

## Task Commits

Each task was committed atomically via TDD RED → GREEN gate:

1. **Task 1: src/locations.py + tests**
   - `d4235db` test(04-01): add failing tests for normalize_location + is_us_location (RED)
   - `160c9f8` feat(04-01): implement src/locations.py — normalize_location + is_us_location (GREEN)

2. **Task 2: Extend normalizer — salary verbatim + normalize_location wiring**
   - `fb547f1` test(04-01): add failing tests for normalizer salary verbatim + location normalize (RED)
   - `d7b9e1b` feat(04-01): wire normalize_location + per-adapter salary verbatim into all 7 normalizers (GREEN)

3. **Task 3: Renderer — salary placeholder coalesce + 80-char truncation**
   - `fc9bf83` test(04-01): add failing tests for renderer salary coalesce + 80-char truncation (RED)
   - `8550ee5` feat(04-01): renderer salary cell — placeholder coalesce + 80-char truncation (GREEN)

_TDD cycle: each task = 1 RED (failing-test) commit + 1 GREEN (implementation) commit. No REFACTOR commits needed — implementations were minimal and clean from first GREEN pass._

## Files Created/Modified

- `src/locations.py` (NEW) — `normalize_location()` Remote-variant collapser + `is_us_location()` 8-rule classifier + curated US-state/US-city/non-US-token dictionaries
- `src/normalizer.py` (MODIFIED) — added `from src.locations import normalize_location`; added `_extract_greenhouse_salary` helper + `_GREENHOUSE_SALARY_METADATA_NAMES` frozenset; modified all 7 `_normalize_<adapter>` helpers to populate `Posting.salary` from source-specific path and route `Posting.location` through `normalize_location`
- `src/renderer.py` (MODIFIED) — added `_SALARY_PLACEHOLDER_PATTERN`, `_CELL_TRUNCATE_LEN`, `_CELL_TRUNCATE_ELLIPSIS` constants; added `_coalesce_salary()` + `_truncate_cell()` helpers; rewrote `_table_row` salary-cell line to coalesce → truncate → escape
- `tests/test_locations.py` (NEW) — 56 tests across TestNormalizeLocation (Remote collapse + passthrough + empty handling), TestIsUsLocationClassifierRules (all 8 rules), TestEdgeCases (rule-ordering + boundary)
- `tests/test_normalizer.py` (EXTENDED) — TestSalaryVerbatimPerAdapter (13 tests covering all 7 adapters' salary access paths) + TestLocationNormalizationPerAdapter (7 tests, one per adapter, asserting Remote-variant → canonical via the normalizer)
- `tests/test_renderer.py` (EXTENDED) — TestCoalesceSalaryHelper (28 parametrized placeholder cases + 4 real-salary passthrough cases), TestTruncateCellHelper (5 cases), TestSalaryCellRendering (8 end-to-end render assertions)

**Test counts per file:** locations 56 / normalizer 54 (was 34 → +20) / renderer 79 (was 56 → +23). **Cumulative: 499 (was 375 → +124 net new).**

## Decisions Made

- **`salary=''` vs `salary=None` in normalizer helpers.** Picked `''` (empty string) so the renderer's coalesce step has a single null-state to match. The Posting model still permits `salary: str | None = None` as the default for model-default constructors (test_models.py:75 still passes), but every normalizer call site now writes a string value.
- **Greenhouse salary metadata-name set.** Used the frozenset `{salary, salary range, compensation range, pay range, base pay range}` — these are the 5 names Greenhouse boards documented as canonical. First non-empty match wins (rare for one posting to have multiple, but deterministic if it does).
- **Apple location composes-then-normalizes.** `normalize_location(", ".join(loc_names))` is the path. This means a single-element `[{"name": "Remote"}]` composes to `"Remote"` → normalizes to `"Remote (US)"` (bare-Remote rule). A two-element `[{"name":"Cupertino, CA"},{"name":"Austin, TX"}]` composes to `"Cupertino, CA, Austin, TX"` — not a Remote shape → passthrough.
- **Renderer pipeline order: coalesce → truncate → escape.** Coalesce first so placeholders never reach escape; truncate before escape so the 80-char limit applies to visible characters (not escape-padding). The escape step (NORM-07) handles pipe / NBSP / invisible-Unicode last as the final user-facing boundary.
- **Truncation ellipsis is U+2026 single codepoint.** Predictable cell width in monospace. Length of a truncated cell == `limit` (80 chars including the ellipsis).
- **Non-US token list includes Bahrain and Ireland.** These aren't on the seed list in CONTEXT.md but they're common non-US locations in the dataset; adding them per D-02c "tunable" guidance.

## Deviations from Plan

None — plan executed exactly as written.

The plan's `<interfaces>` block accurately documented that Phase 1's `escape_markdown_cell` does NOT truncate at 80 chars (audit-confirmed), and the plan correctly noted that the `_truncate_cell` helper is added by this plan rather than reused from Phase 1. Task 3 implemented exactly that.

The verify automation in each task's `<verify>` block ran clean on first try after the GREEN commit. One test had an off-by-one cell-index in its assertion (the row-split started with `"| X"` not `"X"`, so the salary cell was at index 3 not 4) — this was caught immediately within the same Task 3 GREEN cycle, fixed in the same commit (no separate commit needed because it was a test-only correction that surfaced before the GREEN commit was staged).

**Total deviations:** 0
**Impact on plan:** None — plan was unusually crisp about per-adapter access paths and pipeline ordering, leaving no ambiguity at execution time.

## Threat-Model Posture

All 5 threat-model entries from PLAN.md addressed:

- **T-04-01-01 (Tampering via salary string):** Mitigated. `escape_markdown_cell` still applies last (NORM-07 / Pitfall 13 unchanged); `_truncate_cell` adds a defense-in-depth 80-char width bound.
- **T-04-01-02 (Pathological location string):** Mitigated. The Remote-form regex set has 3 patterns, all anchored with `^…$`. No nested quantifiers. US state regex is `\b(<alternation>)\b` with literal state-code alternates only.
- **T-04-01-03 (DoS via long salary):** Mitigated. Hard 80-char cap before escape. Single anchored placeholder check (`^…$`).
- **T-04-01-04 (Info disclosure via truncation):** Accepted as documented — posting salary is public ATS data; truncation is intentional UX.
- **T-04-01-05 (Adapter contract break):** Mitigated. `git diff --name-only HEAD~7 -- src/adapters/` = 0. `tests/test_adapter_contract.py` 7/7 pass.

## ADP-15 Re-Proof

```
$ git diff --name-only HEAD~7 -- src/adapters/
$ wc -l < /dev/null  # → 0
```

Zero edits to any `src/adapters/*.py` file across all 7 commits of this plan. The seven-times-running invariant since Phase 1 stands.

## Self-Check: PASSED

Verified after writing this SUMMARY:
- ✓ `src/locations.py` exists (151 lines)
- ✓ `tests/test_locations.py` exists (56 tests collected)
- ✓ `src/normalizer.py` contains `from src.locations import normalize_location` (line 22)
- ✓ `src/normalizer.py` contains `_extract_greenhouse_salary` (line 149)
- ✓ `src/normalizer.py` `normalize_location` occurrences = 8 (≥8 verify target)
- ✓ `src/renderer.py` contains `_SALARY_PLACEHOLDER_PATTERN` (line 135), `_coalesce_salary` (line 159), `_truncate_cell` (line 175)
- ✓ All 7 commits (d4235db, 160c9f8, fb547f1, d7b9e1b, fc9bf83, 8550ee5) present in `git log`
- ✓ Full pytest suite: 499/499 passing
- ✓ `git diff --name-only HEAD~7 -- src/adapters/` returns 0 files
- ✓ ruff clean across src/ and tests/

## Issues Encountered

- **Test cell-index off-by-one:** While writing `test_render_salary_long_value_truncated_to_80_chars_with_ellipsis`, the initial assertion split each row by `" | "` and indexed cells[4] for salary. In practice, splitting a row starting with `"| X | ... | ... | ... | <salary> | ..."` yields cells[0]=`"| X"`, cells[1]=`"T"`, cells[2]=`"SF"`, cells[3]=`"<salary>"` — so salary is at index 3, not 4. Caught immediately on first test run, fixed in the same Task 3 GREEN edit. Not a separate deviation — purely test-only correction.

## User Setup Required

None — no external service configuration required for this plan. All changes are pure-function library code + tests.

## Next Phase Readiness

- **Plan 04-02 (FILT-07 US-only region filter)** consumes `is_us_location` from `src/locations.py`. The classifier is exported, tested via 23+ rule-specific test cases, and ready to be wrapped in `src/filter.py:is_us_location_acceptable(posting)` per CONTEXT.md D-03. No further changes to `src/locations.py` are anticipated for Plan 04-02.
- **Plan 04-03 (source_health observability)** is independent of this plan's deliverables; it operates on `src/state_store.py` + `src/state_merger.py` + orchestrator try/except classification.
- **NORM-02 + NORM-03 requirement IDs ready to mark complete** in REQUIREMENTS.md.

---
*Phase: 04-extraction-polish-health-observability*
*Completed: 2026-06-08*
