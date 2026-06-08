---
phase: 04-extraction-polish-health-observability
plan: 03
subsystem: state-store
tags: [state-store, schema-migration, source-health, observability, out-09, requirements-doc, phase-4]

# Dependency graph
requires:
  - phase: 01-walking-skeleton
    provides: src/state_store.py (atomic write + .bak + sanity gate + STATE-08), src/state_merger.py (merge_state pure function), src/main.py (orchestrator + per-company outcomes dict)
  - phase: 04-extraction-polish-health-observability/02
    provides: orchestrator outcome capture pipeline (no logical dep on FILT-07 itself; just serialized for safe REQUIREMENTS.md + main.py editing)
provides:
  - seen.json schema_version 2 with new top-level source_health block (per-company adapter outcome tracking)
  - load_state v1 → v2 in-memory auto-migration (one-shot, on every load)
  - save_state_atomic writes v2 only (load-time migration guarantees this)
  - classify_outcome(outcome, prior_consecutive_failures) → (status, new_fail, is_success) pure helper
  - update_source_health(state, company_name, outcome, run_started_at) in-place mutator
  - Orchestrator wires per-company source_health update between merge_state and sanity_gate
  - REQUIREMENTS.md OUT-09 amended (strikethrough + footnote per CONTEXT.md D-04c)
  - Source Health data persisted in seen.json.source_health; explicitly NOT rendered in README (D-04c invariant)
affects: [phase-5, future-claude-cli-diagnostic-sessions, any-future-source-health-footer-plan]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Forward-compatible schema migration: loader auto-migrates older versions in memory; saver writes current version only; future versions raise UnknownSchemaVersion (STATE-08 invariant)"
    - "Per-company health tracking via 3-fail consecutive_failures threshold (CONTEXT.md D-04b) — distinguishes 'transient error' from 'persistently blocked' without notification noise"
    - "Data-persisted-not-rendered surface: diagnostic data lives in seen.json for future Claude CLI sessions to consume; renderer intentionally not modified (D-04c)"

key-files:
  created:
    - "tests/fixtures/seen_v1_sample.json (v1 schema reference fixture)"
    - "tests/fixtures/seen_v2_sample.json (v2 schema reference fixture with source_health)"
  modified:
    - "src/state_store.py (SCHEMA_VERSION 1→2, EMPTY_STATE adds source_health, _parse_state_bytes auto-migrates v1)"
    - "src/state_merger.py (merge_state emits v2 + carries source_health; new classify_outcome + update_source_health helpers)"
    - "src/main.py (import update_source_health; per-company source_health update loop between merge_state and sanity_gate)"
    - ".planning/REQUIREMENTS.md (OUT-09 strikethrough + footnote; Traceability row Pending → Complete)"
    - "tests/test_state_store.py (10 net new tests + 5 pre-existing updated for v2 contract)"
    - "tests/test_state_merger.py (16 net new tests for classify_outcome + update_source_health + merge_state source_health carryforward)"
    - "tests/test_orchestrator.py (5 net new tests: end-to-end source_health write, 3-run accumulation, no-adapter → error, D-04c not-rendered invariant, REQUIREMENTS.md doc invariant)"

