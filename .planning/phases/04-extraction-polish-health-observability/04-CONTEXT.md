# Phase 4: Extraction Polish + Health Observability - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 is the smallest phase by REQ count and ships **four** concerns:

1. **Salary column population (NORM-02)** — verbatim copy-paste of the ATS-provided `salary` string into the table cell, with `—` for empties and 80-char truncation. Zero parsing logic. No currency conversion.

2. **Location normalization (NORM-03)** — collapse the Remote-form variants (`Remote, US` / `Remote — US` / `Remote (USA)` → `Remote (US)`) and provide a `is_us_location(s)` classifier that powers the new FILT-07 filter. City names display as-is.

3. **US-only region filter (NEW: FILT-07)** — drops non-US postings before they reach the renderer. Uses NORM-03's classifier. Per FILT-05's bias-toward-inclusion principle, ambiguous/empty locations are kept.

4. **Source Health data (OUT-09, restructured)** — `seen.json` schema bumps from 1 → 2 to add a `source_health` block tracking per-company adapter outcomes (`last_attempt_utc`, `last_success_utc`, `status`, `consecutive_failures`). **Data is tracked but NOT rendered in the README footer** — user explicitly does not want it visible. Used by future Claude CLI sessions to diagnose "I haven't seen Apple postings lately, what's up?" by reading `seen.json.source_health` directly.

**What ships at the end of Phase 4:**
- `src/normalizer.py` extended: every `_extract_<adapter>` helper sets `Posting.salary = raw.get("<salary_field>", "") or ""` (verbatim). Some adapters' salary field is nested; per-adapter access pattern documented inline.
- `src/renderer.py` extended: salary cell respects 80-char truncation per Phase 1's NORM-07 escaping helper (same `_truncate_cell()` used for other cells). Salary `""` or non-numeric placeholders (`Competitive`, `DOE`, `Not disclosed`, `TBD`, `null`) → `—`.
- `src/normalizer.py` extended: each helper normalizes location through new `normalize_location(raw_location: str) -> str` from `src/locations.py`. Remote variants collapse; non-Remote unchanged.
- `src/locations.py` (NEW) — contains `normalize_location()`, `is_us_location(s) -> bool`, and the US state code + city dictionary backing the classifier.
- `src/filter.py` extended: new `is_us_location_acceptable(posting: Posting) -> bool` returns True for US postings AND for ambiguous/empty locations (per FILT-05 bias). Wired into the orchestrator AFTER `is_early_career` filter.
- `src/state_store.py` extended: schema bumps from 1 → 2; loader supports both versions (auto-migrates v1 → v2 by adding empty `source_health: {}`); saver writes v2 only.
- `src/state_merger.py` extended: at run end, per-company status records appended to `source_health`. Adapter exceptions classified into `ok` / `blocked` / `schema-drift` / `error`.
- `.planning/REQUIREMENTS.md` updated: FILT-07 added; OUT-09 description amended to note "data persisted in `seen.json.source_health`; not rendered in README per Phase 4 CONTEXT.md D-04".
- Tests for: salary verbatim + truncation, location normalization happy/edge cases, US/non-US classifier, FILT-07 filtering, schema-bump load/save round-trip, source_health accumulation across runs.

**What is NOT in Phase 4:**
- Source Health footer rendering in README (explicitly excluded per D-04 user decision)
- Salary parsing / extraction logic (replaced by verbatim per D-01)
- Currency conversion (no exchange rates baked, no normalization across currencies)
- Full canonical city library (only Remote variants are collapsed)
- LLM-based field extraction (out of scope per PROJECT.md)

</domain>

<decisions>
## Implementation Decisions

### Salary cell (NORM-02)

- **D-01: Salary is verbatim copy-paste from the ATS-provided field. No parsing.** Each adapter's normalizer helper sets `Posting.salary = raw.get("<salary_path>", None)`. Per-adapter access paths:
  - Greenhouse: `raw["metadata"][?].value` where metadata entry has `name="Salary"` OR top-level absent — fallback to empty string. Greenhouse rarely exposes salary; most Stripe postings will be empty.
  - Lever: `raw.get("salaryRange", {}).get("text", "")` if present, else `raw.get("salary", "")`.
  - Ashby: `raw.get("compensation", {}).get("compensationTierSummary", "")` if `includeCompensation=true` (already in our URL).
  - SmartRecruiters: `raw.get("typeOfEmployment", {})...` — varies; per-adapter helper extracts best-effort.
  - Workday: rarely exposed in CXS response; most will be empty.
  - Apple: response field `requisitions[].postingPay.payRange.text` or similar (verify live at implementation).
  - PlaywrightAdapter: when XHR returns salary, use it; when DOM-scraped, attempt extraction from a known selector (`.salary`, `[data-salary]`) — best effort only.
