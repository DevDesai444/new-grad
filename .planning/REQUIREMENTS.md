# Requirements: new-grad

**Defined:** 2026-06-07
**Core Value:** One glance at the GitHub repo shows every currently-known new-grad-eligible role across the user's tracked companies, with a working application link.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Infrastructure (INFRA)

- [x] **INFRA-01**: System runs as a GitHub Actions cron job scheduled hourly (`0 * * * *`) with `timeout-minutes: 50`
- [x] **INFRA-02**: Workflow declares `permissions: contents: write` and `concurrency: { group: scan, cancel-in-progress: false }` so runs serialize and pushes succeed
- [x] **INFRA-03**: Python 3.12 environment installed via `uv` with `actions/setup-python@v5` and dependency caching on `requirements.lock`
- [x] **INFRA-04**: Playwright Chromium browser cache restored via `actions/cache@v4` keyed on dep lockfile (avoids 60–90s cold install per run)
- [ ] **INFRA-05**: `health.json` is updated every run (including failed runs) so the workflow always produces ≥1 commit candidate per run — prevents GitHub's 60-day schedule auto-disable
- [x] **INFRA-06**: Repo is public, owned by `github.com/DevDesai444`, named `new-grad`
- [x] **INFRA-07**: `.gitignore` blocks `.env`, `*.har`, `trace.zip`, `cookies.json`, `__pycache__/`, `.pytest_cache/`, `seen.json.tmp`, `seen.json.bak`
- [x] **INFRA-08**: GitHub repo secret scanning + push protection enabled in repo settings (documented in README setup)
- [x] **INFRA-09**: Any per-site credentials (rare) are stored only in GitHub Actions Secrets, read via `os.environ[...]`, never committed
- [x] **INFRA-10**: Commits and pushes use `stefanzweifel/git-auto-commit-action@v5` with `GITHUB_TOKEN`; no PAT required

### Configuration (CFG)

- [x] **CFG-01**: `companies.txt` is the single source of truth — **the user only ever pastes one careers URL per line**; no other metadata, labels, hints, or fields are required from the user
- [x] **CFG-02**: Blank lines and `#`-prefixed comment lines are allowed in `companies.txt` and skipped by the loader
- [x] **CFG-03**: An optional inline `#adapter=<name>` hint on a URL line (added by Claude, never required of the user) overrides URL-pattern dispatch when needed
- [x] **CFG-04**: When the user instructs Claude CLI to "add company X" with a URL, Claude alone performs all necessary work: append the URL to `companies.txt`, add a new adapter if needed (per ADP-14), set up GitHub Actions Secrets if credentials are needed (per SEC-01), commit, and push. The user provides only the URL (and credentials if asked).
- [x] **CFG-05**: Malformed entries in `companies.txt` (invalid URL, unsupported scheme) are logged and skipped; the run continues
- [x] **CFG-06**: README documents the `companies.txt` format from the user's perspective: "paste career URLs, one per line"

### Scraping Adapters (ADP)

- [x] **ADP-01**: An `Adapter` ABC with `matches(url) -> bool` and `fetch(company) -> list[RawPosting]` defines the per-source contract
- [x] **ADP-02**: A URL-pattern registry dispatches each `companies.txt` entry to the right adapter; Playwright is the catch-all when nothing else matches
- [x] **ADP-03**: Greenhouse adapter — fetches `boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true`, validates response via pydantic v2, emits stable key `gh:<company>:<id>`
- [x] **ADP-04**: Lever adapter — fetches `api.lever.co/v0/postings/<company>?mode=json`, stable key `lever:<company>:<uuid>`
- [x] **ADP-05**: Ashby adapter — fetches `api.ashbyhq.com/posting-api/job-board/<org>`, stable key `ashby:<org>:<uuid>`
- [x] **ADP-06**: SmartRecruiters adapter — fetches `api.smartrecruiters.com/v1/companies/<co>/postings`, stable key `sr:<co>:<id>`
- [x] **ADP-07**: Workday adapter — POSTs to `<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs` with pagination, stable key `wd:<tenant>:<id>`, handles epoch-ms dates
- [x] **ADP-08**: Apple Jobs adapter — POSTs to `jobs.apple.com/api/role/search`, stable key `apple:<id>`
- [ ] **ADP-09**: Playwright fallback adapter — uses Chromium with `wait_for_selector` or `expect_response` interception, 20s per-page navigation timeout, post-render parse via selectolax
- [ ] **ADP-10**: `playwright-stealth` is applied conditionally only on sites that demonstrably need it (per-site flag in registry)
- [x] **ADP-11**: Each adapter raises typed errors: `SiteBlocked` (rate limit / IP block), `SchemaDrift` (pydantic validation failed), `PlaywrightTimeout`, or generic `Exception` — distinct from "zero results found"
- [x] **ADP-12**: One company's adapter failure is caught by the orchestrator and does not abort the run for the other companies
- [x] **ADP-13**: Per-adapter unit tests run against recorded JSON fixtures in `tests/fixtures/` via `respx` for HTTP mocking
- [x] **ADP-14**: When the user adds a career URL that no existing adapter recognizes, Claude creates a new adapter file `src/adapters/<name>.py` implementing the `Adapter` ABC and registers it. Existing adapter files MUST NOT be modified for this to land (Open/Closed). The new adapter is covered by at least one unit test using a recorded fixture before it ships.
- [x] **ADP-15**: Adapter additions are reversible — removing or disabling one adapter file (and its registry line) must not break any other adapter or the orchestrator

