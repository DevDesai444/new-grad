# Technology Stack

**Project:** new-grad (automated career-page job tracker)
**Researched:** 2026-06-07
**Overall confidence:** MEDIUM (versions and ATS endpoints verified against training-data; pin exact versions in `requirements.txt` after a `pip index versions` check at install time)

> **Source note:** External research tools (WebSearch, WebFetch, Bash, Context7) were unavailable during this research pass. Recommendations below draw on training data (knowledge cutoff Jan 2026) plus the user's already-validated assumptions in `PROJECT.md`. Each recommendation carries an explicit confidence level. Where confidence is MEDIUM/LOW, the roadmap should add a "verify latest version against PyPI" task in Phase 0 / setup.

---

## Recommended Stack

### Runtime

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **Python** | 3.12 (3.13 acceptable) | Primary language | User-preferred; best ecosystem for hybrid HTTP + headless browser scraping; both Greenhouse/Lever client libs and Playwright are Python-first | HIGH |
| **GitHub Actions** (ubuntu-latest) | runner image refreshed continuously | Cron host | Free unlimited minutes on public repos; native git push; pre-installed Python; matrix support if we ever shard | HIGH |

**Why not Node.js / TypeScript:** Playwright is technically first-class in Node, but ATS parsing, salary/experience regex, and Markdown table generation are markedly more concise in Python, and the user explicitly prefers Python. The dual-language overhead isn't worth marginal Playwright maturity gains.

**Why not Python 3.13 as the floor:** As of early 2026, several scraping libs (notably `lxml` wheels and some Playwright transitive deps) still smoke-test against 3.12 first. 3.12 is the safe LTS-equivalent choice; 3.13 works but adds minor risk for zero upside on a cron job.

---

### HTTP Client (ATS API path)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **httpx** | `>=0.27,<1.0` | Async + sync HTTP for ATS JSON endpoints | Single library covers sync (simple scripts) and async (parallel fan-out across N companies); HTTP/2 support; modern timeout/retry semantics; widely adopted for scraping in 2025–2026 | HIGH |
| **tenacity** | `>=8.2` | Retry with exponential backoff | Decorator-based; integrates cleanly with httpx; handles transient 429/5xx without us hand-rolling retry math | HIGH |

**Why not `requests`:** `requests` is sync-only and in maintenance mode (no active feature development since 2023). For an hourly fan-out across 20–100+ companies, async I/O cuts wall-clock time 5–10x and reduces Actions-minute consumption. `httpx` is the de-facto successor.

**Why not `aiohttp`:** `aiohttp` is async-only — forces async everywhere even for single-shot scripts. `httpx`'s dual-mode API lets us write sync code where it's simpler (Playwright fallback paths) and async where it pays (ATS fan-out).

**Why not `requests-html` / `httpx-html`:** Outdated, sparsely maintained, and we already have Playwright for JS rendering.

---

### HTML Parsing (Playwright fallback path)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **selectolax** | `>=0.3.21` | Fast HTML → CSS-selector parsing | C-based (Modest/Lexbor backend), 5–25x faster than BeautifulSoup; matters because Playwright already gives us a DOM, but post-rendering parsing of huge career-page HTML is the bottleneck | MEDIUM |
| **BeautifulSoup4** | `>=4.12` | Fallback parser for weird HTML | Permissive parser handles malformed HTML where selectolax fails; only used when selectolax raises | HIGH |

**Why not lxml directly:** selectolax wraps a more permissive parser; lxml chokes on real-world career-page HTML more often. We can pull `lxml` in transitively via BS4 if needed.

**Why not just use Playwright's `page.locator()`:** Each `locator.evaluate()` round-trips to the browser process — slow when extracting 50+ fields per page. Parse the HTML once with selectolax after `page.content()`.

---

