"""The state system -- axes, observed entity state, and declared transitions.

This module gives every grouping/ungrouping mechanism ONE vocabulary for the
states it moves between, the axes those states live on, which transitions are
reversible/critical, and what each transition preserves, creates, or destroys.
Until now that contract lived only in markdown (and drifted -- the mode-switch
criticality table had to be hand-corrected once). Here it is code the runtime
can query and tests can enumerate.

Design (see the 2026-06-09 state-system DWP):

- **Generic by construction.** The four core types import NOTHING from
  ``engine``/``mode``/``groupable`` -- axes are *registered*, not hardcoded, so
  the module ships in the standalone lib and any aggregator builds its own
  registry. The dependency direction is ``states`` <- ``groupable`` <-
  entity-verbs; engine/mode register their axes. ``build_default_registry()``
  is the reference registration for the dazzlecmd toolset.

- **State is OBSERVED, not stored** (F1). ``EntityState`` is a frozen snapshot
  assembled on demand; the substrates (filesystem for MODE, config for
  VISIBILITY/ACTIVATION, the Python type for KIND, the index for ROUTING) stay
  authoritative -- exactly the ``ResolutionContext`` precedent. Only identity
  (C1 ``fqcn``) is carried by the entity itself.

- **Transitions are DECLARED edges** (F2/F3). A :class:`Transition` names its
  axis, the states it goes from/to, its verb, its reversibility class, the
  conserved quantity (C2, by NAME -- the context fills the runtime value, which
  keeps this module free of the ``groupable`` invariant types), and the
  criticality bookkeeping (``creates``/``loses``/``fqcn_fate``). The
  :class:`TransitionRegistry` makes the markdown tables queryable: receipts can
  stop hardcoding ``reversible=``, the round-trip harness enumerates the edges,
  and a future ``dz explain`` can answer "what would this lose?".

- **The identity contract becomes a test** (F3.2). :func:`assert_round_trip`
  orchestrates read -> apply -> invert -> read and asserts L2-semantic equality
  (the ``group o ungroup = identity`` concept, generated rather than asserted in
  prose). It is substrate-agnostic: ``read`` returns whatever observation the
  axis exposes (a MODE state, an alias target), so the same harness covers both
  entity-axis and index-level (routing) transitions.

Reserved -- :class:`CompositeTransition` (multi-axis moves like graduation =
KIND+MODE+identity) is COMPOSITION of single-axis transitions, not a new
primitive; it is defined in the ``group``/``ungroup`` design pass and reserved
here as a documented extension point. Nothing in the single-axis types changes
to accommodate it -- the test that it is genuinely composition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Optional, Tuple

from .continuum import Continuum, ContinuumSpaceProtocol


# ---------------------------------------------------------------------------
# OPEN -- the sentinel for open-valued axes / wildcards
# ---------------------------------------------------------------------------
class _Open:
    """Sentinel: an open value space (e.g. ROUTING ranges over all FQCNs, not a
    fixed enum) or a wildcard in a transition's ``from_values``/``to_value``."""

    _instance: "Optional[_Open]" = None

    def __new__(cls) -> "_Open":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "OPEN"


OPEN = _Open()


def _admits(allowed: Tuple[Any, ...], value: Any) -> bool:
    """True if ``value`` is in ``allowed`` or ``allowed`` wildcards via OPEN."""
    return any(a is OPEN or a == value for a in allowed)


# ---------------------------------------------------------------------------
# Reversibility -- the criticality algebra (the 5/2 bridge as data)
# ---------------------------------------------------------------------------
class Reversibility(Enum):
    """How a transition relates to its inverse -- straight from the corpus.

    - ``REVERSIBLE``: the inverse verb restores the prior state because the
      conserved invariant is preserved (in-orbit; ``receipt.reversible=True``).
    - ``ONE_WAY``: permitted, but it enters an orbit it cannot return from on its
      own (e.g. EMBEDDED -> publish -- a mini-graduation; ``reversible=False``).
    - ``REFUSED_AT_BOUNDARY``: the conserved invariant cannot be derived, so the
      transition would be irreversible -> refused PRE-FLIGHT
      (``CriticalityBoundaryError``).
    - ``GENERATIVE``: creates/destroys structure (ungroup / graduation);
      irreversible by construction -- ``creates``/``loses`` MUST be declared and
      ``fqcn_fate`` is typically ``"reborn"``.
    """

    REVERSIBLE = "reversible"
    ONE_WAY = "one_way"
    REFUSED_AT_BOUNDARY = "refused_at_boundary"
    GENERATIVE = "generative"


