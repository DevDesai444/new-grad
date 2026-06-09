---
slug: bug-f-new-adapters
status: partial
trigger: |
  Bug F: 5 companies in companies.txt are backed by ATSes the project doesn't
  support (Phenom, iCIMS, Avature, Oracle HCM). All fell through to
  PlaywrightAdapter and timed out.
created: 2026-06-09
updated: 2026-06-09
---

# Bug F — New ATS adapters

## Shipped

### Oracle HCM Cloud (Fusion) — `src/adapters/oracle_hcm.py`

- **Unlocks:** **JPMorgan** (verified live — 625 raw postings, hit cold-start cap).
- **API:** `GET https://<tenant>.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?finder=findReqs;siteNumber=<SITE>&limit=N&offset=N&onlyData=true&expand=requisitionList`. Public, unauthenticated.
- **Resolver extension:** body-scan now recognizes the Oracle HCM pattern (`<tenant>.fa.oraclecloud.com/...sites/<SITE>`) — `careers.jpmorgan.com` → `jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001`.
- **Pagination:** 25 per page, 25-page cold-start cap (mirrors WorkdayAdapter pattern). JPMorgan has 7156 total active reqs; we cap at 625 on first scrape, then early-terminate via seen_keys overlap going forward (Phase 4 dedup invariant).
- **Tests:** 19 new tests in `tests/test_oracle_hcm_adapter.py` (happy path, pagination, all 4 error-path classes, registry/dispatch, ADAPTERS ordering invariant).

## Deferred (NOT shipped)

Each of these requires either non-trivial reverse engineering or anti-bot bypass — both beyond reasonable scope for tonight's session.

### Phenom People (Adobe)

- **Tenant:** `ADOBUS` (visible in CDN URLs: `cdn.phenompeople.com/CareerConnectResources/ADOBUS/...`).
- **Probe results 2026-06-09:**

  | Endpoint | HTTP | Notes |
  |---|---|---|
  | `careers.adobe.com/api/jobs/search` (GET) | 200, 99B JSON | `{"status":"failure","errorMsg":"Tenant not identified"}` |
  | `careers.adobe.com/api/jobs/search` (POST + JSON body) | same | tenant header / cookie required |
  | `careers.adobe.com/api/jobs/search?tenant=ADOBUS` | same | URL param not accepted |
  | `careers.adobe.com/widgets/...` | 200 HTML | error page, not API |
  | `careers.adobe.com/services/jobs/search` | 303 | redirect, not API |

- **Blocker:** Tenant identification requires a session cookie or specific header set by the SPA after page load. The standard Phenom endpoint exists at `<careersite>/api/jobs/search` but rejects unauthenticated tenant probes.
- **What's needed:** Load `careers.adobe.com/us/en/search-results` in a real browser with DevTools open, capture the exact XHR sequence — including the tenant-identifying cookie/header. Then either replay that header set, or use a small Playwright-driven helper to obtain the session cookie + use it for the JSON probe.
- **Affects:** Adobe (~1 company in current `companies.txt`). Phenom is used by ~500+ Fortune-500 employers, so a working Phenom adapter would be high-leverage for future additions.

### iCIMS (ARM)

- **Tenants:** `earlycareers-arm.icims.com`, `experienced-arm.icims.com`.
- **Probe results 2026-06-09:**
  - `https://earlycareers-arm.icims.com/jobs/search?ss=1&format=json` → HTTP 200 but Content-Type unset, body is HTML (the SPA wrapper, no jobs in static HTML).
  - `/jobs/search.rss` → HTTP 302 (redirect to auth wall or similar).
- **Blocker:** Modern iCIMS Career Sites are SPAs — jobs load via JS-driven XHR with session state. The legacy RSS feed has been redirected. Direct JSON negotiation via `Accept` / `format=json` is ignored.
- **What's needed:** Inspect the actual XHR endpoint in a browser session (likely `/jobs/search/json`, `/jobs/data`, or similar — varies by iCIMS Career Center version). Then derive identifier + endpoint from hostname pattern.
- **Affects:** ARM (~1 company in current `companies.txt`).

### Avature (Bloomberg, Lenovo)

- **Hosts:** `bloomberg.avature.net`, `<lenovo>.avature.net`.
- **Probe results 2026-06-09:**
  - `careers.bloomberg.com` → 301 → `bloomberg.com/company/what-we-do/` → 403 (Akamai/Imperva wall on every non-browser fetch).
- **Blocker:** Bloomberg is fully behind anti-bot (Akamai). Without a residential proxy or a browser-equivalent fingerprint (TLS handshake + JS challenge response), the resolver can't even reach the Avature URL — `bloomberg.avature.net` is known publicly but reaching it requires defeating the Cloudflare/Akamai challenge that protects the redirect target.
- **What's needed for Bloomberg:** residential proxy (violates $0 constraint per CLAUDE.md). Recommend dropping Bloomberg from `companies.txt` until budget allows.
- **What's needed for Lenovo:** Recon Lenovo's Avature host directly (probably reachable without anti-bot) and build a generic Avature adapter — likely `<tenant>.avature.net/careers/<site>/json` or similar. Lenovo recon hasn't been done yet in this session.

## Companies remaining unsupported after this commit

After Bug F's Oracle HCM ship, the following companies still need work:
- **Adobe** (Phenom — deferred above)
- **ARM** (iCIMS — deferred above)
- **Bloomberg** (Avature + Akamai — likely permanently blocked under $0 constraint)
- **Lenovo** (Avature — needs recon)
- **Apple** (separate bug — endpoint deprecation in `.planning/debug/apple-api-deprecated.md`)

Plus the catch-all SPA sites (Google, LinkedIn, Microsoft, Meta, Oracle Careers, Samsung, Tesla, Uber, Nvidia) which fundamentally rely on PlaywrightAdapter — Bug E's payload-shape validation may unlock 1-2 of these once we observe the next post-fix scan.

## Live verification

```
$ python -c "from src.url_resolver import resolve_url; from src.registry import get_adapter; from src.models import CompanyConfig; c=CompanyConfig(name='jpmorgan', url='https://careers.jpmorgan.com'); c.resolved_url=resolve_url(c.url); a=get_adapter(c); print(type(a).__name__, '->', len(a.fetch(c)), 'postings')"
OracleHCMAdapter -> 625 postings
```
