"""Tests for the constitutional link primitive `core.links.create_link`.

`create_link` backs every `dz mode switch` into dev mode. On Windows it now uses
PowerShell `New-Item` (SymbolicLink -> Junction fallback) rather than
`cmd /c mklink`, which fails silently when invoked as a subprocess from bash/WSL
(CLAUDE.md rule #4; #37 Tier-1 criterion). These pin the create/remove
round-trip and the path-quoting that the PowerShell rewrite must get right.
"""
import os

from dazzlecmd_lib.core.links import (
    create_link,
    remove_link,
    is_linked_project,
)


def test_create_and_remove_link_roundtrip(tmp_path):
    """A link points at the source; removing it leaves the source intact."""
    src = tmp_path / "source"
    src.mkdir()
    (src / "f.txt").write_text("precious")
    link = tmp_path / "link"

    mode = create_link(str(src), str(link))
    assert mode in ("symlink", "junction")          # a real link mode
    assert is_linked_project(str(link))
    assert os.path.isfile(str(link / "f.txt"))      # content reachable through it

    assert remove_link(str(link))
    assert not is_linked_project(str(link))
    assert os.path.isfile(str(src / "f.txt"))       # source untouched by removal


def test_create_link_handles_spaced_paths(tmp_path):
    """Paths with spaces must be quoted correctly (the PowerShell New-Item
    rewrite single-quotes its -Path/-Target; a regression here would silently
    create the wrong link or none)."""
    src = tmp_path / "a source with spaces"
    src.mkdir()
    (src / "keep.txt").write_text("x")
    link = tmp_path / "the link dir"

    mode = create_link(str(src), str(link))
    assert mode in ("symlink", "junction")
    assert is_linked_project(str(link))
    assert os.path.isfile(str(link / "keep.txt"))
    remove_link(str(link))


def test_create_link_refuses_occupied_target(tmp_path):
    """create_link must not clobber an existing path -> returns None, no
    exception (mode switch relies on this contract before symlinking)."""
    src = tmp_path / "src"
    src.mkdir()
    link = tmp_path / "occupied"
    link.write_text("i am already here")          # target occupied by a file
    assert create_link(str(src), str(link)) is None
    assert link.read_text() == "i am already here"  # untouched
