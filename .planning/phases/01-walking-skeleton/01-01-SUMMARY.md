---
phase: 01-walking-skeleton
plan: 01
subsystem: infra
tags: [python, pydantic, httpx, respx, pytest, ruff, uv, github-actions, greenhouse, adapter-pattern]

# Dependency graph
requires:
  - phase: planning
    provides: ARCHITECTURE.md (file layout), STACK.md (locked deps), PITFALLS.md (existential risks), CONTEXT.md (D-01..D-08 decisions)
provides:
  - Buildable Python 3.12 codebase scaffolding (pyproject.toml, requirements.lock, .gitignore, README sentinels, placeholder companies.txt)
  - Hourly GitHub Actions workflow with all 5 existential-risk mitigations baked in
  - Canonical pydantic v2 data models (Posting, RawPosting, CompanyConfig)
  - Adapter ABC + four typed exception classes (SiteBlocked, SchemaDrift, PlaywrightTimeout, MissingCredential)
  - One working Greenhouse adapter emitting stable `gh:<board_token>:<id>` dedup keys
  - Recorded Greenhouse JSON fixture (3 jobs covering filter pass + reject cases) for offline pipeline tests
  - 26 passing pytest tests (9 models + 7 adapter base + 10 Greenhouse)
affects: [01-02-walking-skeleton, 01-03-walking-skeleton, phase-02-ats-breadth, phase-03-playwright-fallback]

# Tech tracking
tech-stack:
  added: [httpx 0.28.1, pydantic 2.12.4, orjson 3.11.4, tenacity 9.1.4, selectolax 0.4.10, beautifulsoup4 4.15.0, dateparser 1.2, playwright 1.45+ (pinned, not installed), python-dotenv, pytest 9.0.3, respx 0.23.1, ruff 0.15.16, uv]
  patterns:
    - "Adapter ABC + URL-pattern dispatch — one file per ATS, zero core edits to add new sources (ARCHITECTURE.md §Pattern 1)"
    - "Pure-core / impure-edges — models contain zero I/O and zero datetime.now() calls (CONTEXT.md §Code Insights)"
    - "Stable per-ATS dedup keys `gh:<board_token>:<id>` extracted from API response, never URL-based (PITFALLS.md Pitfall 5)"
    - "Sentinel-bracketed render region in README.md (<!-- BEGIN/END JOBS -->) for safe partial overwrite"
    - "Concurrency group + cancel-in-progress=false in workflow serializes runs (PITFALLS.md Pitfall 3)"
    - "Secret-shaped files blocked by .gitignore BEFORE first commit (PITFALLS.md Pitfall 4, preventative)"

key-files:
  created:
    - pyproject.toml
    - requirements.txt
    - requirements.lock
    - requirements-dev.txt
    - .gitignore
    - README.md
    - companies.txt
    - .github/workflows/scan.yml
    - src/__init__.py
    - src/models.py
    - src/adapters/__init__.py
    - src/adapters/base.py
    - src/adapters/greenhouse.py
    - tests/__init__.py
    - tests/fixtures/.gitkeep
    - tests/fixtures/greenhouse_stripe.json
    - tests/test_models.py
    - tests/test_adapter_base.py
    - tests/test_greenhouse_adapter.py
  modified: []

key-decisions:
  - "Used `uv pip compile` to generate requirements.lock (deterministic pins; Python 3.12 floor)"
  - "Greenhouse adapter matches both `boards.greenhouse.io` and `job-boards.greenhouse.io` hostnames (both in production 2025–2026)"
  - "Dedup key stashed in raw['__dedup_key'] inside the adapter so the future normalizer (Plan 02) reads it without re-computing per ARCHITECTURE.md"
  - "Greenhouse adapter raises SiteBlocked on 403/429/5xx and SchemaDrift on missing 'jobs' key / non-JSON / wrong types — code path live in Phase 1 even though full coverage is deferred to Phase 2 per CONTEXT.md D-07"
  - "Workflow's 'Run scan' step is a guarded stub `if [ -f src/main.py ]; then ...; else echo 'not yet built'; fi` so CI is green from day one and Plan 03's main.py drops in cleanly"
  - "Playwright is pinned in requirements.txt (so requirements.lock hash includes it, Phase 3 cache hits cleanly) but `python -m playwright install` is NOT invoked in Phase 1 per CONTEXT.md D-05"

