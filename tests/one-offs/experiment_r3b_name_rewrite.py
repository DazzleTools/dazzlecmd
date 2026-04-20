"""Round 3b experiment: name_rewrite missing entries + pure pass-through.

Meta-A (bonus): verify the default-to-last-segment path when a virtual
kit has `tools` but no `name_rewrite`, or name_rewrite with partial coverage.
"""

import sys
import os
import tempfile
import json
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "packages", "dazzlecmd-lib", "src"))

from dazzlecmd_lib.engine import AggregatorEngine


def setup_aggregator_root():
    """Build a minimal aggregator tree in a temp dir with 3 canonicals and
    a virtual kit that has partial name_rewrite coverage."""
    root = tempfile.mkdtemp(prefix="dz_r3b_")
    os.makedirs(os.path.join(root, "kits"))
    os.makedirs(os.path.join(root, "projects", "demo", "tool-alpha"))
    os.makedirs(os.path.join(root, "projects", "demo", "tool-beta"))
    os.makedirs(os.path.join(root, "projects", "demo", "tool-gamma"))

    # Canonical demo kit
    with open(os.path.join(root, "kits", "demo.kit.json"), "w") as f:
        json.dump({
            "_schema_version": 1,
            "name": "demo",
            "always_active": True,
            "tools": ["demo:tool-alpha", "demo:tool-beta", "demo:tool-gamma"]
        }, f)

    # Virtual kit with PARTIAL name_rewrite (only alpha rewritten)
    with open(os.path.join(root, "kits", "vpartial.kit.json"), "w") as f:
        json.dump({
            "_schema_version": 1,
            "name": "vpartial",
            "virtual": True,
            "always_active": True,
            "tools": [
                "demo:tool-alpha",
                "demo:tool-beta",
                "demo:tool-gamma",
            ],
            "name_rewrite": {
                "demo:tool-alpha": "alpha-short",
                # beta and gamma NOT rewritten -- should default to last segment
            }
        }, f)

    # Virtual kit with NO name_rewrite at all (pure pass-through)
    with open(os.path.join(root, "kits", "vnone.kit.json"), "w") as f:
        json.dump({
            "_schema_version": 1,
            "name": "vnone",
            "virtual": True,
            "always_active": True,
            "tools": ["demo:tool-alpha", "demo:tool-beta"],
        }, f)

    # Tool manifests
    for tool in ["tool-alpha", "tool-beta", "tool-gamma"]:
        tool_dir = os.path.join(root, "projects", "demo", tool)
        with open(os.path.join(tool_dir, ".dazzlecmd.json"), "w") as f:
            json.dump({
                "name": tool,
                "description": f"Demo {tool}",
                "version": "0.0.1",
            }, f)

    return root


def test(name, fn):
    try:
        fn()
        print(f"  [PASS] {name}")
    except AssertionError as exc:
        print(f"  [FAIL] {name}: {exc}")
    except Exception as exc:
        print(f"  [ERROR] {name}: {type(exc).__name__}: {exc}")


root = setup_aggregator_root()
print(f"Aggregator root: {root}\n")

try:
    engine = AggregatorEngine(name="dztest", command="dztest",
                              tools_dir="projects", kits_dir="kits",
                              manifest=".dazzlecmd.json", is_root=True,
                              config_dir=tempfile.mkdtemp(prefix="dz_cfg_"))
    engine.discover(project_root=root)
    idx = engine.fqcn_index

    print("Canonical index:")
    for fqcn in sorted(idx.canonical_index):
        print(f"  {fqcn}")
    print("\nAlias index:")
    for alias, canonical in sorted(idx.alias_index.items()):
        print(f"  {alias} -> {canonical}")
    print()

    # ============================================================

    def test_partial_rewrite_alpha_uses_rewrite():
        assert "vpartial:alpha-short" in idx.alias_index
        assert idx.alias_index["vpartial:alpha-short"] == "demo:tool-alpha"

    def test_partial_rewrite_beta_defaults_to_last_segment():
        """With no rewrite for tool-beta, alias should default to 'tool-beta'"""
        assert "vpartial:tool-beta" in idx.alias_index
        assert idx.alias_index["vpartial:tool-beta"] == "demo:tool-beta"

    def test_partial_rewrite_gamma_defaults_to_last_segment():
        assert "vpartial:tool-gamma" in idx.alias_index
        assert idx.alias_index["vpartial:tool-gamma"] == "demo:tool-gamma"

    def test_pass_through_no_rewrite():
        """Virtual kit with no name_rewrite at all."""
        assert "vnone:tool-alpha" in idx.alias_index
        assert "vnone:tool-beta" in idx.alias_index

    def test_resolve_works_for_defaulted_alias():
        project, note = idx.resolve("vpartial:tool-beta")
        assert project is not None
        assert project["_fqcn"] == "demo:tool-beta"

    def test_resolve_works_for_rewritten_alias():
        project, note = idx.resolve("vpartial:alpha-short")
        assert project is not None
        assert project["_fqcn"] == "demo:tool-alpha"

    test("partial rewrite: alpha uses 'alpha-short'",
         test_partial_rewrite_alpha_uses_rewrite)
    test("partial rewrite: beta defaults to 'tool-beta'",
         test_partial_rewrite_beta_defaults_to_last_segment)
    test("partial rewrite: gamma defaults to 'tool-gamma'",
         test_partial_rewrite_gamma_defaults_to_last_segment)
    test("pass-through (no rewrite dict)", test_pass_through_no_rewrite)
    test("resolve works for defaulted alias", test_resolve_works_for_defaulted_alias)
    test("resolve works for rewritten alias", test_resolve_works_for_rewritten_alias)

finally:
    # Cleanup temp dirs -- OK to use shutil here since they're temp fixtures
    shutil.rmtree(root, ignore_errors=True)
    print("\nDone.")
