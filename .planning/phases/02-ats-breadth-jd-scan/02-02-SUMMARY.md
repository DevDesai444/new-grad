---
phase: 02-ats-breadth-jd-scan
plan: 02
subsystem: workday-adapter
tags: [adapters, workday, pagination, epoch-ms, posted-relative, schema-drift, site-blocked, early-termination, sort-monotonicity, user-agent, rate-limit]

# Dependency graph
requires:
  - phase: 01-walking-skeleton
    provides: Adapter ABC + typed exceptions (src/adapters/base.py — SiteBlocked / SchemaDrift), URL-pattern registry (src/registry.py — ADAPTERS list + get_adapter), per-adapter dispatch normalizer (src/normalizer.py — _DISPATCH + canonicalize_url + _parse_iso_to_utc), canonical models (src/models.py — RawPosting/Posting/CompanyConfig), respx-based adapter test pattern, contract test (tests/test_adapter_contract.py ADP-14/15)
  - phase: 02-ats-breadth-jd-scan
    provides: 4-adapter open-closed pattern from Plan 02-01 (LeverAdapter / AshbyAdapter / SmartRecruitersAdapter + their normalizer dispatch entries + the 9-test-per-adapter D-03 template); adapter file SELF-CONTAINMENT discipline (no sibling imports)
provides:
  - WorkdayAdapter (src/adapters/workday.py) — matches *.wd*.myworkdayjobs.com hosts via subdomain regex; auto-parses (tenant, wd-number, site) from raw URL per D-01 (no metadata hint needed); POSTs to CXS jobs endpoint with realistic User-Agent (Pitfall 5 mitigation); emits dedup keys wd:<tenant>:<JOB_REQ_ID>
  - 3-form postedOn resolver (_parse_workday_posted) — epoch milliseconds, ISO-8601, relative strings ("Posted Today" / "Posted Yesterday" / "Posted N Days Ago" / "Posted N+ Days Ago" with N+ as LOWER bound); unknown forms return None gracefully
  - D-04 pagination wrapper on fetch() — empty-page break, short-page break, seen_keys early-termination, 25-page cold-start hard cap, sort-monotonicity sanity check that logs a warning + suppresses early-termination for the rest of the run when a tenant ignores sort ordering, 0.5-1.5s random inter-page sleep (monkeypatched to noop in slow tests)
  - _normalize_workday helper in src/normalizer.py + _DISPATCH["workday"] entry — reads the adapter-stashed __posted_date_utc (defensively reparses ISO string fallback); experience_min/max left None pending Plan 02-03 JD-scan
  - WorkdayAdapter imported + appended to ADAPTERS in src/registry.py (ADP-14 open-closed pattern; registry now holds 5 adapters)
  - tests/fixtures/workday_sample.json — synthetic 5-posting CXS response covering all 4 postedOn forms (epoch ms / ISO / Posted Today / Posted 3 Days Ago / Posted 30+ Days Ago)
  - tests/test_workday_adapter.py — 35 tests (Task 1: 25 covering URL parser + matches + happy path + dedup-key shape + 8 postedOn parser cases + 6 D-03 error paths + realistic-UA assertion; Task 2: +10 covering pagination empty-page / seen_keys early-term / 25-page cap / short-page / sort-monotonicity warning / normalizer round-trip + missing date + ISO-string fallback / registry membership + dispatch)
  - ADP-14/15 open-closed contract re-proven with 5 adapters: 0 edits to main.py / models.py / state_store.py / state_merger.py / renderer.py / filter.py / config_loader.py / src/adapters/{base,greenhouse,lever,ashby,smartrecruiters}.py
affects:
  - 02-03-ats-breadth-jd-scan (Apple adapter + JD-scan — same Adapter contract; Apple inherits the D-04 pagination pattern; JD-scan extends all 5 normalizers including _normalize_workday)
  - phase-03 (proves the contract scales with 5 adapters before Playwright fallback adds the most-complex adapter type)

