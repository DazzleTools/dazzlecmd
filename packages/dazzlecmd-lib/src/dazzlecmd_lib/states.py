"""The state system -- dazzlecmd's declared axes + transitions.

The GENERIC machinery (``StateAxis``, ``EntityState``, ``Transition``,
``CompositeTransition``, ``TransitionRegistry``, ``Reversibility``, ``OPEN``,
``assert_round_trip``, ``observe``) was lifted to the ``dazzle-lib`` bedrock
(``dazzle_lib.states``; B3b of the Groupable<->Continuum<->states unification,
dazzle-lib 0.4.0) -- it proved domain-neutral (it imports nothing from any
aggregator) and pure (stdlib + the ``Continuum`` primitive only). This module
RE-EXPORTS those types so every ``from dazzlecmd_lib.states import ...`` keeps
working unchanged, and KEEPS what is genuinely dazzlecmd's: the reference
registry (which axes the dazzlecmd toolset has, which transitions are live).

The split mirrors the design's own boundary -- the bedrock ships the vocabulary,
the consumer DECLARES its instances. The DECLARED edges below were each added BY
the commit that made their verb a live Groupable method (the registry is filled
by the verb, never ahead of it). ``test_states.py`` cross-checks the value
literals against the ``mode``/``engine`` constants so drift is caught.
"""

from __future__ import annotations

from typing import Any, Tuple

# The generic state-system primitives now live in the bedrock (lifted in
# dazzlecmd 0.9.44 / dazzle-lib 0.4.0); re-exported here so the historical
# ``dazzlecmd_lib.states`` import path resolves to the SAME classes.
from dazzle_lib.states import (  # noqa: F401
    OPEN,
    CompositeTransition,
    EntityState,
    Reversibility,
    StateAxis,
    Transition,
    TransitionRegistry,
    assert_round_trip,
    observe,
)

# ``Continuum`` for the VISIBILITY axis below (the dazzlecmd_lib.continuum shim
# re-exports the bedrock primitive).
from .continuum import Continuum


# ---------------------------------------------------------------------------
# The dazzlecmd reference registry -- axes + the LIVE rebind transitions
# ---------------------------------------------------------------------------
# MODE axis values mirror ``mode.STATE_*`` (kept as literals here so this module
# imports nothing from ``mode``; ``test_states.py`` cross-checks them against the
# constants so drift is caught).
MODE_VALUES: Tuple[str, ...] = ("symlink", "submodule", "embedded", "missing", "local-only")

# The VISIBILITY axis is a CONTINUUM (the signed, channel-backed source of truth):
# ``visible`` is rank 0 (veil-free; canonical_dispatch intact), each colder rung
# suppresses one more surface (hints -> display -> resolution), ``shadowed`` is the
# cold pole (refused for constitutional items -- C3). hide = step COLDER; expose =
# step WARMER. This is the ONE source for the axis's ordered values; it lived in
# ``groupable.py`` until B1 moved it down to L0 so the registry that DECLARES the
# axes owns it (``groupable.py`` re-imports it for its derived shims +
# ``KIT_PRESENCE_SPACE``).
VISIBILITY_CONTINUUM = Continuum(
    name="visibility",
    ranks={"visible": 0, "silenced": -1, "hidden": -2, "shadowed": -3},
    invariant="canonical_dispatch",
    channels={
        "visible": frozenset(),
        "silenced": frozenset({"hints"}),
        "hidden": frozenset({"hints", "display"}),
        "shadowed": frozenset({"hints", "display", "resolution"}),
    },
)
# Single source: the value set DERIVES from the continuum (warm->cold), byte-
# identical to the prior literal ``("visible","silenced","hidden","shadowed")``.
VISIBILITY_VALUES: Tuple[str, ...] = VISIBILITY_CONTINUUM.levels()[::-1]

