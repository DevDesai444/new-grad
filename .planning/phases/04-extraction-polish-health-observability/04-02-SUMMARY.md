---
phase: 04-extraction-polish-health-observability
plan: 02
subsystem: filter
tags: [filter, us-only, filt-07, orchestrator, requirements-doc, phase-4, pure-functions]

# Dependency graph
requires:
  - phase: 04-extraction-polish-health-observability
    provides: "is_us_location() 8-rule classifier in src/locations.py (Plan 04-01)"
  - phase: 01-walking-skeleton
    provides: "src/filter.py pure-function pattern (is_early_career) + src/main.py _scrape_one orchestrator + Posting model"
  - phase: 02-ats-breadth-jd-scan
    provides: "Phase 2 D-02 simplification of is_early_career to title-only (FILT-04 strikethrough) — pattern for sequential filter passes"
provides:
  - "src/filter.py exports is_us_location_acceptable(posting: Posting) -> bool — pure wrapper over src.locations.is_us_location"
  - "src/main.py _scrape_one runs FILT-07 AFTER is_early_career and BEFORE state merge with INFO log line on each drop naming title + location"
  - ".planning/REQUIREMENTS.md gains FILT-07 as the 7th Filter entry + Traceability row + Coverage bumped 71→72 (7 FILT, Phase 4 = 4)"
  - "Doc-as-test invariant test_filt07_documented_in_requirements_md locks the 4 substring anchors against future doc rot"
affects: [04-03-source-health, future-region-filter-opt-out, multi-region-display]

# Tech tracking
tech-stack:
  added: []  # zero new deps — pure-function wrapper + import-only orchestrator wire
  patterns:
    - "Sequential filter passes — title-keyword gate then US-only region gate; each pass is a separate `if not ... continue` block with its own log line on drop"
    - "Doc-as-test for REQUIREMENTS.md invariants — substring-anchor assertions in tests/test_filter.py catch doc rot on next CI run (mirrors Phase 3 03-03 credential-flow doc invariants)"
    - "FILT-07 drop log is INFO not WARNING — a correctly-filtered non-US posting is not a bug; INFO makes filter behavior visible in Actions logs for user verification without polluting WARNING channel"

key-files:
  created:
    - ".planning/phases/04-extraction-polish-health-observability/04-02-SUMMARY.md (this file)"
  modified:
    - "src/filter.py — +1 import (is_us_location) + 18-line is_us_location_acceptable function + module-docstring FILT-07 note"
    - "src/main.py — extended is_early_career import + 18-line two-pass filter block in _scrape_one with FILT-07 INFO log line"
    - ".planning/REQUIREMENTS.md — FILT-07 added as 7th Filter bullet + Traceability row + Coverage block bumped (71→72, 6 FILT→7 FILT, Phase 4 = 3→4)"
    - "tests/test_filter.py — TestIsUsLocationAcceptable class (21 tests across parametrize + spot-check + determinism + bool-return) + test_filt07_documented_in_requirements_md doc invariant (22 net new tests)"
    - "tests/test_orchestrator.py — _TwoCityAdapter synthetic adapter + 3 net new integration tests (London-drop + SF-keep, log-line, US-keep regression)"

key-decisions:
  - "Doc-as-test test_filt07_documented_in_requirements_md lives in tests/test_filter.py (not a new tests/test_requirements_doc.py) — colocates the FILT-07 contract with the function tests; mirrors Phase 3 03-03 precedent of doc invariants alongside their feature tests"
  - "_TwoCityAdapter uses source_adapter='greenhouse' so existing _normalize_greenhouse dispatches — no new normalizer arm registered just for the integration test (saves churn; existing tolerant raw-shape handling covers the synthetic input)"
  - "FILT-07 drop logger.info uses format 'scrape:%s drop FILT-07 non-US: %s (%s)' (company, title, location) — matches the existing 'scrape:%s ...' pattern used elsewhere in _scrape_one; user can grep 'FILT-07' to see all region drops in one pass"
  - "Two-pass filter block uses `if not X: continue` form (not chained `and`) so each gate has its own short-circuit + its own log call on drop — makes drop reasons unambiguous in logs (no need to figure out which gate fired)"
  - "REQUIREMENTS.md FILT-07 entry checked as [x] (not [ ]) on first insertion since the implementation lands in the same plan — same pattern as Plan 04-01's NORM-02/NORM-03 closure annotations"
  - "Doc test uses Path(__file__).resolve().parent.parent for repo-root resolution — robust to test cwd (pytest's default is repo root, but rootdir gymnastics or absolute pytest invocations would break a bare Path('.planning/...').read_text())"

