# Roadmap: new-grad

**Defined:** 2026-06-07
**Granularity:** coarse
**Mode:** mvp (Vertical MVP — every phase delivers an end-to-end working slice)
**Core Value:** One glance at the GitHub repo shows every currently-known new-grad-eligible role across the user's tracked companies, with a working application link.

## Phases

- [ ] **Phase 1: Walking Skeleton** — One Greenhouse company scraped, filtered, deduped, rendered, committed end-to-end on hourly cron
- [x] **Phase 2: ATS Breadth + JD-Scan** — Lever, Ashby, SmartRecruiters, Workday, Apple adapters land; experience-range extraction from descriptions  *(execute-complete 2026-06-08; awaiting `/gsd-verify-phase 2`)*
- [ ] **Phase 3: Playwright Fallback + Credential Workflow** — Headless-browser adapter covers non-ATS SPAs; `gh secret set` workflow for sites needing login (Wave 1/3 complete: URL resolver + Playwright cache foundation landed in Plan 03-01)
- [x] **Phase 4: Extraction Polish + Health Observability** — Salary verbatim + location Remote-collapse + US-only region filter (FILT-07); per-source health DATA tracked in `seen.json.source_health` (data-persisted-not-rendered per Phase 4 CONTEXT.md D-04c) (completed 2026-06-08)

## Phase Details

### Phase 1: Walking Skeleton
**Goal**: User opens repo and sees real Greenhouse postings in a README table updated within the last hour by GitHub Actions — every architectural seam exists, every existential risk is baked in, and the commit-back loop is proven on real infrastructure.
**Mode:** mvp
**Depends on**: Nothing (foundation phase)
**Requirements**:
- INFRA-01, INFRA-02, INFRA-03, INFRA-04, ~~INFRA-05~~ (removed per phases/01-walking-skeleton/01-CONTEXT.md D-01 — `health.json` deferred), INFRA-06, INFRA-07, INFRA-08, INFRA-09, INFRA-10
- CFG-01, CFG-02, CFG-03, CFG-04, CFG-05, CFG-06
- ADP-01, ADP-02, ADP-03, ADP-11, ADP-12, ADP-13, ADP-14, ADP-15
- FILT-01, FILT-02, FILT-04, FILT-05, FILT-06
- NORM-01, NORM-04, NORM-05, NORM-06, NORM-07
- STATE-01, STATE-02, STATE-03, STATE-04, STATE-05, STATE-06, STATE-07, STATE-08
- OUT-01, OUT-02, OUT-03, OUT-04, OUT-05, OUT-06, OUT-07, OUT-08
- SEC-03, SEC-05
- RUN-01, RUN-02, RUN-03, RUN-04

**Success Criteria** (what must be TRUE):
  1. User opens `github.com/DevDesai444/new-grad` and sees a Markdown table with real new-grad-eligible Greenhouse postings (e.g., Stripe) updated within the last hour, columns: Company | Position | Location | Salary | Experience | Posting | Age — each Posting link opens the application page on the company's career portal.
  2. The hourly cron has fired at least twice; the second run produces no spurious diff (idempotent render) and `seen.json` correctly tracks `first_seen` / `last_seen` per posting; no posting that was ever observed has been deleted from `seen.json`.
  3. Killing the workflow mid-run (or running `--validate` against a deliberately corrupted `seen.json`) does not brick the next run — atomic write + `.bak` fallback + sanity gate (≥0.9× prior count) all engage as designed; the run continues, exits non-zero on unrecoverable corruption, and never silently wipes the table.
  4. User runs `gh secret list` and confirms zero secrets are referenced by Phase 1 adapters (Greenhouse needs none); a deliberate `git add` of `.env`, `cookies.json`, or `trace.zip` is blocked by `.gitignore` + repo-level Push Protection; no credential string ever appears in workflow logs.
  5. User asks Claude CLI to "add this Greenhouse URL" — Claude appends one line to `companies.txt`, commits, pushes; the next hourly run picks up the new company without any other edit.