- **D-01a: Empty / null / non-numeric placeholders → `—`.** Renderer-level: when `Posting.salary` is empty, None, or matches the regex `^\s*(competitive|doe|tbd|not disclosed|null|n/a|—)\s*$` case-insensitive → render `—`. Anything else → render the raw string (after cell-escape + truncation per Phase 1 NORM-07).
- **D-01b: 80-char truncation with ellipsis.** Long salary strings ("$120,000 - $160,000 plus 15% annual bonus plus equity grant of $200K vesting over 4 years") truncated at 80 chars per Phase 1's existing `_truncate_cell()` helper — same rule as other cells. Mirrors Pitfall 13 mitigation.
- **D-01c: No currency conversion, no extraction.** UK/EU postings render their original `£60,000 - £80,000` text. (Note: this is moot if FILT-07 drops all non-US postings — see D-04. But the rule is defensive in case a US adapter ever returns a salary with non-USD prefix.)

### Location normalization (NORM-03)

- **D-02: New module `src/locations.py` with two exports:**
  ```python
  def normalize_location(raw: str) -> str:
      """Collapse Remote variants to canonical form. Non-Remote strings unchanged."""
      # Maps:
      # "Remote, United States" / "Remote — US" / "Remote (USA)" / "Remote - US" / "Remote (United States)" / "REMOTE / US" → "Remote (US)"
      # "Remote, United Kingdom" / "Remote (UK)" / "Remote — Europe" → "Remote (non-US)"
      # "Remote" (no country) → "Remote (US)" (bias-toward-inclusion per FILT-05; user is in US)
      # "Cupertino, CA" / "San Francisco" / "London, UK" → unchanged

  def is_us_location(raw: str) -> bool:
      """True if location string indicates US. False if non-US. True for ambiguous/empty (FILT-05 bias)."""
  ```
- **D-02a: Classifier rules (in order):**
  1. Empty / None → True (ambiguous; FILT-05 bias)
  2. Contains canonical `Remote (US)` (after normalize) → True
  3. Contains canonical `Remote (non-US)` → False
  4. Contains US state code (CA, NY, WA, TX, MA, IL, GA, FL, CO, OR, etc. — 50 + DC) as a standalone token → True
  5. Contains `USA`, `United States`, `U.S.`, `U.S.A.` as a token → True
  6. Contains known US city (`San Francisco`, `New York`, `Seattle`, `Boston`, etc. — a curated list of ~30 major tech-hub cities) → True
  7. Contains known non-US country / city (`London`, `Berlin`, `Bangalore`, `Singapore`, `Toronto`, etc. — curated list of ~30 likely non-US strings) → False
  8. Otherwise → True (ambiguous; FILT-05 bias)
- **D-02b: City name display is verbatim** — `is_us_location()` operates on the raw string, but the rendered cell shows whatever the ATS sent (after `normalize_location()` collapses only the Remote variants). `Cupertino, CA` stays `Cupertino, CA`. `SF` stays `SF`. No deep city canonicalization.
- **D-02c: City lists are intentionally not exhaustive.** ~30 US cities + ~30 non-US cities/countries cover the bulk of postings; ambiguous cases default to "keep" per FILT-05. The user accepts that occasionally a non-US city we don't recognize might leak through; the table is still mostly US.

### US-only region filter (FILT-07 — NEW REQUIREMENT)

- **D-03: New requirement FILT-07 added to REQUIREMENTS.md (Filter section).** Definition (planner writes this into REQUIREMENTS.md during plan execution):
  > **FILT-07**: Postings whose location is classified as non-US by `is_us_location()` (`src/locations.py`) are dropped before the renderer. Ambiguous or empty locations are kept (bias toward inclusion per FILT-05). The filter runs AFTER `is_early_career()` (title-keyword gate) and BEFORE state merge.
