"""Golden invariant tests for safedel behavior.

These tests capture the END-STATE properties that safedel guarantees.
They are the invariants that must NOT change when filekit v0.3.x lands
and safedel migrates to the consolidated API.

Unlike text-based golden outputs (which drift with timestamps and paths),
invariant tests assert behavioral properties that are stable across
implementation changes. Run this suite before and after the filekit
consolidation -- results must be identical.

If any test here fails after the v0.3.x migration, it indicates a
regression that must be fixed before shipping.
"""

import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from _store import TrashStore
from _classifier import classify, FileType
from _recover import cmd_recover, cmd_list, cmd_status
from _platform import detect_platform


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


# ---------------------------------------------------------------------------
# Invariant 1: Classification determinism
# ---------------------------------------------------------------------------


class TestClassificationInvariants:
    """Classification of a file type must be deterministic and stable."""

    def test_regular_file_classifies_as_regular_file(self, workdir):
        f = workdir / "plain.txt"
        f.write_text("x")
        c = classify(str(f))
        assert c.file_type == FileType.REGULAR_FILE
        assert c.delete_method.value == "os.unlink"
        assert c.content_preservable is True

    def test_empty_dir_classifies_as_empty_dir(self, workdir):
        d = workdir / "empty"
        d.mkdir()
        c = classify(str(d))
        assert c.file_type == FileType.EMPTY_DIR
        assert c.delete_method.value == "os.rmdir"

    def test_nonempty_dir_classifies_as_regular_dir(self, workdir):
        d = workdir / "full"
        d.mkdir()
        (d / "a.txt").write_text("x")
        c = classify(str(d))
        assert c.file_type == FileType.REGULAR_DIR
        assert c.delete_method.value == "shutil.rmtree"


# ---------------------------------------------------------------------------
# Invariant 2: Full roundtrip preserves content and metadata
# ---------------------------------------------------------------------------


class TestRoundtripInvariants:
    """A file that goes through delete -> recover must match its original."""

    def test_file_content_preserved(self, store, workdir):
        f = workdir / "test.txt"
        f.write_text("important content")

        store.trash([str(f)])
        assert not f.exists()

        rc = cmd_recover(store, positional_args=["last"])
        assert rc == 0
        assert f.read_text() == "important content"

    def test_file_mtime_preserved(self, store, workdir):
        f = workdir / "test.txt"
        f.write_text("x")

        # Set a specific mtime
        past = (datetime.datetime.now() - datetime.timedelta(days=30)).timestamp()
        os.utime(str(f), (past, past))

        original_mtime = f.stat().st_mtime

        store.trash([str(f)])
        cmd_recover(store, positional_args=["last"])

        restored_mtime = f.stat().st_mtime
        assert abs(restored_mtime - original_mtime) < 2.0, (
            f"mtime drift: {original_mtime} -> {restored_mtime}"
        )

    def test_directory_structure_preserved(self, store, workdir):
        d = workdir / "tree"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "sub").mkdir()
        (d / "sub" / "b.txt").write_text("b")

        store.trash([str(d)])
        assert not d.exists()

        cmd_recover(store, positional_args=["last"])

        assert d.is_dir()
        assert (d / "a.txt").read_text() == "a"
        assert (d / "sub" / "b.txt").read_text() == "b"


# ---------------------------------------------------------------------------
# Invariant 3: Manifest schema stability
# ---------------------------------------------------------------------------