# ---------------------------------------------------------------------------
# StateAxis -- a named dimension an entity varies along
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StateAxis:
    """One dimension of state, plus where its truth lives.

    ``values`` is the allowed value set, or ``None`` for an open-valued axis
    (ROUTING ranges over all FQCNs). When a ``continuum`` is supplied -- the
    signed, ordered backing (the unification's *StateAxis HAS-A Continuum* seam,
    B1) -- ``values`` DERIVES from it (single source: no ``values``/``ranks``
    drift); passing both that disagree is a contract breach, raised here.
    ``read_only`` marks an axis that the verbs do not transition directly (KIND
    -- changed only by graduation, a composite). ``detect`` is an optional reader
    hook into the substrate; it is intentionally left ``None`` in the default
    registry so this module imports nothing from ``mode``/``engine`` -- the axis
    documents its substrate, the consumer reads it.
    """

    name: str
    values: Optional[Tuple[Any, ...]] = None
    read_only: bool = False
    substrate: str = ""
    detect: Optional[Callable[..., Any]] = None
    continuum: Optional[Continuum] = None

    def __post_init__(self) -> None:
        # The HAS-A Continuum seam (B1): when an axis carries its signed/ordered
        # backing, the ordered value set IS the Continuum's -- derive it
        # (warm->cold) so there is ONE source, and refuse a ``values=`` that
        # disagrees rather than silently preferring one (the drift guard).
        if self.continuum is not None:
            if self.values is None:
                object.__setattr__(self, "values", self.continuum.levels()[::-1])
            elif set(self.values) != set(self.continuum.ranks):
                raise ValueError(
                    f"StateAxis {self.name!r}: values {tuple(self.values)!r} "
                    f"disagree with continuum {self.continuum.name!r} levels "
                    f"{tuple(self.continuum.ranks)!r} -- an axis has one value set"
                )

    def admits(self, value: Any) -> bool:
        """True if ``value`` is a legal value on this axis (open axes admit any)."""
        return self.values is None or value in self.values


# ---------------------------------------------------------------------------
# EntityState -- a frozen observation (NOT stored on the entity)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EntityState:
    """A measurement of an entity's state across one or more axes.

    Assembled on demand from the authoritative substrates and never persisted
    (F1). Carries C1 (``fqcn``) plus an ``axis-name -> observed value`` mapping.
    Equality is by ``(fqcn, values)``; use :meth:`on` to compare a subset of
    axes (the L2-semantic round-trip check ignores axes a transition does not
    touch).
    """

    fqcn: str
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalize to a plain dict copy (frozen => via object.__setattr__).
        object.__setattr__(self, "values", dict(self.values))

    def __getitem__(self, axis: str) -> Any:
        return self.values[axis]

    def get(self, axis: str, default: Any = None) -> Any:
        return self.values.get(axis, default)

    def on(self, *axes: str) -> "EntityState":
        """A restriction of this observation to ``axes`` (for subset equality)."""
        return EntityState(self.fqcn, {a: self.values[a] for a in axes if a in self.values})

    def coordinates_in(self, space: ContinuumSpaceProtocol) -> Mapping[str, int]:
        """This observation as a POINT in a :class:`ContinuumSpace` -- the signed
        presence coordinate for each of the space's axes that this state carries.

        The executable reading of "an ``EntityState`` is a point in the space"
        (the unification target): it pairs the OBSERVED value on each axis with
        the space's shared presence scale. Axes the state does not carry are
        skipped (a partial observation is a partial point); a carried value that
        is not a level of its axis surfaces as the Continuum's own error."""
        return {axis: space.presence_of(axis, self.values[axis])
                for axis in space.axes if axis in self.values}


