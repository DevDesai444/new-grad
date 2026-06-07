# Domain Pitfalls

**Domain:** Unattended career-page scraper (Python + Playwright on GitHub Actions, hourly cron, public repo, state committed back)
**Researched:** 2026-06-07
**Confidence note:** WebSearch and Context7 were unavailable in this session. Findings rely on established knowledge of the scraping/Actions/ATS ecosystem and the project's own requirements. Confidence levels are flagged per item. Items marked LOW confidence should be validated in the phase that touches them.

---

## Why This Pitfalls Doc Matters

The system must run **unattended for months** with **no alerts** and a **public repo** as both the UI and the database. This combination creates a particular failure mode:

> A silent corruption of `seen.json` or `README.md` is worse than a loud crash — because a crash on an hourly cron is automatically retried 60 minutes later, but a corruption gets *committed* and propagates forward.

Every pitfall below is evaluated against that lens: **"Does this fail loud (good), fail isolated (good), or fail silent-and-committed (catastrophic)?"** The Prevention strategies are biased toward making everything fail loud-and-isolated.

---

## Critical Pitfalls

These cause data loss, state corruption, security incidents, or permanent breakage. The roadmap MUST address these in the foundational phases.

### Pitfall 1: `seen.json` half-written, bricking every future run
**Confidence:** HIGH
**What goes wrong:** The scraper writes `seen.json` with `open(path, "w")` then `json.dump(...)`. The Actions runner is killed mid-write (timeout, OOM, cancelled by a newer queued run). The file is now truncated/invalid JSON. The next hourly run calls `json.load()`, raises `JSONDecodeError`, and the entire scan dies before producing anything. Every subsequent hour fails the same way. The user doesn't notice for weeks because there are no alerts.
**Why it happens:** Non-atomic writes are the default in Python. `open("w")` truncates before writing.
**Consequences:** System dies permanently until manual intervention. Worst possible failure mode for an unattended system.
**Prevention:**
- Atomic write pattern: write to `seen.json.tmp` in the same directory, `os.fsync()`, then `os.replace("seen.json.tmp", "seen.json")`. `os.replace` is atomic on POSIX.
- On read, wrap `json.load` in try/except. On `JSONDecodeError`, fall back to the previous good copy (see Pitfall 2) and continue the run rather than crashing.
- Validate the parsed object's shape (top-level dict, required keys exist) before trusting it.
**Detection:**
- Add a lightweight `--validate` mode the workflow runs as the first step. If invalid, abort the run before any destructive write.
- Commit a `seen.json.size` counter to the README footer so growth/shrinkage is visible at a glance during manual checks.
**Phase mapping:** **Foundational phase (Phase 1 / state layer).** This must be designed before any scraping code is written.

---

