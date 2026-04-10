"""
Volume detection and per-volume trash directory management for safedel.

Per-volume trash enables zero-copy os.rename() staging, which preserves
ALL metadata (creation time, ACLs, ADS, xattrs). When the trash store
is on the same volume as the source, rename is atomic and lossless.

Volume registry at ~/.safedel/volumes.json tracks known volume stores
with stable identifiers (serial number on Windows, filesystem UUID on
Linux/macOS) so ejected volumes can be detected as orphaned.

Trash location per volume:
    Windows local:  <drive>:\\Users\\<username>\\.safedel-trash\\
    Windows net:    Not supported (fallback to central store)
    Linux/macOS:    <mountpoint>/.safedel-trash-<uid>/
    Fallback:       Central store (~/.safedel/trash/ or %LOCALAPPDATA%)

Uses dazzle-filekit for disk utilities and unctools for drive type detection.
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Drive detection via dazzlelib packages
from dazzle_filekit.utils.disk import get_disk_usage

if sys.platform == "win32":
    from unctools.detector import get_drive_type, is_network_drive, is_unc_path
    # Drive type constants from unctools
    PATH_TYPE_NETWORK = "network"
    PATH_TYPE_REMOVABLE = "removable"
    PATH_TYPE_FIXED = "fixed"
else:
    # Stubs for non-Windows -- these features are Windows-specific
    def get_drive_type(path):
        return "fixed"
    def is_network_drive(path):
        return False
    def is_unc_path(path):
        return False
    PATH_TYPE_NETWORK = "network"
    PATH_TYPE_REMOVABLE = "removable"
    PATH_TYPE_FIXED = "fixed"


@dataclass
class VolumeInfo:
    """Information about a filesystem volume."""
    device_id: int              # os.stat().st_dev
    mount_point: str            # Drive root or mount point
    volume_serial: Optional[str] = None  # Stable ID (Windows serial, Linux UUID)
    volume_name: Optional[str] = None    # Human-readable label
    filesystem: Optional[str] = None     # NTFS, ext4, APFS, etc.
    drive_type: str = "fixed"   # fixed, network, removable, etc.
    is_network: bool = False
    is_subst: bool = False
    is_removable: bool = False
    is_readonly: bool = False


@dataclass
class VolumeTrashInfo:
    """Registry entry for a per-volume trash store."""
    volume_serial: str
    volume_name: Optional[str]
    mount_point: str
    trash_path: str
    last_seen: str              # ISO timestamp
    entry_count: int = 0
    is_reachable: bool = True


# -- Volume Detection --


def get_volume_info(path: str) -> VolumeInfo:
    """Get volume information for the filesystem containing path."""
    st = os.stat(path)
    device_id = st.st_dev

    if sys.platform == "win32":
        return _get_volume_info_windows(path, device_id)
    else:
        return _get_volume_info_unix(path, device_id)


def _get_volume_info_windows(path: str, device_id: int) -> VolumeInfo:
    """Get volume info on Windows using unctools + ctypes for serial."""
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive:
        return VolumeInfo(device_id=device_id, mount_point=path)

    root = drive + os.sep
    info = VolumeInfo(device_id=device_id, mount_point=root)

    # Use unctools for drive type detection
    dtype = get_drive_type(root)
    info.drive_type = dtype
    info.is_network = (dtype == PATH_TYPE_NETWORK)
    info.is_removable = (dtype == PATH_TYPE_REMOVABLE)
    info.is_readonly = not os.access(root, os.W_OK)

    # Detect subst drives via QueryDosDeviceW
    info.is_subst = _is_subst_drive_windows(drive)

    # Get volume serial and name via GetVolumeInformationW
    try:
        serial, name, fs = _get_volume_serial_windows(root)
        info.volume_serial = f"{serial:#010x}" if serial else None
        info.volume_name = name
        info.filesystem = fs
    except OSError:
        pass

    return info


def _is_subst_drive_windows(drive_letter: str) -> bool:
    """Check if a drive letter is a SUBST'd path."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        drive = drive_letter.rstrip(":\\/")
        buf = ctypes.create_unicode_buffer(1024)
        result = kernel32.QueryDosDeviceW(drive + ":", buf, 1024)
        if result > 0:
            # SUBST drives have a device path starting with \??\
            return buf.value.startswith("\\??\\")
        return False
    except (AttributeError, OSError):
        return False


