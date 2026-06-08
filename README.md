# new-grad

Automated hourly tracker for new-grad / early-career job postings (0–5 yrs experience).

**Repo:** github.com/DevDesai444/new-grad
**Cadence:** Hourly (GitHub Actions cron, `0 * * * *` UTC; cron drift of 5–60 min is normal on free-tier — see PITFALLS.md §Pitfall 19).
**Status:** Phase 1 — Walking Skeleton (Greenhouse adapter only; placeholder `companies.txt`).

## Setup — One-Time Repository Configuration (INFRA-08)

Before pushing the first commit, enable in **GitHub Settings → Code security & analysis**:
- **Secret scanning** → ON
- **Push Protection** → ON

These block accidental commits of recognized credential patterns (API tokens, etc.). The `.gitignore` in this repo also blocks `*.env`, `*.har`, `trace.zip`, `cookies.json`, and the `seen.json.tmp` / `seen.json.bak` atomic-write artifacts.

## Current Postings

<!-- BEGIN JOBS -->

(no matching postings yet)

<!-- END JOBS -->

## companies.txt Format (CFG-06)

`companies.txt` is the user's single source of truth for which career pages to scan. The format is intentionally minimal:

- **One career URL per line.** Paste the URL — no other metadata required.
- **Blank lines and `#`-prefixed comment lines are ignored.** Use comments freely to group / annotate / temporarily disable companies.
- **Optional inline hint** (`#adapter=<name>`) overrides URL-pattern dispatch. Claude adds this when needed — the user never needs to.

**Example (Phase 1 supports Greenhouse only):**

```text
# Stripe — Greenhouse
https://boards.greenhouse.io/stripe

# Notion — Greenhouse
https://boards.greenhouse.io/notion

# Anthropic — Phase 3 (custom SPA, requires Playwright)
# https://www.anthropic.com/careers  #adapter=playwright   <-- not yet supported
```

**Phase 1 scope:** Only Greenhouse URLs (`boards.greenhouse.io` and `job-boards.greenhouse.io`) are scraped. Other ATS URLs added before Phase 2 are silently skipped — the run continues for the rest of the file (CFG-05).

## Add a Company (CFG-04)

Tell Claude CLI:

> "Add this Greenhouse URL to the tracker: https://boards.greenhouse.io/<company>"

Claude will:

1. Append the URL line to `companies.txt`
2. Commit + push the change
3. The next hourly cron picks it up automatically — no further user action needed

For non-Greenhouse URLs (Lever, Workday, etc. — Phase 2+), Claude will say "Phase 1 only supports Greenhouse; this URL will be silently skipped until Phase 2 ships."

For credentialed scrapes (Phase 3), Claude will prompt for credentials inline in the chat, store them via `gh secret set SCRAPER_<COMPANY>_EMAIL` / `_PASSWORD`, and confirm by listing `gh secret list` (names only, never values).

## Secret Hygiene (SEC-03)

Phase 1 needs **zero credentials** — the Greenhouse public boards API requires no auth. The discipline below applies as soon as Phase 3 introduces credentialed scrapes:

- All credentials accessed via `os.environ[<NAME>]` (sourced from GitHub Actions Secrets like `secrets.SCRAPER_*` or `secrets.GITHUB_TOKEN`) — never hard-coded in code, never logged.
- `.gitignore` blocks `.env`, `cookies.json`, `*.har`, `trace.zip`, `playwright-report/`, `seen.json.tmp`, `seen.json.bak` — preventing accidental `git add .` of credential-bearing files.
- Adapter code that catches HTTP exceptions logs **status code + URL + exception class only** — never the full traceback (which could include request headers, potentially leaking `Authorization: Bearer ...` tokens or cookies). See Pitfall 17.
- **Secret naming convention placeholder** (filled in Phase 3): scraper credentials use `SCRAPER_<COMPANY>_<KIND>` (e.g., `SCRAPER_ACME_EMAIL`, `SCRAPER_ACME_PASSWORD`). The README's secret-audit table (Phase 3) lets the user list, rotate, or delete credentials via `gh secret` without touching repo files.

## Hourly Cadence — What to Expect

- GitHub Actions cron runs `0 * * * *` UTC. Free-tier cron can be **delayed 15–60 minutes** under load (PITFALLS.md §Pitfall 19) — "hourly" is approximate, not a sub-hour SLA.
- If a run fails mid-write, the next run reads `seen.json.bak` and continues (STATE-03 — atomic write + .bak fallback).
- If a mass-block-or-error scrape would shrink the visible posting count by more than 10%, the run aborts and exits non-zero — visible as a red run in the Actions tab. No silent table wipes (STATE-06).
- **Schedule may auto-disable if no commits occur for 60 consecutive days.** Re-enable via repo settings (Actions → enable the workflow). Health monitoring deferred to a future phase per CONTEXT.md D-01 / D-02 — Phase 1's placeholder `companies.txt` may produce zero commits for an extended period, and that risk is knowingly accepted.

## Recovery — Corrupted seen.json

The state store writes atomically (`.tmp` + `fsync` + `os.replace`) and keeps a `.bak` of the previous version. If both files get corrupted (extremely rare), recovery options in order of preference:

1. **Per-file revert from prior commit:** `git checkout HEAD~1 -- seen.json` then commit + push.
2. **Restore from the `.bak` sibling:** `mv seen.json.bak seen.json` then commit + push.
3. **Cold-restart with empty state:** delete `seen.json` (the next run will create a fresh one). All historical `first_seen` timestamps will be lost — first_seen is reset to the next-run timestamp for every posting.

## Ops Quick Reference

- **Force a run now:** Go to repo → Actions → "scan" workflow → "Run workflow" button.
- **Disable a noisy adapter:** Comment the URL line out in `companies.txt` (prefix with `#`).
- **Recover from a corrupted seen.json:** see "Recovery" section above.
- **Audit secret usage (Phase 3+):** `gh secret list --repo DevDesai444/new-grad` (names only; no values).

## Terms-of-Service Hygiene

- Only public career pages are scraped. No login walls, no JS-protected behind-auth content (Phase 3 will introduce credentialed scrapes only after explicit per-site review).
- Hourly cadence is intentionally conservative — well below the polling rates that draw rate-limit attention from public ATS APIs.
- Posting URLs are listed; full descriptions are NOT mirrored. The user clicks through to the source for the role detail.

## Architecture

See `.planning/research/ARCHITECTURE.md` for the full component diagram. The pipeline is `companies.txt → config_loader → registry → adapters → normalizer → filter → state_merger → renderer → git commit`, executed hourly by `.github/workflows/scan.yml`.

## Local Development

```bash
pipx install uv
uv venv && source .venv/bin/activate
uv pip install -r requirements.lock
pytest -q
```
