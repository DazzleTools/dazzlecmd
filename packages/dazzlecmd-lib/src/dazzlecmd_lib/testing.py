"""Test factories for constructing :class:`DazzleEntity` instances.

Public, permanent test infrastructure -- the blessed way to build entities in
tests, for dazzlecmd AND any aggregator consumer (wtf-windows, amdead, third
parties). Replaces ad-hoc dict literals (`{"name": "x", ...}`) with typed
entity construction.

These are NOT transitional shims: they produce real `DazzleEntity` objects via
the canonical :func:`dazzlecmd_lib.entity.build_entity` path, and they stay
after the dict shim is removed.

Usage::

    from dazzlecmd_lib.testing import make_tool, make_kit

    t = make_tool(name="rn", namespace="core", runtime={"type": "python"})
    k = make_kit(name="core", tools=["core:rn"], always_active=True)

Legacy `_`-prefixed computed keys are normalized to their promoted field names
(`_dir` -> `directory`, `_kit_active` -> `kit_active`, ...) and `_fqcn` / `fqcn`
is applied via the set-once property -- so porting an existing dict fixture is
mechanical: ``make_tool(**old_fixture_dict)``.
"""

from __future__ import annotations

from typing import Any

from dazzlecmd_lib.entity import DazzleEntity, build_entity


# Legacy `_`-prefixed computed keys -> their promoted field names, so old dict
# fixtures (which used `_dir`, `_kit_active`, ...) port to the factory unchanged.
# This is INPUT normalization at construction -- distinct from the runtime dict
# shim, which was removed in the 0.8.0 lib bump. (`_fqcn` is handled separately
# via the set-once property.)
_LEGACY_INPUT_ALIASES = {
    "_short_name": "short_name",
    "_kit_import_name": "kit_import_name",
    "_dir": "directory",
    "_manifest_path": "manifest_path",
    "_cached": "cached",
    "_source": "kit_source",
    "_kit_name": "kit_name",
    "_kit_active": "kit_active",
    "_auto_realpath_alias": "auto_realpath_alias",
    "_canonical_fqcn": "canonical_fqcn",
    "_original_name": "original_name",
    "_override_tools_dir": "override_tools_dir",
    "_override_manifest": "override_manifest",
}


def _make(entity_type: str, fields: dict) -> DazzleEntity:
    data = dict(fields)
    # fqcn is a set-once PROPERTY, not a constructor field -- apply it after.
    fqcn = data.pop("_fqcn", None)
    if "fqcn" in data:
        fqcn = data.pop("fqcn")
    norm = {_LEGACY_INPUT_ALIASES.get(k, k): v for k, v in data.items()}
    entity = build_entity(norm, entity_type=entity_type)
    if fqcn is not None:
        entity.fqcn = fqcn
    return entity


def make_tool(**fields: Any) -> DazzleEntity:
    """Build a ``Tool`` entity. ``name`` defaults to ``"tool"`` if omitted."""
    fields.setdefault("name", "tool")
    return _make("tool", fields)


def make_kit(**fields: Any) -> DazzleEntity:
    """Build a ``Kit`` entity. ``name`` defaults to ``"kit"`` if omitted."""
    fields.setdefault("name", "kit")
    return _make("kit", fields)


def make_aggregator(**fields: Any) -> DazzleEntity:
    """Build an ``Aggregator`` entity. ``name`` defaults to ``"aggregator"``."""
    fields.setdefault("name", "aggregator")
    return _make("aggregator", fields)