### Headless Browser (JS-heavy SPA path)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **playwright** (Python) | `>=1.45` (1.49+ preferred if available) | Headless Chromium for JS-rendered career pages | Industry standard 2024–2026; Microsoft-backed; better auto-wait semantics than Selenium; built-in network interception (lets us sniff XHR endpoints and bypass DOM entirely for many sites) | HIGH on choice, MEDIUM on exact version |
| **playwright-stealth** | `>=1.0.6` | Light fingerprint masking | Some career portals (Workday, certain Apple pages) drop headless browsers; stealth plugin patches the most-checked telltales (`navigator.webdriver`, plugin shape, etc.) | MEDIUM |

**Chromium only** — don't install Firefox/WebKit. Each browser binary is ~150–300 MB; on GitHub Actions runners (14 GB disk, 7 GB RAM for ubuntu-latest as of 2025) we want lean installs. Chromium covers every site we'd target.

**Why not Selenium:** Worse auto-wait, worse network interception, slower on cold-start, and the WebDriver protocol overhead matters when we're rendering 5–20 pages per hour.

**Why not Puppeteer / pyppeteer:** Pyppeteer is unmaintained; Puppeteer is Node-only.

**Why not `requests-html` or `splash`:** Splash is a separate Docker service (adds Actions complexity); both are stale.

---

### State Persistence

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib `json`** | n/a | `seen.json` read/write | Zero dependencies; human-readable diffs in git PRs; the entire state file is small (KB → low MB at scale) | HIGH |
| **orjson** | `>=3.10` | Faster JSON serialization | 2–5x faster than stdlib; deterministic key ordering with `OPT_SORT_KEYS` (critical so git diffs are minimal/readable) | HIGH |

**Why not SQLite:** Tempting, but binary diffs in git are opaque, can't be reviewed in PRs, and merge conflicts are unsolvable. JSON is the right choice when the repo IS the database.

**Why orjson `OPT_SORT_KEYS`:** Without sorted keys, Python dict insertion order leaks into the file, causing spurious diffs every run. Sorted keys = clean diffs = readable history.

---

### Markdown Generation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib f-strings + manual table** | n/a | README.md table rendering | A GitHub-flavored Markdown table is 3 lines of f-string per row; pulling in a library here is overkill | HIGH |
| **(optional) tabulate** | `>=0.9` | If table grows columns/formatting complexity | Only add if README rendering becomes non-trivial; YAGNI for v1 | LOW |

**Why not Jinja2:** Overkill for a single, fixed-schema table. Adds a dep with no benefit until we have multiple templates.

---

### Data Validation / Models

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **pydantic** | v2 (`>=2.7`) | Posting / company / state schemas | Strong runtime validation catches ATS API drift (a field changing type silently); v2 is much faster than v1; widely adopted 2024–2026 | HIGH |

**Why pydantic over `dataclasses`:** Dataclasses don't validate. When Greenhouse changes a field from `int` to `str` for some tenant, pydantic raises immediately at parse time; dataclasses would silently propagate the wrong type until something downstream crashes hours later. Worth the dep.

---

### Date / Time

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib `datetime` + `zoneinfo`** | n/a | Posting dates, "Age" column | All ATS APIs return ISO-8601 UTC; stdlib handles parsing and "X days ago" math; `zoneinfo` (Python 3.9+) replaces `pytz` | HIGH |
| **dateparser** | `>=1.2` | Free-text date fallback | When a custom career page exposes "Posted 3 days ago" or "March 2026" instead of ISO timestamps, `dateparser` handles 200+ formats; gracefully returns `None` on failure | MEDIUM |

**Why not Arrow / Pendulum:** stdlib is sufficient; extra dep doesn't earn its keep.

---

### Job-Description Text Filtering (0–5 yrs filter)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib `re`** | n/a | Experience-range regex over description text | Patterns like `\b(\d+)\+?\s*(?:to|-|–)?\s*(\d+)?\s*years?\b` cover ~90% of postings; well-understood; no model needed | HIGH |
| **(deferred) spaCy or LLM** | n/a | If regex precision is too low | Defer until v2 — measure regex precision/recall first | LOW |

