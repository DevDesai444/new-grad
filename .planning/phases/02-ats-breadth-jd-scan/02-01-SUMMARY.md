---
phase: 02-ats-breadth-jd-scan
plan: 01
subsystem: adapters
tags: [adapters, lever, ashby, smartrecruiters, httpx, respx, schema-drift, site-blocked, normalizer, registry, open-closed]

# Dependency graph
requires:
  - phase: 01-walking-skeleton
    provides: Adapter ABC + 4 typed exceptions (src/adapters/base.py), URL-pattern registry (src/registry.py), per-adapter dispatch normalizer (src/normalizer.py with _DISPATCH map + canonicalize_url + _parse_iso_to_utc), canonical models (src/models.py — RawPosting/Posting/CompanyConfig), GreenhouseAdapter reference implementation, respx-based adapter test pattern, contract test (tests/test_adapter_contract.py ADP-14/15)
provides:
  - LeverAdapter (src/adapters/lever.py) — matches jobs.lever.co; fetches api.lever.co/v0/postings/<co>?mode=json; emits lever:<co>:<uuid>
  - AshbyAdapter (src/adapters/ashby.py) — matches jobs.ashbyhq.com; fetches api.ashbyhq.com/posting-api/job-board/<org>?includeCompensation=true; emits ashby:<org>:<uuid>
  - SmartRecruitersAdapter (src/adapters/smartrecruiters.py) — matches careers.smartrecruiters.com; fetches api.smartrecruiters.com/v1/companies/<co>/postings; emits sr:<co>:<id>  (SHORT prefix per D-01a — Adapter.name="smartrecruiters" but dedup prefix="sr:")
  - 3 new normalizer helpers (_normalize_lever / _normalize_ashby / _normalize_smartrecruiters) wired through _DISPATCH
  - 3 new synthetic fixtures under tests/fixtures/{lever,ashby,smartrecruiters}_sample.json (3 postings each: pass + reject + pass-ish)
  - 27 new tests (9 per adapter: 2 matches + happy + stable-dedup-key + 2 SchemaDrift + 2 SiteBlocked + generic propagation)
  - ADP-14/15 open-closed contract re-proven: 0 edits to main.py, models.py, state_store.py, state_merger.py, renderer.py, filter.py, config_loader.py
affects: [02-02-ats-breadth-jd-scan (Workday — same Adapter contract), 02-03-ats-breadth-jd-scan (Apple + JD-scan extension), phase-03 (proves the contract scales before Playwright fallback adds the most-complex adapter)]

# Tech tracking
tech-stack:
  added: []   # no new dependencies — httpx, pydantic, respx all already pinned in Phase 1
  patterns:
    - "Per-adapter file mirrors the greenhouse.py skeleton: matches() hostname check + _extract_identifier() path-segment-0 + fetch() with 403/429/5xx → SiteBlocked, missing/wrong-typed top-level → SchemaDrift, response.json() ValueError → SchemaDrift, generic httpx.HTTPError propagates uncaught"
    - "Dedup key is ALWAYS extracted from the API response (the source-stable ID), NEVER from the URL — Pitfall 5 honored across 3 new adapters"
    - "Adapter stashes `__dedup_key` + `__identifier` in `enriched = dict(raw_posting)` so the normalizer reads them without recomputing"
    - "Per-adapter normalizer helper is a pure function: `_normalize_<name>(rp: RawPosting, run_started_at: datetime) -> Posting` — zero I/O, zero datetime.now()"
    - "9-test-per-adapter D-03 set (2 matches + happy + dedup-key + 2 SchemaDrift + 2 SiteBlocked + generic propagation) — closes part of the D-07 deferred-test debt for the 3 Phase-2-Wave-1 adapters"

key-files:
  created:
    - src/adapters/lever.py
    - src/adapters/ashby.py
    - src/adapters/smartrecruiters.py
    - tests/fixtures/lever_sample.json
    - tests/fixtures/ashby_sample.json
    - tests/fixtures/smartrecruiters_sample.json
    - tests/test_lever_adapter.py
    - tests/test_ashby_adapter.py
    - tests/test_smartrecruiters_adapter.py
  modified:
    - src/normalizer.py        # 3 new private helpers + 3 new _DISPATCH entries (no edits to existing _normalize_greenhouse, canonicalize_url, _parse_iso_to_utc, normalize)
    - src/registry.py          # 3 new imports + 3 new ADAPTERS list entries (no edits to get_adapter, NoAdapterFound, GreenhouseAdapter entry)

