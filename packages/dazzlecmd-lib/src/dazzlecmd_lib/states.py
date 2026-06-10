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
    (ROUTING ranges over all FQCNs). ``read_only`` marks an axis that the verbs
    do not transition directly (KIND -- changed only by graduation, a composite).
    ``detect`` is an optional reader hook into the substrate; it is intentionally
    left ``None`` in the default registry so this module imports nothing from
    ``mode``/``engine`` -- the axis documents its substrate, the consumer reads it.
    """

    name: str
    values: Optional[Tuple[Any, ...]] = None
    read_only: bool = False
    substrate: str = ""
    detect: Optional[Callable[..., Any]] = None

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
VISIBILITY_VALUES: Tuple[str, ...] = ("visible", "silenced", "hidden", "shadowed")
ACTIVATION_VALUES: Tuple[str, ...] = ("active", "inactive")
KIND_VALUES: Tuple[str, ...] = ("tool", "kit", "aggregator")

# The two MODE states that constitute the dev<->publish orbit (in-orbit =
# reversible; entering from outside is one-way).
_MODE_ORBIT: Tuple[str, ...] = ("symlink", "submodule")
_MODE_OUT_OF_ORBIT: Tuple[str, ...] = ("embedded", "local-only")


def build_default_registry() -> TransitionRegistry:
    """Build the reference registry for the dazzlecmd toolset.

    Registers the four entity-state axes (KIND/MODE/VISIBILITY/ACTIVATION) plus
    the index-level ROUTING axis, and DECLARES the transitions that already ship
    live (the two ``rebind`` mechanisms -- alias routing and dev<->publish
    mode-switch). Visibility and activation transitions are intentionally absent
    until ``hide``/``expose`` and kit-activation become Groupable verbs; the
    GENERATIVE graduation edges land in the ``group``/``ungroup`` design pass.
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
        name="visibility", values=VISIBILITY_VALUES,
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
    reg.declare(Transition(
        axis="mode", from_values=_MODE_OUT_OF_ORBIT, to_value=OPEN, verb="rebind",
        reversibility=Reversibility.ONE_WAY, conserved="remote_url",
        note="entering the orbit from EMBEDDED/LOCAL_ONLY -- one-way (mini-graduation)",
    ))
    reg.declare(Transition(
        axis="mode", from_values=("missing",), to_value=OPEN, verb="rebind",
        reversibility=Reversibility.REFUSED_AT_BOUNDARY, conserved="remote_url",
        note="path missing / conserved invariant underivable -> refuse (pre-flight)",
    ))

    return reg


__all__ = [
    "OPEN",
    "Reversibility",
    "StateAxis",
    "EntityState",
    "Transition",
    "TransitionRegistry",
    "assert_round_trip",
    "observe",
    "build_default_registry",
    "MODE_VALUES",
    "VISIBILITY_VALUES",
    "ACTIVATION_VALUES",
    "KIND_VALUES",
]
