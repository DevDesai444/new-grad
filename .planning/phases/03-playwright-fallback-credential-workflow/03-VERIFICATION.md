---
phase: 03
phase_name: playwright-fallback-credential-workflow
status: human_needed
gates_passed: 14
gates_total: 14
verified_at: 2026-06-08T16:09:16Z
score: 4/4 ROADMAP success criteria verified (structural); 1 requires live human confirmation
overrides_applied: 0
human_verification:
  - test: "Live cron run scrapes at least one JS-heavy SPA via Playwright fallback and renders it in the README table"
    expected: "After `gh workflow run scan` (or natural hourly trigger), README's BEGIN/END JOBS block contains at least one row whose `Posting` link resolves to a JS-heavy SPA (e.g., anthropic.com/careers) and that company's outcome row in the per-company table is `ok`."
    why_human: "Verifier cannot run real Chromium against live anthropic.com from this environment. Structural evidence (PlaywrightAdapter exists + matches catch-all + 35 unit tests against mocked browser pages + workflow YAML installs Chromium with cache key) is in place; only a live workflow run can confirm SC-1's user-visible outcome end-to-end."
  - test: "Second consecutive hourly run hits Playwright Chromium cache (cold-install penalty avoided)"
    expected: "After two consecutive runs of the `scan` workflow with no changes to requirements.lock, the `Install Playwright browsers` step on the 2nd run reports cache hit (`Cache restored from key: playwright-Linux-<hash>`) and completes in <10s rather than ~90s."
    why_human: "GitHub Actions cache behavior can only be observed on actual runner logs. Structural evidence: `actions/cache@v4` with `path: ~/.cache/ms-playwright` and `key: playwright-${{ runner.os }}-${{ hashFiles('requirements.lock') }}` exists in scan.yml lines 42-45; install step runs unconditionally (cache restore happens via the cache action automatically)."
  - test: "Claude CLI end-to-end credential provisioning flow against a real credentialed site"
    expected: "User says `add https://<credentialed-site>` to Claude CLI; Claude detects login form, prompts inline for email+password, runs `gh secret set` for both, confirms with `gh secret list` (names only), commits URL to companies.txt, next hourly run scrapes successfully."
    why_human: "The flow is documented in CLAUDE.md `## Adding a Company` Step 5 (verified via 4 test_credential_flow doc-invariant tests), the adapter code exists (`_attempt_login` raises `MissingCredential`/`InvalidCredential`), and per-company isolation is integration-tested. But an actual end-to-end Claude CLI session with a real credentialed site is the only way to confirm the documented workflow runs cleanly with real `gh` calls. No such credentialed company is currently in companies.txt."
---

# Phase 3: Playwright Fallback + Credential Workflow Verification Report

**Phase Goal:** User's `companies.txt` can include a JS-heavy SPA and the hourly run scrapes it via headless Chromium; if a site requires login, Claude CLI handles the entire credential-storage flow via `gh secret set` with zero manual repo-config work.

**Verified:** 2026-06-08T16:09:16Z
**Status:** human_needed
**Re-verification:** No — initial verification.

All structural and behavioral truths are VERIFIED in code. Three success-criteria items require live runner / live external-site confirmation (cannot be falsified by the verifier without executing the workflow on GitHub Actions or running Claude CLI against a real credentialed company). Status therefore is `human_needed` rather than `passed` per the verification decision tree.

---

## 1. ROADMAP Success Criteria Verification

