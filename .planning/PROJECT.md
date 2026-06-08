# new-grad

## What This Is

An automated job-posting tracker that scans a configurable list of company career pages every hour for new grad / early-career roles (0–5 yrs experience) and publishes the current list as a Markdown table in a public GitHub repo. The user (Dev Desai) opens the repo, sees every posting, and applies directly via the linked posting URL — no manual scanning, no notifications, no extra tooling.

## Core Value

**One glance at the GitHub repo shows every currently-known new-grad-eligible role across the user's tracked companies, with a working application link.** If hourly refresh, dedup, or the linked posting fail, the system loses its point.

## Requirements

### Validated

- ✓ System scans every company in `companies.txt` once per hour, automatically — v1.0 (GitHub Actions hourly cron with concurrency group + timeout-minutes: 50)
- ✓ System runs entirely on GitHub Actions (no laptop, no paid server, no manual trigger) — v1.0
- ✓ System supports any career-page URL via 7 adapters: Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Apple, Playwright (catch-all for JS-heavy SPAs) — v1.0
- ✓ Filters postings to early-career roles via title-keyword gate (FILT-01/02/05/06) + JD-scan extracts experience range (FILT-03 informational, FILT-04 softened to display-only per Phase 2 D-02) — v1.0
- ✓ Markdown table in `README.md` with 7-col order `Company | Position | Location | Salary | Experience | Posting | Age` rendered between sentinel markers — v1.0
- ✓ Experience range extracted from JD via regex; surfaced in Experience column — v1.0 (display-only per D-02)
- ✓ No duplicates — per-ATS stable dedup keys (`gh:<co>:<id>`, `lever:<co>:<uuid>`, `ashby:<org>:<uuid>`, `sr:<co>:<id>`, `wd:<tenant>:<id>`, `apple:<id>`, `pw:<host>:<id>`) — v1.0
- ✓ Stale postings preserved forever (STATE-04 add-only merge; keys never deleted) — v1.0
- ✓ Age column uses source `posted_date` when available, falls back to `first_seen` — v1.0
- ✓ Posting URL is a clickable Markdown link to the original career portal — v1.0
- ✓ Hourly commit-back via `stefanzweifel/git-auto-commit-action@v5` with `GITHUB_TOKEN` — v1.0
- ✓ Claude CLI "Adding a Company" 5-step workflow documented in CLAUDE.md (try existing → resolve redirect → Playwright catch-all → write new adapter → credential branch) — v1.0
- ✓ Credentials stored only as GitHub Actions Secrets via `SCRAPER_<CO>_<KIND>` convention; PlaywrightAdapter reads via `os.environ[...]`; never echoed in chat, never committed, never logged (SEC-03 structurally enforced) — v1.0
- ✓ US-only region filter (FILT-07) — new requirement added during Phase 4 discuss; drops non-US postings via 8-rule classifier; ambiguous locations kept per FILT-05 bias — v1.0

### Active

(All v1.0 requirements validated. Next milestone requirements TBD via `/gsd-new-milestone`.)

### Out of Scope (audited at v1.0 close)

- **Notifications (email/Slack/SMS/push)** — user explicitly wants to check the repo manually; no notifications
- **Web UI / dashboard** — table-in-README on GitHub is the entire UI
- **Apply-on-behalf / autofill** — user clicks the link and applies themselves
- **Resume tailoring, cover letters, application tracking** — out of scope; this is a discovery tool only
- **Senior / staff / principal / manager roles** — explicitly excluded by the 0–5 yrs filter
- **Auto-removal of closed postings** — user wants stale entries kept even if links eventually 404
- **Local cron / laptop-dependent execution** — must run in the cloud (GitHub Actions only)
- **Private repo** — public repo chosen to get unlimited free GitHub Actions minutes
- **Notification of duplicates / errors** — silent; user inspects repo if something seems off
- **Multi-user support** — single-user tool for Dev Desai only

## Context

**User**: Dev Desai (github.com/DevDesai444). Looking for new grad / early-career roles. Wants a zero-touch system — set it up once, then just open the repo and apply when there's something worth applying to.

**Why now**: Manually checking 20+ company career pages is tedious. ATS platforms (Greenhouse, Lever, Workday) make this scriptable, but many big-name companies (Apple, Nvidia, Google) use custom or JS-heavy portals that need browser automation. The user wants ONE system that handles all of them.

**Technical environment**:
- Public GitHub repo (unlimited Actions minutes)
- Python 3 + Playwright for browser-based scraping fallback
- ATS-specific adapters where APIs/JSON endpoints exist (faster, more reliable than Playwright)
- Persistent state file (`seen.json`) in the repo tracking every posting ever observed (key, first-seen, last-seen, posted-date) — needed for dedup, Age column, and the "keep forever" requirement
- `companies.txt` — one careers URL per line, the source of truth for what gets scanned
- GitHub Actions cron (`0 * * * *`) triggers the hourly scan
- Commits are made by GitHub Actions bot to the user's repo; pushes happen on every run that produces changes

**Known scraping realities**:
- Workday URLs expose a JSON search API at `<host>/wday/cxs/<tenant>/<site>/jobs` — fast, reliable
- Apple jobs uses `jobs.apple.com/api/role/search` — JSON, fast
- Greenhouse, Lever, Ashby, SmartRecruiters all have well-known JSON endpoints
- Sites without an ATS pattern fall back to Playwright headless browser
- Some sites may rate-limit / block automation; the design must tolerate per-site failures without failing the whole run

## Constraints

- **Tech stack**: Python 3 + Playwright (chosen for best-in-class scraping ecosystem and Playwright's robust JS-rendering)
- **Hosting**: GitHub Actions only — cron-driven, free tier of public repo, no other infrastructure
- **Budget**: $0/month — must stay within GitHub's free tier indefinitely
- **Storage**: All state (companies list, seen postings, table) lives in the same public GitHub repo. No database.
- **Security**: Any per-site credentials → GitHub Actions Secrets. Never committed. Never logged.
- **Cadence**: Hourly scan — non-negotiable (the "every hour" promise is the product)
- **Privacy**: Repo is public — the list of companies being tracked, postings found, and history are all publicly visible. No personal data (resume, email, etc.) goes in the repo.
- **Resilience**: A single company failing must not block the rest of the scan. Per-site try/except with logging.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| GitHub Actions cron, not laptop cron | User wants zero-touch; laptop must not need to be on | — Pending |
| Public repo over private | Public gets unlimited free Action minutes; Playwright scans of many companies could exceed the 2,000 min/mo private cap | — Pending |
| Python + Playwright stack | Best ecosystem for hybrid ATS-API + headless-browser scraping | — Pending |
| Markdown table in README.md | Repo homepage = the UI; no separate site needed | — Pending |
| Keep stale postings forever | User explicitly prefers history over freshness; accepts that some links will eventually 404 | — Pending |
| Experience range as its own column | User wants visibility into 0–5 yrs spread per posting | — Pending |
| Dedup by company + posting URL | Most stable unique identifier across re-scans | — Pending |
| `seen.json` state file committed to the repo | No database; repo IS the database | — Pending |
| Credentials in GitHub Actions Secrets only | Public repo means anything in the repo is exposed; secrets must stay out | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-07 after initialization*
