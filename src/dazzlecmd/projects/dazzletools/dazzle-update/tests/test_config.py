"""Unit tests for dazzle-update's config.py.

Covers load precedence (explicit > project-local > user config dir),
loud-not-silent degradation on malformed JSON, unknown-key warnings, and
write_template(). config.py had no test coverage before this session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_TOOL_DIR = _HERE.parent
sys.path.insert(0, str(_TOOL_DIR))

import config  # noqa: E402


# -- candidate_paths / precedence ------------------------------------------

class TestCandidatePaths:
    def test_order_is_explicit_then_project_then_user(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
        paths = config.candidate_paths(explicit="/explicit/path.json",
                                       cwd=str(tmp_path))
        assert paths[0] == "/explicit/path.json"
        assert paths[1] == str(tmp_path / config.PROJECT_CONFIG)
        # user config dir candidates (json, yaml, yml) come after
        assert str(tmp_path / "appdata" / "dazzlecmd") in paths[2]

    def test_no_explicit_still_lists_project_and_user(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
        paths = config.candidate_paths(explicit=None, cwd=str(tmp_path))
        assert paths[0] == str(tmp_path / config.PROJECT_CONFIG)
        assert len(paths) == 4  # project + json/yaml/yml user variants


# -- load() precedence and error handling -----------------------------------

class TestLoad:
    def test_missing_config_is_silent_and_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "nonexistent-appdata"))
        cfg, path, err = config.load(explicit=None, cwd=str(tmp_path))
        assert cfg == config.DEFAULTS
        assert path is None
        assert err is None

    def test_explicit_missing_file_is_reported_not_silent(self, tmp_path):
        missing = str(tmp_path / "does-not-exist.json")
        cfg, path, err = config.load(explicit=missing, cwd=str(tmp_path))
        assert cfg == config.DEFAULTS
        assert path is None
        assert err is not None
        assert missing in err

    def test_explicit_beats_project_local(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
        explicit_path = tmp_path / "explicit.json"
        explicit_path.write_text(json.dumps({"sort": "name"}), encoding="utf-8")
        project_path = tmp_path / config.PROJECT_CONFIG
        project_path.write_text(json.dumps({"sort": "oldest"}), encoding="utf-8")

        cfg, path, err = config.load(explicit=str(explicit_path), cwd=str(tmp_path))
        assert err is None
        assert path == str(explicit_path)
        assert cfg["sort"] == "name"

    def test_project_local_beats_user_config_dir(self, tmp_path, monkeypatch):
        appdata = tmp_path / "appdata"
        monkeypatch.setenv("LOCALAPPDATA", str(appdata))
        project_path = tmp_path / config.PROJECT_CONFIG
        project_path.write_text(json.dumps({"sort": "oldest"}), encoding="utf-8")
        user_dir = appdata / "dazzlecmd"
        user_dir.mkdir(parents=True)
        (user_dir / "dazzle-update.json").write_text(
            json.dumps({"sort": "name"}), encoding="utf-8")

        cfg, path, err = config.load(explicit=None, cwd=str(tmp_path))
        assert err is None
        assert path == str(project_path)
        assert cfg["sort"] == "oldest"

    def test_malformed_json_is_reported_not_swallowed(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json,,,", encoding="utf-8")
        cfg, path, err = config.load(explicit=str(bad), cwd=str(tmp_path))
        # Loud degradation: defaults are used, but the error MUST surface.
        assert cfg == config.DEFAULTS
        assert path is None
        assert err is not None
        assert str(bad) in err

    def test_non_dict_top_level_is_reported(self, tmp_path):
        arr = tmp_path / "array.json"
        arr.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        cfg, path, err = config.load(explicit=str(arr), cwd=str(tmp_path))
        assert cfg == config.DEFAULTS
        assert path is None
        assert err is not None
        assert "mapping" in err

    def test_unknown_keys_are_warned_not_silently_dropped(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text(json.dumps({"sort": "name", "bogus_key": 1,
                                 "another_bogus": 2}), encoding="utf-8")
        cfg, path, err = config.load(explicit=str(f), cwd=str(tmp_path))
        assert path == str(f)
        assert err is not None
        assert "bogus_key" in err
        assert "another_bogus" in err
        # unknown keys are dropped from the MERGED config, but the warning
        # is how the user finds out -- not silence.
        assert "bogus_key" not in cfg

    def test_known_keys_override_defaults_unknown_keys_ignored(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text(json.dumps({"roots": ["C:/somewhere"], "typo_field": True}),
                     encoding="utf-8")
        cfg, path, err = config.load(explicit=str(f), cwd=str(tmp_path))
        assert cfg["roots"] == ["C:/somewhere"]
        assert "typo_field" not in cfg
        # every DEFAULTS key is still present even though not in the file
        assert set(config.DEFAULTS) <= set(cfg)

    def test_empty_file_treated_as_empty_object(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("", encoding="utf-8")
        cfg, path, err = config.load(explicit=str(f), cwd=str(tmp_path))
        assert err is None
        assert cfg == config.DEFAULTS

    def test_unreadable_file_permission_style_error(self, tmp_path, monkeypatch):
        """Simulate an OSError during read (e.g. a permissions problem)
        without depending on real ACL manipulation."""
        f = tmp_path / "cfg.json"
        f.write_text("{}", encoding="utf-8")

        real_open = open  # the real builtin, captured before patching

        def _boom(path, *a, **kw):
            if str(path) == str(f):
                raise OSError("simulated permission denied")
            return real_open(path, *a, **kw)

        monkeypatch.setattr("builtins.open", _boom)
        cfg, path, err = config.load(explicit=str(f), cwd=str(tmp_path))
        assert cfg == config.DEFAULTS
        assert path is None
        assert err is not None
        assert "simulated permission denied" in err

    def test_yaml_without_pyyaml_reports_actionable_error(self, tmp_path, monkeypatch):
        f = tmp_path / "cfg.yaml"
        f.write_text("sort: name\n", encoding="utf-8")
        import builtins
        real_import = builtins.__import__

        def _no_yaml(name, *a, **kw):
            if name == "yaml":
                raise ImportError("no module named yaml")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _no_yaml)
        cfg, path, err = config.load(explicit=str(f), cwd=str(tmp_path))
        assert cfg == config.DEFAULTS
        assert path is None
        assert err is not None
        assert "PyYAML" in err


# -- write_template() --------------------------------------------------------

class TestWriteTemplate:
    def test_writes_valid_json_with_expected_keys(self, tmp_path):
        target = tmp_path / "sub" / "dazzle-update.json"
        ok, err = config.write_template(str(target))
        assert ok is True
        assert err is None
        assert target.is_file()
        data = json.loads(target.read_text(encoding="utf-8"))
        for key in ("roots", "namespaces", "personal_namespace", "exclude",
                    "sort", "order", "cache_write"):
            assert key in data

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "a" / "b" / "c" / "dazzle-update.json"
        ok, err = config.write_template(str(target))
        assert ok is True
        assert target.is_file()

    def test_written_template_round_trips_through_load(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
        target = tmp_path / "cfg.json"
        ok, err = config.write_template(str(target))
        assert ok
        cfg, path, load_err = config.load(explicit=str(target), cwd=str(tmp_path))
        assert path == str(target)
        # The template's own "_comment" key is not a real config key, so
        # load() correctly warns about it -- not silent, not fatal.
        assert load_err is not None
        assert "_comment" in load_err
        assert cfg["sort"] == "newest"

    def test_oserror_returns_false_and_error(self, tmp_path, monkeypatch):
        target = tmp_path / "cfg.json"

        def _boom(*a, **kw):
            raise OSError("simulated disk full")

        monkeypatch.setattr(config.os, "makedirs", _boom)
        ok, err = config.write_template(str(target))
        assert ok is False
        assert "simulated disk full" in err