key-decisions:
  - "Locked Adapter.name='smartrecruiters' (full) while dedup-key prefix='sr:' (short) per CONTEXT.md D-01a — added the dedicated regression test test_fetch_emits_stable_dedup_key_with_sr_prefix that asserts BOTH `startswith('sr:')` AND `not startswith('smartrecruiters:')` to lock the split into the suite; documented in src/adapters/smartrecruiters.py module docstring."
  - "Lever's top-level response shape is a JSON ARRAY (not a dict) — adapter asserts `isinstance(payload, list)` and raises SchemaDrift with the observed type name on violation; tested with both dict and int payloads."
  - "Ashby normalizer coalesces TWO known location shapes (flat `locationName` string OR nested `{location: {name: ...}}`) — tenants vary; fixture row 1 uses flat form, row 2 uses nested form, exercising both paths."
  - "SmartRecruiters normalizer defensively prefixes `https://` on relative `ref` URLs before canonicalization — protects against an SR contract drift to relative URLs without breaking the absolute path."
  - "Lever posted_date converts epoch-millisecond `createdAt` via `datetime.fromtimestamp(ms/1000.0, tz=UTC)` — guarded against non-numeric / non-positive values returning None gracefully (mirrors `_parse_iso_to_utc` None-on-failure semantics)."
  - "All 3 new adapters reuse the existing `_TIMEOUT_S = 20.0` value from greenhouse.py (locked per ATS-side empirical timeout from Phase 1) — kept identical for runner-budget consistency on GitHub Actions free tier."
  - "Each adapter accepts the `name='notion'` company fixture in tests so identifier extraction works against a single common URL across all 3 tests — confirms the adapters are URL-driven, not company-name-driven."

patterns-established:
  - "Phase 2 Wave 1 vertical-slice template: adapter.py + normalizer helper + _DISPATCH entry + registry import+append + fixture + 9-test module — Wave 2 (Workday) and Wave 3 (Apple) will mirror this template with their own pagination/auth nuances."
  - "D-03 9-test set per adapter is the new minimum bar (was happy-path-only per D-07 in Phase 1); Plan 02-03 will retroactively backfill the same 6 D-03 tests onto greenhouse.py to fully close D-07."

requirements-completed:
  - ADP-04
  - ADP-05
  - ADP-06

metrics:
  duration: ~25min
  completed: 2026-06-08
  tasks: 3
  files_created: 9
  files_modified: 2
  tests_added: 27
  cumulative_tests: 214
---

# Phase 2 Plan 01: Lever + Ashby + SmartRecruiters Adapters Summary

Three vertical ATS slices — Lever, Ashby, SmartRecruiters — added behind the
Phase-1 `Adapter` ABC, each a complete URL-match → HTTP-fetch → schema-validate
→ `RawPosting`-emit → normalize → filter path that lands in the README table
with ZERO edits to `main.py`, `models.py`, `state_store.py`, `state_merger.py`,
`renderer.py`, `filter.py`, or `config_loader.py`. The open-closed contract
(ADP-14/15) is re-proven by `tests/test_adapter_contract.py` continuing to
pass with 4 adapters registered.

## What Shipped

### New Adapters (all `src/adapters/*.py`)

| Adapter | Class | Matches Host | API Endpoint | Dedup Key |
|---------|-------|--------------|--------------|-----------|
| Lever | `LeverAdapter` | `jobs.lever.co` | `https://api.lever.co/v0/postings/<co>?mode=json` | `lever:<co>:<uuid>` |
| Ashby | `AshbyAdapter` | `jobs.ashbyhq.com` | `https://api.ashbyhq.com/posting-api/job-board/<org>?includeCompensation=true` | `ashby:<org>:<uuid>` |
| SmartRecruiters | `SmartRecruitersAdapter` | `careers.smartrecruiters.com` | `https://api.smartrecruiters.com/v1/companies/<co>/postings` | `sr:<co>:<id>` (SHORT prefix; see Decision note below) |