class TestManifestInvariants:
    """The manifest.json schema must remain stable across refactors."""

    REQUIRED_TOP_LEVEL_KEYS = {
        "version", "safedel_version", "deleted_at", "folder_name",
        "platform", "entries",
    }

    REQUIRED_ENTRY_KEYS = {
        "original_path", "original_name", "file_type", "link_target",
        "link_broken", "link_count", "is_dir", "content_preserved",
        "content_path", "delete_method", "stat", "metadata", "warnings",
    }

    REQUIRED_PLATFORM_KEYS = {
        "system", "platform", "is_wsl", "python_version", "hostname",
    }

    def test_manifest_has_all_required_top_level_keys(self, store, workdir):
        f = workdir / "x.txt"
        f.write_text("x")
        result = store.trash([str(f)])

        manifest_path = os.path.join(result.folder_path, "manifest.json")
        with open(manifest_path) as mf:
            manifest = json.load(mf)

        for key in self.REQUIRED_TOP_LEVEL_KEYS:
            assert key in manifest, f"Missing required key: {key}"

    def test_manifest_entry_has_all_required_keys(self, store, workdir):
        f = workdir / "x.txt"
        f.write_text("x")
        result = store.trash([str(f)])

        manifest_path = os.path.join(result.folder_path, "manifest.json")
        with open(manifest_path) as mf:
            manifest = json.load(mf)

        assert len(manifest["entries"]) == 1
        entry = manifest["entries"][0]
        for key in self.REQUIRED_ENTRY_KEYS:
            assert key in entry, f"Missing required entry key: {key}"

    def test_manifest_platform_has_all_required_keys(self, store, workdir):
        f = workdir / "x.txt"
        f.write_text("x")
        result = store.trash([str(f)])

        manifest_path = os.path.join(result.folder_path, "manifest.json")
        with open(manifest_path) as mf:
            manifest = json.load(mf)

        platform = manifest["platform"]
        for key in self.REQUIRED_PLATFORM_KEYS:
            assert key in platform, f"Missing required platform key: {key}"


# ---------------------------------------------------------------------------
# Invariant 4: Folder naming convention
# ---------------------------------------------------------------------------


class TestFolderNamingInvariants:
    """Trash folders must use the YYYY-MM-DD__hh-mm-ss format."""

    def test_folder_name_matches_pattern(self, store, workdir):
        import re
        f = workdir / "x.txt"
        f.write_text("x")
        result = store.trash([str(f)])

        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2}(_\d{3})?$")
        assert pattern.match(result.folder_name), (
            f"Folder name {result.folder_name!r} does not match expected pattern"
        )

    def test_folder_name_is_parseable_as_datetime(self, store, workdir):
        f = workdir / "x.txt"
        f.write_text("x")
        result = store.trash([str(f)])

        # First 19 chars should be parseable
        dt_str = result.folder_name[:19]
        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d__%H-%M-%S")
        # Should be recent (within the last minute)
        age = datetime.datetime.now() - dt
        assert age.total_seconds() < 60


# ---------------------------------------------------------------------------
# Invariant 5: Dry-run leaves filesystem untouched
# ---------------------------------------------------------------------------


class TestDryRunInvariants:
    def test_dry_run_no_file_changes(self, store, workdir):
        f = workdir / "keep.txt"
        f.write_text("keep me")

        store.trash([str(f)], dry_run=True)

        # File still exists with original content
        assert f.exists()
        assert f.read_text() == "keep me"

    def test_dry_run_no_trash_entries(self, store, workdir):
        f = workdir / "keep.txt"
        f.write_text("keep me")

        store.trash([str(f)], dry_run=True)

        folders = store.list_entries()
        assert len(folders) == 0


# ---------------------------------------------------------------------------
# Invariant 6: List and status consistency
# ---------------------------------------------------------------------------


class TestListStatusInvariants:
    def test_list_count_matches_stats(self, store, workdir):
        for i in range(3):
            f = workdir / f"file_{i}.txt"
            f.write_text(f"content {i}")
            store.trash([str(f)])

        folders = store.list_entries()
        stats = store.get_stats()

        assert len(folders) == 3
        assert stats.total_folders == 3
        assert stats.total_entries == 3

    def test_empty_store_reports_zero(self, store):
        folders = store.list_entries()
        stats = store.get_stats()

        assert len(folders) == 0
        assert stats.total_folders == 0
        assert stats.total_entries == 0
        assert stats.total_size_bytes == 0


# ---------------------------------------------------------------------------
# Invariant 7: Platform detection stability
# ---------------------------------------------------------------------------


class TestPlatformInvariants:
    def test_detect_platform_returns_platform_info(self):
        info = detect_platform()
        assert info.system in ("Windows", "Linux", "Darwin")
        assert info.platform in ("win32", "linux", "darwin")
        assert info.python_version
        assert info.hostname

    def test_wsl_detection_consistent(self):
        """is_wsl should be False on native Windows, consistent otherwise."""
        info = detect_platform()
        if info.platform == "win32":
            assert info.is_wsl is False