patterns-established:
  - "Adapter pattern: every ATS = one file under src/adapters/ implementing Adapter ABC; URL-pattern dispatch via classmethod `matches()`"
  - "Typed-exception ladder for adapters (SiteBlocked / SchemaDrift / PlaywrightTimeout / MissingCredential) — distinguishes 'blocked' from 'empty', and routes per-company isolation"
  - "respx + recorded JSON fixture for adapter happy-path tests — zero network in CI"
  - "Ruff config in pyproject.toml [tool.ruff.lint] selects E/F/I/B/W/UP (UP = PEP-604 modern type-hint enforcement)"

requirements-completed:
  - INFRA-01
  - INFRA-02
  - INFRA-03
  - INFRA-04
  - INFRA-06
  - INFRA-07
  - INFRA-09
  - INFRA-10
  - ADP-01
  - ADP-03
  - ADP-11
  - ADP-13
  - NORM-01
  - SEC-03
  - SEC-05
  - RUN-03

# Metrics
duration: ~6 min
completed: 2026-06-08
---

# Phase 1 Plan 1: Walking Skeleton — Scaffolding + Models + Greenhouse Adapter Summary

**Buildable Python 3.12 codebase with pydantic v2 models, Adapter ABC + 4 typed errors, one working Greenhouse adapter emitting stable `gh:<board>:<id>` dedup keys, and an hourly GitHub Actions workflow wired with all 5 existential-risk mitigations (concurrency group, permissions, timeout, cache, commit-back) — 26 happy-path tests passing via respx mocks against a recorded Stripe fixture.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-08T01:45:39Z
- **Completed:** 2026-06-08T01:51:43Z
- **Tasks:** 3
- **Files created:** 19 (16 listed in plan `files_modified` + 3 test files: test_models.py, test_adapter_base.py — plus the implicit tests/fixtures/.gitkeep)

## Accomplishments

- Project scaffold (pyproject.toml, requirements.lock, .gitignore with secret blocklist, README with sentinels, placeholder companies.txt, GitHub Actions workflow)
- Canonical data models (Posting / RawPosting / CompanyConfig) with pydantic v2 validation
- Adapter ABC + four typed exception classes (SiteBlocked, SchemaDrift, PlaywrightTimeout, MissingCredential)
- One working Greenhouse adapter — matches both `boards.greenhouse.io` and `job-boards.greenhouse.io`, extracts board token from any URL form, raises typed exceptions on 403/429/5xx and missing-`jobs` payloads, stashes stable dedup keys inside raw response for downstream normalizer
- Recorded Greenhouse JSON fixture (3 jobs: New Grad / Senior Staff / Associate) covering both filter pass + reject cases
- 26 passing pytest tests — 9 models, 7 adapter base, 10 Greenhouse adapter
- `ruff check src/ tests/` clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Project scaffolding + workflow YAML + src/tests packages** — `3713ee9` (feat)
2. **Task 2: Canonical pydantic models + Adapter ABC with typed errors** — `69be7f3` (feat)
3. **Task 3: Greenhouse adapter + recorded fixture + happy-path tests** — `f6b0344` (feat)

**Plan metadata commit:** (to be added by orchestrator final commit step)

_Note: Each task internally followed RED → GREEN. Test files were written first and confirmed failing (RED), then implementation files were written and tests confirmed passing (GREEN). Per plan task-commit cadence, RED and GREEN are batched into a single task commit rather than separate `test(...)` / `feat(...)` commits — this matches the plan's outer "one commit per task" expectation._

## Files Created/Modified

### Scaffolding (Task 1)
- `pyproject.toml` — Python 3.12 floor, ruff (E/F/I/B/W/UP) config, pytest pythonpath=['.'], testpaths=['tests']
- `requirements.txt` — runtime deps (httpx, tenacity, selectolax, bs4, playwright pinned-but-not-installed, pydantic, orjson, dateparser, python-dotenv)
- `requirements-dev.txt` — pytest, respx, ruff
- `requirements.lock` — `uv pip compile` deterministic pins (91 lines)
- `.gitignore` — Python artifacts + secrets (.env, cookies.json, *.har, trace.zip, playwright-report/) + state-store transients (seen.json.tmp/.bak) + OS junk
- `README.md` — `<!-- BEGIN JOBS -->` / `<!-- END JOBS -->` sentinels around "(no matching postings yet)" placeholder; INFRA-08 push-protection docs
- `companies.txt` — header-only placeholder per CONTEXT.md D-03 (zero http(s) URL lines)
- `.github/workflows/scan.yml` — hourly cron (`0 * * * *`), `permissions: contents: write`, `concurrency: group: scan, cancel-in-progress: false`, `timeout-minutes: 50`, `actions/setup-python@v5` with Python 3.12, uv install, Playwright cache (`actions/cache@v4` keyed on requirements.lock), guarded `python -m src.main` run step, `stefanzweifel/git-auto-commit-action@v5`
- `src/__init__.py`, `src/adapters/__init__.py`, `tests/__init__.py`, `tests/fixtures/.gitkeep` — package markers