All three subclass `Adapter`, set `name: ClassVar[str]`, implement `matches()` +
`fetch()`, and apply the SAME error ladder as `greenhouse.py`:

- HTTP 403 / 429 → `SiteBlocked`
- HTTP ≥ 500 → `SiteBlocked`
- `response.raise_for_status()` on other 4xx
- `response.json()` raising `ValueError` → `SchemaDrift`
- Missing / wrong-typed top-level payload → `SchemaDrift`
- Per-posting malformed entry (`not isinstance(p, dict) or "id" not in p`) → skipped silently to avoid killing the company

Generic `httpx.HTTPError` (incl. `NetworkError`) is **not** swallowed — it
propagates uncaught so the orchestrator's per-company `except Exception` arm
logs it without leaking request headers (Pitfall 17 / SEC-03).

### Normalizer Extensions (`src/normalizer.py`)

Three new private helpers + three new `_DISPATCH` entries:

```python
_DISPATCH = {
    "greenhouse": _normalize_greenhouse,
    "lever": _normalize_lever,
    "ashby": _normalize_ashby,
    "smartrecruiters": _normalize_smartrecruiters,
}
```

Field shape per adapter (all UTC-normalized, all URL-canonicalized via
`canonicalize_url`):

| Adapter | `title` | `location` | `posted_date` | `posting_url` |
|---------|---------|------------|---------------|---------------|
| Lever | `raw["text"]` | `raw["categories"]["location"]` | `createdAt` (epoch ms) → UTC | `canonicalize_url(raw["hostedUrl"])` |
| Ashby | `raw["title"]` | coalesce `locationName` ∨ `location.name` | `_parse_iso_to_utc(raw["publishedAt"])` | `canonicalize_url(raw["jobUrl"])` |
| SmartRecruiters | `raw["name"]` | compose `city, country` (graceful on missing parts) | `_parse_iso_to_utc(raw["releasedDate"])` | `canonicalize_url(https-prefixed raw["ref"])` |

`experience_min` / `experience_max` are left `None` per plan — FILT-03 JD-scan
extraction lands in Plan 02-03.

### Registry (`src/registry.py`)

Three imports + three list-append entries:

```python
ADAPTERS: list[type[Adapter]] = [
    GreenhouseAdapter,
    LeverAdapter,
    AshbyAdapter,
    SmartRecruitersAdapter,
]
```

`get_adapter`, `NoAdapterFound`, and the hint-resolution logic are
**unchanged** — pure append, ADP-14 open-closed confirmed.

### Tests

| Test Module | Tests | Coverage |
|-------------|-------|----------|
| `tests/test_lever_adapter.py` | 9 | 2 matches + happy + stable-dedup-key + 2 SchemaDrift (dict-instead-of-list, int-instead-of-list) + 2 SiteBlocked (403, 429) + generic propagation |
| `tests/test_ashby_adapter.py` | 9 | 2 matches + happy + stable-dedup-key + 2 SchemaDrift (missing `jobs`, wrong-typed `jobs`) + 2 SiteBlocked + generic propagation |
| `tests/test_smartrecruiters_adapter.py` | 9 | 2 matches + happy + **dedup-key-prefix split regression** + 2 SchemaDrift (missing `content`, wrong-typed `content`) + 2 SiteBlocked + generic propagation |
| **Total new** | **27** | (plan target was ~18; we added 1 extra dedup-key assertion per adapter as a separate test for clarity) |

### Synthetic Fixtures

