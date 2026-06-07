# Project Research Summary

**Project:** new-grad (automated career-page job tracker)
**Domain:** Unattended hourly batch scraper — ATS API fan-out + Playwright fallback, state committed to public GitHub repo
**Researched:** 2026-06-07
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a well-understood domain with established public examples (SimplifyJobs/New-Grad-Positions, Pitt-CSC/Summer-Internships) and clear expert consensus: hit ATS JSON endpoints first (Greenhouse, Lever, Ashby, SmartRecruiters, Workday CXS, Apple Jobs), fall back to Playwright only for sites that have no API surface. All four research tracks independently arrived at the same core architecture: an adapter-per-ATS pattern dispatched by URL pattern, a single add-only `seen.json` state file committed to the repo, and pure-core/impure-edges component separation. The system is an ETL pipeline — config in, fetch, normalize, filter, merge state, render Markdown, commit — with no background workers, no database, and no UI beyond the README table.

The recommended v1 path is a walking skeleton: get one Greenhouse company scraped, filtered, deduped, and committed end-to-end before adding any adapter breadth. This forces every architectural seam to exist (registry, normalizer, filter, state merger, renderer, Actions workflow) and validates the commit-back loop before any Playwright complexity is introduced. The dedup key design is the single most consequential early decision: keys must be per-ATS stable IDs (format `gh:<company>:<id>`, `lever:<company>:<uuid>`, etc.) rather than raw URLs, because tracking parameters and slug changes cause silent duplicates that are hard to clean up retroactively.

The five existential risks for an unattended, unalerted, public-repo system are: (1) non-atomic `seen.json` writes that brick every future run; (2) concurrent Actions runs racing on git push; (3) a zero-result sweep wiping the entire table; (4) a secret committed to the public repo; (5) the Actions schedule silently going dead. None are complex to prevent — each requires one design decision baked in from day one — but all five must be addressed before the scraper opens to more than a handful of companies.

---

## Key Findings

### Recommended Stack

Python 3.12 is the right choice: best ecosystem for hybrid ATS-API plus headless-browser scraping, user-preferred, and 3.13 adds minor risk for zero upside on a cron job. The HTTP layer is `httpx` (async + sync, HTTP/2, modern timeout semantics) backed by `tenacity` for exponential-backoff retries. Playwright with Chromium-only install is the headless browser; install only Chromium (~400 MB with deps) to stay within Actions runner disk budget. State serialization uses `orjson` with `OPT_SORT_KEYS` — deterministic key ordering is not optional, it keeps git diffs readable. Pydantic v2 validates every ATS response at parse time and catches field-shape drift before it corrupts state. The Actions workflow uses `actions/cache@v4` for Playwright browsers (saves 60–90 seconds per run), `stefanzweifel/git-auto-commit-action@v5` for clean commit-only-on-diff, and `permissions: contents: write` is mandatory or the push silently fails.

No "unified jobs API" service, no Scrapy, no SQLite, no external database. All state lives in the repo as JSON. Dep install uses `uv` (10–100x faster than pip, real savings on 24 runs/day). Dev tooling: `ruff` for lint/format, `pytest` + `respx` for adapter unit tests against captured JSON fixtures.

**Core technologies:**
- **Python 3.12** + **httpx** + **tenacity**: primary language and async HTTP fan-out with retry — user-preferred, best ATS scraping ecosystem
- **Playwright** (Chromium only): headless JS rendering for non-ATS SPAs — Microsoft-backed, better auto-wait than Selenium, supports network interception to sniff XHR endpoints
- **playwright-stealth**: light fingerprint masking for sites that detect headless Chrome — MEDIUM confidence on effectiveness; add per-site only when needed
- **pydantic v2**: ATS response validation — catches silent field-shape drift that would otherwise corrupt state hours later
- **orjson** (`OPT_SORT_KEYS`): JSON serialization with deterministic ordering — required for clean git diffs; stdlib json produces spurious diffs from dict insertion order
- **selectolax** + **BeautifulSoup4**: HTML parsing on the Playwright path — selectolax is 5–25x faster than BS4 for clean HTML; BS4 fallback for malformed markup
- **uv**: fast dep installer — saves 30–90 seconds per hourly Actions run
- **stefanzweifel/git-auto-commit-action@v5**: commit-only-on-diff with `GITHUB_TOKEN`; no PAT needed for default-branch pushes
- **actions/cache@v4**: Playwright browser cache keyed on `requirements.lock` — prevents 90-second cold-download on every run

