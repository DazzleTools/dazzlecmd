#!/usr/bin/env python3
"""
claude-sesslog-datefix - Fix timestamps on Claude Code session log directories.

After git stash/switch operations on ~/.claude, file timestamps get reset to the
restore time. This tool parses the [[YYYY-MM-DD HH:MM:SS]] timestamps embedded
in sesslog files and restores correct mtime (last entry) and creation time
(first entry) for each file and directory.

Usage via dz:
    dz claude-sesslog-datefix                    # dry-run preview (default)
    dz claude-sesslog-datefix --apply            # apply timestamp fixes
    dz claude-sesslog-datefix --apply --verbose  # apply with per-file detail
    dz claude-sesslog-datefix --path /other/dir  # custom sesslogs path
"""

import argparse
import os
import platform
import re
import sys
from datetime import datetime
from pathlib import Path

# Timestamp pattern: [[2026-02-24 23:28:19]]
TS_PATTERN = re.compile(r"\[\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\]")

# How much to read from end of file for last timestamp
TAIL_READ_SIZE = 8192

# Fallback file priority (globs, checked in order)
# .sesslog_bash* is the most complete; others are fallbacks
SOURCE_FILE_PRIORITY = [
    ".sesslog_bash*",
    ".shell_bash*",
    ".tasks_bash*",
    ".Python_sesslog_bash*",
    ".Python_shell_bash*",
]


# ---------------------------------------------------------------------------
# Win32 creation time support (via pywin32)
# ---------------------------------------------------------------------------

_HAS_PYWIN32 = False
if platform.system() == "Windows":
    try:
        import win32file
        import win32con
        import pywintypes
        _HAS_PYWIN32 = True
    except ImportError:
        pass


def set_creation_time(path, dt):
    """Set file/directory creation time on Windows using pywin32.

    Returns True on success, False on failure or non-Windows platform.
    """
    if not _HAS_PYWIN32:
        return False

    try:
        path_obj = Path(path).resolve()
        wintime = pywintypes.Time(dt)

        # FILE_FLAG_BACKUP_SEMANTICS is required for opening directories
        flags = win32con.FILE_ATTRIBUTE_NORMAL
        if path_obj.is_dir():
            flags = win32con.FILE_FLAG_BACKUP_SEMANTICS

        FILE_WRITE_ATTRIBUTES = 0x100  # not always in win32con
        handle = win32file.CreateFile(
            str(path_obj),
            FILE_WRITE_ATTRIBUTES,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
            None,
            win32con.OPEN_EXISTING,
            flags,
            None,
        )

        win32file.SetFileTime(handle, wintime)
        handle.close()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Timestamp extraction
# ---------------------------------------------------------------------------

