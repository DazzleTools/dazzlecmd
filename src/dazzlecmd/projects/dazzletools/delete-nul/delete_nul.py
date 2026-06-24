#!/usr/bin/env python3
"""
Delete Windows NUL device file that gets accidentally created.

This script handles the special case where a file named "nul" gets created
in a directory. On Windows, NUL is a reserved device name (like CON, PRN, AUX)
and such files can be difficult to delete through normal means.

This typically happens when a script accidentally redirects output to "nul"
instead of "NUL" or "/dev/null".

Usage:
    python delete_nul.py [options] [path_to_nul_file]

    Options:
        -y, --yes        Skip confirmation prompts and delete automatically
        -r, --recursive  Scan subdirectories recursively
        -a, --all        Scan for all reserved Windows device names, not just 'nul'

    If no path is provided, scans current directory for files named 'nul' or 'NUL'.
    Shows file info and contents before prompting for deletion (unless -y is used).

    Reserved Windows device names: CON, PRN, AUX, NUL, COM1-9, LPT1-9
"""

import ctypes
from ctypes import wintypes
import sys
import os
import stat
import subprocess
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# Windows reserved device names that can't be used as filenames
# but sometimes get created accidentally
RESERVED_NAMES = {
    'con', 'prn', 'aux', 'nul',
    'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
    'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
}


def format_size(size_bytes):
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}K"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}M"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f}G"


def format_mode(mode):
    """Format file mode in ls-style (e.g., -rw-r--r--)."""
    is_dir = 'd' if stat.S_ISDIR(mode) else '-'
    perms = ''
    for who in ['USR', 'GRP', 'OTH']:
        for what in ['R', 'W', 'X']:
            bit = getattr(stat, f'S_I{what}{who}', 0)
            perms += what.lower() if mode & bit else '-'
    return is_dir + perms


def filetime_to_datetime(filetime):
    """Convert Windows FILETIME to Python datetime."""
    # FILETIME is 100-nanosecond intervals since January 1, 1601
    timestamp = (filetime.dwHighDateTime << 32) + filetime.dwLowDateTime
    # Convert to Unix timestamp (seconds since 1970)
    # Difference between 1601 and 1970 in 100-nanosecond intervals
    EPOCH_DIFF = 116444736000000000
    if timestamp > EPOCH_DIFF:
        unix_timestamp = (timestamp - EPOCH_DIFF) / 10000000
        return datetime.fromtimestamp(unix_timestamp)
    return datetime(1970, 1, 1)