- **D-03a: Order of filter passes:** title-keyword (FILT-01/02 — keep/exclude) → US-only (FILT-07 — drop non-US) → state merge. Postings that fail FILT-07 are NEVER stored in `seen.json` and NEVER appear in the README. (Postings that previously made it into `seen.json` before FILT-07 was introduced are NOT retroactively removed — STATE-04's "never delete" rule still wins.)
- **D-03b: Test coverage:** representative test inputs covering all 8 classifier rules in `tests/test_locations.py`. Integration test in `tests/test_orchestrator.py` proves a London-based posting is dropped while an SF posting is kept.

### Source Health data (OUT-09, restructured)

- **D-04: `seen.json` schema bumps from 1 → 2 to add `source_health` block.** New top-level key alongside existing `postings`:
  ```json
  {
    "schema_version": 2,
    "last_run_utc": "2026-06-08T15:00:00Z",
    "postings": { ... },
    "source_health": {
      "Stripe": {
        "last_attempt_utc": "2026-06-08T15:00:00Z",
        "last_success_utc": "2026-06-08T15:00:00Z",
        "status": "ok",
        "consecutive_failures": 0
      },
      "Apple": {
        "last_attempt_utc": "2026-06-08T15:00:00Z",
        "last_success_utc": "2026-06-03T15:00:00Z",
        "status": "blocked",
        "consecutive_failures": 120
      }
    }
  }
  ```
- **D-04a: Schema migration is one-way and automatic.** Loader (`src/state_store.py:load_state()`) handles both versions: if schema_version=1 (or absent), add `source_health: {}`, treat as v2 internally. Saver always writes v2. STATE-08's "refuse unknown future versions" semantics: refuse 3 or higher, accept 1 and 2.
- **D-04b: Status classification rules** (locked defaults, no user input needed):
  - `ok` — last attempt succeeded (adapter returned at least one posting OR `total=0` non-error).
  - `blocked` — last 3+ consecutive attempts raised `SiteBlocked`.
  - `schema-drift` — most recent failure was `SchemaDrift`.
  - `error` — any other failure (generic `Exception`, `PlaywrightTimeout`, `InvalidCredential`, etc.).
- **D-04c: Source Health data is NOT rendered in README footer.** User explicitly does NOT want to see this in the README. The data lives in `seen.json.source_health` for diagnostic purposes only. Future Claude CLI sessions can read it when the user mentions a missing company. **OUT-09 requirement text in REQUIREMENTS.md must be amended to reflect this:** strike-through the original "render as a footer" language and replace with "data persisted in `seen.json.source_health`; not rendered in README per Phase 4 D-04c".
- **D-04d: Per-run accumulation logic** (orchestrator + state_merger):
  - Run start: load `source_health` from `seen.json`.
  - For each company: after adapter call (success or fail), update its entry. On success: `last_attempt_utc = run_started_at`, `last_success_utc = run_started_at`, `status = "ok"`, `consecutive_failures = 0`. On failure: `last_attempt_utc = run_started_at`, `last_success_utc` unchanged, `consecutive_failures += 1`, `status` per D-04b rules.
  - Run end: write back to `seen.json` via atomic write (same path as `postings`).

### Claude's Discretion

These were not explicitly asked because they're implementation details, not user-visible choices:

- **Exact US city list contents (D-02a rule 6).** ~30 cities. Planner picks based on the ATS responses encountered. Suggested seed: San Francisco, New York, Seattle, Boston, Cupertino, Mountain View, Palo Alto, San Jose, Sunnyvale, Redmond, Cambridge MA, Austin, Denver, Chicago, Atlanta, Los Angeles, San Diego, Washington DC, Pittsburgh, Detroit, Phoenix, Portland, Minneapolis, Salt Lake City, Raleigh, Durham, Madison, Ann Arbor, Bellevue, Mountain View. Tunable.
- **Exact non-US city/country list (D-02a rule 7).** ~30 entries. Suggested seed: London, Berlin, Munich, Paris, Amsterdam, Dublin, Bangalore, Hyderabad, Mumbai, Pune, Singapore, Tokyo, Seoul, Shanghai, Beijing, Hong Kong, Sydney, Melbourne, Toronto, Vancouver, Montreal, Mexico City, São Paulo, Tel Aviv, Stockholm, Copenhagen, Zurich, Madrid, Barcelona, Warsaw.
- **Exact regex for non-numeric salary placeholder (D-01a).** Planner picks; suggested `^\s*(competitive|doe|tbd|not disclosed|n/?a|null|—|to be determined|negotiable|depends on experience)\s*$` case-insensitive.
- **Whether to extract salary from PlaywrightAdapter at all.** Anthropic's careers may or may not expose salary. Planner does best-effort during implementation.
- **OUT-09 REQUIREMENTS.md edit format.** Use strike-through markdown plus a parenthetical note pointing to D-04c. Same pattern as Phase 1 INFRA-05 and Phase 2 FILT-04.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-Level Specs

- `.planning/PROJECT.md` — Core value, requirements, constraints. **Note:** PROJECT.md's "Out of Scope" table lists "US-only region filter" as out-of-scope; Phase 4 D-03 reverses that. Planner should NOT remove the line from PROJECT.md's Out of Scope table — leave it for historical clarity. REQUIREMENTS.md is the live source.
- `.planning/REQUIREMENTS.md` — Per-requirement definitions. **Phase 4 mutations:** add FILT-07 to the Filter section; amend OUT-09 to reflect data-persisted-not-rendered per D-04c. INFRA-05 (Phase 1 D-01) and FILT-04 (Phase 2 D-02) already struck through.
- `.planning/ROADMAP.md` — Phase 4 section: goal, mode (`mvp`), 3 original requirement IDs (NORM-02, NORM-03, OUT-09) — planner adds FILT-07.
- `CLAUDE.md` — Project-level constraints; Phase 3 added "Adding a Company" section.

### Phase 1–3 outputs (consumed by Phase 4)

- `.planning/phases/01-walking-skeleton/01-CONTEXT.md` — Phase 1 decisions, especially D-01 (no health.json — Phase 4 D-04 does NOT reverse this; source_health lives inside seen.json, not as a separate file).
- `.planning/phases/02-ats-breadth-jd-scan/02-CONTEXT.md` — Phase 2 patterns; D-02 (filter title-only) sets the precedent for FILT-07 also being a post-title-gate filter.
- `.planning/phases/03-playwright-fallback-credential-workflow/03-CONTEXT.md` — Phase 3 patterns.
- `.planning/phases/01-walking-skeleton/01-0{1,2,3}-SUMMARY.md`, `.planning/phases/02-ats-breadth-jd-scan/02-0{1,2,3}-SUMMARY.md`, `.planning/phases/03-playwright-fallback-credential-workflow/03-0{1,2,3}-SUMMARY.md` — what's been built.
- `src/state_store.py` — atomic write + `.bak` fallback + sanity gate already coded; Phase 4 only adds schema_version bump and source_health key handling.
- `src/normalizer.py` — 7 dispatch helpers; Phase 4 extends each.
- `src/filter.py` — `is_early_career()` title-gate; Phase 4 adds `is_us_location_acceptable()` after.
- `src/renderer.py` — cell-escape + truncate; Phase 4 only changes the salary cell selection logic.

### Research Outputs

- `.planning/research/SUMMARY.md` — Phase 4 description: "Salary patterns, location normalization, source health footer are high-value but late-binding." Note: SUMMARY.md predates the user's "don't render OUT-09 footer" decision; Phase 4 D-04c overrides.
- `.planning/research/PITFALLS.md` — Pitfall 11 (salary regex misclassification) — mitigated by D-01 verbatim approach (no parsing = no misclassification). Pitfall 13 (Markdown escaping) — already handled by Phase 1. Pitfall 20 (N-failure threshold) — incorporated into D-04b consecutive_failures rules. Pitfall 27 (seen.json diff sorting) — already handled by Phase 1's orjson OPT_SORT_KEYS.

### External

- ATS field names for salary — planner verifies against live samples at implementation. Training-data field paths are MEDIUM confidence (per research/SUMMARY.md "Gaps to Address").

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phases 1-3)