**Anti-recommendation:** Don't reach for an LLM API for experience extraction on day 1. It's a paid service, adds latency and a fail mode, and a tight regex set is good enough. Revisit only if measurement shows the regex misses too much.

---

### Logging / Observability

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **stdlib `logging`** | n/a | Per-company structured logs | Free; Actions captures stdout/stderr automatically; surfaces in the Actions run UI | HIGH |
| **rich** (optional) | `>=13.7` | Local dev pretty output | Nice locally; on Actions it auto-degrades to plain text. Optional. | MEDIUM |

**Why not structlog / loguru:** Overkill for a single-script cron. Stdlib `logging` with a JSON formatter (if we want structured logs) is enough.

---

### GitHub Actions / Commit-Back

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **actions/checkout** | `@v4` | Repo checkout | Pinned major tag; v4 is the current standard 2024–2026 | HIGH |
| **actions/setup-python** | `@v5` | Python install | Current standard | HIGH |
| **actions/cache** | `@v4` | Pip + Playwright browser cache | v4 mandatory after v3 deprecation in early 2025; required for Playwright cache to actually persist | HIGH |
| **stefanzweifel/git-auto-commit-action** | `@v5` | Commit & push README + seen.json | Battle-tested; handles the "only commit if there's a diff" case cleanly; uses `GITHUB_TOKEN` so no PAT needed for default-branch pushes | HIGH |

**`permissions:` block** — must include `contents: write` at the job level so `GITHUB_TOKEN` can push. Default token is read-only as of 2023.

**Alternative for commit-back:** Plain `git config` + `git add` + `git commit` + `git push` inline. Equally valid; use stefanzweifel's action for less YAML.

---

### Configuration / Secrets

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **GitHub Actions Secrets** | n/a | Per-site auth (rare) | Surfaced as env vars; never committed; never echoed in logs (Actions masks them automatically) | HIGH |
| **python-dotenv** | `>=1.0` | Local dev only | Loads `.env` for local testing; `.env` in `.gitignore` | HIGH |

---

### Dev Tooling

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|-----------|
| **uv** | `>=0.4` | Fast pip-replacement | 10–100x faster than pip for install; matters on every Actions run (saves 30–90 sec of wall-clock); reads standard `requirements.txt` | MEDIUM |
| **ruff** | `>=0.6` | Lint + format | Replaces flake8/black/isort; one tool; fast | HIGH |
| **pytest** | `>=8.0` | Tests for ATS parsers (using captured JSON fixtures) | Standard; fixture support critical for replaying real ATS responses | HIGH |
| **respx** | `>=0.21` | Mock httpx in tests | First-class httpx mocker; lets us replay captured Greenhouse/Lever responses in tests without hitting the network | HIGH |

**Why uv over pip:** On a public-repo hourly cron, every minute saved is real (saves wear on the runner pool too). uv is now the de facto fast installer in 2025–2026.

---

## ATS-Specific Endpoints (no SDKs needed — pure JSON)

These are public, undocumented-but-stable endpoints. No "official SDK" exists for most of them; the recommended approach is a thin per-ATS adapter calling these directly with `httpx`.

| ATS | Endpoint Pattern | Auth | Confidence |
|-----|------------------|------|-----------|
| **Greenhouse** | `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true` | None (public boards) | HIGH |
| **Lever** | `https://api.lever.co/v0/postings/{company}?mode=json` | None (public) | HIGH |
| **Ashby** | `https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true` | None (public job board API) | HIGH |
| **SmartRecruiters** | `https://api.smartrecruiters.com/v1/companies/{company}/postings` | None (public) | HIGH |
| **Workday** | `POST https://{host}/wday/cxs/{tenant}/{site}/jobs` (JSON body with `limit`, `offset`, `searchText`) | None | HIGH (well-documented in scraping community) |
| **Apple Jobs** | `https://jobs.apple.com/api/role/search` (POST JSON) | None | MEDIUM (endpoint stable but shape changes occasionally) |
| **iCIMS** | varies per tenant; usually `/jobs/search/...` or RSS feed | None | MEDIUM |