# Tech tracking
tech-stack:
  added: []  # no new dependencies — httpx, pydantic, respx already pinned from Phase 1
  patterns:
    - "Workday adapter mirrors the greenhouse.py/lever.py error ladder (403/429/5xx -> SiteBlocked; missing or wrong-typed top-level key -> SchemaDrift; response.json() ValueError -> SchemaDrift; httpx.HTTPError propagates uncaught) but adds two Workday-specific layers: (a) realistic User-Agent constant required at the request-headers level per Pitfall 5, (b) multi-form postedOn resolver because Workday tenants drift between epoch-ms / ISO / relative-string formats per CONTEXT.md <specifics>"
    - "URL parsing is module-level: a compiled regex (_WORKDAY_URL_RE) + a typed NamedTuple (WorkdayURLParts) + a helper (_parse_workday_url) that raises SchemaDrift with a PARTIAL-MATCH DIAGNOSTIC — the SchemaDrift message names WHICH piece is missing (host vs site) so the user can fix the URL without log-diving"
    - "Pagination is a vertical wrapper around the existing single-page fetch helper (_fetch_page_and_emit) — Task 1 shipped the helper standalone, Task 2 wrapped it. This kept the diff small and the per-page error-ladder reusable, and means a future change to either layer (e.g., adding HTTP-2 to the page-level POST or changing the cap algorithm) edits exactly one site"
    - "Sort-monotonicity sanity check is OBSERVABLE (logger.warning at WARNING level) AND non-fatal — when a Workday tenant ignores sortBy, the adapter continues paginating, just degrades to the cold-start cap. Tests assert the warning fires via caplog without coupling to internal state flags"
    - "Inter-page sleep is PRODUCTION-REAL (0.5-1.5s jitter via random.uniform) but tests monkeypatch src.adapters.workday.time.sleep to noop — production keeps the rate-limit hedge, test suite runs in milliseconds (test_fetch_cold_start_cap_25_pages would otherwise add ~25 seconds of wall-clock)"
    - "Dedup key fallback chain: prefer bulletFields[0] (JOB_REQ_ID = Workday's stable internal ID), fall back to the last URL slug of externalPath, skip the posting entirely if neither yields an ID — same one-bad-posting-doesn't-kill-the-company discipline as greenhouse.py"

key-files:
  created:
    - src/adapters/workday.py
    - tests/fixtures/workday_sample.json
    - tests/test_workday_adapter.py
  modified:
    - src/normalizer.py    # +_normalize_workday helper + _DISPATCH["workday"] entry (no edits to existing entries)
    - src/registry.py      # +WorkdayAdapter import + ADAPTERS append (no edits to get_adapter, NoAdapterFound, or existing entries)

key-decisions:
  - "Combined URL parser + single-page fetch + postedOn resolver into Task 1; Task 2 added only the pagination wrapper + normalizer + registry — kept Task 1 self-contained (you could check it out at HEAD~1 and it would have 25 passing tests, a working adapter for single-page tenants, and a cleanly extensible fetch() signature). This deliberately accepted Task 1 not being wired through the normalizer/registry until Task 2 so the diff and risk per commit stays small."
  - "WorkdayAdapter.matches() uses subdomain-pattern check (host.endswith(.myworkdayjobs.com) and .wd in host) instead of importing/re-running _WORKDAY_URL_RE — cheap substring check, no regex compile cost on every URL lookup, matches() contract per ADP-01 is 'should be cheap, no I/O'."
  - "_parse_workday_url emits diagnostic SchemaDrift messages naming WHICH piece is missing (host vs site) via a partial-match probe regex — defensive UX: the user fixing a typo in companies.txt sees `Workday URL did not match expected pattern (tenant + wd-number parsed but site segment is missing or malformed): ...` not just `Workday URL did not match`."
  - "fetch() accepts seen_keys: set[str] | None = None as an optional kwarg — Phase 1 Adapter.fetch contract is single-arg, so a default of None preserves backwards compatibility. When orchestrator (main.py — out of scope for this plan) starts threading seen.json keys through, early-termination engages automatically. Until then, cold-start cap is the limiter: behavior is correct in BOTH modes (cold-start = always fetch up to 25 pages; with seen_keys = fetch until last-on-page is known, typically 1-3 pages in steady state)."
  - "Inter-page sleep uses random.uniform(0.5, 1.5) — jitter is intentional (deterministic sleep makes rate-limit detection trivial for hostile tenants). Production keeps it; tests monkeypatch src.adapters.workday.time.sleep to noop so the 25-page-cap test runs in <100ms instead of ~25 seconds."
  - "Sort-monotonicity violation does NOT abort the page or the run — it logs a warning AND suppresses early-termination for the remainder of this run (degrades to cap-only). Worst case is wasted requests up to the 25-page cap; best case is still correct postings collected. Tradeoff favors completeness over speed when sort ordering is broken."
  - "_parse_workday_posted accepts None / empty string / unknown form and returns None — does NOT raise. Same contract as _parse_iso_to_utc; renderer falls back to first_seen for Age column. SchemaDrift is for the WIRE response shape (missing jobPostings), not per-posting field-level malformations."
  - "Workday CXS jobs endpoint does NOT return per-posting description text — so _normalize_workday leaves experience_min/max = None unconditionally. JD-scan (FILT-03, Plan 02-03) will need to make a separate per-posting fetch if it wants Workday descriptions; that's an extension, not a regression."
  - "Defensive bool exclusion in _parse_workday_posted: `isinstance(value, (int, float)) and not isinstance(value, bool)` because Python bool is a subclass of int (True == 1) and a JSON `true` value should not be treated as epoch millisecond 1ms — return None instead."
  - "Sort-monotonicity test uses string postedOn forms (`Posted Today` / `Posted 5 Days Ago`) rather than absolute timestamps because the relative-form parser anchors to run_started_at — same instant for both pages in the same fetch() call, so the test result is independent of the wall-clock moment the test runs."