**Plans**: 3 plans
- [x] 01-01-PLAN.md — Project scaffold, .gitignore, GH Actions workflow, data models, Adapter ABC + typed errors, Greenhouse adapter + fixture + unit tests (Wave 1)
- [x] 01-02-PLAN.md — Pure-core pipeline: normalizer, filter, state_store (atomic write + sanity gate), state_merger (add-only), renderer (sentinels + Markdown escape + idempotent), registry (URL dispatch) (Wave 2)
- [x] 01-03-PLAN.md — config_loader, main.py orchestrator (per-company isolation, run_started_at, summary), end-to-end pipeline test, adapter-contract test, README docs (CFG-04/06, INFRA-08, SEC-03) (Wave 3)

### Phase 2: ATS Breadth + JD-Scan
**Goal**: User's `companies.txt` can list any Greenhouse, Lever, Ashby, SmartRecruiters, Workday, or Apple URL and the hourly run scrapes them all, extracting experience range from each posting's description so the Experience column populates.
**Mode:** mvp
**Depends on**: Phase 1 (adapter ABC, registry, normalizer, filter, state, render, commit must all exist)
**Requirements**:
- ADP-04, ADP-05, ADP-06, ADP-07, ADP-08
- FILT-03

**Success Criteria** (what must be TRUE):
  1. User opens the repo after an hourly run and sees postings from at least 3 distinct ATS platforms (Greenhouse + Lever + at least one of Ashby/SmartRecruiters/Workday/Apple) in the same Markdown table, each with stable dedup keys (`gh:<co>:<id>`, `lever:<co>:<uuid>`, etc.); no duplicates across re-scans even when source URLs gain tracking params.
  2. Workday postings show correct posted dates (epoch-millisecond handling verified against a live Workday tenant) and Apple Jobs postings show correct postingDate; all dates render as UTC ISO 8601 internally and as human-readable Age (`3h`, `2d`, `3w`) in the table.
  3. The Experience column shows `Xy–Yy` / `≤Yy` / blank for the majority of postings — extracted via JD-scan regex (`X+ years`, `X-Y years`, `entry-level`, `recent graduate`); a posting whose title passes the keyword gate but whose JD says `5+ years required` is correctly excluded from the table.  *[Softened per .planning/phases/02-ats-breadth-jd-scan/02-CONTEXT.md D-02: JD-scan is display-only; the title-pass / JD-says-5+yr row STAYS in the table with `Experience` showing `5y+` rather than being excluded. FILT-04 in REQUIREMENTS.md is struck through. The first half of the criterion (Experience column populates) still holds.]*
  4. One adapter failing (e.g., Workday returns `SiteBlocked` because the tenant is rate-limiting Actions IPs) does NOT abort the run for the other adapters; the failing company keeps its prior `seen.json` entries unchanged with `still_listed` preserved, and the rest of the table updates normally.
**Plans**: 3 plans
- [x] 02-01-PLAN.md — Lever, Ashby, SmartRecruiters adapters + normalizer dispatch + registry append + 27 D-03 tests (Wave 1; ADP-04/05/06)  *(complete 2026-06-08; 3 commits bc05f08/3a9308f/f77106c; 214 cumulative tests; ADP-14/15 open-closed re-proven)*
- [x] 02-02-PLAN.md — Workday adapter (D-01 URL regex + D-04 pagination + 3-form postedOn parsing) + normalizer + registry + 35 tests (Wave 2; ADP-07)  *(complete 2026-06-08; 2 commits ff6172a/9d22e62; 249 cumulative tests; ADP-14/15 open-closed re-proven with 5 adapters)*
- [x] 02-03-PLAN.md — Apple adapter + JD-scan extension (extract_experience_range wires all 6 normalizers; is_early_career simplified per D-02) + retroactive Greenhouse D-03 tests + REQUIREMENTS.md FILT-04 strikethrough (Wave 3; ADP-08, FILT-03)  *(complete 2026-06-08; 3 commits 589f1da/c44f910/efba667; 298 cumulative tests; Phase 2 execute-complete — all 6 phase REQ-IDs closed; ADP-14/15 open-closed re-proven across all 3 Phase 2 plans with 6 adapters)*