# ---------------------------------------------------------------------------
# Transition -- a DECLARED edge on one axis
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Transition:
    """A declared, single-axis state-transition edge.

    ``conserved`` names the C2 invariant (e.g. ``"remote_url"``,
    ``"single_hop_rule"``); the runtime VALUE is supplied by the context's
    receipt, which is why this module declares the name only and never imports
    the ``groupable`` invariant types. ``invariant_factory`` is a reserved hook
    for consumers that want the registry to build their descriptor type; it stays
    ``None`` in the lib default registry to preserve ``states <- groupable``.

    ``creates``/``loses``/``fqcn_fate`` make the criticality bridging points
    declared DATA: what a transition brings into being, what it destroys, and
    what becomes of C1 (``"preserved"`` | ``"reborn"`` | ``"dissolved"``).
    """

    axis: str
    from_values: Tuple[Any, ...]
    to_value: Any
    verb: str
    reversibility: Reversibility
    conserved: str = ""
    invariant_factory: Optional[Callable[..., Any]] = None
    creates: Tuple[str, ...] = ()
    loses: Tuple[str, ...] = ()
    fqcn_fate: str = "preserved"
    note: str = ""

    def __post_init__(self) -> None:
        # A GENERATIVE edge must declare what it brings into being / destroys --
        # the criticality bridging points are not allowed to be implicit.
        if self.reversibility is Reversibility.GENERATIVE and not (self.creates or self.loses):
            raise ValueError(
                f"GENERATIVE transition ({self.verb} on {self.axis}) must declare "
                f"creates and/or loses -- the criticality must be explicit data."
            )
        # A REVERSIBLE edge must preserve C1 (identity is the carried invariant).
        if self.reversibility is Reversibility.REVERSIBLE and self.fqcn_fate != "preserved":
            raise ValueError(
                f"REVERSIBLE transition ({self.verb} on {self.axis}) must preserve "
                f"fqcn (C1); got fqcn_fate={self.fqcn_fate!r}."
            )

    @property
    def reversible(self) -> bool:
        """Whether the inverse verb restores the prior state (REVERSIBLE only)."""
        return self.reversibility is Reversibility.REVERSIBLE

    def matches(self, *, verb: str, axis: str, from_value: Any, to_value: Any = OPEN) -> bool:
        """Whether this declared edge covers an observed ``(verb, axis, from -> to)``."""
        if verb != self.verb or axis != self.axis:
            return False
        if not _admits(self.from_values, from_value):
            return False
        if to_value is not OPEN and self.to_value is not OPEN and to_value != self.to_value:
            return False
        return True


# ---------------------------------------------------------------------------
# CompositeTransition -- a multi-axis move as ordered composition (graduation)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CompositeTransition:
    """A multi-axis transition: an ORDERED composition of single-axis legs.

    Graduation (tool -> own repo -> kit/aggregator) is the canonical case: it
    changes KIND + MODE + identity at once. This is COMPOSITION, not a new
    primitive -- the legs are ordinary :class:`Transition` objects; this
    aggregates them with an order (the legs are not freely commutable -- you
    cannot publish a submodule against a remote the extraction leg hasn't created
    yet) and an atomicity policy.

    The load-bearing rule -- **composite-criticality is NOT the union of the
    legs' classes.** If any leg's ``creates`` feeds a LATER leg's conserved
    invariant, the whole is GENERATIVE even when every leg, taken alone, is
    reversible (the 5/2 structural bridge at composite scale). Otherwise the
    composite is as strong as its strongest leg.
    """

    name: str
    legs: Tuple[Transition, ...]
    verb: str
    atomicity: str = "all_or_nothing"   # "all_or_nothing" | "checkpoint"
    fqcn_fate: str = "reborn"

    def __post_init__(self) -> None:
        if not self.legs:
            raise ValueError("CompositeTransition must declare at least one leg")

    @property
    def reversibility(self) -> Reversibility:
        # Interaction first: a leg that CREATES a quantity a later leg CONSERVES
        # crosses the criticality boundary -> generative (this is the case where
        # the composite is strictly stronger than the union of its legs).
        for i, leg in enumerate(self.legs):
            created = set(leg.creates)
            for later in self.legs[i + 1:]:
                if later.conserved and later.conserved in created:
                    return Reversibility.GENERATIVE
        # Otherwise: as strong as the strongest leg.
        classes = {leg.reversibility for leg in self.legs}
        for strongest in (Reversibility.GENERATIVE, Reversibility.REFUSED_AT_BOUNDARY,
                          Reversibility.ONE_WAY):
            if strongest in classes:
                return strongest
        return Reversibility.REVERSIBLE

    @property
    def creates(self) -> Tuple[str, ...]:
        return tuple(c for leg in self.legs for c in leg.creates)

    @property
    def loses(self) -> Tuple[str, ...]:
        return tuple(x for leg in self.legs for x in leg.loses)

    @property
    def axes(self) -> Tuple[str, ...]:
        return tuple(leg.axis for leg in self.legs)


