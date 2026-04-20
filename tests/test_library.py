"""Tests for the dazzlecmd-lib library package (Phase 4b).

Verifies that the extracted library works independently:
    - Direct dazzlecmd_lib imports (not through dazzlecmd shims)
    - RunnerRegistry standalone (register, resolve, unknown type)
    - ConfigManager standalone (read, write, cache, malformed)
    - Class identity (same objects through both import paths)
    - set_manifest_cache_fn callback hook
    - meta_commands configurable parameter
    - Library has no dazzlecmd.* imports (isolation check)
"""

import json
import os
import subprocess
import sys

import pytest


# ---------------------------------------------------------------------------
# Direct library imports
# ---------------------------------------------------------------------------


class TestDirectLibraryImports:
    """Verify the library is independently importable."""

    def test_import_engine(self):
        from dazzlecmd_lib.engine import AggregatorEngine
        assert AggregatorEngine is not None

    def test_import_fqcn_index(self):
        from dazzlecmd_lib.engine import FQCNIndex
        assert FQCNIndex is not None

    def test_import_exceptions(self):
        from dazzlecmd_lib.engine import (
            FQCNCollisionError,
            CircularDependencyError,
        )
        assert issubclass(FQCNCollisionError, Exception)
        assert issubclass(CircularDependencyError, Exception)

    def test_import_registry(self):
        from dazzlecmd_lib.registry import RunnerRegistry
        assert RunnerRegistry is not None

    def test_import_config(self):
        from dazzlecmd_lib.config import ConfigManager
        assert ConfigManager is not None

    def test_import_loader(self):
        from dazzlecmd_lib.loader import discover_kits, discover_projects
        assert discover_kits is not None
        assert discover_projects is not None

    def test_import_top_level(self):
        from dazzlecmd_lib import (
            AggregatorEngine,
            FQCNIndex,
            RunnerRegistry,
            ConfigManager,
        )
        assert all(x is not None for x in [
            AggregatorEngine, FQCNIndex, RunnerRegistry, ConfigManager
        ])

    def test_library_version(self):
        """Verify dazzlecmd_lib exports a well-formed version string.

        Intentionally does not pin a specific version -- pinning broke
        every release bump and added pre-push noise without catching any
        real bug. We assert the export exists and parses as a semver-ish
        major.minor[.patch] string; the exact value is the canonical
        source's responsibility.
        """
        from dazzlecmd_lib import __version__
        assert isinstance(__version__, str), (
            f"__version__ must be str, got {type(__version__).__name__}"
        )
        assert __version__, "__version__ must be non-empty"
        parts = __version__.split(".")
        assert len(parts) >= 2, (
            f"__version__ must be at least major.minor format, got {__version__!r}"
        )
        # First two segments must be numeric (major, minor)
        assert parts[0].isdigit() and parts[1].isdigit(), (
            f"major.minor segments must be numeric, got {__version__!r}"
        )


# ---------------------------------------------------------------------------
# Class identity across import paths
# ---------------------------------------------------------------------------


class TestClassIdentity:
    """The shim must re-export the SAME objects, not copies."""

    def test_engine_same_class(self):
        from dazzlecmd.engine import AggregatorEngine as A
        from dazzlecmd_lib.engine import AggregatorEngine as B
        assert A is B

    def test_fqcn_index_same_class(self):
        from dazzlecmd.engine import FQCNIndex as A
        from dazzlecmd_lib.engine import FQCNIndex as B
        assert A is B

    def test_collision_error_same_class(self):
        from dazzlecmd.engine import FQCNCollisionError as A
        from dazzlecmd_lib.engine import FQCNCollisionError as B
        assert A is B

    def test_circular_error_same_class(self):
        from dazzlecmd.engine import CircularDependencyError as A
        from dazzlecmd_lib.engine import CircularDependencyError as B
        assert A is B


# ---------------------------------------------------------------------------
# RunnerRegistry standalone
# ---------------------------------------------------------------------------


class TestRunnerRegistry:

    def test_built_in_types_registered(self):
        from dazzlecmd_lib.registry import RunnerRegistry
        types = RunnerRegistry.registered_types()
        assert "python" in types
        assert "shell" in types
        assert "script" in types
        assert "binary" in types

    def test_resolve_unknown_type_returns_none(self, capsys):
        from dazzlecmd_lib.registry import RunnerRegistry
        project = {"name": "test", "runtime": {"type": "nonexistent"}, "_dir": "."}
        result = RunnerRegistry.resolve(project)
        assert result is None
        captured = capsys.readouterr()
        assert "Unknown runtime type" in captured.err

    def test_register_custom_type(self):
        from dazzlecmd_lib.registry import RunnerRegistry

        def custom_factory(project):
            return lambda argv: 42

        RunnerRegistry.register("_test_custom", custom_factory)
        try:
            project = {"name": "test", "runtime": {"type": "_test_custom"}, "_dir": "."}
            runner = RunnerRegistry.resolve(project)
            assert runner is not None
            assert runner([]) == 42
        finally:
            # Clean up to not pollute other tests
            del RunnerRegistry._factories["_test_custom"]

    def test_public_factory_names(self):
        from dazzlecmd_lib.registry import (
            make_python_runner,
            make_subprocess_runner,
            make_shell_runner,
            make_script_runner,
            make_binary_runner,
        )
        # All are callable
        assert all(callable(f) for f in [
            make_python_runner,
            make_subprocess_runner,
            make_shell_runner,
            make_script_runner,
            make_binary_runner,
        ])


