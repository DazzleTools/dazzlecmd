"""
links - Detect and display filesystem links

Cross-platform tool that scans directories for all types of filesystem links
and shortcuts, and displays them with their targets and status.

Detected types:
  symlink     - Symbolic links (file or directory)
  junction    - Windows junctions (directory reparse points)
  hardlink    - Hard links (multiple directory entries for same inode)
  shortcut    - Windows .lnk Shell Link files
  urlshortcut - .url Internet Shortcut files (web resources, URIs)
  dazzlelink  - .dazzlelink JSON descriptor files
"""

import argparse
import json
import os
import re
import stat
import struct
import sys


# -- Path canonicalization --
# Handles MSYS/Git Bash paths (/c/foo), forward slashes, mixed slashes,
# and uses dazzle-filekit/unctools when available for normalization and UNC support.

# MSYS-style path pattern: /c/ or /d/ etc.
_MSYS_DRIVE_RE = re.compile(r"^/([a-zA-Z])/")


def canonicalize_path(path):
    """Canonicalize a user-provided path to the native OS format.

    Handles:
      /c/Users/foo  ->  C:\\Users\\foo       (MSYS/Git Bash style)
      c:/Users/foo  ->  C:\\Users\\foo       (forward-slash Windows)
      c:\\Users\\foo ->  C:\\Users\\foo       (native Windows)
      \\\\?\\C:\\... ->  C:\\...              (extended-length prefix)
      ~/foo         ->  C:\\Users\\Me\\foo   (tilde expansion)

    Uses dazzle_filekit.paths.normalize_path() when available for
    symlink resolution and robust normalization. Uses unctools for
    UNC path canonicalization when available.
    """
    if not path:
        return path

    path = str(path).strip()

    # Expand ~ first
    path = os.path.expanduser(path)

    # Convert MSYS /c/path -> C:/path (before any backslash conversion)
    m = _MSYS_DRIVE_RE.match(path)
    if m:
        drive = m.group(1).upper()
        path = drive + ":" + path[2:]

    # Normalize slashes to OS native
    path = path.replace("/", os.sep)

    # Strip extended-length prefix \\?\ on Windows
    if sys.platform == "win32" and path.startswith("\\\\?\\"):
        path = path[4:]

    # Try dazzle_filekit for robust normalization (resolve symlinks, etc.)
    try:
        from dazzle_filekit.paths import normalize_path as fk_normalize
        return str(fk_normalize(path))
    except ImportError:
        pass

    # Fallback: os-level normalization
    path = os.path.normpath(path)
    path = os.path.abspath(path)
    return path


def canonicalize_target(target):
    """Canonicalize a link target path for display.

    Strips \\\\?\\ prefix and normalizes slashes, but does NOT
    resolve the path (the target may not exist).
    """
    if not target:
        return target

    target = str(target)

    # Strip extended-length prefix
    if target.startswith("\\\\?\\"):
        target = target[4:]

    return target


# -- Link type constants --

LINK_SYMLINK = "symlink"
LINK_JUNCTION = "junction"
LINK_HARDLINK = "hardlink"
LINK_SHORTCUT = "shortcut"
LINK_URLSHORTCUT = "urlshortcut"
LINK_DAZZLELINK = "dazzlelink"

ALL_LINK_TYPES = [
    LINK_SYMLINK, LINK_JUNCTION, LINK_HARDLINK,
    LINK_SHORTCUT, LINK_URLSHORTCUT, LINK_DAZZLELINK,
]


# -- Data structure --

class LinkInfo:
    """Information about a detected link."""

    __slots__ = (
        "path", "name", "link_type", "target", "broken",
        "link_count", "inode", "size", "is_dir",
    )

    def __init__(self, path, name, link_type, target=None, broken=False,
                 link_count=1, inode=0, size=0, is_dir=False):
        self.path = path
        self.name = name
        self.link_type = link_type
        self.target = target
        self.broken = broken
        self.link_count = link_count
        self.inode = inode
        self.size = size
        self.is_dir = is_dir

    def to_dict(self):
        return {
            "path": self.path,
            "name": self.name,
            "link_type": self.link_type,
            "target": self.target,
            "broken": self.broken,
            "link_count": self.link_count,
            "inode": self.inode,
            "size": self.size,
            "is_dir": self.is_dir,
        }