### Expected Features

The feature surface is deliberately narrow — all meaningful work is data-extraction quality, not UX.

**Must have (table stakes — v1 is broken without these):**
- Per-source fetcher with normalized `Posting` output regardless of adapter
- Greenhouse + Lever ATS adapters — cover the largest share of mid-size tech employers; both are single JSON GET calls
- URL-based adapter auto-detection — given a careers URL, pick the right adapter without user labeling
- Stable dedup key per ATS (format `gh:<co>:<id>`, not raw URL) — raw URL dedup fails silently on tracking params; this is the silent killer
- URL canonicalization before keying — strip `utm_*`, `gh_src`, `lever-source`, trailing slash, lowercase host
- Early-career title-keyword filter — include `new grad`, `entry`, `junior`, `associate`, `university`, `I`; exclude `senior`, `staff`, `principal`, `lead`, `manager`, `II`, `III`
- `seen.json` state file with add-only merge semantics and schema version
- Idempotent Markdown table render between `<!-- BEGIN JOBS -->` / `<!-- END JOBS -->` sentinels
- GitHub Actions hourly cron with `concurrency: cancel-in-progress: false`
- Per-source try/except error isolation
- Commit + push only when diff exists

**Should have (compound value, no v1 pressure):**
- JD-based experience filter + `experience_min`/`experience_max` extraction — title filter catches ~75% of senior roles; JD scan catches the rest
- Workday adapter — covers Nvidia, Microsoft, and many large employers; complex per-tenant POST body
- Playwright fallback adapter — proves non-ATS coverage; target one JS-heavy SPA
- Salary extraction from JD text — tolerate `—` for unparseable; do not block v1
- Posted-date extraction per adapter + human-readable Age column (`3h`, `2d`, `3w`)
- Per-source health table in README footer — `Apple: last seen 2h ago | Nvidia: BLOCKED 5d` — passive observability without notifications
- `still_listed` flag on stale postings
- Informative commit message: `+3 new (Apple, Stripe), 2 closed (Anthropic)`

**Defer to v2+:**
- Ashby + SmartRecruiters + Apple Jobs dedicated adapters — incremental, low-risk, add after adapter contract is stable
- LLM-based JD parsing — regex covers 90% of cases; reach for LLMs only if measured precision falls below threshold
- Visa/clearance flags, language filter, US-only region filter
- Title/salary normalization beyond trivial cases
- Per-posting JSON archive in `postings/`

### Architecture Approach

The system is a classic ETL pipeline with a plugin/adapter registry: config in → fetch → normalize → filter → merge with state → render → commit. State lives in `seen.json`, render target is `README.md`; no database, no queues, no background workers. Three architectural forcing functions: companies are data (adding a company = one line in `companies.txt`, zero code edits for known ATS patterns); one company's failure cannot stop the run (per-company try/except); the adapter pattern absorbs ATS diversity (one file per ATS implementing a `fetch() -> list[RawPosting]` ABC). Pure components — normalizer, filter, state merger, renderer — have no I/O and are trivially testable. I/O lives only at the edges (adapters, state store, git commit). A single `run_started_at` UTC timestamp is captured in `main.py` and passed through; nothing else calls `datetime.now()`.