# ---------------------------------------------------------------------------
# TransitionRegistry -- the markdown tables, queryable
# ---------------------------------------------------------------------------
class TransitionRegistry:
    """A catalogue of registered axes and declared transitions.

    Powers receipt truthfulness (contexts look up the declared reversibility /
    invariant instead of hardcoding it), the round-trip harness (property tests
    enumerate the edges), and explainability.
    """

    def __init__(self) -> None:
        self._axes: dict[str, StateAxis] = {}
        self._transitions: list[Transition] = []
        self._composites: list[CompositeTransition] = []

    # -- axes -----------------------------------------------------------------
    def register_axis(self, axis: StateAxis) -> StateAxis:
        if axis.name in self._axes:
            raise ValueError(f"axis {axis.name!r} is already registered")
        self._axes[axis.name] = axis
        return axis

    def axis(self, name: str) -> StateAxis:
        return self._axes[name]

    def axes(self) -> Tuple[StateAxis, ...]:
        return tuple(self._axes.values())

    # -- transitions ----------------------------------------------------------
    def declare(self, transition: Transition) -> Transition:
        """Register a transition, validating its endpoints against its axis."""
        axis = self._axes.get(transition.axis)
        if axis is None:
            raise KeyError(
                f"transition references unregistered axis {transition.axis!r}; "
                f"register the axis first"
            )
        for fv in transition.from_values:
            if fv is not OPEN and not axis.admits(fv):
                raise ValueError(
                    f"transition from_value {fv!r} not admitted by axis "
                    f"{axis.name!r} (values={axis.values!r})"
                )
        if transition.to_value is not OPEN and not axis.admits(transition.to_value):
            raise ValueError(
                f"transition to_value {transition.to_value!r} not admitted by axis "
                f"{axis.name!r} (values={axis.values!r})"
            )
        self._transitions.append(transition)
        return transition

    def transitions(self) -> Tuple[Transition, ...]:
        return tuple(self._transitions)

    # -- composites (multi-axis) ---------------------------------------------
    def register_composite(self, composite: CompositeTransition) -> CompositeTransition:
        """Register a multi-axis composite; validate each leg's axis is known."""
        for leg in composite.legs:
            if leg.axis not in self._axes:
                raise KeyError(
                    f"composite {composite.name!r} leg references unregistered "
                    f"axis {leg.axis!r}"
                )
        self._composites.append(composite)
        return composite

    def composites(self) -> Tuple[CompositeTransition, ...]:
        return tuple(self._composites)

    def composite(self, name: str) -> CompositeTransition:
        for c in self._composites:
            if c.name == name:
                return c
        raise LookupError(f"no composite transition named {name!r}")

    def for_verb(self, verb: str) -> Tuple[Transition, ...]:
        return tuple(t for t in self._transitions if t.verb == verb)

    def for_axis(self, axis: str) -> Tuple[Transition, ...]:
        return tuple(t for t in self._transitions if t.axis == axis)

    def by_reversibility(self, reversibility: Reversibility) -> Tuple[Transition, ...]:
        return tuple(t for t in self._transitions if t.reversibility is reversibility)

    def find(self, *, verb: str, axis: str, from_value: Any, to_value: Any = OPEN) -> Optional[Transition]:
        """The declared edge covering ``(verb, axis, from -> to)``, or ``None``."""
        for t in self._transitions:
            if t.matches(verb=verb, axis=axis, from_value=from_value, to_value=to_value):
                return t
        return None

    def lookup(self, *, verb: str, axis: str, from_value: Any, to_value: Any = OPEN) -> Transition:
        """Like :meth:`find` but raises ``LookupError`` if no edge matches."""
        t = self.find(verb=verb, axis=axis, from_value=from_value, to_value=to_value)
        if t is None:
            raise LookupError(
                f"no declared transition for verb={verb!r} axis={axis!r} "
                f"from={from_value!r} to={to_value!r}"
            )
        return t


