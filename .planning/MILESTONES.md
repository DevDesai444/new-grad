# Milestones

## v1.0 new-grad v1.0 MVP (Shipped: 2026-06-08)

**Phases completed:** 4 phases, 12 plans, 23 tasks

**Key accomplishments:**

- Buildable Python 3.12 codebase with pydantic v2 models, Adapter ABC + 4 typed errors, one working Greenhouse adapter emitting stable `gh:<board>:<id>` dedup keys, and an hourly GitHub Actions workflow wired with all 5 existential-risk mitigations (concurrency group, permissions, timeout, cache, commit-back) — 26 happy-path tests passing via respx mocks against a recorded Stripe fixture.
- Pure-core pipeline that turns RawPosting from Plan 01-01's Greenhouse adapter into a rendered Markdown table backed by a versioned, atomic `seen.json` — 124 new tests (51 normalizer+filter, 33 state, 40 renderer+registry) for a cumulative 150 passing, ruff clean, every NORM/FILT/STATE/OUT/ADP-02 requirement traceable to a test.
- Wired the runnable `python -m src.main` orchestrator over Plan 01's adapter and Plan 02's pure-core pipeline; added the companies.txt parser (config_loader), the canonical Phase 1 acceptance-gate end-to-end test (respx-mocked Greenhouse → seen.json + README, byte-identical on second consecutive run under frozen clock), and the open/closed adapter contract test (ADP-14/15). README documents the full user-facing operational model. 37 new tests, 187 cumulative, ruff clean, `python -m src.main` against the placeholder companies.txt exits 0.
- WorkdayAdapter ships ADP-07 fully — D-01 URL auto-parse without metadata hints, D-04 paginated fetch with early-termination + 25-page cold-start cap + sort-monotonicity sanity check, 3-form postedOn resolver (epoch ms / ISO / relative strings), realistic User-Agent (Pitfall 5), and normalizer + registry wiring — added behind the Phase 1 Adapter ABC with ZERO edits to main.py, models.py, state_store.py, state_merger.py, renderer.py, filter.py, config_loader.py, or any sibling adapter file. ADP-14/15 open-closed contract re-proven with 5 adapters.
- Apple Jobs adapter with D-04 pagination (early-termination + 25-page cold-start cap), JD-scan regex extraction populating Experience column across all 6 adapters, is_early_career simplification per CONTEXT.md D-02 (title-gate-only), 4 retroactive Greenhouse D-03 error-path tests closing Phase 1 W-1/D-07 debt, and REQUIREMENTS.md FILT-04 strikethrough — Phase 2 execute-complete with all 6 REQ-IDs closed.
- One-liner:
- One-liner:
- One-liner:
- Per-adapter verbatim Salary cell + canonical `Remote (US)` / `Remote (non-US)` collapse + 8-rule US classifier exported as `is_us_location()` for Plan 04-02 FILT-07 consumption — zero edits to src/adapters/, 124 net new tests, 499 cumulative passing.
- Adds the FILT-07 US-only region filter as a pure-function `is_us_location_acceptable` in `src/filter.py` wrapping Plan 04-01's `is_us_location` 8-rule classifier, wired into the orchestrator AFTER the title-keyword gate with an INFO log line on each drop. REQUIREMENTS.md gains FILT-07 as the 7th Filter entry. 25 net new tests / 524 cumulative passing. ADP-15 re-proven for the 8th consecutive plan.
- seen.json schema bump 1→2 + per-company source_health observability data (data-persisted, NOT rendered per CONTEXT.md D-04c). Phase 4 execute-complete.

---