**Major components:**
1. **Adapter Registry** (`src/registry.py`) — URL-pattern dispatch to the right adapter class; Playwright is catch-all; explicit `#adapter=` hint in `companies.txt` overrides
2. **ATS Adapters** (`src/adapters/`) — each implements `Adapter` ABC with `matches(url)` + `fetch(company) -> list[RawPosting]`; new ATS = new file + one registry import
3. **Normalizer** (`src/normalizer.py`) — pure function; `RawPosting` → canonical `Posting`; dispatches on `source_adapter`; no I/O
4. **Filter** (`src/filter.py`) — pure function; title keyword gate (Phase 1) + JD years-regex gate (Phase 2); bias toward exclusion on ambiguity
5. **State Store + Merger** (`src/state_store.py`, `src/state_merger.py`) — only component that reads/writes `seen.json`; add-only merge; assigns `first_seen` on new keys; never deletes keys; sanity gate before write
6. **Renderer** (`src/renderer.py`) — pure function; splices Markdown table between sentinels in `README.md`; sorted by posted_date desc then company asc; idempotent
7. **Orchestrator** (`src/main.py`) — wires components; drives per-company loop; captures `run_started_at`; collects errors; emits run summary
8. **GitHub Actions Workflow** (`.github/workflows/scan.yml`) — cron schedule, permissions, cache, Python setup, run, commit-back

### Critical Pitfalls

1. **Non-atomic `seen.json` write bricks all future runs** — always write to `seen.json.tmp` then `os.replace()` (POSIX-atomic); wrap `json.load()` in try/except with fallback to `.bak`; add `--validate` pre-flight step in workflow
2. **Concurrent runs racing on push** — set `concurrency: group: scan; cancel-in-progress: false` from day one; the queue serializes runs; never `git push --force`
3. **Zero-result sweep wipes entire table** — merge is add-only; sanity gate aborts commit if `len(new) < 0.9 * len(old)`; distinguish `SiteBlocked` from "genuinely zero" in every adapter
4. **Secret committed to the public repo** — strict `.gitignore` (`.env`, `*.har`, `trace.zip`, `cookies.json`) before first commit; Push Protection enabled in repo settings; all credentials via `os.environ` from `secrets.*`; disable Playwright trace in production
5. **Dedup key instability from URL tracking params** — keys must be per-ATS stable IDs extracted from ATS responses, not raw URLs: `gh:<company>:<id>`, `lever:<company>:<uuid>`, `wd:<tenant>:<id>`; URL canonicalization is the fallback for unknown adapters
6. **Actions schedule silently disabled** — GitHub kills scheduled workflows after 60 days of repo inactivity; a `health.json` updated on every run guarantees at least one commit per run, preventing schedule death

---

## Implications for Roadmap

Based on combined research, the natural phase structure follows the architecture's own layer ordering, with the absolute requirement that Phase 1 bakes in all five existential risks before any scraping breadth is added.

### Phase 1: Walking Skeleton — Foundation and One End-to-End Slice

**Rationale:** All four researchers converge on this: get one Greenhouse company working end-to-end before any breadth. This forces every architectural seam to exist and validates the commit-back loop on real infrastructure. Phase 1 is the only cheap chance to bake in the five existential risks — retrofitting atomic writes, concurrency groups, and sanity gates into a 500-line script is painful; building them into a 100-line slice is trivial.

**Delivers:**
- Full project scaffolding (`src/` layout, `pyproject.toml`, `.gitignore`, `requirements.txt`, `requirements-dev.txt`)
- `models.py` with `Posting`, `RawPosting`, `CompanyConfig` and the per-ATS dedup key format locked in
- `config_loader.py` — robust `companies.txt` parser (strips whitespace, skips blanks/comments, validates URLs, supports `#adapter=` hint)
- `adapters/base.py` ABC + `adapters/greenhouse.py` — one JSON GET, schema assertion, stable key `gh:<co>:<id>`
- `registry.py`, `normalizer.py` (Greenhouse only), `filter.py` (title keywords only)
- `state_store.py` — atomic write via `os.replace`, read with try/except + `.bak` fallback, sanity gate (`len(new) < 0.9 * len(old)` aborts)
- `state_merger.py` — add-only merge, `first_seen` assignment, `still_listed` tracking
- `renderer.py` — sentinel splice, idempotent sort, cell escaping (pipe, newline, invisible Unicode)
- `main.py` — orchestrator with per-company try/except, single `run_started_at` clock, run summary
- `.github/workflows/scan.yml` — `permissions: contents: write`, `concurrency: cancel-in-progress: false`, `cache@v4`, `timeout-minutes: 50`, `git-auto-commit-action@v5`
- `health.json` updated on every run (including failed runs) to prevent schedule-disable
- Definition of done: cron fires, one Greenhouse company scraped, README table updated, committed; second run dedups cleanly with no diff

