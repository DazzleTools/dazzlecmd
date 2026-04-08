"""
Time-pattern parsing for safedel trash folder matching.

Trash folders are named YYYY-MM-DD__hh-mm-ss. This module converts
user-friendly time expressions into glob patterns that match against
those folder names.

Supported patterns:
    last                        -> most recent folder
    today                       -> YYYY-MM-DD__*  (today's date)
    today 10:46                 -> YYYY-MM-DD__10-46-*
    2026-04-08                  -> 2026-04-08__*
    2026-04-08 10:46            -> 2026-04-08__10-46-*
    2026-04-08 10:4*            -> 2026-04-08__10-4*
    2026-04-0*                  -> 2026-04-0*
    2026-03-*                   -> 2026-03-*
    --age ">30d"                -> all folders older than 30 days
    --contains foo.txt          -> scan manifests for filename match
    --path "*/bar/*"            -> scan manifests for original path match
"""

import datetime
import fnmatch
import glob
import json
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple


# Folder name format: YYYY-MM-DD__hh-mm-ss  (possibly with suffix like _001)
FOLDER_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2})__(\d{2}-\d{2}-\d{2})(_\d+)?$"
)

FOLDER_DATETIME_FMT = "%Y-%m-%d__%H-%M-%S"


def parse_folder_datetime(folder_name: str) -> Optional[datetime.datetime]:
    """Parse a trash folder name into a datetime, or None if invalid."""
    m = FOLDER_PATTERN.match(folder_name)
    if not m:
        return None
    date_part = m.group(1)
    time_part = m.group(2)
    try:
        return datetime.datetime.strptime(
            f"{date_part}__{time_part}", FOLDER_DATETIME_FMT
        )
    except ValueError:
        return None


def generate_folder_name(dt: Optional[datetime.datetime] = None) -> str:
    """Generate a trash folder name from a datetime (default: now)."""
    if dt is None:
        dt = datetime.datetime.now()
    return dt.strftime(FOLDER_DATETIME_FMT)


def generate_unique_folder_name(
    trash_dir: str, dt: Optional[datetime.datetime] = None
) -> str:
    """Generate a unique trash folder name, adding a suffix on collision."""
    base = generate_folder_name(dt)
    candidate = base
    suffix = 1
    while os.path.exists(os.path.join(trash_dir, candidate)):
        candidate = f"{base}_{suffix:03d}"
        suffix += 1
    return candidate


# -- Age filter parsing --

_AGE_RE = re.compile(r"^([<>]=?)\s*(\d+)\s*([dhms])$")

_AGE_UNITS = {
    "d": "days",
    "h": "hours",
    "m": "minutes",
    "s": "seconds",
}


def parse_age_filter(age_str: str) -> Tuple[str, datetime.timedelta]:
    """Parse an age filter string like '>30d' into (operator, timedelta).

    Returns:
        (operator, timedelta) where operator is '>', '>=', '<', or '<='

    Raises:
        ValueError: if the format is not recognized
    """
    age_str = age_str.strip().strip('"').strip("'")
    m = _AGE_RE.match(age_str)
    if not m:
        raise ValueError(
            f"Invalid age filter: {age_str!r}. "
            f"Expected format like '>30d', '>=2h', '<7d'"
        )
    op = m.group(1)
    value = int(m.group(2))
    unit_key = m.group(3)
    unit = _AGE_UNITS[unit_key]
    return op, datetime.timedelta(**{unit: value})


def matches_age_filter(
    folder_dt: datetime.datetime,
    op: str,
    delta: datetime.timedelta,
    now: Optional[datetime.datetime] = None,
) -> bool:
    """Check if a folder datetime matches an age filter."""
    if now is None:
        now = datetime.datetime.now()
    age = now - folder_dt
    if op == ">":
        return age > delta
    elif op == ">=":
        return age >= delta
    elif op == "<":
        return age < delta
    elif op == "<=":
        return age <= delta
    return False


# -- Time pattern -> glob conversion --


def time_pattern_to_glob(args: List[str]) -> Optional[str]:
    """Convert time-pattern arguments to a glob pattern for folder names.

    Args:
        args: list of positional arguments from the user, e.g.:
              ["today"], ["today", "10:46"], ["2026-04-08", "10:4*"],
              ["2026-04-0*"], ["last"]

    Returns:
        A glob pattern string, or None for special tokens like "last"
        that require different handling.
    """
    if not args:
        return "*"  # Match all

    first = args[0].lower().strip()

    # Special token: "last" means most recent -- handled by caller
    if first == "last":
        return None  # Sentinel: caller handles "last" specially

    # Special token: "today" expands to today's date
    if first == "today":
        date_str = datetime.date.today().strftime("%Y-%m-%d")
        if len(args) >= 2:
            time_str = _normalize_time_arg(args[1])
            return f"{date_str}__{time_str}"
        return f"{date_str}__*"

    # Check if first arg looks like a date or date-with-wildcard
    # Could be: 2026-04-08, 2026-04-0*, 2026-03-*, etc.
    if re.match(r"^\d{4}-", first):
        date_str = first
        if len(args) >= 2:
            time_str = _normalize_time_arg(args[1])
            return f"{date_str}__{time_str}"
        # Date only -- if it's a full date, match all times that day
        # If it has wildcards, match as-is
        if "*" in date_str or "?" in date_str:
            return f"{date_str}*"
        return f"{date_str}__*"

    # If nothing matched, treat the whole thing as a raw glob
    return args[0]