# -- Platform-specific detection --

def _is_junction_win(path):
    """Check if a path is a Windows junction (not a symlink)."""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        # Get reparse point data to distinguish junction from symlink
        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        attrs = kernel32.GetFileAttributesW(str(path))
        if attrs == -1 or not (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
            return False

        # Open the file to read the reparse tag
        OPEN_EXISTING = 3
        FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        GENERIC_READ = 0x80000000

        handle = kernel32.CreateFileW(
            str(path), 0,
            0x01 | 0x02 | 0x04,  # FILE_SHARE_READ | WRITE | DELETE
            None, OPEN_EXISTING,
            FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle == wintypes.HANDLE(-1).value:
            # Can't open - fall back to assuming junction if it's a reparse
            # point but os.path.islink returns False
            return not os.path.islink(path)

        try:
            # Read reparse data
            IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
            FSCTL_GET_REPARSE_POINT = 0x000900A8
            buf = ctypes.create_string_buffer(16384)
            bytes_returned = wintypes.DWORD(0)

            ok = kernel32.DeviceIoControl(
                handle, FSCTL_GET_REPARSE_POINT,
                None, 0, buf, 16384,
                ctypes.byref(bytes_returned), None,
            )
            if ok:
                tag = int.from_bytes(buf[:4], byteorder="little")
                return tag == IO_REPARSE_TAG_MOUNT_POINT
            else:
                return not os.path.islink(path)
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError, ImportError):
        return False


def _get_hardlink_paths_win(filepath):
    """Get all paths for a hardlinked file on Windows using FindFirstFileNameW."""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        # Declare function signatures to avoid access violations
        kernel32.FindFirstFileNameW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR,
        ]
        kernel32.FindFirstFileNameW.restype = ctypes.c_void_p

        kernel32.FindNextFileNameW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR,
        ]
        kernel32.FindNextFileNameW.restype = wintypes.BOOL

        buf_size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)

        handle = kernel32.FindFirstFileNameW(
            str(filepath), 0, ctypes.byref(buf_size), buf
        )
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        if handle is None or handle == INVALID_HANDLE_VALUE:
            return []

        # Set FindClose to accept c_void_p handle
        kernel32.FindClose.argtypes = [ctypes.c_void_p]
        kernel32.FindClose.restype = wintypes.BOOL

        paths = []
        try:
            paths.append(buf.value)
            buf_size.value = 1024
            while kernel32.FindNextFileNameW(handle, ctypes.byref(buf_size), buf):
                paths.append(buf.value)
                buf_size.value = 1024
        finally:
            kernel32.FindClose(handle)

        # Paths are volume-relative (e.g. \Users\foo\file.txt)
        # Prepend drive letter from the original path
        drive = os.path.splitdrive(os.path.abspath(filepath))[0]
        return [drive + p for p in paths]
    except (OSError, AttributeError, ImportError):
        return []


def _get_hardlink_paths_unix(filepath):
    """Get hardlink paths on Unix by scanning mount point for matching inode."""
    # This is expensive - only do it for explicit file queries, not directory scans
    try:
        st = os.stat(filepath)
        if st.st_nlink <= 1:
            return []
        # We can't efficiently find other paths without scanning
        # Just report the link count
        return []
    except OSError:
        return []


# -- Shortcut parsing (.lnk and .url) --

