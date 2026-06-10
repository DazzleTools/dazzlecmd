"""Tests for the constitutional recoverable-delete primitive.

`dazzlecmd_lib.core.safedel` is the engine relocated from the safedel tool so
every aggregator gets recoverable deletion with no fallback path. These verify
the lib copy imports and performs a real trash round-trip in an isolated store
(the tool's own 121-test suite covers the full surface; this pins the lib-side
relocation).
"""
import os
import tempfile

import pytest

import dazzlecmd_lib.core.safedel as sd


def test_public_surface():
    assert sd.__api_version__ == "2"  # v2 added recover_folder (#37)
    for name in ("TrashStore", "TrashEntry", "TrashResult", "StoreStats",
                 "stage_to_trash", "safe_delete", "get_trash_dir", "classify",
                 "cmd_recover", "cmd_list", "recover_folder"):
        assert hasattr(sd, name), name


def test_classify_dir_and_file(tmp_path):
    d = tmp_path / "adir"
    d.mkdir()
    (d / "f.txt").write_text("x")
    f = tmp_path / "afile.txt"
    f.write_text("y")
    assert sd.classify(str(d)).file_type == sd.FileType.REGULAR_DIR
    assert sd.classify(str(f)).file_type == sd.FileType.REGULAR_FILE


def test_trash_round_trip_isolated_store(tmp_path):
    """A real directory is staged to an isolated trash store and removed."""
    store_dir = tmp_path / "trash"
    reg = tmp_path / "reg.json"
    victim = tmp_path / "tool"
    victim.mkdir()
    (victim / "keep.txt").write_text("precious")

    store = sd.TrashStore(store_path=str(store_dir), registry_path=str(reg))
    result = store.trash([str(victim)])

    assert result.success
    assert not victim.exists()                      # original removed
    assert os.path.isdir(result.folder_path)        # staged into the store
    # the staged content survives under the trash folder
    staged = []
    for root, _dirs, files in os.walk(result.folder_path):
        staged.extend(files)
    assert "keep.txt" in staged


def test_links_detection_reexported():
    """core.links exposes the relocated detection surface core.safedel needs."""
    from dazzlecmd_lib.core.links import (
        detect_link, canonicalize_path, LinkInfo,
        LINK_SYMLINK, LINK_JUNCTION, LINK_HARDLINK,
    )
    assert callable(detect_link)
    assert callable(canonicalize_path)
