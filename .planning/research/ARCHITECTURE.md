# Architecture Patterns

**Domain:** Automated job-posting tracker (Python + Playwright + GitHub Actions)
**Researched:** 2026-06-07
**Confidence:** HIGH (architecture maps cleanly to validated PROJECT.md constraints; ATS endpoint shapes are well-known public surface area)

---

## Executive Summary

This system is a classic **ETL pipeline with a plugin/adapter registry**, run as a stateless hourly batch job on GitHub Actions. State lives in the repo (`seen.json`); the render target is the repo itself (`README.md`). The architecture has three forcing functions:

1. **Companies are data, not code.** Adding a company is a one-line append to `companies.txt`. Zero Python edits.
2. **One company's failure cannot break the run.** Every per-company step is wrapped in try/except with structured logging; the worst case is "no new postings from CompanyX this hour."
3. **The adapter pattern absorbs ATS diversity.** Each ATS (Greenhouse, Lever, Ashby, Workday, SmartRecruiters) is one file implementing one interface. Custom JS-heavy sites fall back to a single Playwright adapter. A new ATS = new file in `adapters/`, no refactor.

The data flow is linear and unidirectional: **config in → fetch → normalize → filter → merge with state → render → commit.** No background workers, no queues, no databases. GitHub Actions itself is the scheduler.

---

## Recommended Architecture

### High-Level Diagram

```
                    ┌─────────────────────────────────────┐
                    │   GitHub Actions cron (0 * * * *)   │
                    └────────────────┬────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────┐
                    │           src/main.py                │
                    │   (orchestrator / entry point)       │
                    └────────────────┬────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
   │ companies.txt   │    │  seen.json      │    │  README.md       │
   │ (input config)  │    │ (state store)   │    │ (render target)  │
   └────────┬────────┘    └─────────────────┘    └─────────────────┘
            │                      ▲                      ▲
            ▼                      │                      │
   ┌─────────────────┐             │                      │
   │ config_loader   │             │                      │
   └────────┬────────┘             │                      │
            │                      │                      │
            ▼                      │                      │
   ┌─────────────────┐             │                      │
   │ adapter_registry│             │                      │
   │ (URL→adapter)   │             │                      │
   └────────┬────────┘             │                      │
            │                      │                      │
   ┌────────┴────────────┐         │                      │
   ▼                     ▼         │                      │
┌────────────┐  ┌────────────────┐ │                      │
│ ATS adapter│  │Playwright      │ │                      │
│ (HTTP+JSON)│  │ adapter (HTML) │ │                      │
└──────┬─────┘  └────────┬───────┘ │                      │
       │                 │         │                      │
       └────────┬────────┘         │                      │
                ▼                  │                      │
       ┌─────────────────┐         │                      │
       │  normalizer     │         │                      │
       │ (→ Posting)     │         │                      │
       └────────┬────────┘         │                      │
                ▼                  │                      │
       ┌─────────────────┐         │                      │
       │  filter         │         │                      │
       │ (0-5 yrs gate)  │         │                      │
       └────────┬────────┘         │                      │
                ▼                  │                      │
       ┌─────────────────┐         │                      │
       │  state_merger   ├─────────┘                      │
       │ (dedup, first-  │                                │
       │  seen, age)     │                                │
       └────────┬────────┘                                │
                ▼                                         │
       ┌─────────────────┐                                │
       │  renderer       ├────────────────────────────────┘
       │ (Markdown table)│
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │  git_commit     │
       └─────────────────┘
```

### Component Boundaries

