"""``dazzlecmd_lib.continuum`` -- the signed ordered-axis primitive (the bones
of every Groupable verb's ladder).

A **Continuum** is an axis whose states are TOTALLY ORDERED by a SIGNED rank
with an INVARIANT-BEARING ZERO: `cold pole (-N) ... 0 (neutral, the invariant)
... warm pole (+M)`. 0 is not "nothing" -- it is the canonical, no-lean state
where the conserved invariant is purely held; leaning toward either pole is a
projection away from it (freely reversible across the band), and a pole is the
criticality boundary where the invariant breaks. This is the THAC0 logger model
(`NOTHING=-4 ... DEFAULT=0 ... DEBUG=+3`, gate `level <= threshold`) generalized
so the SAME primitive serves the visibility ladder, activation, the load/pointer
spectrum, AND log verbosity.

**PURE + import-clean BY CHARTER.** This module imports ONLY stdlib typing/
dataclasses -- no ``os``/``subprocess``/path/platform, no I/O, no effects. The
ordering, poles, stepping, channel presets, and the threshold predicate are all
deterministic functions over ints + declared data. Effectful state changes
(writing config, git, filesystem) live in the *contexts* that CONSUME a
Continuum, never here. This purity is what keeps the primitive eligible to lift
into the ``dazzle-lib`` bedrock as a core interface importable by every project
(see the continuum DWP, 2026-06-13); the guard test
``test_continuum_is_pure`` pins it.

Two backings, one interface:
- **scalar** (THAC0 logger): rank IS the level; ``passes(level, threshold)`` is
  the emit gate.
- **channel-backed** (visibility ladder): each level maps to a monotone set of
  suppressed/active CHANNELS; ``level_for_channels`` inverts a channel set to its
  level. Channels are the orthogonal sub-dimension (THAC0's per-channel
  thresholds == visibility's hints/display/resolution surfaces).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    FrozenSet,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)


class ContinuumError(Exception):
    """Base for continuum misuse (unknown level, etc.)."""


class ContinuumBoundaryError(ContinuumError):
    """Raised when a step would move past a pole (the criticality edge).

    The pole is where the conserved invariant breaks; the continuum itself
    refuses to step past it -- a consuming context decides whether the
    pole-crossing operation (e.g. remove, graduate) is permitted via its own
    criticality handling.
    """


@runtime_checkable
class ContinuumProtocol(Protocol):
    """The structural contract a continuum satisfies (the lift-to-dazzle-lib
    interface; matches dazzle-lib's ``protocols.py`` idiom -- nothing is forced
    to subclass)."""

    name: str

    def rank(self, level: str) -> int: ...
    def neutral(self) -> str: ...
    def cold_pole(self) -> str: ...
    def warm_pole(self) -> str: ...
    def step(self, level: str, direction: int) -> str: ...
    def passes(self, level: str, threshold: str) -> bool: ...


@dataclass(frozen=True)
class Continuum:
    """A signed, ordered axis with an invariant-bearing zero.

    ``ranks`` maps each level name to a SIGNED int (0 == neutral/invariant);
    the level set and ordering ARE the rank map (no separate ordered tuple to
    drift). ``channels`` optionally maps each level to its suppressed/active
    channel set (the channel-backed case; empty for a scalar continuum).
    ``invariant`` names the conserved quantity held AT rank 0.
    """

    name: str
    ranks: Mapping[str, int]
    invariant: str = ""
    channels: Mapping[str, FrozenSet[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ranks:
            raise ContinuumError(f"continuum {self.name!r} has no levels")
        # Freeze to plain dicts (frozen dataclass -> object.__setattr__).
        object.__setattr__(self, "ranks", dict(self.ranks))
        object.__setattr__(self, "channels",
                           {k: frozenset(v) for k, v in self.channels.items()})
        if len(set(self.ranks.values())) != len(self.ranks):
            raise ContinuumError(
                f"continuum {self.name!r} has duplicate ranks -- the order must "
                f"be a strict total order"
            )

    # -- order ---------------------------------------------------------------
    def levels(self) -> Tuple[str, ...]:
        """All levels ordered cold -> warm (ascending signed rank)."""
        return tuple(sorted(self.ranks, key=self.ranks.__getitem__))

    def rank(self, level: str) -> int:
        try:
            return self.ranks[level]
        except KeyError:
            raise ContinuumError(
                f"{level!r} is not a level of continuum {self.name!r}; "
                f"levels: {self.levels()}"
            )

    def neutral(self) -> str:
        """The rank-0 level (the invariant-bearing center). Raises if the axis
        declares no zero -- every well-formed continuum should name its 0."""
        for lvl, r in self.ranks.items():
            if r == 0:
                return lvl
        raise ContinuumError(
            f"continuum {self.name!r} declares no neutral (rank-0) level"
        )

    def cold_pole(self) -> str:
        """The minimum-rank level (the cold criticality edge)."""
        return min(self.ranks, key=self.ranks.__getitem__)

    def warm_pole(self) -> str:
        """The maximum-rank level (the warm criticality edge)."""
        return max(self.ranks, key=self.ranks.__getitem__)

    def compare(self, a: str, b: str) -> int:
        """-1 if a is colder than b, +1 if warmer, 0 if equal."""
        ra, rb = self.rank(a), self.rank(b)
        return (ra > rb) - (ra < rb)

    def is_warmer(self, a: str, b: str) -> bool:
        return self.rank(a) > self.rank(b)

    def is_colder(self, a: str, b: str) -> bool:
        return self.rank(a) < self.rank(b)

    # -- stepping (the low-level primitive; the warm/cold lenses build their
    #    unambiguous more/less on top of this signed step) --------------------
    def step(self, level: str, direction: int) -> str:
        """Move one rung toward warm (``direction > 0``) or cold (``< 0``).

        Raises ``ContinuumBoundaryError`` at a pole (stepping past the
        criticality edge); the consuming context decides pole-crossing policy.
        """
        if direction == 0:
            return level
        cur = self.rank(level)
        ordered = self.levels()  # cold -> warm
        idx = ordered.index(level)
        nxt = idx + (1 if direction > 0 else -1)
        if nxt < 0 or nxt >= len(ordered):
            pole = "warm" if direction > 0 else "cold"
            raise ContinuumBoundaryError(
                f"cannot step {pole}-ward past the {pole} pole "
                f"({level!r}) of continuum {self.name!r}"
            )
        return ordered[nxt]

    # -- directional framings (the {P, not-P} duality; RGB/CMYK) -------------
    # `more`/`less` alone are ambiguous ("more of WHAT?"). Anchor them to an
    # absolute via a LENS: a framing picks which pole is "more," and within it
    # `.more`/`.less` are unambiguous. `warm` (additive) and `cold` (subtractive)
    # are two COMPLETE constructions of the one axis (RGB vs CMYK) -- the
    # cross-lens identity `warm.more == cold.less` holds. warm/cold is the
    # PRIMITIVE vocabulary only; user-facing names stay the DOMAIN verbs
    # (hide/expose, enable/disable), which bind to a framing.
    @property
    def warm(self) -> "_ContinuumLens":
        """The WARM framing (additive): ``.more`` steps toward the warm/+ pole,
        ``.less`` toward cold."""
        return _ContinuumLens(self, +1, "warm")

    @property
    def cold(self) -> "_ContinuumLens":
        """The COLD framing (subtractive, the dual of ``warm``): ``.more`` steps
        toward the cold/- pole, ``.less`` toward warm. ``cold.more == warm.less``
        -- both construct the full axis."""
        return _ContinuumLens(self, -1, "cold")

    # -- the THAC0 threshold predicate (scalar / cursor consumers) -----------
    def passes(self, level: str, threshold: str) -> bool:
        """THAC0 emit gate: a thing at ``level`` passes a ``threshold`` cursor
        when it is at-or-colder than the threshold (``rank <= threshold``).

        This is the logger's ``message.level <= verbosity`` lifted: ``level`` is
        the message/position, ``threshold`` the active cutoff. Pure int compare
        -- the hot path stays a single comparison (logger-generality + the
        cheap-hot-path constraint from the DWP).
        """
        return self.rank(level) <= self.rank(threshold)

    # -- channel backing (visibility / per-channel consumers) ----------------
    def channels_at(self, level: str) -> FrozenSet[str]:
        """The channel set a level expresses (suppressed surfaces for
        visibility; empty for a scalar continuum)."""
        self.rank(level)  # validate membership
        return self.channels.get(level, frozenset())

    def level_for_channels(self, present: FrozenSet[str]) -> str:
        """Invert a channel set to the level it denotes -- "the coldest level
        whose UNIQUELY-INTRODUCED channel is present" (equivalently: the highest
        channel present wins). Derived from the declared monotone presets rather
        than hand-coded, so adding a rung needs no code change; matches the
        visibility ladder's ``level_for_channels`` exactly (incl. a non-preset
        edit like ``{display}`` -> the level that introduces ``display``).
        """
        if not self.channels:
            raise ContinuumError(
                f"continuum {self.name!r} is scalar (no channel backing); "
                f"level_for_channels does not apply"
            )
        present = frozenset(present)
        ordered = self.levels()  # cold -> warm; each rung is a superset of warmer
        for i, level in enumerate(ordered):
            warmer = self.channels.get(ordered[i + 1], frozenset()) \
                if i + 1 < len(ordered) else frozenset()
            introduced = self.channels.get(level, frozenset()) - warmer
            if introduced & present:
                return level
        # Nothing introduced is present -> the neutral / warmest level.
        return self.warm_pole()


@dataclass(frozen=True)
class _ContinuumLens:
    """One directional FRAMING of a Continuum (the {P, not-P} / RGB-CMYK duality).

    A lens fixes which absolute is "more": the ``warm`` lens (additive) steps
    ``more`` toward the warm/+ pole; the ``cold`` lens (subtractive) steps
    ``more`` toward the cold/- pole. Within a lens, ``more``/``less`` are
    unambiguous. The two lenses are complete, complementary constructions of the
    SAME signed axis (like RGB and CMYK) -- the cross-lens identity
    ``c.warm.more(x) == c.cold.less(x)`` holds. Obtained via ``Continuum.warm`` /
    ``Continuum.cold``; not constructed directly.
    """

    continuum: "Continuum"
    sign: int            # +1 = warm framing, -1 = cold framing
    name: str            # "warm" | "cold"

    def more(self, level: str) -> str:
        """One rung MORE toward this framing's pole (raises at the pole)."""
        return self.continuum.step(level, self.sign)

    def less(self, level: str) -> str:
        """One rung LESS (away from this framing's pole / toward its complement)."""
        return self.continuum.step(level, -self.sign)

    def pole(self) -> str:
        """This framing's pole: ``warm_pole`` for warm, ``cold_pole`` for cold."""
        return (self.continuum.warm_pole() if self.sign > 0
                else self.continuum.cold_pole())


