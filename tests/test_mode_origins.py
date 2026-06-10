"""Tests for mode-swap restore origins (the #37 reversibility foundation).

`dz mode switch <tool>` into dev mode destroys the prior on-disk form (an
embedded dir or a submodule checkout). Schema v2 of `mode_local.json` records
that prior form under an `origins` key so `dz mode restore <tool>` can
re-materialize it. These pin the data layer: the schema bump, the `origins`
key migration, and the `_record_origin` / `_clear_origin` helpers.

The restore command itself (`cmd_restore`) and its fs round-trip are covered
separately.
"""
import json
import os

import pytest

from dazzlecmd_lib import mode
from dazzlecmd_lib.entity import build_entity
from dazzlecmd_lib.paths import is_linked_project


def _read(project_root):
    with open(os.path.join(project_root, "mode_local.json"),
              "r", encoding="utf-8") as f:
        return json.load(f)


def _embedded_tool(root):
    """An embedded tool at ``root/projects/core/find`` + a separate dev source.

    Returns ``(project_entity, tool_dir, dev_src)``.
    """
    tool_dir = os.path.join(root, "projects", "core", "find")
    os.makedirs(tool_dir)
    with open(os.path.join(tool_dir, "find.py"), "w", encoding="utf-8") as f:
        f.write("EMBEDDED CONTENT")
    dev_src = os.path.join(root, "devsrc")
    os.makedirs(dev_src)
    with open(os.path.join(dev_src, "find.py"), "w", encoding="utf-8") as f:
        f.write("DEV CONTENT")
    project = build_entity({
        "name": "find", "namespace": "core", "version": "1.0.0",
        "description": "sandbox", "directory": tool_dir, "_fqcn": "core:find",
        "runtime": {"type": "python", "script_path": "find.py"},
    }, entity_type="tool")
    return project, tool_dir, dev_src


def _isolate_trash(monkeypatch, root):
    """Point safedel's default TrashStore at an isolated store under ``root`` so
    the switch backup + restore recovery never touch the real trash store."""
    import dazzlecmd_lib.core.safedel as sd
    real = sd.TrashStore
    store_path = os.path.join(root, "_trash")
    reg_path = os.path.join(root, "_trash_reg.json")

    def _isolated(*a, **k):
        k.setdefault("store_path", store_path)
        k.setdefault("registry_path", reg_path)
        return real(*a, **k)

    monkeypatch.setattr(sd, "TrashStore", _isolated)


def test_schema_version_is_2():
    """The schema version bumped to 2 when `origins` was added (#37)."""
    assert mode.MODE_LOCAL_SCHEMA_VERSION == 2


def test_load_full_config_migrates_missing_origins(tmp_path):
    """An old config (no `origins` key) loads with an empty origins dict."""
    root = str(tmp_path)
    legacy = {"dev_paths": {"core:x": "/p"}, "cached_manifests": {},
              "_schema_version": 1}
    with open(os.path.join(root, "mode_local.json"), "w", encoding="utf-8") as f:
        json.dump(legacy, f)
    data = mode._load_full_config(root)
    assert data["origins"] == {}
    assert data["dev_paths"] == {"core:x": "/p"}  # untouched


def test_load_full_config_missing_file(tmp_path):
    """A missing config returns the full v2 skeleton including origins."""
    data = mode._load_full_config(str(tmp_path))
    assert data["origins"] == {}
    assert data["dev_paths"] == {} and data["cached_manifests"] == {}


def test_record_origin_writes_shape(tmp_path):
    """`_record_origin` writes the documented record and stamps schema v2."""
    root = str(tmp_path)
    mode._record_origin(
        "core:find", mode.STATE_EMBEDDED, root,
        trash_folder="2026-06-10__14-19-27",
        original_path=os.path.join(root, "projects", "core", "find"),
    )
    data = _read(root)
    assert data["_schema_version"] == 2
    rec = data["origins"]["core:find"]
    assert rec["prior_state"] == "embedded"
    assert rec["trash_folder"] == "2026-06-10__14-19-27"
    assert rec["original_path"].endswith(os.path.join("core", "find"))
    assert rec["switch_timestamp"]  # ISO 8601 timestamp recorded


def test_record_origin_submodule_has_null_trash(tmp_path):
    """A SUBMODULE origin records no trash folder (restore re-clones)."""
    root = str(tmp_path)
    mode._record_origin("core:listall", mode.STATE_SUBMODULE, root,
                        trash_folder=None, original_path="/p")
    rec = _read(root)["origins"]["core:listall"]
    assert rec["prior_state"] == "submodule"
    assert rec["trash_folder"] is None


def test_record_origin_overwrites(tmp_path):
    """A second record for the same tool overwrites the first (flat dict)."""
    root = str(tmp_path)
    mode._record_origin("core:find", mode.STATE_SUBMODULE, root)
    mode._record_origin("core:find", mode.STATE_EMBEDDED, root,
                        trash_folder="f2")
    rec = _read(root)["origins"]["core:find"]
    assert rec["prior_state"] == "embedded"
    assert rec["trash_folder"] == "f2"


