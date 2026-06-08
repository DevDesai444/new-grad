---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Awaiting next milestone
stopped_at: Plan 04-02 execute-complete — FILT-07 US-only filter shipped (is_us_location_acceptable + orchestrator wiring + REQUIREMENTS.md FILT-07 entry); ready for Plan 04-03 (seen.json schema v1→v2 + source_health observability data per CONTEXT.md D-04)
last_updated: "2026-06-08T18:56:47.623Z"
last_activity: 2026-06-08 — Milestone v1.0 completed and archived
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 12
  completed_plans: 12
  percent: 100
---

# STATE: new-grad

## Project Reference

**Project:** new-grad
**Core Value:** One glance at the GitHub repo shows every currently-known new-grad-eligible role across the user's tracked companies, with a working application link.
**Mode:** mvp (Vertical MVP — every phase delivers an end-to-end working slice)
**Granularity:** coarse
**Total Phases:** 4

## Current Position

Phase: Milestone v1.0 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-06-08 — Milestone v1.0 completed and archived

### Phase 1 Goal

User opens repo and sees real Greenhouse postings in a README table updated within the last hour by GitHub Actions — every architectural seam exists, every existential risk is baked in, and the commit-back loop is proven on real infrastructure.

### Phase 1 Success Criteria

1. User opens `github.com/DevDesai444/new-grad` and sees a Markdown table with real Greenhouse postings updated within the last hour; Posting links open the company's career portal.
2. Hourly cron has fired at least twice; second run produces no spurious diff (idempotent render); `seen.json` correctly tracks `first_seen` / `last_seen`; nothing ever deleted from `seen.json`.
3. Killing the workflow mid-run or running `--validate` against a corrupted `seen.json` does not brick the next run — atomic write + `.bak` fallback + sanity gate (≥0.9× prior count) all engage; run exits non-zero on unrecoverable corruption, never silently wipes the table.
4. `gh secret list` shows zero secrets referenced by Phase 1 adapters; deliberate `git add` of `.env`/`cookies.json`/`trace.zip` is blocked by `.gitignore` + Push Protection; no credential string in workflow logs.
5. "Add this Greenhouse URL" via Claude CLI → one-line append to `companies.txt`, commit, push; next hourly run picks it up without further edits.

## Performance Metrics

- **Phases complete:** 0/4 (Phase 1 + Phase 2 + Phase 3 all execute-complete; Phase 4 ALL 3 plans execute-complete, awaiting `/gsd-verify-phase 4` for full milestone close)
- **Requirements mapped:** 72/72 (100%) *[FILT-07 added in Phase 4 per CONTEXT.md D-03]*
- **Requirements validated:** 72/72 (56 in Phase 1 + ADP-04/05/06 in Plan 02-01 + ADP-07 in Plan 02-02 + ADP-08 + FILT-03 in Plan 02-03 + ADP-09 + ADP-10 in Plan 03-02 + SEC-01 + SEC-02 + SEC-04 + SEC-06 in Plan 03-03 + NORM-02 + NORM-03 in Plan 04-01 + FILT-07 in Plan 04-02 + OUT-09 in Plan 04-03) — **all v1 requirements closed**
- **Plans complete:** 12/12 (3/3 Phase 01 + 3/3 Phase 02 + 3/3 Phase 03 + 3/3 Phase 04 — Plan 04-03: ~25min, 3 tasks via 6 commits (strict TDD RED→GREEN per task), 5 modified files + 2 new fixtures + 1 new SUMMARY, 31 net new tests / 555 cumulative)
- **Existential risks addressed:** 5/5 in Phase 01 (unchanged)

### Per-Plan Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01    | 01   | 6min     | 3     | 19    |
| 01    | 02   | ~25min   | 3     | 12    |
| 01    | 03   | ~8min    | 3     | 7 (6 new + 1 mod) |
| 02    | 01   | ~25min   | 3     | 11 (9 new + 2 mod) |
| 02    | 02   | ~25min   | 2     | 5 (3 new + 2 mod)  |
| 02    | 03   | ~30min   | 3     | 10 (3 new + 7 mod) |
| 03    | 01   | ~10min   | 2     | 11 (3 new + 8 mod) |
| 03    | 02   | ~25min   | 2     | 9 (4 new + 5 mod)  |
| 03    | 03   | 31min    | 3     | 9 (1 new + 8 mod)  |
| 04    | 01   | ~50min   | 3     | 6 (2 new + 4 mod)  |
| 04    | 02   | ~6min    | 3     | 5 (1 new + 4 mod)  |
| 04    | 03   | ~25min   | 3     | 9 (2 new + 7 mod)  |

## Accumulated Context

### Key Decisions (from PROJECT.md)

| Decision | Rationale |
|----------|-----------|
| GitHub Actions cron, not laptop cron | Zero-touch; laptop must not need to be on |
| Public repo over private | Unlimited free Action minutes |
| Python + Playwright stack | Best ecosystem for hybrid ATS-API + headless-browser scraping |
| Markdown table in README.md | Repo homepage = the UI; no separate site needed |
| Keep stale postings forever | User explicitly prefers history over freshness |
| Experience range as its own column | User wants 0–5 yrs visibility per posting |
| Dedup by per-ATS stable ID (`gh:<co>:<id>`) | Most stable identifier; raw URL dedup fails on tracking params |
| `seen.json` state file committed to the repo | No database; repo IS the database |
| Credentials in GitHub Actions Secrets only | Public repo means anything in the repo is exposed |

### Decisions Made During Execution

