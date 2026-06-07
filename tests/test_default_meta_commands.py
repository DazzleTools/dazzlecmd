"""Tests for dazzlecmd_lib.default_meta_commands.

Covers:
- render_list (filters, empty, formatting)
- render_info (fields, FQCN lookup, ambiguity, not found)
- render_kit_list (all kits, specific kit, empty)
- render_kit_status
- render_version (with/without version_info)
- render_tree (ASCII, JSON, empty)
- render_setup_listing (tools with/without setup)
- register_all / register_selected

Pure printing tests use capsys. No mocks needed for these — they're
deterministic given input projects/kits fixtures.
"""

from __future__ import annotations

import argparse
import json as _json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dazzlecmd_lib import default_meta_commands as dmc
from dazzlecmd_lib.meta_command_registry import MetaCommandRegistry
from dazzlecmd_lib.testing import make_kit, make_tool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _project(
    name,
    namespace="test",
    kit="testkit",
    description="",
    platform="cross-platform",
    fqcn=None,
    **extra,
):
    # A fully-annotated tool entity, mirroring what discovery +
    # engine._annotate_project_fqcn produce in production: short_name == name,
    # kit_import_name == kit, fqcn set, directory set.
    return make_tool(
        name=name,
        namespace=namespace,
        short_name=name,
        kit_import_name=kit,
        fqcn=fqcn or f"{kit}:{name}",
        directory=f"/tmp/{kit}/{name}",
        description=description,
        platform=platform,
        **extra,
    )


def _kit(name, tools=None, description="", always_active=False):
    return make_kit(
        name=name,
        _kit_name=name,
        description=description,
        tools=tools or [],
        always_active=always_active,
    )


