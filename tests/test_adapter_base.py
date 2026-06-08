"""Unit tests for the Adapter ABC and typed exception classes.

Per CONTEXT.md D-07: Phase 1 ships happy-path tests; ADP-11 error classes are
defined and verified inheritable here but not exercised against real fetches
(that lives in Phase 2's fixture-mutation tests).
"""
import pytest

from src.adapters.base import (
    Adapter,
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
    [SiteBlocked, SchemaDrift, PlaywrightTimeout, MissingCredential],
)
def test_typed_errors_inherit_from_exception(exc_cls):
    assert issubclass(exc_cls, Exception)
    # Smoke: can be raised and caught
    with pytest.raises(exc_cls):
        raise exc_cls("test")


def test_typed_errors_are_distinct_classes():
    # ADP-11 requires four distinct types so the orchestrator can route on them
    classes = {SiteBlocked, SchemaDrift, PlaywrightTimeout, MissingCredential}
    assert len(classes) == 4


def test_adapter_subclass_must_implement_matches_and_fetch():
    # Subclass declaring neither matches nor fetch is still abstract
    class IncompleteAdapter(Adapter):
        name = "incomplete"

    with pytest.raises(TypeError):
        IncompleteAdapter()  # type: ignore[abstract]
