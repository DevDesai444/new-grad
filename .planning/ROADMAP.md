# Roadmap: new-grad

**Defined:** 2026-06-07
**Granularity:** coarse
**Mode:** mvp (Vertical MVP — every phase delivers an end-to-end working slice)
**Core Value:** One glance at the GitHub repo shows every currently-known new-grad-eligible role across the user's tracked companies, with a working application link.

## Phases

- [ ] **Phase 1: Walking Skeleton** — One Greenhouse company scraped, filtered, deduped, rendered, committed end-to-end on hourly cron
- [ ] **Phase 2: ATS Breadth + JD-Scan** — Lever, Ashby, SmartRecruiters, Workday, Apple adapters land; experience-range extraction from descriptions
- [ ] **Phase 3: Playwright Fallback + Credential Workflow** — Headless-browser adapter covers non-ATS SPAs; `gh secret set` workflow for sites needing login
- [ ] **Phase 4: Extraction Polish + Health Observability** — Salary + location normalization; per-source health footer renders status of every tracked company

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
- [ ] 02-03-PLAN.md — Apple adapter + JD-scan extension (extract_experience_range wires all 6 normalizers; is_early_career simplified per D-02) + retroactive Greenhouse D-03 tests + REQUIREMENTS.md FILT-04 strikethrough (Wave 3; ADP-08, FILT-03)

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
**Plans**: TBD

### Phase 4: Extraction Polish + Health Observability
**Goal**: Salary and Location columns are useful (not just `—`) for the majority of postings, and the README footer surfaces per-source health (ok / blocked / schema-drift / error) so the user can passively notice when a company's adapter has degraded without needing notifications.
**Mode:** mvp
**Depends on**: Phase 3 (all adapter types — ATS, Playwright, credentialed — must exist so the health footer covers the full surface)
**Requirements**:
- NORM-02, NORM-03
- OUT-09

**Success Criteria** (what must be TRUE):
  1. User opens the repo after an hourly run and sees a Salary column populated with normalized values (`$120k–$160k`, `≤$200k`, `$50/hr`) for the majority of postings whose source exposes salary; unparseable strings render as `—` (never `$0–$0` or `null`); the pattern library was validated against a corpus of ≥30 real strings from the user's tracked companies.
  2. User opens the repo and sees Location values like `Remote (US)` (not `Remote, United States` on one row and `Remote — US` on another); multi-location postings render readably without breaking table alignment.
  3. Below the postings table, the README shows a "Source Health" footer with rows like `Company | Last seen | Status` covering every URL in `companies.txt` — `ok` rows show recent timestamps, `blocked` rows show how long the company has been failing, `schema-drift` rows surface an adapter contract break; user can scan this footer in one glance to identify which company's adapter needs attention, no notification required.
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Walking Skeleton | 3/3 | Execute-complete (verification pending) | 2026-06-08 |
| 2. ATS Breadth + JD-Scan | 2/3 | Executing — Plans 02-01 (Lever/Ashby/SR) + 02-02 (Workday) complete; Plan 02-03 (Apple + JD-scan) next | - |
| 3. Playwright Fallback + Credential Workflow | 0/? | Not started | - |
| 4. Extraction Polish + Health Observability | 0/? | Not started | - |

## Phase Ordering Rationale

- **Phase 1 is the only cheap chance to bake in the five existential risks** (atomic `seen.json` write, concurrency group, sanity gate against zero-result wipe, secret hygiene, schedule-keepalive `health.json`). Retrofitting these into a 500-line scraper is painful; building them into a 100-line slice is trivial. Phase 1 also locks the per-ATS dedup key format (`gh:<co>:<id>`) before adapter breadth — changing the key format retroactively requires a `seen.json` migration.
- **Phase 2 is mechanical given Phase 1's adapter ABC.** Lever, Ashby, SmartRecruiters are similar single JSON GET calls; Workday is more complex (per-tenant POST body, epoch-ms dates) but belongs here because it covers Nvidia, Microsoft, and many large employers. Apple Jobs is included since its `api/role/search` is JSON-first (Playwright not needed). JD-scan extraction lands here because it co-evolves with the adapter response shapes that expose description text.
- **Phase 3 is deferred until Phases 1–2 prove the adapter contract.** Playwright is the most complex adapter, most failure-prone (anti-bot, hydration timing, browser cache cost), and the only one that pairs with the credential workflow. Implementing it third keeps Phases 1–2 clean and ensures the adapter interface is mature before the most exotic case exercises it. The credential workflow (`gh secret set`) lives here because the first plausible credentialed scrape is a custom SPA, not an ATS API.
- **Phase 4 is extraction polish that doesn't affect architectural correctness.** Salary patterns, location normalization, and the health footer are high-value but late-binding — they should ship after the core pipeline is stable so the salary pattern library can be built from a live corpus of real strings, and the health footer can cover every adapter type that exists. The footer is the product's passive observability layer, replacing notifications for an unattended system.

## SEC Mapping Justification

The 6 SEC requirements split across phases by intent:

- **Phase 1 (foundational hygiene):** SEC-03 (credentials never written to repo files, chat history, or logs — a discipline, not a feature, established before any credential ever exists) and SEC-05 (`MissingCredential` typed error defined and integrated into the orchestrator's per-company isolation so a missing env var on one company doesn't abort the run for others).
- **Phase 3 (credential workflow):** SEC-01 (Claude inline-prompts the user and calls `gh secret set`), SEC-02 (`SCRAPER_<COMPANY>_<KIND>` naming convention enforced in adapter code), SEC-04 (confirmation via `gh secret list`, names only), and SEC-06 (README documents which secret names which adapter references for user audit/rotation).

This split is correct because Phase 1 has no plausible credentialed scrape (Greenhouse is public, no login), but must establish the hygiene rules; Phase 3 is where the first credentialed scrape actually lands (custom SPA via Playwright is the only plausible case for v1).

## Coverage

- v1 requirements total: 71 (10 INFRA + 6 CFG + 15 ADP + 6 FILT + 7 NORM + 8 STATE + 9 OUT + 6 SEC + 4 RUN)
- Mapped: 71/71 ✓
- Unmapped: 0
- See REQUIREMENTS.md Traceability table for the per-requirement → phase mapping.

---
*Roadmap created: 2026-06-07*
*Phase 2 plans finalized: 2026-06-08 (Plans 02-01, 02-02, 02-03 — covers ADP-04..08 + FILT-03)*
