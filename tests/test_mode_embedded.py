"""Tests for the EMBEDDED-swap enablement + config schema version.

Phase-3.5 Bucket D, the slice that became data-safe once the mode swap removes
recoverably via safedel (#38):
- 3.5-1: `_determine_target` returns "dev" for STATE_EMBEDDED, so a bare
  `dz mode switch <embedded-tool>` routes to `_switch_to_dev` instead of
  printing "no mode toggle available".
- 3.5-12: `mode_local.json` carries a `_schema_version` stamp for future
  migrations.
"""
import json
import os

from dazzlecmd_lib import mode


# --- 3.5-1: EMBEDDED swap unblock -------------------------------------------

def test_determine_target_embedded_returns_dev():
    """The headline unblock: EMBEDDED now toggles to dev (was None)."""
    assert mode._determine_target(mode.STATE_EMBEDDED) == "dev"


def test_determine_target_other_states_unchanged():
    """The other states keep their existing toggle semantics."""
    assert mode._determine_target(mode.STATE_SYMLINK) == "publish"
    assert mode._determine_target(mode.STATE_SUBMODULE) == "dev"
    assert mode._determine_target(mode.STATE_MISSING) is None
    assert mode._determine_target(mode.STATE_LOCAL_ONLY) is None


# --- 3.5-12: mode_local.json schema version ---------------------------------

def test_save_stamps_schema_version(tmp_path):
    """Every save stamps the current _schema_version into mode_local.json."""
    root = str(tmp_path)
    mode._save_full_config(root, {"dev_paths": {}, "cached_manifests": {}})
    on_disk = json.loads(
        (tmp_path / "mode_local.json").read_text(encoding="utf-8")
    )
    assert on_disk["_schema_version"] == mode.MODE_LOCAL_SCHEMA_VERSION


def test_schema_version_roundtrips(tmp_path):
    """A stamped config loads back with its _schema_version intact."""
    root = str(tmp_path)
    mode._save_full_config(root, {"dev_paths": {"core:x": "/repo"},
                                  "cached_manifests": {}})
    loaded = mode._load_full_config(root)
    assert loaded["_schema_version"] == mode.MODE_LOCAL_SCHEMA_VERSION
    assert loaded["dev_paths"] == {"core:x": "/repo"}


def test_save_preserves_existing_keys(tmp_path):
    """Stamping the schema version does not disturb dev_paths/manifests."""
    root = str(tmp_path)
    data = {"dev_paths": {"core:a": "/p"}, "cached_manifests": {"core:a": {}},
            "origins": {"core:a": "embedded"}}
    mode._save_full_config(root, data)
    loaded = mode._load_full_config(root)
    assert loaded["dev_paths"] == {"core:a": "/p"}
    assert loaded["origins"] == {"core:a": "embedded"}  # unknown keys survive
