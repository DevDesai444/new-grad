"""Orchestrator (src.main) unit tests.

Covers ADP-12 per-company isolation, RUN-01 single-clock discipline,
RUN-02 summary emission, sanity-gate routing (SiteBlocked carve-out + abort
path with state preserved), Pitfall 17 logging discipline.
"""
from __future__ import annotations

from typing import ClassVar

import orjson

from src.adapters.base import Adapter, InvalidCredential, SiteBlocked
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


# --- Phase 3 Plan 03-01 — resolve_url wiring (CONTEXT.md D-01b) ---------------


def test_main_loop_calls_resolve_url_per_company(tmp_path, monkeypatch):
    """D-01b — orchestrator must call resolve_url(company.url) for each
    company before dispatching to the adapter. The returned resolved URL
    must be assigned to company.resolved_url so the registry sees it.
    """
    from src import main as main_mod
    from src import registry as reg

    # Track every call resolve_url received + the company that triggered it.
    seen_urls: list[str] = []

    def fake_resolve_url(url: str, timeout_s: float = 5.0) -> str:
        seen_urls.append(url)
        # Simulate the CNAME→Workday redirect for amd, identity for the other.
        if "careers.amd.com" in url:
            return "https://amd.wd1.myworkdayjobs.com/External"
        return url

    monkeypatch.setattr(main_mod, "resolve_url", fake_resolve_url)
    # Only the _OkAdapter is registered — we don't care which dispatches,
    # just that resolve_url got called for each company.
    monkeypatch.setattr(reg, "ADAPTERS", [_OkAdapter])

    cfg = _setup_companies(
        tmp_path,
        ("https://ok.example/co1", None),
        ("https://careers.amd.com/", None),
    )
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0
    # resolve_url called exactly twice — once per company.
    assert seen_urls == [
        "https://ok.example/co1",
        "https://careers.amd.com/",
    ]


# --- Phase 3 Plan 03-03 — InvalidCredential per-company isolation (D-02c) ----


class _InvalidCredentialAdapter(Adapter):
    """Synthetic adapter that always raises InvalidCredential.

    Plan 03-03 — the orchestrator's _scrape_one catch tuple is extended to
    include InvalidCredential so a credential-rejection on one company never
    aborts the rest of the run (ADP-12 per-company isolation preserved).
    """

    name: ClassVar[str] = "bad_creds"

    @classmethod
    def matches(cls, url):
        return "bad-creds.example" in url

    def fetch(self, company):
        raise InvalidCredential(
            f"Playwright {company.name}: login form still present after submit"
        )


def test_orchestrator_isolates_invalid_credential(tmp_path, monkeypatch):
    """Plan 03-03 — one company raises InvalidCredential; the other still
    produces a posting. Outcome for the failing company is `error: InvalidCredential`.
    """
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(
        reg, "ADAPTERS", [_OkAdapter, _InvalidCredentialAdapter]
    )
    cfg = _setup_companies(
        tmp_path,
        ("https://ok.example/co-ok", None),
        ("https://bad-creds.example/co-bad", None),
    )
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    # ADP-12 — credential failure of one company never causes non-zero exit.
    assert code == 0
    saved = orjson.loads(state.read_bytes())
    keys = list(saved["postings"].keys())
    # The OK company landed a posting.
    assert any("co-ok" in k for k in keys), f"expected ok posting, got {keys}"
    # The bad-creds company contributed nothing.
    assert not any("co-bad" in k for k in keys)


# --- Phase 4 Plan 04-02 — FILT-07 US-only region filter wiring (D-03 / D-03a) -


class _TwoCityAdapter(Adapter):
    """Synthetic adapter returning two postings — one US, one non-US.

    Both pass `is_early_career` (title="Software Engineer, New Grad"). Phase 4
    Plan 04-02's FILT-07 must drop the London posting while keeping the SF one.
    Uses source_adapter="greenhouse" so the existing _normalize_greenhouse
    dispatcher handles the tolerant raw shape — saves registering a new
    dispatch arm just for the test.
    """

    name: ClassVar[str] = "twocity"

    @classmethod
    def matches(cls, url):
        return "twocity.example" in url

    def fetch(self, company: CompanyConfig):
        return [
            RawPosting(
                source_company=company.name,
                source_adapter="greenhouse",
                raw={
                    "id": 1,
                    "title": "Software Engineer, New Grad",
                    "updated_at": "2026-06-01T00:00:00Z",
                    "location": {"name": "San Francisco, CA"},
                    "absolute_url": f"https://x/{company.name}/sf",
                    "__dedup_key": f"gh:{company.name}:sf",
                    "__board_token": company.name,
                },
            ),
            RawPosting(
                source_company=company.name,
                source_adapter="greenhouse",
                raw={
                    "id": 2,
                    "title": "Software Engineer, New Grad",
                    "updated_at": "2026-06-01T00:00:00Z",
                    "location": {"name": "London, UK"},
                    "absolute_url": f"https://x/{company.name}/london",
                    "__dedup_key": f"gh:{company.name}:london",
                    "__board_token": company.name,
                },
            ),
        ]


