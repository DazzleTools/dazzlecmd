"""Integration tests for recursive discovery and FQCN remapping.

Uses temporary directory fixtures to build mock aggregator trees, avoiding
reliance on the real projects/wtf submodule. Exercises:
    - Recursive discovery through a nested `kits/` directory
    - FQCN remapping (parent_kit + ':' + child_namespace + ':' + tool)
    - Cycle detection via the loading stack
    - is_root=False behavior (meta-commands suppressed on imported aggregators)
    - Registry-level tools_dir/manifest overrides
"""

import json
import os

import pytest

from dazzlecmd.engine import AggregatorEngine, CircularDependencyError
from dazzlecmd_lib.testing import make_kit, make_tool


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _write_tool(tool_dir, name, manifest_name=".dazzlecmd.json",
                description="A test tool"):
    """Create a minimal tool with a manifest and a python script."""
    os.makedirs(tool_dir, exist_ok=True)
    manifest = {
        "name": name,
        "version": "0.1.0",
        "description": description,
        "platform": "cross-platform",
        "runtime": {
            "type": "python",
            "entry_point": "main",
            "script_path": f"{name}.py",
        },
    }
    _write_json(os.path.join(tool_dir, manifest_name), manifest)
    with open(os.path.join(tool_dir, f"{name}.py"), "w", encoding="utf-8") as f:
        f.write(f"def main(argv=None):\n    print('{name}')\n    return 0\n")


def build_flat_aggregator(root, name="flat"):
    """Build a simple flat aggregator with one kit and two tools.

    Layout:
        root/
            kits/
                core.kit.json
            projects/
                core/
                    toolA/.dazzlecmd.json
                    toolB/.dazzlecmd.json
    """
    _write_json(
        os.path.join(root, "kits", "core.kit.json"),
        {"name": "core", "always_active": True},
    )
    _write_json(
        os.path.join(root, "projects", "core", ".kit.json"),
        {
            "name": "core",
            "tools_dir": ".",
            "manifest": ".dazzlecmd.json",
            "tools": ["core:toolA", "core:toolB"],
        },
    )
    _write_tool(os.path.join(root, "projects", "core", "toolA"), "toolA")
    _write_tool(os.path.join(root, "projects", "core", "toolB"), "toolB")