# The ACTIVATION axis as a signed Continuum (mirrors VISIBILITY_CONTINUUM): ``active``
# is the neutral/fully-present pole (rank 0 -- a kit's default), ``inactive`` is
# suppressed (-1). Giving activation a Continuum (not just a value tuple) lets it
# COMPOSE as a presence axis alongside visibility -- the multi-axis KIT_PRESENCE
# product. The conserved quantity at rank 0 is the kit's re-activatable config
# membership: enable<->disable is a reversible config toggle, never a removal, so
# the axis round-trips (the B4 activation-as-Groupable seam).
ACTIVATION_CONTINUUM = Continuum(
    name="activation",
    ranks={"active": 0, "inactive": -1},
    invariant="kit_activation",
)
# Derived warm->cold, byte-identical to the prior literal ``("active","inactive")``.
ACTIVATION_VALUES: Tuple[str, ...] = ACTIVATION_CONTINUUM.levels()[::-1]
KIND_VALUES: Tuple[str, ...] = ("tool", "kit", "aggregator")

# The two MODE states that constitute the dev<->publish orbit (in-orbit =
# reversible; entering from outside is one-way).
_MODE_ORBIT: Tuple[str, ...] = ("symlink", "submodule")
_MODE_OUT_OF_ORBIT: Tuple[str, ...] = ("embedded", "local-only")


