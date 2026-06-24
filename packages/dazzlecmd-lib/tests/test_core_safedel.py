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


def test_cmd_list_count_limits_to_most_recent(tmp_path, capsys):
    """`cmd_list(count=N)` shows only the N most recent folders + a truncation
    note; count=0/None shows all (the `dz safedel list` default is 10)."""
    store = sd.TrashStore(store_path=str(tmp_path / "trash"),
                          registry_path=str(tmp_path / "reg.json"))
    for i in range(12):
        d = tmp_path / f"victim_{i}"
        d.mkdir()
        (d / "f.txt").write_text(str(i))
        assert store.trash([str(d)]).success
    capsys.readouterr()  # clear trash() chatter

    # default-style cap
    assert sd.cmd_list(store, [], count=10) == 0
    out = capsys.readouterr().out
    assert "10 most recent of 12 folder(s)" in out

    # count=0 -> show all
    assert sd.cmd_list(store, [], count=0) == 0
    assert "12 matching folder(s)" in capsys.readouterr().out

    # count=None (library default) -> show all, backward-compatible
    assert sd.cmd_list(store, [], count=None) == 0
    assert "12 matching folder(s)" in capsys.readouterr().out

    # fewer entries than the cap -> no truncation note
    assert sd.cmd_list(store, [], count=50) == 0
    out = capsys.readouterr().out
    assert "12 matching folder(s)" in out and "most recent of" not in out


def test_list_parser_count_and_all():
    """The `dz safedel list` parser exposes --count (default 10) and --all."""
    import importlib.util
    import os
    spec = importlib.util.spec_from_file_location(
        "_safedel_tool",
        os.path.join(os.path.dirname(__file__), "..", "..", "..",
                     "src", "dazzlecmd", "projects", "core", "safedel", "safedel.py"),
    )
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    p = tool._build_list_parser()
    assert p.parse_args([]).count == 10          # default
    assert p.parse_args(["--count", "5"]).count == 5
    assert p.parse_args(["--all"]).all is True


def test_links_detection_reexported():
    """core.links exposes the relocated detection surface core.safedel needs."""
    from dazzlecmd_lib.core.links import (
        detect_link, canonicalize_path, LinkInfo,
        LINK_SYMLINK, LINK_JUNCTION, LINK_HARDLINK,
    )
    assert callable(detect_link)
    assert callable(canonicalize_path)
