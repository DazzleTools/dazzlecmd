"""Tests for FQCNIndex alias + shortcut features (Phase 4e Commit 1).

Covers the pieces added in v0.7.25:

- ``FQCNIndex.insert_alias()`` — alias registration with §9b shadowing
  check, dangling-target rejection, idempotent same-target, fail-loud
  different-target conflict.
- ``FQCNIndex.insert_canonical()`` §9b mirror — canonical cannot be
  added after an alias claimed the same FQCN.
- Alias-aware ``resolve()`` — alias FQCN dispatches to canonical with
  ``resolution_kind="alias"`` and ``alias_fqcn`` populated.
- Favorites targeting aliases — follow single hop to canonical,
  context records both the alias and kind=favorite.
- ``ResolutionContext`` population — all five ``resolution_kind``
  values emit correctly populated contexts.
- Shortcut index O(1) correctness — kit-qualified shortcut returns
  the same result as the old O(n) list comprehension for both
  unambiguous and ambiguous cases.
"""

import pytest

from dazzlecmd_lib.engine import FQCNCollisionError, FQCNIndex
from dazzlecmd_lib.resolution_context import ResolutionContext


def _proj(fqcn, short, kit, **extra):
    """Minimal project dict for unit tests."""
    p = {
        "_fqcn": fqcn,
        "_short_name": short,
        "_kit_import_name": kit,
        "name": short,
        "namespace": kit,
    }
    p.update(extra)
    return p


# ---------------------------------------------------------------------------
# insert_alias() — validation paths
# ---------------------------------------------------------------------------