def _get_volume_serial_windows(root: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """Get volume serial number, name, and filesystem type on Windows."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    vol_name = ctypes.create_unicode_buffer(256)
    vol_serial = wintypes.DWORD()
    max_len = wintypes.DWORD()
    flags = wintypes.DWORD()
    fs_name = ctypes.create_unicode_buffer(256)

    ok = kernel32.GetVolumeInformationW(
        root, vol_name, 256,
        ctypes.byref(vol_serial), ctypes.byref(max_len),
        ctypes.byref(flags), fs_name, 256
    )
    if ok:
        return vol_serial.value, vol_name.value or None, fs_name.value or None
    return None, None, None


def _get_volume_info_unix(path: str, device_id: int) -> VolumeInfo:
    """Get volume info on Linux/macOS."""
    mount_point = _find_mount_point(path)

    info = VolumeInfo(device_id=device_id, mount_point=mount_point)
    info.is_readonly = not os.access(mount_point, os.W_OK)

    # Detect network mounts
    info.is_network = _is_network_mount_unix(mount_point)
    info.drive_type = PATH_TYPE_NETWORK if info.is_network else PATH_TYPE_FIXED

    # Try to get filesystem UUID on Linux
    if sys.platform == "linux":
        info.volume_serial = _get_fs_uuid_linux(mount_point)

    return info


def _find_mount_point(path: str) -> str:
    """Find the mount point for a given path."""
    path = os.path.abspath(path)
    while not os.path.ismount(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def _get_fs_uuid_linux(mount_point: str) -> Optional[str]:
    """Get filesystem UUID on Linux via /dev/disk/by-uuid/."""
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == mount_point:
                    device = parts[0]
                    break
            else:
                return None

        uuid_dir = "/dev/disk/by-uuid"
        if os.path.isdir(uuid_dir):
            for uuid_name in os.listdir(uuid_dir):
                link_target = os.path.realpath(os.path.join(uuid_dir, uuid_name))
                if link_target == os.path.realpath(device):
                    return uuid_name
    except (OSError, ValueError):
        pass
    return None


def _is_network_mount_unix(mount_point: str) -> bool:
    """Check if a mount point is a network filesystem."""
    network_fs = {"nfs", "nfs4", "cifs", "smbfs", "afp", "fuse.sshfs"}
    try:
        if os.path.isfile("/proc/mounts"):
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == mount_point:
                        return parts[2] in network_fs
    except OSError:
        pass
    return False


# -- Per-Volume Trash Path Resolution --


def get_per_volume_trash_path(
    volume: VolumeInfo, username: Optional[str] = None
) -> Optional[str]:
    """Determine the per-volume trash path for a given volume.

    Returns None if per-volume trash is not appropriate (network drives,
    read-only volumes, subst drives).
    """
    if volume.is_network or volume.is_readonly or volume.is_subst:
        return None

    if sys.platform == "win32":
        return _per_volume_path_windows(volume, username)
    else:
        return _per_volume_path_unix(volume)


def _per_volume_path_windows(
    volume: VolumeInfo, username: Optional[str] = None
) -> Optional[str]:
    """Per-volume trash: <drive>\\Users\\<username>\\.safedel-trash\\"""
    if not username:
        username = os.environ.get("USERNAME", "")
        if not username:
            try:
                username = os.getlogin()
            except OSError:
                return None

    drive = volume.mount_point.rstrip(os.sep)
    user_dir = os.path.join(drive, os.sep, "Users", username)

    if os.path.isdir(user_dir):
        return os.path.join(user_dir, ".safedel-trash")

    # Fallback: try root of drive
    root_path = os.path.join(drive, os.sep, ".safedel-trash")
    try:
        os.makedirs(root_path, exist_ok=True)
        return root_path
    except PermissionError:
        return None


def _per_volume_path_unix(volume: VolumeInfo) -> Optional[str]:
    """Per-volume trash: <mountpoint>/.safedel-trash-<uid>/"""
    uid = os.getuid()
    trash_dir = os.path.join(volume.mount_point, f".safedel-trash-{uid}")

    try:
        if not os.path.exists(trash_dir):
            os.makedirs(trash_dir, mode=0o700)
        return trash_dir
    except PermissionError:
        return None


def is_same_volume(path1: str, path2: str) -> bool:
    """Check if two paths are on the same volume."""
    try:
        return os.stat(path1).st_dev == os.stat(path2).st_dev
    except OSError:
        return False


# -- Volume Registry --


def get_registry_path() -> str:
    """Path to the volume registry file."""
    return os.path.join(os.path.expanduser("~"), ".safedel", "volumes.json")


def load_registry(registry_path: Optional[str] = None) -> Dict[str, VolumeTrashInfo]:
    """Load the volume registry. Returns dict mapping volume_serial to info."""
    if registry_path is None:
        registry_path = get_registry_path()

    if not os.path.isfile(registry_path):
        return {}

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            serial: VolumeTrashInfo(
                volume_serial=serial,
                volume_name=entry.get("volume_name"),
                mount_point=entry.get("mount_point", ""),
                trash_path=entry.get("trash_path", ""),
                last_seen=entry.get("last_seen", ""),
                entry_count=entry.get("entry_count", 0),
                is_reachable=entry.get("is_reachable", True),
            )
            for serial, entry in data.items()
        }
    except (json.JSONDecodeError, OSError):
        return {}


def save_registry(
    registry: Dict[str, VolumeTrashInfo],
    registry_path: Optional[str] = None,
) -> None:
    """Save the volume registry atomically."""
    if registry_path is None:
        registry_path = get_registry_path()

    os.makedirs(os.path.dirname(registry_path), exist_ok=True)

    data = {
        serial: {
            "volume_name": info.volume_name,
            "mount_point": info.mount_point,
            "trash_path": info.trash_path,
            "last_seen": info.last_seen,
            "entry_count": info.entry_count,
            "is_reachable": info.is_reachable,
        }
        for serial, info in registry.items()
    }

    tmp_path = registry_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, registry_path)


def register_volume(
    volume: VolumeInfo, trash_path: str,
    registry_path: Optional[str] = None,
) -> None:
    """Register a per-volume trash store in the registry."""
    if not volume.volume_serial:
        return

    registry = load_registry(registry_path)
    registry[volume.volume_serial] = VolumeTrashInfo(
        volume_serial=volume.volume_serial,
        volume_name=volume.volume_name,
        mount_point=volume.mount_point,
        trash_path=trash_path,
        last_seen=_now_iso(),
        is_reachable=True,
    )
    save_registry(registry, registry_path)


def update_registry_reachability(
    registry_path: Optional[str] = None,
) -> Dict[str, VolumeTrashInfo]:
    """Scan all registered volumes and update reachability."""
    registry = load_registry(registry_path)

    for info in registry.values():
        info.is_reachable = os.path.isdir(info.trash_path)
        if info.is_reachable:
            info.last_seen = _now_iso()
            try:
                entries = [
                    d for d in os.listdir(info.trash_path)
                    if os.path.isdir(os.path.join(info.trash_path, d))
                ]
                info.entry_count = len(entries)
            except OSError:
                info.entry_count = 0

    save_registry(registry, registry_path)
    return registry


def get_all_trash_paths(
    central_path: str,
    registry_path: Optional[str] = None,
) -> List[str]:
    """Get all known trash store paths (central + per-volume) that exist."""
    paths = [central_path] if os.path.isdir(central_path) else []

    registry = load_registry(registry_path)
    for info in registry.values():
        if info.is_reachable and os.path.isdir(info.trash_path):
            if info.trash_path not in paths:
                paths.append(info.trash_path)

    return paths


# -- Resolve Trash Store for a Path --


def resolve_trash_store(
    source_path: str, central_path: str
) -> Tuple[str, bool]:
    """Determine which trash store to use for a given source path.

    Tries per-volume trash first (for zero-copy rename). Falls back to
    central store if per-volume is not available.

    Returns:
        (trash_path, is_per_volume) tuple.
    """
    try:
        volume = get_volume_info(source_path)
    except OSError:
        return central_path, False

    per_volume_path = get_per_volume_trash_path(volume)
    if per_volume_path:
        try:
            os.makedirs(per_volume_path, exist_ok=True)
            if is_same_volume(source_path, per_volume_path):
                register_volume(volume, per_volume_path)
                return per_volume_path, True
        except OSError:
            pass

    return central_path, False


def _now_iso() -> str:
    """Current time as ISO string."""
    import datetime
    return datetime.datetime.now().isoformat()