def get_file_info(file_path):
    """Get ls-style file info string using Windows API for reserved names."""
    file_path = Path(file_path)

    # Use Windows API to get file attributes since os.stat() fails on reserved names
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    class WIN32_FILE_ATTRIBUTE_DATA(ctypes.Structure):
        _fields_ = [
            ('dwFileAttributes', wintypes.DWORD),
            ('ftCreationTime', wintypes.FILETIME),
            ('ftLastAccessTime', wintypes.FILETIME),
            ('ftLastWriteTime', wintypes.FILETIME),
            ('nFileSizeHigh', wintypes.DWORD),
            ('nFileSizeLow', wintypes.DWORD),
        ]

    GetFileAttributesExW = kernel32.GetFileAttributesExW
    GetFileAttributesExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    GetFileAttributesExW.restype = wintypes.BOOL

    GetFileExInfoStandard = 0
    FILE_ATTRIBUTE_DIRECTORY = 0x10
    FILE_ATTRIBUTE_READONLY = 0x1

    # Use extended path format for reserved names
    extended_path = f'\\\\?\\{file_path.absolute()}'

    file_data = WIN32_FILE_ATTRIBUTE_DATA()
    if not GetFileAttributesExW(extended_path, GetFileExInfoStandard, ctypes.byref(file_data)):
        # Fall back to os.stat for regular files
        try:
            st = os.stat(file_path)
            mode_str = format_mode(st.st_mode)
            size_str = format_size(st.st_size)
            mtime = datetime.fromtimestamp(st.st_mtime)
            time_str = mtime.strftime("%b %d %H:%M")
            return {
                'mode': mode_str,
                'size': st.st_size,
                'size_str': size_str,
                'mtime': time_str,
                'is_dir': stat.S_ISDIR(st.st_mode),
                'display': f"{mode_str}  {size_str:>8}  {time_str}  {file_path.name}"
            }
        except OSError:
            return None

    # Parse Windows attributes
    is_dir = bool(file_data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
    is_readonly = bool(file_data.dwFileAttributes & FILE_ATTRIBUTE_READONLY)
    size = (file_data.nFileSizeHigh << 32) + file_data.nFileSizeLow
    mtime = filetime_to_datetime(file_data.ftLastWriteTime)

    # Build a simple mode string (Windows doesn't have Unix permissions)
    if is_dir:
        mode_str = 'drwxr-xr-x'
    elif is_readonly:
        mode_str = '-r--r--r--'
    else:
        mode_str = '-rw-rw-rw-'

    size_str = format_size(size)
    time_str = mtime.strftime("%b %d %H:%M")

    return {
        'mode': mode_str,
        'size': size,
        'size_str': size_str,
        'mtime': time_str,
        'is_dir': is_dir,
        'display': f"{mode_str}  {size_str:>8}  {time_str}  {file_path.name}"
    }


def show_file_contents(file_path, max_lines=50):
    """Show file contents using a pager if available, otherwise print directly."""
    try:
        # Try to read the file contents
        extended_path = f'\\\\?\\{file_path.absolute()}'

        # Use Windows API to open and read
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x00000001
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_HANDLE_VALUE = -1

        CreateFileW = kernel32.CreateFileW
        CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        CreateFileW.restype = wintypes.HANDLE

        ReadFile = kernel32.ReadFile
        ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        ReadFile.restype = wintypes.BOOL

        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL

        handle = CreateFileW(extended_path, GENERIC_READ, FILE_SHARE_READ,
                            None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)

        if handle == INVALID_HANDLE_VALUE:
            print("  (Could not read file contents)")
            return

        try:
            # Read up to 64KB
            buffer_size = 65536
            buffer = ctypes.create_string_buffer(buffer_size)
            bytes_read = wintypes.DWORD()

            if ReadFile(handle, buffer, buffer_size, ctypes.byref(bytes_read), None):
                content = buffer.raw[:bytes_read.value]
                if not content:
                    print("  (File is empty)")
                    return

                # Try to decode as text
                try:
                    text = content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        text = content.decode('latin-1')
                    except:
                        print(f"  (Binary content: {len(content)} bytes)")
                        # Show hex preview
                        hex_preview = ' '.join(f'{b:02x}' for b in content[:64])
                        print(f"  Hex: {hex_preview}...")
                        return

                lines = text.splitlines()

                # Check if 'less' or similar pager is available
                less_path = shutil.which('less')
                more_path = shutil.which('more')

                if len(lines) > max_lines and (less_path or more_path):
                    # Use pager for large content
                    pager = less_path or more_path
                    print(f"\n  Showing contents with pager ({len(lines)} lines)...")
                    print("  Press 'q' to exit pager.\n")
                    try:
                        proc = subprocess.Popen([pager], stdin=subprocess.PIPE, text=True)
                        proc.communicate(input=text)
                    except Exception as e:
                        # Fall back to direct printing
                        print(f"  (Pager failed, showing first {max_lines} lines)")
                        for i, line in enumerate(lines[:max_lines]):
                            print(f"  {i+1:4}: {line}")
                        if len(lines) > max_lines:
                            print(f"  ... ({len(lines) - max_lines} more lines)")
                else:
                    # Print directly
                    print("\n  --- File Contents ---")
                    for i, line in enumerate(lines[:max_lines]):
                        print(f"  {i+1:4}: {line}")
                    if len(lines) > max_lines:
                        print(f"  ... ({len(lines) - max_lines} more lines)")
                    print("  --- End Contents ---\n")
            else:
                print("  (Could not read file contents)")
        finally:
            CloseHandle(handle)

    except Exception as e:
        print(f"  (Error reading file: {e})")


def find_reserved_files(directory=None, recursive=False, scan_all_reserved=False):
    """
    Find files with reserved Windows device names in the specified directory.

    Args:
        directory: Directory to search (defaults to current directory)
        recursive: If True, search subdirectories recursively
        scan_all_reserved: If True, search for all reserved names; if False, only 'nul'

    Returns list of Path objects for found files.
    """
    if directory is None:
        directory = Path.cwd()
    else:
        directory = Path(directory)

    # Determine which names to search for
    if scan_all_reserved:
        target_names = RESERVED_NAMES
    else:
        target_names = {'nul'}

    found = []

    # Use Windows API to enumerate files since Python's Path.iterdir()
    # may have issues with reserved names
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    class WIN32_FIND_DATAW(ctypes.Structure):
        _fields_ = [
            ('dwFileAttributes', wintypes.DWORD),
            ('ftCreationTime', wintypes.FILETIME),
            ('ftLastAccessTime', wintypes.FILETIME),
            ('ftLastWriteTime', wintypes.FILETIME),
            ('nFileSizeHigh', wintypes.DWORD),
            ('nFileSizeLow', wintypes.DWORD),
            ('dwReserved0', wintypes.DWORD),
            ('dwReserved1', wintypes.DWORD),
            ('cFileName', wintypes.WCHAR * 260),
            ('cAlternateFileName', wintypes.WCHAR * 14),
        ]

    FILE_ATTRIBUTE_DIRECTORY = 0x10

    FindFirstFileW = kernel32.FindFirstFileW
    FindFirstFileW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(WIN32_FIND_DATAW)]
    FindFirstFileW.restype = wintypes.HANDLE

    FindNextFileW = kernel32.FindNextFileW
    FindNextFileW.argtypes = [wintypes.HANDLE, ctypes.POINTER(WIN32_FIND_DATAW)]
    FindNextFileW.restype = wintypes.BOOL

    FindClose = kernel32.FindClose
    FindClose.argtypes = [wintypes.HANDLE]
    FindClose.restype = wintypes.BOOL

    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    def scan_directory(dir_path):
        """Scan a single directory for reserved files."""
        results = []
        subdirs = []

        # Search for all files
        search_path = f'\\\\?\\{dir_path.absolute()}\\*'
        find_data = WIN32_FIND_DATAW()

        handle = FindFirstFileW(search_path, ctypes.byref(find_data))
        if handle == INVALID_HANDLE_VALUE:
            # Fall back to standard method
            try:
                for item in dir_path.iterdir():
                    if item.name.lower() in target_names:
                        results.append(item)
                    elif recursive and item.is_dir():
                        subdirs.append(item)
            except (PermissionError, OSError):
                pass
            return results, subdirs

        try:
            while True:
                filename = find_data.cFileName
                is_dir = bool(find_data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)

                # Skip . and ..
                if filename not in ('.', '..'):
                    if filename.lower() in target_names:
                        results.append(dir_path / filename)
                    elif recursive and is_dir:
                        subdirs.append(dir_path / filename)

                if not FindNextFileW(handle, ctypes.byref(find_data)):
                    break
        finally:
            FindClose(handle)

        return results, subdirs

    # Start with the initial directory
    dirs_to_scan = [directory]

    while dirs_to_scan:
        current_dir = dirs_to_scan.pop(0)
        try:
            files, subdirs = scan_directory(current_dir)
            found.extend(files)
            if recursive:
                dirs_to_scan.extend(subdirs)
        except (PermissionError, OSError) as e:
            # Skip directories we can't access
            print(f"  Warning: Cannot access {current_dir}: {e}")

    return found


