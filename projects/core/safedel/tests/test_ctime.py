"""Tests for Windows ctime (creation time) restoration.

Windows-only. Uses pywin32 to set and restore creation timestamps.
Skips on non-Windows platforms or if pywin32 is not installed.
"""

import datetime
import os
import sys
import tempfile

import pytest

from _store import TrashStore
from _recover import cmd_recover

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows ctime tests are Windows-only"
)


def _pywin32_available():
    try:
        import win32file  # noqa: F401
        import pywintypes  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark_pywin32 = pytest.mark.skipif(
    not _pywin32_available(), reason="pywin32 not installed"
)


@pytest.fixture
def store(tmp_path):
    return TrashStore(
        store_path=str(tmp_path / "trash"),
        registry_path=str(tmp_path / "volumes.json"),
    )


@pytest.fixture
def workdir(tmp_path):
    d = tmp_path / "work"
    d.mkdir()
    return d


@pytestmark_pywin32
def test_is_win32_available():
    """Verify pywin32 is detected."""
    from preservelib.metadata import is_win32_available
    assert is_win32_available() is True


@pytestmark_pywin32
def test_restore_creation_time_file(workdir):
    """Directly test restore_windows_creation_time on a file."""
    from preservelib.metadata import restore_windows_creation_time

    f = workdir / "ctime_test.txt"
    f.write_text("hello")

    target_dt = datetime.datetime(2024, 6, 15, 10, 30, 0)
    result = restore_windows_creation_time(str(f), target_dt.timestamp())
    assert result is True

    # Verify ctime was set
    restored = datetime.datetime.fromtimestamp(f.stat().st_ctime)
    # Allow 2 second tolerance for filesystem precision
    assert abs((restored - target_dt).total_seconds()) < 2


@pytestmark_pywin32
def test_restore_creation_time_directory(workdir):
    """restore_windows_creation_time should work on directories too."""
    from preservelib.metadata import restore_windows_creation_time

    d = workdir / "ctime_dir"
    d.mkdir()

    target_dt = datetime.datetime(2023, 3, 10, 14, 0, 0)
    result = restore_windows_creation_time(str(d), target_dt.timestamp())
    assert result is True

    restored = datetime.datetime.fromtimestamp(d.stat().st_ctime)
    assert abs((restored - target_dt).total_seconds()) < 2


@pytestmark_pywin32
def test_ctime_preserved_through_roundtrip(store, workdir):
    """End-to-end: create file with past ctime, delete, recover, verify ctime."""
    from preservelib.metadata import restore_windows_creation_time

    f = workdir / "roundtrip.txt"
    f.write_text("original content")

    # Set ctime to a specific past time
    target_dt = datetime.datetime(2025, 1, 15, 12, 0, 0)
    target_epoch = target_dt.timestamp()
    restore_windows_creation_time(str(f), target_epoch)
    os.utime(str(f), (target_epoch, target_epoch))

    original_ctime = f.stat().st_ctime

    # Delete and recover
    store.trash([str(f)])
    assert not f.exists()

    rc = cmd_recover(store, positional_args=["last"])
    assert rc == 0

    # Verify ctime was restored
    assert f.exists()
    recovered_ctime = f.stat().st_ctime
    assert abs(recovered_ctime - original_ctime) < 2, (
        f"ctime not preserved: original={original_ctime}, "
        f"recovered={recovered_ctime}"
    )


@pytestmark_pywin32
def test_ctime_metadata_only_recovery(store, workdir):
    """Metadata-only recovery should apply ctime to an existing file."""
    from preservelib.metadata import restore_windows_creation_time

    f = workdir / "meta_ctime.txt"
    f.write_text("original")

    target_dt = datetime.datetime(2024, 8, 20, 9, 0, 0)
    restore_windows_creation_time(str(f), target_dt.timestamp())
    os.utime(str(f), (target_dt.timestamp(), target_dt.timestamp()))

    store.trash([str(f)])

    # Create new file with different content at same path
    f.write_text("different content")
    new_ctime = f.stat().st_ctime

    # Metadata-only recovery
    rc = cmd_recover(store, positional_args=["last"], metadata_only=True)
    assert rc == 0

    # Content unchanged but ctime restored
    assert f.read_text() == "different content"
    restored_ctime = f.stat().st_ctime
    assert abs(restored_ctime - target_dt.timestamp()) < 2


def test_restore_on_non_windows_returns_false(monkeypatch):
    """On non-Windows, restore_windows_creation_time should return False."""
    from preservelib.metadata import restore_windows_creation_time
    import platform as pf

    monkeypatch.setattr(pf, "system", lambda: "Linux")
    result = restore_windows_creation_time("/tmp/whatever", 12345.0)
    assert result is False