def _parse_lnk(filepath):
    """Parse a Windows .lnk Shell Link file (MS-SHLLINK binary format).

    Returns a dict with keys: target, working_dir, arguments, description,
    icon_location, is_dir. Returns None on parse failure.

    Target resolution priority:
    1. StringData relative_path (resolved relative to .lnk location) -- most reliable
    2. LinkInfo local base path + common suffix -- sometimes just the drive root
    3. LinkInfo network path -- UNC paths
    """
    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except OSError:
        return None

    # ShellLinkHeader is 76 bytes, starts with HeaderSize=0x4C
    if len(data) < 76:
        return None
    header_size = struct.unpack_from("<I", data, 0)[0]
    if header_size != 0x4C:
        return None

    # Verify CLSID {00021401-0000-0000-C000-000000000046}
    clsid = data[4:20]
    expected_clsid = (
        b"\x01\x14\x02\x00\x00\x00\x00\x00"
        b"\xC0\x00\x00\x00\x00\x00\x00\x46"
    )
    if clsid != expected_clsid:
        return None

    link_flags = struct.unpack_from("<I", data, 20)[0]
    file_attrs = struct.unpack_from("<I", data, 24)[0]

    has_id_list = bool(link_flags & 0x01)
    has_link_info = bool(link_flags & 0x02)
    has_name = bool(link_flags & 0x04)
    has_relative_path = bool(link_flags & 0x08)
    has_working_dir = bool(link_flags & 0x10)
    has_arguments = bool(link_flags & 0x20)
    has_icon_location = bool(link_flags & 0x40)
    is_unicode = bool(link_flags & 0x80)

    is_dir = bool(file_attrs & 0x10)  # FILE_ATTRIBUTE_DIRECTORY

    offset = 76  # Past the header

    # Skip LinkTargetIDList if present
    if has_id_list:
        if offset + 2 > len(data):
            return None
        id_list_size = struct.unpack_from("<H", data, offset)[0]
        offset += 2 + id_list_size

    # Parse LinkInfo for local/network base path
    linkinfo_target = None
    if has_link_info:
        if offset + 4 > len(data):
            return None
        link_info_size = struct.unpack_from("<I", data, offset)[0]
        if link_info_size >= 12:
            li_start = offset
            li_header_size = struct.unpack_from("<I", data, offset + 4)[0]
            li_flags = struct.unpack_from("<I", data, offset + 8)[0]

            has_volume_and_path = bool(li_flags & 0x01)
            has_network_path = bool(li_flags & 0x02)

            if has_volume_and_path and li_header_size >= 28:
                local_base_offset = struct.unpack_from("<I", data, offset + 16)[0]
                # Check for Unicode variant (header >= 0x24)
                if li_header_size >= 0x24 and offset + 28 <= len(data):
                    local_base_unicode_offset = struct.unpack_from(
                        "<I", data, offset + 28
                    )[0]
                    if local_base_unicode_offset > 0:
                        pos = li_start + local_base_unicode_offset
                        linkinfo_target = _read_wstring_null(data, pos)
                if not linkinfo_target:
                    pos = li_start + local_base_offset
                    linkinfo_target = _read_string_null(data, pos)

            if not linkinfo_target and has_network_path and li_header_size >= 20:
                net_rel_offset = struct.unpack_from("<I", data, offset + 20)[0]
                if net_rel_offset > 0:
                    net_start = li_start + net_rel_offset
                    if net_start + 20 <= len(data):
                        net_name_offset = struct.unpack_from(
                            "<I", data, net_start + 8
                        )[0]
                        net_name = _read_string_null(data, net_start + net_name_offset)
                        if net_name:
                            linkinfo_target = net_name

        offset += link_info_size

    # Parse StringData section
    result = {
        "target": None,
        "working_dir": None,
        "arguments": None,
        "description": None,
        "icon_location": None,
        "is_dir": is_dir,
    }

    relative_path = None
    for field, flag in [
        ("description", has_name),
        ("relative_path", has_relative_path),
        ("working_dir", has_working_dir),
        ("arguments", has_arguments),
        ("icon_location", has_icon_location),
    ]:
        if flag:
            if offset + 2 > len(data):
                break
            count = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            if is_unicode:
                byte_len = count * 2
                if offset + byte_len > len(data):
                    break
                val = data[offset:offset + byte_len].decode("utf-16-le", errors="replace")
                offset += byte_len
            else:
                if offset + count > len(data):
                    break
                val = data[offset:offset + count].decode("cp1252", errors="replace")
                offset += count

            if field == "relative_path":
                relative_path = val
            elif field in result:
                result[field] = val

    # Resolve target with priority: relative_path > linkinfo_target
    if relative_path:
        # Resolve relative to the .lnk file's directory
        lnk_dir = os.path.dirname(os.path.abspath(filepath))
        resolved = os.path.normpath(os.path.join(lnk_dir, relative_path))
        result["target"] = resolved
    elif linkinfo_target:
        result["target"] = linkinfo_target

    return result