key-decisions:
  - "Schema migration is single-pass and in-memory: loader sees v1 → adds source_health: {} → bumps in-memory schema_version to 2. The next save_state_atomic call writes v2 to disk. No on-load-and-write migration script needed; the next scan does it for free."
  - "source_health is mandatory in v2 but loader defensively defaults missing/wrong-type to {} (Pitfall 1 'fail soft on corrupted state'). Catches partial writes + future drift without crashing production."
  - "save_state_atomic strict-version enforcement preserved: refuses v != SCHEMA_VERSION. The load-time migration guarantees callers always hand it v2."
  - "merge_state always emits schema_version=SCHEMA_VERSION (2) — no longer preserves-from-prior. Combined with load-time auto-migration, callers cannot accidentally write back a v1 dict."
  - "classify_outcome is a pure function returning (status, new_fail_count, is_success) — caller-friendly tuple keeps update_source_health's mutation logic minimal + testable in isolation."
  - "3-fail consecutive_failures threshold for 'blocked' status (D-04b): a transient block (1-2 failures) reads as 'error'; sustained block (3+) reads as 'blocked'. Surfaces persistent issues without noise from single-run flakes."
  - "Source Health update runs BEFORE sanity_gate, not after — but state is only saved if the gate passes. A sanity-aborted run intentionally writes nothing, including the source_health snapshot, so the on-disk record matches what's been committed to git (T-03-02 preserved)."
  - "REQUIREMENTS.md OUT-09 uses '[x] ~~**OUT-09**~~' (checked + strikethrough) because the data IS persisted; only the rendering surface is dropped. Mirrors Phase 1 INFRA-05 and Phase 2 FILT-04 strikethrough patterns."
  - "renderer.py UNTOUCHED per CONTEXT.md D-04c — explicit user request to NOT show health footer in README. Data lives in seen.json for future Claude CLI diagnostic sessions only."

patterns-established:
  - "Forward-compatible schema bump cycle: loader handles vN+vN-1 in same code path; saver writes vN only; vN+1 raises. Demonstrated end-to-end here; reusable for any future schema bumps."
  - "Doc-as-test invariant guard: test_out09_amended_with_strikethrough_in_requirements_md asserts the strikethrough form + footnote text + Traceability row state. Doc rot fails CI immediately. Mirrors Phase 2 FILT-04 + Phase 3 doc-invariant tests."

requirements-completed: [OUT-09]

# Metrics
duration: ~25min
completed: 2026-06-07
---

# Phase 4 Plan 03: Source Health Schema Bump (1→2) + Persisted Observability Summary

**seen.json schema bump 1→2 + per-company source_health observability data (data-persisted, NOT rendered per CONTEXT.md D-04c). Phase 4 execute-complete.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-07 (session start, see git log)
- **Completed:** 2026-06-07
- **Tasks:** 3 (all TDD: RED → GREEN per task)
- **Net new tests:** 31 (10 state_store + 16 state_merger + 5 orchestrator)
- **Full suite:** 555 tests passing (524 baseline + 31 Plan 04-03)
- **Files modified:** 7 source + 2 fixtures = 9

## Accomplishments

- **seen.json schema bumped 1 → 2** with one-shot in-memory auto-migration of pre-existing v1 files. Loader handles both versions in the same code path; saver writes v2 only; v3+ raises `UnknownSchemaVersion` (STATE-08 invariant preserved).
- **`source_health` block** added as 4th top-level key in `seen.json`, recording per-company `{last_attempt_utc, last_success_utc, status, consecutive_failures}` with status enum `ok` / `blocked` / `schema-drift` / `error`.
- **`classify_outcome` + `update_source_health` helpers** in `src/state_merger.py`. Pure-function + in-place-mutator pair; tested in isolation (16 unit tests) before wiring into orchestrator.
- **Orchestrator wiring** in `src/main.py` — per-company `update_source_health` call between `merge_state` and `sanity_gate`. Aborted runs intentionally write nothing (T-03-02 preserved).
- **REQUIREMENTS.md OUT-09 amendment** with strikethrough + footnote per CONTEXT.md D-04c. Mirrors Phase 1 INFRA-05 + Phase 2 FILT-04 strikethrough patterns. Traceability row: `Pending` → `Complete`.
- **CONTEXT.md D-04c invariant honored** — `src/renderer.py` and `README.md` UNTOUCHED. Source Health data lives in `seen.json` for diagnostic use only.
- **ADP-14/15 invariant re-proven for the 9th time** — zero edits to `src/adapters/*.py`. Adapter contract test still passes.
- **Phase 4 execute-complete** — all 4 Phase 4 REQ-IDs closed: NORM-02 + NORM-03 (Plan 04-01), FILT-07 (Plan 04-02), OUT-09 (Plan 04-03).

