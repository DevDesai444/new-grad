---
phase: 03-playwright-fallback-credential-workflow
plan: 03
subsystem: credentials-workflow-and-meta-documentation
tags: [credentials, secrets, sec-01, sec-02, sec-04, sec-06, invalid-credential, claude-md, readme, login-detection, gh-secret, adp-12]
requirements: [SEC-01, SEC-02, SEC-04, SEC-06]
requires:
  - src/adapters/base.py Adapter ABC + 4 Phase 1 typed exceptions
  - src/adapters/playwright_fallback.py PlaywrightAdapter (Plan 03-02)
  - src/main.py orchestrator with _scrape_one + typed-exception catch tuple
  - src/url_resolver.resolve_url (Plan 03-01) — referenced by CLAUDE.md Step 2
  - CONTEXT.md D-02 / D-02a / D-02b / D-02c (credentials)
  - CONTEXT.md D-03 / D-03a (Adding-a-Company workflow)
provides:
  - src/adapters/base.InvalidCredential — new typed exception (subclass of
    Exception; distinct from MissingCredential); orchestrator catches both
    via the extended except tuple
  - PlaywrightAdapter._detect_login_form (static heuristic on
    input[type='password']), _company_to_secret_prefix (SEC-02 naming
    convention), _attempt_login (env-var read + form fill + submit + verify)
  - src/main.py _scrape_one extended catch tuple includes InvalidCredential
    so credential rejection on one company is isolated per ADP-12
  - CLAUDE.md `## Adding a Company` 5-step workflow (per D-03 + D-03a)
    documenting how Claude CLI handles `add <URL>` autonomously
  - README.md `## Credential Naming Convention (SEC-06)` section with
    per-adapter audit table + gh secret list/set/delete commands + SEC-04
    "names only" reminder
affects:
  - All future credentialed scrapes — PlaywrightAdapter is the only adapter
    that reads SCRAPER_<COMPANY>_<KIND> env vars; the 6 ATS adapters
    continue to use public APIs with no auth
  - Future "Adding a Company" requests — Claude CLI follows CLAUDE.md's
    5-step flow with the credential branch as an automatic pre-check
  - Phase 4+ verification — SEC-06 audit table is the canonical reference
    for the user's `gh secret list` audit
tech-stack:
  added: []  # all deps already pinned; no new packages
  patterns:
    - "Typed exceptions for distinct credential failure modes
      (MissingCredential vs InvalidCredential)"
    - "Structural SEC-03 enforcement via grep audit tests
      (no credential VALUE in raise/log/print)"
    - "`raise ... from None` to suppress chained tracebacks that could leak
      DOM text via __cause__"
    - "Documentation-as-test pattern (substring assertions on CLAUDE.md +
      README.md catch future structural drift)"
key-files:
  created:
    - tests/test_credential_flow.py
  modified:
    - src/adapters/base.py
    - src/adapters/playwright_fallback.py
    - src/main.py
    - tests/test_adapter_base.py
    - tests/test_orchestrator.py
    - tests/test_playwright_adapter.py
    - CLAUDE.md
    - README.md
decisions:
  - "InvalidCredential added to src/adapters/base.py as APPEND-ONLY change
    (MissingCredential + 3 Phase 1 typed exceptions unchanged); ADP-14/15
    invariant preserved for a sixth time"
  - "Credential gate placed AFTER initial navigation but BEFORE the
    expect_response context block; XHR-intercept re-navigates inside
    expect_response so the fresh response captures cleanly post-auth"
  - "Initial navigation pre-credential-gate wraps PlaywrightTimeoutError in
    a defensive try/pass — downstream XHR-intercept may race a redirect
    successfully even if the initial nav timed out"
  - "_attempt_login uses `raise InvalidCredential(...) from None` to
    suppress the chained traceback (D-02c — prevents __cause__ from
    leaking DOM text including the typed email)"
  - "Selectors are generic (input[type='email'], input[name='email'],
    input[name='username']; button[type='submit'], input[type='submit'],
    button:has-text('Sign in'), button:has-text('Log in')) — per-site
    overrides remain v2 work"
  - "Documentation tests (test_credential_flow.py docs cluster) use
    substring assertions, not exact regex anchors, to tolerate minor
    capitalisation drift while still catching whole-step deletion"
  - "test_invalid_credential_message_never_includes_credential_values
    uses canary strings (secret-leak-canary@example.com / PaSsW0rD-leak-canary)
    + asserts both absence from str(exc) AND exc.__cause__ is None"
  - "_company_to_secret_prefix is a class @staticmethod (not module-level
    helper) so callers + tests reference it via PlaywrightAdapter — keeps
    the credential surface co-located with the adapter that uses it"
  - "Ship 13 PlaywrightAdapter credential tests vs plan's '~7' target —
    granular split per heuristic / env-var / SEC-03 audit / no-login
    regression / D-02a wiring; defends each documented behavior with its
    own regression signal"
  - "Used file-based commit messages (`git commit -F /tmp/...`) for all 3
    tasks because heredoc bash quoting fails on the apostrophe in plan-body
    text — same precedent as Plan 02-03"