def build_default_registry() -> TransitionRegistry:
    """Build the reference registry for the dazzlecmd toolset.

    Registers the entity-state axes (KIND/MODE/VISIBILITY/ACTIVATION plus the
    open-valued CONTAINMENT/PROJECTION naming axes) and the index-level ROUTING
    axis, and DECLARES the live transitions: the ``rebind`` mechanisms (alias
    routing + dev<->publish mode-switch), the VISIBILITY ``hide``/``expose``
    ladder, the CONTAINMENT and PROJECTION ``group``/``ungroup`` edges, and the
    GENERATIVE ``graduation`` composite. Each edge-set was added BY the commit
    that made its verb a live Groupable method (the intended trigger -- the
    registry is filled by the verb, never ahead of it). The ACTIVATION
    enable/disable edges land here too (the B4 activation-as-Groupable seam --
    the ``ActivationContext`` that drives ``dz kit enable``/``disable``).
    """
    reg = TransitionRegistry()

    # -- axes -----------------------------------------------------------------
    reg.register_axis(StateAxis(
        name="kind", values=KIND_VALUES, read_only=True,
        substrate="the Python type (discriminated union); changes only via graduation",
    ))
    reg.register_axis(StateAxis(
        name="mode", values=MODE_VALUES,
        substrate="filesystem (detect_tool_state)",
    ))
    reg.register_axis(StateAxis(
        name="visibility", continuum=VISIBILITY_CONTINUUM,
        substrate="user config (silenced_hints / shadowed_tools / planned hidden_tools)",
    ))
    reg.register_axis(StateAxis(
        name="activation", values=ACTIVATION_VALUES,
        substrate="kit_active, derived from active_kits / disabled_kits config",
    ))
    reg.register_axis(StateAxis(
        name="routing", values=None,  # open-valued: any FQCN
        substrate="FQCNIndex.alias_index",
    ))

    # -- ROUTING: alias rebind (in-memory; always reversible -- a repoint) -----
    reg.declare(Transition(
        axis="routing", from_values=(OPEN,), to_value=OPEN, verb="rebind",
        reversibility=Reversibility.REVERSIBLE, conserved="single_hop_rule",
        note="repoint an alias to a different canonical; C1 of the owner unchanged",
    ))

    # -- MODE: dev<->publish rebind (filesystem; reversibility by orbit) -------
    reg.declare(Transition(
        axis="mode", from_values=_MODE_ORBIT, to_value=OPEN, verb="rebind",
        reversibility=Reversibility.REVERSIBLE, conserved="remote_url",
        note="dev<->publish within the orbit (SYMLINK<->SUBMODULE); reversible",
    ))
    # EMBEDDED -> orbit is now REVERSIBLE: `dz mode restore` (#37) re-materializes
    # the embedded content from the origins record + safedel backup. The inverse
    # mechanism is restore, not a bare rebind, but the edge can be inverted -- so
    # it is no longer a one-way mini-graduation.
    reg.declare(Transition(
        axis="mode", from_values=("embedded",), to_value=OPEN, verb="rebind",
        reversibility=Reversibility.REVERSIBLE, conserved="embedded_content",
        note="EMBEDDED->SYMLINK: reversible via origins tracking + 'dz mode restore'",
    ))
    # LOCAL_ONLY -> orbit stays ONE_WAY: there is no backed-up content to recover
    # and no registered submodule to re-clone, so the entry cannot be inverted.
    reg.declare(Transition(
        axis="mode", from_values=("local-only",), to_value=OPEN, verb="rebind",
        reversibility=Reversibility.ONE_WAY, conserved="remote_url",
        note="LOCAL_ONLY->SYMLINK: one-way (no backed-up content, no registered submodule)",
    ))
    reg.declare(Transition(
        axis="mode", from_values=("missing",), to_value=OPEN, verb="rebind",
        reversibility=Reversibility.REFUSED_AT_BOUNDARY, conserved="remote_url",
        note="path missing / conserved invariant underivable -> refuse (pre-flight)",
    ))

    # -- VISIBILITY: hide/expose ladder walks (config; always reversible) ------
    # The conserved invariant is canonical_dispatch: a veil never removes the
    # canonical from the index, so every visibility move round-trips. The C3
    # boundary (refusing to shadow a constitutional item) is a pre-flight refusal
    # the context raises, not an irreversible edge.
    reg.declare(Transition(
        axis="visibility", from_values=("visible", "silenced", "hidden"),
        to_value=OPEN, verb="hide", reversibility=Reversibility.REVERSIBLE,
        conserved="canonical_dispatch",
        note="walk down the ladder (more suppressed); dispatch survives",
    ))
    reg.declare(Transition(
        axis="visibility", from_values=("silenced", "hidden", "shadowed"),
        to_value=OPEN, verb="expose", reversibility=Reversibility.REVERSIBLE,
        conserved="canonical_dispatch",
        note="walk up the ladder (less suppressed); the inverse of hide",
    ))

    # -- ACTIVATION: enable/disable toggle (config; always reversible) ---------
    # enable<->disable is a LATERAL round-trip: a kit's config membership is never
    # destroyed (it can always be re-toggled), so both directions are reversible
    # (enable o disable = identity). The substrate is active_kits / disabled_kits;
    # the ActivationContext binds it. The B4 activation-as-Groupable seam.
    reg.declare(Transition(
        axis="activation", from_values=("active", "inactive"),
        to_value="active", verb="enable",
        reversibility=Reversibility.REVERSIBLE, conserved="kit_activation",
        note="add to active_kits / drop from disabled_kits; reversible via disable",
    ))
    reg.declare(Transition(
        axis="activation", from_values=("active", "inactive"),
        to_value="inactive", verb="disable",
        reversibility=Reversibility.REVERSIBLE, conserved="kit_activation",
        note="add to disabled_kits / drop from active_kits; reversible via enable",
    ))

    # -- CONTAINMENT: group/ungroup membership moves (in-tree; reversible) -----
    reg.register_axis(StateAxis(
        name="containment", values=None,   # open-valued: which boundary holds it
        substrate="kit.tools membership / nested-aggregator structure",
    ))
    reg.declare(Transition(
        axis="containment", from_values=(OPEN,), to_value=OPEN, verb="group",
        reversibility=Reversibility.REVERSIBLE, conserved="local_incorporability",
        note="incorporate an entity into a boundary's membership (in-tree; reversible)",
    ))
    reg.declare(Transition(
        axis="containment", from_values=(OPEN,), to_value=OPEN, verb="ungroup",
        reversibility=Reversibility.REVERSIBLE, conserved="local_incorporability",
        note="disincorporate an entity from a boundary (in-tree; the inverse of group)",
    ))

    # -- MEMBERSHIP: kit-in-aggregator group/ungroup (the kits/*.kit.json registry) --
    # DISTINCT from CONTAINMENT (tool-in-kit, in-memory): membership is
    # kit-in-aggregator, its substrate is the kits/ registry FILES, and it PERSISTS
    # (a deregistered kit's entry is gone from disk -- there is no in-memory rebuild).
    # The KitMembershipContext binds it (a sibling of ContainmentContext, not a
    # subclass). group = register a kit; ungroup = deregister it -- the strong-remove's
    # deregister half (safedel + deactivate layer onto the ungroup verb in a later slice).
    reg.register_axis(StateAxis(
        name="membership", values=None,   # open-valued: which aggregator registers it
        substrate="kits/*.kit.json registry (kit-in-aggregator); persists to disk",
    ))
    reg.declare(Transition(
        axis="membership", from_values=(OPEN,), to_value=OPEN, verb="group",
        reversibility=Reversibility.REVERSIBLE, conserved="kit_registration",
        note="register a kit in the aggregator (write its kits/<name>.kit.json); reversible via ungroup",
    ))
    reg.declare(Transition(
        axis="membership", from_values=(OPEN,), to_value=OPEN, verb="ungroup",
        reversibility=Reversibility.REVERSIBLE, conserved="kit_registration",
        note="deregister a kit (remove its registry entry); reversible by re-group / dz kit add",
    ))

    # -- GRADUATION: the generative multi-axis ungroup (declared as DATA) ------
    # Local tool -> its own git repo (-> kit/aggregator). The KIND leg CREATES
    # the remote the MODE leg conserves, so the composite is GENERATIVE even
    # though its MODE leg is reversible in isolation -- composite-criticality from
    # leg interaction, not union. The fs+git EXECUTION is #73 build-environment
    # work; here the edge is declared + criticality-classified as data so the
    # contract is settled before its body exists.
    _grad_kind = Transition(
        axis="kind", from_values=("tool",), to_value=OPEN, verb="graduate",
        reversibility=Reversibility.GENERATIVE, conserved="local_files",
        creates=("own_repo", "remote_url"), loses=("in_tree_coupling",),
        identity_fate="reborn",
        note="extract a local tool into its own git repo (creates the remote)",
    )
    _grad_mode = Transition(
        axis="mode", from_values=("embedded", "local-only"), to_value="submodule",
        verb="graduate", reversibility=Reversibility.ONE_WAY, conserved="remote_url",
        note="re-enter the graduated repo as a submodule (depends on the remote above)",
    )
    reg.register_composite(CompositeTransition(
        name="graduation", legs=(_grad_kind, _grad_mode), verb="graduate",
        atomicity="all_or_nothing", identity_fate="reborn",
    ))

    # -- PROJECTION: FQCN-name overlay/alias moves (the naming axis) -----------
    # How a canonical's name is PROJECTED into a consumer's surface -- the two
    # directions of the {group, ungroup} primitive on the naming substrate:
    #   - ungroup (VIRTUAL KIT): one canonical projected under additional alias
    #     names -- split a kit into pieces (e.g. ``core:safedel`` also surfaced
    #     as ``f:rm``). One thing presented as many.
    #   - group (OVERLAY): many home canonicals grouped onto ONE consumer
    #     surface -- collapse ``dazzlecmd_lib:core`` onto ``<consumer>:core`` so
    #     the lib's constitutional tools appear in the consumer's ``core:`` list
    #     as projection-aliases. Many homes presented as one surface. This is the
    #     INVERSE of a virtual kit.
    # Both are REVERSIBLE name projections that CONSERVE the canonical FQCN (C1):
    # the absolute identity never changes; only its projected/aliased names do.
    # Declared as DATA here (the precedent: graduation above); the index body
    # (home canonical + projection alias in the FQCN index) is the next slice,
    # replacing the v0.9.9 ``_absolute_to_local`` normalization shim.
    reg.register_axis(StateAxis(
        name="projection", values=None,   # open-valued: the set of projected names
        substrate="fqcn_index alias/canonical entries (display + dispatch)",
    ))
    reg.declare(Transition(
        axis="projection", from_values=(OPEN,), to_value=OPEN, verb="ungroup",
        reversibility=Reversibility.REVERSIBLE, conserved="canonical_fqcn",
        note="virtual kit: project a canonical under additional alias names (split)",
    ))
    reg.declare(Transition(
        axis="projection", from_values=(OPEN,), to_value=OPEN, verb="group",
        reversibility=Reversibility.REVERSIBLE, conserved="canonical_fqcn",
        note="overlay: group a home namespace's canonicals onto a consumer "
             "surface as projection-aliases (the inverse of the virtual-kit ungroup)",
    ))

    return reg


__all__ = [
    # re-exported generic primitives (lifted to dazzle_lib.states in B3b)
    "OPEN",
    "Reversibility",
    "StateAxis",
    "EntityState",
    "Transition",
    "CompositeTransition",
    "TransitionRegistry",
    "assert_round_trip",
    "observe",
    # dazzlecmd's declared instances (kept here)
    "MODE_VALUES",
    "VISIBILITY_CONTINUUM",
    "VISIBILITY_VALUES",
    "ACTIVATION_CONTINUUM",
    "ACTIVATION_VALUES",
    "KIND_VALUES",
    "build_default_registry",
]
