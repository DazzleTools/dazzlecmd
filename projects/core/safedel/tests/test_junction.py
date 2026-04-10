"""Tests for junction handling in safedel.

Junctions are Windows-only. On non-Windows platforms these tests are skipped.
On Windows without admin, symlink tests are skipped but junction tests run
(junctions don't require admin).
"""

import os
import subprocess
import sys

import pytest

from _store import TrashStore
from _classifier import classify, FileType
from _recover import cmd_recover


pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Junctions are Windows-only"
)


def _create_junction(link_path: str, target_path: str):
    """Create a junction using PowerShell."""
    result = subprocess.run(
        [
            "powershell", "-Command",
            f"New-Item -ItemType Junction -Path '{link_path}' -Target '{target_path}'"
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"Cannot create junction: {result.stderr.strip()}")


@pytest.fixture
def store(tmp_path):
    return TrashStore(
        store_path=str(tmp_path / "trash"),
        registry_path=str(tmp_path / "volumes.json"),
    )


@pytest.fixture
def junction_fixture(tmp_path):
    """Create a target directory and a junction pointing to it."""
    target_dir = tmp_path / "real_dir"
    target_dir.mkdir()
    (target_dir / "data.txt").write_text("real data")
    (target_dir / "sub").mkdir()
    (target_dir / "sub" / "nested.txt").write_text("nested")

    junction_path = tmp_path / "junc_link"
    _create_junction(str(junction_path), str(target_dir))

    return target_dir, junction_path


class TestJunctionClassification:
    def test_detected_as_junction(self, junction_fixture):
        _, junction_path = junction_fixture
        c = classify(str(junction_path))
        assert c.file_type == FileType.JUNCTION

    def test_delete_method_is_rmdir(self, junction_fixture):
        _, junction_path = junction_fixture
        c = classify(str(junction_path))
        assert c.delete_method.value == "os.rmdir"

    def test_link_target_recorded(self, junction_fixture):
        target_dir, junction_path = junction_fixture
        c = classify(str(junction_path))
        assert c.link_target is not None
        # Target should resolve to the real dir
        assert os.path.normcase(c.link_target) == os.path.normcase(str(target_dir))


class TestJunctionDelete:
    def test_junction_removed_target_survives(self, store, junction_fixture):
        target_dir, junction_path = junction_fixture

        result = store.trash([str(junction_path)])
        assert result.success

        # Junction is gone
        assert not junction_path.exists()

        # Target directory and all contents survive
        assert target_dir.exists()
        assert (target_dir / "data.txt").read_text() == "real data"
        assert (target_dir / "sub" / "nested.txt").read_text() == "nested"

    def test_manifest_records_junction_metadata(self, store, junction_fixture):
        _, junction_path = junction_fixture

        result = store.trash([str(junction_path)])
        entry = result.entries[0]
        assert entry.file_type == "junction"
        assert entry.link_target is not None
        assert entry.content_preserved is False  # Junctions are metadata-only


class TestJunctionRecover:
    def test_recover_recreates_junction(self, store, junction_fixture):
        target_dir, junction_path = junction_fixture

        store.trash([str(junction_path)])
        assert not junction_path.exists()

        rc = cmd_recover(store, positional_args=["last"])
        assert rc == 0

        # Junction is back
        assert junction_path.exists()
        assert os.path.isdir(str(junction_path))

        # Content accessible through junction
        assert (junction_path / "data.txt").read_text() == "real data"
        assert (junction_path / "sub" / "nested.txt").read_text() == "nested"

    def test_recover_to_alternate_path(self, store, junction_fixture, tmp_path):
        target_dir, junction_path = junction_fixture

        store.trash([str(junction_path)])

        recover_dir = tmp_path / "recovered"
        rc = cmd_recover(
            store, positional_args=["last"], to_path=str(recover_dir)
        )
        assert rc == 0

        recovered_junction = recover_dir / junction_path.name
        assert recovered_junction.exists()
        assert (recovered_junction / "data.txt").read_text() == "real data"
