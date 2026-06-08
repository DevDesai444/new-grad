---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-06-08T02:18:00.000Z"
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 3
  completed_plans: 2
  percent: 67
---

# STATE: new-grad

## Project Reference

**Project:** new-grad
**Core Value:** One glance at the GitHub repo shows every currently-known new-grad-eligible role across the user's tracked companies, with a working application link.
**Mode:** mvp (Vertical MVP — every phase delivers an end-to-end working slice)
**Granularity:** coarse
**Total Phases:** 4

## Current Position

Phase: 01 (Walking Skeleton) — EXECUTING
Plan: 3 of 3 (Plans 01-01 and 01-02 complete; Plan 01-03 next)
**Milestone:** v1
**Phase:** 1 — Walking Skeleton
**Plan:** 01-02 complete — `feat(01-02): pure-core pipeline (normalize/filter/state/render/registry)` (commits 9879279, 59b897c, 814feea)
**Status:** Executing Phase 01 — 2/3 plans complete
**Progress:** [██████░░░░] 67%

### Phase 1 Goal

User opens repo and sees real Greenhouse postings in a README table updated within the last hour by GitHub Actions — every architectural seam exists, every existential risk is baked in, and the commit-back loop is proven on real infrastructure.

### Phase 1 Success Criteria

1. User opens `github.com/DevDesai444/new-grad` and sees a Markdown table with real Greenhouse postings updated within the last hour; Posting links open the company's career portal.
2. Hourly cron has fired at least twice; second run produces no spurious diff (idempotent render); `seen.json` correctly tracks `first_seen` / `last_seen`; nothing ever deleted from `seen.json`.
3. Killing the workflow mid-run or running `--validate` against a corrupted `seen.json` does not brick the next run — atomic write + `.bak` fallback + sanity gate (≥0.9× prior count) all engage; run exits non-zero on unrecoverable corruption, never silently wipes the table.
4. `gh secret list` shows zero secrets referenced by Phase 1 adapters; deliberate `git add` of `.env`/`cookies.json`/`trace.zip` is blocked by `.gitignore` + Push Protection; no credential string in workflow logs.
5. "Add this Greenhouse URL" via Claude CLI → one-line append to `companies.txt`, commit, push; next hourly run picks it up without further edits.

## Performance Metrics

- **Phases complete:** 0/4
- **Requirements mapped:** 71/71 (100%)
- **Requirements validated:** 42/71 (16 from Plan 01-01 + 26 from Plan 01-02: FILT-01/02/04/05/06, NORM-04/05/06/07, STATE-01..08, OUT-01..08, ADP-02)
- **Plans complete:** 2/3 in Phase 01 (Plan 01-01: 6min, 3 tasks, 19 files, 26 tests; Plan 01-02: ~25min, 3 tasks, 12 files, 124 new tests / 150 cumulative)
- **Existential risks addressed:** 5/5 in Phase 01 so far (concurrency group ✓, secret hygiene ✓, stable dedup keys ✓, schedule resilience via timeout-minutes:50 ✓, atomic write + .bak + sanity gate ✓ via Plan 01-02; health.json knowingly omitted per CONTEXT.md D-01)

### Per-Plan Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01    | 01   | 6min     | 3     | 19    |
| 01    | 02   | ~25min   | 3     | 12    |

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

**Last session:** 2026-06-08T02:18:00Z
**Last action:** Completed Plan 01-02 (3 tasks committed: 9879279, 59b897c, 814feea); 150/150 cumulative tests passing; `ruff check src/ tests/` clean; SUMMARY.md written at `.planning/phases/01-walking-skeleton/01-02-SUMMARY.md`.
**Stopped at:** Plan 01-02 complete — orchestrator should advance to Wave 3 / Plan 01-03
**Resume file:** `.planning/phases/01-walking-skeleton/01-03-PLAN.md`

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

**Next action:** Orchestrator advances to Plan 01-03 via `/gsd-execute-phase 1` continuation (Wave 3 — config_loader, main.py orchestrator, end-to-end test, README docs).

**Recovery context:** If session is interrupted, resume by reading `.planning/phases/01-walking-skeleton/01-CONTEXT.md` (Phase 1 locked decisions, supersedes ROADMAP success criteria where they conflict — e.g., INFRA-05 dropped; criterion #1 live-data verification deferred), then `.planning/phases/01-walking-skeleton/01-01-SUMMARY.md` (Wave 1) + `.planning/phases/01-walking-skeleton/01-02-SUMMARY.md` (Wave 2 — pure-core pipeline), then `.planning/phases/01-walking-skeleton/01-03-PLAN.md` (next wave to execute).

---
*State initialized: 2026-06-07*
*Plan 01-01 complete: 2026-06-08*
*Plan 01-02 complete: 2026-06-08*
