# Phase 1: Walking Skeleton - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 01-walking-skeleton
**Areas discussed:** health.json commit policy, Seed Greenhouse company + Day-1 companies.txt, Sanity-gate cold-start rule (STATE-06), Adapter error-path test strategy

---

## health.json commit policy

### Round 1 — Commit cadence

| Option | Description | Selected |
|--------|-------------|----------|
| Daily heartbeat in health.json | health.json only changes once per UTC day. 365 commits/year. Schedule stays alive; git log stays useful. | |
| Commit every hour | health.json timestamp updates every run. 8,760 commits/year. Schedule bulletproof. Noisy git log. | ✓ (initial) |
| Commit only when other files change | health.json bumps only when README/seen.json also change. Quiet periods produce zero commits. Defeats INFRA-05. | |

**User's initial choice:** Commit every hour.

### Round 2 — health.json fields

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: last_run + status | {last_run_utc, status, run_count}. Smallest diff. | |
| Minimal + per-company timestamps | Adds `per_company: {<name>: last_successful_run_utc}` for future Phase 4 footer. | |
| Rich: full per-source telemetry | Per-company outcomes, durations, commit hash, totals. | |

**User's response (paraphrased):** "What is health.json for?" — clarification requested. After explanation, user reversed direction: "Don't worry about that, such case won't happen (no posting for 60 days never happens), assume each commit will have some changes."

### Round 3 — Confirm drop

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — drop it, accept risk | No health.json. INFRA-05 removed. Manual re-enable if schedule dies. | ✓ |
| Keep minimal version after all | 1-line file, hourly commit, no cold-start risk. | |
| Defer the decision | Mark Claude's discretion. | |

**User's final choice:** Drop health.json entirely. "Project will find some new posting every hour so there is no problem of empty commits, and even if there are empty commits I don't care."

**Notes:** This reversed the Round-1 answer. The user's mental model is that postings WILL change at least hourly once the real URL list is added post-launch. They're explicitly accepting the 60-day cold-start risk for Phase 1's placeholder-companies.txt window. Captured as D-01 / D-02.

---

## Seed Greenhouse company + Day-1 companies.txt

### Round 1 — Seed company

| Option | Description | Selected |
|--------|-------------|----------|
| Stripe | Greenhouse `stripe`. Consistent new-grad volume. Mentioned in ROADMAP criterion. | |
| Airbnb | Greenhouse `airbnb`. Smaller volume but reliable. | |
| Pick a company you're applying to | User-personal seed. Risk: may not have current postings. | |

**User's response (paraphrased):** "Commits, once you write the code I will give you 10 company career websites — even if there's no new posting in any of the company, there won't be an empty commit, right?"

**Claude's response:** Explained that `git-auto-commit-action@v5` skips on no-diff by default — no empty commits regardless of company count. Also flagged that Phase 1 only ships the Greenhouse adapter, so non-Greenhouse URLs in the eventual 10-list will be logged + skipped (CFG-05).

### Round 2 — Day-1 companies.txt content

| Option | Description | Selected |
|--------|-------------|----------|
| Stripe only | One Greenhouse URL. Phase 1 verification is reliable on live data. | |
| 3–5 Greenhouse companies | Exercises per-company isolation on real data. | |
| Empty / placeholder file | User adds URLs after code is reviewed. Verification can't prove end-to-end on live data. | ✓ |

**User's final choice:** "I will give you later, till then use placeholder."

**Notes:** Captured as D-03 / D-04 / D-05. Phase 1 verification becomes fixture-based (recorded Greenhouse JSON via respx) instead of live-data-based. Success criterion #1 from ROADMAP is deferred to post-launch user-driven verification.

---

## Sanity-gate cold-start rule (STATE-06)

### Round 1 — Cold-start behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Skip gate when prior < N (floor) | E.g., N=5. Below N, gate no-op. Above N, 0.9× protection engages. | |
| Skip gate when no_adapter_succeeded_last_run | Engages only after a prior successful scrape. | |
| Always engage | Gate runs every time. prior=0 trivially passes. prior=1 boundary aborts on zero-result. | |

**User's response (paraphrased):** "What is the prior, explain me in short, easy to understand."

**Claude's response:** Plain-English explanation provided — "prior" = postings count from previous run's seen.json; gate aborts the commit if current scrape returns dramatically less; protects against zero-result wipes; cold-start prior=0 is trivially safe.

### Round 2 — Re-ask after clarification

| Option | Description | Selected |
|--------|-------------|----------|
| Skip when prior < 5 | Floor at 5. Below = no-op. Predictable. | |
| Always engage | Gate runs every time. prior=1 boundary defensive. | ✓ |
| Let the planner decide | Claude's discretion. | |

**User's final choice:** Always engage.

**Notes:** Captured as D-06. The prior=1 boundary aborts on a zero-result scrape — the user accepted this as defensive behavior (any unexplained loss of state fails loud, even at small sizes).

---

## Adapter error-path test strategy

### Round 1

| Option | Description | Selected |
|--------|-------------|----------|
| Fixture mutation tests via respx | Per-adapter tests mutate recorded fixture to trigger SchemaDrift; mock 403/CAPTCHA for SiteBlocked. Test orchestrator try/except. | |
| Tests + deliberate runtime drill | Same as above + CI step running orchestrator against broken fixtures. | |
| Skip explicit error-path tests in Phase 1 | Trust happy-path tests; defer error-path tests to Phase 2. | ✓ |

**User's final choice:** Skip explicit error-path tests in Phase 1.

**Notes:** Captured as D-07. Risk explicitly accepted: if SchemaDrift / SiteBlocked handlers have bugs, the bug surfaces in Phase 2 under real drift conditions. Phase 2 planner is expected to add fixture-mutation tests across all adapters at once. D-08 added separately: ADP-12 (per-company isolation) is still tested in Phase 1, but with a mock adapter raising generic Exception — does not depend on typed errors.

---

## Claude's Discretion

Items not explicitly asked because they are implementation details, not user-visible choices:

- Idempotent-render proof test (OUT-07): planner picks whether to add an explicit byte-equal test or rely on the fixture-based pipeline test.
- `still_listed` semantics when a company is removed from companies.txt: planner follows STATE-04 ("keys are never deleted"); stale entries remain with their last-known `still_listed` value.
- `seen.json` backup filename (`seen.json.bak` vs `seen.previous.json`): planner picks.
- Fixture file naming (`greenhouse_stripe.json` vs `greenhouse_sample.json`): planner picks.
- REQUIREMENTS.md INFRA-05 strikeout convention: planner marks during phase plan generation.

## Deferred Ideas

- `health.json` mechanism — revisit in a later phase if 60-day risk materializes.
- Error-path adapter tests (SchemaDrift, SiteBlocked) — Phase 2.
- Source Health footer (OUT-09) — already scheduled in Phase 4.
- Go-live verification gate — rejected; live verification happens post-launch when user adds URLs.
- Auto-removal of companies from `seen.json` — explicitly out of scope per STATE-04.