| Component | File | Responsibility | Inputs | Outputs | Communicates With |
|-----------|------|----------------|--------|---------|-------------------|
| **Orchestrator** | `src/main.py` | Wire components, drive the run, isolate per-company failures | argv, env | exit code | All components |
| **Config Loader** | `src/config_loader.py` | Parse `companies.txt` into structured records | `companies.txt` | `list[CompanyConfig]` | Registry |
| **Adapter Registry** | `src/registry.py` | Map a careers URL → the right adapter class | URL | Adapter instance | Adapters |
| **Adapter (interface)** | `src/adapters/base.py` | Abstract base: `fetch() -> list[RawPosting]` | URL, params | `list[RawPosting]` | HTTP/Playwright |
| **ATS Adapters** | `src/adapters/{greenhouse,lever,ashby,workday,smartrecruiters}.py` | Hit ATS JSON endpoint, return raw postings | URL | `list[RawPosting]` | `httpx` |
| **Playwright Adapter** | `src/adapters/playwright_fallback.py` | Headless browser scrape for non-ATS / SPA sites | URL, selectors hint | `list[RawPosting]` | Playwright |
| **Normalizer** | `src/normalizer.py` | Convert `RawPosting` → canonical `Posting`; extract experience range from description | `RawPosting` | `Posting` | (pure) |
| **Filter** | `src/filter.py` | Drop senior/staff/principal; keep 0–5 yrs via title keywords AND description scan | `Posting` | `Posting` or None | (pure) |
| **State Store** | `src/state_store.py` | Load/save `seen.json`; provide dedup key lookup | `seen.json` | dict, save fn | Filesystem |
| **State Merger** | `src/state_merger.py` | Merge fresh postings with `seen.json`: assign first_seen, update last_seen, preserve stale | `list[Posting]`, state | merged state, render list | State Store |
| **Renderer** | `src/renderer.py` | Emit Markdown table block; splice into `README.md` between sentinels | merged state | `README.md` content | Filesystem |
| **Git Commit** | `.github/workflows/scan.yml` (inline) | Stage `README.md` and `seen.json`, commit, push | working tree | git push | git CLI |

**Key boundary rules:**
- **Adapters know nothing about state or rendering.** They return raw dicts/objects only.
- **Normalizer is pure** — same `RawPosting` always yields the same `Posting`. No I/O.
- **State merger is the only component that knows about time** (first_seen, last_seen). Adapters and normalizer never call `datetime.now()`.
- **Renderer is the only component that touches `README.md`.**

### Data Flow

```
companies.txt
   │
   ▼  config_loader.load()
list[CompanyConfig]
   │
   ▼  for each company (try/except isolated):
   │     registry.get_adapter(company.url).fetch()
list[RawPosting]   (per company)
   │
   ▼  normalizer.normalize(raw)
list[Posting]      (per company)
   │
   ▼  filter.is_early_career(posting)
list[Posting]      (filtered, per company)
   │
   ▼  (aggregate across all companies)
list[Posting]      (all fresh postings this run)
   │
   ▼  state_merger.merge(fresh, seen_state)
   │     - new posting   → assign first_seen = now, last_seen = now
   │     - known posting → update last_seen = now
   │     - missing from fresh but in state → KEEP (stale-but-tracked)
MergedState (dict: key → PostingRecord)
   │
   ▼  state_store.save(merged_state)  → writes seen.json
   │
   ▼  renderer.render(merged_state) → Markdown table
   │
   ▼  splice into README.md between <!-- BEGIN/END JOBS --> sentinels
   │
   ▼  git add seen.json README.md && git commit && git push
   │     (skip commit if no diff)
```

**Error isolation guarantee:** The `for each company` loop wraps EACH company's `fetch → normalize → filter` pipeline in `try/except Exception`. A Workday tenant returning 503, a Playwright timeout, or a JSON parse error logs the company name + error and continues to the next company. The merge step then operates only on the companies that succeeded; the state for failed companies is preserved untouched (they remain in `seen.json` with their old `last_seen`, exactly as if no fresh data arrived).

---

## Concrete Data Shapes

### `Posting` (canonical, post-normalize)

```python
# src/models.py
from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass(frozen=True)
class Posting:
    company: str             # canonical company name, e.g. "Apple"
    title: str               # exact job title from source
    location: str            # "Cupertino, CA" | "Remote, US" | "Multiple" | ""
    url: str                 # canonical posting URL (stable, https)
    posted_date: Optional[date]  # from source if exposed, else None
    salary: Optional[str]    # "$120k–$160k" | None
    experience_min: Optional[int]  # years, extracted from description
    experience_max: Optional[int]  # years, extracted from description
    description_excerpt: str # first ~500 chars, used for filter scan

    @property
    def dedup_key(self) -> str:
        return f"{self.company.lower()}::{self.url}"
```

### `RawPosting` (adapter output, pre-normalize)

```python
@dataclass
class RawPosting:
    source_company: str       # company name the adapter was called with
    raw: dict                 # ATS JSON blob OR scraped HTML fields
    source_adapter: str       # "greenhouse" | "lever" | "playwright" | ...
```

Normalizer dispatches on `source_adapter` to know how to dig into `raw`.

### `seen.json` schema

