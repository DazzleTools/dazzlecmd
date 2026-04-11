"""Unit tests for the FQCN index and resolver in dazzlecmd.engine.

Covers the Phase 2 additions:
    - FQCNIndex: insert, resolve (exact FQCN, short-name, precedence)
    - AggregatorEngine.resolve_command() integration
    - AggregatorEngine.get_kit_precedence() config reading
    - CircularDependencyError and FQCNCollisionError

Recursive discovery tests live in test_engine_recursive.py (separate file
because they need a filesystem fixture).
"""

import json
import os
import tempfile

import pytest

from dazzlecmd.engine import (
    AggregatorEngine,
    CircularDependencyError,
    FQCNCollisionError,
    FQCNIndex,
)


def _proj(fqcn, short, kit, description=""):
    """Build a minimal project dict for tests."""
    return {
        "name": short,
        "_fqcn": fqcn,
        "_short_name": short,
        "_kit_import_name": kit,
        "_dir": f"/fake/{fqcn.replace(':', '/')}",
        "description": description,
    }


# ---------------------------------------------------------------------------
# FQCNIndex
# ---------------------------------------------------------------------------


class TestFQCNIndex:

    def _build(self):
        idx = FQCNIndex()
        idx.insert(_proj("core:rn", "rn", "core"))
        idx.insert(_proj("core:fixpath", "fixpath", "core"))
        idx.insert(_proj("core:find", "find", "core"))
        idx.insert(_proj("dazzletools:dos2unix", "dos2unix", "dazzletools"))
        idx.insert(_proj("wtf:core:restarted", "restarted", "wtf"))
        idx.insert(_proj("wtf:core:find", "find", "wtf"))  # collides with core:find
        return idx

    def test_exact_fqcn_match(self):
        idx = self._build()
        project, note = idx.resolve("core:fixpath")
        assert project is not None
        assert project["_fqcn"] == "core:fixpath"
        assert note is None

    def test_exact_fqcn_three_part(self):
        idx = self._build()
        project, note = idx.resolve("wtf:core:restarted")
        assert project is not None
        assert project["_fqcn"] == "wtf:core:restarted"
        assert note is None

    def test_exact_fqcn_no_match_returns_none(self):
        idx = self._build()
        project, note = idx.resolve("core:ghost")
        assert project is None
        assert note is None

    def test_unambiguous_short_name(self):
        idx = self._build()
        project, note = idx.resolve("fixpath")
        assert project["_fqcn"] == "core:fixpath"
        assert note is None

    def test_unambiguous_short_name_from_imported_kit(self):
        idx = self._build()
        project, note = idx.resolve("restarted")
        assert project["_fqcn"] == "wtf:core:restarted"
        assert note is None

    def test_colliding_short_name_default_precedence_core_wins(self):
        idx = self._build()
        project, note = idx.resolve("find")
        assert project["_fqcn"] == "core:find"
        assert note is not None
        assert "core:find" in note
        assert "wtf" in note
        assert "Use 'dz core:find'" in note

    def test_colliding_short_name_custom_precedence(self):
        idx = self._build()
        project, note = idx.resolve("find", precedence=["wtf", "core"])
        assert project["_fqcn"] == "wtf:core:find"
        assert note is not None
        assert "wtf:core:find" in note

    def test_short_name_no_match_returns_none(self):
        idx = self._build()
        project, note = idx.resolve("nonexistent")
        assert project is None
        assert note is None

    def test_fqcn_collision_raises(self):
        idx = FQCNIndex()
        idx.insert(_proj("core:rn", "rn", "core"))
        with pytest.raises(FQCNCollisionError) as exc_info:
            idx.insert(_proj("core:rn", "rn", "core"))
        assert "core:rn" in str(exc_info.value)

    def test_unknown_kit_in_precedence_is_tolerated(self):
        idx = self._build()
        project, _ = idx.resolve("find", precedence=["ghost", "core"])
        assert project["_fqcn"] == "core:find"

    def test_all_projects_returns_in_insertion_order(self):
        idx = self._build()
        projects = idx.all_projects()
        assert len(projects) == 6
        assert projects[0]["_fqcn"] == "core:rn"
        assert projects[-1]["_fqcn"] == "wtf:core:find"

    def test_kit_order_tracked(self):
        idx = self._build()
        assert idx.kit_order == ["core", "dazzletools", "wtf"]

    def test_three_way_collision_ordering(self):
        idx = FQCNIndex()
        idx.insert(_proj("wtf:status", "status", "wtf"))
        idx.insert(_proj("dazzletools:status", "status", "dazzletools"))
        idx.insert(_proj("core:status", "status", "core"))
        project, note = idx.resolve("status")
        # Default precedence: core first, then dazzletools, then wtf
        assert project["_fqcn"] == "core:status"
        assert "dazzletools" in note
        assert "wtf" in note