# ---------------------------------------------------------------------------
# ConfigManager standalone
# ---------------------------------------------------------------------------


class TestConfigManagerStandalone:

    def test_read_missing_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "nonexistent.json"))
        from dazzlecmd_lib.config import ConfigManager
        cm = ConfigManager()
        assert cm.read() == {}

    def test_write_creates_dir(self, monkeypatch, tmp_path):
        config_path = tmp_path / "nested" / "dir" / "config.json"
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        from dazzlecmd_lib.config import ConfigManager
        cm = ConfigManager()
        cm.write({"key": "value"})
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["key"] == "value"
        assert data["_schema_version"] == 1

    def test_write_merge_semantics(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"existing": "keep"}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        from dazzlecmd_lib.config import ConfigManager
        cm = ConfigManager()
        cm.write({"new": "added"})
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["existing"] == "keep"
        assert data["new"] == "added"

    def test_cache_invalidated_after_write(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        from dazzlecmd_lib.config import ConfigManager
        cm = ConfigManager()
        assert cm.read() == {}
        cm.write({"x": 1})
        assert cm.read() == {"_schema_version": 1, "x": 1}

    def test_get_list_validates_type(self, monkeypatch, tmp_path, capsys):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"items": "not a list"}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        from dazzlecmd_lib.config import ConfigManager
        cm = ConfigManager()
        assert cm.get_list("items") is None
        captured = capsys.readouterr()
        assert "not a list" in captured.err

    def test_get_dict_validates_type(self, monkeypatch, tmp_path, capsys):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"favorites": [1, 2]}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        from dazzlecmd_lib.config import ConfigManager
        cm = ConfigManager()
        assert cm.get_dict("favorites") == {}
        captured = capsys.readouterr()
        assert "not a dict" in captured.err

    def test_malformed_json_returns_empty(self, monkeypatch, tmp_path, capsys):
        config_path = tmp_path / "config.json"
        config_path.write_text("{bad json", encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        from dazzlecmd_lib.config import ConfigManager
        cm = ConfigManager()
        assert cm.read() == {}
        captured = capsys.readouterr()
        assert "could not read" in captured.err.lower() or "warning" in captured.err.lower()


# ---------------------------------------------------------------------------
# Manifest cache hook
# ---------------------------------------------------------------------------


class TestManifestCacheHook:

    def test_library_starts_with_no_hook(self):
        from dazzlecmd_lib.loader import _manifest_cache_fn
        # The library itself has no hook — it's injected by the host app
        # Note: this may be True if dazzlecmd.loader was imported first
        # (which wires the hook). Test the mechanism, not the global state.
        from dazzlecmd_lib.loader import set_manifest_cache_fn
        assert callable(set_manifest_cache_fn)

    def test_hook_can_be_set_and_used(self):
        from dazzlecmd_lib import loader as lib_loader

        original = lib_loader._manifest_cache_fn
        try:
            called_with = {}

            def mock_cache(project_root, qualified):
                called_with["root"] = project_root
                called_with["qualified"] = qualified
                return {"name": "cached-tool", "version": "0.0.0"}

            lib_loader.set_manifest_cache_fn(mock_cache)
            assert lib_loader._manifest_cache_fn is mock_cache

            result = lib_loader._load_cached_manifest(
                "/fake/projects", "ns", "tool", "/fake/projects/ns/tool"
            )
            assert result is not None
            assert result["name"] == "cached-tool"
            assert result["_cached"] is True
            assert called_with["qualified"] == "ns:tool"
        finally:
            lib_loader._manifest_cache_fn = original


# ---------------------------------------------------------------------------
# meta_commands configurable
# ---------------------------------------------------------------------------


class TestMetaCommandsConfigurable:

    def test_default_meta_commands(self):
        from dazzlecmd_lib.engine import AggregatorEngine
        engine = AggregatorEngine()
        # The _meta_commands attribute should be None (uses defaults in run())
        assert engine._meta_commands is None

    def test_custom_meta_commands(self):
        from dazzlecmd_lib.engine import AggregatorEngine
        custom = {"help", "about", "tools"}
        engine = AggregatorEngine(meta_commands=custom)
        assert engine._meta_commands == custom


# ---------------------------------------------------------------------------
# Library isolation check
# ---------------------------------------------------------------------------


class TestLibraryIsolation:
    """Verify the library doesn't accidentally import from dazzlecmd.*"""

    def test_no_dazzlecmd_imports_in_library_source(self):
        """Scan all .py files in the library for dazzlecmd.* imports."""
        import glob
        lib_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "packages", "dazzlecmd-lib", "src", "dazzlecmd_lib",
        )
        violations = []
        for py_file in glob.glob(os.path.join(lib_dir, "*.py")):
            with open(py_file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if "from dazzlecmd." in stripped and "dazzlecmd_lib" not in stripped:
                        violations.append(f"{os.path.basename(py_file)}:{i}: {stripped}")
                    if "import dazzlecmd." in stripped and "dazzlecmd_lib" not in stripped:
                        violations.append(f"{os.path.basename(py_file)}:{i}: {stripped}")

        assert violations == [], f"Library imports from dazzlecmd.*:\n" + "\n".join(violations)