def test_orchestrator_drops_non_us_postings_per_filt07(tmp_path, monkeypatch):
    """FILT-07 integration — London posting dropped, SF posting kept.

    Both postings pass the FILT-01/02 title-keyword gate ("New Grad"); the
    SF one passes FILT-07 (is_us_location returns True for "San Francisco, CA")
    while the London one fails (rule 6 — known non-US substring).
    """
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_TwoCityAdapter])
    cfg = _setup_companies(tmp_path, ("https://twocity.example/co", None))
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0

    saved = orjson.loads(state.read_bytes())
    keys = list(saved["postings"].keys())
    # SF posting kept (US per FILT-07).
    assert any(":sf" in k for k in keys), (
        f"expected SF posting key, got {keys}"
    )
    # London posting dropped (non-US per FILT-07) — must NOT appear in seen.json.
    assert not any(":london" in k for k in keys), (
        f"London posting should have been dropped by FILT-07, found in {keys}"
    )
    # And the rendered README must not link the London posting.
    readme_text = readme.read_text()
    assert "/london" not in readme_text, (
        "London posting URL leaked into README despite FILT-07 drop"
    )
    assert "/sf" in readme_text, "SF posting URL missing from README"


def test_orchestrator_filt07_drop_emits_info_log_line(
    tmp_path, monkeypatch, caplog
):
    """FILT-07 — dropped non-US postings get a logger.info line naming title + location.

    Makes the filter behavior visible in the Actions log so the user can verify
    "yes, the London Workday postings are being dropped on purpose" without
    instrumenting. The log line must include both title and location for clarity.
    """
    import logging

    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_TwoCityAdapter])
    cfg = _setup_companies(tmp_path, ("https://twocity.example/co", None))
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)

    with caplog.at_level(logging.INFO, logger="scan"):
        code = main_mod.main(cfg, state, readme)
    assert code == 0

    # Find the FILT-07 drop line.
    drop_lines = [
        rec.getMessage()
        for rec in caplog.records
        if "FILT-07" in rec.getMessage()
    ]
    assert len(drop_lines) >= 1, (
        f"expected ≥1 FILT-07 drop log line, got {[r.getMessage() for r in caplog.records]}"
    )
    # The drop line must name title + location for diagnostic clarity.
    london_drops = [m for m in drop_lines if "London" in m]
    assert len(london_drops) >= 1, (
        f"expected ≥1 FILT-07 drop line mentioning 'London', got {drop_lines}"
    )


