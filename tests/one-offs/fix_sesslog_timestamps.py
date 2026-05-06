#!/usr/bin/env python3
"""
Fix timestamps on ~/.claude/sesslogs/ directories and files.

After a git stash/switch operation, all file timestamps get reset to the
restore time. This script parses the [[YYYY-MM-DD HH:MM:SS]] timestamps
embedded in sesslog files and restores correct mtime (last entry) and
creation time (first entry) for each file and directory.

Usage:
    python fix_sesslog_timestamps.py                    # dry-run by default
    python fix_sesslog_timestamps.py --apply            # actually apply changes
    python fix_sesslog_timestamps.py --verbose          # show per-file details
    python fix_sesslog_timestamps.py --path /some/path  # custom sesslogs path
"""

import argparse
import ctypes
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Timestamp pattern: [[2026-02-24 23:28:19]]
TS_PATTERN = re.compile(r"\[\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\]")

# How much to read from end of file for last timestamp
TAIL_READ_SIZE = 8192

# Fallback file priority (globs, checked in order)
SOURCE_FILE_PRIORITY = [
    ".sesslog_bash*",
    ".shell_bash*",
    ".tasks_bash*",
    ".Python_sesslog_bash*",
    ".Python_shell_bash*",
]


# ---------------------------------------------------------------------------
# Win32 creation time support
# ---------------------------------------------------------------------------

def _datetime_to_filetime(dt):
    """Convert a datetime to a Windows FILETIME (100-ns intervals since 1601-01-01)."""
    EPOCH_DIFF = 116444736000000000  # 100-ns intervals between 1601 and 1970
    ft = int(dt.timestamp() * 10_000_000) + EPOCH_DIFF
    return ft


def set_creation_time(path, dt):
    """Set file/directory creation time on Windows using SetFileTime."""
    if sys.platform != "win32":
        return False

    kernel32 = ctypes.windll.kernel32

    ft_int = _datetime_to_filetime(dt)

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                     ("dwHighDateTime", ctypes.c_uint32)]

    filetime = FILETIME(ft_int & 0xFFFFFFFF, ft_int >> 32)

    # Need Windows-native path (backslashes)
    win_path = str(Path(path).resolve())

    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000  # required for directories

    handle = kernel32.CreateFileW(
        win_path,
        GENERIC_WRITE,
        0,       # no sharing
        None,    # default security
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )

    INVALID_HANDLE = ctypes.c_void_p(-1).value
    if handle == INVALID_HANDLE or handle == -1:
        return False

    try:
        # SetFileTime(handle, lpCreationTime, lpLastAccessTime, lpLastWriteTime)
        # Only set creation time, leave access and write times as None
        result = kernel32.SetFileTime(
            handle,
            ctypes.byref(filetime),  # creation time
            None,                     # access time (unchanged)
            None,                     # write time (unchanged)
        )
        return bool(result)
    finally:
        kernel32.CloseHandle(handle)


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
                # Seek near end -- overshoot slightly to avoid splitting a line
                f.seek(file_size - TAIL_READ_SIZE)
                # Discard partial first line
                f.readline()
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

