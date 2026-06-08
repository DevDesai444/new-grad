---
phase: 04
phase_name: extraction-polish-health-observability
status: passed
gates_passed: 4
gates_total: 4
verified_at: 2026-06-08T00:00:00Z
---

# Phase 4: Extraction Polish + Health Observability — Verification Report

**Phase Goal:** Salary and Location columns populate verbatim from the source (no parsing per D-01); Remote-variant locations collapse to canonical `Remote (US)` / `Remote (non-US)` (D-02); a US-only region filter (FILT-07 — new requirement per D-03) drops non-US postings before render; per-source adapter health is **tracked in `seen.json.source_health` but NOT rendered in the README** (D-04c — user explicitly does not want a footer; data exists for Claude CLI diagnostic reads).

**Verified:** 2026-06-08
**Status:** passed
**Re-verification:** No — initial verification

---

## 1. Success Criteria Verification (3 ROADMAP + 1 NEW FILT-07)

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Salary column populated verbatim from per-adapter source field; empty/placeholder → `—`; >80 chars → ellipsis truncation | VERIFIED | `src/normalizer.py` — each `_normalize_*` helper sets `salary` from per-adapter path (Greenhouse `_extract_greenhouse_salary` lines 149-166; Lever `salaryRange.text` fallback `salary` lines 200-205; Ashby `compensation.compensationTierSummary` lines 255-259; SR `""` (no public field) line 325; Workday `""` (CXS has no salary) line 387; Apple coalesces `postingPay.payRange.text` → `salaryRange` → `homeOffice` lines 531-540; Playwright `raw.get("salary") or ""` line 599). `src/renderer.py` `_coalesce_salary` (lines 159-172) + `_SALARY_PLACEHOLDER_PATTERN` (lines 135-150) handles Competitive/DOE/TBD/TBC/Not Disclosed/N/A/null/Negotiable/etc.; `_truncate_cell` (lines 175-185) caps at 80 chars with U+2026 ellipsis. `_table_row` (line 196-198) wires `_truncate_cell(_coalesce_salary(...))` into the Salary column. Per-adapter tests in `tests/test_normalizer.py` (15+ salary tests at lines 546-791) + 12+ renderer salary tests (`test_renderer.py` lines 411-548). |
| 2 | Location values normalized for Remote variants; `is_us_location()` 8-rule classifier per D-02a | VERIFIED | `src/locations.py` (171 lines, NEW module). `normalize_location` (lines 102-121) collapses ~10 Remote-shape variants to `Remote (US)` / `Remote (non-US)`; bare `Remote` → `Remote (US)` per D-02 user-in-US bias. `is_us_location` (lines 124-171) implements all 8 D-02a rules in declared order: empty→True, Remote-canonical, US state code (50+DC), US country tokens (USA/U.S./U.S.A./United States), curated US city list (~30), curated non-US substring list (~45 covering cities + country names), fallback True. Compiled regex at module load (`_US_STATE_REGEX` line 97). 56 tests in `tests/test_locations.py` exercise every rule + edge cases (rule-order priority, word-boundary state codes, normalize-then-classify roundtrip). All 7 per-adapter normalizers route their location through `normalize_location` (Greenhouse line 420-422, Lever 182-186, Ashby 245, SR 308, Workday 368, Apple 505, Playwright 581). |
| 3 | Source Health data persisted in `seen.json.source_health`, NOT rendered in README (D-04c) | VERIFIED | `src/state_store.py` `SCHEMA_VERSION=2` (line 31); `EMPTY_STATE` includes `"source_health": {}` (line 39); `_parse_state_bytes` auto-migrates v1→v2 (lines 111-120). `src/state_merger.py` `classify_outcome` (lines 111-140) implements D-04b: ok→(ok,0,True); blocked + prior≥2→(blocked,…); blocked + prior<2→(error,…); SchemaDrift→(schema-drift,…); else→(error,…). `update_source_health` (lines 143-187) mutates state in place per D-04d. `src/main.py` orchestrator loop (lines 280-282) calls `update_source_health` per company AFTER merge_state and BEFORE save_state_atomic — wired into the orchestrator. **D-04c invariant proven:** `grep -c source_health src/renderer.py` = 0; `grep -c "Source Health\|BEGIN HEALTH" README.md` = 0; renderer file diff shows ONLY salary-cell logic, no source_health touch. `REQUIREMENTS.md` OUT-09 is struck through with the D-04c footnote pointing to CONTEXT.md (line 91). |
| 4 | (NEW) FILT-07 — US-only filter drops non-US postings; ambiguous kept (FILT-05 bias); wired AFTER `is_early_career` and BEFORE state merge | VERIFIED | `src/filter.py` `is_us_location_acceptable` (lines 171-187) wraps `src.locations.is_us_location(posting.location)`. `src/main.py:_scrape_one` order (lines 113-126): `is_early_career` (FILT-01/02) → `is_us_location_acceptable` (FILT-07) → state merge. Dropped postings emit `logger.info` line naming title + location (line 121-124). Integration test `test_orchestrator_drops_non_us_postings_per_filt07` (test_orchestrator.py:455-487): asserts London posting NOT in `seen.json` and NOT in README, SF posting IS in both. `REQUIREMENTS.md` line 58: FILT-07 inserted as 7th Filter entry with full definition and provenance footnote. Coverage updated to 72 (was 71) in ROADMAP.md line 125 and REQUIREMENTS.md Coverage section. |

