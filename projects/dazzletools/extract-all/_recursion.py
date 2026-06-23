"""
extract-all/_recursion.py

Recursive extraction loop. Given a source archive and a destination directory,
extracts the source, then walks the extracted tree and recursively extracts
any nested archives discovered inside.

Each nested archive is extracted into a sibling directory named
"<archive-stem>.extracted/" so the original archive file remains alongside
its extracted contents (useful for hash verification).

Cycle protection: tracks SHA-256 of every archive extracted; if the same
hash reappears at a deeper depth, that archive is skipped.

Depth limit: bails out at `max_depth` levels of nesting (default 8).
"""

from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass, field

# Add this directory to sys.path so sibling modules import cleanly regardless
# of how dazzlecmd's loader spec_from_file_locations us.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _engine
import _staging


@dataclass
class ExtractionStats:
    """Summary of a recursive extraction run."""
    archives_extracted: int = 0
    archives_skipped_cycle: int = 0
    archives_skipped_depth: int = 0
    archives_failed: int = 0
    bytes_extracted: int = 0
    max_depth_reached: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (path, error)


def recursive_extract(
    z7: str,
    source_archive: str | os.PathLike,
    dest_root: str | os.PathLike,
    max_depth: int = 8,
    quiet: bool = False,
    log=sys.stderr,
) -> ExtractionStats:
    """Extract `source_archive` into `dest_root`, then recursively extract any
    nested archives discovered.

    The source archive is extracted directly into `dest_root` (not into a
    nested subdir). Nested archives are extracted into sibling
    `<stem>.extracted/` directories.

    Returns ExtractionStats describing what happened.
    """
    stats = ExtractionStats()
    seen_hashes: set[str] = set()

    source_path = pathlib.Path(source_archive).resolve()
    dest_root_path = pathlib.Path(dest_root).resolve()
    dest_root_path.mkdir(parents=True, exist_ok=True)

    def _say(msg: str) -> None:
        if not quiet:
            print(msg, file=log, flush=True)

    # --- Layer 0: extract the source itself ---
    source_hash = _staging.sha256_full(source_path)
    seen_hashes.add(source_hash)

    _say(f"[extract-all] L0  extracting {source_path.name}")
    ok, err = _engine.extract_archive(z7, str(source_path), str(dest_root_path))
    if not ok:
        stats.failures.append((str(source_path), err))
        stats.archives_failed += 1
        _say(f"[extract-all] L0  FAILED: {err}")
        return stats
    stats.archives_extracted += 1
    if err:
        # 7z warning (partial success)
        _say(f"[extract-all] L0  warning: {err}")

    # --- Recursive descent into extracted tree ---
    _walk_and_extract(
        z7=z7,
        root=dest_root_path,
        staging_root=dest_root_path,
        current_depth=1,
        max_depth=max_depth,
        seen_hashes=seen_hashes,
        stats=stats,
        say=_say,
    )

    return stats


def _format_lineage(candidate: pathlib.Path, staging: pathlib.Path) -> str:
    """Render `candidate` relative to staging, with `.extracted/` boundaries
    rewritten as `::` so the archive nesting is visible in one glance.

    Examples:
        staging/Bin64/7z.exe                          -> Bin64/7z.exe
        staging/Setup.exe.extracted/$PLUGINSDIR/x.exe -> Setup.exe::$PLUGINSDIR/x.exe
        staging/a.7z.extracted/b.cab.extracted/x      -> a.7z::b.cab::x
    """
    try:
        rel = candidate.resolve().relative_to(staging.resolve())
    except ValueError:
        return str(candidate)
    return str(rel).replace(os.sep, "/").replace(".extracted/", "::")


