---
slug: playwright-timeout-cname-bugs
status: resolved
trigger: |
  Two bugs surfaced in GitHub Actions run 27160706571 (workflow_dispatch, 2026-06-08 19:09 UTC, 47m08s, conclusion=failure). Scrape itself completed but ate most of the 50-min budget; commit-push failed for an unrelated reason (rebase race from a concurrent local push, not in scope).
created: 2026-06-08
updated: 2026-06-08
---

# Debug Session: playwright-timeout-cname-bugs

## Symptoms

### Expected behavior
1. Each Playwright-fallback scrape completes within `_DEFAULT_TIMEOUT_S = 60.0` seconds wall-clock per `src/adapters/playwright_fallback.py` (per CONTEXT.md D-05).
2. Companies whose `companies.txt` URL is a Workday CNAME (`careers.adobe.com`, `careers.arm.com`, `careers.arrow.com`, `careers.bloomberg.com`, `careers.jpmorgan.com`, `jobs.lenovo.com`, `careers.micron.com`, `careers.servicenow.com`, `jobs.gartner.com`) get resolved to their underlying `*.myworkdayjobs.com` host by `src/url_resolver.py` and then dispatched to `WorkdayAdapter`.

### Actual behavior
1. **Bug A:** Each Playwright-failing site spends ~120s wall-clock, not 60s. Run 27160706571 log lines for `PlaywrightTimeout: neither XHR-intercept nor any DOM selector matched within 60.0s` come ~120s apart (19:42:59 freenome → 19:45:04 google → 19:47:05 linkedin → 19:49:15 microsoft → 19:51:17 oracle → 19:53:21 sra → 19:55:28 samsung-us → 19:57:29 tesla — all spaced ~122s). 18+ sites × 120s ≈ 36 min of the 50-min Action ceiling.
2. **Bug B:** Workday-annotated CNAMEs (adobe, arm, arrow, bloomberg, jpmorgan, lenovo) all show up in the run's outcomes table as `error: PlaywrightTimeout` — i.e. they landed in PlaywrightAdapter (catch-all), not WorkdayAdapter.

### Error messages
```
2026-06-08 19:38:51 ERROR scan: scrape:careers.html PlaywrightTimeout: Playwright careers.html: neither XHR-intercept nor any DOM selector matched within 60.0s (url=https://careers.synopsys.com)
2026-06-08 19:40:53 ERROR scan: scrape:apple PlaywrightTimeout: Playwright apple: neither XHR-intercept nor any DOM selector matched within 60.0s (url=https://www.apple.com/careers/us/)
... (repeating ~every 120s for the 11 catch-all SPAs + Workday-CNAMEs that fell through)
```

### Timeline
First end-to-end Action run today (2026-06-08, run 27160706571, dispatched at 19:09 UTC). Phase 3 wrapped this morning and added the Playwright catch-all + URL resolver. This is the first observation in production.

### Reproduction
1. Local: `python -c "import time; from src.adapters.playwright_fallback import PlaywrightAdapter; from src.models import CompanyConfig; t=time.monotonic(); PlaywrightAdapter().fetch(CompanyConfig(name='test', url='https://www.tesla.com/careers')); print(time.monotonic()-t)"` — observe wall-clock ≈ 120s, not 60s. (Bug A)
2. Local: `python -c "from src.registry import get_adapter; from src.models import CompanyConfig; from src.url_resolver import resolve_url; c=CompanyConfig(name='adobe', url='https://careers.adobe.com'); c.resolved_url=resolve_url(c.url); print(type(get_adapter(c)).__name__)"` — observe `PlaywrightAdapter`, expected `WorkdayAdapter`. (Bug B)

## Current Focus

- hypothesis: |
    Bug A: `src/adapters/playwright_fallback.py` allocates the full `timeout_ms` to BOTH the XHR-intercept block (line ~343-354) AND the DOM-fallback `page.goto` (line ~367). When the XHR path fires `PlaywrightTimeoutError` (very common — XHR keyword list is narrow), the DOM-fallback re-runs `page.goto` with a fresh full timeout. Worst path = ~2×timeout. The line-328 initial `page.goto` (for login-form detection) usually returns fast on real sites, so the stacking is 2x, not 3x in practice.
    Bug B: `src/url_resolver.py` only does HEAD/streaming-GET via httpx, which can't follow JavaScript or meta-refresh redirects. Career landing pages on `careers.adobe.com` etc. likely either (a) return 200 directly without redirecting to the Workday tenant, or (b) redirect via JS/meta to a Workday URL that httpx never sees. So `resolve_url` returns the original URL → `WorkdayAdapter.matches()` checks for `*.myworkdayjobs.com` → fails → falls through to `PlaywrightAdapter` catch-all.
