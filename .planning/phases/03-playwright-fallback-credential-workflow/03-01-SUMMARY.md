---
phase: 03-playwright-fallback-credential-workflow
plan: 01
subsystem: url-resolver-and-playwright-cache
tags: [url-resolver, redirect-following, cname-workday, playwright-cache, models, registry, foundation, infra]
requirements: [ADP-09]
requires:
  - src/models.py CompanyConfig (Phase 1)
  - src/registry.py get_adapter (Phase 1/2)
  - src/main.py orchestrator (Phase 1)
  - src/adapters/workday.py (Phase 2 — receives resolved CNAME URLs)
  - httpx, respx, pyyaml (already in requirements.lock / requirements-dev.txt)
provides:
  - src/url_resolver.resolve_url(url, timeout_s=5.0) -> str — HEAD-first
    redirect resolver, NEVER raises, returns original URL on any error
  - CompanyConfig.resolved_url: str | None — optional field populated by
    orchestrator before adapter dispatch
  - registry.get_adapter() now dispatches on `resolved_url or url`
  - Workflow installs Chromium via `playwright install --with-deps chromium`
    with cache keyed on requirements.lock (Pitfall 14 + 26 mitigations)
  - .gitignore extended with .playwright-trace/ + playwright/.cache/
affects:
  - PlaywrightAdapter (Plan 03-02) — will be appended as catch-all LAST in
    ADAPTERS list; reads `company.resolved_url or company.url`
  - CLAUDE.md "Adding a Company" workflow (Plan 03-03) — D-03a step 2
    (resolve redirects) now wired
tech-stack:
  added: []  # all deps were already pinned in Phase 1's requirements.lock
  patterns:
    - "Pre-flight redirect resolution as orchestrator step (vs per-adapter)"
    - "Optional pydantic field for downstream adapter consumption"
    - "Never-raises contract on resolver to keep orchestrator loop simple"
    - "GitHub Actions cache keyed on lock-file hash (Pitfall 26)"
key-files:
  created:
    - src/url_resolver.py
    - tests/test_url_resolver.py
    - tests/test_workflow_yaml.py
  modified:
    - src/models.py
    - src/registry.py
    - src/main.py
    - .github/workflows/scan.yml
    - .gitignore
    - tests/test_models.py
    - tests/test_registry.py
    - tests/test_orchestrator.py
decisions:
  - "resolve_url logs only on actual resolution (URL changed), not on identity passes — keeps logs signal-rich"
  - "Defensive try/except in main loop even though resolve_url's contract is no-raise (defense in depth per Pitfall 1)"
  - "NoAdapterFound message now includes resolved URL for diagnostic clarity"
  - "8 url_resolver tests instead of plan's enumerated 9 — kept the 8 distinct semantic cases from the plan's behavior block; the 9th (HEAD-405 fallback) was already covered"
  - "Docstring reworded to drop `traceback.format_exc()` literal substring so AC `grep -c traceback.format_exc src/url_resolver.py == 0` passes (mirrors Phase 1 Plan 01-03 precedent)"
metrics:
  duration_minutes: 10
  tasks: 2
  files_created: 3
  files_modified: 8
  tests_added: 18
  cumulative_tests: 316
  completed: 2026-06-08
---

# Phase 03 Plan 01: URL Resolver + CompanyConfig.resolved_url + Playwright Cache Summary

**One-liner:** Wave 1 ships the pre-flight HTTP redirect resolver (`src/url_resolver.py`), the additive `CompanyConfig.resolved_url` field, the registry dispatch update, and the Actions Chromium install step + cache — unblocking the ~18-of-31 CNAME→Workday URLs in companies.txt and preparing the runner for Wave 2's PlaywrightAdapter.

## What Shipped

### 1. URL redirect resolver — `src/url_resolver.py` (NEW)

Pure function `resolve_url(url, timeout_s=5.0) -> str`:

- **HEAD-first** via `httpx.head(url, follow_redirects=True, timeout=5.0)`.
- **Fallback to streaming GET** when the server returns 405 (Method Not Allowed) or 501 (Not Implemented). Context-manager closes the connection before the body is read — never transfers payload.
- **Never raises.** On `httpx.TimeoutException`, `httpx.HTTPError`, any non-2xx/3xx terminal status, or unexpected response shape, returns the original `url` unchanged. Orchestrator can always continue.
- **Pitfall 17 / SEC-03 logging discipline:** exception class name + URL only. No `traceback.format_exc()`, no exception attributes (which could include request headers / cookies).
- Honest scraper User-Agent (`new-grad-tracker/0.1 (+repo URL)`) — matches threat-model T-03-01-06 (no spoofing at HEAD layer).

### 2. CompanyConfig.resolved_url — `src/models.py` (ADDITIVE)

