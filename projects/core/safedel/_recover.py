"""
Recovery, cleanup, listing, and status subcommands for safedel.

Implements:
    safedel list [time-pattern] [--json] [--age ">Nd"]
    safedel recover [time-pattern] [--to PATH] [--metadata-only] [--dry-run]
    safedel clean [time-pattern] [--force] [--yes] [--age ">Nd"] [-q] [-qq]
    safedel status
"""

import datetime
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from _store import TrashFolder, TrashStore, TrashEntry
from _timepattern import resolve_time_args, parse_folder_datetime
from _zones import (
    Zone,
    check_clean_permission,
    determine_zone,
    format_age,
    get_zone_warnings,
    load_config,
)

# Import preservelib from local _lib/
_lib_dir = str(Path(__file__).parent / "_lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from preservelib.metadata import apply_file_metadata


# -- List --


def _resolve_folders(
    store: TrashStore,
    positional_args: List[str],
    contains: Optional[str] = None,
    path_pattern: Optional[str] = None,
    age_filter: Optional[str] = None,
) -> List[TrashFolder]:
    """Resolve user arguments to matching TrashFolder objects across all stores."""
    from _timepattern import time_pattern_to_glob, get_most_recent_folder

    # --contains and --path search: scan all manifests
    if contains or path_pattern:
        all_folders = store.list_entries()
        results = []
        for folder in all_folders:
            for entry in folder.entries:
                if contains and _fnmatch(entry.original_name, contains):
                    results.append(folder)
                    break
                if path_pattern:
                    orig = entry.original_path.replace("\\", "/")
                    if _fnmatch(orig, path_pattern) or _fnmatch(entry.original_path, path_pattern):
                        results.append(folder)
                        break
        return results

    # Time-pattern based matching
    glob_pattern = time_pattern_to_glob(positional_args)

    if glob_pattern is None:
        # "last" -- get most recent across all stores
        all_folders = store.list_entries()
        return [all_folders[-1]] if all_folders else []

    return store.list_entries(pattern=glob_pattern, age_filter=age_filter)


def _fnmatch(name: str, pattern: str) -> bool:
    """Filename match helper."""
    import fnmatch
    return fnmatch.fnmatch(name, pattern)


def _path_parent_accessible(path: str) -> bool:
    """Check if a path's parent directory exists and is accessible.

    Used for WSL dual-path fallback: a path is "usable" if its parent
    dir exists so we can recover into it. The path itself may not exist
    yet (we're recovering into it).
    """
    if not path:
        return False
    try:
        parent = os.path.dirname(path) or "."
        return os.path.isdir(parent)
    except (OSError, ValueError):
        return False


def cmd_list(
    store: TrashStore,
    positional_args: List[str],
    contains: Optional[str] = None,
    path_pattern: Optional[str] = None,
    age_filter: Optional[str] = None,
    json_output: bool = False,
) -> int:
    """List trash contents matching the given pattern."""
    folders = _resolve_folders(
        store, positional_args,
        contains=contains, path_pattern=path_pattern,
        age_filter=age_filter,
    )
    folder_names = [f.folder_name for f in folders]

    if not folder_names:
        if not json_output:
            print("  No matching entries in trash.")
        else:
            print("[]")
        return 0

    config = load_config()
    now = datetime.datetime.now()

    if json_output:
        items = []
        for name in folder_names:
            folder = store.get_folder(name)
            if folder:
                items.append(_folder_to_json(folder, config, now))
        print(json.dumps(items, indent=2, default=str))
        return 0

    # Table output
    print(f"\n  Trash store: {store.store_path}")
    print(f"  {len(folder_names)} matching folder(s):\n")

    for name in folder_names:
        folder = store.get_folder(name)
        if not folder:
            continue

        age = now - folder.deleted_at
        zone = determine_zone(folder.deleted_at, config, now)
        age_str = format_age(age)

        print(f"  [{zone.label}] {name} ({age_str} ago)")
        for entry in folder.entries:
            type_str = entry.file_type
            target_str = ""
            if entry.link_target:
                target_str = f" -> {entry.link_target}"
            size_str = ""
            if entry.stat and entry.stat.get("st_size"):
                size_str = f"  ({_format_size(entry.stat['st_size'])})"
            print(f"    {entry.original_name}  {type_str}{target_str}{size_str}")
            print(f"    from: {entry.original_path}")
        print()

    return 0


# -- Recover --


def cmd_recover(
    store: TrashStore,
    positional_args: List[str],
    contains: Optional[str] = None,
    path_pattern: Optional[str] = None,
    to_path: Optional[str] = None,
    metadata_only: bool = False,
    dry_run: bool = False,
) -> int:
    """Recover files from trash."""
    folders = _resolve_folders(
        store, positional_args,
        contains=contains, path_pattern=path_pattern,
    )

    if not folders:
        print("  No matching entries to recover.", file=sys.stderr)
        return 1

    total_recovered = 0
    total_errors = 0

    for folder in folders:
        if not folder:
            continue

        for entry in folder.entries:
            result = _recover_entry(
                store, folder, entry,
                to_path=to_path,
                metadata_only=metadata_only,
                dry_run=dry_run,
            )
            if result:
                total_recovered += 1
            else:
                total_errors += 1

        # If all entries recovered and not dry-run, remove the trash folder
        if not dry_run and total_errors == 0:
            store.remove_folder(folder.folder_name)

    if dry_run:
        print(f"\n  DRY RUN: Would recover {total_recovered} item(s).")
    else:
        print(f"\n  Recovered {total_recovered} item(s).")
        if total_errors:
            print(f"  {total_errors} error(s) occurred.", file=sys.stderr)

    return 1 if total_errors > 0 else 0


def _recover_entry(
    store: TrashStore,
    folder: TrashFolder,
    entry: TrashEntry,
    to_path: Optional[str] = None,
    metadata_only: bool = False,
    dry_run: bool = False,
) -> bool:
    """Recover a single entry from trash.

    Returns True on success, False on error.
    """
    # Determine recovery target
    if to_path:
        # --to always acts as a parent directory: recover into it
        os.makedirs(to_path, exist_ok=True)
        target = os.path.join(to_path, entry.original_name)
    else:
        target = entry.original_path
        # WSL dual-path fallback: if the native original_path can't be used
        # (e.g., manifest written by WSL Python with /mnt/c/ paths, now
        # recovering from Windows Python), try the alternate form.
        if target and not _path_parent_accessible(target) and entry.original_path_alt:
            alt = entry.original_path_alt
            if _path_parent_accessible(alt):
                target = alt
                print(f"  [using alternate path form: {alt}]")

    # Metadata-only recovery
    if metadata_only:
        if dry_run:
            print(f"  Would apply metadata to: {target}")
            if entry.metadata:
                _print_metadata_summary(entry)
            return True

        if not os.path.exists(target):
            print(
                f"  ERROR: Target does not exist for metadata recovery: {target}",
                file=sys.stderr,
            )
            return False

        if entry.metadata:
            try:
                apply_file_metadata(target, entry.metadata)
                print(f"  Applied metadata to: {target}")
                return True
            except Exception as e:
                print(f"  ERROR applying metadata to {target}: {e}", file=sys.stderr)
                return False
        else:
            print(f"  No metadata stored for: {entry.original_name}", file=sys.stderr)
            return False

    # Full recovery
    content_path = None
    if entry.content_path:
        content_path = os.path.join(folder.folder_path, entry.content_path)

    if dry_run:
        print(f"  Would recover: {entry.original_name}")
        print(f"    Type: {entry.file_type}")
        print(f"    To: {target}")
        if entry.link_target:
            print(f"    Link target: {entry.link_target}")
        if content_path and os.path.exists(content_path):
            print(f"    Content: available")
        elif entry.file_type in ("symlink_file", "symlink_dir", "junction"):
            print(f"    Content: link metadata (target={entry.link_target})")
        else:
            print(f"    Content: NOT available")
        return True

    # Check for conflicts at target
    if os.path.exists(target) or os.path.islink(target):
        print(
            f"  ERROR: Target already exists: {target}\n"
            f"  Use --to to recover to a different location.",
            file=sys.stderr,
        )
        return False

    # Ensure parent directory exists
    parent = os.path.dirname(target)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    # Recover based on type
    try:
        if entry.file_type in ("symlink_file", "symlink_dir"):
            # Recreate symlink
            if entry.link_target:
                is_dir = entry.file_type == "symlink_dir"
                os.symlink(entry.link_target, target, target_is_directory=is_dir)
                print(f"  Recovered symlink: {target} -> {entry.link_target}")
            else:
                print(f"  ERROR: No link target recorded for symlink", file=sys.stderr)
                return False

        elif entry.file_type == "junction":
            # Recreate junction (Windows only)
            if sys.platform == "win32" and entry.link_target:
                _create_junction(target, entry.link_target)
                print(f"  Recovered junction: {target} -> {entry.link_target}")
            elif entry.link_target:
                print(
                    f"  WARNING: Cannot recreate junction on {sys.platform}. "
                    f"Target was: {entry.link_target}",
                    file=sys.stderr,
                )
                return False
            else:
                print(f"  ERROR: No link target recorded for junction", file=sys.stderr)
                return False

        elif content_path and os.path.exists(content_path):
            # Move content back
            if os.path.isdir(content_path):
                from dazzle_filekit.operations import copy_tree_preserving_links
                copy_tree_preserving_links(content_path, target)
                shutil.rmtree(content_path)
            else:
                shutil.copy2(content_path, target)
                os.unlink(content_path)

            # Apply preserved metadata
            if entry.metadata:
                try:
                    apply_file_metadata(target, entry.metadata)
                except Exception:
                    pass  # Best effort

            print(f"  Recovered: {target}")

        else:
            print(
                f"  ERROR: No content available to recover for: {entry.original_name}",
                file=sys.stderr,
            )
            return False

        return True

    except OSError as e:
        print(f"  ERROR recovering {entry.original_name}: {e}", file=sys.stderr)
        return False


# -- Clean --


def cmd_clean(
    store: TrashStore,
    positional_args: List[str],
    age_filter: Optional[str] = None,
    force: bool = False,
    yes: bool = False,
    verbosity: int = 0,
) -> int:
    """Permanently delete trash entries with zone-based protection."""
    folders = _resolve_folders(
        store, positional_args,
        age_filter=age_filter,
    )

    if not folders:
        print("  No matching entries to clean.")
        return 0

    config = load_config()
    now = datetime.datetime.now()
    is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()

    cleaned = 0
    skipped = 0

    for folder in folders:
        name = folder.folder_name

        zone = determine_zone(folder.deleted_at, config, now)

        # Check permission
        allowed, reason = check_clean_permission(
            zone, force=force, yes=yes, is_tty=is_tty
        )
        if not allowed:
            print(f"\n  {name}: {reason}")
            skipped += 1
            continue

        # Build entry metadata for warnings
        entry_meta = {}
        if folder.entries:
            e = folder.entries[0]
            entry_meta = {
                "original_path": e.original_path,
                "file_type": e.file_type,
                "link_target": e.link_target,
                "link_count": e.link_count,
                "stat": e.stat or {},
                "age_description": format_age(now - folder.deleted_at) + " ago",
            }

        # Show warnings
        zone_warnings = get_zone_warnings(zone, entry_meta, verbosity)
        if zone_warnings:
            print()
            for w in zone_warnings:
                print(f"  {w}")

        # Show what will be deleted
        print(f"\n  Permanently delete: {name}")
        for entry in folder.entries:
            print(f"    {entry.original_name} ({entry.file_type})")
            print(f"    was at: {entry.original_path}")

        # Interactive confirmation (zones B, C, D without --yes)
        if zone.requires_interactive:
            if zone.allows_yes_override and yes:
                pass  # Zone D with --yes: skip prompt
            else:
                try:
                    answer = input("\n  Permanently delete? [y/N]: ").strip().lower()
                    if answer != "y":
                        print("  Skipped.")
                        skipped += 1
                        continue
                except (EOFError, KeyboardInterrupt):
                    print("\n  Aborted.")
                    skipped += 1
                    continue

        # Do the permanent delete
        if store.remove_folder(name):
            print(f"  Deleted: {name}")
            cleaned += 1
        else:
            print(f"  ERROR: Failed to delete {name}", file=sys.stderr)

    print(f"\n  Cleaned: {cleaned}, Skipped: {skipped}")
    return 0


# -- Status --


def cmd_status(store: TrashStore) -> int:
    """Show trash store statistics."""
    stats = store.get_stats()

    print(f"\n  Trash store: {stats.store_path}")
    print(f"  Folders: {stats.total_folders}")
    print(f"  Entries: {stats.total_entries}")
    print(f"  Total size: {_format_size(stats.total_size_bytes)}")

    if stats.oldest:
        oldest_dt = parse_folder_datetime(stats.oldest)
        if oldest_dt:
            age = format_age(datetime.datetime.now() - oldest_dt)
            print(f"  Oldest: {stats.oldest} ({age} ago)")

    if stats.newest:
        newest_dt = parse_folder_datetime(stats.newest)
        if newest_dt:
            age = format_age(datetime.datetime.now() - newest_dt)
            print(f"  Newest: {stats.newest} ({age} ago)")

    # Zone breakdown
    if stats.total_folders > 0:
        config = load_config()
        now = datetime.datetime.now()
        zone_counts = {z: 0 for z in Zone}

        all_folders = store.list_entries()
        for folder in all_folders:
            zone = determine_zone(folder.deleted_at, config, now)
            zone_counts[zone] += 1

        print(f"\n  Zone breakdown:")
        for zone in Zone:
            count = zone_counts[zone]
            if count > 0:
                print(f"    {zone.label}: {count}")

    print()
    return 0


# -- Helpers --


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _folder_to_json(
    folder: TrashFolder, config: dict, now: datetime.datetime
) -> Dict[str, Any]:
    """Convert a TrashFolder to a JSON-serializable dict."""
    zone = determine_zone(folder.deleted_at, config, now)
    return {
        "folder_name": folder.folder_name,
        "deleted_at": folder.deleted_at.isoformat(),
        "age": format_age(now - folder.deleted_at),
        "zone": zone.name,
        "entries": [
            {
                "original_path": e.original_path,
                "original_name": e.original_name,
                "file_type": e.file_type,
                "link_target": e.link_target,
                "size": e.stat.get("st_size") if e.stat else None,
            }
            for e in folder.entries
        ],
    }


def _print_metadata_summary(entry: TrashEntry) -> None:
    """Print a summary of preserved metadata."""
    meta = entry.metadata or {}
    if "timestamps" in meta:
        ts = meta["timestamps"]
        print(f"    Timestamps:")
        print(f"      Modified: {ts.get('modified_iso', 'N/A')}")
        print(f"      Accessed: {ts.get('accessed_iso', 'N/A')}")
        print(f"      Created:  {ts.get('created_iso', 'N/A')}")
    if "mode" in meta:
        print(f"    Permissions: {oct(meta['mode'])}")


def _create_junction(link_path: str, target_path: str) -> None:
    """Create a Windows junction point using PowerShell."""
    import subprocess
    result = subprocess.run(
        [
            "powershell", "-Command",
            f"New-Item -ItemType Junction -Path '{link_path}' -Target '{target_path}'"
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise OSError(
            f"Failed to create junction: {result.stderr.strip()}"
        )