# ===========================================================================
# ContinuumSpace -- N parallel Continuums composed on a shared PRESENCE scale.
# ===========================================================================
# A domain-NEUTRAL composition primitive: take N Continuum axes (each a distinct
# mechanism) and project every (axis, level) onto ONE shared signed PRESENCE
# scale -- "how much of the axis's quality is expressed" -- so the orthogonal
# axes become comparable and a strict merged order (the *spectrum*) emerges.
# "next colder / next warmer" navigation is then well-defined ACROSS axes.
#
# PRESENCE is a general abstraction, NOT visibility: warm = MORE present, cold =
# LESS present, of WHATEVER quality the axis measures -- water for wet/dry, heat
# for hot/cold, loudness for quiet/loud, listing for visible/hidden, dispatch for
# enabled/disabled. It applies to ANY abstract type; visibility is just one axis.
# Presence is the grouping<->ungrouping reading of warm/cold at the space level
# (group = make more present, ungroup = make less present).
#
# Concrete (the canonical dazzlecmd presence space): silence, hide, shadow,
# disable, detach, remove are DIFFERENT mechanisms (different config keys, code
# paths) but ALL move a tool MORE or LESS present. A ContinuumSpace aligns them on
# one scale so "the next STRONGER (colder) / WEAKER (warmer) move" is well-defined
# across those orthogonal mechanisms -- the keystone of the same-bones thesis at
# the verb layer.
#
# Membership is LOOSE/STRUCTURAL (matching the ContinuumProtocol idiom): an axis
# joins by satisfying ContinuumProtocol AND declaring its presence coordinates
# (level -> signed scale int). No inheritance; the "is presence-aligned" contract
# is verified at construction, the same way the constitutional boundary is test-
# enforced rather than typed. PURE -- composition + ordering over declared data;
# the effectful group/ungroup EXECUTION lives in the consuming Contexts.


