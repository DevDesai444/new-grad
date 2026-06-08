"""Unit tests for canonical data models.

Per CONTEXT.md (pure-core/impure-edges): models contain zero I/O. These tests
exercise pydantic v2 validation only — no network, no filesystem.
"""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models import CompanyConfig, Posting, RawPosting


def test_posting_happy_path():
    now = datetime.now(UTC)
    p = Posting(
        dedup_key="gh:stripe:1234567",
        company="Stripe",
        title="Software Engineer, New Grad",
        location="San Francisco, CA",
        salary=None,
        experience_min=None,
        experience_max=None,
        posting_url="https://boards.greenhouse.io/stripe/jobs/1234567",
        posted_date=None,
        first_seen=now,
        last_seen=now,
        still_listed=True,
        source_adapter="greenhouse",
    )
    assert p.dedup_key == "gh:stripe:1234567"
    assert p.still_listed is True
    assert p.source_adapter == "greenhouse"


def test_posting_requires_dedup_key():
    with pytest.raises(ValidationError):
        Posting(
            dedup_key="",  # empty violates min_length=1
            company="X",
            title="X",
            posting_url="https://x",
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            source_adapter="greenhouse",
        )


def test_posting_requires_first_seen():
    with pytest.raises(ValidationError):
        Posting(
            dedup_key="gh:x:1",
            company="X",
            title="X",
            posting_url="https://x",
            # first_seen missing
            last_seen=datetime.now(UTC),
            source_adapter="greenhouse",
        )


def test_posting_defaults_location_and_still_listed():
    now = datetime.now(UTC)
    p = Posting(
        dedup_key="gh:x:1",
        company="X",
        title="X",
        posting_url="https://x",
        first_seen=now,
        last_seen=now,
        source_adapter="greenhouse",
    )
    assert p.location == ""
    assert p.still_listed is True
    assert p.salary is None
    assert p.experience_min is None
    assert p.experience_max is None
    assert p.posted_date is None


def test_company_config_rejects_non_http_url():
    with pytest.raises(ValidationError):
        CompanyConfig(name="x", url="ftp://x.com")


def test_company_config_accepts_https_and_hint():
    c = CompanyConfig(
        name="stripe",
        url="https://boards.greenhouse.io/stripe",
        hint="greenhouse",
    )
    assert c.hint == "greenhouse"
    assert c.name == "stripe"


def test_company_config_accepts_http_scheme():
    # http:// is also valid per the validator (some intranet/staging URLs are http)
    c = CompanyConfig(name="x", url="http://example.com")
    assert c.url == "http://example.com"


def test_company_config_rejects_empty_name():
    with pytest.raises(ValidationError):
        CompanyConfig(name="", url="https://x.com")


def test_raw_posting_accepts_arbitrary_dict():
    r = RawPosting(
        source_company="stripe",
        source_adapter="greenhouse",
        raw={"id": 1, "title": "SWE"},
    )
    assert r.raw["id"] == 1
    assert r.source_adapter == "greenhouse"