class TestInsertAlias:
    """Alias insertion invariants: §9b shadowing, dangling targets,
    idempotent same-target, fail-loud different-target."""

    def test_alias_to_existing_canonical_succeeds(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dazzletools:claude-cleanup", "claude-cleanup", "dazzletools"))
        idx.insert_alias("claude:cleanup", "dazzletools:claude-cleanup")
        assert idx.alias_index["claude:cleanup"] == "dazzletools:claude-cleanup"

    def test_alias_to_missing_canonical_raises_keyerror(self):
        idx = FQCNIndex()
        with pytest.raises(KeyError) as exc_info:
            idx.insert_alias("claude:cleanup", "dazzletools:gone")
        assert "not found in canonical index" in str(exc_info.value)

    def test_alias_to_missing_canonical_includes_source(self):
        idx = FQCNIndex()
        with pytest.raises(KeyError) as exc_info:
            idx.insert_alias(
                "claude:cleanup", "dazzletools:gone",
                source="kits/claude.kit.json",
            )
        assert "kits/claude.kit.json" in str(exc_info.value)

    def test_alias_shadowing_canonical_raises_9b(self):
        """§9b: alias FQCN cannot equal an existing canonical FQCN."""
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dazzletools:claude-cleanup", "claude-cleanup", "dazzletools"))
        idx.insert_canonical(_proj("core:rn", "rn", "core"))
        with pytest.raises(FQCNCollisionError) as exc_info:
            idx.insert_alias("core:rn", "dazzletools:claude-cleanup")
        msg = str(exc_info.value)
        assert "rule 9b" in msg or "shadow" in msg
        assert "core:rn" in msg

    def test_alias_same_target_is_idempotent(self):
        """Two virtual kits both declaring the same alias to the same
        canonical target is a silent no-op."""
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dazzletools:tool_a", "tool_a", "dazzletools"))
        idx.insert_alias("foo:bar", "dazzletools:tool_a")
        # Second call with same target -- no exception, no state change
        idx.insert_alias("foo:bar", "dazzletools:tool_a")
        assert idx.alias_index["foo:bar"] == "dazzletools:tool_a"
        assert len(idx.alias_index) == 1

    def test_alias_different_target_raises(self):
        """First virtual kit wins; a second with a different target is rejected."""
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dazzletools:tool_a", "tool_a", "dazzletools"))
        idx.insert_canonical(_proj("dazzletools:tool_b", "tool_b", "dazzletools"))
        idx.insert_alias("foo:bar", "dazzletools:tool_a")
        with pytest.raises(FQCNCollisionError) as exc_info:
            idx.insert_alias("foo:bar", "dazzletools:tool_b")
        msg = str(exc_info.value)
        assert "already maps to" in msg
        assert "dazzletools:tool_a" in msg
        assert "dazzletools:tool_b" in msg

    def test_alias_different_target_preserves_original(self):
        """After a rejected conflict, the original alias mapping is unchanged."""
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dazzletools:tool_a", "tool_a", "dazzletools"))
        idx.insert_canonical(_proj("dazzletools:tool_b", "tool_b", "dazzletools"))
        idx.insert_alias("foo:bar", "dazzletools:tool_a")
        with pytest.raises(FQCNCollisionError):
            idx.insert_alias("foo:bar", "dazzletools:tool_b")
        assert idx.alias_index["foo:bar"] == "dazzletools:tool_a"
        # Idempotent retry with the original target still works
        idx.insert_alias("foo:bar", "dazzletools:tool_a")
        assert idx.alias_index["foo:bar"] == "dazzletools:tool_a"


class TestInsertCanonicalMirrorsAlias:
    """§9b mirror: canonical cannot be added after an alias claimed the
    same FQCN. (In practice canonicals load first, but the invariant
    holds symmetrically.)"""

    def test_canonical_added_after_alias_raises(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dazzletools:tool_a", "tool_a", "dazzletools"))
        idx.insert_alias("foo:bar", "dazzletools:tool_a")
        with pytest.raises(FQCNCollisionError) as exc_info:
            idx.insert_canonical(_proj("foo:bar", "bar", "foo"))
        assert "collides with existing alias" in str(exc_info.value)


# ---------------------------------------------------------------------------
# resolve() with aliases present
# ---------------------------------------------------------------------------


class TestResolveWithAliases:
    """Alias FQCNs dispatch to canonical; context records the provenance."""

    def _build(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dazzletools:claude-cleanup", "claude-cleanup", "dazzletools"))
        idx.insert_canonical(_proj("dazzletools:claude-session-metadata", "claude-session-metadata", "dazzletools"))
        idx.insert_canonical(_proj("core:rn", "rn", "core"))
        idx.insert_alias("claude:cleanup", "dazzletools:claude-cleanup")
        idx.insert_alias("claude:session-metadata", "dazzletools:claude-session-metadata")
        return idx

    def test_alias_resolves_to_canonical_project(self):
        idx = self._build()
        project, ctx = idx.resolve("claude:cleanup")
        assert project is not None
        assert project["_fqcn"] == "dazzletools:claude-cleanup"

    def test_alias_context_records_alias_and_kind(self):
        idx = self._build()
        project, ctx = idx.resolve("claude:cleanup")
        assert ctx.resolution_kind == "alias"
        assert ctx.original_input == "claude:cleanup"
        assert ctx.canonical_fqcn == "dazzletools:claude-cleanup"
        assert ctx.alias_fqcn == "claude:cleanup"
        assert ctx.notification is None

    def test_canonical_direct_hit_still_works(self):
        idx = self._build()
        project, ctx = idx.resolve("dazzletools:claude-cleanup")
        assert project["_fqcn"] == "dazzletools:claude-cleanup"
        assert ctx.resolution_kind == "canonical"
        assert ctx.alias_fqcn is None

    def test_short_name_resolves_canonical_only(self):
        """§7c: aliases do NOT populate short_index. The alias's short
        form (e.g., 'cleanup') is NOT a candidate — the canonical's
        short name ('claude-cleanup') still is."""
        idx = self._build()
        project, ctx = idx.resolve("claude-cleanup")
        assert project["_fqcn"] == "dazzletools:claude-cleanup"
        # "cleanup" is the alias short, should NOT resolve
        project, ctx = idx.resolve("cleanup")
        assert project is None

    def test_unknown_alias_fqcn_returns_none(self):
        idx = self._build()
        project, ctx = idx.resolve("claude:nonexistent")
        assert project is None


# ---------------------------------------------------------------------------
# Favorites targeting aliases
# ---------------------------------------------------------------------------


class TestFavoritesOnAliases:
    """Favorites can point to an alias FQCN — resolver follows single
    hop to canonical, context records both the alias and kind=favorite."""

    def _build(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dazzletools:claude-cleanup", "claude-cleanup", "dazzletools"))
        idx.insert_alias("claude:cleanup", "dazzletools:claude-cleanup")
        return idx

    def test_favorite_pointing_to_alias_resolves_to_canonical(self):
        idx = self._build()
        project, ctx = idx.resolve(
            "cc", favorites={"cc": "claude:cleanup"},
        )
        assert project is not None
        assert project["_fqcn"] == "dazzletools:claude-cleanup"

    def test_favorite_to_alias_context_records_both(self):
        idx = self._build()
        project, ctx = idx.resolve(
            "cc", favorites={"cc": "claude:cleanup"},
        )
        assert ctx.resolution_kind == "favorite"
        assert ctx.canonical_fqcn == "dazzletools:claude-cleanup"
        assert ctx.alias_fqcn == "claude:cleanup"
        assert ctx.original_input == "cc"


# ---------------------------------------------------------------------------
# ResolutionContext population for each resolution_kind
# ---------------------------------------------------------------------------


class TestResolutionKindPopulation:
    """Verify every resolution_kind emits a correctly populated context.

    Phase 4e Commit 1 handles: canonical, alias, kit_shortcut, favorite,
    precedence. (The "relocated" kind is reserved for Phase 5.)
    """

    def test_kind_canonical(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("core:rn", "rn", "core"))
        project, ctx = idx.resolve("core:rn")
        assert ctx.resolution_kind == "canonical"
        assert ctx.alias_fqcn is None

    def test_kind_alias(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dz:tool", "tool", "dz"))
        idx.insert_alias("virt:tool", "dz:tool")
        project, ctx = idx.resolve("virt:tool")
        assert ctx.resolution_kind == "alias"
        assert ctx.alias_fqcn == "virt:tool"

    def test_kind_kit_shortcut(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("wtf:core:locked", "locked", "wtf"))
        project, ctx = idx.resolve("wtf:locked")
        assert ctx.resolution_kind == "kit_shortcut"
        assert ctx.canonical_fqcn == "wtf:core:locked"

    def test_kind_favorite(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("core:find", "find", "core"))
        idx.insert_canonical(_proj("wtf:core:find", "find", "wtf"))
        project, ctx = idx.resolve("find", favorites={"find": "wtf:core:find"})
        assert ctx.resolution_kind == "favorite"
        assert ctx.canonical_fqcn == "wtf:core:find"

    def test_kind_precedence_single_candidate(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("core:rn", "rn", "core"))
        project, ctx = idx.resolve("rn")
        assert ctx.resolution_kind == "precedence"
        assert ctx.canonical_fqcn == "core:rn"

    def test_kind_precedence_multiple_candidates(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("core:find", "find", "core"))
        idx.insert_canonical(_proj("wtf:core:find", "find", "wtf"))
        project, ctx = idx.resolve("find")
        assert ctx.resolution_kind == "precedence"
        assert ctx.notification is not None


# ---------------------------------------------------------------------------
# shortcut_candidates (precomputed O(1) kit-qualified resolution)
# ---------------------------------------------------------------------------


class TestShortcutCandidates:
    """The precomputed shortcut_candidates index replaces the old O(n)
    list comprehension. Verify it produces identical results."""

    def test_shortcut_populated_on_insert(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("wtf:core:locked", "locked", "wtf"))
        assert ("wtf", "locked") in idx.shortcut_candidates
        assert idx.shortcut_candidates[("wtf", "locked")] == ["wtf:core:locked"]

    def test_shortcut_resolves_2segment_input_to_3segment_canonical(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("wtf:core:locked", "locked", "wtf"))
        project, ctx = idx.resolve("wtf:locked")
        assert project["_fqcn"] == "wtf:core:locked"
        assert ctx.resolution_kind == "kit_shortcut"

    def test_shortcut_ambiguous_picks_alphabetically_first(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("wtf:zeta:find", "find", "wtf"))
        idx.insert_canonical(_proj("wtf:alpha:find", "find", "wtf"))
        project, ctx = idx.resolve("wtf:find")
        # Sorted alphabetically -- alpha wins
        assert project["_fqcn"] == "wtf:alpha:find"
        assert ctx.notification is not None
        assert "ambiguous" in ctx.notification.lower()
        assert "wtf:alpha:find" in ctx.notification
        assert "wtf:zeta:find" in ctx.notification

    def test_shortcut_no_match_returns_none(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj("core:rn", "rn", "core"))
        project, ctx = idx.resolve("wtf:nonexistent")
        assert project is None
        assert ctx is None

    def test_shortcut_index_ordering_stable_under_insert_order(self):
        """Regardless of insertion order, alphabetical tiebreak is stable."""
        idx1 = FQCNIndex()
        idx1.insert_canonical(_proj("wtf:alpha:find", "find", "wtf"))
        idx1.insert_canonical(_proj("wtf:zeta:find", "find", "wtf"))
        p1, _ = idx1.resolve("wtf:find")

        idx2 = FQCNIndex()
        idx2.insert_canonical(_proj("wtf:zeta:find", "find", "wtf"))
        idx2.insert_canonical(_proj("wtf:alpha:find", "find", "wtf"))
        p2, _ = idx2.resolve("wtf:find")

        assert p1["_fqcn"] == p2["_fqcn"] == "wtf:alpha:find"

    def test_shortcut_does_not_match_aliases(self):
        """Shortcut path searches canonical only. Aliases had their
        exact-match chance earlier in resolve()."""
        idx = FQCNIndex()
        idx.insert_canonical(_proj("dz:real-tool", "real-tool", "dz"))
        idx.insert_alias("virt:anything", "dz:real-tool")
        # "virt:anything" is an alias FQCN, not a shortcut
        project, ctx = idx.resolve("virt:anything")
        assert ctx.resolution_kind == "alias"
        # "virt:something-else" has no canonical or alias; shortcut should miss
        project, ctx = idx.resolve("virt:something-else")
        assert project is None


# ---------------------------------------------------------------------------
# Engine.find_project helper
# ---------------------------------------------------------------------------


class TestEngineFindProject:
    """The find_project helper is the canonical lookup for callers —
    short names, canonical FQCNs, alias FQCNs, and kit shortcuts all
    route through it uniformly."""

    def _engine_with_aliases(self):
        from dazzlecmd_lib.engine import AggregatorEngine
        engine = AggregatorEngine(is_root=True)
        engine.projects = [
            _proj("dazzletools:claude-cleanup", "claude-cleanup", "dazzletools"),
            _proj("core:rn", "rn", "core"),
        ]
        engine._build_fqcn_index()
        # Manually add an alias for the test (Commit 2 will wire this
        # through the loader automatically)
        engine.fqcn_index.insert_alias(
            "claude:cleanup", "dazzletools:claude-cleanup"
        )
        return engine

    def test_find_project_by_short_name(self):
        engine = self._engine_with_aliases()
        project, ctx = engine.find_project("rn")
        assert project["_fqcn"] == "core:rn"

    def test_find_project_by_canonical_fqcn(self):
        engine = self._engine_with_aliases()
        project, ctx = engine.find_project("dazzletools:claude-cleanup")
        assert project["_fqcn"] == "dazzletools:claude-cleanup"

    def test_find_project_by_alias_fqcn(self):
        engine = self._engine_with_aliases()
        project, ctx = engine.find_project("claude:cleanup")
        assert project["_fqcn"] == "dazzletools:claude-cleanup"
        assert ctx.resolution_kind == "alias"

    def test_find_project_unknown_returns_none(self):
        engine = self._engine_with_aliases()
        project, ctx = engine.find_project("ghost")
        assert project is None
        assert ctx is None
