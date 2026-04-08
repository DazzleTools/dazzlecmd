"""
Symlink Timestamp Experiment
=============================
Goal: Determine if we can set mtime/ctime/atime on a Windows symlink
independently of its target file.

Steps:
1. Copy a real file (preserving timestamps) to our test area
2. Create a symlink pointing to the copy
3. Record timestamps of both the symlink and the target
4. Attempt to change the symlink's timestamps to a DIFFERENT value
5. Re-read both timestamps to see what actually changed

This tells us:
- Can we set symlink timestamps independently on Windows?
- Does os.utime(symlink, follow_symlinks=False) work?
- Does os.utime(symlink) (default follow_symlinks=True) affect the target?
- Can we use pywin32 / ctypes to set symlink timestamps without following?
"""

import os
import sys
import shutil
import stat
import time
import datetime
from pathlib import Path

# --- Configuration ---
TEST_DIR = Path(__file__).parent / "workspace"

# Source: a real known-docs symlink target
SOURCE_FILE = Path(
    r"C:\code\obsidian-mindmap\local\private\claude"
    r"\2026-01-22__17-54-35__claude-code-shell-snapshot-corruption-windows.md"
)

# The timestamp we'll try to SET on the symlink (clearly different from source)
# Using 2020-06-15 12:00:00 as a very different date
FAKE_TIMESTAMP = datetime.datetime(2020, 6, 15, 12, 0, 0).timestamp()


def stat_report(path, label, follow=True):
    """Report timestamps for a path."""
    try:
        s = os.stat(path, follow_symlinks=follow)
        atime = datetime.datetime.fromtimestamp(s.st_atime)
        mtime = datetime.datetime.fromtimestamp(s.st_mtime)
        ctime = datetime.datetime.fromtimestamp(s.st_ctime)
        print(f"  {label}:")
        print(f"    atime: {atime}")
        print(f"    mtime: {mtime}")
        print(f"    ctime: {ctime}")
        return s
    except Exception as e:
        print(f"  {label}: ERROR - {e}")
        return None