patterns-established:
  - "Sequential filter passes in orchestrator: each pass = its own `if not ...: continue` block with its own log call on drop. Pattern scales — Plan 04-03+ can add additional gates the same way without restructuring _scrape_one"
  - "Doc-as-test invariants for REQUIREMENTS.md: assert substring anchors via Path(__file__)-relative read; fails on next CI run if a future editor strips/renames the requirement"
  - "ADP-15 open-closed re-proven for the 8th consecutive plan: zero edits to src/adapters/*.py since Plan 01-01; Phase 4 changes live entirely in filter / locations / main / normalizer / renderer / state modules"

requirements-completed: [FILT-07]

# Metrics
duration: ~6min
completed: 2026-06-08
---

# Phase 4 Plan 02: FILT-07 US-only Region Filter Summary

**Adds the FILT-07 US-only region filter as a pure-function `is_us_location_acceptable` in `src/filter.py` wrapping Plan 04-01's `is_us_location` 8-rule classifier, wired into the orchestrator AFTER the title-keyword gate with an INFO log line on each drop. REQUIREMENTS.md gains FILT-07 as the 7th Filter entry. 25 net new tests / 524 cumulative passing. ADP-15 re-proven for the 8th consecutive plan.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-08T18:06:34Z
- **Completed:** 2026-06-08T18:12:24Z
- **Tasks:** 3 (all TDD: RED → GREEN per Task 1 + Task 2; Task 3 is doc-only with the test already RED from Task 1)
- **Files modified:** 5 (1 new SUMMARY + 4 source/test/doc files)

## Accomplishments

