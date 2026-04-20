"""Phase 4e Commit 4: verify grouped stale-favorite warning.

A favorite entry ``short -> fqcn`` is stale when the fqcn is neither
a canonical FQCN nor an alias FQCN in the current index. The engine
emits ONE grouped warning at discover() time, respecting silenced_hints.
"""

import json
import os

import pytest

from dazzlecmd_lib.engine import AggregatorEngine


def _write_config(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _proj(fqcn, short, kit):
    return {
        "_fqcn": fqcn,
        "_short_name": short,
        "_kit_import_name": kit,
        "name": short,
        "namespace": kit,
    }


class TestStaleFavoriteWarning:
    def _engine_with_projects(self, tmp_path, monkeypatch, favorites, projects):
        config_path = str(tmp_path / "config.json")
        monkeypatch.setenv("DAZZLECMD_CONFIG", config_path)
        _write_config(config_path, {"_schema_version": 1, "favorites": favorites})

        engine = AggregatorEngine(is_root=True)
        engine.projects = list(projects)
        engine._build_fqcn_index()
        return engine

    def test_no_favorites_no_warning(self, tmp_path, monkeypatch, capsys):
        engine = self._engine_with_projects(
            tmp_path, monkeypatch, {}, [_proj("core:rn", "rn", "core")]
        )
        engine._maybe_emit_stale_favorites_warning()
        assert capsys.readouterr().err == ""

    def test_live_favorite_no_warning(self, tmp_path, monkeypatch, capsys):
        engine = self._engine_with_projects(
            tmp_path, monkeypatch,
            {"rn": "core:rn"},
            [_proj("core:rn", "rn", "core")],
        )
        engine._maybe_emit_stale_favorites_warning()
        assert capsys.readouterr().err == ""

    def test_stale_favorite_triggers_warning(self, tmp_path, monkeypatch, capsys):
        engine = self._engine_with_projects(
            tmp_path, monkeypatch,
            {"gone": "missing:tool"},
            [_proj("core:rn", "rn", "core")],
        )
        engine._maybe_emit_stale_favorites_warning()
        err = capsys.readouterr().err
        assert "stale favorite" in err.lower()
        assert "gone" in err
        assert "missing:tool" in err

    def test_multiple_stale_favorites_grouped(self, tmp_path, monkeypatch, capsys):
        engine = self._engine_with_projects(
            tmp_path, monkeypatch,
            {"a": "x:1", "b": "x:2", "c": "x:3", "d": "x:4"},
            [_proj("core:rn", "rn", "core")],
        )
        engine._maybe_emit_stale_favorites_warning()
        err = capsys.readouterr().err
        # ONE warning with count
        assert "4 stale favorite" in err
        # First 3 listed by detail
        assert "x:1" in err
        assert "x:2" in err
        assert "x:3" in err
        # 4th compressed into "+1 more"
        assert "+1 more" in err

    def test_favorite_pointing_to_alias_not_stale(self, tmp_path, monkeypatch, capsys):
        """A favorite targeting an alias FQCN is live as long as the alias
        exists in alias_index."""
        config_path = str(tmp_path / "config.json")
        monkeypatch.setenv("DAZZLECMD_CONFIG", config_path)
        _write_config(config_path, {"_schema_version": 1, "favorites": {"cc": "claude:cleanup"}})

        engine = AggregatorEngine(is_root=True)
        engine.projects = [_proj("dz:claude-cleanup", "claude-cleanup", "dz")]
        engine._build_fqcn_index()
        engine.fqcn_index.insert_alias("claude:cleanup", "dz:claude-cleanup")

        engine._maybe_emit_stale_favorites_warning()
        assert capsys.readouterr().err == ""

    def test_silenced_kit_suppresses_warning(self, tmp_path, monkeypatch, capsys):
        config_path = str(tmp_path / "config.json")
        monkeypatch.setenv("DAZZLECMD_CONFIG", config_path)
        _write_config(config_path, {
            "_schema_version": 1,
            "favorites": {"gone": "dropped:tool"},
            "silenced_hints": {"kits": ["dropped"]},
        })

        engine = AggregatorEngine(is_root=True)
        engine.projects = [_proj("core:rn", "rn", "core")]
        engine._build_fqcn_index()

        engine._maybe_emit_stale_favorites_warning()
        assert capsys.readouterr().err == ""

    def test_dz_quiet_suppresses_warning(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("DZ_QUIET", "1")
        engine = self._engine_with_projects(
            tmp_path, monkeypatch,
            {"gone": "missing:tool"},
            [_proj("core:rn", "rn", "core")],
        )
        engine._maybe_emit_stale_favorites_warning()
        assert capsys.readouterr().err == ""
