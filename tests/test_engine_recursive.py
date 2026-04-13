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
        short_names = {p["_short_name"] for p in engine.projects}
        assert short_names == {"toolA", "toolB"}

    def test_flat_fqcn_format(self, tmp_path):
        build_flat_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        fqcns = {p["_fqcn"] for p in engine.projects}
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
        assert project["_fqcn"] == "core:toolA"
        assert note is None


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
        fqcns = {p["_fqcn"] for p in engine.projects}
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
        parent_tool = [p for p in engine.projects if p["_short_name"] == "parent_tool"][0]
        assert parent_tool["_kit_import_name"] == "core"
        # Child tools have kit_import_name "child" (the parent's view)
        child_a = [p for p in engine.projects if p["_short_name"] == "child_toolA"][0]
        assert child_a["_kit_import_name"] == "child"

    def test_recursive_resolve_short_name_no_collision(self, tmp_path):
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        project, note = engine.resolve_command("child_toolA")
        assert project is not None
        assert project["_fqcn"] == "child:core:child_toolA"
        assert note is None  # no collision, no notification

    def test_recursive_resolve_explicit_fqcn(self, tmp_path):
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        project, note = engine.resolve_command("child:core:child_toolA")
        assert project is not None
        assert project["_fqcn"] == "child:core:child_toolA"

    def test_registry_override_custom_manifest(self, tmp_path):
        """The child uses .child.json manifest, not .dazzlecmd.json."""
        build_nested_aggregator(str(tmp_path))
        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=str(tmp_path))
        # If the override isn't honored, child tools wouldn't be discovered
        child_fqcns = [p["_fqcn"] for p in engine.projects if p["_kit_import_name"] == "child"]
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
            {
                "name": "leaf",
                "_fqcn": "a:b:c:d:leaf",
                "_short_name": "leaf",
                "_kit_import_name": "a",
                "_dir": "/fake",
                "description": "deep tool",
            }
        ]
        engine._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert "deeply nested" in captured.err
        assert "a:b:c:d:leaf" in captured.err
        assert "5 segments" in captured.err
        assert "rerooting" in captured.err

    def test_hint_silenceable_via_dz_quiet(self, monkeypatch, capsys):
        monkeypatch.setenv("DZ_QUIET", "1")
        engine = AggregatorEngine(is_root=True)
        engine.projects = [
            {
                "name": "leaf",
                "_fqcn": "a:b:c:d:leaf",
                "_short_name": "leaf",
                "_kit_import_name": "a",
                "_dir": "/fake",
                "description": "deep tool",
            }
        ]
        engine._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_hint_skipped_when_not_root(self, capsys):
        """Imported aggregators (is_root=False) never emit the hint --
        only the top-level engine does."""
        engine = AggregatorEngine(is_root=False)
        engine.projects = [
            {
                "name": "leaf",
                "_fqcn": "a:b:c:d:leaf",
                "_short_name": "leaf",
                "_kit_import_name": "a",
                "_dir": "/fake",
                "description": "deep tool",
            }
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
        assert project["_fqcn"] == "core:toolA"
        # Notification should mention extra as an alternative
        assert note is not None
        assert "extra" in note
        assert "core:toolA" in note

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
        assert project["_fqcn"] == "extra:core:toolA"


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

        fqcns = {p["_fqcn"] for p in engine.projects}
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
        assert project["_fqcn"] == "other:core:shared"
        assert note is None  # no collision anymore

    def test_silenced_tool_suppresses_reroot_hint(self, tmp_path, monkeypatch, capsys):
        """When the only deeply-nested tool is silenced, no hint fires."""
        engine = AggregatorEngine(is_root=True)
        engine.projects = [
            {
                "name": "leaf",
                "_fqcn": "a:b:c:d:leaf",
                "_short_name": "leaf",
                "_kit_import_name": "a",
                "_dir": "/fake",
                "description": "deep tool",
            }
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
            {
                "name": "leaf",
                "_fqcn": "deepkit:sub:core:leaf",
                "_short_name": "leaf",
                "_kit_import_name": "deepkit",
                "_dir": "/fake",
                "description": "deep tool",
            }
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
            {
                "name": "silenced",
                "_fqcn": "a:b:c:d:silenced",
                "_short_name": "silenced",
                "_kit_import_name": "a",
                "_dir": "/fake",
                "description": "silenced tool",
            },
            {
                "name": "notsilenced",
                "_fqcn": "x:y:z:w:notsilenced",
                "_short_name": "notsilenced",
                "_kit_import_name": "x",
                "_dir": "/fake",
                "description": "other deep tool",
            },
        ]
        engine._maybe_emit_reroot_hint()
        captured = capsys.readouterr()
        assert "deeply nested" in captured.err
        assert "notsilenced" in captured.err
        assert "silenced" not in captured.err.split("notsilenced")[0]
