"""Step 5 tests for the group/ungroup verbs + CompositeTransition.

group/ungroup are the {P, -P} boundary primitive at full strength. This slice
wires the REVERSIBLE in-tree regime (move an entity in/out of a boundary's
membership; group o ungroup = identity, C2 = local_incorporability) and declares
the GENERATIVE graduation regime as DATA (a CompositeTransition) -- its fs+git
body is #73, so requesting it is refused at the criticality boundary. C3:
constitutional items may be grouped/hidden but never ungrouped.

The CompositeTransition tests pin the load-bearing rule: composite-criticality is
computed from leg INTERACTION (a leg's `creates` feeding a later leg's conserved
invariant => generative), NOT the union of the legs' classes.
"""

import pytest

from dazzlecmd_lib.contexts import (
    ContainmentContext,
    ContainmentInvariant,
    ContainmentReceipt,
    CriticalityBoundaryError,
    RebindError,
)
from dazzlecmd_lib.states import (
    CompositeTransition,
    Reversibility,
    Transition,
    assert_round_trip,
    build_default_registry,
)
from dazzlecmd_lib.testing import make_kit, make_tool


def _boundary(tools=None):
    return make_kit(name="core", _kit_name="core", _fqcn="core",
                    tools=list(tools or []))


def _tool(**over):
    base = dict(name="rn", _fqcn="core:rn", _short_name="rn", _kit_import_name="core")
    base.update(over)
    return make_tool(**base)


# ---------------------------------------------------------------------------
# The reversible in-tree regime
# ---------------------------------------------------------------------------
class TestGroupUngroup:
    def test_group_adds_to_boundary(self):
        kit = _boundary()
        r = _tool().group("core", context=ContainmentContext(kit))
        assert isinstance(r, ContainmentReceipt)
        assert r.verb == "group" and r.new_state == "core"
        assert "core:rn" in kit.tools

    def test_ungroup_removes_from_boundary(self):
        kit = _boundary(tools=["core:rn"])
        r = _tool().ungroup(context=ContainmentContext(kit))
        assert r.verb == "ungroup" and r.new_state is None
        assert "core:rn" not in kit.tools

    def test_round_trip_via_undo(self):
        kit = _boundary()
        ctx = ContainmentContext(kit)
        tool = _tool()
        assert_round_trip(
            read=lambda: ctx.contains(tool),
            apply=lambda: tool.group("core", context=ctx),
            invert=ctx.undo,
            expected_new=True,
        )
        assert ctx.contains(tool) is False

    def test_group_is_idempotent(self):
        kit = _boundary()
        ctx = ContainmentContext(kit)
        tool = _tool()
        tool.group("core", context=ctx)
        tool.group("core", context=ctx)
        assert kit.tools.count("core:rn") == 1


# ---------------------------------------------------------------------------
# C3 + the graduation boundary
# ---------------------------------------------------------------------------
class TestC3AndGraduation:
    def test_ungroup_constitutional_refused(self):
        kit = _boundary(tools=["core:rn"])
        with pytest.raises(CriticalityBoundaryError, match="constitutional"):
            _tool(always_active=True).ungroup(context=ContainmentContext(kit))

    def test_group_constitutional_is_allowed(self):
        kit = _boundary()
        _tool(always_active=True).group("core", context=ContainmentContext(kit))
        assert "core:rn" in kit.tools

    def test_graduation_refused_until_73(self):
        kit = _boundary(tools=["core:rn"])
        ctx = ContainmentContext(kit)
        with pytest.raises(CriticalityBoundaryError, match="#73"):
            _tool().ungroup(target=ContainmentContext.GRADUATE, context=ctx)

    def test_undo_without_apply_raises(self):
        ctx = ContainmentContext(_boundary())
        fake = ContainmentReceipt(
            entity_fqcn="core:rn", sub_kind="containment",
            previous_state=None, new_state="core",
            invariant=ContainmentInvariant(), verb="group",
        )
        with pytest.raises(RebindError, match="prior apply"):
            ctx.undo(fake)


# ---------------------------------------------------------------------------
# CompositeTransition -- the criticality-from-interaction rule
# ---------------------------------------------------------------------------
class TestCompositeTransition:
    def test_graduation_is_generative(self):
        grad = build_default_registry().composite("graduation")
        assert grad.reversibility is Reversibility.GENERATIVE
        assert grad.identity_fate == "reborn"
        assert "remote_url" in grad.creates
        assert "in_tree_coupling" in grad.loses
        assert grad.axes == ("kind", "mode")

    def test_composite_criticality_is_not_union(self):
        """Two legs each REVERSIBLE in isolation compose to GENERATIVE when one
        leg CREATES what a later leg CONSERVES (the 5/2 bridge at composite scale)."""
        leg1 = Transition(axis="kind", from_values=("tool",), to_value="aggregator",
                          verb="x", reversibility=Reversibility.REVERSIBLE,
                          creates=("remote_url",), conserved="local")
        leg2 = Transition(axis="mode", from_values=("embedded",), to_value="submodule",
                          verb="x", reversibility=Reversibility.REVERSIBLE,
                          conserved="remote_url")
        ct = CompositeTransition(name="synthetic", legs=(leg1, leg2), verb="x")
        assert ct.reversibility is Reversibility.GENERATIVE

    def test_composite_without_interaction_is_strongest_leg(self):
        leg1 = Transition(axis="kind", from_values=("tool",), to_value="kit",
                          verb="x", reversibility=Reversibility.REVERSIBLE, conserved="a")
        leg2 = Transition(axis="mode", from_values=("embedded",), to_value="submodule",
                          verb="x", reversibility=Reversibility.ONE_WAY, conserved="b")
        ct = CompositeTransition(name="s2", legs=(leg1, leg2), verb="x")
        assert ct.reversibility is Reversibility.ONE_WAY

    def test_empty_composite_rejected(self):
        with pytest.raises(ValueError, match="at least one leg"):
            CompositeTransition(name="empty", legs=(), verb="x")


# ---------------------------------------------------------------------------
# Registry declarations
# ---------------------------------------------------------------------------
class TestRegistry:
    def test_containment_transitions_reversible(self):
        reg = build_default_registry()
        # group/ungroup are one primitive across substrates -- containment
        # (in-tree membership) AND projection (FQCN overlay/virtual-kit). Scope
        # to the containment axis here; projection is covered in test_states.
        for verb in ("group", "ungroup"):
            edges = [t for t in reg.for_verb(verb) if t.axis == "containment"]
            assert edges, f"registry must declare containment {verb} edges"
            for t in edges:
                assert t.reversibility is Reversibility.REVERSIBLE
                assert t.conserved == "local_incorporability"

    def test_graduation_composite_registered(self):
        names = {c.name for c in build_default_registry().composites()}
        assert "graduation" in names


# ---------------------------------------------------------------------------
# B2b -- containment runs on the generic TransitionContext (registry-sourced)
# ---------------------------------------------------------------------------
def test_containment_receipt_sources_invariant_from_registry():
    """AC4: after migrating onto TransitionContext, the ContainmentReceipt's
    reversible + conserved-name trace to the DECLARED containment edge (the
    registry is on the verb's runtime path), not a hardcoded literal."""
    kit = _boundary()
    r = _tool().group("core", context=ContainmentContext(kit))
    edge = next(t for t in build_default_registry().for_verb("group")
                if t.axis == "containment")
    assert r.invariant.conserved_quantity_name == edge.conserved == "local_incorporability"
    assert r.reversible is edge.reversible is True
