"""
extract-all -- Recursively extract archives and locate files within them.

Usage:
    dz extract-all <source> <pattern1> [<pattern2> ...]

The source archive is staged under %USERPROFILE%/extract-all/<sha12>/, then
fully expanded (every nested archive recursively unpacked into a sibling
.extracted/ directory). Each pattern is searched against the resulting tree
and matching paths are reported, grouped by pattern.

Patterns are auto-classified:
    - Glob (fnmatch syntax): "amd*.dll", "*.sys", "readme.txt"
    - Regex: "^amd.+\\.sys$", "baz\\..*$", anything containing
      ^ $ \\. \\d \\w \\s (?: (?= (?<  etc.

Disk-saving modes:
    --print-locate    Extract, print archive-lineage paths, then delete the
                      staging directory. Useful for "where does X live?"
                      queries without keeping ~hundreds of MB on disk.
    --extract-matches Extract, then delete every file in the staging tree that
                      does not match one of the requested patterns (and prune
                      empty directories). Keeps only what you asked for.

Examples:
    dz extract-all amd-driver.exe amdkmdag.sys
    dz extract-all installer.exe "*.sys" "*.dll"
    dz extract-all bundle.zip "^amd.+\\.sys$" license.txt
    dz extract-all foo.7z "*.md" "baz\\..*$"
    dz extract-all driver.exe --print-locate amdkmdag.sys
    dz extract-all driver.exe --extract-matches "*.sys"

Exit codes:
    0  -- at least one match for every pattern
    1  -- some patterns had no matches
    2  -- fatal error (no 7z, source missing, extraction failed)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sys
from typing import Iterable

# Ensure sibling modules import cleanly under dazzlecmd's loader.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _engine
import _matcher
import _recursion
import _staging


def _resolve_source(raw: str) -> pathlib.Path:
    """Normalize a user-supplied path. Expands ~ and resolves relative paths."""
    return pathlib.Path(os.path.expanduser(os.path.expandvars(raw))).resolve()


def _format_size(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024:
            return f"{f:.1f} {unit}" if unit != "B" else f"{int(f)} B"
        f /= 1024
    return f"{f:.1f} PB"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="extract-all",
        description=(
            "Recursively extract an archive and locate files within it. "
            "Patterns may be glob (fnmatch) or regex (auto-detected)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  dz extract-all driver.exe amdkmdag.sys\n"
            "  dz extract-all setup.exe \"*.sys\" \"*.dll\"\n"
            "  dz extract-all bundle.7z \"^amd.+\\.sys$\"\n"
            "  dz extract-all driver.exe --print-locate amdkmdag.sys\n"
            "  dz extract-all driver.exe --extract-matches \"*.sys\"\n"
        ),
    )
    p.add_argument("source", nargs="?", help="Archive to extract (exe, zip, msi, 7z, etc.)")
    p.add_argument(
        "patterns",
        nargs="*",
        help="One or more filename patterns to locate (glob or regex; auto-detected)",
    )
    p.add_argument(
        "--max-depth",
        type=int,
        default=8,
        metavar="N",
        help="Maximum archive-nesting depth to descend (default: 8)",
    )
    p.add_argument(
        "--first",
        action="store_true",
        help="Print only the shallowest match for each pattern",
    )

    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--print-locate",
        action="store_true",
        help="Print archive-lineage paths and delete the staging dir afterward (saves disk)",
    )
    mode.add_argument(
        "--extract-matches",
        action="store_true",
        help="Keep ONLY files matching the patterns; prune everything else from staging",
    )

    p.add_argument(
        "--re-extract",
        action="store_true",
        help="Force re-extraction even if staging directory already exists",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress extraction progress output",
    )
    p.add_argument(
        "--staging-root",
        metavar="DIR",
        default=None,
        help=f"Staging root (default: {_staging.DEFAULT_STAGING_ROOT})",
    )
    p.add_argument(
        "--seven-zip-path",
        metavar="PATH",
        default=None,
        help="Path to 7z binary (overrides PATH lookup; can also set DZ_SEVEN_ZIP env)",
    )
    p.add_argument(
        "--list-cache",
        action="store_true",
        help="List cached extractions and exit",
    )
    p.add_argument(
        "--clear-cache",
        metavar="SHA12",
        default=None,
        help="Delete a single cache entry by sha12 prefix and exit",
    )
    return p


def _cmd_list_cache(staging_root: pathlib.Path | None) -> int:
    entries = _staging.list_cache(staging_root)
    if not entries:
        print("(cache empty)")
        return 0
    print(f"{'SHA12':<14} {'SIZE':>12}  SOURCE")
    print("-" * 70)
    for e in entries:
        size = int(e.get("size_bytes", 0) or 0)
        print(f"{e['sha12']:<14} {_format_size(size):>12}  {e.get('source_name', '?')}")
    return 0


def _cmd_clear_cache(sha12_prefix: str, staging_root: pathlib.Path | None) -> int:
    entries = _staging.list_cache(staging_root)
    matches = [e for e in entries if e["sha12"].startswith(sha12_prefix)]
    if not matches:
        print(f"no cache entry matching '{sha12_prefix}'", file=sys.stderr)
        return 2
    if len(matches) > 1:
        print(f"ambiguous prefix '{sha12_prefix}' matches {len(matches)} entries:", file=sys.stderr)
        for m in matches:
            print(f"  {m['sha12']}  {m.get('source_name', '?')}", file=sys.stderr)
        return 2
    target = matches[0]["stage_dir"]
    print(f"removing {target}")
    return 0 if _staging.clear_cache_entry(target) else 1


def _prune_to_matches(staging: pathlib.Path, keep: set[pathlib.Path], say) -> tuple[int, int]:
    """Delete every file in `staging` that is not in `keep`. Then prune empty dirs.

    Returns (files_deleted, bytes_freed).
    """
    deleted = 0
    freed = 0
    keep_resolved = {p.resolve() for p in keep}

    for dirpath, _dirnames, filenames in os.walk(staging):
        for fname in filenames:
            full = pathlib.Path(dirpath) / fname
            if full.resolve() in keep_resolved:
                continue
            try:
                size = full.stat().st_size
            except OSError:
                size = 0
            try:
                full.unlink()
                deleted += 1
                freed += size
            except OSError as e:
                say(f"[extract-all] could not delete {full}: {e}")

    # Prune empty dirs (post-order so we drop leaves first).
    for dirpath, _dirnames, _filenames in os.walk(staging, topdown=False):
        d = pathlib.Path(dirpath)
        if d == staging:
            continue
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    return deleted, freed


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(list(argv) if argv is not None else None)

    staging_root = pathlib.Path(ns.staging_root) if ns.staging_root else None

    # Cache-management commands -- handle before requiring 7z / source.
    if ns.list_cache:
        return _cmd_list_cache(staging_root)
    if ns.clear_cache:
        return _cmd_clear_cache(ns.clear_cache, staging_root)

    # From here on, source + patterns are required.
    if not ns.source:
        parser.error("source archive is required")
    if not ns.patterns:
        parser.error("at least one pattern is required")

    def _say(msg: str) -> None:
        if not ns.quiet:
            print(msg, file=sys.stderr, flush=True)

    # Locate 7z.
    z7 = _engine.find_seven_zip(ns.seven_zip_path)
    if not z7:
        print(_engine.SEVEN_ZIP_INSTALL_HINT, file=sys.stderr)
        return 2
    _say(f"[extract-all] using 7z: {z7}")

    # Validate source.
    source = _resolve_source(ns.source)
    if not source.exists():
        print(f"source not found: {source}", file=sys.stderr)
        return 2
    if not source.is_file():
        print(f"source is not a file: {source}", file=sys.stderr)
        return 2

    # Stable cache key from content hash.
    source_sha = _staging.sha256_full(source)
    staging = (staging_root or _staging.DEFAULT_STAGING_ROOT) / source_sha[:12]

    if ns.re_extract and staging.exists():
        _say(f"[extract-all] re-extract requested: clearing {staging}")
        _staging.clear_cache_entry(staging)

    already_extracted = staging.exists() and any(staging.iterdir())

    if not already_extracted:
        staging.mkdir(parents=True, exist_ok=True)
        _staging.write_source_record(staging, source, full_sha256=source_sha)
        stats = _recursion.recursive_extract(
            z7=z7,
            source_archive=source,
            dest_root=staging,
            max_depth=ns.max_depth,
            quiet=ns.quiet,
        )
        _say(
            f"[extract-all] done: {stats.archives_extracted} archives, "
            f"{stats.archives_failed} failed, "
            f"{stats.archives_skipped_cycle} cycle-skips, "
            f"{stats.archives_skipped_depth} depth-skips, "
            f"max nesting={stats.max_depth_reached}"
        )
        if stats.archives_extracted == 0:
            print(f"extraction failed: {stats.failures}", file=sys.stderr)
            return 2
    else:
        _say(f"[extract-all] cache hit: {staging}")

    # Search the extracted tree for each pattern.
    print(f"\n[extract-all] staging: {staging}")
    print(f"[extract-all] source:  {source.name} (sha256={source_sha[:16]}...)\n")

    all_matches: dict[str, list[pathlib.Path]] = {}
    keep_set: set[pathlib.Path] = set()
    total_misses = 0

    for pattern in ns.patterns:
        kind = "regex" if _matcher.looks_like_regex(pattern) else "glob"
        matches = _matcher.find_matches(staging, pattern)
        if ns.first and matches:
            matches = matches[:1]

        all_matches[pattern] = matches
        keep_set.update(matches)

        print(f"pattern: {pattern!r}  [{kind}]")
        if not matches:
            print("  (no matches)")
            total_misses += 1
        else:
            for m in matches:
                lineage = _matcher.archive_lineage(m, staging, source.name)
                if ns.print_locate:
                    print(f"  {lineage}")
                else:
                    print(f"  {lineage}")
                    try:
                        rel = m.relative_to(staging)
                        print(f"    -> {rel}")
                    except ValueError:
                        print(f"    -> {m}")
        print()

    # Disk-saving post-processing.
    if ns.print_locate:
        _say(f"[extract-all] --print-locate: removing staging {staging}")
        try:
            shutil.rmtree(staging)
        except OSError as e:
            print(f"warning: failed to remove staging: {e}", file=sys.stderr)
    elif ns.extract_matches:
        _say(f"[extract-all] --extract-matches: pruning non-matching files from {staging}")
        deleted, freed = _prune_to_matches(staging, keep_set, _say)
        _say(f"[extract-all] pruned {deleted} files ({_format_size(freed)} freed)")

    return 1 if total_misses else 0


if __name__ == "__main__":
    sys.exit(main())
