# Phase 2: ATS Breadth + JD-Scan - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 expands the adapter layer from "Greenhouse only" to the five major ATS platforms in use across mid-to-large tech employers: **Lever**, **Ashby**, **SmartRecruiters**, **Workday**, **Apple Jobs**. Each adapter implements the existing `Adapter` ABC (from Phase 1's `src/adapters/base.py`), registers itself by appending to `ADAPTERS` in `src/registry.py`, and raises the same typed exception classes (`SiteBlocked` / `SchemaDrift` / generic `Exception`).

The phase also adds the **JD-scan extraction layer** (FILT-03): a regex pass over each posting's description text that pulls out experience requirements (`5+ years`, `0-3 years`, `entry-level`, `recent graduate`) and populates `Posting.experience_min` / `Posting.experience_max`. These numbers feed the README table's `Experience` column.

**What ships at the end of Phase 2:**
- 5 new adapter files under `src/adapters/` — `lever.py`, `ashby.py`, `smartrecruiters.py`, `workday.py`, `apple.py`
- Registry updated to include them (one-line append per adapter, per ADP-14)
- Normalizer extended with per-adapter `_extract_<name>()` dispatch for the 5 new shapes
- JD-scan regex library in `src/filter.py` populating experience fields (without gating row inclusion per D-02)
- Per-adapter happy-path tests + fixture-mutation error-path tests for ALL 6 adapters including Greenhouse (closes Phase 1's D-07 debt)
- Recorded JSON fixtures under `tests/fixtures/` for each new adapter
- README table now shows `Experience` column populated for the majority of postings whose source exposes JD text

**What is NOT in Phase 2:**
- Playwright fallback adapter (Phase 3)
- Credentialed adapters (Phase 3)
- Salary extraction (Phase 4 / NORM-02)
- Location normalization (Phase 4 / NORM-03)
- Source Health footer (Phase 4 / OUT-09)

</domain>

<decisions>
## Implementation Decisions

### Adapter URL → tenant addressing

- **D-01: Workday adapter auto-parses tenant + site from the raw URL.** Users paste the careers-page URL exactly as seen in the browser (e.g., `https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite`). The adapter regex-extracts `tenant=nvidia`, `wd_number=5`, `site=NVIDIAExternalCareerSite`, and constructs the CXS endpoint `https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs`. Matches CFG-01's "paste one URL per line" UX. If the URL doesn't fit the pattern, the adapter raises `SchemaDrift` with a clear message naming what was missing (tenant / wd-number / site), and the orchestrator's per-company isolation (ADP-12) skips that company. **No `#adapter=workday:tenant=...` metadata needed** — the URL is sufficient.
- **D-01a (lock for other adapters):** Lever, Ashby, SmartRecruiters, Apple all follow the same "URL parses to identifier" rule:
  - Lever: `https://jobs.lever.co/<company>` → `company=<company>`. API: `https://api.lever.co/v0/postings/<company>?mode=json`.
  - Ashby: `https://jobs.ashbyhq.com/<org>` → `org=<org>`. API: `https://api.ashbyhq.com/posting-api/job-board/<org>?includeCompensation=true`.
  - SmartRecruiters: `https://careers.smartrecruiters.com/<company>` → `company=<company>`. API: `https://api.smartrecruiters.com/v1/companies/<company>/postings`.
  - Apple: `https://jobs.apple.com/...` → no company segment in URL; adapter calls `POST https://jobs.apple.com/api/role/search` for ALL postings. Each posting in the response carries its own `id`; dedup key is `apple:<id>` (no per-company prefix).

### Filter logic (FILT-03 + FILT-04)

- **D-02: Title wins. JD-scan is informational, not gating.** Phase 2 implements the JD-scan regex extraction described in FILT-03, populating `experience_min` and `experience_max` on every `Posting`. These numbers render in the README's `Experience` column per OUT-05. **They DO NOT gate the row in/out of the table.** A posting with title "Software Engineer, New Grad" and description "5+ years required" stays in the table with `Experience = 5y+` displayed; the user reads the cell and decides themselves.
  - **Impact on FILT-04:** REQUIREMENTS.md FILT-04 says "A posting is kept if (title passes keyword gate) AND (extracted `experience_min ≤ 5` OR no experience range found)." Per D-02, the second clause becomes a no-op — once title passes, JD signal does not affect inclusion. The planner should implement this as: filter function returns kept-or-not based on title only, and a SEPARATE function/pass populates experience fields on every Posting that passed the title gate.
  - **Impact on FILT-05:** FILT-05's "bias toward inclusion when ambiguous" applies only at the title level. Once title is unambiguous (include OR exclude word matched), JD is purely descriptive.
  - **Rationale:** User explicitly prefers more rows + visible experience numbers (so they can skim past mismatches) over auto-dropping based on JD ambiguity. Pitfall 12's "natural language is hostile" risk is mitigated by *showing* the extracted number rather than acting on it.

### Test scope

- **D-03: Fixture-mutation error-path tests for all 6 adapters (closes D-07 debt).** Each adapter ships with these test cases:
  1. Happy path: recorded fixture → adapter produces expected `list[RawPosting]` with correct dedup keys.
  2. `SchemaDrift` on missing top-level key (mutate fixture to delete the postings array).
  3. `SchemaDrift` on wrong type for postings array (mutate to `null` or `{}`).
  4. `SiteBlocked` on HTTP 403 (`respx`-mocked response).
  5. `SiteBlocked` on HTTP 429 (rate-limit, `respx`-mocked).
  6. Generic exception path (e.g., `httpx.NetworkError` propagates up un-caught — orchestrator-level test confirms isolation).
  - Greenhouse retroactively gets these tests too. ~24 new tests across the 6 adapters.
  - **Why retroactive on Greenhouse:** D-07 deferred these in Phase 1 with the explicit plan to do all adapters at once in Phase 2. That's now.

### Workday + Apple pagination strategy

- **D-04: Early-termination by "already-seen" detection. No fixed per-run count cap (only a cold-start safety cap).** The user's insight: with hourly scans, there's no need to fetch *all* pages every time. Once we hit a page whose entries are already in `seen.json`, the rest are older and known — stop.
  - **Algorithm (Workday + Apple — the only paginated adapters in Phase 2):**
    1. Request page 1 sorted **newest first** (DESC by `posted_date` / Workday's `posted` field / Apple's `postingDate`).
    2. Process every posting on the page; assemble `RawPosting` entries.
    3. After the page, check: is the **last posting on this page** already a key in `seen.json` for this company? If yes → stop pagination; return the postings collected so far. If no → fetch the next page.
    4. Repeat steps 2–3 until either (a) early-termination fires, or (b) cold-start safety cap (25 pages) is hit, or (c) the adapter returns an empty page (no more results).
    5. **Sort-monotonicity sanity check:** the adapter tracks the latest `posted_date` seen on each page. If page N+1's first posting is *newer* than page N's last posting, the source ignored `sortBy` — log a warning and fall back to the cold-start cap (25 pages) for this run.
  - **Cold-start safety cap = 25 pages.** First-ever scrape of a new Workday/Apple company has zero `seen.json` entries, so early-termination never fires. The 25-page cap (~500 postings) prevents runaway scrapes on day one. Subsequent runs are bounded by early-termination and typically fetch 1–3 pages.
  - **Does NOT apply to:** Greenhouse, Lever, Ashby, SmartRecruiters — these return the full board in a single response (typically <500 postings) and don't paginate. They fetch one page, process all results.
  - **Edge case — newly-closed postings on Workday/Apple:** if a posting that was previously in `seen.json` is closed by the source between runs, it disappears from the paginated response entirely. Early-termination still works correctly because we check for the last-on-page key in `seen.json` — a closed-and-removed posting simply isn't on the page anymore. Its `seen.json` entry stays untouched with whatever `still_listed` value it last had; the state_merger's pass-2 logic doesn't flip it because we never observed the page that "would have" contained it. **This is acceptable** under STATE-04 ("keys are never deleted") — the user accepts that a closed posting may keep `still_listed=True` until the next page-1-only scrape happens to include it as a comparison point.

### Claude's Discretion

These were not asked because they're implementation details rather than user-visible choices:

- **Apple Jobs request body shape.** The planner should research the current `POST jobs.apple.com/api/role/search` body via a one-time live call or check community fixtures — body shape drifts occasionally per training data. Lock the body in the adapter; document it in a comment. Suggested minimal body: `{"query": "", "locale": "en-us", "page": 0, "pageSize": 20, "sort": {"field": "postingDate", "order": "desc"}, "filters": {}}` — adjust based on what actually works.
- **Per-adapter rate limiting / inter-request sleeps.** Phase 1 has no sleeps. Phase 2 adds 5 more adapters hit per company per hour. The orchestrator's sequential per-company loop already provides natural staggering (~1 company per few seconds). Decide per adapter whether to add `time.sleep(random.uniform(0.5, 1.5))` between pages (Workday/Apple, where multiple pages per company) — likely worth it for Workday. No sleeps between companies; the orchestrator's loop is enough.
- **Test fixture sourcing.** For each new adapter, the planner should hand-craft a minimal synthetic fixture (~3 postings: one new-grad pass, one senior fail, one ambiguous title) and commit it under `tests/fixtures/<adapter>_sample.json`. Recording from live is fragile (response shape varies, timestamps move). Synthetic is fast and deterministic.
- **`updated_at` field naming per adapter.** Lever uses `createdAt` (epoch ms). Ashby uses `publishedAt` (ISO). SmartRecruiters uses `releasedDate` (ISO). Workday uses `postedOn` (epoch ms or ISO depending on version). Apple uses `postingDate` (ISO). Each adapter's normalizer-dispatch helper handles the conversion to UTC ISO 8601.
- **Lever `team` / `categories` field handling.** Lever's response includes department/team metadata that the renderer doesn't currently use. The planner can ignore it for Phase 2 (Posting.location is the only org/location field rendered).
- **REQUIREMENTS.md FILT-04 strikethrough.** Like INFRA-05 in Phase 1, the planner should mark FILT-04 in REQUIREMENTS.md with a strike-through and a reference to CONTEXT.md D-02 ("requirement softened to no-op; experience_min/max now display-only").

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-Level Specs

- `.planning/PROJECT.md` — Core value, requirements (active + out-of-scope), constraints.
- `.planning/REQUIREMENTS.md` — Per-requirement definitions. **Note:** INFRA-05 dropped per Phase 1 D-01; FILT-04 softened per Phase 2 D-02.
- `.planning/ROADMAP.md` — Phase 2 section: goal, mode (`mvp`), depends-on Phase 1, 6 requirement IDs (ADP-04..08 + FILT-03).
- `CLAUDE.md` — Project-level constraints.

### Phase 1 outputs (consumed by Phase 2)

- `.planning/phases/01-walking-skeleton/01-CONTEXT.md` — Phase 1 decisions (especially D-05 "Greenhouse only in Phase 1, others land in Phase 2" — that's NOW).
- `.planning/phases/01-walking-skeleton/01-SKELETON.md` — Architectural manifest of seams built in Phase 1.
- `.planning/phases/01-walking-skeleton/01-01-SUMMARY.md` — Files created in Wave 1 (models, Adapter ABC, Greenhouse adapter, etc.).
- `.planning/phases/01-walking-skeleton/01-02-SUMMARY.md` — Files in Wave 2 (normalizer, filter, state_store, state_merger, renderer, registry).
- `.planning/phases/01-walking-skeleton/01-03-SUMMARY.md` — Files in Wave 3 (config_loader, main.py, end-to-end test).

### Research Outputs

- `.planning/research/SUMMARY.md` — Per-phase deliverables. Phase 2 is "Needs live validation at implementation time" — verify Workday CXS POST body shape and Apple Jobs request shape via a live call before locking adapter contracts (training data is MEDIUM confidence).
- `.planning/research/ARCHITECTURE.md` — `Posting` / `RawPosting` schema, dedup-key format conventions per ATS.
- `.planning/research/STACK.md` — Locked stack; no new dependencies needed for Phase 2 (httpx, pydantic, orjson, respx all already pinned).
- `.planning/research/PITFALLS.md` — Phase 2 must address Pitfalls 5 (stable keys per ATS), 6 (schema assertions), 9 (canonicalization), 10 (UTC dates — Workday epoch-ms quirk), 12 (two-layer experience filter — modified by D-02), 13 (Markdown escaping — already done), 15 (headless detection — N/A for Phase 2's HTTP adapters), 21 (companies.txt robustness — already done).

### External API References

- **Lever:** `https://api.lever.co/v0/postings/<company>?mode=json` — no auth, well-documented.
- **Ashby:** `https://api.ashbyhq.com/posting-api/job-board/<org>?includeCompensation=true` — no auth, public.
- **SmartRecruiters:** `https://api.smartrecruiters.com/v1/companies/<company>/postings` — no auth, public.
- **Workday CXS:** `POST https://<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs` with JSON body `{ "limit": N, "offset": N, "searchText": "", "appliedFacets": {} }`. Response includes `jobPostings: [...]` and `total`. Workday `postedOn` is "Posted Today" / "Posted X Days Ago" relative-string format in some tenants — adapter handles both relative-string + ISO/epoch parsing.
- **Apple Jobs:** `POST https://jobs.apple.com/api/role/search` with JSON body (shape per Claude's Discretion above).

**Planner action item:** Before writing Workday adapter code, fetch a live sample from one known-good tenant (e.g., `nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`) and `apple.com/api/role/search` to confirm current field shapes. Save the response as a fixture. Training-data field names are MEDIUM confidence only.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1)

- **`src/adapters/base.py`** — `Adapter` ABC with `matches(url) -> bool` + `fetch(company) -> list[RawPosting]` + `name: ClassVar[str]`. The 4 typed exceptions (`SiteBlocked`, `SchemaDrift`, `PlaywrightTimeout`, `MissingCredential`) are already defined. New adapters subclass `Adapter` only.
- **`src/registry.py`** — `ADAPTERS: list[type[Adapter]]` — append-only list. `get_adapter(company)` resolution order: explicit `#adapter=` hint → URL-pattern match → `NoAdapterFound`. Adding a Phase 2 adapter is literally one line: `from src.adapters.lever import LeverAdapter` + appending `LeverAdapter` to `ADAPTERS`. ADP-14 / ADP-15 already proven by Phase 1's `test_adapter_contract.py`.
- **`src/normalizer.py`** — Dispatches on `RawPosting.source_adapter` to call the right `_extract_<name>()` helper. Phase 2 adds 5 new dispatch arms (one per new adapter).
- **`src/filter.py`** — Phase 1 ships title-keyword filter only (FILT-01/02/04/05). Phase 2 extends with JD-scan regex (FILT-03). Per D-02, the JD-scan output feeds Posting.experience_min/max but does NOT gate `is_early_career()`.
- **`tests/fixtures/greenhouse_stripe.json`** — Pattern to mirror for the 5 new adapter fixtures: small (~3 postings), covers a pass and an exclude title.
- **`tests/test_adapter_contract.py`** — Existing test for the `Adapter` ABC's open-closed property. Phase 2 doesn't need to modify this; it should *continue to pass* with the 5 new adapters added.

### Established Patterns

- **Dedup-key format per ATS** (already locked):
  - Greenhouse: `gh:<board_token>:<job_id>` (Phase 1 implementation)
  - Lever: `lever:<company>:<uuid>` (Phase 2 — uuid is Lever's posting `id`)
  - Ashby: `ashby:<org>:<uuid>` (Phase 2 — uuid is Ashby's posting `id`)
  - SmartRecruiters: `sr:<company>:<id>` (Phase 2)
  - Workday: `wd:<tenant>:<id>` (Phase 2 — id is Workday's `bulletFields.JOB_REQ_ID` or the URL slug suffix)
  - Apple: `apple:<id>` (Phase 2 — no per-company prefix because Apple is a single org)
- **Per-adapter normalizer helper signature** (already locked):
  - `def _extract_<adapter_name>(raw: dict, source_company: str, run_started_at: datetime) -> Posting`
  - Pure function, no I/O, no `datetime.now()`. Receives `run_started_at` from the orchestrator.
- **Adapter `matches()` hostname check pattern** (already locked):
  - Each adapter checks `urlparse(url).hostname` against a known host substring (e.g., `"jobs.lever.co"`). Cheap, no regex unless needed.
- **`respx` for HTTP mocking** (already locked in Phase 1):
  - All adapter tests use `respx_mock.get(...).mock(return_value=httpx.Response(...))`. No live network calls in tests.

### Integration Points

- **`src/registry.py` ↔ new adapters:** Phase 2's 5 new adapter files each get exactly one import line + one `ADAPTERS` append in registry.py. No other registry changes.
- **`src/normalizer.py` ↔ new adapters:** 5 new `_extract_<name>` private helpers + 5 new dispatch arms in the main normalize function.
- **`src/filter.py` ↔ JD-scan:** New module-level constant `_JD_REGEX_PATTERNS` (list of compiled regexes), new function `extract_experience_range(description: str) -> tuple[int | None, int | None]`. Called by the orchestrator AFTER title filter passes and BEFORE state merge.
- **`tests/fixtures/*.json`** — 5 new fixture files; no live recording (per Claude's Discretion above).

</code_context>

<specifics>
## Specific Ideas

- **Workday URL pattern regex (D-01):** `^https?://(?P<tenant>[a-z0-9-]+)\.wd(?P<wd_num>\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?(?P<site>[A-Za-z0-9_-]+)/?$` — captures tenant, wd-number, site. Two-letter locale prefix (`en-US`) is optional. If regex fails, raise `SchemaDrift` with message `Workday URL did not match expected pattern: <url>`.
- **Workday CXS endpoint construction (D-01):** `https://{tenant}.wd{wd_num}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`. Headers: `Content-Type: application/json`, `Accept: application/json`, `User-Agent: <project realistic UA, NOT default httpx>`.
- **Workday request body (D-04 pagination):** `{ "limit": 20, "offset": <0, 20, 40, ...>, "searchText": "", "appliedFacets": {} }`. Workday's default page size is 20. The 25-page cold-start cap = 500 postings max on first run per Workday company.
- **Apple request body (Claude's Discretion):** Start with `{"query": "", "locale": "en-us", "page": 0, "pageSize": 20, "sort": {"field": "postingDate", "order": "desc"}, "filters": {}}`. Adjust based on live validation. Pagination via `page` increment.
- **JD-scan regex set (D-02 — informational only):**
  - `\b(\d+)\+?\s*(?:to|-|–)?\s*(\d+)?\s*\+?\s*years?\b` — captures `5+ years`, `5-7 years`, `3 to 5 years`.
  - `\b(entry[- ]?level|recent graduate|no experience required|0\s*[-–]\s*\d+\s*years?)\b` — captures unambiguous entry signals (sets `experience_min=0`).
  - Both run; if a numeric range is found, use those bounds. If only an entry signal, set `experience_min=0`, leave `experience_max=None`.
- **Workday `postedOn` parsing:** Workday's response sometimes returns `"Posted Today"`, `"Posted Yesterday"`, `"Posted 3 Days Ago"`, `"Posted 30+ Days Ago"`. Adapter helper `_workday_parse_posted(s, run_started_at)` handles each form and computes UTC ISO. The "30+ Days Ago" case returns `run_started_at - timedelta(days=30)` (lower bound — we know it's *at least* 30 days old). Numeric and ISO forms are also handled in the same helper.
- **REQUIREMENTS.md edits during plan execution:** Strike through INFRA-05 (already done in Phase 1) and FILT-04 (new in Phase 2). Both with footnote pointing to CONTEXT.md.

</specifics>

<deferred>
## Deferred Ideas

- **Manual override files for filter tuning (`included_keywords.txt`, `excluded_keywords.txt`).** SUS-05 in REQUIREMENTS.md v2. Lets the user fine-tune the title-keyword filter without code edits. Not needed in Phase 2 — the keyword lists are already fairly robust and the JD-scan column gives visibility into mistakes.
- **`#adapter=` metadata for non-standard Workday tenants.** D-01 chose raw-URL-only. The `#adapter=workday:tenant=...,site=...` hint mechanism exists in `CompanyConfig.hint` (already supported by Phase 1's `config_loader.py`) — the planner doesn't need to *implement* it; users who have a non-standard tenant URL can use it as an escape hatch via the existing hint slot, with no code changes required. Document this in the README's "Add a Company" section.
- **Pagination for non-paginated ATSes (defensive).** Greenhouse, Lever, Ashby, SmartRecruiters all return full boards in one response. If a tenant ever exceeds the API's hard cap (Greenhouse caps at ~1000), the adapter would silently truncate. Not a real concern for Phase 2 (none of these ATSes are known to have >1000 postings on a single board for the company sizes the user targets). If it ever becomes a problem, add pagination to that adapter in a future phase.
- **Closed-posting `still_listed` accuracy for Workday/Apple under early-termination (D-04 edge case).** Today, a posting that gets closed between hourly runs may keep `still_listed=True` indefinitely until a page-1-only-scrape happens to compare against it. Acceptable per STATE-04 (history > freshness), but if it ever becomes a problem, a periodic "deep scan" (e.g., once a day, ignore early-termination, fetch all pages, mark unfound as `still_listed=False`) could be added in Phase 4 alongside Source Health.
- **LLM-based JD parsing.** Out of scope explicitly per PROJECT.md and FEATURES.md. Don't add it in Phase 2.

</deferred>

---

*Phase: 02-ats-breadth-jd-scan*
*Context gathered: 2026-06-07*
