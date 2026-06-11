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

**Boundary contract** (see ``dazzlecmd_lib.core.__init__`` for the full
statement): this package is the link ENGINE -- detection, classification,
creation, scanning; everything returns data. The user-facing ``dz links`` CLI
(argparse, table/JSON display, exit codes) lives in the ``projects/core/links``
tool, which imports this engine -- the same engine/CLI split as
``core.safedel`` and its tool. A duplicate engine in the tool is a contract
violation (enforced by ``tests/test_constitutional_contract.py``).
"""

from __future__ import annotations

# Subprocess timeouts (seconds): PowerShell New-Item pays shell startup
# cost (hence the headroom); rmdir of a junction is a fast local op.
_PS_LINK_TIMEOUT = 15
_RMDIR_TIMEOUT = 10

import os
import subprocess
import sys

# Link DETECTION / classification (detect_link, LinkInfo, the LINK_* varieties,
# canonicalize_path) -- relocated from the `links` tool into this constitutional
# primitive so lib code (e.g. core.safedel's classifier) imports it normally
# rather than via a sibling-tool sys.path hack. The link CREATION/removal helpers
# (create_link, remove_link, ...) are defined below.
from dazzlecmd_lib.core.links._detect import (  # noqa: E402,F401
    detect_link,
    scan_directory,
    matches_filter,
    canonicalize_path,
    canonicalize_target,
    LinkInfo,
    LINK_SYMLINK,
    LINK_JUNCTION,
    LINK_HARDLINK,
    LINK_SHORTCUT,
    LINK_URLSHORTCUT,
    LINK_DAZZLELINK,
    ALL_LINK_TYPES,
)


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
    """Create a directory link on Windows via PowerShell ``New-Item``.

    Tries a symbolic link first (``New-Item -ItemType SymbolicLink``; needs admin
    or Developer Mode), then falls back to a junction (``New-Item -ItemType
    Junction``; no elevation, directory-only). Returns "symlink", "junction", or
    None.

    PowerShell is used instead of ``cmd /c mklink``: mklink fails silently when
    invoked as a subprocess from bash/WSL (CLAUDE.md rule #4; #37 Tier-1
    criterion -- "PowerShell New-Item replaces cmd.exe /c mklink"). PowerShell
    gives reliable exit codes and error reporting across invocation contexts.
    """
    def _ps_new_item(item_type):
        # Single-quote the paths as PowerShell literal strings; double any
        # embedded single quote (PowerShell's literal-escape). $ErrorAction=Stop
        # makes a failed New-Item return a non-zero exit code.
        src = source_path.replace("'", "''")
        tgt = target_path.replace("'", "''")
        ps = (
            "$ErrorActionPreference='Stop'; "
            f"New-Item -ItemType {item_type} -Path '{tgt}' -Target '{src}' "
            "| Out-Null"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=_PS_LINK_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        # Confirm the link actually materialized (a non-zero rc OR a missing
        # link both mean failure -> let the next mechanism try).
        return result.returncode == 0 and is_linked_project(target_path)

    if _ps_new_item("SymbolicLink"):
        return "symlink"
    if _ps_new_item("Junction"):
        return "junction"

    print(f"Error: Could not create link: {target_path} -> {source_path}",
          file=sys.stderr)
    print("  New-Item -ItemType SymbolicLink failed (may need admin / Developer "
          "Mode); Junction also failed.", file=sys.stderr)
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
                capture_output=True, text=True, timeout=_RMDIR_TIMEOUT
            )
            return result.returncode == 0
        else:
            os.unlink(target_path)
            return True
    except (OSError, subprocess.TimeoutExpired):
        return False
