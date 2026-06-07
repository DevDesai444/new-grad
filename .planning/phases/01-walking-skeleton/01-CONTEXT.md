# Phase 1: Walking Skeleton - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers a **foundation-heavy walking skeleton**: every architectural seam (config loader, adapter registry, Greenhouse adapter, normalizer, filter, state store, state merger, renderer, orchestrator, GitHub Actions workflow) exists in code, the commit-back loop is wired end-to-end, and the five existential risks (atomic `seen.json` write, concurrency group, sanity gate, secret hygiene, schedule resilience) are baked in from day one.

**What ships at the end of Phase 1:**
- A buildable, testable Python 3.12 codebase under `src/` with `pyproject.toml` / `requirements.lock` / `.gitignore`.
- One working ATS adapter (Greenhouse) covered by happy-path unit tests against recorded JSON fixtures.
- A `.github/workflows/scan.yml` that runs hourly with the right permissions, concurrency group, caches, and commit-back action.
- An empty-but-valid `seen.json` (or absent file the loader can bootstrap), a placeholder `companies.txt` (header comments only), and a README with `<!-- BEGIN JOBS -->` / `<!-- END JOBS -->` sentinels around a "(no matching postings yet)" placeholder.

**What is explicitly NOT verified at ship time:** "User opens the public repo and sees real Greenhouse postings in the README table." That depends on the user adding URLs to `companies.txt` after the code is reviewed (D-03). Pre-launch verification is fixture-based unit tests + green CI; post-launch verification is the user-driven "add URLs → wait 2 hourly runs → inspect repo" loop.

</domain>

<decisions>
## Implementation Decisions

### Run Lifecycle & Schedule Resilience

- **D-01: No `health.json` in Phase 1.** INFRA-05 is removed from Phase 1 scope. The commit-back step relies on natural traffic from `README.md` and `seen.json` diffs to keep the GitHub Actions cron alive. `git-auto-commit-action@v5`'s default skip-on-no-diff behavior provides RUN-03 with no extra config.
- **D-02: Accept the 60-day cold-start risk.** With a placeholder `companies.txt` and only the Greenhouse adapter (D-05), there is a non-zero chance the repo goes 60+ days without a commit and GitHub Actions auto-disables the schedule. User has explicitly accepted this risk on the rationale that "the project will find some new posting every hour" once URLs are added post-launch. If the schedule ever does die, recovery is a manual re-enable in repo settings — not a code change.

### Seed Configuration & Companies List

- **D-03: Day-1 `companies.txt` is a header-comment-only placeholder.** No real URLs ship in the first commit. The user provides real URLs (up to ~10 companies, mixed ATSes) after the Phase 1 code is reviewed.
- **D-04: Phase 1 verification uses fixture-based unit tests, not live data.** A recorded Greenhouse JSON response lives under `tests/fixtures/greenhouse_<seed>.json` (planner picks the seed company for the fixture — Stripe is a reasonable default given research/SUMMARY.md references). The end-to-end test mocks the HTTP layer via `respx`, runs the full pipeline (fetch → normalize → filter → merge → render), and asserts byte-identical README output and a well-formed `seen.json`. Success criterion #1 from ROADMAP ("user sees real postings in github.com/DevDesai444/new-grad") is **deferred to post-launch user-driven verification** — not a Phase 1 acceptance gate.
- **D-05: Phase 1 ships only the Greenhouse adapter (ADP-03).** Lever / Ashby / SmartRecruiters / Workday / Apple adapters and the Playwright fallback do not exist. Non-Greenhouse URLs that ever land in `companies.txt` (whether on Day 1 or post-launch) are logged + skipped by the registry per CFG-05, never raising an error. The orchestrator continues for any URLs the registry can dispatch.

### State Store & Sanity Gate

- **D-06: STATE-06 sanity gate always engages — no floor on `prior`.** The condition `len(new) < 0.9 * len(prior)` runs every hourly scan regardless of `prior` size. Cold-start (`prior == 0`) trivially passes because `0 < 0.9 * 0` is false. The `prior == 1` boundary case aborts the commit on a zero-result scrape — this is intentional and defensive (any unexplained loss of state should fail loud, even at small sizes). The aborted-commit path exits non-zero so the failure is visible in the Actions run UI.

### Testing Strategy