### Models + Adapter ABC (Task 2)
- `src/models.py` — `CompanyConfig` (with http(s)-only URL validator), `RawPosting` (source_company / source_adapter / raw dict), `Posting` (all 13 NORM-01 fields: dedup_key, company, title, location, salary, experience_min/max, posting_url, posted_date, first_seen, last_seen, still_listed, source_adapter). Zero I/O, zero datetime.now() — pure-core per CONTEXT.md.
- `src/adapters/base.py` — `Adapter(ABC)` with `name: ClassVar[str]`, `@classmethod @abstractmethod matches(cls, url) -> bool`, `@abstractmethod fetch(self, company) -> list[RawPosting]`. Four typed exception classes (SiteBlocked, SchemaDrift, PlaywrightTimeout, MissingCredential).
- `tests/test_models.py` — 9 tests (happy-path + min_length validation + URL scheme validator + defaults)
- `tests/test_adapter_base.py` — 7 tests (abstract instantiation rejection + 4 parametrized exception inheritance checks + distinctness + subclass abstractness)

### Greenhouse Adapter (Task 3)
- `src/adapters/greenhouse.py` — `GreenhouseAdapter(Adapter)` with `name = "greenhouse"`. Matches both Greenhouse hostnames. `_extract_board_token` handles `/stripe`, `/stripe/`, `/stripe/jobs/123` URL forms. `fetch()` calls `https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true` via httpx with 20s timeout; raises `SiteBlocked` on 403/429/5xx and `SchemaDrift` on non-JSON / missing `jobs` key / wrong type. Stashes `__dedup_key = f"gh:{board_token}:{job['id']}"` and `__board_token` inside `raw` so the normalizer doesn't re-compute.
- `tests/fixtures/greenhouse_stripe.json` — 3 jobs: row 0 "Software Engineer, New Grad" (filter pass), row 1 "Senior Staff Engineer, Infrastructure" (filter reject), row 2 "Associate Software Engineer" (filter pass). Row 1's URL has `?utm_source=careers` to exercise future URL canonicalization in normalizer.
- `tests/test_greenhouse_adapter.py` — 10 tests via respx mock (3 matches() + 3 _extract_board_token() variants + happy-path fetch + stable-dedup-key assertion + 2 W-1 smoke tests for SiteBlocked/SchemaDrift)

### Auto-fixed (Task 3 deviation)
- `src/models.py` (modified) — ruff UP045 auto-fix: `Optional[X]` → `X | None`, removed now-unused `Optional` import. Behavior identical; required for plan's `ruff check src/ tests/` verification step to exit 0.

## Decisions Made

- **Per-task RED/GREEN batched into single commit** — plan specifies "commit each task atomically" so the executor honored that outer cadence rather than emitting separate `test(...)` and `feat(...)` commits per the orchestrator-defined TDD micro-cycle. Tests were nonetheless written first and confirmed failing before any implementation.
- **Pinned Playwright in `requirements.txt`** (per plan D-05 / STACK.md note) so the lockfile hash invalidates correctly when Phase 3 actually installs Chromium — but `python -m playwright install` is NOT invoked by the workflow's scan step.
- **Workflow's run step is guarded** (`if [ -f src/main.py ]; then python -m src.main; else echo ...; fi`) so the workflow YAML is valid + CI green from Plan 01 onward, and Plan 03's `src/main.py` lands without a workflow edit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug / Lint Compliance] Updated `Optional[X]` → `X | None` in src/models.py**
- **Found during:** Task 3 verification (`ruff check src/ tests/`)
- **Issue:** Plan's literal action block specified `from typing import Optional` and `Optional[str]` type hints, but pyproject.toml's ruff config selects the `UP` ruleset with `target-version = "py312"`, which raises `UP045` for `Optional[X]` (PEP-604 modernization). The plan's own verification step requires `ruff check` to exit 0, so this is an internal plan inconsistency, not project drift.
- **Fix:** Ran `ruff check src/ tests/ --fix` — auto-rewrites `Optional[X]` to `X | None` (6 replacements) and removes the now-unused `Optional` import.
- **Files modified:** `src/models.py`
- **Verification:** `ruff check src/ tests/` exits 0; all 26 tests still pass.
- **Committed in:** `f6b0344` (Task 3 commit)

