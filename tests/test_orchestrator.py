"""Orchestrator (src.main) unit tests.

Covers ADP-12 per-company isolation, RUN-01 single-clock discipline,
RUN-02 summary emission, sanity-gate routing (SiteBlocked carve-out + abort
path with state preserved), Pitfall 17 logging discipline.
"""
from __future__ import annotations

from typing import ClassVar

import orjson

from src.adapters.base import Adapter, SiteBlocked
from src.models import CompanyConfig, RawPosting
from src.state_store import SCHEMA_VERSION

# ----------------------------- Mock adapters -----------------------------


class _OkAdapter(Adapter):
    name: ClassVar[str] = "ok"

    @classmethod
    def matches(cls, url):
        return "ok.example" in url

    def fetch(self, company: CompanyConfig):
        # Use source_adapter="greenhouse" so normalizer._DISPATCH dispatches.
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


class _RaisingAdapter(Adapter):
    name: ClassVar[str] = "raise"

    @classmethod
    def matches(cls, url):
        return "raise.example" in url

    def fetch(self, company):
        raise RuntimeError("boom")


class _BlockedAdapter(Adapter):
    name: ClassVar[str] = "blocked"

    @classmethod
    def matches(cls, url):
        return "blocked.example" in url

    def fetch(self, company):
        raise SiteBlocked("test")


# ----------------------------- Helpers -----------------------------


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


# ----------------------------- Tests -----------------------------


def test_empty_companies_exits_zero(tmp_path):
    from src import main as main_mod

    cfg = _setup_companies(tmp_path)  # empty
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0
    # No prior, no fresh -> empty merged.
    saved = orjson.loads(state.read_bytes())
    assert saved["postings"] == {}
    assert "no matching postings yet" in readme.read_text()


def test_one_working_adapter_produces_posting(tmp_path, monkeypatch):
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_OkAdapter])
    cfg = _setup_companies(tmp_path, ("https://ok.example/co", None))
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0
    saved = orjson.loads(state.read_bytes())
    assert saved["schema_version"] == SCHEMA_VERSION
    assert len(saved["postings"]) == 1
    rec = next(iter(saved["postings"].values()))
    assert "New Grad" in rec["title"]
    # README should have an [Apply] link for the kept posting.
    assert "[Apply]" in readme.read_text()


def test_per_company_isolation_one_raises(tmp_path, monkeypatch):
    """ADP-12 — one company raises RuntimeError; the other still produces a posting."""
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_OkAdapter, _RaisingAdapter])
    cfg = _setup_companies(
        tmp_path,
        ("https://ok.example/co-ok", None),
        ("https://raise.example/co-raise", None),
    )
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0  # ADP-12 — failure of one company never causes non-zero exit
    saved = orjson.loads(state.read_bytes())
    keys = list(saved["postings"].keys())
    assert any("co-ok" in k for k in keys), f"expected ok posting key, got {keys}"
    # The raising company contributed nothing — it's not in seen.json.
    assert not any("co-raise" in k for k in keys)


def test_site_blocked_bypasses_sanity_gate(tmp_path, monkeypatch):
    """When SiteBlocked is raised, sanity gate is excused even when new_count << prior_count."""
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_BlockedAdapter])
    # Pre-populate seen.json with 100 prior entries.
    prior = {
        "schema_version": SCHEMA_VERSION,
        "last_run_utc": "2026-05-01T00:00:00+00:00",
        "postings": {
            f"gh:x:{i}": {
                "still_listed": True,
                "first_seen": "2026-05-01T00:00:00+00:00",
                "last_seen": "2026-05-01T00:00:00+00:00",
                "company": "X",
                "title": "Engineer",
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": f"https://x/{i}",
                "posted_date": None,
                "source_adapter": "greenhouse",
            }
            for i in range(100)
        },
    }
    state = tmp_path / "seen.json"
    state.write_bytes(orjson.dumps(prior, option=orjson.OPT_SORT_KEYS))
    cfg = _setup_companies(tmp_path, ("https://blocked.example/x", None))
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0  # any_blocked excuses the gate


