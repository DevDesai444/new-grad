"""companies.txt parser.

CFG-01: one URL per line.
CFG-02: blank lines + #-prefixed comments are skipped.
CFG-03: optional `#adapter=<name>` inline hint after the URL on the same line.
CFG-05: malformed lines are logged + skipped; the run continues.

Pitfall 21 mitigation: strip whitespace, strip UTF-8 BOM, support comments,
log + skip bad URLs (never raise — one bad line must not abort the whole file).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from src.models import CompanyConfig

logger = logging.getLogger(__name__)

# Matches `... #adapter=<value>` at end of line (after the URL portion). Captures
# the value. The value may contain alphanumerics, hyphens, underscores, dots,
# colons, equals signs, and commas — the colon + equals + comma combo is reserved
# for Phase 2's "adapter:metadata" form (e.g., `workday:tenant=foo,site=bar`).
# Note the loose whitespace around `#`, `adapter`, and `=` — generous to humans.
_ADAPTER_HINT_RE = re.compile(r"\s*#\s*adapter\s*=\s*([A-Za-z0-9_.:=,\-]+)\s*$")


def _derive_company_name(url: str) -> str:
    """Pick a stable display name from the URL.

    Order of preference:
    1. First non-empty path segment (e.g., `/stripe` -> "stripe",
       `/stripe/jobs/123` -> "stripe")
    2. Hostname's second-level domain (e.g., `boards.greenhouse.io` -> "greenhouse")
    3. Full hostname as a fallback
    """
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    if segments:
        return segments[0]
    host = parsed.hostname or "unknown"
    parts = host.split(".")
    if len(parts) >= 2:
        return parts[-2]
    return host


def _parse_line(line: str, line_num: int, source: Path) -> CompanyConfig | None:
    """Parse one non-blank, non-comment line into a CompanyConfig.

    Returns None on malformed input (logs the issue per CFG-05).
    """
    # Extract optional `#adapter=<name>` hint and strip from the URL portion.
    hint: str | None = None
    m = _ADAPTER_HINT_RE.search(line)
    if m:
        hint = m.group(1)
        line = line[: m.start()].rstrip()

    url = line.strip()
    if not url:
        return None

    # Pre-validate scheme so we get a clean log message rather than a Pydantic
    # ValidationError stack trace.
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        logger.warning(
            "config_loader: %s line %d: skipping unsupported URL scheme %r "
            "(only http/https are supported): %r",
            source, line_num, parsed.scheme, url,
        )
        return None
    if not parsed.netloc:
        logger.warning(
            "config_loader: %s line %d: skipping malformed URL (no host): %r",
            source, line_num, url,
        )
        return None

    name = _derive_company_name(url)
    try:
        return CompanyConfig(name=name, url=url, hint=hint)
    except ValidationError as e:
        logger.warning(
            "config_loader: %s line %d: CompanyConfig validation failed for %r: %s",
            source, line_num, url, e,
        )
        return None


def load_companies(path: Path = Path("companies.txt")) -> list[CompanyConfig]:
    """Parse companies.txt into a list of CompanyConfig.

    Skips blanks and comment lines per CFG-02. Logs + skips malformed lines per
    CFG-05. UTF-8 BOM at file start is silently consumed via the `utf-8-sig`
    codec (Pitfall 21 / 25). Missing file is treated as empty.
    """
    if not path.exists():
        logger.warning("config_loader: %s does not exist; returning []", path)
        return []

    # `utf-8-sig` silently strips the BOM if present (Pitfall 21 / 25).
    text = path.read_text(encoding="utf-8-sig")
    result: list[CompanyConfig] = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        # CFG-02 — skip blanks + #-comments.
        if not stripped or stripped.startswith("#"):
            continue
        cfg = _parse_line(raw_line, i, path)
        if cfg is not None:
            result.append(cfg)
    return result
