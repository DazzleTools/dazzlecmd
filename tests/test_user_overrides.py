"""Tests for dazzlecmd_lib.user_overrides."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dazzlecmd_lib.user_overrides import (
    OVERRIDE_ENV_VAR,
    get_override_root,
    get_override_path,
    load_override,
    _fqcn_to_filename,
)
from dazzlecmd_lib.schema_version import UnsupportedSchemaVersionError


class TestGetOverrideRoot:
    def test_default_location(self, monkeypatch):
        monkeypatch.delenv(OVERRIDE_ENV_VAR, raising=False)
        root = get_override_root()
        assert root == Path.home() / ".dazzlecmd" / "overrides"

    def test_env_var_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        assert get_override_root() == tmp_path

    def test_empty_env_var_uses_default(self, monkeypatch):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, "")
        root = get_override_root()
        assert root == Path.home() / ".dazzlecmd" / "overrides"


class TestFqcnToFilename:
    def test_simple_fqcn(self):
        assert _fqcn_to_filename("mytool") == "mytool"

    def test_one_colon(self):
        assert _fqcn_to_filename("dazzletools:fixpath") == "dazzletools__fixpath"

    def test_multiple_colons(self):
        assert _fqcn_to_filename("a:b:c") == "a__b__c"


class TestGetOverridePath:
    def test_full_path_construction(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        path = get_override_path("setup", "dazzletools:fixpath")
        assert path == tmp_path / "setup" / "dazzletools__fixpath.json"

    def test_runtime_layer(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        path = get_override_path("runtime", "mytool")
        assert path == tmp_path / "runtime" / "mytool.json"

    def test_empty_layer_raises(self):
        with pytest.raises(ValueError):
            get_override_path("", "mytool")

    def test_empty_fqcn_raises(self):
        with pytest.raises(ValueError):
            get_override_path("setup", "")


class TestLoadOverride:
    def test_missing_file_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        assert load_override("setup", "nonexistent") is None

    def test_valid_file_returns_dict(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        override_dir = tmp_path / "setup"
        override_dir.mkdir()
        override_file = override_dir / "mytool.json"
        data = {"_schema_version": "1", "command": "apt install -y mytool"}
        override_file.write_text(json.dumps(data))
        loaded = load_override("setup", "mytool")
        assert loaded == data

    def test_valid_file_no_schema_version_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        override_dir = tmp_path / "setup"
        override_dir.mkdir()
        override_file = override_dir / "mytool.json"
        data = {"command": "pip install mytool"}
        override_file.write_text(json.dumps(data))
        loaded = load_override("setup", "mytool")
        assert loaded is not None
        assert loaded["command"] == "pip install mytool"

    def test_unsupported_schema_version_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        override_dir = tmp_path / "setup"
        override_dir.mkdir()
        override_file = override_dir / "mytool.json"
        override_file.write_text(json.dumps({"_schema_version": "99"}))
        with pytest.raises(UnsupportedSchemaVersionError) as exc:
            load_override("setup", "mytool")
        assert "99" in str(exc.value)

    def test_malformed_json_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        override_dir = tmp_path / "setup"
        override_dir.mkdir()
        override_file = override_dir / "mytool.json"
        override_file.write_text("{not valid json")
        with pytest.raises(json.JSONDecodeError):
            load_override("setup", "mytool")

    def test_non_object_json_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        override_dir = tmp_path / "setup"
        override_dir.mkdir()
        override_file = override_dir / "mytool.json"
        override_file.write_text("[1, 2, 3]")
        with pytest.raises(ValueError) as exc:
            load_override("setup", "mytool")
        assert "JSON object" in str(exc.value) or "object" in str(exc.value)

    def test_fqcn_with_colons_maps_correctly(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        override_dir = tmp_path / "setup"
        override_dir.mkdir()
        # File on disk uses translated name
        override_file = override_dir / "kitname__toolname.json"
        override_file.write_text(json.dumps({"_schema_version": "1", "x": 1}))
        # Load using the original FQCN -- file should be found
        loaded = load_override("setup", "kitname:toolname")
        assert loaded == {"_schema_version": "1", "x": 1}

    def test_directory_at_expected_path_returns_none(self, monkeypatch, tmp_path):
        # If the path is a directory instead of a file, it's not an override.
        monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
        override_dir = tmp_path / "setup" / "mytool.json"
        override_dir.mkdir(parents=True)
        assert load_override("setup", "mytool") is None
