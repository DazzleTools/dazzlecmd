"""Convergence invariant: all user-typed forms of a tool name resolve
to the same canonical project.

For a tool with canonical FQCN ``dazzletools:claude-cleanup`` aliased
as ``claude:cleanup`` via a virtual kit ``claude``, ALL of the
following inputs must resolve to the same canonical project:

1. **Canonical FQCN**: ``dazzletools:claude-cleanup`` (the on-disk
   truth — kit + canonical short with `-` separator)
2. **Canonical short**: ``claude-cleanup`` (the canonical's last segment)
3. **Alias FQCN**: ``claude:cleanup`` (declared in the virtual kit's
   ``name_rewrite``)
4. **Alias short**: ``cleanup`` (rule 7c relaxation: alias shorts
   populate ``short_index``)
5. **Qualified alias**: ``dazzletools:claude:cleanup`` (the form
   shown in sectioned ``dz list`` output -- canonical_kit_path +
   virtual_kit_name + alias_short)

Plus, for tools in a nested-canonical kit (e.g., ``wtf:core:locked``):

6. **Kit-qualified shortcut**: ``wtf:locked`` (drop the inner
   ``core`` segment when unambiguous)

This file encodes that invariant as test cases. If any of these
resolution paths fails to converge, the user-facing display is
inconsistent with the dispatch model.
"""

import pytest

from dazzlecmd_lib.engine import FQCNIndex


def _proj(fqcn, short, kit, **extra):
    p = {
        "_fqcn": fqcn,
        "_short_name": short,
        "_kit_import_name": kit,
        "name": short,
        "namespace": kit,
    }
    p.update(extra)
    return p


class TestAllPathsConvergeToCanonical:
    """For a typical root virtual-kit setup, verify all five user-typed
    forms of the same tool resolve to the same canonical project."""

    @pytest.fixture
    def index(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj(
            "dazzletools:claude-cleanup", "claude-cleanup", "dazzletools"
        ))
        idx.insert_alias("claude:cleanup", "dazzletools:claude-cleanup")
        return idx

    def test_canonical_fqcn(self, index):
        project, ctx = index.resolve("dazzletools:claude-cleanup")
        assert project["_fqcn"] == "dazzletools:claude-cleanup"
        assert ctx.resolution_kind == "canonical"

    def test_canonical_short(self, index):
        project, ctx = index.resolve("claude-cleanup")
        assert project["_fqcn"] == "dazzletools:claude-cleanup"
        # Canonical short with no aliases would be "precedence";
        # with rule 7c relaxation, alias short collisions don't
        # affect canonical short uniqueness here.
        assert ctx.resolution_kind in ("precedence", "favorite")

    def test_alias_fqcn(self, index):
        project, ctx = index.resolve("claude:cleanup")
        assert project["_fqcn"] == "dazzletools:claude-cleanup"
        assert ctx.resolution_kind == "alias"
        assert ctx.alias_fqcn == "claude:cleanup"

    def test_alias_short_via_rule_7c(self, index):
        """Rule 7c: alias shorts populate short_index."""
        project, ctx = index.resolve("cleanup")
        assert project["_fqcn"] == "dazzletools:claude-cleanup"
        # Resolution mode for short-name with one candidate is
        # "precedence" (single-candidate path)
        assert ctx.resolution_kind == "precedence"

    def test_qualified_alias(self, index):
        """v0.7.28: the qualified form shown in `dz list` sections is
        invocable. ``dazzletools:claude:cleanup`` resolves via the
        alias ``claude:cleanup``."""
        project, ctx = index.resolve("dazzletools:claude:cleanup")
        assert project["_fqcn"] == "dazzletools:claude-cleanup"
        assert ctx.resolution_kind == "qualified_alias"
        assert ctx.alias_fqcn == "claude:cleanup"
        assert ctx.original_input == "dazzletools:claude:cleanup"

    def test_all_five_forms_resolve_to_same_project_object(self, index):
        """Strongest invariant: every form returns the SAME project
        dict (same object identity)."""
        canonical, _ = index.resolve("dazzletools:claude-cleanup")
        canonical_short, _ = index.resolve("claude-cleanup")
        alias_fqcn, _ = index.resolve("claude:cleanup")
        alias_short, _ = index.resolve("cleanup")
        qualified, _ = index.resolve("dazzletools:claude:cleanup")
        # All same project (same canonical_index entry)
        assert canonical is canonical_short
        assert canonical is alias_fqcn
        assert canonical is alias_short
        assert canonical is qualified