metrics:
  duration_minutes: 31
  tasks: 3
  files_created: 1
  files_modified: 8
  tests_added: 27  # 4 base+orch + 13 playwright + 10 credential_flow
  cumulative_tests: 375
  completed: 2026-06-08
---

# Phase 03 Plan 03: Credential Workflow + Meta-Documentation Summary

**One-liner:** Wave 3 closes Phase 3 — `InvalidCredential` typed exception in `src/adapters/base.py` (additive; pairs with `MissingCredential`), PlaywrightAdapter credential flow (`_detect_login_form` + `_company_to_secret_prefix` + `_attempt_login` reading `SCRAPER_<COMPANY_UPPERCASE>_<KIND>` env vars; `from None` suppresses chained tracebacks per SEC-03 / D-02c), single-line orchestrator catch-tuple extension, CLAUDE.md "Adding a Company" 5-step workflow (per D-03 + D-03a), and README.md SEC-06 "Credential Naming Convention" section with per-adapter audit table. All 6 Phase 3 REQ-IDs (ADP-09, ADP-10, SEC-01, SEC-02, SEC-04, SEC-06) closed. **Phase 3 execute-complete.**

## What Shipped

### 1. `InvalidCredential` — `src/adapters/base.py` (APPEND-ONLY)

```python
class InvalidCredential(Exception):
    """Raised by Playwright adapter (Phase 3 Plan 03-03) when login credentials
    are PRESENT in env vars (`SCRAPER_<COMPANY>_<KIND>`) but the login form
    rejects them — heuristic: form still visible after submit + brief wait.
    Distinct from MissingCredential (env var unset).

    Per SEC-03 / Pitfall 17 / CONTEXT.md D-02c: exception message includes
    COMPANY + URL only — NEVER credential values, NEVER response body, NEVER
    request headers. Orchestrator's per-company isolation (ADP-12) catches
    alongside MissingCredential and continues scanning other companies.
    """
```

Mirrors the shape of the 4 Phase 1 typed exceptions (`SiteBlocked`, `SchemaDrift`, `PlaywrightTimeout`, `MissingCredential`). Distinct from `MissingCredential` so the orchestrator + adapter can disambiguate "env var unset" from "login form rejected".

### 2. PlaywrightAdapter credential flow — `src/adapters/playwright_fallback.py` (extended)

Three new class members:

```python
@staticmethod
def _detect_login_form(page) -> bool:
    """Heuristic: page has at least one <input type='password'>."""
    try:
        return page.locator(PlaywrightAdapter._PASSWORD_SELECTOR).count() > 0
    except Exception:
        return False

@staticmethod
def _company_to_secret_prefix(company_name: str) -> str:
    """SEC-02: uppercase + hyphens/spaces -> underscores.
       amd -> AMD; acme-corp -> ACME_CORP; 'Big Co Inc' -> BIG_CO_INC."""
    return company_name.upper().replace("-", "_").replace(" ", "_")

def _attempt_login(self, page, company: CompanyConfig) -> None:
    """Read SCRAPER_<COMPANY>_<KIND> -> fill form -> submit -> verify.
       Raises MissingCredential (env unset) or InvalidCredential (form persists)."""
```

Class-level selector constants:

```python
_LOGIN_WAIT_MS: ClassVar[int] = 3000
_EMAIL_SELECTOR: ClassVar[str] = (
    "input[type='email'], input[name='email'], input[name='username']"
)
_PASSWORD_SELECTOR: ClassVar[str] = "input[type='password']"
_SUBMIT_SELECTOR: ClassVar[str] = (
    "button[type='submit'], input[type='submit'], "
    "button:has-text('Sign in'), button:has-text('Log in')"
)
```

**Integration into `fetch()`:** After context + page creation, BEFORE the `expect_response` XHR-intercept block:

```python
page = context.new_page()
page.set_default_navigation_timeout(timeout_ms)

# Plan 03-03 credential gate.
try:
    page.goto(target_url, timeout=timeout_ms)
except PlaywrightTimeoutError:
    pass  # let XHR-intercept retry; might race a redirect successfully
if self._detect_login_form(page):
    self._attempt_login(page, company)

try:
    with page.expect_response(...) as resp_info:
        page.goto(target_url, timeout=timeout_ms)
    # ... rest of existing XHR-intercept + DOM-fallback ...
```

**SEC-03 / D-02c enforcement:**
- `raise InvalidCredential(...) from None` suppresses the chained `__cause__` traceback that could leak DOM text (including the typed email).
- Exception messages contain ONLY: adapter name (`Playwright`), `company.name`, env var NAMES (`SCRAPER_<COMPANY>_EMAIL`), diagnostic context ("login form still present after submit (wrong credentials, anti-bot challenge, or selector drift)"). **No credential values, ever.**
- Grep audit (`test_sec03_grep_audit_no_credential_values_in_adapter_logging`): no `SCRAPER_..._<KIND>=` assignment line on raise / logger / print.
- Grep audit (`test_sec03_no_traceback_format_exc_in_adapter`): `traceback.format_exc` count == 0.

### 3. Orchestrator catch-tuple extension — `src/main.py` (single-line edits)

```python
from src.adapters.base import (
    InvalidCredential,   # NEW Plan 03-03
    MissingCredential,
    PlaywrightTimeout,
    SchemaDrift,
    SiteBlocked,
)

# inside _scrape_one:
except (
    SchemaDrift, PlaywrightTimeout, MissingCredential, InvalidCredential,
) as e:
    logger.error("scrape:%s %s: %s", company.name, type(e).__name__, e)
    return [], f"error: {type(e).__name__}"
```

A credentialed adapter raising `InvalidCredential` is now isolated per ADP-12 — the orchestrator logs class name + str(e) only (Pitfall 17), records outcome as `"error: InvalidCredential"`, and continues to the next company.

### 4. CLAUDE.md `## Adding a Company` section (per D-03 + D-03a)

New top-level section inserted between `<!-- GSD:workflow-end -->` and `<!-- GSD:profile-start -->`. The section lives **outside** any GSD-managed sentinel block so it survives future GSD regeneration cycles.

Documents the 5-step flow:

| Step | What | Outcome |
|------|------|---------|
| 1 | Try existing adapters via `get_adapter()` on raw URL | Append URL + commit if matched |
| 2 | Resolve redirects via `resolve_url()` | Append the **resolved** URL (D-03a) if matched after resolution |
| 3 | Playwright catch-all + one-shot verification | Append URL + commit if verification succeeds |
| 4 | Write a new adapter (rare) | Insert before catch-all at `len(ADAPTERS) - 1` (preserves ADP-14/15) |
| 5 | Credential branch (jumps in BEFORE step 1 when login detected) | Inline-prompt → `gh secret set` → `gh secret list` audit → one-shot login test |

Step 5 details the SEC-01/02/04 credential flow:

1. Inline-prompt user in chat (never echo values back).
2. `gh secret set SCRAPER_<COMPANY_UPPERCASE>_EMAIL --repo DevDesai444/new-grad --body "<email>"` (and `_PASSWORD`).
3. `gh secret list --repo DevDesai444/new-grad` — names only.
4. One-shot login test via `PlaywrightAdapter().fetch(...)` with env vars set in the local shell.
5. Update README SEC-06 audit table.
6. Append URL to `companies.txt`; commit.

Explicit out-of-scope: 2FA, OAuth, magic-link auth.

### 5. README.md `## Credential Naming Convention (SEC-06)` section

New section inserted between `## Secret Hygiene (SEC-03)` and `## Hourly Cadence — What to Expect`. Documents:

- Naming pattern `SCRAPER_<COMPANY_UPPERCASE>_<KIND>` with `<KIND>` ∈ {EMAIL, USERNAME, PASSWORD, API_KEY, OAUTH_TOKEN} (v1 supports EMAIL + PASSWORD).
- Per-adapter secret audit table — all 6 ATS adapters show `(none)` (public APIs, no auth); only `**playwright**` references `SCRAPER_<COMPANY>_EMAIL` + `SCRAPER_<COMPANY>_PASSWORD`.
- `gh` commands for list / rotate / delete.
- SEC-04 reminder: `gh secret list` shows names only, never values.

### 6. Tests (+27 net, 348 -> 375)

