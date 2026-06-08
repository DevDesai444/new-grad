# Phase 4: Extraction Polish + Health Observability - Discussion Log

> **Audit trail only.** Decisions are in CONTEXT.md.

**Date:** 2026-06-08
**Phase:** 04-extraction-polish-health-observability
**Areas discussed:** Salary precision/currency, Location normalization scope, Source Health data source, US-only filter (NEW scope item)

---

## Salary extraction precision + currency handling

User requested explanation; Claude explained the salary text formats + the two design axes (precision + currency).

After explanation:

**User's pivot:** "Cant you simply copy paste what they have mentioned ?"

Claude validated this as a smarter approach than what was originally proposed — zero parsing, zero false positives, always 100% accurate, handles any currency. Asked the user to lock the two small refinements (empty handling + truncation).

User also added a new scope item: "I want to see only USA openings ok ?"

Claude flagged this as scope expansion (US-only was in PROJECT.md's Out of Scope) and surfaced it as a separate decision (FILT-07).

| Option | Selected |
|--------|----------|
| Verbatim + `—` for empty/non-numeric + truncate 80 chars | ✓ |
| Verbatim, no transformations | |
| `—` for empty only, non-numeric strings stay raw | |

| US-only decision | Selected |
|------------------|----------|
| Yes — add FILT-07 to Phase 4 | ✓ |
| Defer to a new Phase 5 | |
| Follow-up via /gsd-quick | |

**Captured as D-01 (verbatim salary) + D-03 (FILT-07 new requirement).**

---

## Location normalization scope

User requested explanation; Claude explained the location-string variability + the dual job (visual consistency + US/non-US classification).

After explanation:

| Option | Selected |
|--------|----------|
| Practical: Remote variants + US/non-US classification | ✓ |
| Aggressive: full canonical library | |
| Minimal: Remote variants only | |

**Captured as D-02.**

---

## Source Health data source

User requested explanation; Claude explained that OUT-09 is a separate per-company footer (not the per-posting Age column), and that it requires cross-run persistence somewhere.

**User's pivot:** "Cant you just store at what time you first saw (only if you dont get date at which it was posted from the posting itself) that perticular posting and based on current time just count how old is the posting ?"

Claude clarified the distinction between the Age column (per-posting, already in Phase 1) and the Source Health footer (per-company, what OUT-09 was originally about). The user was conflating the two.

Then user said: "If you think it is usefull then use it else you can drop it. But the thing is I dont want to see it. If you need that for debugging then let it be there, it is for you not me."

Resolution: keep OUT-09 as internal-only diagnostic data, NOT rendered in README. Extend seen.json schema 1→2 to add `source_health` block. Footer is suppressed.

**Captured as D-04.**

---

## Status thresholds

**Skipped as a user question.** Since the Source Health data is not user-facing, the thresholds don't need user input. Locked reasonable defaults internally:
- `ok` — last attempt succeeded
- `blocked` — 3+ consecutive `SiteBlocked` exceptions
- `schema-drift` — most recent failure was `SchemaDrift`
- `error` — any other exception

**Captured as D-04b.**

---

## Claude's Discretion

- Exact US city list contents (~30 entries; planner picks)
- Exact non-US city/country list (~30 entries; planner picks)
- Exact regex for non-numeric salary placeholder
- PlaywrightAdapter salary extraction (best effort)
- OUT-09 REQUIREMENTS.md edit format (strike-through pattern)

## Deferred Ideas

- Source Health README footer rendering — data exists; rendering is a future 1-task plan if desired
- Salary normalization across currencies — out of scope (D-01c)
- Full canonical city library — D-02b limits to Remote variants
- Salary-based sorting / filtering — out of scope v1
- Non-US visibility opt-in — user wants US-only; if changes, easy to add a hint
- Periodic deep scan for paginated adapter `still_listed` accuracy — carried from Phase 2
