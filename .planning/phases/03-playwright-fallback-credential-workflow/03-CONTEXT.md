# Phase 3: Playwright Fallback + Credential Workflow - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 closes the adapter universe with two pieces that together cover **every kind of career page** the user is likely to track:

1. **Playwright fallback adapter** — for JS-heavy SPAs that don't expose a public ATS API (Anthropic, Vercel, Linear, Tesla, custom corporate portals). Uses headless Chromium with XHR-intercept-first strategy, DOM-selector fallback, `playwright-stealth` for anti-bot evasion. This becomes the **catch-all** appended last to `src/registry.py`'s `ADAPTERS` list.

2. **Credential workflow** — for the rare site that requires login to view postings. Claude CLI handles the entire flow conversationally: prompt for email + password inline, call `gh secret set SCRAPER_<COMPANY>_<KIND>`, verify with a one-shot test scrape, confirm via `gh secret list`. No manual repo-config work from the user.

**Additional architectural work (forced by the user's actual companies.txt):**

3. **URL redirect-resolver** — `src/url_resolver.py` performs `httpx.head(url, follow_redirects=True)` (with 5s timeout) before adapter dispatch. ~18 of the user's 31 listed URLs are branded CNAMEs that redirect to Workday tenants (e.g., `careers.amd.com` → `amd.wd1.myworkdayjobs.com/...`); without this resolver, the strict Workday URL regex from Phase 2 would miss them. Cheap HEAD request; Workday adapter then handles the resolved URL normally.

4. **CLAUDE.md "Adding a Company" workflow documentation** — explicit instructions for how Claude CLI handles `add <URL>` autonomously: try existing adapters → resolve redirects → re-try → Playwright catch-all → only write a new adapter if all of the above fail. Documents what Phase 1+2's open-closed contract (ADP-14/15) enables at the user-facing layer (CFG-04).

**What ships at the end of Phase 3:**
- `src/adapters/playwright_fallback.py` — Playwright-based scraper with XHR intercept, DOM selector fallback, stealth, 60s timeout, trace=off, credential support
- `src/url_resolver.py` (new) — pre-flight redirect-following helper
- `src/registry.py` — Playwright appended last to `ADAPTERS`; resolver wired into `get_adapter()`
- Credential workflow integrated into Playwright adapter via `os.environ["SCRAPER_<CO>_EMAIL"]` / `SCRAPER_<CO>_PASSWORD"]` reads
- README + CLAUDE.md sections: "Adding a Company" (CLAUDE.md), "Credential Naming Convention" (README — SEC-06)
- `pyproject.toml` / `requirements.lock` updated with `playwright>=1.45`, `playwright-stealth>=1.0.6`, `selectolax>=0.3.21` (selectolax may have landed earlier; verify)
- `.github/workflows/scan.yml` updated: Playwright Chromium cache (`actions/cache@v4` keyed on Playwright version), `playwright install --with-deps chromium` only on cache miss
- Anthropic careers (`anthropic.com/careers`) as the seed development target — at least one new-grad-eligible posting must render in the README table by end of phase
- Per-adapter fixture-mutation tests for Playwright (mocked browser scenarios via Playwright's built-in mocking)

**What is NOT in Phase 3:**
- Salary extraction (Phase 4 / NORM-02)
- Location normalization (Phase 4 / NORM-03)
- Source Health footer (Phase 4 / OUT-09)
- Multi-credential sites (oauth, 2FA) — out of scope for v1; document in deferred ideas

</domain>

<decisions>
## Implementation Decisions

### Playwright adapter — seed target + strategy

- **D-01: Anthropic careers is the Phase 3 seed Playwright target.** `https://anthropic.com/careers` — custom React SPA, no public ATS API, likely uses a `/api/jobs` style XHR. The Playwright adapter's first implementation is shaped against this site; happy-path tests + fixture use Anthropic's response shape.
- **D-01a: XHR-intercept first, DOM-selector fallback.** The adapter tries `page.expect_response(lambda r: "/api/" in r.url and "jobs" in r.url)` to capture the network call that loads postings, parses the response JSON directly. If no matching XHR appears within the timeout, fall back to waiting for a DOM selector (e.g., `[data-testid="job-card"]` or whatever Anthropic's careers page uses) and parsing rendered HTML via `selectolax`. The adapter logs which path was taken so debugging shows whether the site has stable XHRs or relies on selectors.
- **D-01b: URL redirect-resolver (new architecture, pre-existing-adapter dispatch).** Before `get_adapter()` returns, it calls `resolve_url(company.url)` which does `httpx.head(url, follow_redirects=True, timeout=5.0)` and returns the final URL. The resolver attaches the resolved URL to `CompanyConfig` (new field `resolved_url: str | None`) so adapters that need the canonical form (Workday) can use it; the original URL is preserved on `CompanyConfig.url` for display. **Critical for user's actual list:** ~18 of 31 URLs are CNAMEs to Workday — this resolver unblocks them without any per-adapter changes.
- **D-01c: Playwright is the catch-all, appended LAST to `ADAPTERS`.** All earlier adapters' `matches()` get first crack; if none match (even after redirect resolution), Playwright's `matches()` returns True for any HTTP/HTTPS URL — it's the unconditional fallback. Naming the catch-all "playwright" preserves the per-adapter dispatch pattern in the normalizer.

### Credential workflow (SEC-01, SEC-02, SEC-04, SEC-06)

- **D-02: Eager prompt + separate per-kind secrets.** When the user says "add company X" via Claude CLI and the page requires login, Claude prompts inline for email + password (and other kinds the site needs), runs `gh secret set SCRAPER_<COMPANY>_EMAIL <value> --repo DevDesai444/new-grad` and `gh secret set SCRAPER_<COMPANY>_PASSWORD <value>`, then runs a one-shot Playwright login test to verify the credentials work (without committing the verification — just runs `python -m src.main --verify-login <company>` or similar).
- **D-02a: Secret naming convention is `SCRAPER_<COMPANY>_<KIND>`.** `<COMPANY>` is UPPERCASE, alphanumeric with underscores. `<KIND>` is one of `EMAIL`, `USERNAME`, `PASSWORD`, `API_KEY`, `OAUTH_TOKEN` (other kinds as needed). Each credential is its own env var — easy rotation, easy audit via `gh secret list`. The adapter reads via `os.environ["SCRAPER_<CO>_<KIND>"]` and raises `MissingCredential` (Phase 1 typed error) if any expected var is unset.
- **D-02b: Verification before declaring success.** After `gh secret set`, Claude runs the one-shot Playwright login test. If login fails (wrong password, wrong selector, anti-bot), Claude re-prompts the user. If login succeeds, Claude appends the URL to `companies.txt` and commits. **The user only confirms once — Claude does NOT echo credentials back, only reports success/failure.**
- **D-02c: SEC-03 enforcement is structural, not just procedural.** The Playwright adapter NEVER `traceback.format_exc()` an exception that might carry HTTP headers (mirrors Phase 1's discipline). Login failures log only "Login failed for <COMPANY> — wrong credentials, anti-bot challenge, or selector drift" with no credential values.

### CLAUDE.md "Adding a Company" workflow (CFG-04)

- **D-03: CLAUDE.md gains a section "How Claude CLI Handles `add <URL>` Autonomously".** This is a meta-instruction file (not project code) telling future Claude CLI sessions how to handle the user's "add this URL" request. The flow:
  1. **Try existing adapters via `get_adapter()`** on the raw URL. If an adapter matches (Greenhouse/Lever/Ashby/SR/Workday/Apple) → append URL to `companies.txt`, commit, push. Done.
  2. **Resolve redirects** via `resolve_url()` (the new D-01b helper). Re-try `get_adapter()` on the resolved URL. If now matches (typical CNAME→Workday case) → append the **resolved** URL (not original) to `companies.txt`. Commit. Done.
  3. **Playwright catch-all** — if no specific adapter matches even after resolution, Playwright handles it. Append URL to `companies.txt`. Run one-shot smoke test (`python -m src.main --test <url>`) to verify Playwright extracts at least one posting. If smoke test passes → commit. If smoke test fails → step 4.
  4. **New adapter** — Playwright catch-all couldn't extract postings cleanly. This means the site has a unique structure that benefits from its own adapter. Claude creates `src/adapters/<name>.py` subclassing `Adapter`, registers it in `ADAPTERS` (append-only — does NOT modify existing adapter files; ADP-15 invariant), writes a fixture + happy-path + error-path tests mirroring the Phase 2 pattern, runs the test suite to confirm nothing else breaks, then appends URL to `companies.txt` and commits.
  5. **Credential check at every step** — if the page requires login (Claude detects via a one-shot HEAD + check for `<form>` with `password`-type input), Claude jumps to the D-02 credential flow before step 1.
- **D-03a: Resolved URLs go in companies.txt, not original.** When a CNAME resolves to a Workday URL, the **resolved** URL is what's committed. This guarantees the Workday adapter regex matches on every hourly run without re-resolving each time. The original URL is fine to know about (logged as a comment by the Claude session) but the source-of-truth is the canonical form.

### Playwright runtime configuration

- **D-04: Stealth on by default; per-site opt-out via `#adapter=playwright:stealth=false`.** `playwright-stealth` is applied to every Playwright scrape. ~150ms overhead per page — negligible against the 60s navigation timeout. Per-site opt-out via the existing hint slot (`CompanyConfig.hint` from Phase 1) lets the user reclaim the speed for sites that demonstrably don't need stealth.
- **D-05: 60s per-page navigation timeout default; per-site override via `#adapter=playwright:timeout_s=N`.** The 60s is a **maximum** — fast pages return immediately at their actual load time (Playwright's `page.goto(url, timeout=60_000)` semantics). Generous default protects slow legitimate sites (Nvidia Workday tail can be 15s+; some sites with heavy tracking pixels approach 30s). Per-site override for sites known to be even slower, or for tightening on fast sites.
- **D-06: `trace="off"` in production; `SCRAPER_DEBUG_TRACE=1` env-var escape hatch enables `trace="retain-on-failure"` for local debug only.** Pitfall 4 mitigation. The env var is read by the Playwright adapter at startup; if set, it switches to retain-on-failure (which saves a trace file only when a page errors). The GitHub Actions workflow does NOT set this env var; only developer machines do. Production traces never get committed because the file path is gitignored (`.playwright-trace/`).

### Claude's Discretion

These were not explicitly asked because they're implementation details, not user-visible choices:

- **Realistic User-Agent string** — adapter sets `chromium.launch_persistent_context(user_agent=...)` with a recent Chrome string. Planner picks a current Chrome version at implementation time (e.g., `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36`). Refresh annually.
- **Viewport size** — `1920x1080` (most common desktop viewport — passes most anti-bot fingerprinting checks).
- **Login-required detection heuristic for D-03 step 5** — Claude CLI does `httpx.get(url, follow_redirects=True)` and parses the HTML for `<input type="password">` and/or `<form action="*login*">`. If found → likely credentialed.
- **`InvalidCredential` vs `MissingCredential` typed exception** — `MissingCredential` (Phase 1, env var unset) is distinct from `InvalidCredential` (env var present but login form rejected). Planner adds `InvalidCredential` to `src/adapters/base.py` and raises it from the Playwright adapter's login flow.
- **Network throttling for tests** — Playwright's `page.route()` lets tests mock network responses for deterministic fixture-mutation tests. Planner uses this pattern; no real Anthropic HTTP calls in CI.
- **Playwright install command in workflow YAML** — `playwright install --with-deps chromium`. On cache hit, no-op. Cache key includes Playwright version (from `pip show playwright`) so version bumps invalidate correctly (per Pitfall 26).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-Level Specs

- `.planning/PROJECT.md` — Core value, requirements, constraints.
- `.planning/REQUIREMENTS.md` — Per-requirement definitions. INFRA-05 dropped (Phase 1); FILT-04 softened (Phase 2). Phase 3 closes ADP-09, ADP-10, SEC-01, SEC-02, SEC-04, SEC-06.
- `.planning/ROADMAP.md` — Phase 3 section: goal, mode (`mvp`), depends-on Phase 2, success criteria.
- `CLAUDE.md` — Project-level constraints; Phase 3 EXTENDS this with the "Adding a Company" section per D-03.

### Phase 1 + 2 outputs (consumed by Phase 3)

- `.planning/phases/01-walking-skeleton/01-CONTEXT.md` — Phase 1 decisions (SEC-03 / SEC-05 hygiene rules from D-08).
- `.planning/phases/02-ats-breadth-jd-scan/02-CONTEXT.md` — Phase 2 decisions (especially D-04 pagination algorithm — applies to Playwright if Anthropic paginates).
- `.planning/phases/02-ats-breadth-jd-scan/02-{01,02,03}-SUMMARY.md` — what Phase 2 built.
- `src/adapters/base.py` — `Adapter` ABC, typed exceptions (`SiteBlocked`, `SchemaDrift`, `PlaywrightTimeout`, `MissingCredential`). Phase 3 adds `InvalidCredential` here.
- `src/adapters/workday.py` — D-04 pagination pattern to mirror in Playwright if Anthropic paginates.

### Research Outputs

- `.planning/research/SUMMARY.md` — Phase 3 deliverables list. Phase 3 IS the "needs shallow phase research" phase per the SUMMARY's research-flag table.
- `.planning/research/ARCHITECTURE.md` — `Posting` schema, dedup-key conventions.
- `.planning/research/STACK.md` — Locked stack; Phase 3 adds `playwright>=1.45`, `playwright-stealth>=1.0.6`. `selectolax>=0.3.21` may already be in `requirements.lock` from Phase 2 (used for SmartRecruiters HTML stripping); verify before pinning.
- `.planning/research/PITFALLS.md` — Phase 3 addresses Pitfalls 4 (secret hygiene — credentialed scrapes), 5 (anti-bot blocks — `playwright-stealth`), 8 (SPA hydration timing — `page.expect_response`), 14 (Playwright install time — cache), 15 (headless detection — stealth), 17 (secret leaks in logs), 26 (cache key invalidation — include Playwright version).
- `.planning/research/FEATURES.md` — Playwright is "should have" + credential workflow is "should have"; both land in Phase 3.

### External References

- **Playwright Python docs** — verify current API at implementation time; the planner should confirm `page.expect_response` signature, `launch_persistent_context` for stealth, `chromium.launch(headless=True)` recommended over deprecated `headless="new"` mode.
- **playwright-stealth** — community package, MIT license. Verify it still maintains parity with current Chrome stealth checks (anti-bot vendors evolve continuously per PITFALLS.md note).
- **GitHub Actions Cache** — `actions/cache@v4` (already pinned in workflow YAML from Phase 1; ensure Playwright cache key includes Playwright version).

**Planner action item:** Run `playwright install chromium && playwright --version` and capture the version in the cache key. Also verify Anthropic's `anthropic.com/careers` page structure (which XHR loads the postings, what selector identifies them) by a one-time browser inspection or test run.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1 + 2)

- **`src/adapters/base.py`** — `Adapter` ABC + 4 typed exceptions + `requires_seen_keys: ClassVar[bool] = False` pattern (Phase 2 introduced this for Workday/Apple pagination; Playwright may also need it if Anthropic paginates). Phase 3 adds `InvalidCredential` here.
- **`src/registry.py`** — `ADAPTERS` list, `get_adapter()` resolution order. Phase 3 modifies this: adds redirect-resolver pre-flight; appends `PlaywrightAdapter` LAST to `ADAPTERS` (catch-all).
- **`src/normalizer.py`** — Per-adapter dispatch via `_DISPATCH[adapter_name]`. Phase 3 adds `_extract_playwright` helper that handles the generic Playwright-extracted dict shape.
- **`src/filter.py`** — JD-scan extraction (Phase 2's `extract_experience_range`). Wires into the Playwright adapter's normalizer helper identically to Phase 2's pattern.
- **`src/adapters/workday.py`** — D-04 pagination algorithm. Playwright reuses this pattern if Anthropic paginates (likely it doesn't — most custom SPAs return all postings in one XHR).
- **`tests/test_workday_adapter.py`** — Test pattern for adapters that need `seen_keys`. Mirror for Playwright if needed.
- **`tests/test_adapter_contract.py`** — Open/closed proof (ADP-14/15). Phase 3 MUST keep this test green: adding `PlaywrightAdapter` and adding `resolve_url()` must NOT modify any existing adapter file.
- **`src/config_loader.py`** — Phase 1's `companies.txt` parser. Already supports the `#adapter=<name>` hint slot. Phase 3 uses it for `#adapter=playwright:stealth=false`, `#adapter=playwright:timeout_s=30`, etc.

### Established Patterns

- **Playwright catch-all matching pattern:** `class PlaywrightAdapter(Adapter): @classmethod def matches(cls, url: str) -> bool: return url.startswith(("http://", "https://"))` — returns True for any HTTP/HTTPS URL. Always last in `ADAPTERS` so other adapters' specific `matches()` fire first.
- **Per-site hint parsing:** `CompanyConfig.hint` is `name:k1=v1,k2=v2` form. Phase 1's `config_loader` already parses this into a dict. The Playwright adapter reads `hint_kwargs.get("stealth", "true")`, `hint_kwargs.get("timeout_s", "60")`.
- **Dedup-key format for Playwright:** `pw:<host>:<id>` where `<id>` is extracted from the XHR response's posting object (preferred), or hashed from the posting URL if no clean ID is available (fallback). Per Pitfall 5 / 9, NEVER use raw URL as key.

### Integration Points

- **`src/main.py` ↔ resolve_url:** the orchestrator calls `resolve_url(company.url)` once at run start per company (before `get_adapter()`). The resolved URL is stored on `company.resolved_url` and used by Workday / Playwright adapters.
- **`src/main.py` ↔ Playwright adapter:** the Playwright adapter's `fetch(company, seen_keys=None)` follows the same signature as other adapters. Plays nicely with the existing per-company try/except (ADP-12) — no orchestrator changes beyond passing `seen_keys`.
- **`.github/workflows/scan.yml` ↔ Playwright cache:** Phase 1's workflow already has the cache step (stub). Phase 3 fills it in: `path: ~/.cache/ms-playwright`, `key: playwright-${{ runner.os }}-${{ hashFiles('requirements.lock') }}`. `playwright install --with-deps chromium` runs only on cache miss.
- **`CLAUDE.md` ↔ "Adding a Company" section:** D-03 documentation lives in this file. The planner appends a section (does not modify existing content beyond appending).

</code_context>

<specifics>
## Specific Ideas

- **Anthropic careers URL pattern:** `https://anthropic.com/careers` (likely the canonical form; `www.anthropic.com/careers` should also match). Planner verifies at implementation.
- **XHR intercept pattern:** Likely `/api/jobs` or `/api/v1/openings` on Anthropic's site (per training data; verify live). The adapter uses `page.expect_response(lambda r: "/api/" in r.url and r.status == 200)` to capture.
- **Dedup key format for Playwright postings:** `pw:<host>:<id>` where `<id>` is the posting's stable ID from the XHR response, or `sha256(canonical_url)[:16]` if no ID. Document the format in the adapter file's docstring.
- **`.gitignore` additions for Phase 3:** `.playwright-trace/` (debug trace output), `playwright-report/`, `playwright/.cache/`. Phase 1's `.gitignore` already covers `trace.zip` and similar files; Phase 3 extends.
- **CLAUDE.md "Adding a Company" section structure (D-03):** Subsections "Step 1: Try existing adapters", "Step 2: Resolve redirects", "Step 3: Playwright catch-all", "Step 4: Write a new adapter", "Step 5: Credential-required sites (see SEC-01)". Each subsection ~10 lines, with a concrete command example.
- **Login form detection (D-03 step 5):** Use `httpx.get(url, follow_redirects=True, timeout=5.0)` and check the response body for `<input type="password">` or `<form action="*login*"`. If found, treat as credentialed.
- **Resolver edge cases:** When `httpx.head` fails (some sites reject HEAD), fall back to `httpx.get` with `stream=True` and only read headers — same effective behavior. When the resolver's 5s timeout fires, treat the URL as unresolvable; adapter dispatch falls through to Playwright catch-all.

</specifics>

<deferred>
## Deferred Ideas

- **Multi-factor / OAuth-based credentialed sites.** v1 supports email + password only. 2FA, magic links, OAuth flows out of scope. If the user encounters such a site, document it as a known-not-supported case and skip in companies.txt.
- **Proxy escape hatch for IP-blocked sites.** PITFALLS.md Pitfall 5 mentions a future workflow variable `USE_PROXY=1` routing through Bright Data / Tailscale exit node. Not in Phase 3 scope; design for it (document in CLAUDE.md as "future capability"). Adding it later requires modifying only the Playwright adapter's `chromium.launch` to read the proxy URL from env.
- **Per-site Chromium launch profile reuse.** Playwright supports persistent contexts (`launch_persistent_context`) that retain cookies across runs. Useful for sites that issue session tokens after a login. Not in v1 — current credential flow re-logs in each hourly run (slower but stateless). Re-evaluate in Phase 4 if any credentialed site has aggressive session-bound rate limiting.
- **Selenium fallback.** If Playwright ever breaks against a site (very rare), Selenium might work. Out of scope; document the option in PITFALLS-style language.
- **Auto-detection of underlying ATS at URL resolve time.** When `resolve_url` follows a CNAME and lands on a Workday URL, we already dispatch to Workday adapter. We could go further: detect "this resolved URL is on a Greenhouse hostname" and auto-add it. Already implicit in the flow (D-03 step 2 + step 1 retry), but could be made more explicit. Defer to a polish phase if needed.
- **Browser pool / connection reuse across companies.** Phase 3 launches Chromium once per company per run. A pool would amortize startup cost. v1 doesn't need this (31 companies × ~10s = 5 min worst case, well within 50-min budget). Phase 5 sustainability if it becomes a bottleneck.

</deferred>

---

*Phase: 03-playwright-fallback-credential-workflow*
*Context gathered: 2026-06-07*
