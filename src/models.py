"""Canonical data models for the new-grad pipeline.

Per ARCHITECTURE.md §Concrete Data Shapes:
- RawPosting: adapter output, pre-normalize, holds the source-specific blob.
- Posting: canonical post-normalize shape, what the renderer consumes.
- CompanyConfig: companies.txt parse output.

Per CONTEXT.md (pure-core / impure-edges pattern): these models contain ZERO I/O
and ZERO datetime.now() calls. The orchestrator (main.py) is the only module
that calls datetime.now(timezone.utc) and threads run_started_at through.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CompanyConfig(BaseModel):
    """Parsed entry from companies.txt."""

    name: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    hint: str | None = None
    # Phase 3 Plan 03-01 (CONTEXT.md D-01b): populated by the orchestrator after
    # url_resolver.resolve_url(); downstream adapters read `company.resolved_url
    # or company.url`. Optional + default None preserves Phase 1/2 call sites
    # that don't set it. Additive change — no migration needed.
    resolved_url: str | None = None

    @field_validator("url")
    @classmethod
    def _validate_url_scheme(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"URL must start with http:// or https:// (got: {v})")
        return v


class RawPosting(BaseModel):
    """Adapter output — pre-normalize. `raw` shape depends on `source_adapter`."""

    source_company: str
    source_adapter: str  # "greenhouse" | "lever" | ... (matches Adapter.name)
    raw: dict


class Posting(BaseModel):
    """Canonical Posting — what the renderer reads, what state_merger persists.

    Field set is locked per REQUIREMENTS.md NORM-01:
    dedup_key, company, title, location, salary, experience_min, experience_max,
    posting_url, posted_date, first_seen, last_seen, still_listed, source_adapter.
    """

    dedup_key: str = Field(..., min_length=1)  # e.g., "gh:stripe:1234567"
    company: str = Field(..., min_length=1)
    title: str
    location: str = ""  # may be empty; renderer handles empties (OUT-08)
    salary: str | None = None  # raw string; NORM-02 will normalize in Phase 4
    experience_min: int | None = None
    experience_max: int | None = None
    posting_url: str = Field(..., min_length=1)  # already canonicalized by normalizer
    posted_date: datetime | None = None  # UTC ISO-8601 if exposed by source
    first_seen: datetime  # assigned by state_merger from run_started_at
    last_seen: datetime
    still_listed: bool = True
    source_adapter: str = Field(..., min_length=1)
