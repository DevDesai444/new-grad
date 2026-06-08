"""seen.json state store: atomic write + .bak fallback + sanity gate.

PITFALLS.md Pitfalls 1 (atomic write) and 2 (sanity gate) mitigation.

Per ARCHITECTURE.md §State Store, this is the SOLE component that touches
seen.json on disk. All other modules see state as a dict.

Requirements covered:
- STATE-01: all state in seen.json at repo root, keyed by dedup_key.
- STATE-02: atomic write via seen.json.tmp + os.replace().
- STATE-03: read with try/except, fall back to seen.json.bak on JSONDecodeError.
- STATE-06: sanity gate (CONTEXT.md D-06) — engages unconditionally; any_blocked
  carve-out skips the gate when a known adapter reported SiteBlocked.
- STATE-07: orjson with OPT_SORT_KEYS for deterministic git diffs.
- STATE-08: schema_version field; loader refuses unknown future versions.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import orjson

logger = logging.getLogger(__name__)

# STATE-08
# Phase 4 Plan 04-03 D-04 — bumped 1 → 2 to add the source_health block.
# load_state auto-migrates v1 in memory; save_state_atomic writes v2 only.
SCHEMA_VERSION: int = 2

EMPTY_STATE: dict = {
    "schema_version": SCHEMA_VERSION,
    "last_run_utc": None,
    "postings": {},
    # Plan 04-03 D-04 — per-company adapter outcome tracking; NOT rendered
    # in README per CONTEXT.md D-04c (data persisted for diagnostic use only).
    "source_health": {},
}


def _fresh_empty_state() -> dict:
    """Return a fresh, independent EMPTY_STATE copy (callers may mutate)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "last_run_utc": None,
        "postings": {},
        "source_health": {},
    }

# STATE-06 — CONTEXT.md D-06: gate always engages; cold-start (prior=0) trivially
# passes because new < 0.9 * 0 = 0 is False.
_SANITY_FLOOR_RATIO = 0.9


class SanityGateAborted(Exception):
    """Raised when the new scan would shrink seen.json by more than 10% with no
    adapter reporting SiteBlocked. CONTEXT.md D-06.

    The orchestrator (Plan 03 main.py) must let this bubble up and exit non-zero
    so the failure is visible in the GitHub Actions run UI.
    """


class UnknownSchemaVersion(Exception):
    """Raised when seen.json declares a schema_version this code can't read.

    STATE-08. Prevents an older deployment from silently truncating fields that
    a newer version wrote.
    """


def _bak_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".bak")


def _tmp_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".tmp")


def _parse_state_bytes(data: bytes, source: Path) -> dict | None:
    """Parse seen.json bytes; return dict on success, None on recoverable failure.

    Raises UnknownSchemaVersion (STATE-08) on forward-incompatible schema —
    this is NOT recoverable and must crash the run.
    """
    try:
        state = orjson.loads(data)
    except orjson.JSONDecodeError as e:
        logger.warning("state_store: JSON decode failed for %s: %s", source, e)
        return None
    if not isinstance(state, dict):
        logger.warning("state_store: %s is not a top-level dict", source)
        return None
    sv = state.get("schema_version")
    if not isinstance(sv, int):
        logger.warning("state_store: %s has missing/invalid schema_version", source)
        return None
    if sv > SCHEMA_VERSION:
        raise UnknownSchemaVersion(
            f"{source}: schema_version={sv} > SCHEMA_VERSION={SCHEMA_VERSION}. "
            "Refusing to read."
        )
    if "postings" not in state or not isinstance(state["postings"], dict):
        logger.warning("state_store: %s missing 'postings' dict", source)
        return None
    # Phase 4 Plan 04-03 D-04a — auto-migrate older schemas in memory.
    # Currently only v1 → v2 (add empty source_health block). The migration
    # is in-memory only; the next save_state_atomic call writes v2.
    if sv < SCHEMA_VERSION:
        if sv == 1:
            state.setdefault("source_health", {})
            state["schema_version"] = SCHEMA_VERSION
            logger.info(
                "state_store: auto-migrated %s from schema_version=1 to %d "
                "(added empty source_health block)",
                source,
                SCHEMA_VERSION,
            )
        else:
            # Defensive: any older version we haven't written explicit
            # migration code for. Treat as corrupt to force investigation.
            logger.warning(
                "state_store: %s has schema_version=%d which has no migration "
                "path; treating as corrupt",
                source,
                sv,
            )
            return None
    # Plan 04-03 D-04 — source_health is mandatory for v2 but tolerate
    # missing / wrong-type for forward compatibility and partial-write recovery.
    # Defaulting to {} preserves Pitfall 1's "fail soft on corrupted state".
    if "source_health" not in state or not isinstance(state.get("source_health"), dict):
        logger.warning(
            "state_store: %s missing/invalid source_health; defaulting to {}",
            source,
        )
        state["source_health"] = {}
    return state


