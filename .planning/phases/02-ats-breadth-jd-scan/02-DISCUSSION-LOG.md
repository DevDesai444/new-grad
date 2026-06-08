# Phase 2: ATS Breadth + JD-Scan - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 02-ats-breadth-jd-scan
**Areas discussed:** Workday tenant addressing, JD-scan precision/recall (FILT-03), Adapter error-path tests scope, Workday pagination cap

---

## Workday tenant addressing

| Option | Description | Selected |
|--------|-------------|----------|
| Raw URL, adapter auto-parses | User pastes the careers-page URL as-is; adapter regex-extracts tenant + site. | ✓ |
| Explicit `#adapter=workday` hint | User writes URL + `#adapter=workday:tenant=foo,site=bar` metadata. | |
| Hybrid: auto-parse with override | Auto-parse by default; hint overrides for non-standard tenants. | |

**Outcome:** Raw URL, adapter auto-parses. Unparseable URLs raise `SchemaDrift`. Captured as D-01.

---

## JD-scan precision/recall (FILT-03)

**Round 1 — Initial framing:**

| Option | Description | Selected |
|--------|-------------|----------|
| Title-permissive, JD-strict | Title-yes required; JD signal >5y excludes. | |
| Title wins, JD only informs Experience column | Filter decision is title-only; JD populates column only. | |
| JD wins (precision over recall) | JD signal always overrides title. | |

**User response:** "Explain me this problem what are you saying then I will tell you what to do."

**Claude's response:** Plain-text explanation with examples of misleading recruiter titles ("Software Engineer, New Grad" with "5+ years required" in description). Clarified that JD-scan numbers are *available*; question is whether to use them to filter rows or just display them.

**Round 2 — After clarification:**

| Option | Description | Selected |
|--------|-------------|----------|
| Description wins when it says >5y | Title must say keep; JD >5y kicks out. | |
| Title wins, description is just info | Filter is title-only; JD populates column only. | ✓ |
| Description always wins (strictest) | Any clear JD signal overrides title. | |

**Outcome:** Title wins; JD-scan output is display-only (Experience column). FILT-04's "experience_min ≤ 5" inclusion gate becomes a no-op. Captured as D-02 with explicit guidance to the planner about FILT-04 strikethrough in REQUIREMENTS.md.

---

## Adapter error-path tests scope

**Round 1:**

| Option | Description | Selected |
|--------|-------------|----------|
| Fixture mutation tests via respx | Per-adapter tests for all new + retroactive Greenhouse. | |
| Tests + runtime drill | Same + CI step against broken fixtures. | |
| Skip error-path tests in Phase 2 | Defer to Phase 3. | |

**User response:** "Explain me what are you asking ?"

**Claude's response:** Plain-text explanation of `SchemaDrift` / `SiteBlocked` exception contract, why error paths matter for orchestrator isolation, what fixture-mutation testing means, and what risk each option carries.

**Round 2:**

| Option | Description | Selected |
|--------|-------------|----------|
| All 6 adapters | Greenhouse + 5 new get fixture-mutation tests. ~24 tests. | ✓ |
| Only the 5 new adapters | Greenhouse stays untested at error paths. | |
| Defer all error-path tests to Phase 3 | All happy-path only in Phase 2. | |

**Outcome:** All 6 adapters get error-path tests in Phase 2. Closes D-07 debt from Phase 1. Captured as D-03.

---

## Workday pagination cap

**Round 1:**

| Option | Description | Selected |
|--------|-------------|----------|
| Cap at 200 postings (~10 pages of 20) | Hard count cap per Workday company per run. | |
| Cap at 5 pages | Tighter cap. | |
| No cap | Fetch all pages until empty. | |

**User response (paraphrased):** "Cap like this. Since this project is scanning the sites every hour, it is unlikely that any post is missed. but what it should do is that sort the postings based newest first to older and scan all postings one by one once the project sees that older postings are getting shown up there is no need to scan further. ok ?"

**Outcome (user-proposed strategy, accepted):** Early-termination based on `seen.json` lookup. Sort newest-first; stop fetching pages once the last posting on a page is already in seen.json. Cold-start safety cap of 25 pages (~500 postings) prevents runaway day-one scrapes. Sort-monotonicity sanity check falls back to absolute cap if the source ignores `sortBy`. Applied to Workday and Apple (the two paginated adapters); non-paginated ATSes (Greenhouse / Lever / Ashby / SmartRecruiters) return full board in one response. Captured as D-04.

---

## Claude's Discretion

- Apple Jobs API request body shape — planner to research via live call before locking.
- Per-adapter inter-page sleeps — likely 0.5–1.5s for Workday/Apple; not needed for single-shot adapters.
- Test fixture sourcing — hand-craft synthetic (~3 postings each); avoid live recording.
- `updated_at` field naming per adapter — handled inside each `_extract_<name>` normalizer helper.
- Lever `team` / `categories` field handling — ignored (Posting.location is the only org-location field rendered).
- REQUIREMENTS.md FILT-04 strikethrough — planner marks during plan execution.

## Deferred Ideas

- Manual override files for filter tuning (`included_keywords.txt`, `excluded_keywords.txt`) — SUS-05, v2.
- `#adapter=` metadata for non-standard Workday tenants — documented as escape hatch; no implementation needed (Phase 1's config_loader already supports the hint slot).
- Pagination for non-paginated ATSes — Greenhouse / Lever / Ashby / SmartRecruiters; not a real concern for Phase 2.
- Closed-posting `still_listed` accuracy edge case under early-termination — acceptable per STATE-04; could add periodic deep-scan in Phase 4 if needed.
- LLM-based JD parsing — explicitly out of scope per PROJECT.md.