**Addresses pitfalls:** 1 (atomic write), 2 (sanity gate), 3 (concurrency group), 4 (secrets + .gitignore), 5 (stable dedup key), 16 (permissions), 17 (log discipline), 18 (empty commit guard), 23 (health.json)

**Research flag:** Standard patterns — no phase research needed. Greenhouse API shape and Actions workflow wiring are well-documented with community examples.

---

### Phase 2: ATS Adapter Breadth — API-First Coverage

**Rationale:** Once the architecture is proven with one adapter, adding the rest is mechanical. Lever, Ashby, SmartRecruiters are similar single JSON GET calls — low implementation risk, high coverage gain. Workday is the most complex (per-tenant POST body, pagination, epoch-millisecond dates) but belongs in this phase because it covers Nvidia, Microsoft, and many large employers. Each adapter enforces the same contract: schema assertion on raw response, stable ID extraction, UTC date normalization, `SiteBlocked` exception distinct from zero-results.

**Delivers:**
- `adapters/lever.py`, `adapters/ashby.py`, `adapters/smartrecruiters.py`, `adapters/workday.py`
- Stable key per adapter: `lever:<co>:<uuid>`, `ashby:<co>:<uuid>`, `sr:<co>:<id>`, `wd:<tenant>:<id>`
- `SiteBlocked` exception type — merge treats blocked as "no update" for that company
- Per-adapter date normalization to UTC ISO 8601; Workday epoch-ms handling
- `filter.py` JD-scan extension: years-regex + `entry-level`/`recent graduate` signals; `experience_min`/`experience_max` populated
- Age column render
- `companies.txt` with 3–5 companies per ATS; adapter contract validated against live data before locking
- pytest fixtures (recorded JSON responses); regression tests for date parsing edge cases

**Addresses pitfalls:** 5 (stable keys per ATS), 6 (schema assertions), 8 (API-first before Playwright), 9 (canonicalization), 10 (UTC dates), 12 (two-layer experience filter), 13 (Markdown escaping), 21 (companies.txt robustness)

**Research flag:** Needs live validation at implementation time. Workday CXS POST body shape and Apple Jobs `api/role/search` field names should be fetched live and confirmed before locking adapter contracts. Training-data field names are MEDIUM confidence only.

---

### Phase 3: Playwright Fallback — Non-ATS Coverage

**Rationale:** Playwright is deferred until after the ATS adapter layer is stable so the adapter ABC is proven. The fallback is the most complex adapter and is only needed for companies with no JSON API surface. Implementing it third keeps Phases 1 and 2 clean and ensures the adapter interface is mature before the most exotic use case exercises it.

**Delivers:**
- `adapters/playwright_fallback.py` — `wait_for_selector` or `expect_response` interception, post-render parse via selectolax, `PlaywrightTimeout` typed error
- `adapters/apple.py` — dedicated adapter for `jobs.apple.com/api/role/search` POST JSON (API-first, no Playwright needed; included here as it commonly pairs with Playwright research)
- Playwright cache wiring validated; `--with-deps chromium` only on cache miss
- `playwright-stealth` added conditionally only for sites that require it
- One JS-heavy SPA company passing end-to-end (e.g., Anthropic careers)
- Per-page navigation timeout (20000ms) and session-level timeout set; hung page = typed error, not zero results

**Addresses pitfalls:** 8 (hydration waiting), 14 (Playwright cache), 15 (stealth conditional), 25 (UTF-8 encoding), 26 (cache key invalidation)