def build_nested_aggregator(root):
    """Build a parent aggregator that imports a child aggregator.

    Layout:
        root/
            kits/
                core.kit.json
                child.kit.json        <- references child aggregator
            projects/
                core/
                    parent_tool/.dazzlecmd.json
                child/                <- nested aggregator root
                    kits/
                        core.kit.json
                    tools/            <- child's tools_dir (non-default)
                        core/
                            child_toolA/.child.json
                            child_toolB/.child.json
    """
    # Parent's core kit with one tool
    _write_json(
        os.path.join(root, "kits", "core.kit.json"),
        {"name": "core", "always_active": True},
    )
    _write_json(
        os.path.join(root, "projects", "core", ".kit.json"),
        {
            "name": "core",
            "tools_dir": ".",
            "tools": ["core:parent_tool"],
        },
    )
    _write_tool(
        os.path.join(root, "projects", "core", "parent_tool"),
        "parent_tool",
    )

    # Parent's registry pointer for the child aggregator, with overrides
    _write_json(
        os.path.join(root, "kits", "child.kit.json"),
        {
            "name": "child",
            "always_active": True,
            "_override_tools_dir": "tools",
            "_override_manifest": ".child.json",
        },
    )

    # Child aggregator structure
    child_root = os.path.join(root, "projects", "child")
    _write_json(
        os.path.join(child_root, "kits", "core.kit.json"),
        {
            "name": "core",
            "always_active": True,
            "tools": ["core:child_toolA", "core:child_toolB"],
        },
    )
    _write_tool(
        os.path.join(child_root, "tools", "core", "child_toolA"),
        "child_toolA",
        manifest_name=".child.json",
    )
    _write_tool(
        os.path.join(child_root, "tools", "core", "child_toolB"),
        "child_toolB",
        manifest_name=".child.json",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlatDiscovery:
    """Baseline: flat aggregator with no nesting still works after Phase 2."""

    def test_flat_discovery_finds_tools(self, tmp_path):
        build_flat_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            name="test", command="test",
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        assert len(engine.projects) == 2
        short_names = {p.short_name for p in engine.projects}
        assert short_names == {"toolA", "toolB"}

    def test_flat_fqcn_format(self, tmp_path):
        build_flat_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        fqcns = {p.fqcn for p in engine.projects}
        assert fqcns == {"core:toolA", "core:toolB"}

    def test_flat_resolve_short_name(self, tmp_path):
        build_flat_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        project, note = engine.resolve_command("toolA")
        assert project is not None
        assert project.fqcn == "core:toolA"
        assert note is None or note.notification is None


class TestPointerKitDiscoverySkip:
    """Slice 4 step 1: a kit with a `pointer` block (written by `dz kit detach`)
    LISTS but its tools are NOT loaded -- the LOADING-axis pole. Default off, so
    normal kits are unaffected (the byte-gate stays green)."""

    def _build(self, root, pointer=None):
        # a normal kit (core) + an `extra` kit (optionally a pointer), each with an
        # in-repo manifest -- which exercises discover_kits CARRYING `pointer` across
        # the merge (the registry pointer block must survive an in-repo manifest).
        _write_json(os.path.join(root, "kits", "core.kit.json"),
                    {"name": "core", "always_active": True})
        _write_json(os.path.join(root, "projects", "core", ".kit.json"),
                    {"name": "core", "tools_dir": ".", "manifest": ".dazzlecmd.json",
                     "tools": ["core:toolA"]})
        _write_tool(os.path.join(root, "projects", "core", "toolA"), "toolA")
        extra_reg = {"name": "extra", "always_active": False}
        if pointer is not None:
            extra_reg["pointer"] = pointer
        _write_json(os.path.join(root, "kits", "extra.kit.json"), extra_reg)
        _write_json(os.path.join(root, "projects", "extra", ".kit.json"),
                    {"name": "extra", "tools_dir": ".", "manifest": ".dazzlecmd.json",
                     "tools": ["extra:ptool"]})
        _write_tool(os.path.join(root, "projects", "extra", "ptool"), "ptool")

    def _discover(self, root):
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits", manifest=".dazzlecmd.json")
        engine.discover(project_root=str(root))
        return engine

    def test_pointer_kit_lists_but_loads_no_tools(self, tmp_path):
        self._build(str(tmp_path), pointer={"materialized": True})
        engine = self._discover(str(tmp_path))
        kit_names = {k.kit_name or k.name for k in engine.kits}
        assert "extra" in kit_names                      # the pointer kit LISTS
        short = {p.short_name for p in engine.projects}
        assert "ptool" not in short                      # ... but loads NO tools
        assert "toolA" in short                          # the normal kit still loads

    def test_non_pointer_kit_loads_normally(self, tmp_path):
        self._build(str(tmp_path), pointer=None)         # control: no pointer block
        engine = self._discover(str(tmp_path))
        short = {p.short_name for p in engine.projects}
        assert "ptool" in short                          # without pointer -> loads

    def test_detach_handler_then_rediscover_skips_the_kit(self, tmp_path, monkeypatch):
        # End-to-end contract: the pointer block `dz kit detach` WRITES is the same
        # shape discovery CONSUMES. Without it, each half could pass in isolation
        # while the integration silently breaks.
        import types
        from dazzlecmd.cli import _cmd_kit_detach
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        self._build(str(tmp_path), pointer=None)         # extra loads normally first
        engine = self._discover(str(tmp_path))
        assert "ptool" in {p.short_name for p in engine.projects}

        rc = _cmd_kit_detach(
            types.SimpleNamespace(name="extra", dry_run=False), str(tmp_path), engine)
        assert rc == 0

        engine2 = self._discover(str(tmp_path))
        assert "extra" in {k.kit_name or k.name for k in engine2.kits}   # still LISTS
        assert "ptool" not in {p.short_name for p in engine2.projects}   # ... not loaded
        assert "toolA" in {p.short_name for p in engine2.projects}       # neighbor intact


class TestRecursiveDiscovery:
    """Nested aggregator: parent imports child with FQCN remapping."""

    def test_recursive_discovery_finds_all_tools(self, tmp_path):
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        # Parent has 1 tool, child has 2 tools
        assert len(engine.projects) == 3

    def test_recursive_fqcn_remapping(self, tmp_path):
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        fqcns = {p.fqcn for p in engine.projects}
        assert "core:parent_tool" in fqcns
        assert "child:core:child_toolA" in fqcns
        assert "child:core:child_toolB" in fqcns

    def test_recursive_kit_import_name(self, tmp_path):
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        # Parent tool has kit_import_name "core"
        parent_tool = [p for p in engine.projects if p.short_name == "parent_tool"][0]
        assert parent_tool.kit_import_name == "core"
        # Child tools have kit_import_name "child" (the parent's view)
        child_a = [p for p in engine.projects if p.short_name == "child_toolA"][0]
        assert child_a.kit_import_name == "child"

    def test_recursive_resolve_short_name_no_collision(self, tmp_path):
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        project, note = engine.resolve_command("child_toolA")
        assert project is not None
        assert project.fqcn == "child:core:child_toolA"
        assert note is None or note.notification is None  # no collision, no notification

    def test_recursive_resolve_explicit_fqcn(self, tmp_path):
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        project, note = engine.resolve_command("child:core:child_toolA")
        assert project is not None
        assert project.fqcn == "child:core:child_toolA"

    def test_registry_override_custom_manifest(self, tmp_path):
        """The child uses .child.json manifest, not .dazzlecmd.json."""
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        # If the override isn't honored, child tools wouldn't be discovered
        child_fqcns = [p.fqcn for p in engine.projects if p.kit_import_name == "child"]
        assert len(child_fqcns) == 2


class TestCycleDetection:

    def test_cycle_detection_raises(self, tmp_path):
        """Build an aggregator that imports itself and verify cycle detection."""
        # Create a parent that tries to import itself as a kit
        root = str(tmp_path)
        _write_json(
            os.path.join(root, "kits", "core.kit.json"),
            {"name": "core", "always_active": True},
        )
        _write_json(
            os.path.join(root, "kits", "self.kit.json"),
            {
                "name": "self",
                "always_active": True,
                "_override_tools_dir": "projects",
                "_override_manifest": ".dazzlecmd.json",
            },
        )
        # The kit "self" resolves to projects/self/, which we make
        # point back to the root via its own kits/
        self_dir = os.path.join(root, "projects", "self")
        os.makedirs(os.path.join(self_dir, "kits"), exist_ok=True)
        # Create a symlink-style setup by having self/kits mirror parent/kits
        # Actually, for a true cycle we'd need self to recurse into root.
        # Easier: mock this with a realpath collision.

        # Simpler approach: directly call _discover_aggregator with a
        # pre-populated loading stack containing the real root
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        real_root = os.path.realpath(root)
        loading_stack = frozenset({real_root})

        with pytest.raises(CircularDependencyError) as exc_info:
            engine._discover_aggregator(
                root, loading_stack, depth=1, kit_prefix="parent"
            )
        assert "Circular" in str(exc_info.value)

    def test_loading_stack_threads_through_recursion(self, tmp_path):
        """Normal recursive discovery does NOT raise cycle errors."""
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        # Should not raise
        engine.discover(project_root=str(tmp_path))
        assert len(engine.projects) == 3


class TestRerootHint:
    """Discovery emits a one-time hint when tools have deeply nested FQCNs.

    Nesting is unlimited; the hint exists to suggest rerooting (extracting
    a deep subtree as a standalone install) when typing the full FQCN
    becomes awkward. The hint fires only when at least one tool's FQCN has
    4+ segments (3+ colons).
    """

    def test_no_hint_for_shallow_tree(self, tmp_path, capsys):
        """Realistic 2-level nesting (wtf:core:tool) does NOT trigger the hint."""
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        captured = capsys.readouterr()
        assert "deeply nested" not in captured.err
        assert "rerooting" not in captured.err

    def test_no_hint_for_flat_tree(self, tmp_path, capsys):
        build_flat_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        captured = capsys.readouterr()
        assert "rerooting" not in captured.err

    def test_hint_emitted_for_deep_fqcn(self, capsys):
        """A project with 4+ FQCN segments triggers the rerooting hint."""
        engine = AggregatorEngine(is_root=True)
        engine.projects = [
            make_tool(
                name="leaf",
                _fqcn="a:b:c:d:leaf",
                _short_name="leaf",
                _kit_import_name="a",
                _dir="/fake",
                description="deep tool",
            )
        ]
        engine._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert "deeply nested" in captured.err
        assert "a:b:c:d:leaf" in captured.err
        assert "5 segments" in captured.err
        assert "rerooting" in captured.err

    def test_hint_uses_engine_command(self, capsys):
        """Hint message uses the consumer's command name, not hardcoded 'dz'.

        Regression for #64: lib previously hardcoded 'dz' in user-facing
        hint messages, giving wtf-windows / amdead / future consumers bad
        advice (e.g., 'dz kit silence ...' instead of 'wtf kit silence ...').
        """
        engine = AggregatorEngine(command="wtf", is_root=True)
        engine.projects = [
            make_tool(
                name="leaf",
                _fqcn="a:b:c:d:leaf",
                _short_name="leaf",
                _kit_import_name="a",
                _dir="/fake",
                description="deep tool",
            )
        ]
        engine._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert "wtf: hint:" in captured.err
        assert "'wtf kit silence" in captured.err
        # No hardcoded dz in the per-engine portions of the message.
        assert "dz kit silence" not in captured.err

    def test_hint_silenceable_via_dz_quiet(self, monkeypatch, capsys):
        monkeypatch.setenv("DZ_QUIET", "1")
        engine = AggregatorEngine(is_root=True)
        engine.projects = [
            make_tool(
                name="leaf",
                _fqcn="a:b:c:d:leaf",
                _short_name="leaf",
                _kit_import_name="a",
                _dir="/fake",
                description="deep tool",
            )
        ]
        engine._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_hint_skipped_when_not_root(self, capsys):
        """Imported aggregators (is_root=False) never emit the hint --
        only the top-level engine does."""
        engine = AggregatorEngine(is_root=False)
        engine.projects = [
            make_tool(
                name="leaf",
                _fqcn="a:b:c:d:leaf",
                _short_name="leaf",
                _kit_import_name="a",
                _dir="/fake",
                description="deep tool",
            )
        ]
        engine._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_unlimited_nesting_does_not_raise(self, tmp_path):
        """Synthetic depth=20 discovery completes without raising or stopping."""
        build_flat_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        # Bypass discover() to control depth directly
        projects = engine._discover_aggregator(
            str(tmp_path),
            frozenset(),
            depth=20,
            kit_prefix="a:b:c:d:e:f:g:h:i:j:k:l:m:n:o:p:q:r:s:t",
        )
        # Discovery completes successfully even at depth 20 -- nesting is unlimited
        assert len(projects) == 2


class TestIsRootFlag:
    """Imported aggregators have is_root=False and suppress meta-commands."""

    def test_child_engine_is_not_root(self, tmp_path):
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
            is_root=True,
        )
        engine.discover(project_root=str(tmp_path))
        # Parent is root
        assert engine.is_root is True
        # reserved_commands is non-empty for root
        assert len(engine.reserved_commands) > 0

    def test_non_root_reserved_commands_empty(self):
        engine = AggregatorEngine(is_root=False)
        assert engine.reserved_commands == set()


