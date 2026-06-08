# Walking Skeleton — new-grad

**Phase:** 1
**Generated:** 2026-06-07
**Mode:** mvp + walking-skeleton

## Capability Proven End-to-End

A Python script, executed by an hourly GitHub Actions cron, reads `companies.txt`, fetches one Greenhouse board via the public ATS JSON API, normalizes the postings to a canonical `Posting` model, applies a title-keyword filter for 0–5 yrs roles, atomically merges into a versioned `seen.json` state file (with `.bak` fallback and a 0.9× sanity gate), renders a Markdown table between `<!-- BEGIN JOBS -->` / `<!-- END JOBS -->` sentinels in `README.md`, and pushes the result via `stefanzweifel/git-auto-commit-action@v5` — with one company's failure unable to abort the run for others and no credentials ever written to a committed file or log.

**Phase 1 verification is fixture-based:** the `companies.txt` shipped on day 1 is a placeholder header-comment-only file (per CONTEXT.md D-03), so the user-facing "table populated with real Stripe roles" outcome is **deferred to post-launch user-driven verification** (per CONTEXT.md D-04). The end-to-end test under `tests/test_end_to_end.py` uses `respx` to mock the Greenhouse HTTP response with `tests/fixtures/greenhouse_stripe.json`, walks the full pipeline, and asserts byte-identical README output + well-formed `seen.json`.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / runtime | Python 3.12 | User-preferred; best ecosystem for hybrid ATS-API + headless browser scraping (per STACK.md). Python 3.13 acceptable but not required. |
| HTTP client | `httpx[http2]>=0.27,<1.0` | Sync + async + HTTP/2; modern timeout semantics. Used sync in Phase 1 (one Greenhouse call) but kept dual-mode for Phase 2 fan-out. |
| Retry | `tenacity>=8.2` | Decorator-based exponential backoff for transient 429/5xx. Not aggressively used in Phase 1 (single endpoint, low risk) but wired into the adapter base. |
| Data validation | `pydantic>=2.7` | Runtime validation at adapter parse time catches silent ATS field-shape drift before it corrupts `seen.json`. |
| JSON serialization | `orjson>=3.10` with `OPT_SORT_KEYS` | Deterministic key ordering = clean git diffs on `seen.json`. Stdlib `json` is used only for reading (no perf-critical path on the read side). |
| State storage | `seen.json` (JSON in repo root) | Public repo is the database. `os.replace()` atomic write; `seen.json.bak` recovery; `schema_version` field for forward compat. |
| Render target | `README.md` with `<!-- BEGIN JOBS -->` / `<!-- END JOBS -->` sentinels | Single source of truth for the user-facing UI. Only renderer ever writes between the sentinels. |
| Input config | `companies.txt` (one URL per line, `#` comments, `#adapter=<name>` inline hint) | User edits one line to add a company; zero Python edits in 99% of cases. |
| HTML parsing | `selectolax>=0.3.21` + `beautifulsoup4>=4.12` (fallback) | Not exercised in Phase 1 (no Playwright). Pinned in `requirements.lock` so Phase 3 doesn't re-bid the choice. |
| Headless browser | Playwright — **NOT installed in Phase 1** | Deferred to Phase 3 per CONTEXT.md D-05. `requirements.lock` includes the version floor for future install. |
| Dev tooling | `uv>=0.4` (install), `ruff>=0.6` (lint+format), `pytest>=8.0` (test), `respx>=0.21` (httpx mock) | uv saves 30–90s per Actions run. ruff replaces flake8+black+isort. respx mocks Greenhouse for fixture-based testing. |
| Cron host | GitHub Actions (`ubuntu-latest`), `0 * * * *` | $0 budget — unlimited free public-repo minutes. `timeout-minutes: 50` protects the next slot. |
| Concurrency | `concurrency: { group: scan, cancel-in-progress: false }` | Serializes runs to prevent racing `git push`. Never cancel in-flight (`.tmp` could be orphaned). |
| Permissions | `permissions: contents: write` | Default `GITHUB_TOKEN` is read-only as of 2023; explicit elevation required for `git push`. |
| Commit-back | `stefanzweifel/git-auto-commit-action@v5` | Battle-tested skip-on-no-diff behavior — provides RUN-03 for free. No PAT needed. |
| Cache strategy | `actions/cache@v4` keyed on `requirements.lock` | Saves 30–90s on every run. (Playwright cache wired but unused in Phase 1; cache key already includes lockfile hash so Phase 3 cache hits cleanly.) |
| Directory layout | `src/{main,models,registry,config_loader,normalizer,filter,state_store,state_merger,renderer}.py` + `src/adapters/{base,greenhouse}.py` + `tests/` + `tests/fixtures/` (per ARCHITECTURE.md) | Pure core (normalizer/filter/state_merger/renderer) + impure edges (adapters/state_store/main). Single-writer invariants. |
| Time source | `main.py` captures `run_started_at = datetime.now(timezone.utc)` once and threads it through (RUN-01) | No other module calls `datetime.now()`; eliminates timezone drift and multiple "now" values in a single run. |
| Dedup key format | `gh:<board_token>:<job_id>` for Greenhouse (extracted from API response, never URL-based) | Per-ATS stable ID survives URL tracking-param drift. Format locked for forward compat with Phase 2 (`lever:<co>:<uuid>`, `wd:<tenant>:<id>`, etc.). |
| Markdown table columns | `\| Company \| Position \| Location \| Salary \| Experience \| Posting \| Age \|` (OUT-02) | Locked in Phase 1; later phases populate Salary/Experience without changing schema. |
| Markdown escaping | Pipe (`\|`), newline → space, invisible Unicode (U+200B, U+200C, U+200D, U+FEFF, U+00A0, U+2060) stripped | Pitfall 13 mitigation. Pure function in `renderer.py`. |
| URL canonicalization | Strip `utm_*`, `gh_src`, `lever-source` query params; lowercase host; remove trailing slash | Pitfall 9 mitigation. Applied to `posting_url` before storage. Pure function in `normalizer.py`. |
| Secret strategy | Zero secrets in Phase 1 (Greenhouse is public). `os.environ` access pattern + `MissingCredential` typed error pre-defined for Phase 3. | SEC-03/SEC-05. `.gitignore` blocks `.env`, `*.har`, `cookies.json`, `trace.zip`. Push Protection documented in README for user to enable in repo settings (INFRA-08). |

