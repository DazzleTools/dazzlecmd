"""
Trash store management for safedel.

Manages the timestamped trash folder structure and manifest creation.
Each delete operation creates a folder named YYYY-MM-DD__hh-mm-ss
containing a manifest.json and a content/ directory.

Uses preservelib.PreserveManifest for the manifest format and
preservelib.metadata for metadata collection.
"""

import datetime
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from _classifier import Classification, FileType, classify, format_classification
from _platform import (
    PlatformInfo,
    StagingResult,
    DeleteResult,
    detect_platform,
    get_trash_dir,
    stage_to_trash,
    safe_delete,
    check_disk_space,
    calculate_size,
    is_same_device,
    detect_alternate_streams,
)
from _timepattern import (
    generate_unique_folder_name,
    parse_folder_datetime,
    match_trash_folders,
)
from _volumes import resolve_trash_store, get_all_trash_paths

# Import preservelib from local _lib/
_lib_dir = str(Path(__file__).parent / "_lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from preservelib.metadata import collect_file_metadata, metadata_to_json


def _compute_alt_path(path: str) -> Optional[str]:
    """Compute the alternate-platform form of a path for cross-runtime recovery.

    On Windows: C:\\Users\\foo -> /mnt/c/Users/foo (WSL form)
    On Linux/WSL: /mnt/c/Users/foo -> C:\\Users\\foo (Windows form)

    Uses filekit's normalize_cross_platform_path which handles the conversion.
    Returns None if no sensible alternate form exists (e.g., a Linux path on
    Linux with no Windows equivalent, or a VolFs path inside WSL2).
    """
    try:
        from dazzle_filekit.utils.compat import is_windows
        import re

        if is_windows():
            # Native form is C:\..., compute WSL form /mnt/c/...
            m = re.match(r"^([a-zA-Z]):[\\/](.*)$", path)
            if m:
                drive = m.group(1).lower()
                rest = m.group(2).replace("\\", "/")
                return f"/mnt/{drive}/{rest}"
        else:
            # Native form might be /mnt/c/... or /c/..., compute Windows form
            m = re.match(r"^/mnt/([a-zA-Z])(/.*)?$", path)
            if m:
                drive = m.group(1).upper()
                rest = (m.group(2) or "").replace("/", "\\")
                return f"{drive}:{rest}"
            m = re.match(r"^/([a-zA-Z])(/.*)?$", path)
            if m and len(m.group(1)) == 1:
                drive = m.group(1).upper()
                rest = (m.group(2) or "").replace("/", "\\")
                return f"{drive}:{rest}"
    except Exception:
        pass
    return None


@dataclass
class TrashEntry:
    """A single file/dir entry within a trash folder."""
    original_path: str                          # Native path for current platform
    original_name: str
    file_type: str
    link_target: Optional[str] = None
    link_broken: bool = False
    link_count: int = 1
    is_dir: bool = False
    content_preserved: bool = True
    content_path: Optional[str] = None
    delete_method: str = ""
    stat: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    # WSL dual-path support: original_path_alt holds the other platform's form
    # (e.g., /mnt/c/... when original_path is C:\..., or vice versa).
    # Populated when operating on WSL DrvFs paths so recovery works from
    # either runtime.
    original_path_alt: Optional[str] = None


@dataclass
class TrashFolder:
    """A timestamped trash folder containing one or more entries."""
    folder_name: str
    folder_path: str
    deleted_at: datetime.datetime
    entries: List[TrashEntry] = field(default_factory=list)
    manifest: Optional[Dict[str, Any]] = None

    @property
    def age(self) -> datetime.timedelta:
        return datetime.datetime.now() - self.deleted_at


@dataclass
class TrashResult:
    """Result of a trash operation (one or more files deleted)."""
    success: bool
    folder_name: str
    folder_path: str
    entries: List[TrashEntry] = field(default_factory=list)
    staging_results: List[StagingResult] = field(default_factory=list)
    delete_results: List[DeleteResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class StoreStats:
    """Statistics about the trash store."""
    total_entries: int = 0
    total_folders: int = 0
    total_size_bytes: int = 0
    oldest: Optional[str] = None
    newest: Optional[str] = None
    store_path: str = ""


class TrashStore:
    """Manages the safedel trash store."""

    def __init__(self, store_path: Optional[str] = None, registry_path: Optional[str] = None):
        self.store_path = store_path or get_trash_dir()
        self.registry_path = registry_path  # None = global default
        self.platform_info = detect_platform()

    def ensure_store_exists(self):
        """Create the trash store directory if it doesn't exist."""
        os.makedirs(self.store_path, exist_ok=True)

    def trash(
        self,
        paths: List[str],
        dry_run: bool = False,
    ) -> TrashResult:
        """Stage files for deletion and remove originals.

        This is the main entry point for the delete operation:
        1. Classify each path
        2. Create timestamped trash folder
        3. Collect metadata for each path
        4. Stage files to trash (rename or copy)
        5. Build and save manifest
        6. Delete originals
        7. Return report

        Args:
            paths: list of filesystem paths to delete
            dry_run: if True, classify and report but don't touch files

        Returns:
            TrashResult with full details of what happened
        """
        self.ensure_store_exists()

        # Step 1: Classify all paths
        classifications = []
        for path in paths:
            c = classify(path)
            classifications.append(c)

        # Resolve trash store: try per-volume for zero-copy rename,
        # fall back to central store.
        # Skip per-volume routing when registry_path is explicitly set
        # (test isolation -- tests provide their own store).
        existing = [c for c in classifications if c.exists]
        if existing and self.registry_path is None:
            effective_store, is_per_volume = resolve_trash_store(
                existing[0].path, self.store_path
            )
        else:
            effective_store, is_per_volume = self.store_path, False

        os.makedirs(effective_store, exist_ok=True)

        # Generate folder name in the chosen store
        folder_name = generate_unique_folder_name(effective_store)
        folder_path = os.path.join(effective_store, folder_name)
        content_dir = os.path.join(folder_path, "content")

        if dry_run:
            entries = []
            for c in classifications:
                entry = self._build_entry(c, content_dir, collect_meta=False)
                entries.append(entry)
            return TrashResult(
                success=True,
                folder_name=folder_name,
                folder_path=folder_path,
                entries=entries,
                warnings=["DRY RUN: No files were modified."],
            )

        # Step 2: Create trash folder
        os.makedirs(content_dir, exist_ok=True)

        # Step 3-6: Process each path
        entries = []
        staging_results = []
        delete_results = []
        errors = []
        warnings = []

        # Pre-flight: calculate total size and check disk space
        preservable_paths = [
            c.path for c in classifications
            if c.exists and c.content_preservable
        ]
        if preservable_paths:
            total_size = calculate_size(preservable_paths)
            space_warning = check_disk_space(self.store_path, total_size)
            if space_warning:
                warnings.append(space_warning)

            # Cross-device detection for warning triggers
            cross_device = not is_same_device(
                preservable_paths[0], effective_store
            )
            one_gb = 1024 * 1024 * 1024
            if cross_device and total_size > one_gb:
                size_gb = total_size / one_gb
                warnings.append(
                    f"Cross-device staging: {size_gb:.1f}GB will be copied "
                    f"(not renamed). This may be slow and some metadata "
                    f"(creation time, ADS) will not be preserved in the copy. "
                    f"Original metadata is recorded in the manifest."
                )

            # NTFS ADS warning: if cross-device AND files have significant
            # alternate data streams, the streams will be lost in the copy.
            if cross_device and sys.platform == "win32":
                ads_files = []
                for p in preservable_paths:
                    try:
                        streams = detect_alternate_streams(p)
                        if streams:
                            ads_files.append((p, streams))
                    except Exception:
                        pass
                if ads_files:
                    names = ", ".join(
                        f"{os.path.basename(p)}({len(s)} streams)"
                        for p, s in ads_files[:3]
                    )
                    if len(ads_files) > 3:
                        names += f", and {len(ads_files) - 3} more"
                    warnings.append(
                        f"NTFS alternate data streams detected on "
                        f"cross-device staging: {names}. These streams will "
                        f"NOT be preserved in the copy (stream names are "
                        f"recorded in the manifest)."
                    )

        for c in classifications:
            if not c.exists:
                errors.append(f"Skipping non-existent path: {c.path}")
                continue

            # Collect metadata before any changes
            entry = self._build_entry(c, content_dir, collect_meta=True)
            entries.append(entry)

            # Stage to trash
            sr = stage_to_trash(c.path, content_dir, c)
            staging_results.append(sr)

            if not sr.success:
                errors.append(f"Failed to stage {c.path}: {sr.error}")
                continue

            if sr.warnings:
                warnings.extend(sr.warnings)

            # Update entry with actual content path
            if sr.method != "metadata_only":
                entry.content_path = os.path.join(
                    "content", os.path.basename(c.path)
                )

            # Delete original (only if staging used copy, not rename)
            if sr.method == "copy":
                dr = safe_delete(c.path, c)
                delete_results.append(dr)
                if not dr.success:
                    errors.append(f"Failed to delete {c.path}: {dr.error}")
                if dr.warnings:
                    warnings.extend(dr.warnings)
            elif sr.method == "rename":
                # Rename already moved the file -- nothing to delete
                delete_results.append(DeleteResult(
                    success=True, path=c.path, method_used="rename (moved to trash)"
                ))
            elif sr.method in ("metadata_only", "symlink_recreate"):
                # For links: delete the link itself
                dr = safe_delete(c.path, c)
                delete_results.append(dr)
                if not dr.success:
                    errors.append(f"Failed to remove link {c.path}: {dr.error}")
                if dr.warnings:
                    warnings.extend(dr.warnings)

        # Step 5: Save manifest
        manifest = self._build_manifest(folder_name, entries)
        manifest_path = os.path.join(folder_path, "manifest.json")
        self._save_manifest(manifest, manifest_path)

        all_success = len(errors) == 0
        return TrashResult(
            success=all_success,
            folder_name=folder_name,
            folder_path=folder_path,
            entries=entries,
            staging_results=staging_results,
            delete_results=delete_results,
            errors=errors,
            warnings=warnings,
        )

    def list_entries(
        self,
        pattern: Optional[str] = None,
        age_filter: Optional[str] = None,
    ) -> List[TrashFolder]:
        """List trash folders matching a pattern and/or age filter.

        Scans both central and per-volume trash stores.
        """
        results = []
        for store_path in self._all_store_paths():
            folder_names = match_trash_folders(store_path, pattern, age_filter)
            for name in folder_names:
                folder = self._load_trash_folder(name, store_path)
                if folder:
                    results.append(folder)
        # Sort by timestamp across all stores
        results.sort(key=lambda f: f.deleted_at)
        return results

    def get_folder(self, folder_name: str) -> Optional[TrashFolder]:
        """Load a specific trash folder by name, searching all stores."""
        for store_path in self._all_store_paths():
            folder = self._load_trash_folder(folder_name, store_path)
            if folder:
                return folder
        return None

    def get_stats(self) -> StoreStats:
        """Get statistics about the trash store (all stores combined)."""
        stats = StoreStats(store_path=self.store_path)

        all_folders = self.list_entries()
        stats.total_folders = len(all_folders)

        if all_folders:
            stats.oldest = all_folders[0].folder_name
            stats.newest = all_folders[-1].folder_name

        total_entries = 0
        total_size = 0
        for folder in all_folders:
            total_entries += len(folder.entries)
            for e in folder.entries:
                if e.stat:
                    total_size += e.stat.get("st_size", 0)

        stats.total_entries = total_entries
        stats.total_size_bytes = total_size
        return stats

    def remove_folder(self, folder_name: str) -> bool:
        """Permanently remove a trash folder, searching all stores."""
        import shutil as _shutil
        for store_path in self._all_store_paths():
            folder_path = os.path.join(store_path, folder_name)
            if os.path.isdir(folder_path):
                try:
                    _shutil.rmtree(folder_path)
                    return True
                except OSError:
                    return False
        return False

    def _all_store_paths(self) -> List[str]:
        """Get all known trash store paths (central + per-volume)."""
        return get_all_trash_paths(self.store_path, self.registry_path)

    # -- Internal methods --

    def _build_entry(
        self, c: Classification, content_dir: str, collect_meta: bool
    ) -> TrashEntry:
        """Build a TrashEntry from a Classification."""
        meta = None
        stat_dict = None

        if collect_meta:
            try:
                raw_meta = collect_file_metadata(c.path)
                meta = metadata_to_json(raw_meta)
            except Exception:
                meta = None

            try:
                st = os.lstat(c.path)
                stat_dict = {
                    "st_size": st.st_size,
                    "st_mtime": st.st_mtime,
                    "st_atime": st.st_atime,
                    "st_ctime": st.st_ctime,
                    "st_mode": st.st_mode,
                    "st_nlink": st.st_nlink,
                    "st_ino": getattr(st, "st_ino", 0),
                }
                # Windows-specific
                if hasattr(st, "st_file_attributes"):
                    stat_dict["st_file_attributes"] = st.st_file_attributes
                # macOS/BSD birthtime
                if hasattr(st, "st_birthtime"):
                    stat_dict["st_birthtime"] = st.st_birthtime
                # Unix uid/gid
                if hasattr(st, "st_uid"):
                    stat_dict["st_uid"] = st.st_uid
                    stat_dict["st_gid"] = st.st_gid
            except OSError:
                stat_dict = None

        # Compute alternate-platform path form for cross-runtime recovery
        # (WSL <-> Windows). Uses filekit's normalize_cross_platform_path.
        alt_path = _compute_alt_path(c.path)

        return TrashEntry(
            original_path=c.path,
            original_path_alt=alt_path,
            original_name=os.path.basename(c.path),
            file_type=c.file_type.value,
            link_target=c.link_target,
            link_broken=c.link_broken,
            link_count=c.link_count,
            is_dir=c.is_dir,
            content_preserved=c.content_preservable,
            delete_method=c.delete_method.value,
            stat=stat_dict,
            metadata=meta,
            warnings=list(c.warnings),
        )

    def _build_manifest(
        self, folder_name: str, entries: List[TrashEntry]
    ) -> Dict[str, Any]:
        """Build the manifest dict for a trash folder."""
        now = datetime.datetime.now()
        return {
            "version": 1,
            "safedel_version": "0.1.0",
            "deleted_at": now.isoformat(),
            "folder_name": folder_name,
            "platform": {
                "system": self.platform_info.system,
                "platform": self.platform_info.platform,
                "is_wsl": self.platform_info.is_wsl,
                "wsl_distro": self.platform_info.wsl_distro,
                "python_version": self.platform_info.python_version,
                "hostname": self.platform_info.hostname,
            },
            "entries": [self._entry_to_dict(e) for e in entries],
        }

    def _entry_to_dict(self, entry: TrashEntry) -> Dict[str, Any]:
        """Convert a TrashEntry to a JSON-serializable dict."""
        return {
            "original_path": entry.original_path,
            "original_path_alt": entry.original_path_alt,
            "original_name": entry.original_name,
            "file_type": entry.file_type,
            "link_target": entry.link_target,
            "link_broken": entry.link_broken,
            "link_count": entry.link_count,
            "is_dir": entry.is_dir,
            "content_preserved": entry.content_preserved,
            "content_path": entry.content_path,
            "delete_method": entry.delete_method,
            "stat": entry.stat,
            "metadata": entry.metadata,
            "warnings": entry.warnings,
        }

    def _save_manifest(
        self, manifest: Dict[str, Any], path: str
    ) -> None:
        """Save manifest atomically via dazzle_filekit.operations.atomic_write_json."""
        from dazzle_filekit.operations import atomic_write_json
        atomic_write_json(path, manifest, indent=2, default=str)

    def _load_trash_folder(self, folder_name: str, store_path: Optional[str] = None) -> Optional[TrashFolder]:
        """Load a TrashFolder from disk."""
        folder_path = os.path.join(store_path or self.store_path, folder_name)
        manifest_path = os.path.join(folder_path, "manifest.json")

        if not os.path.isdir(folder_path):
            return None

        dt = parse_folder_datetime(folder_name)
        if dt is None:
            return None

        manifest = None
        entries = []

        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                for e_dict in manifest.get("entries", []):
                    entries.append(TrashEntry(
                        original_path=e_dict.get("original_path", ""),
                        original_path_alt=e_dict.get("original_path_alt"),
                        original_name=e_dict.get("original_name", ""),
                        file_type=e_dict.get("file_type", "unknown"),
                        link_target=e_dict.get("link_target"),
                        link_broken=e_dict.get("link_broken", False),
                        link_count=e_dict.get("link_count", 1),
                        is_dir=e_dict.get("is_dir", False),
                        content_preserved=e_dict.get("content_preserved", True),
                        content_path=e_dict.get("content_path"),
                        delete_method=e_dict.get("delete_method", ""),
                        stat=e_dict.get("stat"),
                        metadata=e_dict.get("metadata"),
                        warnings=e_dict.get("warnings", []),
                    ))
            except (json.JSONDecodeError, OSError):
                pass

        return TrashFolder(
            folder_name=folder_name,
            folder_path=folder_path,
            deleted_at=dt,
            entries=entries,
            manifest=manifest,
        )
