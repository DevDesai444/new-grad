# Phase 3: Playwright Fallback + Credential Workflow - Discussion Log

> **Audit trail only.** Decisions are in CONTEXT.md.

**Date:** 2026-06-07
**Phase:** 03-playwright-fallback-credential-workflow
**Areas discussed:** Seed SPA target + selector strategy, Credential UX, playwright-stealth default, Timeout + trace policy

---

## Seed SPA target + selector vs XHR strategy

User shared their actual companies.txt (`/Users/DEVDESAI1/Downloads/companies.txt`, 31 URLs) and asked Claude to assess coverage. Claude categorized:
- ~18 URLs = CNAME → Workday tenants (need redirect-follow to be handled by Phase 2's Workday adapter)
- ~6 URLs = static landing → JS redirect to Workday
- ~7 URLs = true custom SPA (Playwright candidates)
- 1 URL = apple.com/careers (different host than Phase 2's jobs.apple.com adapter — needs Playwright)
- 1 URL = Freenome (likely Greenhouse)

**User's expressed workflow expectation:** "When I find some new company that I am interested in I will tell claude code cli to add them in the list. I want claude code to see if my current project can handle that companies career page reliably or not. If not then I want claude code to update the project code such that it will support that companies career page reliably without disturbing other companies adaptors. This till all thing should be done without me explicitly tell it to do. I will just say something like 'add <this companies career page url> to tracking' or something like that and claude code should do rest stuff for me and incorporate that company's career page into tracking and tracking of all companies should be done in correct way."

Claude addressed this as a CLAUDE.md workflow doc (D-03). It's not project code — it's instructions for Claude CLI.

| Option | Selected |
|--------|----------|
| Anthropic careers (recommended fallback since user's list has no clean SPA-only target — all are CNAME→ATS) | ✓ |
| Pick a different company | |
| Hand-crafted synthetic fixture only | |

**Bonus decisions surfaced from companies.txt analysis (locked alongside D-01):**
- D-01b: Add `httpx.head(url, follow_redirects=True)` pre-flight in `src/registry.py` — unblocks the ~18 CNAME→Workday cases.
- D-01c: Add CLAUDE.md "Adding a Company" workflow section.

---

## Credential UX flow

User requested explanation; Claude explained the public-repo constraint + the gh-secret-set workflow + the two design axes (when to prompt; how to store).

After explanation:

| Option | Selected |
|--------|----------|
| Eager prompt + separate per-kind secrets | ✓ |
| Lazy prompt (on first MissingCredential) | |
| Eager prompt + single combined secret | |

Captured as D-02 + D-02a + D-02b + D-02c.

---

## playwright-stealth default

User requested explanation; Claude explained anti-bot fingerprinting + what stealth patches.

After explanation:

| Option | Selected |
|--------|----------|
| On by default, per-site opt-out | ✓ |
| Off by default, per-site opt-in | |
| Always on, no opt-out | |

Captured as D-04.

---

## Per-page timeout + trace recording

User requested explanation for both; Claude explained:
- Timeout = upper bound, not fixed wait (fast pages return at actual load time)
- Trace = captures HTTP headers including credentials, lethal in production

After explanation, user asked clarifying question: "60 sec + per-site override, but if the site openns before it will start working right?"

Claude confirmed: yes, timeout is a maximum, not a fixed wait.

| Question | Selection |
|----------|-----------|
| Timeout | 60s default + per-site override (user-modified from 20s recommendation) |
| Trace | Off in prod + env-var escape hatch for local debug (recommended) |

Captured as D-05 + D-06.

---

## Claude's Discretion

- Realistic User-Agent string (planner picks current Chrome version at implementation)
- Viewport size (`1920x1080`)
- Login-form detection heuristic (`<input type="password">` parsing)
- `InvalidCredential` vs `MissingCredential` typed exception split
- Network throttling for tests (`page.route()` mocking)
- Playwright install command in workflow YAML

## Deferred Ideas

- Multi-factor / OAuth credentialed sites (out of scope v1)
- Proxy escape hatch (`USE_PROXY=1` workflow var)
- Persistent browser context (session reuse)
- Selenium fallback
- Auto-detection of underlying ATS at URL resolve time
- Browser pool / connection reuse across companies