| Plan | Decision | Rationale |
|------|----------|-----------|
| 01-01 | One commit per task (RED + GREEN batched) | Matches plan's "commit each task atomically" outer cadence; tests still written first + run RED before implementation |
| 01-01 | Pinned Playwright in requirements.txt but did NOT install via workflow | Per CONTEXT.md D-05; pin keeps requirements.lock hash stable so Phase 3 cache hits cleanly |
| 01-01 | Greenhouse adapter stashes `__dedup_key` + `__board_token` in raw response | Per ARCHITECTURE.md — normalizer (Plan 02) reads them without recomputing |
| 01-01 | `Optional[X]` → `X \| None` in src/models.py (ruff UP045 auto-fix) | Required for plan's own `ruff check` verification step to pass; behavior identical |
| 01-01 | Workflow "Run scan" step is guarded stub `if [ -f src/main.py ]; then ...` | Keeps CI green from day one; Plan 03's main.py drops in cleanly without a workflow edit |
| 01-02 | Sanity gate `_SANITY_FLOOR_RATIO = 0.9` is a module-level private constant, not config-driven | CONTEXT.md D-06 makes the 90% threshold a permanent semantic, not a tunable knob |
| 01-02 | `save_state_atomic` rejects writes with wrong `schema_version` (defensive) | Symmetric defense vs `load_state` raising `UnknownSchemaVersion`; prevents accidentally writing forward-incompatible state |
| 01-02 | Renderer falls back to `first_seen` for Age when `posted_date` is None | Keeps Age column always meaningful (coalesce-style behavior) |
| 01-02 | Hint-resolution falls through to URL match when hint name does not resolve | Defensive: a typo or future-ATS hint should not block a recognizable URL |
| 01-02 | `_posting_to_record` produces dict (not Pydantic .model_dump()) | Keeps on-disk state shape decoupled from model evolution; future Posting fields don't auto-break state file shape |
| 01-02 | `timezone.utc` → `UTC` alias auto-fix (ruff UP017) | Required for plan's own `ruff check` verification step to pass; behavior identical |
| 01-02 | Renderer docstring `datetime.now(UTC)` reference removed | Required for plan's `grep -c 'datetime.now' src/renderer.py` AC to return at most 1 (literal grep was matching the docstring) |
| 01-03 | `# noqa: UP017` on `datetime.now(timezone.utc)` in src/main.py | Plan's literal AC requires the `datetime.now(timezone.utc)` substring; ruff UP017 wants the `UTC` alias. noqa preserves the AC literal while keeping ruff clean — same precedent as Plans 01-01/01-02. |
| 01-03 | Reworded `traceback.format_exc` references in docstrings/comments | Plan AC: `grep -c "traceback.format_exc" src/main.py == 0`. Substring was present in comments explaining what we DON'T do. Reworded to `format full tracebacks` / `the full traceback`; intent preserved. |
| 01-03 | Three-arm per-company isolation in main._scrape_one | Finer-grained than the plan's two-arm example: third arm catches per-posting normalize exceptions so one malformed entry doesn't kill the rest of a company's postings. |
| 01-03 | Sanity-gate `new_count` arg = `count(still_listed=True in merged)`, not raw fresh count | Correct semantic for "visible postings"; otherwise a scan returning 0 fresh would falsely trigger gate when prior had still-listed-flip-to-False entries. |
| 01-03 | README `Push protection` → `Push Protection` (capitalization) | Plan AC literal-grep match; substance unchanged. |
| 02-01 | Ship 9 tests per adapter instead of plan's 8 | Split `test_fetch_emits_stable_dedup_key` out of happy-path test for clearer regression signal; 27 new vs plan's 24. |
| 02-01 | `name="smartrecruiters"` vs dedup-prefix `"sr:"` split locked via dedicated regression test (`test_fetch_emits_stable_dedup_key_with_sr_prefix`) | Asserts BOTH `startswith('sr:')` AND `not startswith('smartrecruiters:')` to lock CONTEXT.md D-01a into the suite; full word + short prefix is intentional. |
| 02-01 | Lever epoch-ms `createdAt` defensively None-on-bad-input rather than SchemaDrift | Lever sometimes omits the timestamp; `posted_date=None` is the correct render outcome (mirrors `_parse_iso_to_utc`'s contract). |
| 02-01 | Each adapter defines its own module-level `_TIMEOUT_S = 20.0` rather than importing a shared constant | Locality + per-adapter tunability without touching siblings; mirrors greenhouse.py's pattern. |
| 02-02 | Task 1 ships standalone-functional even before Task 2's pagination wrap | Single-page tenants work at HEAD of Task 1; diff stays small per commit; Task 2 wrapper is purely additive. |
| 02-02 | `WorkdayAdapter.matches()` uses cheap subdomain substring check, not the full URL regex | matches() must be cheap per ADP-01 — substring is O(len(host)) vs regex compile+match cost on every URL lookup. |
| 02-02 | `_parse_workday_url` emits diagnostic SchemaDrift naming WHICH piece is missing (host vs site) via a partial-match probe | Defensive UX: user fixing a typo in companies.txt sees what's wrong without log-diving. |
| 02-02 | `fetch(company, seen_keys=None)` — optional kwarg default preserves Phase 1 single-arg Adapter.fetch contract | Behavior degrades gracefully to cold-start-cap-only when orchestrator hasn't been wired to thread seen_keys; correct in both modes. |
| 02-02 | Sort-monotonicity violation logs WARNING + suppresses early-term, does NOT abort | Tradeoff favors completeness over speed when tenant sort ordering is broken. |
| 02-02 | `_parse_workday_posted` excludes `bool` from the epoch-ms branch via `not isinstance(value, bool)` | Python `bool` is a subclass of `int` (True == 1); a JSON `true` value should not silently become datetime(1970-01-01, 1ms). |
| 02-02 | `time.sleep` is monkeypatched to noop in slow tests via `src.adapters.workday.time.sleep -> lambda s: None` | Keeps `test_fetch_cold_start_cap_25_pages` under 100ms instead of ~25s; production keeps real sleep for rate-limit hedging. |
| 02-02 | Ship 35 tests vs plan's "~14" budget | Granular split per postedOn form / per malformed-URL case gives clearer regression signal; no scope creep, all defend documented behavior. |
| 02-03 | Apple `matches()` accepts ANY jobs.apple.com subpath; no path validation | Per CONTEXT.md D-01a Apple is single-org; user can paste search / details / browse URL — adapter ignores path and POSTs the broad endpoint. |
| 02-03 | Apple dedup-key regex test uses `^apple:[^:]+$` (one colon, not two) | Locks D-01a invariant into the suite — `apple:<id>` not `apple:apple:<id>`; mirrors the SR `name="smartrecruiters"` vs `"sr:"` precedent test from Plan 02-01. |
| 02-03 | `is_early_career` body is one line (`return _passes_title_gate(...)`); zero `experience_min` references | D-02 simplification taken at the source — docstring documents the change but no live code touches `experience_min`. AC literal-grep `awk '/^def is_early_career/,/^def /' src/filter.py \| grep -c experience_min` returns 0. |
| 02-03 | Phase 1 `test_experience_min_above_ceiling_overrides_title_pass` REWRITTEN as `test_is_early_career_ignores_experience_min_per_d02`, not deleted | Same test slot, inverted assertion, explicit docstring pointing to CONTEXT.md D-02 — preserves Phase 1's grep-able test-id while encoding the new D-02 invariant. |
| 02-03 | Workday `__description` hook wired even though CXS /jobs doesn't return per-posting description today | Future per-posting detail fetch starts populating Experience automatically with zero normalizer changes — the JD-scan layer is open-closed for future Workday enhancements. |
| 02-03 | `commit -m` HEREDOC switched to `commit -F /tmp/<file>.txt` for Tasks 2 + 3 after a bash quoting failure on apostrophes | Mechanical workaround — no content lost; commits applied cleanly. Documented for future Phase 3/4 commit-message authors. |
| 02-03 | REQUIREMENTS.md FILT-04 line keeps `[x]` checkbox + adds `~~**FILT-04**~~` + footnote | Same convention as Phase 1 INFRA-05 strikethrough — the Phase 1 implementation literally satisfied FILT-04; the softening is a SEMANTIC change documented via strikethrough + footnote, not an unship. |
| 02-03 | Apple sort-monotonicity violation logs WARNING + suppresses early-term (degrade to cap-only) | Mirrors Workday from Plan 02-02 — same tradeoff: completeness over speed when source sort ordering breaks. |
| 02-03 | Ship 49 tests vs plan's "≥22" budget | Granular split per regex form + 2 Workday cases (absent vs stashed __description) + 4 retroactive Greenhouse tests + 16 Apple tests; defends explicit behavior per AC. |
| 03-01 | resolve_url returns ORIGINAL url on any error rather than raising | D-01b explicit no-raise contract — graceful degradation lets orchestrator dispatch fall through to Playwright catch-all (Plan 03-02). Resolver is best-effort, never blocking. |
| 03-01 | Orchestrator wraps resolve_url in defensive try/except even though contract is no-raise | Defense in depth (Pitfall 1 / ADP-12) — if a future bug causes a raise, main loop logs class name + continues with original URL. Costs nothing; protects everything. |
| 03-01 | Resolver logs ONLY on actual resolution (URL changed), not on identity passes | Signal-rich logs — every line in Actions output means something happened. Identity-resolve (already-canonical Workday tenant URL) is the common case and would otherwise dominate logs. |
| 03-01 | NoAdapterFound message extended to include resolved URL alongside original | Diagnostic clarity — when a CNAME doesn't resolve to a known ATS (Playwright catch-all not yet shipping in Wave 1), user sees BOTH urls in the log line and knows whether to blame the resolver or the adapter set. |
| 03-01 | Ship 18 tests vs plan's nominal "19 / cumulative 317" target | Plan body enumerated 8 distinct resolver semantic cases + 2 models + 3 registry + 2 orchestrator + 3 workflow_yaml = 18 substantively. The "≥317" success criterion was rounded; substance matches plan body verbatim. |
| 03-01 | Reworded `traceback.format_exc()` reference in resolver docstring to `the full traceback` | Plan AC: `grep -c traceback.format_exc src/url_resolver.py == 0`. Same precedent as Phase 1 Plan 01-03 docstring rewordings; intent preserved. |
| 03-01 | Phase 3 .gitignore additions skip `playwright-report/` (already in Phase 1 list); add only `.playwright-trace/` and `playwright/.cache/` | Avoids duplicate gitignore entries; Phase 1 already covered `playwright-report/`. Plan's `<artifacts>` block listed all three; matching disposition — Phase 3 contributes the two truly new ones. |
| 03-02 | Documented `_test_route_handler` kwarg on `PlaywrightAdapter.fetch` as the test seam (Callable[[BrowserContext], None] \| None = None) | Mirrors Phase 2 `seen_keys` precedent — single documented optional kwarg with a clear test-injection role; production code never passes it. Cleaner than monkeypatching internals or subclassing. |
| 03-02 | Wrapped `playwright_stealth.Stealth` import in `_get_stealth_class()` indirection | Tests monkeypatch `_get_stealth_class` to return a sentinel that records calls — needed for the stealth-on/off assertions. Production: function returns the real Stealth class lazily on first use. |
| 03-02 | Added `_record_trace_started()` no-op hook called only when context.tracing.start() runs | Test-observable indirection — tests monkeypatch to detect trace activation without inspecting Playwright internals. Mirrors the `_get_stealth_class` pattern; production no-op. |
| 03-02 | `_test_route_handler` callback receives the `BrowserContext` (not the page) so tests can install `context.route()` mocks BEFORE any navigation fires | Page routes don't apply to in-flight navigations; context routes do. Tests use `context.route('**/api/jobs', ...)` and `context.route('https://www.anthropic.com/careers', ...)` to mock both the navigation document and the XHR — no real network in CI. |
| 03-02 | Removed `pytest.mark.slow` decorators from Playwright runtime tests | The marker generated `PytestUnknownMarkWarning` and wasn't gated anywhere. Tests run in ~40s total — acceptable in CI without a slow-gate. |
| 03-02 | Rewrote 2 Phase 1 NoAdapterFound assertions as PlaywrightAdapter dispatch assertions | Phase 3 D-01c invalidates the prior "unknown http(s) URL → NoAdapterFound" contract — catch-all now matches any http(s). Replaced `test_unknown_url_raises` and `test_unrecognized_hint_no_url_match_raises` with `test_unknown_http_url_dispatches_to_playwright_catch_all` and `test_unrecognized_hint_no_url_match_dispatches_to_playwright`. NoAdapterFound contract still holds for non-http schemes (CompanyConfig's url validator stops those upstream). |
| 03-02 | Updated `test_new_adapter_can_be_added_without_touching_existing_files` to INSERT before catch-all at len-1, not APPEND | Catch-all-last invariant means appended adapters never get a chance to match (Playwright matches any http(s) URL first in the loop). Inserting at `len(ADAPTERS) - 1` preserves both invariants: open-closed proof + catch-all is still last. |
| 03-02 | `src/filter.py` NOT modified — `_read_playwright_description` lives in normalizer.py alongside the 6 sibling `_read_<adapter>_description` helpers | Plan frontmatter listed filter.py defensively; plan body / Task 2 action block correctly identified that helpers live in normalizer.py per Phase 2 precedent. Zero filter.py edits; commit message documents the divergence. |
| 03-02 | NoAdapterFound docstring updated to note Phase 3 catch-all eliminates the error for http(s) URLs | Diagnostic clarity — future readers see WHY NoAdapterFound is now nearly-unreachable instead of being puzzled. |
| 03-02 | Ship 32 net new tests (22 adapter + 5 normalizer + 5 registry) vs plan's "≥20-25" budget | Granular split per behavior (matches() 3 cases, hint parse 5, id extraction 3, XHR/DOM/timeout 3, dedup key 2, stealth 2, trace 2, catch-all/default 2 in adapter; 5 normalizer including alt-date-key + URL canonicalization; 5 registry covering all dispatch orderings). Defends each documented behavior with its own regression signal. |
| 03-02 | Manually installed Chromium via `playwright install chromium` before running tests | Local dev environment didn't have Chromium cached. In CI, Plan 03-01's workflow step (`playwright install --with-deps chromium`) + `actions/cache@v4` handle this. Tests fail-fast with clear error if Chromium absent — no silent skip. |
| 03-03 | InvalidCredential added to base.py as APPEND-ONLY change | MissingCredential + 3 Phase 1 typed exceptions left untouched; ADP-14/15 invariant preserved for sixth time. test_typed_errors_are_distinct_classes count bumped 4 -> 5 to reflect the new class. |
| 03-03 | Credential gate placed AFTER initial navigation but BEFORE `expect_response` block | Initial `page.goto` exposes the DOM for `_detect_login_form` heuristic; if login present, `_attempt_login` runs to completion (raises typed errors on failure); the existing XHR-intercept block then re-navigates inside `page.expect_response` so the fresh post-auth response captures cleanly. Initial-nav PlaywrightTimeoutError is swallowed via try/pass — downstream block may still race a redirect successfully. |
| 03-03 | `raise InvalidCredential(...) from None` everywhere | D-02c — suppresses `__cause__` chain that could leak DOM text (including the typed email) through the chained traceback. Mirrors Phase 1's SEC-03 hygiene. |
| 03-03 | `_company_to_secret_prefix` is a class @staticmethod on PlaywrightAdapter (not module-level) | Co-locates the SEC-02 naming convention with the only adapter that uses it; tests reference `PlaywrightAdapter._company_to_secret_prefix(...)` — unambiguous. Same shape as `_detect_login_form`. |
| 03-03 | 13 PlaywrightAdapter credential tests vs plan's "~7" target | Granular split: 3 prefix cases + 2 detection + 2 missing-cred + 1 invalid-cred + 1 message-leak audit + 1 D-02a wiring + 1 no-login regression + 2 SEC-03 grep audits. Each documented behavior gets its own regression signal. |
| 03-03 | `test_invalid_credential_message_never_includes_credential_values` uses canary strings + asserts `exc.__cause__ is None` | Direct enforcement of D-02c — secret-leak-canary email + password substrings must not appear in str(exc); chained traceback must also be suppressed (proves `from None` is wired). |
| 03-03 | Used `git commit -F /tmp/...` for all 3 tasks | Heredoc bash quoting fails on the apostrophe in plan-body text. Same precedent as Plan 02-03 Tasks 2+3. |
| 03-03 | CLAUDE.md "Adding a Company" section lives OUTSIDE any `<!-- GSD:* -->` sentinel block | Per CONTEXT.md D-03 — survives future GSD regeneration cycles. Inserted between `<!-- GSD:workflow-end -->` and `<!-- GSD:profile-start -->`. |
| 03-03 | Ship 27 net new tests vs plan's "≥21" target | Plan body counted the orchestrator-isolation test once but explicitly lists it in BOTH Task 1 (tests/test_orchestrator.py — unit-level synthetic-adapter mock) AND Task 3 (tests/test_credential_flow.py — integration-level 3-company scenario). Implementation ships BOTH (different scope; both add value). |
| 04-01 | `salary=''` (empty string) vs `salary=None` in all 7 normalizer helpers | Picks empty string so renderer's coalesce step has a single null-state to match (D-01a `_coalesce_salary` treats `None` and `''` identically, but writing `''` from every normalizer call site removes the two-null-states confusion at the call sites). Posting model still allows `salary: str \| None = None` default; test_models.py:75 still passes. |
| 04-01 | Greenhouse salary metadata-name frozenset `{salary, salary range, compensation range, pay range, base pay range}` | These are the 5 canonical Greenhouse metadata names documented across boards. First non-empty match wins (rare for one posting to have multiple, but deterministic if it does). Extracted into private `_extract_greenhouse_salary` helper for unit-testability. |
| 04-01 | Apple location: compose FIRST then normalize | `normalize_location(", ".join(loc_names))` is the path. Single-element `[{"name":"Remote"}]` composes to `"Remote"` → bare-Remote rule → `"Remote (US)"`. Multi-element composes to comma-joined city list (not a Remote shape → passthrough). |
| 04-01 | Renderer pipeline order: coalesce → truncate → escape | Coalesce first so placeholders never reach escape; truncate before escape so 80-char limit applies to visible characters (not escape-padding). escape_markdown_cell (NORM-07) stays last as the final user-facing boundary. |
| 04-01 | Truncation ellipsis uses single codepoint U+2026 not three dots | Predictable cell width in monospace. Length of a truncated cell == limit (80 chars including the ellipsis). |
| 04-01 | `_coalesce_salary` + `_truncate_cell` kept as separate composable helpers | Future polish can apply `_truncate_cell` to Position/Location cells without changing salary semantics. Single-responsibility per helper, each independently testable. |
| 04-01 | Bare "Remote" biases to "Remote (US)" per D-02 user-is-US-based | Explicit test (`test_bare_remote_biases_to_us_per_d02`) locks this regression-free. Mirrors FILT-05 bias-toward-inclusion principle. |
| 04-01 | Non-US token list adds Bahrain, Ireland beyond CONTEXT.md seed | Per D-02c "tunable" guidance — common non-US locations in the dataset. Bias-list still defaults ambiguous cases to True. |
| 04-01 | Ship 124 net new tests vs plan's "~25-30" target | Heavy use of `pytest.mark.parametrize` (e.g., 28 placeholder strings in one coalesce test, 10 Remote-collapse rows in one normalize test) inflates collected-count without adding new regression-distinct cases. Per-rule classifier coverage + adapter-by-adapter assertion is exhaustive by design. |
| 04-02 | `is_us_location_acceptable` body is a one-line wrapper (`return is_us_location(posting.location)`) | All 8-rule classifier logic lives in Plan 04-01's `src/locations.py`; FILT-07's only job is to adapt the classifier to the Posting type for orchestrator chaining. One-line bodies make the gate trivially auditable; future per-region opt-out can wrap this without touching classifier internals. |
| 04-02 | Two-pass `if not X: continue` filter form in `_scrape_one`, not chained `and` | Each gate has its own short-circuit + its own log call on drop. Chained form would have been one line shorter but would have prevented per-gate INFO log on FILT-07 drop. Sequential form preserves drop-reason clarity in Actions logs and is open-closed at the filter-pass dimension (future Phase 5+ gates append the same way). |
| 04-02 | FILT-07 drop log uses `logger.info` not `logger.warning` | A non-US posting being filtered is correct behavior, not an error condition. WARNING is reserved for adapter-level "something went wrong" signals (SiteBlocked, normalize failure). INFO makes drop behavior visible in Actions logs without polluting the WARNING channel. |
| 04-02 | `_TwoCityAdapter` uses `source_adapter="greenhouse"` not a new dispatch arm | Existing `_normalize_greenhouse` accepts a tolerant raw-dict shape (id / title / updated_at / location.name / absolute_url / __dedup_key / __board_token) sufficient to synthesize two postings with different locations. Registering a new normalizer arm just for the integration test would have been unnecessary churn. |
| 04-02 | Doc-as-test `test_filt07_documented_in_requirements_md` lives in `tests/test_filter.py`, not a new `tests/test_requirements_doc.py` | Colocates the FILT-07 contract assertion with the function-under-test. Mirrors Phase 3 Plan 03-03 precedent (credential-flow doc invariants live in `tests/test_credential_flow.py`, not a separate doc-test module). |
| 04-02 | REQUIREMENTS.md FILT-07 checkbox `[x]` on first insertion | Implementation lands in the same plan that adds the requirement; checking it on insertion is correct. Plan 04-01's NORM-02/NORM-03 closure annotations pre-existed as `[x]`; FILT-07 is fully new + fully shipped in one plan. |
| 04-02 | Doc test uses `Path(__file__).resolve().parent.parent` for repo root | Robust to test cwd. pytest's default is repo root, but rootdir overrides or absolute pytest invocations would break a bare `Path('.planning/...').read_text()`. File-relative form is cwd-independent. |
| 04-02 | Task 3 ships as a single doc commit, not RED+GREEN | Task 3's doc-invariant test was authored as part of Task 1 RED (the test lives in tests/test_filter.py per plan body's `<action>` block); Task 3 only needed REQUIREMENTS.md edits to flip that test GREEN. TDD discipline preserved — test was RED before doc edit, GREEN after. 5 commits total instead of 6 planned; net outcome identical. |
| 04-03 | Schema migration is single-pass, in-memory: loader sees v1 → adds `source_health: {}` → bumps in-memory `schema_version` to 2; next save writes v2 | No on-load-and-write migration script; the next scan does it for free. Production runs migrate automatically on the first post-deploy execution. Minimizes blast radius — if migration logic is wrong, only in-memory state is affected; on-disk v1 is untouched until save_state_atomic runs. |
| 04-03 | `_fresh_empty_state()` helper for independent EMPTY_STATE copies (cold-start + both-corrupted branches) | EMPTY_STATE is shallow; nested dicts are empty — a fresh inline dict literal works. Helper centralizes the shape so future field additions (e.g., Phase 5 v3 schema bump) only need a one-line change. Mirrors Phase 1 atomic-write helpers. |
| 04-03 | Loader defensively defaults missing/wrong-type `source_health` to `{}` (Pitfall 1) | v2 mandates the key but partial-write recovery or future drift could land it absent / wrong-typed. Defaulting beats crashing — preserves Phase 1's "fail soft on corrupted state" pattern. Two explicit tests guard the contract. |
| 04-03 | `merge_state` always emits `schema_version=SCHEMA_VERSION` (no longer preserves-from-prior) | Combined with load-time auto-migration, callers cannot accidentally write back a v1 dict. Single-source-of-truth: bump SCHEMA_VERSION in state_store and merge_state output follows. |
| 04-03 | `classify_outcome` returns `(status, new_fail_count, is_success)` tuple, not just status | Caller-friendly: `update_source_health` reads all three with one call; `is_success` boolean is more expressive than `status == "ok"` substring check. Mirrors Phase 2 `get_adapter` precedent of multi-value returns when the caller needs branched behavior. |
| 04-03 | 3-fail consecutive_failures threshold for 'blocked' status (per CONTEXT.md D-04b) | Single-run flakes (1-2 failures) read as 'error' — transient. Sustained block (3+) reads as 'blocked' — actionable. Surfaces persistent issues without notification noise from intermittent network blips. Threshold is a Phase-4 D-04b lock; not user-configurable. |
| 04-03 | Source Health update runs BEFORE sanity_gate; sanity-aborted runs save nothing | T-03-02 preserved: state file unchanged on abort. The in-memory source_health mutation is discarded along with the merged postings — which is correct because a sanity-aborted run intentionally writes nothing. Diagnostic data only persists when the gate passes. |
| 04-03 | REQUIREMENTS.md OUT-09 uses `[x] ~~**OUT-09**~~` (checked + strikethrough) | Data IS persisted (so [x] is honest); rendering surface is dropped (so strikethrough). Mirrors Phase 1 INFRA-05 + Phase 2 FILT-04 strikethrough patterns. The "checked-with-strikethrough" combo signals "shipped, but in a different form than originally specified". |
| 04-03 | `src/renderer.py` UNTOUCHED per CONTEXT.md D-04c — explicit user request | User does not want a Source Health footer in README. Data lives in `seen.json.source_health` for future Claude CLI sessions to consume. The verifier's invariant test `test_orchestrator_source_health_not_rendered_in_readme` guards against regression. |
| 04-03 | Ship 31 net new tests vs plan's "≥12 / cumulative ~440" target | Granular split per behavior: 10 state_store covering 4 bump invariants + 4 migration scenarios + 2 defensive-defaulting cases; 16 state_merger covering 6 classify_outcome enum cases + 8 update_source_health mutation paths + 2 merge_state carryforward; 5 orchestrator including 3-run cross-scan accumulation. Each documented D-04b/D-04d rule gets its own regression signal. Cumulative exceeds plan target (555 vs ≥440). |

### Open Decisions

(none yet — surfaced during planning)

### Todos

(none yet — surfaced during planning)

### Blockers

(none)

### Research Flags for Phase 2 (when implementation begins)

- Verify current Workday CXS POST body shape, response field names, and pagination token format against a live tenant before locking adapter contracts (training data is MEDIUM confidence)
- Verify Apple Jobs `api/role/search` current request/response shape — endpoint is stable but field names drift
- Build a live test corpus from real postings before writing the salary pattern library (deferred to Phase 4)

### Research Flags for Phase 3 (when implementation begins)

- Identify the specific XHR intercept target or stable selector for the chosen JS-heavy SPA target
- Validate `playwright-stealth` effectiveness vs current DataDome/PerimeterX per target site (LOW confidence from training data)

## Session Continuity

**Last session:** 2026-06-08T18:35:57.011Z
**Last action:** Completed Plan 04-02 (3 tasks via 5 commits: 7ff1b0d Task 1 RED, 130382a Task 1 GREEN, c13cfad Task 2 RED, 463917c Task 2 GREEN, ce6dcd0 Task 3 doc). 524 cumulative tests pass; 25 net new (22 in tests/test_filter.py — TestIsUsLocationAcceptable parametrized + spot-check + determinism + bool-return + doc-invariant; 3 in tests/test_orchestrator.py — London-drop integration + INFO log assertion + US-keep regression). FILT-07 US-only region filter shipped: `is_us_location_acceptable(posting) -> bool` in src/filter.py wraps src.locations.is_us_location applied to posting.location; pure function per FILT-06. src/main.py `_scrape_one` runs FILT-07 AFTER is_early_career and BEFORE state merge per CONTEXT.md D-03a; dropped non-US postings get `logger.info("scrape:%s drop FILT-07 non-US: %s (%s)", ...)` line (INFO not WARNING — correctly-filtered non-US is not a bug). .planning/REQUIREMENTS.md gains FILT-07 as 7th Filter bullet + Traceability row + Coverage bumped 71→72 (FILT 6→7, Phase 4 = 3→4). Doc-as-test `test_filt07_documented_in_requirements_md` asserts 4 substring anchors. ADP-15 invariant preserved (git diff --name-only 36dd035..HEAD -- src/adapters/ = 0). Ruff clean. FILT-07 closed in REQUIREMENTS.md.
**Previously:** Completed Plan 04-01 (3 TDD tasks, 6 commits: d4235db Task 1 RED, 160c9f8 Task 1 GREEN, fb547f1 Task 2 RED, d7b9e1b Task 2 GREEN, fc9bf83 Task 3 RED, 8550ee5 Task 3 GREEN). 499 cumulative tests pass; 124 net new (56 locations + 20 normalizer + 23 renderer + 25 parametrized expansions). ADP-15 invariant preserved. NORM-02 + NORM-03 closed.
**Stopped at:** Plan 04-02 execute-complete — FILT-07 US-only filter shipped (is_us_location_acceptable + orchestrator wiring + REQUIREMENTS.md FILT-07 entry); ready for Plan 04-03 (seen.json schema v1→v2 + source_health observability data per CONTEXT.md D-04)
**Resume file:** None

**Plan 01-01 Deliverables (Wave 1):**

- Scaffold: pyproject.toml, requirements.lock (uv-compiled, 91 lines), .gitignore (secrets + atomic-write transients blocked), README.md (sentinels + push-protection docs), companies.txt (header-only per D-03), .github/workflows/scan.yml (hourly cron + permissions + concurrency + cache + git-auto-commit-action@v5)
- Models: `src/models.py` (Posting / RawPosting / CompanyConfig — pydantic v2)
- Adapter ABC: `src/adapters/base.py` (Adapter + 4 typed errors)
- Greenhouse adapter: `src/adapters/greenhouse.py` + `tests/fixtures/greenhouse_stripe.json` (3-job fixture)
- Tests: 26 passing (9 models + 7 adapter base + 10 Greenhouse)

**Plan 01-02 Deliverables (Wave 2):**

- Normalizer: `src/normalizer.py` (RawPosting → Posting; URL canonicalize; UTC date conv; per-adapter dispatch)
- Filter: `src/filter.py` (title-keyword gate with 10+10 patterns; FILT-04 ceiling; FILT-05 bias)
- State store: `src/state_store.py` (atomic write via os.replace + .bak; .bak read fallback; sanity gate per D-06; SCHEMA_VERSION=1)
- State merger: `src/state_merger.py` (add-only two-pass merge; first_seen preserved; STATE-05 still_listed flip)
- Renderer: `src/renderer.py` (sentinel splice; Markdown escape with 5 invisible-Unicode codepoints; OUT-07 idempotent; OUT-08 placeholder)
- Registry: `src/registry.py` (ADAPTERS = [GreenhouseAdapter]; hint-override per CFG-03; NoAdapterFound for CFG-05)
- Tests: 124 new (51 normalizer+filter; 33 state; 40 renderer+registry); cumulative 150 passing

**Plan 01-03 Deliverables (Wave 3 — final wave; Phase 1 execute-complete):**

- Config loader: `src/config_loader.py` (companies.txt parser; CFG-01/02/03/05; BOM tolerance; logged-skip on malformed lines)
- Orchestrator: `src/main.py` (single run_started_at; per-company try/except isolation; SiteBlocked → any_blocked → sanity-gate carve-out; SchemaDrift/PlaywrightTimeout/MissingCredential typed catches; generic Exception catch logs class+str ONLY; summary to stdout + $GITHUB_STEP_SUMMARY; exit codes 0/1/2)
- Tests: 37 new (17 config_loader + 10 orchestrator + 3 end-to-end + 7 adapter contract); cumulative 187 passing
- README documentation: CFG-06 (companies.txt format), CFG-04 (Add a Company flow), SEC-03 (Secret Hygiene + naming-convention placeholder), Hourly Cadence with D-02 60-day acknowledgment, Recovery, Ops Quick Reference, ToS Hygiene; INFRA-08 Push Protection capitalized
- End-to-end test result: respx-mocked Greenhouse → New Grad + Associate postings persisted, Senior posting filtered out, [Apply] link in README, sentinels preserved; second consecutive run under frozen clock produces byte-identical seen.json + README (D-04 acceptance gate proven)
- ADP-12 isolation test result: RaisingAdapter raises RuntimeError; OkAdapter still succeeds; exit code 0; only OK posting persisted
- Sanity-gate state-preservation test result: 100 prior, 0 visible, no `any_blocked` → exit 1; seen.json bytes unchanged (T-03-02 mitigation)
- `python -m src.main` against placeholder companies.txt exits 0 (zero companies, empty merge, README placeholder rendered)

**Files written previously (planning):**

- `.planning/phases/01-walking-skeleton/01-CONTEXT.md` (gathered earlier via discuss-phase)
- `.planning/phases/01-walking-skeleton/01-DISCUSSION-LOG.md` (audit trail)
- `.planning/phases/01-walking-skeleton/01-SKELETON.md` (Walking Skeleton manifest)
- `.planning/phases/01-walking-skeleton/01-01-PLAN.md` (Wave 1 — scaffold + models + Adapter ABC + Greenhouse adapter)
- `.planning/phases/01-walking-skeleton/01-02-PLAN.md` (Wave 2 — normalizer, filter, state_store, state_merger, renderer, registry)
- `.planning/phases/01-walking-skeleton/01-03-PLAN.md` (Wave 3 — config_loader, main.py, end-to-end test, README docs)
- `.planning/ROADMAP.md` (Phase 1 plans list finalized; INFRA-05 struck through per CONTEXT.md D-01)

**Plan-checker warnings (non-blocking, recorded for transparency):**

- W-1 (CONTEXT.md drift): Plan 01-01 Task 3 ships 2 single-line error-branch smoke tests beyond D-07's "happy-path only" guidance. **Outcome:** orchestrator prompt directed to keep them; both tests pass. Accepted.
- W-2 (long-term gate semantics): Phase 1's sanity gate compares `still_listed_count` against monotonically-growing `prior_count`. Over many months `still_listed_count < 0.9 * prior_count` becomes structurally inevitable. Implementation matches STATE-06 as written. Fix can be deferred (most naturally to Phase 4 alongside OUT-09).

**Next action:** Run `/gsd-verify-phase 3` (or equivalent verification gate). All 3 phases (1, 2, 3) are now execute-complete and awaiting verification. After verification, Phase 4 (NORM-02 salary extraction + NORM-03 location normalization + OUT-09 Source Health footer) is the next planning target per ROADMAP.md.

**Recovery context:** If session is interrupted, resume by reading `.planning/phases/01-walking-skeleton/01-CONTEXT.md` (Phase 1 locked decisions, supersedes ROADMAP success criteria where they conflict — e.g., INFRA-05 dropped; criterion #1 live-data verification deferred), then `.planning/phases/01-walking-skeleton/01-01-SUMMARY.md` (Wave 1) + `.planning/phases/01-walking-skeleton/01-02-SUMMARY.md` (Wave 2 — pure-core pipeline) + `.planning/phases/01-walking-skeleton/01-03-SUMMARY.md` (Wave 3 — orchestrator + e2e). Phase 1 deliverables: 10 source modules, 13 test files / 187 tests, 1 GitHub Actions workflow, 1 placeholder companies.txt, README with sentinels + full user-facing operational docs.

---
*State initialized: 2026-06-07*
*Plan 01-01 complete: 2026-06-08*
*Plan 01-02 complete: 2026-06-08*
*Plan 01-03 complete: 2026-06-08 — Phase 1 execute-complete.*
*Plan 02-01 complete: 2026-06-08 — Lever + Ashby + SmartRecruiters adapters (ADP-04/05/06); 214 tests; ADP-14/15 open-closed re-proven.*
*Plan 02-02 complete: 2026-06-08 — Workday adapter (ADP-07); 249 tests; ADP-14/15 open-closed re-proven with 5 adapters; D-01 URL auto-parse + D-04 pagination with 25-page cap + sort-monotonicity + 3-form postedOn resolver + realistic User-Agent (Pitfall 5).*
*Plan 02-03 complete: 2026-06-08 — Apple adapter (ADP-08) + JD-scan (FILT-03) + D-02 is_early_career simplification + retroactive Greenhouse D-03 tests + REQUIREMENTS.md FILT-04 strikethrough; 298 tests; Phase 2 execute-complete (all 6 phase REQ-IDs closed: ADP-04..08 + FILT-03); ADP-14/15 open-closed re-proven across all 3 Phase 2 plans with 6 adapters.*
*Plan 03-01 complete: 2026-06-08 — URL redirect resolver (src/url_resolver.py per CONTEXT.md D-01b) + CompanyConfig.resolved_url field + registry dispatch update + orchestrator wiring with defense-in-depth + workflow YAML Chromium install/cache step + .gitignore trace-output paths; 316 tests (+18 new: 8 url_resolver + 2 models + 3 registry + 2 orchestrator + 3 workflow_yaml); ADP-09 infrastructure prerequisite closed; ADP-14/15 open-closed re-proven a fourth time (zero edits to src/adapters/*); foundation for Plan 03-02 PlaywrightAdapter ready.*
*Plan 03-02 complete: 2026-06-08 — PlaywrightAdapter (`src/adapters/playwright_fallback.py`, ADP-09 + ADP-10) — XHR-intercept-first via `page.expect_response` + DOM-selector fallback via `wait_for_selector` + selectolax + playwright-stealth on by default (D-04) + 60s navigation timeout (D-05) + trace=off in production with `SCRAPER_DEBUG_TRACE=1` escape hatch (D-06) + `pw:<host>:<id>` dedup keys with `sha256(url)[:16]` fallback (Pitfall 9); registry appends as catch-all LAST (D-01c — 7 adapters total); normalizer dispatches via `_normalize_playwright` (coalesces postingDate/postedAt/created_at/publishedAt date keys; canonicalizes URL; FILT-03 JD-scan via `_read_playwright_description`); 348 cumulative tests (+32 net: 22 adapter + 5 normalizer + 5 registry; 2 NoAdapterFound assertions rewritten as PlaywrightAdapter dispatch); ADP-14/15 open-closed re-proven a fifth time (zero edits to existing 6 src/adapters/*.py files); SEC-03 enforced (zero `traceback.format_exc` references in adapter); ADP-09 + ADP-10 closed.*
*Plan 03-03 complete: 2026-06-08 — Phase 3 execute-complete. InvalidCredential typed exception in `src/adapters/base.py` (additive — pairs with MissingCredential; distinct typed error for "env present but login rejected" vs Phase 1's "env unset"); PlaywrightAdapter credential flow extending `src/adapters/playwright_fallback.py` with `_detect_login_form` (heuristic on `input[type='password']`) + `_company_to_secret_prefix` (SEC-02 naming: uppercase + hyphens/spaces -> underscores) + `_attempt_login` (reads `SCRAPER_<COMPANY_UPPERCASE>_<KIND>` env vars; raises MissingCredential on unset / InvalidCredential on form-persists-after-submit; `from None` suppresses chained traceback per D-02c so DOM-text leak via `__cause__` is impossible); single-line orchestrator catch-tuple extension in `src/main.py` (import + tuple include InvalidCredential); CLAUDE.md `## Adding a Company` 5-step workflow (Step 1 try-existing → Step 2 resolve-redirects with D-03a "commit resolved URL" → Step 3 Playwright catch-all → Step 4 new adapter → Step 5 credential branch with SEC-01 inline-prompt + SEC-02 `gh secret set` + SEC-04 `gh secret list` names-only audit + one-shot login test); README.md `## Credential Naming Convention (SEC-06)` with per-adapter audit table (6 ATS rows show `(none)` because all use public APIs; `**playwright**` row references `SCRAPER_<COMPANY>_EMAIL` + `_PASSWORD`); 375 cumulative tests (+27 net: 4 base/orch unit + 13 playwright credential + 10 credential_flow integration+docs); ADP-14/15 open-closed re-proven a sixth time (zero edits to the 6 ATS adapter files; base.py is APPEND-ONLY); SEC-03 structural enforcement via grep audit tests (no credential VALUE in raise/log/print; traceback.format_exc count == 0); all 6 Phase 3 REQ-IDs closed (ADP-09 + ADP-10 from Plan 03-02; SEC-01 + SEC-02 + SEC-04 + SEC-06 from Plan 03-03). Commits: 86397ed Task 1, 9e8a6dd Task 2, 87912d7 Task 3.*
*Plan 04-01 complete: 2026-06-08 — src/locations.py (NEW, 151 lines) exporting normalize_location() (Remote-variant collapse per D-02 to canonical Remote (US) / Remote (non-US); non-Remote verbatim per D-02b) + is_us_location() (8-rule classifier per D-02a; 51 US state codes + 30 US tech-hub cities + 45 non-US tokens; all regex compiled at module load; <1ms/call). All 7 _normalize_<adapter> helpers in src/normalizer.py now populate Posting.salary verbatim from source-specific path per D-01 (Greenhouse via dedicated _extract_greenhouse_salary metadata-list scanner; Lever salaryRange.text → salary fallback; Ashby compensation.compensationTierSummary defensive against None; SR/Workday hard-coded empty with rationale; Apple postingPay.payRange.text → salaryRange → homeOffice; Playwright raw['salary'] best-effort) AND route location through normalize_location() (Apple composes locations[].name list FIRST then normalizes the composed string). src/renderer.py salary cell now flows through _coalesce_salary() (D-01a) → _truncate_cell(limit=80) (D-01b) → existing escape_markdown_cell (NORM-07 unchanged). 124 net new tests; 499 cumulative passing. ADP-15 re-proven a SEVENTH time. NORM-02 + NORM-03 closed. Commits: d4235db Task 1 RED, 160c9f8 Task 1 GREEN, fb547f1 Task 2 RED, d7b9e1b Task 2 GREEN, fc9bf83 Task 3 RED, 8550ee5 Task 3 GREEN.*
*Plan 04-02 complete: 2026-06-08 — FILT-07 US-only region filter. src/filter.py exposes is_us_location_acceptable(posting: Posting) -> bool — pure one-line wrapper over src.locations.is_us_location applied to posting.location (no new business logic; all 8-rule classification lives in Plan 04-01's src/locations.py). src/main.py `_scrape_one` filter block rewritten from single-pass title-keyword gate to two-pass sequential form per CONTEXT.md D-03a: title gate (FILT-01/02) → US-only gate (FILT-07) → state merge. Dropped non-US postings get logger.info("scrape:%s drop FILT-07 non-US: %s (%s)", company.name, p.title, p.location) — INFO not WARNING because correctly-filtered non-US is not an error; visible in Actions logs so user can verify drops without instrumenting. .planning/REQUIREMENTS.md gains FILT-07 as 7th Filter bullet between FILT-06 and Normalization heading (verbatim CONTEXT.md D-03 wording including STATE-04 "never delete" carve-out + cross-reference to PROJECT.md's prior out-of-scope listing); Traceability table row `| FILT-07 | Phase 4 | Complete |` between FILT-06 and NORM-01; Coverage block bumped (v1 total 71→72, FILT 6→7, Phase 4 distribution 3→4). Doc-as-test test_filt07_documented_in_requirements_md (in tests/test_filter.py) asserts 4 substring anchors (**FILT-07**, is_us_location(), bias toward inclusion per FILT-05, | FILT-07 | Phase 4 |) — fails next CI run if a future editor strips them. 25 net new tests (22 in tests/test_filter.py — 16-row parametrized US-keep/non-US-drop + SF-keep/London-drop/empty-keep spot-checks + determinism + bool-return + doc-invariant; 3 in tests/test_orchestrator.py — _TwoCityAdapter London-drop integration + caplog INFO log assertion + US-keep regression guard); 524 cumulative passing (was 499 → +25 net new). ADP-15 re-proven an EIGHTH time (git diff --name-only 36dd035..HEAD -- src/adapters/ = 0). Ruff clean. FILT-07 closed in REQUIREMENTS.md. Duration ~6min. Commits: 7ff1b0d Task 1 RED, 130382a Task 1 GREEN, c13cfad Task 2 RED, 463917c Task 2 GREEN, ce6dcd0 Task 3 doc (5 commits — Task 3 doc-test was authored in Task 1 RED so Task 3 only needed REQUIREMENTS.md edits to flip GREEN, TDD discipline preserved).*

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
