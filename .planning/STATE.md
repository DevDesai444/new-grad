---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Plan 02-03 execute-complete — Phase 2 execute-complete (all 6 REQ-IDs closed); ready for /gsd-verify-phase 2
last_updated: "2026-06-08T08:25:00.000Z"
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 7
  completed_plans: 6
  percent: 86
---

# STATE: new-grad

## Project Reference

**Project:** new-grad
**Core Value:** One glance at the GitHub repo shows every currently-known new-grad-eligible role across the user's tracked companies, with a working application link.
**Mode:** mvp (Vertical MVP — every phase delivers an end-to-end working slice)
**Granularity:** coarse
**Total Phases:** 4

## Current Position

Phase: 02 (ATS Breadth + JD-Scan) — EXECUTE-COMPLETE
Plan: 3 of 3 COMPLETE (all 3 Phase 2 plans landed)
**Milestone:** v1
**Phase:** 2 — ATS Breadth + JD-Scan
**Plan:** 02-03 complete — Apple adapter (ADP-08) + JD-scan (FILT-03) + D-02 simplification + retroactive Greenhouse D-03 (commits 589f1da Task 1, c44f910 Task 2, efba667 Task 3); 298 cumulative tests passing; ADP-08 + FILT-03 closed. Phase 2 execute-complete — all 6 phase REQ-IDs (ADP-04..08 + FILT-03) closed.
**Status:** Phase 02 execute-complete; awaiting `/gsd-verify-phase 2`
**Progress:** [█████████░] 86% (6/7 plans complete: 3 in Phase 1, 3 in Phase 2)

### Phase 1 Goal

User opens repo and sees real Greenhouse postings in a README table updated within the last hour by GitHub Actions — every architectural seam exists, every existential risk is baked in, and the commit-back loop is proven on real infrastructure.

### Phase 1 Success Criteria

1. User opens `github.com/DevDesai444/new-grad` and sees a Markdown table with real Greenhouse postings updated within the last hour; Posting links open the company's career portal.
2. Hourly cron has fired at least twice; second run produces no spurious diff (idempotent render); `seen.json` correctly tracks `first_seen` / `last_seen`; nothing ever deleted from `seen.json`.
3. Killing the workflow mid-run or running `--validate` against a corrupted `seen.json` does not brick the next run — atomic write + `.bak` fallback + sanity gate (≥0.9× prior count) all engage; run exits non-zero on unrecoverable corruption, never silently wipes the table.
4. `gh secret list` shows zero secrets referenced by Phase 1 adapters; deliberate `git add` of `.env`/`cookies.json`/`trace.zip` is blocked by `.gitignore` + Push Protection; no credential string in workflow logs.
5. "Add this Greenhouse URL" via Claude CLI → one-line append to `companies.txt`, commit, push; next hourly run picks it up without further edits.

## Performance Metrics

- **Phases complete:** 0/4 (Phase 1 + Phase 2 both execute-complete, awaiting verification)
- **Requirements mapped:** 71/71 (100%)
- **Requirements validated:** 62/71 (56 in Phase 1 + ADP-04/05/06 in Plan 02-01 + ADP-07 in Plan 02-02 + ADP-08 + FILT-03 in Plan 02-03)
- **Plans complete:** 6/7 (3/3 in Phase 01 + 3/3 in Phase 02 — Plan 02-03: ~30min, 3 tasks, 3 created + 7 modified files, 49 new tests / 298 cumulative)
- **Existential risks addressed:** 5/5 in Phase 01 (unchanged)

### Per-Plan Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01    | 01   | 6min     | 3     | 19    |
| 01    | 02   | ~25min   | 3     | 12    |
| 01    | 03   | ~8min    | 3     | 7 (6 new + 1 mod) |
| 02    | 01   | ~25min   | 3     | 11 (9 new + 2 mod) |
| 02    | 02   | ~25min   | 2     | 5 (3 new + 2 mod)  |
| 02    | 03   | ~30min   | 3     | 10 (3 new + 7 mod) |

