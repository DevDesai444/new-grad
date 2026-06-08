"""Unit tests for the Adapter ABC and typed exception classes.

Per CONTEXT.md D-07: Phase 1 ships happy-path tests; ADP-11 error classes are
defined and verified inheritable here but not exercised against real fetches
(that lives in Phase 2's fixture-mutation tests).
"""
import pytest

from src.adapters.base import (
    Adapter,
    InvalidCredential,
    MissingCredential,
    PlaywrightTimeout,
    SchemaDrift,
    SiteBlocked,
)


def test_adapter_is_abstract():
    with pytest.raises(TypeError):
        Adapter()  # type: ignore[abstract]


@pytest.mark.parametrize(
    "exc_cls",
    [
        SiteBlocked,
        SchemaDrift,
        PlaywrightTimeout,
        MissingCredential,
        InvalidCredential,
    ],
)
def test_typed_errors_inherit_from_exception(exc_cls):
    assert issubclass(exc_cls, Exception)
    # Smoke: can be raised and caught
    with pytest.raises(exc_cls):
        raise exc_cls("test")


def test_typed_errors_are_distinct_classes():
    # ADP-11 (+ Phase 3 Plan 03-03 InvalidCredential) — five distinct types so
    # the orchestrator can route on them.
    classes = {
        SiteBlocked,
        SchemaDrift,
        PlaywrightTimeout,
        MissingCredential,
        InvalidCredential,
    }
    assert len(classes) == 5


def test_invalid_credential_exists_and_subclasses_exception():
    """Plan 03-03 — InvalidCredential is importable and a proper Exception subclass."""
    assert issubclass(InvalidCredential, Exception)


def test_invalid_credential_distinct_from_missing_credential():
    """Plan 03-03 D-02c — InvalidCredential is distinct from MissingCredential
    so the orchestrator can route on each (env-var unset vs login rejected).
    """
    assert InvalidCredential is not MissingCredential
    assert not issubclass(InvalidCredential, MissingCredential)
    assert not issubclass(MissingCredential, InvalidCredential)


def test_adapter_subclass_must_implement_matches_and_fetch():
    # Subclass declaring neither matches nor fetch is still abstract
    class IncompleteAdapter(Adapter):
        name = "incomplete"

    with pytest.raises(TypeError):
        IncompleteAdapter()  # type: ignore[abstract]
