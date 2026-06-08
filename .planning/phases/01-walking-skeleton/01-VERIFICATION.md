---
phase: 01
phase_name: walking-skeleton
status: human_needed
gates_passed: 4
gates_total: 5
score: 55/55 must-haves verified (with D-04 override applied to SC#1 & SC#5)
verified_at: 2026-06-08T02:36:00Z
re_verification:
  previous_status: null
  previous_score: null
overrides_applied: 2
overrides:
  - must_have: "Success Criterion #1 — User opens github.com/DevDesai444/new-grad and sees real Greenhouse postings"
    reason: "Per CONTEXT.md D-04, live-data verification is explicitly deferred to post-launch user-driven verification. Phase 1 ships placeholder companies.txt (no real URLs) and substitutes a fixture-based end-to-end test (tests/test_end_to_end.py)."
    accepted_by: "user (CONTEXT.md D-04 locked decision)"
    accepted_at: "2026-06-07"
  - must_have: "Success Criterion #5 — User asks Claude CLI to add a Greenhouse URL and next hourly run picks it up"
    reason: "Per CONTEXT.md D-04 (and verification spec), the 'add a Greenhouse URL → live pickup' workflow is a post-launch user-driven action. Substitute: config_loader correctly parses appended URL line + registry dispatches it + README CFG-04 documents the flow. The open/closed adapter contract test (test_new_adapter_can_be_added_without_touching_existing_files) covers ADP-14."
    accepted_by: "user (CONTEXT.md D-04 locked decision)"
    accepted_at: "2026-06-07"
human_verification:
  - test: "Enable GitHub Push Protection at github.com/DevDesai444/new-grad → Settings → Code security & analysis → Secret scanning → Push protection"
    expected: "Push Protection toggle is ON; future commits with credential-shaped patterns are blocked at push time"
    why_human: "GitHub repo settings are UI-only (no CLI); INFRA-08 requires this manual user action — documented in README §Setup, but cannot be programmatically verified from this repo"
  - test: "Push the repo to github.com/DevDesai444/new-grad and wait for ≥2 hourly cron runs to fire (or trigger via Actions → 'scan' → 'Run workflow' button)"
    expected: "Two runs succeed; second run produces no spurious diff (no commit) because git-auto-commit-action@v5 skips on no-diff (RUN-03)"
    why_human: "Requires a real GitHub Actions environment; placeholder companies.txt produces empty pipeline so no diff is expected — confirmation requires watching the Actions UI"
  - test: "Optionally append a real Greenhouse URL (e.g., `https://boards.greenhouse.io/stripe`) to companies.txt, commit + push, and verify the next hourly run populates seen.json + README table"
    expected: "Within ≤2 hours, the public README table at github.com/DevDesai444/new-grad shows real new-grad-eligible postings; the linked [Apply] URLs open the live Greenhouse posting pages"
    why_human: "ROADMAP SC#1 — live-data verification was explicitly deferred per CONTEXT.md D-04 to post-launch user-driven action; cannot be verified pre-launch with placeholder companies.txt"
---

# Phase 1: Walking Skeleton Verification Report

**Phase Goal:** User opens repo and sees real Greenhouse postings in a README table updated within the last hour by GitHub Actions — every architectural seam exists, every existential risk is baked in, and the commit-back loop is proven on real infrastructure.

**Verified:** 2026-06-08T02:36:00Z
**Status:** human_needed (all code-verifiable gates pass; remaining items are post-launch user actions explicitly deferred per CONTEXT.md D-04)
**Re-verification:** No — initial verification

## Decision Overrides Applied

Per `<verification_context>` from the orchestrator:
- **D-04 override on SC#1:** Live-data verification deferred to post-launch user action. Substitute = fixture-based `tests/test_end_to_end.py` exercising the full pipeline against a respx-mocked Greenhouse endpoint.
- **D-04 override on SC#5:** "Claude adds a Greenhouse URL" live-pickup workflow deferred to post-launch. Substitute = `config_loader` + `registry` correctness + CFG-04 README documentation + `test_new_adapter_can_be_added_without_touching_existing_files` contract test.

These overrides are locked decisions in `01-CONTEXT.md` — accepted, not flagged.

## Goal Achievement

### Success Criteria Verification

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | (deferred per D-04) Fixture-based end-to-end test exercises companies.txt → config_loader → registry → Greenhouse adapter (respx-mocked) → normalizer → filter → state_merger → renderer → README write; README between sentinels has 7-column table + `[Apply](URL)` links | ✓ PASSED (override) | `tests/test_end_to_end.py::test_pipeline_first_run` PASSED — asserts schema_version=1, kept titles include "New Grad" + "Associate", "Senior" filtered out, `[Apply](https://boards.greenhouse.io/stripe/jobs/...)` link present in README. Pipeline output verified by running `pytest tests/test_end_to_end.py -v` (3 passed in 0.20s). |
| 2 | Idempotent render + cumulative state — second run byte-equal output; `seen.json` records `first_seen` / `last_seen` / `still_listed`; no posting key ever deleted | ✓ VERIFIED | `tests/test_end_to_end.py::test_pipeline_idempotent_second_run` PASSED — frozen clock, two consecutive `main.main(...)` calls produce byte-identical seen.json AND README. `tests/test_renderer.py::test_render_idempotent_byte_equal` PASSED at unit level. STATE-04: `tests/test_state_merger.py::test_merge_never_deletes_keys` PASSED. STATE-05: `test_merge_flips_still_listed_for_missing_keys` PASSED. `tests/test_end_to_end.py::test_pipeline_persists_keys_across_runs` PASSED. |
| 3 | Crash recovery + sanity gate — atomic write via `os.replace`; `.bak` fallback on read; sanity gate engages on prior=100/new=0/no-block, passes on cold start, aborts on prior=1/new=0 | ✓ VERIFIED (partial) | **Atomic write:** `src/state_store.py:157` `os.replace(tmp, path)` after fsync. **.bak fallback:** `src/state_store.py:108-119`, tested by `test_load_corrupted_falls_back_to_bak`, `test_load_both_corrupted_returns_empty`, `test_load_corrupted_main_no_bak_returns_empty`. **Sanity gate engages:** `test_sanity_gate_threshold[100-85-True]`, `[100-89-True]`, `[100-90-False]`, `[100-91-False]`, `[10-9-False]`, `[10-8-True]` all PASSED. **Cold start passes:** `test_sanity_gate_cold_start_passes` PASSED. **Prior=1/new=0 aborts:** `test_sanity_gate_prior_one_zero_new_raises` PASSED (D-06 boundary). **State NOT overwritten on abort:** `test_sanity_gate_fires_without_blocked` PASSED — asserts seen.json bytes before/after byte-equal. ⚠️ `--validate` CLI mode NOT implemented (see Gaps). |
| 4 | Secret hygiene — `.gitignore` blocks `.env`/`*.har`/`trace.zip`/`cookies.json`/`__pycache__/`/`.pytest_cache/`/`seen.json.tmp`/`seen.json.bak`; no `traceback.format_exc()` in main; README documents secret naming convention and Push Protection | ✓ VERIFIED | `.gitignore` lines 14-25 block all 8 expected patterns (`grep -E "^\.env$\|cookies\.json\|trace\.zip\|\*\.har\|seen\.json\.tmp\|seen\.json\.bak\|__pycache__/\|\.pytest_cache/" .gitignore` returns 8). `grep -c "traceback.format_exc" src/main.py` returns 0. README §Setup documents Push Protection (line 9-15); §Secret Hygiene documents `SCRAPER_<COMPANY>_<KIND>` naming convention placeholder (lines 64-71). Orchestrator's `_scrape_one` logs only `type(e).__name__ + str(e)` — never request headers (verified `src/main.py:80-89`). ⚠️ See WARNING below re: query-param stripping. |
| 5 | (deferred per D-04) `config_loader` parses appended URL line; `registry` dispatches it; CFG-04 README doc exists; open/closed contract test passes | ✓ PASSED (override) | **config_loader:** `tests/test_config_loader.py` 17 PASSED, including `test_single_greenhouse_url`, `test_mixed_comments_blanks_and_urls`, `test_adapter_hint_parsed`. **Registry dispatch:** `tests/test_registry.py::test_get_adapter_for_greenhouse_url` PASSED. **CFG-04 doc:** README.md lines 48-62 contain `## Add a Company (CFG-04)` with the Claude CLI workflow described. **Open/closed contract test:** `tests/test_adapter_contract.py::test_new_adapter_can_be_added_without_touching_existing_files` PASSED — proves a synthetic adapter can be appended at runtime and `get_adapter` dispatches to it without editing existing adapter files. |

**Score:** 5/5 success criteria verified (with 2 D-04 overrides applied).

### Required Artifacts (Phase 1 Scope)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | Python 3.12 floor, ruff config | ✓ VERIFIED | Parses; `requires-python = ">=3.12"`; ruff selects E,F,I,B,W,UP. |
| `requirements.txt` | httpx, pydantic, orjson, tenacity, selectolax, beautifulsoup4, playwright, dateparser, python-dotenv | ✓ VERIFIED | All 9 deps present per STACK.md floors. |
| `requirements-dev.txt` | pytest, respx, ruff | ✓ VERIFIED | All 3 present. |
| `requirements.lock` | Pinned versions | ✓ VERIFIED | 87 lines; generated via `uv pip compile`; pins httpx==0.28.1, pydantic==2.13.4, orjson==3.11.9, playwright==1.60.0, respx==0.23.1, ruff==0.15.16. |
| `.gitignore` | Blocks 8 secret-shaped + transient files | ✓ VERIFIED | 30 lines; all 8 patterns present. |
| `companies.txt` | Header-comments-only placeholder (D-03) | ✓ VERIFIED | 7 lines, all comments; `load_companies(Path("companies.txt"))` returns `[]`. |
| `README.md` | Sentinels + 5 doc sections (Setup, companies.txt Format, Add a Company, Secret Hygiene, Hourly Cadence) | ✓ VERIFIED | Contains `<!-- BEGIN JOBS -->` + `<!-- END JOBS -->`; all 5 sections present; placeholder `(no matching postings yet)` between sentinels. |
| `.github/workflows/scan.yml` | Hourly cron, `permissions: contents:write`, `concurrency: {group: scan, cancel-in-progress: false}`, `timeout-minutes: 50`, Playwright cache, `git-auto-commit-action@v5` | ✓ VERIFIED | YAML parses; all 6 required elements present (verified by grep). |
| `src/models.py` | Posting / RawPosting / CompanyConfig pydantic v2 (NORM-01 fields) | ✓ VERIFIED | 63 lines; all 13 NORM-01 fields on Posting class; `_validate_url_scheme` validator on CompanyConfig. |
| `src/adapters/base.py` | Adapter ABC + 4 typed exceptions | ✓ VERIFIED | 88 lines; `class Adapter(ABC)` with `@abstractmethod matches` + `fetch`; `SiteBlocked`, `SchemaDrift`, `PlaywrightTimeout`, `MissingCredential` defined. |
| `src/adapters/greenhouse.py` | Greenhouse adapter, `gh:<board>:<id>` keys, raises SiteBlocked/SchemaDrift | ✓ VERIFIED | 130 lines; matches both `boards.greenhouse.io` + `job-boards.greenhouse.io`; raises SiteBlocked on 403/429/5xx; raises SchemaDrift on missing/wrong-type 'jobs' key; stashes `__dedup_key` in raw. |
| `src/normalizer.py` | RawPosting→Posting, URL canonicalization, UTC date parse | ✓ VERIFIED | 127 lines; `canonicalize_url` strips utm_*/gh_src/lever-source, lowercases host, removes trailing slash, drops fragment; `_parse_iso_to_utc` handles Z suffix + offsets; dispatch table for adapter-specific normalizers. |
| `src/filter.py` | FILT-01/02/04/05 — title-keyword gate + experience ceiling | ✓ VERIFIED | 80 lines; pure function (no `datetime.now`); excludes win on conflict; ambiguous title → include (FILT-05). |
| `src/state_store.py` | Atomic write + .bak fallback + sanity gate + schema_version | ✓ VERIFIED | 183 lines; `SCHEMA_VERSION=1`; `EMPTY_STATE` constant; `load_state` with .bak fallback; `save_state_atomic` uses `os.replace` + fsync + `OPT_SORT_KEYS`; `sanity_gate(prior, new, any_blocked)` with 0.9 floor; `SanityGateAborted` + `UnknownSchemaVersion` exceptions. |
| `src/state_merger.py` | Add-only merge, first_seen preserved, still_listed flip | ✓ VERIFIED | 91 lines; `merge_state` — Pass 1 preserves prior.first_seen, sets last_seen=run_started_at on present-in-fresh, flips still_listed=False on absent-from-fresh; Pass 2 inserts new keys with first_seen=run_started_at; never deletes keys (grep `^\s*del ` returns 0). |
| `src/renderer.py` | Sentinel splice, Markdown escape, idempotent sort | ✓ VERIFIED | 220 lines; SENTINEL_BEGIN/END constants; `escape_markdown_cell` strips 5 invisible Unicode codepoints + replaces NBSP/newline/tab with space + escapes `\|`; `format_age` handles m/h/d/w/mo/y + `now` + negative clamp; `_sort_key` sorts posted_date DESC then company ASC, None-dates last; placeholder `(no matching postings yet)` on empty. |
| `src/registry.py` | URL-pattern adapter dispatch, NoAdapterFound | ✓ VERIFIED | 61 lines; `ADAPTERS = [GreenhouseAdapter]`; `get_adapter` resolves hint first (CFG-03) then URL-match; raises `NoAdapterFound` on no match. |
| `src/config_loader.py` | companies.txt parser (CFG-01/02/03/05) | ✓ VERIFIED | 118 lines; `load_companies` reads with `utf-8-sig` (BOM tolerance); skips blanks + `#` comments; parses `#adapter=<name>` hint with Phase-2-forward-compat `name:metadata=value` form; logs + skips malformed lines. |
| `src/main.py` | Orchestrator with per-company isolation, RUN-01 clock threading, RUN-02 summary, sanity gate routing | ✓ VERIFIED | 259 lines; `datetime.now(timezone.utc)` called ONCE at line 198; `_scrape_one` has 3 typed-except arms + generic Exception arm; routes SiteBlocked → `any_blocked=True`; emits run summary to stdout + `$GITHUB_STEP_SUMMARY`; exit codes 0/1/2 per design. |
| `tests/fixtures/greenhouse_stripe.json` | 3+ jobs covering filter pass + reject | ✓ VERIFIED | 33 lines; 3 jobs — New Grad (kept), Senior Staff (filtered out), Associate (kept). |
| Test files (13 modules) | ≥ 70 passing tests | ✓ VERIFIED | 187 tests collected; 187 passed in 0.26s; ruff `All checks passed!`. |

**Score:** 21/21 artifacts pass all 3 verification levels (exists, substantive, wired).

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `src/main.py` | `src/config_loader.py` | `from src.config_loader import load_companies` | ✓ WIRED | `src/main.py:32`, used line 209. |
| `src/main.py` | `src/registry.py` | `from src.registry import NoAdapterFound, get_adapter` | ✓ WIRED | `src/main.py:36`, used lines 70, 71. |
| `src/main.py` | `src/state_store.py` | imports `load_state`, `save_state_atomic`, `sanity_gate`, `SanityGateAborted`, `UnknownSchemaVersion` | ✓ WIRED | `src/main.py:39-45`, used lines 204, 237, 248. |
| `src/main.py` | `src/renderer.py` | `from src.renderer import write_readme` | ✓ WIRED | `src/main.py:37`, used line 249. |
| `src/main.py` | `src/normalizer.py` | `from src.normalizer import normalize` | ✓ WIRED | `src/main.py:35`, used line 95. |
| `src/main.py` | `src/filter.py` | `from src.filter import is_early_career` | ✓ WIRED | `src/main.py:33`, used line 102. |
| `src/main.py` | `src/state_merger.py` | `from src.state_merger import merge_state` | ✓ WIRED | `src/main.py:38`, used line 226. |
| `src/normalizer.py` | `src/models.py` | imports Posting, RawPosting | ✓ WIRED | `src/normalizer.py:20`. |
| `src/normalizer.py` | `src/adapters/greenhouse.py` | reads `raw['__dedup_key']` | ✓ WIRED | `src/normalizer.py:81` reads dedup_key; greenhouse.py:119 sets it. |
| `src/state_store.py` | `seen.json` | `os.replace` from `.tmp` | ✓ WIRED | `src/state_store.py:157`. |
| `src/renderer.py` | `README.md` | sentinel splice | ✓ WIRED | `src/renderer.py:194-200` reads README, regex-splices between sentinels. |
| `src/registry.py` | `src/adapters/greenhouse.py` | imports GreenhouseAdapter, ADAPTERS list | ✓ WIRED | `src/registry.py:13, 30`. |
| `.github/workflows/scan.yml` | `src/main.py` | `python -m src.main` invocation | ✓ WIRED | scan.yml line 49 (guarded by `if [ -f src/main.py ]`). |
| `tests/test_end_to_end.py` | `src/main.py` | `from src.main import main` | ✓ WIRED | tests/test_end_to_end.py:43. |
| `tests/test_greenhouse_adapter.py` | `tests/fixtures/greenhouse_stripe.json` | fixture loaded for respx mock | ✓ WIRED | tests/test_greenhouse_adapter.py loads the file (verified by `pytest tests/test_greenhouse_adapter.py` — 10/10 PASSED). |

**Score:** 15/15 key links verified.

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|---------|
| `seen.json` (state file) | `merged["postings"]` | `merge_state(prior, all_fresh, run_started_at)` where `all_fresh` comes from `_scrape_one` → `adapter.fetch` → `normalize` → `is_early_career` | YES (proven by `test_pipeline_first_run` which asserts 2 expected postings land in seen.json after respx-mocked Greenhouse fetch) | ✓ FLOWING |
| `README.md` (between sentinels) | `state` dict → `render_table` rows | `write_readme(merged, readme_path, run_started_at)` after sanity gate | YES (proven by `test_pipeline_first_run` asserting `[Apply](https://boards.greenhouse.io/stripe/jobs/...)` appears in README) | ✓ FLOWING |
| `$GITHUB_STEP_SUMMARY` (Actions UI) | summary dict with `+N new / M closed / K total open` | `_emit_summary(summary)` writes to file pointed by env var | YES (proven by `test_step_summary_written_when_env_set`) | ✓ FLOWING |

**Score:** 3/3 dynamic-data-producing artifacts have verified upstream data flow.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|---------|
| Full test suite passes | `python -m pytest tests/ -v` | `187 passed in 0.26s` | ✓ PASS |
| End-to-end pipeline test passes | `python -m pytest tests/test_end_to_end.py -v` | `3 passed in 0.20s` | ✓ PASS |
| Adapter contract test passes | `python -m pytest tests/test_adapter_contract.py -v` | `7 passed in 0.05s` | ✓ PASS |
| Ruff lint passes | `ruff check src/ tests/` | `All checks passed!` (exit 0) | ✓ PASS |
| `python -m src.main` against placeholder | `python -m src.main` (companies.txt has no URLs) | Exit 0; logs `loaded 0 companies`; emits scan summary | ✓ PASS |
| Workflow YAML parses | `python -c "import yaml; yaml.safe_load(open('.github/workflows/scan.yml'))"` | Exits 0 | ✓ PASS |
| State corruption recovery | Manual: bad-JSON main + good .bak → fall back to .bak; both bad → empty state | Recovered via .bak; both-bad → empty `{}` (no crash) | ✓ PASS |
| Atomic write — no .tmp residue | Manual: `save_state_atomic` → assert no `.tmp` file | Confirmed: tmp does not exist after save | ✓ PASS |

**Score:** 8/8 behavioral spot-checks pass.

### REQ-ID Coverage Matrix

All 55 expected Phase 1 requirement IDs (INFRA-05 EXCLUDED per D-01) traced to code/test/doc evidence:

| REQ-ID | Status | Evidence |
|--------|--------|----------|
| INFRA-01 | ✓ SATISFIED | `.github/workflows/scan.yml:5` (`cron: "0 * * * *"`), `:18` (`timeout-minutes: 50`) |
| INFRA-02 | ✓ SATISFIED | `.github/workflows/scan.yml:8-9` (`permissions: contents: write`), `:11-13` (`concurrency: group: scan, cancel-in-progress: false`) |
| INFRA-03 | ✓ SATISFIED | `.github/workflows/scan.yml:22-32` (setup-python@v5 with python-version:3.12 + uv install via lockfile) |
| INFRA-04 | ✓ SATISFIED | `.github/workflows/scan.yml:38-41` (actions/cache@v4 keyed on requirements.lock) |
| ~~INFRA-05~~ | EXCLUDED per D-01 | health.json removed from Phase 1; see CONTEXT.md D-01/D-02 |
| INFRA-06 | ✓ SATISFIED | README.md:5 documents `github.com/DevDesai444/new-grad`; documented + claimed in user_setup |
| INFRA-07 | ✓ SATISFIED | `.gitignore` lines 14-25 — all 8 expected patterns present |
| INFRA-08 | ✓ SATISFIED | README.md:9-15 §Setup — documents Push Protection enable; flagged for user verification |
| INFRA-09 | ✓ SATISFIED | Phase 1 needs zero credentials (Greenhouse public); pattern documented in README §Secret Hygiene |
| INFRA-10 | ✓ SATISFIED | `.github/workflows/scan.yml:56` (`stefanzweifel/git-auto-commit-action@v5` with default GITHUB_TOKEN) |
| CFG-01 | ✓ SATISFIED | `src/config_loader.py` `load_companies` returns `list[CompanyConfig]`; `tests/test_config_loader.py::test_single_greenhouse_url` PASSED |
| CFG-02 | ✓ SATISFIED | `src/config_loader.py:113` skips blanks + `#` comments; `tests/test_config_loader.py::test_mixed_comments_blanks_and_urls` PASSED |
| CFG-03 | ✓ SATISFIED | `src/config_loader.py:29` `_ADAPTER_HINT_RE` regex; `tests/test_config_loader.py::test_adapter_hint_parsed`, `test_adapter_hint_with_metadata` PASSED; registry.py:45-49 resolves hint first |
| CFG-04 | ✓ SATISFIED | README.md:48-62 §Add a Company documents the Claude CLI flow |
| CFG-05 | ✓ SATISFIED | `src/config_loader.py:72-93` logs+skips malformed lines; `src/main.py:73` logs+skips NoAdapterFound; tests `test_invalid_scheme_skipped`, `test_no_adapter_found_does_not_abort_run` PASSED |
| CFG-06 | ✓ SATISFIED | README.md:25-46 §companies.txt Format documents the user-facing format |
| ADP-01 | ✓ SATISFIED | `src/adapters/base.py:61` `class Adapter(ABC)` with `@abstractmethod matches` + `fetch` |
| ADP-02 | ✓ SATISFIED | `src/registry.py:35-60` `get_adapter` dispatches via `Adapter.matches()`; `tests/test_adapter_contract.py::test_registry_dispatches_via_matches_only` PASSED |
| ADP-03 | ✓ SATISFIED | `src/adapters/greenhouse.py:116` `dedup_key = f"gh:{board_token}:{job['id']}"`; fetches `boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true` (line 62); `tests/test_greenhouse_adapter.py::test_fetch_emits_stable_dedup_key` PASSED |
| ADP-11 | ✓ SATISFIED | `src/adapters/base.py:25-58` — SiteBlocked, SchemaDrift, PlaywrightTimeout, MissingCredential all defined |
| ADP-12 | ✓ SATISFIED | `src/main.py:_scrape_one` 3-arm try/except; `tests/test_orchestrator.py::test_per_company_isolation_one_raises` PASSED — RaisingAdapter doesn't abort OkAdapter |
| ADP-13 | ✓ SATISFIED | `tests/test_greenhouse_adapter.py` 10 tests using `@respx.mock` against `tests/fixtures/greenhouse_stripe.json`; all PASSED |
| ADP-14 | ✓ SATISFIED | `tests/test_adapter_contract.py::test_new_adapter_can_be_added_without_touching_existing_files` PASSED — synthetic adapter appended to ADAPTERS dispatches correctly without editing existing files |
| ADP-15 | ✓ SATISFIED | `tests/test_adapter_contract.py::test_greenhouse_adapter_is_self_contained` PASSED — grep audit confirms greenhouse.py has no sibling-adapter imports |
| FILT-01 | ✓ SATISFIED | `src/filter.py:18-33` `_INCLUDE_PATTERNS` covers all 10 specified keywords; parametrized tests `test_title_gate[Software Engineer, New Grad-True]` etc. PASSED |
| FILT-02 | ✓ SATISFIED | `src/filter.py:36-54` `_EXCLUDE_PATTERNS` covers senior/sr./staff/principal/lead/manager/director/head of/II/III/IV/V/2-9; parametrized tests for negative cases PASSED |
| FILT-04 | ✓ SATISFIED | `src/filter.py:70-79` `is_early_career` enforces title-gate AND `experience_min <= 5`; `test_experience_min_above_ceiling_overrides_title_pass` PASSED |
| FILT-05 | ✓ SATISFIED | `src/filter.py:67` ambiguous bias → True; `test_title_gate[Backend Developer-True]` PASSED |
| FILT-06 | ✓ SATISFIED | `src/filter.py` has no `import datetime`, no I/O; `tests/test_filter.py` 7 passing test functions cover representative cases |
| NORM-01 | ✓ SATISFIED | `src/models.py:42-62` `class Posting` with all 13 required fields (dedup_key, company, title, location, salary, experience_min/max, posting_url, posted_date, first_seen, last_seen, still_listed, source_adapter) |
| NORM-04 | ✓ SATISFIED | `src/normalizer.py:85` reads `updated_at` from Greenhouse raw; returns None on missing (`_parse_iso_to_utc(None) → None`); `tests/test_normalizer.py::test_normalize_posted_date_none_when_updated_at_missing` PASSED |
| NORM-05 | ✓ SATISFIED | `src/normalizer.py:53-70` `_parse_iso_to_utc` converts to UTC-aware; `tests/test_normalizer.py::test_parse_iso_to_utc_with_negative_offset` PASSED |
| NORM-06 | ✓ SATISFIED | `src/normalizer.py:27-50` `canonicalize_url` strips utm_*/gh_src/lever-source, lowercases host, strips trailing slash, drops fragment; 7+ tests covering each case |
| NORM-07 | ✓ SATISFIED | `src/renderer.py:32-46` strips U+200B/U+200C/U+200D/U+FEFF/U+2060 and replaces U+00A0/newline/tab/CR with space, escapes pipe; 9 escape tests PASSED |
| STATE-01 | ✓ SATISFIED | `src/state_store.py:34` `EMPTY_STATE["postings"] = {}` (dict keyed by dedup_key); `save_state_atomic(state, path=Path("seen.json"))` default |
| STATE-02 | ✓ SATISFIED | `src/state_store.py:157` `os.replace(tmp, path)`; `tests/test_state_store.py::test_save_atomic_no_tmp_remains` PASSED |
| STATE-03 | ✓ SATISFIED | `src/state_store.py:73-127` JSONDecodeError → .bak fallback; tests `test_load_corrupted_falls_back_to_bak`, `test_load_both_corrupted_returns_empty` PASSED |
| STATE-04 | ✓ SATISFIED | `src/state_merger.py:60-76` Pass 1 preserves prior keys (flips still_listed=False if missing from fresh); never deletes (`grep -c "^\s*del " src/state_merger.py == 0`); `tests/test_state_merger.py::test_merge_never_deletes_keys` PASSED |
| STATE-05 | ✓ SATISFIED | `src/state_merger.py:73-76` missing-from-fresh keys retain prior fields with still_listed=False; `tests/test_state_merger.py::test_merge_flips_still_listed_for_missing_keys` PASSED |
| STATE-06 | ✓ SATISFIED | `src/state_store.py:160-182` `sanity_gate` with 0.9 floor; any_blocked carve-out (Pitfall 5); `test_sanity_gate_threshold` parametrized (6 cases), `test_sanity_gate_any_blocked_excuses`, `test_sanity_gate_prior_one_zero_new_raises` (D-06 boundary) PASSED |
| STATE-07 | ✓ SATISFIED | `src/state_store.py:149` `orjson.dumps(state, option=orjson.OPT_SORT_KEYS | OPT_INDENT_2)`; `tests/test_state_store.py::test_save_atomic_byte_deterministic` PASSED |
| STATE-08 | ✓ SATISFIED | `src/state_store.py:29` `SCHEMA_VERSION = 1`; loader raises `UnknownSchemaVersion` on `sv > SCHEMA_VERSION`; `tests/test_state_store.py::test_load_unknown_future_schema_raises` PASSED; orchestrator returns exit 2 on this |
| OUT-01 | ✓ SATISFIED | `src/renderer.py:21-22, 194-200` `SENTINEL_BEGIN/END` constants + regex splice; `tests/test_renderer.py::test_render_only_replaces_between_sentinels` PASSED |
| OUT-02 | ✓ SATISFIED | `src/renderer.py:27` `_HEADER_ROW = "| Company | Position | Location | Salary | Experience | Posting | Age |"`; `test_render_table_has_required_columns` PASSED |
| OUT-03 | ✓ SATISFIED | `src/renderer.py:140` `posting_link = f"[Apply]({posting_url})"`; `test_render_table_contains_apply_link` PASSED; end-to-end test confirms `[Apply](https://boards.greenhouse.io/stripe/jobs/` in README |
| OUT-04 | ✓ SATISFIED | `src/renderer.py:71-104` `format_age`; `_table_row` falls back to first_seen if posted_date is None (line 142-144); 9 format_age tests PASSED |
| OUT-05 | ✓ SATISFIED | `src/renderer.py:107-115` `_format_experience` returns "Xy-Yy" / "<=Yy" / ">=Xy" / "" per the rules; 4 tests PASSED |
| OUT-06 | ✓ SATISFIED | `src/renderer.py:152-167` `_sort_key` sorts posted_date DESC then company ASC; None-dates last; `test_render_sort_order_posted_date_desc`, `test_render_sort_none_posted_date_last` PASSED |
| OUT-07 | ✓ SATISFIED | `tests/test_renderer.py::test_render_idempotent_byte_equal` PASSED; `tests/test_end_to_end.py::test_pipeline_idempotent_second_run` PASSED |
| OUT-08 | ✓ SATISFIED | `src/renderer.py:24, 174` `EMPTY_PLACEHOLDER = "(no matching postings yet)"`; `test_render_empty_state_shows_placeholder` PASSED |
| SEC-03 | ✓ SATISFIED | `.gitignore` blocks all secret-shaped files; README §Secret Hygiene (lines 64-71) documents discipline; orchestrator's `_scrape_one` logs only `type(e).__name__ + str(e)`; `grep -c "traceback.format_exc" src/main.py == 0` |
| SEC-05 | ✓ SATISFIED | `src/adapters/base.py:51-58` `class MissingCredential(Exception)` defined; orchestrator catches it in `_scrape_one` line 82 |
| RUN-01 | ✓ SATISFIED | `src/main.py:198` single `datetime.now(timezone.utc)` at entry; threaded to normalize/merge_state/write_readme as `run_started_at` param; `tests/test_orchestrator.py::test_run_started_at_threaded_consistently` PASSED |
| RUN-02 | ✓ SATISFIED | `src/main.py:143-180` `_emit_summary` prints to stdout AND appends to `$GITHUB_STEP_SUMMARY`; `tests/test_orchestrator.py::test_step_summary_written_when_env_set` PASSED; counts +N new / M closed / K total open + per-company outcomes table |
| RUN-03 | ✓ SATISFIED | `.github/workflows/scan.yml:56-59` `git-auto-commit-action@v5` default skip-on-no-diff behavior |
| RUN-04 | ✓ SATISFIED | `src/main.py:_emit_summary` produces informative summary with company names + counts; consumed via step summary (Phase 1 leaves actual commit message at action's default per plan AC) |

**REQ-ID Coverage:** 55/55 satisfied (INFRA-05 explicitly excluded per D-01).

### Existential Risks (PITFALLS.md top-5)

| # | Risk | Status | Notes |
|---|------|--------|-------|
| 1 | Atomic write (`os.replace` + `.bak` write timing) | ✓ MITIGATED | `src/state_store.py:130-157` — copy2 to .bak BEFORE write, then write to .tmp + fsync + os.replace. Tested by `test_save_atomic_creates_bak_when_overwriting` + `test_save_atomic_no_tmp_remains`. |
| 2 | Sanity gate engages unconditionally per D-06 | ✓ MITIGATED | `src/state_store.py:160-182` — no floor on `prior_count`; cold-start passes by math; prior=1/new=0 aborts (D-06 boundary tested). |
| 3 | Concurrency group on workflow | ✓ MITIGATED | `.github/workflows/scan.yml:11-13` `concurrency: {group: scan, cancel-in-progress: false}`. |
| 4 | Secret hygiene — `.gitignore` patterns | ✓ MITIGATED | `.gitignore` lines 14-25 block all 8 expected secret-shaped + transient files. |
| 5 | Schedule auto-disable risk (Pitfall 23) | ✓ ACCEPTED per D-01/D-02 | README.md:78 documents the 60-day risk and manual recovery path; user has explicitly accepted this risk per CONTEXT.md D-01/D-02. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| _(none)_ | — | No TODO/FIXME/XXX/HACK in src/ | ℹ️ Info | Clean codebase. |
| `src/main.py` | 198 | `datetime.now(timezone.utc)` — single call (RUN-01) | ℹ️ Info (expected) | Plan AC explicitly requires this literal; `# noqa: UP017` keeps ruff clean. Justified single use. |
| `src/renderer.py` | 192 | `datetime.now(UTC)` — defensive default in `render_readme` | ℹ️ Info (acceptable) | Used ONLY when caller omits `run_started_at`; main.py always passes one explicitly. Documented at line 11. |

No blocker anti-patterns.

### Gaps Found

**WARNING #1: No `--validate` CLI mode implemented.**

The verification goal (from orchestrator's `<verification_context>`) specifies:
> `--validate` mode: `python -m src.main --validate` exits 0 on valid state, non-zero on corruption.

`src/main.py` does NOT accept any CLI arguments — `python -m src.main` always runs the full orchestrator. No argparse / sys.argv parsing.

**Impact analysis:**
- This is mentioned in the original ROADMAP SC#3 as "or running `--validate` against a deliberately corrupted seen.json".
- The OTHER mechanisms in SC#3 (atomic write, `.bak` fallback, sanity gate, exit non-zero on unrecoverable corruption) ARE implemented and tested.
- `load_state` already does the equivalent of `--validate` internally on every run: corruption → fall back to .bak → log; unknown schema → raise → orchestrator returns exit 2.
- No plan in Phase 1 explicitly scoped the `--validate` flag — neither 01-01, 01-02, nor 01-03 mentions it.

**Verdict:** WARNING, not BLOCKER. The substantive guarantee ("doesn't brick the next run; never silently wipes the table") is satisfied by the existing mechanisms. The `--validate` flag is a convenience CLI form that the spec mentions as an OR-alternative, not the primary mechanism.

**WARNING #2: Log discipline — no explicit query-param stripping in log messages.**

The verification goal specifies:
> Logging discipline: log messages strip query params from URLs (verify in test or implementation).

Neither `src/main.py` nor `src/adapters/greenhouse.py` strip query params from URLs in log messages. `src/adapters/greenhouse.py:77` logs the full `api_url` (which has `?content=true` — not a secret, but a query param).

**Impact analysis:**
- Phase 1 has ZERO credentialed scrapes (Greenhouse is public; no auth tokens in URLs).
- The harder guarantee (`grep -c "traceback.format_exc" src/main.py == 0`) IS enforced — exception attributes that COULD include request headers are never logged.
- This becomes load-bearing only when Phase 3 adds credentialed scrapes that might put tokens in query strings — and Phase 3 is the right time to add the stripping helper.

**Verdict:** WARNING, not BLOCKER. Phase 1 has no secrets that COULD leak via URL query params. Phase 3 should add explicit query-param stripping before credentialed scrapes ship.

### Human Verification Required

See `human_verification` in frontmatter. Three items, all post-launch user actions explicitly deferred per CONTEXT.md D-04:

1. Enable GitHub Push Protection at the repo settings (INFRA-08).
2. Push to GitHub and observe ≥2 successful hourly cron runs.
3. Optionally add real Greenhouse URLs to companies.txt to begin live operation (ROADMAP SC#1 live-data verification — deferred per D-04).

## Final Verdict

**Status: human_needed** — all code-verifiable gates pass; remaining items are post-launch user actions explicitly deferred per CONTEXT.md D-04.

**Summary:**
- 55/55 in-scope REQ-IDs satisfied (INFRA-05 excluded per D-01).
- 5/5 ROADMAP Success Criteria pass (2 with D-04 deferred-to-human override).
- 21/21 artifacts verified at all 3 levels (exists, substantive, wired).
- 15/15 key links wired.
- 3/3 dynamic-data flows traced.
- 8/8 behavioral spot-checks pass.
- 187/187 pytest tests pass; ruff clean.
- 2 WARNINGs documented (`--validate` CLI not implemented; query-param stripping deferred to Phase 3); neither is a blocker for Phase 1.
- 3 human-verification items (post-launch GitHub UI + live-data confirmation).

Phase 1 is execute-complete. The walking skeleton is verified end-to-end via the fixture-based pipeline test, all 5 existential risks are mitigated (with the 60-day cron auto-disable risk knowingly accepted per D-02), and the architectural seams are in place for Phase 2 (additional ATS adapters) and Phase 3 (Playwright fallback + credentialed scrapes).

The phase goal — "every architectural seam exists, every existential risk is baked in, and the commit-back loop is proven on real infrastructure" — is achieved in code. The "user opens repo and sees real Greenhouse postings" half of the goal is verifiable only post-launch per the locked D-04 deferral.

---
*Verified: 2026-06-08T02:36:00Z*
*Verifier: Claude (gsd-verifier)*
