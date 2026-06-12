---
phase: quick
plan: 260611-d2z
subsystem: filter, ai
tags: [groq, llm, classification, ai-classifier, httpx, respx]

# Dependency graph
requires:
  - phase: 04-observability
    provides: is_us_location_acceptable, _scrape_one pipeline structure in src/main.py
provides:
  - src/ai_classifier.py exporting Classification dataclass + classify() function
  - Groq-backed domain + early-career gate wired into scan pipeline
  - GROQ_API_KEY secret wired into scan.yml Run scan step
affects:
  - src/main.py pipeline (is_early_career removed, Groq step added)
  - tests/test_end_to_end.py (now mocks Groq API)

# Tech tracking
tech-stack:
  added: []  # No new deps; httpx already in requirements.txt
  patterns:
    - "Soft-fail classifier: all error paths return keep=True, never raise, never drop"
    - "API key never logged: exceptions caught by type, message excluded (Pitfall 17)"
    - "TDD RED/GREEN: test file committed before implementation"

key-files:
  created:
    - src/ai_classifier.py
    - tests/test_ai_classifier.py
  modified:
    - src/main.py
    - .github/workflows/scan.yml
    - README.md
    - tests/test_end_to_end.py

key-decisions:
  - "classify() called with (posting.title, None) — Posting has no description field, soft-fail on None is safe"
  - "is_early_career() import + call REMOVED from main.py _scrape_one; function stays in filter.py for potential reuse"
  - "Filter order: is_us_location_acceptable -> ai_classifier.classify (Groq replaces title-keyword gate)"
  - "Per-company log: groq-classified: kept=X dropped=Y errors=Z for observability"
  - "test_end_to_end.py updated to mock Groq API with respx side_effect list"

patterns-established:
  - "Soft-fail pattern: any error in classify() -> keep=True to prevent silent posting drops"

requirements-completed:
  - GROQ-CLASSIFY-01

# Metrics
duration: 11min
completed: 2026-06-12
---

# Quick Task 260611-d2z: Groq-Backed AI/SWE/DS Early-Career Classifier Summary

**Groq llama-3.3-70b-versatile classifier replacing title-keyword gate: domain (AI/ML|SWE|Data Science|Other) + early-career (0-5 yrs) filter wired into scan pipeline with full soft-fail on any API error**

## Performance

- **Duration:** 11min
- **Started:** 2026-06-12T04:40:49Z
- **Completed:** 2026-06-12T04:51:51Z
- **Tasks:** 2 (Task 1 TDD RED+GREEN, Task 2 wire)
- **Files modified:** 6 (2 new, 4 modified)

## Accomplishments

- Created `src/ai_classifier.py` with `Classification` frozen dataclass and `classify(title, description)` function calling Groq's OpenAI-compatible API
- All error paths (timeout, HTTP non-2xx, malformed JSON, missing API key) return `keep=True` and never raise — transient Groq failures never silently drop postings
- Removed `is_early_career` call from `_scrape_one` pipeline; Groq now handles both domain AND early-career classification in one LLM call
- Wired `GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}` into the scan.yml Run scan step
- 11 new tests covering all locked scenarios; existing tests updated to mock Groq

## Task Commits

1. **Task 1 RED: test file** - `77b8fac` (test)
2. **Task 1 GREEN: implementation** - `58cbb1b` (feat)
3. **Task 2: wire + scan.yml + README** - `b80b1a9` (feat)

## Files Created/Modified

- `src/ai_classifier.py` - Groq classifier module: Classification dataclass, classify() soft-fail function, system prompt with 4-domain taxonomy
- `tests/test_ai_classifier.py` - 11 test cases: 3 happy-path, 2 rejection, 3 error/soft-fail, 1 truncation, 1 no-key, 1 never-logs-key
- `src/main.py` - Removed is_early_career import/call, added `from src import ai_classifier` and Groq classify step with groq_kept/dropped/errors counters
- `.github/workflows/scan.yml` - Added `GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}` env block to Run scan step
- `README.md` - Added "## Groq Classification" section (11 lines) documenting domain/early-career axes and soft-fail behavior
- `tests/test_end_to_end.py` - Updated test_pipeline_first_run to mock Groq API via respx side_effect list + inject GROQ_API_KEY via monkeypatch