def apply_timestamps(path, first_ts, last_ts, dry_run, verbose):
    """Apply creation time and mtime to a file or directory."""
    changes = []
    path = Path(path)
    current_mtime = datetime.fromtimestamp(path.stat().st_mtime)

    # Set mtime via os.utime
    if last_ts and abs((current_mtime - last_ts).total_seconds()) > 1:
        if not dry_run:
            ts_epoch = last_ts.timestamp()
            os.utime(path, (ts_epoch, ts_epoch))
        changes.append(("mtime", current_mtime, last_ts))

    # Set creation time via Win32 API
    if first_ts:
        try:
            birth = datetime.fromtimestamp(path.stat().st_ctime)
            if abs((birth - first_ts).total_seconds()) > 1:
                if not dry_run:
                    set_creation_time(path, first_ts)
                changes.append(("ctime", birth, first_ts))
        except (OSError, AttributeError):
            pass

    return changes


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_directory(dirpath, dry_run, verbose):
    """Process a single session directory. Returns (success, changes_count)."""
    source = find_source_file(dirpath)
    if not source:
        if verbose:
            print(f"  SKIP {dirpath.name}/ -- no parseable log files")
        return False, 0

    first_ts = extract_first_timestamp(source)
    last_ts = extract_last_timestamp(source)

    if not first_ts and not last_ts:
        if verbose:
            print(f"  SKIP {dirpath.name}/ -- no timestamps found in {source.name}")
        return False, 0

    changes = 0
    label = "[DRY RUN] " if dry_run else ""

    # Apply to all log files in this directory
    all_files = find_all_log_files(dirpath)
    for f in all_files:
        file_changes = apply_timestamps(f, first_ts, last_ts, dry_run, verbose)
        if file_changes and verbose:
            for kind, old, new in file_changes:
                print(f"  {label}{kind}: {f.name}")
                print(f"         {old.strftime('%Y-%m-%d %H:%M:%S')} -> {new.strftime('%Y-%m-%d %H:%M:%S')}")
        changes += len(file_changes)

    # Apply to directory itself
    dir_changes = apply_timestamps(dirpath, first_ts, last_ts, dry_run, verbose)
    if dir_changes and verbose:
        for kind, old, new in dir_changes:
            print(f"  {label}{kind}: {dirpath.name}/")
            print(f"         {old.strftime('%Y-%m-%d %H:%M:%S')} -> {new.strftime('%Y-%m-%d %H:%M:%S')}")
    changes += len(dir_changes)

    return True, changes


def process_root_files(sesslogs_path, dry_run, verbose):
    """Process legacy sesslog files at the root of sesslogs/."""
    root_files = find_root_level_files(sesslogs_path)
    changes = 0
    label = "[DRY RUN] " if dry_run else ""

    for f in root_files:
        first_ts = extract_first_timestamp(f)
        last_ts = extract_last_timestamp(f)
        if not first_ts and not last_ts:
            if verbose:
                print(f"  SKIP root file {f.name} -- no timestamps")
            continue

        file_changes = apply_timestamps(f, first_ts, last_ts, dry_run, verbose)
        if file_changes and verbose:
            for kind, old, new in file_changes:
                print(f"  {label}{kind}: (root) {f.name}")
                print(f"         {old.strftime('%Y-%m-%d %H:%M:%S')} -> {new.strftime('%Y-%m-%d %H:%M:%S')}")
        changes += len(file_changes)

    return len(root_files), changes


def main():
    parser = argparse.ArgumentParser(
        description="Fix timestamps on ~/.claude/sesslogs/ after git stash/switch corruption.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          Preview changes (dry-run, default)
  %(prog)s --apply                  Apply timestamp fixes
  %(prog)s --apply --verbose        Apply with per-file detail
  %(prog)s --path /other/sesslogs   Use a different sesslogs directory
        """,
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually apply changes (default is dry-run preview)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show per-file timestamp changes",
    )
    parser.add_argument(
        "--path", type=str, default=None,
        help="Path to sesslogs directory (default: ~/.claude/sesslogs)",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    # Resolve sesslogs path
    if args.path:
        sesslogs = Path(args.path)
    else:
        sesslogs = Path.home() / ".claude" / "sesslogs"

    if not sesslogs.is_dir():
        print(f"ERROR: {sesslogs} is not a directory", file=sys.stderr)
        return 1

    mode = "DRY RUN (use --apply to commit changes)" if dry_run else "APPLYING CHANGES"
    print(f"Sesslog Timestamp Fix -- {mode}")
    print(f"Target: {sesslogs}")
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
        success, changes = process_directory(dirpath, dry_run, args.verbose)
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
    print(f"  Directories processed: {processed}/{total_dirs} ({skipped} skipped -- no log files)")
    print(f"  Root-level files:      {root_count}")
    print(f"  Total timestamp fixes: {total_changes}")
    if dry_run:
        print()
        print("  This was a dry run. Use --apply to commit changes.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
