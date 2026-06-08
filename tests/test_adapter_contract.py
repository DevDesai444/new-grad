"""ADP-14 / ADP-15 contract test — adapter additions are open/closed + reversible.

Asserts:
  - Every entry in registry.ADAPTERS subclasses Adapter
  - Every adapter has a non-empty `name` class attribute
  - Names are unique (registry hint dispatch must be unambiguous)
  - The Greenhouse adapter file does not import from any sibling adapter file —
    proves ADP-15 reversibility (removing one adapter file does not break others)
  - Registry dispatch uses Adapter.matches() rather than hard-coded class names
    (ADP-02 — open/closed dispatch principle)
"""
from __future__ import annotations

from pathlib import Path

from src.adapters.base import Adapter
from src.registry import ADAPTERS


def test_all_adapters_subclass_base():
    """ADP-14 — every entry in ADAPTERS must subclass the Adapter ABC."""
    for cls in ADAPTERS:
        assert issubclass(cls, Adapter), f"{cls!r} is not an Adapter subclass"


def test_all_adapters_have_name():
    """ADP-01 — every adapter must declare a non-empty `name`."""
    for cls in ADAPTERS:
        assert hasattr(cls, "name") and cls.name and isinstance(cls.name, str), \
            f"{cls!r} missing or empty `name`"


def test_adapter_names_unique():
    """ADP-14 — no two adapters may claim the same name (hint dispatch would
    be ambiguous; ADP-03 dedup key prefix `gh:`, `lv:` etc. would collide).
    """
    names = [cls.name for cls in ADAPTERS]
    assert len(names) == len(set(names)), f"duplicate adapter names: {names}"


def test_greenhouse_adapter_is_self_contained():
    """ADP-15 — removing one adapter file must not break the others.

    Greenhouse must not import from src.adapters.lever / workday / etc.
    """
    src = Path("src/adapters/greenhouse.py").read_text()
    forbidden = [
        "from src.adapters.lever",
        "from src.adapters.ashby",
        "from src.adapters.workday",
        "from src.adapters.smartrecruiters",
        "from src.adapters.apple",
        "from src.adapters.playwright_fallback",
    ]
    for f in forbidden:
        assert f not in src, \
            f"greenhouse.py imports {f!r} — violates ADP-15 reversibility"


def test_registry_dispatches_via_matches_only():
    """ADP-02 — registry dispatch is via Adapter.matches(), not class names."""
    src = Path("src/registry.py").read_text()
    assert ".matches(" in src, \
        "registry.py must invoke Adapter.matches() for URL-pattern dispatch"


def test_adapters_list_is_concrete_classes_not_instances():
    """ADAPTERS must hold classes, not instances — registry instantiates per call."""
    for entry in ADAPTERS:
        assert isinstance(entry, type), \
            f"{entry!r} must be a class, not an instance"


def test_new_adapter_can_be_added_without_touching_existing_files(tmp_path):
    """ADP-14 — proof by construction: a synthetic adapter can be appended to
    ADAPTERS at runtime, and the registry dispatches to it without any edits
    to existing adapter files.
    """
    from src import registry as reg
    from src.models import CompanyConfig

    class _SyntheticAdapter(Adapter):
        name = "synthetic-test"

        @classmethod
        def matches(cls, url: str) -> bool:
            return "synthetic.example" in url

        def fetch(self, company):
            return []

    original = list(reg.ADAPTERS)
    try:
        reg.ADAPTERS.append(_SyntheticAdapter)
        company = CompanyConfig(
            name="synthetic",
            url="https://synthetic.example/jobs",
            hint=None,
        )
        adapter = reg.get_adapter(company)
        assert isinstance(adapter, _SyntheticAdapter)
    finally:
        reg.ADAPTERS[:] = original
