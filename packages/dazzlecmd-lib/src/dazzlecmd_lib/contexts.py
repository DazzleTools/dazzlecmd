"""dazzlecmd's per-verb CONTEXTS -- the state-transition operators bound to its substrates.

This module (renamed from ``groupable.py`` in B3d, once the generic machinery
lifted out) houses the dazzlecmd-specific verb contexts that BIND the bedrock's
generic :class:`~dazzle_lib.transitions.TransitionContext` engine to dazzlecmd's
substrates -- ``AliasRebindContext`` (FQCN index), ``VisibilityContext`` /
``ContainmentContext`` / ``ProjectionContext`` (config + tree) -- plus their
per-verb ``*Receipt`` / ``*Invariant`` types, ``KIT_PRESENCE_SPACE``, and ``Frame``.
The generic primitives (``Receipt``, ``TransitionContext``, the criticality
errors) now live in the dazzle-lib bedrock (B3a-B3c) and are re-exported at the
top of this module; ``RebindError`` is a back-compat alias of ``TransitionError``.

It still imports NOTHING from ``engine``/``mode`` -- each context receives the
handle it operates on (an ``FQCNIndex``, a filesystem context), which keeps this
module dependency-light and the verbs unit-testable against real components.

Design (see the #84 behavioral-phase DWP + its 2026-06-09 hole-review addendum):

- The verbs are NOT entity-local: the mechanisms they drive (alias routing on
  ``FQCNIndex``, mode state on the filesystem) live outside the entity. So a
  verb takes an explicit ``context`` -- a :class:`RebindContext` -- that carries
  both the handle AND the identity the verb itself can't (e.g. WHICH alias).
- ``Groupable.rebind`` is a thin delegate: ``return context.apply(self, target)``.
  Each rebind sub-kind is a new context impl rather than a branch inside the
  verb -- this protocol IS the generalizable seam the PoC validates.
- C2 (the restorability invariant) is modeled as a per-transition
  :class:`RebindInvariant` naming the conserved quantity; :class:`RebindReceipt`
  records the transition so the round-trip (``rebind o rebind^-1 = identity``)
  is assertable. ``CriticalityBoundaryError`` marks where the invariant cannot
  be preserved (the transition would be irreversible -> refuse).

``Frame`` (reserved): a presentation/consumer context that ``hide``/``expose``
will consume (it ties to ``AggregatorConfig.presentation``). ``rebind`` is NOT
frame-relative, so Frame is only reserved here, not built.
"""

from __future__ import annotations

import json
import os

from dataclasses import dataclass
from typing import Any, Protocol

from dazzlecmd_lib.continuum import ContinuumSpace
from dazzlecmd_lib.states import (
    ACTIVATION_CONTINUUM,
    VISIBILITY_CONTINUUM,
    build_default_registry,
)

# The generic transition executor (Receipt + TransitionContext) and its typed
# failures were lifted to the dazzle-lib bedrock (B3c; dazzle_lib.transitions).
# Re-exported here so every ``from dazzlecmd_lib.contexts import ...`` keeps
# resolving. The executor's one consumer-coupling -- an ``entity.fqcn`` access --
# is now a domain-neutral ``identity_of`` hook the per-verb contexts below supply
# (``identity_of=lambda e: e.fqcn``). ``RebindError`` stays as a back-compat alias
# of the neutral ``TransitionError`` (the executor's failure is not rebind-specific).
from dazzle_lib.transitions import (  # noqa: F401
    CriticalityBoundaryError,
    Receipt,
    TransitionContext,
    TransitionError,
)

RebindError = TransitionError

_DEFAULT_REGISTRY = build_default_registry()


@dataclass(frozen=True)
class RebindInvariant:
    """C2 descriptor: the quantity conserved across a ``rebind`` transition.

    Naming the invariant explicitly is what makes the round-trip property
    (``rebind o rebind^-1 = identity``) machine-checkable rather than vague.

    - alias rebind: the conserved quantity is the binding owner's canonical
      identity (C1 ``fqcn`` -- it never changes; only the alias pointer moves,
      under the single-hop rule).
    - mode-switch rebind (Phase 2): the remote URL (always re-derivable, so the
      published state can be restored).
    """

    conserved_quantity_name: str   # e.g. "single_hop_rule", "remote_url"
    conserved_value: Any           # the value at transition time
    restore_path: str = ""         # human note on how it is re-derived


@dataclass(frozen=True)
class RebindReceipt:
    """The record returned by ``entity.rebind()`` on success.

    Enables asserting the transition and composing its inverse: after
    ``r = e.rebind(B, context=ctx)``, rebinding back to ``r.previous_state``
    restores the prior state (while ``r.reversible`` is True).
    """

    entity_fqcn: str               # C1 identity of the binding owner (UNCHANGED)
    sub_kind: str                  # "alias" | "mode-switch"
    previous_state: Any            # the inverse target (e.g. prior canonical FQCN)
    new_state: Any                 # what it is now
    invariant: RebindInvariant
    reversible: bool               # True iff the inverse verb restores prior state
    verb: str = "rebind"


class RebindContext(Protocol):
    """The context a ``rebind`` operates within (the verb is not entity-local).

    Each rebind sub-kind implements this protocol, encapsulating its mechanism
    and carrying the identity the verb itself lacks. ``Groupable.rebind``
    delegates to ``context.apply(self, target)``; ``undo`` inverts a receipt so
    callers (and the ``assert_round_trip`` harness) need not track the new owner.
    """

    def apply(self, entity: Any, target: Any) -> RebindReceipt:  # pragma: no cover - protocol
        ...

    def undo(self, receipt: RebindReceipt) -> RebindReceipt:  # pragma: no cover - protocol
        ...