# Alias for backward compatibility
def find_nul_files(directory=None):
    """Find files named 'nul' or 'NUL' in the specified directory."""
    return find_reserved_files(directory, recursive=False, scan_all_reserved=False)


def delete_nul_file(file_path, confirm=True):
    """
    Delete a NUL device file using Windows API.

    Args:
        file_path: Path to the nul file.
        confirm: If True, prompt user before deletion.

    Returns:
        bool: True if successful, False otherwise
    """
    file_path = Path(file_path)

    # Check if running on Windows
    if os.name != 'nt':
        print("This script is for Windows only")
        return False

    # Get and display file info
    info = get_file_info(file_path)
    if info is None:
        print(f"Could not get info for: {file_path}")
        return False

    print(f"\nFound: {info['display']}")

    # Check if it's a directory
    if info['is_dir']:
        print(f"  WARNING: '{file_path}' is a DIRECTORY, not a file.")
        print("  This script does not delete directories.")
        return False

    # If file has content, show it
    if info['size'] > 0:
        print(f"\n  File contains {info['size']} bytes of data!")
        show_file_contents(file_path)
    else:
        print("  (File is empty)")

    # Prompt for confirmation
    if confirm:
        while True:
            response = input(f"\nDelete '{file_path.name}'? [y/N]: ").strip().lower()
            if response in ('y', 'yes'):
                break
            elif response in ('n', 'no', ''):
                print("Skipped.")
                return False
            else:
                print("Please enter 'y' or 'n'")

    # Use Windows API to delete the special file
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    DeleteFileW = kernel32.DeleteFileW
    DeleteFileW.argtypes = [wintypes.LPCWSTR]
    DeleteFileW.restype = wintypes.BOOL

    # Convert to extended path format to bypass name checking
    extended_path = f'\\\\?\\{file_path.absolute()}'

    print(f"Attempting to delete: {file_path}")

    if DeleteFileW(extended_path):
        print("Successfully deleted nul file")
        return True
    else:
        error = ctypes.get_last_error()
        print(f"Failed to delete nul file. Error code: {error}")

        # Try alternative approach using cmd
        cmd_path = f'"\\\\?\\{file_path.absolute()}"'
        result = subprocess.run(['cmd', '/c', 'del', cmd_path],
                              capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            print("Deleted using cmd")
            return True
        else:
            print(f"Could not delete the file: {result.stderr}")
            return False


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description='Delete Windows reserved device name files that get accidentally created.',
        epilog='If no path is provided, scans current directory for reserved name files.'
    )
    parser.add_argument(
        'path',
        nargs='?',
        help='Path to the file to delete (optional)'
    )
    parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompts and delete automatically'
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Scan subdirectories recursively'
    )
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        dest='all_reserved',
        help='Scan for all reserved Windows device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)'
    )

    args = parser.parse_args()
    confirm = not args.yes

    if args.path:
        # Path provided as argument - delete directly
        success = delete_nul_file(args.path, confirm=confirm)
        sys.exit(0 if success else 1)
    else:
        # No argument - scan for reserved name files
        if args.all_reserved:
            names_desc = "reserved Windows device name"
            names_list = ", ".join(sorted(RESERVED_NAMES)).upper()
        else:
            names_desc = "'nul' or 'NUL'"
            names_list = None

        mode_desc = "recursively" if args.recursive else "in current directory"
        print(f"Scanning {mode_desc} for {names_desc} files...")
        print(f"Directory: {Path.cwd()}")
        if names_list:
            print(f"Looking for: {names_list}")
        print()

        found_files = find_reserved_files(
            recursive=args.recursive,
            scan_all_reserved=args.all_reserved
        )

        if not found_files:
            print(f"No {names_desc} files found.")
            sys.exit(0)

        print(f"Found {len(found_files)} file(s):\n")

        deleted = 0
        for file_path in found_files:
            if delete_nul_file(file_path, confirm=confirm):
                deleted += 1
            print()  # Blank line between files

        print(f"\nSummary: Deleted {deleted} of {len(found_files)} file(s)")
        sys.exit(0 if deleted == len(found_files) else 1)


if __name__ == '__main__':
    main()