def test_sanity_gate_fires_without_blocked(tmp_path, monkeypatch):
    """Without any blocked outcome, mass loss triggers SanityGateAborted -> exit 1.

    Critical: state file MUST NOT be overwritten on abort (T-03-02 mitigation).
    """
    from src import main as main_mod
    from src import registry as reg

    # No adapters -> every company gets NoAdapterFound (CFG-05 skip, not "blocked").
    monkeypatch.setattr(reg, "ADAPTERS", [])
    prior = {
        "schema_version": SCHEMA_VERSION,
        "last_run_utc": "2026-05-01T00:00:00+00:00",
        "postings": {
            f"gh:x:{i}": {
                "still_listed": True,
                "first_seen": "2026-05-01T00:00:00+00:00",
                "last_seen": "2026-05-01T00:00:00+00:00",
                "company": "X",
                "title": "Engineer",
                "location": "",
                "salary": None,
                "experience_min": None,
                "experience_max": None,
                "posting_url": f"https://x/{i}",
                "posted_date": None,
                "source_adapter": "greenhouse",
            }
            for i in range(100)
        },
    }
    state = tmp_path / "seen.json"
    state.write_bytes(orjson.dumps(prior, option=orjson.OPT_SORT_KEYS))
    before_bytes = state.read_bytes()
    cfg = _setup_companies(tmp_path, ("https://unknown.example/x", None))
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 1  # SanityGateAborted
    # T-03-02 — state must NOT be overwritten when sanity gate fires.
    after_bytes = state.read_bytes()
    assert before_bytes == after_bytes, "state must not be overwritten when sanity gate fires"


def test_step_summary_written_when_env_set(tmp_path, monkeypatch):
    """RUN-02 — when $GITHUB_STEP_SUMMARY is set, summary is appended there."""
    from src import main as main_mod

    summary_file = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    cfg = _setup_companies(tmp_path)
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    main_mod.main(cfg, state, readme)
    assert summary_file.exists()
    content = summary_file.read_text()
    assert "Scan summary" in content
    assert "total open" in content


def test_summary_printed_to_stdout(tmp_path, capsys):
    """RUN-02 — summary is also printed to stdout even when env var is unset."""
    from src import main as main_mod

    cfg = _setup_companies(tmp_path)
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    main_mod.main(cfg, state, readme)
    captured = capsys.readouterr()
    assert "Scan summary" in captured.out


def test_unknown_schema_returns_exit_2(tmp_path):
    """STATE-08 / T-03-05 — UnknownSchemaVersion on load_state -> exit 2."""
    from src import main as main_mod

    state = tmp_path / "seen.json"
    state.write_bytes(orjson.dumps({"schema_version": 999, "postings": {}}))
    cfg = _setup_companies(tmp_path)
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 2


def test_no_adapter_found_does_not_abort_run(tmp_path, monkeypatch):
    """CFG-05 — NoAdapterFound for one company is logged + skipped; run continues."""
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_OkAdapter])
    cfg = _setup_companies(
        tmp_path,
        ("https://ok.example/co-ok", None),
        ("https://unknown.example/co-unknown", None),  # no adapter matches
    )
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0
    saved = orjson.loads(state.read_bytes())
    # ok-co posting present; unknown company contributed nothing.
    keys = list(saved["postings"].keys())
    assert any("co-ok" in k for k in keys)
    assert not any("co-unknown" in k for k in keys)


def test_run_started_at_threaded_consistently(tmp_path, monkeypatch):
    """RUN-01 — first_seen / last_seen on a freshly inserted record equal the
    single run_started_at, not two different datetime.now() calls.
    """
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_OkAdapter])
    cfg = _setup_companies(tmp_path, ("https://ok.example/co", None))
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0
    saved = orjson.loads(state.read_bytes())
    rec = next(iter(saved["postings"].values()))
    # first_seen and last_seen should match exactly on initial insert.
    assert rec["first_seen"] == rec["last_seen"]
    # And both should match last_run_utc.
    assert rec["first_seen"] == saved["last_run_utc"]
