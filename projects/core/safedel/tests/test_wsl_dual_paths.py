"""Tests for WSL dual-path storage and recovery.

Tests the _compute_alt_path helper and manifest round-trip with
original_path_alt field. These tests don't require WSL itself -- they
verify the path conversion logic which is platform-aware but
deterministic.
"""

import json
import os
import sys

import pytest

from _store import TrashStore, _compute_alt_path


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


class TestComputeAltPath:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_windows_path_to_wsl(self):
        """C:\\Users\\foo -> /mnt/c/Users/foo"""
        assert _compute_alt_path(r"C:\Users\foo\test.txt") == "/mnt/c/Users/foo/test.txt"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_windows_forward_slashes(self):
        """C:/Users/foo -> /mnt/c/Users/foo"""
        assert _compute_alt_path("C:/Users/foo/test.txt") == "/mnt/c/Users/foo/test.txt"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_other_drives(self):
        """D:\\projects -> /mnt/d/projects"""
        assert _compute_alt_path(r"D:\projects\bar.md") == "/mnt/d/projects/bar.md"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_drive_root(self):
        """C:\\ -> /mnt/c/"""
        result = _compute_alt_path("C:\\")
        assert result is not None and result.startswith("/mnt/c")

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
    def test_wsl_path_to_windows(self):
        """/mnt/c/Users/foo -> C:\\Users\\foo"""
        result = _compute_alt_path("/mnt/c/Users/foo/test.txt")
        assert result is not None
        assert result.startswith("C:")

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
    def test_msys_path_to_windows(self):
        """/c/Users/foo -> C:\\Users\\foo"""
        result = _compute_alt_path("/c/Users/foo/test.txt")
        assert result is not None
        assert result.startswith("C:")


class TestManifestDualPaths:
    def test_alt_path_stored_in_manifest(self, store, workdir):
        """After deletion, manifest should contain original_path_alt."""
        f = workdir / "dual.txt"
        f.write_text("test")

        result = store.trash([str(f)])
        assert result.success

        manifest_path = os.path.join(result.folder_path, "manifest.json")
        with open(manifest_path) as mf:
            manifest = json.load(mf)

        entry = manifest["entries"][0]
        assert "original_path_alt" in entry
        # On Windows with an absolute path, alt should be set
        if sys.platform == "win32" and ":" in str(f):
            assert entry["original_path_alt"] is not None
            assert entry["original_path_alt"].startswith("/mnt/")

    def test_alt_path_loaded_back(self, store, workdir):
        """Loading a TrashFolder should include original_path_alt."""
        f = workdir / "load.txt"
        f.write_text("test")

        store.trash([str(f)])

        folders = store.list_entries()
        assert len(folders) == 1
        entry = folders[0].entries[0]
        assert hasattr(entry, "original_path_alt")


class TestPathParentAccessible:
    def test_existing_parent(self, workdir):
        from _recover import _path_parent_accessible
        f = workdir / "nested" / "file.txt"
        (workdir / "nested").mkdir()
        assert _path_parent_accessible(str(f)) is True

    def test_missing_parent(self):
        from _recover import _path_parent_accessible
        assert _path_parent_accessible("/nonexistent/path/to/file.txt") is False

    def test_none_or_empty(self):
        from _recover import _path_parent_accessible
        assert _path_parent_accessible("") is False
        assert _path_parent_accessible(None) is False