def extract_first_timestamp(filepath):
    """Read the first [[timestamp]] from a file. Reads first 4KB."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            chunk = f.read(4096)
        match = TS_PATTERN.search(chunk)
        if match:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    except OSError:
        pass
    return None


def extract_last_timestamp(filepath):
    """Read the last [[timestamp]] from a file. Seeks to end for efficiency."""
    try:
        file_size = os.path.getsize(filepath)
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            if file_size > TAIL_READ_SIZE:
                f.seek(file_size - TAIL_READ_SIZE)
                f.readline()  # discard partial first line
            chunk = f.read()

        matches = TS_PATTERN.findall(chunk)
        if matches:
            return datetime.strptime(matches[-1], "%Y-%m-%d %H:%M:%S")
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_source_file(directory):
    """Find the best timestamp source file in a directory using fallback priority."""
    dirpath = Path(directory)
    for pattern in SOURCE_FILE_PRIORITY:
        matches = sorted(dirpath.glob(pattern))
        if matches:
            return matches[0]
    return None


def find_all_log_files(directory):
    """Find all log files in a directory (for applying timestamps to)."""
    dirpath = Path(directory)
    files = []
    for pattern in SOURCE_FILE_PRIORITY:
        files.extend(dirpath.glob(pattern))
    return sorted(set(files))


def find_root_level_files(sesslogs_path):
    """Find sesslog files at the root level (not in subdirectories)."""
    root = Path(sesslogs_path)
    files = []
    for pattern in SOURCE_FILE_PRIORITY:
        files.extend(f for f in root.glob(pattern) if f.is_file())
    return sorted(set(files))


# ---------------------------------------------------------------------------
# Timestamp application
# ---------------------------------------------------------------------------

def apply_mtime(path, last_ts, dry_run):
    """Apply mtime to a file or directory.

    Returns (kind, old_dt, new_dt) tuple if changed, else None.
    """
    path = Path(path)
    current_mtime = datetime.fromtimestamp(path.stat().st_mtime)

    if last_ts and abs((current_mtime - last_ts).total_seconds()) > 1:
        if not dry_run:
            ts_epoch = last_ts.timestamp()
            os.utime(path, (ts_epoch, ts_epoch))
        return ("mtime", current_mtime, last_ts)
    return None


def apply_ctime(path, ctime_dt, dry_run):
    """Apply creation time to a file or directory via Win32 API.

    Returns (kind, old_dt, new_dt) tuple if changed, else None.
    """
    if not ctime_dt:
        return None
    try:
        path = Path(path)
        birth = datetime.fromtimestamp(path.stat().st_ctime)
        if abs((birth - ctime_dt).total_seconds()) > 1:
            if not dry_run:
                set_creation_time(path, ctime_dt)
            return ("ctime", birth, ctime_dt)
    except (OSError, AttributeError):
        pass
    return None


def apply_symlink_timestamps(symlink_path, first_ts, last_ts, dry_run, verbose):
    """Apply timestamps to a symlink itself (not its target).

    Returns list of (kind, old_dt, new_dt) tuples for changes made/planned.
    """
    changes = []
    path = Path(symlink_path)

    try:
        lstat = path.lstat()
    except OSError:
        return changes

    current_mtime = datetime.fromtimestamp(lstat.st_mtime)

    if last_ts and abs((current_mtime - last_ts).total_seconds()) > 1:
        if not dry_run:
            try:
                ts_epoch = last_ts.timestamp()
                os.utime(path, (ts_epoch, ts_epoch), follow_symlinks=False)
            except (OSError, NotImplementedError):
                # follow_symlinks=False not supported on all Windows/Python combos
                pass
        changes.append(("mtime", current_mtime, last_ts))

    return changes


def format_change(kind, old_dt, new_dt, name, prefix=""):
    """Format a timestamp change for display."""
    lines = []
    lines.append(f"  {prefix}{kind}: {name}")
    lines.append(
        f"         {old_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        f" -> {new_dt.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Directory processing
# ---------------------------------------------------------------------------

def _get_ref_ctime(ctime_source, dirpath):
    """Get creation time from a reference directory, if it exists."""
    if not ctime_source:
        return None
    ref_dir = ctime_source / dirpath.name
    if ref_dir.is_dir():
        try:
            return datetime.fromtimestamp(ref_dir.stat().st_ctime)
        except OSError:
            pass
    return None


def process_directory(dirpath, dry_run, verbose, ctime_source=None):
    """Process a single session directory.

    mtime comes from the last [[timestamp]] in sesslog files.
    ctime comes from --ctime-source reference directory only.

    Returns (success, changes_count).
    """
    source = find_source_file(dirpath)
    ref_ctime = _get_ref_ctime(ctime_source, dirpath)

    # If no sesslog files and no reference ctime, nothing to do
    if not source and not ref_ctime:
        if verbose:
            print(f"  SKIP {dirpath.name}/ -- no log files, no ctime reference")
        return False, 0

    # mtime always from logs
    last_ts = extract_last_timestamp(source) if source else None

    if not last_ts and not ref_ctime:
        if verbose:
            print(f"  SKIP {dirpath.name}/ -- no timestamps found")
        return False, 0

    changes = 0
    label = "[DRY RUN] " if dry_run else ""

    if ref_ctime and verbose:
        print(f"  ctime from reference: {dirpath.name}/"
              f" -> {ref_ctime.strftime('%Y-%m-%d %H:%M:%S')}")

    # Apply mtime to all log files in this directory
    all_files = find_all_log_files(dirpath) if source else []
    for f in all_files:
        change = apply_mtime(f, last_ts, dry_run)
        if change:
            if verbose:
                print(format_change(*change, f.name, label))
            changes += 1
        # Apply ctime from reference to log files too
        cchange = apply_ctime(f, ref_ctime, dry_run)
        if cchange:
            if verbose:
                print(format_change(*cchange, f.name, label))
            changes += 1

    # Apply to symlinks (e.g. transcript.jsonl) -- set symlink mtime, not target
    for item in dirpath.iterdir():
        if item.is_symlink():
            sym_changes = apply_symlink_timestamps(
                item, None, last_ts, dry_run, verbose
            )
            if sym_changes and verbose:
                for kind, old, new in sym_changes:
                    print(format_change(kind, old, new, f"{item.name} (symlink)", label))
            changes += len(sym_changes)

    # Apply mtime + ctime to directory itself
    change = apply_mtime(dirpath, last_ts, dry_run)
    if change:
        if verbose:
            print(format_change(*change, f"{dirpath.name}/", label))
        changes += 1
    cchange = apply_ctime(dirpath, ref_ctime, dry_run)
    if cchange:
        if verbose:
            print(format_change(*cchange, f"{dirpath.name}/", label))
        changes += 1

    return True, changes


def process_root_files(sesslogs_path, dry_run, verbose):
    """Process legacy sesslog files at the root of sesslogs/.

    Returns (file_count, changes_count).
    """
    root_files = find_root_level_files(sesslogs_path)
    changes = 0
    label = "[DRY RUN] " if dry_run else ""

    for f in root_files:
        last_ts = extract_last_timestamp(f)
        if not last_ts:
            if verbose:
                print(f"  SKIP root file {f.name} -- no timestamps")
            continue

        change = apply_mtime(f, last_ts, dry_run)
        if change:
            if verbose:
                print(format_change(*change, f"(root) {f.name}", label))
            changes += 1

    return len(root_files), changes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    """Entry point for dz claude-sesslog-datefix."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="dz claude-sesslog-datefix",
        description=(
            "Fix timestamps on ~/.claude/sesslogs/ directories and files. "
            "Parses [[YYYY-MM-DD HH:MM:SS]] entries in session logs to restore "
            "correct mtime (last activity) and creation time (session start)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  dz claude-sesslog-datefix                    Preview changes (dry-run)
  dz claude-sesslog-datefix --apply            Apply timestamp fixes
  dz claude-sesslog-datefix --apply -v         Apply with per-file detail
  dz claude-sesslog-datefix --path /other/dir  Use a different directory
        """,
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="apply changes (default is dry-run preview)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="show per-file timestamp changes",
    )
    parser.add_argument(
        "--path", type=str, default=None,
        help="path to sesslogs directory (default: ~/.claude/sesslogs)",
    )
    parser.add_argument(
        "--ctime-source", type=str, default=None,
        metavar="DIR",
        help="reference sesslogs directory to copy creation times from "
             "(matching subdirectory names)",
    )
    args = parser.parse_args(argv)

    dry_run = not args.apply

    # Resolve sesslogs path
    if args.path:
        sesslogs = Path(args.path)
    else:
        sesslogs = Path.home() / ".claude" / "sesslogs"

    if not sesslogs.is_dir():
        print(f"ERROR: {sesslogs} is not a directory", file=sys.stderr)
        return 1

    ctime_source = Path(args.ctime_source) if args.ctime_source else None
    if ctime_source and not ctime_source.is_dir():
        print(f"ERROR: ctime-source {ctime_source} is not a directory", file=sys.stderr)
        return 1

    mode = "DRY RUN (use --apply to commit changes)" if dry_run else "APPLYING CHANGES"
    print(f"Claude Sesslog DateFix -- {mode}")
    print(f"Target: {sesslogs}")
    if ctime_source:
        print(f"Ctime source: {ctime_source}")
    print()

    # Gather subdirectories
    subdirs = sorted(
        [d for d in sesslogs.iterdir() if d.is_dir()],
        key=lambda d: d.name.lower(),
    )

    total_dirs = len(subdirs)
    processed = 0
    skipped = 0
    total_changes = 0

    print(f"Found {total_dirs} session directories")
    print()

    for dirpath in subdirs:
        success, changes = process_directory(dirpath, dry_run, args.verbose, ctime_source)
        if success:
            processed += 1
            total_changes += changes
            if not args.verbose and changes > 0:
                src = find_source_file(dirpath)
                last = extract_last_timestamp(src) if src else None
                ts_str = last.strftime("%Y-%m-%d %H:%M") if last else "?"
                prefix = "[DRY RUN] " if dry_run else ""
                print(f"  {prefix}{dirpath.name}/ -> {ts_str}")
        else:
            skipped += 1

    # Process root-level files
    print()
    print("Root-level files:")
    root_count, root_changes = process_root_files(sesslogs, dry_run, args.verbose)
    total_changes += root_changes

    # Summary
    print()
    print("--- Summary ---")
    print(f"  Directories processed: {processed}/{total_dirs}"
          f" ({skipped} skipped -- no log files)")
    print(f"  Root-level files:      {root_count}")
    print(f"  Total timestamp fixes: {total_changes}")
    if dry_run:
        print()
        print("  This was a dry run. Use --apply to commit changes.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
