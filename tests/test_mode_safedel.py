"""Tests for safedel adoption in the mode swap (#38 / Phase-3.5 item 3.5-10).

Covers:
- `_load_safedel_api`: real load from the repo's safedel, absent->None, caching.
- `_remove_tool_dir_recoverable`: the recoverable-removal policy branches
  (safedel present + success, safedel absent -> rmtree fallback, backup
  failure aborts unless --force).

The helper-logic tests stub `_load_safedel_api` so they assert the branching
without touching the real trash store; the real trash-store behavior is covered
by safedel's own suite. One integration test exercises the real load mechanism.
"""
import os
import sys
import types
from pathlib import Path

import pytest

from dazzlecmd_lib import mode

REPO_ROOT = str(Path(__file__).resolve().parents[1])


@pytest.fixture(autouse=True)
def _clear_safedel_cache():
    """Each test starts and ends without the cached safedel api module."""
    sys.modules.pop(mode._SAFEDEL_API_CACHE_KEY, None)
    yield
    sys.modules.pop(mode._SAFEDEL_API_CACHE_KEY, None)


def _make_victim(tmp_path):
    d = tmp_path / "tool"
    d.mkdir()
    (d / "f.txt").write_text("x")
    return str(d)


def _fake_api(*, success=True, removes=False, raises=False):
    """A stand-in safedel api module whose TrashStore().trash() is scripted."""
    mod = types.ModuleType("_fake_safedel_api")

    class _Store:
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
                folder_path="/trash/2026-06-10__00-00-00",
            )

    mod.TrashStore = _Store
    return mod


# --- _load_safedel_api -------------------------------------------------------

def test_load_safedel_api_absent_returns_none(tmp_path):
    """No safedel under the given root -> None (graceful, not an error)."""
    assert mode._load_safedel_api(str(tmp_path), "projects") is None


def test_load_safedel_api_present_loads_real_and_caches():
    """The real repo safedel loads with its full public surface, then caches."""
    api = mode._load_safedel_api(REPO_ROOT, "projects")
    assert api is not None
    assert api.__api_version__ == "1"
    for name in ("TrashStore", "TrashEntry", "TrashResult", "StoreStats",
                 "stage_to_trash", "safe_delete", "classify"):
        assert hasattr(api, name), name
    # Second call returns the cached module object.
    assert mode._load_safedel_api(REPO_ROOT, "projects") is api


# --- _remove_tool_dir_recoverable -------------------------------------------

def test_remove_safedel_present_success_removes(tmp_path, monkeypatch):
    """safedel present + backup success -> dir removed, rc 0."""
    victim = _make_victim(tmp_path)
    monkeypatch.setattr(mode, "_load_safedel_api",
                        lambda pr, td: _fake_api(success=True, removes=True))
    rc = mode._remove_tool_dir_recoverable(
        victim, project_root=str(tmp_path), tools_dir="projects",
        tool_name="tool", command="dz", force=False,
    )
    assert rc == 0
    assert not os.path.exists(victim)


def test_remove_safedel_absent_falls_back_to_rmtree(tmp_path, monkeypatch):
    """safedel absent -> rmtree fallback (backward-compat), dir removed, rc 0."""
    victim = _make_victim(tmp_path)
    monkeypatch.setattr(mode, "_load_safedel_api", lambda pr, td: None)
    rc = mode._remove_tool_dir_recoverable(
        victim, project_root=str(tmp_path), tools_dir="projects",
        tool_name="tool", command="dz", force=False,
    )
    assert rc == 0
    assert not os.path.exists(victim)


def test_remove_backup_failure_aborts_without_force(tmp_path, monkeypatch):
    """Backup FAILS + no --force -> abort, dir intact, rc 1."""
    victim = _make_victim(tmp_path)
    monkeypatch.setattr(mode, "_load_safedel_api",
                        lambda pr, td: _fake_api(success=False, removes=False))
    rc = mode._remove_tool_dir_recoverable(
        victim, project_root=str(tmp_path), tools_dir="projects",
        tool_name="tool", command="dz", force=False,
    )
    assert rc == 1
    assert os.path.exists(victim)  # nothing deleted -- backup failed


def test_remove_backup_failure_force_rmtrees(tmp_path, monkeypatch):
    """Backup FAILS + --force -> rmtree fallback, dir removed, rc 0."""
    victim = _make_victim(tmp_path)
    monkeypatch.setattr(mode, "_load_safedel_api",
                        lambda pr, td: _fake_api(success=False, removes=False))
    rc = mode._remove_tool_dir_recoverable(
        victim, project_root=str(tmp_path), tools_dir="projects",
        tool_name="tool", command="dz", force=True,
    )
    assert rc == 0
    assert not os.path.exists(victim)


def test_remove_backup_raises_aborts_without_force(tmp_path, monkeypatch):
    """Backup raises + no --force -> abort, dir intact, rc 1."""
    victim = _make_victim(tmp_path)
    monkeypatch.setattr(mode, "_load_safedel_api",
                        lambda pr, td: _fake_api(raises=True))
    rc = mode._remove_tool_dir_recoverable(
        victim, project_root=str(tmp_path), tools_dir="projects",
        tool_name="tool", command="dz", force=False,
    )
    assert rc == 1
    assert os.path.exists(victim)