- **`src/filter.py` extended:** New `is_us_location_acceptable(posting: Posting) -> bool` (18 lines including docstring) wraps `src.locations.is_us_location` applied to `posting.location`. Pure function per FILT-06 — no I/O, no datetime, no state. Module docstring extended with FILT-07 note pointing at the orchestrator ordering (D-03a: is_early_career → is_us_location_acceptable → state merge).
- **`src/main.py` wired:** `_scrape_one` filter block becomes a 2-pass sequential gate per CONTEXT.md D-03a. Title-keyword gate runs first; FILT-07 runs immediately after; only postings passing both are appended for state merge. Dropped non-US postings get a `logger.info("scrape:%s drop FILT-07 non-US: %s (%s)", company.name, p.title, p.location)` line — visible in Actions logs so the user can verify "yes, the London postings are being dropped on purpose" without instrumenting.
- **`.planning/REQUIREMENTS.md` updated:** FILT-07 added as the 7th Filter bullet with verbatim CONTEXT.md D-03 wording (including the STATE-04 "never delete" carve-out note and the cross-reference to PROJECT.md's prior out-of-scope listing). Traceability table gains `| FILT-07 | Phase 4 | Complete |` between FILT-06 and NORM-01. Coverage block bumps v1 total 71→72, FILT count 6→7, Phase 4 distribution 3→4.
- **25 net new tests** (22 in tests/test_filter.py + 3 in tests/test_orchestrator.py) across: 16-row parametrized US-keep/non-US-drop coverage, SF-keep + London-drop + empty-keep spot-checks, determinism + bool-return purity, doc invariant for REQUIREMENTS.md, orchestrator-level London-drop integration, INFO log assertion via caplog, US-keep regression guard.
- **524 cumulative tests pass** (499 baseline + 25 net new). Ruff clean across `src/` and `tests/`.
- **ADP-15 open-closed invariant re-proven for the 8th consecutive plan:** `git diff --name-only 36dd035..HEAD -- src/adapters/` = 0 files. All Phase 4 changes continue to live in `src/filter.py`, `src/main.py`, `src/locations.py`, `src/normalizer.py`, `src/renderer.py`, and `.planning/*`.

## Task Commits

Each task was committed atomically via TDD RED → GREEN gates:

1. **Task 1: src/filter.py is_us_location_acceptable + tests**
   - `7ff1b0d` test(04-02): add failing tests for is_us_location_acceptable + FILT-07 doc invariant (RED)
   - `130382a` feat(04-02): is_us_location_acceptable — FILT-07 filter pass (GREEN)

2. **Task 2: src/main.py orchestrator wiring + integration tests**
   - `c13cfad` test(04-02): add failing FILT-07 orchestrator integration tests (RED)
   - `463917c` feat(04-02): wire FILT-07 into orchestrator _scrape_one (GREEN)

3. **Task 3: REQUIREMENTS.md FILT-07 entry + Traceability + Coverage**
   - `ce6dcd0` docs(04-02): add FILT-07 to REQUIREMENTS.md (Task 3)

_TDD cycle: Task 1 and Task 2 each landed as 1 RED commit + 1 GREEN commit. Task 3's doc-invariant test was authored as part of Task 1 RED (because the test lives in tests/test_filter.py per the plan body), so Task 3 only required the REQUIREMENTS.md edits to flip that test GREEN — no separate test-commit needed. No REFACTOR commits — implementations were minimal and clean from first GREEN pass._

## Files Created/Modified

- `src/filter.py` (MODIFIED) — Added `from src.locations import is_us_location` import. Appended new `is_us_location_acceptable(posting: Posting) -> bool` pure function at end of file. Extended module docstring with FILT-07 paragraph describing the orchestrator ordering (FILT-06 → FILT-07).
- `src/main.py` (MODIFIED) — Extended import line to `from src.filter import is_early_career, is_us_location_acceptable`. Rewrote `_scrape_one` filter block from single-pass (`if is_early_career(p): postings.append(p)`) to two-pass sequential form: title-keyword guard → FILT-07 guard → append. FILT-07 drops emit a `logger.info("scrape:%s drop FILT-07 non-US: %s (%s)", ...)` line.
- `.planning/REQUIREMENTS.md` (MODIFIED) — Inserted FILT-07 as 7th Filter bullet (between FILT-06 and Normalization & Extraction heading) with verbatim CONTEXT.md D-03 wording. Added `| FILT-07 | Phase 4 | Complete |` to Traceability table. Bumped Coverage block: v1 total 71→72, FILT 6→7, Phase 4 distribution 3→4.
- `tests/test_filter.py` (MODIFIED) — Added `is_us_location_acceptable` import. Added `_make_posting_loc(location)` helper. Added `class TestIsUsLocationAcceptable` with 21 tests (16 parametrized SF/Boston/Cupertino/NY/Seattle/USA/UnitedStates/Remote-US/Remote-non-US/London/Bangalore/Berlin/Toronto/Singapore/empty/ambiguous rows + SF-keep + London-drop + empty-keep spot-checks + determinism + bool-return). Added `test_filt07_documented_in_requirements_md` doc invariant. **Test count: 52 → 74 (+22).**
- `tests/test_orchestrator.py` (MODIFIED) — Added `_TwoCityAdapter` synthetic adapter (returns SF + London postings, both source_adapter='greenhouse' for existing-dispatch reuse). Added 3 integration tests: `test_orchestrator_drops_non_us_postings_per_filt07`, `test_orchestrator_filt07_drop_emits_info_log_line`, `test_orchestrator_filt07_does_not_drop_us_postings`. **Test count: 13 → 16 (+3).**
- `.planning/phases/04-extraction-polish-health-observability/04-02-SUMMARY.md` (NEW, this file).

**Test counts per file:** filter 74 (was 52 → +22) / orchestrator 16 (was 13 → +3). **Cumulative: 524 (was 499 → +25 net new).**

## Decisions Made

- **`is_us_location_acceptable` is a single-line wrapper.** `return is_us_location(posting.location)`. All classification logic lives in `src/locations.py` (Plan 04-01); FILT-07's only job is to adapt that classifier to the Posting type for orchestrator chaining. Single-line bodies are deliberate — they make the gate trivially auditable.
- **Two-pass filter block with explicit `continue`, not chained boolean.** `if not is_early_career(p): continue; if not is_us_location_acceptable(p): logger.info(...); continue; postings.append(p)`. The chained form `if is_early_career(p) and is_us_location_acceptable(p):` would have been one line shorter but would have prevented a per-gate log call on drop. Two-pass form preserves drop-reason clarity in Actions logs.
- **FILT-07 drop log uses `logger.info` not `logger.warning`.** A non-US posting being filtered is correct behavior, not an error condition. WARNING is reserved for adapter-level "something went wrong" signals (SiteBlocked, normalize failure). INFO keeps the drop visible without polluting the WARNING channel.
- **`_TwoCityAdapter` uses `source_adapter="greenhouse"` not a new dispatch arm.** The existing `_normalize_greenhouse` accepts a tolerant raw-dict shape (id / title / updated_at / location.name / absolute_url / __dedup_key / __board_token) which is sufficient to synthesize two postings with different locations. Registering a new normalizer arm for a single integration test would have been unnecessary churn.
- **Doc-as-test lives in `tests/test_filter.py`, not a new `tests/test_requirements_doc.py`.** Colocates the FILT-07 contract assertion with the function-under-test. Mirrors the Phase 3 Plan 03-03 precedent (credential-flow doc invariants live in `tests/test_credential_flow.py`, not a separate doc-test module).
- **REQUIREMENTS.md FILT-07 checkbox is `[x]` on first insertion.** Implementation lands in the same plan that adds the requirement, so checking it on insertion is correct. Same pattern as Plan 04-01's NORM-02 / NORM-03 closure annotations (which were already `[x]` before that plan since they pre-existed; FILT-07 is fully new + fully shipped in one plan).
- **Doc test uses `Path(__file__).resolve().parent.parent`.** Robust to test cwd. pytest's default cwd is repo root, but absolute pytest invocations or rootdir overrides would break a bare `Path('.planning/...').read_text()`. The file-relative form is cwd-independent.
- **Sequential filter pattern locked.** Future region/role/seniority filters in Phase 5+ can append additional gates as `if not is_X_acceptable(p): logger.info(...); continue` blocks without restructuring `_scrape_one`. Pattern is open-closed at the filter-pass dimension.

## Deviations from Plan

None — plan executed exactly as written.

The plan's `<context>` and `<tasks>` blocks accurately described every file edit, log-line format, and test name. The verify automation in each task's `<verify>` block ran clean on first try after each GREEN commit. Test counts exceeded plan minimums (74 filter vs ≥34, 16 orchestrator vs ≥14).

One minor difference from the plan's task structure: the plan body listed Task 3 as a separate TDD task with its own RED commit. In practice the doc-invariant test was authored as part of Task 1 RED (since the test lives in tests/test_filter.py per `<action>` block's "Edit tests/test_filter.py: Add the test_filt07_documented_in_requirements_md test"), so Task 3 only needed the REQUIREMENTS.md edits to flip that test GREEN. Same net outcome (one commit per task gate); just one fewer commit overall (5 vs 6 planned). The TDD discipline is preserved — the test was RED before the doc edit and GREEN after.