| Fixture | Shape | Contents |
|---------|-------|----------|
| `tests/fixtures/lever_sample.json` | top-level JSON array (Lever's real shape) | 3 postings: "Software Engineer, New Grad" (pass), "Senior SWE, Infrastructure" (reject) with `?lever-source=careers` for canonicalization, "Associate SWE" (pass) |
| `tests/fixtures/ashby_sample.json` | `{"jobs": [...]}` | 3 postings: row 1 uses flat `locationName`, row 2 uses nested `{"location": {"name": ...}}` + `?utm_source=careers`, row 3 = Junior pass |
| `tests/fixtures/smartrecruiters_sample.json` | `{"totalFound": 3, "content": [...]}` | 3 postings: new-grad pass, Director reject + `?utm_source=careers`, Junior pass |

## Verification Results

```
$ python -m pytest tests/ -q
214 passed in 0.32s    # 187 baseline + 27 new

$ python -c "from src.registry import ADAPTERS; print([c.name for c in ADAPTERS])"
['greenhouse', 'lever', 'ashby', 'smartrecruiters']

$ python -c "from src.normalizer import _DISPATCH; print(sorted(_DISPATCH.keys()))"
['ashby', 'greenhouse', 'lever', 'smartrecruiters']

$ ruff check src/ tests/
All checks passed!

# ADP-15 reversibility — no sibling-adapter imports anywhere in the 3 new files
OK: all new adapters are self-contained (ADP-15)

$ python -m src.main       # smoke run against placeholder companies.txt
... scan complete
exit=0
```

`tests/test_adapter_contract.py` continues to pass with 4 adapters registered —
`test_adapters_subclass_base`, `test_adapters_have_name`, `test_adapter_names_unique`
(no `lever` / `ashby` / `smartrecruiters` collision with `greenhouse`),
`test_greenhouse_adapter_is_self_contained` (greenhouse still imports zero
siblings), `test_registry_dispatches_via_matches_only`,
`test_adapters_list_is_concrete_classes_not_instances`, and
`test_new_adapter_can_be_added_without_touching_existing_files` are all green.

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | `bc05f08` | `feat(02-01): Lever adapter + normalizer dispatch + 9 tests (ADP-04, D-03)` |
| 2 | `3a9308f` | `feat(02-01): Ashby adapter + normalizer dispatch + 9 tests (ADP-05, D-03)` |
| 3 | `f77106c` | `feat(02-01): SmartRecruiters adapter + normalizer dispatch + 9 tests (ADP-06, D-03)` |

## Key Decisions

1. **`Adapter.name="smartrecruiters"` vs dedup-key prefix `"sr:"` is a deliberate split** — `name` is the dispatch identifier used in `_DISPATCH` and `RawPosting.source_adapter`; the prefix is the persistent on-disk format the user sees in `seen.json`. Locked into the test suite via the dedicated `test_fetch_emits_stable_dedup_key_with_sr_prefix` test which asserts BOTH `startswith('sr:')` AND `not startswith('smartrecruiters:')`. Documented in `src/adapters/smartrecruiters.py` module docstring AND in `_normalize_smartrecruiters` docstring.

2. **Each adapter ships 9 tests (1 above the plan's 8 target)** — the dedup-key stability test was split out into its own assertion because the happy-path test already grows long; clearer regression signal when one assertion fails versus the broader happy-path test. The 8-vs-9 difference does not change scope.

3. **Lever's `createdAt` (epoch ms) is gated on `isinstance(created_ms, (int, float)) and created_ms > 0`** — a defensive None-on-bad-input mirroring `_parse_iso_to_utc`'s contract. A SchemaDrift-style assertion would be wrong here because Lever sometimes omits `createdAt` for postings without a published timestamp; `posted_date=None` is the correct render-time outcome.

4. **No new dependencies** — `httpx`, `pydantic`, `respx` are all already pinned in `requirements.lock` from Phase 1. The 3 new adapter modules are pure standard-library + `httpx` + existing project models.

5. **All 3 new adapters reuse `_TIMEOUT_S = 20.0`** — same as `greenhouse.py`. Each adapter defines its own module-level constant for locality (Python's name resolution rules + Pitfall-style code-review symmetry) rather than importing from a shared module. If a future tenant needs a different timeout, the constant can be tuned per-adapter without touching siblings.

## Deviations from Plan

### Auto-fixed Issues

None. The plan was followed exactly as written; all acceptance criteria pass without any Rule-1/2/3 deviations.

### Scope additions (above plan target)

- **9 tests per adapter instead of 8.** Plan said "8 tests total: happy + 5 D-03 + 2 matches() tests"; shipped 9 by splitting `test_fetch_emits_stable_dedup_key` out from `test_fetch_happy_path` for clearer regression signal. Net: 27 new tests vs plan's 24.

### Authentication / blocking gates

None encountered. All 3 ATSes are public unauthenticated APIs; tests use `respx` mocks exclusively (zero network in CI).

### Threat surface scan

No new security-relevant surface beyond what the plan's `<threat_model>` enumerates. All 3 new adapters apply the documented T-02-01-01..T-02-01-06 mitigations (type assertions raise `SchemaDrift`, 403/429/5xx raise `SiteBlocked`, exception messages include only adapter+company+observed-shape — never request headers / response bodies; per-posting malformed entries are skipped). No threat flags raised.

## Known Stubs

None. Every adapter is wired end-to-end into the normalizer + registry; no placeholder
data sources, no hardcoded empties flowing to UI rendering. The orchestrator (`main.py`)
picks up Lever / Ashby / SmartRecruiters URLs from `companies.txt` on the next hourly run
without any further wiring — exactly the open-closed promise of ADP-14/15.

## What's NOT in This Plan (carries forward to Plans 02-02 / 02-03)

- **Workday adapter** (ADP-07) — Plan 02-02, includes D-01 URL parsing (regex extraction of tenant + wd-number + site), D-04 early-termination pagination, three-form `postedOn` parsing (relative-string + epoch-ms + ISO).
- **Apple adapter** (ADP-08) — Plan 02-03, includes `POST jobs.apple.com/api/role/search` with TBD body shape (Claude's-Discretion item — verify live before locking).
- **JD-scan extraction** (FILT-03) — Plan 02-03, regex library populating `experience_min` / `experience_max` per posting; D-02 makes this display-only (does NOT gate row inclusion).
- **Retroactive Greenhouse D-03 tests** — Plan 02-03, closes the rest of the D-07 debt by backfilling the same 9-test set on `greenhouse.py`.
- **REQUIREMENTS.md FILT-04 strikethrough** — Plan 02-03 per CONTEXT.md D-02.

## Self-Check

- [x] `src/adapters/lever.py` exists (FOUND)
- [x] `src/adapters/ashby.py` exists (FOUND)
- [x] `src/adapters/smartrecruiters.py` exists (FOUND)
- [x] `tests/fixtures/lever_sample.json` exists (FOUND, 3 postings, top-level list)
- [x] `tests/fixtures/ashby_sample.json` exists (FOUND, 3 postings in `jobs` array)
- [x] `tests/fixtures/smartrecruiters_sample.json` exists (FOUND, 3 postings in `content` array)
- [x] `tests/test_lever_adapter.py` exists (FOUND, 9 tests, all pass)
- [x] `tests/test_ashby_adapter.py` exists (FOUND, 9 tests, all pass)
- [x] `tests/test_smartrecruiters_adapter.py` exists (FOUND, 9 tests, all pass)
- [x] Commit `bc05f08` exists in git log (FOUND)
- [x] Commit `3a9308f` exists in git log (FOUND)
- [x] Commit `f77106c` exists in git log (FOUND)
- [x] `python -m pytest tests/ -q` → 214 passed (187 baseline + 27 new)
- [x] `ruff check src/ tests/` → All checks passed
- [x] `from src.registry import ADAPTERS; len(ADAPTERS) == 4` ✓ (greenhouse, lever, ashby, smartrecruiters)
- [x] `from src.normalizer import _DISPATCH; set(_DISPATCH.keys()) == {"greenhouse", "lever", "ashby", "smartrecruiters"}` ✓
- [x] `python -m src.main` against placeholder companies.txt exits 0
- [x] No edits to `main.py`, `models.py`, `state_store.py`, `state_merger.py`, `renderer.py`, `filter.py`, `config_loader.py` (verified by inspection of commits — only `src/normalizer.py` and `src/registry.py` modified, plus new files)
- [x] `tests/test_adapter_contract.py` continues to pass with 4 adapters registered

## Self-Check: PASSED