def _read_string_null(data, offset):
    """Read a null-terminated ASCII/CP1252 string from binary data."""
    if offset >= len(data):
        return None
    end = data.index(b"\x00", offset) if b"\x00" in data[offset:] else len(data)
    return data[offset:end].decode("cp1252", errors="replace")


def _read_wstring_null(data, offset):
    """Read a null-terminated UTF-16LE string from binary data."""
    if offset >= len(data):
        return None
    result = []
    pos = offset
    while pos + 1 < len(data):
        char = struct.unpack_from("<H", data, pos)[0]
        if char == 0:
            break
        result.append(chr(char))
        pos += 2
    return "".join(result) if result else None


def _parse_url_shortcut(filepath):
    """Parse a .url Internet Shortcut file (INI format).

    Returns the URL string, or None on failure.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            in_section = False
            for line in f:
                line = line.strip()
                if line.lower() == "[internetshortcut]":
                    in_section = True
                    continue
                if in_section:
                    if line.startswith("["):
                        break
                    if line.lower().startswith("url="):
                        return line[4:].strip()
        return None
    except OSError:
        return None


# -- Core detection --

def detect_link(path):
    """Detect the link type for a single path. Returns LinkInfo or None."""
    name = os.path.basename(path)
    abs_path = os.path.abspath(path)

    try:
        lstat = os.lstat(path)
    except OSError:
        return None

    is_dir = stat.S_ISDIR(lstat.st_mode) or (
        stat.S_ISLNK(lstat.st_mode) and os.path.isdir(path)
    )
    inode = getattr(lstat, "st_ino", 0)
    size = lstat.st_size

    # Check file-based link types first (not OS links)
    name_lower = name.lower()

    if name_lower.endswith(".dazzlelink"):
        return _detect_dazzlelink(abs_path, name, lstat)

    if name_lower.endswith(".lnk"):
        return _detect_shortcut(abs_path, name, lstat)

    if name_lower.endswith(".url"):
        return _detect_url_shortcut(abs_path, name, lstat)

    # Symlink or junction
    if os.path.islink(path):
        target = canonicalize_target(_safe_readlink(path))
        broken = target is not None and not os.path.exists(path)
        return LinkInfo(
            path=abs_path, name=name, link_type=LINK_SYMLINK,
            target=target, broken=broken, inode=inode, size=size,
            is_dir=is_dir,
        )

    # Windows junction (reparse point that isn't a symlink)
    if sys.platform == "win32" and os.path.isdir(path) and _is_junction_win(path):
        target = canonicalize_target(_safe_readlink(path))
        broken = target is not None and not os.path.exists(path)
        return LinkInfo(
            path=abs_path, name=name, link_type=LINK_JUNCTION,
            target=target, broken=broken, inode=inode, size=size,
            is_dir=True,
        )

    # Hardlink (regular file with nlink > 1)
    if stat.S_ISREG(lstat.st_mode) and lstat.st_nlink > 1:
        if sys.platform == "win32":
            other_paths = _get_hardlink_paths_win(abs_path)
        else:
            other_paths = _get_hardlink_paths_unix(abs_path)

        # Filter out self
        other_paths = [p for p in other_paths
                       if os.path.normcase(os.path.normpath(p))
                       != os.path.normcase(os.path.normpath(abs_path))]

        target = other_paths[0] if other_paths else None
        return LinkInfo(
            path=abs_path, name=name, link_type=LINK_HARDLINK,
            target=target, broken=False,
            link_count=lstat.st_nlink, inode=inode, size=size,
        )

    return None


def _detect_shortcut(path, name, lstat):
    """Parse a .lnk Windows Shell Link file."""
    parsed = _parse_lnk(path)
    if parsed is None:
        return LinkInfo(
            path=path, name=name, link_type=LINK_SHORTCUT,
            target=None, broken=True,
            inode=getattr(lstat, "st_ino", 0), size=lstat.st_size,
        )
    target = parsed.get("target")
    if target:
        broken = not os.path.exists(target)
    else:
        broken = True
    return LinkInfo(
        path=path, name=name, link_type=LINK_SHORTCUT,
        target=target, broken=broken,
        inode=getattr(lstat, "st_ino", 0), size=lstat.st_size,
        is_dir=parsed.get("is_dir", False),
    )


def _detect_url_shortcut(path, name, lstat):
    """Parse a .url Internet Shortcut file."""
    url = _parse_url_shortcut(path)
    # URL shortcuts point to web resources -- "broken" means unparseable,
    # not that the URL is unreachable (we don't do HTTP checks)
    return LinkInfo(
        path=path, name=name, link_type=LINK_URLSHORTCUT,
        target=url, broken=(url is None),
        inode=getattr(lstat, "st_ino", 0), size=lstat.st_size,
    )


def _detect_dazzlelink(path, name, lstat):
    """Parse a .dazzlelink JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        target = data.get("link", {}).get("target_path") or data.get("target")
        if target:
            target = os.path.expanduser(target)
            broken = not os.path.exists(target)
        else:
            broken = True
        return LinkInfo(
            path=path, name=name, link_type=LINK_DAZZLELINK,
            target=target, broken=broken,
            inode=getattr(lstat, "st_ino", 0), size=lstat.st_size,
        )
    except (json.JSONDecodeError, OSError):
        return LinkInfo(
            path=path, name=name, link_type=LINK_DAZZLELINK,
            target=None, broken=True,
            inode=getattr(lstat, "st_ino", 0), size=lstat.st_size,
        )