## Accumulated Context

### Key Decisions (from PROJECT.md)

| Decision | Rationale |
|----------|-----------|
| GitHub Actions cron, not laptop cron | Zero-touch; laptop must not need to be on |
| Public repo over private | Unlimited free Action minutes |
| Python + Playwright stack | Best ecosystem for hybrid ATS-API + headless-browser scraping |
| Markdown table in README.md | Repo homepage = the UI; no separate site needed |
| Keep stale postings forever | User explicitly prefers history over freshness |
| Experience range as its own column | User wants 0–5 yrs visibility per posting |
| Dedup by per-ATS stable ID (`gh:<co>:<id>`) | Most stable identifier; raw URL dedup fails on tracking params |
| `seen.json` state file committed to the repo | No database; repo IS the database |
| Credentials in GitHub Actions Secrets only | Public repo means anything in the repo is exposed |

### Decisions Made During Execution

| Plan | Decision | Rationale |
|------|----------|-----------|
| 01-01 | One commit per task (RED + GREEN batched) | Matches plan's "commit each task atomically" outer cadence; tests still written first + run RED before implementation |
| 01-01 | Pinned Playwright in requirements.txt but did NOT install via workflow | Per CONTEXT.md D-05; pin keeps requirements.lock hash stable so Phase 3 cache hits cleanly |
| 01-01 | Greenhouse adapter stashes `__dedup_key` + `__board_token` in raw response | Per ARCHITECTURE.md — normalizer (Plan 02) reads them without recomputing |
| 01-01 | `Optional[X]` → `X \| None` in src/models.py (ruff UP045 auto-fix) | Required for plan's own `ruff check` verification step to pass; behavior identical |
| 01-01 | Workflow "Run scan" step is guarded stub `if [ -f src/main.py ]; then ...` | Keeps CI green from day one; Plan 03's main.py drops in cleanly without a workflow edit |
| 01-02 | Sanity gate `_SANITY_FLOOR_RATIO = 0.9` is a module-level private constant, not config-driven | CONTEXT.md D-06 makes the 90% threshold a permanent semantic, not a tunable knob |
| 01-02 | `save_state_atomic` rejects writes with wrong `schema_version` (defensive) | Symmetric defense vs `load_state` raising `UnknownSchemaVersion`; prevents accidentally writing forward-incompatible state |
| 01-02 | Renderer falls back to `first_seen` for Age when `posted_date` is None | Keeps Age column always meaningful (coalesce-style behavior) |
| 01-02 | Hint-resolution falls through to URL match when hint name does not resolve | Defensive: a typo or future-ATS hint should not block a recognizable URL |
| 01-02 | `_posting_to_record` produces dict (not Pydantic .model_dump()) | Keeps on-disk state shape decoupled from model evolution; future Posting fields don't auto-break state file shape |
| 01-02 | `timezone.utc` → `UTC` alias auto-fix (ruff UP017) | Required for plan's own `ruff check` verification step to pass; behavior identical |
| 01-02 | Renderer docstring `datetime.now(UTC)` reference removed | Required for plan's `grep -c 'datetime.now' src/renderer.py` AC to return at most 1 (literal grep was matching the docstring) |
| 01-03 | `# noqa: UP017` on `datetime.now(timezone.utc)` in src/main.py | Plan's literal AC requires the `datetime.now(timezone.utc)` substring; ruff UP017 wants the `UTC` alias. noqa preserves the AC literal while keeping ruff clean — same precedent as Plans 01-01/01-02. |
| 01-03 | Reworded `traceback.format_exc` references in docstrings/comments | Plan AC: `grep -c "traceback.format_exc" src/main.py == 0`. Substring was present in comments explaining what we DON'T do. Reworded to `format full tracebacks` / `the full traceback`; intent preserved. |
| 01-03 | Three-arm per-company isolation in main._scrape_one | Finer-grained than the plan's two-arm example: third arm catches per-posting normalize exceptions so one malformed entry doesn't kill the rest of a company's postings. |
| 01-03 | Sanity-gate `new_count` arg = `count(still_listed=True in merged)`, not raw fresh count | Correct semantic for "visible postings"; otherwise a scan returning 0 fresh would falsely trigger gate when prior had still-listed-flip-to-False entries. |
| 01-03 | README `Push protection` → `Push Protection` (capitalization) | Plan AC literal-grep match; substance unchanged. |
| 02-01 | Ship 9 tests per adapter instead of plan's 8 | Split `test_fetch_emits_stable_dedup_key` out of happy-path test for clearer regression signal; 27 new vs plan's 24. |
| 02-01 | `name="smartrecruiters"` vs dedup-prefix `"sr:"` split locked via dedicated regression test (`test_fetch_emits_stable_dedup_key_with_sr_prefix`) | Asserts BOTH `startswith('sr:')` AND `not startswith('smartrecruiters:')` to lock CONTEXT.md D-01a into the suite; full word + short prefix is intentional. |
| 02-01 | Lever epoch-ms `createdAt` defensively None-on-bad-input rather than SchemaDrift | Lever sometimes omits the timestamp; `posted_date=None` is the correct render outcome (mirrors `_parse_iso_to_utc`'s contract). |
| 02-01 | Each adapter defines its own module-level `_TIMEOUT_S = 20.0` rather than importing a shared constant | Locality + per-adapter tunability without touching siblings; mirrors greenhouse.py's pattern. |
| 02-02 | Task 1 ships standalone-functional even before Task 2's pagination wrap | Single-page tenants work at HEAD of Task 1; diff stays small per commit; Task 2 wrapper is purely additive. |
| 02-02 | `WorkdayAdapter.matches()` uses cheap subdomain substring check, not the full URL regex | matches() must be cheap per ADP-01 — substring is O(len(host)) vs regex compile+match cost on every URL lookup. |
| 02-02 | `_parse_workday_url` emits diagnostic SchemaDrift naming WHICH piece is missing (host vs site) via a partial-match probe | Defensive UX: user fixing a typo in companies.txt sees what's wrong without log-diving. |
| 02-02 | `fetch(company, seen_keys=None)` — optional kwarg default preserves Phase 1 single-arg Adapter.fetch contract | Behavior degrades gracefully to cold-start-cap-only when orchestrator hasn't been wired to thread seen_keys; correct in both modes. |
| 02-02 | Sort-monotonicity violation logs WARNING + suppresses early-term, does NOT abort | Tradeoff favors completeness over speed when tenant sort ordering is broken. |
| 02-02 | `_parse_workday_posted` excludes `bool` from the epoch-ms branch via `not isinstance(value, bool)` | Python `bool` is a subclass of `int` (True == 1); a JSON `true` value should not silently become datetime(1970-01-01, 1ms). |
| 02-02 | `time.sleep` is monkeypatched to noop in slow tests via `src.adapters.workday.time.sleep -> lambda s: None` | Keeps `test_fetch_cold_start_cap_25_pages` under 100ms instead of ~25s; production keeps real sleep for rate-limit hedging. |
| 02-02 | Ship 35 tests vs plan's "~14" budget | Granular split per postedOn form / per malformed-URL case gives clearer regression signal; no scope creep, all defend documented behavior. |
| 02-03 | Apple `matches()` accepts ANY jobs.apple.com subpath; no path validation | Per CONTEXT.md D-01a Apple is single-org; user can paste search / details / browse URL — adapter ignores path and POSTs the broad endpoint. |
| 02-03 | Apple dedup-key regex test uses `^apple:[^:]+$` (one colon, not two) | Locks D-01a invariant into the suite — `apple:<id>` not `apple:apple:<id>`; mirrors the SR `name="smartrecruiters"` vs `"sr:"` precedent test from Plan 02-01. |
| 02-03 | `is_early_career` body is one line (`return _passes_title_gate(...)`); zero `experience_min` references | D-02 simplification taken at the source — docstring documents the change but no live code touches `experience_min`. AC literal-grep `awk '/^def is_early_career/,/^def /' src/filter.py \| grep -c experience_min` returns 0. |
| 02-03 | Phase 1 `test_experience_min_above_ceiling_overrides_title_pass` REWRITTEN as `test_is_early_career_ignores_experience_min_per_d02`, not deleted | Same test slot, inverted assertion, explicit docstring pointing to CONTEXT.md D-02 — preserves Phase 1's grep-able test-id while encoding the new D-02 invariant. |
| 02-03 | Workday `__description` hook wired even though CXS /jobs doesn't return per-posting description today | Future per-posting detail fetch starts populating Experience automatically with zero normalizer changes — the JD-scan layer is open-closed for future Workday enhancements. |
| 02-03 | `commit -m` HEREDOC switched to `commit -F /tmp/<file>.txt` for Tasks 2 + 3 after a bash quoting failure on apostrophes | Mechanical workaround — no content lost; commits applied cleanly. Documented for future Phase 3/4 commit-message authors. |
| 02-03 | REQUIREMENTS.md FILT-04 line keeps `[x]` checkbox + adds `~~**FILT-04**~~` + footnote | Same convention as Phase 1 INFRA-05 strikethrough — the Phase 1 implementation literally satisfied FILT-04; the softening is a SEMANTIC change documented via strikethrough + footnote, not an unship. |
| 02-03 | Apple sort-monotonicity violation logs WARNING + suppresses early-term (degrade to cap-only) | Mirrors Workday from Plan 02-02 — same tradeoff: completeness over speed when source sort ordering breaks. |
| 02-03 | Ship 49 tests vs plan's "≥22" budget | Granular split per regex form + 2 Workday cases (absent vs stashed __description) + 4 retroactive Greenhouse tests + 16 Apple tests; defends explicit behavior per AC. |

### Open Decisions

(none yet — surfaced during planning)

### Todos

(none yet — surfaced during planning)

### Blockers

(none)

### Research Flags for Phase 2 (when implementation begins)

- Verify current Workday CXS POST body shape, response field names, and pagination token format against a live tenant before locking adapter contracts (training data is MEDIUM confidence)
- Verify Apple Jobs `api/role/search` current request/response shape — endpoint is stable but field names drift
- Build a live test corpus from real postings before writing the salary pattern library (deferred to Phase 4)

### Research Flags for Phase 3 (when implementation begins)

- Identify the specific XHR intercept target or stable selector for the chosen JS-heavy SPA target
- Validate `playwright-stealth` effectiveness vs current DataDome/PerimeterX per target site (LOW confidence from training data)

## Session Continuity

**Last session:** 2026-06-08T08:25:00Z
**Last action:** Completed Plan 02-03 (3 tasks committed: 589f1da Task 1 = Apple adapter + D-04 pagination + 16 tests; c44f910 Task 2 = JD-scan (FILT-03) + wire all 6 normalizers + D-02 is_early_career simplification + REQUIREMENTS.md FILT-04 strikethrough; efba667 Task 3 = retroactive Greenhouse D-03 tests closing Phase 1 W-1/D-07 debt); 298/298 cumulative tests passing (249 baseline + 49 new); `ruff check src/ tests/` clean; `python -m src.main` against placeholder companies.txt exits 0; SUMMARY.md written at `.planning/phases/02-ats-breadth-jd-scan/02-03-SUMMARY.md`. ADP-08 + FILT-03 complete — Phase 2 execute-complete, all 6 phase REQ-IDs closed. ADP-14/15 open-closed re-proven across all 3 Phase 2 plans: 0 edits to main.py / models.py / state_*.py / renderer.py / config_loader.py. Registry now holds 6 adapters (greenhouse, lever, ashby, smartrecruiters, workday, apple); normalizer dispatch covers all 6 sources; every per-adapter normalizer wires extract_experience_range; is_early_career is title-gate-only per D-02. Greenhouse adapter has parity D-03 6-test coverage with the 5 newer adapters; D-07 deferred-test debt formally closed.
**Stopped at:** Plan 02-03 execute-complete — Phase 2 execute-complete; ready for `/gsd-verify-phase 2`
**Resume file:** `.planning/phases/02-ats-breadth-jd-scan/02-03-SUMMARY.md` (Phase 2 done; next milestone is verification)

**Plan 01-01 Deliverables (Wave 1):**

- Scaffold: pyproject.toml, requirements.lock (uv-compiled, 91 lines), .gitignore (secrets + atomic-write transients blocked), README.md (sentinels + push-protection docs), companies.txt (header-only per D-03), .github/workflows/scan.yml (hourly cron + permissions + concurrency + cache + git-auto-commit-action@v5)
- Models: `src/models.py` (Posting / RawPosting / CompanyConfig — pydantic v2)
- Adapter ABC: `src/adapters/base.py` (Adapter + 4 typed errors)
- Greenhouse adapter: `src/adapters/greenhouse.py` + `tests/fixtures/greenhouse_stripe.json` (3-job fixture)
- Tests: 26 passing (9 models + 7 adapter base + 10 Greenhouse)

**Plan 01-02 Deliverables (Wave 2):**

- Normalizer: `src/normalizer.py` (RawPosting → Posting; URL canonicalize; UTC date conv; per-adapter dispatch)
- Filter: `src/filter.py` (title-keyword gate with 10+10 patterns; FILT-04 ceiling; FILT-05 bias)
- State store: `src/state_store.py` (atomic write via os.replace + .bak; .bak read fallback; sanity gate per D-06; SCHEMA_VERSION=1)
- State merger: `src/state_merger.py` (add-only two-pass merge; first_seen preserved; STATE-05 still_listed flip)
- Renderer: `src/renderer.py` (sentinel splice; Markdown escape with 5 invisible-Unicode codepoints; OUT-07 idempotent; OUT-08 placeholder)
- Registry: `src/registry.py` (ADAPTERS = [GreenhouseAdapter]; hint-override per CFG-03; NoAdapterFound for CFG-05)
- Tests: 124 new (51 normalizer+filter; 33 state; 40 renderer+registry); cumulative 150 passing

**Plan 01-03 Deliverables (Wave 3 — final wave; Phase 1 execute-complete):**

- Config loader: `src/config_loader.py` (companies.txt parser; CFG-01/02/03/05; BOM tolerance; logged-skip on malformed lines)
- Orchestrator: `src/main.py` (single run_started_at; per-company try/except isolation; SiteBlocked → any_blocked → sanity-gate carve-out; SchemaDrift/PlaywrightTimeout/MissingCredential typed catches; generic Exception catch logs class+str ONLY; summary to stdout + $GITHUB_STEP_SUMMARY; exit codes 0/1/2)
- Tests: 37 new (17 config_loader + 10 orchestrator + 3 end-to-end + 7 adapter contract); cumulative 187 passing
- README documentation: CFG-06 (companies.txt format), CFG-04 (Add a Company flow), SEC-03 (Secret Hygiene + naming-convention placeholder), Hourly Cadence with D-02 60-day acknowledgment, Recovery, Ops Quick Reference, ToS Hygiene; INFRA-08 Push Protection capitalized
- End-to-end test result: respx-mocked Greenhouse → New Grad + Associate postings persisted, Senior posting filtered out, [Apply] link in README, sentinels preserved; second consecutive run under frozen clock produces byte-identical seen.json + README (D-04 acceptance gate proven)
- ADP-12 isolation test result: RaisingAdapter raises RuntimeError; OkAdapter still succeeds; exit code 0; only OK posting persisted
- Sanity-gate state-preservation test result: 100 prior, 0 visible, no `any_blocked` → exit 1; seen.json bytes unchanged (T-03-02 mitigation)
- `python -m src.main` against placeholder companies.txt exits 0 (zero companies, empty merge, README placeholder rendered)

**Files written previously (planning):**

- `.planning/phases/01-walking-skeleton/01-CONTEXT.md` (gathered earlier via discuss-phase)
- `.planning/phases/01-walking-skeleton/01-DISCUSSION-LOG.md` (audit trail)
- `.planning/phases/01-walking-skeleton/01-SKELETON.md` (Walking Skeleton manifest)
- `.planning/phases/01-walking-skeleton/01-01-PLAN.md` (Wave 1 — scaffold + models + Adapter ABC + Greenhouse adapter)
- `.planning/phases/01-walking-skeleton/01-02-PLAN.md` (Wave 2 — normalizer, filter, state_store, state_merger, renderer, registry)
- `.planning/phases/01-walking-skeleton/01-03-PLAN.md` (Wave 3 — config_loader, main.py, end-to-end test, README docs)
- `.planning/ROADMAP.md` (Phase 1 plans list finalized; INFRA-05 struck through per CONTEXT.md D-01)

**Plan-checker warnings (non-blocking, recorded for transparency):**

- W-1 (CONTEXT.md drift): Plan 01-01 Task 3 ships 2 single-line error-branch smoke tests beyond D-07's "happy-path only" guidance. **Outcome:** orchestrator prompt directed to keep them; both tests pass. Accepted.
- W-2 (long-term gate semantics): Phase 1's sanity gate compares `still_listed_count` against monotonically-growing `prior_count`. Over many months `still_listed_count < 0.9 * prior_count` becomes structurally inevitable. Implementation matches STATE-06 as written. Fix can be deferred (most naturally to Phase 4 alongside OUT-09).

**Next action:** Phase 1 execute-complete. Next step is verification (`/gsd-verify-phase 1` or equivalent), then user-side go-live steps: (1) enable GitHub Push Protection in repo settings (INFRA-08 / user_setup), (2) push the repo to `github.com/DevDesai444/new-grad`, (3) optionally add real Greenhouse URLs to `companies.txt` to begin live operation per CONTEXT.md D-03.

**Recovery context:** If session is interrupted, resume by reading `.planning/phases/01-walking-skeleton/01-CONTEXT.md` (Phase 1 locked decisions, supersedes ROADMAP success criteria where they conflict — e.g., INFRA-05 dropped; criterion #1 live-data verification deferred), then `.planning/phases/01-walking-skeleton/01-01-SUMMARY.md` (Wave 1) + `.planning/phases/01-walking-skeleton/01-02-SUMMARY.md` (Wave 2 — pure-core pipeline) + `.planning/phases/01-walking-skeleton/01-03-SUMMARY.md` (Wave 3 — orchestrator + e2e). Phase 1 deliverables: 10 source modules, 13 test files / 187 tests, 1 GitHub Actions workflow, 1 placeholder companies.txt, README with sentinels + full user-facing operational docs.

---
*State initialized: 2026-06-07*
*Plan 01-01 complete: 2026-06-08*
*Plan 01-02 complete: 2026-06-08*
*Plan 01-03 complete: 2026-06-08 — Phase 1 execute-complete.*
*Plan 02-01 complete: 2026-06-08 — Lever + Ashby + SmartRecruiters adapters (ADP-04/05/06); 214 tests; ADP-14/15 open-closed re-proven.*
*Plan 02-02 complete: 2026-06-08 — Workday adapter (ADP-07); 249 tests; ADP-14/15 open-closed re-proven with 5 adapters; D-01 URL auto-parse + D-04 pagination with 25-page cap + sort-monotonicity + 3-form postedOn resolver + realistic User-Agent (Pitfall 5).*
*Plan 02-03 complete: 2026-06-08 — Apple adapter (ADP-08) + JD-scan (FILT-03) + D-02 is_early_career simplification + retroactive Greenhouse D-03 tests + REQUIREMENTS.md FILT-04 strikethrough; 298 tests; Phase 2 execute-complete (all 6 phase REQ-IDs closed: ADP-04..08 + FILT-03); ADP-14/15 open-closed re-proven across all 3 Phase 2 plans with 6 adapters.*
