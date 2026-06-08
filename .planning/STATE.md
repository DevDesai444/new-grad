---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-06-08T01:54:30.632Z"
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 3
  completed_plans: 1
  percent: 33
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
Plan: 2 of 3 (Plan 01-01 complete; Plan 01-02 next)
**Milestone:** v1
**Phase:** 1 — Walking Skeleton
**Plan:** 01-01 complete — `feat(01-01): scaffold + models + Adapter ABC + Greenhouse adapter` (commits 3713ee9, 69be7f3, f6b0344)
**Status:** Executing Phase 01 — 1/3 plans complete
**Progress:** [███░░░░░░░] 33%

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
- **Requirements validated:** 16/71 (16 from Plan 01-01: INFRA-01/02/03/04/06/07/09/10, ADP-01/03/11/13, NORM-01, SEC-03/05, RUN-03)
- **Plans complete:** 1/12 (Plan 01-01: 6min, 3 tasks, 19 files, 26/26 tests, ruff clean, commits 3713ee9/69be7f3/f6b0344)
- **Existential risks addressed:** 4/5 in Plan 01-01 (concurrency group ✓, secret hygiene ✓, stable dedup keys ✓, schedule resilience via timeout-minutes:50 ✓; atomic write + sanity gate land in Plan 02; health.json knowingly omitted per CONTEXT.md D-01)

### Per-Plan Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01    | 01   | 6min     | 3     | 19    |

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

**Last session:** 2026-06-08T01:51:43Z
**Last action:** Completed Plan 01-01 (3 tasks committed: 3713ee9, 69be7f3, f6b0344); 26/26 tests passing; `ruff check src/ tests/` clean; SUMMARY.md written at `.planning/phases/01-walking-skeleton/01-01-SUMMARY.md`.
**Stopped at:** Plan 01-01 complete — orchestrator should advance to Wave 2 / Plan 01-02
**Resume file:** `.planning/phases/01-walking-skeleton/01-02-PLAN.md`

**Plan 01-01 Deliverables (Wave 1):**
- Scaffold: pyproject.toml, requirements.lock (uv-compiled, 91 lines), .gitignore (secrets + atomic-write transients blocked), README.md (sentinels + push-protection docs), companies.txt (header-only per D-03), .github/workflows/scan.yml (hourly cron + permissions + concurrency + cache + git-auto-commit-action@v5)
- Models: `src/models.py` (Posting / RawPosting / CompanyConfig — pydantic v2)
- Adapter ABC: `src/adapters/base.py` (Adapter + 4 typed errors)
- Greenhouse adapter: `src/adapters/greenhouse.py` + `tests/fixtures/greenhouse_stripe.json` (3-job fixture)
- Tests: 26 passing (9 models + 7 adapter base + 10 Greenhouse)

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

**Next action:** Orchestrator advances to Plan 01-02 via `/gsd-execute-phase 1` continuation (Wave 2 — pure-core pipeline).

**Recovery context:** If session is interrupted, resume by reading `.planning/phases/01-walking-skeleton/01-CONTEXT.md` (Phase 1 locked decisions, supersedes ROADMAP success criteria where they conflict — e.g., INFRA-05 dropped; criterion #1 live-data verification deferred), then `.planning/phases/01-walking-skeleton/01-01-SUMMARY.md` (what shipped in Wave 1), then `.planning/phases/01-walking-skeleton/01-02-PLAN.md` (next wave to execute).

---
*State initialized: 2026-06-07*
*Plan 01-01 complete: 2026-06-08*
