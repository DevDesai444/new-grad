"""End-to-end pipeline test — the canonical Phase 1 acceptance gate per CONTEXT.md D-04.

Mocks Greenhouse via respx; walks companies.txt -> config_loader -> registry ->
GreenhouseAdapter -> normalizer -> filter -> state_merger -> save_state_atomic ->
render_readme. Asserts:
  - exit 0
  - seen.json well-formed (schema_version=1, contains the expected postings)
  - README has [Apply] links
  - A second consecutive run produces byte-identical seen.json AND byte-identical
    README (full-pipeline idempotency proof — augments OUT-07's unit-level proof)
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import orjson
import respx

from src.state_store import SCHEMA_VERSION

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "greenhouse_stripe.json"


def _setup_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create companies.txt, seen.json target, README.md with sentinels."""
    companies = tmp_path / "companies.txt"
    companies.write_text("https://boards.greenhouse.io/stripe\n")
    state = tmp_path / "seen.json"
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Test\n\nintro\n\n<!-- BEGIN JOBS -->\n"
        "(no matching postings yet)\n<!-- END JOBS -->\n\noutro\n"
    )
    return companies, state, readme


@respx.mock
def test_pipeline_first_run(tmp_path):
    """Full pipeline: respx-mocked Greenhouse -> seen.json + README populated."""
    from src.main import main

    fixture = json.loads(_FIXTURE_PATH.read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=fixture))

    companies, state, readme = _setup_repo(tmp_path)
    code = main(companies, state, readme)
    assert code == 0

    saved = orjson.loads(state.read_bytes())
    assert saved["schema_version"] == SCHEMA_VERSION

    # The fixture has 3 jobs: New Grad (kept), Senior Staff (filtered out),
    # Associate (kept). Both kept postings should be in seen.json.
    kept_titles = [r["title"] for r in saved["postings"].values()]
    assert any("New Grad" in t for t in kept_titles), \
        f"expected New Grad in {kept_titles}"
    assert any("Associate" in t for t in kept_titles), \
        f"expected Associate in {kept_titles}"
    assert not any("Senior" in t for t in kept_titles), \
        f"Senior should be filtered out, got {kept_titles}"

    # All kept postings should have still_listed=True and a source_adapter.
    for rec in saved["postings"].values():
        assert rec["still_listed"] is True
        assert rec["source_adapter"] == "greenhouse"

    readme_content = readme.read_text()
    # OUT-03 — each kept posting renders an [Apply] link.
    assert "[Apply](https://boards.greenhouse.io/stripe/jobs/" in readme_content
    # Sentinels are still in place — renderer must not nuke the user-authored frame.
    assert "<!-- BEGIN JOBS -->" in readme_content
    assert "<!-- END JOBS -->" in readme_content


@respx.mock
def test_pipeline_idempotent_second_run(tmp_path, monkeypatch):
    """Two consecutive runs at the same logical instant -> byte-identical outputs.

    This augments OUT-07's unit-level idempotency proof by walking the FULL
    pipeline (fetch -> normalize -> filter -> merge -> save -> render) twice
    under a frozen clock and asserting byte-equal seen.json + byte-equal README.

    The clock is frozen by monkey-patching `datetime` in the src.main module
    namespace — that's the only module that calls `datetime.now()`; all
    downstream functions accept run_started_at as a parameter (RUN-01).
    """
    import src.main as main_mod

    fixed_now = datetime(2026, 6, 7, 14, 0, 0, tzinfo=UTC)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    fixture = json.loads(_FIXTURE_PATH.read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=fixture))

    companies, state, readme = _setup_repo(tmp_path)

    monkeypatch.setattr(main_mod, "datetime", _FrozenDateTime)

    code1 = main_mod.main(companies, state, readme)
    seen_after_run1 = state.read_bytes()
    readme_after_run1 = readme.read_bytes()

    code2 = main_mod.main(companies, state, readme)
    seen_after_run2 = state.read_bytes()
    readme_after_run2 = readme.read_bytes()

    assert code1 == 0 and code2 == 0
    assert seen_after_run1 == seen_after_run2, \
        "seen.json must be byte-identical on idempotent second run"
    assert readme_after_run1 == readme_after_run2, \
        "README.md must be byte-identical on idempotent second run"


@respx.mock
def test_pipeline_persists_keys_across_runs(tmp_path, monkeypatch):
    """STATE-04 — keys are never deleted. Re-running on the same fixture
    keeps the same set of dedup_keys in seen.json.
    """
    import src.main as main_mod

    fixed_now = datetime(2026, 6, 7, 14, 0, 0, tzinfo=UTC)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    fixture = json.loads(_FIXTURE_PATH.read_text())
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=fixture))

    companies, state, readme = _setup_repo(tmp_path)
    monkeypatch.setattr(main_mod, "datetime", _FrozenDateTime)

    main_mod.main(companies, state, readme)
    keys_run1 = set(orjson.loads(state.read_bytes())["postings"].keys())

    main_mod.main(companies, state, readme)
    keys_run2 = set(orjson.loads(state.read_bytes())["postings"].keys())

    assert keys_run1 == keys_run2, "STATE-04 — keys must be preserved across runs"
    # Both kept postings should be present (New Grad + Associate from fixture).
    assert any("4567890" in k for k in keys_run1)  # New Grad
    assert any("4567892" in k for k in keys_run1)  # Associate
