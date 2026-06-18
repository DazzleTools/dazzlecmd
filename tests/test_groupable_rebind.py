"""Phase 1 (alias) tests for ``Groupable.rebind`` -- the first live
state-transition operator (#84 behavioral phase; the rebind PoC).

Validates against a REAL ``FQCNIndex`` (not a mock): the context+receipt+
invariant pattern, the round-trip property (``rebind o rebind^-1 = identity``),
the receiver precondition + single-hop/existence guards, idempotence, and
``short_index`` coherence after a repoint (the corruption risk flagged in the
DWP hole-review H2).
"""
import os
import tempfile

import pytest

from dazzlecmd_lib.engine import FQCNIndex
from dazzlecmd_lib.entity import build_entity
from dazzlecmd_lib.contexts import (
    AliasRebindContext,
    CriticalityBoundaryError,
    RebindError,
    RebindReceipt,
    RebindInvariant,
)
from dazzlecmd_lib.states import assert_round_trip, build_default_registry
from dazzlecmd_lib.testing import make_tool


def _sandbox_tool(tmpdir, *, with_url=True, gitmodules=False):
    """A tool entity at ``tmpdir/projects/core/mytool`` (an embedded dir), with
    an optional ``source.url`` and an optional ``.gitmodules`` entry (the latter
    makes ``detect_tool_state`` report SUBMODULE -- i.e. in-orbit)."""
    tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
    os.makedirs(tool_dir)
    with open(os.path.join(tool_dir, "mytool.py"), "w", encoding="utf-8") as f:
        f.write("# placeholder")
    data = {
        "name": "mytool", "namespace": "core", "version": "1.0.0",
        "description": "sandbox", "directory": tool_dir, "_fqcn": "core:mytool",
        "runtime": {"type": "python", "script_path": "mytool.py"},
    }
    if with_url:
        data["source"] = {"url": "https://example.com/mytool.git"}
    if gitmodules:
        with open(os.path.join(tmpdir, ".gitmodules"), "w", encoding="utf-8") as f:
            f.write('[submodule "projects/core/mytool"]\n'
                    '\tpath = projects/core/mytool\n'
                    '\turl = https://example.com/mytool.git\n')
    return build_entity(data, entity_type="tool")


def _idx_two_canonicals_one_alias():
    """Two canonicals (both short 'cleanup') + alias claude:cleanup -> c1."""
    idx = FQCNIndex()
    c1 = make_tool(name="cleanup", namespace="dazzletools",
                   _fqcn="dazzletools:cleanup", _short_name="cleanup",
                   _kit_import_name="dazzletools")
    c2 = make_tool(name="cleanup", namespace="core",
                   _fqcn="core:cleanup", _short_name="cleanup",
                   _kit_import_name="core")
    idx.insert_canonical(c1)
    idx.insert_canonical(c2)
    idx.insert_alias("claude:cleanup", "dazzletools:cleanup")
    return idx, c1, c2


class TestAliasRebindRoundTrip:
    def test_repoint_and_receipt(self):
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        ctx = AliasRebindContext(idx, alias="claude:cleanup")
        receipt = c1.rebind("core:cleanup", context=ctx)

        assert isinstance(receipt, RebindReceipt)
        assert idx.alias_index["claude:cleanup"] == "core:cleanup"
        assert receipt.sub_kind == "alias"
        assert receipt.previous_state == "dazzletools:cleanup"
        assert receipt.new_state == "core:cleanup"
        assert receipt.reversible is True
        assert isinstance(receipt.invariant, RebindInvariant)
        assert receipt.invariant.conserved_quantity_name == "single_hop_rule"
        # C1: the binding owner's canonical identity is UNCHANGED by rebind.
        assert c1.fqcn == "dazzletools:cleanup"

    def test_round_trip_restores_identity(self):
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        ctx = AliasRebindContext(idx, alias="claude:cleanup")

        r = c1.rebind("core:cleanup", context=ctx)
        # Inverse: receiver = current owner (the alias now points at c2).
        r2 = c2.rebind(r.previous_state, context=ctx)

        assert idx.alias_index["claude:cleanup"] == "dazzletools:cleanup"
        assert r2.new_state == "dazzletools:cleanup"
        # C1 unchanged for both ends across the full round-trip.
        assert c1.fqcn == "dazzletools:cleanup"
        assert c2.fqcn == "core:cleanup"

    def test_idempotent_same_target(self):
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        ctx = AliasRebindContext(idx, alias="claude:cleanup")
        r = c1.rebind("dazzletools:cleanup", context=ctx)  # current target
        assert idx.alias_index["claude:cleanup"] == "dazzletools:cleanup"
        assert r.previous_state == "dazzletools:cleanup"
        assert r.reversible is True

    def test_resolve_follows_repoint(self):
        """End-to-end: after rebind, resolving the alias FQCN returns the new
        canonical (the strongest coherence check)."""
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        proj, _ = idx.resolve("claude:cleanup")
        assert proj.fqcn == "dazzletools:cleanup"

        c1.rebind("core:cleanup", context=AliasRebindContext(idx, "claude:cleanup"))

        proj2, rctx = idx.resolve("claude:cleanup")
        assert proj2.fqcn == "core:cleanup"
        assert rctx.resolution_kind == "alias"


