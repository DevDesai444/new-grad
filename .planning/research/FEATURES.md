# Feature Landscape

**Domain:** Automated job-posting tracker (career-page scraper → Markdown table in public GitHub repo) for new grad / early-career roles
**Researched:** 2026-06-07
**Confidence (overall):** MEDIUM-HIGH (anchored in well-known public job-board GitHub projects and standard ATS scraping patterns; web verification was unavailable in this session — findings drawn from prior knowledge of SimplifyJobs/New-Grad-Positions, Pitt-CSC/Summer-Internships, ouckah/Summer-Internships, jobright-ai, and the published JSON shapes of Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Apple Jobs)

---

## How this maps to the user's stated product

The user's product is unusually well-scoped:

- **Discovery only.** Not a job board, not a CRM, not a notifier. Open repo → see table → click link → apply.
- **Single user.** No accounts, no preferences UI, no settings page.
- **History is a feature.** Stale postings stay in the table forever.
- **Repo IS the database.** No external storage. Everything reproducible from the repo.
- **GitHub Actions only.** Hourly cron, free public-repo minutes, no other infra.

Because the surface is so small, the meaningful feature work is almost entirely **data-extraction quality**, not UX. "Table stakes" below means *"if this is wrong, the table becomes useless"* — not *"users expect a search bar."*

---

## Table Stakes

Features without which the README table fails its stated job: showing the user a current, clickable, filtered list of new-grad-eligible roles.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Per-source fetcher with structured output | Every posting must produce `{company, title, location, url, ...}` regardless of source (ATS API vs Playwright). Without normalization at ingest, downstream dedup/filter logic explodes. | M | Depends on: ATS adapters + Playwright fallback. |
| ATS adapters: Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Apple | These cover the majority of big-name career pages and have stable JSON endpoints. Scraping HTML when JSON exists is wasteful and brittle. | M-L | Greenhouse/Lever/Ashby/SmartRecruiters: small (well-documented public JSON). Workday: medium (POST body with facets, per-tenant URL shape). Apple: small (single JSON endpoint, requires `Referer`/UA header in practice). |
| Playwright fallback for non-ATS sites | User explicitly listed JS-heavy SPAs (Nvidia Workday, Apple jobs, custom portals). Without a generic fallback, the tool covers only ATS-using companies. | L | Browser launch in GitHub Actions is feasible but slow; needs concurrency limit and per-site timeout. |
| URL-based source detection | Given a careers URL in `companies.txt`, the system must pick the right adapter (Greenhouse vs Lever vs Workday vs generic) without user labeling. | S | Pattern-match on hostname/path; fall through to Playwright. |
| Posting deduplication (stable key) | User requirement: never duplicate a row. Key = `company + canonical_posting_url`. | S | Depends on: URL canonicalization. |
| URL canonicalization | Same posting often appears under multiple URLs (tracking params, locale segments, mirrored sites). Without canonicalization, dedup fails silently. | S-M | Strip query params (`utm_*`, `gh_src`, `lever-source`), strip trailing slash, lowercase host, resolve known mirror patterns (e.g., `boards.greenhouse.io/X` vs `careers.X.com`). |
| Early-career filter (title keywords + JD scan) | User requirement: filter to 0–5 yrs. Title-only filtering misses many ("Software Engineer" can be new-grad or staff). JD scan catches the rest. | M | Title allowlist (`new grad`, `entry`, `junior`, `university`, `early career`, `associate`, `I`, `II`); title denylist (`senior`, `staff`, `principal`, `lead`, `manager`, `director`, `architect`, `III`, `IV`); JD regex for years (`0-2`, `0–5`, `up to 5 years`, etc.). |
| Experience-range extraction from JD | User requirement: dedicated `Experience` column showing the 0–5 spread. | M | Regex over JD: `(\d+)\s*[-–to]+\s*(\d+)\s*(?:\+\s*)?years?`, plus single-bound forms (`5+ years`, `at least 2 years`). Many postings omit a range — column must tolerate empty. |
| Posted-date extraction with fallback | User requirement: real date when source exposes it, else first-seen. | S | Greenhouse exposes `updated_at`; Lever exposes `createdAt`; Ashby exposes `publishedAt`; Workday exposes `postedOn`; Apple exposes `postingDate`. For others (Playwright path), fall back to scanner's first-observed date. |
| Age computation for the table | `Age` column should be human-readable (`3h`, `2d`, `3w`) computed from posted-or-first-seen. | S | Pure formatting on top of the date extraction feature. |
| Persistent `seen.json` state file | User requirement: keep stale postings forever; dedup across runs; record first-seen for Age fallback. | S | Schema per key: `{first_seen, last_seen, posted_date, company, title, location, salary, experience, url}`. Committed to repo on every change. |
| Per-source error isolation | User constraint: one company failing must not kill the run. | S | Try/except wrapping each source; collect errors; log to a file (`scan.log`) committed alongside the table. |
| Idempotent Markdown table render | The README table must regenerate deterministically from `seen.json` — same input → same output → empty git diff. | S | Sort by a stable key (posted_date desc, then company asc, then title asc). Avoid embedding "generated at" timestamps inside the table body. |
| GitHub Actions hourly workflow | Product requirement: `0 * * * *` cron, runs end-to-end, commits and pushes on change. | S-M | GitHub free public-repo Actions are unlimited; cron may run late (5–15 min drift is normal). |
| Commit + push on change only | Avoids noisy git history when nothing new. | S | Compare working tree to HEAD; commit only if dirty. |
| Salary extraction (when present) | The `Salary` column is in the user's required schema. Many US postings expose it (CA, CO, NY, WA pay-transparency laws). | M | ATS adapters: Greenhouse/Lever expose structured pay sometimes; for most, parse JD for `$XXX,XXX` ranges. Tolerate empty (column shows `—`). |
| Location extraction + multi-location handling | Postings often list multiple locations or "Remote — US". `Location` column must be readable and not 200 chars long. | S-M | Take first 1–2 locations; collapse `Remote (USA)`, `Remote — United States` to a canonical `Remote (US)`. |
| Company-name normalization | Same company should always render the same way (`Apple`, not `Apple Inc.` on one row and `apple` on another). | S | Derive canonical name from `companies.txt` entry (or a `companies.yaml` with `{url, display_name}`); never trust the scraped value blindly. |

