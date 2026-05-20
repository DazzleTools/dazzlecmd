"""Tool import logic for dazzlecmd — add repos as projects."""

import json
import os
import subprocess
import sys

from dazzlecmd_lib.paths import create_link, is_linked_project


def add_from_local(source_path, projects_dir, namespace, link_mode="copy",
                   tool_name=None, *, reserved_commands=None,
                   manifest_name=".dazzlecmd.json", command="dz"):
    """Import a local repo/directory as an aggregator project.

    Args:
        source_path: Absolute path to source directory.
        projects_dir: Path to the aggregator's tools directory
            (``projects/`` for dazzlecmd, ``tools/`` for wtf-windows etc.).
        namespace: Namespace to place the tool in (e.g., ``"core"``).
        link_mode: ``"link"`` for symlink/junction, ``"copy"`` for file copy.
        tool_name: Override name (default: from manifest or dirname).
        reserved_commands: Set of command names that may not be used as
            tool names (BLOCKER F1 fix -- no more
            ``from dazzlecmd.cli import RESERVED_COMMANDS`` inline).
            Defaults to the empty set when None.
        manifest_name: Per-tool manifest filename to look for
            (``".dazzlecmd.json"`` / ``".wtf.json"`` / ``".amdead.json"``).
        command: CLI command name for user-facing strings (``"dz"``,
            ``"wtf"``, ``"amdead"``). Used in error messages so the
            suggestion matches the user's actual CLI.

    Returns:
        dict with import results, or None on failure.
    """
    source_path = os.path.abspath(source_path)

    if not os.path.isdir(source_path):
        print(f"Error: Path does not exist: {source_path}", file=sys.stderr)
        return None

    # Check for per-tool manifest
    manifest_path = os.path.join(source_path, manifest_name)
    if not os.path.isfile(manifest_path):
        print(f"Error: No {manifest_name} found in {source_path}",
              file=sys.stderr)
        print(f"  Create one manually or use '{command} new' to generate a template.",
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

    # Check reserved names against the aggregator's policy
    reserved = reserved_commands or set()
    if name in reserved:
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