class TestAliasRebindGuards:
    def test_receiver_must_own_alias(self):
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        ctx = AliasRebindContext(idx, alias="claude:cleanup")
        # c2 does NOT currently own the alias (it points at c1).
        with pytest.raises(ValueError, match="receiver mismatch"):
            c2.rebind("core:cleanup", context=ctx)

    def test_target_must_be_canonical(self):
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        ctx = AliasRebindContext(idx, alias="claude:cleanup")
        with pytest.raises(KeyError):
            c1.rebind("nonexistent:tool", context=ctx)

    def test_unknown_alias(self):
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        ctx = AliasRebindContext(idx, alias="ghost:alias")
        with pytest.raises(KeyError):
            c1.rebind("core:cleanup", context=ctx)

    def test_rebind_requires_context(self):
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        with pytest.raises(TypeError):
            c1.rebind("core:cleanup", context=None)


class TestShortIndexCoherence:
    def test_short_rebookkeeping_drops_unjustified_old(self):
        """When the old canonical is in the alias-short bucket ONLY because of
        the alias (not its own short), repoint must drop it and add the new
        canonical -- otherwise short-name resolution stays stale (H2)."""
        idx = FQCNIndex()
        c1 = make_tool(name="cleanup", namespace="dazzletools",
                       _fqcn="dazzletools:cleanup", _short_name="cleanup",
                       _kit_import_name="dazzletools")
        c2 = make_tool(name="restart", namespace="core",
                       _fqcn="core:restart", _short_name="restart",
                       _kit_import_name="core")
        idx.insert_canonical(c1)
        idx.insert_canonical(c2)
        # alias short "foo" contributes its canonical (dazzletools:cleanup),
        # which is NOT justified by its own short ("cleanup").
        idx.insert_alias("claude:foo", "dazzletools:cleanup")
        assert idx.short_index["foo"] == ["dazzletools:cleanup"]

        c1.rebind("core:restart", context=AliasRebindContext(idx, "claude:foo"))

        # "foo" now maps only to the new canonical; the old one was dropped.
        assert idx.short_index["foo"] == ["core:restart"]
        # ...but dazzletools:cleanup is still reachable by its OWN short.
        assert "dazzletools:cleanup" in idx.short_index["cleanup"]

    def test_short_keeps_old_when_justified_by_own_short(self):
        """When the old canonical's own short == the alias short, it stays in
        the bucket after the repoint (justified)."""
        idx, c1, c2 = _idx_two_canonicals_one_alias()  # both own short "cleanup"
        c1.rebind("core:cleanup", context=AliasRebindContext(idx, "claude:cleanup"))
        bucket = idx.short_index["cleanup"]
        assert "core:cleanup" in bucket          # new target present
        assert "dazzletools:cleanup" in bucket   # kept: it is its own short

    def test_short_name_resolution_follows_repoint(self):
        """Behavioral: resolving the alias SHORT after a repoint must dispatch
        to the NEW canonical -- the user-visible consequence of the bucket
        re-bookkeeping (a raw alias_index poke would leave this stale)."""
        idx = FQCNIndex()
        c1 = make_tool(name="cleanup", namespace="dazzletools",
                       _fqcn="dazzletools:cleanup", _short_name="cleanup",
                       _kit_import_name="dazzletools")
        c2 = make_tool(name="restart", namespace="core",
                       _fqcn="core:restart", _short_name="restart",
                       _kit_import_name="core")
        idx.insert_canonical(c1)
        idx.insert_canonical(c2)
        idx.insert_alias("claude:foo", "dazzletools:cleanup")

        proj, _ = idx.resolve("foo")
        assert proj.fqcn == "dazzletools:cleanup"

        c1.rebind("core:restart", context=AliasRebindContext(idx, "claude:foo"))

        proj2, _ = idx.resolve("foo")
        assert proj2.fqcn == "core:restart"

    def test_repoint_restamps_alias_provenance(self):
        """_alias_sources is consumed by display surfaces (dz list --show
        alias); after a repoint the original declaration no longer describes
        the mapping, so provenance is re-stamped to "rebind"."""
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        idx._alias_sources["claude:cleanup"] = "virtual-claude.kit.json"

        c1.rebind("core:cleanup", context=AliasRebindContext(idx, "claude:cleanup"))

        assert idx._alias_sources["claude:cleanup"] == "rebind"