## Stack Touched in Phase 1

- [x] Project scaffold — `pyproject.toml`, `requirements.txt`, `requirements.lock`, `requirements-dev.txt`, `.gitignore`, `ruff.toml` (or `pyproject.toml [tool.ruff]`), test runner via `pytest.ini` or pyproject section
- [x] Routing equivalent — `companies.txt` → `config_loader` → `registry` URL-pattern dispatch → `Adapter` ABC instances
- [x] Database — `seen.json` round-trip (read corrupted → fall back to `.bak`; merge → atomic write via `os.replace`); end-to-end test asserts well-formed `seen.json` after one pipeline run
- [x] UI — `README.md` Markdown table rendered between sentinels; idempotent render proof test asserts byte-equal output on repeated render of identical input
- [x] Deployment — `.github/workflows/scan.yml` with hourly cron, permissions, concurrency group, cache, uv install, scan execution, `git-auto-commit-action@v5` commit-back; local execution via `python -m src.main`

## Out of Scope (Deferred to Later Slices)

The following are NOT in the Walking Skeleton. Future phases must not re-litigate these decisions:

- **`health.json` mechanism (INFRA-05).** Removed from Phase 1 per CONTEXT.md D-01. The repo's natural commit traffic (README + seen.json diffs once URLs are added post-launch) is expected to keep the cron alive. Cold-start 60-day risk knowingly accepted per D-02.
- **All ATS adapters other than Greenhouse** (Lever, Ashby, SmartRecruiters, Workday, Apple) — deferred to Phase 2 per CONTEXT.md D-05.
- **Playwright headless-browser fallback** — deferred to Phase 3.
- **Credentialed-scrape workflow** (`gh secret set` flow, `SCRAPER_<COMPANY>_*` naming, Push Protection enforcement beyond docs) — deferred to Phase 3 per REQUIREMENTS.md SEC-01/02/04/06.
- **JD-text experience-range extraction (FILT-03, NORM-02 salary, NORM-03 location normalization)** — deferred to Phase 2/4. Phase 1 filter is title-keyword only.
- **Per-source health footer (OUT-09)** — deferred to Phase 4.
- **Adapter error-path tests (SchemaDrift, SiteBlocked branches)** — deferred to Phase 2 per CONTEXT.md D-07. Phase 1 ships happy-path unit tests only; the error classes exist and are raised, but the branches are not unit-tested.
- **Live-data verification** — Phase 1 does NOT block on "user sees real postings in github.com/DevDesai444/new-grad." That is post-launch user-driven verification per D-04.
- **Auto-removal of postings** — STATE-04 forbids deletion; stale entries with `still_listed: true/false` persist forever.

## Subsequent Slice Plan

Each later phase adds a vertical slice on top of this skeleton without altering the architectural decisions above:

- **Phase 2 (ATS Breadth + JD-Scan):** Add `adapters/{lever,ashby,smartrecruiters,workday,apple}.py` files (each implementing the same `Adapter` ABC), extend `filter.py` with `FILT-03` JD-regex experience extraction, populate `Posting.experience_min/max`. Per CONTEXT.md D-07, also adds fixture-mutation error-path tests for every adapter at once (SchemaDrift + SiteBlocked).
- **Phase 3 (Playwright Fallback + Credentialed Workflow):** Add `adapters/playwright_fallback.py`, install Playwright Chromium in CI (cache already keyed correctly), wire `playwright-stealth` conditionally per registry flag, implement the `gh secret set` workflow for credentialed scrapes. `MissingCredential` error class already defined in Phase 1 will be exercised here.
- **Phase 4 (Extraction Polish + Health Observability):** Implement NORM-02 (salary patterns), NORM-03 (location normalization), OUT-09 (per-source health footer). Builds on the same `Posting` schema and renderer sentinel pattern from Phase 1.

The architectural backbone above is a **contract**. Later phases extend it; they do not modify the directory layout, the `Posting`/`RawPosting`/`seen.json` schemas, the dedup-key format, the sentinel scheme, the atomic-write+sanity-gate pattern, or the per-company error-isolation contract.