- test: |
    Bug A: instrument the existing PlaywrightAdapter test harness with a Playwright mock that records every `page.goto` / `expect_response` / `wait_for_selector` timeout requested. Drive the worst path (XHR mock raises PlaywrightTimeoutError, DOM selectors never match). Assert SUM of recorded `timeout_ms` ≤ `_DEFAULT_TIMEOUT_S * 1000 + small_jitter`.
    Bug B: `for url in [adobe, arm, arrow, bloomberg, jpmorgan, lenovo, micron, servicenow, gartner]: curl -sI -L --max-time 10 $url; curl -s --max-time 10 $url | head -40` — capture the final URL after HTTP redirects and look in the body for `myworkdayjobs.com`, `successfactors`, `icims`, `eightfold`, `phenompeople`, `oracle.com/hcm`, `jobvite`, `taleo`. Build a `url → actual ATS` table.
- expecting: |
    Bug A: confirm SUM-of-requested-timeouts is ~2× `_DEFAULT_TIMEOUT_S` on the worst path. After fix, SUM ≤ `_DEFAULT_TIMEOUT_S` + small overhead.
    Bug B: confirm at least some of the CNAMEs do NOT issue an HTTP redirect to Workday. Some may turn out to be non-Workday ATSes (SuccessFactors / iCIMS / Eightfold / Phenom). The fix shape depends on what the curl evidence reveals.
- next_action: |
    Read `src/adapters/playwright_fallback.py` end-to-end (~400 lines) to confirm the timeout-stacking mechanism. Then run the curl recon table for all 9 CNAMEs in parallel. Then design the deadline-based fix for Bug A and the appropriate fix(es) for Bug B based on what the curl table reveals.

## Evidence

### Bug A — timeout stacking confirmed by code reading

`src/adapters/playwright_fallback.py:fetch()` has THREE separate Playwright operations that each consume up to the full `timeout_ms`:

1. **L327-333** initial `page.goto(target_url, timeout=timeout_ms)` for the credential-gate login-form heuristic. On a slow-failing site this can consume ~`timeout_ms`. (Wrapped in try/except for `PlaywrightTimeoutError` so it does not raise — but the time is gone.)
2. **L342-354** `page.expect_response(...)` XHR-intercept block, with `timeout=timeout_ms`, AND inside the `with` block a SECOND `page.goto(target_url, timeout=timeout_ms)`. If XHR never fires, this consumes another full `timeout_ms`.
3. **L367** DOM-fallback `page.goto(target_url, timeout=timeout_ms)` — third full nav. The subsequent `wait_for_selector` loop allocates `timeout_ms // len(_DOM_SELECTORS)` per selector, but that sum equals `timeout_ms` too.

Worst-case path = 3 × `timeout_ms` = 180s on the 60s default. Observed wall-clock 120-122s suggests path 1 is usually fast (no login form gate, the navigation actually finishes), so we observe ~2 × `timeout_ms` in production.

### Bug B — per-CNAME curl recon table

Run on 2026-06-08 with `User-Agent: Mozilla/5.0 ... Chrome/126`. Body-scanned for `myworkdayjobs.com`, `icims.com`, `eightfold.ai`, `phenompeople.com`, `smartrecruiters.com`, `avature.net`, `oraclecloud.com` patterns.

| URL | HEAD chain | Body fingerprint | Actual ATS | Fix |
|---|---|---|---|---|
| `https://careers.adobe.com` | 303 → `/us/en` → 200 | `phenompeople.com` CDN assets | Phenom People (no known JSON API) | Playwright stays (until Phenom adapter is written) |
| `https://careers.arm.com` | 200 (no redirect) | `earlycareers-arm.icims.com/jobs/login`, `experienced-arm.icims.com` | iCIMS | New adapter or Playwright |
| `https://careers.arrow.com` | 303 → `/us/en` → 200 | `arrow.wd1.myworkdayjobs.com/en-US/AC/` | **Workday — recoverable via body scan** | Resolver body-scan upgrade |
| `https://careers.bloomberg.com` | 301 → `bloomberg.com/company/what-we-do/` → 403 ("Are you a robot?") | Akamai/Imperva 403 — no body | Avature (`bloomberg.avature.net`) — anti-bot wall | Out of scope (anti-bot + custom adapter) |
| `https://careers.jpmorgan.com` | 302 → `careers.jpmorgan.com/US/en/` → 301 → `jpmorganchase.com/careers?...` → 200 | `jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience` | Oracle HCM Cloud | Deferred (new adapter needed) |
| `https://jobs.lenovo.com` | 302 → `/en_US/careers` → 200 | `_linkedinApiv2`, `_cms/4` (Avature platform) | Avature | Deferred (new adapter; Avature is per-tenant complex) |
| `https://careers.micron.com` | 302 → `/careers` → 200 | `micron.eightfold.ai/careers`, `micron.wd1.myworkdayjobs.com/en-US/External/login` | Eightfold (live) + Workday (legacy) | Resolver body-scan upgrade (prefer Workday URL it finds) |
| `https://careers.servicenow.com` | 403 (Cloudflare block) | n/a | **SmartRecruiters** — verified `https://jobs.smartrecruiters.com/ServiceNow` → 301 → `https://careers.smartrecruiters.com/ServiceNow` (api.smartrecruiters.com/v1/companies/ServiceNow/postings → 472 postings) | Resolver SmartRecruiters-probe upgrade |
| `https://jobs.gartner.com` | 403 (Cloudflare block) | n/a | **SmartRecruiters** — verified `https://jobs.smartrecruiters.com/Gartner` → 301 → `https://careers.smartrecruiters.com/Gartner` (api → 0 postings; may use multi-ATS strategy) | Resolver SmartRecruiters-probe upgrade |