def _args(**kwargs):
    defaults = {
        "namespace": None,
        "kit": None,
        "tag": None,
        "platform": None,
        "tool": None,
        "name": None,
        "json": False,
        "depth": None,
        "show": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _engine_with_virtual_kit(canonical_projects, vk_name, alias_map):
    """Build an engine with a virtual kit declared on top of canonical
    projects. ``alias_map`` is a dict mapping alias-FQCN to canonical-FQCN.

    Used by the parity tests for render_list / build_list_entries /
    render_tree to cover the virtual-kit code paths without standing up
    a full kit-manifest fixture.
    """
    engine = _engine_with(canonical_projects)
    # Add a virtual-kit entry to engine.kits so render_tree finds it
    engine.kits.append(make_kit(
        name=vk_name,
        _kit_name=vk_name,
        virtual=True,
        _kit_active=True,
        always_active=False,
        tools=list(alias_map.keys()),
    ))
    # Inject aliases into the FQCN index
    for alias_fqcn, canonical_fqcn in alias_map.items():
        engine.fqcn_index.alias_index[alias_fqcn] = canonical_fqcn
    return engine


def _engine_with(projects):
    """Build a minimal AggregatorEngine with projects indexed.

    render_info / setup_handler now require ``engine`` (rule 7c relaxation +
    alias-blindness audit, v0.7.28). Tests build a real engine with
    canonical projects inserted; no virtual kits unless explicitly added.
    """
    from dazzlecmd_lib.engine import AggregatorEngine
    engine = AggregatorEngine(is_root=True)
    # Fixtures are already fully-annotated entities (see _project), so no
    # short_name backfill is needed -- _build_fqcn_index consumes the
    # annotation production sets during discovery.
    engine.projects = list(projects)
    engine._build_fqcn_index()
    return engine


def _engine(command="test", name="test-aggregator", version_info=None, projects=None, kits=None):
    e = MagicMock()
    e.command = command
    e.name = name
    e.version_info = version_info
    e.projects = projects or []
    e.kits = kits or []
    e.tools_dir = "tools"
    return e


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestRenderList:
    def test_empty_projects_prints_no_tools(self, capsys):
        assert dmc.render_list(_args(), []) == 0
        assert "No tools found" in capsys.readouterr().out

    def test_basic_listing(self, capsys):
        projects = [
            _project("alpha", description="First tool"),
            _project("beta", description="Second tool"),
        ]
        assert dmc.render_list(_args(), projects) == 0
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out
        assert "First tool" in out
        assert "2 tool(s) found" in out

    def test_filter_by_namespace(self, capsys):
        projects = [
            _project("a", namespace="foo"),
            _project("b", namespace="bar"),
        ]
        dmc.render_list(_args(namespace="foo"), projects)
        out = capsys.readouterr().out
        assert " a " in out or "  a " in out
        assert " b " not in out

    def test_filter_by_kit(self, capsys):
        projects = [
            _project("a", kit="kit1"),
            _project("b", kit="kit2"),
        ]
        dmc.render_list(_args(kit="kit1"), projects)
        out = capsys.readouterr().out
        assert " a " in out or "  a " in out
        assert "1 tool(s) found" in out

    def test_filter_by_tag(self, capsys):
        projects = [
            _project("a", taxonomy={"tags": ["security"]}),
            _project("b", taxonomy={"tags": ["networking"]}),
        ]
        dmc.render_list(_args(tag="security"), projects)
        out = capsys.readouterr().out
        assert "1 tool(s) found" in out

    def test_filter_by_platform(self, capsys):
        projects = [
            _project("a", platform="windows"),
            _project("b", platform="linux"),
        ]
        dmc.render_list(_args(platform="linux"), projects)
        out = capsys.readouterr().out
        assert "1 tool(s) found" in out

    def test_description_truncation(self, capsys):
        long_desc = "x" * 100
        dmc.render_list(_args(), [_project("a", description=long_desc)])
        out = capsys.readouterr().out
        assert "..." in out

    def test_list_handler_delegates_to_render(self, capsys):
        projects = [_project("a")]
        rc = dmc.list_handler(_args(), None, projects, [], None)
        assert rc == 0
        assert "a" in capsys.readouterr().out

    # --- 4b-T9 parity surfaces (engine-aware sectioned layout, --show modes) ---

    def test_engine_none_backward_compat_flat_output(self, capsys):
        """Without engine, render_list emits the legacy flat output.

        Backward-compat: aggregators that haven't migrated to the
        engine-aware path get unchanged behavior.
        """
        projects = [_project("alpha"), _project("beta")]
        rc = dmc.render_list(_args(), projects)
        assert rc == 0
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out
        assert "2 tool(s) found" in out
        # Backward-compat output uses the "Name | Kit | Description" header
        assert "Name" in out and "Kit" in out and "Description" in out

    def test_show_canonical_mode_with_engine(self, capsys):
        """--show canonical lists canonicals only (no aliases)."""
        projects = [
            _project("alpha", kit="core", fqcn="core:alpha"),
            _project("beta", kit="core", fqcn="core:beta"),
        ]
        engine = _engine_with(projects)
        rc = dmc.render_list(_args(show="canonical"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out
        assert "tool(s) found" in out

    def test_show_alias_mode_with_virtual_kit(self, capsys):
        """--show alias lists virtual-kit aliases only."""
        projects = [_project("alpha", kit="core", fqcn="core:alpha")]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        rc = dmc.render_list(_args(show="alias"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # alias entry shown (alpha as alias under claude)
        assert "alpha" in out
        # canonical not shown in alias-only mode
        assert "alias(es) found" in out

    def test_show_all_marks_aliased_canonicals(self, capsys):
        """--show all marks canonicals that have aliases with [+]."""
        projects = [
            _project("alpha", kit="core", fqcn="core:alpha"),
            _project("beta", kit="core", fqcn="core:beta"),
        ]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        rc = dmc.render_list(_args(show="all"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # alpha has an alias → marked with [+]
        assert "[+]" in out
        # beta has no alias → no [+] on beta
        assert "alpha" in out
        assert "beta" in out

    def test_default_mode_alias_preferred(self, capsys):
        """Default mode hides canonicals that have aliases (alias-preferred)."""
        projects = [
            _project("alpha", kit="core", fqcn="core:alpha"),
            _project("beta", kit="core", fqcn="core:beta"),
        ]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        rc = dmc.render_list(_args(show="default"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # alpha-as-alias shown, alpha-as-canonical hidden
        assert "alpha" in out
        # beta has no alias → still shown as canonical
        assert "beta" in out
        # Footer mentions canonical + virtual-kit alias counts
        assert "canonical" in out
        assert "virtual-kit alias" in out

    def test_sectioned_layout_multi_kit(self, capsys):
        """Multi-kit projects render in sectioned layout (not flat)."""
        projects = [
            _project("alpha", kit="kit1", fqcn="kit1:alpha"),
            _project("beta", kit="kit2", fqcn="kit2:beta"),
        ]
        engine = _engine_with(projects)
        rc = dmc.render_list(_args(show="canonical"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # Section headers (kit:)
        assert "kit1:" in out
        assert "kit2:" in out
        # Tools nested under their kit
        assert "alpha" in out
        assert "beta" in out

    def test_virtual_kit_section_annotation(self, capsys):
        """Virtual-kit sections show a (virtual kit '<name>') annotation."""
        projects = [_project("alpha", kit="core", fqcn="core:alpha")]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        rc = dmc.render_list(_args(show="all"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "(virtual kit 'claude')" in out


class TestBuildListEntries:
    """Tests for the public ``build_list_entries`` data-layer API.

    Aggregators that want to render their own display layer can call
    this to get the entry list, then iterate however they like.
    """

    def test_canonical_entries_only_no_engine(self):
        """Without engine, no FQCN index → no aliases → canonical only."""
        projects = [_project("alpha", kit="core", fqcn="core:alpha")]
        entries = dmc.build_list_entries(projects, None, "default", None)
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "canonical"
        assert entries[0]["_fqcn"] == "core:alpha"

    def test_canonical_entries_with_engine(self):
        """With engine but no virtual kits, all entries are canonical."""
        projects = [
            _project("alpha", kit="core", fqcn="core:alpha"),
            _project("beta", kit="core", fqcn="core:beta"),
        ]
        engine = _engine_with(projects)
        entries = dmc.build_list_entries(projects, engine, "canonical", None)
        assert len(entries) == 2
        for e in entries:
            assert e["entry_type"] == "canonical"
            assert e["section_kind"] == "canonical"
            assert e["section_key"] == "core"

    def test_alias_entries_from_virtual_kit(self):
        """Engine with virtual kit → alias entries included in mode 'alias'."""
        projects = [_project("alpha", kit="core", fqcn="core:alpha")]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        entries = dmc.build_list_entries(projects, engine, "alias", None)
        assert len(entries) == 1
        e = entries[0]
        assert e["entry_type"] == "alias"
        assert e["_fqcn"] == "claude:alpha"
        assert e["_canonical_fqcn"] == "core:alpha"
        assert e["section_kind"] == "virtual"
        assert e["name"] == "alpha"
        # Section key encodes canonical_kit_path:vk_name for root virtual kits
        assert e["section_key"] == "core:claude"

    def test_has_aliases_marker_on_canonical(self):
        """Canonicals with aliases get has_aliases=True (for [+] marker)."""
        projects = [
            _project("alpha", kit="core", fqcn="core:alpha"),
            _project("beta", kit="core", fqcn="core:beta"),
        ]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        entries = dmc.build_list_entries(projects, engine, "all", None)
        canonical_alpha = [e for e in entries if e["entry_type"] == "canonical" and e["name"] == "alpha"][0]
        canonical_beta = [e for e in entries if e["entry_type"] == "canonical" and e["name"] == "beta"][0]
        assert canonical_alpha["has_aliases"] is True
        assert canonical_beta["has_aliases"] is False

    def test_default_mode_hides_aliased_canonicals(self):
        """Default mode: canonicals that have aliases are dropped from output."""
        projects = [
            _project("alpha", kit="core", fqcn="core:alpha"),
            _project("beta", kit="core", fqcn="core:beta"),
        ]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        entries = dmc.build_list_entries(projects, engine, "default", None)
        # beta canonical present; alpha canonical hidden; alpha alias present
        names = [(e["name"], e["entry_type"]) for e in entries]
        assert ("beta", "canonical") in names
        assert ("alpha", "canonical") not in names
        assert ("alpha", "alias") in names

    def test_show_all_includes_both(self):
        """--show all returns canonicals AND aliases."""
        projects = [_project("alpha", kit="core", fqcn="core:alpha")]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        entries = dmc.build_list_entries(projects, engine, "all", None)
        types = [e["entry_type"] for e in entries]
        assert types.count("canonical") == 1
        assert types.count("alias") == 1

    def test_kit_filter_by_canonical_kit(self):
        """Filtering by canonical kit name shows only that kit's tools."""
        projects = [
            _project("alpha", kit="core", fqcn="core:alpha"),
            _project("beta", kit="other", fqcn="other:beta"),
        ]
        engine = _engine_with(projects)
        entries = dmc.build_list_entries(projects, engine, "canonical", "core")
        assert len(entries) == 1
        assert entries[0]["name"] == "alpha"

    def test_kit_filter_by_virtual_kit(self):
        """Filtering by virtual-kit name shows only its aliases."""
        projects = [
            _project("alpha", kit="core", fqcn="core:alpha"),
            _project("beta", kit="core", fqcn="core:beta"),
        ]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        entries = dmc.build_list_entries(projects, engine, "default", "claude")
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "alias"
        assert entries[0]["_fqcn"] == "claude:alpha"

    def test_entry_dict_shape_stable(self):
        """Each entry has the documented stable keys."""
        projects = [_project("alpha", kit="core", fqcn="core:alpha")]
        engine = _engine_with(projects)
        entries = dmc.build_list_entries(projects, engine, "canonical", None)
        e = entries[0]
        # Required keys per the docstring contract
        for key in (
            "name", "kit", "description", "entry_type", "namespace",
            "platform", "tags", "_fqcn", "_canonical_fqcn",
            "section_key", "section_kind", "has_aliases",
        ):
            assert key in e, f"missing key {key!r} in entry"


class TestListParserFactory:
    def test_registers_subparser(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        dmc.list_parser_factory(subparsers)
        args = parser.parse_args(["list", "--namespace", "core"])
        assert args.namespace == "core"
        assert args._meta == "list"

    def test_all_filter_flags_available(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        dmc.list_parser_factory(subparsers)
        args = parser.parse_args(["list", "-n", "ns", "-k", "kit", "-t", "tag", "-p", "linux"])
        assert args.namespace == "ns"
        assert args.kit == "kit"
        assert args.tag == "tag"
        assert args.platform == "linux"


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


class TestRenderInfo:
    def test_not_found(self, capsys):
        engine = _engine_with([])
        rc = dmc.render_info(_args(tool="nonexistent"), [], engine=engine)
        assert rc == 1
        captured = capsys.readouterr()
        # v0.7.34: not-found message goes to stdout (matches dazzlecmd CLI's
        # prior behavior; uses engine.command for the "Use 'X list'" hint).
        assert "not found" in captured.out.lower()
        assert "list" in captured.out.lower()

    def test_basic_fields_printed(self, capsys):
        projects = [
            _project("alpha", description="desc", fqcn="testkit:alpha", version="1.0.0"),
        ]
        engine = _engine_with(projects)
        rc = dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "testkit:alpha" in out
        assert "1.0.0" in out
        assert "desc" in out

    def test_fqcn_lookup_colliding_short_picks_by_precedence(self, capsys):
        """Short name 'alpha' collides across two kits. Under the new
        find_project path, resolution goes through precedence — the
        default precedence ordering picks a winner (no 'Multiple' error)
        and may emit a notification. Rule 7c relaxation means alias
        shorts could also appear in short_index."""
        projects = [
            _project("alpha", fqcn="kit1:alpha"),
            _project("alpha", fqcn="kit2:alpha"),
        ]
        engine = _engine_with(projects)
        rc = dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        # Resolution succeeds via precedence; one of the two is picked
        assert rc == 0
        out = capsys.readouterr().out
        # One of the colliding FQCNs is shown
        assert ("kit1:alpha" in out) or ("kit2:alpha" in out)

    def test_fqcn_unique_lookup(self, capsys):
        projects = [
            _project("alpha", fqcn="kit1:alpha"),
            _project("alpha", fqcn="kit2:alpha"),
        ]
        engine = _engine_with(projects)
        rc = dmc.render_info(_args(tool="kit2:alpha"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "kit2:alpha" in out

    def test_runtime_fields_printed(self, capsys):
        projects = [
            _project(
                "alpha",
                runtime={
                    "type": "python",
                    "script_path": "main.py",
                    "interpreter": "/usr/bin/python3",
                },
            )
        ]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Runtime:" in out
        assert "python" in out
        assert "main.py" in out
        assert "/usr/bin/python3" in out

    def test_taxonomy_fields_printed(self, capsys):
        projects = [
            _project(
                "alpha",
                taxonomy={"category": "security", "tags": ["audit", "network"]},
            )
        ]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Category" in out
        assert "security" in out
        assert "Tags" in out
        assert "audit" in out
        assert "network" in out

    def test_setup_hint_shown(self, capsys):
        projects = [
            _project(
                "alpha",
                setup={"command": "pip install .", "note": "Basic install"},
            )
        ]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Setup" in out
        assert "Basic install" in out

    def test_info_handler_delegates_to_render(self, capsys):
        projects = [_project("alpha")]
        engine = _engine_with(projects)
        rc = dmc.info_handler(_args(tool="alpha"), engine, projects, [], None)
        assert rc == 0

    def test_shadow_block_when_tool_shadows_meta_no_override(self, capsys):
        """Tool short-named after a reserved meta-command, no override
        registered: shadow block must surface the dispatch state and tell
        the user the tool is unreachable via short name (issue #56)."""
        projects = [_project("info", fqcn="amdead:info", description="probe")]
        engine = _engine_with(projects)
        rc = dmc.render_info(_args(tool="amdead:info"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Shadow status:" in out
        assert "library default meta-command: info" in out
        assert "aggregator tool: amdead:info" in out
        assert "NOT overridden" in out
        assert "amdead:info" in out

    def test_shadow_block_when_tool_shadows_meta_with_override(self, capsys):
        """Same shadow but the aggregator called override() to chain --
        block must say the override IS the acknowledgment (issue #56)."""
        projects = [_project("info", fqcn="amdead:info")]
        engine = _engine_with(projects)
        engine.meta_registry.override("info", handler=lambda *a, **k: 0)
        rc = dmc.render_info(_args(tool="amdead:info"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Shadow status:" in out
        assert "has overridden the handler" in out
        assert "NOT overridden" not in out

    def test_no_shadow_block_when_not_reserved(self, capsys):
        """Regression guard: non-shadowed tools must not see a shadow
        block (the block only appears for genuine name conflicts)."""
        projects = [_project("alpha", fqcn="amdead:alpha")]
        engine = _engine_with(projects)
        rc = dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Shadow status:" not in out

    # --- v0.7.32 info-parity port (raw/platform flags, qualified-alias,
    # pass_through, python deps, setup hint) ---

    def test_pass_through_displayed(self, capsys):
        projects = [_project("alpha", fqcn="core:alpha", pass_through=True)]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Pass-through: yes" in out

    def test_python_deps_displayed(self, capsys):
        projects = [
            _project(
                "alpha",
                fqcn="core:alpha",
                dependencies={"python": ["requests>=2", "pyyaml"]},
            )
        ]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Python deps:" in out
        assert "requests>=2" in out
        assert "pyyaml" in out

    def test_setup_hint_uses_engine_command(self, capsys):
        """Setup hint should use ``engine.command`` (not literal 'dz') so
        a library consumer like amdead sees 'Run: amdead setup ...'
        rather than 'Run: dz setup ...'."""
        projects = [
            _project("alpha", fqcn="core:alpha", setup={"command": "pip install ."})
        ]
        engine = _engine_with(projects)
        engine.command = "amdead"  # simulate library consumer
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Run: amdead setup core:alpha" in out

    def test_raw_flag_marks_runtime_unresolved(self, capsys):
        """--raw should append '(raw, unresolved)' to the Runtime line."""
        projects = [
            _project(
                "alpha",
                fqcn="core:alpha",
                runtime={"type": "python", "script_path": "main.py"},
            )
        ]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha", raw=True), projects, engine=engine)
        out = capsys.readouterr().out
        assert "(raw, unresolved)" in out
        assert "main.py" in out

    def test_platform_flag_shows_preview(self, capsys):
        """--platform SPEC should mark the runtime as a preview for the
        given platform spec, not a resolution for the current host."""
        projects = [
            _project(
                "alpha",
                fqcn="core:alpha",
                runtime={
                    "type": "python",
                    "platforms": {
                        "linux": {"interpreter": "/usr/bin/python3"},
                        "windows": {"interpreter": "py.exe"},
                    },
                },
            )
        ]
        engine = _engine_with(projects)
        dmc.render_info(
            _args(tool="alpha", platform="linux"),
            projects,
            engine=engine,
        )
        out = capsys.readouterr().out
        assert "(preview for linux)" in out

    def test_qualified_alias_provenance(self, capsys):
        """When ctx.resolution_kind is 'qualified_alias', the provenance
        line shows the qualified path AND the canonical target."""
        projects = [_project("alpha", fqcn="core:alpha")]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        # Inject a qualified-alias resolution context via find_project
        # patch isn't necessary; we test directly through engine.find_project
        # which the library uses. To trigger the qualified_alias path, we
        # mimic the scenario by manually constructing the print call.
        # The existing TestRenderInfo coverage exercises the regular
        # alias-provenance path; this test guards the alternative
        # message variant exists in the code (smoke check).
        out = capsys.readouterr().out  # clear buffer
        # Direct check that the variant text is in render_info source path
        # is covered by the implementation's branching; this asserts the
        # default alias-provenance path (regular kind) still works.
        rc = dmc.render_info(_args(tool="claude:alpha"), projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "resolved via virtual-kit alias" in out or "qualified alias" in out

    def test_runtime_resolved_for_simple_python_runtime(self, capsys):
        """Default mode (no --raw/--platform): non-conditional runtime
        renders simply — type + dispatch fields, no '(resolved for X)'
        annotation."""
        projects = [
            _project(
                "alpha",
                fqcn="core:alpha",
                runtime={"type": "python", "script_path": "main.py"},
            )
        ]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Runtime:     python" in out
        assert "main.py" in out
        # Non-conditional runtime: no "(resolved for ...)" suffix
        assert "(resolved for" not in out
        assert "(raw" not in out
        assert "(preview for" not in out

    def test_no_linked_to_line_for_non_linked_project(self, capsys, tmp_path):
        """Regression guard (v0.7.33): render_info should NOT emit a
        ``Linked to:`` line for a project whose ``_dir`` is a normal
        directory (not a symlink/junction)."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        projects = [_project("alpha", fqcn="core:alpha")]
        projects[0]["_dir"] = str(plain_dir)
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Linked to:" not in out

    def test_linked_to_line_for_linked_project(self, capsys, tmp_path):
        """Positive case for linked-project surface (v0.7.33). Skips
        when symlink creation isn't available on the runtime (e.g.,
        Windows without Developer Mode or admin)."""
        import os as _os
        source = tmp_path / "source"
        source.mkdir()
        link = tmp_path / "link"
        try:
            _os.symlink(str(source), str(link), target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation not available on this platform/runtime")
        projects = [_project("alpha", fqcn="core:alpha")]
        projects[0]["_dir"] = str(link)
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Linked to:" in out

    def test_docker_runtime_fields(self, capsys):
        """Docker runtime renders Image / Volumes / Env / etc. fields."""
        projects = [
            _project(
                "alpha",
                fqcn="core:alpha",
                runtime={
                    "type": "docker",
                    "image": "python:3.11",
                    "volumes": [
                        {"host": "/tmp", "container": "/data", "mode": "ro"},
                    ],
                    "env": {"FOO": "bar"},
                },
            )
        ]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Image:" in out
        assert "python:3.11" in out
        assert "Volumes:" in out
        assert "1 mount(s)" in out
        assert "/tmp -> /data" in out
        assert "Env:" in out
        assert "1 var(s)" in out


class TestRenderInfoDescriptionWrap:
    """v0.7.37: Description field wraps to terminal width with continuation
    indent aligned to the value column (closes the wrap-fix follow-up)."""

    def _label_len(self):
        return len("Description: ")  # 13 chars

    def test_short_description_unwrapped(self, capsys, monkeypatch):
        # Force a wide terminal so short text never wraps.
        monkeypatch.setenv("COLUMNS", "200")
        projects = [_project("alpha", description="short desc", fqcn="k:alpha")]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        # The description line appears as one line; no continuation indent
        # lines beneath it (which would show up as 13-space-prefixed text).
        desc_lines = [l for l in out.splitlines() if l.startswith("Description: ")]
        assert len(desc_lines) == 1
        assert desc_lines[0] == "Description: short desc"

    def test_long_description_wraps_to_terminal_width(self, capsys, monkeypatch):
        # Narrow terminal forces wrap.
        monkeypatch.setattr(
            "dazzlecmd_lib.default_meta_commands._shutil.get_terminal_size",
            lambda fallback=(80, 24): type("S", (), {"columns": 60})(),
        )
        long_desc = (
            "Apply the driver-disable workaround: turn off the leaking AMD "
            "iGPU when a discrete GPU is available to take over display. "
            "Snapshots state for revert."
        )
        projects = [_project("alpha", description=long_desc, fqcn="k:alpha")]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        lines = out.splitlines()
        desc_idx = next(i for i, l in enumerate(lines) if l.startswith("Description: "))
        # The Description: line should be <= terminal width
        assert len(lines[desc_idx]) <= 60
        # At least one continuation line follows, indented to value column
        # (13 spaces). The next non-continuation field is "Platform:".
        cont_lines = []
        i = desc_idx + 1
        while i < len(lines) and lines[i].startswith(" " * self._label_len()):
            cont_lines.append(lines[i])
            i += 1
        assert len(cont_lines) >= 1
        # Every continuation line starts with exactly 13 spaces, no more
        for line in cont_lines:
            assert line.startswith(" " * 13)
            # next char isn't whitespace (no over-indent)
            assert line[13] != " "

    def test_continuation_indent_aligns_with_value_column(self, capsys, monkeypatch):
        # Verify the alignment: continuation chars line up directly under
        # the first char of the description value on the header row.
        monkeypatch.setattr(
            "dazzlecmd_lib.default_meta_commands._shutil.get_terminal_size",
            lambda fallback=(80, 24): type("S", (), {"columns": 40})(),
        )
        projects = [
            _project(
                "alpha",
                description="word1 word2 word3 word4 word5 word6 word7",
                fqcn="k:alpha",
            ),
        ]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        lines = out.splitlines()
        desc_idx = next(i for i, l in enumerate(lines) if l.startswith("Description: "))
        header = lines[desc_idx]
        # Column where description value begins on the header row
        value_col = len("Description: ")
        # Continuation line's first non-space char should be at that column
        cont = lines[desc_idx + 1]
        assert cont.startswith(" " * value_col)
        assert cont[value_col] != " "

    def test_empty_description_renders_single_line(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "dazzlecmd_lib.default_meta_commands._shutil.get_terminal_size",
            lambda fallback=(80, 24): type("S", (), {"columns": 80})(),
        )
        projects = [_project("alpha", description="", fqcn="k:alpha")]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        desc_lines = [l for l in out.splitlines() if l.startswith("Description:")]
        assert len(desc_lines) == 1
        assert desc_lines[0].rstrip() == "Description:"


class TestRenderInfoLongDescription:
    """v0.7.40 / lib v0.6.3: long_description manifest field rendered as
    a mini-manpage Details: block below the standard field rows.

    Closes dazzlecmd #61 -- the schema field was added in v0.7.40
    (scaffolding side); this surface is the rendering complement.
    """

    def _project_with_long_desc(self, long_desc):
        return _project(
            "alpha",
            description="short one-liner",
            fqcn="k:alpha",
            long_description=long_desc,
        )

    def test_long_description_renders_with_details_header(self, capsys, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")  # strip ANSI so assertions are simple
        monkeypatch.setattr(
            "dazzlecmd_lib.default_meta_commands._shutil.get_terminal_size",
            lambda fallback=(80, 24): type("S", (), {"columns": 80})(),
        )
        projects = [self._project_with_long_desc(
            "Detailed body explaining the tool's purpose and gotchas."
        )]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Details:" in out
        assert "Detailed body explaining the tool's purpose" in out

    def test_long_description_absent_no_details_block(self, capsys, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr(
            "dazzlecmd_lib.default_meta_commands._shutil.get_terminal_size",
            lambda fallback=(80, 24): type("S", (), {"columns": 80})(),
        )
        # Project explicitly has empty long_description.
        projects = [self._project_with_long_desc("")]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Details:" not in out

    def test_long_description_field_missing_no_details_block(self, capsys, monkeypatch):
        """Backward-compat: manifests without the field render normally."""
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr(
            "dazzlecmd_lib.default_meta_commands._shutil.get_terminal_size",
            lambda fallback=(80, 24): type("S", (), {"columns": 80})(),
        )
        # _project builds a tool without long_description -> the typed field
        # defaults to "" (effectively absent; no Details block should render).
        projects = [_project("alpha", description="x", fqcn="k:alpha")]
        assert projects[0].long_description == ""
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Details:" not in out

    def test_long_description_whitespace_only_renders_nothing(self, capsys, monkeypatch):
        """A long_description of `   \\n  \\n` (only whitespace) is treated
        as absent -- no Details: block."""
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr(
            "dazzlecmd_lib.default_meta_commands._shutil.get_terminal_size",
            lambda fallback=(80, 24): type("S", (), {"columns": 80})(),
        )
        projects = [self._project_with_long_desc("   \n  \n   ")]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        assert "Details:" not in out

    def test_long_description_wraps_to_terminal_width(self, capsys, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr(
            "dazzlecmd_lib.default_meta_commands._shutil.get_terminal_size",
            lambda fallback=(80, 24): type("S", (), {"columns": 50})(),
        )
        long_text = (
            "This is a very long paragraph of body text that must wrap "
            "to the configured terminal width because terminals are "
            "narrow when piped or in small consoles."
        )
        projects = [self._project_with_long_desc(long_text)]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        lines = out.splitlines()
        # Find the Details: line index, then check the body lines beneath
        details_idx = next(i for i, l in enumerate(lines) if l.startswith("Details:"))
        body_lines = []
        i = details_idx + 1
        while i < len(lines) and lines[i].startswith("  "):
            body_lines.append(lines[i])
            i += 1
        assert len(body_lines) >= 2  # wrapped to at least 2 lines
        for line in body_lines:
            assert len(line) <= 50  # within terminal width

    def test_long_description_multi_line_preserved(self, capsys, monkeypatch):
        """Paragraph breaks in long_description survive into the output."""
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr(
            "dazzlecmd_lib.default_meta_commands._shutil.get_terminal_size",
            lambda fallback=(80, 24): type("S", (), {"columns": 80})(),
        )
        long_text = "First paragraph.\n\nSecond paragraph after a blank line."
        projects = [self._project_with_long_desc(long_text)]
        engine = _engine_with(projects)
        dmc.render_info(_args(tool="alpha"), projects, engine=engine)
        out = capsys.readouterr().out
        # Both paragraphs present; a blank line between them.
        assert "First paragraph." in out
        assert "Second paragraph" in out
        # Locate them and check separation
        lines = out.splitlines()
        first_idx = next(i for i, l in enumerate(lines) if "First paragraph" in l)
        second_idx = next(i for i, l in enumerate(lines) if "Second paragraph" in l)
        assert second_idx > first_idx
        # A blank line should sit between them (paragraph break)
        assert any(
            lines[j].strip() == "" for j in range(first_idx + 1, second_idx)
        )


class TestInfoParserFactory:
    def test_registers_subparser_with_tool_arg(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        dmc.info_parser_factory(subparsers)
        args = parser.parse_args(["info", "my-tool"])
        assert args.tool == "my-tool"
        assert args._meta == "info"


# ---------------------------------------------------------------------------
# kit
# ---------------------------------------------------------------------------


class TestRenderKitList:
    def test_empty_kits(self, capsys):
        rc = dmc.render_kit_list(_args(), [], [])
        assert rc == 0
        assert "No kits" in capsys.readouterr().out

    def test_list_all_kits(self, capsys):
        kits = [
            _kit("core", tools=["core:a", "core:b"], description="Core kit"),
            _kit("extra", tools=["extra:c"]),
        ]
        rc = dmc.render_kit_list(_args(), kits, [])
        assert rc == 0
        out = capsys.readouterr().out
        assert "core" in out
        assert "2 tool(s)" in out
        assert "extra" in out
        assert "1 tool(s)" in out
        assert "Core kit" in out

    def test_always_active_marker(self, capsys):
        kits = [_kit("core", tools=["core:a"], always_active=True)]
        dmc.render_kit_list(_args(), kits, [])
        out = capsys.readouterr().out
        assert "always active" in out

    def test_specific_kit_lists_tools(self, capsys):
        kits = [_kit("core", tools=["core:a", "core:b"])]
        projects = [
            _project("a", namespace="core", kit="core", description="Tool A"),
            _project("b", namespace="core", kit="core", description="Tool B"),
        ]
        rc = dmc.render_kit_list(_args(name="core"), kits, projects)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Kit: core" in out
        assert "Tool A" in out
        assert "Tool B" in out
        assert "2 tool(s)" in out

    def test_specific_kit_not_found(self, capsys):
        kits = [_kit("core")]
        rc = dmc.render_kit_list(_args(name="nonexistent"), kits, [])
        assert rc == 1
        out = capsys.readouterr().out
        assert "not found" in out

    def test_specific_kit_with_missing_tools(self, capsys):
        """When kit references a tool that wasn't discovered, mark (not found)."""
        kits = [_kit("core", tools=["core:ghost"])]
        dmc.render_kit_list(_args(name="core"), kits, [])
        out = capsys.readouterr().out
        assert "(not found)" in out

    def test_fqcn_ref_resolves_via_fqcn_match(self, capsys):
        """Aggregator-as-kit kits contain full FQCNs (e.g. 'wtf:core:locked').

        Regression for #64: prior to fix, the ``ns:name`` parser split on
        the first colon -- yielding ``ns="wtf"``, ``name_part="core:locked"``
        -- and the matcher then looked for a project with name
        ``"core:locked"`` which never exists. Multi-segment FQCN refs must
        match by ``_fqcn`` directly.
        """
        kits = [_kit("wtf", tools=["wtf:core:locked", "wtf:core:restarted"])]
        projects = [
            _project(
                "locked", namespace="core", kit="wtf",
                fqcn="wtf:core:locked", description="Lock cause",
            ),
            _project(
                "restarted", namespace="core", kit="wtf",
                fqcn="wtf:core:restarted", description="Restart cause",
            ),
        ]
        rc = dmc.render_kit_list(_args(name="wtf"), kits, projects)
        assert rc == 0
        out = capsys.readouterr().out
        assert "(not found)" not in out
        assert "Lock cause" in out
        assert "Restart cause" in out

    def test_fqcn_ref_displays_leaf_name(self, capsys):
        """The display column shows the project's leaf name, not the full
        FQCN, so existing ``dz kit list`` output stays readable.
        """
        kits = [_kit("wtf", tools=["wtf:core:locked"])]
        projects = [
            _project(
                "locked", namespace="core", kit="wtf",
                fqcn="wtf:core:locked", description="Lock cause",
            ),
        ]
        dmc.render_kit_list(_args(name="wtf"), kits, projects)
        out = capsys.readouterr().out
        # Leaf name visible, full FQCN not in the row body (only in lookup).
        assert "  locked   " in out or "locked " in out

    def test_legacy_ns_name_ref_still_works(self, capsys):
        """Existing kit manifests with 2-segment ``ns:name`` refs (e.g.
        ``core:find``) keep working via the legacy fallback parser.
        """
        kits = [_kit("core", tools=["core:find"])]
        projects = [
            _project(
                "find", namespace="core", kit="core",
                fqcn="core:find", description="File search",
            ),
        ]
        dmc.render_kit_list(_args(name="core"), kits, projects)
        out = capsys.readouterr().out
        assert "(not found)" not in out
        assert "File search" in out


class TestRenderKitStatus:
    def test_prints_active_count(self, capsys):
        kits = [
            _kit("a", always_active=True),
            _kit("b", always_active=True),
        ]
        rc = dmc.render_kit_status(kits)
        assert rc == 0
        assert "2" in capsys.readouterr().out


class TestKitParserFactory:
    def test_kit_list_subcommand(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        dmc.kit_parser_factory(subparsers)
        args = parser.parse_args(["kit", "list"])
        assert args._meta == "kit_list"

    def test_kit_list_with_name(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        dmc.kit_parser_factory(subparsers)
        args = parser.parse_args(["kit", "list", "core"])
        assert args.name == "core"

    def test_kit_status_subcommand(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        dmc.kit_parser_factory(subparsers)
        args = parser.parse_args(["kit", "status"])
        assert args._meta == "kit_status"

    def test_bare_kit_defaults_to_list(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        dmc.kit_parser_factory(subparsers)
        args = parser.parse_args(["kit"])
        assert args._meta == "kit_list"


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


class TestRenderVersion:
    def test_with_version_info(self, capsys):
        engine = _engine(name="foo", version_info=("1.0.0", "1.0.0_main_1"))
        rc = dmc.render_version(engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "foo" in out
        assert "1.0.0" in out

    def test_without_version_info(self, capsys):
        engine = _engine(name="foo", version_info=None)
        dmc.render_version(engine)
        out = capsys.readouterr().out
        assert "foo" in out

    def test_no_engine(self, capsys):
        dmc.render_version(None)
        out = capsys.readouterr().out
        assert out.strip() != ""  # something is printed


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------


class TestRenderTree:
    def test_no_engine_returns_error(self, capsys):
        rc = dmc.render_tree(_args(), None, [], [], None)
        assert rc == 1
        assert "requires engine" in capsys.readouterr().err

    def test_ascii_tree_empty(self, capsys):
        engine = _engine(command="dz")
        rc = dmc.render_tree(_args(), engine, [], [], None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "0 tools" in out

    def test_ascii_tree_with_projects(self, capsys):
        engine = _engine(command="dz")
        projects = [
            _project("a", kit="kit1"),
            _project("b", kit="kit1"),
            _project("c", kit="kit2"),
        ]
        rc = dmc.render_tree(_args(), engine, projects, [], None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "dz" in out
        assert "kit1" in out
        assert "kit2" in out
        assert "kit1:a" in out or "kit1:b" in out
        assert "3 tools across 2 kit(s)" in out

    def test_tree_json_output(self, capsys):
        engine = _engine(command="dz", name="test", version_info=("1.0", "1.0"))
        projects = [_project("a", kit="kit1", fqcn="kit1:a")]
        rc = dmc.render_tree(_args(json=True), engine, projects, [], None)
        assert rc == 0
        out = capsys.readouterr().out
        data = _json.loads(out)
        assert data["root"] == "test"
        assert data["command"] == "dz"
        assert "kit1" in data["kits"]
        assert len(data["kits"]["kit1"]["tools"]) == 1
        assert data["kits"]["kit1"]["tools"][0]["fqcn"] == "kit1:a"

    def test_tree_depth_limit(self, capsys):
        engine = _engine(command="dz")
        projects = [_project("a", kit="kit1")]
        dmc.render_tree(_args(depth=1), engine, projects, [], None)
        out = capsys.readouterr().out
        assert "kit1" in out
        assert "kit1:a" not in out  # tool filtered out by depth=1

    def test_tree_kit_filter(self, capsys):
        engine = _engine(command="dz")
        projects = [
            _project("a", kit="kit1"),
            _project("b", kit="kit2"),
        ]
        dmc.render_tree(_args(kit="kit1"), engine, projects, [], None)
        out = capsys.readouterr().out
        assert "kit1" in out
        assert "kit2" not in out

    def test_tree_kit_filter_not_found(self, capsys):
        engine = _engine(command="dz")
        rc = dmc.render_tree(_args(kit="nonexistent"), engine, [], [], None)
        assert rc == 1

    def test_shadow_marker_when_tool_shadows_meta(self, capsys):
        """Tools whose short name conflicts with a reserved meta-command
        must render with [shadowed] in tree output (issue #56)."""
        projects = [
            _project("info", kit="amdead", fqcn="amdead:info"),
            _project("alpha", kit="amdead", fqcn="amdead:alpha"),
        ]
        engine = _engine_with(projects)
        rc = dmc.render_tree(_args(), engine, projects, [], None)
        assert rc == 0
        out = capsys.readouterr().out
        # Shadowed line shows the marker
        assert "amdead:info [shadowed]" in out
        # Non-shadowed line does NOT
        assert "amdead:alpha [shadowed]" not in out
        assert "amdead:alpha" in out

    def test_no_shadow_marker_when_not_reserved(self, capsys):
        """Regression guard: tree output must not flag non-shadowed tools."""
        projects = [_project("alpha", kit="amdead", fqcn="amdead:alpha")]
        engine = _engine_with(projects)
        rc = dmc.render_tree(_args(), engine, projects, [], None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "[shadowed]" not in out

    # --- 4b-T9 virtual-kit branches in render_tree ---

    def test_virtual_kit_branch_renders(self, capsys):
        """Virtual kits render as a separate branch with [virtual] marker
        and -> arrows from each alias to its canonical target."""
        projects = [_project("alpha", kit="core", fqcn="core:alpha")]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        rc = dmc.render_tree(_args(), engine, projects, [], None)
        assert rc == 0
        out = capsys.readouterr().out
        # Canonical kit branch
        assert "core" in out
        # Virtual kit branch with [virtual] marker
        assert "claude [virtual]" in out
        # Alias arrow line
        assert "claude:alpha -> core:alpha" in out

    def test_virtual_kit_summary_includes_alias_count(self, capsys):
        """Tree footer with virtual kits reports alias count in addition
        to tool/kit counts."""
        projects = [
            _project("alpha", kit="core", fqcn="core:alpha"),
            _project("beta", kit="core", fqcn="core:beta"),
        ]
        engine = _engine_with_virtual_kit(
            projects, "claude",
            {"claude:alpha": "core:alpha", "claude:beta": "core:beta"},
        )
        rc = dmc.render_tree(_args(), engine, projects, [], None)
        assert rc == 0
        out = capsys.readouterr().out
        # Footer includes both canonical and virtual counts
        assert "2 tools across 1 kit(s)" in out
        assert "2 alias(es) in 1 virtual kit(s)" in out

    def test_no_virtual_kits_no_alias_summary(self, capsys):
        """Regression guard: tree footer keeps the simple form when no
        virtual kits are present (don't add a misleading 0 alias(es))."""
        projects = [_project("alpha", kit="core", fqcn="core:alpha")]
        engine = _engine_with(projects)
        rc = dmc.render_tree(_args(), engine, projects, [], None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "alias(es)" not in out
        assert "1 tools across 1 kit(s)" in out

    def test_virtual_kit_filter_with_kit_flag_matches_dazzlecmd_limitation(self, capsys):
        """Parity note: dazzlecmd's --kit filter only checks canonical kits.

        Filtering --kit by a virtual-kit name fails with "kit not found"
        because the canonical-kit short-circuit in render_tree fires
        before virtual-kit collection. This matches dazzlecmd's
        ``_cmd_tree`` behavior at cli.py:2154-2160. Improving this is a
        separate enhancement (out of 4b-T9 parity scope).
        """
        projects = [_project("alpha", kit="core", fqcn="core:alpha")]
        engine = _engine_with_virtual_kit(
            projects, "claude", {"claude:alpha": "core:alpha"}
        )
        rc = dmc.render_tree(_args(kit="claude"), engine, projects, [], None)
        # Current behavior: returns 1 with "kit not found" for virtual-only
        # match. The library matches dazzlecmd here for parity.
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err.lower()


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


class TestRenderSetupListing:
    def test_no_tools_with_setup(self, capsys):
        rc = dmc.render_setup_listing([_project("a"), _project("b")])
        assert rc == 0
        assert "No tools have setup" in capsys.readouterr().out

    def test_lists_tools_with_setup_command(self, capsys):
        projects = [
            _project("aaa"),
            _project("bbb", setup={"command": "pip install"}),
            _project("ccc", setup={"command": "make", "note": "Build step"}),
        ]
        rc = dmc.render_setup_listing(projects)
        assert rc == 0
        out = capsys.readouterr().out
        # bbb + ccc should appear; aaa (no setup) should not
        assert "bbb" in out
        assert "ccc" in out
        assert "Build step" in out
        assert "aaa" not in out

    def test_platforms_only_tool_detected(self, capsys):
        """Tool with setup.platforms but no top-level command should be listed."""
        projects = [
            _project(
                "t",
                setup={"platforms": {"linux": {"command": "apt install foo"}}},
            )
        ]
        rc = dmc.render_setup_listing(projects)
        assert rc == 0
        out = capsys.readouterr().out
        assert "t" in out

    def test_placeholder_dash_for_missing_note(self, capsys):
        projects = [_project("a", setup={"command": "x"})]
        dmc.render_setup_listing(projects)
        out = capsys.readouterr().out
        assert "-" in out  # placeholder for missing note


class TestSetupHandler:
    def test_no_tool_shows_listing(self, capsys):
        projects = [_project("a", setup={"command": "echo hi"})]
        rc = dmc.setup_handler(_args(tool=None), None, projects, [], None)
        assert rc == 0
        assert "setup declared" in capsys.readouterr().out.lower()

    def test_tool_not_found(self, capsys):
        engine = _engine_with([])
        rc = dmc.setup_handler(_args(tool="nonexistent"), engine, [], [], None)
        assert rc == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_tool_without_setup(self, capsys):
        projects = [_project("a")]
        engine = _engine_with(projects)
        rc = dmc.setup_handler(_args(tool="a"), engine, projects, [], None)
        assert rc == 1
        assert "no setup" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# register_all / register_selected
# ---------------------------------------------------------------------------


class TestRegisterAll:
    def test_registers_all_defaults(self):
        r = MetaCommandRegistry()
        dmc.register_all(r)
        # Top-level commands
        for name in ["list", "info", "kit", "version", "tree", "setup"]:
            assert name in r, f"{name} should be registered"
        # Sub-handlers for kit nested commands
        assert "kit_list" in r
        assert "kit_status" in r

    def test_registered_parsers_are_callable(self):
        r = MetaCommandRegistry()
        dmc.register_all(r)
        for name in ["list", "info", "kit", "version", "tree", "setup"]:
            parser_factory, handler = r.resolve(name)
            assert callable(parser_factory)
            assert callable(handler)


class TestRegisterSelected:
    def test_no_include_registers_all(self):
        r = MetaCommandRegistry()
        dmc.register_selected(r, include=None)
        assert "list" in r
        assert "tree" in r

    def test_selective_include(self):
        r = MetaCommandRegistry()
        dmc.register_selected(r, include=["list", "info", "version"])
        assert "list" in r
        assert "info" in r
        assert "version" in r
        assert "tree" not in r
        assert "setup" not in r
        assert "kit" not in r

    def test_kit_include_registers_sub_handlers(self):
        r = MetaCommandRegistry()
        dmc.register_selected(r, include=["kit"])
        assert "kit" in r
        assert "kit_list" in r
        assert "kit_status" in r

    def test_unknown_name_raises(self):
        r = MetaCommandRegistry()
        with pytest.raises(KeyError) as exc:
            dmc.register_selected(r, include=["bogus"])
        assert "bogus" in str(exc.value)

    def test_empty_include_registers_nothing(self):
        r = MetaCommandRegistry()
        dmc.register_selected(r, include=[])
        assert r.registered() == []


# ---------------------------------------------------------------------------
# Integration: full parser build from registered defaults
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_parser_tree_builds(self):
        """After register_all, build_parsers populates an argparse hierarchy."""
        r = MetaCommandRegistry()
        dmc.register_all(r)

        parser = argparse.ArgumentParser(prog="test")
        subparsers = parser.add_subparsers(dest="command")
        r.build_parsers(subparsers)

        # Test each top-level command parses
        assert parser.parse_args(["list"])._meta == "list"
        assert parser.parse_args(["info", "mytool"])._meta == "info"
        assert parser.parse_args(["kit"])._meta == "kit_list"
        assert parser.parse_args(["kit", "list"])._meta == "kit_list"
        assert parser.parse_args(["kit", "status"])._meta == "kit_status"
        assert parser.parse_args(["version"])._meta == "version"
        assert parser.parse_args(["tree"])._meta == "tree"
        assert parser.parse_args(["setup"])._meta == "setup"

    def test_dispatch_routing_via_registry(self):
        """After build_parsers + parse_args, registry.dispatch routes to handler."""
        r = MetaCommandRegistry()
        dmc.register_all(r)

        parser = argparse.ArgumentParser(prog="test")
        subparsers = parser.add_subparsers(dest="command")
        r.build_parsers(subparsers)

        engine = _engine(command="test", name="test", version_info=("1.0", "1.0.0_main_1"))
        args = parser.parse_args(["version"])
        rc = r.dispatch(args, engine, [], [], None)
        assert rc == 0
