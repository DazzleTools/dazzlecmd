"""Tests for the mode swap's recoverable removal (no fallback; #38 reframe / #179).

The recoverable-delete engine is now a constitutional lib primitive
(`dazzlecmd_lib.core.safedel`), so mode.py removes a tool directory via that
primitive ALWAYS -- there is NO "safedel absent" fallback path. `--immediate`
is a deliberate CHOICE (direct rmtree, no recovery backup), not a fallback.
These pin `_remove_tool_dir`'s branches (the trash call is stubbed so they
don't touch the real store; the real round-trip is in the lib's
`test_core_safedel.py`).
"""
import os
import types

from dazzlecmd_lib import mode


def _make_victim(tmp_path):
    d = tmp_path / "tool"
    d.mkdir()
    (d / "f.txt").write_text("x")
    return str(d)


def _fake_store_cls(*, success=True, removes=False, raises=False):
    class _Store:
        def __init__(self, *a, **k):
            pass

        def trash(self, paths, dry_run=False):
            if raises:
                raise RuntimeError("boom")
            if removes and success:
                import shutil
                for p in paths:
                    shutil.rmtree(p)
            return types.SimpleNamespace(
                success=success,
                errors=[] if success else ["disk full"],
                folder_name="2026-06-10__00-00-00" if success else None,
                folder_path="/trash/2026-06-10__00-00-00",
            )

    return _Store


def test_immediate_rmtrees(tmp_path):
    """--immediate deletes directly with no backup -> rc 0, dir gone, no folder."""
    victim = _make_victim(tmp_path)
    rc, folder = mode._remove_tool_dir(victim, tool_name="t", command="dz",
                                       force=False, immediate=True)
    assert rc == 0
    assert folder is None  # no backup made -> no restore pointer (#37)
    assert not os.path.exists(victim)


def test_recoverable_default_trashes(tmp_path, monkeypatch):
    """Default path stages to the lib trash primitive -> rc 0, dir removed,
    and returns the trash folder name (the restore pointer, #37)."""
    victim = _make_victim(tmp_path)
    monkeypatch.setattr("dazzlecmd_lib.core.safedel.TrashStore",
                        _fake_store_cls(success=True, removes=True))
    rc, folder = mode._remove_tool_dir(victim, tool_name="t", command="dz",
                                       force=False)
    assert rc == 0
    assert folder == "2026-06-10__00-00-00"
    assert not os.path.exists(victim)


def test_backup_failure_aborts_without_force(tmp_path, monkeypatch):
    """A backup FAILURE aborts (nothing deleted) unless --force/--immediate."""
    victim = _make_victim(tmp_path)
    monkeypatch.setattr("dazzlecmd_lib.core.safedel.TrashStore",
                        _fake_store_cls(success=False))
    rc, folder = mode._remove_tool_dir(victim, tool_name="t", command="dz",
                                       force=False)
    assert rc == 1
    assert folder is None
    assert os.path.exists(victim)


def test_backup_failure_force_rmtrees(tmp_path, monkeypatch):
    """--force proceeds past a backup failure (rmtree) -> rc 0, dir gone, no folder."""
    victim = _make_victim(tmp_path)
    monkeypatch.setattr("dazzlecmd_lib.core.safedel.TrashStore",
                        _fake_store_cls(success=False))
    rc, folder = mode._remove_tool_dir(victim, tool_name="t", command="dz",
                                       force=True)
    assert rc == 0
    assert folder is None
    assert not os.path.exists(victim)


def test_backup_exception_aborts(tmp_path, monkeypatch):
    """An exception in the trash call aborts (nothing deleted) without force."""
    victim = _make_victim(tmp_path)
    monkeypatch.setattr("dazzlecmd_lib.core.safedel.TrashStore",
                        _fake_store_cls(raises=True))
    rc, folder = mode._remove_tool_dir(victim, tool_name="t", command="dz",
                                       force=False)
    assert rc == 1
    assert folder is None
    assert os.path.exists(victim)


def test_no_fallback_loader_removed():
    """The tool-loading shim + its absent-fallback are gone (no dead path)."""
    assert not hasattr(mode, "_load_safedel_api")
    assert not hasattr(mode, "_remove_tool_dir_recoverable")
    assert hasattr(mode, "_remove_tool_dir")