## Decisions Made

- `classify()` called with `(posting.title, None)` per plan constraint — Posting model has no description field; soft-fail handles None safely (empty string after truncation)
- `is_early_career` function KEPT in `filter.py` (only the call in `_scrape_one` removed) — function may be useful for testing/debugging; removal from import also dropped per isort
- Filter order locked: `is_us_location_acceptable` (FILT-07) → `ai_classifier.classify` → `postings.append` — US filter first to avoid burning Groq quota on non-US postings
- `error:` prefix on all error reasons and `no-api-key` sentinel enable `groq_errors` counter to tally soft-fails in the per-company log line

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_pipeline_first_run to mock Groq API**
- **Found during:** Task 2 (wiring Groq into main.py)
- **Issue:** End-to-end test expected "Senior Staff Engineer" to be filtered by title-keyword gate (`is_early_career`). After removing that gate and replacing with Groq, the test failed because Groq soft-fails to `keep=True` when `GROQ_API_KEY` is not set in the test environment — causing Senior Staff to be kept incorrectly
- **Fix:** Updated `test_pipeline_first_run` to inject `GROQ_API_KEY` via monkeypatch and mock the Groq API with a `respx.post().mock(side_effect=[...])` list returning correct classifications (New Grad=SWE+early, Senior Staff=SWE+NOT early, Associate=SWE+early)
- **Files modified:** `tests/test_end_to_end.py`
- **Verification:** `pytest tests/test_end_to_end.py -v` — all 3 tests pass
- **Committed in:** b80b1a9

**2. [Rule 1 - Bug] Fixed respx API: `mock.call_count` does not exist**
- **Found during:** Task 1 GREEN (running tests)
- **Issue:** Test used `mock.call_count == 0` but respx MockRouter exposes `mock.calls` list, not a `.call_count` attribute
- **Fix:** Changed assertion to `len(mock.calls) == 0`
- **Files modified:** `tests/test_ai_classifier.py`
- **Verification:** `pytest tests/test_ai_classifier.py -v` — all 11 tests pass
- **Committed in:** 58cbb1b

**3. [Rule 1 - Bug] Fixed ruff E501 line-too-long in _SYSTEM_PROMPT string**
- **Found during:** Task 1 GREEN (ruff check)
- **Issue:** The multiline triple-quoted string for `_SYSTEM_PROMPT` had 8 lines exceeding the 100-char limit
- **Fix:** Converted to concatenated string literals with lines split under 100 chars each
- **Files modified:** `src/ai_classifier.py`
- **Verification:** `python3 -m ruff check src/ai_classifier.py` → "All checks passed!"
- **Committed in:** 58cbb1b

---

**Total deviations:** 3 auto-fixed (all Rule 1 bugs)
**Impact on plan:** All necessary for correctness and linting compliance. No scope creep.

## Issues Encountered

None beyond the auto-fixed deviations above.

## Test Results

- **New tests:** 11 in `tests/test_ai_classifier.py` — all pass
- **Pre-existing test suite:** 617 pass, 3 fail (pre-existing worktree-env issues: `.planning/REQUIREMENTS.md` path not available in worktree + `companies.txt` already populated)
- **Playwright tests excluded:** pre-existing Chromium-not-installed failures in worktree env
- **ruff:** clean on `src/ai_classifier.py` and `src/main.py`

## Known Stubs

None — `classify()` makes real Groq API calls; soft-fail is the explicit design, not a stub.

## Threat Flags

All network surface from this task is explicitly covered by the plan's `<threat_model>`:

| Flag | File | Description |
|------|------|-------------|
| T-groq-01 mitigated | src/ai_classifier.py | API key never logged; only `type(e).__name__` and `title` in error paths |
| T-groq-04 mitigated | .github/workflows/scan.yml | `${{ secrets.GROQ_API_KEY }}` — GitHub auto-masks in logs |

## Self-Check: PASSED

- src/ai_classifier.py: FOUND
- tests/test_ai_classifier.py: FOUND
- SUMMARY.md: FOUND
- Commit 77b8fac (RED): FOUND
- Commit 58cbb1b (GREEN): FOUND
- Commit b80b1a9 (Task 2): FOUND