- **`src/normalizer.py`** — 7 dispatch helpers (`_extract_greenhouse`, `_extract_lever`, `_extract_ashby`, `_extract_smartrecruiters`, `_extract_workday`, `_extract_apple`, `_extract_playwright`). Phase 4 extends each with: (a) salary extraction from source-specific path, (b) `normalize_location()` call on the location field.
- **`src/filter.py`** — `is_early_career()` (title-only per Phase 2 D-02). Phase 4 adds `is_us_location_acceptable()` as a separate filter pass.
- **`src/state_store.py`** — `load_state()` and `save_state()` already handle atomic write + .bak fallback + sanity gate. Phase 4 only changes the schema_version handling and adds source_health to the serialized blob.
- **`src/state_merger.py`** — `merge_state()` for postings. Phase 4 adds a sibling function `update_source_health()` called once per company after the adapter call.
- **`src/renderer.py`** — `_truncate_cell()` from Phase 1 already truncates at 80 chars with ellipsis. Phase 4 just routes the salary cell through it.
- **`src/main.py`** — orchestrator already has per-company try/except. Phase 4 wraps each call with a `try/except` that classifies the exception type into the source_health status enum.
- **`src/locations.py`** — DOES NOT EXIST YET. New module in Phase 4.

### Established Patterns

