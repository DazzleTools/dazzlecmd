"""Tool import logic for dazzlecmd — add repos as projects."""

import json
import os
import subprocess
import sys


def add_from_local(source_path, projects_dir, namespace, link_mode="copy",
                   tool_name=None):
    """Import a local repo/directory as a dazzlecmd project.

    Args:
        source_path: Absolute path to source directory
        projects_dir: Path to dazzlecmd's projects/ directory
        namespace: Namespace to place the tool in (e.g., "core")
        link_mode: "link" for symlink/junction, "copy" for file copy
        tool_name: Override name (default: from manifest or dirname)

    Returns:
        dict with import results, or None on failure
    """
    source_path = os.path.abspath(source_path)

    if not os.path.isdir(source_path):
        print(f"Error: Path does not exist: {source_path}", file=sys.stderr)
        return None

    # Check for .dazzlecmd.json
    manifest_path = os.path.join(source_path, ".dazzlecmd.json")
    if not os.path.isfile(manifest_path):
        print(f"Error: No .dazzlecmd.json found in {source_path}",
              file=sys.stderr)
        print("  Create one manually or use 'dz new' to generate a template.",
              file=sys.stderr)
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: Could not read manifest: {exc}", file=sys.stderr)
        return None

    # Resolve tool name
    name = tool_name or manifest.get("name")
    if not name:
        name = os.path.basename(source_path).lower().replace(" ", "-")

    # Check reserved names
    from dazzlecmd.cli import RESERVED_COMMANDS
    if name in RESERVED_COMMANDS:
        print(f"Error: '{name}' is a reserved command name.",
              file=sys.stderr)
        print("  Use --name to specify a different name.", file=sys.stderr)
        return None

    # Create namespace directory if needed
    ns_dir = os.path.join(projects_dir, namespace)
    os.makedirs(ns_dir, exist_ok=True)

    # Check if target already exists
    target_dir = os.path.join(ns_dir, name)
    if os.path.exists(target_dir) or is_linked_project(target_dir):
        print(f"Error: '{namespace}/{name}' already exists at {target_dir}",
              file=sys.stderr)
        return None

    # Create link or copy
    if link_mode == "link":
        actual_mode = create_link(source_path, target_dir)
        if actual_mode is None:
            return None
    else:
        print("Error: Copy mode not yet implemented. Use --link.",
              file=sys.stderr)
        return None

    return {
        "name": name,
        "namespace": namespace,
        "source_path": source_path,
        "link_mode": actual_mode,
        "target_dir": target_dir,
    }


# Link helpers (create_link, remove_link, is_linked_project, get_link_target)
# live in dazzlecmd_lib.paths as of v0.7.47 -- they're aggregator-agnostic
# primitives any consumer of dazzlecmd_lib can use. This module re-exports
# them for callers that import from dazzlecmd.importer.
from dazzlecmd_lib.paths import (  # noqa: F401
    create_link,
    get_link_target,
    is_linked_project,
    remove_link,
)