def _safe_readlink(path):
    """Read link target, returning None on failure."""
    try:
        return os.readlink(path)
    except OSError:
        return None


# -- Directory scanning --

def scan_directory(directory, recursive=False, type_filter=None, broken_only=False):
    """Scan a directory for links. Yields LinkInfo objects."""
    directory = os.path.abspath(directory)

    if recursive:
        for root, dirs, files in os.walk(directory):
            # Check directories themselves (symlinks/junctions)
            for d in list(dirs):
                full = os.path.join(root, d)
                info = detect_link(full)
                if info and _matches_filter(info, type_filter, broken_only):
                    yield info
                    # Don't recurse into linked directories
                    if info.link_type in (LINK_SYMLINK, LINK_JUNCTION):
                        dirs.remove(d)
            for f in files:
                full = os.path.join(root, f)
                info = detect_link(full)
                if info and _matches_filter(info, type_filter, broken_only):
                    yield info
    else:
        try:
            entries = os.listdir(directory)
        except OSError as exc:
            print(f"Error: Cannot read directory: {exc}", file=sys.stderr)
            return

        for entry in sorted(entries):
            full = os.path.join(directory, entry)
            info = detect_link(full)
            if info and _matches_filter(info, type_filter, broken_only):
                yield info


def _matches_filter(info, type_filter, broken_only):
    """Check if a LinkInfo matches the active filters."""
    if broken_only and not info.broken:
        return False
    if type_filter and info.link_type not in type_filter:
        return False
    return True


