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
# FQCNIndex.resolve() with kit-qualified shortcuts (Phase 3)
# ---------------------------------------------------------------------------


class TestKitQualifiedResolution:
    """Two-segment names like 'wtf:locked' resolve by searching within
    the kit for a tool matching the suffix."""

    def _build(self):
        idx = FQCNIndex()
        idx.insert(_proj("core:rn", "rn", "core"))
        idx.insert(_proj("core:fixpath", "fixpath", "core"))
        idx.insert(_proj("wtf:core:locked", "locked", "wtf"))
        idx.insert(_proj("wtf:core:restarted", "restarted", "wtf"))
        return idx

    def test_kit_qualified_resolves_unambiguous(self):
        idx = self._build()
        project, note = idx.resolve("wtf:locked")
        assert project is not None
        assert project["_fqcn"] == "wtf:core:locked"
        assert note is None

    def test_kit_qualified_restarted(self):
        idx = self._build()
        project, note = idx.resolve("wtf:restarted")
        assert project is not None
        assert project["_fqcn"] == "wtf:core:restarted"
        assert note is None

    def test_exact_fqcn_still_takes_priority(self):
        """Two-segment exact matches (like core:fixpath) still resolve
        via exact match, not kit-qualified search."""
        idx = self._build()
        project, note = idx.resolve("core:fixpath")
        assert project is not None
        assert project["_fqcn"] == "core:fixpath"
        assert note is None

    def test_kit_qualified_not_found(self):
        idx = self._build()
        project, note = idx.resolve("wtf:nonexistent")
        assert project is None

    def test_nonexistent_kit_returns_none(self):
        idx = self._build()
        project, note = idx.resolve("ghost:locked")
        assert project is None

    def test_kit_qualified_ambiguous(self):
        """Two tools with same name in different namespaces within one kit."""
        idx = FQCNIndex()
        idx.insert(_proj("mykit:ns1:shared", "shared", "mykit"))
        idx.insert(_proj("mykit:ns2:shared", "shared", "mykit"))
        project, note = idx.resolve("mykit:shared")
        assert project is not None  # picks one (first alphabetically)
        assert note is not None  # notification about ambiguity
        assert "ambiguous" in note.lower()
        assert "mykit:ns1:shared" in note
        assert "mykit:ns2:shared" in note

    def test_three_segment_mismatch_returns_none(self):
        """A 3-segment name that doesn't match any FQCN is NOT treated
        as a kit-qualified shortcut — only 2-segment names trigger the
        kit-scoped search."""
        idx = self._build()
        project, note = idx.resolve("wtf:wrong:locked")
        assert project is None


# ---------------------------------------------------------------------------
# FQCNIndex.resolve() with favorites (Phase 3)
# ---------------------------------------------------------------------------


class TestFavoritesResolution:
    """Favorites bypass precedence when set and target exists."""

    def _build(self):
        idx = FQCNIndex()
        idx.insert(_proj("core:find", "find", "core"))
        idx.insert(_proj("wtf:core:find", "find", "wtf"))
        idx.insert(_proj("core:rn", "rn", "core"))
        return idx

    def test_favorite_wins_over_precedence(self):
        idx = self._build()
        # Without favorite: core wins (default precedence)
        project, note = idx.resolve("find")
        assert project["_fqcn"] == "core:find"

        # With favorite pointing at wtf: wtf wins, no notification
        project, note = idx.resolve("find", favorites={"find": "wtf:core:find"})
        assert project["_fqcn"] == "wtf:core:find"
        assert note is None

    def test_favorite_no_collision_dispatches_silently(self):
        """If only one tool has the short name, favorite is redundant but
        should still dispatch silently."""
        idx = self._build()
        project, note = idx.resolve("rn", favorites={"rn": "core:rn"})
        assert project["_fqcn"] == "core:rn"
        assert note is None

    def test_stale_favorite_falls_through_with_warning(self):
        """Favorite pointing at a non-existent FQCN warns and falls through
        to precedence resolution."""
        idx = self._build()
        project, note = idx.resolve(
            "find", favorites={"find": "ghost:find"}
        )
        assert project["_fqcn"] == "core:find"  # fell through to precedence
        assert note is not None
        assert "warning" in note.lower()
        assert "ghost:find" in note

    def test_stale_favorite_with_single_candidate(self):
        idx = self._build()
        project, note = idx.resolve("rn", favorites={"rn": "ghost:rn"})
        assert project["_fqcn"] == "core:rn"
        assert note is not None
        assert "warning" in note.lower()

    def test_stale_favorite_no_match_returns_none(self):
        idx = self._build()
        project, note = idx.resolve(
            "nonexistent", favorites={"nonexistent": "ghost:nonexistent"}
        )
        assert project is None
        assert note is not None
        assert "warning" in note.lower()

    def test_favorite_not_applied_to_unrelated_short_names(self):
        idx = self._build()
        project, note = idx.resolve(
            "find", favorites={"other_name": "ghost:other"}
        )
        # "find" has no favorite -- normal precedence applies
        assert project["_fqcn"] == "core:find"
        # Notification is the collision notification, not a stale-favorite warning
        assert "also in" in note

    def test_favorite_fqcn_match_still_bypasses_favorites(self):
        """Explicit FQCN input always works and is unaffected by favorites."""
        idx = self._build()
        project, note = idx.resolve(
            "wtf:core:find", favorites={"find": "core:find"}
        )
        assert project["_fqcn"] == "wtf:core:find"
        assert note is None


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
    """Tests for get_kit_precedence() backwards-compat wrapper.

    Uses DAZZLECMD_CONFIG env var for reliable isolation (HOME/USERPROFILE
    monkeypatching is flaky on Windows because os.path.expanduser doesn't
    always honor monkeypatched env vars in all hook/subprocess contexts).
    """

    def test_no_config_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        engine = AggregatorEngine()
        assert engine.get_kit_precedence() is None

    def test_config_without_kit_precedence_returns_none(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"other_key": "value"}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine.get_kit_precedence() is None

    def test_config_with_kit_precedence_returns_list(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        config = {"kit_precedence": ["wtf", "core", "dazzletools"]}
        config_path.write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine.get_kit_precedence() == ["wtf", "core", "dazzletools"]

    def test_malformed_config_returns_none(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text('{bad json', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        assert engine.get_kit_precedence() is None

    def test_kit_precedence_non_list_returns_none(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            '{"kit_precedence": "core"}', encoding="utf-8"
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
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