**Adapter pattern:** One Python module per ATS (`adapters/greenhouse.py`, `adapters/workday.py`, etc.) exposing a `fetch(url_or_config) -> list[Posting]` function. URL → adapter dispatch lives in a registry. New ATS = new file, no core changes.

**Anti-recommendation:** Don't use any "unified jobs API" service (e.g., paid aggregators) — violates the $0 constraint and adds an upstream failure point.

**No official SDKs for ATSes:** Greenhouse publishes a Harvest API (paid/keyed, for employers), but the public board API is direct JSON. There is no maintained Python SDK worth pulling in.

---

## Final `requirements.txt` (recommended)

```text
# Core HTTP / parsing
httpx[http2]>=0.27,<1.0
tenacity>=8.2
selectolax>=0.3.21
beautifulsoup4>=4.12

# Headless browser (Chromium only)
playwright>=1.45
playwright-stealth>=1.0.6

# Data
pydantic>=2.7
orjson>=3.10
dateparser>=1.2

# Local dev only
python-dotenv>=1.0
```

```text
# requirements-dev.txt
pytest>=8.0
respx>=0.21
ruff>=0.6
```

**Pin exact versions** in the lockfile (`uv pip compile requirements.txt -o requirements.lock`) so Actions runs are deterministic. The `>=` floors above are minimums known to work; the lock pins the resolved set.

---

## GitHub Actions Workflow Pattern

```yaml
name: scan
on:
  schedule:
    - cron: "0 * * * *"  # hourly
  workflow_dispatch:      # manual trigger for testing

permissions:
  contents: write          # required for git-auto-commit to push

concurrency:
  group: scan
  cancel-in-progress: false  # let an in-flight run finish; don't overlap

jobs:
  scan:
    runs-on: ubuntu-latest
    timeout-minutes: 50    # hard ceiling; cron interval is 60 min
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install uv
        run: pipx install uv

      - name: Install Python deps
        run: uv pip install --system -r requirements.lock

      - name: Cache Playwright browsers
        uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: playwright-${{ runner.os }}-${{ hashFiles('requirements.lock') }}

      - name: Install Playwright Chromium
        run: python -m playwright install --with-deps chromium

      - name: Run scan
        run: python -m scanner
        env:
          # any per-site secrets surfaced here
          EXAMPLE_SITE_TOKEN: ${{ secrets.EXAMPLE_SITE_TOKEN }}

      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: hourly scan update"
          file_pattern: "README.md seen.json"
```

**Key details:**
- `timeout-minutes: 50` — protects against a hung Playwright session burning the next hour's slot.
- `concurrency.cancel-in-progress: false` — never let two runs race on the same `seen.json`. If a run takes 70 min, the next one waits or gets dropped (acceptable; this is a public-repo cron, not a SaaS SLA).
- `actions/cache@v4` for Playwright — saves 60–90 seconds per run on Chromium download. Cache key tied to `requirements.lock` so a Playwright version bump invalidates correctly.
- `--with-deps chromium` — installs Chromium *and* the system libs Chromium needs; first run installs both, subsequent runs hit the cache.
- `stefanzweifel/git-auto-commit-action@v5` — only commits when there's a diff; no-ops cleanly otherwise (no empty "nothing changed" commits cluttering history).

---

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

**Cron drift is the biggest hidden risk.** GitHub explicitly states scheduled workflows on free tier can be delayed or skipped during high load. For this product (job postings, not stock trading), occasional 15-min drift is fine — but PITFALLS.md should call it out so the user doesn't chase "why didn't it run at exactly :00."

---

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

---

## Installation (local dev)

```bash
# Once
pipx install uv
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium

# Run
python -m scanner --dry-run  # no commit
```

---

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
