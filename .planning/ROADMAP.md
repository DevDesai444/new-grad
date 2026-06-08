# Roadmap: new-grad

**Core Value:** One glance at the GitHub repo shows every currently-known new-grad-eligible role across the user's tracked companies, with a working application link.
**Mode:** mvp (Vertical MVP — every phase delivers an end-to-end working slice)

## Milestones

- ✅ **v1.0 MVP** — Phases 1–4 (shipped 2026-06-08) — [archive](milestones/v1.0-ROADMAP.md) · [audit](milestones/v1.0-MILESTONE-AUDIT.md) · [requirements](milestones/v1.0-REQUIREMENTS.md)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1–4) — SHIPPED 2026-06-08</summary>

- [x] **Phase 1: Walking Skeleton** — One Greenhouse company scraped → filtered → deduped → rendered → committed end-to-end on hourly cron. Verification: human_needed (live-cron + GitHub Push Protection deferred to post-launch user action).
- [x] **Phase 2: ATS Breadth + JD-Scan** — Lever / Ashby / SmartRecruiters / Workday / Apple adapters + JD-scan extraction populating Experience column. Verification: human_needed (live ATS smoke deferred to post-launch).
- [x] **Phase 3: Playwright Fallback + Credential Workflow** — Headless-Chromium catch-all for JS-heavy SPAs + URL redirect-resolver for CNAME→Workday + `gh secret set` credential flow via Claude CLI. Verification: human_needed (live SPA scrape + credential provisioning deferred to post-launch).
- [x] **Phase 4: Extraction Polish + Health Observability** — Salary verbatim + Remote-variant location collapse + US-only filter (FILT-07 NEW) + per-source health DATA tracked in `seen.json.source_health` (NOT rendered, per CONTEXT.md D-04c). Verification: passed.

</details>

## Backlog

Items captured during development for future milestones (not in v1.0 scope):

- `seen_keys` threading from `src/main.py` into Workday/Apple/Playwright `fetch()` (early-termination optimization currently dormant; 25-page cold-start cap is active limit)
- `--validate` CLI mode for pre-flight state inspection
- Explicit query-param stripping in log messages (Phase 3+ credentialed-adapter hygiene)
- `src/adapters/workday.py` RUN-01 deviation cleanup (local `datetime.now()` in relative-postedOn parsing)
- Optional: render `seen.json.source_health` as README footer (data is already tracked; rendering deferred per D-04c)

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Walking Skeleton | v1.0 | 3/3 | Complete | 2026-06-07 |
| 2. ATS Breadth + JD-Scan | v1.0 | 3/3 | Complete | 2026-06-08 |
| 3. Playwright Fallback + Credential Workflow | v1.0 | 3/3 | Complete | 2026-06-08 |
| 4. Extraction Polish + Health Observability | v1.0 | 3/3 | Complete | 2026-06-08 |

---

*Milestone v1.0 shipped: 2026-06-08*
*72/72 v1 requirements satisfied (3 user-decision strikethroughs honored)*
*555 tests passing · ruff clean · ADP-14/15 invariant preserved across all 4 phases*
