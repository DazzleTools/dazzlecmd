"""Tests for virtual kits (Phase 4e Commit 2, v0.7.26).

Covers:

- Loader detection of ``"virtual": true`` manifests, including the
  skip-in-repo-manifest behaviour (virtual kits named after canonical
  kits must not inherit tool lists).
- Engine ``_apply_virtual_kits`` installing aliases after the canonical
  FQCN index is built.
- ``name_rewrite`` with partial, full, and absent coverage (absent
  entries default to the canonical FQCN's last segment).
- Cross-aggregator Option A: virtual kits defined inside a nested
  aggregator are collected during recursive discovery, rewritten with
  the parent FQCN prefix, and applied at the root.
- Rule 9a warning (not error): virtual kit whose name shadows a
  canonical kit's name still loads; rule 9b catches per-alias shadowing.
- Dispatch end-to-end via alias FQCN.
"""

import json
import os

import pytest

from dazzlecmd_lib.engine import AggregatorEngine


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _write_tool(tool_dir, tool_name):
    """Create a minimal Python tool manifest + stub script."""
    os.makedirs(tool_dir, exist_ok=True)
    _write_json(
        os.path.join(tool_dir, ".dazzlecmd.json"),
        {
            "name": tool_name,
            "description": f"{tool_name} tool",
            "version": "0.0.1",
            "runtime": {"type": "python", "script_path": f"{tool_name}.py"},
        },
    )
    with open(os.path.join(tool_dir, f"{tool_name}.py"), "w") as f:
        f.write(f"# stub {tool_name}\n")


def _build_aggregator_with_virtual(root):
    """Build a minimal aggregator tree with:
    - Canonical 'demo' kit containing 3 tools (alpha, beta, gamma)
    - Virtual 'grouped' kit aliasing alpha + beta with custom shorts
    """
    # Canonical demo kit
    _write_json(
        os.path.join(root, "kits", "demo.kit.json"),
        {"name": "demo", "always_active": True, "tools": [
            "demo:tool-alpha", "demo:tool-beta", "demo:tool-gamma",
        ]},
    )
    for tool in ["tool-alpha", "tool-beta", "tool-gamma"]:
        _write_tool(os.path.join(root, "projects", "demo", tool), tool)

    # Virtual 'grouped' kit
    _write_json(
        os.path.join(root, "kits", "grouped.kit.json"),
        {
            "_schema_version": 1,
            "name": "grouped",
            "virtual": True,
            "always_active": True,
            "tools": ["demo:tool-alpha", "demo:tool-beta"],
            "name_rewrite": {
                "demo:tool-alpha": "alpha",
                "demo:tool-beta": "beta",
            },
        },
    )


class TestLoaderVirtualKitDetection:
    """The loader detects ``"virtual": true`` and carries through the
    manifest's ``tools`` + ``name_rewrite`` fields. Virtual kits skip
    in-repo manifest lookup."""

    def test_loader_marks_virtual_kit(self, tmp_path, monkeypatch):
        """A virtual kit manifest round-trips through the loader with
        its virtual flag preserved and its declared fields intact."""
        from dazzlecmd_lib.loader import discover_kits
        root = str(tmp_path)
        os.makedirs(os.path.join(root, "kits"))
        os.makedirs(os.path.join(root, "projects"))
        _write_json(
            os.path.join(root, "kits", "my-virt.kit.json"),
            {
                "_schema_version": 1,
                "name": "my-virt",
                "virtual": True,
                "tools": ["dz:tool"],
                "name_rewrite": {"dz:tool": "t"},
            },
        )
        kits = discover_kits(
            os.path.join(root, "kits"),
            os.path.join(root, "projects"),
        )
        assert len(kits) == 1
        kit = kits[0]
        assert kit.get("virtual") is True
        assert kit["name"] == "my-virt"
        assert kit["tools"] == ["dz:tool"]
        assert kit["name_rewrite"] == {"dz:tool": "t"}

    def test_virtual_kit_skips_in_repo_manifest_lookup(self, tmp_path, monkeypatch):
        """A virtual kit named after an existing projects/<name>/.kit.json
        MUST NOT inherit that canonical kit's tool list. The skeleton
        experiment surfaced this bug; v0.7.26 fixes it structurally."""
        from dazzlecmd_lib.loader import discover_kits
        root = str(tmp_path)
        os.makedirs(os.path.join(root, "kits"))
        os.makedirs(os.path.join(root, "projects", "shared"))
        # Canonical-style in-repo manifest for "shared"
        _write_json(
            os.path.join(root, "projects", "shared", ".kit.json"),
            {"name": "shared", "tools": ["a", "b", "c", "d"]},
        )
        # Virtual kit with the same name
        _write_json(
            os.path.join(root, "kits", "shared.kit.json"),
            {"name": "shared", "virtual": True, "tools": ["x:y"]},
        )
        kits = discover_kits(
            os.path.join(root, "kits"),
            os.path.join(root, "projects"),
        )
        # Should NOT have inherited the 4 in-repo tools -- just our 1
        assert kits[0].get("virtual") is True
        assert kits[0]["tools"] == ["x:y"]