# ---------------------------------------------------------------------------
# assert_round_trip -- the identity contract as an executable check
# ---------------------------------------------------------------------------
class _Unset:
    pass


_UNSET = _Unset()


def assert_round_trip(
    read: Callable[[], Any],
    apply: Callable[[], Any],
    invert: Callable[[Any], Any],
    *,
    expected_new: Any = _UNSET,
) -> Any:
    """Assert ``apply`` then ``invert`` restores the observed state (L2-semantic).

    Substrate-agnostic by design: ``read`` returns whatever observation the axis
    exposes (a MODE state value, an alias's current target), ``apply`` performs
    the transition and returns its receipt, and ``invert`` consumes that receipt
    to walk the edge back. The equality is on whatever ``read`` returns, so the
    same harness covers entity-axis and index-level (routing) transitions. In
    Step 1 ``invert`` re-applies the verb toward ``receipt.previous_state`` (the
    verb is its own inverse); once ``ctx.undo(receipt)`` lands it becomes
    ``invert=ctx.undo`` with no change here.

    Returns the receipt from ``apply`` so callers can assert on it.
    """
    before = read()
    receipt = apply()
    if expected_new is not _UNSET:
        observed_new = read()
        if observed_new != expected_new:
            raise AssertionError(
                f"transition did not reach the expected state: "
                f"expected {expected_new!r}, observed {observed_new!r}"
            )
    invert(receipt)
    restored = read()
    if restored != before:
        raise AssertionError(
            f"round-trip is not the identity (L2): before={before!r} "
            f"restored={restored!r}"
        )
    return receipt


# ---------------------------------------------------------------------------
# observe -- assemble a VALIDATED EntityState from platform readings
# ---------------------------------------------------------------------------
def observe(registry: TransitionRegistry, fqcn: str, **axis_values: Any) -> EntityState:
    """Build an :class:`EntityState` from per-axis readings, validated against
    the registered axes.

    The bridge between the platform and the model: the *consumer* reads its own
    substrates (``detect_tool_state`` for MODE, ``kit_active`` for ACTIVATION,
    the discriminated-union ``type`` for KIND, ``visibility_in`` for VISIBILITY)
    and passes the readings here; this function asserts each reading is something
    the model can express. A value an axis does not admit is a contract breach --
    either the model is missing a value or the reading is wrong -- and is raised
    rather than silently stored. Stays generic: no substrate access happens here,
    so this module still imports nothing from ``engine``/``mode``.
    """
    for name, value in axis_values.items():
        try:
            axis = registry.axis(name)
        except KeyError:
            raise KeyError(f"observed unknown axis {name!r} (not registered)") from None
        if not axis.admits(value):
            raise ValueError(
                f"observed value {value!r} on axis {name!r} is not admitted by the "
                f"state model (axis values={axis.values!r}); the model does not "
                f"cover this platform state"
            )
    return EntityState(fqcn, dict(axis_values))


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
ACTIVATION_VALUES: Tuple[str, ...] = ("active", "inactive")
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
    registry is filled by the verb, never ahead of it). Only the ACTIVATION
    transitions remain absent: they land when ``dz kit enable``/``disable``
    become Groupable verbs (B4 of the unification).
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
        fqcn_fate="reborn",
        note="extract a local tool into its own git repo (creates the remote)",
    )
    _grad_mode = Transition(
        axis="mode", from_values=("embedded", "local-only"), to_value="submodule",
        verb="graduate", reversibility=Reversibility.ONE_WAY, conserved="remote_url",
        note="re-enter the graduated repo as a submodule (depends on the remote above)",
    )
    reg.register_composite(CompositeTransition(
        name="graduation", legs=(_grad_kind, _grad_mode), verb="graduate",
        atomicity="all_or_nothing", fqcn_fate="reborn",
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
    "OPEN",
    "Reversibility",
    "StateAxis",
    "EntityState",
    "Transition",
    "CompositeTransition",
    "TransitionRegistry",
    "assert_round_trip",
    "observe",
    "build_default_registry",
    "MODE_VALUES",
    "VISIBILITY_CONTINUUM",
    "VISIBILITY_VALUES",
    "ACTIVATION_VALUES",
    "KIND_VALUES",
]
