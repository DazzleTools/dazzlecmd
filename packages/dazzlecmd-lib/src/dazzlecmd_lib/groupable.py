"""Behavioral types for the ``Groupable`` verbs -- the state-transition operators.

This module houses the verb-support types so ``entity.py`` stays focused on the
entity model. It imports NOTHING from ``engine``/``mode`` -- each context
receives the handle it operates on (an ``FQCNIndex``, a filesystem context),
which keeps this module dependency-light and the verbs unit-testable against
real components.

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

from dataclasses import dataclass
from typing import Any, Protocol

from dazzlecmd_lib.continuum import ContinuumSpace
from dazzlecmd_lib.states import VISIBILITY_CONTINUUM


class CriticalityBoundaryError(Exception):
    """Raised when a transition would cross a criticality boundary.

    The conserved invariant (C2) cannot be preserved, so the transition would
    be irreversible/non-restorable -- it is refused rather than performed.

    Example: a mode-switch ``rebind`` whose published state cannot be re-derived
    (no remote URL resolvable) would be a lossy, unrecoverable change.

    This is a PRE-FLIGHT refusal (the invariant check fails before any change).
    """


class RebindError(Exception):
    """Raised when a rebind transition fails to APPLY.

    Distinct from :class:`CriticalityBoundaryError` (a pre-flight refusal): the
    invariant was fine, but the underlying mechanism failed mid-apply (e.g. the
    mode-switch returned a non-zero exit code). The transition's success/failure
    is the mechanism's; this surfaces it as the verb's typed failure.
    """


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

    def apply(self, entity: Any, target: str) -> RebindReceipt:
        # Receiver precondition: the receiver must CURRENTLY own this alias
        # (the alias must resolve to the receiver's canonical FQCN). This one
        # check catches both wrong-index and wrong-receiver. The inverse call is
        # therefore made on the NEW owner -- "receiver = current owner" stays
        # consistent across the round-trip (DWP addendum H1).
        current = self.index.alias_index.get(self.alias)
        if current is None:
            raise KeyError(
                f"alias {self.alias!r} is not registered in this index"
            )
        if current != entity.fqcn:
            raise ValueError(
                f"rebind receiver mismatch: alias {self.alias!r} currently "
                f"points at {current!r}, not the receiver {entity.fqcn!r}. "
                f"Call rebind on the alias's current owner."
            )
        previous = self.index.repoint_alias(self.alias, target)
        return RebindReceipt(
            entity_fqcn=entity.fqcn,        # C1 -- unchanged by the rebind
            sub_kind="alias",
            previous_state=previous,        # repoint back here to invert
            new_state=target,
            invariant=RebindInvariant(
                conserved_quantity_name="single_hop_rule",
                conserved_value=entity.fqcn,
                restore_path="repoint the alias back to previous_state",
            ),
            reversible=True,                # alias repoint is always reversible
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

# The kit-presence space: the visibility ladder as ONE presence axis on a shared
# scale, each rung carrying its typed VisibilityRung payload. The `dz kit
# visibility` surface navigates it and READS the rung objects (no string table).
# Single-axis today; activation / load compose as further axes per the
# ContinuumSpace DWP -- the seam is ready.
KIT_PRESENCE_SPACE = ContinuumSpace(
    name="kit_presence",
    meaning="how present a tool is to dz (listing + dispatch)",
    axes={"visibility": VISIBILITY_CONTINUUM},
    presence={"visibility": dict(VISIBILITY_CONTINUUM.ranks)},
    payloads={"visibility": VISIBILITY_RUNGS},
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

    # -- the operation -------------------------------------------------------
    def apply(self, entity, target, *, verb):
        if self.frame is not None:
            raise CriticalityBoundaryError(
                "frame-relative visibility is not wired in this slice -- only the "
                "global frame (frame=None) is supported until #79 environments land."
            )
        if target not in VISIBILITY_CONTINUUM.ranks:
            raise ValueError(
                f"unknown visibility level {target!r}; expected one of {VISIBILITY_ORDER}"
            )
        fqcn = entity.fqcn
        prev = self.current_level(entity)
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
                f"{fqcn} is constitutional (always_active) -- it may be hidden but "
                f"never shadowed (C3: constitutional items are never removed)."
            )

        before = self._read_suppressed(fqcn)
        self._write_level(fqcn, target)
        after = set(VISIBILITY_CONTINUUM.channels_at(target))
        self._applied_entity = entity
        return VisibilityReceipt(
            entity_fqcn=fqcn,
            sub_kind="visibility",
            previous_state=prev,
            new_state=target,
            invariant=VisibilityInvariant(conserved_value=fqcn),
            reversible=True,
            channels_suppressed=tuple(sorted(after - before)),
            channels_restored=tuple(sorted(before - after)),
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

    def _tools(self):
        return list(getattr(self.boundary, "tools", []) or [])

    def contains(self, entity):
        return entity.fqcn in self._tools()

    def apply(self, entity, target, *, verb):
        fqcn = entity.fqcn
        # Graduation regime: generative (tool -> own repo); fs+git is #73.
        if target == self.GRADUATE:
            raise CriticalityBoundaryError(
                f"graduation of {fqcn} is generative (tool -> own git repo): the "
                f"transition is declared in the registry as a CompositeTransition, "
                f"but its fs+git execution lands with #73. Only the reversible "
                f"in-tree move is wired here."
            )
        # C3: constitutional items may be grouped (and hidden) but never ungrouped
        # out of the tree.
        if verb == "ungroup" and getattr(entity, "always_active", False):
            raise CriticalityBoundaryError(
                f"{fqcn} is constitutional (always_active) -- it may be grouped or "
                f"hidden but never ungrouped out of the tree (C3)."
            )

        was_in = fqcn in self._tools()
        prev = self.boundary.fqcn if was_in else None
        tools = self._tools()
        if verb == "group":
            if fqcn not in tools:
                tools.append(fqcn)
            new = self.boundary.fqcn
        elif verb == "ungroup":
            if fqcn in tools:
                tools.remove(fqcn)
            new = None
        else:
            raise ValueError(f"unknown containment verb {verb!r}")
        setattr(self.boundary, "tools", tools)
        self._applied_entity = entity
        return ContainmentReceipt(
            entity_fqcn=fqcn,
            sub_kind="containment",
            previous_state=prev,
            new_state=new,
            invariant=ContainmentInvariant(conserved_value=fqcn),
            reversible=True,
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


# Public API surface -- frozen until 1.0 (Gate I). See the lib README.
__all__ = [
    # errors
    "CriticalityBoundaryError",
    "RebindError",
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
    # containment (group/ungroup)
    "ContainmentInvariant",
    "ContainmentReceipt",
    "ContainmentContext",
]
