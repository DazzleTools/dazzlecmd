"""Cross-platform path helpers -- shared library for setup and runtime layers.

Covers the three recurring path concerns both layers face:

    1. Relative-path resolution against a tool's directory (runtime `script_path`
       and setup `steps` alike). The v0.7.18 shell_env fix was an instance of
       this; this module generalizes the pattern so every caller behaves
       consistently.

    2. Windows executable suffix handling. Authors often declare binaries
       without extensions; on Windows we append `.exe` (or consult PATHEXT)
       for display and dispatch.

    3. WSL path translation. A tool running under WSL may need to pass paths
       to or from a Windows-native process. This module provides the common
       `/mnt/c/foo <-> C:\\foo` translation without attempting to handle
       every edge case (UNC paths, symlinks, etc.).

Design: every helper is a pure function taking explicit inputs. No global
state, no caching, no environment mutation. Callers compose as needed.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional


def resolve_relative_path(candidate: str, tool_dir: str) -> str:
    """Resolve a relative path against a tool's directory when doing so yields
    an existing file.

    Absolute paths pass through unchanged. Paths beginning with a shell
    variable expansion marker (`$VAR`, `%VAR%`) pass through unchanged -- the
    shell owns that resolution.

    Otherwise, join `candidate` against `tool_dir`; if the joined path points
    to an existing file, return it. Else return the original `candidate`
    (caller decides how to proceed -- typically passes to the shell/subprocess
    for its own resolution against cwd).

    This is the v0.7.18 shell_env.script fix, generalized. Every caller that
    accepts a relative path from a manifest field should use this helper to
    keep behavior consistent across runners.
    """
    if not candidate:
        return candidate
    if os.path.isabs(candidate):
        return candidate
    if candidate.startswith("$") or candidate.startswith("%"):
        return candidate
    joined = os.path.join(tool_dir, candidate)
    if os.path.isfile(joined):
        return joined
    return candidate


def ensure_windows_executable_suffix(name: str) -> str:
    """On Windows, append `.exe` to names that have no extension.

    Returns the original `name` unchanged on non-Windows hosts, on empty input,
    or when `name` already has an extension (trusted as-is).

    Intended for display / logging / manifest normalization. For actual
    executable lookup use `which_with_pathext` -- shutil.which consults PATHEXT
    natively and handles the full suffix search.
    """
    if os.name != "nt" or not name:
        return name
    _, ext = os.path.splitext(name)
    if ext:
        return name
    return name + ".exe"


def translate_wsl_path(path: str, direction: str) -> str:
    """Translate between WSL (/mnt/<drive>/...) and Windows (<drive>:\\...) forms.

    Args:
        path: Input path.
        direction: "to_windows" converts `/mnt/c/foo` -> `C:\\foo`.
                   "to_wsl" converts `C:\\foo` -> `/mnt/c/foo`.

    Paths that do not match the expected source form pass through unchanged.
    UNC paths, drive-relative paths (e.g., `C:foo` without a separator), and
    paths with unusual drive letters are not handled -- this helper is for
    the common `/mnt/<single-letter>/...` and `<letter>:...` cases.

    Raises:
        ValueError: if `direction` is neither "to_windows" nor "to_wsl".
    """
    if direction == "to_windows":
        if path.startswith("/mnt/") and len(path) >= 7 and path[6] == "/":
            drive = path[5].upper()
            rest = path[7:].replace("/", "\\")
            return f"{drive}:\\{rest}"
        return path
    if direction == "to_wsl":
        if len(path) >= 3 and path[1] == ":" and path[2] in ("\\", "/"):
            drive = path[0].lower()
            rest = path[3:].replace("\\", "/")
            return f"/mnt/{drive}/{rest}"
        return path
    raise ValueError(
        f"direction must be 'to_windows' or 'to_wsl', got {direction!r}"
    )


def which_with_pathext(name: str) -> Optional[str]:
    """Locate an executable on PATH. Returns full path or None.

    Thin wrapper over `shutil.which` that documents PATHEXT behavior: on
    Windows, passing `mytool` will find `mytool.exe` / `mytool.bat` / etc.
    per the PATHEXT environment variable. On POSIX hosts, PATHEXT is ignored
    and the name is matched exactly.

    Exists as a named helper so caller sites read "we are locating an
    executable" rather than "we are probing a path."
    """
    if not name:
        return None
    return shutil.which(name)