**Score: 4/4 truths VERIFIED**

---

## 2. REQ-ID Coverage Matrix (4 IDs Expected)

| REQ-ID | Description | Plan | Status | Evidence |
|--------|-------------|------|--------|----------|
| **NORM-02** | Salary verbatim (softened from "extraction with patterns" per D-01) | 04-01 | SATISFIED | REQUIREMENTS.md line 63 struck-through with D-01 footnote → "Closed by Plan 04-01". Implementation: per-adapter `_extract_*_salary` paths in `src/normalizer.py`; renderer placeholder coalesce + 80-char truncation in `src/renderer.py`. Tests: 15+ per-adapter salary tests in `test_normalizer.py`; 12+ renderer cell tests in `test_renderer.py`. |
| **NORM-03** | Location normalization (Remote variants → canonical form) | 04-01 | SATISFIED | REQUIREMENTS.md line 64: closed by Plan 04-01. `src/locations.py:normalize_location` collapses Remote variants; non-Remote unchanged per D-02b. All 7 per-adapter normalizers route through it (7 separate "routes_location_through_normalize" tests in `test_normalizer.py`). |
| **FILT-07** | (NEW) US-only region filter — drops non-US postings | 04-02 | SATISFIED | REQUIREMENTS.md line 58: full definition added as 7th Filter entry with provenance footnote referencing CONTEXT.md D-03. Traceability table updated line 193. Coverage bumped 71→72 in both ROADMAP.md and REQUIREMENTS.md. Implementation: `src/filter.py:is_us_location_acceptable` (pure function). Wired in `src/main.py:_scrape_one` AFTER is_early_career, BEFORE state merge. Integration tests prove London-drop + SF-keep + INFO log emission. |
| **OUT-09** | Source Health (softened to data-persisted-not-rendered per D-04c) | 04-03 | SATISFIED | REQUIREMENTS.md line 91 struck-through with D-04c footnote pointing to CONTEXT.md. Data tracked in `seen.json.source_health` with status enum (ok/blocked/schema-drift/error) + consecutive_failures + last_attempt_utc + last_success_utc. Traceability table updated line 217. **NOT rendered in README** (D-04c critical invariant verified — see §4). |

**Orphaned requirements check:** REQUIREMENTS.md Phase 4 mapping lists exactly NORM-02, NORM-03, FILT-07, OUT-09 — all 4 accounted for in plans. No orphans.

---

## 3. ADP-14/15 Invariant — Adapter Stability Proof

**Claim:** Across ALL of Phase 4 (3 plans, 9 commits with `feat(04-*)` prefix), zero changes to `src/adapters/{greenhouse,lever,ashby,smartrecruiters,workday,apple,playwright_fallback}.py`.

| Check | Command | Result |
|-------|---------|--------|
| Files in src/adapters/ touched by Phase 4 | `git diff 947863a..HEAD --stat -- src/adapters/` | **empty (zero files)** |
| Last adapter commit | `git log --since="2026-06-07" -- src/adapters/` | `9e8a6dd feat(03-03)` — Phase 3 Plan 03-03 (no Phase 4 entries) |
| Adapter contract test | `pytest tests/test_adapter_contract.py` | **7/7 passed** including `test_new_adapter_can_be_added_without_touching_existing_files` and `test_greenhouse_adapter_is_self_contained` |
| Full suite regression | `pytest tests/` | **555/555 passed** (Phase 3 was 524; +31 net new in Phase 4, dominated by salary + location + FILT-07 + source_health) |

**ADP-15 invariant re-proven a 9th time** (Phase 1: 3 plans × 1 = 3; Phase 2: 3; Phase 3: 3; Phase 4: 3 — covering all plan executions across 4 phases).

---

## 4. D-04c Critical Invariants — Source Health Data-Persisted-Not-Rendered

D-04c is the locked decision that Source Health data MUST be tracked but MUST NOT be rendered. This section explicitly proves both halves.

### 4a. Data IS persisted (positive invariant)

