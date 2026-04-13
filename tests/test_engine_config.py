"""Tests for the user config read/write path introduced in Phase 3.

Covers:
    - _get_user_config: read, missing file, malformed JSON, non-dict root
    - _get_config_list / _get_config_dict type validation
    - _write_user_config: create dir, atomic write, merge semantics,
      schema version injection, cache invalidation
    - Integration with loader.get_active_kits via user_config parameter
    - DZ_KITS environment variable override
"""

import json
import os

import pytest

from dazzlecmd.engine import AggregatorEngine
from dazzlecmd.loader import get_active_kits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine_with_config(tmp_path, monkeypatch):
    """Build an engine pointing at a clean tmp_path config file."""
    config_path = tmp_path / "config.json"
    monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
    return AggregatorEngine()


# ---------------------------------------------------------------------------
# _get_user_config
# ---------------------------------------------------------------------------


class TestGetUserConfig:

    def test_missing_file_returns_empty_dict(self, tmp_path, monkeypatch):
        engine = _engine_with_config(tmp_path, monkeypatch)
        assert engine._get_user_config() == {}

    def test_empty_file_returns_empty_dict(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text("", encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine._get_user_config() == {}

    def test_valid_config_returns_parsed_dict(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        data = {"_schema_version": 1, "kit_precedence": ["core", "wtf"]}
        config_path.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine._get_user_config() == data

    def test_malformed_json_returns_empty_dict(self, tmp_path, monkeypatch, capsys):
        config_path = tmp_path / "config.json"
        config_path.write_text("{ not valid json", encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine._get_user_config() == {}
        captured = capsys.readouterr()
        assert "could not read" in captured.err.lower() or "warning" in captured.err.lower()

    def test_non_dict_root_returns_empty_dict(self, tmp_path, monkeypatch, capsys):
        config_path = tmp_path / "config.json"
        config_path.write_text('["not", "a", "dict"]', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine._get_user_config() == {}
        captured = capsys.readouterr()
        assert "not a json object" in captured.err.lower() or "warning" in captured.err.lower()

    def test_result_is_cached(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"kit_precedence": ["core"]}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        _ = engine._get_user_config()
        # Modify file underneath -- cache should still return old value
        config_path.write_text('{"kit_precedence": ["wtf"]}', encoding="utf-8")
        assert engine._get_user_config() == {"kit_precedence": ["core"]}


# ---------------------------------------------------------------------------
# _get_config_list / _get_config_dict
# ---------------------------------------------------------------------------


class TestGetConfigList:

    def test_missing_key_returns_default(self, tmp_path, monkeypatch):
        engine = _engine_with_config(tmp_path, monkeypatch)
        assert engine._get_config_list("ghost") is None
        assert engine._get_config_list("ghost", default=[]) == []

    def test_list_value_returned(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"items": ["a", "b"]}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine._get_config_list("items") == ["a", "b"]

    def test_non_list_value_warns_and_returns_default(
        self, tmp_path, monkeypatch, capsys
    ):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"items": "not a list"}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine._get_config_list("items") is None
        captured = capsys.readouterr()
        assert "not a list" in captured.err


class TestGetConfigDict:

    def test_missing_key_returns_empty_dict(self, tmp_path, monkeypatch):
        engine = _engine_with_config(tmp_path, monkeypatch)
        assert engine._get_config_dict("ghost") == {}

    def test_dict_value_returned(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"favorites": {"a": "b"}}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine._get_config_dict("favorites") == {"a": "b"}

    def test_non_dict_value_warns_and_returns_default(
        self, tmp_path, monkeypatch, capsys
    ):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"favorites": ["a", "b"]}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine._get_config_dict("favorites") == {}
        captured = capsys.readouterr()
        assert "not a dict" in captured.err


# ---------------------------------------------------------------------------
# _write_user_config
# ---------------------------------------------------------------------------


class TestWriteUserConfig:

    def test_creates_config_dir_if_missing(self, tmp_path, monkeypatch):
        config_path = tmp_path / "nested" / "dazzlecmd" / "config.json"
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        engine._write_user_config({"kit_precedence": ["core"]})
        assert config_path.exists()
        assert config_path.parent.is_dir()

    def test_writes_json_with_schema_version(self, tmp_path, monkeypatch):
        engine = _engine_with_config(tmp_path, monkeypatch)
        engine._write_user_config({"kit_precedence": ["core"]})
        data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert data["_schema_version"] == 1
        assert data["kit_precedence"] == ["core"]

    def test_merge_preserves_existing_keys(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "kit_precedence": ["core"],
                "favorites": {"foo": "core:foo"},
            }),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        engine._write_user_config({"shadowed_tools": ["core:bar"]})
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["kit_precedence"] == ["core"]
        assert data["favorites"] == {"foo": "core:foo"}
        assert data["shadowed_tools"] == ["core:bar"]

    def test_merge_preserves_unknown_user_keys(self, tmp_path, monkeypatch):
        """User-added keys we don't know about are preserved."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "kit_precedence": ["core"],
                "user_custom_key": "keep me",
            }),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        engine._write_user_config({"active_kits": ["core"]})
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["user_custom_key"] == "keep me"

    def test_write_invalidates_cache(self, tmp_path, monkeypatch):
        engine = _engine_with_config(tmp_path, monkeypatch)
        # First read populates the cache
        assert engine._get_user_config() == {}
        engine._write_user_config({"kit_precedence": ["core"]})
        # Cache should be invalidated; next read picks up the write
        assert engine._get_user_config() == {
            "_schema_version": 1,
            "kit_precedence": ["core"],
        }

    def test_write_atomic_no_temp_left_behind(self, tmp_path, monkeypatch):
        engine = _engine_with_config(tmp_path, monkeypatch)
        engine._write_user_config({"kit_precedence": ["core"]})
        # No .config.json.*.tmp files should remain after a successful write
        leftovers = list(tmp_path.glob(".config.json.*.tmp"))
        assert leftovers == []

    def test_corrupted_existing_file_starts_fresh(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text("{ corrupted", encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        engine._write_user_config({"kit_precedence": ["core"]})
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["kit_precedence"] == ["core"]


# ---------------------------------------------------------------------------
# loader.get_active_kits with user_config parameter
# ---------------------------------------------------------------------------


def _mk_kit(name, always_active=False):
    return {
        "_kit_name": name,
        "name": name,
        "always_active": always_active,
        "tools": [],
    }


class TestGetActiveKits:

    def setup_method(self):
        self.kits = [
            _mk_kit("core", always_active=True),
            _mk_kit("dazzletools", always_active=True),
            _mk_kit("wtf", always_active=False),
            _mk_kit("extra", always_active=False),
        ]

    def test_no_config_returns_all(self):
        result = get_active_kits(self.kits, user_config=None)
        assert [k["name"] for k in result] == ["core", "dazzletools", "wtf", "extra"]

    def test_empty_config_returns_all(self):
        result = get_active_kits(self.kits, user_config={})
        assert len(result) == 4

    def test_disabled_kits_excluded(self):
        result = get_active_kits(self.kits, user_config={
            "disabled_kits": ["wtf", "extra"],
        })
        assert [k["name"] for k in result] == ["core", "dazzletools"]

    def test_disabled_overrides_always_active(self):
        """Explicit disable overrides always_active=True."""
        result = get_active_kits(self.kits, user_config={
            "disabled_kits": ["core"],
        })
        names = [k["name"] for k in result]
        assert "core" not in names

    def test_active_kits_filter_preserves_always_active(self):
        result = get_active_kits(self.kits, user_config={
            "active_kits": ["wtf"],
        })
        names = {k["name"] for k in result}
        # core and dazzletools stay because they're always_active
        assert "core" in names
        assert "dazzletools" in names
        assert "wtf" in names
        # extra is NOT in active_kits and is not always_active
        assert "extra" not in names

    def test_overlap_disabled_wins(self, capsys):
        result = get_active_kits(self.kits, user_config={
            "active_kits": ["wtf", "core"],
            "disabled_kits": ["wtf"],
        })
        names = {k["name"] for k in result}
        assert "wtf" not in names
        captured = capsys.readouterr()
        assert "disabled wins" in captured.err.lower() or "warning" in captured.err.lower()

    def test_dz_kits_env_override(self, monkeypatch):
        monkeypatch.setenv("DZ_KITS", "core,wtf")
        result = get_active_kits(self.kits, user_config={
            "disabled_kits": ["core"],  # ignored by env override
        })
        assert {k["name"] for k in result} == {"core", "wtf"}

    def test_dz_kits_empty_means_no_kits(self, monkeypatch):
        monkeypatch.setenv("DZ_KITS", "")
        result = get_active_kits(self.kits, user_config={})
        assert result == []

    def test_dz_kits_unset_falls_through_to_config(self, monkeypatch):
        monkeypatch.delenv("DZ_KITS", raising=False)
        result = get_active_kits(self.kits, user_config={
            "disabled_kits": ["wtf"],
        })
        names = {k["name"] for k in result}
        assert "wtf" not in names
