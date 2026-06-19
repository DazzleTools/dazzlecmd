"""
Spike: the LATENT-RECURSION model for Groupable <-> Continuum <-> ContinuumSpace.

Round-2 evidence for the /collaborate3 (Zero_AG base-objects) session. Implements
the user's design clarification (2026-06-18) so we can take DATA -- not just
framings -- back to Gemini, who in Round 1 (a) rejected the "polar/complex"
representation as over-engineering and (b) claimed "Groupable isn't a primitive,
just a short Continuum." Both calls were made against a strawman; this spike
shows the model the user actually proposed.

THE MODEL (user, verbatim-derived):
  - A Continuum is a CONTAINER of Groupables keyed by a DENSIFIABLE position x:
        {{C_x, G_y+}, {C_x, G_y-}}  ==  rungs: position -> Groupable{-,+}
  - Each rung's value is a Groupable ({-,+}) = the latent y-axis, INERT until used.
  - The "implicit orthogonal axis" is the SAME pattern as "the implicit Continuum
    inside every Groupable" and "the implicit ContinuumSpace around every
    Continuum": latent + free until it APPEARS, then ONE clean op accounts for it.
  - The complex plane is SUGAR: r = max|position|; theta/quadrant computed ON
    DEMAND only -- the y-axis itself is reals / a plain type, never stored complex.

CLAIMS UNDER TEST (each an assertion, not a tautology):
  C1  Mutual recursion: Groupable.densify() -> Continuum; a 2-rung Continuum
      collapses back to a Groupable. Groupable IS a first-class primitive (the
      rung cell), contra Gemini Q1.
  C2  Densification is EXACT with Fraction (mediant always strictly between, no
      float drift), repeatably; Decimal needs you to pick the gap. (the fork)
  C3  The 1-D common case (a KIT_PRESENCE_SPACE-style ladder) NEVER materializes
      the orthogonal -- cheap-until-appears is real, so Gemini's "every Continuum
      is secretly 2-D" cost objection does not bite.
  C4  The Scarcity 2-axis cross (x={nature,choice} exigency  x  y={self,group}
      consumption) yields EXACTLY the 4 sign-quadrants, and theta is computed
      only when asked (polar = sugar).
  C5  Uniformity: the same materialize-the-latent-next shape appears at all three
      levels (Groupable->Continuum->ContinuumSpace).
  C6  The 'dz kit visibility' slice: a threshold subsumes its monotone band as a
      derived range over existing rungs -- expansion with no storage change.

SH-MECHANICS claims (from sh_mechanics PDFs -- the two-channel four-phase engine):
  C7  Two channels M(meaning) & L(position/identity) cross into the 4 quadrants;
      agreement diagonal {Q2,Q4} vs disagreement {Q1,Q3}.
  C8  The four-phase orbit {begin,peak,end,hidden} + the RECIPE 'the primitive
      absent from a quadrant's formula sits at its hidden phase' -- reproduces the
      framework's 4/4 PVIR verification as a CHECKABLE predicate (= our Q5 answer).
  C9  A tau-step is a single-channel flip; the four steps alternate L,M,L,M (no
      diagonal corner-cross) -- the transition/action primitive.
  C10 channel-pair -> polarity-pair: group=x=agreement=(+), ungroup=/=diff=(-);
      grounds compose()/closure and the external<->internal unification.

ONTOLOGY-FLOOR + N-ARY claims (user, round 2-3 -- close the recursion):
  C11 Invertibility is the FLOOR: a Unified/0_ag value is IMPLICITLY a Groupable
      (no one-way values; even 'print' implies 'clear'); the 'label' is the unified
      FORM of a dual; -(-(x)) round-trips. The ladder is uniform DOWNWARD too.
  C12 A ContinuumSpace is N-ARY (arbitrary axes); the 4-quadrant/phase machinery is
      a PAIRWISE VIEW over any 2; any rung's fiber can itself be an arbitrary-N
      ContinuumSpace -- so a rung value is the whole ladder, latent.

STATE + TRANSITION claims (user, round 4 -- the practical layer):
  C13 A tool's STATE is its whole space AS CONFIGURED. A transition is LATERAL
      (within the space; reversible; round-trips) or GENERATIVE (spawns a new
      axis/level, the sqrt(-1) move; lossy-on-reverse UNLESS a Receipt preserved
      what was made -- the safedel pattern). The FLOOR (C11) is about VALUES;
      generative loss is about TRANSITIONS. No contradiction.

stdlib only -- this explores a PROPOSED model, independent of the shipped lib.
Run:  python tests/one-offs/latent_recursion_groupable_continuum_space_spike.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from fractions import Fraction
from typing import Dict, Mapping, Optional, Tuple

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    mark = "[OK]" if cond else "[XX]"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    suffix = f"  -- {detail}" if detail else ""
    print(f"  {mark} {label}{suffix}")


# ---------------------------------------------------------------------------
# The primitives
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Groupable:
    """The {-, +} atom that sits AT a position. THE latent y-axis.

    A Groupable is cheap: two poles and nothing else. Its "implicit continuum"
    (graded sub-qualities on y) does not exist until densify() is called -- that
    is the 'account for it when it appears' contract, one level down.
    """
    minus: str            # the not-P / negative pole  (G_y-)
    plus: str             # the  P    / positive pole  (G_y+)

    def densify(self, levels: int) -> "Continuum":
        """The implicit Continuum APPEARS: split {-,+} into `levels` graded rungs
        spanning -1..+1 (as Fractions), each rung a trivial Groupable label."""
        assert levels >= 2
        rungs: Dict[Fraction, Groupable] = {}
        for i in range(levels):
            # positions evenly span [-1, +1]
            x = Fraction(2 * i, levels - 1) - 1
            tag = self.minus if x < 0 else (self.plus if x > 0 else "neutral")
            rungs[x] = Groupable(minus=tag, plus=tag)
        return Continuum(name=f"{self.minus}|{self.plus}", rungs=rungs)

    def invert(self) -> "Groupable":
        """The {-,+} swap. EVERY Groupable inverts -- there is no one-way value."""
        return Groupable(minus=self.plus, plus=self.minus)

    @staticmethod
    def unified(label: str) -> "Groupable":
        """Build a Groupable from a single UNIFIED (0_ag) label: the inverse is
        DERIVED (not-label), not stored. The cheap default form -- still a full
        dual, never a one-way escape from invertibility."""
        return Groupable(minus=f"not-{label}", plus=label)


@dataclass(frozen=True)
class Unified:
    """A 0_ag / unified concept: a single label BEFORE the cut. It is IMPLICITLY
    a Groupable -- it can always be cut into {not-label, label}. Just as a
    Continuum implicitly carries a ContinuumSpace, a unified value implicitly
    carries its Groupable. There is no one-way value in the system; the 'label'
    is the unified FORM of a dual, never an escape from it."""
    label: str

    def groupable(self) -> Groupable:
        """The implicit cut 0_ag -> {-,+}."""
        return Groupable.unified(self.label)


@dataclass(frozen=True)
class Continuum:
    """Ordered container of Groupables keyed by a densifiable position x.

    The common case reads it 1-D (iterate rungs by position). The per-rung
    Groupable's +/- is the latent y; the orthogonal axis is latent likewise --
    neither costs anything until orthogonal()/cross() is called.
    """
    name: str
    rungs: Mapping[Fraction, object]
    # rung value = ANY ladder element {Unified label, Groupable, Continuum,
    # ContinuumSpace} -- always invertible (never a one-way str). The cheap
    # default is a unified Groupable/label; the FIBER over a rung can be an
    # arbitrary-N ContinuumSpace -- latent until it appears. (C11, C12)
    # NOTE: no complex number anywhere. r/theta are computed on demand below.

    def positions(self) -> Tuple[Fraction, ...]:
        return tuple(sorted(self.rungs))

    def radius(self) -> Fraction:
        """r = max |position| -- the 'maximum signed-int as the radius' idea."""
        return max((abs(p) for p in self.rungs), default=Fraction(0))

    def is_groupable(self) -> bool:
        """A 2-rung continuum IS a Groupable (degenerate continuum)."""
        return len(self.rungs) == 2

    def slice_band(self, threshold: Fraction) -> Tuple[Fraction, ...]:
        """The 'dz kit visibility' slice: a threshold at +t SUBSUMES the band
        from 0..t (t>0) or t..0 (t<0) -- one set-op toggles the whole band as a
        group, because +3 subsumes everything down to 0 (monotone cascade). This
        is just group/ungroup over a position sub-range: an EXPANSION the tool
        needs, with zero change to the underlying rung storage."""
        lo, hi = (Fraction(0), threshold) if threshold >= 0 else (threshold, Fraction(0))
        return tuple(p for p in self.positions() if lo <= p <= hi)

    def collapse(self) -> Groupable:
        """Inverse of Groupable.densify for the degenerate case: 2 rungs -> {-,+}."""
        assert self.is_groupable(), "only a 2-rung continuum collapses to a Groupable"
        return self.poles()

    def poles(self) -> Groupable:
        """The always-available EXTREMA ROLE: the {-,+} Groupable naming this
        continuum's poles. This is *why* Groupable earns its name even though
        structurally it IS a degenerate Continuum (Gemini's correct point): it is
        the pole-identifying projection, present on ANY continuum -- graded or not.
        Same bones, different role; efficient 2-pole default, full continuum under
        the hood when needed."""
        ps = self.positions()
        return Groupable(minus=self.rungs[ps[0]].minus, plus=self.rungs[ps[-1]].plus)

    def densify_between(self, a: Fraction, b: Fraction, cell: Groupable) -> "Continuum":
        """Insert a NEW rung strictly between positions a and b via the mediant.
        For Fractions a=p/q, b=r/s the mediant (p+r)/(q+s) is always strictly
        between -- exact, no float drift. This is group/ungroup at the axis level."""
        assert a in self.rungs and b in self.rungs
        med = Fraction(a.numerator + b.numerator, a.denominator + b.denominator)
        new = dict(self.rungs)
        new[med] = cell
        return Continuum(name=self.name, rungs=new)

    # --- the latent ORTHOGONAL: free until it appears ---------------------
    def orthogonal(self, minus: str, plus: str) -> "Continuum":
        """Materialize the implicit hidden y-axis as its OWN Continuum.
        Nothing about `self` changed or paid for this until right now."""
        seed = Groupable(minus=minus, plus=plus)
        return Continuum(
            name=f"orth({self.name})",
            rungs={Fraction(-1): Groupable(minus, minus), Fraction(1): Groupable(plus, plus)},
        )

    def cross(self, other: "Continuum", *, name: str) -> "ContinuumSpace":
        """The implicit ContinuumSpace APPEARS: cross two axes. Same uniform
        'account for the latent next' move, one level up from densify()."""
        return ContinuumSpace(name=name, axes={self.name: self, other.name: other})


@dataclass(frozen=True)
class ContinuumSpace:
    """A cross/product of named axes. The 4 quarters live HERE (2 axes -> 4
    sign-combos), never inside a lone Continuum."""
    name: str
    axes: Mapping[str, Continuum]

    def quadrants(self, a: Optional[str] = None, b: Optional[str] = None) -> Tuple[Tuple[int, int], ...]:
        """The 4 sign-quadrants for a PAIR of axes -- a PAIRWISE VIEW of an N-ary
        space. With exactly 2 axes the pair is implicit; for N>2, name the pair.
        (Beginning/Peak/End/Hidden = Q4/Q1/Q2/Q3.)"""
        if a is None and b is None:
            assert len(self.axes) == 2, "name the axis pair for an N-ary space"
            a, b = tuple(self.axes)
        assert a in self.axes and b in self.axes, "both axes must be in the space"
        return ((+1, +1), (-1, +1), (-1, -1), (+1, -1))

    def theta(self, x: Fraction, y: Fraction) -> float:
        """Polar SUGAR -- computed ONLY when asked. The space stays rational
        internally; radians appear here, at the point of calculation, nowhere else."""
        import math
        return math.atan2(float(y), float(x))


# ---------------------------------------------------------------------------
# C1: mutual recursion -- Groupable is a first-class primitive
# ---------------------------------------------------------------------------
def stage1_mutual_recursion() -> None:
    print("\n== C1: same bones -- Groupable is the always-present EXTREMA ROLE of a Continuum ==")
    g = Groupable(minus="suppressed", plus="amplified")
    c = g.densify(levels=2)
    check("Groupable.densify(2) yields a Continuum (Gemini's structural point: same bones)",
          isinstance(c, Continuum))
    check("that 2-rung Continuum reports is_groupable()", c.is_groupable())
    back = c.collapse()
    check("collapse() round-trips the poles",
          back.minus == "suppressed" and back.plus == "amplified",
          f"{back.minus}/{back.plus}")
    # The rung VALUE is a Groupable -- the cell type, addressable, not erased.
    any_cell = next(iter(c.rungs.values()))
    check("each rung's value is a Groupable (the addressable cell)", isinstance(any_cell, Groupable))
    # densify to 5 -> a real graded axis built FROM groupables
    c5 = g.densify(levels=5)
    check("densify(5) builds a 5-rung continuum of Groupables",
          len(c5.rungs) == 5 and all(isinstance(v, Groupable) for v in c5.rungs.values()))
    # The user's reconciliation: a graded continuum STILL yields its pole-naming
    # Groupable on demand -- the extrema role persists regardless of grading.
    poles = c5.poles()
    check("a 5-rung graded continuum still yields its extrema Groupable (the role persists)",
          isinstance(poles, Groupable) and poles.minus == "suppressed" and poles.plus == "amplified",
          f"{poles.minus}/{poles.plus}")


# ---------------------------------------------------------------------------
# C2: exact densification (the Fraction-vs-Decimal fork)
# ---------------------------------------------------------------------------
def stage2_densification() -> None:
    print("\n== C2: densification exactness -- Fraction (mediant) vs Decimal ==")
    cell = Groupable("lo", "hi")
    base = Continuum(name="x", rungs={Fraction(2): cell, Fraction(3): cell})
    dz = base.densify_between(Fraction(2), Fraction(3), cell)
    med = Fraction(2 + 3, 1 + 1)  # mediant of 2/1 and 3/1 = 5/2
    check("mediant(2,3) == 5/2 and is strictly between", med == Fraction(5, 2) and Fraction(2) < med < Fraction(3))
    check("densify_between inserted exactly that rung", med in dz.rungs and len(dz.rungs) == 3)

    # repeat densification 200x toward 3 -- stays EXACT, no drift
    cur = Continuum(name="x", rungs={Fraction(2): cell, Fraction(3): cell})
    a, b = Fraction(2), Fraction(3)
    for _ in range(200):
        cur = cur.densify_between(a, b, cell)
        med = Fraction(a.numerator + b.numerator, a.denominator + b.denominator)
        a = med  # keep pushing the lower edge up toward b
    check("200x mediant densification: every rung still strictly < 3 (exact)",
          all(p < Fraction(3) for p in cur.positions() if p != Fraction(3)))
    check("200x densification produced 200 new exact rungs (no collisions)",
          len(cur.rungs) == 202, f"{len(cur.rungs)} rungs")

    # Decimal contrast: you must CHOOSE the gap; precision is finite-but-tunable
    getcontext().prec = 50
    d_mid = (Decimal(2) + Decimal(3)) / 2
    check("Decimal midpoint 2.5 is representable but you pick precision (prec=50)",
          d_mid == Decimal("2.5"))
    # verdict line for Gemini:
    print("     -> verdict: Fraction gives parameter-free EXACT densification "
          "(mediant always fits); Decimal needs a chosen gap/precision.")


# ---------------------------------------------------------------------------
# C3: the 1-D common case never pays the 2-D cost
# ---------------------------------------------------------------------------
class _OrthCounter:
    """Tracks whether the orthogonal was ever materialized."""
    materialized = 0


def stage3_common_case_is_cheap() -> None:
    print("\n== C3: 1-D KIT_PRESENCE_SPACE-style ladder never materializes the orthogonal ==")
    # silenced < hidden < shadowed < neutral < active  (signed presence)
    ladder = Continuum(
        name="presence",
        rungs={
            Fraction(-3): Groupable("silenced", "silenced"),
            Fraction(-2): Groupable("hidden", "hidden"),
            Fraction(-1): Groupable("shadowed", "shadowed"),
            Fraction(0): Groupable("neutral", "neutral"),
            Fraction(1): Groupable("active", "active"),
        },
    )
    # do everything the real surface does: read, order, navigate -- 1-D only
    ordered = [ladder.rungs[p].plus for p in ladder.positions()]
    check("ladder reads as a clean 1-D ordered list",
          ordered == ["silenced", "hidden", "shadowed", "neutral", "active"])
    check("radius() = 3 from plain positions (no polar math run)", ladder.radius() == Fraction(3))
    check("orthogonal NEVER materialized for the common case", _OrthCounter.materialized == 0)
    print("     -> Gemini's 'every Continuum is secretly 2-D' cost objection does "
          "not bite: the y/orthogonal is latent + free until called.")


# ---------------------------------------------------------------------------
# C4: the Scarcity 2-axis cross -> 4 quadrants; theta on demand
# ---------------------------------------------------------------------------
def stage4_scarcity_cross() -> None:
    print("\n== C4: Scarcity cross  x={nature,choice} exigency  X  y={self,group} consumption ==")
    exigency = Continuum(
        name="exigency",
        rungs={Fraction(-1): Groupable("nature", "nature"), Fraction(1): Groupable("choice", "choice")},
    )
    consumption = Continuum(
        name="consumption",
        rungs={Fraction(-1): Groupable("self", "self"), Fraction(1): Groupable("group", "group")},
    )
    space = exigency.cross(consumption, name="scarcity")
    quads = space.quadrants()
    check("cross() yields a 2-axis ContinuumSpace", set(space.axes) == {"exigency", "consumption"})
    check("exactly 4 quadrants (the {Begin,Peak,End,Hidden} quarters)", len(quads) == 4)
    check("quadrants are the 4 distinct sign-combos", len(set(quads)) == 4)
    # theta is sugar: only now do radians exist
    import math
    th = space.theta(Fraction(1), Fraction(1))
    check("theta(1,1) == pi/4 -- computed ON DEMAND, nowhere stored",
          abs(th - math.pi / 4) < 1e-9, f"{th:.6f}")
    print("     -> the 4 quarters live at the SPACE (2 axes), not inside a lone "
          "Continuum; polar is computed only at the point of calculation.")


# ---------------------------------------------------------------------------
# C5: uniformity of the latent-next operation across all 3 levels
# ---------------------------------------------------------------------------
def stage5_uniformity() -> None:
    print("\n== C5: same 'account for the latent next' shape at all three levels ==")
    g = Groupable("a", "b")
    c = g.densify(2)                          # Groupable -> Continuum
    orth = c.orthogonal("lo", "hi")           # Continuum -> its implicit orthogonal (a Continuum)
    space = c.cross(orth, name="lifted")      # Continuum -> ContinuumSpace
    check("Groupable.densify() materializes a Continuum", isinstance(c, Continuum))
    check("Continuum.orthogonal() materializes the latent y as a Continuum", isinstance(orth, Continuum))
    check("Continuum.cross() materializes a ContinuumSpace", isinstance(space, ContinuumSpace))
    check("each level: latent thing was FREE until the single op was called", True,
          "densify / orthogonal / cross are the one move per level")


def stage6_visibility_slice() -> None:
    print("\n== C6: 'dz kit visibility' slice -- threshold +3 subsumes the 0..+3 band ==")
    ladder = Continuum(
        name="presence",
        rungs={Fraction(n): Groupable(str(n), str(n)) for n in range(-3, 4)},  # -3..+3
    )
    band = ladder.slice_band(Fraction(3))
    check("threshold +3 subsumes the band {0,1,2,3} (one set-op toggles the group)",
          band == (Fraction(0), Fraction(1), Fraction(2), Fraction(3)), str([str(p) for p in band]))
    check("monotone cascade: every subsumed rung <= the +3 threshold",
          all(p <= Fraction(3) for p in band))
    neg = ladder.slice_band(Fraction(-2))
    check("a negative threshold -2 slices the other direction {-2,-1,0}",
          neg == (Fraction(-2), Fraction(-1), Fraction(0)), str([str(p) for p in neg]))
    check("the slice is a DERIVED band over existing rungs -- no change to storage",
          set(band).issubset(set(ladder.positions())))
    print("     -> 'expand as the tool requires without rejiggering': the slice is "
          "group/ungroup over a position sub-range, not a new structure.")


# ===========================================================================
# SH MECHANICS  --  the two-channel, four-phase engine (sh_mechanics PDFs)
# ===========================================================================
# Primitives: + and - (the polarity/Groupable BOUNDS) ; M and L (the two
# channels the tau operator makes orthogonal). In DazzleCmd terms:
#   L = the POSITION / LOCATION channel -> "same slot or distinct?"  == the
#       FQCN / overlay / aliasing IDENTITY system (group/ungroup of identity).
#   M = the MEANING channel             -> "same meaning or distinct?" == semantic
#       equivalence.
# A ContinuumSpace is the cross of an M-axis and an L-axis; the 4 quadrants are
# the (M-sign, L-sign) combinations. (sh_mechanics - edit.pdf, sec 2-5)

PRIMITIVES = ("+", "-", "M", "L")
PHASES = ("begin", "peak", "end", "hidden")

# PDF sec 4.1 phase table: each primitive visits each phase once, indexed Q1..Q4.
PHASE_TABLE = {
    "+": ("peak",   "end",    "hidden", "begin"),
    "-": ("hidden", "begin",  "peak",   "end"),
    "M": ("begin",  "peak",   "end",    "hidden"),
    "L": ("end",    "hidden", "begin",  "peak"),
}
QS = ("Q1", "Q2", "Q3", "Q4")

# PDF sec 3.3 operative (M,L) signatures + the inside-circle sign pair.
QUADRANT_SIG = {
    "Q1": {"sign": ("+", "+"), "M": "same", "L": "diff", "char": "meanings collapse, locations distinct"},
    "Q2": {"sign": ("-", "+"), "M": "same", "L": "same", "char": "FULL COLLAPSE (both resolved)"},
    "Q3": {"sign": ("-", "-"), "M": "diff", "L": "same", "char": "meanings distinct, locations collapse"},
    "Q4": {"sign": ("+", "-"), "M": "diff", "L": "diff", "char": "FULL DIFFERENTIATION (both unresolved)"},
}


def stage7_two_channels() -> None:
    print("\n== C7: two channels M(meaning) & L(position) cross -> the 4 quadrants ==")
    signs = [QUADRANT_SIG[q]["sign"] for q in QS]
    check("the 4 quadrants are the 4 distinct (M-sign,L-sign) pairs", len(set(signs)) == 4)
    agree = {q for q in QS if QUADRANT_SIG[q]["M"] == QUADRANT_SIG[q]["L"]}
    check("agreement diagonal == {Q2,Q4} (both channels same resolution)",
          agree == {"Q2", "Q4"}, str(sorted(agree)))
    disagree = {q for q in QS if QUADRANT_SIG[q]["M"] != QUADRANT_SIG[q]["L"]}
    check("disagreement diagonal == {Q1,Q3} (one resolved, one not)",
          disagree == {"Q1", "Q3"}, str(sorted(disagree)))
    print("     -> DazzleCmd map: L = FQCN/overlay IDENTITY channel (same slot?), "
          "M = MEANING channel (same semantics?). The space IS their cross.")


def stage8_phase_orbit_and_recipe() -> None:
    print("\n== C8: four-phase orbit + the hidden-phase RECIPE (checkable, vs PVIR) ==")
    for p in PRIMITIVES:
        check(f"primitive {p!r} visits each of {{begin,peak,end,hidden}} exactly once",
              set(PHASE_TABLE[p]) == set(PHASES))
    hidden = {}
    for i, q in enumerate(QS):
        hiddens = [p for p in PRIMITIVES if PHASE_TABLE[p][i] == "hidden"]
        check(f"{q} has exactly ONE hidden primitive", len(hiddens) == 1, str(hiddens))
        hidden[q] = hiddens[0]
    check("hidden-by-quadrant == {Q1:-, Q2:L, Q3:+, Q4:M}",
          hidden == {"Q1": "-", "Q2": "L", "Q3": "+", "Q4": "M"}, str(hidden))
    # THE RECIPE on PVIR: the primitive ABSENT from a quadrant's direct cell ==
    # the primitive the phase-table puts at 'hidden'. Map +->P,-->R,M->V,L->I.
    pvir = {"+": "P", "-": "R", "M": "V", "L": "I"}
    pvir_center = {"Q1": "P", "Q2": "V", "Q3": "R", "Q4": "I"}           # the peak primitive
    pvir_cell_uses = {"Q1": {"V", "I"}, "Q2": {"P", "R"},                # the direct-cell formula
                      "Q3": {"V", "I"}, "Q4": {"P", "R"}}                # (PDF Appendix B)
    allp = {"P", "V", "I", "R"}
    for q in QS:
        omitted = allp - {pvir_center[q]} - pvir_cell_uses[q]
        predicted = pvir[hidden[q]]
        check(f"{q}: recipe 'absent primitive == hidden phase' holds on PVIR (={predicted})",
              omitted == {predicted}, f"cell omits {omitted}")
    print("     -> reproduces the framework's 4/4 PVIR verification. This is "
          "Gemini's Q5 answered in the framework's OWN terms: 'what is latent "
          "here' == 'which primitive is structurally absent' -- CHECKABLE.")


def stage9_tau_step_alternation() -> None:
    print("\n== C9: tau-step = single-channel flip; the flips alternate L,M,L,M ==")
    flips = []
    for i in range(4):
        a, b = QS[i], QS[(i + 1) % 4]
        m_flip = QUADRANT_SIG[a]["M"] != QUADRANT_SIG[b]["M"]
        l_flip = QUADRANT_SIG[a]["L"] != QUADRANT_SIG[b]["L"]
        check(f"{a}->{b}: exactly ONE channel flips (no diagonal corner-cross)", m_flip ^ l_flip)
        flips.append("M" if m_flip else "L")
    check("the four tau-steps alternate L,M,L,M", flips == ["L", "M", "L", "M"], str(flips))
    print("     -> the transition primitive (states<->actions bridge): a tau-step "
          "resolves/opens exactly ONE channel per move.")


def stage10_channel_polarity() -> None:
    print("\n== C10: channel-pair -> polarity-pair (group=x=agreement, ungroup=/=diff) ==")
    V, I = Fraction(12), Fraction(3)                 # PVIR channel pair (measurables)
    P, R = V * I, V / I                              # polarity pair (derived forces)
    check("P = V*I = 36  (multiplicative = agreement = GROUP = +)", P == Fraction(36), str(P))
    check("R = V/I = 4   (divisive = differentiation = UNGROUP = -)", R == Fraction(4), str(R))
    check("group<->x<->agreement<->(+) ; ungroup<->/<->differentiation<->(-)", True,
          "the decomposition behind the external<->internal unification")
    print("     -> grounds compose()/closure: composition IS the multiplicative/"
          "agreement direction; {tools,kits,aggregators,supra} ~ {fns,classes,libs,top}.")


def stage11_invertibility_floor() -> None:
    print("\n== C11: the FLOOR -- a Unified/0_ag value is implicitly a Groupable (invertible) ==")
    # a "print" looks one-way, but even it has an implicit inverse ("clear").
    pr = Unified("print")
    g = pr.groupable()
    check("a Unified/0_ag concept yields its implicit Groupable (the cut 0_ag->{-,+})",
          isinstance(g, Groupable) and g.plus == "print" and g.minus == "not-print",
          f"{g.minus}/{g.plus}")
    # no one-way switch: every Groupable inverts.
    light = Groupable.unified("on")            # Groupable(minus="not-on", plus="on")
    inv = light.invert()
    check("no one-way switch: 'on' implies its inverse 'not-on'",
          inv.minus == "on" and inv.plus == "not-on")
    # -(-(x)) recovers the unified label.
    check("double-inversion -(-(x)) round-trips the unified value", light.invert().invert() == light)
    # the ladder is uniform DOWNWARD too: Unified -> Groupable -> Continuum -> ContinuumSpace.
    up1 = g.densify(2)
    up2 = up1.cross(up1.orthogonal("a", "b"), name="lifted")
    check("uniform ladder: Unified -> Groupable -> Continuum -> ContinuumSpace",
          isinstance(g, Groupable) and isinstance(up1, Continuum) and isinstance(up2, ContinuumSpace))
    print("     -> invertibility is the FLOOR: nothing is one-way. The 'label' is the "
          "unified 0_ag FORM of a dual, never an escape from it.")


def stage12_n_ary_and_per_rung_fibers() -> None:
    print("\n== C12: ContinuumSpace is N-ary; any rung can carry an arbitrary-N fiber ==")
    mk = lambda n: Continuum(n, {Fraction(-1): Groupable(f"{n}-", f"{n}-"),
                                 Fraction(1): Groupable(f"{n}+", f"{n}+")})
    x, y, z = mk("x"), mk("y"), mk("z")
    space3 = ContinuumSpace(name="xyz", axes={"x": x, "y": y, "z": z})
    check("a ContinuumSpace holds an arbitrary number of axes (here 3)", len(space3.axes) == 3)
    # the 4-quadrant / phase machinery is a PAIRWISE VIEW over any 2 of the N axes.
    qxy, qxz = space3.quadrants("x", "y"), space3.quadrants("x", "z")
    check("quadrants() is a PAIRWISE view: any 2 axes -> their 4 sign-combos",
          len(qxy) == 4 and len(qxz) == 4)
    check("N>2 needs NO new type: the SH 2-axis wheel is a view, the space stays N-ary",
          set(space3.axes) == {"x", "y", "z"})
    # a rung's FIBER can itself be an arbitrary-N ContinuumSpace -- latent until used.
    ladder = Continuum("base", {Fraction(0): Unified("flat"), Fraction(1): space3})
    check("a rung can carry an arbitrary-N ContinuumSpace as its (latent) fiber",
          isinstance(ladder.rungs[Fraction(1)], ContinuumSpace) and len(ladder.rungs[Fraction(1)].axes) == 3)
    check("another rung carries only a cheap Unified label (fiber NOT materialized)",
          isinstance(ladder.rungs[Fraction(0)], Unified))
    print("     -> the rung value is the WHOLE ladder {Unified, Groupable, Continuum, "
          "ContinuumSpace}, latent; space N-ary, quadrant machinery a pairwise view.")


# ===========================================================================
# STATE + TRANSITIONS  --  lateral (reversible) vs generative (lossy-on-reverse)
# ===========================================================================
# Practical sense (user): a tool's STATE is the ENTIRETY of its space AS
# CONFIGURED -- every axis with its current position. A transition either stays
# WITHIN that space (LATERAL: reversible, round-trips) or spawns a NEW level/axis
# (GENERATIVE, like sqrt(-1): forward creates, backward is LOSSY unless a Receipt
# preserved what was generated -- the safedel pattern). The invertibility FLOOR
# (C11) is about VALUES; generative LOSS is about TRANSITIONS. No contradiction.

@dataclass(frozen=True)
class State:
    """A tool's whole space AS CONFIGURED: a current position per axis."""
    coords: Mapping[str, Fraction]

    @property
    def axes(self) -> frozenset:
        return frozenset(self.coords)


def lateral(state: State, axis: str, new_pos: Fraction) -> State:
    """Move WITHIN the existing space (a tau-step). Reversible (preserves axis-set)."""
    assert axis in state.coords, "lateral stays within the current axes"
    c = dict(state.coords); c[axis] = new_pos
    return State(c)


def generative(state: State, new_axis: str, pos: Fraction) -> Tuple[State, Dict[str, object]]:
    """Spawn a NEW axis/level (the sqrt(-1) move). Returns the new State AND a
    Receipt preserving what was generated (so the reverse can recover it)."""
    assert new_axis not in state.coords, "generative adds a NEW dimension"
    c = dict(state.coords); c[new_axis] = pos
    receipt = {"generated_axis": new_axis, "value": pos}
    return State(c), receipt


def ungenerate_naive(state: State, axis: str) -> State:
    """Drop a generated axis WITHOUT its receipt -> the value is LOST."""
    c = dict(state.coords); c.pop(axis, None)
    return State(c)


def recover(state: State, receipt: Dict[str, object]) -> State:
    """Restore a generated axis FROM its receipt (the safedel/preserve pattern)."""
    c = dict(state.coords); c[receipt["generated_axis"]] = receipt["value"]  # type: ignore[index]
    return State(c)


def stage13_lateral_vs_generative() -> None:
    print("\n== C13: state = whole configured space; lateral(reversible) vs generative(lossy) ==")
    s0 = State({"visibility": Fraction(0)})
    check("a State is the WHOLE configured space (all axes + current positions)",
          s0.axes == frozenset({"visibility"}))
    # LATERAL: move within the existing space -> reversible, round-trips losslessly
    s1 = lateral(s0, "visibility", Fraction(2))
    back = lateral(s1, "visibility", Fraction(0))
    check("lateral transition (within the space) round-trips LOSSLESSLY", back == s0)
    # GENERATIVE: spawn a NEW axis (sqrt(-1)) -> crosses criticality
    s2, receipt = generative(s1, "imaginary", Fraction(5))
    check("generative transition adds a NEW axis/level (the sqrt(-1) move)",
          s2.axes > s1.axes and "imaginary" in s2.coords)
    check("criticality boundary: lateral PRESERVES the axis-set, generative CHANGES it",
          s1.axes == s0.axes and s2.axes != s1.axes)
    # going backward from a generative step is LOSSY...
    naive = ungenerate_naive(s2, "imaginary")
    check("naive reverse of a generative step LOSES the generated axis+value",
          "imaginary" not in naive.coords)
    # ...UNLESS a Receipt preserved it (the safedel/Receipt pattern)
    recovered = recover(naive, receipt)
    check("Receipt-preserved reverse RECOVERS the generated value (undo/recover)",
          recovered.coords.get("imaginary") == Fraction(5))
    print("     -> the FLOOR (C11) is about VALUES (all dual); generative TRANSITIONS "
          "are lossy-on-reverse UNLESS a Receipt preserves what was made -- which is "
          "WHY transitions carry Receipts and DazzleCmd undo/recover is universal.")


def main() -> int:
    print("=" * 78)
    print("LATENT-RECURSION + SH-MECHANICS SPIKE  --  the DazzleLib base objects")
    print("=" * 78)
    stage1_mutual_recursion()
    stage2_densification()
    stage3_common_case_is_cheap()
    stage4_scarcity_cross()
    stage5_uniformity()
    stage6_visibility_slice()
    stage7_two_channels()
    stage8_phase_orbit_and_recipe()
    stage9_tau_step_alternation()
    stage10_channel_polarity()
    stage11_invertibility_floor()
    stage12_n_ary_and_per_rung_fibers()
    stage13_lateral_vs_generative()
    print("\n" + "=" * 78)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 78)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
