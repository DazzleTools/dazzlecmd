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