| File | Δ | Notes |
|------|---|-------|
| `tests/test_adapter_base.py` | +3 | Parametrize InvalidCredential into the typed-error inheritance test (+1 case); 2 explicit tests (importable + Exception subclass; distinct from MissingCredential). The `test_typed_errors_are_distinct_classes` count check expanded from 4 -> 5. |
| `tests/test_orchestrator.py` | +1 | `test_orchestrator_isolates_invalid_credential` — synthetic adapter raises InvalidCredential; OK company still produces posting; exit 0. |
| `tests/test_playwright_adapter.py` | +13 | _company_to_secret_prefix (3 cases); _detect_login_form (2 cases — positive + anthropic_sample.html negative); MissingCredential (2 cases — email unset + password unset); InvalidCredential (1 — form persists); SEC-03 message-leak audit (1 — canary email + password absent from str(exc) AND exc.__cause__ is None); D-02a env-var-name wiring (1 — acme-corp -> SCRAPER_ACME_CORP_*); no-login-regression (1); SEC-03 grep audit (2 — no credential VALUE assignment in raise/log/print; no traceback.format_exc). |
| `tests/test_credential_flow.py` NEW | +10 | 9 doc invariants (CLAUDE.md 4 + README.md 5) + 1 cross-cutting orchestrator-isolation integration test (3-company companies.txt; one InvalidCredential; other two land postings; exit 0). |

Full suite: **375 passing** (348 Plan 03-02 baseline + 27 net new).

ADP-14/15 invariant **preserved a sixth time** — zero edits to any of the 6 ATS adapter files (`greenhouse / lever / ashby / smartrecruiters / workday / apple`). `tests/test_adapter_contract.py` (7 cases) continues to pass.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| 1 | 86397ed | src/adapters/base.py, src/main.py, tests/test_adapter_base.py, tests/test_orchestrator.py |
| 2 | 9e8a6dd | src/adapters/playwright_fallback.py, tests/test_playwright_adapter.py |
| 3 | 87912d7 | CLAUDE.md, README.md, tests/test_credential_flow.py |

## Manual Sanity

```bash
$ .venv/bin/python -c "from src.adapters.base import InvalidCredential, MissingCredential; \
    assert InvalidCredential is not MissingCredential and \
    issubclass(InvalidCredential, Exception); print('OK')"
OK

$ .venv/bin/python -c "from src.adapters.playwright_fallback import PlaywrightAdapter; \
    assert PlaywrightAdapter._company_to_secret_prefix('acme-corp') == 'ACME_CORP' and \
    PlaywrightAdapter._company_to_secret_prefix('Big Co Inc') == 'BIG_CO_INC'; print('OK')"
OK

$ command grep -c 'traceback.format_exc' src/adapters/playwright_fallback.py
0

$ command grep -c 'class InvalidCredential' src/adapters/base.py
1

$ command grep -E 'raise (MissingCredential|InvalidCredential)' src/adapters/playwright_fallback.py | wc -l
3

$ command grep -q '## Adding a Company' CLAUDE.md && \
    command grep -q '## Credential Naming Convention' README.md && echo "docs OK"
docs OK
```

## Threat Model Posture

All 10 STRIDE entries from `03-03-PLAN.md` addressed:

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-03-03-01 (credential leak via __cause__ chain) | mitigate | `raise InvalidCredential(...) from None` suppresses chain; `test_invalid_credential_message_never_includes_credential_values` asserts `exc.__cause__ is None` |
| T-03-03-02 (credential leak via logger output) | mitigate | Structural ban verified by `test_sec03_grep_audit_no_credential_values_in_adapter_logging` — zero `SCRAPER_..._<KIND>=` assignment lines on raise/logger/print |
| T-03-03-03 (trace file leak in production) | mitigate | D-06 enforced by Plan 03-02 — workflow YAML does not set SCRAPER_DEBUG_TRACE; `.playwright-trace/` gitignored per Plan 03-01 |
| T-03-03-04 (gh secret --body in argv) | accept | Standard pattern; documented in CLAUDE.md Step 5 as the simplest form on a personal dev laptop |
| T-03-03-05 (login selector drift) | mitigate | Generic selector list; on selector failure raises InvalidCredential (typed exception surfaces in next scan summary) |
| T-03-03-06 (hung login DoS) | mitigate | All login operations bounded — page.fill/click are sync; wait_for_timeout(3000ms); outer 60s navigation timeout is upper ceiling |
| T-03-03-07 (gh secret operations not logged in repo) | accept | GitHub-side audit log covers `secret set` / `list` / `delete`; repo mirroring would defeat SEC-03 |
| T-03-03-08 (README SEC-06 audit table reveals credentialed adapters) | accept | Table lists adapter names + secret-name PATTERNS, not company names; per-company secret existence is gated by `gh secret list` repo-read access |
| T-03-03-09 (login probe by Claude CLI hits target site unauthenticated) | accept | Single pre-auth GET is indistinguishable from a normal user pre-auth browse; no credentials in the probe |
| T-03-03-10 (CLAUDE.md documentation drift) | mitigate | `test_claude_md_documents_5_step_flow` asserts all 5 step headings exist; doc-rot fails the test on next CI run |

