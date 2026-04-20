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
    return {
        "name": name,
        "namespace": namespace,
        "_kit_import_name": kit,
        "_fqcn": fqcn or f"{kit}:{name}",
        "_dir": f"/tmp/{kit}/{name}",
        "description": description,
        "platform": platform,
        **extra,
    }


def _kit(name, tools=None, description="", always_active=False):
    return {
        "name": name,
        "_kit_name": name,
        "description": description,
        "tools": tools or [],
        "always_active": always_active,
    }


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
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _engine_with(projects):
    """Build a minimal AggregatorEngine with projects indexed.

    render_info / setup_handler now require ``engine`` (rule 7c relaxation +
    alias-blindness audit, v0.7.28). Tests build a real engine with
    canonical projects inserted; no virtual kits unless explicitly added.
    """
    from dazzlecmd_lib.engine import AggregatorEngine
    engine = AggregatorEngine(is_root=True)
    engine.projects = list(projects)
    for p in projects:
        p.setdefault("_short_name", p["name"])
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
        err = capsys.readouterr().err
        assert "not found" in err.lower()

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
