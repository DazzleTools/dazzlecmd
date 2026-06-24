"""
extract-all/_matcher.py

Pattern matching against extracted file trees.

Supports both glob and regex patterns. Each pattern is auto-classified:
    - If the pattern contains regex-specific syntax (^, $, \\., \\d, \\w,
      \\s, (?:, etc.) it is treated as a regular expression.
    - Otherwise it is treated as an fnmatch glob (* and ? wildcards).

Examples:
    "amdkmdag.sys"    -- glob (literal filename)
    "*.sys"           -- glob (all .sys files)
    "amd*.dll"        -- glob (any AMD-prefixed dll)
    "^amd.+\\.sys$"   -- regex (anchored)
    "baz\\..*$"       -- regex (literal dot, then anything)
    "(?i)readme"      -- regex (inline case flag, though we set IGNORECASE anyway)

Default behavior is case-insensitive matching, since the use case is
inspecting Windows installers where filenames are case-insensitive.
"""

from __future__ import annotations

import fnmatch
import os
import pathlib
import re


# Substrings that indicate a pattern is regex (not glob). Order doesn't matter.
_REGEX_INDICATORS = (
    "^", "$",                                  # anchors
    r"\.", r"\d", r"\w", r"\s",                # character classes (literal/digit/word/space)
    r"\D", r"\W", r"\S", r"\b", r"\B",         # negated/boundary classes
    "(?:", "(?=", "(?!", "(?<",                # grouping / lookarounds
    "(?i", "(?m", "(?s", "(?x",                # inline flags
)


def looks_like_regex(pattern: str) -> bool:
    """Heuristic classifier: does `pattern` look like a regular expression?

    A pattern is treated as regex if it contains any of the indicators in
    `_REGEX_INDICATORS`. Otherwise treated as glob.

    Edge case: a pattern that LOOKS like regex but fails to compile falls
    back to glob inside `find_matches`.
    """
    return any(ind in pattern for ind in _REGEX_INDICATORS)


def find_matches(
    root: str | os.PathLike,
    pattern: str,
    case_insensitive: bool = True,
) -> list[pathlib.Path]:
    """Recursively find files under `root` whose name matches `pattern`.

    Auto-detects glob vs regex. Returns absolute paths in shallow-first
    order (sorted by depth ascending, then alphabetically within depth)
    so `--first` returns the shallowest match deterministically.
    """
    root_path = pathlib.Path(root).resolve()
    if not root_path.exists():
        return []

    use_regex = looks_like_regex(pattern)
    regex_compiled: re.Pattern | None = None

    if use_regex:
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex_compiled = re.compile(pattern, flags)
        except re.error:
            # Pattern looked like regex but didn't compile -- fall back to glob.
            use_regex = False

    glob_needle = pattern.lower() if (case_insensitive and not use_regex) else pattern
    matches: list[tuple[int, pathlib.Path]] = []

    for dirpath, _dirnames, filenames in os.walk(root_path):
        for fname in filenames:
            if use_regex:
                if regex_compiled.search(fname):
                    _record_match(matches, root_path, dirpath, fname)
            else:
                cmp_name = fname.lower() if case_insensitive else fname
                if fnmatch.fnmatchcase(cmp_name, glob_needle):
                    _record_match(matches, root_path, dirpath, fname)

    matches.sort(key=lambda t: (t[0], str(t[1]).lower()))
    return [p for _depth, p in matches]


def _record_match(
    matches: list[tuple[int, pathlib.Path]],
    root: pathlib.Path,
    dirpath: str,
    fname: str,
) -> None:
    full_path = pathlib.Path(dirpath) / fname
    rel = full_path.relative_to(root)
    depth = len(rel.parts) - 1
    matches.append((depth, full_path))


def shallowest_match(matches: list[pathlib.Path]) -> pathlib.Path | None:
    """Return the match closest to root (shallowest depth). None if no matches."""
    return matches[0] if matches else None


def archive_lineage(
    match: pathlib.Path,
    staging: pathlib.Path,
    source_name: str,
) -> str:
    """Render a match path as an archive-lineage string.

    Each `<archive>.extracted/` boundary in the relative path becomes `::`,
    making the nesting visible. Examples:

        staging/Drivers/foo.sys                    -> setup.exe::Drivers/foo.sys
        staging/inner.zip.extracted/foo.dll        -> setup.exe::inner.zip::foo.dll
        staging/a.7z.extracted/b.cab.extracted/x   -> setup.exe::a.7z::b.cab::x
        staging/sub/inner.zip.extracted/x          -> setup.exe::sub/inner.zip::x
    """
    rel = match.resolve().relative_to(staging.resolve())
    s = str(rel).replace(os.sep, "/").replace(".extracted/", "::")
    return f"{source_name}::{s}"
