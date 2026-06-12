"""Tests for src/ai_classifier.py — 11 test cases covering all locked scenarios.

Uses respx to mock httpx calls. Mirror pattern from tests/test_filter.py.
"""
from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from src.ai_classifier import Classification, classify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _groq_ok_response(domain: str, is_early_career: bool) -> httpx.Response:
    """Build a mock Groq 200 response with the given classification."""
    content_json = json.dumps({"domain": domain, "is_early_career": is_early_career})
    body = {
        "choices": [
            {
                "message": {
                    "content": content_json,
                }
            }
        ]
    }
    return httpx.Response(200, json=body)


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_happy_path_ai_ml_early_career(monkeypatch):
    """Groq returns AI/ML + early_career=true → keep=True, domain='AI/ML'."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    with respx.mock:
        respx.post(_GROQ_URL).mock(return_value=_groq_ok_response("AI/ML", True))
        result = classify("Machine Learning Engineer", None)
    assert result.domain == "AI/ML"
    assert result.is_early_career is True
    assert result.keep is True
    assert result.reason == "ok"


def test_happy_path_swe_early_career(monkeypatch):
    """Groq returns SWE + early_career=true → keep=True, domain='SWE'."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    with respx.mock:
        respx.post(_GROQ_URL).mock(return_value=_groq_ok_response("SWE", True))
        result = classify("Software Engineer I", None)
    assert result.domain == "SWE"
    assert result.is_early_career is True
    assert result.keep is True
    assert result.reason == "ok"


def test_happy_path_data_science_early_career(monkeypatch):
    """Groq returns Data Science + early_career=true → keep=True, domain='Data Science'."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    with respx.mock:
        respx.post(_GROQ_URL).mock(return_value=_groq_ok_response("Data Science", True))
        result = classify("Data Scientist", None)
    assert result.domain == "Data Science"
    assert result.is_early_career is True
    assert result.keep is True
    assert result.reason == "ok"


# ---------------------------------------------------------------------------
# Rejection cases
# ---------------------------------------------------------------------------


def test_domain_other(monkeypatch):
    """Groq returns Other domain → keep=False; reason contains 'Other'."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    with respx.mock:
        respx.post(_GROQ_URL).mock(return_value=_groq_ok_response("Other", True))
        result = classify("Product Manager", None)
    assert result.domain == "Other"
    assert result.keep is False
    assert "Other" in result.reason


def test_not_early_career(monkeypatch):
    """Groq returns SWE + early_career=false → keep=False even though domain=SWE."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    with respx.mock:
        respx.post(_GROQ_URL).mock(return_value=_groq_ok_response("SWE", False))
        result = classify("Senior Software Engineer", None)
    assert result.domain == "SWE"
    assert result.is_early_career is False
    assert result.keep is False


# ---------------------------------------------------------------------------
# Soft-fail / error cases
# ---------------------------------------------------------------------------


def test_timeout(monkeypatch):
    """httpx.TimeoutException → keep=True, reason starts with 'error:'."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    with respx.mock:
        respx.post(_GROQ_URL).mock(side_effect=httpx.TimeoutException("timed out"))
        result = classify("Software Engineer", None)
    assert result.keep is True
    assert result.reason.startswith("error:")


def test_http_500(monkeypatch):
    """Groq returns HTTP 500 → keep=True, reason starts with 'error:'."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    with respx.mock:
        respx.post(_GROQ_URL).mock(return_value=httpx.Response(500))
        result = classify("Software Engineer", None)
    assert result.keep is True
    assert result.reason.startswith("error:")


def test_malformed_json(monkeypatch):
    """Groq returns non-JSON body with 200 → keep=True, reason starts with 'error:'."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    malformed_body = {
        "choices": [
            {
                "message": {
                    "content": "NOT JSON — sorry",
                }
            }
        ]
    }
    with respx.mock:
        respx.post(_GROQ_URL).mock(return_value=httpx.Response(200, json=malformed_body))
        result = classify("Software Engineer", None)
    assert result.keep is True
    assert result.reason.startswith("error:")


def test_missing_api_key(monkeypatch):
    """api_key=None, GROQ_API_KEY not in env → keep=True, reason='no-api-key', no HTTP call made."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with respx.mock as mock:
        result = classify("Software Engineer", None, api_key=None)
        # No HTTP call should have been made.
        assert mock.call_count == 0
    assert result.keep is True
    assert result.reason == "no-api-key"


# ---------------------------------------------------------------------------
# Truncation + security tests
# ---------------------------------------------------------------------------


def test_description_truncation_at_2000_chars(monkeypatch):
    """Description longer than 2000 chars is truncated before sending to Groq."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    long_description = "x" * 3000  # 3000 chars — should be capped at 2000

    with respx.mock:
        route = respx.post(_GROQ_URL).mock(
            return_value=_groq_ok_response("SWE", True)
        )
        classify("Engineer", long_description)
        # Inspect the request body sent to Groq.
        assert route.called
        request = route.calls[0].request
        request_body = json.loads(request.content)
        user_content = request_body["messages"][1]["content"]
        # The description portion should be capped at 2000 chars.
        # user_content = "Title: Engineer\n\nDescription:\n" + truncated_desc
        prefix = "Title: Engineer\n\nDescription:\n"
        assert user_content.startswith(prefix)
        desc_in_request = user_content[len(prefix):]
        assert len(desc_in_request) <= 2000


def test_never_logs_api_key(monkeypatch, caplog):
    """The bearer token value 'test-key-never-logs' must never appear in any log record."""
    api_key = "test-key-never-logs"
    monkeypatch.setenv("GROQ_API_KEY", api_key)

    with caplog.at_level(logging.DEBUG, logger="src.ai_classifier"):
        with respx.mock:
            # Trigger an error path so there's logging activity.
            respx.post(_GROQ_URL).mock(return_value=httpx.Response(500))
            classify("Software Engineer", None, api_key=api_key)

    # The key must never appear in any log message.
    assert api_key not in caplog.text