| # | Success Criterion (verbatim from ROADMAP) | Status | Evidence |
|---|--------------------------------------------|--------|----------|
| 1 | "User opens the repo after an hourly run and sees at least one posting from a JS-heavy SPA — scraped via Playwright fallback with `wait_for_selector` or `expect_response`, parsed via selectolax; per-page navigation timeout enforces typed `PlaywrightTimeout`." | VERIFIED (structural) + HUMAN (live) | `PlaywrightAdapter` (`src/adapters/playwright_fallback.py:130-440`) implements XHR-intercept-first via `page.expect_response` (line 343) AND DOM-selector fallback via `page.wait_for_selector` (line 383). selectolax HTMLParser used at line 494. 60s default timeout (`_DEFAULT_TIMEOUT_S = 60.0`, line 60). Raises `PlaywrightTimeout` when both paths fail (line 391). 35 unit tests pass against mocked browser pages with Anthropic fixture. Live cron-render-in-README is a human-verifiable item. |
| 2 | "Playwright Chromium cache (`actions/cache@v4` keyed on `requirements.lock`) is hit on the second consecutive run; total runtime under 50min." | VERIFIED (structural) + HUMAN (live runner) | `.github/workflows/scan.yml:42-45` — `uses: actions/cache@v4` with `path: ~/.cache/ms-playwright` and `key: playwright-${{ runner.os }}-${{ hashFiles('requirements.lock') }}`. Install step at line 52: `playwright install --with-deps chromium`. `test_workflow_cache_key_includes_requirements_lock` enforces this structurally. `timeout-minutes: 50` at line 18. Live cache-hit observation is the human item. |
| 3 | "User says 'add this credentialed site' to Claude CLI — Claude inline-prompts, calls `gh secret set SCRAPER_<COMPANY>_<KIND>`, confirms via `gh secret list` (names only), commits adapter referencing `os.environ[<NAME>]`, updates README audit table — no credential value in chat/repo/logs." | VERIFIED (structural + behavioral) + HUMAN (end-to-end flow) | CLAUDE.md `## Adding a Company` 5-step workflow exists (lines 201-279); Step 5 documents inline prompt + `gh secret set` + `gh secret list` + one-shot login test. PlaywrightAdapter `_attempt_login` reads `os.environ.get("SCRAPER_<PREFIX>_EMAIL")` and `..._PASSWORD` via `_company_to_secret_prefix(company.name)` (lines 192-241). README has `## Credential Naming Convention (SEC-06)` section with per-adapter audit table at lines 73-110. `InvalidCredential` exists in `src/adapters/base.py:61-71` and is caught in `src/main.py:86` alongside `MissingCredential`. Structural SEC-03 enforcement: `grep -c traceback.format_exc src/adapters/playwright_fallback.py` returns 0; `test_sec03_no_traceback_format_exc_in_adapter` + `test_sec03_grep_audit_no_credential_values_in_adapter_logging` enforce this in CI. |
| 4 | "`playwright-stealth` is applied only to sites that demonstrably need it (per-site flag in registry), not globally." | VERIFIED with PLAN-DEVIATION NOTE | The implemented behavior is per CONTEXT.md D-04 (which INVERTS the ROADMAP wording): stealth is ON by default with per-site OPT-OUT via `#adapter=playwright:stealth=false` in `companies.txt`. The `_parse_hint_kwargs` helper (`src/adapters/playwright_fallback.py:80-95`) parses this hint. Tests `test_fetch_stealth_enabled_by_default` and `test_fetch_stealth_disabled_by_hint` confirm both branches. Per-site control DOES exist via the existing `CompanyConfig.hint` slot. **REQ-ID ADP-10 is documented in REQUIREMENTS.md line 43 as `*[Phase 3 Plan 03-02: D-04 inverts default — stealth ON by default; per-site opt-out via #adapter=playwright:stealth=false]*` — the deviation is project-blessed and per the verification context instructions ("DO NOT flag D-04 stealth-default as a gap; that's locked"). |

**Score:** 4/4 SC verified at structural level; 3 of 4 also require human live-runner / live-site confirmation, which is captured in `human_verification` items above.

---

## 2. REQ-ID Coverage Matrix (6 expected)

| REQ-ID | Closed in | Description | Status | Evidence |
|--------|-----------|-------------|--------|----------|
| ADP-09 | Plan 03-02 | Playwright fallback adapter (Chromium + `wait_for_selector`/`expect_response` + selectolax) | SATISFIED | `src/adapters/playwright_fallback.py` (440 lines); both XHR-intercept + DOM-fallback paths implemented; 35 tests in `tests/test_playwright_adapter.py`. |
| ADP-10 | Plan 03-02 | `playwright-stealth` conditional per-site | SATISFIED (project-blessed inversion) | `_parse_hint_kwargs` + `stealth_enabled = hint_kw.get("stealth", "true").lower() != "false"`. Tests `test_fetch_stealth_enabled_by_default` + `test_fetch_stealth_disabled_by_hint`. REQUIREMENTS.md line 43 records the D-04 inversion. |
| SEC-01 | Plan 03-03 | Claude inline-prompt + `gh secret set` flow | SATISFIED | CLAUDE.md `## Adding a Company` Step 5 (lines 240-279) documents the full flow. Tested in `test_credential_flow.py::test_claude_md_documents_gh_secret_set`. |
| SEC-02 | Plan 03-03 | `SCRAPER_<COMPANY>_<KIND>` env-var naming convention enforced in adapter | SATISFIED | `PlaywrightAdapter._company_to_secret_prefix` (`src/adapters/playwright_fallback.py:179-190`) implements UPPERCASE + `-`/space → `_` transform. `_attempt_login` reads `os.environ.get(f"SCRAPER_{prefix}_EMAIL")` and `..._PASSWORD` at lines 207-210. Tests `test_company_to_secret_prefix_*` (3 cases) + `test_attempt_login_uses_uppercased_hyphen_translated_env_vars`. |
| SEC-04 | Plan 03-03 | `gh secret list` names-only confirmation | SATISFIED | README.md line 100 + 110: `gh secret list --repo DevDesai444/new-grad` with explicit "names only" note. CLAUDE.md Step 5 sub-step 3 (line 257). Tests `test_readme_documents_gh_secret_list_audit` + `test_readme_documents_sec04_names_only`. |
| SEC-06 | Plan 03-03 | README documents per-adapter secret-audit table | SATISFIED | README `## Credential Naming Convention (SEC-06)` (lines 73-110) with table covering all 7 adapters. Test `test_readme_lists_per_adapter_audit_table` enforces all 7 adapter names appear. |