**Total deviations:** 0
**Impact on plan:** None — plan was unusually crisp.

## Threat-Model Posture

All 5 threat-model entries from PLAN.md addressed:

- **T-04-02-01 (Tampering — bypassing FILT-07 via malformed Posting.location):** Accepted as documented. Falsifying location to `""` intentionally KEEPS the posting (FILT-05 bias). No untrusted source upstream of FILT-07 attempts to inject postings; all postings come from the user's own `companies.txt` scrape. The bias-toward-inclusion principle is documented in the function docstring + the REQUIREMENTS.md entry.
- **T-04-02-02 (Info Disclosure — INFO log line leaks PII via title/location):** Accepted. `Posting.title` + `Posting.location` are public data from public career pages. No credential surface; Pitfall 17 hygiene preserved (no headers, no traceback, no exception attrs).
- **T-04-02-03 (DoS — many postings cause N log lines on FILT-07 drop):** Accepted. Bounded — at most ~500 postings/company/run × ~30 companies = ~15K log lines worst case; Actions captures stdout, no issue at this scale.
- **T-04-02-04 (Tampering — REQUIREMENTS.md drift):** **Mitigated.** `test_filt07_documented_in_requirements_md` asserts the entry exists with 4 substring anchors (`**FILT-07**`, `is_us_location()`, `bias toward inclusion per FILT-05`, `| FILT-07 | Phase 4 |`); doc rot fails the test on next CI run.
- **T-04-02-05 (Tampering — adapter contract break by Phase 4 changes):** **Mitigated.** Zero edits to `src/adapters/*.py` files. `tests/test_adapter_contract.py` continues to pass 7/7. ADP-14/15 invariant re-proven for the 8th time.

