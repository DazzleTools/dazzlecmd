"""
Tiered protection zones for safedel trash cleanup.

Controls how much friction is required to permanently delete trash entries
based on their age. Designed to prevent LLMs from aggressively cleaning up
after destructive delete operations.

Zone tiers (configurable in ~/.safedel/config.json):

    Zone A (Blocked):           Outright refusal. No flags override.
                                Disabled by default.
    Zone B (Maximum Friction):  Requires --force AND interactive Y/N.
                                --yes is rejected. Full warnings emitted.
                                Default: items < 48 hours old.
    Zone C (Standard):          Interactive Y/N with warnings.
                                No --force needed. --yes rejected.
                                Default: items 48h - 30 days old.
    Zone D (Relaxed):           Interactive by default.
                                --yes accepted for automation.
                                Default: items > 30 days old.
"""

import datetime
import json
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class Zone(Enum):
    """Protection zone for a trash entry."""
    A = "blocked"
    B = "max_friction"
    C = "standard"
    D = "relaxed"

    @property
    def requires_force(self) -> bool:
        return self == Zone.B

    @property
    def requires_interactive(self) -> bool:
        return self in (Zone.B, Zone.C, Zone.D)

    @property
    def allows_yes_override(self) -> bool:
        return self == Zone.D

    @property
    def is_blocked(self) -> bool:
        return self == Zone.A

    @property
    def label(self) -> str:
        labels = {
            Zone.A: "BLOCKED",
            Zone.B: "PROTECTED (< 48h)",
            Zone.C: "STANDARD (< 30d)",
            Zone.D: "RELAXED (> 30d)",
        }
        return labels.get(self, self.value)


# -- Default configuration --

DEFAULT_CONFIG = {
    "protection": {
        "zone_a_enabled": False,
        "zone_a_hours": 6,
        "zone_b_hours": 48,
        "zone_c_days": 30,
    }
}