## Task Commits

Each task followed strict TDD (RED → GREEN). All commits atomic; no destructive operations.

1. **Task 1: SCHEMA_VERSION 1→2 + v1→v2 auto-migration + fixtures + tests**
   - `2b65f9e` (test) — `test(04-03): add failing v1→v2 schema migration tests + fixtures (RED)`
   - `95f6ca6` (feat) — `feat(04-03): bump seen.json schema 1→2 + auto-migrate v1 (GREEN)`

2. **Task 2: classify_outcome + update_source_health helpers + tests**
   - `9b881c6` (test) — `test(04-03): add failing classify_outcome + update_source_health tests (RED)`
   - `7a424d7` (feat) — `feat(04-03): classify_outcome + update_source_health helpers (GREEN)`

3. **Task 3: Orchestrator wiring + REQUIREMENTS.md OUT-09 amendment + end-to-end tests**
   - `3e221a6` (test) — `test(04-03): add failing source_health orchestrator + doc invariant tests (RED)`
   - `59ff6a9` (feat) — `feat(04-03): wire source_health update into orchestrator + amend OUT-09 (GREEN)`

**Plan metadata commit:** (to follow — this SUMMARY + STATE.md + ROADMAP.md update)

## Files Created/Modified

### Created

- **`tests/fixtures/seen_v1_sample.json`** — v1 schema reference fixture (single Stripe posting; no source_health key)
- **`tests/fixtures/seen_v2_sample.json`** — v2 schema reference fixture (same posting + `source_health: {}` block)

### Modified — source

- **`src/state_store.py`** — `SCHEMA_VERSION: int = 2`; `EMPTY_STATE` gains `"source_health": {}`; new `_fresh_empty_state()` helper for independent EMPTY_STATE copies; `_parse_state_bytes` adds v1→v2 in-memory auto-migration block + defensive source_health shape check; `load_state` cold-start + both-corrupted branches use `_fresh_empty_state()`; `save_state_atomic` docstring updated to mention v2 payload includes source_health.
- **`src/state_merger.py`** — Import `SCHEMA_VERSION` from `src.state_store` for single-source-of-truth; `merge_state` returns `schema_version: SCHEMA_VERSION` (always 2) + shallow-copy of `source_health` from prior; new `classify_outcome` pure helper (D-04b enum mapping); new `update_source_health` in-place mutator (D-04d entry shape + accumulation rules).
- **`src/main.py`** — Import `update_source_health`; per-company source_health update loop inserted between `merge_state` and `sanity_gate` (so on-disk reflects this run; aborted runs save nothing).
- **`.planning/REQUIREMENTS.md`** — OUT-09: `[ ]` → `[x] ~~**OUT-09**~~` with footnote pointing to CONTEXT.md D-04c (mirrors Phase 1 INFRA-05 + Phase 2 FILT-04 patterns); Traceability row `Pending` → `Complete`.

### Modified — tests

- **`tests/test_state_store.py`** — 10 net new tests (schema bump invariants, v1→v2 migration round-trip, v3 still raises, defensive source_health defaulting, v2 populated-source_health round-trip, save_state_atomic refuses v1); 5 pre-existing tests updated for v2 contract.
- **`tests/test_state_merger.py`** — 16 net new tests (6 classify_outcome + 8 update_source_health + 2 merge_state source_health carryforward); 1 pre-existing test renamed + expanded.
- **`tests/test_orchestrator.py`** — 5 net new tests (end-to-end source_health write, 3-run accumulation reaches 'blocked', no-adapter → error, D-04c not-rendered invariant, REQUIREMENTS.md doc invariant).

## Decisions Made

Followed plan as specified. Key implementation choices documented inline in `key-decisions` frontmatter above. Notably:

- Used `dict(EMPTY_STATE)`-equivalent fresh-copy helper (`_fresh_empty_state()`) instead of a deep-copy import, since the EMPTY_STATE shape is shallow (nested dicts are empty).
- Imported `SCHEMA_VERSION` from `src.state_store` into `src.state_merger` (single-source-of-truth) rather than hard-coding `2` (would require coordinated update on next schema bump).
- Outcome string fallback in orchestrator: `outcomes.get(company.name, "no-adapter")` defends against any edge case where `_scrape_one` didn't record an outcome (every company in `companies` should be in `outcomes`, but defensive default is cheap).

## Deviations from Plan

**None — plan executed exactly as written.**

All three tasks shipped per the plan's `<behavior>` and `<action>` blocks. All `<verify>` automated checks passed.

## Schema Migration Round-Trip Evidence

End-to-end verification via the plan's `<verification>` smoke test:

```
$ .venv/bin/python -c "
from pathlib import Path
from src.state_store import load_state, save_state_atomic, SCHEMA_VERSION
import tempfile, shutil
tmp = Path(tempfile.mkdtemp()) / 'seen.json'
shutil.copy('tests/fixtures/seen_v1_sample.json', tmp)
state = load_state(tmp)
assert state['schema_version'] == 2
assert state['source_health'] == {}
assert 'gh:stripe:42' in state['postings']
save_state_atomic(state, tmp)
state2 = load_state(tmp)
assert state2['schema_version'] == 2
print('round-trip OK; SCHEMA_VERSION=', SCHEMA_VERSION)
"
round-trip OK; SCHEMA_VERSION= 2
```

The v1 fixture loads, auto-migrates in memory to v2 with empty source_health, saves to disk as v2, reloads as v2 — postings unchanged.

## ADP-14/15 Re-Proof (9th Time)

```
$ git diff --name-only HEAD~6 HEAD | grep -E '(renderer|adapters/)'
(no changes to renderer/adapters)

$ .venv/bin/pytest tests/test_adapter_contract.py
7 passed in 0.07s
```

Zero edits to `src/adapters/*.py`. `tests/test_adapter_contract.py` still green. Adapter contract invariant re-proven for the 9th time across Phases 3 + 4.

## Threat-Model Posture

All six threats in the plan's `<threat_model>` register were either mitigated or accepted per the documented plan:

| Threat ID | Disposition | Mitigation Verified |
|-----------|-------------|---------------------|
| T-04-03-01 (corrupt v2 seen.json) | mitigate | Defensive `isinstance` check defaults missing/wrong-type source_health to `{}` (`test_load_v2_with_missing_source_health_defaults_to_empty`, `test_load_v2_with_wrong_type_source_health_defaults_to_empty`) |
| T-04-03-02 (orchestrator wrong outcome) | accept | Controlled vocabulary from `_scrape_one`; classify_outcome covers all forms |
| T-04-03-03 (info disclosure — company names + timestamps public) | accept | Per CONTEXT.md threat model (company names already in public companies.txt) |
| T-04-03-04 (DoS — pathological v1 migration loop) | mitigate | Single-pass `sv == 1` branch; no loop |
| T-04-03-05 (REQUIREMENTS.md OUT-09 drift) | mitigate | `test_out09_amended_with_strikethrough_in_requirements_md` doc invariant |
| T-04-03-06 (adapter contract break) | mitigate | Zero edits to adapters; `test_adapter_contract.py` passes |

## Phase 4 REQ-IDs Closure Confirmation

| REQ-ID | Plan | Status (REQUIREMENTS.md Traceability) | Notes |
|--------|------|----------------------------------------|-------|
| NORM-02 | 04-01 | Complete | Salary verbatim copy-paste (Plan 04-01 Summary) |
| NORM-03 | 04-01 | Complete | Location normalize_location + is_us_location (Plan 04-01 Summary) |
| FILT-07 | 04-02 | Complete | US-only region filter; Phase 4 NEW requirement (Plan 04-02 Summary) |
| OUT-09 | 04-03 | Complete | **This plan** — Source Health data persisted in seen.json.source_health; NOT rendered per D-04c |

