---
phase: 02
phase_name: ats-breadth-jd-scan
status: human_needed
gates_passed: 4
gates_total: 4
verified_at: 2026-06-08T00:00:00Z
score: 4/4 success criteria verified by automated checks
overrides_applied: 0
human_verification:
  - test: "Add a live Workday tenant URL (e.g. https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite) to companies.txt and wait for the next hourly run"
    expected: "README table updates with wd:nvidia:* dedup keys, all postedOn forms (epoch-ms, ISO, 'Posted Today', 'Posted N Days Ago') render as human-readable Age values, per-company outcome shows ok (not SiteBlocked or schema-drift)"
    why_human: "Workday tenants are per-IP rate-limited from GitHub Actions runners (Pitfall 5). Adapter handles 403/429 -> SiteBlocked correctly, but only a live request confirms the tenant accepts the realistic User-Agent and per-page sleep is sufficient. Synthetic respx fixtures cannot exercise this."
  - test: "Add a live Apple Jobs URL (e.g. https://jobs.apple.com/en-us/search) to companies.txt and wait for the next hourly run"
    expected: "Apple postings appear with apple:<id> dedup keys (no per-company prefix); postingDate ISO values render as Age column entries; no SiteBlocked; request body shape {query, locale, page, pageSize, sort, filters} accepted by current production API"
    why_human: "Per CONTEXT.md Claude's Discretion, Apple's api/role/search body shape 'drifts occasionally per training data'. Verification requires one live call to confirm 2xx response and that searchResults/results shape matches our SchemaDrift guards."
  - test: "Open github.com/DevDesai444/new-grad/README.md after an hourly run with >= 3 distinct ATS URLs in companies.txt (Stripe Greenhouse + Notion Lever + Nvidia Workday)"
    expected: "Markdown table contains postings from all 3 platforms in the same <!-- BEGIN JOBS -->/<!-- END JOBS --> section, sorted by posted_date DESC (OUT-06); Experience column shows Xy-Yy / <=Yy / blank per OUT-05 + D-02"
    why_human: "Visual + cross-source verification on the rendered repo. Goal-backward Truth 1 requires postings from >=3 distinct ATS platforms in the same table — only observable after live multi-source scrape."
  - test: "Add a deliberately-broken Workday URL (e.g. wrong tenant name) alongside >= 1 working URL in companies.txt; run twice"
    expected: "Broken URL produces schema-drift outcome (logged) but working URL's postings still appear in the table; seen.json for the broken company keeps its prior entries unchanged with still_listed preserved (STATE-05)"
    why_human: "ROADMAP success criterion #4 requires verifying that one adapter failing does not abort the run for others, AND that the failing company's prior seen.json entries are preserved. Phase 1 mock-based isolation tests prove the orchestrator contract; live verification proves the contract still holds end-to-end with 6 adapter types across multiple hourly runs."
---

# Phase 2: ATS Breadth + JD-Scan Verification Report

**Phase Goal (ROADMAP.md):** User's `companies.txt` can list any Greenhouse, Lever, Ashby, SmartRecruiters, Workday, or Apple URL and the hourly run scrapes them all, extracting experience range from each posting's description so the Experience column populates.

**Context overrides applied:**
- D-02 (CONTEXT.md): JD-scan is display-only — title gate alone decides inclusion; FILT-04 softened in REQUIREMENTS.md (strike-through). Verifier did NOT flag this softening as a gap.
- D-04 (CONTEXT.md): Workday + Apple use newest-first early-termination pagination with 25-page cold-start cap.

**Verified:** 2026-06-08 UTC
**Status:** human_needed — all 4 ROADMAP success criteria pass automated verification in code; 4 live-service end-to-end smoke checks remain for operational confidence.
**Re-verification:** No — initial verification.

---

## 1. Success Criteria Verification (ROADMAP + D-02/D-04 overrides)

### Truth 1: Multi-ATS coverage with stable dedup keys + no duplicates across re-scans