## ADP-15 Re-Proof

```
$ git diff --name-only 36dd035..HEAD -- src/adapters/
$ wc -l < /dev/null
0
```

Zero edits to any `src/adapters/*.py` file across all 5 commits of this plan. The 8-consecutive-plans-running invariant since Phase 1 stands.

## Self-Check: PASSED

Verified after writing this SUMMARY:
- src/filter.py contains `def is_us_location_acceptable` (line 171)
- src/filter.py contains `from src.locations import is_us_location` (line 26)
- src/main.py contains `is_us_location_acceptable` (3 occurrences — import + call site + log-line companion comment)
- src/main.py contains `FILT-07` (in the `_scrape_one` comment block)
- .planning/REQUIREMENTS.md contains `**FILT-07**`
- .planning/REQUIREMENTS.md contains `is_us_location()`
- .planning/REQUIREMENTS.md contains `| FILT-07 | Phase 4 | Complete |`
- .planning/REQUIREMENTS.md Coverage line reads `72 total` and `7 FILT` and `Phase 4 = 4`
- All 5 commits (7ff1b0d, 130382a, c13cfad, 463917c, ce6dcd0) present in git log
- Full pytest suite: 524/524 passing (was 499 → +25 net new)
- tests/test_adapter_contract.py: 7/7 passing (ADP-15 invariant)
- `git diff --name-only 36dd035..HEAD -- src/adapters/` returns 0 files
- ruff clean across src/ and tests/
- Sanity-command from plan body prints `OK`

## Issues Encountered

None. Each task's RED phase failed exactly as intended; each GREEN phase passed on first run.

## User Setup Required

None — no external service configuration required for this plan. All changes are pure-function library code, orchestrator wiring, doc-edit, and tests.

## Next Phase Readiness

- **Plan 04-03 (OUT-09 source_health data via seen.json schema bump v1→v2)** is independent of this plan's deliverables. It operates on `src/state_store.py` + `src/state_merger.py` + `src/main.py` orchestrator try/except classification and adds a `source_health` top-level block alongside `postings`. No edits to filter / locations / normalizer / renderer expected.
- **FILT-07 requirement ready to mark complete** in REQUIREMENTS.md (already done in Task 3).
- **`is_us_location_acceptable` is stable + tested + ready for any future consumer** (e.g., a region-filter opt-out per CONTEXT.md `<deferred>` "Non-US visibility opt-in" — would wrap this function in a conditional based on `companies.txt` per-line hint or env var).

---
*Phase: 04-extraction-polish-health-observability*
*Completed: 2026-06-08*