```json
{
  "schema_version": 1,
  "last_run_utc": "2026-06-07T14:00:00Z",
  "postings": {
    "apple::https://jobs.apple.com/en-us/details/200593841": {
      "company": "Apple",
      "title": "Software Engineer, New Grad",
      "location": "Cupertino, CA",
      "url": "https://jobs.apple.com/en-us/details/200593841",
      "posted_date": "2026-06-01",
      "salary": "$135k–$170k",
      "experience_min": 0,
      "experience_max": 3,
      "first_seen_utc": "2026-06-02T15:00:00Z",
      "last_seen_utc": "2026-06-07T14:00:00Z",
      "still_listed": true
    }
  }
}
```

Keys are `dedup_key` strings (`company_lower::url`). `still_listed=false` means the posting was in `seen.json` but absent from the latest fresh fetch — kept forever per requirement, just flagged.

### `CompanyConfig` (companies.txt parse output)

```python
@dataclass
class CompanyConfig:
    name: str          # derived from URL or explicit comment annotation
    url: str           # the careers URL the user pasted
    hint: Optional[str]  # optional override like "playwright" or "workday:companyname"
```

`companies.txt` format (one URL per line, comments allowed):

```
# Apple — uses jobs.apple.com JSON API
https://jobs.apple.com/en-us/search?location=united-states

# Stripe — Greenhouse
https://boards.greenhouse.io/stripe

# Anthropic — custom; force Playwright
https://www.anthropic.com/careers  #adapter=playwright

# Nvidia — Workday
https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite  #tenant=nvidia,site=NVIDIAExternalCareerSite
```

---

## The Adapter Pattern (the heart of "1-line to add a company")

### Interface

```python
# src/adapters/base.py
from abc import ABC, abstractmethod

class Adapter(ABC):
    name: str  # class attribute: "greenhouse", "lever", ...

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        """Return True if this adapter handles this careers URL."""

    @abstractmethod
    def fetch(self, company: CompanyConfig) -> list[RawPosting]:
        """Hit the source, return raw postings. Raise on hard failure."""
```

### Registry (auto-discovery)

```python
# src/registry.py
from src.adapters import greenhouse, lever, ashby, workday, smartrecruiters, playwright_fallback

ADAPTERS = [
    greenhouse.GreenhouseAdapter,
    lever.LeverAdapter,
    ashby.AshbyAdapter,
    workday.WorkdayAdapter,
    smartrecruiters.SmartRecruitersAdapter,
    # Apple, Nvidia-custom, etc. → playwright fallback always last
    playwright_fallback.PlaywrightAdapter,
]

def get_adapter(company: CompanyConfig) -> Adapter:
    # Explicit hint wins
    if company.hint:
        for A in ADAPTERS:
            if A.name == company.hint.split(":")[0]:
                return A()
    # Otherwise URL-pattern match, first wins, Playwright is catch-all
    for A in ADAPTERS:
        if A.matches(company.url):
            return A()
    raise NoAdapterFound(company.url)
```

**Adding a new ATS = create one file in `src/adapters/`, append one line to `ADAPTERS`.** No refactor of registry logic, no changes to orchestrator, normalizer, filter, or renderer.

**Adding a new company = append one line to `companies.txt`.** Zero Python edits if URL matches an existing adapter. If the site is exotic, the user adds `#adapter=playwright` and it routes to the fallback.

---

## File Layout Proposal

```
/                                # repo root
├── README.md                    # render target (table between sentinels)
├── companies.txt                # input config
├── seen.json                    # state store
├── pyproject.toml               # deps: httpx, playwright, python-dateutil
├── .github/
│   └── workflows/
│       └── scan.yml             # hourly cron
├── src/
│   ├── __init__.py
│   ├── main.py                  # entry point: `python -m src.main`
│   ├── models.py                # Posting, RawPosting, CompanyConfig
│   ├── config_loader.py
│   ├── registry.py
│   ├── normalizer.py
│   ├── filter.py
│   ├── state_store.py
│   ├── state_merger.py
│   ├── renderer.py
│   └── adapters/
│       ├── __init__.py
│       ├── base.py              # Adapter ABC
│       ├── greenhouse.py
│       ├── lever.py
│       ├── ashby.py
│       ├── workday.py
│       ├── smartrecruiters.py
│       ├── apple.py             # uses jobs.apple.com/api/role/search directly
│       └── playwright_fallback.py
└── tests/
    ├── fixtures/                # canned ATS JSON responses
    ├── test_normalizer.py
    ├── test_filter.py
    ├── test_state_merger.py
    └── test_renderer.py
```

---

## Patterns to Follow