- **Filter passes are pure functions, chained in main.py.** Phase 1 set this; Phase 2 extended; Phase 4 adds one more pass (FILT-07).
- **Per-adapter normalizer helpers are pure** — no I/O, no `datetime.now()`, accept `run_started_at` as parameter (RUN-01). Phase 4 maintains this.
- **Schema migrations are forward-compatible read, strict-version write.** Phase 1's STATE-08 set this. Phase 4 demonstrates the pattern.

### Integration Points

- **`src/locations.py` ↔ normalizer:** every `_extract_<adapter>` helper imports `normalize_location` and applies it to the location field before setting `Posting.location`.
- **`src/locations.py` ↔ filter:** `is_us_location` powers FILT-07's `is_us_location_acceptable()`.
- **`src/state_store.py` ↔ orchestrator:** at run start, loader returns the full state dict (postings + source_health). At run end, saver writes both.
- **`src/main.py` ↔ source_health:** orchestrator records per-company outcome immediately after adapter call. Wraps `update_source_health(state, company, outcome, run_started_at)`.

</code_context>

<specifics>
## Specific Ideas

- **`is_us_location()` regex performance:** all state-code and city checks use compiled `re.compile()` at module load. ~60 patterns total — runs <1ms per call.
- **Schema migration test (D-04a):** load a fixture `seen_v1.json` with no `source_health` key; assert loader returns a state dict with `source_health: {}`. Save the loaded state; assert the saved file has `schema_version: 2` and an empty `source_health` block.
- **Source health record (`D-04`) initial population:** when a company is first scraped, its `source_health[company.name]` entry doesn't exist yet. Helper `_ensure_source_health(state, company.name)` creates a default `{last_attempt_utc: None, last_success_utc: None, status: "ok", consecutive_failures: 0}` on first encounter.
- **REQUIREMENTS.md FILT-07 insertion point:** insert as the 7th entry in the Filter section, after FILT-06. Numbering is now consistent (1-7).
- **REQUIREMENTS.md OUT-09 amendment:** strike through the original "footer renders" language; append parenthetical "*— data persisted in `seen.json.source_health`; not rendered in README per [Phase 4 CONTEXT.md D-04c](phases/04-extraction-polish-health-observability/04-CONTEXT.md)*".
- **Test coverage targets:** ~25-30 new tests across salary handling, location normalization, classifier rules, FILT-07 integration, schema migration.

</specifics>

<deferred>
## Deferred Ideas

- **Source Health README footer rendering.** Per D-04c, the data is tracked but not rendered. If user later wants visibility, the footer can be added in a future phase as a 1-task plan — render a small Markdown table from the existing `source_health` block, splice it into a new `<!-- BEGIN HEALTH -->` / `<!-- END HEALTH -->` sentinel pair in the README. No data-store changes needed; just rendering.
- **Salary normalization across currencies.** Out of scope explicitly (D-01c). If currency conversion ever becomes desirable, would need a date-stamped exchange rate table refreshed manually or via a scheduled task; not worth the complexity.
- **Full canonical city library.** D-02b limits normalization to Remote variants only. A "city canonicalization" effort would expand `normalize_location()` to map SF / Bay Area / San Francisco → `San Francisco, CA`. Future polish if visual consistency becomes a pain point.
- **Salary-based sorting / filtering.** No salary filter in v1. If desired later, would require switching from verbatim copy-paste back to extraction. Out of scope for v1.
- **Non-US visibility opt-in.** User explicitly wants US-only. If they later want to see UK/EU postings, a `companies.txt` per-line hint (`#region=non-us`) or a global env var could disable FILT-07. Out of scope for v1.
- **Periodic "deep scan" for accurate `still_listed` on paginated adapters** (carried from Phase 2 deferred). Same status; not a Phase 4 concern.

</deferred>

---

*Phase: 04-extraction-polish-health-observability*
*Context gathered: 2026-06-08*
