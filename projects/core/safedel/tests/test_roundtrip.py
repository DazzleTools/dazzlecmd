"""End-to-end roundtrip tests for safedel.

Tests the full cycle: create -> delete -> verify trash -> recover -> verify restored.
"""

import json
import os
import shutil
import tempfile

import pytest

from _store import TrashStore
from _classifier import classify, FileType
from _platform import detect_platform
from _recover import cmd_recover


@pytest.fixture
def store(tmp_path):
    """Create a TrashStore backed by a temp directory."""
    return TrashStore(store_path=str(tmp_path / "trash"))


@pytest.fixture
def workdir(tmp_path):
    """Create a temp working directory for test files."""
    d = tmp_path / "work"
    d.mkdir()
    return d


class TestRegularFile:
    def test_classify(self, workdir):
        f = workdir / "hello.txt"
        f.write_text("hello world")
        c = classify(str(f))
        assert c.file_type == FileType.REGULAR_FILE
        assert c.exists is True

    def test_delete_and_recover(self, store, workdir):
        f = workdir / "hello.txt"
        f.write_text("hello world")

        result = store.trash([str(f)])
        assert result.success is True
        assert not f.exists()

        # Verify manifest
        manifest_path = os.path.join(
            store.store_path, result.folder_name, "manifest.json"
        )
        with open(manifest_path) as mf:
            manifest = json.load(mf)
        assert manifest["entries"][0]["file_type"] == "regular_file"

        # Recover
        recover_dir = workdir / "recovered"
        recover_dir.mkdir()
        rc = cmd_recover(store, positional_args=["last"], to_path=str(recover_dir))
        assert rc == 0
        assert (recover_dir / "hello.txt").read_text() == "hello world"


class TestDirectory:
    def test_classify(self, workdir):
        d = workdir / "mydir"
        d.mkdir()
        (d / "a.txt").write_text("file a")
        c = classify(str(d))
        assert c.file_type == FileType.REGULAR_DIR

    def test_delete_and_recover(self, store, workdir):
        d = workdir / "mydir"
        d.mkdir()
        (d / "a.txt").write_text("file a")
        (d / "b.txt").write_text("file b")

        result = store.trash([str(d)])
        assert result.success
        assert not d.exists()

        recover_dir = workdir / "recovered"
        recover_dir.mkdir()
        rc = cmd_recover(store, positional_args=["last"], to_path=str(recover_dir))
        assert rc == 0
        assert (recover_dir / "mydir" / "a.txt").read_text() == "file a"
        assert (recover_dir / "mydir" / "b.txt").read_text() == "file b"


class TestDryRun:
    def test_no_modifications(self, store, workdir):
        f = workdir / "keep_me.txt"
        f.write_text("don't delete")

        result = store.trash([str(f)], dry_run=True)
        assert result.success
        assert f.exists()
        assert f.read_text() == "don't delete"
        assert len(store.list_entries()) == 0


class TestMultipleFiles:
    def test_all_in_one_folder(self, store, workdir):
        files = []
        for name in ["a.txt", "b.txt", "c.txt"]:
            f = workdir / name
            f.write_text(f"content of {name}")
            files.append(str(f))

        result = store.trash(files)
        assert result.success
        assert len(result.entries) == 3
        for f in files:
            assert not os.path.exists(f)

        folders = store.list_entries()
        assert len(folders) == 1
        assert len(folders[0].entries) == 3


class TestSymlink:
    @pytest.fixture(autouse=True)
    def check_symlink_support(self):
        """Skip symlink tests if we can't create them (need admin on Windows)."""
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "t.txt")
            link = os.path.join(d, "l.txt")
            with open(target, "w") as f:
                f.write("x")
            try:
                os.symlink(target, link)
            except OSError:
                pytest.skip("symlink creation requires admin on Windows")

    def test_classify_symlink(self, workdir):
        target = workdir / "target.txt"
        target.write_text("target content")
        link = workdir / "sym.txt"
        os.symlink(str(target), str(link))

        c = classify(str(link))
        assert c.file_type == FileType.SYMLINK_FILE

    def test_delete_preserves_target(self, store, workdir):
        target = workdir / "target.txt"
        target.write_text("target content")
        link = workdir / "sym.txt"
        os.symlink(str(target), str(link))

        result = store.trash([str(link)])
        assert result.success
        assert not link.exists()
        assert target.read_text() == "target content"

    def test_recover_recreates_symlink(self, store, workdir):
        target = workdir / "target.txt"
        target.write_text("target content")
        link = workdir / "sym.txt"
        os.symlink(str(target), str(link))

        store.trash([str(link)])
        rc = cmd_recover(store, positional_args=["last"])
        assert rc == 0
        assert os.path.islink(str(link))
        assert link.read_text() == "target content"


class TestStatus:
    def test_empty_store(self, store):
        stats = store.get_stats()
        assert stats.total_folders == 0
        assert stats.total_entries == 0

    def test_after_delete(self, store, workdir):
        f = workdir / "test.txt"
        f.write_text("x" * 100)
        store.trash([str(f)])

        stats = store.get_stats()
        assert stats.total_folders == 1
        assert stats.total_entries == 1
        assert stats.total_size_bytes == 100
