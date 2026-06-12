"""Groq-backed domain + early-career classifier.

classify() is the only public API. Returns a Classification dataclass.
NEVER raises — all failures return keep=True (soft-fail per FILT-05 bias philosophy).
NEVER logs the API key. NEVER logs raw response bodies.

Model: llama-3.3-70b-versatile via Groq's OpenAI-compatible endpoint.
Uses httpx (already in requirements.txt) — no new dep.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.3-70b-versatile"
_DESCRIPTION_CHAR_CAP = 2000

_SYSTEM_PROMPT = (  # noqa: E501
    "You are a job-posting classifier. Given a job title and description,"
    " output ONLY a JSON object with exactly two keys:\n"
    '- "domain": one of "AI/ML", "SWE", "Data Science", or "Other"\n'
    '  - "AI/ML": machine learning, deep learning, LLMs, MLOps,'
    " computer vision, NLP, AI research, AI infrastructure\n"
    '  - "SWE": software engineering, backend, frontend, full-stack,'
    " mobile, DevOps, platform, infra (non-AI), security engineering, systems\n"
    '  - "Data Science": data analysis, data science, business intelligence,'
    " analytics engineering, data engineering (non-ML pipelines)\n"
    '  - "Other": product management, design, sales, marketing, legal, HR,'
    " finance, recruiting, operations, program management,"
    " or anything not clearly SWE/AI/DS\n"
    '- "is_early_career": true if the role is appropriate for 0-5 years'
    " of experience (new grad, junior, associate, entry-level), false otherwise\n"
    "  - When ambiguous (no experience requirement stated), bias toward true (inclusive).\n"
    "  - is_early_career=false only when the posting clearly requires 5+ years"
    " or uses senior/staff/principal/lead in a non-ironic way.\n"
    "\n"
    'Output exactly: {"domain": "<value>", "is_early_career": <true|false>}\n'
    "No explanation. No markdown. No extra keys."
)

_VALID_DOMAINS = {"AI/ML", "SWE", "Data Science", "Other"}


@dataclass(frozen=True)
class Classification:
    domain: str
    is_early_career: bool
    keep: bool
    reason: str


def classify(
    title: str,
    description: str | None,
    *,
    api_key: str | None = None,
    timeout: float = 8.0,
) -> Classification:
    """Classify a posting. NEVER raises.

    Returns Classification with keep=True on any error (soft-fail).
    api_key defaults to os.environ["GROQ_API_KEY"]; absent -> keep=True, reason="no-api-key".
    """
    resolved_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY")
    if not resolved_key:
        logger.warning("ai_classifier: GROQ_API_KEY not set -- soft-failing keep=True")
        return Classification(
            domain="unknown", is_early_career=True, keep=True, reason="no-api-key"
        )

    truncated_desc = (description or "")[:_DESCRIPTION_CHAR_CAP]
    user_content = f"Title: {title}\n\nDescription:\n{truncated_desc}"

    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 100,
    }
    headers = {
        "Authorization": f"Bearer {resolved_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(_GROQ_ENDPOINT, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.warning(
                "ai_classifier: Groq returned HTTP %d for title=%r -- soft-failing keep=True",
                resp.status_code,
                title,
            )
            return Classification(
                domain="unknown",
                is_early_career=True,
                keep=True,
                reason=f"error:HTTP{resp.status_code}",
            )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        domain = parsed["domain"]
        is_early = bool(parsed["is_early_career"])
    except (KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "ai_classifier: malformed Groq response for title=%r (%s) -- soft-failing keep=True",
            title,
            type(e).__name__,
        )
        return Classification(
            domain="unknown",
            is_early_career=True,
            keep=True,
            reason=f"error:{type(e).__name__}",
        )
    except Exception as e:  # noqa: BLE001
        # Catches httpx.TimeoutException, httpx.ConnectError, any other httpx error.
        # NEVER log the exception value -- it may contain request headers (Authorization).
        logger.warning(
            "ai_classifier: %s for title=%r -- soft-failing keep=True",
            type(e).__name__,
            title,
        )
        return Classification(
            domain="unknown",
            is_early_career=True,
            keep=True,
            reason=f"error:{type(e).__name__}",
        )

    if domain not in _VALID_DOMAINS:
        logger.warning(
            "ai_classifier: unexpected domain %r for title=%r -- soft-failing keep=True",
            domain,
            title,
        )
        return Classification(
            domain=domain,
            is_early_career=is_early,
            keep=True,
            reason=f"error:UnknownDomain:{domain}",
        )

    keep = domain in {"AI/ML", "SWE", "Data Science"} and is_early
    if keep:
        reason = "ok"
    else:
        reason = f"domain={domain}"
    return Classification(domain=domain, is_early_career=is_early, keep=keep, reason=reason)