@dataclass
class AliasRebindContext:
    """Repoint the alias ``alias`` (currently owned by the receiver) to a
    different canonical FQCN, within the given ``FQCNIndex``.

    In-memory only: ``alias_index`` lives on the index. **Persistence is out of
    PoC scope** -- the index is rebuilt from manifests/config every CLI
    invocation, so a repoint evaporates with the process (DWP addendum H4). Do
    not wire a user-facing ``dz rebind`` to this path until a persistence design
    exists.

    The index (duck-typed) must expose ``alias_index`` and ``repoint_alias``.
    """

    index: Any
    alias: str

    def __post_init__(self):
        # B2b-2: run `apply` on the generic executor (the routing/rebind edge), so
        # the receipt's reversible/conserved come from the registry (F3). detect/
        # check/write are the alias-specific hooks; `undo` stays bespoke (it is
        # ENTITY-FREE -- see below).
        self._tc = TransitionContext(
            _DEFAULT_REGISTRY, "routing",
            detect=self._detect, write=self._write, check=self._check,
            identity_of=lambda e: e.fqcn,
        )

    def _detect(self, entity: Any) -> Any:
        """The canonical THIS alias currently points at (None if unregistered)."""
        return self.index.alias_index.get(self.alias)

    def _check(self, entity: Any, target: str, verb: str, prev: Any) -> None:
        # Receiver precondition: the receiver must CURRENTLY own this alias
        # (the alias must resolve to the receiver's canonical FQCN). This one
        # check catches both wrong-index and wrong-receiver. The inverse call is
        # therefore made on the NEW owner -- "receiver = current owner" stays
        # consistent across the round-trip (DWP addendum H1).
        if prev is None:
            raise KeyError(
                f"alias {self.alias!r} is not registered in this index"
            )
        if prev != entity.fqcn:
            raise ValueError(
                f"rebind receiver mismatch: alias {self.alias!r} currently "
                f"points at {prev!r}, not the receiver {entity.fqcn!r}. "
                f"Call rebind on the alias's current owner."
            )

    def _write(self, entity: Any, target: str, prev: Any) -> None:
        # repoint_alias enforces target-is-canonical (raises KeyError otherwise)
        # + the §9b/single-hop rules + short-index bookkeeping -- callers keep
        # their handling (the KeyError on a non-canonical target propagates here).
        self.index.repoint_alias(self.alias, target)
        return None

    def apply(self, entity: Any, target: str) -> RebindReceipt:
        r = self._tc.apply(entity, target, verb="rebind")
        # reversible + the conserved-invariant NAME now come from the declared
        # routing/rebind edge (r.reversible / r.conserved), not a literal. prev
        # is the detect reading (== repoint's prior target, single-threaded).
        return RebindReceipt(
            entity_fqcn=r.entity_identity,      # C1 -- unchanged by the rebind
            sub_kind="alias",
            previous_state=r.previous_state,  # repoint back here to invert
            new_state=r.new_state,
            invariant=RebindInvariant(
                conserved_quantity_name=r.conserved,
                conserved_value=r.entity_identity,
                restore_path="repoint the alias back to previous_state",
            ),
            reversible=r.reversible,        # from the declared edge
        )

    def undo(self, receipt: RebindReceipt) -> RebindReceipt:
        """Invert a prior ``apply``: repoint the alias back to
        ``receipt.previous_state``.

        Entity-free -- the context owns the alias and the index, so it looks up
        the CURRENT owner itself. This is where the receiver asymmetry of
        ``apply`` dissolves (DWP addendum H1): after the apply the alias points at
        the apply's target, and ``undo`` simply points it back, without the caller
        having to know who the new owner is. Always reversible.
        """
        current = self.index.alias_index.get(self.alias)
        if current is None:
            raise KeyError(
                f"alias {self.alias!r} is not registered in this index"
            )
        self.index.repoint_alias(self.alias, receipt.previous_state)
        return RebindReceipt(
            entity_fqcn=receipt.entity_fqcn,    # C1 -- unchanged
            sub_kind="alias",
            previous_state=current,             # where it pointed before this undo
            new_state=receipt.previous_state,   # the restored target
            invariant=RebindInvariant(
                conserved_quantity_name="single_hop_rule",
                conserved_value=receipt.entity_fqcn,
                restore_path="repoint the alias back to previous_state",
            ),
            reversible=True,
        )


# ===========================================================================
# Projection -- the group/ungroup verbs on the NAMING axis (overlay / virtual kit)
# ===========================================================================
#
# The PROJECTION axis is the second substrate the {group, ungroup} primitive
# spans (the first is CONTAINMENT -- kit membership / graduation). On the naming
# axis the two directions are:
#
#   group   = OVERLAY    -- collapse a home namespace's canonical onto THIS
#                           consumer surface (dazzlecmd_lib:core:safedel projected
#                           as core:safedel). Many homes group onto one surface.
#   ungroup = VIRTUAL KIT -- split one canonical into additional alias names
#                           (core:locked also reachable as wtf:locked). One
#                           canonical ungroups into many names.
#
# Both materialize as a single FQCNIndex alias entry, so they are SYMMETRIC and
# REVERSIBLE -- the inverse is dropping the alias (remove_alias), and the
# canonical FQCN (C1) is conserved throughout. This is the crisp contrast with
# the CONTAINMENT axis, where graduation is GENERATIVE / one-way (a new repo is
# born, the in-tree form is lost). Routing both projection directions through the
# SAME verb is what makes that asymmetry-between-axes legible in the code, and
# pins the invariant (canonical_fqcn) at the one place aliases are created.


@dataclass
class ProjectionReceipt:
    """The record returned by ``entity.group()`` / ``entity.ungroup()`` on the
    PROJECTION axis. Enables asserting the transition and composing its inverse
    (drop the alias)."""

    entity_fqcn: str          # C1 of the canonical the alias projects onto (UNCHANGED)
    verb: str                 # "group" (overlay) | "ungroup" (virtual kit)
    alias_fqcn: str           # the projection name that was added / removed
    canonical_fqcn: str       # what it resolves to (== entity_fqcn)
    conserved: str            # the invariant kept across the transition
    reversible: bool          # projection adds/removes are always reversible


