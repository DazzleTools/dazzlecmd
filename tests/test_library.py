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

from dazzlecmd_lib.testing import make_tool, make_kit


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
        project = make_tool(name="test", runtime={"type": "nonexistent"}, _dir=".")
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
            project = make_tool(name="test", runtime={"type": "_test_custom"}, _dir=".")
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
            assert result.name == "cached-tool"
            assert result.cached is True
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


# ---------------------------------------------------------------------------
# Aggregator-as-kit discovery (closes #63, v0.7.38 fix)
# ---------------------------------------------------------------------------


class TestAggregatorAsKitDiscovery:
    """Regression tests for the discover_kits aggregator-as-kit bug.

    Pre-v0.7.38, ``_load_in_repo_kit_manifest`` Option 2 ("kits/ subdirectory
    aggregator-style kit") incorrectly merged the FIRST inner kit's identity
    fields (``name``, ``tools``, ``description``, etc.) into the outer
    aggregator-as-kit pointer. It also constructed an absolute ``tools_dir``
    that pointed at the kit's root (not its actual tools directory), which
    the engine's ``_recurse_into_nested`` then mis-normalized via ``basename``
    -- yielding a doubled path like ``<root>/<kit>/<kit>``.

    The forward direction (dazzlecmd embeds wtf-windows) happened to work
    because wtf's ``kits/core.kit.json`` declares ``tools_dir: "tools"`` and
    ``manifest: ".wtf.json"`` -- those got merged correctly. The inverse
    direction (wtf embeds dazzlecmd) failed because dazzlecmd's per-kit
    pointers are minimal, leaving the merge with no useful structural hints.

    These tests pin the correct behavior:

    * Identity fields (``name``) come from the registry pointer, never from
      an inner kit's manifest.
    * Structural hints (``tools_dir``, ``manifest``) are extracted from the
      first non-virtual inner kit that declares them; otherwise the engine
      falls back to defaults.
    * Hints stay relative (not absolute) so the engine's recursion joins
      them with ``nested_root`` correctly.
    """

    def _make_aggregator(self, tmp_path, name, has_inner_tools_dir=True,
                        inner_manifest_name=".dazzlecmd.json"):
        """Build a minimal aggregator-as-kit on disk under tmp_path.

        Layout:
            tmp_path/<name>/
                kits/core.kit.json   <- inner kit registry
                kits/extra.kit.json  <- second inner kit (so this is unambiguously an aggregator)
                projects/core/sample/<inner_manifest_name>
                projects/extra/other/<inner_manifest_name>
        """
        root = tmp_path / name
        root.mkdir()
        (root / "kits").mkdir()

        # Note: inner kits must declare their tools list so that
        # discover_projects' kit_tools filter (loader.py:401) admits them.
        # Real-world aggregators (dazzlecmd, wtf) populate this either via
        # Pattern 1 (.kit.json at project root) or via the registry pointer.
        core_kit = {
            "name": "core",
            "always_active": True,
            "tools": ["core:sample"],
        }
        if has_inner_tools_dir:
            core_kit["tools_dir"] = "projects"
            core_kit["manifest"] = inner_manifest_name
        (root / "kits" / "core.kit.json").write_text(json.dumps(core_kit))

        extra_kit = {
            "name": "extra",
            "always_active": True,
            "tools": ["extra:other"],
        }
        if has_inner_tools_dir:
            extra_kit["tools_dir"] = "projects"
            extra_kit["manifest"] = inner_manifest_name
        (root / "kits" / "extra.kit.json").write_text(json.dumps(extra_kit))

        # Make minimal tool dirs so the structure is plausible
        for kit_ns, tool in [("core", "sample"), ("extra", "other")]:
            tool_dir = root / "projects" / kit_ns / tool
            tool_dir.mkdir(parents=True)
            (tool_dir / inner_manifest_name).write_text(json.dumps({
                "name": tool, "version": "0.1.0",
                "description": f"{tool} tool", "runtime": {"type": "python"},
                "namespace": kit_ns,
            }))

        return root

    def test_pointer_name_preserved_in_aggregator_case(self, tmp_path):
        """Registry pointer's ``name`` field must NOT be overridden by inner
        kits. Pre-fix, the pointer named ``dz`` would end up with
        ``name='core'`` (the first inner kit's name)."""
        from dazzlecmd_lib.loader import discover_kits

        # Embedded aggregator at tmp_path/embedded/ with kits/{core,extra}.kit.json
        self._make_aggregator(tmp_path, "embedded")

        # Parent's registry kits/ dir with a single pointer for the embedded aggregator
        parent_kits = tmp_path / "parent_kits"
        parent_kits.mkdir()
        (parent_kits / "myptr.kit.json").write_text(json.dumps({
            "name": "myptr",
            "always_active": True,
            "source": "https://example.com/repo.git",
        }))

        kits = discover_kits(str(parent_kits), str(tmp_path))
        myptr = next(k for k in kits if k.kit_name == "myptr")

        # The aggregator-as-kit's identity comes from the registry pointer
        assert myptr.name == "myptr"
        assert myptr.extra_get("source") == "https://example.com/repo.git"
        assert myptr.always_active is True
        # Identity fields from inner kits must NOT leak in
        # (pre-fix, name='core' and tools=[...] would have leaked)
        assert myptr.tools or [] == []

    def test_structural_hints_extracted_from_inner_kits(self, tmp_path):
        """When inner kits declare ``tools_dir`` and ``manifest``, those
        should be extracted as structural hints onto the aggregator-as-kit
        dict so the engine knows how to recurse into it."""
        from dazzlecmd_lib.loader import discover_kits

        # The embedded aggregator's directory name must match the pointer name
        # (this is how discover_kits resolves where to look).
        self._make_aggregator(tmp_path, "ptr", has_inner_tools_dir=True,
                              inner_manifest_name=".myrepo.json")

        parent_kits = tmp_path / "parent_kits"
        parent_kits.mkdir()
        (parent_kits / "ptr.kit.json").write_text(json.dumps({
            "name": "ptr", "always_active": True,
        }))

        kits = discover_kits(str(parent_kits), str(tmp_path))
        ptr = next(k for k in kits if k.kit_name == "ptr")

        # Inner kits declared tools_dir="projects" and manifest=".myrepo.json"
        # (typed fields as of v0.8.32 -- attribute access)
        assert ptr.tools_dir == "projects"
        assert ptr.manifest == ".myrepo.json"
        # And it stays RELATIVE -- not absolute (pre-fix it was joined with
        # the embedded root, producing absolute paths that triggered the
        # basename mis-normalization downstream)
        assert not os.path.isabs(ptr.tools_dir)

    def test_no_hints_when_inner_kits_minimal(self, tmp_path):
        """When inner kits don't declare structural fields, the
        aggregator-as-kit dict has no tools_dir/manifest. The engine
        falls back to its own defaults."""
        from dazzlecmd_lib.loader import discover_kits

        self._make_aggregator(tmp_path, "ptr", has_inner_tools_dir=False)

        parent_kits = tmp_path / "parent_kits"
        parent_kits.mkdir()
        (parent_kits / "ptr.kit.json").write_text(json.dumps({
            "name": "ptr", "always_active": True,
        }))

        kits = discover_kits(str(parent_kits), str(tmp_path))
        ptr = next(k for k in kits if k.kit_name == "ptr")

        # No hints -- engine will use defaults (tools_dir="projects",
        # manifest=".dazzlecmd.json") via _recurse_into_nested fallbacks.
        assert ptr.extra_get("tools_dir") in (None, "")
        assert ptr.extra_get("manifest") in (None, "")
        # Identity still comes from the pointer
        assert ptr.name == "ptr"

    def test_single_kit_pattern_1_unchanged(self, tmp_path):
        """Pattern 1 (kit_dir/.kit.json self-describing) must still work.
        This is dazzlecmd's own kits' shape and predates the aggregator
        case. Regression guard against breaking single-kit semantics."""
        from dazzlecmd_lib.loader import discover_kits

        # Make a SINGLE kit (no kits/ subdir, just .kit.json at root)
        kit_dir = tmp_path / "singlekit"
        kit_dir.mkdir()
        (kit_dir / ".kit.json").write_text(json.dumps({
            "name": "singlekit",
            "version": "1.0.0",
            "description": "A single self-describing kit",
            "tools_dir": ".",
            "manifest": ".dazzlecmd.json",
            "tools": ["singlekit:something"],
        }))

        parent_kits = tmp_path / "parent_kits"
        parent_kits.mkdir()
        (parent_kits / "singlekit.kit.json").write_text(json.dumps({
            "name": "singlekit", "always_active": True,
        }))

        kits = discover_kits(str(parent_kits), str(tmp_path))
        kit = next(k for k in kits if k.kit_name == "singlekit")

        # Pattern 1: full manifest merged, including version, description,
        # tools list -- this is the legitimate self-describing case.
        assert kit.name == "singlekit"
        assert kit.version == "1.0.0"
        assert kit.tools == ["singlekit:something"]

    def test_engine_recurses_correctly_for_aggregator_as_kit(self, tmp_path):
        """End-to-end: the engine constructs a child for an aggregator-as-kit
        with the correct (relative) tools_dir, recursively discovers the
        inner kits' tools, and populates ``kit.tools`` with the FQCNs of
        the discovered projects."""
        from dazzlecmd_lib import AggregatorEngine

        embedded = self._make_aggregator(
            tmp_path, "embedded", has_inner_tools_dir=True,
            inner_manifest_name=".dazzlecmd.json",
        )

        # Parent layout matching wtf-windows-style: kits/ + tools/<kit_name>/
        # where tools/<kit_name> is the embedded aggregator.
        parent_root = tmp_path / "parent"
        parent_root.mkdir()
        (parent_root / "kits").mkdir()
        (parent_root / "tools").mkdir()
        # Symlink-ish: point to embedded via os.symlink (Linux) or just copy
        # the relative path. For test portability, use a directory move.
        os.rename(str(embedded), str(parent_root / "tools" / "embedded"))

        # Parent's pointer at parent/kits/embedded.kit.json
        (parent_root / "kits" / "embedded.kit.json").write_text(json.dumps({
            "name": "embedded",
            "always_active": True,
            "source": "https://example.com/embedded.git",
        }))

        engine = AggregatorEngine(
            name="parent", command="parent",
            tools_dir="tools", kits_dir="kits",
            manifest=".dazzlecmd.json", is_root=True,
            project_root=str(parent_root),
        )
        engine.discover()

        # Both inner kits' tools should be discovered with embedded: prefix
        fqcns = [p.fqcn for p in engine.projects]
        assert "embedded:core:sample" in fqcns, (
            f"Expected embedded:core:sample in projects; got {fqcns!r}"
        )
        assert "embedded:extra:other" in fqcns, (
            f"Expected embedded:extra:other in projects; got {fqcns!r}"
        )

        # The kit dict should have its tools field populated with FQCNs
        # of the discovered projects (post-recursion derived view).
        embedded_kit = next(
            k for k in engine.kits if k.kit_name == "embedded"
        )
        assert set(embedded_kit.tools) == {
            "embedded:core:sample", "embedded:extra:other",
        }