def test_orchestrator_filt07_does_not_drop_us_postings(tmp_path, monkeypatch):
    """FILT-07 — a US-only company's postings all survive (regression guard).

    Re-runs the Phase 1 _OkAdapter pattern (SF posting) and asserts FILT-07
    leaves it untouched.
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
    # _OkAdapter posts location="SF" (rule 5 — known US city substring) → keep.
    assert len(saved["postings"]) == 1, (
        "US-only posting must survive FILT-07; got "
        f"{saved['postings']}"
    )


def test_main_loop_resolve_url_failure_continues_per_company_isolation(
    tmp_path, monkeypatch
):
    """Defense in depth — even though resolve_url's contract is no-raise,
    the orchestrator wraps it defensively. If a future bug causes a raise,
    the main loop logs + continues with the original URL (ADP-12 / Pitfall 1
    one-bad-line isolation discipline).
    """
    from src import main as main_mod
    from src import registry as reg

    def boom_resolve_url(url: str, timeout_s: float = 5.0) -> str:
        raise RuntimeError("simulated resolver crash")

    monkeypatch.setattr(main_mod, "resolve_url", boom_resolve_url)
    monkeypatch.setattr(reg, "ADAPTERS", [_OkAdapter])

    cfg = _setup_companies(tmp_path, ("https://ok.example/co", None))
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    # Orchestrator MUST tolerate the resolver crash (defense in depth).
    # Exit code 0 + the posting still lands (adapter dispatched on original URL).
    code = main_mod.main(cfg, state, readme)
    assert code == 0
    saved = orjson.loads(state.read_bytes())
    assert len(saved["postings"]) == 1


# --- Phase 4 Plan 04-03 — source_health end-to-end + doc invariant ------------


def test_orchestrator_writes_source_health_to_seen_json(tmp_path, monkeypatch):
    """Plan 04-03 D-04 / D-04d — orchestrator records per-company source_health
    after each adapter call. After main() runs with one OK + one Blocked adapter,
    on-disk seen.json carries:
      - schema_version: 2
      - source_health block with both companies' outcomes
      - OK company → status='ok', consecutive_failures=0
      - Blocked company → status='error' (1 failure < 3-fail threshold),
        consecutive_failures=1, last_success_utc=None
    """
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_OkAdapter, _BlockedAdapter])
    cfg = _setup_companies(
        tmp_path,
        ("https://ok.example/CompanyA", None),
        ("https://blocked.example/CompanyB", None),
    )
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0

    saved = orjson.loads(state.read_bytes())
    assert saved["schema_version"] == 2
    assert "source_health" in saved
    health = saved["source_health"]

    # Companies are named by the URL path segment per _setup_companies +
    # load_companies derivation; verify via stable substring matching to keep
    # the test resilient to companies.txt naming conventions.
    co_a_keys = [k for k in health if "companya" in k.lower()]
    co_b_keys = [k for k in health if "companyb" in k.lower()]
    assert len(co_a_keys) == 1, f"expected one CompanyA health entry, got {list(health.keys())}"
    assert len(co_b_keys) == 1, f"expected one CompanyB health entry, got {list(health.keys())}"

    a_entry = health[co_a_keys[0]]
    b_entry = health[co_b_keys[0]]

    # OK adapter — successful scrape.
    assert a_entry["status"] == "ok"
    assert a_entry["consecutive_failures"] == 0
    assert a_entry["last_success_utc"] is not None
    assert a_entry["last_attempt_utc"] == a_entry["last_success_utc"]

    # Blocked adapter — 1 failure (< 3 threshold) → status 'error', not 'blocked'.
    assert b_entry["status"] == "error", (
        f"1 failure should be 'error', not 'blocked' (3+ required). Got: {b_entry}"
    )
    assert b_entry["consecutive_failures"] == 1
    assert b_entry["last_success_utc"] is None
    assert b_entry["last_attempt_utc"] is not None


def test_orchestrator_source_health_accumulates_across_runs(tmp_path, monkeypatch):
    """D-04b — three consecutive blocked runs promote the company to 'blocked' status.

    Verifies the cross-run accumulation: each run reads the prior source_health
    block from seen.json, increments consecutive_failures, and after the 3rd run
    the status flips from 'error' (1-2 fails) to 'blocked' (3+ fails).
    """
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_BlockedAdapter])
    cfg = _setup_companies(tmp_path, ("https://blocked.example/StuckCo", None))
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)

    # Pre-seed seen.json with 100 prior entries so sanity gate doesn't fire on
    # the empty scrape. Use v2 (current SCHEMA_VERSION).
    prior = {
        "schema_version": 2,
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
        "source_health": {},
    }
    state.write_bytes(orjson.dumps(prior, option=orjson.OPT_SORT_KEYS))

    # Run 1 — 1 failure → status 'error', consecutive_failures=1
    assert main_mod.main(cfg, state, readme) == 0
    h = orjson.loads(state.read_bytes())["source_health"]
    co_keys = [k for k in h if "stuckco" in k.lower()]
    assert len(co_keys) == 1
    co = co_keys[0]
    assert h[co]["consecutive_failures"] == 1
    assert h[co]["status"] == "error"

    # Run 2 — 2 failures → still 'error'
    assert main_mod.main(cfg, state, readme) == 0
    h = orjson.loads(state.read_bytes())["source_health"]
    assert h[co]["consecutive_failures"] == 2
    assert h[co]["status"] == "error"

    # Run 3 — 3 failures → promoted to 'blocked'
    assert main_mod.main(cfg, state, readme) == 0
    h = orjson.loads(state.read_bytes())["source_health"]
    assert h[co]["consecutive_failures"] == 3
    assert h[co]["status"] == "blocked", (
        f"3 consecutive failures should promote to 'blocked'; got {h[co]}"
    )


def test_orchestrator_source_health_no_adapter_classified_as_error(tmp_path, monkeypatch):
    """D-04b — CFG-05 'no-adapter' outcome counts as a scan failure for health."""
    from src import main as main_mod
    from src import registry as reg

    # No adapters registered → every company gets NoAdapterFound (CFG-05 skip path).
    monkeypatch.setattr(reg, "ADAPTERS", [])
    cfg = _setup_companies(tmp_path, ("https://unknown.example/UnmappedCo", None))
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    code = main_mod.main(cfg, state, readme)
    assert code == 0

    saved = orjson.loads(state.read_bytes())
    co_keys = [k for k in saved["source_health"] if "unmappedco" in k.lower()]
    assert len(co_keys) == 1
    entry = saved["source_health"][co_keys[0]]
    assert entry["status"] == "error"
    assert entry["consecutive_failures"] == 1
    assert entry["last_success_utc"] is None


def test_orchestrator_source_health_not_rendered_in_readme(tmp_path, monkeypatch):
    """Plan 04-03 CONTEXT.md D-04c invariant — Source Health data IS persisted in
    seen.json but is NOT rendered in the README. The user explicitly does not
    want a health footer. This test guards against regression on that contract.
    """
    from src import main as main_mod
    from src import registry as reg

    monkeypatch.setattr(reg, "ADAPTERS", [_OkAdapter, _BlockedAdapter])
    cfg = _setup_companies(
        tmp_path,
        ("https://ok.example/HealthyCo", None),
        ("https://blocked.example/BrokenCo", None),
    )
    state = tmp_path / "seen.json"
    readme = _setup_readme(tmp_path)
    assert main_mod.main(cfg, state, readme) == 0

    readme_text = readme.read_text()
    # Footer section heading must not appear.
    assert "Source Health" not in readme_text, (
        "D-04c violated — README contains a 'Source Health' heading; the data "
        "is persisted in seen.json only, NOT rendered."
    )
    # HEALTH sentinels must not appear.
    assert "BEGIN HEALTH" not in readme_text
    assert "END HEALTH" not in readme_text
    # Per-company status strings must not appear in the README (they only
    # belong in seen.json.source_health). 'consecutive_failures' is the
    # most-unique invariant of the source_health record shape.
    assert "consecutive_failures" not in readme_text
    assert "last_attempt_utc" not in readme_text
    # But the data IS in seen.json — sanity check.
    saved = orjson.loads(state.read_bytes())
    assert "source_health" in saved
    assert len(saved["source_health"]) == 2


def test_out09_amended_with_strikethrough_in_requirements_md():
    """Doc invariant — Plan 04-03 CONTEXT.md D-04c requires REQUIREMENTS.md OUT-09
    to be amended with strikethrough + footnote pointing to D-04c. Mirrors the
    Phase 1 INFRA-05 and Phase 2 FILT-04 strikethrough pattern.
    """
    from pathlib import Path

    text = Path(".planning/REQUIREMENTS.md").read_text(encoding="utf-8")

    # Strikethrough marker present (mirrors FILT-04 / INFRA-05 style).
    assert "~~**OUT-09**~~" in text, (
        "OUT-09 missing strikethrough form '~~**OUT-09**~~' per CONTEXT.md D-04c"
    )
    # Footnote points to the persisted-not-rendered data location.
    assert "seen.json.source_health" in text, (
        "OUT-09 footnote missing reference to seen.json.source_health"
    )
    # Footnote uses the exact 'NOT rendered in the README' phrasing.
    assert "NOT rendered in the README" in text, (
        "OUT-09 footnote missing the literal 'NOT rendered in the README' phrasing "
        "(D-04c amendment text)"
    )
    # Traceability row marked Complete (not Pending).
    assert "| OUT-09 | Phase 4 | Complete |" in text, (
        "Traceability row for OUT-09 must read 'Complete' after Plan 04-03"
    )
    assert "| OUT-09 | Phase 4 | Pending |" not in text, (
        "Traceability row for OUT-09 still says 'Pending' — was the amendment applied?"
    )
