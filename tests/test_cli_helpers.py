"""Tests for dazzlecmd_lib.cli_helpers — CLI scaffolding helpers."""

from __future__ import annotations

import argparse
import pytest

from dazzlecmd_lib import cli_helpers as h
from dazzlecmd_lib.meta_command_registry import MetaCommandRegistry


# ---------------------------------------------------------------------------
# build_tool_subparsers
# ---------------------------------------------------------------------------


class TestBuildToolSubparsers:
    def test_registers_one_subparser_per_tool(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        projects = [
            {"name": "alpha", "description": "First"},
            {"name": "beta", "description": "Second"},
        ]
        result = h.build_tool_subparsers(subparsers, projects)
        assert len(result) == 2

        # Each subparser should have _project set
        args = parser.parse_args(["alpha"])
        assert args._project["name"] == "alpha"

        args = parser.parse_args(["beta"])
        assert args._project["name"] == "beta"

    def test_skips_reserved_commands(self, capsys):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        projects = [
            {"name": "list", "description": "conflicts!"},
            {"name": "mytool", "description": "OK"},
        ]
        result = h.build_tool_subparsers(
            subparsers, projects, reserved_commands={"list"}
        )
        assert len(result) == 1
        # Warning on stderr
        assert "reserved" in capsys.readouterr().err.lower()

    def test_warn_on_conflict_false_suppresses_warning(self, capsys):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        projects = [{"name": "list"}]
        h.build_tool_subparsers(
            subparsers, projects,
            reserved_commands={"list"},
            warn_on_conflict=False,
        )
        assert capsys.readouterr().err == ""

    def test_duplicate_names_skipped(self):
        """Same short name across kits — register first, skip subsequent."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        projects = [
            {"name": "shared", "description": "First"},
            {"name": "shared", "description": "Second"},  # duplicate
        ]
        result = h.build_tool_subparsers(subparsers, projects)
        # Only one subparser registered (first wins)
        assert len(result) == 1

    def test_skips_projects_without_name(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        projects = [
            {"description": "no name"},
            {"name": "ok"},
        ]
        result = h.build_tool_subparsers(subparsers, projects)
        assert len(result) == 1

    def test_empty_projects_is_noop(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        result = h.build_tool_subparsers(subparsers, [])
        assert result == []

    def test_reserved_defaults_to_empty(self):
        """If reserved_commands not passed, nothing is reserved."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        projects = [{"name": "list"}]  # would conflict if reserved
        result = h.build_tool_subparsers(subparsers, projects)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# derive_reserved_from_registry
# ---------------------------------------------------------------------------


class TestDeriveReservedFromRegistry:
    def test_empty_registry_returns_empty_set(self):
        r = MetaCommandRegistry()
        assert h.derive_reserved_from_registry(r) == set()

    def test_returns_registered_names(self):
        r = MetaCommandRegistry()
        r.register("list", lambda s: None, lambda *a: 0)
        r.register("info", lambda s: None, lambda *a: 0)
        assert h.derive_reserved_from_registry(r) == {"list", "info"}

    def test_includes_extras(self):
        r = MetaCommandRegistry()
        r.register("list", lambda s: None, lambda *a: 0)
        result = h.derive_reserved_from_registry(r, extras={"enhance", "graduate"})
        assert result == {"list", "enhance", "graduate"}

    def test_none_registry_returns_extras_only(self):
        result = h.derive_reserved_from_registry(None, extras={"foo"})
        assert result == {"foo"}

    def test_none_registry_no_extras_returns_empty(self):
        assert h.derive_reserved_from_registry(None) == set()


# ---------------------------------------------------------------------------
# add_version_flag
# ---------------------------------------------------------------------------


class TestAddVersionFlag:
    def test_with_version_info(self, capsys):
        parser = argparse.ArgumentParser()
        h.add_version_flag(
            parser, version_info=("1.0.0", "1.0.0_main_5"), app_name="myapp"
        )
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])
        out = capsys.readouterr().out
        assert "myapp" in out
        assert "1.0.0" in out

    def test_without_version_info(self, capsys):
        parser = argparse.ArgumentParser()
        h.add_version_flag(parser, version_info=None, app_name="myapp")
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])
        out = capsys.readouterr().out
        assert "myapp" in out

    def test_short_flag_works(self, capsys):
        parser = argparse.ArgumentParser()
        h.add_version_flag(parser, version_info=("1.0", "1.0.0"), app_name="x")
        with pytest.raises(SystemExit):
            parser.parse_args(["-V"])
        out = capsys.readouterr().out
        assert "1.0" in out

    def test_none_parser_is_noop(self):
        h.add_version_flag(None, version_info=("1", "1"))  # should not raise


# ---------------------------------------------------------------------------
# default_epilog_for
# ---------------------------------------------------------------------------


class TestDefaultEpilogFor:
    def test_includes_app_name(self):
        s = h.default_epilog_for("myapp", 5, 2)
        assert "myapp" in s
        assert "5 tool(s)" in s
        assert "2 kit(s)" in s

    def test_no_kits(self):
        s = h.default_epilog_for("myapp", 5)
        assert "5 tool(s)" in s
        assert "kit(s)" not in s

    def test_zero_tools(self):
        s = h.default_epilog_for("myapp", 0)
        assert "tool(s)" not in s
        assert "myapp" in s
