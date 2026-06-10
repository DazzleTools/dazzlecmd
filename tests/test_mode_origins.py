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

from dazzlecmd_lib import mode


def _read(project_root):
    with open(os.path.join(project_root, "mode_local.json"),
              "r", encoding="utf-8") as f:
        return json.load(f)


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