---

## Differentiators

Features that compound value without violating the product's "discovery-only" scope. None are required to ship a v1.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Posting-language filter (English-only) | Big employers have postings in many languages; filtering to English keeps the table actionable for a US-based user. | S | `langdetect` on title; fast and good enough. |
| US-only / region filter | User is US-based; postings in Tel Aviv/Bangalore/Berlin are noise. Configurable via `companies.txt` or a `config.yaml`. | S | Filter on normalized location. |
| Sponsorship / visa flag | Many postings say "no sponsorship" or "must be authorized to work in the US." A column / icon surfaces this. | M | JD regex (`will not sponsor`, `not provide sponsorship`, `must be authorized`). High false-positive risk; mark as best-effort. |
| Citizenship/security-clearance flag | Defense/aerospace postings often require US citizenship or clearance. Surfacing this saves clicks. | S-M | JD regex (`US citizen`, `Secret clearance`, `TS/SCI`). |
| Posting-removed marker | User keeps stale postings in the table forever. A subtle marker (e.g., struck-through link, or a "Status" column with `Open`/`Closed`) tells the user the link likely 404s. | S | Compare each run's seen set to previous; when a key disappears from source, flip status. Does NOT remove the row. |
| Per-company section / pivot table | Beyond one master table, group postings by company for quick scanning. | S | Generated from same `seen.json`; either inline in README or in a `BY_COMPANY.md`. |
| First-seen sort vs posted-date sort | Two reading modes: "what's newly discovered" (first_seen desc) vs "what employers just posted" (posted_date desc). | S | Configurable order. |
| Diff comment in commit message | Commit message summarizing what changed: `+3 new (Apple, Stripe), 2 closed (Anthropic)`. Lets the user skim git history. | S | Generated during table render step. |
| `companies.txt` validation on add | When user runs Claude CLI to add a URL, validate it matches a known ATS pattern OR test a Playwright fetch returns >0 postings. Prevents bad entries entering rotation. | S | Optional, but cheap value. |
| Per-source rate limiting / politeness | Some sites block hostile scraping. Per-host sleep, configurable UA, retries with backoff. | S-M | Keeps the tool from becoming a public-shame liability on a public repo. |
| Caching / conditional GET for ATS APIs | Greenhouse/Lever expose ETags or `Last-Modified`. Conditional GETs cut bandwidth and reduce block risk. | M | Marginal at one user's scale; nice hygiene. |
| Posting-content hash for soft-dedup | A second-level dedup: same title+company+location at two URLs (e.g., Workday + Greenhouse mirrors) collapses to one row. | M | Risk: false-positive merges. Only enable after evidence the issue exists. |
| Title normalization | Map `SWE I`, `Software Engineer 1`, `Software Engineer, Early Career` to a canonical bucket. Helps the eye; helps later filtering. | M | Don't over-normalize — losing employer-specific wording costs trust. |
| Salary normalization (currency + period) | `$120k`, `$120,000`, `$60/hr`, `€100,000` → consistent column format. | M | Many extractions; tolerable to show `$120k–$150k` and leave others raw. |
| Posting-age decay highlight | Bold rows posted in the last 24h; dim rows older than 30 days. Pure Markdown emphasis, no JS. | S | Aids the user's eye on a 100-row table. |
| README badge: last-run + posting count | Top of README: `Last scan: 2026-06-07 14:00 UTC · 87 open postings · 14 companies` — single status line, no separate UI. | S | Pure render. |
| Per-source health table | A small "scraper health" table or section showing each company's last successful scan + last error. Lets user notice "Nvidia hasn't worked in a week." | S-M | Visible in README; respects "no notifications" by being passive. |
| Optional structured archive (`postings/<key>.json`) | Per-posting JSON files in a `postings/` dir. Enables grep, jq, and external tools without parsing Markdown. | S | Increases repo size; only valuable if user later wants to re-aggregate. |
| GitHub Actions failure visibility (passive) | Workflow status badge in README. If a run fails entirely (vs per-source), the badge turns red — passive signal, no notification. | S | Built into GitHub. |
| Job-role tagging (SWE / DS / PM / HW / Design) | Optional column or section grouping by inferred role family. Helps a user who only cares about SWE. | M | Title-keyword classification; coarse but useful. |

