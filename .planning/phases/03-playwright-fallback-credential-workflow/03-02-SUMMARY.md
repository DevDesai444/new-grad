---
phase: 03-playwright-fallback-credential-workflow
plan: 02
subsystem: playwright-catch-all-adapter
tags: [adapter, playwright, chromium, stealth, xhr-intercept, dom-fallback, anthropic, catch-all, registry, normalizer, adp-09, adp-10]
requirements: [ADP-09, ADP-10]
requires:
  - src/adapters/base.py Adapter ABC + PlaywrightTimeout (Phase 1)
  - src/models.py CompanyConfig with hint + resolved_url (Phase 1 + 03-01)
  - src/normalizer.py with 6 ATS dispatch entries (Phase 1 + 2)
  - src/registry.py ADAPTERS list (Phase 1 + 2 + 03-01)
  - playwright==1.60.0 + playwright-stealth==2.0.3 + selectolax==0.4.10 (locked)
  - Plan 03-01 deliverables (CompanyConfig.resolved_url + workflow Chromium install)
provides:
  - src/adapters/playwright_fallback.PlaywrightAdapter — catch-all subclass:
    name='playwright'; matches() returns True for any http(s) URL;
    XHR-intercept-first via page.expect_response (predicate matches /api/
    paths containing jobs/openings/positions/careers/roles keywords);
    DOM-selector fallback via page.wait_for_selector + selectolax HTMLParser
    against 6 common card selectors; stealth on by default (D-04) with
    per-site opt-out; 60s navigation timeout (D-05) with per-site override;
    trace='off' in production with SCRAPER_DEBUG_TRACE=1 escape hatch (D-06);
    dedup keys `pw:<host>:<id>` with sha256(url)[:16] fallback (Pitfall 9);
    raises PlaywrightTimeout when both extraction paths fail.
  - src/normalizer._normalize_playwright + _read_playwright_description +
    'playwright' entry in _DISPATCH — handles generic XHR/DOM raw shape,
    coalesces postingDate/postedAt/created_at/publishedAt date keys, wires
    FILT-03 JD-scan from description text.
  - src/registry.ADAPTERS now ends with PlaywrightAdapter (catch-all LAST
    per CONTEXT.md D-01c — all 6 ATS adapters' specific matches() fire first).
  - Test seam: PlaywrightAdapter.fetch accepts documented optional
    `_test_route_handler` kwarg for tests to inject context.route() mocks.
affects:
  - Plan 03-03 (credential workflow) — extends PlaywrightAdapter with
    SCRAPER_<COMPANY>_<KIND> env-var reads + InvalidCredential typed exception.
  - All future "Adding a Company" flows — any http(s) URL is now scrapable
    out of the box; new ATS adapters STILL go into their own module per
    ADP-14/15 (Playwright catch-all is the safety net, not the destination).
tech-stack:
  added: []  # all deps locked in Phase 1; Chromium installed by Plan 03-01 workflow step
  patterns:
    - "XHR-intercept-first + DOM-fallback dual-path for SPA scraping"
    - "Indirect import hook (_get_stealth_class) for test monkeypatching"
    - "Test-observable no-op hook (_record_trace_started) for invisible state changes"
    - "Documented test seam kwarg (_test_route_handler) for browser-context mock injection"
    - "Defensive XHR payload coalescing across {jobs|openings|positions|postings|results|data}: [...]"
    - "Selectolax for fast HTML extraction in DOM fallback path"
key-files:
  created:
    - src/adapters/playwright_fallback.py
    - tests/test_playwright_adapter.py
    - tests/fixtures/anthropic_sample.json
    - tests/fixtures/anthropic_sample.html
  modified:
    - src/normalizer.py
    - src/registry.py
    - tests/test_normalizer.py
    - tests/test_registry.py
    - tests/test_adapter_contract.py
decisions:
  - "Wrapped Stealth import in _get_stealth_class() indirection — tests monkeypatch this to record calls; production no-op cost"
  - "Added _record_trace_started() no-op hook for test-observable trace-policy assertions without inspecting Playwright internals"
  - "Documented _test_route_handler kwarg on .fetch() as the test seam — mirrors Phase 2 seen_keys precedent"
  - "Removed pytest.mark.slow decorators (unused marker generated PytestUnknownMarkWarning; tests run ~40s total — fine in CI ungated)"
  - "Rewrote 2 Phase 1 NoAdapterFound tests as PlaywrightAdapter dispatch tests (D-01c invalidates the unknown-URL→error contract for http(s) URLs)"
  - "Updated test_new_adapter_can_be_added to INSERT before catch-all at len-1 (preserves both open-closed proof + catch-all-last invariant)"
  - "src/filter.py NOT modified — _read_playwright_description belongs in normalizer.py alongside 6 sibling helpers; plan frontmatter listed filter.py defensively"
metrics:
  duration_minutes: 25
  tasks: 2
  files_created: 4
  files_modified: 5
  tests_added: 32  # 22 adapter + 5 normalizer + 5 registry
  cumulative_tests: 348
  completed: 2026-06-08
---

# Phase 03 Plan 02: PlaywrightAdapter (XHR + DOM Catch-All) Summary

**One-liner:** Wave 2 ships the Playwright catch-all adapter — XHR-intercept-first (via `page.expect_response`) with DOM-selector fallback (via `wait_for_selector` + selectolax), `playwright-stealth` on by default, 60s navigation timeout, `trace='off'` in production with `SCRAPER_DEBUG_TRACE=1` escape hatch, `pw:<host>:<id>` dedup keys (sha256-of-url fallback) — appended LAST in `ADAPTERS` so all 6 ATS adapters' specific `matches()` get first crack. Anthropic careers (`https://www.anthropic.com/careers`) now dispatches cleanly without needing a dedicated adapter.

## What Shipped

### 1. `src/adapters/playwright_fallback.py` (NEW)

`PlaywrightAdapter(Adapter)` with `name='playwright'`. Module-level constants:

- `_DEFAULT_TIMEOUT_S = 60.0` (D-05)
- `_VIEWPORT = {"width": 1920, "height": 1080}` (current desktop standard)
- `_USER_AGENT` (Chrome 126.0.0.0 on macOS — refresh annually)
- `_DEBUG_TRACE_ENV = "SCRAPER_DEBUG_TRACE"` (D-06 env-var name)
- `_TRACE_DIR = ".playwright-trace"` (gitignored per Plan 03-01)
- `_XHR_KEYWORDS = ("jobs", "openings", "positions", "careers", "roles")` — URL keyword predicate for response interception
- `_DOM_SELECTORS` — 6 common card selectors tried in order, first match wins

**Strategy** per CONTEXT.md D-01a:

1. **XHR-intercept FIRST** via `page.expect_response(predicate)` — captures the JSON job-data call (any `/api/...` response containing one of the keyword fragments) with HTTP 200. Parses via `response.json()` and routes through `_parse_xhr_payload` which coalesces 6 common payload shapes (`{jobs:[..]}`, `{openings:[..]}`, `{positions:[..]}`, `{postings:[..]}`, `{results:[..]}`, `{data:[..]}`, or bare `[..]`) into a list of dicts.

2. **DOM-selector fallback** when XHR predicate doesn't fire — `page.wait_for_selector(sel)` against `_DOM_SELECTORS` in order with per-selector budget of `timeout_ms / len(selectors)`. First match wins; HTML parsed via `selectolax.HTMLParser.css(selector)` extracting title (h3/h2/.job-title/.title), location (.location/[data-testid='location']), and `<a href>` (resolved via `urljoin(base_url, href)`).

3. **Both paths fail → raise `PlaywrightTimeout`** (Phase 1 typed exception) with a sanitized message containing only adapter name + company + URL + timeout-seconds. No headers, no body, no traceback.

**Hint metadata parsing** (D-04 / D-05):

```python
_parse_hint_kwargs("playwright")                              -> {}
_parse_hint_kwargs("playwright:stealth=false")                -> {"stealth": "false"}
_parse_hint_kwargs("playwright:timeout_s=30")                 -> {"timeout_s": "30"}
_parse_hint_kwargs("playwright:stealth=false,timeout_s=30")   -> {"stealth": "false", "timeout_s": "30"}
```

`stealth_enabled = hint_kw.get("stealth", "true").lower() != "false"` — stealth defaults ON.
`timeout_s = float(hint_kw.get("timeout_s", 60.0))` — 60s default with safe-cast fallback.

**Stealth integration** (D-04 — playwright-stealth 2.x API):

```python
from playwright_stealth import Stealth
Stealth().apply_stealth_sync(context)
```

Wrapped in a `_get_stealth_class()` indirection so tests can monkeypatch without touching Playwright internals. Production: zero-cost lazy import.

**Trace policy** (D-06):

```python
trace_enabled = os.environ.get("SCRAPER_DEBUG_TRACE") == "1"
if trace_enabled:
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    _record_trace_started()  # test-observable hook
# ... in finally:
if trace_enabled:
    os.makedirs(".playwright-trace", exist_ok=True)
    context.tracing.stop(path=f".playwright-trace/{host}.zip")
```

Workflow YAML does NOT set `SCRAPER_DEBUG_TRACE` — verified by `python -c "import os; assert 'SCRAPER_DEBUG_TRACE' not in open('.github/workflows/scan.yml').read()"`. Trace files are gitignored.

**Dedup key format** (`pw:<host>:<id>`) per Pitfall 9:

```python
def _id_from_posting(posting: dict, posting_url: str) -> str:
    for k in ("id", "jobId", "positionId", "postingId", "uuid"):
        v = posting.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return hashlib.sha256(posting_url.encode("utf-8")).hexdigest()[:16]
```

NEVER raw URL. Stable XHR ID wins when present; sha256 prefix is a stable per-URL fallback so re-scrapes converge on the same key.

**Test seam:** `fetch(..., _test_route_handler: Callable | None = None)` — when not None, called with the `BrowserContext` BEFORE any navigation so tests can install `context.route(...)` mocks. Documented as TEST-ONLY; production callers never pass it. Mirrors Phase 2's `seen_keys` precedent.

### 2. `src/normalizer.py` (APPEND-ONLY)

Added two helpers + one dispatch entry:

```python
def _read_playwright_description(raw: dict) -> str:
    return raw.get("description") or ""


def _normalize_playwright(rp: RawPosting, run_started_at: datetime) -> Posting:
    raw = rp.raw
    dedup_key = raw["__dedup_key"]
    title = (raw.get("title") or "").strip()
    location = (raw.get("location") or "").strip()
    posting_url = canonicalize_url(raw.get("posting_url") or "")
    posted_raw = (
        raw.get("postingDate") or raw.get("postedAt")
        or raw.get("created_at") or raw.get("publishedAt")
    )
    posted_date = _parse_iso_to_utc(posted_raw)
    exp_min, exp_max = extract_experience_range(_read_playwright_description(raw))
    # ... Posting(...) construction mirrors the 6 sibling normalizers ...


_DISPATCH = {
    "greenhouse": _normalize_greenhouse,
    "lever": _normalize_lever,
    "ashby": _normalize_ashby,
    "smartrecruiters": _normalize_smartrecruiters,
    "workday": _normalize_workday,
    "apple": _normalize_apple,
    "playwright": _normalize_playwright,  # Phase 3 Plan 03-02 — catch-all SPA
}
```

Date-key coalesce covers the 4 most common SPA conventions; URL canonicalization (NORM-06) strips utm_*, gh_src, lever-source, ref, ref_src. JD-scan output (`experience_min`, `experience_max`) is display-only per D-02 — never gates inclusion.

### 3. `src/registry.py` (APPEND-ONLY)

```python
from src.adapters.playwright_fallback import PlaywrightAdapter

ADAPTERS: list[type[Adapter]] = [
    GreenhouseAdapter,
    LeverAdapter,
    AshbyAdapter,
    SmartRecruitersAdapter,
    WorkdayAdapter,
    AppleAdapter,
    PlaywrightAdapter,  # CATCH-ALL — must stay last per CONTEXT.md D-01c
]
```

`NoAdapterFound` docstring updated to note that the catch-all eliminates the http(s)-URL error path. The exception remains defined for the (now-unreachable except via malformed input) non-http scheme case.

### 4. Test fixtures (NEW)

- `tests/fixtures/anthropic_sample.json` — 4-posting XHR shape: 1 new-grad pass (`0-3 years`), 1 entry-signal (`Recent graduate`), 1 senior fail (`10+ years`), 1 ambiguous (empty description).
- `tests/fixtures/anthropic_sample.html` — 3-card DOM shape using `[data-testid='job-card']` selector pattern.

### 5. Tests (NEW + APPEND)

`tests/test_playwright_adapter.py` (NEW — 22 tests):

| Block | Count | Coverage |
|-------|-------|----------|
| matches() catch-all | 3 | http://, https://, non-http (ftp:// + javascript:) |
| _parse_hint_kwargs | 5 | None, bare, stealth=false, timeout_s, both |
| _id_from_posting | 3 | id field, alternate keys (jobId/positionId/postingId/uuid), sha256 fallback |
| XHR happy path | 1 | route mocks /api/jobs; 4 RawPostings; key shape `pw:<host>:<id>` |
| Dedup-key id win | 1 | XHR id `j-100` appears in key, not hash |
| Dedup-key sha256 fallback | 1 | No id field → 16-char hex prefix |
| DOM fallback | 1 | XHR absent; HTML served; 3 cards parsed |
| PlaywrightTimeout | 1 | Blank page; both paths fail; raises within timeout |
| Stealth on by default (D-04) | 1 | _SentinelStealth records call; default ON |
| Stealth opt-out (D-04) | 1 | `#adapter=playwright:stealth=false` → not called |
| Trace off by default (D-06) | 1 | SCRAPER_DEBUG_TRACE unset → tracing.start not invoked |
| Trace retain-on-failure (D-06) | 1 | SCRAPER_DEBUG_TRACE=1 → tracing.start invoked |
| Catch-all-last invariant | 1 | `ADAPTERS[-1].name == 'playwright'` |
| Default timeout sentinel (D-05) | 1 | `_DEFAULT_TIMEOUT_S == 60.0` |

`tests/test_normalizer.py` (+5):

- `test_normalize_playwright_xhr_path_with_id` — full XHR shape → Posting; JD-scan `0-3 years` → (0, 3); company capitalized
- `test_normalize_playwright_dom_path_no_description` — DOM shape, no description → (None, None) experience; missing date → None
- `test_normalize_playwright_handles_missing_posted_date`
- `test_normalize_playwright_handles_alternate_date_keys` — `postedAt` parsed
- `test_normalize_playwright_canonicalizes_url` — utm_* + fragment stripped; `keep=yes` preserved

`tests/test_registry.py` (+5):

- `test_playwright_adapter_is_last_in_list` — D-01c invariant
- `test_playwright_dispatches_only_when_no_other_matches` — anthropic.com → PlaywrightAdapter
- `test_greenhouse_url_still_dispatches_to_greenhouse_not_playwright` — specific wins over catch-all
- `test_workday_resolved_url_still_dispatches_to_workday_not_playwright` — CNAME→Workday still wins
- `test_no_adapter_found_eliminated_by_catch_all` — random unknown http URL → PlaywrightAdapter

`tests/test_registry.py` — 2 Phase 1 NoAdapterFound assertions REWRITTEN as PlaywrightAdapter dispatch assertions:

- `test_unknown_url_raises` → `test_unknown_http_url_dispatches_to_playwright_catch_all`
- `test_unrecognized_hint_no_url_match_raises` → `test_unrecognized_hint_no_url_match_dispatches_to_playwright`

`tests/test_adapter_contract.py` (1 line semantic change):

- `test_new_adapter_can_be_added_without_touching_existing_files` — `reg.ADAPTERS.append(_SyntheticAdapter)` → `reg.ADAPTERS.insert(len(reg.ADAPTERS) - 1, _SyntheticAdapter)`. Preserves both invariants: open-closed proof + catch-all is still last in iteration order.

## Test Delta (+32 net, 316 → 348)

| File | Δ | Notes |
|------|---|-------|
| `tests/test_playwright_adapter.py` NEW | +22 | full coverage table above |
| `tests/test_normalizer.py` | +5 | playwright normalizer dispatch tests |
| `tests/test_registry.py` | +5 new, 2 rewritten | catch-all dispatch + 2 Phase 1 NoAdapterFound tests rewritten |
| `tests/test_adapter_contract.py` | 0 (1 line semantic update) | INSERT-before-catch-all preserves open-closed proof |

Full suite: **348 passing** (316 baseline + 32 net new).

## Commits

| Task | Commit | Files |
|------|--------|-------|
| 1 | 7202dc0 | src/adapters/playwright_fallback.py (new), tests/fixtures/anthropic_sample.{json,html} (new), tests/test_playwright_adapter.py (new) |
| 2 | ac6f40f | src/registry.py, src/normalizer.py, tests/test_normalizer.py, tests/test_registry.py, tests/test_adapter_contract.py |

## Manual Sanity

```bash
$ .venv/bin/python -c "from src.registry import ADAPTERS; assert ADAPTERS[-1].name == 'playwright' and len(ADAPTERS) == 7; print('OK')"
OK

$ .venv/bin/python -c "from src.registry import get_adapter; from src.models import CompanyConfig; c = CompanyConfig(name='anthropic', url='https://www.anthropic.com/careers'); print(type(get_adapter(c)).__name__)"
PlaywrightAdapter

$ .venv/bin/python -c "from src.registry import get_adapter; from src.models import CompanyConfig; c = CompanyConfig(name='stripe', url='https://boards.greenhouse.io/stripe'); print(type(get_adapter(c)).__name__)"
GreenhouseAdapter

$ .venv/bin/python -c "import os; assert 'SCRAPER_DEBUG_TRACE' not in open('.github/workflows/scan.yml').read(); print('D-06 enforced')"
D-06 enforced
```

## Threat Model Posture

All 10 STRIDE entries from `03-02-PLAN.md` addressed:

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-03-02-01 (trace file leak) | mitigate | D-06 — production `trace='off'`; SCRAPER_DEBUG_TRACE=1 escape hatch never set in workflow YAML; `.playwright-trace/` gitignored |
| T-03-02-02 (header leak in exceptions) | mitigate | `grep -c 'traceback.format_exc' src/adapters/playwright_fallback.py == 0`; messages include only adapter + company + URL + timeout-seconds |
| T-03-02-03 (UA impersonation) | accept | Standard scraper practice; documented in adapter docstring |
| T-03-02-04 (anti-bot detection) | mitigate | D-04 — playwright-stealth ON by default; 1920x1080 viewport |
| T-03-02-05 (hung page DoS) | mitigate | D-05 — 60s timeout on navigation + expect_response + wait_for_selector; workflow timeout-minutes: 50 is upper cap |
| T-03-02-06 (Chromium memory leak across companies) | mitigate | `with sync_playwright()` + `try/finally: browser.close()`; serial execution per Phase 1 orchestrator pattern |
| T-03-02-07 (malicious XHR payload) | mitigate | `_parse_xhr_payload` only accepts dict items in lists; downstream pydantic Posting validation catches type drift; title-gate filter (FILT-01/02) rejects bogus titles |
| T-03-02-08 (mass-posting flood) | accept | Phase 1 STATE-06 sanity gate catches mass-additions in merge step |
| T-03-02-09 (browser exploit via malicious page) | accept | GitHub Actions sandbox; runner is throw-away; Plan 03-01's cache invalidation on Playwright version bump keeps us current |
| T-03-02-10 (extraction-path log) | accept | Diagnostic only — `playwright:%s extracted %d postings via %s path` |

## SEC-03 Enforcement (Structural)

```bash
$ grep -c 'traceback.format_exc' src/adapters/playwright_fallback.py
0
```

Mirrors Phase 1 + 2 + Plan 03-01 discipline. Exception messages contain only:

- Adapter name (`Playwright`)
- Company name (`company.name`)
- Sanitized URL (`target_url`)
- Timeout seconds

Never headers, never response body, never `_test_route_handler` reference, never trace file paths.

## ADP-14 / ADP-15 Open-Closed Re-Proof (5th time)

```bash
$ git diff 7202dc0^..ac6f40f -- src/adapters/greenhouse.py src/adapters/lever.py src/adapters/ashby.py src/adapters/smartrecruiters.py src/adapters/workday.py src/adapters/apple.py
(empty)
```

The catch-all addition required zero edits to any of the 6 existing adapter files. `tests/test_adapter_contract.py` (7 cases) continues to pass — `test_greenhouse_adapter_is_self_contained` confirms `greenhouse.py` does not import from `playwright_fallback.py` (the forbidden-imports list at line 53 already included `from src.adapters.playwright_fallback` defensively per Phase 1 planning).

## Deviations from Plan

### 1. Removed `pytest.mark.slow` markers

The plan body suggested marking Playwright runtime tests as `slow` to gate them under a custom marker. Implementation initially added 9 such decorators; pytest emitted `PytestUnknownMarkWarning` for each because the marker isn't registered in `pyproject.toml` and no CI step gates on it. Removed the decorators — tests run in ~40s total which is acceptable ungated. If a future need arises to skip them locally, registering the marker in `[tool.pytest.ini_options]` is a one-liner.

### 2. `src/filter.py` NOT modified despite being in `files_modified` frontmatter

Plan frontmatter `files_modified` listed `src/filter.py` defensively in case `_read_playwright_description` belonged there. After reading the Phase 2 codebase carefully (per the plan body's explicit decision check in Task 2 Step 2), the per-adapter `_read_<adapter>_description` helpers all live in `src/normalizer.py` alongside the 6 sibling normalizers, NOT in `src/filter.py`. Plan body / Task 2 action block correctly steers to normalizer.py. Zero filter.py edits; commit message documents the divergence. **Net effect:** plan frontmatter is mildly inaccurate but plan body is correct and was followed.

### 3. Rewrote 2 Phase 1 NoAdapterFound tests as PlaywrightAdapter dispatch tests

Phase 1 had `test_unknown_url_raises` and `test_unrecognized_hint_no_url_match_raises` — both asserted `NoAdapterFound` for arbitrary unknown URLs. CONTEXT.md D-01c (the whole point of the Playwright catch-all) is that this NoAdapterFound contract no longer holds for http(s) URLs. Renamed and inverted both:

- `test_unknown_url_raises` → `test_unknown_http_url_dispatches_to_playwright_catch_all`
- `test_unrecognized_hint_no_url_match_raises` → `test_unrecognized_hint_no_url_match_dispatches_to_playwright`

Same precedent as Plan 02-03's `test_experience_min_above_ceiling_overrides_title_pass` → `test_is_early_career_ignores_experience_min_per_d02` rewrite (preserve the test slot, invert the assertion, document the CONTEXT.md decision driving the change).

### 4. Updated `test_new_adapter_can_be_added_without_touching_existing_files` to insert before catch-all

The synthetic-adapter open-closed proof originally appended `_SyntheticAdapter` to `ADAPTERS`. With PlaywrightAdapter as catch-all at index `-1`, appending puts synthetic at index `-1` and Playwright at `-2` — but loop iteration order means Playwright now matches `https://synthetic.example/jobs` FIRST. Switched `.append()` → `.insert(len(reg.ADAPTERS) - 1, ...)` to insert just before the catch-all. Preserves both invariants: open-closed proof + catch-all still last.

### 5. Added `_get_stealth_class()` + `_record_trace_started()` test-observable hooks

Plan body's Task 1 mentioned monkeypatching the Stealth class directly. In practice, monkeypatching `playwright_stealth.Stealth` proved fragile (import order matters; the production import inside `fetch()` may have already bound to the real class). Cleaner pattern: wrap the import in an indirection (`_get_stealth_class() -> Stealth`) so tests monkeypatch the indirection, not the source. Same pattern for trace activation (`_record_trace_started()` — no-op in production; tests monkeypatch to detect calls). Both are documented in module-level `__all__`; production cost is zero.

### 6. `_test_route_handler` callback receives BrowserContext, not Page

The plan body suggested passing the page to the test handler. In Playwright, `page.route()` only affects requests after the route is installed; if the page navigates before the route fires, the navigation request itself is unmocked. Switched to `context.route()` (set up on the BrowserContext BEFORE any page is created or navigation begins) — applies to all pages in the context, including the initial navigation. Tests now reliably intercept both the navigation document and the XHR.

### 7. Manually installed Chromium for local dev

The local dev environment didn't have Chromium cached at `~/Library/Caches/ms-playwright/chromium-1223/`. Running `playwright install chromium` (one-time, ~260MB download) before running tests. In CI, Plan 03-01's workflow step (`playwright install --with-deps chromium`) + `actions/cache@v4` keyed on `requirements.lock` handle this — the workflow YAML is already configured correctly. No code change needed; just dev-environment setup.

## Auth Gates

None encountered. PlaywrightAdapter doesn't read credentials — that's Plan 03-03's scope.

## Stub Tracking

None — the adapter emits real `RawPosting` objects with all required fields populated. JD-scan returns `(None, None)` for postings without description text (the contractual behavior per FILT-03, NOT a stub).

## Threat Flags

No new security surface introduced beyond what the plan's `<threat_model>` already enumerated. The catch-all's matches() returns True for any http(s) URL — but this is exactly the desired behavior per CONTEXT.md D-01c. Untrusted page content is sandboxed by Chromium; XHR payloads pass through defensive parsing.

## ADP-09 + ADP-10 Closure Confirmation

- **ADP-09** (Playwright fallback adapter): CLOSED. `src/adapters/playwright_fallback.py` implements XHR-intercept-first via `page.expect_response`, DOM-selector fallback via `page.wait_for_selector` + `selectolax.HTMLParser`, navigation timeout (plan-body update: 60s default, was 20s in REQUIREMENTS.md — D-05 reconciliation documented in REQUIREMENTS.md footnote). REQUIREMENTS.md row marked `[x]`.
- **ADP-10** (conditional stealth): CLOSED. Default INVERTED per D-04 — stealth ON by default with per-site opt-out via `#adapter=playwright:stealth=false` hint, rather than off-by-default with per-site opt-in. The "per-site flag in registry" interpretation is satisfied via the `CompanyConfig.hint` slot (already present from Phase 1 CFG-03). REQUIREMENTS.md row marked `[x]` with footnote documenting the D-04 inversion.

## What's Next

Wave 3 (Plan 03-03) lands the credential workflow:

- `InvalidCredential` typed exception in `src/adapters/base.py`
- `_attempt_login` flow in `PlaywrightAdapter` reads `SCRAPER_<COMPANY_UPPERCASE>_<KIND>` env vars (SEC-02 / D-02a)
- Structural SEC-03 ban on credential-value logging (verified by `grep -c`)
- `CLAUDE.md` gets the `## Adding a Company` 5-step workflow per D-03 + D-03a
- `README.md` gets `## Credential Naming Convention (SEC-06)` with per-adapter audit table

Phase 3 closes after Wave 3; all 6 phase REQ-IDs (ADP-09, ADP-10, SEC-01, SEC-02, SEC-04, SEC-06) closed.

## Self-Check: PASSED

**Files claimed to exist:**

- src/adapters/playwright_fallback.py — FOUND
- src/normalizer.py — FOUND
- src/registry.py — FOUND
- tests/test_playwright_adapter.py — FOUND
- tests/test_normalizer.py — FOUND
- tests/test_registry.py — FOUND
- tests/test_adapter_contract.py — FOUND
- tests/fixtures/anthropic_sample.json — FOUND
- tests/fixtures/anthropic_sample.html — FOUND

**Commits claimed to exist:**

- 7202dc0 — FOUND
- ac6f40f — FOUND
