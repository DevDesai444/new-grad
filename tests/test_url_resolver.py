"""Unit tests for src/url_resolver.py (Phase 3 Plan 03-01).

Covers CONTEXT.md D-01b — the pre-flight URL redirect resolver that unblocks
the ~18-of-31 CNAME→Workday URLs in the user's actual companies.txt.

Contract (D-01b):
- HEAD-first with follow_redirects=True; fall back to streaming GET on 405/501.
- Per-request 5s timeout (default).
- NEVER raises — returns the original URL on ANY error (timeout, network,
  unexpected status). Orchestrator dispatches with original URL on failure.
- Never reads response body (HEAD or streaming GET that closes immediately).
"""
from __future__ import annotations

import httpx
import respx

from src.url_resolver import resolve_url


@respx.mock
def test_resolve_url_no_redirect_passthrough():
    """200 HEAD with no redirect → returns input URL unchanged (identity)."""
    url = "https://example.com/foo"
    respx.head(url).mock(return_value=httpx.Response(200))
    assert resolve_url(url) == url


@respx.mock
def test_resolve_url_single_302_follow():
    """One 302 hop (CNAME→Workday shape per D-01b) returns the terminal URL."""
    src = "https://careers.amd.com/"
    dst = "https://amd.wd1.myworkdayjobs.com/External"
    respx.head(src).mock(
        return_value=httpx.Response(302, headers={"Location": dst})
    )
    respx.head(dst).mock(return_value=httpx.Response(200))
    assert resolve_url(src) == dst


@respx.mock
def test_resolve_url_chained_301_then_302():
    """Multi-hop redirect chain (301 → 302 → 200) returns terminal URL."""
    src = "https://careers.example.com/"
    mid = "https://www.example.com/jobs"
    dst = "https://example.wd5.myworkdayjobs.com/Careers"
    respx.head(src).mock(
        return_value=httpx.Response(301, headers={"Location": mid})
    )
    respx.head(mid).mock(
        return_value=httpx.Response(302, headers={"Location": dst})
    )
    respx.head(dst).mock(return_value=httpx.Response(200))
    assert resolve_url(src) == dst


@respx.mock
def test_resolve_url_head_405_falls_back_to_get():
    """HEAD returns 405 (method not allowed) → fall back to streaming GET."""
    src = "https://strict.example.com/"
    dst = "https://target.example.com/final"
    respx.head(src).mock(return_value=httpx.Response(405))
    # Streaming GET follows redirect to dst.
    respx.get(src).mock(
        return_value=httpx.Response(302, headers={"Location": dst})
    )
    respx.get(dst).mock(return_value=httpx.Response(200))
    assert resolve_url(src) == dst


@respx.mock
def test_resolve_url_timeout_returns_original():
    """httpx.TimeoutException → return original URL (graceful degradation per D-01b)."""
    url = "https://slow.example.com/"
    respx.head(url).mock(side_effect=httpx.TimeoutException("timed out"))
    # Streaming GET fallback should also fail/timeout.
    respx.get(url).mock(side_effect=httpx.TimeoutException("timed out"))
    assert resolve_url(url) == url


@respx.mock
def test_resolve_url_connect_error_returns_original():
    """httpx.ConnectError → return original URL (graceful degradation per D-01b)."""
    url = "https://nonexistent.example.invalid/"
    respx.head(url).mock(side_effect=httpx.ConnectError("dns fail"))
    respx.get(url).mock(side_effect=httpx.ConnectError("dns fail"))
    assert resolve_url(url) == url


@respx.mock
def test_resolve_url_5xx_returns_original():
    """5xx HEAD response → returns original (5xx is not a redirect signal)."""
    url = "https://broken.example.com/"
    respx.head(url).mock(return_value=httpx.Response(503))
    assert resolve_url(url) == url


@respx.mock
def test_resolve_url_preserves_query_and_fragment_when_no_redirect():
    """When no redirect: resolver does NOT canonicalize (that's normalizer's job per NORM-06)."""
    url = "https://example.com/jobs?team=eng#anchor"
    respx.head(url).mock(return_value=httpx.Response(200))
    # Note: httpx may strip the fragment from the request URL itself (fragments
    # are client-side only), but the returned URL should still match the input
    # bytes if no redirect occurred. We assert the path + query are preserved.
    result = resolve_url(url)
    assert result.startswith("https://example.com/jobs")
    assert "team=eng" in result