### Pitfall 2: A single bad run wipes the entire `seen.json` table
**Confidence:** HIGH
**What goes wrong:** All adapters return zero results (network outage, mass ATS endpoint change, GitHub Actions region issue). The merge logic treats "scraped set" as the new truth and replaces `seen.json` with `{}`. The "keep stale postings forever" requirement is now destroyed — every historical posting is gone. The diff in the commit shows a huge deletion, but no one is watching.
**Why it happens:** Sloppy merge logic: `seen = scraped_now` instead of `seen.update(scraped_now)`. Or filter logic that treats "not in current scrape" as "remove from seen."
**Consequences:** Permanent loss of history. Violates an explicit project requirement.
**Prevention:**
- Merge logic is **add-only** for keys. `seen[key] = {...}` never `seen = {...}`. `last_seen` updates in place; nothing is ever popped.
- **Sanity gate before commit:** if `len(new_seen) < len(old_seen) * 0.9`, abort the commit and exit non-zero. The hourly cron will retry next hour with un-corrupted state.
- Keep a `seen.json.bak` (previous run's version) committed alongside `seen.json`. On startup, if main file fails the sanity gate or parse, recover from `.bak`.
- Git history is itself a backup; document the recovery command (`git checkout HEAD~1 -- seen.json`) in the repo README's "ops" section.
**Detection:** Watch for commit messages showing large negative diffs. Sanity gate produces a loud failure in the Actions log.
**Phase mapping:** **Foundational phase (Phase 1).** Bake into the very first merge implementation.

---

### Pitfall 3: Concurrent Actions runs race on the commit; second push rejected
**Confidence:** HIGH
**What goes wrong:** Hourly cron fires at `:00`. A long Playwright run (5–10 min on Apple/Workday) is still going when manual `workflow_dispatch` or a `companies.txt` edit triggers a second run. Both finish, both try `git push`, second fails with non-fast-forward. Worse: both succeed via `--force`, and one set of changes is silently overwritten. Even worse: both commit conflicting `seen.json` versions and the merge clobbers the longer one.
**Why it happens:** GitHub Actions does not serialize workflow runs by default. `git push` from a workflow that started before the latest `main` HEAD will be rejected. `--force` "fixes" the symptom by destroying data.
**Consequences:** Lost postings, lost dedup state, or stuck workflow.
**Prevention:**
- **Use `concurrency:` group at the workflow level** with `cancel-in-progress: false`. This serializes runs, queueing any new trigger until the current one completes. (Setting `cancel-in-progress: true` is wrong here — cancelling the in-flight run can leave `seen.json.tmp` orphaned.)
- Before push: `git pull --rebase origin main` to handle any external commits (companies.txt edits, Claude CLI commits).
- Never `git push --force`. If push is rejected after a rebase attempt, exit non-zero and let next hour retry.
- On the README commit, use `git commit --allow-empty` only when needed; check `git status --porcelain` before committing to avoid empty commits flooding history.
**Detection:** Actions logs will show "rejected — non-fast-forward." Make this exit non-zero so the run is marked failed (visible in the repo's Actions tab even without alerts).
**Phase mapping:** **Foundational phase (Phase 1 / Actions workflow).** Set `concurrency:` from day one.

---

### Pitfall 4: Accidentally committing a secret to the public repo
**Confidence:** HIGH
**What goes wrong:** Developer iterating locally writes an auth header literal into an adapter, or pastes a token into `companies.txt` while debugging, or a Playwright trace file containing a cookie gets `git add .`'d. Public repo means it's immediately scraped by credential-harvesting bots. GitHub's push protection may catch obvious tokens but not custom ATS session cookies, Workday tenant IDs that some orgs treat as semi-secret, or personal access tokens with non-standard prefixes.
**Why it happens:** Defaults favor convenience. `git add .` is universal. Playwright HAR/trace files capture full request headers.
**Consequences:** Credential exposure, possible account suspension by the target site, possible reputational damage. In the worst case, a leaked GitHub PAT in `.env` could let an attacker push malicious changes back to the repo.
**Prevention:**
- Strict `.gitignore` from day one: `*.env`, `*.har`, `trace.zip`, `playwright-report/`, `__pycache__/`, `.venv/`, `*.log`, `cookies.json`, `auth_state.json`.
- Pre-commit hook (`pre-commit` framework) running `gitleaks` or `detect-secrets`. Fast, free, no infra.
- Enable GitHub's **Push Protection** (Settings → Code security → Secret scanning) — it blocks pushes containing known token patterns.
- All credentials accessed only via `os.environ[...]` which is populated from `secrets.*` in the workflow file. Workflow uses `env:` block scoped to the step, not globally.
- In Playwright, disable trace recording in production runs (`trace="off"`); only enable on local debugging.
- Never log request headers or response bodies. Add a `redact()` helper that strips known secret-shaped strings from log output.
**Detection:**
- `gitleaks detect` runs in the workflow as a job step before any other work.
- Schedule a weekly job that runs `gitleaks detect --log-opts="--all"` on full history.
**Phase mapping:** **Phase 1 (foundational).** Push Protection and `.gitignore` must exist before first commit. Pre-commit hooks before second commit.

---

### Pitfall 5: Anti-bot blocks GitHub Actions IPs, scraper silently returns zero
**Confidence:** HIGH (general), MEDIUM (specifics per site)
**What goes wrong:** GitHub Actions runners use a well-known, published, and finite range of Azure IPs. Cloudflare, Akamai, DataDome, and PerimeterX all maintain blocklists or aggressive challenge rules for these ranges. The scraper hits a Workday or Greenhouse endpoint and gets a 403, a CAPTCHA HTML page, or an empty 200 response. The parser sees "no postings" and the merge logic (if Pitfall 2 isn't fixed) wipes the table. Even if not wiped, the user sees "Apple has zero open roles" and assumes it's accurate.
**Why it happens:** GitHub publishes Actions IP ranges as a public list (`api.github.com/meta`). Bot-management vendors ingest it. They cannot tell your hourly scrape from credential stuffing.
**Consequences:** Per-site silent zeros that look like normal "no new postings." Trust in the table erodes.
**Prevention:**
- **Distinguish "site blocked us" from "site has zero matching roles":** an adapter returns an explicit `SiteBlocked` outcome (HTTP 403, CAPTCHA HTML signature detected, response shorter than 200 bytes when JSON expected, rate-limit headers present). The merge logic treats `SiteBlocked` as "no update" — don't touch existing postings for this company, don't claim zero.
- Surface per-site status in the README footer: `Last successful scan per company: Apple 2h ago, Nvidia 5d ago (BLOCKED)`. The user notices via manual inspection.
- Prefer documented JSON ATS endpoints (Greenhouse `boards-api.greenhouse.io`, Lever `api.lever.co`, Ashby `jobs.ashbyhq.com/api`, SmartRecruiters `api.smartrecruiters.com`) — these are designed for public consumption and rarely block by IP.
- Realistic User-Agent and headers (`Accept`, `Accept-Language`, `Sec-Fetch-*`). Don't ship Playwright's default UA in production.
- Add `time.sleep(random.uniform(1, 3))` between requests; respect any `Retry-After` header.
- **Have a documented escape hatch** for the future: a workflow variable `USE_PROXY=1` that routes through a small residential proxy (e.g., Bright Data, or a self-hosted Tailscale exit node on a home machine) for specific companies. Don't build this on day one — design for it.
- Avoid hammering: if a company's adapter has succeeded in the last hour and returned content, you could skip it (caching), but this complicates dedup. Simpler: respect 429s with exponential backoff.
**Detection:**
- Per-adapter health metric: success/blocked/error counts in `seen.json` metadata or a separate `health.json`. Render the last-N-hour summary in README footer.
- If an adapter has been `blocked` for >24h, that's a signal to investigate.
**Phase mapping:** **Phase 2 (scraping core)** for distinguishing blocked-vs-empty. **Phase 4 (resilience polish)** for proxy escape hatch.

---

### Pitfall 6: ATS endpoint changes shape and adapter silently produces garbage
**Confidence:** HIGH
**What goes wrong:** Workday's `/wday/cxs/...` response is undocumented. They could rename `jobPostings` to `postings`, change `externalPath` to `jobUrl`, or move location data. Greenhouse occasionally adds optional fields. Adapter code does `data["jobPostings"]` → `KeyError`, which (if caught broadly) results in zero postings for that company. Or worse: `data.get("jobPostings", [])` returns `[]` silently and the company looks dead.
**Why it happens:** ATS vendors' public-facing JSON shapes are not contractual APIs. Workday in particular is notorious for tenant-specific quirks; some tenants paginate differently.
**Consequences:** Silent under-reporting. User misses real openings.
**Prevention:**
- **Schema assertions per adapter:** after fetching, assert that expected top-level keys exist. If not, raise a typed `SchemaDrift(company, missing_keys)` exception, classify as a per-adapter failure (not blocked, not empty — *broken*), and surface in the health footer.
- Snapshot the latest raw response per site (compressed, last 1 per company, in `.snapshots/`) — when a schema drifts, diffing this against the previous shape pinpoints the change. Keep snapshots small (truncate to first N postings) to avoid repo bloat.
- Unit tests with **recorded fixtures** for each adapter (commit a sample response JSON, test parser against it). Run on every PR.
- Versioned adapters: if Workday v2 emerges, keep both. The adapter selection knows which company uses which version.
- Don't pin Playwright/HTTPX/Pydantic versions too aggressively — but **do** pin them, and keep an eye on changelogs (dependabot weekly is fine).
**Detection:** Schema assertion failures show up as per-adapter errors in the health footer. Snapshot diffs in PRs.
**Phase mapping:** **Phase 2 (per-adapter implementation).** Schema assertions are part of "definition of done" for each adapter.

---

### Pitfall 7: `seen.json` grows unbounded; eventually breaks the repo
**Confidence:** MEDIUM
**What goes wrong:** Requirement says "keep stale postings forever." Over a year, 20 companies × ~100 postings/year × ~1KB/posting metadata = ~2MB. Manageable. But: if any company has a tenant where every page-refresh generates new posting IDs (some Workday tenants do this), or if dedup keys aren't stable (Pitfall 9), the file can balloon to 50MB+ within months. GitHub Actions clones the repo on every run — a 100MB `seen.json` adds minutes to every run and eventually triggers Git LFS warnings. Also, GitHub's web UI struggles to render diffs of large JSON files.
**Why it happens:** "Forever" was a product requirement, but the threat model didn't include adversarial growth from bad keys.
**Consequences:** Runs get slow, then time out, then the system effectively dies.
**Prevention:**
- **Bound the file with a soft cap:** if `len(seen) > 10_000`, move entries with `last_seen` older than 18 months to `seen.archive.jsonl` (line-delimited, append-only). They still exist (requirement honored), but the hot file stays small. Archive file isn't read at runtime.
- **Compress payload per entry:** only store fields that appear in the table + dedup key. Don't store the full job description — extract experience/salary at scrape time, store the extract, discard the raw.
- Stable dedup keys (Pitfall 9) are the real fix; bounding is the safety net.
- Monitor file size: commit a `seen.json.size_bytes` value to README footer. If it crosses 5MB, alarms (well, manual-inspection-alarms) should ring.
**Detection:** Size in README footer is the dashboard.
**Phase mapping:** **Phase 3 (polish / sustainability).** Not urgent at MVP, but the archive design needs to exist before the file hits 5MB.

---

## Moderate Pitfalls

These degrade quality silently or cause occasional incorrect output. Address in middle phases.

### Pitfall 8: JavaScript-rendered content read before the SPA hydrates
**Confidence:** HIGH
**What goes wrong:** Playwright loads `apple.com/jobs` or an Nvidia Workday page. The DOM is present but the React app hasn't fetched the postings yet. Scraper reads an empty list, treats as "no jobs."
**Why it happens:** `page.goto()` returns when the navigation is "load" — not when arbitrary client-side fetches complete. Even `wait_until="networkidle"` is unreliable on apps that poll.
**Prevention:**
- Wait for a specific selector that only exists after data loads: `page.wait_for_selector("[data-testid='job-card']", timeout=15000)`.
- Or wait for a specific network response: `with page.expect_response(lambda r: "/api/jobs" in r.url): page.goto(...)`. This is faster and more deterministic than polling the DOM.
- Always set a timeout and treat timeout as "site is slow / changed structure" — a typed error, not zero results.
- If the underlying network call is identifiable (it usually is — Apple's `/api/role/search`, Nvidia's `/wday/cxs/...`), **skip Playwright entirely and call the JSON API directly.** Faster, cheaper, more reliable. Reserve Playwright for sites with no other option.
**Phase mapping:** **Phase 2.** Establish the API-first/Playwright-fallback pattern early.

### Pitfall 9: Dedup keys break when posting URLs gain tracking params
**Confidence:** HIGH
**What goes wrong:** Dedup key is "company + URL." Workday URLs gain `?source=careersite_xyz` or session params between runs. Same posting now has two keys. Table shows duplicates. Or: the canonical URL changes from `/job/12345` to `/job/12345-software-engineer-new-grad` as the slug is added.
**Why it happens:** URLs aren't canonical. ATS systems inject session/tracking junk.
**Prevention:**
- **Canonicalize before keying:** strip query params, strip trailing slashes, lowercase host, drop fragment. For known ATS patterns, extract the stable ID:
  - Greenhouse: `boards.greenhouse.io/<company>/jobs/<ID>` → key = `gh:<company>:<ID>`
  - Lever: `jobs.lever.co/<company>/<UUID>` → key = `lever:<company>:<UUID>`
  - Workday: `/job/<location>/<title>_<ID>` → key = `wd:<tenant>:<ID>`
  - Ashby: `jobs.ashbyhq.com/<company>/<UUID>` → key = `ashby:<company>:<UUID>`
- For unknown sites: canonical URL only, document that dedup may be looser.
- Have a "merge duplicates" script for emergency cleanup; never auto-merge at runtime (risk of false positives merging two genuinely different roles).
**Phase mapping:** **Phase 2 (per-adapter).** Each adapter is responsible for emitting the canonical key.

### Pitfall 10: Date parsing across timezones and locales produces "negative age" or off-by-one
**Confidence:** HIGH
**What goes wrong:** ATS returns "Posted 2 days ago" or `2026-06-05T00:00:00` (no TZ) or `1717545600` (epoch). Scraper interprets in runner's UTC. User in Eastern time sees "Posted in 4 hours" for a job that's already a day old, or Age=`-1d`.
**Why it happens:** Naive datetime arithmetic. Mixing aware and naive datetimes. Assuming epoch is seconds when it's milliseconds (Workday).
**Prevention:**
- All internal datetimes are `datetime.now(timezone.utc)`-style aware UTC. Never `datetime.now()`.
- Each adapter normalizes to UTC ISO 8601 with explicit `+00:00`. Document the source's TZ convention per adapter.
- Workday epochs are milliseconds — divide by 1000. Have a parser test for this.
- "Days ago" relative strings: parse against the run's UTC clock, document the assumption.
- The README's "Age" column computes from `first_seen` (always set by us, always UTC) when source's posted-date is missing. Never let Age be negative — clamp to 0 or "today."
**Phase mapping:** **Phase 2.** Add unit tests for date parsing per adapter.

### Pitfall 11: Salary regex misclassifies "Up to $X" and "$X – $Y" ranges
**Confidence:** HIGH
**What goes wrong:** Regex `\$(\d+[KkMm]?)\s*-\s*\$?(\d+[KkMm]?)` matches `$150K - $200K` but fails on:
- `$150,000 - $200,000` (commas)
- `Up to $200K` (no range, just ceiling)
- `$200K+` (no upper bound)
- `USD 150,000 - 200,000` (non-$ prefix)
- `£60,000 - £80,000` (UK roles, different currency)
- `Compensation: 150-200K USD` (no $ at all)
- Equity grants treated as cash: `$0 base + $200K equity`
- Hourly vs annual: `$50/hr` vs `$50K/yr`
**Why it happens:** Salary text is free-form marketing copy, not structured.
**Prevention:**
- Don't roll one big regex. Use a small library of patterns, each emitting `(min, max, currency, period)` or `None`. Try in priority order.
- If multiple patterns match, prefer the most specific (range > single > ceiling).
- Always emit currency and period. If hourly, multiply by 2080 only with a flag (`~$104K/yr est.`).
- If extraction is ambiguous or low-confidence, store the raw string and display it as-is. Don't fabricate a range.
- For unknown formats, leave column blank — don't show `$0 - $0` or `null - null`.
- Pin a test corpus of 30+ real salary strings from your actual companies; regression test on every change.
**Phase mapping:** **Phase 3 (extraction polish).** MVP can leave Salary blank; add incrementally.

### Pitfall 12: Experience extraction from free-form descriptions is a quagmire
**Confidence:** HIGH
**What goes wrong:** The job description says "5+ years preferred, but new grads welcome." Filter logic sees "5+" and excludes. Or: "experience equivalent to 3 years" passes but is actually senior. Or: title says "Software Engineer II" — no number, but II implies mid-level.
**Why it happens:** Natural language is hostile. Title and description often disagree. Recruiters write aspirationally.
**Prevention:**
- **Two-layer filter:** title-based (hard rules: include "new grad", "early career", "associate", "I" — exclude "senior", "staff", "principal", "lead", "manager", "II", "III", "IV") + description-based (years extraction).
- For years, look for patterns: `(\d+)\+?\s*(?:to|-|–)?\s*(\d+)?\s*years?`, also `entry-level`, `recent graduate`, `no experience required`.
- If title is ambiguous and description says "5+ years," exclude. Bias toward exclusion to avoid false positives clogging the table.
- Surface the extracted range in the Experience column so the user can see when extraction is suspicious (e.g., "5-10 yrs" appearing means filter is too loose).
- Maintain a manual override list: `excluded_keywords.txt` (and `included_keywords.txt`) the user can tune over time.
- Don't try LLM-based filtering at MVP — expensive, slow, non-deterministic, and the user is the LLM (Claude CLI can refine the list).
**Phase mapping:** **Phase 2 (filter logic)** for title rules. **Phase 3** for description scanning.

### Pitfall 13: Markdown table breaks on pipes, emoji, newlines in fields
**Confidence:** HIGH
**What goes wrong:** Job title is `Software Engineer | New Grad | Bay Area`. Naive `f"| {title} |"` produces a row with 5 cells instead of 3, breaking the table render. Or location contains a newline. Or salary has `<` / `>` that GitHub interprets as HTML.
**Why it happens:** Markdown's pipe-delimited tables have no escape syntax in the spec, though GitHub-flavored Markdown supports `\|`.
**Prevention:**
- Escape function for every cell: `cell.replace("|", "\\|").replace("\n", " ").replace("\r", " ").strip()`.
- Truncate excessively long cells (>80 chars) with an ellipsis — they break GitHub's table rendering on mobile anyway.
- Strip invisible Unicode that won't render but will break alignment / diffing / dedup: U+200B (zero-width space), U+200C (ZWNJ), U+200D (ZWJ), U+FEFF (BOM), U+00A0 (non-breaking space → convert to regular space), U+2060 (word joiner). A single `unicodedata.category(ch).startswith("C")` filter catches most control chars; whitelist visible categories instead.
- Emoji are generally fine in GH markdown, but test with the actual rendered output (companies love putting rocket emoji in titles).
- Wrap the table generation in a unit test that asserts the row count matches the row count of the source list.
- For URLs in cells: use the `[Apply](url)` form, never bare URLs (bare URLs with `?` can confuse some renderers).
**Phase mapping:** **Phase 2 (table rendering).** Trivial to fix, painful to skip.

### Pitfall 14: Playwright install time dominates the run
**Confidence:** HIGH
**What goes wrong:** Every hour, the runner does `pip install playwright && playwright install chromium`. The browser download is ~150MB. Cold runs take 90+ seconds before any scraping starts. Adds up: 24 hours × 90s = 36 minutes/day of pure overhead. With the 2,000-minute private cap you'd already be at 30% just from this (public repo dodges this, but still wasteful).
**Why it happens:** Default workflow patterns rebuild from scratch.
**Prevention:**
- **Cache the Playwright browsers** via `actions/cache@v4`:
  ```yaml
  - uses: actions/cache@v4
    with:
      path: ~/.cache/ms-playwright
      key: playwright-${{ runner.os }}-${{ hashFiles('requirements.txt') }}
  ```
- Cache pip too: `actions/setup-python@v5` with `cache: 'pip'`.
- Use `playwright install --with-deps chromium` only on cache miss.
- Consider a custom Docker image with Playwright pre-baked and pushed to GHCR — only worth it if cache invalidation becomes a problem.
- Set per-page navigation timeouts (`page.set_default_navigation_timeout(20000)`) so a single slow site doesn't block the whole run.
- Set workflow-level `timeout-minutes: 30` so a hung run is killed before the next hour's cron fires.
**Phase mapping:** **Phase 1 (workflow setup).** Cache from day one.

### Pitfall 15: Headless detection bouncing Playwright
**Confidence:** MEDIUM
**What goes wrong:** Some sites (DataDome, PerimeterX, custom checks) detect headless Chrome via `navigator.webdriver`, missing plugins, missing `chrome` property, suspicious window dimensions, or absent `WebGL` vendor strings. Scraper gets a CAPTCHA page or a JS challenge it can't solve.
**Why it happens:** Anti-bot vendors actively fingerprint.
**Prevention:**
- Use Playwright's `chromium.launch(headless=True)` with realistic defaults; or `headless="new"` mode where supported.
- `playwright-stealth` (community package, MIT) applies common evasions. **LOW confidence on current effectiveness** — anti-bot vendors update. Validate per-site.
- Set viewport to a common desktop size (`1920x1080`).
- Don't disable images/fonts/CSS unless verified — many anti-bot checks expect them loaded.
- If a site is unscrapeable after reasonable effort, **document it as out-of-scope per company.** Better an empty cell than a phantom one.
- Last resort: use a self-hosted runner on a home machine for that one specific company. Adds infra; weigh against value.
**Phase mapping:** **Phase 2 / Phase 4.** Try plain Playwright first; add stealth only where needed.

### Pitfall 16: Workflow file permissions block git push
**Confidence:** HIGH
**What goes wrong:** Workflow uses `GITHUB_TOKEN` but doesn't grant `contents: write`. Push fails with `Permission denied`. Or the repo has branch protection on `main` requiring PRs, and the bot can't push directly.
**Why it happens:** GitHub tightened default `GITHUB_TOKEN` permissions in 2023. New workflows get read-only by default unless explicitly elevated.
**Prevention:**
- Workflow YAML includes:
  ```yaml
  permissions:
    contents: write
  ```
- Do NOT enable branch protection on `main` for this repo — it defeats the purpose. If branch protection is required (org policy), the bot needs a fine-grained PAT instead of `GITHUB_TOKEN`.
- Use `actions/checkout@v4` with `persist-credentials: true` (default) so subsequent `git push` works.
- Set git identity in the workflow: `git config user.name "github-actions[bot]"` / `user.email "41898282+github-actions[bot]@users.noreply.github.com"`.
**Phase mapping:** **Phase 1.** First failed run will surface this; fix immediately.

### Pitfall 17: Secrets leaked in logs via debug output or stack traces
**Confidence:** HIGH
**What goes wrong:** An exception logs the full request including `Authorization: Bearer ...`. GitHub Actions logs are public on public repos. Token is now world-readable.
**Why it happens:** Default logging captures everything. Many HTTP libraries print headers on error.
**Prevention:**
- GitHub auto-masks values registered as secrets (`::add-mask::` is implicit for `${{ secrets.* }}`). **Verify per-secret** — masking only matches exact string occurrence. Tokens that appear base64-decoded, URL-encoded, or in a different case will not be masked.
- Wrap every HTTP call's exception handler to log only status code, URL (with secrets stripped from query), and exception type. Never `traceback.format_exc()` containing headers.
- Don't enable Playwright's `DEBUG=pw:api` in production.
- Audit: search recent Actions logs for substrings of known secrets before going public-public (i.e., before publicizing the repo).
**Phase mapping:** **Phase 1.** Set up logging discipline early.

---

## Minor Pitfalls

Edge cases, polish, or known-livable issues.

### Pitfall 18: Empty commits on quiet hours flood git history
**What goes wrong:** Hours pass with no new postings. Workflow commits "Update postings" 24 times with no actual diff. History becomes useless for diagnostics.
**Prevention:** Check `git status --porcelain`. If empty, exit before committing. Optionally still commit a heartbeat to a `last_run.txt` file once a day so the user knows the cron is alive — but not every hour.

### Pitfall 19: Time zones in cron — "every hour" isn't quite
**What goes wrong:** GitHub Actions cron runs on UTC. `0 * * * *` fires at top of UTC hour. Also, scheduled workflows have observed delays of up to 10+ minutes during peak Actions load. "Hourly" is best-effort.
**Prevention:** Don't promise sub-hourly precision. Document in README that runs are "approximately hourly." Add a `last_successful_run` timestamp to the README footer.

### Pitfall 20: Companies disabling JS-rendered pages mid-flight (A/B tests)
**What goes wrong:** Site is fine for 5 runs, then a vendor A/B test changes selectors for 30 minutes, then reverts. Adapter health flickers.
**Prevention:** Don't react to single-run failures. Only mark an adapter "broken" after N consecutive failures (e.g., 3). Health footer can show transient yellow vs persistent red.

### Pitfall 21: `companies.txt` parsed too strictly — one bad line kills the whole run
**What goes wrong:** Trailing whitespace, BOM, comment line, blank line breaks parsing.
**Prevention:** Strip per-line, skip empty, support `#` comments. Validate URL format per line; log and skip bad ones.

### Pitfall 22: Legal / ToS exposure
**Confidence:** LOW-MEDIUM (jurisdiction-dependent, not legal advice)
**What goes wrong:** Scraping ToS-violating content. While public job postings are generally low-risk (Van Buren v. US, hiQ v. LinkedIn precedents lean favorably for scraping public data), the public repo amplifies visibility. A large company's legal team could send a takedown.
**Prevention:**
- Stick to publicly accessible URLs only — no authentication required to view.
- Respect `robots.txt` where it explicitly disallows the scraped paths (parse `robots.txt` per company; skip disallowed). Reality: most ATS APIs and career pages don't disallow scraping.
- Hourly is conservative. Not aggressive.
- The README should not mirror posting *descriptions* (which are copyrightable). Just title + link is fair use territory.
- If a company sends a takedown or polite ask, remove that company from `companies.txt`. Document the policy in the repo's README.
- Don't redistribute raw company data beyond the table; don't build a public API on top.
**Phase mapping:** Awareness-level. No code change required at MVP. Document in repo README.

### Pitfall 23: GitHub Actions schedule disabled after 60 days of repo inactivity
**Confidence:** HIGH
**What goes wrong:** GitHub disables scheduled workflows on repos with no commits for 60 days. Since this repo commits on every run, that shouldn't happen — but if all runs fail for 60 days (e.g., Playwright broken upstream), the cron stops entirely and the user assumes "no new jobs" when really the system is dead.
**Prevention:**
- Workflow already commits on most runs (when there's a diff). The empty-commit policy (Pitfall 18) should still produce *some* commit at least weekly to keep the schedule alive.
- Add a `health.json` updated every run with `{last_run: ISO, status: ok|degraded}` so even failed runs produce a commit to keep the schedule active.
- Monitor the Actions tab during manual repo visits.

### Pitfall 24: Rate limit on GitHub API for `git push` from too many runs
**What goes wrong:** Not really a risk at 1 push/hour, but worth knowing: GitHub limits authenticated API calls to 1000/hour for `GITHUB_TOKEN`.
**Prevention:** Single push per run; don't make extra API calls. N/A at this scale.

### Pitfall 25: Encoding bugs in foreign-language postings
**What goes wrong:** Job title in Japanese, French, or with accented characters. Default file encoding on some runners isn't UTF-8.
**Prevention:** Explicit `encoding="utf-8"` on every `open()`. Set `PYTHONIOENCODING=utf-8` in workflow env. Test with at least one non-ASCII fixture.

### Pitfall 26: Cache key invalidation surprises (Playwright version bumps)
**What goes wrong:** Playwright auto-updates its bundled Chromium when the pip version changes. Cache key based only on `requirements.txt` becomes stale. Browser launch fails with "Executable doesn't exist."
**Prevention:** Include the Playwright pip version (or the resolved Chromium version) in the cache key. Or pin `playwright==X.Y.Z` strictly and refresh quarterly.

### Pitfall 27: `seen.json` git diffs are huge and slow to render in PRs
**What goes wrong:** A 2MB JSON file with `last_seen` updated on every entry produces a 2MB diff every hour. GitHub's PR view becomes useless.
**Prevention:**
- Sort keys consistently (`json.dump(..., sort_keys=True, indent=2)`) so diffs are minimal.
- Only update `last_seen` when the entry was actually seen this run; don't bump every entry.
- Add `seen.json -diff` in `.gitattributes` to suppress diff rendering.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|---|---|---|
| **Phase 1: Foundation (workflow, state, commit loop)** | Pitfalls 1, 2, 3, 4, 14, 16, 17, 23 | Atomic writes, sanity gates, concurrency group, Push Protection, .gitignore, cache, permissions, weekly health commit |
| **Phase 2: ATS Adapters & API-first scraping** | Pitfalls 5, 6, 8, 9, 10, 13, 21 | Schema assertions, canonical keys, UTC dates, table escaping, robust companies.txt parser, blocked-vs-empty distinction |
| **Phase 3: Filter logic & extraction** | Pitfalls 11, 12 | Salary pattern library w/ tests, two-layer experience filter, exclusion bias |
| **Phase 4: Playwright fallback & resilience polish** | Pitfalls 15, 20, 25, 26 | Stealth where needed, N-failure threshold, UTF-8 everywhere, cache key includes Playwright version |
| **Phase 5: Sustainability (size, history, ops)** | Pitfalls 7, 18, 22, 27 | Archive rollover, no empty commits, ToS hygiene, sorted JSON + .gitattributes |

---

## "What Could Silently Kill This System For Months?" — Top 5 Watchlist

Ranked for an unattended, unalerted, public-repo deployment:

1. **Half-written `seen.json` after a runner kill** (Pitfall 1) — atomic write or die.
2. **Concurrent runs racing on push, second `--force`s and clobbers** (Pitfall 3) — `concurrency:` group from day one.
3. **All ATS endpoints return blocked-or-empty, merge logic wipes table** (Pitfalls 2, 5) — sanity gate on merge, distinguish blocked from empty.
4. **Secret leaked into public repo via committed file or log** (Pitfalls 4, 17) — Push Protection + gitleaks + scoped logging.
5. **Workflow scheduled-disabled or permission-broken, no commits for weeks** (Pitfalls 16, 23) — health.json on every run + `permissions: contents: write` from day one.

If the roadmap addresses these five before opening the firehose to 20+ companies, the system will survive months unattended. If any one is missing, expect a silent failure mode within weeks.

---

## Sources

- **Project requirements:** `/Users/DEVDESAI1/Desktop/University_at_Buffalo/Projects/new-grad/.planning/PROJECT.md`
- **GitHub Actions documentation** (concurrency, GITHUB_TOKEN permissions, schedule deactivation policy, IP ranges via `api.github.com/meta`) — HIGH confidence on documented behaviors, established for years.
- **Playwright documentation** (browser caching, navigation timeouts, headless modes) — HIGH confidence.
- **ATS endpoint shapes** (Greenhouse, Lever, Ashby, SmartRecruiters, Workday CXS, Apple jobs API) — MEDIUM confidence on current shapes (these are undocumented public endpoints and can change; Phase 2 should fetch a current sample per company before locking adapter contracts).
- **Anti-bot vendor behavior** (Cloudflare, DataDome, PerimeterX detection patterns) — MEDIUM confidence on general approach, LOW confidence on per-site current state (vendors update continuously; validate per company).
- **Legal landscape on scraping public data** (hiQ v. LinkedIn, Van Buren v. US) — MEDIUM confidence on US precedent direction; not legal advice; jurisdiction-dependent.

**Session note:** Live web search (WebSearch, WebFetch, Context7) was unavailable during this research session. Findings rest on established knowledge of the domain and the project's own requirements document. Items flagged MEDIUM or LOW confidence should be empirically validated during the phase that implements them — particularly current ATS endpoint shapes and current anti-bot fingerprinting techniques, which drift fastest.