**Research flag:** Needs shallow phase research. Specific selector patterns or XHR intercept targets for the chosen JS-heavy SPA must be discovered empirically. Playwright stealth effectiveness vs current anti-bot vendors (DataDome, PerimeterX) is LOW confidence from training data; validate per target site.

---

### Phase 4: Extraction Polish — Salary, Location, Observability

**Rationale:** Salary, location normalization, and per-source health reporting are high-value additions that don't affect architectural correctness. They belong after the core pipeline is stable. The health table is the product's passive observability layer — it replaces notifications for an unattended system and should ship before the company list grows large.

**Delivers:**
- Salary extraction: pattern library (range, ceiling, hourly, currency-prefixed), test corpus of 30+ real strings from tracked companies, `—` for unparseable
- Location normalization: collapse `Remote, United States` / `Remote — US` to `Remote (US)`
- Per-source health table in README footer: `Company | Last seen | Status (ok/blocked/schema-drift/error)`
- `still_listed: false` postings rendered with subtle marker in table
- Informative commit messages: `chore: +3 new (Apple, Stripe), 2 closed (Anthropic)`
- `seen.json` size monitoring: `size_bytes` in README footer; alert threshold documented at 5MB
- Run summary printed to Actions step summary

**Addresses pitfalls:** 5 (blocking detection surfaced in health table), 7 (size monitoring), 11 (salary regex), 20 (N-failure threshold before marking adapter broken), 27 (sorted JSON + `.gitattributes`)

**Research flag:** Salary extraction patterns — LOW confidence that training-data patterns cover all real-world ATS salary text. Build a live corpus from actual tracked companies before writing the pattern library.

---

### Phase 5: Sustainability — Archival, Hardening, Ops Documentation

**Rationale:** This phase addresses long-horizon risks that are not urgent at MVP but will bite within months. The `seen.json` archival mechanism, ToS hygiene documentation, and ops runbook exist to make the system survivable for a solo operator with no monitoring.

**Delivers:**
- `seen.json` soft cap: entries with `last_seen` older than 18 months roll to `seen.archive.jsonl` (append-only, not read at runtime)
- `robots.txt` check per company on first scrape; skip explicitly disallowed paths
- Ops runbook in README: recover from corrupted `seen.json`, add a company, disable a broken adapter, rotate a secret
- ToS notice in README: public job postings only, no auth required, hourly is conservative, description text not mirrored
- Weekly `gitleaks detect --log-opts="--all"` history scan (scheduled separate workflow)
- Manual override files: `excluded_keywords.txt` and `included_keywords.txt` for filter tuning without code edits
- `dependabot.yml` for weekly pip and Actions dep updates

**Addresses pitfalls:** 4 (gitleaks history scan), 7 (archive rollover), 22 (ToS hygiene), 27 (sorted JSON, .gitattributes)

**Research flag:** Standard patterns — no phase research needed.

---

### Phase Ordering Rationale

- **Foundations before breadth.** The state file design (dedup key format, atomic write, sanity gate) must be locked before adding ATS adapters. Changing the key format retroactively requires a migration across `seen.json`. Phase 1 locks this.
- **API-first before Playwright.** Every site that exposes a JSON endpoint should use it — Playwright is slower, more brittle, and more maintenance-intensive. The adapter pattern means Playwright is just one more adapter, but it should be added after API-first adapters prove the interface is stable.
- **Architectural correctness before extraction polish.** Salary and location normalization are extraction improvements, not architectural requirements. Shipping them in Phase 4 keeps Phase 1–2 focused on correctness.
- **The five existential risks are Phase 1 non-negotiables.** PITFALLS.md is explicit: if atomic writes, concurrency group, sanity gate, secrets hygiene, and health.json are not in from day one, the system will fail silently within weeks.

### Research Flags

