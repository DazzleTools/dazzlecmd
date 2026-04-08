"""
File classification and safety verdicts for safedel.

Wraps the links.py detect_link() function from the sibling 'links' tool
and adds a safety layer that determines the correct delete method per
file type and platform.

The safety matrix prevents the most dangerous mistakes:
- Never shutil.rmtree() on a junction (pre-3.12 traverses into target)
- Never os.unlink() on a Windows directory symlink (PermissionError)
- Always warn about hardlink count before deletion
"""

import os
import stat
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# -- Import detect_link from sibling links tool --

def _import_links():
    """Import the links module from the sibling 'links' tool directory."""
    links_dir = str(Path(__file__).parent.parent / "links")
    if links_dir not in sys.path:
        sys.path.insert(0, links_dir)
    import links as _links_mod
    return _links_mod


_links = _import_links()
detect_link = _links.detect_link
canonicalize_path = _links.canonicalize_path
LinkInfo = _links.LinkInfo

# Link type constants from links.py
LINK_SYMLINK = _links.LINK_SYMLINK
LINK_JUNCTION = _links.LINK_JUNCTION
LINK_HARDLINK = _links.LINK_HARDLINK
LINK_SHORTCUT = _links.LINK_SHORTCUT
LINK_URLSHORTCUT = _links.LINK_URLSHORTCUT
LINK_DAZZLELINK = _links.LINK_DAZZLELINK


class FileType(Enum):
    """Classified file type for safedel operations."""
    REGULAR_FILE = "regular_file"
    REGULAR_DIR = "regular_dir"
    EMPTY_DIR = "empty_dir"
    SYMLINK_FILE = "symlink_file"
    SYMLINK_DIR = "symlink_dir"
    JUNCTION = "junction"
    HARDLINK = "hardlink"
    SHORTCUT = "shortcut"         # .lnk file
    URL_SHORTCUT = "url_shortcut"  # .url file
    DAZZLELINK = "dazzlelink"     # .dazzlelink file
    BROKEN_LINK = "broken_link"
    UNKNOWN = "unknown"


class DeleteMethod(Enum):
    """The OS-level delete operation to use."""
    UNLINK = "os.unlink"
    RMDIR = "os.rmdir"
    RMTREE = "shutil.rmtree"


@dataclass
class Classification:
    """Result of classifying a filesystem path for safe deletion."""
    path: str
    file_type: FileType
    delete_method: DeleteMethod
    link_info: Optional[Any] = None  # LinkInfo from links.py
    link_target: Optional[str] = None
    link_broken: bool = False
    link_count: int = 1
    is_dir: bool = False
    size: int = 0
    warnings: List[str] = field(default_factory=list)
    content_preservable: bool = True
    exists: bool = True


def _normalize_path_no_resolve(path: str) -> str:
    """Normalize path format without resolving symlinks/junctions.

    Delegates to dazzle_filekit.paths.normalize_path_no_resolve() when
    available, with a stdlib fallback.
    """
    try:
        from dazzle_filekit.paths import normalize_path_no_resolve
        return str(normalize_path_no_resolve(path))
    except ImportError:
        pass

    # Fallback: basic normalization without resolving links
    import re
    path = str(path).strip()
    path = os.path.expanduser(path)
    m = re.match(r"^/([a-zA-Z])/", path)
    if m:
        drive = m.group(1).upper()
        path = drive + ":" + path[2:]
    path = path.replace("/", os.sep)
    if sys.platform == "win32" and path.startswith("\\\\?\\"):
        path = path[4:]
    path = os.path.normpath(path)
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.getcwd(), path))
    return path


def classify(path: str) -> Classification:
    """Classify a filesystem path for safe deletion.

    Determines the file type, correct delete method for the current platform,
    and generates safety warnings.

    Args:
        path: filesystem path to classify

    Returns:
        Classification with all relevant information for the delete operation.
    """
    path = _normalize_path_no_resolve(path)
    warnings = []

    # Check existence (use lstat to not follow links)
    try:
        lst = os.lstat(path)
    except OSError as e:
        return Classification(
            path=path,
            file_type=FileType.UNKNOWN,
            delete_method=DeleteMethod.UNLINK,
            exists=False,
            warnings=[f"Path does not exist or is not accessible: {e}"],
        )

    size = lst.st_size
    is_link = stat.S_ISLNK(lst.st_mode)

    # Use links.py detection for link types
    link_info = detect_link(path)

    if link_info is not None:
        return _classify_link(path, link_info, lst, warnings)

    # Not a link -- regular file or directory
    if os.path.isdir(path):
        return _classify_directory(path, lst, warnings)

    if os.path.isfile(path):
        return Classification(
            path=path,
            file_type=FileType.REGULAR_FILE,
            delete_method=DeleteMethod.UNLINK,
            size=size,
            warnings=warnings,
            content_preservable=True,
        )

    # Something else (device, socket, etc.)
    warnings.append(f"Unusual file type: mode={oct(lst.st_mode)}")
    return Classification(
        path=path,
        file_type=FileType.UNKNOWN,
        delete_method=DeleteMethod.UNLINK,
        size=size,
        warnings=warnings,
    )


