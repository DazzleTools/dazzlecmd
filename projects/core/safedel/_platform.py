"""
Platform-specific operations for safedel.

Handles the low-level filesystem operations that differ across platforms:
- Delete dispatch (unlink, rmdir, rmtree with safety checks)
- Staging files to trash (rename vs copy+delete)
- WSL detection
- Same-device detection
- Readonly file handling
"""

import errno
import os
import platform
import shutil
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from _classifier import Classification, DeleteMethod, FileType


@dataclass
class PlatformInfo:
    """Information about the current platform."""
    system: str        # "Windows", "Linux", "Darwin"
    platform: str      # sys.platform: "win32", "linux", "darwin"
    is_wsl: bool = False
    wsl_distro: Optional[str] = None
    python_version: str = ""
    hostname: str = ""

    @property
    def is_windows(self) -> bool:
        return self.platform == "win32"

    @property
    def is_linux(self) -> bool:
        return self.platform == "linux"

    @property
    def is_macos(self) -> bool:
        return self.platform == "darwin"


@dataclass
class DeleteResult:
    """Result of a delete operation."""
    success: bool
    path: str
    method_used: str = ""
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class StagingResult:
    """Result of staging a file/dir to the trash store."""
    success: bool
    source_path: str
    dest_path: str
    method: str = ""   # "rename" or "copy"
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def detect_platform() -> PlatformInfo:
    """Detect the current platform, including WSL."""
    info = PlatformInfo(
        system=platform.system(),
        platform=sys.platform,
        python_version=platform.python_version(),
        hostname=platform.node(),
    )

    # WSL detection
    if sys.platform == "linux":
        wsl_distro = os.environ.get("WSL_DISTRO_NAME")
        if wsl_distro:
            info.is_wsl = True
            info.wsl_distro = wsl_distro
        else:
            # Fallback: check /proc/version
            try:
                with open("/proc/version", "r") as f:
                    version_str = f.read().lower()
                if "microsoft" in version_str or "wsl" in version_str:
                    info.is_wsl = True
            except OSError:
                pass

    return info


def is_same_device(path1: str, path2: str) -> bool:
    """Check if two paths are on the same filesystem device.

    This determines whether os.rename() can be used (atomic, zero-copy)
    or if a copy+delete is required.
    """
    try:
        dev1 = os.stat(path1).st_dev
        dev2 = os.stat(path2).st_dev
        return dev1 == dev2
    except OSError:
        return False


def stage_to_trash(
    source_path: str,
    dest_dir: str,
    classification: Classification,
) -> StagingResult:
    """Stage a file or directory to the trash store.

    Strategy:
    1. Try os.rename() first (same-volume, atomic, preserves ALL metadata)
    2. Fall back to copy+delete on cross-device error (EXDEV)
    3. For links: we stage the link info, not the target content

    Args:
        source_path: the path being deleted
        dest_dir: the content/ directory inside the timestamped trash folder
        classification: the classification result from _classifier

    Returns:
        StagingResult
    """
    source_name = os.path.basename(source_path)
    dest_path = os.path.join(dest_dir, source_name)

    # Ensure dest directory exists
    os.makedirs(dest_dir, exist_ok=True)

    # For link types (symlink, junction): we don't copy target content.
    # We just need to record the link metadata in the manifest.
    # Stage the link entry itself if possible.
    if classification.file_type in (
        FileType.SYMLINK_FILE, FileType.SYMLINK_DIR,
        FileType.JUNCTION, FileType.BROKEN_LINK,
    ):
        return _stage_link(source_path, dest_path, classification)

    # For regular files, hardlinks, and descriptor files (.lnk, .url):
    # Try rename first, fall back to copy
    return _stage_regular(source_path, dest_path, classification)


def _stage_link(
    source_path: str, dest_path: str, classification: Classification
) -> StagingResult:
    """Stage a symlink or junction.

    We recreate the link in the trash rather than copying the target.
    If we can't recreate it, we just record it in the manifest (content_preserved=False).
    """
    warnings = []
    link_target = classification.link_target

    if classification.file_type == FileType.JUNCTION:
        # Junctions: we can't easily recreate them portably.
        # Just record the metadata. The manifest has the target path.
        warnings.append(
            "Junction staged as metadata only (target path recorded in manifest)."
        )
        return StagingResult(
            success=True,
            source_path=source_path,
            dest_path=dest_path,
            method="metadata_only",
            warnings=warnings,
        )

    # Symlinks: try to recreate in trash
    if link_target:
        try:
            os.symlink(link_target, dest_path,
                        target_is_directory=classification.is_dir)
            return StagingResult(
                success=True,
                source_path=source_path,
                dest_path=dest_path,
                method="symlink_recreate",
            )
        except OSError as e:
            warnings.append(
                f"Could not recreate symlink in trash: {e}. "
                f"Link target recorded in manifest."
            )

    return StagingResult(
        success=True,
        source_path=source_path,
        dest_path=dest_path,
        method="metadata_only",
        warnings=warnings,
    )