**Needs deeper research during planning:**
- **Phase 2 (ATS adapters):** Verify current Workday CXS POST body shape, response field names, and pagination token format against a live tenant before locking adapter contracts. Training data is MEDIUM confidence. Also verify Apple Jobs `api/role/search` current request/response shape — endpoint is stable but field names drift.
- **Phase 3 (Playwright fallback):** Identify the specific XHR intercept target or stable selector for the chosen JS-heavy SPA target. Playwright stealth effectiveness vs current DataDome/PerimeterX versions needs empirical validation per target site.
- **Phase 4 (salary extraction):** Build a live test corpus from real postings before writing the pattern library. Training-data salary regex patterns are LOW confidence on format coverage.

**Standard patterns (skip research phase):**
- **Phase 1 (walking skeleton):** Greenhouse API shape, Actions workflow wiring, atomic file write, git commit-back pattern — all well-documented with community examples.
- **Phase 5 (sustainability):** Archival, robots.txt parsing, dependabot — all standard tooling.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Technology choices are well-established, user-preferred, and corroborated across research. Version floors need PyPI verification at project start via `uv pip index versions`. |
| Features | MEDIUM-HIGH | Table-stakes feature list is directly derived from user requirements + public new-grad-tracker norms. Filter precision estimates (~75% title-filter coverage) are order-of-magnitude from domain familiarity, not measured — validate after first week of real data. |
| Architecture | HIGH | ETL + adapter pattern maps cleanly to project constraints. Data shapes, component boundaries, and file layout are concrete and validated against PROJECT.md. |
| Pitfalls | HIGH | All five existential risks are well-understood failure modes in unattended GitHub Actions scrapers. Specific anti-bot vendor behavior (DataDome, PerimeterX current fingerprint checks) is MEDIUM confidence and must be validated empirically per site. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Exact ATS endpoint field names:** All ATS JSON endpoints are undocumented public surface area. Field names used in training data (e.g., Workday's `jobPostings`, `externalPath`) may have drifted. Fetch a live sample per ATS before writing the adapter — do not write adapter code against training-data field names alone.
- **Filter precision:** The claim that title-keyword filtering catches ~75% of senior roles is a domain estimate, not a measured figure. After the first week of real data, count false positives and false negatives to calibrate the keyword lists.
- **Playwright stealth per target site:** Effectiveness against current anti-bot vendors drifts continuously. Do not assume it will work; validate per site and document which sites require it.
- **GitHub Actions cron drift:** Free-tier cron can be delayed 15–60 minutes under load. Document this in the repo README so the user does not chase phantom reliability failures.
- **Workday per-tenant variation:** ~10–20% of Workday tenants have non-standard pagination or facet configurations. The fallback for any Workday company the adapter can't parse cleanly is `#adapter=playwright` in `companies.txt`.

---

## Sources

### Primary (HIGH confidence)
- `PROJECT.md` — domain constraints, requirements, explicit out-of-scope list, tech decisions
- Greenhouse public API: `boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true` — no auth, stable
- Lever public API: `api.lever.co/v0/postings/<company>?mode=json` — no auth, stable
- GitHub Actions documentation — concurrency, `GITHUB_TOKEN` permissions, schedule deactivation policy, `permissions: contents: write`
- Playwright documentation — browser caching, navigation timeouts, headless modes

### Secondary (MEDIUM confidence)
- Community documentation of Workday CXS endpoint: `POST <tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs` — undocumented but community-stable
- Apple Jobs API: `jobs.apple.com/api/role/search` POST JSON — unofficial, field names drift occasionally
- Ashby: `api.ashbyhq.com/posting-api/job-board/<org>` — public posting API
- SmartRecruiters: `api.smartrecruiters.com/v1/companies/<co>/postings` — public, well-known
- Public new-grad tracker repos (SimplifyJobs/New-Grad-Positions, Pitt-CSC/Summer-Internships) — establish Markdown table format norms and adapter-pattern precedent

### Tertiary (LOW confidence, validate empirically)
- `playwright-stealth` effectiveness vs current DataDome/PerimeterX versions — validate per target site
- Filter precision estimates (~75% title-filter coverage) — measure after first week of real data
- Salary regex format coverage — build live corpus before writing pattern library

---
*Research completed: 2026-06-07*
*Ready for roadmap: yes*