| Sub-claim | Status | Evidence |
| --- | --- | --- |
| Registry dispatches Greenhouse + Lever + Ashby + SmartRecruiters + Workday + Apple | VERIFIED | `python -c "from src.registry import ADAPTERS; print([c.name for c in ADAPTERS])"` -> `['greenhouse', 'lever', 'ashby', 'smartrecruiters', 'workday', 'apple']`. `len(ADAPTERS) == 6`. |
| Stable dedup keys per adapter (`gh:`, `lever:`, `ashby:`, `sr:`, `wd:`, `apple:`) | VERIFIED | Per-adapter dedup-key emission verified by grep across `src/adapters/*.py`: greenhouse.py `f"gh:{board_token}:{job['id']}"`; lever.py `f"lever:{identifier}:{posting['id']}"`; ashby.py `f"ashby:{identifier}:{job['id']}"`; smartrecruiters.py `f"sr:{identifier}:{posting['id']}"` (locked split with name="smartrecruiters" via dedicated regression test); workday.py `f"wd:{parts.tenant}:{job_id}"`; apple.py `f"apple:{position_id}"` (no per-company prefix per D-01a). |
| Dedup keys are extracted from API response (Pitfall 9 — not from URL) | VERIFIED | All adapters use `job["id"]` / `posting["id"]` / `bulletFields[0]` / `positionId` from the response payload, never `urlparse(url)`. |
| Per-adapter dedup-key assertions covered by tests | VERIFIED | `tests/test_lever_adapter.py` asserts `.startswith("lever:notion:")`; ashby asserts `.startswith("ashby:notion:")`; greenhouse asserts `.startswith("gh:stripe:")`; sr asserts `.startswith("sr:")` AND `not .startswith("smartrecruiters:")`; workday asserts `.startswith("wd:nvidia:")`; apple asserts `.startswith("apple:")` plus a no-per-company-prefix regression test. |
| URL canonicalization strips tracking params (Pitfall 9 — no duplicate keys across URL variants) | VERIFIED | Phase 1's `canonicalize_url` is invoked in every per-adapter normalizer (`src/normalizer.py` lines 167, 213, 254, 309, etc.); dedup key is derived from response ID independent of URL, so tracking-param variants produce the same key. |

