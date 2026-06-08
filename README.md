# new-grad

Automated hourly tracker for new-grad / early-career job postings (0–5 yrs experience).

**Repo:** github.com/DevDesai444/new-grad
**Cadence:** Hourly (GitHub Actions cron, `0 * * * *` UTC; cron drift of 5–60 min is normal on free-tier — see PITFALLS.md §Pitfall 19).
**Status:** Phase 1 — Walking Skeleton (Greenhouse adapter only; placeholder `companies.txt`).

## Setup — One-Time Repository Configuration (INFRA-08)

Before pushing the first commit, enable in **GitHub Settings → Code security & analysis**:
- **Secret scanning** → ON
- **Push protection** → ON

These block accidental commits of recognized credential patterns (API tokens, etc.). The `.gitignore` in this repo also blocks `*.env`, `*.har`, `trace.zip`, `cookies.json`, and the `seen.json.tmp` / `seen.json.bak` atomic-write artifacts.

## Current Postings

<!-- BEGIN JOBS -->
(no matching postings yet)
<!-- END JOBS -->

## Architecture

See `.planning/research/ARCHITECTURE.md` for the full component diagram. The pipeline is `companies.txt → config_loader → registry → adapters → normalizer → filter → state_merger → renderer → git commit`, executed hourly by `.github/workflows/scan.yml`.

## Local Development

```bash
pipx install uv
uv venv && source .venv/bin/activate
uv pip install -r requirements.lock
pytest -q
```