## SEC-03 Enforcement (Structural)

```bash
$ command grep -c 'traceback.format_exc' src/adapters/playwright_fallback.py
0
```

Mirrors Phase 1 + 2 + Plans 03-01 + 03-02 discipline (sixth re-proof). Exception messages from `_attempt_login` contain ONLY:

- Adapter name (`Playwright`)
- Company name (`company.name`)
- Env var NAMES (`SCRAPER_<COMPANY>_EMAIL`, `SCRAPER_<COMPANY>_PASSWORD`) — public information that appears in README SEC-06 + CLAUDE.md
- Diagnostic context strings

Never: headers, response body, the env-var VALUES, the typed email, the typed password, the chained traceback.

## ADP-14 / ADP-15 Open-Closed Re-Proof (6th time)

```bash
$ git diff 7d5dd0a^..HEAD -- \
    src/adapters/greenhouse.py src/adapters/lever.py src/adapters/ashby.py \
    src/adapters/smartrecruiters.py src/adapters/workday.py src/adapters/apple.py
(empty)
```

Plan 03-03 modified only:
- `src/adapters/base.py` — APPEND-ONLY (InvalidCredential added; 4 Phase 1 typed exceptions unchanged)
- `src/adapters/playwright_fallback.py` — its own creation from Plan 03-02 (credential flow extension)
- `src/main.py` — TWO single-line edits (import + catch tuple)
- 3 test files + 1 new test file
- CLAUDE.md, README.md

`tests/test_adapter_contract.py` (7 cases) continues to pass unchanged.

## Deviations from Plan

### 1. Ship 13 PlaywrightAdapter credential tests vs plan's "~7" target

Plan body enumerated 7 explicit credential tests. The implementation ships 13 to defend each documented behavior with its own regression signal:

- `_company_to_secret_prefix` split per case shape (3 instead of 1 — simple / hyphens / spaces) — D-02a translation is the public-facing convention; granular regression signal worth the test count.
- 1 extra SEC-03 leak audit (`test_invalid_credential_message_never_includes_credential_values`) with canary email + password substrings + `exc.__cause__ is None` assertion — directly defends D-02c "values never leak through traceback chain".
- 1 extra D-02a wiring test (`test_attempt_login_uses_uppercased_hyphen_translated_env_vars`) — proves the adapter actually USES `_company_to_secret_prefix` (not just defines it).
- 1 extra no-login regression (`test_no_login_form_skips_credential_path`) — proves the credential gate is silent on pages WITHOUT a login form (the common case).

### 2. `_company_to_secret_prefix` is a class @staticmethod, not a module-level helper

The plan's `<interfaces>` block uses a module-level `_company_to_secret_prefix(name: str) -> str`. The implementation puts it on `PlaywrightAdapter` as `@staticmethod`. Rationale: the function is solely consumed by the adapter that uses credentials; keeping it co-located with the credential surface improves discoverability and matches the existing pattern of `_detect_login_form` (which the plan also recommends as a class method, line 489 of the plan). Tests reference `PlaywrightAdapter._company_to_secret_prefix(...)` — unambiguous + consistent.

### 3. Initial-navigation `try/except PlaywrightTimeoutError: pass` before the credential gate

The plan body discussed two possible patterns for inserting the credential gate. The implementation does an initial `page.goto()` wrapped in `try/except PlaywrightTimeoutError: pass`, then `_detect_login_form` + `_attempt_login`, then the existing `with page.expect_response(...)` block which re-navigates inside. The initial-nav timeout is swallowed because the downstream XHR-intercept block has its own navigation+expect_response that may race a redirect successfully. This keeps the credential gate compatible with both the XHR-intercept happy path AND the DOM-fallback path — both downstream paths see an already-authenticated page when login was detected. No regression in the 22 Plan 03-02 tests.