def main():
    print("=" * 70)
    print("SYMLINK TIMESTAMP EXPERIMENT")
    print("=" * 70)

    # --- Step 0: Verify source ---
    if not SOURCE_FILE.exists():
        print(f"\nERROR: Source file not found: {SOURCE_FILE}")
        print("Adjust SOURCE_FILE path and rerun.")
        return 1

    # --- Step 1: Setup test workspace ---
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True)

    # Copy file preserving metadata
    target_copy = TEST_DIR / "original_file.md"
    shutil.copy2(str(SOURCE_FILE), str(target_copy))
    print(f"\nStep 1: Copied source to {target_copy}")
    print(f"  Source: {SOURCE_FILE}")

    print("\n--- BEFORE any symlink operations ---")
    stat_report(target_copy, "Target file (copied)")

    # --- Step 2: Create symlink ---
    symlink_path = TEST_DIR / "test_symlink.md"
    os.symlink(str(target_copy), str(symlink_path))
    print(f"\nStep 2: Created symlink {symlink_path} -> {target_copy}")

    print("\n--- AFTER symlink creation ---")
    stat_report(target_copy, "Target file")
    stat_report(symlink_path, "Symlink (following to target)", follow=True)
    stat_report(symlink_path, "Symlink (lstat, not following)", follow=False)

    # --- Step 3: Try os.utime with follow_symlinks=True (default) ---
    print("\n" + "=" * 70)
    print("EXPERIMENT A: os.utime(symlink, follow_symlinks=True)")
    print(f"  Setting to: {datetime.datetime.fromtimestamp(FAKE_TIMESTAMP)}")
    print("=" * 70)

    # Record target's current mtime before we touch anything
    target_mtime_before = os.stat(target_copy).st_mtime

    try:
        os.utime(str(symlink_path), (FAKE_TIMESTAMP, FAKE_TIMESTAMP))
        print("  Result: SUCCESS (no error)")
    except Exception as e:
        print(f"  Result: FAILED - {e}")

    print("\n--- AFTER os.utime(symlink, follow_symlinks=True) ---")
    stat_report(target_copy, "Target file")
    stat_report(symlink_path, "Symlink (following)", follow=True)
    stat_report(symlink_path, "Symlink (lstat)", follow=False)

    target_mtime_after = os.stat(target_copy).st_mtime
    if target_mtime_after != target_mtime_before:
        print("\n  ** WARNING: Target file mtime WAS CHANGED! **")
        print(f"     Before: {datetime.datetime.fromtimestamp(target_mtime_before)}")
        print(f"     After:  {datetime.datetime.fromtimestamp(target_mtime_after)}")
    else:
        print("\n  Target file mtime unchanged (good).")

    # --- Restore target timestamps ---
    original_stat = os.stat(str(SOURCE_FILE))
    os.utime(str(target_copy), (original_stat.st_atime, original_stat.st_mtime))
    print("\n  (Restored target file timestamps from original)")

    # --- Step 4: Try os.utime with follow_symlinks=False ---
    print("\n" + "=" * 70)
    print("EXPERIMENT B: os.utime(symlink, follow_symlinks=False)")
    print(f"  Setting to: {datetime.datetime.fromtimestamp(FAKE_TIMESTAMP)}")
    print("=" * 70)

    target_mtime_before = os.stat(target_copy).st_mtime

    try:
        os.utime(str(symlink_path), (FAKE_TIMESTAMP, FAKE_TIMESTAMP),
                 follow_symlinks=False)
        print("  Result: SUCCESS (no error)")
    except NotImplementedError:
        print("  Result: NotImplementedError (expected on Windows Python)")
    except Exception as e:
        print(f"  Result: FAILED - {type(e).__name__}: {e}")

    print("\n--- AFTER os.utime(symlink, follow_symlinks=False) ---")
    stat_report(target_copy, "Target file")
    stat_report(symlink_path, "Symlink (following)", follow=True)
    stat_report(symlink_path, "Symlink (lstat)", follow=False)

    target_mtime_after = os.stat(target_copy).st_mtime
    if target_mtime_after != target_mtime_before:
        print("\n  ** WARNING: Target file mtime WAS CHANGED! **")
    else:
        print("\n  Target file mtime unchanged.")

    # --- Step 5: Try ctypes / Win32 API approach ---
    print("\n" + "=" * 70)
    print("EXPERIMENT C: Win32 API via ctypes (SetFileTime on symlink handle)")
    print(f"  Setting to: {datetime.datetime.fromtimestamp(FAKE_TIMESTAMP)}")
    print("=" * 70)

    # Restore target timestamps first
    os.utime(str(target_copy), (original_stat.st_atime, original_stat.st_mtime))
    target_mtime_before = os.stat(target_copy).st_mtime

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        # FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
        # This flag prevents following the symlink
        FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        FILE_WRITE_ATTRIBUTES = 0x100
        OPEN_EXISTING = 3

        # Open the symlink itself (not following it)
        handle = kernel32.CreateFileW(
            str(symlink_path),
            FILE_WRITE_ATTRIBUTES,
            0,  # no sharing
            None,  # no security attrs
            OPEN_EXISTING,
            FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
            None  # no template
        )

        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        if handle == INVALID_HANDLE_VALUE:
            err = ctypes.GetLastError()
            print(f"  CreateFileW failed, error code: {err}")
        else:
            print(f"  CreateFileW succeeded, handle: {handle}")

            # Convert Python timestamp to Windows FILETIME
            # Windows FILETIME: 100-nanosecond intervals since 1601-01-01
            # Python timestamp: seconds since 1970-01-01
            # Offset: 116444736000000000 (100-ns intervals between 1601 and 1970)
            EPOCH_DIFF = 116444736000000000
            ft_value = int(FAKE_TIMESTAMP * 10000000) + EPOCH_DIFF

            class FILETIME(ctypes.Structure):
                _fields_ = [
                    ("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD),
                ]

            ft = FILETIME()
            ft.dwLowDateTime = ft_value & 0xFFFFFFFF
            ft.dwHighDateTime = (ft_value >> 32) & 0xFFFFFFFF

            # SetFileTime(handle, lpCreationTime, lpLastAccessTime, lpLastWriteTime)
            # We set all three to our fake timestamp
            result = kernel32.SetFileTime(
                handle,
                ctypes.byref(ft),  # creation time
                ctypes.byref(ft),  # last access time
                ctypes.byref(ft),  # last write time
            )

            if result:
                print("  SetFileTime succeeded!")
            else:
                err = ctypes.GetLastError()
                print(f"  SetFileTime failed, error code: {err}")

            kernel32.CloseHandle(handle)

        print("\n--- AFTER Win32 SetFileTime on symlink ---")
        stat_report(target_copy, "Target file")
        stat_report(symlink_path, "Symlink (following)", follow=True)
        stat_report(symlink_path, "Symlink (lstat)", follow=False)

        target_mtime_after = os.stat(target_copy).st_mtime
        symlink_mtime = os.lstat(symlink_path).st_mtime
        symlink_dt = datetime.datetime.fromtimestamp(symlink_mtime)
        fake_dt = datetime.datetime.fromtimestamp(FAKE_TIMESTAMP)

        if target_mtime_after != target_mtime_before:
            print("\n  ** WARNING: Target file mtime WAS CHANGED! **")
        else:
            print("\n  Target file mtime unchanged (GOOD - we didn't corrupt the original).")

        if abs(symlink_mtime - FAKE_TIMESTAMP) < 2:  # within 2 seconds
            print(f"  Symlink mtime matches our fake date ({fake_dt}) -- SUCCESS!")
            print("  ** We CAN set symlink timestamps independently on Windows! **")
        else:
            print(f"  Symlink mtime ({symlink_dt}) does NOT match fake date ({fake_dt})")

    except ImportError:
        print("  ctypes not available (unexpected on CPython)")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")

    # --- Step 6: Verify original source file was never touched ---
    print("\n" + "=" * 70)
    print("FINAL VERIFICATION: Original source file integrity")
    print("=" * 70)
    stat_report(SOURCE_FILE, "Original source (should be UNCHANGED)")
    print(f"\n  Original mtime should be: {datetime.datetime.fromtimestamp(original_stat.st_mtime)}")

    current_source_mtime = os.stat(str(SOURCE_FILE)).st_mtime
    if current_source_mtime == original_stat.st_mtime:
        print("  VERIFIED: Original source file was NOT modified.")
    else:
        print("  ** ALERT: Original source file was somehow modified! **")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
    Experiment A (os.utime follow=True):  Follows symlink, changes TARGET
    Experiment B (os.utime follow=False): Expected NotImplementedError on Windows
    Experiment C (Win32 CreateFileW + SetFileTime with FILE_FLAG_OPEN_REPARSE_POINT):
      Opens the symlink itself (not target) and sets its timestamps directly.
      If this works, we can safely set symlink timestamps without affecting targets.
    """)

    print(f"\nTest workspace: {TEST_DIR}")
    print("Review the workspace files to confirm results manually if needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
