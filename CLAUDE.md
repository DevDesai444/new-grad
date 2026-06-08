<!-- GSD:project-start source:PROJECT.md -->
## Project

**new-grad**

An automated job-posting tracker that scans a configurable list of company career pages every hour for new grad / early-career roles (0–5 yrs experience) and publishes the current list as a Markdown table in a public GitHub repo. The user (Dev Desai) opens the repo, sees every posting, and applies directly via the linked posting URL — no manual scanning, no notifications, no extra tooling.

**Core Value:** **One glance at the GitHub repo shows every currently-known new-grad-eligible role across the user's tracked companies, with a working application link.** If hourly refresh, dedup, or the linked posting fail, the system loses its point.

### Constraints

- **Tech stack**: Python 3 + Playwright (chosen for best-in-class scraping ecosystem and Playwright's robust JS-rendering)
- **Hosting**: GitHub Actions only — cron-driven, free tier of public repo, no other infrastructure
- **Budget**: $0/month — must stay within GitHub's free tier indefinitely
- **Storage**: All state (companies list, seen postings, table) lives in the same public GitHub repo. No database.
- **Security**: Any per-site credentials → GitHub Actions Secrets. Never committed. Never logged.
- **Cadence**: Hourly scan — non-negotiable (the "every hour" promise is the product)
- **Privacy**: Repo is public — the list of companies being tracked, postings found, and history are all publicly visible. No personal data (resume, email, etc.) goes in the repo.
- **Resilience**: A single company failing must not block the rest of the scan. Per-site try/except with logging.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Runtime
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **Python** | 3.12 (3.13 acceptable) | Primary language | User-preferred; best ecosystem for hybrid HTTP + headless browser scraping; both Greenhouse/Lever client libs and Playwright are Python-first | HIGH |
| **GitHub Actions** (ubuntu-latest) | runner image refreshed continuously | Cron host | Free unlimited minutes on public repos; native git push; pre-installed Python; matrix support if we ever shard | HIGH |
### HTTP Client (ATS API path)
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **httpx** | `>=0.27,<1.0` | Async + sync HTTP for ATS JSON endpoints | Single library covers sync (simple scripts) and async (parallel fan-out across N companies); HTTP/2 support; modern timeout/retry semantics; widely adopted for scraping in 2025–2026 | HIGH |
| **tenacity** | `>=8.2` | Retry with exponential backoff | Decorator-based; integrates cleanly with httpx; handles transient 429/5xx without us hand-rolling retry math | HIGH |
### HTML Parsing (Playwright fallback path)
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **selectolax** | `>=0.3.21` | Fast HTML → CSS-selector parsing | C-based (Modest/Lexbor backend), 5–25x faster than BeautifulSoup; matters because Playwright already gives us a DOM, but post-rendering parsing of huge career-page HTML is the bottleneck | MEDIUM |
| **BeautifulSoup4** | `>=4.12` | Fallback parser for weird HTML | Permissive parser handles malformed HTML where selectolax fails; only used when selectolax raises | HIGH |
### Headless Browser (JS-heavy SPA path)
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **playwright** (Python) | `>=1.45` (1.49+ preferred if available) | Headless Chromium for JS-rendered career pages | Industry standard 2024–2026; Microsoft-backed; better auto-wait semantics than Selenium; built-in network interception (lets us sniff XHR endpoints and bypass DOM entirely for many sites) | HIGH on choice, MEDIUM on exact version |
| **playwright-stealth** | `>=1.0.6` | Light fingerprint masking | Some career portals (Workday, certain Apple pages) drop headless browsers; stealth plugin patches the most-checked telltales (`navigator.webdriver`, plugin shape, etc.) | MEDIUM |
### State Persistence
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib `json`** | n/a | `seen.json` read/write | Zero dependencies; human-readable diffs in git PRs; the entire state file is small (KB → low MB at scale) | HIGH |
| **orjson** | `>=3.10` | Faster JSON serialization | 2–5x faster than stdlib; deterministic key ordering with `OPT_SORT_KEYS` (critical so git diffs are minimal/readable) | HIGH |
### Markdown Generation
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib f-strings + manual table** | n/a | README.md table rendering | A GitHub-flavored Markdown table is 3 lines of f-string per row; pulling in a library here is overkill | HIGH |
| **(optional) tabulate** | `>=0.9` | If table grows columns/formatting complexity | Only add if README rendering becomes non-trivial; YAGNI for v1 | LOW |
### Data Validation / Models
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **pydantic** | v2 (`>=2.7`) | Posting / company / state schemas | Strong runtime validation catches ATS API drift (a field changing type silently); v2 is much faster than v1; widely adopted 2024–2026 | HIGH |
### Date / Time
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib `datetime` + `zoneinfo`** | n/a | Posting dates, "Age" column | All ATS APIs return ISO-8601 UTC; stdlib handles parsing and "X days ago" math; `zoneinfo` (Python 3.9+) replaces `pytz` | HIGH |
| **dateparser** | `>=1.2` | Free-text date fallback | When a custom career page exposes "Posted 3 days ago" or "March 2026" instead of ISO timestamps, `dateparser` handles 200+ formats; gracefully returns `None` on failure | MEDIUM |
### Job-Description Text Filtering (0–5 yrs filter)
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib `re`** | n/a | Experience-range regex over description text | Patterns like `\b(\d+)\+?\s*(?:to|-|–)?\s*(\d+)?\s*years?\b` cover ~90% of postings; well-understood; no model needed | HIGH |
| **(deferred) spaCy or LLM** | n/a | If regex precision is too low | Defer until v2 — measure regex precision/recall first | LOW |
### Logging / Observability
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib `logging`** | n/a | Per-company structured logs | Free; Actions captures stdout/stderr automatically; surfaces in the Actions run UI | HIGH |
| **rich** (optional) | `>=13.7` | Local dev pretty output | Nice locally; on Actions it auto-degrades to plain text. Optional. | MEDIUM |
### GitHub Actions / Commit-Back
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **actions/checkout** | `@v4` | Repo checkout | Pinned major tag; v4 is the current standard 2024–2026 | HIGH |
| **actions/setup-python** | `@v5` | Python install | Current standard | HIGH |
| **actions/cache** | `@v4` | Pip + Playwright browser cache | v4 mandatory after v3 deprecation in early 2025; required for Playwright cache to actually persist | HIGH |
| **stefanzweifel/git-auto-commit-action** | `@v5` | Commit & push README + seen.json | Battle-tested; handles the "only commit if there's a diff" case cleanly; uses `GITHUB_TOKEN` so no PAT needed for default-branch pushes | HIGH |
### Configuration / Secrets
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **GitHub Actions Secrets** | n/a | Per-site auth (rare) | Surfaced as env vars; never committed; never echoed in logs (Actions masks them automatically) | HIGH |
| **python-dotenv** | `>=1.0` | Local dev only | Loads `.env` for local testing; `.env` in `.gitignore` | HIGH |
### Dev Tooling
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **uv** | `>=0.4` | Fast pip-replacement | 10–100x faster than pip for install; matters on every Actions run (saves 30–90 sec of wall-clock); reads standard `requirements.txt` | MEDIUM |
| **ruff** | `>=0.6` | Lint + format | Replaces flake8/black/isort; one tool; fast | HIGH |
| **pytest** | `>=8.0` | Tests for ATS parsers (using captured JSON fixtures) | Standard; fixture support critical for replaying real ATS responses | HIGH |
| **respx** | `>=0.21` | Mock httpx in tests | First-class httpx mocker; lets us replay captured Greenhouse/Lever responses in tests without hitting the network | HIGH |
## ATS-Specific Endpoints (no SDKs needed — pure JSON)
| ATS | Endpoint Pattern | Auth | Confidence |
|-----|------------------|------|-----------|
| **Greenhouse** | `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true` | None (public boards) | HIGH |
| **Lever** | `https://api.lever.co/v0/postings/{company}?mode=json` | None (public) | HIGH |
| **Ashby** | `https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true` | None (public job board API) | HIGH |
| **SmartRecruiters** | `https://api.smartrecruiters.com/v1/companies/{company}/postings` | None (public) | HIGH |
| **Workday** | `POST https://{host}/wday/cxs/{tenant}/{site}/jobs` (JSON body with `limit`, `offset`, `searchText`) | None | HIGH (well-documented in scraping community) |
| **Apple Jobs** | `https://jobs.apple.com/api/role/search` (POST JSON) | None | MEDIUM (endpoint stable but shape changes occasionally) |
| **iCIMS** | varies per tenant; usually `/jobs/search/...` or RSS feed | None | MEDIUM |
## Final `requirements.txt` (recommended)
# Core HTTP / parsing
# Headless browser (Chromium only)
# Data
# Local dev only
# requirements-dev.txt
## GitHub Actions Workflow Pattern
- `timeout-minutes: 50` — protects against a hung Playwright session burning the next hour's slot.
- `concurrency.cancel-in-progress: false` — never let two runs race on the same `seen.json`. If a run takes 70 min, the next one waits or gets dropped (acceptable; this is a public-repo cron, not a SaaS SLA).
- `actions/cache@v4` for Playwright — saves 60–90 seconds per run on Chromium download. Cache key tied to `requirements.lock` so a Playwright version bump invalidates correctly.
- `--with-deps chromium` — installs Chromium *and* the system libs Chromium needs; first run installs both, subsequent runs hit the cache.
- `stefanzweifel/git-auto-commit-action@v5` — only commits when there's a diff; no-ops cleanly otherwise (no empty "nothing changed" commits cluttering history).
## GitHub Actions Free-Tier Resource Reality Check
| Resource | Limit (public repo, ubuntu-latest, 2025–2026) | Implication |
|----------|-----------------------------------------------|-------------|
| Minutes | **Unlimited** for public repos | Hourly cron is free forever |
| Disk | ~14 GB usable | Plenty for one Chromium install (~400 MB with deps) + repo |
| RAM | 7 GB (standard) → 16 GB (large, paid) | Chromium uses 200–500 MB per page; we serialize per company so RAM never a problem |
| CPU | 2 vCPU (standard) | Async fan-out for ATS APIs is the right call; CPU is not the bottleneck — network is |
| Concurrent runs | 20 jobs / 5 cron jobs on free | We run one cron, one job — well under |
| Cron drift | Cron can be **delayed by 15–60 min** under load on free tier | The "hourly" promise is approximate; document this — don't claim sub-hour precision |
| Cache size | 10 GB per repo, evicted after 7 days unused | Playwright cache (~400 MB) fits easily; refreshes weekly which keeps it current |
## Alternatives Considered (and rejected)
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| HTTP client | httpx | requests | Sync-only, maintenance mode |
| HTTP client | httpx | aiohttp | Async-only, forces async everywhere |
| Browser | Playwright | Selenium | Worse auto-wait, slower, weaker interception |
| Browser | Playwright | pyppeteer | Unmaintained |
| Browser | Playwright | Splash | Requires separate Docker service |
| HTML parsing | selectolax + bs4 | lxml direct | Chokes on real-world malformed HTML |
| HTML parsing | selectolax + bs4 | parsel | Scrapy-coupled; we're not using Scrapy |
| Scraping framework | (none — direct scripts) | Scrapy | Massive overhead for a 20–100 URL cron; spiders/pipelines/middleware are overkill |
| State storage | JSON in repo | SQLite in repo | Opaque binary diffs, unmergeable conflicts |
| State storage | JSON in repo | External DB (Supabase, Turso) | Violates $0 + public-repo-as-database principle |
| Validation | pydantic v2 | dataclasses | No runtime validation = silent ATS-drift bugs |
| Validation | pydantic v2 | attrs | pydantic is more idiomatic for API-shape validation |
| Markdown table | f-string | Jinja2 | Single template; YAGNI |
| Markdown table | f-string | pandas `.to_markdown()` | Pandas is ~50 MB for one table render — absurd |
| Commit-back | git-auto-commit-action | EndBug/add-and-commit | Both work; stefanzweifel is more popular and has cleaner skip-on-no-diff |
| Commit-back | git-auto-commit-action | Manual `git push` | Equally valid; saves one action dep but adds YAML |
| Date parsing | stdlib + dateparser | Arrow / Pendulum | Stdlib + dateparser covers everything we need |
| Logging | stdlib logging | loguru / structlog | Single script; overkill |
| Package install | uv | pip | uv is 10–100x faster; matters on every run |
| ATS access | Direct JSON adapters | Paid jobs API aggregator | Violates $0 constraint, adds upstream failure |
## Installation (local dev)
# Once
# Run
## Sources
- Direct PyPI / official-docs verification was **blocked during this research pass**. Recommendations draw on training data (knowledge cutoff Jan 2026).
- **Action item for Phase 0 / setup:** Run `uv pip index versions <package>` for each pinned dep and update the lock file to the latest stable as of project start.
- **ATS endpoint patterns** (Greenhouse, Lever, Ashby, SmartRecruiters, Workday CXS, Apple jobs) are community-documented and stable as of training cutoff — but they are unofficial APIs and can change without notice. PITFALLS.md must call this out.
- **GitHub Actions limits** (unlimited minutes for public repos, cron drift on free tier, `permissions: contents: write` requirement) are documented behavior as of training cutoff; verify against current GitHub docs before commit.
## Confidence Summary
| Area | Confidence | Why |
|------|-----------|-----|
| Language choice (Python 3.12) | HIGH | User-preferred, ecosystem fit |
| HTTP client (httpx) | HIGH | Industry standard for 2024–2026 async scraping |
| Headless browser (Playwright) | HIGH on choice, MEDIUM on exact version | Verify `>=1.45` floor against PyPI before locking |
| HTML parsing (selectolax + bs4) | MEDIUM | selectolax is fast but smaller ecosystem; bs4 fallback de-risks |
| ATS endpoints | HIGH (Greenhouse/Lever/Ashby/SR/Workday), MEDIUM (Apple) | Community-stable but unofficial — drift is the #1 maintenance burden |
| GitHub Actions wiring | HIGH | All actions cited (`checkout@v4`, `setup-python@v5`, `cache@v4`, `git-auto-commit-action@v5`) are current major tags |
| State format (JSON) | HIGH | Diff-friendly + zero deps; correct call for repo-as-database |
| Validation (pydantic v2) | HIGH | Catches silent ATS shape changes — critical for long-term robustness |
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

## Adding a Company

When the user says "add this URL: <URL>", follow this 5-step flow autonomously. The user provides only the URL (and credentials if the site needs login).

### Step 1: Try existing adapters

Call `get_adapter(CompanyConfig(name=<derived>, url=<URL>))`. If an adapter matches (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Apple) → append `<URL>` to `companies.txt`, commit `chore(companies): add <name>`, push. **Done.**

### Step 2: Resolve redirects

Call `resolve_url(<URL>)` (Phase 3 Plan 03-01 helper). If the resolved URL differs from the original, re-try `get_adapter(CompanyConfig(name=<derived>, url=<URL>, resolved_url=<resolved>))`. If now matches (typical CNAME→Workday case) → append the **resolved** URL (not the original — per D-03a) to `companies.txt`. Commit. **Done.**

### Step 3: Playwright catch-all

If no specific adapter matches even after resolution, `PlaywrightAdapter` will handle it (registered LAST in `ADAPTERS`). Before committing:

1. Append `<URL>` to `companies.txt`.
2. Run a one-shot verification:
   ```bash
   python -c "from src.adapters.playwright_fallback import PlaywrightAdapter; \
              from src.models import CompanyConfig; \
              r = PlaywrightAdapter().fetch(CompanyConfig(name='<derived>', url='<URL>')); \
              print(len(r))"
   ```
   The output should be at least 1 (or the adapter should raise a typed `PlaywrightTimeout` we can diagnose).
3. If verification succeeds → commit. **Done.**
4. If verification fails → step 4.

### Step 4: Write a new adapter (rare)

Playwright catch-all couldn't extract postings cleanly — the site has a unique structure benefiting from a dedicated adapter.

1. Create `src/adapters/<name>.py` subclassing `Adapter` (mirror `src/adapters/apple.py` shape).
2. Insert `<NameAdapter>` into `ADAPTERS` in `src/registry.py` **before the Playwright catch-all** (at `len(ADAPTERS) - 1`) — does NOT modify any existing adapter file (ADP-15 invariant; `tests/test_adapter_contract.py` enforces this).
3. Append `_normalize_<name>` to `src/normalizer.py`'s `_DISPATCH`.
4. Write fixture + happy-path + 5 error-path tests mirroring `tests/test_apple_adapter.py`.
5. `pytest tests/ -v` — all 365+ tests still pass.
6. Append URL to `companies.txt`. Commit. **Done.**

### Step 5: Credential branch (jumps in BEFORE step 1 if detected)

When pasting a new URL, first probe whether it needs login: `httpx.get(<URL>, follow_redirects=True, timeout=5)` and search response body for `<input type="password">` or `<form action="*login*">`. If found → credentialed site.

Then (per SEC-01 / SEC-02 / SEC-04):

1. **Inline-prompt the user in chat:**

   > "This site requires login. What email and password should I use? (I will store them as `SCRAPER_<COMPANY>_EMAIL` and `SCRAPER_<COMPANY>_PASSWORD` via `gh secret set` — values will never appear in chat history, repo files, or workflow logs.)"

2. **Store secrets** (the user pastes them in chat once; never echo back):
   ```bash
   gh secret set SCRAPER_<COMPANY_UPPERCASE>_EMAIL --repo DevDesai444/new-grad --body "<email>"
   gh secret set SCRAPER_<COMPANY_UPPERCASE>_PASSWORD --repo DevDesai444/new-grad --body "<password>"
   ```
   `<COMPANY_UPPERCASE>` is `company.name` uppercased with hyphens and spaces replaced by underscores. See `PlaywrightAdapter._company_to_secret_prefix` in `src/adapters/playwright_fallback.py`.

3. **Verify by listing** (names ONLY, never values per SEC-04):
   ```bash
   gh secret list --repo DevDesai444/new-grad
   ```

4. **One-shot login test** (uses the stored secrets via env-var mapping in the workflow YAML; for local verification, run with the values temporarily in shell env, NEVER in a committed file):
   ```bash
   SCRAPER_<COMPANY>_EMAIL="<email>" SCRAPER_<COMPANY>_PASSWORD="<password>" \
     python -c "from src.adapters.playwright_fallback import PlaywrightAdapter; \
                from src.models import CompanyConfig; \
                print(PlaywrightAdapter().fetch(CompanyConfig(name='<lowercase>', url='<URL>')))"
   ```
   - If returns ≥1 RawPosting → credentials work; continue to step 1.
   - If raises `InvalidCredential` → re-prompt the user; **do NOT echo what was tried**.
   - If raises `MissingCredential` → env-var setup failed; re-run the `gh secret set` and shell-env steps.

5. **Update README SEC-06 secret-audit table** with the new entry.

6. Append URL to `companies.txt`; commit.

**Never echo credential values back in chat.** **Never commit them to any file.** **Never include them in commit messages or workflow logs.** GitHub auto-masks values registered as secrets in the `${{ secrets.* }}` block, but verify per-secret with `gh secret list`.

**Out of scope for v1** (per CONTEXT.md `<deferred>`): 2FA, OAuth, magic-link auth. If the site requires any of these, document as unsupported and skip.

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
