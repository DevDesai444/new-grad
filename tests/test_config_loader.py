"""Unit tests for src.config_loader — companies.txt parser.

Covers CFG-01 (one URL per line), CFG-02 (blanks + #-comments skipped),
CFG-03 (inline #adapter=<name> hint), CFG-05 (malformed lines logged + skipped),
and Pitfall 21 mitigations (BOM, whitespace, trailing comments).
"""
from __future__ import annotations

import logging

from src.config_loader import _derive_company_name, load_companies


def test_empty_file_returns_empty(tmp_path):
    p = tmp_path / "companies.txt"
    p.write_text("")
    assert load_companies(p) == []


def test_comments_only_file_returns_empty(tmp_path):
    p = tmp_path / "companies.txt"
    p.write_text("# header comment\n# another\n\n  # indented comment\n")
    assert load_companies(p) == []


def test_missing_file_returns_empty(tmp_path):
    assert load_companies(tmp_path / "absent.txt") == []


def test_single_greenhouse_url(tmp_path):
    p = tmp_path / "companies.txt"
    p.write_text("https://boards.greenhouse.io/stripe\n")
    out = load_companies(p)
    assert len(out) == 1
    assert out[0].url == "https://boards.greenhouse.io/stripe"
    assert out[0].name == "stripe"
    assert out[0].hint is None


def test_mixed_comments_blanks_and_urls(tmp_path):
    p = tmp_path / "companies.txt"
    p.write_text(
        "# Header\n"
        "\n"
        "https://boards.greenhouse.io/stripe\n"
        "\n"
        "# Anthropic (not yet supported in Phase 1)\n"
        "https://boards.greenhouse.io/notion\n"
    )
    out = load_companies(p)
    assert len(out) == 2
    assert {c.name for c in out} == {"stripe", "notion"}


def test_adapter_hint_parsed(tmp_path):
    p = tmp_path / "companies.txt"
    p.write_text("https://boards.greenhouse.io/stripe #adapter=greenhouse\n")
    out = load_companies(p)
    assert len(out) == 1
    assert out[0].hint == "greenhouse"
    assert out[0].url == "https://boards.greenhouse.io/stripe"


def test_adapter_hint_with_metadata(tmp_path):
    p = tmp_path / "companies.txt"
    p.write_text("https://x.example/jobs #adapter=workday:tenant=foo,site=bar\n")
    out = load_companies(p)
    assert len(out) == 1
    assert out[0].hint == "workday:tenant=foo,site=bar"


def test_adapter_hint_extra_spacing(tmp_path):
    """Loose spacing around `#adapter=` should still parse cleanly."""
    p = tmp_path / "companies.txt"
    p.write_text("https://boards.greenhouse.io/stripe   #  adapter = greenhouse  \n")
    out = load_companies(p)
    assert len(out) == 1
    assert out[0].hint == "greenhouse"


def test_invalid_scheme_skipped(tmp_path, caplog):
    p = tmp_path / "companies.txt"
    p.write_text("ftp://example.com/jobs\nhttps://boards.greenhouse.io/stripe\n")
    with caplog.at_level(logging.WARNING):
        out = load_companies(p)
    assert len(out) == 1
    assert out[0].name == "stripe"
    # The skipped line should have been logged.
    assert any("ftp" in r.getMessage() or "scheme" in r.getMessage() for r in caplog.records)


def test_malformed_url_skipped(tmp_path, caplog):
    p = tmp_path / "companies.txt"
    p.write_text("not-a-url\nhttps://boards.greenhouse.io/stripe\n")
    with caplog.at_level(logging.WARNING):
        out = load_companies(p)
    assert len(out) == 1
    # The malformed line should have been logged.
    assert any("not-a-url" in r.getMessage() or "malformed" in r.getMessage().lower()
               or "scheme" in r.getMessage().lower() for r in caplog.records)


def test_utf8_bom_consumed(tmp_path):
    p = tmp_path / "companies.txt"
    # ﻿ = UTF-8 BOM
    p.write_text("﻿https://boards.greenhouse.io/stripe\n", encoding="utf-8")
    out = load_companies(p)
    assert len(out) == 1
    # The URL must not retain a leading BOM character.
    assert out[0].url == "https://boards.greenhouse.io/stripe"


def test_trailing_whitespace_handled(tmp_path):
    p = tmp_path / "companies.txt"
    p.write_text("   https://boards.greenhouse.io/stripe   \n")
    out = load_companies(p)
    assert len(out) == 1
    assert out[0].url == "https://boards.greenhouse.io/stripe"


def test_run_continues_after_bad_line(tmp_path, caplog):
    """CFG-05 — one bad line must not abort parsing of the rest of the file."""
    p = tmp_path / "companies.txt"
    p.write_text(
        "https://boards.greenhouse.io/stripe\n"
        "ftp://bad.example/jobs\n"
        "not-a-url-at-all\n"
        "https://boards.greenhouse.io/notion\n"
    )
    with caplog.at_level(logging.WARNING):
        out = load_companies(p)
    assert len(out) == 2
    assert {c.name for c in out} == {"stripe", "notion"}


def test_placeholder_companies_txt_is_empty():
    """D-03 — the real companies.txt at the repo root parses to an empty list."""
    from pathlib import Path
    out = load_companies(Path("companies.txt"))
    assert out == []


def test_derive_name_from_greenhouse_url():
    assert _derive_company_name("https://boards.greenhouse.io/stripe") == "stripe"


def test_derive_name_from_url_with_jobs_segment():
    """The first path segment is the company; later segments are job IDs."""
    assert _derive_company_name("https://boards.greenhouse.io/stripe/jobs/123") == "stripe"


def test_derive_name_fallback_to_host():
    """No path segments — fall back to second-level domain of the host."""
    assert _derive_company_name("https://example.com/") == "example"