@dataclass
class ProjectionContext:
    """Create (or, via ``undo``, drop) a naming PROJECTION of a canonical -- the
    runtime mechanism the PROJECTION-axis ``group``/``ungroup`` verbs delegate to.

    The verb is called on the CANONICAL target entity; ``target`` is the alias
    name to project onto it, and ``source`` tags the provenance ("overlay" for a
    constitutional overlay, or the virtual-kit manifest path). ``group`` and
    ``ungroup`` share this one mechanism -- they differ only in DIRECTION/intent
    (recorded as the receipt ``verb``), because on the naming axis both add a
    single alias and both invert by removing it (conserving the canonical FQCN).

    The index (duck-typed) must expose ``insert_alias`` and ``remove_alias``.
    Like ``AliasRebindContext``, this is in-memory only: the FQCN index is rebuilt
    from manifests/config every CLI invocation, so a projection evaporates with
    the process -- the value here is the SHARED, invariant-pinning mechanism, not
    persistence.
    """

    index: Any
    source: str = "overlay"

    def apply(self, entity: Any, target: str, *, verb: str = "group") -> ProjectionReceipt:
        # entity = the canonical target project; `target` = the alias name to add.
        # `insert_alias` enforces §9b (an alias may not shadow a canonical) and
        # the single-hop rule, raising as before -- callers keep their handling.
        self.index.insert_alias(target, entity.fqcn, source=self.source)
        return ProjectionReceipt(
            entity_fqcn=entity.fqcn,
            verb=verb,
            alias_fqcn=target,
            canonical_fqcn=entity.fqcn,
            conserved="canonical_fqcn",
            reversible=True,
        )

    def undo(self, receipt: ProjectionReceipt) -> ProjectionReceipt:
        """Invert a prior ``apply``: drop the projection alias. The canonical and
        every other name are untouched -- always reversible."""
        self.index.remove_alias(receipt.alias_fqcn)
        return ProjectionReceipt(
            entity_fqcn=receipt.entity_fqcn,
            verb="ungroup" if receipt.verb == "group" else "group",
            alias_fqcn=receipt.alias_fqcn,
            canonical_fqcn=receipt.canonical_fqcn,
            conserved="canonical_fqcn",
            reversible=True,
        )


# ===========================================================================
# Visibility -- the hide/expose verbs and the monotone channel ladder
# ===========================================================================
#
# The visibility ladder is a set of MONOTONE channel-suppression presets over
# three channels. Each ladder level suppresses strictly one more channel than
# the previous -- so the levels form a {P, -P} boundary-tightening chain, and a
# level is fully described by the SET of channels it suppresses (the channels
# addendum to the hide/expose DWP). The existing config keys ARE those
# suppression sets, one per channel:
#
#     channel       config key (persisted form)        what it suppresses
#     ----------    -------------------------------    -----------------------
#     hints         silenced_hints["tools"]            "did you mean" hints
#     display       hidden_tools                       list/tree/help rendering
#     resolution    shadowed_tools                     short-name claim + dispatch
#
# So a tool at level Hidden ({hints, display}) is in BOTH silenced_hints and
# hidden_tools -- which means the EXISTING hint/display filters already produce
# the monotone effect with no new engine logic. Shadowed adds resolution, which
# is the discovery-time removal (and the C3 hard wall for constitutional items).

VISIBILITY_CHANNELS = ("hints", "display", "resolution")

# The visibility CONTINUUM (the signed, channel-backed source of truth) now lives
# in ``states.py`` at L0, where the state registry that DECLARES the axes owns it
# (B1 of the unification); it is imported above. ``visible`` is rank 0 (veil-free,
# canonical_dispatch intact); each colder rung suppresses one more surface (hints
# -> display -> resolution); ``shadowed`` is the cold pole (refused for
# constitutional items -- C3). hide = step COLDER (less); expose = step WARMER
# (more). The module-level names below are DERIVED shims preserving the public
# surface (and ``KIT_PRESENCE_SPACE`` composes the one instance).

# Derived shims (continuum = source of truth): the level->channels presets and
# the weakest->strongest order, kept for the existing public surface.
VISIBILITY_LADDER = {lvl: VISIBILITY_CONTINUUM.channels_at(lvl)
                     for lvl in VISIBILITY_CONTINUUM.levels()[::-1]}  # warm->cold
VISIBILITY_ORDER = VISIBILITY_CONTINUUM.levels()[::-1]  # ("visible",...,"shadowed")


def level_for_channels(suppressed):
    """The ladder level a suppressed-channel set denotes -- delegates to the
    continuum (highest channel present wins; a non-preset ``{display}`` -> the
    level that introduces ``display`` == Hidden). Kept as a module function for
    the existing public surface."""
    return VISIBILITY_CONTINUUM.level_for_channels(frozenset(suppressed))


@dataclass(frozen=True)
class VisibilityRung:
    """The TYPED payload for one visibility rung -- the verbs that reach/leave it,
    the channel it introduces, and where it writes -- so consumers read typed
    fields + call methods instead of an in-CLI string table. The typed-object
    successor to the CLI's old ``SUPPRESS``/``RESTORE`` dicts (consolidation DWP
    2026-06-17); the deeper ``states.py`` ``Transition`` unification is #188.
    """

    level: str
    verb: str            # the command that REACHES this rung (suppress)
    unverb: str          # the command that LEAVES it (restore)
    channel: str         # the visibility channel it introduces
    config_key: str      # the user-config key it writes
    config_nested: bool = False           # True for silenced_hints (.tools)
    forbids_constitutional: bool = False  # C3: shadowed refuses constitutional

    def write(self, config, fqcn, *, add):
        """Return the config-update that adds/removes ``fqcn`` at this rung's
        target. PURE over the config mapping -- the engine performs the write."""
        if self.config_nested:
            section = dict(config.get(self.config_key) or {})
            tools = list(section.get("tools") or [])
            if add and fqcn not in tools:
                tools.append(fqcn)
            elif not add and fqcn in tools:
                tools.remove(fqcn)
            section["tools"] = tools
            section.setdefault("kits", [])
            return {self.config_key: section}
        items = list(config.get(self.config_key) or [])
        if add and fqcn not in items:
            items.append(fqcn)
        elif not add and fqcn in items:
            items.remove(fqcn)
        return {self.config_key: items}

    def present(self, config, fqcn):
        """Whether ``fqcn`` currently sits at this rung in ``config``."""
        if self.config_nested:
            return fqcn in ((config.get(self.config_key) or {}).get("tools") or [])
        return fqcn in (config.get(self.config_key) or [])


# The typed payloads for the suppression rungs (visible = the warm pole, no
# payload). One source of truth for the verb<->rung<->config binding.
VISIBILITY_RUNGS = {
    "silenced": VisibilityRung(
        "silenced", "silence", "unsilence", "hints", "silenced_hints",
        config_nested=True),
    "hidden": VisibilityRung(
        "hidden", "hide", "unhide", "display", "hidden_tools"),
    "shadowed": VisibilityRung(
        "shadowed", "shadow", "unshadow", "resolution", "shadowed_tools",
        forbids_constitutional=True),
}

