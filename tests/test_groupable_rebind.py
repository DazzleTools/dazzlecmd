"""Phase 1 (alias) tests for ``Groupable.rebind`` -- the first live
state-transition operator (#84 behavioral phase; the rebind PoC).

Validates against a REAL ``FQCNIndex`` (not a mock): the context+receipt+
invariant pattern, the round-trip property (``rebind o rebind^-1 = identity``),
the receiver precondition + single-hop/existence guards, idempotence, and
``short_index`` coherence after a repoint (the corruption risk flagged in the
DWP hole-review H2).
"""
import pytest

from dazzlecmd_lib.engine import FQCNIndex
from dazzlecmd_lib.groupable import (
    AliasRebindContext,
    RebindReceipt,
    RebindInvariant,
)
from dazzlecmd_lib.testing import make_tool


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