def _stage_regular(
    source_path: str, dest_path: str, classification: Classification
) -> StagingResult:
    """Stage a regular file or directory via rename or copy."""
    # Try atomic rename first
    try:
        os.rename(source_path, dest_path)
        return StagingResult(
            success=True,
            source_path=source_path,
            dest_path=dest_path,
            method="rename",
        )
    except OSError as e:
        if e.errno != errno.EXDEV:
            # Not a cross-device error -- something else went wrong
            # Still try copy as fallback
            pass

    # Cross-device: must copy then delete
    warnings = []
    try:
        if classification.is_dir:
            shutil.copytree(
                source_path, dest_path,
                symlinks=True,  # CRITICAL: never follow symlinks in trees
                copy_function=shutil.copy2,  # Preserve metadata
            )
        else:
            shutil.copy2(source_path, dest_path)

        warnings.append(
            "Cross-device staging: file was copied (some metadata like "
            "creation time may not be preserved). Original metadata "
            "is recorded in manifest."
        )
        return StagingResult(
            success=True,
            source_path=source_path,
            dest_path=dest_path,
            method="copy",
            warnings=warnings,
        )
    except OSError as e:
        return StagingResult(
            success=False,
            source_path=source_path,
            dest_path=dest_path,
            method="copy",
            error=f"Failed to stage: {e}",
            warnings=warnings,
        )


def safe_delete(path: str, classification: Classification) -> DeleteResult:
    """Execute the delete operation using the correct method for the platform.

    This is called AFTER the file has been staged to trash. It removes
    the original file/link from its location.

    Args:
        path: the path to delete
        classification: the classification with the determined delete method

    Returns:
        DeleteResult
    """
    method = classification.delete_method
    warnings = []

    try:
        if method == DeleteMethod.UNLINK:
            _safe_unlink(path)
            return DeleteResult(
                success=True, path=path, method_used="os.unlink"
            )

        elif method == DeleteMethod.RMDIR:
            os.rmdir(path)
            return DeleteResult(
                success=True, path=path, method_used="os.rmdir"
            )

        elif method == DeleteMethod.RMTREE:
            # Extra safety: verify this is NOT a junction or symlink
            # (defense in depth -- classifier should never assign RMTREE to these)
            if os.path.islink(path):
                warnings.append(
                    "SAFETY OVERRIDE: rmtree was requested on a symlink. "
                    "Using unlink instead to prevent target traversal."
                )
                _safe_unlink(path)
                return DeleteResult(
                    success=True, path=path,
                    method_used="os.unlink (safety override)",
                    warnings=warnings,
                )

            if sys.platform == "win32":
                # Check for junction (defense in depth)
                try:
                    st = os.lstat(path)
                    if st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        warnings.append(
                            "SAFETY OVERRIDE: rmtree on reparse point. "
                            "Using rmdir instead."
                        )
                        os.rmdir(path)
                        return DeleteResult(
                            success=True, path=path,
                            method_used="os.rmdir (safety override)",
                            warnings=warnings,
                        )
                except (AttributeError, OSError):
                    pass

            shutil.rmtree(path, onerror=_rmtree_error_handler)
            return DeleteResult(
                success=True, path=path, method_used="shutil.rmtree"
            )

        else:
            return DeleteResult(
                success=False, path=path,
                error=f"Unknown delete method: {method}",
            )

    except OSError as e:
        return DeleteResult(
            success=False, path=path,
            method_used=method.value,
            error=str(e),
            warnings=warnings,
        )


def _safe_unlink(path: str) -> None:
    """Unlink a file, handling readonly files by clearing the flag first."""
    try:
        os.unlink(path)
    except PermissionError:
        # Try clearing readonly flag and retry
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            os.unlink(path)
        except OSError:
            raise  # Re-raise the original if chmod didn't help


def _rmtree_error_handler(func, path, exc_info):
    """Error handler for shutil.rmtree that handles readonly files."""
    # If the error is due to readonly, clear the flag and retry
    if isinstance(exc_info[1], PermissionError):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)
        except OSError:
            pass  # Give up on this file


def get_trash_dir() -> str:
    """Get the default trash store directory for the current platform.

    Location:
        Windows:  %LOCALAPPDATA%\\safedel\\trash\\
        Linux:    ~/.safedel/trash/
        macOS:    ~/.safedel/trash/
        WSL:      ~/.safedel/trash/

    Override: SAFEDEL_STORE environment variable
    """
    override = os.environ.get("SAFEDEL_STORE")
    if override:
        return override

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return os.path.join(local_app_data, "safedel", "trash")

    # Linux, macOS, WSL
    return os.path.join(os.path.expanduser("~"), ".safedel", "trash")


def check_disk_space(trash_dir: str, required_bytes: int) -> Optional[str]:
    """Check if there's enough disk space for staging.

    Returns:
        None if OK, or a warning string if space is low.
    """
    try:
        usage = shutil.disk_usage(trash_dir)
        if usage.free < required_bytes + (500 * 1024 * 1024):  # 500MB buffer
            free_mb = usage.free / (1024 * 1024)
            req_mb = required_bytes / (1024 * 1024)
            return (
                f"Low disk space at {trash_dir}: "
                f"{free_mb:.0f}MB free, need {req_mb:.0f}MB + 500MB buffer."
            )
    except OSError:
        pass  # Can't check -- proceed anyway
    return None