### Phase 3: Playwright Fallback + Credential Workflow
**Goal**: User's `companies.txt` can include a JS-heavy SPA (e.g., Anthropic, custom careers portal) and the hourly run scrapes it via headless Chromium; if a site requires login, Claude CLI handles the entire credential-storage flow via `gh secret set` with zero manual repo-config work from the user.
**Mode:** mvp
**Depends on**: Phase 2 (adapter contract proven stable across 6 ATS adapters before exercising the most exotic adapter type)
**Requirements**:
- ADP-09, ADP-10
- SEC-01, SEC-02, SEC-04, SEC-06

**Success Criteria** (what must be TRUE):
  1. User opens the repo after an hourly run and sees at least one posting from a JS-heavy SPA (no ATS JSON endpoint) — scraped via Playwright fallback with `wait_for_selector` or `expect_response`, parsed via selectolax, surfaced in the same table alongside ATS-sourced rows; per-page navigation timeout (20s) enforces that a hung page produces a typed `PlaywrightTimeout` error and not a silent zero-result wipe.
  2. The Playwright Chromium cache (`actions/cache@v4` keyed on `requirements.lock`) is hit on the second consecutive run; cold-install penalty (~90s) only occurs on cache miss; total workflow runtime remains under `timeout-minutes: 50`.
  3. User says "add this credentialed site" to Claude CLI — Claude inline-prompts for email + password in chat, calls `gh secret set SCRAPER_<COMPANY>_EMAIL` and `SCRAPER_<COMPANY>_PASSWORD --repo DevDesai444/new-grad`, confirms by running `gh secret list` (names only, no values), commits the adapter referencing `os.environ[<NAME>]`, and updates the README's secret-name audit table — none of the credential values ever appear in chat history, repo files, or Actions logs.
  4. `playwright-stealth` is applied only to sites that demonstrably need it (per-site flag in registry), not globally — verified by inspecting the registry config; sites that work without stealth do not pay its cost.
**Plans**: 3 plans
- [x] 03-01-PLAN.md — URL redirect resolver (`src/url_resolver.py` + `CompanyConfig.resolved_url` field) + registry/orchestrator wiring + `.github/workflows/scan.yml` Chromium install step + cache key on `requirements.lock` + `.gitignore` trace-debug extension (Wave 1; foundational — claims ADP-09 prerequisite) — **COMPLETE 2026-06-08** (commits 70fb47d, 07489cd; 316 tests; ADP-14/15 preserved)
- [x] 03-02-PLAN.md — `PlaywrightAdapter` (`src/adapters/playwright_fallback.py`): XHR-intercept-first + DOM-selector fallback against Anthropic seed target + `playwright-stealth` on by default + 60s navigation timeout + trace=off-in-prod + `pw:<host>:<id>` dedup keys + normalizer dispatch + registry append-as-catch-all-LAST (Wave 2; ADP-09 + ADP-10) — **COMPLETE 2026-06-08** (commits 7202dc0, ac6f40f; 348 tests; ADP-14/15 preserved with 7 adapters)
- [x] 03-03-PLAN.md — Credential workflow: `InvalidCredential` typed exception in `src/adapters/base.py` + `_attempt_login` flow reads `SCRAPER_<COMPANY_UPPERCASE>_<KIND>` env vars (SEC-02) + structural SEC-03 ban on credential-value logging + CLAUDE.md `## Adding a Company` 5-step workflow (per D-03 + D-03a) + README.md `## Credential Naming Convention (SEC-06)` with per-adapter audit table (Wave 3; SEC-01 + SEC-02 + SEC-04 + SEC-06)