- **D-07: Adapter error-path tests are deferred to Phase 2.** Phase 1's Greenhouse adapter ships with happy-path unit tests only (ADP-13). The `SchemaDrift` and `SiteBlocked` exception classes are *defined* in `adapters/base.py` and *raised* by `adapters/greenhouse.py` where the code paths require them, but no tests assert those branches fire. Risk accepted: if those handlers are buggy, the bug surfaces in Phase 2 under real drift / blocking conditions. The mitigation in Phase 2 is to add fixture-mutation tests for every adapter at once, exercising the shared error-handling contract.
- **D-08: ADP-12 (per-company isolation) is still tested in Phase 1.** A unit test injects a mock adapter that raises a generic `Exception` and asserts the orchestrator's per-company try/except catches it, logs the company name, and continues to the next company. This test does not depend on the error being typed — it covers the orchestrator's contract, not the adapter's contract.

### Claude's Discretion

These were not asked because they are implementation details, not user-visible choices. The planner / executor should make these calls based on what reads cleanest in the actual code:

- **Idempotent-render proof test (OUT-07).** Whether to add a dedicated "render twice on identical input → assert byte-equal output" test, or rely on the fact that the fixture-based pipeline test (D-04) already exercises this property by being deterministic. Recommendation: include the explicit test — it's cheap and pins the contract.
- **`still_listed` semantics for companies removed from `companies.txt`.** When the user removes a URL post-launch, their existing `seen.json` entries are never scraped again. `still_listed` stays at whatever it last was (probably `true` from the final successful scrape). This is correct under STATE-04 ("keys are never deleted") and consistent with the "keep stale postings forever" requirement.
- **`seen.json` filename for the `.bak` fallback.** Planner picks: `seen.json.bak` (atomic-write convention) vs `seen.previous.json` (slightly more human-readable). No user preference.
- **Seed company used in fixture file naming.** `tests/fixtures/greenhouse_stripe.json` vs `tests/fixtures/greenhouse_sample.json`. Planner picks; either is fine.
- **Whether `health.json` is *removed entirely* or *referenced as removed* in REQUIREMENTS.md.** REQUIREMENTS.md INFRA-05 should be marked struck/removed by the planner during phase plan generation, with a note pointing to D-01.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-Level Specs

- `.planning/PROJECT.md` — Core value, requirements (active + out-of-scope), constraints (tech stack, hosting, budget, security, cadence, privacy, resilience), key decisions table.
- `.planning/REQUIREMENTS.md` — All 71 v1 requirements with IDs; Traceability table maps every REQ-ID to a phase. **Note:** INFRA-05 (`health.json`) is removed from Phase 1 per D-01.
- `.planning/ROADMAP.md` — Phase 1 section: goal, mode (`mvp`), depends-on, success criteria (5 numbered items), full requirements list (51 IDs).
- `CLAUDE.md` — Project-level constraints repeated for runtime: $0 budget, public repo, hourly cadence, Python 3 + Playwright stack, GitHub Actions only.

### Research Outputs (read before planning)

- `.planning/research/SUMMARY.md` — Executive summary; phase ordering rationale; per-phase deliverables (Phase 1 list is authoritative for which files exist); research-flag designations (Phase 1 = "no phase research needed; standard patterns").
- `.planning/research/ARCHITECTURE.md` — Full component layout, data flow diagram, file paths under `src/`, `Posting` / `RawPosting` / `seen.json` schemas, error-isolation contract. **Authoritative for file layout under `src/`.**
- `.planning/research/STACK.md` — Locked dependency choices and versions (httpx, tenacity, pydantic v2, orjson, selectolax, BeautifulSoup4, pytest, respx, uv, ruff). Phase 1 does NOT install Playwright (deferred to Phase 3).
- `.planning/research/PITFALLS.md` — All 27 pitfalls with prevention strategies. Phase 1 must address Pitfalls 1 (atomic write), 2 (sanity gate), 3 (concurrency), 4 (secrets + .gitignore), 5 (stable dedup keys), 13 (Markdown escaping), 16 (workflow permissions), 17 (log discipline), 18 (empty commits — handled by `git-auto-commit-action@v5` default). Pitfall 23 (schedule-disable) is **knowingly not mitigated** in Phase 1 per D-01/D-02.
- `.planning/research/FEATURES.md` — Must-have / should-have / defer feature lists; Phase 1 scope maps to "must have" + a subset of "should have" (per-source error isolation, informative commit messages).

### External API References (Greenhouse only for Phase 1)

- Greenhouse public boards API: `https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true` (no auth; documented in STACK.md and SUMMARY.md). Field shape verified against research training data; planner should fetch a live sample at implementation time to confirm field names before writing pydantic models (per SUMMARY.md "Gaps to Address" §1).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