### Filtering (FILT)

- [x] **FILT-01**: Title-keyword filter includes: `new grad`, `new graduate`, `entry`, `entry-level`, `early career`, `early-career`, `junior`, `associate`, `university`, `recent graduate`, `class of 20XX`, and Roman/Arabic `I`/`1` level markers
- [x] **FILT-02**: Title-keyword filter excludes: `senior`, `sr.`, `staff`, `principal`, `lead`, `manager`, `director`, `head of`, `II`, `III`, `IV`, `V`, levels `2`/`3`/`4`/`5`+
- [x] **FILT-03**: JD-text scan extracts experience range using regex patterns (`X+ years`, `X-Y years`, `0-N years`, `recent graduate`, `entry level`) and populates `experience_min` / `experience_max`
- [x] ~~**FILT-04**~~: A posting is kept if (title passes keyword gate) AND (extracted `experience_min ≤ 5` OR no experience range found)  *[Softened per .planning/phases/02-ats-breadth-jd-scan/02-CONTEXT.md D-02: JD-scan is display-only; title gate alone decides inclusion. experience_min/max now populate the Experience column rather than gate the row.]*
- [x] **FILT-05**: When the title is ambiguous (no included or excluded keywords) and JD-scan finds no experience signal, the posting is included (bias toward inclusion at this gate, so the table doesn't miss things)
- [x] **FILT-06**: Filter logic is a pure function with no I/O; covered by unit tests with representative title/description fixtures

### Normalization & Extraction (NORM)

- [x] **NORM-01**: A canonical `Posting` model includes: `dedup_key`, `company`, `title`, `location`, `salary`, `experience_min`, `experience_max`, `posting_url`, `posted_date`, `first_seen`, `last_seen`, `still_listed`, `source_adapter`
- [ ] **NORM-02**: Salary extraction recognizes range (`$X–$Y`), ceiling (`up to $X`), hourly (`$X/hr`), and currency-prefixed formats; unparseable salary renders as `—`
- [ ] **NORM-03**: Location normalization collapses `Remote, United States` / `Remote — US` / `Remote (USA)` to a consistent `Remote (US)` form
- [x] **NORM-04**: Posted date is extracted from the source adapter when exposed; missing dates leave `posted_date` null
- [x] **NORM-05**: All dates are normalized to UTC ISO 8601 strings
- [x] **NORM-06**: URL canonicalization strips known tracking params (`utm_*`, `gh_src`, `lever-source`), lowercases the host, and removes trailing slashes — applied to `posting_url` before storage
- [x] **NORM-07**: Markdown cell escaping handles pipe characters, newlines, and invisible Unicode (U+200B, U+200C, U+200D, U+FEFF, U+00A0, U+2060) in titles/locations

### State & Dedup (STATE)

- [x] **STATE-01**: All persistent state lives in `seen.json` at the repo root — a single dict keyed by per-ATS stable dedup key
- [x] **STATE-02**: Writes are atomic — write to `seen.json.tmp` then `os.replace()` (POSIX-atomic)
- [x] **STATE-03**: Reads tolerate corruption — on `json.JSONDecodeError`, fall back to `seen.json.bak` and log
- [x] **STATE-04**: Merge is add-only — new keys get `first_seen = run_started_at`; existing keys keep their `first_seen` and update `last_seen`; **keys are never deleted** (per user's "keep forever" requirement)
- [x] **STATE-05**: When a key seen in a previous run is missing from the current scan, `last_seen` stays unchanged and `still_listed` flips to `false`
- [x] **STATE-06**: Sanity gate aborts the commit if `len(new_postings_seen) < 0.9 * len(prior_postings_seen)` for a run where no adapter reported `SiteBlocked` — protects against mass-block silently wiping the table
- [x] **STATE-07**: `seen.json` is serialized via `orjson` with `OPT_SORT_KEYS` for deterministic git diffs
- [x] **STATE-08**: `seen.json` schema includes a `schema_version` field; loader validates it and refuses to run on unknown future versions

### Output & Render (OUT)

- [x] **OUT-01**: `README.md` contains a section bracketed by `<!-- BEGIN JOBS -->` and `<!-- END JOBS -->` sentinels; the renderer overwrites only the content between sentinels
- [x] **OUT-02**: Table columns, in order: `| Company | Position | Location | Salary | Experience | Posting | Age |`
- [x] **OUT-03**: `Posting` column is a clickable Markdown link pointing to the canonicalized posting URL
- [x] **OUT-04**: `Age` renders the human-readable interval since `posted_date` if known, else since `first_seen` (e.g., `3h`, `2d`, `3w`)
- [x] **OUT-05**: `Experience` renders `Xy–Yy` if both bounds known, `≤Yy` if only max known, or blank if unknown
- [x] **OUT-06**: Table is sorted by `posted_date` descending (most recent first), then by company name ascending; sort is stable across runs given identical input
- [x] **OUT-07**: Renderer is a pure function — given identical input it produces byte-identical output (idempotent)
- [x] **OUT-08**: Render runs even when zero postings exist — the section between sentinels then contains a "(no matching postings yet)" placeholder
- [ ] **OUT-09**: A per-source health footer below the table shows `Company | Last seen | Status (ok/blocked/schema-drift/error)` for passive observability without notifications

### Credentials & Secrets (SEC)

- [ ] **SEC-01**: When adding a company whose career site requires login to scrape useful results, Claude inline-prompts the user for email + password (and any other credential the site needs), receives them in the chat, and stores them via `gh secret set <NAME> --repo DevDesai444/new-grad` — the user does no manual repo-config work
- [ ] **SEC-02**: Secret naming convention: `SCRAPER_<COMPANY>_EMAIL` and `SCRAPER_<COMPANY>_PASSWORD` (or similar typed names per credential kind); the secret name is referenced in the adapter via `os.environ[<NAME>]`
- [x] **SEC-03**: Credentials are NEVER written to: `companies.txt`, the repo, any committed file, any local file outside of `gh` CLI internals, the chat history (echoed back), or workflow logs
- [ ] **SEC-04**: After storing a secret, Claude confirms by listing `gh secret list --repo DevDesai444/new-grad` (which shows names only, not values) — never by echoing the value
- [x] **SEC-05**: Adapter code that reads credentials raises a typed `MissingCredential` error if the env var is unset on a production run; this is logged and isolated per company (other companies in the same run still scan)
- [ ] **SEC-06**: README documents which secret names are referenced by which adapter so the user can audit / rotate / delete them via `gh secret` later

### Run Lifecycle & Commit (RUN)

- [x] **RUN-01**: A single `run_started_at` UTC timestamp is captured at orchestrator start and threaded through all downstream components — no other component calls `datetime.now()`
- [x] **RUN-02**: Run summary is printed to the GitHub Actions step summary: counts of `+N new`, `M closed`, `K total open`, and per-source outcomes
- [x] **RUN-03**: The auto-commit step skips when no files changed (no-op runs do not push)
- [x] **RUN-04**: Commit message is informative: `chore(scan): +N new (Apple, Stripe), M closed (Anthropic)` when there are changes, else not committed at all

### Out of Scope (carried from PROJECT.md)

These are out of scope explicitly so they don't sneak back in.

## v2 Requirements

Deferred to a future milestone. Tracked but not in current roadmap.

### Sustainability (SUS)

- **SUS-01**: `seen.json` archive rollover — entries with `last_seen` older than 18 months move to `seen.archive.jsonl` (append-only, not read at runtime)
- **SUS-02**: `robots.txt` check per company on first scrape; skip explicitly disallowed paths
- **SUS-03**: Weekly `gitleaks detect --log-opts="--all"` history scan on a separate workflow
- **SUS-04**: `dependabot.yml` for weekly pip and Actions dep updates
- **SUS-05**: Manual `excluded_keywords.txt` / `included_keywords.txt` override files for filter tuning without code edits

### Operations (OPS)

- **OPS-01**: README ops runbook — recover from corrupted `seen.json`, add a company, disable a broken adapter, rotate a secret
- **OPS-02**: README ToS notice — public postings only, no auth required, hourly cadence is conservative, description text not mirrored
- **OPS-03**: `seen.json` size monitoring — alert threshold at 5MB documented in README footer

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Notifications (email/Slack/SMS/push) | User explicitly wants to check the repo manually; no notifications |
| Web UI / dashboard | Table-in-README on GitHub is the entire UI |
| Apply-on-behalf / autofill | User clicks the link and applies themselves |
| Resume tailoring, cover letters, application tracking | Out of scope; this is a discovery tool only |
| Senior / staff / principal / manager roles | Explicitly excluded by the 0–5 yrs filter |
| Auto-removal of closed postings | User wants stale entries kept even if links eventually 404 |
| Local cron / laptop-dependent execution | Must run in the cloud (GitHub Actions only) |
| Private repo | Public repo chosen to get unlimited free GitHub Actions minutes |
| Multi-user support | Single-user tool for Dev Desai only |
| Database (SQLite / Postgres / etc.) | `seen.json` in the repo is the database; no infrastructure beyond GitHub |
| LinkedIn / Indeed / aggregator scraping | Only company career pages — ToS hygiene + dedup complexity |
| LLM-based JD parsing | Regex covers 90% of cases; LLM call cost + latency not justified for v1 |

## Traceability

Which phases cover which requirements. Filled in by the roadmapper.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Complete |
| INFRA-05 | Phase 1 | Pending |
| INFRA-06 | Phase 1 | Complete |
| INFRA-07 | Phase 1 | Complete |
| INFRA-08 | Phase 1 | Complete |
| INFRA-09 | Phase 1 | Complete |
| INFRA-10 | Phase 1 | Complete |
| CFG-01 | Phase 1 | Complete |
| CFG-02 | Phase 1 | Complete |
| CFG-03 | Phase 1 | Complete |
| CFG-04 | Phase 1 | Complete |
| CFG-05 | Phase 1 | Complete |
| CFG-06 | Phase 1 | Complete |
| ADP-01 | Phase 1 | Complete |
| ADP-02 | Phase 1 | Complete |
| ADP-03 | Phase 1 | Complete |
| ADP-04 | Phase 2 | Complete |
| ADP-05 | Phase 2 | Complete |
| ADP-06 | Phase 2 | Complete |
| ADP-07 | Phase 2 | Complete |
| ADP-08 | Phase 2 | Complete |
| ADP-09 | Phase 3 | Pending |
| ADP-10 | Phase 3 | Pending |
| ADP-11 | Phase 1 | Complete |
| ADP-12 | Phase 1 | Complete |
| ADP-13 | Phase 1 | Complete |
| ADP-14 | Phase 1 | Complete |
| ADP-15 | Phase 1 | Complete |
| FILT-01 | Phase 1 | Complete |
| FILT-02 | Phase 1 | Complete |
| FILT-03 | Phase 2 | Complete |
| FILT-04 | Phase 1 | Complete |
| FILT-05 | Phase 1 | Complete |
| FILT-06 | Phase 1 | Complete |
| NORM-01 | Phase 1 | Complete |
| NORM-02 | Phase 4 | Pending |
| NORM-03 | Phase 4 | Pending |
| NORM-04 | Phase 1 | Complete |
| NORM-05 | Phase 1 | Complete |
| NORM-06 | Phase 1 | Complete |
| NORM-07 | Phase 1 | Complete |
| STATE-01 | Phase 1 | Complete |
| STATE-02 | Phase 1 | Complete |
| STATE-03 | Phase 1 | Complete |
| STATE-04 | Phase 1 | Complete |
| STATE-05 | Phase 1 | Complete |
| STATE-06 | Phase 1 | Complete |
| STATE-07 | Phase 1 | Complete |
| STATE-08 | Phase 1 | Complete |
| OUT-01 | Phase 1 | Complete |
| OUT-02 | Phase 1 | Complete |
| OUT-03 | Phase 1 | Complete |
| OUT-04 | Phase 1 | Complete |
| OUT-05 | Phase 1 | Complete |
| OUT-06 | Phase 1 | Complete |
| OUT-07 | Phase 1 | Complete |
| OUT-08 | Phase 1 | Complete |
| OUT-09 | Phase 4 | Pending |
| SEC-01 | Phase 3 | Pending |
| SEC-02 | Phase 3 | Pending |
| SEC-03 | Phase 1 | Complete |
| SEC-04 | Phase 3 | Pending |
| SEC-05 | Phase 1 | Complete |
| SEC-06 | Phase 3 | Pending |
| RUN-01 | Phase 1 | Complete |
| RUN-02 | Phase 1 | Complete |
| RUN-03 | Phase 1 | Complete |
| RUN-04 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 71 total (10 INFRA + 6 CFG + 15 ADP + 6 FILT + 7 NORM + 8 STATE + 9 OUT + 6 SEC + 4 RUN)
- Mapped to phases: 71/71 ✓ (no orphans, no double-maps)
- Per-phase distribution: Phase 1 = 58, Phase 2 = 6, Phase 3 = 6, Phase 4 = 3 (note: Phase 1 is foundation-heavy by design — all infra, state, basic adapter contract, basic filter, basic render, and run lifecycle land here so the walking skeleton is end-to-end on day one; subsequent phases add ATS breadth, JS fallback + credentials, and extraction polish)
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-07*
*Last updated: 2026-06-07 — Traceability table populated by roadmapper (4-phase MVP-mode roadmap)*