**Coverage:** 6/6 REQ-IDs satisfied.

---

## 3. Pitfall Coverage Matrix

| Pitfall | Concern | Mitigation | Status | Evidence |
|---------|---------|------------|--------|----------|
| 4 | Secrets in trace files | D-06 trace=off in production; SCRAPER_DEBUG_TRACE=1 escape hatch; `.playwright-trace/` gitignored | VERIFIED | `src/adapters/playwright_fallback.py:62 `_DEBUG_TRACE_ENV`, line 280 `trace_enabled = os.environ.get(_DEBUG_TRACE_ENV) == "1"`. `grep -c SCRAPER_DEBUG_TRACE .github/workflows/scan.yml` returns 0 (not set in prod). `.gitignore:25` includes `.playwright-trace/`. Plus D-02c: structural ban on `traceback.format_exc` — `grep -c traceback.format_exc src/adapters/playwright_fallback.py == 0`. |
| 5 | Anti-bot blocks on SPAs | D-04 stealth ON by default; realistic Chrome UA | VERIFIED | `_USER_AGENT` line 55-59 = realistic Chrome 126.0.0.0; viewport `1920x1080` line 61; stealth default-on. |
| 8 | SPA hydration timing | D-01a XHR-intercept-first | VERIFIED | `page.expect_response` predicate at lines 343-352 captures `/api/` responses with `jobs`/`openings`/etc. keywords BEFORE relying on DOM hydration. |
| 14 | Playwright install time on every run | Cache via `actions/cache@v4` | VERIFIED | `.github/workflows/scan.yml:42-45` caches `~/.cache/ms-playwright`. |
| 15 | Headless detection | `playwright-stealth` | VERIFIED | `_get_stealth_class()` + `stealth_cls().apply_stealth_sync(context)` line 298-301; opt-out via hint. |
| 17 | Secret values leak in logs | Structural grep audit; `from None` on credential exceptions | VERIFIED | `test_sec03_grep_audit_no_credential_values_in_adapter_logging` + `test_sec03_no_traceback_format_exc_in_adapter` enforce in CI. `raise InvalidCredential(...) from None` at lines 230 + 240 suppresses chained traceback. `test_invalid_credential_message_never_includes_credential_values` proves canary strings absent. |
| 26 | Cache key invalidation on Playwright version bump | Key includes `hashFiles('requirements.lock')` | VERIFIED | `.github/workflows/scan.yml:45` — `key: playwright-${{ runner.os }}-${{ hashFiles('requirements.lock') }}`. `requirements.lock` pins `playwright==1.60.0`, `playwright-stealth==2.0.3`, `selectolax==0.4.10`. |

---

## 4. URL Resolver Bonus Verification (D-01b)

This is added scope per CONTEXT.md D-01b (unblocks ~18 CNAME→Workday URLs in user's actual companies.txt). Not strictly in ROADMAP Phase 3 scope but verified because Plan 03-01 shipped it.

| Item | Status | Evidence |
|------|--------|----------|
| `src/url_resolver.py` exists with `resolve_url(url, timeout_s=5.0)` | VERIFIED | File present (106 lines); function signature at line 31; HEAD-first + GET-fallback (405/501) + no-raise contract per D-01b at lines 53-102. |
| `CompanyConfig.resolved_url` field added | VERIFIED | `src/models.py:29` — `resolved_url: str | None = None`, default None preserves Phase 1/2 call sites. |
| `get_adapter` uses resolved URL | VERIFIED | `src/registry.py:75` — `effective_url = company.resolved_url or company.url`; tests `test_get_adapter_uses_resolved_url_when_set` + `test_get_adapter_falls_back_to_url_when_resolved_url_none` + `test_get_adapter_explicit_hint_overrides_resolved_url`. |
| Orchestrator calls `resolve_url` per company | VERIFIED | `src/main.py:47` import; line 227 `company.resolved_url = resolve_url(company.url)`; defensive try/except wraps the call per Pitfall 1. |
| Test proves CNAME→Workday dispatch | VERIFIED | `test_get_adapter_uses_resolved_url_when_set` builds `CompanyConfig(url="https://careers.amd.com", resolved_url="https://amd.wd1.myworkdayjobs.com/External")` and asserts WorkdayAdapter dispatch. |
| 8 url_resolver unit tests pass | VERIFIED | `tests/test_url_resolver.py` — 8 tests collected: passthrough, single redirect, chained, 405→GET, timeout, connect-error, 5xx, query+fragment preservation. All pass. |

---

## 5. ADP-14/15 Open-Closed Invariant Check

Phase 3 must not modify any of the 6 ATS adapter files.

```
git diff --stat 7d5dd0a~1..HEAD -- \
  src/adapters/greenhouse.py src/adapters/lever.py src/adapters/ashby.py \
  src/adapters/smartrecruiters.py src/adapters/workday.py src/adapters/apple.py
