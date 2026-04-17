"""Platform detection -- shared library for setup and runtime layers.

Provides PlatformInfo (frozen dataclass) and get_platform_info() that detects
the host OS, subtype (Linux distribution or Windows major version), architecture,
and WSL status. Used by both the runtime conditional dispatch resolver and the
multi-platform setup resolver.

Optional dependency: `distro` package gives richer Linux subtype detection.
Without it the module parses /etc/os-release directly. If neither works,
subtype is None and the module still functions.

Canonical OS names (PlatformInfo.os):
    "linux" | "windows" | "macos" | "bsd" | "other"

Subtype examples:
    linux:   "debian", "ubuntu", "rhel", "centos", "arch", "nixos"
    windows: "win10", "win11"
    macos:   "macos13", "macos14", "macos15"
    bsd:     "freebsd", "openbsd", "netbsd", "dragonfly"

Subtypes are always lowercased. Unknown subtype is None (not the empty string).
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional, Tuple


@dataclass(frozen=True)
class PlatformInfo:
    """Immutable snapshot of the current host's platform.

    Fields:
        os: Canonical OS name.
        subtype: OS-specific variant (see module docstring). None when unknown.
        arch: Normalized architecture ("x86_64", "arm64", "i386", ...).
        is_wsl: True if running under Windows Subsystem for Linux.
        version: OS version string ("11", "22.04", "13.4"). None if unavailable.
        raw: Diagnostic dict of raw detection inputs. Excluded from equality.
    """

    os: str
    subtype: Optional[str]
    arch: str
    is_wsl: bool
    version: Optional[str]
    raw: dict = field(default_factory=dict, compare=False, hash=False)


def _detect_wsl() -> bool:
    """Return True if running under WSL."""
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with open("/proc/version", "r", encoding="utf-8", errors="replace") as f:
            content = f.read().lower()
            return "microsoft" in content or "wsl" in content
    except (OSError, IOError):
        return False


def _normalize_arch(machine: str) -> str:
    """Normalize platform.machine() output to a canonical form."""
    m = (machine or "").lower()
    if m in ("x86_64", "amd64"):
        return "x86_64"
    if m in ("aarch64", "arm64"):
        return "arm64"
    if m in ("i386", "i686", "x86"):
        return "i386"
    return m or "unknown"


def _detect_linux_subtype() -> Tuple[Optional[str], Optional[str], dict]:
    """Detect Linux distribution subtype and version."""
    raw: dict = {}
    try:
        import distro  # type: ignore

        raw["distro_id"] = distro.id()
        raw["distro_version"] = distro.version()
        raw["distro_name"] = distro.name()
        subtype = distro.id() or None
        version = distro.version() or None
        return subtype, version, raw
    except ImportError:
        pass

    # Stdlib fallback: parse /etc/os-release
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                v = v.strip('"').strip("'")
                raw[f"os_release_{k.lower()}"] = v
        subtype = raw.get("os_release_id") or None
        version = raw.get("os_release_version_id") or None
        return subtype, version, raw
    except (OSError, IOError):
        return None, None, raw


def _detect_windows_subtype() -> Tuple[Optional[str], Optional[str], dict]:
    """Detect Windows major version via build number (>= 22000 = Win11)."""
    raw: dict = {}
    release = platform.release()
    version = platform.version()
    raw["platform_release"] = release
    raw["platform_version"] = version

    try:
        parts = version.split(".")
        if len(parts) >= 3:
            build = int(parts[2])
            if build >= 22000:
                return "win11", version, raw
            if build >= 10240:
                return "win10", version, raw
    except (ValueError, IndexError):
        pass

    if release == "11":
        return "win11", version, raw
    if release == "10":
        return "win10", version, raw
    return None, version or None, raw


def _detect_macos_subtype() -> Tuple[Optional[str], Optional[str], dict]:
    """Detect macOS major version (e.g., macos13, macos14)."""
    raw: dict = {}
    try:
        release, _, _ = platform.mac_ver()
        raw["mac_ver"] = release
        if release:
            major = release.split(".")[0]
            return f"macos{major}", release, raw
    except Exception:
        pass
    return None, None, raw


def _detect_bsd_subtype(system: str) -> Tuple[Optional[str], Optional[str], dict]:
    """Detect BSD variant (FreeBSD / OpenBSD / NetBSD / DragonFly)."""
    raw: dict = {"system": system}
    s = (system or "").lower()
    if "freebsd" in s:
        return "freebsd", platform.release() or None, raw
    if "openbsd" in s:
        return "openbsd", platform.release() or None, raw
    if "netbsd" in s:
        return "netbsd", platform.release() or None, raw
    if "dragonfly" in s:
        return "dragonfly", platform.release() or None, raw
    return None, None, raw


def _detect_platform_info_uncached() -> PlatformInfo:
    """Build a PlatformInfo from the live environment. No caching."""
    system = platform.system()
    machine = platform.machine()
    is_wsl = _detect_wsl()
    arch = _normalize_arch(machine)

    raw: dict = {
        "platform_system": system,
        "platform_machine": machine,
        "platform_release": platform.release(),
        "python_version": sys.version.split()[0],
    }

    if system == "Linux":
        subtype, version, subtype_raw = _detect_linux_subtype()
        os_name = "linux"
    elif system == "Windows":
        subtype, version, subtype_raw = _detect_windows_subtype()
        os_name = "windows"
    elif system == "Darwin":
        subtype, version, subtype_raw = _detect_macos_subtype()
        os_name = "macos"
    elif any(b in system for b in ("BSD", "DragonFly")):
        subtype, version, subtype_raw = _detect_bsd_subtype(system)
        os_name = "bsd"
    else:
        subtype, version, subtype_raw = None, platform.release() or None, {}
        os_name = "other"

    raw.update(subtype_raw)

    if subtype:
        subtype = subtype.lower()

    return PlatformInfo(
        os=os_name,
        subtype=subtype,
        arch=arch,
        is_wsl=is_wsl,
        version=version,
        raw=raw,
    )


@lru_cache(maxsize=1)
def get_platform_info() -> PlatformInfo:
    """Detect the current host's platform. Cached per-process.

    Tests that need different platform values should either construct
    PlatformInfo directly or call get_platform_info.cache_clear() after
    monkeypatching the underlying platform helpers.
    """
    return _detect_platform_info_uncached()