# The ALIGNED visibility presence space: the visibility ladder as ONE presence
# axis on a merged signed scale, each rung carrying its typed VisibilityRung
# payload. Its merged spectrum is what the `dz kit visibility` navigator and
# ``EntityState.coordinates_in`` read (``presence_of``/``colder_than`` are aligned-
# space operations). It is one DIMENSION of kit-presence -- KIT_PRESENCE_SPACE
# composes it (below) with activation.
VISIBILITY_PRESENCE_SPACE = ContinuumSpace(
    name="visibility_presence",
    meaning="how present a tool is on the visibility ladder (listing + dispatch)",
    axes={"visibility": VISIBILITY_CONTINUUM},
    presence={"visibility": dict(VISIBILITY_CONTINUUM.ranks)},
    payloads={"visibility": VISIBILITY_RUNGS},
    invariant="canonical_dispatch",
)

# The kit-presence space: visibility x activation as a PRODUCT (the v0.6.0
# "alignment is a property" design). "How present a kit is" is multi-dimensional
# (visible? its kit active? -- and, at the capstone, member? materialized?), so
# the canonical KIT_PRESENCE_SPACE is the PRODUCT of those dimensions. Composing
# activation into the ALIGNED visibility space as a further aligned axis would
# absorb activation into the visibility navigator's merged spectrum; instead the
# axes compose as INDEPENDENT dimensions (presence=None). So the navigator reads
# the aligned ``axes["visibility"]`` sub-space byte-identically, the SH pairwise
# QuadrantView (visibility x activation) lives at the product level, and cross-axis
# navigation is refused by design (scale-safety). This is the production-resident
# substrate the activation re-expression + the attach/detach capstone build on.
KIT_PRESENCE_SPACE = ContinuumSpace.compose(
    "kit_presence",
    {"visibility": VISIBILITY_PRESENCE_SPACE, "activation": ACTIVATION_CONTINUUM},
    meaning="how present a tool is (listing + dispatch) x whether its kit dispatches",
    invariant="canonical_dispatch",
)


@dataclass(frozen=True)
class Frame:
    """A consumer/projection context (a Scheme-P veil over the canonical Scheme-O
    tree).

    #79's activated environment constructs one; #72's fold-depth and cd-cursor
    are session-frame parameters (distinct mechanisms, same frame concept). The
    ``channel_overrides`` field (a per-consumer channel configuration -- the
    OutputManager shape lifted from log output to visibility) is RESERVED, not
    wired: frame-relative visibility lands with #79. ``frame=None`` everywhere in
    this slice means the global frame (the running aggregator's user config).
    """

    name: str
    kind: str = "environment"        # "environment" | "aggregator" | "session"
    channel_overrides: Any = None    # reserved (frame-relative writes = #79)


@dataclass(frozen=True)
class VisibilityInvariant:
    """C2 for visibility: dispatch survives any veil.

    The conserved quantity is the canonical FQCN's dispatchability -- a
    visibility change never removes the canonical from the index, so every veil
    is reversible and Hidden keeps dispatch alive (only Shadowed frees the short
    name, and Shadowed is refused for constitutional items -- C3).
    """

    conserved_quantity_name: str = "canonical_dispatch"
    conserved_value: Any = None
    restore_path: str = "re-apply the previous visibility level"


@dataclass(frozen=True)
class VisibilityReceipt:
    """The record returned by ``entity.hide()`` / ``entity.expose()``.

    Carries the ladder-level transition plus the per-channel deltas
    (``channels_suppressed`` / ``channels_restored``) -- forward-compatible with
    fine-grained per-channel ops, while the verbs themselves only walk presets.
    """

    entity_fqcn: str
    sub_kind: str                    # "visibility"
    previous_state: str              # prior ladder level
    new_state: str                   # new ladder level
    invariant: VisibilityInvariant
    reversible: bool = True          # all visibility transitions are reversible
    channels_suppressed: tuple = ()  # channels newly suppressed by this step
    channels_restored: tuple = ()    # channels newly restored by this step
    verb: str = "hide"               # "hide" | "expose"


