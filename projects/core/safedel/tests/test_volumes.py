"""Tests for safedel _volumes module.

Tests volume detection, per-volume trash path resolution, volume registry,
and multi-store integration.
"""

import json
import os
import sys
import tempfile

import pytest

from _volumes import (
    VolumeInfo,
    VolumeTrashInfo,
    get_volume_info,
    get_per_volume_trash_path,
    is_same_volume,
    load_registry,
    save_registry,
    register_volume,
    update_registry_reachability,
    get_all_trash_paths,
    resolve_trash_store,
)
from _store import TrashStore


class TestVolumeDetection:
    def test_local_drive(self):
        """C: should be detected as a local drive."""
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        v = get_volume_info("C:/")
        assert v.device_id > 0
        assert not v.is_network
        assert v.volume_serial is not None
        assert v.filesystem in ("NTFS", "ReFS")

    def test_temp_same_as_c(self):
        """TEMP is on C: -- should have the same device_id."""
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        v_c = get_volume_info("C:/")
        v_temp = get_volume_info(os.environ.get("TEMP", "C:/"))
        assert v_c.device_id == v_temp.device_id

    def test_is_same_volume(self):
        """Two paths on the same drive should be same volume."""
        with tempfile.TemporaryDirectory() as d:
            f1 = os.path.join(d, "a.txt")
            f2 = os.path.join(d, "b.txt")
            open(f1, "w").close()
            open(f2, "w").close()
            assert is_same_volume(f1, f2) is True


class TestPerVolumeTrashPath:
    def test_local_drive_gets_path(self):
        """A local drive should get a per-volume trash path."""
        v = VolumeInfo(
            device_id=1234,
            mount_point="C:" + os.sep,
            is_network=False,
            is_subst=False,
            is_readonly=False,
        )
        path = get_per_volume_trash_path(v)
        # On Windows with a Users dir, should get a path
        if sys.platform == "win32":
            assert path is not None
            assert ".safedel-trash" in path

    def test_network_drive_returns_none(self):
        """Network drives should not get per-volume trash."""
        v = VolumeInfo(device_id=1234, mount_point="Z:" + os.sep, is_network=True)
        assert get_per_volume_trash_path(v) is None

    def test_readonly_returns_none(self):
        """Read-only volumes should not get per-volume trash."""
        v = VolumeInfo(device_id=1234, mount_point="E:" + os.sep, is_readonly=True)
        assert get_per_volume_trash_path(v) is None

    def test_subst_returns_none(self):
        """SUBST'd drives should not get per-volume trash."""
        v = VolumeInfo(device_id=1234, mount_point="Z:" + os.sep, is_subst=True)
        assert get_per_volume_trash_path(v) is None


class TestVolumeRegistry:
    def test_empty_registry(self, tmp_path):
        reg_path = str(tmp_path / "volumes.json")
        assert load_registry(reg_path) == {}

    def test_save_and_load(self, tmp_path):
        reg_path = str(tmp_path / "volumes.json")
        v = VolumeInfo(
            device_id=1234, mount_point="C:" + os.sep,
            volume_serial="0xdeadbeef", volume_name="TestVol",
        )
        register_volume(v, "C:/Users/test/.safedel-trash", reg_path)

        registry = load_registry(reg_path)
        assert "0xdeadbeef" in registry
        assert registry["0xdeadbeef"].trash_path == "C:/Users/test/.safedel-trash"
        assert registry["0xdeadbeef"].volume_name == "TestVol"

    def test_reachability_update(self, tmp_path):
        reg_path = str(tmp_path / "volumes.json")
        trash_dir = str(tmp_path / "trash")
        os.makedirs(trash_dir)

        v = VolumeInfo(
            device_id=1234, mount_point="C:" + os.sep,
            volume_serial="0x12345678",
        )
        register_volume(v, trash_dir, reg_path)

        registry = update_registry_reachability(reg_path)
        assert registry["0x12345678"].is_reachable is True

        # Remove the trash dir
        os.rmdir(trash_dir)
        registry = update_registry_reachability(reg_path)
        assert registry["0x12345678"].is_reachable is False


class TestGetAllTrashPaths:
    def test_central_only(self, tmp_path):
        central = str(tmp_path / "central")
        os.makedirs(central)
        reg_path = str(tmp_path / "volumes.json")
        paths = get_all_trash_paths(central, reg_path)
        assert paths == [central]

    def test_central_plus_per_volume(self, tmp_path):
        central = str(tmp_path / "central")
        per_vol = str(tmp_path / "per_vol")
        os.makedirs(central)
        os.makedirs(per_vol)

        reg_path = str(tmp_path / "volumes.json")
        v = VolumeInfo(
            device_id=1234, mount_point="X:" + os.sep,
            volume_serial="0xaabbccdd",
        )
        register_volume(v, per_vol, reg_path)

        paths = get_all_trash_paths(central, reg_path)
        assert central in paths
        assert per_vol in paths


class TestMultiStoreIntegration:
    """Test that TrashStore correctly routes and discovers across stores."""

    def test_isolated_store_ignores_global(self, tmp_path):
        """A store with explicit registry_path should not see global entries."""
        store = TrashStore(
            store_path=str(tmp_path / "trash"),
            registry_path=str(tmp_path / "volumes.json"),
        )
        # Should be empty -- no leakage from global registry
        assert len(store.list_entries()) == 0
        stats = store.get_stats()
        assert stats.total_folders == 0

    def test_delete_and_list_in_isolated_store(self, tmp_path):
        """Files deleted in isolated store should be found by list."""
        store = TrashStore(
            store_path=str(tmp_path / "trash"),
            registry_path=str(tmp_path / "volumes.json"),
        )
        workdir = tmp_path / "work"
        workdir.mkdir()
        f = workdir / "test.txt"
        f.write_text("hello")

        store.trash([str(f)])
        entries = store.list_entries()
        assert len(entries) == 1
        assert entries[0].entries[0].original_name == "test.txt"