class TestApplyVirtualKitsSingleLevel:
    """Virtual kits at the root level install aliases after the canonical
    FQCN index is built."""

    def test_alias_resolves_via_virtual_kit(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(root)
        _build_aggregator_with_virtual(root)

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        assert "grouped:alpha" in engine.fqcn_index.alias_index
        assert engine.fqcn_index.alias_index["grouped:alpha"] == "demo:tool-alpha"

        project, ctx = engine.fqcn_index.resolve("grouped:alpha")
        assert project is not None
        assert project["_fqcn"] == "demo:tool-alpha"
        assert ctx.resolution_kind == "alias"
        assert ctx.alias_fqcn == "grouped:alpha"

    def test_name_rewrite_default_to_last_segment(self, tmp_path, monkeypatch):
        """A virtual kit with ``tools`` but NO ``name_rewrite`` (or a
        partial map) uses the canonical FQCN's last segment as the
        alias short by default."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(root)
        _write_json(
            os.path.join(root, "kits", "demo.kit.json"),
            {"name": "demo", "always_active": True, "tools": [
                "demo:t1", "demo:t2", "demo:t3",
            ]},
        )
        for t in ["t1", "t2", "t3"]:
            _write_tool(os.path.join(root, "projects", "demo", t), t)
        _write_json(
            os.path.join(root, "kits", "v-default.kit.json"),
            {
                "_schema_version": 1,
                "name": "v-default",
                "virtual": True,
                "always_active": True,
                "tools": ["demo:t1", "demo:t2", "demo:t3"],
                "name_rewrite": {"demo:t1": "one"},
                # t2 and t3 have no rewrite -> default to last segment
            },
        )

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        assert "v-default:one" in engine.fqcn_index.alias_index
        assert "v-default:t2" in engine.fqcn_index.alias_index   # defaulted
        assert "v-default:t3" in engine.fqcn_index.alias_index   # defaulted

    def test_virtual_kit_does_not_add_to_short_index(self, tmp_path, monkeypatch):
        """Rule 7c: aliases never populate short_index. The alias short
        ('alpha') must NOT be a short-name candidate; only the canonical
        short ('tool-alpha') is."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(root)
        _build_aggregator_with_virtual(root)

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        assert "alpha" not in engine.fqcn_index.short_index
        assert "tool-alpha" in engine.fqcn_index.short_index

    def test_inactive_virtual_kit_contributes_no_aliases(self, tmp_path, monkeypatch):
        """A virtual kit disabled via user config does NOT install
        aliases -- its entries are skipped during _apply_virtual_kits."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(root)
        _build_aggregator_with_virtual(root)

        # Disable the virtual kit via config
        _write_json(
            str(tmp_path / "config.json"),
            {"_schema_version": 1, "disabled_kits": ["grouped"]},
        )

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        assert "grouped:alpha" not in engine.fqcn_index.alias_index
        assert "grouped:beta" not in engine.fqcn_index.alias_index


class TestCrossAggregatorOptionA:
    """Virtual kits defined inside a nested aggregator are collected
    during recursive discovery, rewritten with the parent FQCN prefix,
    and applied at the root. Validates the Option A fix for the
    cross-aggregator gap found during R3b experiments."""

    def _build_nested_with_virtual(self, root):
        """Parent has 'core' with one tool.
        Nested 'sub' aggregator has 'core' with two tools AND a virtual
        kit 'bundled' aliasing one of them."""
        # Parent
        _write_json(
            os.path.join(root, "kits", "core.kit.json"),
            {"name": "core", "always_active": True, "tools": ["core:parent-tool"]},
        )
        _write_tool(os.path.join(root, "projects", "core", "parent-tool"), "parent-tool")

        # Nested aggregator: 'sub' kit contains its own kits/ directory
        _write_json(
            os.path.join(root, "kits", "sub.kit.json"),
            {
                "name": "sub",
                "always_active": True,
                "_override_tools_dir": "tools",
                "_override_manifest": ".dazzlecmd.json",
            },
        )
        sub_root = os.path.join(root, "projects", "sub")
        _write_json(
            os.path.join(sub_root, "kits", "core.kit.json"),
            {"name": "core", "always_active": True, "tools": [
                "core:inner-a", "core:inner-b",
            ]},
        )
        _write_tool(os.path.join(sub_root, "tools", "core", "inner-a"), "inner-a")
        _write_tool(os.path.join(sub_root, "tools", "core", "inner-b"), "inner-b")

        # Virtual kit DEFINED INSIDE the nested sub aggregator.
        _write_json(
            os.path.join(sub_root, "kits", "bundled.kit.json"),
            {
                "_schema_version": 1,
                "name": "bundled",
                "virtual": True,
                "always_active": True,
                "tools": ["core:inner-a"],
                "name_rewrite": {"core:inner-a": "first"},
            },
        )

    def test_nested_virtual_kit_is_collected_and_rewritten(self, tmp_path, monkeypatch):
        """The nested virtual kit's name and target FQCNs are prefixed
        with the parent aggregator's FQCN path during discovery."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(os.path.join(root, "kits"))
        os.makedirs(os.path.join(root, "projects"))
        self._build_nested_with_virtual(root)

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        # Nested virtual kit 'bundled' should be namespaced as 'sub:bundled'
        # from root's perspective; alias FQCN becomes 'sub:bundled:first'
        # and targets the prefixed canonical 'sub:core:inner-a'.
        assert "sub:bundled:first" in engine.fqcn_index.alias_index
        assert engine.fqcn_index.alias_index["sub:bundled:first"] == "sub:core:inner-a"

    def test_nested_virtual_alias_dispatches(self, tmp_path, monkeypatch):
        """End-to-end: alias FQCN resolves to the nested canonical project."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(os.path.join(root, "kits"))
        os.makedirs(os.path.join(root, "projects"))
        self._build_nested_with_virtual(root)

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        project, ctx = engine.fqcn_index.resolve("sub:bundled:first")
        assert project is not None
        assert project["_fqcn"] == "sub:core:inner-a"
        assert ctx.resolution_kind == "alias"

    def test_nested_virtual_kit_visible_in_kits_list(self, tmp_path, monkeypatch):
        """Cross-aggregator virtual kits must be merged into self.kits
        so `dz kit list` / `dz kit status` display them. Regression
        guard for a display-gap bug surfaced by the v0.7.26 tester-agent
        checklist run: without this merge, nested virtuals dispatch
        correctly but are invisible to display commands."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(os.path.join(root, "kits"))
        os.makedirs(os.path.join(root, "projects"))
        self._build_nested_with_virtual(root)

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        kit_names = {k.get("_kit_name") or k.get("name") for k in engine.kits}
        assert "sub:bundled" in kit_names, (
            "Nested virtual kit 'bundled' inside 'sub' aggregator should "
            "appear in engine.kits as 'sub:bundled' (prefixed) so "
            "display commands can render it."
        )
        active_names = {
            k.get("_kit_name") or k.get("name") for k in engine.active_kits
        }
        assert "sub:bundled" in active_names

    def test_disabling_nested_aggregator_disables_its_virtual_kits(
        self, tmp_path, monkeypatch
    ):
        """When the containing aggregator is disabled via user config,
        nested virtual kits become inactive and their aliases are not
        installed."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(os.path.join(root, "kits"))
        os.makedirs(os.path.join(root, "projects"))
        self._build_nested_with_virtual(root)

        _write_json(
            str(tmp_path / "config.json"),
            {"_schema_version": 1, "disabled_kits": ["sub"]},
        )

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        assert "sub:bundled:first" not in engine.fqcn_index.alias_index


class TestRule9aWarning:
    """Rule 9a: a virtual kit whose name matches a canonical kit's name
    loads successfully but emits a stderr warning. Rule 9b (alias
    shadowing) still rejects per-alias collisions."""

    def test_9a_warning_not_error(self, tmp_path, monkeypatch, capsys):
        """A virtual kit named 'demo' (same as the canonical kit)
        loads and installs aliases; a warning is emitted."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(root)

        # Canonical demo kit
        _write_json(
            os.path.join(root, "kits", "demo.kit.json"),
            {"name": "demo", "always_active": True, "tools": ["demo:t1"]},
        )
        _write_tool(os.path.join(root, "projects", "demo", "t1"), "t1")

        # Virtual kit with the same name -- uses a different short so
        # rule 9b does NOT fire. (If it aliased "demo:t1" with short "t1",
        # the alias FQCN would be "demo:t1" which is the canonical FQCN
        # and rule 9b would reject it.)
        _write_json(
            os.path.join(root, "kits", "demo-virt.kit.json"),
            {
                "name": "demo",
                "virtual": True,
                "always_active": True,
                "tools": ["demo:t1"],
                "name_rewrite": {"demo:t1": "renamed"},
            },
        )

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        captured = capsys.readouterr()
        assert "shares its name with a canonical kit" in captured.err
        assert "demo" in captured.err

        # The alias was still installed (warning, not error)
        assert "demo:renamed" in engine.fqcn_index.alias_index

    def test_9b_still_rejects_per_alias_shadowing(self, tmp_path, monkeypatch, capsys):
        """A virtual kit attempting to alias a FQCN that equals a
        canonical FQCN is rejected at the alias level (9b), even when
        9a fires a warning at the kit level."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(root)
        _write_json(
            os.path.join(root, "kits", "demo.kit.json"),
            {"name": "demo", "always_active": True, "tools": ["demo:keep"]},
        )
        _write_tool(os.path.join(root, "projects", "demo", "keep"), "keep")
        # Virtual kit 'demo' that tries to alias "demo:keep" -> short "keep"
        # Alias FQCN would be "demo:keep" which IS the canonical -- 9b rejects.
        _write_json(
            os.path.join(root, "kits", "demo-virt.kit.json"),
            {
                "name": "demo",
                "virtual": True,
                "always_active": True,
                "tools": ["demo:keep"],
                "name_rewrite": {"demo:keep": "keep"},
            },
        )

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        captured = capsys.readouterr()
        assert "rule 9b" in captured.err or "shadow a real tool" in captured.err
        # Canonical still dispatches cleanly
        project, ctx = engine.fqcn_index.resolve("demo:keep")
        assert project["_fqcn"] == "demo:keep"
        assert ctx.resolution_kind == "canonical"


class TestFullDispatchEnd2End:
    """Smoke test: virtual-kit alias dispatches through the full engine
    path (not just the FQCN index)."""

    def test_alias_dispatch_via_engine_resolve_command(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(root)
        _build_aggregator_with_virtual(root)

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        project, ctx = engine.resolve_command("grouped:alpha")
        assert project is not None
        assert project["_fqcn"] == "demo:tool-alpha"
        assert ctx.resolution_kind == "alias"
        assert ctx.alias_fqcn == "grouped:alpha"

    def test_alias_via_find_project(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        root = str(tmp_path / "root")
        os.makedirs(root)
        _build_aggregator_with_virtual(root)

        engine = AggregatorEngine(
            tools_dir="projects", kits_dir="kits",
            manifest=".dazzlecmd.json",
        )
        engine.discover(project_root=root)

        project, ctx = engine.find_project("grouped:alpha")
        assert project["_fqcn"] == "demo:tool-alpha"