# ---------------------------------------------------------------------------
# AggregatorEngine.resolve_command()
# ---------------------------------------------------------------------------


class TestResolveCommand:

    def _engine_with_projects(self):
        engine = AggregatorEngine(is_root=True)
        engine.projects = [
            _proj("core:rn", "rn", "core"),
            _proj("core:find", "find", "core"),
            _proj("wtf:core:find", "find", "wtf"),
        ]
        engine._build_fqcn_index()
        return engine

    def test_resolve_exact_fqcn(self):
        engine = self._engine_with_projects()
        project, note = engine.resolve_command("core:rn")
        assert project["_fqcn"] == "core:rn"
        assert note is None

    def test_resolve_unambiguous_short(self):
        engine = self._engine_with_projects()
        project, note = engine.resolve_command("rn")
        assert project["_fqcn"] == "core:rn"
        assert note is None

    def test_resolve_colliding_short_default_precedence(self):
        engine = self._engine_with_projects()
        project, note = engine.resolve_command("find")
        assert project["_fqcn"] == "core:find"
        assert note is not None

    def test_resolve_nonexistent(self):
        engine = self._engine_with_projects()
        project, note = engine.resolve_command("ghost")
        assert project is None
        assert note is None


# ---------------------------------------------------------------------------
# AggregatorEngine.get_kit_precedence() config reading
# ---------------------------------------------------------------------------


class TestGetKitPrecedence:

    def test_no_config_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        engine = AggregatorEngine()
        assert engine.get_kit_precedence() is None

    def test_config_without_kit_precedence_returns_none(self, monkeypatch, tmp_path):
        config_dir = tmp_path / ".dazzlecmd"
        config_dir.mkdir()
        (config_dir / "config.json").write_text('{"other_key": "value"}', encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        engine = AggregatorEngine()
        assert engine.get_kit_precedence() is None

    def test_config_with_kit_precedence_returns_list(self, monkeypatch, tmp_path):
        config_dir = tmp_path / ".dazzlecmd"
        config_dir.mkdir()
        config = {"kit_precedence": ["wtf", "core", "dazzletools"]}
        (config_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        engine = AggregatorEngine()
        assert engine.get_kit_precedence() == ["wtf", "core", "dazzletools"]

    def test_malformed_config_returns_none(self, monkeypatch, tmp_path):
        config_dir = tmp_path / ".dazzlecmd"
        config_dir.mkdir()
        (config_dir / "config.json").write_text('{bad json', encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        engine = AggregatorEngine()
        assert engine.get_kit_precedence() is None

    def test_kit_precedence_non_list_returns_none(self, monkeypatch, tmp_path):
        config_dir = tmp_path / ".dazzlecmd"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            '{"kit_precedence": "core"}', encoding="utf-8"
        )
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        engine = AggregatorEngine()
        assert engine.get_kit_precedence() is None


# ---------------------------------------------------------------------------
# CircularDependencyError
# ---------------------------------------------------------------------------


class TestCircularDependencyError:

    def test_is_exception(self):
        assert issubclass(CircularDependencyError, Exception)

    def test_can_be_raised_with_message(self):
        with pytest.raises(CircularDependencyError) as exc_info:
            raise CircularDependencyError("cycle: a -> b -> a")
        assert "cycle" in str(exc_info.value)