class TestNestedCanonicalConvergence:
    """For a tool in a deeper canonical kit (e.g., ``wtf:core:locked``),
    verify the kit-qualified shortcut form ``wtf:locked`` converges
    with the canonical FQCN."""

    @pytest.fixture
    def index(self):
        idx = FQCNIndex()
        idx.insert_canonical(_proj(
            "wtf:core:locked", "locked", "wtf"
        ))
        return idx

    def test_canonical_fqcn(self, index):
        project, ctx = index.resolve("wtf:core:locked")
        assert project["_fqcn"] == "wtf:core:locked"
        assert ctx.resolution_kind == "canonical"

    def test_kit_qualified_shortcut(self, index):
        """``wtf:locked`` drops the inner ``core`` segment. Must
        resolve to the same canonical."""
        project, ctx = index.resolve("wtf:locked")
        assert project["_fqcn"] == "wtf:core:locked"
        assert ctx.resolution_kind == "kit_shortcut"

    def test_canonical_short(self, index):
        project, ctx = index.resolve("locked")
        assert project["_fqcn"] == "wtf:core:locked"

    def test_all_three_forms_same_object(self, index):
        canonical, _ = index.resolve("wtf:core:locked")
        shortcut, _ = index.resolve("wtf:locked")
        short, _ = index.resolve("locked")
        assert canonical is shortcut is short


class TestQualifiedAliasEdgeCases:
    """Verify the qualified-alias path doesn't create false positives."""

    def test_no_match_when_prefix_does_not_match(self):
        """``foo:claude:cleanup`` should NOT resolve when the canonical
        kit is ``dazzletools`` (not ``foo``)."""
        idx = FQCNIndex()
        idx.insert_canonical(_proj(
            "dazzletools:claude-cleanup", "claude-cleanup", "dazzletools"
        ))
        idx.insert_alias("claude:cleanup", "dazzletools:claude-cleanup")
        project, ctx = idx.resolve("foo:claude:cleanup")
        assert project is None
        assert ctx is None

    def test_no_match_when_alias_short_differs(self):
        """``dazzletools:claude:nonexistent`` should NOT resolve --
        no alias ``claude:nonexistent`` exists."""
        idx = FQCNIndex()
        idx.insert_canonical(_proj(
            "dazzletools:claude-cleanup", "claude-cleanup", "dazzletools"
        ))
        idx.insert_alias("claude:cleanup", "dazzletools:claude-cleanup")
        project, ctx = idx.resolve("dazzletools:claude:nonexistent")
        assert project is None
        assert ctx is None

    def test_canonical_fqcn_takes_priority_over_qualified_alias(self):
        """If a 3-segment input happens to be a canonical FQCN (e.g.,
        ``wtf:core:locked``), the canonical hit wins -- we don't
        misinterpret it as a qualified alias."""
        idx = FQCNIndex()
        idx.insert_canonical(_proj(
            "wtf:core:locked", "locked", "wtf"
        ))
        # Add a (different) virtual kit and alias
        idx.insert_canonical(_proj(
            "dazzletools:claude-cleanup", "claude-cleanup", "dazzletools"
        ))
        idx.insert_alias("claude:cleanup", "dazzletools:claude-cleanup")
        project, ctx = idx.resolve("wtf:core:locked")
        assert project["_fqcn"] == "wtf:core:locked"
        assert ctx.resolution_kind == "canonical"

    def test_nested_virtual_alias_fqcn_uses_alias_path_not_qualified(self):
        """A nested virtual kit's alias FQCN (e.g., ``wtf:claude:why-locked``
        from cross-aggregator Option A) should be a direct alias_index
        hit, NOT a qualified-alias resolution."""
        idx = FQCNIndex()
        idx.insert_canonical(_proj(
            "wtf:core:locked", "locked", "wtf"
        ))
        # Nested virtual kit with already-prefixed name
        idx.insert_alias("wtf:claude:why-locked", "wtf:core:locked")
        project, ctx = idx.resolve("wtf:claude:why-locked")
        assert project["_fqcn"] == "wtf:core:locked"
        assert ctx.resolution_kind == "alias"  # direct alias hit, NOT qualified