**Result: VERIFIED** (4/4 sub-claims for automated code verification; live multi-source render is the corresponding human-verification item #3).

### Truth 2: Workday + Apple date parsing — all forms correct, UTC ISO 8601 internally, Age renders human-readable

| Sub-claim | Status | Evidence |
| --- | --- | --- |
| Workday `_parse_workday_posted` handles 4 forms (epoch ms, ISO-8601, relative "Posted Today/Yesterday/N Days Ago/30+ Days Ago") | VERIFIED | `src/adapters/workday.py` lines 121-156 implement all 4 forms via `_RELATIVE_PATTERNS` tuple + epoch-ms isinstance + `_parse_iso_to_utc` fallback. 7 dedicated tests (`test_parse_postedon_epoch_ms`, `_iso`, `_iso_z_suffix`, `_today`, `_yesterday`, `_n_days_ago`, `_n_plus_days_ago`) all PASS, plus `_unknown_returns_none` for graceful degradation. |
| Apple `postingDate` ISO parsed correctly | VERIFIED | `src/normalizer.py` line 445-446: `posted_raw = raw.get("postingDate") or raw.get("postDateInGMT"); posted_date = _parse_iso_to_utc(posted_raw)`. Coalesces both observed field names. |
| All dates rendered as UTC ISO 8601 internally | VERIFIED | All adapters use `datetime.fromtimestamp(..., tz=UTC)` or `_parse_iso_to_utc()` (which normalizes to UTC). NORM-05 unchanged from Phase 1. |
| Age column renders human-readable via Phase 1's renderer | VERIFIED | Phase 1 renderer's OUT-04 implementation untouched — Phase 2 only feeds it. (Renderer was not modified, by design.) |

**Result: VERIFIED** (4/4 sub-claims).

### Truth 3: Experience column populated (D-02 override: display-only, never gates)

| Sub-claim | Status | Evidence |
| --- | --- | --- |
| `extract_experience_range` exists in `src/filter.py` | VERIFIED | Signature: `(description: str | None) -> tuple[int | None, int | None]`. Lines 113+. |
| Regex covers `X+ years`, `X-Y years`, `entry-level`, `recent graduate` | VERIFIED | Smoke checks pass: `"5+ years"` -> `(5, None)`; `"0-3 years"` -> `(0, 3)`; `"recent graduate"` -> `(0, None)`. 12+ regex-specific tests in `tests/test_filter.py` all pass. |
| ALL 6 normalizer dispatch arms call `extract_experience_range` to populate `experience_min`/`experience_max` | VERIFIED | `grep extract_experience_range src/normalizer.py` shows the call at lines 154 (lever), 199 (ashby), 258 (smartrecruiters), 317 (workday), 359 (greenhouse), 449 (apple). All 6 arms wired. |
| D-02 invariant: `is_early_career` body has zero `experience_min` references (title-only) | VERIFIED | `inspect.getsource(is_early_career)` returns `return _passes_title_gate(posting.title)` only. Docstring explicitly documents D-02 removal of Phase 1's FILT-04 ceiling. |
| Representative test proves D-02: title-pass posting with `experience_min=7` STAYS in table | VERIFIED | `test_is_early_career_ignores_experience_min_per_d02` in `tests/test_filter.py` line 86. Smoke check: `is_early_career(Posting(title="Software Engineer, New Grad", experience_min=7, ...))` returns `True`. |
| FILT-04 strike-through present in REQUIREMENTS.md with D-02 footnote | VERIFIED | `.planning/REQUIREMENTS.md` line 55: `~~**FILT-04**~~` with footnote `[Softened per .planning/phases/02-ats-breadth-jd-scan/02-CONTEXT.md D-02: ...]`. |

**Result: VERIFIED** (6/6 sub-claims). D-02 override applied correctly — verifier did NOT flag the softened FILT-04 as a gap (per `<verification_context>` instruction).

### Truth 4: One adapter failing does NOT abort the run (ADP-12 still holds across 6 adapters)

| Sub-claim | Status | Evidence |
| --- | --- | --- |
| Phase 1's per-company try/except orchestrator wiring is intact | VERIFIED | `src/main.py` lines 71-89: distinct `except` arms for `NoAdapterFound`, `SiteBlocked`, `(SchemaDrift, PlaywrightTimeout, MissingCredential)`, and generic `Exception` — each logs and returns an outcome without propagating. Outcomes recorded per company and aggregated into the summary. |
| All 6 Phase 2 adapters subclass the same `Adapter` ABC | VERIFIED | Smoke check: all 6 ADAPTERS members `issubclass(Adapter)` with `matches`, `fetch`, `name` attributes. `tests/test_adapter_contract.py::test_all_adapters_subclass_base` PASSES with 6 adapters. |
| All 6 adapters raise `SiteBlocked` on 403/429 (Pitfall 5) | VERIFIED | `grep "in (403, 429):" src/adapters/*.py` matches in every adapter (greenhouse, lever, ashby, smartrecruiters, workday, apple). Each raises `SiteBlocked` immediately after. Workday + Apple additionally raise on 5xx. |
| All 6 adapters raise `SchemaDrift` on missing/wrong-typed top-level key (Pitfall 6) | VERIFIED | Each adapter validates `isinstance(payload, ...)` and presence of the expected top-level key (Greenhouse: `jobs`, Lever: list payload, Ashby: `jobs`, SR: `content`, Workday: `jobPostings`, Apple: `searchResults`/`results`) and raises SchemaDrift on violation. Per-adapter D-03 test set covers both missing-key + wrong-type variants (verified across all 6 test files). |
| Orchestrator-level isolation tests pass | VERIFIED | `tests/test_orchestrator.py::test_per_company_isolation_one_raises`, `test_site_blocked_bypasses_sanity_gate`, `test_no_adapter_found_does_not_abort_run` all PASS. The mock-adapter test infra from Phase 1 covers the contract — adding 5 new adapter subclasses does not weaken it. |

**Result: VERIFIED** (5/5 sub-claims for automated code verification; live end-to-end run is the corresponding human-verification item #4).

---

## 2. REQ-ID Coverage Matrix (Phase 2 ownership = 6 REQs)

| REQ | Description | Source Plan | Status | Evidence |
| --- | --- | --- | --- | --- |
| **ADP-04** | Lever adapter — `api.lever.co/v0/postings/<co>?mode=json`, dedup `lever:<co>:<uuid>` | 02-01 | SATISFIED | `src/adapters/lever.py` exists with `LeverAdapter(Adapter)`; emits `lever:<id>:<uuid>` dedup key. `tests/test_lever_adapter.py` 9 tests PASS. Registered in `ADAPTERS`. |
| **ADP-05** | Ashby adapter — `api.ashbyhq.com/posting-api/job-board/<org>`, dedup `ashby:<org>:<uuid>` | 02-01 | SATISFIED | `src/adapters/ashby.py` exists; emits `ashby:<org>:<uuid>`. `tests/test_ashby_adapter.py` 9 tests PASS. Registered. |
| **ADP-06** | SmartRecruiters adapter — `api.smartrecruiters.com/v1/companies/<co>/postings`, dedup `sr:<co>:<id>` | 02-01 | SATISFIED | `src/adapters/smartrecruiters.py` exists; emits `sr:<co>:<id>` (locked SHORT prefix vs. full name "smartrecruiters"). 9 tests PASS including the locked-split regression test. |
| **ADP-07** | Workday adapter — `<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/...`, stable key `wd:<tenant>:<id>`, handles epoch-ms dates, pagination | 02-02 | SATISFIED | `src/adapters/workday.py` (~410 lines). D-01 URL parser, D-04 pagination with 25-page cap + early-termination + sort-monotonicity check, 3-form (4 sub-form) `postedOn` parser, realistic User-Agent (Pitfall 5). 30 tests PASS. |
| **ADP-08** | Apple Jobs adapter — `jobs.apple.com/api/role/search`, stable key `apple:<id>` | 02-03 | SATISFIED | `src/adapters/apple.py`. D-04 pagination same shape as Workday. `apple:<id>` no per-company prefix. 16 tests PASS including `test_apple_dedup_key_has_no_company_prefix`. |
| **FILT-03** | JD-text scan extracts experience range via regex (`X+ years`, `X-Y years`, `entry-level`, `recent graduate`) -> populates `experience_min`/`experience_max` | 02-03 | SATISFIED | `extract_experience_range` in `src/filter.py`; wired into all 6 normalizer arms (`src/normalizer.py`). D-02 enforced: display-only, does NOT gate `is_early_career`. 12+ regex tests PASS. |

**6/6 REQ-IDs satisfied.**

**Orphaned check:** ROADMAP.md Phase 2 declares exactly `[ADP-04, ADP-05, ADP-06, ADP-07, ADP-08, FILT-03]` (6 IDs). Plans' `requirements:` frontmatter collectively cover these 6. Zero orphans.

---

## 3. Pitfall Coverage Matrix

| Pitfall | Concern | Phase 2 Coverage | Status |
| --- | --- | --- | --- |
| **5** | Stable keys per ATS + IP-block surface + realistic User-Agent | All 6 dedup keys formatted per ATS (`gh:`/`lever:`/`ashby:`/`sr:`/`wd:`/`apple:`). All 6 raise SiteBlocked on 403/429. Workday + Apple use realistic `new-grad-tracker/0.1` UA (NOT default httpx). `test_fetch_sends_realistic_user_agent` PASSES. | VERIFIED |
| **6** | Schema assertions on every external response | All 6 adapters validate top-level key presence + isinstance type, raising SchemaDrift on drift. Each adapter ships >= 2 D-03 SchemaDrift tests (missing key + wrong type). | VERIFIED |
| **9** | Canonicalization — extract stable ID from response, NOT URL | All 6 adapters extract IDs from response payload (`job["id"]`, `bulletFields[0]`, `positionId`). `canonicalize_url` invoked on the rendered posting URL but is independent of dedup-key derivation. | VERIFIED |
| **10** | UTC dates + Workday epoch-ms quirk | Workday `_parse_workday_posted` handles epoch-ms (int/float, bool excluded), ISO-8601 (with/without Z suffix), and 4 relative-string forms. Apple uses ISO via `_parse_iso_to_utc`. Lever's epoch-ms `createdAt` divided by 1000 with `tz=UTC`. NORM-05 (all UTC) holds. | VERIFIED |
| **12** | Two-layer experience filter (D-02 override: title-only) | `is_early_career` body is title-only; `experience_min/max` populated for DISPLAY in the Experience column. `test_is_early_career_ignores_experience_min_per_d02` PASSES — proves D-02 invariant. | VERIFIED |
| **13** | Markdown escaping | Inherited from Phase 1 renderer (NORM-07); no Phase 2 regression possible (renderer not modified). | N/A (Phase 1) |
| **17** | Exception messages never leak request headers / response bodies | Each adapter's exception messages include adapter name + company name + observed-shape summary ONLY. Orchestrator logs `type(e).__name__ + str(e)` only (Phase 1 wiring untouched). | VERIFIED |

---

## 4. Quality Gates

| Gate | Command | Result |
| --- | --- | --- |
| Full test suite | `python -m pytest tests/ -q` | **298 passed in 0.77s** |
| Lint clean | `ruff check src/ tests/` | **All checks passed!** |
| Adapter contract holds with 6 adapters | `python -m pytest tests/test_adapter_contract.py -v` | **7 passed** |
| Orchestrator isolation tests | `python -m pytest tests/test_orchestrator.py -v` | **10 passed** |
| Apple + Workday + Filter integration | `python -m pytest tests/test_apple_adapter.py tests/test_workday_adapter.py tests/test_filter.py -v` | **103 passed** |
| Registry has 6 adapter names | `python -c "from src.registry import ADAPTERS; print([c.name for c in ADAPTERS])"` | `['greenhouse', 'lever', 'ashby', 'smartrecruiters', 'workday', 'apple']` |
| Normalizer dispatch has 6 entries | `python -c "from src.normalizer import _DISPATCH; print(sorted(_DISPATCH.keys()))"` | `['apple', 'ashby', 'greenhouse', 'lever', 'smartrecruiters', 'workday']` |

---

## 5. Anti-Pattern Scan (modified Phase 2 files)

| File | TODO/FIXME/Placeholder | Empty Implementations | Hardcoded Empty Data Flowing to Render | Severity |
| --- | --- | --- | --- | --- |
| `src/adapters/lever.py` | none | none | none | clean |
| `src/adapters/ashby.py` | none | none | none | clean |
| `src/adapters/smartrecruiters.py` | none | none | none | clean |
| `src/adapters/workday.py` | none | none | none | clean |
| `src/adapters/apple.py` | none | none | none | clean |
| `src/normalizer.py` | none | none | none (every helper reads source-specific fields) | clean |
| `src/filter.py` | none | none | none | clean |
| `src/registry.py` | none | none | none | clean |

No anti-patterns found.

---

## 6. Gaps Found

**None.** All 4 ROADMAP success criteria are observably true in the codebase by automated checks, all 6 REQ-IDs satisfied, all relevant Pitfalls covered, all 298 tests pass, ruff clean.

The status is `human_needed` (not `passed`) ONLY because the 4 live-service end-to-end smoke checks in section 8 cannot be exercised in CI (would require live Workday + Apple HTTP calls + a real GitHub Actions cron tick). Those are operational rollout confidence checks, not code gaps.

---

## 7. Deferred Items

The following items are NOT gaps — they are explicitly documented as intentional deferrals in the plan frontmatter and CONTEXT.md, with documented graceful degradation in cold-start mode.

| # | Item | Addressed In | Evidence |
| --- | --- | --- | --- |
| 1 | `seen_keys` parameter is wired into `WorkdayAdapter.fetch()` and `AppleAdapter.fetch()` signatures (default `None`) but NOT yet threaded from `src/main.py`. Cold-start cap (25 pages) limits per-run scrape size when `seen_keys` is None — this is the documented Phase 1 contract (`adapter.fetch(company)`) preserved by ADP-14/15 reversibility. | 02-03-PLAN.md `<output>` block: "Plan 02-03 OR a follow-up plan handles that wiring. Until then, the cold-start cap is what limits per-run scrape size; the early-termination optimization is dormant. Behavior is correct in both modes." | `grep "seen_keys" src/main.py` returns 0 hits (intentional). Adapters accept the kw-arg and behave correctly without it. Not a Phase 2 success-criterion blocker. |

---

## 8. Human Verification Required

The 4 automated success criteria are fully verified against the codebase by tests + grep + smoke calls. The following are end-to-end / external-service confirmations that cannot be exercised in CI but become the operational acceptance gate before declaring Phase 2 production-ready:

### 1. Live Workday tenant fetch

**Test:** After deployment, paste a real Workday URL (e.g., `https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`) into `companies.txt` on the public repo and wait for the next hourly run.
**Expected:** README table updates with `wd:nvidia:*` dedup keys, `Posted Today` / epoch-ms / ISO dates all rendered as human-readable Age values. No SiteBlocked. Per-company outcome shows `ok`.
**Why human:** Workday tenants are per-IP rate-limited from GitHub Actions runners (Pitfall 5). Adapter code handles 403/429 -> SiteBlocked correctly, but only a live request confirms the tenant accepts the realistic User-Agent and the per-page sleep is sufficient. Synthetic respx fixtures cannot exercise this.

### 2. Live Apple Jobs fetch

**Test:** Paste an Apple Jobs URL (e.g., `https://jobs.apple.com/en-us/search`) into `companies.txt`.
**Expected:** Apple postings appear with `apple:<id>` dedup keys (no per-company prefix); `postingDate` ISO values render as Age column entries. No SiteBlocked. Per-CONTEXT.md "Claude's Discretion", confirm the request body shape `{"query": "", "locale": "en-us", "page": 0, "pageSize": 20, "sort": {...}, "filters": {}}` works against the current production API.
**Why human:** Apple's `api/role/search` endpoint body shape "drifts occasionally per training data" (CONTEXT.md). Verification requires one live call to confirm 2xx response and `searchResults`/`results` shape match our SchemaDrift guards.

### 3. Multi-ATS table render with >= 3 distinct platforms

**Test:** Open `github.com/DevDesai444/new-grad/blob/main/README.md` after an hourly run with at least 3 different ATS URLs in `companies.txt` (e.g., Stripe Greenhouse + Notion Lever + Nvidia Workday).
**Expected:** Markdown table has postings from all 3 platforms in the same `<!-- BEGIN JOBS -->`/`<!-- END JOBS -->` section, sorted by `posted_date` DESC (OUT-06). Experience column shows `Xy-Yy` / `<=Yy` / blank per OUT-05 + D-02.
**Why human:** Observable in the rendered repo, not in unit tests. ROADMAP Success Criterion 1 requires postings from >=3 distinct ATS platforms in the same table — only observable after live multi-source scrape.

### 4. ADP-12 isolation under real adapter failure across multiple runs

**Test:** Add a deliberately-broken Workday URL (wrong tenant name or 404) to `companies.txt`, alongside >= 1 working URL. Let the cron run twice.
**Expected:** The broken URL produces a per-company outcome (`schema-drift` or `404` log line) but the working URL's postings still appear in the table. `seen.json` for the broken company keeps its prior entries unchanged with `still_listed` preserved (STATE-05) across both runs.
**Why human:** Hourly cron + commit-back loop is the only realistic test for "broken company does not wipe other companies' table rows over multiple runs." Mock-based unit tests prove the orchestrator contract but cannot exercise the full multi-run commit-back behavior.

---

## 9. Final Verdict

**STATUS: human_needed**

**Automated verification:** All 4 ROADMAP Success Criteria PASS against the codebase as written:
1. Multi-ATS coverage — 6 adapters registered with stable per-ATS dedup keys; Pitfall 9 (response-derived IDs) honored.
2. Workday + Apple date parsing — all 4 Workday forms + Apple ISO; UTC ISO 8601 internally.
3. Experience column populated via JD-scan — D-02 override correctly applied (display-only; FILT-04 strike-through honored).
4. ADP-12 per-company isolation intact across all 6 adapters — Phase 1 orchestrator untouched, contract test green.

**Test gates:** 298 tests pass; ruff clean; adapter contract test passes with 6 adapters; orchestrator isolation tests pass.

**REQ coverage:** 6/6 Phase 2 REQ-IDs satisfied (ADP-04, ADP-05, ADP-06, ADP-07, ADP-08, FILT-03). Zero orphans.

**Pitfalls:** Pitfalls 5, 6, 9, 10, 12, 17 all covered. Pitfall 13 inherited from Phase 1 (renderer untouched).

**Overrides honored:** D-02 (FILT-04 softened) and D-04 (early-termination pagination) applied correctly; verifier did NOT flag the softened FILT-04 as a gap.

**Why not `passed`:** Per the Step 9 decision tree, any human-verification items present require status=`human_needed`. The 4 items in section 8 are live-service end-to-end smoke checks for Workday + Apple production endpoints, the cross-source rendered README, and multi-run ADP-12 isolation — none of which CI can exercise. These are operational acceptance gates before Phase 3 work begins to ensure the Phase 2 deployment is healthy.

**No blockers, no implementation gaps. Phase 2 goal achieved in code; awaiting human-driven live-service confirmation.**

---

*Verified: 2026-06-08 UTC*
*Verifier: Claude (gsd-verifier, Opus 4.7 1M)*
