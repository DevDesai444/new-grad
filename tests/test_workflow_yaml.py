"""Tests for `.github/workflows/scan.yml` structure (Phase 3 Plan 03-01).

Asserts:
- The Playwright Chromium install step exists (`playwright install --with-deps chromium`).
- The cache key includes `hashFiles('requirements.lock')` so Playwright version
  bumps (via the lock file) invalidate the cache (Pitfall 26).
- The Playwright install step runs AFTER `Install Python dependencies` — the
  `playwright` CLI is provided by the pip package, so dependencies must be
  installed first.
"""
from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "scan.yml"


def _load_workflow() -> dict:
    return yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_workflow_has_playwright_install_step():
    """Phase 3 — `playwright install --with-deps chromium` step must exist."""
    text = _WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "playwright install --with-deps chromium" in text


def test_workflow_cache_key_includes_requirements_lock():
    """Pitfall 26 — cache key MUST include hashFiles('requirements.lock')
    so Playwright version bumps via the lock file invalidate the cache.
    """
    text = _WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "hashFiles('requirements.lock')" in text
    # And the cache path must be the Playwright browser cache location.
    assert "~/.cache/ms-playwright" in text


def test_workflow_install_step_runs_after_dependency_install():
    """Ordering — `playwright install` runs AFTER `Install Python dependencies`.

    The `playwright` CLI is provided by the pip-installed `playwright` package;
    invoking it before pip-install would fail with command-not-found.
    """
    wf = _load_workflow()
    steps = wf["jobs"]["scan"]["steps"]
    names = [s.get("name") for s in steps]
    assert "Install Python dependencies" in names
    assert "Install Playwright browsers" in names
    deps_idx = names.index("Install Python dependencies")
    pw_idx = names.index("Install Playwright browsers")
    assert pw_idx > deps_idx, (
        f"Install Playwright browsers (idx={pw_idx}) must come AFTER "
        f"Install Python dependencies (idx={deps_idx})"
    )
