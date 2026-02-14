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


def create_link(source_path, target_path):
    """Create a directory symlink or junction.

    Tries symlink first, falls back to junction on Windows.
    Returns the actual link mode used, or None on failure.
    """
    if sys.platform == "win32":
        return _create_link_windows(source_path, target_path)
    else:
        return _create_link_unix(source_path, target_path)


def _create_link_windows(source_path, target_path):
    """Create directory link on Windows: mklink /D -> mklink /J fallback."""
    # Try symbolic link first
    try:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/D", target_path, source_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return "symlink"
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Fall back to junction (no admin required)
    try:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", target_path, source_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return "junction"
    except (OSError, subprocess.TimeoutExpired):
        pass

    print(f"Error: Could not create link: {target_path} -> {source_path}",
          file=sys.stderr)
    print("  mklink /D failed (may need admin). mklink /J also failed.",
          file=sys.stderr)
    return None


def _create_link_unix(source_path, target_path):
    """Create directory symlink on Unix."""
    try:
        os.symlink(source_path, target_path)
        return "symlink"
    except OSError as exc:
        print(f"Error: Could not create symlink: {exc}", file=sys.stderr)
        return None


def is_linked_project(tool_dir):
    """Check if a project directory is a symlink or junction.

    Returns True for both symlinks and Windows junctions.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(tool_dir))
            if attrs == -1:  # INVALID_FILE_ATTRIBUTES
                return False
            return bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
        except (OSError, AttributeError):
            return os.path.islink(tool_dir)
    return os.path.islink(tool_dir)


def get_link_target(tool_dir):
    """Get the target of a symlink/junction.

    Returns the target path string, or None if not a link.
    """
    if not is_linked_project(tool_dir):
        return None
    try:
        return os.readlink(tool_dir)
    except OSError:
        return None


def remove_link(target_path):
    """Remove a symlink/junction without affecting the source.

    On Windows, uses rmdir to remove the junction point.
    On Unix, uses os.unlink.
    """
    if not is_linked_project(target_path):
        return False

    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["cmd", "/c", "rmdir", target_path],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        else:
            os.unlink(target_path)
            return True
    except (OSError, subprocess.TimeoutExpired):
        return False