def get_config_path() -> str:
    """Get the path to the safedel config file."""
    return os.path.join(os.path.expanduser("~"), ".safedel", "config.json")


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load safedel configuration, falling back to defaults.

    Args:
        config_path: explicit path to config file, or None for default

    Returns:
        Merged configuration dict (user config overrides defaults)
    """
    if config_path is None:
        config_path = get_config_path()

    config = _deep_copy_dict(DEFAULT_CONFIG)

    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            _deep_merge(config, user_config)
        except (json.JSONDecodeError, OSError):
            pass  # Silently fall back to defaults on parse error

    return config


def save_default_config(config_path: Optional[str] = None) -> str:
    """Write the default config file if it doesn't exist.

    Returns:
        The path to the config file.
    """
    if config_path is None:
        config_path = get_config_path()

    if os.path.exists(config_path):
        return config_path

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=4)
        f.write("\n")
    return config_path


def determine_zone(
    deleted_at: datetime.datetime,
    config: Optional[Dict[str, Any]] = None,
    now: Optional[datetime.datetime] = None,
) -> Zone:
    """Determine the protection zone for a trash entry based on its age.

    Args:
        deleted_at: when the item was trashed
        config: loaded config dict (uses defaults if None)
        now: current time (defaults to datetime.now())

    Returns:
        The Zone enum value for this entry.
    """
    if config is None:
        config = load_config()
    if now is None:
        now = datetime.datetime.now()

    prot = config.get("protection", DEFAULT_CONFIG["protection"])
    age = now - deleted_at

    # Zone A: blocked (if enabled)
    if prot.get("zone_a_enabled", False):
        zone_a_hours = prot.get("zone_a_hours", 6)
        if age < datetime.timedelta(hours=zone_a_hours):
            return Zone.A

    # Zone B: maximum friction
    zone_b_hours = prot.get("zone_b_hours", 48)
    if age < datetime.timedelta(hours=zone_b_hours):
        return Zone.B

    # Zone C: standard protection
    zone_c_days = prot.get("zone_c_days", 30)
    if age < datetime.timedelta(days=zone_c_days):
        return Zone.C

    # Zone D: relaxed
    return Zone.D


def get_zone_warnings(
    zone: Zone,
    entry_metadata: Optional[Dict[str, Any]] = None,
    verbosity: int = 0,
) -> List[str]:
    """Generate teaching-signal warnings for a given zone.

    These warnings serve as reminders to check before permanently deleting,
    especially useful as feedback to LLMs operating in shell environments.

    Args:
        zone: the protection zone
        entry_metadata: manifest entry data (original_path, file_type, etc.)
        verbosity: 0 = full warnings, 1 = shortened (-q), 2 = none (-qq)

    Returns:
        List of warning strings to display.
    """
    if verbosity >= 2:
        return []  # -qq suppresses all educational warnings

    warnings = []
    meta = entry_metadata or {}

    if zone == Zone.A:
        warnings.append(
            "BLOCKED: This item cannot be permanently deleted yet. "
            "Zone A protection is active."
        )
        return warnings

    # Age-based context
    if zone == Zone.B:
        warnings.append(
            "WARNING: This item was deleted less than 48 hours ago."
        )
        if verbosity == 0:
            warnings.append(
                "Zone B protection requires --force and interactive confirmation."
            )

    elif zone == Zone.C:
        age_desc = meta.get("age_description", "less than 30 days ago")
        warnings.append(f"This item was deleted {age_desc}.")

    # Original path check
    original_path = meta.get("original_path", "")
    if original_path and verbosity == 0:
        warnings.append(
            f"Original location: {original_path}"
        )
        warnings.append(
            "Have you verified this path is safe to permanently lose?"
        )

    # Link-type specific warnings
    file_type = meta.get("file_type", "")
    link_target = meta.get("link_target", "")

    if file_type in ("symlink", "junction") and link_target:
        warnings.append(
            f"File type was: {file_type} -> {link_target}"
        )
        if verbosity == 0:
            warnings.append(
                "Have you checked that the link target still exists independently?"
            )

    elif file_type == "hardlink":
        link_count = meta.get("link_count", 0)
        if link_count and verbosity == 0:
            warnings.append(
                f"This was a hardlink with {link_count} total links at deletion time."
            )

    # Metadata preservation reminder
    if verbosity == 0:
        stat_info = meta.get("stat", {})
        if stat_info:
            warnings.append(
                "Metadata preserved (timestamps, permissions). "
                "Do you need to recover any metadata before permanent deletion?"
            )

    return warnings


def check_clean_permission(
    zone: Zone,
    force: bool = False,
    yes: bool = False,
    is_tty: Optional[bool] = None,
) -> Tuple[bool, Optional[str]]:
    """Check if a clean operation is permitted for a given zone.

    Args:
        zone: the protection zone
        force: whether --force was passed
        yes: whether --yes was passed
        is_tty: whether stdin is a TTY (None = auto-detect)

    Returns:
        (allowed, reason) -- allowed is True if the operation can proceed,
        reason is an error message if not allowed.
    """
    if is_tty is None:
        is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()

    if zone.is_blocked:
        return False, (
            "Zone A: This item is blocked from permanent deletion. "
            "It is too recent to delete. Wait for the protection period "
            "to expire, or adjust zone_a_hours in config."
        )

    if zone.requires_force and not force:
        return False, (
            f"Zone B: This item requires --force to permanently delete. "
            f"It was deleted less than the configured protection period."
        )

    if zone.requires_interactive and not zone.allows_yes_override:
        # Zones B and C: --yes is not accepted
        if yes and not is_tty:
            # LLM in non-TTY with --yes: zone B/C won't accept it
            return False, (
                f"Zone {zone.name}: --yes is not accepted for items in this "
                f"protection zone. Interactive confirmation is required."
            )

    if zone.requires_interactive and not is_tty and not yes:
        return False, (
            f"Zone {zone.name}: Interactive confirmation required but "
            f"stdin is not a TTY. For Zone D items, use --yes."
        )

    return True, None


def format_age(delta: datetime.timedelta) -> str:
    """Format a timedelta as a human-readable age string."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        return f"{total_seconds // 60}m"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours}h"
    else:
        days = total_seconds // 86400
        if days < 365:
            return f"{days}d"
        years = days // 365
        remaining_days = days % 365
        return f"{years}y {remaining_days}d"


# -- Helpers --


def _deep_copy_dict(d: dict) -> dict:
    """Simple deep copy for nested dicts (no external deps)."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _deep_copy_dict(v)
        elif isinstance(v, list):
            result[k] = list(v)
        else:
            result[k] = v
    return result


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base, modifying base in place."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
