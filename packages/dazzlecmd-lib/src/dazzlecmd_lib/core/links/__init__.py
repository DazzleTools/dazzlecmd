"""``dazzlecmd_lib.core.links`` -- constitutional link primitives.

Symlink / junction detection and creation. The first inhabitants of the
``dazzlecmd_lib.core`` constitutional namespace (see ``core/__init__.py``):
every aggregator that consumes dazzlecmd-lib gets these automatically; they
are load-bearing for correctness across mode-switching, ``render_info``
"Linked to:" status, and any link-aware operation.

Relocated VERBATIM from ``dazzlecmd_lib.paths`` in v0.8.0 (the DazzleEntity
foundation release). ``dazzlecmd_lib.paths`` re-exports the four public
helpers (``is_linked_project``, ``get_link_target``, ``create_link``,
``remove_link``) for backward compatibility, so existing
``from dazzlecmd_lib.paths import is_linked_project`` call sites keep working
unchanged. The non-link path helpers (``resolve_relative_path``,
``ensure_windows_executable_suffix``, ``translate_wsl_path``,
``which_with_pathext``) stay in ``paths`` -- they are general path utilities,
not constitutional link primitives.
"""

from __future__ import annotations

import os
import subprocess
import sys


def is_linked_project(tool_dir):
    """Check if a project directory is a symlink or junction.

    Returns True for both symlinks and Windows junctions.

    Cross-platform: on Windows, uses
    ``ctypes.windll.kernel32.GetFileAttributesW`` to detect the
    ``FILE_ATTRIBUTE_REPARSE_POINT`` flag (catches both symlinks AND
    junctions). Falls back to ``os.path.islink`` if the ctypes call
    fails. On POSIX, uses ``os.path.islink`` directly.

    Ported verbatim from dazzlecmd ``importer.py:141`` to dazzlecmd-lib
    in v0.7.33 so library ``render_info`` can surface "Linked to:"
    status without dazzlecmd-package coupling. dazzlecmd-internal and
    wtf-windows callers continue to import from their respective
    package's ``importer`` module (which now re-exports from here).
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

    Ported verbatim from dazzlecmd ``importer.py:158`` to dazzlecmd-lib
    in v0.7.33 alongside :func:`is_linked_project`.
    """
    if not is_linked_project(tool_dir):
        return None
    try:
        return os.readlink(tool_dir)
    except OSError:
        return None


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