class TestModeRebind:
    """Phase 2 -- the SAME `rebind` verb over a different context
    (ModeRebindContext): dev<->publish coupling change with the criticality
    boundary. Filesystem ops run in --dry-run (no mutation, no git network)."""

    def test_invalid_target(self):
        from dazzlecmd_lib.mode import ModeRebindContext
        with tempfile.TemporaryDirectory() as tmp:
            tool = _sandbox_tool(tmp)
            ctx = ModeRebindContext(project_root=tmp, tools_dir="projects", dry_run=True)
            with pytest.raises(ValueError, match="dev"):
                tool.rebind("sideways", context=ctx)

    def test_refused_when_no_remote_url(self):
        """Criticality (H3): no derivable remote URL -> the dev<->publish
        invariant can't be preserved -> CriticalityBoundaryError (pre-flight,
        before any filesystem touch)."""
        from dazzlecmd_lib.mode import ModeRebindContext
        with tempfile.TemporaryDirectory() as tmp:
            tool = _sandbox_tool(tmp, with_url=False)
            ctx = ModeRebindContext(project_root=tmp, tools_dir="projects", dry_run=True)
            with pytest.raises(CriticalityBoundaryError, match="irreversible"):
                tool.rebind("publish", context=ctx)

    def test_publish_dry_run_receipt_one_way_entry(self):
        """Embedded + URL: publish is PERMITTED (URL derivable) but ONE-WAY --
        reversible=False (entering the orbit from outside is a mini-graduation, H3).
        The receipt carries the conserved invariant (the remote URL)."""
        from dazzlecmd_lib.mode import ModeRebindContext
        with tempfile.TemporaryDirectory() as tmp:
            tool = _sandbox_tool(tmp, with_url=True)  # EMBEDDED + url
            ctx = ModeRebindContext(project_root=tmp, tools_dir="projects", dry_run=True)
            r = tool.rebind("publish", context=ctx)
            assert r.sub_kind == "mode-switch"
            assert r.new_state == "publish"
            assert r.invariant.conserved_quantity_name == "remote_url"
            assert r.invariant.conserved_value == "https://example.com/mytool.git"
            assert r.reversible is False
            # C1 unchanged
            assert tool.fqcn == "core:mytool"

    def test_in_orbit_dev_reversible(self):
        """SUBMODULE (publish) -> dev is WITHIN the orbit: reversible=True,
        inverse target = 'publish'."""
        from dazzlecmd_lib.mode import ModeRebindContext
        with tempfile.TemporaryDirectory() as tmp:
            tool = _sandbox_tool(tmp, with_url=True, gitmodules=True)  # SUBMODULE
            dev_src = os.path.join(tmp, "devsrc")
            os.makedirs(dev_src)
            ctx = ModeRebindContext(project_root=tmp, tools_dir="projects",
                                    dev_path=dev_src, dry_run=True)
            r = tool.rebind("dev", context=ctx)
            assert r.new_state == "dev"
            assert r.reversible is True
            assert r.previous_state == "publish"

    def test_resolve_remote_url_reads_from_entity(self):
        """Regression for the latent entity-migration bug this phase surfaced:
        `_resolve_remote_url` must read `source.url` (and the
        `lifecycle.graduated_to` fallback) from a DazzleEntity, not only a dict.
        Pre-fix, `_dotted_lookup`'s `isinstance(dict)` guard returned None for
        entities -- breaking `dz mode switch --publish` without --url."""
        from dazzlecmd_lib.mode import _resolve_remote_url
        tool = build_entity({
            "name": "mytool", "namespace": "core",
            "source": {"url": "https://example.com/mytool.git"},
        }, entity_type="tool")
        assert _resolve_remote_url(tool) == "https://example.com/mytool.git"

        graduated = build_entity({
            "name": "t2", "namespace": "core",
            "lifecycle": {"graduated_to": "https://example.com/t2.git"},
        }, entity_type="tool")
        assert _resolve_remote_url(graduated) == "https://example.com/t2.git"


