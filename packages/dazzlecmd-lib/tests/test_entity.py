"""Tests for ``dazzlecmd_lib.entity`` -- the DazzleEntity object model (Phase 0).

Covers the validated shapes from the /collaborate3 probe plus the
Phase-0 surface: construction, discriminated-union discrimination, the
backward-compat shim, round-trip fidelity, set-once canonical FQCN (C1),
the Groupable capability + MRO, and type detection / hard-fail.
"""
from __future__ import annotations

import warnings

import pytest

from dazzlecmd_lib.entity import (
    Aggregator,
    AmbiguousEntityTypeError,
    AnyDazzleEntity,
    DazzleEntity,
    ENTITY_ADAPTER,
    Groupable,
    Kit,
    Tool,
    build_entity,
    detect_type,
)


def _tool_manifest(i: int = 1) -> dict:
    return {
        "name": f"tool{i}",
        "namespace": "core",
        "description": f"Tool {i}.",
        "version": "0.1.0",
        "runtime": {"type": "python", "interpreter": "python"},
        "script": f"tool{i}.py",
        "tags": ["a", "b"],
    }


class TestConstruction:
    def test_tool_constructs_with_typed_fields(self):
        t = Tool.model_validate(_tool_manifest())
        assert t.name == "tool1"
        assert t.namespace == "core"
        assert t.version == "0.1.0"
        assert t.type == "tool"

    def test_extra_fields_preserved(self):
        t = Tool.model_validate(_tool_manifest())
        # nested blocks + extra fields land in __pydantic_extra__ (stay dicts)
        assert t["runtime"] == {"type": "python", "interpreter": "python"}
        assert t["script"] == "tool1.py"

    def test_missing_required_name_raises(self):
        m = _tool_manifest()
        del m["name"]
        with pytest.raises(Exception):  # pydantic ValidationError
            Tool.model_validate(m)


class TestDiscriminatedUnion:
    def test_adapter_selects_tool(self):
        e = ENTITY_ADAPTER.validate_python({**_tool_manifest(), "type": "tool"})
        assert isinstance(e, Tool)

    def test_adapter_selects_kit(self):
        e = ENTITY_ADAPTER.validate_python(
            {"name": "core", "type": "kit", "tools": ["core:rn"], "always_active": True}
        )
        assert isinstance(e, Kit)
        assert e["tools"] == ["core:rn"]

    def test_adapter_selects_aggregator(self):
        e = ENTITY_ADAPTER.validate_python({"name": "dazzlecmd", "type": "aggregator"})
        assert isinstance(e, Aggregator)

    def test_build_entity_injects_explicit_type(self):
        e = build_entity(_tool_manifest(), entity_type="tool")
        assert isinstance(e, Tool)

    def test_build_entity_missing_type_hard_fails(self):
        with pytest.raises(AmbiguousEntityTypeError):
            build_entity(_tool_manifest())  # no type, no entity_type


class TestShimTransparency:
    def test_item_read_matches_attr(self):
        t = Tool.model_validate(_tool_manifest())
        assert t["name"] == t.name == "tool1"

    def test_get_with_default(self):
        t = Tool.model_validate(_tool_manifest())
        assert t.get("name") == "tool1"
        assert t.get("missing", "d") == "d"

    def test_contains(self):
        t = Tool.model_validate(_tool_manifest())
        assert "name" in t
        assert "script" in t  # extra field
        assert "definitely_missing" not in t

    def test_in_place_computed_mutation(self):
        t = Tool.model_validate(_tool_manifest())
        t["_kit_active"] = True
        t["_dir"] = "/tmp/x"
        assert t["_kit_active"] is True
        assert t["_dir"] == "/tmp/x"

    def test_keyerror_on_missing(self):
        t = Tool.model_validate(_tool_manifest())
        with pytest.raises(KeyError):
            _ = t["definitely_missing"]

    def test_shim_silent_by_default(self):
        """Phase 0: shim must NOT emit warnings (engine relies on it everywhere)."""
        t = Tool.model_validate(_tool_manifest())
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warning -> error
            _ = t["name"]
            _ = t.get("name")
            t["_x"] = 1

    def test_shim_ratchet_can_be_enabled(self):
        """Phase 1 flips the ratchet; verify the mechanism works in isolation."""
        class _RatchetTool(Tool):
            _warn_on_shim = True

        t = _RatchetTool.model_validate(_tool_manifest())
        with pytest.warns(DeprecationWarning):
            _ = t["name"]


class TestRoundTrip:
    def test_to_manifest_strips_computed_keys(self):
        t = Tool.model_validate(_tool_manifest())
        t["_fqcn"] = "core:tool1"
        t["_kit_active"] = True
        manifest = t.to_manifest()
        assert not any(k.startswith("_") for k in manifest)
        # original manifest fields survive
        for k, v in _tool_manifest().items():
            assert manifest[k] == v


class TestSetOnceFQCN:
    def test_set_once_via_property(self):
        t = Tool.model_validate(_tool_manifest())
        t.fqcn = "core:tool1"
        assert t.fqcn == "core:tool1"
        with pytest.raises(RuntimeError):
            t.fqcn = "core:hacked"

    def test_set_once_via_shim_item_assignment(self):
        t = Tool.model_validate(_tool_manifest())
        t["_fqcn"] = "core:tool1"
        assert t.fqcn == "core:tool1"
        with pytest.raises(RuntimeError):
            t["_fqcn"] = "core:hacked"  # item-assignment must honor C1


class TestGroupable:
    def test_entity_is_groupable(self):
        t = Tool.model_validate(_tool_manifest())
        assert isinstance(t, Groupable)

    def test_mro_is_clean(self):
        # Groupable before BaseModel; entity constructs without MRO conflict
        assert Groupable in DazzleEntity.__mro__
        assert DazzleEntity.__mro__.index(Groupable) < DazzleEntity.__mro__.index(__import__("pydantic").BaseModel)

    def test_verbs_declared_but_deferred(self):
        t = Tool.model_validate(_tool_manifest())
        for verb in ("group", "ungroup", "hide", "expose", "rebind"):
            with pytest.raises(NotImplementedError):
                getattr(t, verb)()


class TestDetectType:
    def test_aggregator_precedence(self):
        assert detect_type({"has_kits_dir": True, "has_kit_manifest": True}) == "aggregator"

    def test_kit(self):
        assert detect_type({"has_kit_manifest": True}) == "kit"

    def test_tool(self):
        assert detect_type({"has_tool_manifest": True}) == "tool"

    def test_no_marker_hard_fails(self):
        with pytest.raises(AmbiguousEntityTypeError):
            detect_type({})