### Pattern 1: Adapter ABC + Registry
**What:** Each scraping strategy is a class implementing `Adapter`; registry maps URL → adapter.
**When:** Any time multiple sources expose the same conceptual data through different mechanics.
**Why:** New ATS support is one new file + one new import. Open/closed principle.

### Pattern 2: Per-Company Error Isolation
**What:** Wrap each company's fetch+normalize+filter chain in `try/except Exception`.
**When:** Always. This is the resilience guarantee.
**Example:**
```python
results = []
for company in companies:
    try:
        adapter = get_adapter(company)
        raw = adapter.fetch(company)
        postings = [normalize(r) for r in raw]
        postings = [p for p in postings if is_early_career(p)]
        results.extend(postings)
    except Exception as e:
        log.error("scrape_failed", company=company.name, err=str(e))
        # state for this company is preserved by state_merger
```

### Pattern 3: Pure Core, Impure Edges
**What:** Normalizer, filter, state_merger, renderer are pure functions. I/O lives only in adapters, state_store, and git_commit.
**When:** Always. Makes 95% of the codebase trivially testable.
**Why:** No network or filesystem in unit tests for the logic that gets edited most often.

### Pattern 4: Sentinel-Bracketed Render Region
**What:** README.md has `<!-- BEGIN JOBS -->` and `<!-- END JOBS -->` markers. Renderer replaces everything between them.
**When:** Always.
**Why:** User can edit the rest of README.md (intro, links, attribution) without the scanner clobbering it.

### Pattern 5: Single-Writer State File
**What:** Only `state_store.save()` writes `seen.json`. Only `renderer.write()` writes `README.md`. No other component touches these files.
**When:** Always.
**Why:** Easy to reason about; easy to mock in tests.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: If/Elif Chain on Company Name in main.py
**What:** `if company == "apple": scrape_apple() elif company == "stripe": scrape_stripe()...`
**Why bad:** Every new company is a code edit. Violates the requirement.
**Instead:** Registry + adapter classes.

### Anti-Pattern 2: Mutating Shared State Mid-Fetch
**What:** Each adapter reads/writes `seen.json` directly.
**Why bad:** Race conditions impossible to debug; failure of one adapter corrupts state for all.
**Instead:** Adapters return data; merger is the single writer.

### Anti-Pattern 3: One Big "fetch_all_jobs.py" Script
**What:** Everything in one 800-line file.
**Why bad:** Untestable, every change risks every other behavior.
**Instead:** Component split per File Layout above.

### Anti-Pattern 4: Auto-Removing Postings That Disappear
**What:** Deleting from `seen.json` when a posting drops off the source.
**Why bad:** Explicitly violates the "keep stale entries forever" requirement.
**Instead:** Set `still_listed=false`; render keeps showing it.

### Anti-Pattern 5: `datetime.now()` Scattered Across Modules
**What:** Adapters, normalizer, renderer each call `datetime.now()`.
**Why bad:** Hard to test; multiple "now" values inside one run; timezone drift.
**Instead:** `main.py` captures `run_started_at = datetime.now(UTC)` once, passes it to `state_merger`.

### Anti-Pattern 6: Storing the Markdown Table in seen.json
**What:** Caching the rendered table to avoid re-rendering.
**Why bad:** Two sources of truth. Renders are cheap; state should be data only.
**Instead:** Re-render from `seen.json` every run.

---

## Build Order (Smallest End-to-End Slice First)

The smallest slice that proves the architecture is **one company, one adapter, end-to-end commit.** Everything else is breadth.

### Slice 0: Walking Skeleton (proves the architecture)
1. `models.py` with `Posting`, `RawPosting`, `CompanyConfig`
2. `config_loader.py` reads `companies.txt`
3. `adapters/base.py` ABC
4. **One** adapter: `adapters/greenhouse.py` (simplest ATS — one JSON GET)
5. `registry.py` with just Greenhouse
6. `normalizer.py` for Greenhouse only
7. `filter.py` — title keyword pass only (description scan in Slice 2)
8. `state_store.py` + `state_merger.py`
9. `renderer.py` with sentinel splice
10. `main.py` wiring
11. `.github/workflows/scan.yml` (cron + checkout + run + commit)
12. `companies.txt` with one Greenhouse-hosted company (e.g., Stripe)

**Definition of done for Slice 0:** Cron fires; one Greenhouse company gets scraped; README.md table shows new-grad roles; commit pushes; second run dedups correctly.

### Slice 1: Adapter Breadth
- Add Lever, Ashby, SmartRecruiters adapters (all similar JSON-endpoint shape)
- Add Workday adapter (POST to `/wday/cxs/{tenant}/{site}/jobs`)
- Add ~5 companies per ATS to `companies.txt`