### 4. Test count: 27 net (+4 base/orch + 13 playwright + 10 credential_flow) vs plan's "≥21" target

The plan's `<success_criteria>` enumerated 2 base + 1 orch + 7 playwright + 10 credential_flow = 20 minimum; 21 with the orchestrator-isolation test counted twice (Plan body lists it in both `tests/test_orchestrator.py` Task 1 and `tests/test_credential_flow.py` Task 3). The implementation lands BOTH (different scope: Task 1's is unit-level synthetic-adapter mock; Task 3's is integration-level real-companies.txt + 3-company scenario). Plus 6 extra in `tests/test_playwright_adapter.py` per Deviation #1.

### 5. test_typed_errors_are_distinct_classes count assertion bumped from 4 to 5

The pre-existing Phase 1 test asserted `len({SiteBlocked, SchemaDrift, PlaywrightTimeout, MissingCredential}) == 4`. Adding `InvalidCredential` to the set bumps the count to 5. This is a SEMANTIC update of the existing test (preserving the test ID + adding the new class), not a deletion — same precedent as Plan 02-03's `test_experience_min_above_ceiling_overrides_title_pass` -> `test_is_early_career_ignores_experience_min_per_d02` rewrite and Plan 03-02's two `NoAdapterFound` -> `PlaywrightAdapter dispatch` rewrites.

### 6. Used `git commit -F /tmp/...` for all 3 tasks

Heredoc bash quoting fails on the apostrophe in plan-body text (`Claude's discretion`, `it's`, etc.). All 3 commits used file-based commit messages via `git commit -F /tmp/commit-03-03-task<N>.txt`. Same precedent as Plan 02-03 (Tasks 2 + 3 used this pattern after a heredoc quoting failure).

## Auth Gates

None encountered. The credential-flow code is exercised by mocked Playwright pages (HTML routes via `_test_route_handler`) and `monkeypatch.setenv` — no real GitHub secrets, no real gh CLI calls, no real network. The CLAUDE.md + README.md docs DESCRIBE the gh CLI flow but the tests only assert documentation invariants, not gh execution.

## Stub Tracking

None — the adapter raises typed exceptions in all credential failure modes; documentation tests assert real substring presence in real files; the integration test uses a real `_scrape_one` invocation with mocked adapters. No placeholders, no empty values flowing to UI.

## Threat Flags

No new security surface beyond what the plan's `<threat_model>` enumerated. The credential branch adds the SCRAPER_<COMPANY>_<KIND> env-var read path — covered by T-03-03-01 / 02 / 03 (all mitigated structurally).

## Phase 3 REQ-IDs Closure Confirmation

All 6 Phase 3 REQ-IDs closed:

| REQ-ID | Closed in | What |
|--------|-----------|------|
| ADP-09 | Plan 03-02 | PlaywrightAdapter — XHR-intercept first + DOM-selector fallback + 60s timeout |
| ADP-10 | Plan 03-02 | playwright-stealth on by default + per-site opt-out via hint |
| SEC-01 | Plan 03-03 | Claude inline-prompt flow documented in CLAUDE.md Step 5 |
| SEC-02 | Plan 03-03 | SCRAPER_<COMPANY_UPPERCASE>_<KIND> naming enforced in PlaywrightAdapter._attempt_login + _company_to_secret_prefix |
| SEC-04 | Plan 03-03 | gh secret list names-only doc in README + CLAUDE.md |
| SEC-06 | Plan 03-03 | README.md per-adapter secret-audit table |

**Phase 3 is execute-complete.** Next: `/gsd-verify-phase 3` (or equivalent verification gate). Phase 1 + Phase 2 remain awaiting verification.

## What's Next

Phase 4 (per ROADMAP.md):
- NORM-02 (salary extraction)
- NORM-03 (location normalization)
- OUT-09 (Source Health footer)

Phase 4 implementation may benefit from running the verifier on Phase 1 + 2 + 3 first to catch any cross-phase drift.

## Self-Check: PASSED

**Files claimed to exist:**

- src/adapters/base.py — FOUND
- src/adapters/playwright_fallback.py — FOUND
- src/main.py — FOUND
- tests/test_adapter_base.py — FOUND
- tests/test_orchestrator.py — FOUND
- tests/test_playwright_adapter.py — FOUND
- tests/test_credential_flow.py — FOUND
- CLAUDE.md — FOUND
- README.md — FOUND

**Commits claimed to exist:**

- 86397ed — FOUND
- 9e8a6dd — FOUND
- 87912d7 — FOUND