| Check | Evidence |
|-------|----------|
| Schema version bumped 1→2 | `src/state_store.py:31` — `SCHEMA_VERSION: int = 2`. Test `test_schema_version_is_two` confirms (test_state_store.py:266). |
| `EMPTY_STATE` includes `source_health: {}` | `src/state_store.py:39`. Test `test_empty_state_includes_source_health` confirms (line 271). |
| Auto-migration v1→v2 | `src/state_store.py:111-120` adds empty `source_health` block in memory when loading v1. Tests `test_load_v1_state_auto_migrates_to_v2` (line 277) + `test_load_v1_then_save_round_trip_lands_v2` (line 304) + `test_save_atomic_rejects_v1_after_bump` (line 389). Fixtures `tests/fixtures/seen_v1_sample.json` + `seen_v2_sample.json` present. |
| `update_source_health` + `classify_outcome` helpers | `src/state_merger.py:111-187`. 13+ tests in test_state_merger.py covering all classification branches (ok/blocked-below-3/blocked-at-3/blocked-above-3/SchemaDrift/PlaywrightTimeout/InvalidCredential/MissingCredential/generic-error/no-adapter) + persistence of last_success_utc on failure + reset on success + 3-consecutive promotion to "blocked". |
| Orchestrator wiring | `src/main.py:280-282` — for each company, `update_source_health(merged, company.name, outcome, run_started_at)` is called AFTER `merge_state` and BEFORE `save_state_atomic`. |
| Persisted in seen.json | `src/state_merger.py:104` — `merge_state` carries `source_health` forward via shallow dict copy. `src/state_store.py:save_state_atomic` rejects writes with `schema_version != 2`, ensuring v2 payload (with source_health block) is the only thing written to disk. |

### 4b. Data is NOT rendered (negative invariant — the explicit user decision)

| Check | Command | Result |
|-------|---------|--------|
| renderer.py has zero source_health references | `grep -c -i "source_health" src/renderer.py` | **0** |
| renderer.py has zero "Source Health" string | `grep -c "Source Health" src/renderer.py` | **0** |
| README.md has no `## Source Health` heading | `grep -c "## Source Health\|Source Health" README.md` | **0** |
| README.md has no `<!-- BEGIN HEALTH -->` sentinel pair | `grep -c "BEGIN HEALTH\|END HEALTH" README.md` | **0** |
| README.md current sentinels | `grep "<!--" README.md` | only `<!-- BEGIN JOBS -->` / `<!-- END JOBS -->` (the postings-table sentinels from Phase 1) |
| REQUIREMENTS.md OUT-09 explicitly amended | `grep OUT-09 .planning/REQUIREMENTS.md` | line 91 shows the struck-through original text + D-04c footnote pointing to CONTEXT.md confirming "tracked but not rendered" |
| Renderer diff scope | `git diff 947863a..HEAD -- src/renderer.py` | Only ~66 lines of changes, all in the `_coalesce_salary` / `_truncate_cell` / `_SALARY_PLACEHOLDER_PATTERN` block + `_table_row` salary wiring. **No source_health references** added. |

**D-04c invariant fully verified. The "absent footer" is the desired outcome, NOT a gap.**

---

## 5. Pitfall Coverage Matrix

| Pitfall | Phase 4 Relevance | Status | Evidence |
|---------|-------------------|--------|----------|
| Pitfall 11 — salary regex misclassification | Superseded by D-01 verbatim approach (no parsing = no misclassification surface) | RESOLVED-BY-DESIGN | `src/normalizer.py` per-adapter salary helpers do `raw.get(<path>) or ""` only; no regex extraction. Renderer placeholder-coalesce uses a single anchored regex `_SALARY_PLACEHOLDER_PATTERN` (line 135) ONLY to detect known-empty surface forms — never to "parse" numeric ranges. |
| Pitfall 13 — Markdown table escaping | Already handled Phase 1's NORM-07. Phase 4 adds 80-char truncation. | INHERITED + EXTENDED | `src/renderer.py:_truncate_cell` (line 175) caps salary at 80 chars with single-codepoint U+2026 ellipsis BEFORE the standard `escape_markdown_cell` pass. Test `test_render_salary_pipe_in_value_is_escaped_after_coalesce` (test_renderer.py:534) covers the "pipe inside salary" risk. |
| Pitfall 20 — N-failure threshold for "blocked" status | D-04b encodes the 3+ consecutive rule | RESOLVED | `src/state_merger.py:137` — `classify_outcome` returns "blocked" iff `new_fail = prior+1 >= 3` when outcome=="blocked"; otherwise "error". Test `test_classify_outcome_blocked_at_threshold_returns_blocked` (test_state_merger.py:195) confirms (2→3 promotes, 5→6 stays blocked, 99→100 stays blocked). |
| Pitfall 27 — seen.json diff stability across orjson dump | Already handled Phase 1's `orjson.OPT_SORT_KEYS`. v2 payload preserves the same serialization options. | INHERITED | `src/state_store.py:200` — `orjson.dumps(state, option=orjson.OPT_SORT_KEYS | orjson.OPT_INDENT_2)`. Sorted keys mean adding `source_health` as a sibling of `postings` produces a stable, mergeable git diff. |