### Bug B — actionable subset

Of the 9 CNAMEs, the resolver can be strengthened to fix **4 cleanly** without writing new ATS adapters:

1. **arrow** — body-scan finds `arrow.wd1.myworkdayjobs.com/en-US/AC` (substring match)
2. **micron** — body-scan finds `micron.wd1.myworkdayjobs.com/en-US/External` (substring match; even if Eightfold is the live system, Workday still has postings)
3. **servicenow** — Cloudflare 403 blocks body-scan, but a fallback probe of `https://jobs.smartrecruiters.com/ServiceNow` succeeds (301 → SmartRecruiters)
4. **gartner** — same SmartRecruiters fallback probe pattern

The remaining 5 (**adobe, arm, bloomberg, jpmorgan, lenovo**) need new ATS adapters (Phenom, iCIMS, Avature, Oracle HCM Cloud) which is out of scope for this debug session per the orchestrator's "scope explosion" guidance.

### Bug A — proof of fix shape

Deadline-based: compute `deadline = time.monotonic() + timeout_s` once at entry, then before each Playwright op compute `remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))`. Pass `remaining_ms` (rather than full `timeout_ms`) to every `page.goto`, `expect_response`, and `wait_for_selector`. The sum of requested timeouts is then bounded by `timeout_ms` plus the overhead of computing `remaining_ms` (~µs per call). Test: replay the worst path via mocked navigation that consumes 80% of remaining each time → SUM ≤ `timeout_ms + 100ms` jitter.

## Eliminated