patterns-established:
  - "Multi-form date-field resolver pattern: when a wire field can arrive in N forms across tenant versions, wrap parsing in a single pure helper that returns datetime|None and never raises. Apple's `postingDate` (Plan 02-03) can mirror this pattern."
  - "Stash-then-read normalizer pattern reused: adapter computes anything expensive/source-specific (URL construction, dedup key fallback chain, multi-form date resolution) and stashes results in raw[__*] keys; normalizer reads the keys without re-computing. Decouples adapter and normalizer concerns; same pattern as greenhouse/lever/ashby/smartrecruiters."
  - "Pagination contract for non-trivially-paginated adapters: adapter.fetch(company, seen_keys=None) is the locked signature. seen_keys is documented as the early-termination signal but defaults to None so the adapter still works under the Phase 1 single-arg Adapter.fetch contract. Apple (Plan 02-03) follows the same signature."
  - "Realistic User-Agent constant per adapter: anti-bot-vendor sites (Workday, Apple, Cloudflare-fronted careers pages) block the default python-httpx UA. Module-level _USER_AGENT = `new-grad-tracker/0.1 (+https://github.com/DevDesai444/new-grad)` is the project standard going forward — Apple adapter should adopt the same constant approach."

requirements-completed:
  - ADP-07

# Metrics
duration: ~25min
completed: 2026-06-08
tasks: 2
files_created: 3
files_modified: 2
tests_added: 35
cumulative_tests: 249
---

# Phase 2 Plan 02: Workday Adapter Summary

**WorkdayAdapter ships ADP-07 fully — D-01 URL auto-parse without metadata hints, D-04 paginated fetch with early-termination + 25-page cold-start cap + sort-monotonicity sanity check, 3-form postedOn resolver (epoch ms / ISO / relative strings), realistic User-Agent (Pitfall 5), and normalizer + registry wiring — added behind the Phase 1 Adapter ABC with ZERO edits to main.py, models.py, state_store.py, state_merger.py, renderer.py, filter.py, config_loader.py, or any sibling adapter file. ADP-14/15 open-closed contract re-proven with 5 adapters.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-08T00:10:00Z (approx)
- **Completed:** 2026-06-08T00:35:00Z (approx)
- **Tasks:** 2 (Task 1: URL parser + single-page fetch + postedOn resolver + D-03 tests; Task 2: pagination + sort-monotonicity + normalizer + registry)
- **Files created:** 3 (src/adapters/workday.py, tests/fixtures/workday_sample.json, tests/test_workday_adapter.py)
- **Files modified:** 2 (src/normalizer.py, src/registry.py)
- **Tests added:** 35 (25 in Task 1 + 10 in Task 2)
- **Cumulative tests:** 249 (214 baseline + 35)

## Accomplishments