---

## 6. Test Counts & Cumulative Health

| Metric | Phase 3 baseline | Phase 4 delta | Phase 4 final |
|--------|------------------|---------------|---------------|
| pytest collected | 524 | +31 | **555 ✓** |
| pytest passing | 524 | +31 | **555 ✓** (60.5s wallclock) |
| ruff check | clean | (no new violations) | **clean ✓** |
| `test_locations.py` tests | 0 | +56 | 56 |
| `test_filter.py` (FILT-07 additions) | +X | +new | confirmed via 29 collected `def test_` |
| `test_normalizer.py` (salary + location additions) | (prior) | +new | 33 collected `def test_` |
| `test_renderer.py` (salary coalesce + truncation) | (prior) | +new | 32 collected `def test_` |
| `test_state_merger.py` (classify_outcome + update_source_health + 3-threshold) | (prior) | +new | 24 collected `def test_` |
| `test_state_store.py` (schema migration v1→v2 + v3-rejection retained) | (prior) | +new | 30 collected `def test_` |
| `test_orchestrator.py` (FILT-07 integration: London-drop + SF-keep + INFO log) | (prior) | +new | 21 collected `def test_` |
| `test_adapter_contract.py` | 7 | 0 | 7 (UNCHANGED — invariant) |

---

## 7. Anti-Patterns Found

None blocking.

| Severity | Note |
|----------|------|
| Info | Plans contain reasonable use of strings like `placeholder` (e.g., `_SALARY_PLACEHOLDER_PATTERN` in `src/renderer.py`) — these are correct semantic identifiers (the regex matches placeholder *values*), not implementation-stub markers. |
| Info | `salary = ""` in `_normalize_smartrecruiters` (line 325) and `_normalize_workday` (line 387) is **intentional** per D-01 — these ATSes do not expose a public salary field. Tests `test_smartrecruiters_helper_salary_always_empty` (line 698) and `test_workday_helper_salary_always_empty` (line 715) lock this behavior in. NOT a stub — the empty-string sentinel correctly cascades to renderer's `—` via `_coalesce_salary`. |

---

## 8. Gaps Found

**None.**

D-04c invariant explicitly states the README must NOT have a Source Health footer; verifier respects this and does NOT flag the absence of OUT-09 footer rendering as a gap. The CONTEXT.md override on D-04c is honored.

---

## 9. Human Verification Items

None required. All four success criteria are verifiable programmatically:
- Salary cell rendering: deterministic from per-adapter test fixtures + renderer unit tests
- Location normalization: pure function with comprehensive per-rule unit tests
- Source Health persistence: state round-trip tests + orchestrator integration test
- FILT-07 drop behavior: orchestrator integration test with London-vs-SF fixture proves drop + INFO log + README absence

---

## 10. Final Verdict

**Status: PASSED (4/4 gates)**

| Gate | Result |
|------|--------|
| 1. Salary verbatim per D-01 + placeholder coalesce per D-01a + 80-char truncation per D-01b | PASS |
| 2. Location normalize per D-02 (`Remote (US)` collapse) + `is_us_location` 8-rule classifier per D-02a | PASS |
| 3. Source Health data persisted in `seen.json.source_health` per D-04 + status classification per D-04b + per-run accumulation per D-04d + **NOT rendered in README per D-04c** (positive AND negative invariants both proven) | PASS |
| 4. FILT-07 wired AFTER `is_early_career` and BEFORE state merge per D-03a; London drop + SF keep integration test passes; ambiguous-bias to True per FILT-05 | PASS |

**ADP-14/15 invariant re-proven for the 9th consecutive plan execution** (zero changes to `src/adapters/*` across all 3 Phase 4 plans).

**All 4 expected REQ-IDs (NORM-02, NORM-03, FILT-07, OUT-09) closed per their CONTEXT.md decisions.**

**Pitfall coverage complete:** P11 (resolved-by-design), P13 (extended), P20 (resolved), P27 (inherited).

**All 555 tests pass; ruff is clean.**

Phase 4 — and with it the v1 milestone — is complete. The hourly job-tracker product as scoped in PROJECT.md ships at this commit.

---

*Verified: 2026-06-08*
*Verifier: Claude (gsd-verifier)*