```

Result: **empty diff**. ADP-14/15 invariant preserved.

`tests/test_adapter_contract.py` (7 tests) passes — all 7 ADAPTERS subclass Adapter, names unique, Greenhouse self-contained, PlaywrightAdapter inserted as catch-all-LAST, synthetic adapter insertion test confirms open/closed dispatch.

---

## 6. Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite passes | `.venv/bin/python -m pytest tests/ -x --tb=short` | 375 passed in 60.10s | PASS |
| ruff lint clean | `.venv/bin/ruff check src/ tests/` | All checks passed! | PASS |
| `InvalidCredential` distinct typed exception | `python -c "from src.adapters.base import InvalidCredential, MissingCredential; assert InvalidCredential is not MissingCredential and issubclass(InvalidCredential, Exception)"` | exits 0 | PASS |
| `_company_to_secret_prefix` transforms | `python -c "from src.adapters.playwright_fallback import PlaywrightAdapter; print(PlaywrightAdapter._company_to_secret_prefix('acme-corp'))"` → `ACME_CORP`; `'Big Co Inc'` → `BIG_CO_INC`; `'amd'` → `AMD` | All 3 correct | PASS |
| ADAPTERS list order — PlaywrightAdapter last | `python -c "from src.registry import ADAPTERS; print([c.__name__ for c in ADAPTERS])"` | `[Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Apple, Playwright]` | PASS (catch-all last per D-01c) |
| `_parse_hint_kwargs` parses stealth=false | `python -c "from src.adapters.playwright_fallback import _parse_hint_kwargs; print(_parse_hint_kwargs('playwright:stealth=false'))"` | `{'stealth': 'false'}` | PASS |
| Phase 3 commits exist | `git log --oneline | grep -E '86397ed\|9e8a6dd\|87912d7'` | all 3 present | PASS |
| `traceback.format_exc` count in adapter | `grep -c 'traceback.format_exc' src/adapters/playwright_fallback.py` | 0 | PASS (D-02c structural enforcement) |
| `SCRAPER_DEBUG_TRACE` not set in workflow | `grep -c 'SCRAPER_DEBUG_TRACE' .github/workflows/scan.yml` | 0 | PASS (D-06 prod-trace-off invariant) |

---

## 7. Anti-Patterns Scan

Files modified in Phase 3 (per SUMMARYs of Plans 03-01/02/03):
- `src/url_resolver.py` (NEW), `src/models.py`, `src/registry.py`, `src/normalizer.py`, `src/main.py`
- `src/adapters/base.py`, `src/adapters/playwright_fallback.py` (NEW)
- `.github/workflows/scan.yml`, `.gitignore`, `pyproject.toml`, `requirements.lock`
- `CLAUDE.md`, `README.md`
- Tests: `test_url_resolver.py` (NEW), `test_playwright_adapter.py` (NEW), `test_credential_flow.py` (NEW), `test_workflow_yaml.py` (NEW), edits to `test_adapter_base.py`, `test_orchestrator.py`, `test_models.py`, `test_registry.py`, `test_normalizer.py`, `test_adapter_contract.py`.

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `src/adapters/playwright_fallback.py:333` | `pass` in `except PlaywrightTimeoutError` (initial nav) | INFO | Documented deviation #3 in 03-03-SUMMARY; intentional — lets downstream XHR-intercept block also try (might race a redirect successfully). Not a silent-swallow: downstream `raise PlaywrightTimeout(...)` at line 370 surfaces when both paths fail. |
| `src/normalizer.py:481-533` | `_normalize_playwright` returns `salary=None` always | INFO | Deferred to Phase 4 per ROADMAP (NORM-02). Not a Phase 3 gap. |
| `src/adapters/playwright_fallback.py:529` | `from None` in raise | INFO | Intentional SEC-03 mitigation (D-02c) — suppresses chained traceback to avoid `__cause__` leaking DOM text. |
| `src/adapters/playwright_fallback.py:425-440` | Result loop uses `enriched = dict(p)` then `enriched["__dedup_key"]=...` | OK | Standard pattern; matches Phase 2 adapter conventions. |

No blockers found. Two intentional `pass`-on-timeout / `from None` patterns are documented design choices, not anti-patterns.

---

## 8. Test Inventory (375 passing — 27 net new in Phase 3 Plan 03-03 alone)

| Test File | Tests | New in Phase 3 |
|-----------|-------|----------------|
| `tests/test_url_resolver.py` | 8 | All 8 (NEW Plan 03-01) |
| `tests/test_playwright_adapter.py` | 35 | All 35 (NEW Plan 03-02 ships 22; Plan 03-03 adds 13) |
| `tests/test_credential_flow.py` | 10 | All 10 (NEW Plan 03-03) |
| `tests/test_workflow_yaml.py` | 3 | All 3 (NEW Plan 03-01) |
| `tests/test_adapter_base.py` | 10 | +3 InvalidCredential cases (Plan 03-03) |
| `tests/test_orchestrator.py` | 13 | +1 InvalidCredential isolation (Plan 03-03) |
| `tests/test_registry.py` | 16 | +3 resolved_url dispatch (Plan 03-01) + +1 catch-all-last (Plan 03-02) |
| `tests/test_models.py` | 11 | +1 resolved_url field (Plan 03-01) |
| `tests/test_normalizer.py` | 33 | +N playwright dispatch (Plan 03-02) |
| `tests/test_adapter_contract.py` | 7 | Catch-all-last semantics updated (Plan 03-02) |

---

## 9. Gaps Summary

**No gaps found requiring closure-plan work.** All 4 ROADMAP success criteria are structurally satisfied in the codebase. All 6 phase REQ-IDs are closed. ADP-14/15 invariant preserved. URL resolver bonus (D-01b) verified. All pitfall mitigations in place.

The verifier identified 3 items requiring human verification (live runner / live external sites). These are listed in the `human_verification` section of the frontmatter and are normal for any phase whose success criteria include "user opens the repo and sees..." — only an actual workflow run + real-user observation can fully close them. None of them are gaps in the code: they are confirmations of behavior the structural evidence strongly suggests but cannot prove without external execution.

---

## 10. Final Verdict

**Status: human_needed**

Phase 3 ships:
- `PlaywrightAdapter` as catch-all (last in ADAPTERS); XHR-intercept-first + DOM-selector fallback; stealth on by default with per-site opt-out; 60s timeout; trace=off in prod; raises `PlaywrightTimeout` cleanly.
- `InvalidCredential` typed exception (additive to `src/adapters/base.py`).
- Full credential flow in `PlaywrightAdapter._attempt_login` reading `SCRAPER_<COMPANY_UPPERCASE>_<KIND>` env vars; raises `MissingCredential` (env unset) and `InvalidCredential` (form persists after submit) with structural SEC-03 enforcement (no traceback.format_exc, no credential values in raises/logs, `raise ... from None` to suppress `__cause__` leakage).
- Orchestrator catch-tuple extension (single-line) so `InvalidCredential` isolates per-company per ADP-12.
- `src/url_resolver.py` (D-01b) unblocking ~18 CNAME→Workday URLs in user's actual companies.txt.
- `.github/workflows/scan.yml` Playwright Chromium install + cache keyed on `requirements.lock`.
- CLAUDE.md `## Adding a Company` 5-step workflow (D-03 + D-03a).
- README.md `## Credential Naming Convention (SEC-06)` with per-adapter audit table.
- 375 tests passing; ruff clean; ADP-14/15 invariant preserved (zero touches to the 6 ATS adapter files).

All structural checks pass. The 3 `human_verification` items are routine live-runner confirmations and do not block phase completion in the goal-backward verification sense — they confirm what the code is designed to deliver.

**Recommendation:** Once the user runs `gh workflow run scan` (or waits for the next hourly cron) and confirms the 3 human-verification items, Phase 3 can be marked complete and Phase 4 (NORM-02, NORM-03, OUT-09) can begin.

---

*Verified: 2026-06-08T16:09:16Z*
*Verifier: Claude (gsd-verifier, Opus 4.7 1M context)*