```python
resolved_url: str | None = None  # populated by orchestrator before adapter dispatch
```

Phase 1/2 call sites that don't set it continue to work — default is `None`. Downstream adapters (Workday, Plan 03-02 Playwright) read `company.resolved_url or company.url`.

### 3. Registry dispatch — `src/registry.py` (MODIFIED)

`get_adapter()` resolution order is now:

1. Explicit `#adapter=<name>` hint (CFG-03 — unchanged, hint precedence held).
2. URL-pattern match via `Adapter.matches()` on `company.resolved_url or company.url`.
3. `NoAdapterFound` with diagnostic message including the resolved URL.

The CNAME→Workday case lands cleanly: `careers.amd.com` (no adapter match) → orchestrator resolves to `amd.wd1.myworkdayjobs.com/External` (Workday match) → WorkdayAdapter dispatches.

### 4. Orchestrator wiring — `src/main.py` (MODIFIED)

Per-company main loop now begins with:

```python
try:
    company.resolved_url = resolve_url(company.url)
    if company.resolved_url != company.url:
        logger.info("resolve:%s %s -> %s", ...)
except Exception as e:
    logger.warning("resolve:%s unexpected %s — using original url", ...)
    company.resolved_url = None
```

Defensive `try/except` is **defense in depth** — `resolve_url`'s contract is no-raise, but a future bug must not abort the main loop (Pitfall 1 / ADP-12). Logs only when resolution actually changed the URL (signal-rich logs).

### 5. Workflow YAML — `.github/workflows/scan.yml` (MODIFIED)

Two changes:

- **Cache step comments updated** to call out Pitfall 14 (cache hit saves ~90s) and Pitfall 26 (lock-file-hash key invalidates on Playwright version bump).
- **New `Install Playwright browsers` step** added between the cache step and the Run scan step:

  ```yaml
  - name: Install Playwright browsers
    run: playwright install --with-deps chromium
  ```

  Cache hit → near-no-op (~5s). Cache miss → installs Chromium + system libs (~90s, one-time per lock-file change).

### 6. .gitignore — (MODIFIED)

Appended Phase 3 trace-debug paths (D-06: production `trace="off"`; local debug must never commit traces):

```
.playwright-trace/
playwright/.cache/
```

Phase 1 already covered `.env`, `cookies.json`, `*.har`, `trace.zip`, `playwright-report/`, `seen.json.tmp`, `seen.json.bak`.

## Test Delta (+18 cumulative, 298 → 316)