class TestCollisionWithNotification:
    """When parent and child have tools with the same short name, precedence
    applies and a notification is emitted."""

    def test_colliding_short_name_core_wins_with_notification(self, tmp_path):
        root = str(tmp_path)
        # Parent has a tool named "toolA"
        _write_json(
            os.path.join(root, "kits", "core.kit.json"),
            {"name": "core", "always_active": True},
        )
        _write_json(
            os.path.join(root, "projects", "core", ".kit.json"),
            {
                "name": "core",
                "tools_dir": ".",
                "tools": ["core:toolA"],
            },
        )
        _write_tool(os.path.join(root, "projects", "core", "toolA"), "toolA")

        # Child aggregator also has a "toolA"
        _write_json(
            os.path.join(root, "kits", "extra.kit.json"),
            {
                "name": "extra",
                "always_active": True,
                "_override_tools_dir": "tools",
                "_override_manifest": ".dazzlecmd.json",
            },
        )
        child_root = os.path.join(root, "projects", "extra")
        _write_json(
            os.path.join(child_root, "kits", "core.kit.json"),
            {
                "name": "core",
                "always_active": True,
                "tools": ["core:toolA"],
            },
        )
        _write_tool(
            os.path.join(child_root, "tools", "core", "toolA"),
            "toolA",
        )

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))

        # Short name "toolA" resolves to core (default precedence)
        project, note = engine.resolve_command("toolA")
        assert project is not None
        assert project.fqcn == "core:toolA"
        # Notification should mention extra as an alternative
        assert note is not None and note.notification is not None
        assert "extra" in note.notification
        assert "core:toolA" in note.notification

    def test_precedence_override_inverts_resolution(self, tmp_path):
        """User kit_precedence override puts extra before core."""
        root = str(tmp_path)
        _write_json(
            os.path.join(root, "kits", "core.kit.json"),
            {"name": "core", "always_active": True},
        )
        _write_json(
            os.path.join(root, "projects", "core", ".kit.json"),
            {"name": "core", "tools_dir": ".", "tools": ["core:toolA"]},
        )
        _write_tool(os.path.join(root, "projects", "core", "toolA"), "toolA")

        _write_json(
            os.path.join(root, "kits", "extra.kit.json"),
            {
                "name": "extra",
                "always_active": True,
                "_override_tools_dir": "tools",
                "_override_manifest": ".dazzlecmd.json",
            },
        )
        child_root = os.path.join(root, "projects", "extra")
        _write_json(
            os.path.join(child_root, "kits", "core.kit.json"),
            {"name": "core", "always_active": True, "tools": ["core:toolA"]},
        )
        _write_tool(
            os.path.join(child_root, "tools", "core", "toolA"), "toolA"
        )

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))

        # Directly test with precedence override (not via config file)
        project, note = engine.fqcn_index.resolve("toolA", precedence=["extra", "core"])
        assert project is not None
        assert project.fqcn == "extra:core:toolA"