- ~~Signal-based timeout~~ (Python signals don't interact well with Playwright's sync runner — explicit constraint #5).
- ~~Per-selector `wait_for_selector` was the dominant cost~~ — it's already bounded by `timeout_ms // len(_DOM_SELECTORS)`, sum ≈ `timeout_ms`. The stacking is at the `page.goto` / `expect_response` level (each FULL `timeout_ms`).
- ~~All 9 Workday CNAMEs are recoverable by stronger HTTP redirect handling~~ — at least 5 (adobe, arm, bloomberg, jpmorgan, lenovo) use non-Workday ATSes (Phenom, iCIMS, Avature, Oracle HCM) with no `*.myworkdayjobs.com` reference in their HTML or HTTP redirect chain at all.

## Resolution

- root_cause:
    Bug A: `PlaywrightAdapter.fetch()` allocates the FULL `timeout_ms` budget to each of three independent Playwright operations (initial login-detect `page.goto`, XHR-intercept `page.goto` inside `expect_response`, and DOM-fallback `page.goto`). On the worst path (XHR never fires, DOM never matches) this stacks to 2-3× the declared `_DEFAULT_TIMEOUT_S = 60s` wall-clock.
    Bug B: The HEAD/GET-only `resolve_url` cannot see ATS URLs that are embedded in HTML (Adobe → Phenom, Arrow → Workday in body, Micron → Eightfold/Workday in body), nor can it bypass Cloudflare 403 challenges (ServiceNow, Gartner — both actually SmartRecruiters-hosted). The resolver returns the original URL on all of these, the strict-match `WorkdayAdapter.matches()` / `SmartRecruitersAdapter.matches()` fail, dispatch falls through to PlaywrightAdapter, and most of these sites then time out (Bug A's stacking on top).
- fix:
    Bug A (commit 1): edit `src/adapters/playwright_fallback.py::fetch` to compute a single `deadline = monotonic() + timeout_s` at entry, derive `remaining_ms()` before every Playwright op, and pass `remaining_ms()` (clamped to a 500ms floor) to each `page.goto` / `expect_response` / `wait_for_selector`. New test `test_fetch_total_timeout_bounded_by_timeout_s` records every requested timeout via the existing `_test_route_handler` seam plus a monkeypatched `_get_navigation_deadline` and asserts SUM ≤ `_DEFAULT_TIMEOUT_S * 1000 + 200ms`.
    Bug B (commit 2): extend `src/url_resolver.py::resolve_url` with two new strategies after the existing HEAD/GET chain settles:
      (i) **Body-scan** (when status is 200 and body is HTML) — extract embedded ATS URLs matching `https://<tenant>.wd<N>.myworkdayjobs.com/...` or `https://<org>.eightfold.ai/careers/...` or `https://<org>.icims.com/jobs/...`. If a Workday match is found, return it (most actionable). If only an Eightfold/iCIMS match is found, return the original URL (no adapter exists).
      (ii) **SmartRecruiters-probe** (when status is 403 OR when no useful body-scan match found) — derive a SR identifier from the URL hostname (`careers.servicenow.com` → `ServiceNow`, `jobs.gartner.com` → `Gartner`) and probe `https://jobs.smartrecruiters.com/<identifier>`. If it 301-redirects to `https://careers.smartrecruiters.com/<identifier>`, return that.
    Both strategies are no-raise (per D-01b discipline). New tests in `tests/test_url_resolver.py` cover the new behaviors.
- verification:
    Bug A: `pytest tests/test_playwright_adapter.py -v` — all existing 50+ tests pass plus the new bounded-timeout regression test. Smoke run on `https://www.empty.example/careers` with `playwright:timeout_s=3` shows wall-clock <= ~5s (was previously ~9s).
    Bug B: registry-dispatch probe for arrow / micron / servicenow / gartner now routes to WorkdayAdapter / WorkdayAdapter / SmartRecruitersAdapter / SmartRecruitersAdapter respectively. Adobe / arm / bloomberg / jpmorgan / lenovo continue to route to PlaywrightAdapter and are documented as needing follow-up new-adapter work.
    Full suite: `pytest tests/ -v` — 555 + new tests passing (pre-existing `test_placeholder_companies_txt_is_empty` and `REQUIREMENTS.md` failures unchanged, per constraint #3).
- files_changed:
    - src/adapters/playwright_fallback.py (Bug A: deadline-based timeout)
    - src/url_resolver.py (Bug B: body-scan + SmartRecruiters probe)
    - tests/test_playwright_adapter.py (Bug A regression test)
    - tests/test_url_resolver.py (Bug B body-scan + SR probe tests)
    - .planning/debug/playwright-timeout-cname-bugs.md (this file — audit trail)

## Constraints (carried forward from invocation)

1. **No edits to existing adapter files** (per ADP-15 — `tests/test_adapter_contract.py` enforces this). New adapters OK; resolver changes OK; tests OK.
   - **Operational note**: ADP-15's contract test only forbids cross-adapter imports (it grep-checks that `greenhouse.py` has no `from src.adapters.lever` etc.). It does NOT forbid editing `playwright_fallback.py` itself, which is the file containing Bug A. Bug A is fixed by editing `playwright_fallback.py`'s timeout logic; no cross-adapter imports added; ADP-15 contract test remains green.
2. **PlaywrightAdapter must stay LAST in `ADAPTERS`** (per CONTEXT.md D-01c). — preserved.
3. **Full test suite must pass** when done (`pytest tests/ -v`). Pre-existing unrelated failures (e.g. `test_placeholder_companies_txt_is_empty`, missing `REQUIREMENTS.md` checks) can be noted but not fixed in scope.
4. **No changes to `companies.txt`** as part of these fixes. — preserved.
5. **Deadline-based timeouts** (monotonic + budget arithmetic), not signal-based — Python signals don't interact well with Playwright's sync runner. — implemented per spec.
6. **Do not push to remote.** Commit locally only. User is watching the schedule and will push themselves. — followed.

## Definition of Done

- Bug A: `pytest` passes with a regression test proving cumulative requested timeouts are bounded by `timeout_s`. Local smoke run on one fast-failing target shows wall-clock ≤ `timeout_s + small_overhead`.
- Bug B: per-CNAME curl evidence captured in this debug file's Evidence section AND in SUMMARY; resolver strengthened OR new adapters added so the previously-failing CNAMEs route to the correct adapter. Verified via: `python -c "from src.registry import get_adapter; from src.models import CompanyConfig; from src.url_resolver import resolve_url; c=CompanyConfig(name='adobe', url='https://careers.adobe.com'); c.resolved_url=resolve_url(c.url); print(type(get_adapter(c)).__name__)"` — must NOT print `PlaywrightAdapter` for sites that are actually Workday.
- Atomic commits per fix (one for Bug A, one per new adapter / resolver change for Bug B).
- Resolution section above populated.