---

## Anti-Features

Features that look helpful but are explicitly out of scope for this product. Do not build these — they violate user intent and inflate complexity for no win.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Email / Slack / SMS / push notifications | User explicitly excluded. Notifications are the #1 feature creep in job-tracker tools — and once added, force account/contact management. | The repo is the inbox. User checks it. |
| Web UI / dashboard / static site | User said "the README IS the UI." Adding a Next.js or Astro site doubles maintenance, adds hosting, and adds CI. | Lean on GitHub's Markdown renderer. |
| Auto-apply / form autofill / resume submission | Explicitly excluded. Also a TOS risk on most career portals. | Posting URL → user clicks → user applies. |
| Resume tailoring, cover-letter generation, GPT-suggest-skills | Explicitly excluded. Not the product's job. | Out of scope, end of story. |
| Application-tracking columns (`Applied?`, `Stage`, `Notes`) | Explicitly excluded. Turns the repo into a CRM and requires user to edit it, breaking "zero-touch." | Out of scope. If user later wants this, fork the repo or use a separate tool. |
| Auto-removal of closed postings | User explicitly preferred history over freshness. | Mark as closed (differentiator) but never delete. |
| Senior / staff / principal / manager roles | User explicitly excluded via 0–5 yrs filter. | Title denylist + JD years filter. |
| Multi-user support / accounts / login | User explicitly said single-user. | All config lives in the repo. |
| LinkedIn / Indeed / Glassdoor scraping | User's product is "scan companies the user listed." LinkedIn aggressively blocks scrapers; Indeed has TOS issues; Glassdoor too. Scope creep with legal/blocking risk. | Stay on company career pages and ATS endpoints. |
| GPT/LLM-based JD parsing for everything | Tempting but slow, costs money, and overkill for regex-tractable fields (years, salary, posted date). Adds an API key + rate-limit failure mode. | Regex first. Only reach for LLMs if a field is consistently unparseable by rules. |
| Database (Postgres, SQLite-in-cloud, Supabase, etc.) | User constraint: $0 infra, repo-as-database. | `seen.json` in the repo. |
| Web crawlers that follow internal links | Career pages link to many pages (about, benefits, locations). General-purpose crawling is overkill when ATS endpoints exist. | Adapter-per-source. |
| Discord / Telegram bot relay | Notification in disguise. Excluded. | — |
| Salary prediction / market-rate enrichment (Levels.fyi, Glassdoor scrape) | Cool, but scope creep and TOS-risky. | Show the salary the posting exposes, or `—`. |
| Auto-translation of non-English postings | Scope creep. Most relevant US new-grad postings are English. | Filter to English instead. |
| Per-posting screenshot archive | Cool, expensive, balloons repo size. | The posted URL is the archive. |
| `companies.txt` auto-discovery (crawl Fortune 500) | Scope creep; users curate their own list. | User adds URLs explicitly via Claude CLI. |