class TestPhase3SilencingAndShadowing:
    """Phase 3: silenced_hints and shadowed_tools config keys filter
    discovery output and gate the rerooting hint."""

    def _build_deep_tree(self, tmp_path):
        """Build an aggregator where at least one tool has 4+ FQCN segments,
        so the rerooting hint would fire by default."""
        build_nested_aggregator(str(tmp_path))
        return str(tmp_path)

    def test_shadowed_tool_removed_from_projects(self, tmp_path, monkeypatch):
        build_flat_aggregator(str(tmp_path))
        config_path = tmp_path / "dz-config.json"
        config_path.write_text(
            json.dumps({"shadowed_tools": ["core:toolA"]}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))

        fqcns = {p.fqcn for p in engine.projects}
        assert "core:toolA" not in fqcns
        assert "core:toolB" in fqcns

    def test_shadowed_tool_not_in_fqcn_index(self, tmp_path, monkeypatch):
        build_flat_aggregator(str(tmp_path))
        config_path = tmp_path / "dz-config.json"
        config_path.write_text(
            json.dumps({"shadowed_tools": ["core:toolA"]}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))

        project, _ = engine.fqcn_index.resolve("core:toolA")
        assert project is None

    def test_shadowed_tool_short_name_freed(self, tmp_path, monkeypatch):
        """When a shadowed tool's short name is the only collision source,
        the remaining tool resolves unambiguously (no notification)."""
        root = str(tmp_path)
        # Set up two tools with the same short name in different kits
        _write_json(
            os.path.join(root, "kits", "core.kit.json"),
            {"name": "core", "always_active": True},
        )
        _write_json(
            os.path.join(root, "projects", "core", ".kit.json"),
            {
                "name": "core",
                "tools_dir": ".",
                "tools": ["core:shared"],
            },
        )
        _write_tool(os.path.join(root, "projects", "core", "shared"), "shared")

        _write_json(
            os.path.join(root, "kits", "other.kit.json"),
            {
                "name": "other",
                "always_active": True,
                "_override_tools_dir": "tools",
                "_override_manifest": ".dazzlecmd.json",
            },
        )
        other_root = os.path.join(root, "projects", "other")
        _write_json(
            os.path.join(other_root, "kits", "core.kit.json"),
            {"name": "core", "always_active": True, "tools": ["core:shared"]},
        )
        _write_tool(
            os.path.join(other_root, "tools", "core", "shared"), "shared"
        )

        config_path = tmp_path / "dz-config.json"
        config_path.write_text(
            json.dumps({"shadowed_tools": ["core:shared"]}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))

        # "shared" now resolves unambiguously to other:core:shared
        project, note = engine.resolve_command("shared")
        assert project is not None
        assert project.fqcn == "other:core:shared"
        assert note is None or note.notification is None  # no collision anymore

    def test_silenced_tool_suppresses_reroot_hint(self, tmp_path, monkeypatch, capsys):
        """When the only deeply-nested tool is silenced, no hint fires."""
        engine = AggregatorEngine(is_root=True)
        engine.projects = [
            make_tool(
                name="leaf",
                _fqcn="a:b:c:d:leaf",
                _short_name="leaf",
                _kit_import_name="a",
                _dir="/fake",
                description="deep tool",
            )
        ]
        config_path = tmp_path / "dz-config.json"
        config_path.write_text(
            json.dumps({"silenced_hints": {"tools": ["a:b:c:d:leaf"]}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        # Recreate engine to pick up the config
        engine2 = AggregatorEngine(is_root=True)
        engine2.projects = engine.projects
        engine2._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert "deeply nested" not in captured.err

    def test_silenced_kit_suppresses_reroot_hint_for_all_its_tools(
        self, tmp_path, monkeypatch, capsys
    ):
        """silenced_hints.kits silences all tools whose _kit_import_name matches."""
        config_path = tmp_path / "dz-config.json"
        config_path.write_text(
            json.dumps({"silenced_hints": {"kits": ["deepkit"]}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine(is_root=True)
        engine.projects = [
            make_tool(
                name="leaf",
                _fqcn="deepkit:sub:core:leaf",
                _short_name="leaf",
                _kit_import_name="deepkit",
                _dir="/fake",
                description="deep tool",
            )
        ]
        engine._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert "deeply nested" not in captured.err

    def test_silenced_tool_does_not_suppress_other_deep_tools(
        self, tmp_path, monkeypatch, capsys
    ):
        """Silencing one tool still lets hints fire for other deep tools."""
        config_path = tmp_path / "dz-config.json"
        config_path.write_text(
            json.dumps({"silenced_hints": {"tools": ["a:b:c:d:silenced"]}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine(is_root=True)
        engine.projects = [
            make_tool(
                name="silenced",
                _fqcn="a:b:c:d:silenced",
                _short_name="silenced",
                _kit_import_name="a",
                _dir="/fake",
                description="silenced tool",
            ),
            make_tool(
                name="notsilenced",
                _fqcn="x:y:z:w:notsilenced",
                _short_name="notsilenced",
                _kit_import_name="x",
                _dir="/fake",
                description="other deep tool",
            ),
        ]
        engine._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert "deeply nested" in captured.err
        assert "notsilenced" in captured.err
        assert "silenced" not in captured.err.split("notsilenced")[0]


class TestModuleDispatch:
    """#29: package-structured tools with relative imports need module-mode
    dispatch (python -m module.path) instead of script-mode (python script.py).

    Tests both _make_subprocess_runner (pass_through) and _make_python_runner
    (direct import) module detection paths.
    """

    def _build_package_tool(self, tool_dir, pkg_name="my_pkg"):
        """Create a minimal Python package tool with a relative import."""
        pkg_dir = os.path.join(tool_dir, pkg_name)
        os.makedirs(pkg_dir, exist_ok=True)

        # __init__.py makes it a package
        with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
            f.write("")

        # _version.py — the module that gets relatively-imported
        with open(os.path.join(pkg_dir, "_version.py"), "w") as f:
            f.write("__version__ = '0.1.0'\n")

        # cli.py — uses a relative import (the thing that breaks without -m)
        with open(os.path.join(pkg_dir, "cli.py"), "w") as f:
            f.write(
                "from ._version import __version__\n"
                "def main(argv=None):\n"
                "    print(f'version={__version__}')\n"
                "    return 0\n"
            )

        return pkg_name

    def test_subprocess_runner_detects_package_via_init(self, tmp_path):
        """_make_subprocess_runner uses python -m when __init__.py is present."""
        from dazzlecmd.loader import _make_subprocess_runner

        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        pkg = self._build_package_tool(tool_dir)

        project = make_tool(
            name="test-tool",
            runtime={"type": "python", "script_path": f"{pkg}/cli.py"},
            pass_through=True,
            _dir=tool_dir,
        )

        runner = _make_subprocess_runner(project)
        result = runner(["--version"])  # arbitrary args
        # If module mode works, the script runs without ImportError
        assert result == 0

    def test_subprocess_runner_uses_explicit_module_field(self, tmp_path):
        """runtime.module takes precedence over __init__.py heuristic."""
        from dazzlecmd.loader import _make_subprocess_runner

        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        pkg = self._build_package_tool(tool_dir)

        project = make_tool(
            name="test-tool",
            runtime={
                "type": "python",
                "script_path": f"{pkg}/cli.py",
                "module": f"{pkg}.cli",
            },
            pass_through=True,
            _dir=tool_dir,
        )

        runner = _make_subprocess_runner(project)
        result = runner([])
        assert result == 0

    def test_subprocess_runner_flat_script_still_works(self, tmp_path):
        """Tools without __init__.py still use script-mode dispatch."""
        from dazzlecmd.loader import _make_subprocess_runner

        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)

        # A flat script (no package, no __init__.py)
        with open(os.path.join(tool_dir, "flat_tool.py"), "w") as f:
            f.write("import sys\nprint('flat works')\nsys.exit(0)\n")

        project = make_tool(
            name="flat-tool",
            runtime={"type": "python", "script_path": "flat_tool.py"},
            pass_through=True,
            _dir=tool_dir,
        )

        runner = _make_subprocess_runner(project)
        result = runner([])
        assert result == 0

    def test_python_runner_detects_package_via_init(self, tmp_path):
        """_make_python_runner uses package import when __init__.py detected."""
        from dazzlecmd.loader import _make_python_runner

        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        pkg = self._build_package_tool(tool_dir)

        project = make_tool(
            name="test-tool",
            runtime={
                "type": "python",
                "script_path": f"{pkg}/cli.py",
                "entry_point": "main",
            },
            _dir=tool_dir,
        )

        runner = _make_python_runner(project)
        result = runner([])
        assert result == 0


# ---------------------------------------------------------------------------
# Issue #65: realpath-based auto-aliasing
# ---------------------------------------------------------------------------


def _make_project(fqcn, tool_dir, name=None):
    """Construct a minimal project entity for _build_fqcn_index tests."""
    short = name or fqcn.rsplit(":", 1)[-1]
    kit = fqcn.split(":", 1)[0]
    return make_tool(
        name=short,
        _fqcn=fqcn,
        _short_name=short,
        _kit_import_name=kit,
        _dir=tool_dir,
        _kit_active=True,
        description=f"Tool {short}",
        runtime={"type": "python"},
    )


class TestRealpathDedup:
    """Issue #65: same on-disk script reachable via two FQCNs collapses to
    one canonical + N-1 auto-realpath aliases.
    """

    def _engine(self):
        return AggregatorEngine(
            name="test", command="test",
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )

    def test_same_realpath_two_fqcns_aliases_the_longer(self, tmp_path):
        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        engine = self._engine()
        engine.projects = [
            _make_project("wtf:core:locked", tool_dir),
            _make_project("dz:wtf:core:locked", tool_dir),
        ]
        engine._build_fqcn_index()
        # Shorter FQCN wins canonical.
        assert "wtf:core:locked" in engine.fqcn_index.canonical_index
        assert "dz:wtf:core:locked" not in engine.fqcn_index.canonical_index
        # Longer FQCN becomes auto-realpath alias.
        assert engine.fqcn_index.alias_index["dz:wtf:core:locked"] == "wtf:core:locked"
        assert engine.fqcn_index._alias_sources["dz:wtf:core:locked"] == "auto-realpath"

    def test_distinct_dirs_both_canonical(self, tmp_path):
        dir_a = str(tmp_path / "a")
        dir_b = str(tmp_path / "b")
        os.makedirs(dir_a)
        os.makedirs(dir_b)
        engine = self._engine()
        engine.projects = [
            _make_project("wtf:core:locked", dir_a),
            _make_project("dz:wtf:core:locked", dir_b),
        ]
        engine._build_fqcn_index()
        # No dedup: distinct realpaths -> both canonical.
        assert "wtf:core:locked" in engine.fqcn_index.canonical_index
        assert "dz:wtf:core:locked" in engine.fqcn_index.canonical_index
        assert "dz:wtf:core:locked" not in engine.fqcn_index.alias_index

    def test_shortest_fqcn_wins_three_way(self, tmp_path):
        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        engine = self._engine()
        engine.projects = [
            _make_project("a:b:c:d", tool_dir),
            _make_project("z:x", tool_dir),
            _make_project("m:n:o", tool_dir),
        ]
        engine._build_fqcn_index()
        assert "z:x" in engine.fqcn_index.canonical_index
        assert engine.fqcn_index.alias_index["a:b:c:d"] == "z:x"
        assert engine.fqcn_index.alias_index["m:n:o"] == "z:x"
        for alias in ("a:b:c:d", "m:n:o"):
            assert engine.fqcn_index._alias_sources[alias] == "auto-realpath"

    def test_alphabetical_tiebreak_when_equal_depth(self, tmp_path):
        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        engine = self._engine()
        engine.projects = [
            _make_project("zz:tool", tool_dir),
            _make_project("aa:tool", tool_dir),
        ]
        engine._build_fqcn_index()
        # Same segment count -> alphabetical wins.
        assert "aa:tool" in engine.fqcn_index.canonical_index
        assert engine.fqcn_index.alias_index["zz:tool"] == "aa:tool"

    def test_realpath_index_populated(self, tmp_path):
        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        engine = self._engine()
        engine.projects = [
            _make_project("a:b", tool_dir),
            _make_project("c:d:e", tool_dir),
        ]
        engine._build_fqcn_index()
        real = os.path.realpath(tool_dir)
        assert engine._realpath_index[real] == "a:b"

    def test_dispatch_resolves_alias_to_canonical(self, tmp_path):
        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        engine = self._engine()
        engine.projects = [
            _make_project("wtf:core:locked", tool_dir),
            _make_project("dz:wtf:core:locked", tool_dir),
        ]
        engine._build_fqcn_index()
        # Resolving the alias FQCN returns the canonical project.
        proj, ctx = engine.fqcn_index.resolve("dz:wtf:core:locked")
        assert proj is not None
        assert proj.fqcn == "wtf:core:locked"
        assert ctx.resolution_kind == "alias"
        assert ctx.alias_fqcn == "dz:wtf:core:locked"

    def test_demoted_project_marked(self, tmp_path):
        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        winner = _make_project("a:b", tool_dir)
        loser = _make_project("c:d:e", tool_dir)
        engine = self._engine()
        engine.projects = [winner, loser]
        engine._build_fqcn_index()
        assert not winner.auto_realpath_alias
        assert loser.auto_realpath_alias is True
        assert loser.canonical_fqcn == "a:b"

    def test_list_entries_omit_auto_realpath_alias(self, tmp_path):
        from dazzlecmd_lib.default_meta_commands import build_list_entries

        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        engine = self._engine()
        engine.projects = [
            _make_project("wtf:core:locked", tool_dir),
            _make_project("dz:wtf:core:locked", tool_dir),
        ]
        engine._build_fqcn_index()
        entries = build_list_entries(
            engine.projects, engine, show_mode="all", kit_filter=None
        )
        fqcns_in_entries = {e["_fqcn"] for e in entries}
        # Auto-realpath alias FQCN does NOT appear as a row.
        assert "dz:wtf:core:locked" not in fqcns_in_entries
        # Canonical winner DOES appear, marked with has_aliases.
        winner_entries = [e for e in entries if e["_fqcn"] == "wtf:core:locked"]
        assert len(winner_entries) == 1
        assert winner_entries[0]["has_aliases"] is True

    def test_virtual_kit_alias_follows_demoted_target(self, tmp_path):
        """When a virtual-kit alias's declared target was demoted to an
        auto-realpath alias, the new alias re-points at the actual
        canonical instead of failing with KeyError.
        """
        tool_dir = str(tmp_path / "tool")
        os.makedirs(tool_dir)
        engine = self._engine()
        engine.projects = [
            _make_project("wtf:core:locked", tool_dir),
            _make_project("dz:wtf:core:locked", tool_dir),
        ]
        engine._build_fqcn_index()
        # dz:wtf:core:locked is now an alias of wtf:core:locked.
        # A virtual kit targets the demoted FQCN — should resolve to the canonical.
        virtual_kits = [
            make_kit(
                name="dz:claude",
                _kit_name="dz:claude",
                _kit_active=True,
                virtual=True,
                tools=["dz:wtf:core:locked"],
                name_rewrite={"dz:wtf:core:locked": "why-locked"},
            )
        ]
        engine._apply_virtual_kits(virtual_kits)
        # The virtual-kit alias should be registered with the actual canonical.
        assert engine.fqcn_index.alias_index.get("dz:claude:why-locked") == "wtf:core:locked"

    @pytest.mark.skipif(os.name == "nt", reason="POSIX-only symlink test")
    def test_symlink_loop_real_discovery(self, tmp_path):
        """Integration: build two aggregators where the second symlinks into
        the first, discover, and verify only one canonical exists per script.
        """
        # Aggregator A
        root_a = tmp_path / "agg_a"
        build_flat_aggregator(str(root_a), name="flat")

        # Aggregator B with a kit that symlinks A's projects/core
        root_b = tmp_path / "agg_b"
        os.makedirs(root_b / "kits")
        os.makedirs(root_b / "projects")
        os.symlink(str(root_a / "projects" / "core"),
                   str(root_b / "projects" / "core"))
        _write_json(
            str(root_b / "kits" / "core.kit.json"),
            {"name": "core", "always_active": True},
        )
        engine = AggregatorEngine(
            name="test_b", command="test_b",
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(root_b))
        # The symlink should resolve to the same realpath as A's tools.
        # In a single-aggregator discovery, only one canonical per realpath.
        fqcns = {p.fqcn for p in engine.projects if not p.get("_auto_realpath_alias")}
        # Both tools should still be canonical (no other FQCN reaches them
        # in this single-engine setup).
        assert "core:toolA" in fqcns
        assert "core:toolB" in fqcns