| File                              | Δ   | New cases                                                                                                                                                                                                                                                       |
| --------------------------------- | --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_url_resolver.py` NEW  | +8  | passthrough, single 302, chained 301→302, HEAD-405 GET fallback, timeout, connect-error, 5xx, query/fragment preservation                                                                                                                                       |
| `tests/test_models.py`            | +2  | resolved_url field is optional / default None; accepts string or None nominally                                                                                                                                                                                  |
| `tests/test_registry.py`          | +3  | CNAME→Workday resolved_url dispatch; fallback to url when resolved_url=None; hint precedence over resolved_url                                                                                                                                                  |
| `tests/test_orchestrator.py`      | +2  | resolve_url called once per company with the expected URL each time; defense-in-depth — orchestrator survives a resolver crash and still produces postings                                                                                                       |
| `tests/test_workflow_yaml.py` NEW | +3  | install step exists; cache key includes `hashFiles('requirements.lock')` + path `~/.cache/ms-playwright`; install step runs AFTER `Install Python dependencies`                                                                                                  |

Full suite: **316 passing** (298 Phase 1+2 baseline + 18 new).

ADP-14/15 invariant **preserved** — zero edits to `src/adapters/*.py`. `tests/test_adapter_contract.py` (7 cases) continues to pass unchanged.

## Commits

| Task | Commit  | Files                                                                                                                                                                                                  |
| ---- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1    | 70fb47d | src/url_resolver.py (new), src/models.py, tests/test_url_resolver.py (new), tests/test_models.py                                                                                                       |
| 2    | 07489cd | src/registry.py, src/main.py, .github/workflows/scan.yml, .gitignore, tests/test_registry.py, tests/test_orchestrator.py, tests/test_workflow_yaml.py (new)                                            |

## Manual Sanity

- `.venv/bin/python -m src.main` (empty companies.txt placeholder) exits 0 — Phase 1/2 regression check, "no matching postings yet" placeholder rendered.
- `.venv/bin/python -c "from src.registry import get_adapter; from src.models import CompanyConfig; c = CompanyConfig(name='amd', url='https://careers.amd.com', resolved_url='https://amd.wd5.myworkdayjobs.com/External'); print(type(get_adapter(c)).__name__)"` → `WorkdayAdapter` (CNAME→Workday dispatch confirmed).
- `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/scan.yml'))"` exits 0 — YAML valid.
- `git status` shows no `.playwright-trace/`, `playwright-report/`, or `playwright/.cache/` files staged.

## Threat Model Posture

All 8 STRIDE entries from `03-01-PLAN.md` are addressed:

| Threat ID    | Disposition | Status                                                                                       |
| ------------ | ----------- | -------------------------------------------------------------------------------------------- |
| T-03-01-01   | mitigate    | Resolver logs `type(e).__name__` + URL only; `grep -c traceback.format_exc src/url_resolver.py` = 0 |
| T-03-01-02   | accept      | companies.txt is user-committed; same trust boundary as Phase 1/2 adapters                   |
| T-03-01-03   | mitigate    | 5s per-request timeout; worst case 31 × 5s = 155s, well under workflow timeout-minutes: 50    |
| T-03-01-04   | mitigate    | .gitignore extended with `.playwright-trace/`, `playwright/.cache/`                           |
| T-03-01-05   | mitigate    | Cache key uses `hashFiles('requirements.lock')` — Playwright bump auto-invalidates           |
| T-03-01-06   | accept      | Honest scraper UA; no spoofing at HEAD layer                                                  |
| T-03-01-07   | accept      | Standard GitHub Actions sandboxing                                                            |
| T-03-01-08   | accept      | Resolved URLs are public by design                                                            |

## Deviations from Plan

### 1. Test count: 18 added vs plan's "target 19 / cumulative 317"

The plan's behavior block enumerated 8 distinct `test_resolve_url_*` cases (passthrough, single 302, chained 301→302, HEAD-405 fallback, timeout, connect-error, 5xx, query/fragment preservation), plus 2 `test_models_*` cases. The plan text mentioned "9 tests" in the success criteria — I shipped the 8 distinct semantic cases enumerated in the body. Counting Task 2's contributions (3 registry + 2 orchestrator + 3 workflow YAML), total new = 18; cumulative = 316. **Substance matches the plan's enumerated behavior; only the rounded total is one less.**

### 2. Docstring reworded to drop `traceback.format_exc` literal substring

Initial draft of `src/url_resolver.py` had a docstring sentence `never traceback.format_exc() which could capture request headers`. This made `grep -c 'traceback.format_exc' src/url_resolver.py` return 1, failing the literal AC. Reworded to `never the full traceback, which could capture request headers` — semantics identical, grep AC passes. This mirrors the **Plan 01-03 precedent** in Phase 1's decisions log ("Reworded `traceback.format_exc` references in docstrings/comments — Plan AC literal-grep == 0; substance unchanged").

### 3. Ruff import-sort autofix on `src/main.py`

Adding `from src.url_resolver import resolve_url` initially produced an I001 ruff error because import order needed `state_store` before `url_resolver`. Reordered alphabetically (s before u) — mechanical fix, no behavior change.

### 4. `seen.json` left as untracked artifact (not a deviation, noted for transparency)

A manual `python -m src.main` run during this plan's verification step produced `seen.json` in the repo root. It's never been committed in the project's history (Phase 1 design: workflow's `git-auto-commit-action` commits it on first hourly run when there's a diff). Left untracked locally — same state as end of Phase 2. Not modified by this plan.

## Open-Closed (ADP-14/15) Re-Proof

Files in `src/adapters/`: **zero changes.**

```
$ git diff --name-only 70fb47d^..07489cd -- src/adapters/
(empty)
```

The catch-all addition required no per-adapter changes; the Workday adapter inherits the CNAME→Workday unblocking automatically because the orchestrator threads `resolved_url` into the dispatch URL.

## What's Next

Wave 2 (Plan 03-02) lands the actual `src/adapters/playwright_fallback.py` — XHR-intercept first, DOM-selector fallback via selectolax, `playwright-stealth` on by default, 60s navigation timeout, `trace="off"` in production. It appends to `ADAPTERS` last (catch-all). Anthropic careers (`anthropic.com/careers`) is the seed target per CONTEXT.md D-01.

Wave 3 (Plan 03-03) lands the credential workflow + CLAUDE.md "Adding a Company" instructions per D-02 + D-03.

## Self-Check: PASSED

**Files claimed to exist:**

- src/url_resolver.py — FOUND
- src/models.py — FOUND
- src/registry.py — FOUND
- src/main.py — FOUND
- .github/workflows/scan.yml — FOUND
- .gitignore — FOUND
- tests/test_url_resolver.py — FOUND
- tests/test_registry.py — FOUND
- tests/test_orchestrator.py — FOUND
- tests/test_workflow_yaml.py — FOUND
- tests/test_models.py — FOUND

**Commits claimed to exist:**

- 70fb47d — FOUND
- 07489cd — FOUND