def load_state(path: Path = Path("seen.json")) -> dict:
    """Load seen.json with .bak fallback (STATE-03).

    - Missing file -> independent copy of EMPTY_STATE (so callers can mutate).
    - JSONDecodeError on main -> try .bak.
    - Both unreadable -> log + return EMPTY_STATE.
    - UnknownSchemaVersion on either file -> raise (forward-incompat).
    """
    if not path.exists():
        # Independent copy: prevent callers from mutating the module-level EMPTY_STATE.
        return _fresh_empty_state()

    state = _parse_state_bytes(path.read_bytes(), path)
    if state is not None:
        return state

    bak = _bak_path(path)
    if bak.exists():
        logger.warning(
            "state_store: falling back to %s after %s parse failure", bak, path
        )
        bak_state = _parse_state_bytes(bak.read_bytes(), bak)
        if bak_state is not None:
            return bak_state

    logger.error(
        "state_store: BOTH %s and %s unreadable; returning EMPTY_STATE. "
        "Investigate manually — git history is your backup.",
        path,
        bak,
    )
    return _fresh_empty_state()


def save_state_atomic(state: dict, path: Path = Path("seen.json")) -> None:
    """Atomically save state to path.

    1. Reject saves with the wrong schema_version (defensive).
    2. If path exists, copy to .bak first (so corruption recovery has a baseline).
    3. Serialize via orjson OPT_SORT_KEYS (STATE-07) for deterministic diffs.
    4. Write to .tmp + fsync.
    5. os.replace(.tmp, path) — POSIX-atomic (STATE-02).

    Phase 4 Plan 04-03 D-04: the serialized v2 payload includes the
    `source_health` block alongside `postings`. orjson handles dict-of-dict
    generically — no special serialization needed.
    """
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"save_state_atomic: refusing to write schema_version="
            f"{state.get('schema_version')!r}; must be {SCHEMA_VERSION}"
        )

    if path.exists():
        # copy2 preserves metadata; the .bak is meant to be readable as JSON.
        shutil.copy2(path, _bak_path(path))

    payload = orjson.dumps(state, option=orjson.OPT_SORT_KEYS | orjson.OPT_INDENT_2)

    tmp = _tmp_path(path)
    # Open + write + fsync inside `with` — close happens before os.replace.
    with open(tmp, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def sanity_gate(prior_count: int, new_count: int, any_blocked: bool) -> None:
    """STATE-06 / CONTEXT.md D-06.

    Raises SanityGateAborted if new_count < 0.9 * prior_count AND any_blocked is False.

    Cold-start (prior_count == 0) trivially passes: 0 < 0 is False.
    Prior=1 + new=0 case aborts — intentional defensive behavior per D-06.
    any_blocked=True skips the gate entirely (Pitfall 5 — known block, not silent loss).
    """
    if any_blocked:
        logger.info(
            "sanity_gate: any_blocked=True; gate skipped (prior=%d, new=%d)",
            prior_count,
            new_count,
        )
        return
    threshold = _SANITY_FLOOR_RATIO * prior_count
    if new_count < threshold:
        raise SanityGateAborted(
            f"new_count={new_count} < floor={threshold:.1f} "
            f"(prior_count={prior_count}, ratio={_SANITY_FLOOR_RATIO}). "
            "Aborting commit. Investigate before next run."
        )