def _walk_and_extract(
    z7: str,
    root: pathlib.Path,
    staging_root: pathlib.Path,
    current_depth: int,
    max_depth: int,
    seen_hashes: set[str],
    stats: ExtractionStats,
    say,
) -> None:
    """Walk `root` looking for archive-shaped files; recursively extract them.

    `current_depth` is the archive-nesting depth at which discovered archives
    sit (1 = direct children of staging_root, after layer 0). `staging_root`
    is preserved across recursion so progress messages can render the full
    archive lineage of each candidate (e.g. `Setup.exe::$PLUGINSDIR/x.exe`).
    """
    if current_depth > max_depth:
        return

    # Snapshot the current set of files (we'll add new ones as we extract).
    # We re-walk after each extraction batch to discover newly-extracted nested
    # archives.
    archive_candidates = _scan_for_archive_candidates(root)

    extracted_this_layer: list[pathlib.Path] = []

    for candidate in archive_candidates:
        # Skip files we've extracted already (their .extracted sibling exists).
        sibling = candidate.with_name(candidate.name + ".extracted")
        if sibling.exists():
            continue

        # Probe: is this actually an archive 7z can read?
        if not _engine.is_archive(z7, str(candidate)):
            continue

        lineage = _format_lineage(candidate, staging_root)

        # Cycle check: have we extracted this exact content already?
        try:
            chash = _staging.sha256_full(candidate)
        except OSError as e:
            stats.failures.append((str(candidate), f"hash failed: {e}"))
            continue
        if chash in seen_hashes:
            stats.archives_skipped_cycle += 1
            say(f"[extract-all] L{current_depth}  cycle-skip {lineage}")
            continue
        seen_hashes.add(chash)

        # Extract into sibling .extracted directory.
        sibling.mkdir(parents=True, exist_ok=True)
        say(f"[extract-all] L{current_depth}  extracting {lineage}")
        ok, err = _engine.extract_archive(z7, str(candidate), str(sibling))
        if not ok:
            stats.failures.append((str(candidate), err))
            stats.archives_failed += 1
            say(f"[extract-all] L{current_depth}  FAILED: {err}  ({lineage})")
            # Clean up partial sibling dir on hard failure
            try:
                if not any(sibling.iterdir()):
                    sibling.rmdir()
            except OSError:
                pass
            continue

        stats.archives_extracted += 1
        if err:
            say(f"[extract-all] L{current_depth}  warning: {err}  ({lineage})")
        if current_depth > stats.max_depth_reached:
            stats.max_depth_reached = current_depth
        extracted_this_layer.append(sibling)

    if not extracted_this_layer:
        return

    # Descend into newly extracted directories at the next depth.
    if current_depth + 1 > max_depth:
        stats.archives_skipped_depth += sum(
            len(_scan_for_archive_candidates(d)) for d in extracted_this_layer
        )
        say(f"[extract-all] depth limit ({max_depth}) reached; not descending further")
        return

    for newly_extracted in extracted_this_layer:
        _walk_and_extract(
            z7=z7,
            root=newly_extracted,
            staging_root=staging_root,
            current_depth=current_depth + 1,
            max_depth=max_depth,
            seen_hashes=seen_hashes,
            stats=stats,
            say=say,
        )


# Extensions worth probing as candidate archives. 7z handles many formats but
# we narrow the candidates here to avoid probing every file in the extracted
# tree (which would be slow on large extractions).
_ARCHIVE_EXTENSIONS = {
    # Compressed archives
    ".7z", ".zip", ".rar", ".tar", ".gz", ".bz2", ".xz", ".lzma", ".lzh",
    # Disk images
    ".iso", ".img", ".vhd", ".vhdx", ".wim",
    # Windows installer formats
    ".msi", ".cab", ".msu",
    # Self-extracting / installer wrappers
    ".exe",
    # Other
    ".arj", ".dmg", ".rpm", ".deb",
}


def _scan_for_archive_candidates(root: pathlib.Path) -> list[pathlib.Path]:
    """Return files under `root` whose extension suggests they may be archives."""
    candidates: list[pathlib.Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _ARCHIVE_EXTENSIONS:
                candidates.append(pathlib.Path(dirpath) / fname)
    return candidates
