"""Tests for ``dazzlecmd_lib.entity`` -- the DazzleEntity object model (Phase 0).

Covers the validated shapes from the /collaborate3 probe plus the
Phase-0 surface: construction, discriminated-union discrimination, the
backward-compat shim, round-trip fidelity, set-once canonical FQCN (C1),
the Groupable capability + MRO, and type detection / hard-fail.
"""
from __future__ import annotations

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
    reserve_field_axis,
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
        # typed field access via attribute
        assert t.runtime == {"type": "python", "interpreter": "python"}
        # extra/novel manifest keys read via extra_get
        assert t.extra_get("script") == "tool1.py"

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
        assert e.tools == ["core:rn"]

    def test_adapter_selects_aggregator(self):
        e = ENTITY_ADAPTER.validate_python({"name": "dazzlecmd", "type": "aggregator"})
        assert isinstance(e, Aggregator)

    def test_build_entity_injects_explicit_type(self):
        e = build_entity(_tool_manifest(), entity_type="tool")
        assert isinstance(e, Tool)

    def test_build_entity_missing_type_hard_fails(self):
        with pytest.raises(AmbiguousEntityTypeError):
            build_entity(_tool_manifest())  # no type, no entity_type




class TestRoundTrip:
    def test_to_manifest_strips_computed_keys(self):
        t = Tool.model_validate(_tool_manifest())
        t.fqcn = "core:tool1"    # set-once canonical FQCN via property
        t.kit_active = True      # set computed field via attribute
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


class TestGroupable:
    def test_entity_is_groupable(self):
        t = Tool.model_validate(_tool_manifest())
        assert isinstance(t, Groupable)

    def test_mro_is_clean(self):
        # Groupable before BaseModel; entity constructs without MRO conflict
        assert Groupable in DazzleEntity.__mro__
        assert DazzleEntity.__mro__.index(Groupable) < DazzleEntity.__mro__.index(__import__("pydantic").BaseModel)

    def test_all_five_verbs_live_with_real_signatures(self):
        t = Tool.model_validate(_tool_manifest())
        # All five Groupable verbs are live (#84) -- each delegates to a context,
        # so called without one they raise TypeError (a live signature), not
        # NotImplementedError. group/ungroup are live for the reversible in-tree
        # regime; graduation is refused at the criticality boundary (not
        # unimplemented).
        with pytest.raises(TypeError):
            t.rebind("some:target", context=None)
        with pytest.raises(TypeError):
            t.hide(to="hidden", context=None)
        with pytest.raises(TypeError):
            t.expose(to="visible", context=None)
        with pytest.raises(TypeError):
            t.group("core", context=None)
        with pytest.raises(TypeError):
            t.ungroup(context=None)


class TestReserveFieldAxis:
    def test_clean_name_ok(self):
        reserve_field_axis(name="claude-cleanup", namespace="dazzletools")  # no raise

    def test_dot_in_name_rejected(self):
        with pytest.raises(ValueError, match="reserved for the field-access axis"):
            reserve_field_axis(name="find.recipe")

    def test_dot_in_namespace_rejected(self):
        with pytest.raises(ValueError, match="reserved for the field-access axis"):
            reserve_field_axis(name="rn", namespace="core.x")

    def test_underscore_and_hyphen_allowed(self):
        reserve_field_axis(name="md_rm_img")
        reserve_field_axis(name="claude-session-metadata")


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