**Phase 4 execute-complete.** All 4 Phase 4 REQ-IDs (3 from initial PROJECT.md + 1 added in Phase 4 per CONTEXT.md D-03) closed.

## Known Stubs

**None.** No hardcoded empty UI values, no placeholder text, no unwired components. All source_health data flows from real adapter outcomes through `classify_outcome` to disk-persisted state.

## Threat Flags

**None.** No new security surface introduced beyond the threats already documented in `<threat_model>`. The source_health data introduces no credentials, no network endpoints, no new file-write paths beyond the existing atomic-write contract.

## Issues Encountered

**None.** TDD cycle ran cleanly through all 3 tasks. RED → GREEN transitions confirmed at each step. Full suite remained green throughout: 524 baseline → 534 after Task 1 → 550 after Task 2 → 555 after Task 3.

## User Setup Required

**None.** No external service configuration, no secret rotation, no environment variable changes. The schema migration is automatic on next scan.

## Next Phase Readiness

**Phase 4 is execute-complete.** Recommended next step:

- **`/gsd-verify-phase 4`** — independent verification pass on all 3 plans + the Phase 4 REQ-IDs (NORM-02, NORM-03, FILT-07, OUT-09). The verifier should confirm:
  - `seen.json` writes survive a v1-on-disk + scan cycle (migration to v2 with source_health populated)
  - README does NOT contain "Source Health" heading or HEALTH sentinels (D-04c)
  - REQUIREMENTS.md OUT-09 strikethrough + footnote present; Traceability row Complete
  - All 555 tests green; cumulative test count growth tracked: Phase 1 (~330) → Phase 4 (~555)
  - ADP-14/15 invariant: zero git diff in `src/adapters/` between Phase 4 start and end

**If Phase 4 verification passes**, the milestone is complete. If user wants the Source Health footer rendered after all, a 1-task "Source Health README footer" plan would suffice — render the existing `seen.json.source_health` block into a new `<!-- BEGIN HEALTH -->` / `<!-- END HEALTH -->` sentinel pair (no data-store changes needed). Tracked in CONTEXT.md Deferred Ideas.

## Self-Check: PASSED

**Files verified to exist:**
- `tests/fixtures/seen_v1_sample.json` — FOUND
- `tests/fixtures/seen_v2_sample.json` — FOUND
- `src/state_store.py` (modified) — FOUND with `SCHEMA_VERSION: int = 2`
- `src/state_merger.py` (modified) — FOUND with `def classify_outcome` and `def update_source_health`
- `src/main.py` (modified) — FOUND with `update_source_health` import + call
- `.planning/REQUIREMENTS.md` (modified) — FOUND with `~~**OUT-09**~~` + `seen.json.source_health` + `NOT rendered in the README` + `| OUT-09 | Phase 4 | Complete |`
- `tests/test_state_store.py` (modified) — FOUND, 35 tests pass
- `tests/test_state_merger.py` (modified) — FOUND, 24 tests pass
- `tests/test_orchestrator.py` (modified) — FOUND, 21 tests pass

**Commits verified to exist:**
- `2b65f9e` (RED Task 1) — FOUND
- `95f6ca6` (GREEN Task 1) — FOUND
- `9b881c6` (RED Task 2) — FOUND
- `7a424d7` (GREEN Task 2) — FOUND
- `3e221a6` (RED Task 3) — FOUND
- `59ff6a9` (GREEN Task 3) — FOUND

**Full pytest suite:** 555 passed in 58.77s. Ruff: All checks passed!

---
*Phase: 04-extraction-polish-health-observability*
*Plan: 03*
*Completed: 2026-06-07*