# -- Display --

def shorten_path(path):
    """Shorten a path by replacing the home directory with ~."""
    home = os.path.expanduser("~")
    if path and os.path.normcase(path).startswith(os.path.normcase(home)):
        return "~" + path[len(home):]
    return path


def display_table(links, verbose=False):
    """Display links in table format."""
    link_list = list(links)
    if not link_list:
        print("  No links found.")
        return

    for info in link_list:
        status = "[BROKEN]" if info.broken else ""
        target_str = ""
        if info.target:
            target_str = f" -> {shorten_path(info.target)}"
        count_str = ""
        if info.link_type == LINK_HARDLINK and info.link_count > 1:
            count_str = f"  ({info.link_count} links)"

        suffix = "/"  if info.is_dir else ""
        print(f"  {info.name}{suffix:<1}  {info.link_type:<12}{target_str}{count_str}  {status}")

        if verbose:
            print(f"    path:    {info.path}")
            if info.target:
                print(f"    target:  {info.target}")
            print(f"    type:    {info.link_type}")
            if info.link_type == LINK_HARDLINK:
                print(f"    links:   {info.link_count}")
            if info.inode:
                print(f"    inode:   {info.inode}")
            print(f"    size:    {info.size} bytes")
            print()

    # Summary
    type_counts = {}
    broken_count = 0
    for info in link_list:
        type_counts[info.link_type] = type_counts.get(info.link_type, 0) + 1
        if info.broken:
            broken_count += 1

    parts = [f"{count} {ltype}" for ltype, count in sorted(type_counts.items())]
    summary = f"\n  {len(link_list)} link(s) found: {', '.join(parts)}"
    if broken_count:
        summary += f"  ({broken_count} broken)"
    print(summary)


def display_json(links):
    """Display links as JSON."""
    link_list = [info.to_dict() for info in links]
    print(json.dumps(link_list, indent=2))


# -- CLI --

def build_parser():
    """Build argument parser for links."""
    parser = argparse.ArgumentParser(
        prog="dz links",
        description="Detect and display filesystem links",
    )
    parser.add_argument(
        "paths", nargs="*", default=["."],
        help="Files or directories to scan (default: current directory)",
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true",
        help="Scan directories recursively",
    )
    parser.add_argument(
        "--type", "-t", dest="link_type",
        help=f"Filter by link type: {', '.join(ALL_LINK_TYPES)} (comma-separated)",
    )
    parser.add_argument(
        "--broken", "-b", action="store_true",
        help="Show only broken links",
    )
    parser.add_argument(
        "--json", "-j", dest="json_output", action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show detailed info (inode, size, full paths)",
    )
    return parser


def main(argv=None):
    """Entry point for links."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    # Parse type filter
    type_filter = None
    if args.link_type:
        requested = [t.strip().lower() for t in args.link_type.split(",")]
        invalid = [t for t in requested if t not in ALL_LINK_TYPES]
        if invalid:
            print(f"Error: Unknown link type(s): {', '.join(invalid)}", file=sys.stderr)
            print(f"Valid types: {', '.join(ALL_LINK_TYPES)}", file=sys.stderr)
            return 1
        type_filter = set(requested)

    # Collect links from all paths
    all_links = []
    for path in args.paths:
        path = canonicalize_path(path)
        if os.path.isdir(path):
            all_links.extend(
                scan_directory(path, recursive=args.recursive,
                               type_filter=type_filter, broken_only=args.broken)
            )
        elif os.path.exists(path) or os.path.islink(path):
            info = detect_link(path)
            if info and _matches_filter(info, type_filter, args.broken):
                all_links.append(info)
        else:
            print(f"Warning: Path not found: {path}", file=sys.stderr)

    # Display
    if args.json_output:
        display_json(all_links)
    else:
        display_table(all_links, verbose=args.verbose)

    return 0


if __name__ == "__main__":
    sys.exit(main())