### Slice 2: Description-Based Filtering
- Fetch full job descriptions (most ATS adapters already include this in their list response)
- `filter.py` adds description scan: regex for "X+ years experience", "minimum Y years", etc.
- Normalizer extracts `experience_min` / `experience_max`

### Slice 3: Playwright Fallback
- `adapters/playwright_fallback.py`
- Apple custom adapter (`jobs.apple.com/api/role/search` — actually JSON, no Playwright needed; do as dedicated adapter)
- True Playwright tested on one JS-heavy SPA (e.g., Anthropic careers)

### Slice 4: Resilience & Observability
- Structured logging with `structlog` or stdlib JSON formatter
- Per-company timing
- Run summary printed at end (companies scraped, postings new, postings stale, errors)
- GH Actions step summary uses this

### Slice 5: Polish
- Salary extraction (where exposed)
- Better location normalization (`Remote, US` vs `Cupertino, CA, USA`)
- Posted-date extraction fallback to `first_seen_utc`

**Why this order:** Slice 0 forces every architectural seam (config → registry → adapter → normalize → filter → state → render → commit) to exist before any breadth is added. Slices 1–5 then add capability without touching architecture.

---

## "Add a New Company" Workflow

This is the load-bearing UX. It must work without Python edits.

### Case A: URL matches an existing ATS adapter
1. User says (to Claude CLI): "add https://boards.greenhouse.io/notion"
2. Claude appends one line to `companies.txt`:
   ```
   https://boards.greenhouse.io/notion
   ```
3. Claude commits and pushes.
4. Next hourly cron picks it up automatically.

**Total code edits: 0.**

### Case B: URL is for a known ATS but adapter needs a hint
1. User says: "add Microsoft careers"
2. Claude appends:
   ```
   https://careers.microsoft.com/v2/global/en/search  #adapter=workday,tenant=microsoft,site=mscareers
   ```
3. Commit + push. Cron picks it up.

**Total code edits: 0.**

### Case C: URL is for a site with no existing adapter (exotic SPA)
1. User says: "add Cohere careers"
2. Claude appends:
   ```
   https://cohere.com/careers  #adapter=playwright
   ```
3. Commit + push. Playwright fallback handles it.

**Total code edits: 0.**

### Case D: New ATS entirely (rare; e.g., a Recruitee-hosted company)
1. User says: "add this Recruitee company"
2. Claude creates `src/adapters/recruitee.py` implementing `Adapter`
3. Claude appends one line to `registry.py` `ADAPTERS` list
4. Claude appends URL to `companies.txt`
5. Commit + push

**Total code edits: 1 new file + 1 line in registry.** This is the ONLY case requiring code.

The requirement "1-line to add a company" is satisfied for cases A–C, which cover ~99% of real-world adds. Case D is the legitimate exception and the adapter pattern makes it minimal.

---

## Scalability Considerations

| Concern | At 10 companies | At 100 companies | At 1000 companies |
|---------|-----------------|------------------|-------------------|
| **Runtime per cron** | <30s, mostly Greenhouse/Lever | 3–8 min (Playwright dominates) | Would exceed 1-hour cron; would need parallelism |
| **GitHub Actions minutes/mo** | ~120 min/mo | ~600 min/mo | Tight on private, fine on public |
| **`seen.json` size** | ~10 KB | ~200 KB | ~2 MB (still fine for git) |
| **Commit churn** | Tiny | Small (1–2 lines diff most hours) | Manageable; consider squash-merge bot if noisy |
| **Adapter concurrency** | Serial fine | Serial fine for ATS APIs; Playwright is the bottleneck | Would need `asyncio.gather` for ATS and a Playwright worker pool |
| **Rate limiting** | Negligible | One UA, polite delays between same-ATS calls | Per-host token bucket needed |

The current architecture scales to ~100 companies on its current shape. Beyond that, the parallelization story changes — but YAGNI for a solo user tracking 10–100 companies.

---

## Sources

- Project PROJECT.md — domain constraints, requirements, and tech decisions
- Known public ATS endpoint shapes (training data; verified via well-documented community projects like SimplifyJobs/New-Grad-Positions and Ouckah/Summer2026-Internships — both use the same adapter pattern this design proposes)
- GitHub Actions cron + commit-back pattern is the canonical pattern these public job-tracker repos use
- Adapter / plugin registry pattern: standard OO design (Open/Closed Principle, Strategy Pattern)