class VisibilityContext:
    """The context ``hide``/``expose`` operate within.

    GLOBAL path only in this slice: ``frame=None`` -> the running aggregator's
    user config (already per-aggregator-instance). ``frame=<Frame>`` raises a
    clear error -- frame-relative visibility lands with #79 environments. Writes
    go through ``engine._write_user_config`` (the tested path used by
    ``dz kit silence/shadow``) -- never raw file I/O here.
    """

    def __init__(self, engine, frame=None):
        self.engine = engine
        self.frame = frame
        self._applied_entity = None  # captured at apply() so undo() can re-target
        # B2: run on the generic executor. It resolves the DECLARED visibility
        # edge (so reversible/conserved come from the registry, not a hardcoded
        # literal -- F3) and orchestrates detect -> check -> write -> Receipt; the
        # visibility-specific substrate + guards are the hooks below.
        self._tc = TransitionContext(
            _DEFAULT_REGISTRY, "visibility",
            detect=self.current_level,
            write=self._write_and_delta,
            check=self._check_move,
            invert=self._invert_move,
            identity_of=lambda e: e.fqcn,
        )

    # -- config <-> channel mapping ------------------------------------------
    def _read_suppressed(self, fqcn):
        silenced = self.engine._get_config_dict("silenced_hints", default={}) or {}
        silenced_tools = set(silenced.get("tools", []) or [])
        hidden = set(self.engine._get_config_list("hidden_tools", default=[]) or [])
        shadowed = set(self.engine._get_config_list("shadowed_tools", default=[]) or [])
        s = set()
        if fqcn in silenced_tools:
            s.add("hints")
        if fqcn in hidden:
            s.add("display")
        if fqcn in shadowed:
            s.add("resolution")
        return s

    def current_level(self, entity):
        """The entity's current ladder level in this (global) frame."""
        return level_for_channels(self._read_suppressed(entity.fqcn))

    def _write_level(self, fqcn, target):
        """Persist the channel-suppression sets so ``fqcn`` sits at ``target``."""
        want = VISIBILITY_CONTINUUM.channels_at(target)
        silenced = dict(self.engine._get_config_dict("silenced_hints", default={}) or {})
        tools = list(silenced.get("tools", []) or [])
        kits = list(silenced.get("kits", []) or [])
        hidden = list(self.engine._get_config_list("hidden_tools", default=[]) or [])
        shadowed = list(self.engine._get_config_list("shadowed_tools", default=[]) or [])

        def _set(lst, present):
            if present and fqcn not in lst:
                lst.append(fqcn)
            elif not present and fqcn in lst:
                lst.remove(fqcn)

        _set(tools, "hints" in want)
        _set(hidden, "display" in want)
        _set(shadowed, "resolution" in want)
        self.engine._write_user_config({
            "silenced_hints": {"tools": tools, "kits": kits},
            "hidden_tools": hidden,
            "shadowed_tools": shadowed,
        })

    # -- the visibility-specific hooks the generic executor calls --------------
    def _check_move(self, entity, target, verb, prev):
        """Pre-flight: frame support, target validity, the direction guard, and
        C3 (constitutional items may be hidden, never shadowed)."""
        if self.frame is not None:
            raise CriticalityBoundaryError(
                "frame-relative visibility is not wired in this slice -- only the "
                "global frame (frame=None) is supported until #79 environments land."
            )
        if target not in VISIBILITY_CONTINUUM.ranks:
            raise ValueError(
                f"unknown visibility level {target!r}; expected one of {VISIBILITY_ORDER}"
            )
        # Direction via the continuum's SIGNED rank: hide steps COLDER (lower
        # rank, more suppressed); expose steps WARMER (higher rank). A move in
        # the wrong direction is "backwards."
        c = VISIBILITY_CONTINUUM
        if verb == "hide" and c.is_warmer(target, prev):
            raise ValueError(
                f"hide only moves toward MORE suppression; {prev!r} -> {target!r} "
                f"is backwards (use expose)"
            )
        if verb == "expose" and c.is_colder(target, prev):
            raise ValueError(
                f"expose only moves toward LESS suppression; {prev!r} -> {target!r} "
                f"is backwards (use hide)"
            )
        # C3: constitutional items may be Hidden, never pushed to the COLD POLE
        # (shadowed) -- Hidden is the maximum veil a consumer may apply.
        if target == c.cold_pole() and getattr(entity, "always_active", False):
            raise CriticalityBoundaryError(
                f"{entity.fqcn} is constitutional (always_active) -- it may be hidden but "
                f"never shadowed (C3: constitutional items are never removed)."
            )

    def _write_and_delta(self, entity, target, prev):
        """Persist the move and return the per-channel deltas for the receipt."""
        fqcn = entity.fqcn
        before = self._read_suppressed(fqcn)
        self._write_level(fqcn, target)
        after = set(VISIBILITY_CONTINUUM.channels_at(target))
        return {
            "suppressed": tuple(sorted(after - before)),
            "restored": tuple(sorted(before - after)),
        }

    def _invert_move(self, receipt):
        """The inverse move for undo: restore the prior level (hide<->expose)."""
        verb = "expose" if VISIBILITY_CONTINUUM.is_warmer(
            receipt.previous_state, receipt.new_state) else "hide"
        return (receipt.previous_state, verb)

    # -- the operation (runs on the generic executor) --------------------------
    def apply(self, entity, target, *, verb):
        r = self._tc.apply(entity, target, verb=verb)
        self._applied_entity = entity
        # reversible + the conserved-invariant NAME now come FROM the declared
        # transition (r.reversible / r.conserved), not a hardcoded literal (F3).
        return VisibilityReceipt(
            entity_fqcn=r.entity_identity,
            sub_kind="visibility",
            previous_state=r.previous_state,
            new_state=r.new_state,
            invariant=VisibilityInvariant(
                conserved_quantity_name=r.conserved, conserved_value=r.entity_identity),
            reversible=r.reversible,
            channels_suppressed=r.payload["suppressed"],
            channels_restored=r.payload["restored"],
            verb=verb,
        )

    def undo(self, receipt):
        """Re-apply ``receipt.previous_state`` -- the inverse walk. The direction
        is whichever restores the prior level (undo of a hide is an expose, and
        vice versa)."""
        entity = self._applied_entity
        if entity is None:
            raise RebindError(
                "VisibilityContext.undo() requires a prior apply() on this context."
            )
        target = receipt.previous_state
        # The inverse direction: if the prior level is WARMER than where we
        # landed, restoring it is an expose; otherwise a hide.
        verb = "expose" if VISIBILITY_CONTINUUM.is_warmer(
            target, receipt.new_state) else "hide"
        return self.apply(entity, target, verb=verb)


# ===========================================================================
# Activation -- the enable/disable verbs (the kit-loading toggle)
# ===========================================================================
#
# enable/disable toggle whether a KIT contributes its tools, via the user config's
# active_kits / disabled_kits lists (a kit is INACTIVE iff it sits in
# disabled_kits). It is the activation axis of the multi-axis kit-presence space --
# a binary, always-REVERSIBLE (lateral) round-trip: the kit's config membership is
# never destroyed, so enable o disable = identity. Unlike visibility (which acts on
# a tool ENTITY's fqcn), activation acts on a kit NAME; the generic executor needs
# only identity_of -> str, so a lightweight _KitRef carries it.


@dataclass(frozen=True)
class ActivationInvariant:
    """C2 for activation: a kit's re-activatable config membership survives the toggle.

    Disabling never removes the kit from discovery -- it only moves the kit's name
    between ``active_kits`` / ``disabled_kits`` -- so every enable/disable round-trips.
    """

    conserved_quantity_name: str = "kit_activation"
    conserved_value: Any = None
    restore_path: str = "re-apply the previous activation level (enable<->disable)"


@dataclass(frozen=True)
class ActivationReceipt:
    """The record returned by ``ActivationContext.apply`` (enable / disable).

    Mirrors ``VisibilityReceipt``: it carries the level transition plus the declared
    edge's ``kind`` (``"lateral"`` -- enable/disable round-trip) so the move's
    reversibility class is DATA from the registry, not an assumption at the surface.
    """

    entity_identity: str             # the kit name
    sub_kind: str                    # "activation"
    previous_state: str              # "active" | "inactive"
    new_state: str
    invariant: ActivationInvariant
    reversible: bool = True
    kind: str = "lateral"            # Transition.kind of the declared edge
    verb: str = "enable"             # "enable" | "disable"


class _KitRef:
    """Minimal identity wrapper: activation operates on a kit NAME, not a tool
    entity. The generic executor needs only ``identity_of`` -- this supplies it."""

    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name