def test_clear_origin_removes(tmp_path):
    """`_clear_origin` drops the record for a tool."""
    root = str(tmp_path)
    mode._record_origin("core:find", mode.STATE_EMBEDDED, root, trash_folder="f")
    mode._clear_origin("core:find", root)
    assert "core:find" not in _read(root)["origins"]


def test_clear_origin_noop_when_absent(tmp_path):
    """Clearing a non-existent origin is a harmless no-op."""
    root = str(tmp_path)
    # No config file yet -> nothing written, no crash.
    mode._clear_origin("core:nope", root)
    # With a config present but no such origin -> still fine.
    mode._record_origin("core:other", mode.STATE_EMBEDDED, root)
    mode._clear_origin("core:nope", root)
    assert "core:other" in _read(root)["origins"]


# --- cmd_restore: the EMBEDDED round-trip and refusal paths ----------------

def test_embedded_dev_then_restore_round_trip(tmp_path, monkeypatch):
    """switch->dev backs up the embedded content + records an origin; restore
    removes the symlink and recovers the EXACT embedded content back."""
    root = str(tmp_path / "agg")
    os.makedirs(root)
    _isolate_trash(monkeypatch, str(tmp_path))
    project, tool_dir, dev_src = _embedded_tool(root)

    # Enter dev mode: embedded dir is trashed, a link to dev_src replaces it,
    # and an origin record is written.
    rc = mode._switch_to_dev(
        project, root, {}, dev_src, dry_run=False, force=False,
        tools_dir="projects", command="dz",
    )
    assert rc == 0
    assert is_linked_project(tool_dir)
    origin = _read(root)["origins"]["core:find"]
    assert origin["prior_state"] == "embedded"
    assert origin["trash_folder"]

    # Restore: link removed, original embedded content recovered, origin cleared.
    rc = mode.cmd_restore("find", [project], root,
                          tools_dir="projects", command="dz")
    assert rc == 0
    assert not is_linked_project(tool_dir)
    with open(os.path.join(tool_dir, "find.py"), encoding="utf-8") as f:
        assert f.read() == "EMBEDDED CONTENT"   # the embedded form, not dev
    # dev source is untouched
    with open(os.path.join(dev_src, "find.py"), encoding="utf-8") as f:
        assert f.read() == "DEV CONTENT"
    assert "core:find" not in _read(root)["origins"]


def test_restore_dry_run_changes_nothing(tmp_path, monkeypatch):
    """--dry-run reports the plan but leaves the symlink + origin in place."""
    root = str(tmp_path / "agg")
    os.makedirs(root)
    _isolate_trash(monkeypatch, str(tmp_path))
    project, tool_dir, dev_src = _embedded_tool(root)
    mode._switch_to_dev(project, root, {}, dev_src, dry_run=False, force=False,
                        tools_dir="projects", command="dz")

    rc = mode.cmd_restore("find", [project], root, dry_run=True,
                          tools_dir="projects", command="dz")
    assert rc == 0
    assert is_linked_project(tool_dir)                       # still a link
    assert "core:find" in _read(root)["origins"]             # origin untouched


def test_restore_no_origin_is_noop(tmp_path):
    """Restore with no recorded origin says so and returns 0."""
    root = str(tmp_path / "agg")
    os.makedirs(root)
    project, _tool_dir, _dev = _embedded_tool(root)
    rc = mode.cmd_restore("find", [project], root,
                          tools_dir="projects", command="dz")
    assert rc == 0  # nothing to do
    # No origin was ever recorded.
    assert _read(root)["origins"] == {} if os.path.isfile(
        os.path.join(root, "mode_local.json")) else True


def test_restore_not_in_dev_mode_is_noop(tmp_path):
    """An origin recorded but the tool is NOT currently a symlink -> not
    applicable, returns 0 without touching the dir."""
    root = str(tmp_path / "agg")
    os.makedirs(root)
    project, tool_dir, _dev = _embedded_tool(root)
    # Forge an origin without actually switching (tool stays EMBEDDED).
    mode._record_origin("core:find", mode.STATE_EMBEDDED, root,
                        trash_folder="nonexistent", original_path=tool_dir)
    rc = mode.cmd_restore("find", [project], root,
                          tools_dir="projects", command="dz")
    assert rc == 0
    assert os.path.isfile(os.path.join(tool_dir, "find.py"))  # untouched


def test_restore_missing_trash_entry_fails(tmp_path, monkeypatch):
    """An EMBEDDED origin whose backup is gone fails cleanly (rc 1), leaving the
    symlink in place (we never removed it -- the pre-check caught the gap)."""
    root = str(tmp_path / "agg")
    os.makedirs(root)
    _isolate_trash(monkeypatch, str(tmp_path))
    project, tool_dir, dev_src = _embedded_tool(root)
    mode._switch_to_dev(project, root, {}, dev_src, dry_run=False, force=False,
                        tools_dir="projects", command="dz")
    # Corrupt the origin to point at a backup that doesn't exist.
    data = mode._load_full_config(root)
    data["origins"]["core:find"]["trash_folder"] = "1999-01-01__00-00-00"
    mode._save_full_config(root, data)

    rc = mode.cmd_restore("find", [project], root,
                          tools_dir="projects", command="dz")
    assert rc == 1
    assert is_linked_project(tool_dir)  # symlink NOT removed (pre-check failed)