- **D-01 URL auto-parse** — `_parse_workday_url` regex-extracts (tenant, wd_num, site) from raw careers URLs with and without the optional `en-US/` locale segment; raises diagnostic `SchemaDrift` naming WHICH piece is missing (host vs site) when the regex fails.
- **D-04 pagination** — `fetch(company, seen_keys=None)` paginates the CXS endpoint with four termination paths: empty page, short page (< 20), `seen_keys` overlap on last-of-page, and the 25-page cold-start hard cap. Sort-monotonicity sanity check logs a warning and suppresses early-termination for the remainder of the run when a tenant ignores sort ordering. 0.5-1.5s random inter-page sleep in production; monkeypatched to noop in slow tests.
- **3-form postedOn resolver** — `_parse_workday_posted(value, run_started_at)` handles epoch milliseconds (int/float, with bool exclusion), ISO-8601 strings (with `Z` suffix), and the four relative-string forms (`Posted Today` / `Posted Yesterday` / `Posted N Days Ago` / `Posted N+ Days Ago` with `N+` as LOWER bound). Unknown forms return `None` gracefully — the renderer falls back to `first_seen` for the Age column.
- **Realistic User-Agent** — `_USER_AGENT = "new-grad-tracker/0.1 (+https://github.com/DevDesai444/new-grad)"` is the single most effective Pitfall 5 mitigation against Workday's well-known blocking of `python-httpx/...` defaults; covered by `test_fetch_sends_realistic_user_agent`.
- **5-adapter registry** — `WorkdayAdapter` imported and appended to `ADAPTERS`; `_DISPATCH["workday"]` wired in normalizer. `tests/test_adapter_contract.py` continues to pass with all 5 adapters registered.

## What Shipped

### New Adapter (src/adapters/workday.py)

| Component | Purpose |
|-----------|---------|
| `_WORKDAY_URL_RE` | Compiled D-01 regex with named groups (tenant, wd_num, site) and optional locale segment |
| `WorkdayURLParts` | Typed NamedTuple holding the parsed segments |
| `_parse_workday_url(url)` | Returns `WorkdayURLParts`; raises `SchemaDrift` with partial-match diagnostic on failure |
| `_RELATIVE_PATTERNS` | Module-level table mapping each relative-string regex to its date-arithmetic lambda |
| `_parse_workday_posted(value, run_started_at)` | Pure function returning `datetime \| None` across all 3 wire forms |
| `WorkdayAdapter.matches(url)` | Subdomain-pattern check: `host.endswith(".myworkdayjobs.com") and ".wd" in host` |
| `WorkdayAdapter.fetch(company, seen_keys=None)` | D-04 paginated wrapper — early-term + 25-page cap + sort-monotonicity check |
| `WorkdayAdapter._fetch_page_and_emit(...)` | Per-page POST + error-ladder + RawPosting emission with `__dedup_key` / `__tenant` / `__posting_url` / `__posted_date_utc` stashed |

Error ladder (mirrors greenhouse.py / lever.py exactly):
- HTTP 403 / 429 → `SiteBlocked`
- HTTP ≥ 500 → `SiteBlocked`
- `response.raise_for_status()` on other 4xx
- `response.json()` `ValueError` → `SchemaDrift`
- Missing or wrong-typed `jobPostings` key → `SchemaDrift`
- Per-posting `not isinstance(job, dict)` or missing dedup id → skipped silently

Per Pitfall 17 / SEC-03, all exception messages include adapter name + company name + observed-shape summary ONLY — never response body, never request headers.

### Normalizer Extension (src/normalizer.py)

`_normalize_workday(rp, run_started_at)` reads:

| Posting field | Source in `raw` |
|---------------|-----------------|
| `dedup_key` | `raw["__dedup_key"]` (stashed by adapter) |
| `title` | `raw["title"]` |
| `location` | `raw["locationsText"]` |
| `posting_url` | `canonicalize_url(raw["__posting_url"])` (already tenant-prefixed) |
| `posted_date` | `raw["__posted_date_utc"]` — defensively reparses ISO string if a JSON round-trip turned the datetime into a string |
| `experience_min` / `max` | `None` (Workday CXS doesn't return descriptions; JD-scan lands in Plan 02-03) |

`_DISPATCH` now: `{"greenhouse", "lever", "ashby", "smartrecruiters", "workday"}`.

### Registry (src/registry.py)

Single import + single list-append entry:

```python
from src.adapters.workday import WorkdayAdapter

ADAPTERS: list[type[Adapter]] = [
    GreenhouseAdapter,
    LeverAdapter,
    AshbyAdapter,
    SmartRecruitersAdapter,
    WorkdayAdapter,
]
```

`get_adapter`, `NoAdapterFound`, and all existing entries unchanged — ADP-14 open-closed confirmed.

### Tests (tests/test_workday_adapter.py — 35 tests)

| Group | Tests |
|-------|-------|
| `matches()` | 2 (positive: Workday host; negative: Lever host) |
| URL parser (D-01) | 6 (happy with locale, happy without, trailing slash, microsoft.wd1, malformed no host, malformed no site) |
| Single-page happy path | 2 (5 RawPostings emitted; dedup keys use `wd:nvidia:` prefix) |
| `_parse_workday_posted` | 8 (epoch ms, ISO with offset, ISO with Z suffix, Today, Yesterday, N Days Ago, N+ Days Ago, unknown returns None — includes bool exclusion) |
| Error paths (D-03) | 6 (missing `jobPostings`, wrong-typed `jobPostings`, 403, 429, generic `httpx.NetworkError`, malformed URL via `fetch()`) |
| Headers (Pitfall 5) | 1 (realistic UA + Content-Type + Accept assertion) |
| **Task 2: Pagination (D-04)** | 4 (empty-page break, `seen_keys` early-term, 25-page cap with 30 mocked pages, short-page break) |
| **Task 2: Sort-monotonicity** | 1 (warning logged + all postings still collected) |
| **Task 2: Normalizer dispatch** | 3 (round-trip with all fields, `__posted_date_utc=None` yields `posted_date=None`, ISO string defensive reparse) |
| **Task 2: Registry contract** | 2 (membership in `ADAPTERS`, `get_adapter()` returns `WorkdayAdapter` instance) |
| **Total** | **35** |

### Synthetic Fixture (tests/fixtures/workday_sample.json)

5 postings covering all 4 `postedOn` forms:

| Row | Title | `postedOn` Form |
|-----|-------|-----------------|
| 1 | Software Engineer, New Grad | epoch ms (1748707200000) |
| 2 | Senior Staff Engineer, Infrastructure | ISO-8601 string |
| 3 | Associate Software Engineer | "Posted Today" |
| 4 | Junior Data Scientist | "Posted 3 Days Ago" |
| 5 | Principal Engineer, Compilers | "Posted 30+ Days Ago" (LOWER bound) |

## Task Commits

Each task was committed atomically:

1. **Task 1: URL parser + single-page fetch + postedOn resolver + D-03 tests** — `ff6172a` (feat)
2. **Task 2: Pagination + sort-monotonicity + normalizer + registry** — `9d22e62` (feat)

## Files Created/Modified

- `src/adapters/workday.py` (created, ~290 lines) — full WorkdayAdapter + helpers
- `tests/fixtures/workday_sample.json` (created, 5 postings) — synthetic CXS response
- `tests/test_workday_adapter.py` (created, 35 tests) — all adapter tests
- `src/normalizer.py` (modified, +50 lines) — `_normalize_workday` + `_DISPATCH` entry
- `src/registry.py` (modified, +2 lines) — `WorkdayAdapter` import + ADAPTERS append

## Decisions Made

See `key-decisions` in frontmatter for the full list. Highlights:

1. **Task 1 ships standalone-functional even before Task 2's pagination wrap** — single-page tenants would work at the HEAD of Task 1; the diff stays small per commit. Task 2's wrapper is purely additive.
2. **`fetch()` accepts `seen_keys` as an optional kwarg with default `None`** — preserves Phase 1's single-arg `Adapter.fetch` contract; behavior degrades gracefully to cold-start-cap-only when the orchestrator hasn't been wired to thread `seen_keys` through (which it hasn't yet — see "What's NOT in This Plan" below).
3. **Sort-monotonicity is non-fatal** — logs WARNING + suppresses further early-term, never aborts the page or the run.
4. **`_parse_workday_posted` excludes `bool` from the epoch-ms branch** — `isinstance(True, int) is True` in Python; treating `true` as epoch ms 1 would silently produce 1970-01-01 datetimes. Returns `None` instead.
5. **`time.sleep` is monkeypatched in slow tests** — `src.adapters.workday.time.sleep -> lambda s: None` keeps `test_fetch_cold_start_cap_25_pages` under 100ms instead of ~25 seconds; production keeps the real sleep for rate-limit hedging.

## Deviations from Plan

None auto-fixed (no Rule 1/2/3 deviations).

### Scope additions (above plan target)

- **35 tests vs plan's "≥ 14"** — Plan said "≥ 14 new tests" (the prompt also called out "~14" as the rough budget). Shipped 35 because: (a) the postedOn parser ships 8 tests vs the plan's example "7" since `Z`-suffix ISO and bool exclusion both deserved dedicated regression assertions, (b) URL parser ships 6 tests vs the plan's 5 (added `microsoft.wd1` happy path from the prompt's "examples that should match" set to lock the wd-number variability), (c) Task 2 added 4 dedicated tests for normalizer dispatch + registry contract that the plan implied but didn't enumerate. Net: 35 new tests vs plan's ~14 baseline — no scope creep, all tests defend documented behavior.
- **Task 1 ships 25 tests instead of "≥ 15"** — same reason: more granular test split (each `postedOn` form is its own test, each malformed-URL case is its own test) gives clearer regression signal when one assertion fails.

### Authentication / blocking gates

None encountered. The Workday CXS endpoint is public unauthenticated; all tests use `respx` mocks exclusively (zero network in CI).

### Threat surface scan

No new security-relevant surface beyond what the plan's `<threat_model>` enumerates. All 11 T-02-02-* threats are mitigated as documented:

- T-02-02-01 (schema drift): missing/wrong-typed `jobPostings` -> SchemaDrift (2 dedicated tests)
- T-02-02-02 (postedOn per-tenant variants): all 3 forms handled; unknown -> None (8 dedicated tests)
- T-02-02-03 (Workday IP block): realistic UA + 403/429/5xx -> SiteBlocked + inter-page sleep (3 dedicated tests)
- T-02-02-04 (unbounded pagination): _COLD_START_CAP_PAGES = 25 hard ceiling (test_fetch_cold_start_cap_25_pages asserts exactly 25 requests + 500 postings)
- T-02-02-05 (sort-monotonicity by tenant): warning + suppress early-term (test_fetch_sort_monotonicity_violation_logs_warning)
- T-02-02-06 (header leak): exception messages include only adapter+company+observed-shape — never response body, never request headers
- T-02-02-07 (one-bad-posting): `if not isinstance(job, dict): continue` + dedup-id fallback chain; skip silently rather than aborting
- T-02-02-08/09/10 (repudiation/EoP/spoofing): N/A (no transactions, no auth, public unauthenticated API)
- T-02-02-11 (wall-clock budget): inter-page sleep accepted tradeoff vs T-02-02-03

No threat flags raised.

## Known Stubs

None. WorkdayAdapter is wired end-to-end into the normalizer + registry; no placeholder data sources, no hardcoded empties flowing to UI rendering. The orchestrator (`main.py`) picks up Workday URLs from `companies.txt` on the next hourly run without any further wiring — exactly the open-closed promise of ADP-14/15.

The one caveat (already documented in the plan and decision log, not a stub):

- **`fetch()` accepts `seen_keys` but the orchestrator does NOT yet thread it** — without `seen_keys`, pagination runs to the 25-page cold-start cap every run (correct behavior, just less efficient on tenants with > 25 pages worth of postings). Threading `seen_keys` from `main.py` is scoped to Plan 02-03 OR a Phase 2 follow-up. The behavior degrades gracefully — the table stays correct, just at the cost of more requests per run when a tenant has a large board.

## Issues Encountered

None. The plan was followed as written; both tasks committed cleanly on first verification.

## User Setup Required

None. The Workday CXS endpoint is public and unauthenticated; no secrets, no env vars, no dashboard config required.

## Next Phase Readiness

Plan 02-02 closes ADP-07. Next plan is **02-03 — Apple adapter + JD-scan + retroactive Greenhouse D-03 tests** which:

- Adds `AppleAdapter` mirroring Workday's `seen_keys` pagination pattern (POST `jobs.apple.com/api/role/search`).
- Adds JD-scan regex library to `src/filter.py` populating `experience_min`/`experience_max` across all 5 adapter normalizers (Workday-specific gotcha: CXS doesn't return descriptions, so JD-scan needs an alternate strategy for Workday — most likely deferral).
- Backfills the 9-test D-03 set onto `greenhouse.py` to close the rest of D-07 debt.
- Strikes through FILT-04 in REQUIREMENTS.md per CONTEXT.md D-02.

After Plan 02-03, Phase 2 is execute-complete. No blockers; the 5-adapter contract works.

---

## Verification Results

```
$ source .venv/bin/activate && python -m pytest tests/ -q
249 passed in 0.52s    # 214 baseline + 35 new

$ python -c "from src.registry import ADAPTERS; print([c.name for c in ADAPTERS])"
['greenhouse', 'lever', 'ashby', 'smartrecruiters', 'workday']

$ python -c "from src.normalizer import _DISPATCH; print(sorted(_DISPATCH.keys()))"
['ashby', 'greenhouse', 'lever', 'smartrecruiters', 'workday']

$ ruff check src/ tests/
All checks passed!

$ python -m src.main       # smoke run against placeholder companies.txt
... scan complete
exit=0

$ grep "from src.adapters." src/adapters/workday.py
from src.adapters.base import Adapter, SchemaDrift, SiteBlocked
# OK: workday.py is self-contained per ADP-15 (only imports from base, not from siblings)

$ python -c "from src.adapters.workday import _parse_workday_url; p = _parse_workday_url('https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite'); assert p == ('nvidia', '5', 'NVIDIAExternalCareerSite'); print('OK D-01')"
OK D-01

$ python -c "from src.adapters.workday import _COLD_START_CAP_PAGES; assert _COLD_START_CAP_PAGES == 25; print('OK D-04 cap')"
OK D-04 cap
```

`tests/test_adapter_contract.py` continues to pass with 5 adapters registered — `test_all_adapters_subclass_base`, `test_all_adapters_have_name`, `test_adapter_names_unique` (no `workday` collision with any sibling), `test_greenhouse_adapter_is_self_contained` (greenhouse still imports zero siblings), `test_registry_dispatches_via_matches_only`, `test_adapters_list_is_concrete_classes_not_instances`, and `test_new_adapter_can_be_added_without_touching_existing_files` are all green.

## Self-Check

- [x] `src/adapters/workday.py` exists (FOUND)
- [x] `tests/fixtures/workday_sample.json` exists (FOUND, 5 postings, all 4 postedOn forms)
- [x] `tests/test_workday_adapter.py` exists (FOUND, 35 tests, all pass)
- [x] Commit `ff6172a` exists in git log (Task 1 — FOUND)
- [x] Commit `9d22e62` exists in git log (Task 2 — FOUND)
- [x] `python -m pytest tests/ -q` → 249 passed (214 baseline + 35 new)
- [x] `ruff check src/ tests/` → All checks passed
- [x] `from src.registry import ADAPTERS; len(ADAPTERS) == 5` ✓ (greenhouse, lever, ashby, smartrecruiters, workday)
- [x] `from src.normalizer import _DISPATCH; set(_DISPATCH.keys()) == {"greenhouse", "lever", "ashby", "smartrecruiters", "workday"}` ✓
- [x] `python -m src.main` against placeholder companies.txt exits 0
- [x] No edits to `main.py`, `models.py`, `state_store.py`, `state_merger.py`, `renderer.py`, `filter.py`, `config_loader.py`, or any sibling adapter file (verified by inspection of commits — only `src/normalizer.py` and `src/registry.py` modified, plus new files)
- [x] `tests/test_adapter_contract.py` continues to pass with 5 adapters registered
- [x] `_USER_AGENT` constant contains "new-grad" (Pitfall 5 mitigation — `test_fetch_sends_realistic_user_agent` asserts outgoing UA header at request-time)
- [x] `_COLD_START_CAP_PAGES = 25` is a module-level constant exported in `__all__`
- [x] `_parse_workday_url` raises `SchemaDrift` with a partial-match diagnostic message
- [x] `fetch(company, seen_keys=None)` signature accepts the early-termination kwarg
- [x] `sort-monotonicity` text present in `src/adapters/workday.py` (D-04 sanity check)
- [x] At least one pagination test monkeypatches `src.adapters.workday.time.sleep` (verified: 5 matches in test file)

## Self-Check: PASSED

---
*Phase: 02-ats-breadth-jd-scan*
*Plan 02-02 complete: 2026-06-08 — Workday adapter (ADP-07); 249 cumulative tests; ADP-14/15 open-closed re-proven with 5 adapters.*