---

## Feature Dependencies

```
ATS adapters ─────────┐
                      ├──> Per-source fetcher ──> URL canonicalization ──> Dedup ──> seen.json ──> Render table ──> Commit
Playwright fallback ──┘                                                         │
                                                                                ├──> Age computation
URL-based source detect ──> Per-source fetcher                                  │
                                                                                ├──> Diff commit message (differentiator)
Posted-date extraction ──> Age computation                                      │
                                                                                └──> Per-source health table (differentiator)
Salary / Location / Experience extraction ──> Table row formatting

Early-career filter (title + JD) ──> seen.json write (gate: only matching rows persisted)

Per-source error isolation wraps every adapter call.

Company-name normalization is sourced from companies.txt and feeds every row.
```

**Critical-path features (must work for v1 to ship a useful README):**

1. Per-source fetcher abstraction
2. At least 2 ATS adapters (Greenhouse + Lever — they cover the largest share of medium-size tech employers)
3. Playwright fallback (even if used by only one company at launch — proves the model)
4. URL canonicalization + dedup
5. Early-career filter (title + JD)
6. `seen.json` read/write
7. Markdown table render (idempotent)
8. GitHub Actions hourly workflow + commit-on-change
9. Per-source error isolation

Everything else can be deferred without breaking the product's core promise.

---

## MVP Recommendation

**Ship v1 with this minimal set, in order:**