class TestUndo:
    """Step 2: ``context.undo(receipt)`` -- the context-level inverse, so callers
    (and the ``assert_round_trip`` harness) don't track the new owner. Alias undo
    is entity-free (the context owns the alias + index); mode undo re-drives the
    inverse switch on the entity captured at apply time, iff the receipt is
    reversible."""

    # -- alias -------------------------------------------------------------
    def test_alias_undo_round_trip_via_harness(self):
        """The Step-1 harness now consumes ``ctx.undo`` directly as the inverse."""
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        ctx = AliasRebindContext(idx, alias="claude:cleanup")
        receipt = assert_round_trip(
            read=lambda: idx.alias_index["claude:cleanup"],
            apply=lambda: c1.rebind("core:cleanup", context=ctx),
            invert=ctx.undo,
            expected_new="core:cleanup",
        )
        assert idx.alias_index["claude:cleanup"] == "dazzletools:cleanup"  # restored
        assert receipt.previous_state == "dazzletools:cleanup"

    def test_alias_undo_returns_inverse_receipt(self):
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        ctx = AliasRebindContext(idx, "claude:cleanup")
        r = c1.rebind("core:cleanup", context=ctx)
        u = ctx.undo(r)
        assert u.sub_kind == "alias"
        assert u.previous_state == "core:cleanup"        # where it pointed pre-undo
        assert u.new_state == "dazzletools:cleanup"      # restored
        assert u.reversible is True
        assert idx.alias_index["claude:cleanup"] == "dazzletools:cleanup"

    def test_alias_undo_unknown_alias_raises(self):
        idx, c1, c2 = _idx_two_canonicals_one_alias()
        ctx = AliasRebindContext(idx, "claude:cleanup")
        r = c1.rebind("core:cleanup", context=ctx)
        ghost = AliasRebindContext(idx, "ghost:alias")
        with pytest.raises(KeyError):
            ghost.undo(r)

    # -- mode --------------------------------------------------------------
    def test_mode_undo_refuses_one_way(self):
        """Entering the orbit from EMBEDDED is one-way (reversible=False) -- undo
        refuses (the inverse can't be auto-derived)."""
        from dazzlecmd_lib.mode import ModeRebindContext
        with tempfile.TemporaryDirectory() as tmp:
            tool = _sandbox_tool(tmp, with_url=True)  # EMBEDDED + url
            ctx = ModeRebindContext(project_root=tmp, tools_dir="projects", dry_run=True)
            r = tool.rebind("publish", context=ctx)
            assert r.reversible is False
            with pytest.raises(CriticalityBoundaryError, match="one-way"):
                ctx.undo(r)

    def test_mode_undo_in_orbit_returns_inverse_receipt(self):
        """In-orbit dev<->publish is reversible -- undo re-drives toward the prior
        mode and returns the inverse receipt."""
        from dazzlecmd_lib.mode import ModeRebindContext
        with tempfile.TemporaryDirectory() as tmp:
            tool = _sandbox_tool(tmp, with_url=True, gitmodules=True)  # SUBMODULE
            dev_src = os.path.join(tmp, "devsrc")
            os.makedirs(dev_src)
            ctx = ModeRebindContext(project_root=tmp, tools_dir="projects",
                                    dev_path=dev_src, dry_run=True)
            r = tool.rebind("dev", context=ctx)
            assert r.reversible is True and r.previous_state == "publish"
            u = ctx.undo(r)
            assert u.sub_kind == "mode-switch"
            assert u.new_state == "publish"          # inverted back toward publish

    def test_mode_undo_without_apply_raises(self):
        """undo before any apply on the context -> RebindError (no captured entity)."""
        from dazzlecmd_lib.mode import ModeRebindContext
        ctx = ModeRebindContext(project_root="/nope", tools_dir="projects", dry_run=True)
        fake = RebindReceipt(
            entity_fqcn="core:x", sub_kind="mode-switch",
            previous_state="publish", new_state="dev",
            invariant=RebindInvariant("remote_url", "https://example.com/x.git"),
            reversible=True,
        )
        with pytest.raises(RebindError, match="prior apply"):
            ctx.undo(fake)


# ---------------------------------------------------------------------------
# B2b-2 -- alias rebind runs `apply` on the generic TransitionContext
# ---------------------------------------------------------------------------
def test_alias_rebind_receipt_sources_invariant_from_registry():
    """AC4: after migrating onto TransitionContext, the RebindReceipt's reversible
    + conserved-name trace to the DECLARED routing/rebind edge (the registry is on
    the alias-rebind runtime path), not a hardcoded literal."""
    idx, c1, c2 = _idx_two_canonicals_one_alias()
    r = c1.rebind("core:cleanup", context=AliasRebindContext(idx, "claude:cleanup"))
    edge = next(t for t in build_default_registry().for_verb("rebind")
                if t.axis == "routing")
    assert r.invariant.conserved_quantity_name == edge.conserved == "single_hop_rule"
    assert r.reversible is edge.reversible is True