class ActivationContext:
    """The context ``dz kit enable`` / ``dz kit disable`` operate within -- the
    activation analog of :class:`VisibilityContext`.

    The substrate is the user config's ``active_kits`` / ``disabled_kits`` lists (a
    kit is INACTIVE iff it sits in ``disabled_kits``, ACTIVE otherwise). Runs on the
    generic :class:`~dazzle_lib.transitions.TransitionContext` so ``reversible`` /
    ``conserved`` come from the DECLARED activation edges, not hardcoded literals.
    Writes go through ``engine._write_user_config`` (the tested merge path) -- never
    raw file I/O here.
    """

    def __init__(self, engine):
        self.engine = engine
        self._tc = TransitionContext(
            _DEFAULT_REGISTRY, "activation",
            detect=self._current_level,
            write=self._write_level,
            identity_of=lambda kit: kit.name,
        )

    def _read_lists(self):
        active = list(self.engine._get_config_list("active_kits", default=[]) or [])
        disabled = list(self.engine._get_config_list("disabled_kits", default=[]) or [])
        return active, disabled

    def _current_level(self, kit):
        """A kit is INACTIVE iff it sits in ``disabled_kits``, else ACTIVE."""
        _active, disabled = self._read_lists()
        return "inactive" if kit.name in disabled else "active"

    def _write_level(self, kit, target, prev):
        """Move ``kit.name`` to ``target`` by the SAME active/disabled list mutation
        the verbs have always done (the merge write preserves other config keys)."""
        active, disabled = self._read_lists()
        name = kit.name
        if target == "active":
            if name in disabled:
                disabled.remove(name)
            if name not in active:
                active.append(name)
        else:  # inactive
            if name in active:
                active.remove(name)
            if name not in disabled:
                disabled.append(name)
        self.engine._write_user_config({
            "active_kits": active,
            "disabled_kits": disabled,
        })
        return {"active_kits": active, "disabled_kits": disabled}

    def _edge(self, verb):
        """The declared activation transition for ``verb`` (for its ``kind``)."""
        return next(t for t in _DEFAULT_REGISTRY.for_verb(verb)
                    if t.axis == "activation")

    def apply(self, kit_name, target, *, verb):
        """Toggle ``kit_name`` to ``target`` (``"active"`` / ``"inactive"``) via the
        generic executor; return an :class:`ActivationReceipt` (carrying the declared
        edge's ``kind``, so the move's reversibility class is registry data)."""
        r = self._tc.apply(_KitRef(kit_name), target, verb=verb)
        return ActivationReceipt(
            entity_identity=r.entity_identity,
            sub_kind="activation",
            previous_state=r.previous_state,
            new_state=r.new_state,
            invariant=ActivationInvariant(
                conserved_quantity_name=r.conserved, conserved_value=r.entity_identity),
            reversible=r.reversible,
            kind=self._edge(verb).kind,
            verb=verb,
        )

    def enable(self, kit_name):
        """Enable ``kit_name`` (-> active): add to active_kits, drop from disabled."""
        return self.apply(kit_name, "active", verb="enable")

    def disable(self, kit_name):
        """Disable ``kit_name`` (-> inactive): add to disabled_kits, drop from active."""
        return self.apply(kit_name, "inactive", verb="disable")


# ===========================================================================
# Containment -- the group/ungroup verbs (the {P, -P} boundary primitive)
# ===========================================================================
#
# group forms a boundary (incorporate an entity into a kit/aggregator's
# membership -- LOSSY); ungroup dissolves it (disincorporate -- GENERATIVE).
# They are inverses ONLY while the conserved invariant holds. Two regimes,
# split by the criticality point:
#
#   - REVERSIBLE (in-tree move): the entity stays local; C2 = local
#     incorporability (its files + canonical FQCN are re-groupable). group o
#     ungroup = identity. This is the slice wired here.
#   - GENERATIVE (graduation): ungroup PAST criticality -- the entity leaves the
#     tree to become its own git repo (lifecycle.graduated_to; fs+git). fqcn is
#     reborn; not auto-reversible. Declared in the registry as a Composite
#     transition (KIND+MODE+identity); its fs+git body lands with #73, so
#     requesting it here is refused at the boundary.


@dataclass(frozen=True)
class ContainmentInvariant:
    """C2 for the reversible regime: the entity stays locally re-incorporable --
    its files and canonical FQCN are untouched by an in-tree move, so re-grouping
    restores the prior state."""

    conserved_quantity_name: str = "local_incorporability"
    conserved_value: Any = None
    restore_path: str = "re-group the entity into its prior boundary"


@dataclass(frozen=True)
class ContainmentReceipt:
    """The record returned by ``entity.group()`` / ``entity.ungroup()``."""

    entity_fqcn: str
    sub_kind: str                 # "containment"
    previous_state: Any           # prior boundary fqcn, or None if ungrouped
    new_state: Any                # new boundary fqcn, or None if ungrouped
    invariant: ContainmentInvariant
    reversible: bool = True
    verb: str = "group"           # "group" | "ungroup"


