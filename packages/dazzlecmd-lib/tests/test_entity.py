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


class TestUntypedAccessContract:
    """The v0.8.32 post-shim review: the 4 mis-filed keys are typed, and the
    `_vars` strip bug is fixed (to_manifest preserves `_`-prefixed MANIFEST
    data while still stripping computed `_`-annotations)."""

    def test_vars_survives_to_manifest(self):
        # THE BUG: pre-v0.8.32, to_manifest stripped `_vars` (template
        # variables, #41), so mode.cache_manifest silently lost them.
        t = build_entity(
            {**_tool_manifest(), "_vars": {"venv": ".venv312"}},
            entity_type="tool",
        )
        m = t.to_manifest()
        assert m["_vars"] == {"venv": ".venv312"}

    def test_schema_version_survives_to_manifest(self):
        t = build_entity(
            {**_tool_manifest(), "_schema_version": 2}, entity_type="tool"
        )
        assert t.to_manifest()["_schema_version"] == 2

    def test_computed_underscore_keys_still_stripped(self):
        t = build_entity(_tool_manifest(), entity_type="tool")
        t.fqcn = "core:tool1"
        m = t.to_manifest()
        assert "_fqcn" not in m

    def test_tools_dir_and_manifest_are_typed_fields(self):
        k = build_entity(
            {"name": "wtf", "tools_dir": "src/tools", "manifest": ".wtf.json"},
            entity_type="kit",
        )
        assert k.tools_dir == "src/tools"
        assert k.manifest == ".wtf.json"
        # and they round-trip as manifest data
        m = k.to_manifest()
        assert m["tools_dir"] == "src/tools" and m["manifest"] == ".wtf.json"

    def test_absent_optional_schema_fields_stay_out_of_projection(self):
        # An ordinary kit never declared tools_dir/manifest -- the projection
        # must not grow `"tools_dir": null` noise.
        k = build_entity({"name": "core"}, entity_type="kit")
        assert k.tools_dir is None and k.manifest is None
        m = k.to_manifest()
        assert "tools_dir" not in m and "manifest" not in m

    def test_override_fields_are_computed_and_stripped(self):
        k = build_entity(
            {"name": "wtf", "override_tools_dir": "projects",
             "override_manifest": ".dazzlecmd.json"},
            entity_type="kit",
        )
        assert k.override_tools_dir == "projects"
        m = k.to_manifest()
        # engine annotations, not manifest data
        assert "override_tools_dir" not in m and "override_manifest" not in m


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


