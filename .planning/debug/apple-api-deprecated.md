---
slug: apple-api-deprecated
status: open
trigger: |
  Surfaced during Bug D verification on 2026-06-09. Fixing Bug D's resolver
  short-circuit correctly routes `https://jobs.apple.com` to AppleAdapter (no
  longer downgraded to Playwright). But AppleAdapter's hard-coded endpoint
  `POST https://jobs.apple.com/api/role/search` is permanently dead — Apple
  retired this URL.
created: 2026-06-09
updated: 2026-06-09
---

# Apple API deprecation — AppleAdapter endpoint is dead

## Symptom

After Bug D's resolver short-circuit lands, `careers.adobe.com` dispatches
correctly to AppleAdapter. AppleAdapter then issues `POST https://jobs.apple.com/api/role/search` and gets:

```
HTTP/2 301 Moved Permanently
location: https://apple.com/pagenotfound
```

Result: every Apple scrape raises `httpx.HTTPStatusError: Redirect response
301`. Apple shows up as `outcome=error: Exception` in seen.json — no
postings.

## Recon results

Probed common Apple API URL patterns 2026-06-09:

| Endpoint | Result |
|---|---|
| `https://jobs.apple.com/api/role/search` | 301 → `apple.com/pagenotfound` (dead) |
| `https://jobs.apple.com/api/role/search?l=en-us` | 301 → dead |
| `https://jobs.apple.com/api/role/list` | 301 → dead |
| `https://jobs.apple.com/api/v3/search` | 301 → dead |
| `https://jobs.apple.com/api/v1/search` | HTTP 436 (Apple-custom — likely missing required header) |
| `https://jobs.apple.com/en-us/api/role/search` | HTTP 000 (DNS / TLS error) |

The `/api/v1/search` 436 is the most interesting — Apple still serves it but
demands specific request signing or headers. The Apple jobs SPA likely uses
a client-side token / cookie set during the initial page load.

## What's needed to fix

1. **Reverse-engineer the current API.** Load `https://jobs.apple.com/en-us/search` in a real browser with DevTools open, capture the actual XHR/fetch the SPA makes when paging results. Likely contains a session cookie + custom header (`X-Requested-With: XMLHttpRequest`, possibly a CSRF token, possibly a signed bearer).
2. **Rewrite AppleAdapter** to either (a) replicate the headers/cookies from a logged-out browser visit, or (b) shell out to a tiny Playwright-driven session to fetch the JSON.

## Workaround until then

Comment out Apple in `companies.txt` OR accept the `outcome=error: Exception`
status. With Bug A's deadline fix, the failure is now near-instant (one HTTP
call) rather than a 60s Playwright timeout — so Apple's broken state no
longer eats a meaningful chunk of the Action's 50min budget.

## Scope

Distinct from Bug D. Bug D's deliverable is the dispatch short-circuit;
that's correct in principle even if AppleAdapter's endpoint is dead. This
debug note is the audit trail for the follow-up adapter rewrite.
