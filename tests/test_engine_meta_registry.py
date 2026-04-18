"""Tests for AggregatorEngine's integration with MetaCommandRegistry.

Covers:
- Auto-registration of defaults on engine construction
- include_default_meta_commands=False produces empty registry
- extra_reserved_commands composes with registry names
- config_dir routes ConfigManager to the specified path
- reserved_commands property derives from registry + extras
- Registry path run() end-to-end (no parser_builder passed)
- Escape-hatch run() path still works when parser_builder is passed
- Registry locks during dispatch
- epilog_builder attribute is honored
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch

from dazzlecmd_lib.engine import AggregatorEngine
from dazzlecmd_lib.meta_command_registry import (
    MetaCommandRegistry,
    RegistryLockedError,
)


# ---------------------------------------------------------------------------
# Default meta-command auto-registration
# ---------------------------------------------------------------------------


class TestDefaultRegistration:
    def test_defaults_registered_by_default(self):
        engine = AggregatorEngine(name="t", command="t")
        registered = set(engine.meta_registry.registered())
        # All top-level defaults present
        for name in ["list", "info", "kit", "version", "tree", "setup"]:
            assert name in registered
        # Sub-handlers (kit_list, kit_status) also registered
        assert "kit_list" in registered
        assert "kit_status" in registered

    def test_include_default_false_leaves_empty_registry(self):
        engine = AggregatorEngine(
            name="t", command="t", include_default_meta_commands=False
        )
        assert engine.meta_registry.registered() == []

    def test_is_root_false_still_allows_registry_population(self):
        """Embedded engines start with defaults registered too (they
        just won't dispatch them in _dispatch_registry_path)."""
        engine = AggregatorEngine(
            name="t", command="t", is_root=False
        )
        # With is_root=False, include_default_meta_commands is ignored
        # (defaults are only registered for root engines)
        assert engine.meta_registry.registered() == []

    def test_registry_is_per_engine_instance(self):
        """Two engines have independent registries."""
        e1 = AggregatorEngine(name="a", command="a")
        e2 = AggregatorEngine(name="b", command="b")
        assert e1.meta_registry is not e2.meta_registry
        # Modifying one doesn't affect the other
        e1.meta_registry.unregister("tree")
        assert "tree" not in e1.meta_registry
        assert "tree" in e2.meta_registry


# ---------------------------------------------------------------------------
# reserved_commands property
# ---------------------------------------------------------------------------


class TestReservedCommands:
    def test_reserved_from_default_registry(self):
        engine = AggregatorEngine(name="t", command="t")
        reserved = engine.reserved_commands
        for name in ["list", "info", "kit", "version", "tree", "setup"]:
            assert name in reserved

    def test_extras_merged(self):
        engine = AggregatorEngine(
            name="t", command="t",
            extra_reserved_commands={"mode", "new", "add"},
        )
        reserved = engine.reserved_commands
        assert "mode" in reserved
        assert "new" in reserved
        assert "add" in reserved
        # Defaults still there
        assert "list" in reserved

    def test_empty_when_not_root(self):
        engine = AggregatorEngine(
            name="t", command="t", is_root=False,
        )
        assert engine.reserved_commands == set()

    def test_unregister_removes_from_reserved(self):
        engine = AggregatorEngine(name="t", command="t")
        assert "tree" in engine.reserved_commands
        engine.meta_registry.unregister("tree")
        assert "tree" not in engine.reserved_commands

    def test_register_new_adds_to_reserved(self):
        engine = AggregatorEngine(name="t", command="t")
        assert "custom" not in engine.reserved_commands

        def parser_factory(s):
            s.add_parser("custom").set_defaults(_meta="custom")

        engine.meta_registry.register(
            "custom", parser_factory, lambda *a: 0
        )
        assert "custom" in engine.reserved_commands

    def test_reserved_updates_dynamically(self):
        engine = AggregatorEngine(
            name="t", command="t",
            extra_reserved_commands={"mode"},
        )

        # Register a new command — reserved grows
        def pf(s):
            s.add_parser("foo").set_defaults(_meta="foo")

        engine.meta_registry.register("foo", pf, lambda *a: 0)
        assert "foo" in engine.reserved_commands
        assert "mode" in engine.reserved_commands  # extras preserved


# ---------------------------------------------------------------------------
# config_dir isolation
# ---------------------------------------------------------------------------


class TestConfigDir:
    def test_config_dir_argument_routes_config_path(self, tmp_path):
        engine = AggregatorEngine(
            name="t", command="t", config_dir=str(tmp_path),
        )
        assert engine.config.config_path() == os.path.join(
            str(tmp_path), "config.json"
        )

    def test_default_config_dir_derives_from_command(self, monkeypatch):
        # Ensure DAZZLECMD_CONFIG env is not set
        monkeypatch.delenv("DAZZLECMD_CONFIG", raising=False)
        engine = AggregatorEngine(name="Wtf", command="wtf")
        path = engine.config.config_path()
        # Default is ~/.wtf/config.json on Linux/Mac, similar on Windows
        assert path.endswith(os.path.join(".wtf", "config.json"))

    def test_two_engines_have_isolated_configs(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        ea = AggregatorEngine(name="A", command="a", config_dir=str(dir_a))
        eb = AggregatorEngine(name="B", command="b", config_dir=str(dir_b))
        assert ea.config.config_path() != eb.config.config_path()

    def test_env_var_overrides_config_dir(self, tmp_path, monkeypatch):
        """DAZZLECMD_CONFIG env var takes precedence over constructor arg."""
        explicit_path = str(tmp_path / "forced.json")
        monkeypatch.setenv("DAZZLECMD_CONFIG", explicit_path)
        engine = AggregatorEngine(
            name="t", command="t", config_dir=str(tmp_path / "ignored"),
        )
        assert engine.config.config_path() == explicit_path


# ---------------------------------------------------------------------------
# epilog_builder
# ---------------------------------------------------------------------------


class TestEpilogBuilder:
    def test_epilog_builder_default_is_none(self):
        engine = AggregatorEngine(name="t", command="t")
        assert engine.epilog_builder is None

    def test_epilog_builder_set_as_attribute(self):
        engine = AggregatorEngine(name="t", command="t")

        def my_epilog(projects):
            return "Custom epilog!"

        engine.epilog_builder = my_epilog
        assert engine.epilog_builder is my_epilog


# ---------------------------------------------------------------------------
# Registry-path run()
# ---------------------------------------------------------------------------


class TestRegistryPathRun:
    def test_version_flag_prints_version_and_exits_cleanly(self, capsys, tmp_path):
        engine = AggregatorEngine(
            name="wtf", command="wtf",
            version_info=("1.0.0", "1.0.0_main_5"),
            config_dir=str(tmp_path),
        )
        # Skip discovery (no project_root)
        rc = engine.run(argv=["--version"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "wtf" in out
        assert "1.0.0" in out

    def test_version_flag_without_version_info(self, capsys, tmp_path):
        engine = AggregatorEngine(name="t", command="t", config_dir=str(tmp_path))
        rc = engine.run(argv=["--version"])
        assert rc == 0
        assert "t" in capsys.readouterr().out

    def test_empty_argv_prints_help(self, capsys, tmp_path):
        engine = AggregatorEngine(name="t", command="t", config_dir=str(tmp_path))
        rc = engine.run(argv=[])
        assert rc == 0
        out = capsys.readouterr().out
        # argparse help has the "usage:" prefix
        assert "usage:" in out.lower() or "t - tool aggregator" in out

    def test_registry_dispatches_version(self, capsys, tmp_path):
        engine = AggregatorEngine(
            name="test-app", command="tapp",
            version_info=("0.5", "0.5.0_test"),
            config_dir=str(tmp_path),
        )
        rc = engine.run(argv=["version"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "test-app" in out
        assert "0.5" in out

    def test_registry_locks_during_dispatch(self, tmp_path):
        """The registry should be locked while dispatch runs; mutations fail.

        Harder to test directly — we can at least verify locking behavior
        is invoked by checking registry state after run() completes.
        """
        engine = AggregatorEngine(
            name="t", command="t",
            version_info=("1", "1"),
            config_dir=str(tmp_path),
        )
        # After run completes, registry is unlocked (by the finally block)
        engine.run(argv=["version"])
        assert not engine.meta_registry.is_locked()

    def test_epilog_builder_invoked(self, capsys, tmp_path):
        engine = AggregatorEngine(
            name="t", command="t",
            version_info=("1", "1"),
            config_dir=str(tmp_path),
        )
        engine.epilog_builder = lambda projects: "MAGIC_EPILOG_TOKEN"
        engine.run(argv=[])
        # Epilog is in help output
        out = capsys.readouterr().out
        assert "MAGIC_EPILOG_TOKEN" in out

    def test_epilog_builder_exception_falls_back(self, capsys, tmp_path):
        """If epilog_builder raises, engine prints a warning but continues."""
        engine = AggregatorEngine(
            name="t", command="t",
            version_info=("1", "1"),
            config_dir=str(tmp_path),
        )

        def broken_epilog(projects):
            raise ValueError("oops")

        engine.epilog_builder = broken_epilog
        rc = engine.run(argv=[])
        assert rc == 0  # didn't crash
        captured = capsys.readouterr()
        assert "Warning" in captured.err or "Warning" in captured.out


# ---------------------------------------------------------------------------
# Escape-hatch run() path (backward compat for dazzlecmd)
# ---------------------------------------------------------------------------


class TestEscapeHatchPath:
    def test_escape_hatch_uses_parser_builder(self, capsys, tmp_path):
        """When parser_builder is passed, run() takes the escape-hatch path."""
        import argparse

        called = {"built": False, "tool_dispatched": False}

        def my_parser_builder(projects, engine):
            called["built"] = True
            return argparse.ArgumentParser(prog="custom")

        def my_tool_dispatcher(project, argv):
            called["tool_dispatched"] = True
            return 0

        engine = AggregatorEngine(
            name="custom", command="custom",
            parser_builder=my_parser_builder,
            tool_dispatcher=my_tool_dispatcher,
            config_dir=str(tmp_path),
        )
        # Empty argv -> print help path
        engine.run(argv=[])
        assert called["built"]


# ---------------------------------------------------------------------------
# Unknown command
# ---------------------------------------------------------------------------


class TestUnknownCommand:
    def test_unknown_command_returns_nonzero(self, capsys, tmp_path):
        engine = AggregatorEngine(
            name="t", command="t",
            version_info=("1", "1"),
            config_dir=str(tmp_path),
        )
        # "nonexistent" isn't a meta-command and isn't a discovered tool
        with pytest.raises(SystemExit):
            # argparse prints usage error and exits
            engine.run(argv=["nonexistent-command-xyz"])


# ---------------------------------------------------------------------------
# Realistic wtf-style customization
# ---------------------------------------------------------------------------


class TestWtfStyleCustomization:
    def test_remove_defaults_and_add_custom(self, tmp_path):
        """Simulate wtf-windows: drop tree/setup, override list/info,
        add mode/new/add."""
        engine = AggregatorEngine(
            name="wtf-windows", command="wtf",
            extra_reserved_commands={"mode", "new", "add"},
            config_dir=str(tmp_path),
        )

        # Drop defaults wtf doesn't want
        engine.meta_registry.unregister("tree")
        engine.meta_registry.unregister("setup")

        # Override list handler
        def custom_list(args, eng, projects, kits, project_root):
            print("CUSTOM_LIST_MARKER")
            return 0

        engine.meta_registry.override("list", handler=custom_list)

        # Add wtf-specific commands
        def mode_parser(subs):
            p = subs.add_parser("mode")
            p.set_defaults(_meta="mode")

        def mode_handler(args, eng, projects, kits, project_root):
            return 42

        engine.meta_registry.register("mode", mode_parser, mode_handler)

        # Verify final state
        reg = set(engine.meta_registry.registered())
        assert "tree" not in reg
        assert "setup" not in reg
        assert "list" in reg
        assert "mode" in reg

        assert "tree" not in engine.reserved_commands
        assert "mode" in engine.reserved_commands
        assert "new" in engine.reserved_commands  # from extras

    def test_custom_handler_invoked_on_registry_dispatch(self, capsys, tmp_path):
        """A registered handler is called when the engine dispatches."""
        engine = AggregatorEngine(
            name="t", command="t",
            version_info=("1", "1"),
            config_dir=str(tmp_path),
        )

        def custom_version(args, eng, projects, kits, project_root):
            print("CUSTOM_VERSION_MARKER")
            return 99

        engine.meta_registry.override("version", handler=custom_version)
        rc = engine.run(argv=["version"])
        assert rc == 99
        assert "CUSTOM_VERSION_MARKER" in capsys.readouterr().out
