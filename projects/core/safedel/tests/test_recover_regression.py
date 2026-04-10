"""Regression tests for safedel recovery edge cases.

Covers bugs found during manual testing that the original roundtrip
tests didn't catch.
"""

import os
import shutil

import pytest

from _store import TrashStore
from _recover import cmd_recover


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


class TestRecoverToNonExistentPath:
    """Regression: --to a path that doesn't exist yet should create it
    as a parent directory and place the recovered item inside it.

    Bug: previously treated the non-existent path as the direct target,
    so a directory's contents spilled into the target instead of being
    wrapped in the original directory name.
    """

    def test_file_to_new_path(self, store, workdir):
        f = workdir / "hello.txt"
        f.write_text("hello")
        store.trash([str(f)])

        new_dest = workdir / "does_not_exist_yet"
        rc = cmd_recover(store, positional_args=["last"], to_path=str(new_dest))
        assert rc == 0
        assert (new_dest / "hello.txt").read_text() == "hello"

    def test_directory_to_new_path(self, store, workdir):
        d = workdir / "mydir"
        d.mkdir()
        (d / "sub").mkdir()
        (d / "sub" / "deep.txt").write_text("deep")
        (d / "top.txt").write_text("top")

        store.trash([str(d)])

        new_dest = workdir / "recover_here"
        rc = cmd_recover(store, positional_args=["last"], to_path=str(new_dest))
        assert rc == 0
        # Directory should be recover_here/mydir/, not recover_here/ directly
        assert (new_dest / "mydir" / "top.txt").read_text() == "top"
        assert (new_dest / "mydir" / "sub" / "deep.txt").read_text() == "deep"

    def test_directory_to_existing_path(self, store, workdir):
        d = workdir / "mydir"
        d.mkdir()
        (d / "file.txt").write_text("content")

        store.trash([str(d)])

        existing_dest = workdir / "already_exists"
        existing_dest.mkdir()
        rc = cmd_recover(store, positional_args=["last"], to_path=str(existing_dest))
        assert rc == 0
        assert (existing_dest / "mydir" / "file.txt").read_text() == "content"


class TestRecoverConflict:
    """Recovery should refuse if the target already exists."""

    def test_refuses_overwrite(self, store, workdir):
        f = workdir / "conflict.txt"
        f.write_text("original")
        store.trash([str(f)])

        # Create a new file at the same path
        f.write_text("new content")

        rc = cmd_recover(store, positional_args=["last"])
        assert rc == 1  # Should fail due to conflict


class TestRecoverMetadataOnly:
    """Metadata-only recovery applies timestamps without touching content."""

    def test_timestamps_applied_content_unchanged(self, store, workdir):
        f = workdir / "meta.txt"
        f.write_text("original content")

        # Record original mtime
        original_stat = os.stat(str(f))

        store.trash([str(f)])

        # Create new file with different content
        import time
        time.sleep(0.1)  # Ensure different timestamp
        f.write_text("different content")
        new_stat_before = os.stat(str(f))

        rc = cmd_recover(
            store, positional_args=["last"], metadata_only=True
        )
        assert rc == 0

        # Content should be unchanged
        assert f.read_text() == "different content"

        # mtime should be restored to the original
        restored_stat = os.stat(str(f))
        assert abs(restored_stat.st_mtime - original_stat.st_mtime) < 2.0

    def test_fails_if_target_missing(self, store, workdir):
        f = workdir / "gone.txt"
        f.write_text("will be deleted")
        store.trash([str(f)])

        # Don't create a new file -- target doesn't exist
        rc = cmd_recover(
            store, positional_args=["last"], metadata_only=True
        )
        assert rc == 1  # Should fail


class TestRecoverDryRun:
    """--dry-run should show what would happen without touching anything."""

    def test_no_changes(self, store, workdir):
        f = workdir / "drytest.txt"
        f.write_text("keep me")
        store.trash([str(f)])

        rc = cmd_recover(
            store, positional_args=["last"], dry_run=True
        )
        assert rc == 0
        # File should NOT be recovered (still in trash)
        assert not f.exists()
        # Trash should still have the entry
        assert len(store.list_entries()) == 1