1. Greenhouse adapter (smallest, well-documented JSON; many companies use it; perfect first end-to-end vertical slice).
2. URL canonicalization + dedup + `seen.json` schema (locks in the data model before adding more sources).
3. Early-career title-keyword filter (JD-scan filter can land in v1.1).
4. Markdown table render + idempotent sort.
5. GitHub Actions workflow + commit-on-change.
6. Lever adapter (validates that adapter abstraction holds across two sources).
7. Per-source error isolation (added once 2+ adapters exist, since with one source there's nothing to isolate).
8. Playwright fallback (proves coverage for non-ATS sites; ship with one target like Nvidia or Apple).
9. Posted-date extraction per adapter + Age column.
10. Salary + Experience-range extraction (JD regex).

**Defer to v1.1+:**

- Workday adapter (most complex; per-tenant POST body, facet handling — worth doing properly, not under v1 pressure).
- Ashby + SmartRecruiters + Apple Jobs adapters (incremental, low-risk additions once the adapter contract is stable).
- JD-based experience filter (catches roles that pass title filter but are actually senior).
- Posting-closed marker.
- Per-source health table.
- Visa / clearance flag.
- Diff commit messages.

**Defer indefinitely (low ROI for this user):**

- Title / salary normalization beyond trivial cases.
- Per-posting JSON archive.
- Conditional GET / caching.

---

## Notes on contested or uncertain features

- **JD-based experience filter:** MEDIUM confidence that title-keyword filtering alone catches ~70–85% of new-grad-eligible roles correctly; JD scan is needed to catch the rest and to reject senior roles mistitled "Software Engineer." Worth the M-complexity investment.
- **Salary extraction:** MEDIUM confidence. CA/CO/NY/WA pay-transparency laws have pushed structured salary fields into many ATS responses, but exposure is inconsistent. Plan for `—` to be common. Do not block v1 on this.
- **Workday adapter:** MEDIUM-HIGH confidence the documented `/wday/cxs/<tenant>/<site>/jobs` POST endpoint works for most Workday tenants, but per-tenant configuration (facets, paging tokens) means 10–20% of Workday tenants need adapter tweaks. Plan for "Workday adapter v0 covers 80%; the rest fall through to Playwright."
- **Posted-date trustworthiness:** HIGH confidence on Greenhouse/Lever/Ashby (clear `updated_at`/`createdAt`/`publishedAt` fields). MEDIUM on Workday (`postedOn` exists but is sometimes the "refresh" date, not original). LOW on Playwright-scraped sites; fall back to first-seen.
- **URL canonicalization:** HIGH confidence the user will hit dedup bugs without it (UTM params and ATS source tags are extremely common). It's not optional.

---

## Sources

Web verification was unavailable during this research (WebSearch / WebFetch were blocked in-session). All findings are anchored to:

- Prior knowledge of public new-grad-tracker repos: `SimplifyJobs/New-Grad-Positions`, `SimplifyJobs/Summer2025-Internships`, `Pitt-CSC/Summer-Internships`, `ouckah/Summer2024-Internships`, `vanshb03/Summer2025-Internships`. These define the de facto Markdown-table format (Company | Role | Location | Application/Link | Age) and the community norm of "history kept, age shown."
- Prior knowledge of public ATS endpoints:
  - Greenhouse: `https://boards-api.greenhouse.io/v1/boards/<board>/jobs?content=true`
  - Lever: `https://api.lever.co/v0/postings/<company>?mode=json`
  - Ashby: `https://api.ashbyhq.com/posting-api/job-board/<org>`
  - SmartRecruiters: `https://api.smartrecruiters.com/v1/companies/<company>/postings`
  - Workday: POST `https://<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs`
  - Apple: `https://jobs.apple.com/api/role/search`
- Prior knowledge of Playwright's behavior in GitHub Actions runners (supported, with `playwright install chromium` step; cold start ~5–15 s).
- The user's `PROJECT.md` for scope boundaries and explicit Out of Scope list.

**Confidence per category:**

| Category | Confidence | Reason |
|----------|------------|--------|
| Table-stakes feature list | HIGH | Derived from the user's own requirements doc + well-established norms in the public new-grad-tracker space. |
| Differentiators | MEDIUM-HIGH | Each item is implementable with known patterns, but value is judgment. |
| Anti-features | HIGH | Directly tied to the user's stated Out of Scope. |
| ATS endpoint specifics | MEDIUM-HIGH | Endpoints are stable but versions/paths drift; verify before implementing each adapter. |
| Filter precision claims (e.g., "70–85% caught by titles") | LOW-MEDIUM | Order-of-magnitude estimate from domain familiarity, not measured. Should be re-evaluated after the first week of real data. |

Recommend a quick verification pass (Context7 or live docs) on each ATS endpoint at the moment that adapter is implemented, since URL shapes do shift over time.