class ContainmentContext:
    """The context ``group``/``ungroup`` operate within: a single boundary (a Kit
    entity with a ``tools`` membership list).

    Reversible in-tree regime only. The move is in-memory (the manifests are the
    source of truth, rebuilt each invocation -- persistence is deferred, exactly
    as for alias rebind). The GENERATIVE graduation regime is refused here (its
    fs+git body is #73); request it with ``target=ContainmentContext.GRADUATE``.
    """

    GRADUATE = "graduate"   # the graduation sentinel target (refused until #73)

    def __init__(self, boundary):
        self.boundary = boundary      # a Kit entity exposing a `.tools` list
        self._applied_entity = None
        # B2b: run on the generic executor -- it resolves the declared containment
        # edge (so reversible/conserved come from the registry, not a literal --
        # F3) and orchestrates detect -> check -> write; the boundary-specific
        # substrate + guards are the hooks below.
        self._tc = TransitionContext(
            _DEFAULT_REGISTRY, "containment",
            detect=self._current_boundary,
            write=self._write_membership,
            check=self._check_move,
            invert=self._invert_move,
            identity_of=lambda e: e.fqcn,
        )

    def _tools(self):
        return list(getattr(self.boundary, "tools", []) or [])

    def contains(self, entity):
        return entity.fqcn in self._tools()

    # -- the containment-specific hooks the generic executor calls -------------
    def _current_boundary(self, entity):
        """This entity's current boundary in THIS context (its fqcn if a member,
        else None) -- the single value the containment axis carries here."""
        return self.boundary.fqcn if entity.fqcn in self._tools() else None

    def _check_move(self, entity, target, verb, prev):
        """Pre-flight: refuse the GENERATIVE graduation regime (#73) and C3
        (a constitutional item may be grouped/hidden but never ungrouped)."""
        # Graduation regime: generative (tool -> own repo); fs+git is #73.
        if target == self.GRADUATE:
            raise CriticalityBoundaryError(
                f"graduation of {entity.fqcn} is generative (tool -> own git repo): the "
                f"transition is declared in the registry as a CompositeTransition, "
                f"but its fs+git execution lands with #73. Only the reversible "
                f"in-tree move is wired here."
            )
        # C3: constitutional items may be grouped (and hidden) but never ungrouped
        # out of the tree.
        if verb == "ungroup" and getattr(entity, "always_active", False):
            raise CriticalityBoundaryError(
                f"{entity.fqcn} is constitutional (always_active) -- it may be grouped or "
                f"hidden but never ungrouped out of the tree (C3)."
            )

    def _write_membership(self, entity, target, prev):
        """Add (group) or remove (ungroup) the entity from the boundary's tools.
        ``target is None`` is the ungroup signal (the only verb with a None
        target); both directions are idempotent."""
        fqcn = entity.fqcn
        tools = self._tools()
        if target is None:                       # ungroup
            if fqcn in tools:
                tools.remove(fqcn)
        else:                                    # group
            if fqcn not in tools:
                tools.append(fqcn)
        setattr(self.boundary, "tools", tools)
        return None

    def _invert_move(self, receipt):
        """The inverse in-tree move for undo: re-group what was ungrouped, and
        vice versa."""
        if receipt.verb == "group":
            return (None, "ungroup")
        return (self.boundary.fqcn, "group")

    # -- the operation (runs on the generic executor) --------------------------
    def apply(self, entity, target, *, verb):
        r = self._tc.apply(entity, target, verb=verb)
        self._applied_entity = entity
        # new_state is the boundary on group, None on ungroup (byte-identical to
        # the prior hand-rolled receipt); reversible + the conserved-invariant
        # NAME now come from the declared containment edge (r.reversible/r.conserved).
        new = self.boundary.fqcn if verb == "group" else None
        return ContainmentReceipt(
            entity_fqcn=r.entity_identity,
            sub_kind="containment",
            previous_state=r.previous_state,
            new_state=new,
            invariant=ContainmentInvariant(
                conserved_quantity_name=r.conserved, conserved_value=r.entity_identity),
            reversible=r.reversible,
            verb=verb,
        )

    def undo(self, receipt):
        """Invert a prior in-tree move: re-group what was ungrouped, ungroup what
        was grouped."""
        entity = self._applied_entity
        if entity is None:
            raise RebindError(
                "ContainmentContext.undo() requires a prior apply() on this context."
            )
        if receipt.verb == "group":
            return self.apply(entity, None, verb="ungroup")
        return self.apply(entity, self.boundary.fqcn, verb="group")


# ===========================================================================
# Kit membership -- group/ungroup a KIT in an AGGREGATOR (the persisting sibling)
# ===========================================================================
#
# ContainmentContext above is TOOL-in-kit + IN-MEMORY (a Kit's `.tools` list, rebuilt
# each invocation). Kit-in-aggregator membership is a DIFFERENT substrate -- the
# `kits/*.kit.json` registry FILES -- and it PERSISTS (a deregistered kit's entry is
# gone from disk, no in-memory rebuild). So this is a SIBLING context (same Groupable
# group/ungroup verbs, the generic executor, a C3 refusal), NOT a subclass: it does
# not import or extend ContainmentContext's `.tools` model. The strong `remove`
# (deregister + safedel content + deactivate) and the pointer `detach` COMPOSE onto
# this `ungroup` in later slices; here only the registry substrate moves.


def _kit_identity(kit):
    """A kit's registry name -- the stem of its ``kits/<name>.kit.json`` file."""
    return getattr(kit, "kit_name", None) or kit.name


@dataclass(frozen=True)
class KitMembershipInvariant:
    """C2 for kit-in-aggregator membership: a deregistered kit is restorable.

    The conserved quantity is the kit's REGISTRATION (its registry entry), NOT
    ContainmentContext's in-memory ``local_incorporability`` -- a different substrate
    and a different invariant. Plain ungroup restores via re-group (the captured
    entry); the strong remove additionally safedel-trashes the content so the FILES
    are recoverable too.
    """

    conserved_quantity_name: str = "kit_registration"
    conserved_value: Any = None
    restore_path: str = "re-group / dz kit add the kit (its registry entry restored)"


@dataclass(frozen=True)
class KitMembershipReceipt:
    """The record returned by ``KitMembershipContext`` group/ungroup."""

    entity_identity: str          # the kit name
    sub_kind: str                 # "membership"
    previous_state: Any           # the aggregator boundary, or None if not a member
    new_state: Any                # the boundary on group, None on ungroup
    invariant: KitMembershipInvariant
    reversible: bool = True
    verb: str = "group"           # "group" | "ungroup"


