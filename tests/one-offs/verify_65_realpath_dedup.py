"""One-off verification for issue #65 realpath-based auto-aliasing.

Constructs a synthetic two-aggregator setup where aggregator B reaches
aggregator A's tools via TWO distinct paths (a direct junction to A's
tools dir + a nested-aggregator junction to A itself). Both paths
realpath to the same physical script.

Confirms that:
- engine.projects contains only the canonical (no duplicates)
- alias_index contains the demoted FQCNs with source="auto-realpath"
- engine._realpath_index maps each physical script to its canonical FQCN

Cleans up after itself (junctions removed, tmp dir deleted).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile


def _mk_junction(target_path: str, source_path: str) -> bool:
    """Create a Windows directory junction. Returns True on success."""
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", target_path, source_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"junction failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def _rm_junction(path: str) -> None:
    """Remove a Windows directory junction (NOT its target)."""
    subprocess.run(["cmd", "/c", "rmdir", path], capture_output=True)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="dedup_verify_")
    print(f"Working in: {tmp}")

    agg_a = os.path.join(tmp, "a")
    agg_b = os.path.join(tmp, "b")

    # Build aggregator A: one tool, one kit
    os.makedirs(os.path.join(agg_a, "kits"))
    tool_dir = os.path.join(agg_a, "projects", "core", "echotool")
    os.makedirs(tool_dir)
    with open(os.path.join(agg_a, "kits", "core.kit.json"), "w") as f:
        json.dump({"name": "core", "always_active": True}, f)
    with open(os.path.join(agg_a, "projects", "core", ".kit.json"), "w") as f:
        json.dump({
            "name": "core",
            "tools_dir": ".",
            "manifest": ".dazzlecmd.json",
            "tools": ["core:echotool"],
        }, f)
    with open(os.path.join(tool_dir, ".dazzlecmd.json"), "w") as f:
        json.dump({
            "name": "echotool",
            "description": "Echo a thing",
            "runtime": {
                "type": "python",
                "entry_point": "main",
                "script_path": "echotool.py",
            },
        }, f)
    with open(os.path.join(tool_dir, "echotool.py"), "w") as f:
        f.write("def main(argv=None):\n    print('echo!')\n    return 0\n")

    # Build aggregator B
    os.makedirs(os.path.join(agg_b, "kits"))
    os.makedirs(os.path.join(agg_b, "projects"))
    # B has its own 'core' kit registry pointer; we'll junction B/projects/core
    # to A/projects/core so the tool is reachable at b's "core:echotool"
    with open(os.path.join(agg_b, "kits", "core.kit.json"), "w") as f:
        json.dump({"name": "core", "always_active": True}, f)
    if not _mk_junction(
        os.path.join(agg_b, "projects", "core"),
        os.path.join(agg_a, "projects", "core"),
    ):
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    # B also has a kit pointing at A as a nested aggregator
    with open(os.path.join(agg_b, "kits", "a.kit.json"), "w") as f:
        json.dump({"name": "a", "always_active": True}, f)
    if not _mk_junction(
        os.path.join(agg_b, "projects", "a"),
        agg_a,
    ):
        _rm_junction(os.path.join(agg_b, "projects", "core"))
        shutil.rmtree(tmp, ignore_errors=True)
        return 1

    print("Setup complete. Discovering...")
    print()

    from dazzlecmd_lib.engine import AggregatorEngine
    engine = AggregatorEngine(
        name="b", command="b",
        tools_dir="projects", kits_dir="kits",
        manifest=".dazzlecmd.json",
        project_root=agg_b,
    )
    engine.discover()

    print("engine.projects (active dispatch surface):")
    for p in engine.projects:
        print(f"  {p['_fqcn']}  _dir={p['_dir']}")
    print()
    print("engine.all_projects (full discovery):")
    for p in engine.all_projects:
        flag = " [AUTO-REALPATH-ALIAS]" if p.get("_auto_realpath_alias") else ""
        print(f"  {p['_fqcn']}{flag}")
    print()
    print("alias_index entries:")
    for a, c in sorted(engine.fqcn_index.alias_index.items()):
        src = engine.fqcn_index._alias_sources.get(a, "(virtual)")
        print(f"  {a} -> {c}  [{src}]")
    print()
    print("_realpath_index entries:")
    for real, fq in sorted(engine._realpath_index.items()):
        print(f"  {fq} <- {real}")
    print()

    # Verify expected behavior
    canonical_count = len(engine.projects)
    auto_aliases = [
        a for a in engine.fqcn_index.alias_index
        if engine.fqcn_index._alias_sources.get(a) == "auto-realpath"
    ]
    assert canonical_count == 1, (
        f"Expected 1 canonical project (after dedup), got {canonical_count}"
    )
    assert len(auto_aliases) == 1, (
        f"Expected 1 auto-realpath alias, got {len(auto_aliases)}: {auto_aliases}"
    )
    assert engine._realpath_index, "Expected _realpath_index to be populated"

    print("VERIFIED: realpath dedup fires correctly.")

    # Cleanup
    _rm_junction(os.path.join(agg_b, "projects", "core"))
    _rm_junction(os.path.join(agg_b, "projects", "a"))
    shutil.rmtree(tmp, ignore_errors=True)
    print("Cleanup done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