This is a greenfield repository (no `src/` exists yet, no Python code, no tests, no workflows). All assets in Phase 1 are created from scratch following the layout in `.planning/research/ARCHITECTURE.md`.

### Established Patterns

- **File layout pattern** (from ARCHITECTURE.md): `src/{main.py,registry.py,config_loader.py,normalizer.py,filter.py,state_store.py,state_merger.py,renderer.py,models.py}` plus `src/adapters/{base.py,greenhouse.py}`. Tests under `tests/` mirror the source layout with `tests/fixtures/` for recorded JSON.
- **Pure-core / impure-edges pattern** (from ARCHITECTURE.md §Key boundary rules): `normalizer`, `filter`, `state_merger`, `renderer` are pure functions (no I/O, no `datetime.now()`). `adapters/*`, `state_store`, `config_loader`, `main.py` are the only modules that perform I/O. `main.py` is the only module that calls `datetime.now(timezone.utc)` — the resulting `run_started_at` threads through everywhere else as a parameter (RUN-01).
- **Per-company try/except isolation** (from ARCHITECTURE.md §Error isolation guarantee and ADP-12): the `for company in companies` loop in `main.py` wraps each company's `fetch → normalize → filter` pipeline in `try/except Exception`, logs the failure, and continues. State for failed companies is preserved untouched.

### Integration Points

- **`README.md` ↔ `renderer.py`:** Renderer reads README, locates `<!-- BEGIN JOBS -->` and `<!-- END JOBS -->` sentinels, replaces only the content between them. The README's other sections (project description, setup notes, ToS notice when added later) are never touched by the renderer.
- **`seen.json` ↔ `state_store.py`:** State store is the sole owner of `seen.json` reads/writes. Atomic write via `os.replace`, `.bak` fallback on read corruption, sanity gate before commit (D-06).
- **`companies.txt` ↔ `config_loader.py`:** Loader parses one URL per line, strips whitespace, skips blank lines and `#`-prefixed comments, validates each URL is well-formed and uses `http`/`https`, supports optional `#adapter=<name>` inline hint. Returns `list[CompanyConfig]`.

</code_context>

<specifics>
## Specific Ideas

- **Seed company convention for fixtures:** Use Stripe in `tests/fixtures/greenhouse_<seed>.json` if the planner needs to pick a name (matches ROADMAP success criterion #1's "e.g., Stripe" reference). The fixture is committed; the user's actual `companies.txt` content is *not* this fixture.
- **`companies.txt` placeholder content (Day 1):** A header comment block explaining the format, then no URL lines. Example contents the planner can adapt:
  ```
  # companies.txt — one career URL per line.
  # Blank lines and lines starting with `#` are ignored.
  # Phase 1 supports Greenhouse only — other ATSes (Lever / Ashby / SmartRecruiters / Workday / Apple)
  # land in Phase 2. Non-Greenhouse URLs added before Phase 2 are silently skipped.
  ```
- **Sanity-gate failure exit code:** Non-zero so the run appears red in the Actions tab and the cron history surfaces the failure on manual inspection (no notification system).

</specifics>

<deferred>
## Deferred Ideas

- **`health.json` mechanism (INFRA-05).** Removed from Phase 1 per D-01. Revisit in a later phase (likely Phase 5 / sustainability) if the 60-day cold-start risk materializes or if the user wants per-company telemetry surfaced. When re-added, the field shape decision (minimal / per-company timestamps / rich) becomes a sub-decision.
- **Error-path adapter tests (SchemaDrift, SiteBlocked).** Deferred to Phase 2 per D-07. Phase 2's planner should add fixture-mutation tests for every adapter at once, exercising the shared `Adapter` ABC error contract uniformly.
- **Source Health footer in README (OUT-09).** Already scheduled in Phase 4 per ROADMAP. Not a Phase 1 concern; mentioned here so the planner does not preemptively scaffold for it.
- **Go-live verification gate.** "Wait for 2 successful hourly cron runs on a real repo before declaring Phase 1 done" was considered but rejected. With the placeholder `companies.txt`, those runs produce no diff and prove nothing. Live verification happens post-launch when the user adds URLs.
- **Auto-removal of companies from `seen.json` when their URL leaves `companies.txt`.** Out of scope — STATE-04 explicitly forbids deletion. Stale entries with `still_listed: true` from the last scrape remain in `seen.json` and continue to render in the table. User can manually clean up `seen.json` if needed.

</deferred>

---

*Phase: 01-walking-skeleton*
*Context gathered: 2026-06-07*