def _classify_link(
    path: str, link_info: Any, lst: os.stat_result, warnings: List[str]
) -> Classification:
    """Classify a path that links.py identified as a link."""

    link_target = link_info.target
    link_broken = link_info.broken
    link_count = link_info.link_count
    is_dir = link_info.is_dir

    # Symlinks
    if link_info.link_type == LINK_SYMLINK:
        if link_broken:
            warnings.append(
                f"Broken symlink -> {link_target or '(unknown target)'}"
            )
            # Broken links: use unlink on all platforms (even dir symlinks
            # that are broken can usually be unlinked)
            delete_method = _symlink_delete_method(is_dir)
            return Classification(
                path=path,
                file_type=FileType.BROKEN_LINK,
                delete_method=delete_method,
                link_info=link_info,
                link_target=link_target,
                link_broken=True,
                is_dir=is_dir,
                size=lst.st_size,
                warnings=warnings,
                content_preservable=False,
            )

        file_type = FileType.SYMLINK_DIR if is_dir else FileType.SYMLINK_FILE
        delete_method = _symlink_delete_method(is_dir)

        warnings.append(
            f"Symlink -> {link_target}. "
            f"Only the link will be removed; target is untouched."
        )
        return Classification(
            path=path,
            file_type=file_type,
            delete_method=delete_method,
            link_info=link_info,
            link_target=link_target,
            is_dir=is_dir,
            size=lst.st_size,
            warnings=warnings,
            content_preservable=False,
        )

    # Junctions (Windows only)
    if link_info.link_type == LINK_JUNCTION:
        warnings.append(
            f"Junction -> {link_target}. "
            f"Only the junction entry will be removed; target directory is untouched."
        )
        warnings.append(
            "SAFETY: Using os.rmdir() -- never shutil.rmtree() on a junction."
        )
        return Classification(
            path=path,
            file_type=FileType.JUNCTION,
            delete_method=DeleteMethod.RMDIR,  # ALWAYS rmdir for junctions
            link_info=link_info,
            link_target=link_target,
            link_broken=link_broken,
            is_dir=True,
            size=lst.st_size,
            warnings=warnings,
            content_preservable=False,
        )

    # Hardlinks
    if link_info.link_type == LINK_HARDLINK:
        warnings.append(
            f"Hardlink with {link_count} total links (inode {link_info.inode}). "
            f"Removing this entry does NOT delete the file data."
        )
        if link_info.target:
            warnings.append(f"Other known path: {link_info.target}")
        return Classification(
            path=path,
            file_type=FileType.HARDLINK,
            delete_method=DeleteMethod.UNLINK,
            link_info=link_info,
            link_target=link_info.target,
            link_count=link_count,
            size=lst.st_size,
            warnings=warnings,
            content_preservable=True,  # We can copy the file content
        )

    # File-based link types (.lnk, .url, .dazzlelink)
    if link_info.link_type == LINK_SHORTCUT:
        file_type = FileType.SHORTCUT
    elif link_info.link_type == LINK_URLSHORTCUT:
        file_type = FileType.URL_SHORTCUT
    elif link_info.link_type == LINK_DAZZLELINK:
        file_type = FileType.DAZZLELINK
    else:
        file_type = FileType.UNKNOWN

    warnings.append(
        f"Descriptor file ({link_info.link_type}) -> {link_target or '(none)'}. "
        f"Only this descriptor file will be removed."
    )
    return Classification(
        path=path,
        file_type=file_type,
        delete_method=DeleteMethod.UNLINK,
        link_info=link_info,
        link_target=link_target,
        link_broken=link_broken,
        size=lst.st_size,
        warnings=warnings,
        content_preservable=True,  # The .lnk/.url file itself can be copied
    )


def _classify_directory(
    path: str, lst: os.stat_result, warnings: List[str]
) -> Classification:
    """Classify a regular (non-link) directory."""
    try:
        entries = os.listdir(path)
    except OSError:
        entries = None

    if entries is not None and len(entries) == 0:
        return Classification(
            path=path,
            file_type=FileType.EMPTY_DIR,
            delete_method=DeleteMethod.RMDIR,
            is_dir=True,
            warnings=warnings,
            content_preservable=True,
        )

    if entries is not None:
        count = len(entries)
        warnings.append(f"Directory with {count} entries.")

    return Classification(
        path=path,
        file_type=FileType.REGULAR_DIR,
        delete_method=DeleteMethod.RMTREE,
        is_dir=True,
        size=lst.st_size,
        warnings=warnings,
        content_preservable=True,
    )


def _symlink_delete_method(is_dir: bool) -> DeleteMethod:
    """Determine the correct delete method for a symlink.

    On Windows, directory symlinks MUST use os.rmdir() -- os.unlink()
    raises PermissionError. On Linux/Mac, os.unlink() works for all symlinks.
    """
    if sys.platform == "win32" and is_dir:
        return DeleteMethod.RMDIR
    return DeleteMethod.UNLINK


def format_classification(c: Classification) -> str:
    """Format a classification as a human-readable summary."""
    lines = []
    lines.append(f"  Path: {c.path}")
    lines.append(f"  Type: {c.file_type.value}")
    lines.append(f"  Delete method: {c.delete_method.value}")
    if c.link_target:
        lines.append(f"  Link target: {c.link_target}")
    if c.link_broken:
        lines.append(f"  Link status: BROKEN")
    if c.link_count > 1:
        lines.append(f"  Hard link count: {c.link_count}")
    if c.size:
        lines.append(f"  Size: {c.size} bytes")
    if c.warnings:
        for w in c.warnings:
            lines.append(f"  * {w}")
    return "\n".join(lines)