def _normalize_time_arg(time_arg: str) -> str:
    """Normalize a time argument like '10:46' to folder-name format '10-46-*'.

    Handles:
        10:46       -> 10-46-*
        10:46:33    -> 10-46-33
        10:4*       -> 10-4*
        10-46       -> 10-46-*
        10-46-33    -> 10-46-33
    """
    t = time_arg.strip()

    # Replace colons with dashes (folder names use dashes)
    t = t.replace(":", "-")

    # Count dash-separated parts
    parts = t.split("-")
    if len(parts) == 1:
        # Just hour: "10" -> "10-*"
        return f"{t}-*"
    elif len(parts) == 2:
        # Hour and minute: "10-46" -> "10-46-*"
        # But if there's a wildcard, leave it: "10-4*" -> "10-4*"
        if "*" in parts[1] or "?" in parts[1]:
            return t
        return f"{t}-*"
    else:
        # Full time: "10-46-33" -> "10-46-33"
        return t


# -- Folder matching --


def match_trash_folders(
    trash_dir: str,
    pattern: Optional[str] = None,
    age_filter: Optional[str] = None,
) -> List[str]:
    """Find trash folders matching a glob pattern and/or age filter.

    Args:
        trash_dir: path to the trash directory containing timestamped folders
        pattern: glob pattern for folder names (None = match all for age filter)
        age_filter: age filter string like '>30d' (optional)

    Returns:
        List of matching folder names (just names, not full paths), sorted
        by timestamp ascending (oldest first).
    """
    if not os.path.isdir(trash_dir):
        return []

    # Get candidate folders
    if pattern is None or pattern == "*":
        candidates = os.listdir(trash_dir)
    else:
        # Use glob matching
        matched_paths = glob.glob(os.path.join(trash_dir, pattern))
        candidates = [os.path.basename(p) for p in matched_paths]

    # Filter to valid trash folders only
    results = []
    for name in candidates:
        full_path = os.path.join(trash_dir, name)
        if not os.path.isdir(full_path):
            continue
        dt = parse_folder_datetime(name)
        if dt is None:
            continue
        results.append((name, dt))

    # Apply age filter if provided
    if age_filter:
        op, delta = parse_age_filter(age_filter)
        now = datetime.datetime.now()
        results = [
            (name, dt)
            for name, dt in results
            if matches_age_filter(dt, op, delta, now)
        ]

    # Sort by timestamp ascending
    results.sort(key=lambda x: x[1])
    return [name for name, _ in results]


def get_most_recent_folder(trash_dir: str) -> Optional[str]:
    """Get the most recent trash folder name, or None if empty."""
    folders = match_trash_folders(trash_dir)
    if not folders:
        return None
    return folders[-1]  # Sorted ascending, last is most recent


# -- Manifest-based search --


def search_manifests_by_filename(
    trash_dir: str, filename_pattern: str
) -> List[str]:
    """Search trash manifests for entries matching a filename pattern.

    Args:
        trash_dir: path to the trash directory
        filename_pattern: glob pattern to match against original_name in entries

    Returns:
        List of matching folder names, sorted by timestamp ascending.
    """
    results = []
    folders = match_trash_folders(trash_dir)

    for folder_name in folders:
        manifest_path = os.path.join(trash_dir, folder_name, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            entries = manifest.get("entries", [])
            for entry in entries:
                original_name = entry.get("original_name", "")
                if fnmatch.fnmatch(original_name, filename_pattern):
                    results.append(folder_name)
                    break
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    return results


def search_manifests_by_path(
    trash_dir: str, path_pattern: str
) -> List[str]:
    """Search trash manifests for entries matching an original path pattern.

    Args:
        trash_dir: path to the trash directory
        path_pattern: glob pattern to match against original_path in entries

    Returns:
        List of matching folder names, sorted by timestamp ascending.
    """
    results = []
    folders = match_trash_folders(trash_dir)

    for folder_name in folders:
        manifest_path = os.path.join(trash_dir, folder_name, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            entries = manifest.get("entries", [])
            for entry in entries:
                original_path = entry.get("original_path", "")
                # Try both forward and backslash variants
                if fnmatch.fnmatch(original_path, path_pattern):
                    results.append(folder_name)
                    break
                # Normalize to forward slashes for matching
                normalized = original_path.replace("\\", "/")
                if fnmatch.fnmatch(normalized, path_pattern):
                    results.append(folder_name)
                    break
        except (json.JSONDecodeError, OSError, KeyError):
            continue

    return results


def resolve_time_args(
    trash_dir: str,
    positional_args: List[str],
    contains: Optional[str] = None,
    path_pattern: Optional[str] = None,
    age_filter: Optional[str] = None,
) -> List[str]:
    """High-level resolver: combine all matching strategies.

    This is the main entry point for subcommands. It takes the user's
    arguments and returns matching trash folder names.

    Args:
        trash_dir: path to the trash directory
        positional_args: positional time-pattern arguments (e.g., ["today", "10:46"])
        contains: --contains filename pattern (optional)
        path_pattern: --path original-path pattern (optional)
        age_filter: --age filter string (optional)

    Returns:
        List of matching folder names, sorted by timestamp ascending.
    """
    # --contains search (ignores positional args)
    if contains:
        return search_manifests_by_filename(trash_dir, contains)

    # --path search (ignores positional args)
    if path_pattern:
        return search_manifests_by_path(trash_dir, path_pattern)

    # Time-pattern based matching
    glob_pattern = time_pattern_to_glob(positional_args)

    # "last" special case
    if glob_pattern is None:
        latest = get_most_recent_folder(trash_dir)
        return [latest] if latest else []

    return match_trash_folders(trash_dir, glob_pattern, age_filter)