### Phase 4: Extraction Polish + Health Observability
**Goal**: Salary and Location columns populate verbatim from the source (no parsing per Phase 4 CONTEXT.md D-01); Remote-variant locations collapse to canonical `Remote (US)` / `Remote (non-US)` (D-02); a US-only region filter (FILT-07 — new requirement defined in this phase per D-03) drops non-US postings before render; per-source adapter health is **tracked in `seen.json.source_health` but NOT rendered in the README** (D-04c — user explicitly does not want a footer; data exists for Claude CLI diagnostic reads).
**Mode:** mvp
**Depends on**: Phase 3 (all adapter types — ATS, Playwright, credentialed — must exist so source_health covers the full surface)
**Requirements**:
- NORM-02 *(per Phase 4 CONTEXT.md D-01: verbatim copy-paste from ATS, not regex extraction — replaces the original "pattern library" language)*
- NORM-03
- FILT-07 *(NEW — added by Phase 4 Plan 04-02 per CONTEXT.md D-03; reverses PROJECT.md's prior "US-only region filter" out-of-scope listing)*
- ~~OUT-09~~ *(softened per Phase 4 CONTEXT.md D-04c — data persisted in `seen.json.source_health` (status / consecutive_failures / last_attempt_utc / last_success_utc); NOT rendered in README footer; rendering deferred to future 1-task plan if user reverses)*

**Success Criteria** (what must be TRUE):
  1. User opens the repo after an hourly run and sees a Salary column populated with the source's verbatim salary string (e.g., `$120k–$160k`, `£60,000 - £80,000`) for the majority of postings whose ATS exposes salary; empty / None / non-numeric placeholder strings (`Competitive`, `DOE`, `TBD`, `Not disclosed`, `N/A`, `null`, `Negotiable`) render as `—`; values longer than 80 chars are truncated with an ellipsis.  *[Refined per Phase 4 CONTEXT.md D-01: salary is verbatim copy-paste, not regex extraction. The "pattern library validated against 30 real strings" language from the original criterion is dropped — verbatim copy-paste has no parsing surface to validate.]*
  2. User opens the repo and sees Location values like `Remote (US)` (not `Remote, United States` on one row and `Remote — US` on another); non-Remote city strings display verbatim (no deep city canonicalization per D-02b); multi-location postings render readably without breaking table alignment. Postings whose location classifies as non-US per `is_us_location()` are dropped before the renderer (FILT-07).
  3. ~~Below the postings table, the README shows a "Source Health" footer...~~  *[Softened per Phase 4 CONTEXT.md D-04c: Source Health data IS tracked per-run in `seen.json.source_health` (status: `ok` / `blocked` / `schema-drift` / `error`; plus `consecutive_failures`, `last_attempt_utc`, `last_success_utc` per company), but is NOT rendered in the README footer — user explicitly does not want footer visibility. Future Claude CLI sessions consume the data directly from `seen.json.source_health`. Footer rendering deferred to a future 1-task plan if the user reverses this preference.]*
**Plans**: 3 plans
- [x] 04-01-PLAN.md — `src/locations.py` (new module: `normalize_location` + `is_us_location` + ~30-city + 50-state curated lists) + normalizer extensions for all 7 adapters (salary verbatim per CONTEXT.md D-01 per-adapter access table; location routes through `normalize_location`) + renderer salary cell (placeholder coalesce → `—` + 80-char truncation per D-01a/b) (Wave 1; NORM-02 + NORM-03)  — **Complete 2026-06-08: 124 net new tests / 499 cumulative; ADP-15 re-proven a 7th time**
- [x] 04-02-PLAN.md — `is_us_location_acceptable()` in `src/filter.py` + orchestrator wiring (FILT-07 runs AFTER `is_early_career` and BEFORE state merge per CONTEXT.md D-03a) + REQUIREMENTS.md FILT-07 insertion as 7th Filter entry + Traceability + Coverage update (Wave 2; FILT-07 — NEW requirement)  — **Complete 2026-06-08: 25 net new tests / 524 cumulative; ADP-15 re-proven an 8th time**
- [x] 04-03-PLAN.md — `seen.json` schema bump 1 → 2 (`src/state_store.py` auto-migrates v1 → v2 in load_state; saver writes v2; v3+ still raises UnknownSchemaVersion per STATE-08) + `source_health` block per CONTEXT.md D-04 schema + `update_source_health` / `classify_outcome` helpers in `src/state_merger.py` (per D-04b classification rules: 3+ consecutive SiteBlocked → "blocked"; SchemaDrift → "schema-drift"; other → "error") + orchestrator wiring + REQUIREMENTS.md OUT-09 strikethrough amendment (D-04c) (Wave 3; OUT-09 data-persisted-not-rendered)

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Walking Skeleton | 3/3 | Execute-complete (verification pending) | 2026-06-08 |
| 2. ATS Breadth + JD-Scan | 3/3 | Execute-complete (verification pending) — all 6 phase REQ-IDs closed: ADP-04..08 + FILT-03 | 2026-06-08 |
| 3. Playwright Fallback + Credential Workflow | 3/3 | Execute-complete (verification pending) — all 6 phase REQ-IDs closed: ADP-09 + ADP-10 + SEC-01/02/04/06 | 2026-06-08 |
| 4. Extraction Polish + Health Observability | 3/3 | Complete   | 2026-06-08 |

## Phase Ordering Rationale

- **Phase 1 is the only cheap chance to bake in the five existential risks** (atomic `seen.json` write, concurrency group, sanity gate against zero-result wipe, secret hygiene, schedule-keepalive `health.json`). Retrofitting these into a 500-line scraper is painful; building them into a 100-line slice is trivial. Phase 1 also locks the per-ATS dedup key format (`gh:<co>:<id>`) before adapter breadth — changing the key format retroactively requires a `seen.json` migration.
- **Phase 2 is mechanical given Phase 1's adapter ABC.** Lever, Ashby, SmartRecruiters are similar single JSON GET calls; Workday is more complex (per-tenant POST body, epoch-ms dates) but belongs here because it covers Nvidia, Microsoft, and many large employers. Apple Jobs is included since its `api/role/search` is JSON-first (Playwright not needed). JD-scan extraction lands here because it co-evolves with the adapter response shapes that expose description text.
- **Phase 3 is deferred until Phases 1–2 prove the adapter contract.** Playwright is the most complex adapter, most failure-prone (anti-bot, hydration timing, browser cache cost), and the only one that pairs with the credential workflow. Implementing it third keeps Phases 1–2 clean and ensures the adapter interface is mature before the most exotic case exercises it. The credential workflow (`gh secret set`) lives here because the first plausible credentialed scrape is a custom SPA, not an ATS API.
- **Phase 4 is extraction polish that doesn't affect architectural correctness.** Salary verbatim + Remote-variant collapse + US-only filter + source_health observability data are late-binding — they ship after the core pipeline is stable. Per CONTEXT.md D-04c the Source Health footer is dropped from rendering (user does not want it); the underlying data is still tracked per-run for diagnostic reads via `seen.json.source_health`.

## SEC Mapping Justification

The 6 SEC requirements split across phases by intent:

- **Phase 1 (foundational hygiene):** SEC-03 (credentials never written to repo files, chat history, or logs — a discipline, not a feature, established before any credential ever exists) and SEC-05 (`MissingCredential` typed error defined and integrated into the orchestrator's per-company isolation so a missing env var on one company doesn't abort the run for others).
- **Phase 3 (credential workflow):** SEC-01 (Claude inline-prompts the user and calls `gh secret set`), SEC-02 (`SCRAPER_<COMPANY>_<KIND>` naming convention enforced in adapter code), SEC-04 (confirmation via `gh secret list`, names only), and SEC-06 (README documents which secret names which adapter references for user audit/rotation).

This split is correct because Phase 1 has no plausible credentialed scrape (Greenhouse is public, no login), but must establish the hygiene rules; Phase 3 is where the first credentialed scrape actually lands (custom SPA via Playwright is the only plausible case for v1).

## Coverage

- v1 requirements total: 72 (10 INFRA + 6 CFG + 15 ADP + 7 FILT + 7 NORM + 8 STATE + 9 OUT + 6 SEC + 4 RUN) *[FILT-07 added by Phase 4 Plan 04-02 per CONTEXT.md D-03; original total was 71]*
- Mapped: 72/72 ✓
- Unmapped: 0
- See REQUIREMENTS.md Traceability table for the per-requirement → phase mapping.

---
*Roadmap created: 2026-06-07*
*Phase 2 plans finalized: 2026-06-08 (Plans 02-01, 02-02, 02-03 — covers ADP-04..08 + FILT-03)*
*Phase 3 plans finalized: 2026-06-08 (Plans 03-01, 03-02, 03-03 — covers ADP-09, ADP-10, SEC-01, SEC-02, SEC-04, SEC-06)*
*Phase 4 plans finalized: 2026-06-08 (Plans 04-01, 04-02, 04-03 — covers NORM-02, NORM-03, FILT-07 (new), OUT-09 (softened per D-04c))*