### Documented but not deviations

**W-1 (CONTEXT.md drift, planner-self-documented):** Plan 01-01 Task 3 ships 2 single-line error-branch smoke tests (`test_fetch_raises_site_blocked_on_403`, `test_fetch_raises_schema_drift_on_missing_jobs_key`) beyond CONTEXT.md D-07's "happy-path only" guidance. The orchestrator prompt explicitly directed to **keep them** as cheap extra coverage. Outcome: tests passing, deviation accepted.

---

**Total deviations:** 1 auto-fixed (1 lint-compliance bug)
**Impact on plan:** Auto-fix essential for the plan's own verification step (`ruff check`) to pass. No scope creep. All other code matches the plan's `<action>` block verbatim.

## Issues Encountered

- **Python 3.12 not pre-installed on the workstation** — system Python was 3.11.3. Resolved by `uv python install 3.12` (downloaded 3.12.13 in ~1s) then `uv venv --python 3.12 .venv`. This is a local-dev workstation concern only; GitHub Actions `setup-python@v5` with `python-version: "3.12"` handles this in CI.
- **`uv pip compile` requires explicit `--python 3.12`** — without the flag the resolver would have used 3.11.3 from `/usr/local/bin/python3` and emitted incompatible pins. With the explicit flag, lock file resolved cleanly to 91 lines.
- **PyYAML not in the dep set** — used for the plan's `python -c "import yaml; yaml.safe_load(...)"` verification step. Installed transiently into the .venv for verification (not added to requirements.txt — it's not needed at runtime; the YAML is parsed by GitHub Actions, not by `src/main.py`).

## User Setup Required

**External services require manual configuration.** Per plan frontmatter `user_setup`:
- **GitHub:** Create public repo at `github.com/DevDesai444/new-grad` before pushing the first commit
- **GitHub Settings → Code security & analysis:** Enable Secret scanning + Push Protection (documented in README.md "Setup" section per INFRA-08)

No environment variables / secrets needed for Phase 1 (Greenhouse public API is unauthenticated; per SEC-03/SEC-05 the credentialed-scrape flow is deferred to Phase 3).

## Known Stubs

- `companies.txt` ships with zero URL lines per CONTEXT.md D-03 — this is **intentional**, not a stub. The user provides real URLs post-launch per D-04. README placeholder "(no matching postings yet)" is the correct initial state.
- `.github/workflows/scan.yml` "Run scan" step is a guarded no-op stub until Plan 03 creates `src/main.py` — intentional design so the workflow YAML stays valid + CI stays green across the 3-plan delivery wave.

## Next Phase Readiness

**Ready for Plan 02 (Wave 2):**
- `src/models.py` exports `Posting`, `RawPosting`, `CompanyConfig` ready to import
- `src/adapters/base.py` exports `Adapter`, `SiteBlocked`, `SchemaDrift`, `PlaywrightTimeout`, `MissingCredential` ready to import
- `src/adapters/greenhouse.py` produces `RawPosting` with `raw["__dedup_key"]` and `raw["__board_token"]` pre-stashed for the normalizer
- `tests/fixtures/greenhouse_stripe.json` covers both filter-pass and filter-reject cases for Plan 02's title-keyword filter
- 26 passing tests provide a regression net for changes to models / adapter base in subsequent plans

**Ready for Plan 03 (Wave 3):**
- `.github/workflows/scan.yml`'s guarded `python -m src.main` will start firing once Plan 03 lands `src/main.py`
- `companies.txt` placeholder is in place; Plan 03's config_loader can read it and (correctly) return an empty list

**No blockers.** Pointer to Plan 02: builds the pure-core pipeline (normalizer, filter, state_store, state_merger, renderer, registry) on top of these models + adapter.

## Self-Check: PASSED

All claimed files exist on disk (19 source/test files + this SUMMARY.md = 20 verified).
All claimed commit hashes resolve in `git log --all`:
- `3713ee9` (Task 1)
- `69be7f3` (Task 2)
- `f6b0344` (Task 3)

Verified 2026-06-08T01:51:43Z via Bash file-existence + `git log --oneline --all | grep <hash>` lookup.

---
*Phase: 01-walking-skeleton*
*Completed: 2026-06-08*