@runtime_checkable
class ContinuumSpaceProtocol(Protocol):
    """The structural contract a continuum space satisfies (the lift-to-
    dazzle-lib interface; nothing is forced to subclass)."""

    name: str
    meaning: str
    axes: Mapping[str, Continuum]

    def presence_of(self, axis: str, level: str) -> int: ...
    def payload_for(self, axis: str, level: str) -> Any: ...
    def spectrum(self) -> Tuple[Tuple[str, str], ...]: ...
    def colder_than(self, axis: str, level: str) -> Optional[Tuple[str, str]]: ...
    def warmer_than(self, axis: str, level: str) -> Optional[Tuple[str, str]]: ...


@dataclass(frozen=True)
class ContinuumSpace:
    """A composition of N parallel :class:`Continuum` axes on a shared PRESENCE scale.

    ``axes`` maps an axis name to its Continuum (the mechanism). ``presence``
    maps each axis's level to a SIGNED presence coordinate -- how much of that
    axis's quality is expressed: ``0`` is the axis's NEUTRAL (its rank-0 level --
    the space-level zero every axis's default collapses onto), ``<0`` is LESS
    present (cold), ``>0`` is MORE present (warm). The non-zero coordinates form
    one strict merged order across all axes -- the *spectrum* -- so
    ``colder_than``/``warmer_than`` can hop between axes (one axis's cold rung to
    another's).

    PRESENCE is a GENERAL abstraction, NOT tied to visibility -- the quality being
    measured is per-instance (water for wet/dry, heat for hot/cold, listing for
    visible/hidden, dispatch for enabled/disabled). warm = more present, cold =
    less present is the grouping<->ungrouping reading of the {P, not-P} / RGB-CMYK
    duality (see the directionality / 4-fold note). ``meaning`` is a caller-
    supplied, human-readable description of WHAT this space's scale measures (e.g.
    "output visibility", "how wet", "task priority") so the space is self-
    describing and interrogable via :meth:`describe` -- one reads it to judge what
    fits. ``invariant`` names the conserved quantity at the shared 0 (per-instance,
    like a Continuum's) -- NOT the scale's name. Navigation is framing-NEUTRAL
    (absolute warm/cold); a surface binds "stronger/weaker" (or ``--adjacent``).

    Contract (verified at construction + by the contract tests):
    - ``axes`` and ``presence`` name exactly the same axes;
    - each axis's presence map covers exactly that Continuum's levels;
    - presence is ALIGNED: strictly increasing cold->warm, with the neutral
      (rank-0) level -- and only it -- at presence 0;
    - all non-zero coordinates are unique across the whole space (a strict merged
      order).
    """

    name: str
    axes: Mapping[str, "Continuum"]
    presence: Mapping[str, Mapping[str, int]]
    meaning: str = ""
    invariant: str = ""
    # Optional caller-supplied TYPED payload per (axis, level) -- the "templated
    # object" a rung carries beyond its signed coordinate (a domain rung type,
    # e.g. a visibility VERB binding). The space HOLDS + exposes it opaquely
    # (``payload_for``); it never interprets or calls it -- so the primitive stays
    # pure + domain-neutral while consumers get a typed object, not a string dict.
    payloads: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.axes:
            raise ContinuumError(f"continuum space {self.name!r} has no axes")
        object.__setattr__(self, "axes", dict(self.axes))
        object.__setattr__(self, "presence",
                           {a: dict(m) for a, m in self.presence.items()})
        object.__setattr__(self, "payloads",
                           {a: dict(m) for a, m in self.payloads.items()})
        if set(self.axes) != set(self.presence):
            raise ContinuumError(
                f"continuum space {self.name!r}: axes {sorted(self.axes)} and "
                f"presence keys {sorted(self.presence)} must name the same axes"
            )
        seen_coords = {}  # non-zero coord -> (axis, level), for global uniqueness
        for aname, cont in self.axes.items():
            pmap = self.presence[aname]
            if set(pmap) != set(cont.ranks):
                raise ContinuumError(
                    f"space {self.name!r} axis {aname!r}: presence levels "
                    f"{sorted(pmap)} must cover exactly the continuum's levels "
                    f"{sorted(cont.ranks)}"
                )
            # presence 0 <-> the neutral (rank-0) level, and only it.
            for lvl, p in pmap.items():
                if (cont.rank(lvl) == 0) != (p == 0):
                    raise ContinuumError(
                        f"space {self.name!r} axis {aname!r} level {lvl!r}: "
                        f"presence 0 must align with the neutral (rank-0) level "
                        f"(<0 = suppressed, >0 = amplified)"
                    )
            # presence-aligned: strictly increasing along cold->warm rank order
            # (spans the full signed range -- <0 suppressed, 0 neutral, >0 amplified).
            ordered = cont.levels()  # cold -> warm
            ps = [pmap[lvl] for lvl in ordered]
            if any(ps[i] >= ps[i + 1] for i in range(len(ps) - 1)):
                raise ContinuumError(
                    f"space {self.name!r} axis {aname!r}: presence must be "
                    f"strictly increasing cold->warm (presence-aligned); got "
                    f"{list(zip(ordered, ps))}"
                )
            # non-zero coordinates are globally unique (the merged order is a
            # strict total order; neutrals share 0 and are the space-level zero).
            for lvl, p in pmap.items():
                if p != 0:
                    if p in seen_coords:
                        oa, ol = seen_coords[p]
                        raise ContinuumError(
                            f"space {self.name!r}: presence {p} reused by "
                            f"({oa},{ol}) and ({aname},{lvl}) -- non-zero "
                            f"coordinates must be unique across the space"
                        )
                    seen_coords[p] = (aname, lvl)

    # -- axis access ---------------------------------------------------------
    def axis(self, name: str) -> "Continuum":
        try:
            return self.axes[name]
        except KeyError:
            raise ContinuumError(
                f"{name!r} is not an axis of space {self.name!r}; "
                f"axes: {tuple(self.axes)}"
            )

    def payload_for(self, axis: str, level: str) -> Any:
        """The caller-supplied TYPED payload at ``(axis, level)`` -- the rung's
        "templated object" beyond its coordinate -- or ``None`` if none was
        supplied. Returned opaquely: the consumer knows its type and calls its
        methods (no string dict). Pairs with navigation: ``colder_than`` ->
        ``payload_for`` walks to a neighbour and exposes its object."""
        self.axis(axis).rank(level)  # validate level membership
        return self.payloads.get(axis, {}).get(level)

    def presence_of(self, axis: str, level: str) -> int:
        """The shared-scale presence coordinate of ``(axis, level)`` (0 = fully
        present, <0 = suppressed)."""
        self.axis(axis).rank(level)  # validate level membership
        return self.presence[axis][level]

    def is_neutral(self, axis: str, level: str) -> bool:
        """True when ``(axis, level)`` is fully present (presence 0)."""
        return self.presence_of(axis, level) == 0

    # -- the merged presence spectrum + navigation ---------------------------
    def spectrum(self) -> Tuple[Tuple[str, str], ...]:
        """All NON-NEUTRAL states, warm -> cold (descending presence): the
        navigable merged ladder. The shared neutral (presence 0 -- the space-
        level zero every axis's default collapses onto) is the implicit center
        and is not listed. The proof the axes share one scale:
        ``... featured > [neutral] > silenced > hidden > shadowed > disabled ...``
        """
        items = [(a, lvl) for a, m in self.presence.items()
                 for lvl, p in m.items() if p != 0]
        items.sort(key=lambda al: self.presence[al[0]][al[1]], reverse=True)
        return tuple(items)

    def colder_than(self, axis: str, level: str) -> Optional[Tuple[str, str]]:
        """The next COLDER (more-ungrouped) coordinate on the merged scale, or
        ``None`` at the cold pole. Crosses axes at adjacent presence (e.g.
        ``shadowed`` -> ``disabled``); landing on the shared zero returns THIS
        axis's neutral. Framing-NEUTRAL -- a surface labels it 'stronger'/'weaker'
        (or shows both via ``--adjacent``) per its own figure pole."""
        cur = self.presence_of(axis, level)
        colder = [(a, lvl, p) for a, m in self.presence.items()
                  for lvl, p in m.items() if p < cur]
        if not colder:
            return None
        target = max(p for _, _, p in colder)        # closest-colder presence
        if target == 0:
            return (axis, self.axis(axis).neutral())  # the shared zero -> own default
        return next((a, lvl) for a, lvl, p in colder if p == target)

    def warmer_than(self, axis: str, level: str) -> Optional[Tuple[str, str]]:
        """The next WARMER (more-grouped) coordinate on the merged scale, or
        ``None`` at the warm pole. Symmetric to :meth:`colder_than` -- e.g. from
        a suppressed state up to its axis's neutral, or from neutral up to an
        amplified (``>0``) state if any axis has one."""
        cur = self.presence_of(axis, level)
        warmer = [(a, lvl, p) for a, m in self.presence.items()
                  for lvl, p in m.items() if p > cur]
        if not warmer:
            return None
        target = min(p for _, _, p in warmer)        # closest-warmer presence
        if target == 0:
            return (axis, self.axis(axis).neutral())
        return next((a, lvl) for a, lvl, p in warmer if p == target)

    # -- interrogation -------------------------------------------------------
    def describe(self) -> str:
        """A human-readable summary -- what this space MEANS, the axes that
        compose it (with their presence coordinates), and the merged spectrum --
        so a caller can see at a glance what the space measures and judge what
        fits it. The self-describing affordance for a domain-neutral primitive."""
        lines = [f"ContinuumSpace {self.name!r}: "
                 f"{self.meaning or '(no stated meaning)'}"]
        if self.invariant:
            lines.append(f"  conserved at 0: {self.invariant}")
        for aname, cont in self.axes.items():
            rungs = ", ".join(f"{lvl}[{self.presence_of(aname, lvl):+d}]"
                              for lvl in cont.levels())  # cold -> warm
            lines.append(f"  axis {aname!r}: {rungs}")
        spec = " > ".join(f"{a}:{lvl}" for a, lvl in self.spectrum())
        lines.append(f"  spectrum (warm->cold): {spec or '(none)'}")
        return "\n".join(lines)