class KitMembershipContext:
    """The context kit-in-aggregator ``group``/``ungroup`` operate within -- the
    kit-level persisting SIBLING of :class:`ContainmentContext`.

    Substrate: the ``kits/*.kit.json`` registry under ``project_root``. ``group``
    registers a kit (writes its registry file); ``ungroup`` deregisters it (removes
    the file, capturing its bytes so the move round-trips byte-identically). Identity
    is the kit NAME (no tool entity). C3 refuses ungrouping an ``always_active`` kit.
    """

    def __init__(self, project_root, kits=None, *, boundary_fqcn=None):
        self.project_root = project_root
        self.kits = list(kits or [])          # the membership snapshot (for callers)
        self.boundary_fqcn = boundary_fqcn    # the aggregator's identity (for receipts)
        self._captured = {}                   # name -> registry bytes (round-trip restore)
        self._applied_entity = None
        self._tc = TransitionContext(
            _DEFAULT_REGISTRY, "membership",
            detect=self._current_boundary,
            write=self._write_membership,
            check=self._check_move,
            invert=self._invert_move,
            identity_of=_kit_identity,
        )

    def _registry_path(self, name):
        return os.path.join(self.project_root, "kits", f"{name}.kit.json")

    def is_registered(self, kit):
        return os.path.exists(self._registry_path(_kit_identity(kit)))

    # -- the LOADING axis: the `pointer` block on the registry (detach/attach) --
    # group/ungroup (above) add/remove the registry FILE (membership). These
    # add/remove a `pointer` block WITHIN it (loading): the kit stays a registered
    # member but discovery LISTS it without loading its tools. The kit-presence
    # space reads this as the LOADING pole; `dz kit detach`/`attach` drive it.
    def pointer_of(self, kit):
        """The kit's ``pointer`` block (``{"materialized": bool}``) or ``None`` --
        the LOADING-axis state. ``None`` = loaded; a block = a pointer (detached)."""
        path = self._registry_path(_kit_identity(kit))
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return (json.load(f) or {}).get("pointer")
        except (OSError, ValueError):
            return None

    def set_pointer(self, kit, *, materialized=True):
        """``detach`` the kit (LOADING -> pointer): write ``pointer:{materialized}``
        into its registry. The file stays (still a member); discovery then lists it
        but skips loading its tools. Idempotent. ``materialized`` records whether the
        content is still on disk (``True`` after detach) vs not-yet-fetched (#80)."""
        self._modify_registry(
            kit, lambda d: d.__setitem__("pointer", {"materialized": bool(materialized)}))

    def clear_pointer(self, kit):
        """``attach`` the kit (pointer -> LOADING): drop the ``pointer`` block so
        discovery loads its tools again. Idempotent (a no-op if not a pointer)."""
        self._modify_registry(kit, lambda d: d.pop("pointer", None))

    def _modify_registry(self, kit, mutate):
        """Read the kit's registry json, apply ``mutate(dict)`` in place, write it
        back in the same ``indent=4`` shape ``dz kit add`` writes."""
        name = _kit_identity(kit)
        path = self._registry_path(name)
        if not os.path.exists(path):
            raise CriticalityBoundaryError(
                f"cannot modify {name}: no registry entry (kits/{name}.kit.json)."
            )
        with open(path, encoding="utf-8") as f:
            data = json.load(f) or {}
        mutate(data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.write("\n")

    # -- the membership-specific hooks the generic executor calls --------------
    def _current_boundary(self, kit):
        """The aggregator this kit is registered in (its boundary fqcn), or None."""
        return self.boundary_fqcn if self.is_registered(kit) else None

    def _check_move(self, kit, target, verb, prev):
        """C3: a constitutional / ``always_active`` kit may be grouped but never
        ungrouped (removed) out of the aggregator."""
        if verb == "ungroup" and getattr(kit, "always_active", False):
            raise CriticalityBoundaryError(
                f"{_kit_identity(kit)} is constitutional (always_active) -- it may be "
                f"grouped but never ungrouped/removed (C3). Disable it or clear "
                f"always_active first."
            )

    def _write_membership(self, kit, target, prev):
        """``target is None`` = ungroup (capture + remove the registry file); else
        group (restore from the captured bytes, or the kit's ``registry_bytes`` hook).
        Both idempotent. Fresh registration (no captured/supplied bytes) is ``dz kit
        add``'s job, not this verb's."""
        name = _kit_identity(kit)
        path = self._registry_path(name)
        if target is None:                       # ungroup = deregister
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._captured[name] = f.read()
                os.remove(path)
        else:                                    # group = register
            data = self._captured.get(name)
            if data is None:
                data = getattr(kit, "registry_bytes", None)
            if data is None:
                raise CriticalityBoundaryError(
                    f"cannot group {name}: no captured registry entry and the kit "
                    f"carries no registry_bytes (fresh registration is `dz kit add`)."
                )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        return None

    def _invert_move(self, receipt):
        """The inverse move for undo: re-group what was ungrouped, and vice versa."""
        if receipt.verb == "group":
            return (None, "ungroup")
        return (self.boundary_fqcn, "group")

    # -- the operation (runs on the generic executor) --------------------------
    def apply(self, kit, target, *, verb):
        r = self._tc.apply(kit, target, verb=verb)
        self._applied_entity = kit
        new = self.boundary_fqcn if verb == "group" else None
        return KitMembershipReceipt(
            entity_identity=r.entity_identity,
            sub_kind="membership",
            previous_state=r.previous_state,
            new_state=new,
            invariant=KitMembershipInvariant(
                conserved_quantity_name=r.conserved, conserved_value=r.entity_identity),
            reversible=r.reversible,
            verb=verb,
        )

    def undo(self, receipt):
        """Invert a prior membership move: re-group what was ungrouped, ungroup what
        was grouped (restores the registry from the captured bytes)."""
        kit = self._applied_entity
        if kit is None:
            raise RebindError(
                "KitMembershipContext.undo() requires a prior apply() on this context."
            )
        if receipt.verb == "group":
            return self.apply(kit, None, verb="ungroup")
        return self.apply(kit, self.boundary_fqcn, verb="group")


# Public API surface -- frozen until 1.0 (Gate I). See the lib README.
__all__ = [
    # errors
    "CriticalityBoundaryError",
    "RebindError",
    # generic transition executor (the N-Contexts -> 1 collapse, B2)
    "Receipt",
    "TransitionContext",
    # rebind
    "RebindInvariant",
    "RebindReceipt",
    "RebindContext",
    "AliasRebindContext",
    # projection (group/ungroup on the naming axis: overlay / virtual kit)
    "ProjectionReceipt",
    "ProjectionContext",
    # visibility (hide/expose)
    "VISIBILITY_CHANNELS",
    "VISIBILITY_LADDER",
    "VISIBILITY_ORDER",
    "level_for_channels",
    "Frame",
    "VisibilityInvariant",
    "VisibilityReceipt",
    "VisibilityContext",
    # activation (enable/disable)
    "ActivationInvariant",
    "ActivationReceipt",
    "ActivationContext",
    # containment (group/ungroup) -- tool-in-kit, in-memory
    "ContainmentInvariant",
    "ContainmentReceipt",
    "ContainmentContext",
    # kit membership (group/ungroup) -- kit-in-aggregator, persisting sibling
    "KitMembershipInvariant",
    "KitMembershipReceipt",
    "KitMembershipContext",
]
