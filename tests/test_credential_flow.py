"""Credential-flow integration + documentation tests (Phase 3 Plan 03-03).

Two clusters:

  1. Documentation invariants — CLAUDE.md "Adding a Company" 5-step flow
     (per CONTEXT.md D-03 + D-03a) and README.md SEC-06 "Credential Naming
     Convention" section. Tests are simple substring assertions; they
     guarantee future edits to these files preserve the canonical structure
     so future Claude CLI sessions follow the same workflow.

  2. Per-company isolation — confirms the orchestrator's _scrape_one path
     catches InvalidCredential alongside MissingCredential / SchemaDrift /
     PlaywrightTimeout (ADP-12 preserved). One company's credential
     rejection MUST NOT abort the rest of the run.

Why a separate file: these tests cross-cut multiple modules (CLAUDE.md +
README.md + main.py + adapter base) and don't belong with the per-adapter
unit tests. Plan 03-03 names this file `tests/test_credential_flow.py`.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import orjson

from src.adapters.base import Adapter, InvalidCredential
from src.models import RawPosting
from src.state_store import SCHEMA_VERSION

_CLAUDE_MD = Path("CLAUDE.md")
_README_MD = Path("README.md")


# ============================================================================
# CLAUDE.md — "Adding a Company" section (per CONTEXT.md D-03 + D-03a)
# ============================================================================


def test_claude_md_has_adding_a_company_section():
    """D-03 — CLAUDE.md must have a top-level `## Adding a Company` section."""
    text = _CLAUDE_MD.read_text()
    assert "## Adding a Company" in text, (
        "CLAUDE.md missing the `## Adding a Company` section"
    )


def test_claude_md_documents_gh_secret_set():
    """D-02 — CLAUDE.md must document the `gh secret set SCRAPER_*` command
    so future Claude CLI sessions provision credentials the same way.
    """
    text = _CLAUDE_MD.read_text()
    assert "gh secret set SCRAPER_" in text, (
        "CLAUDE.md must show the gh secret set SCRAPER_ command pattern"
    )


def test_claude_md_documents_5_step_flow():
    """D-03 — CLAUDE.md must document each of the 5 steps explicitly.

    Headings are checked as substrings (not regex anchors) to tolerate minor
    capitalisation drift in future edits while still catching whole-step
    deletion.
    """
    text = _CLAUDE_MD.read_text()
    steps = [
        "Step 1: Try existing adapters",
        "Step 2: Resolve redirects",
        "Step 3: Playwright catch-all",
        "Step 4: Write a new adapter",
        "Step 5: Credential branch",
    ]
    missing = [s for s in steps if s not in text]
    assert not missing, f"CLAUDE.md missing 5-step flow heading(s): {missing}"


def test_claude_md_documents_resolved_url_commit_per_d03a():
    """D-03a invariant — Step 2 commits the RESOLVED URL (not the original
    CNAME). CLAUDE.md must call this out so future flows don't silently
    revert to the original URL.
    """
    text = _CLAUDE_MD.read_text()
    # Accept either bold-markdown emphasis or the literal phrase "resolved URL".
    assert ("**resolved**" in text) or ("resolved URL" in text), (
        "CLAUDE.md Step 2 must emphasize that the RESOLVED URL is what "
        "gets committed to companies.txt (CONTEXT.md D-03a)"
    )


# ============================================================================
# README.md — "Credential Naming Convention (SEC-06)" section
# ============================================================================


def test_readme_has_credential_naming_section():
    """SEC-06 — README.md must have a Credential Naming Convention section."""
    text = _README_MD.read_text()
    assert "## Credential Naming Convention" in text, (
        "README.md missing the `## Credential Naming Convention` section"
    )


def test_readme_documents_scraper_naming_pattern():
    """SEC-02 / D-02a — README.md must document the SCRAPER_<COMPANY>_<KIND>
    naming pattern. Both `SCRAPER_<COMPANY>` (used as a prefix shorthand) and
    the full `SCRAPER_<COMPANY_UPPERCASE>_<KIND>` pattern must appear so users
    can reproduce the convention.
    """
    text = _README_MD.read_text()
    assert "SCRAPER_<COMPANY>" in text, (
        "README must reference the SCRAPER_<COMPANY> prefix shorthand"
    )
    assert "SCRAPER_<COMPANY_UPPERCASE>_<KIND>" in text, (
        "README must show the full SCRAPER_<COMPANY_UPPERCASE>_<KIND> pattern"
    )


def test_readme_lists_per_adapter_audit_table():
    """SEC-06 — README's per-adapter table lets users audit which adapters
    actually reference secrets. Every adapter name from src/registry.ADAPTERS
    must appear in the table.
    """
    text = _README_MD.read_text()
    adapters = [
        "greenhouse",
        "lever",
        "ashby",
        "smartrecruiters",
        "workday",
        "apple",
        "playwright",
    ]
    missing = [a for a in adapters if a not in text]
    assert not missing, (
        f"README SEC-06 audit table missing adapter row(s): {missing}"
    )


def test_readme_documents_gh_secret_list_audit():
    """SEC-04 — README must show the `gh secret list` audit command so the
    user can verify their secret inventory without ever displaying values.
    """
    text = _README_MD.read_text()
    assert "gh secret list --repo DevDesai444/new-grad" in text, (
        "README must show `gh secret list --repo DevDesai444/new-grad`"
    )


def test_readme_documents_sec04_names_only():
    """SEC-04 — README must explicitly note that `gh secret list` shows
    NAMES ONLY, never values. This is the central SEC-04 invariant.
    """
    text = _README_MD.read_text()
    # Accept either phrasing — "names only" or "never values" — both encode
    # the SEC-04 invariant equivalently.
    assert ("names only" in text) or ("never values" in text), (
        "README must call out that gh secret list shows names only / "
        "never values (SEC-04 invariant)"
    )


# ============================================================================
# Per-company isolation — orchestrator must catch InvalidCredential
# alongside the Phase 1 typed errors (ADP-12 preserved through Plan 03-03)
# ============================================================================


class _OkAdapter(Adapter):
    """Mock adapter for the green company — emits a single posting."""

    name: ClassVar[str] = "ok"

    @classmethod
    def matches(cls, url):
        return "ok.example" in url

    def fetch(self, company):
        return [
            RawPosting(
                source_company=company.name,
                source_adapter="greenhouse",
                raw={
                    "id": 1,
                    "title": "Software Engineer, New Grad",
                    "updated_at": "2026-06-01T00:00:00Z",
                    "location": {"name": "SF"},
                    "absolute_url": f"https://x/{company.name}/1",
                    "__dedup_key": f"gh:{company.name}:1",
                    "__board_token": company.name,
                },
            )
        ]


class _InvalidCredentialAdapter(Adapter):
    """Mock credentialed adapter that ALWAYS raises InvalidCredential."""

    name: ClassVar[str] = "invalid_creds"

    @classmethod
    def matches(cls, url):
        return "badcreds.example" in url

    def fetch(self, company):
        raise InvalidCredential(
            f"Playwright {company.name}: login form still present after submit "
            "(wrong credentials, anti-bot challenge, or selector drift)"
        )


def _setup_companies(tmp_path, *urls_with_hints):
    """urls_with_hints: tuples of (url, hint_or_None)."""
    p = tmp_path / "companies.txt"
    lines = []
    for url, hint in urls_with_hints:
        line = url
        if hint:
            line += f"  #adapter={hint}"
        lines.append(line)
    p.write_text(("\n".join(lines) + "\n") if lines else "")
    return p


def _setup_readme(tmp_path):
    p = tmp_path / "README.md"
    p.write_text(
        "intro\n\n<!-- BEGIN JOBS -->\nold\n<!-- END JOBS -->\n\noutro\n"
    )
    return p


def test_orchestrator_isolates_invalid_credential_per_company(
    tmp_path, monkeypatch
):
    """ADP-12 + Plan 03-03 — companies.txt has three entries: two OK + one
    that raises InvalidCredential. Run completes with exit 0; the two OK
    companies' postings land; the invalid-cred company contributes nothing.

    The bare contract: one company's credential rejection is logged + isolated;
    the rest of the scan continues uninterrupted.
    """
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(
        reg, "ADAPTERS", [_OkAdapter, _InvalidCredentialAdapter]
    )
    cfg = _setup_companies(
        tmp_path,
        ("https://ok.example/co-1", None),
        ("https://badcreds.example/co-2", None),
        ("https://ok.example/co-3", None),
    )
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    # ADP-12 — one company's credential rejection MUST NOT cause non-zero exit.
    assert code == 0
    saved = orjson.loads(state.read_bytes())
    assert saved["schema_version"] == SCHEMA_VERSION
    keys = list(saved["postings"].keys())
    # Both OK companies landed postings.
    assert any("co-1" in k for k in keys), keys
    assert any("co-3" in k for k in keys), keys
    # The bad-creds company contributed nothing — not in seen.json.
    assert not any("co-2" in k for k in keys), keys
