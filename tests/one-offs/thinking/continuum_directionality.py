"""THINKING (one-off): what should the Continuum's stepping interface be called?

The problem (user): `more()`/`less()` are ambiguous -- "more" of WHAT? More cold
or more warm? The user's seasons/{P,not-P} model: the SAME signed axis reads two
ways depending on which absolute (pole-concept) you foreground; direction gives
contextual meaning. Proposed fix: anchor to an absolute -> `more_warm()` /
`less_warm()`.

This script prototypes candidate interfaces AS WRAPPERS over the REAL Continuum
(no commitment to continuum.py yet) and works them against the two live consumers
(visibility, THAC0) + a contrived cyclic case, to see what actually reads right.
Run: python tests/one-offs/thinking/continuum_directionality.py
"""
import os
import sys

_DZLIB = r"C:\code\dazzlecmd\github\packages\dazzlecmd-lib\src"
if _DZLIB not in sys.path:
    sys.path.insert(0, _DZLIB)
from dazzlecmd_lib.continuum import Continuum  # noqa: E402


VIS = Continuum(
    name="visibility",
    ranks={"visible": 0, "silenced": -1, "hidden": -2, "shadowed": -3},
    invariant="canonical_dispatch",
    channels={"visible": frozenset(), "silenced": frozenset({"hints"}),
              "hidden": frozenset({"hints", "display"}),
              "shadowed": frozenset({"hints", "display", "resolution"})},
)
THAC0 = Continuum(
    name="verbosity", invariant="default_output",
    ranks={"nothing": -4, "error": -3, "warning": -2, "minimal": -1,
           "default": 0, "timing": 1, "config": 2, "debug": 3},
)


# --- candidate vocabularies, prototyped as wrappers ------------------------
def more_warm(c, lvl):   # +1 rank (toward the warm/+ pole)
    return c.step(lvl, +1)


def less_warm(c, lvl):   # -1 rank (away from warm = toward cold)
    return c.step(lvl, -1)


def more_cold(c, lvl):   # toward the cold/- pole == less_warm (the dual)
    return c.step(lvl, -1)


def less_cold(c, lvl):   # away from cold == more_warm (the dual)
    return c.step(lvl, +1)


def toward(c, lvl, pole):  # neutral, pole-named (my pushback option)
    target_rank = c.rank(pole)
    cur = c.rank(lvl)
    if cur == target_rank:
        return lvl
    return c.step(lvl, +1 if target_rank > cur else -1)


def banner(t):
    print("\n" + "=" * 70 + f"\n  {t}\n" + "=" * 70)


def main():
    banner("1. The duality holds: more_cold == less_warm, less_cold == more_warm")
    for c, lvl in [(VIS, "silenced"), (THAC0, "default")]:
        a, b = more_cold(c, lvl), less_warm(c, lvl)
        d, e = less_cold(c, lvl), more_warm(c, lvl)
        print(f"  {c.name:<10} from {lvl!r}: more_cold={a!r}==less_warm={b!r}? "
              f"{a==b} ; less_cold={d!r}==more_warm={e!r}? {d==e}")

    banner("2. VISIBILITY -- which vocabulary reads as the domain verbs?")
    print("  visible(0) is the WARM end (asymmetric 0..-3); shadowed(-3) the cold pole.")
    print("  hide = step toward suppression (colder); expose = step toward visible (warmer).")
    print(f"    hide   = less_warm(visible)  = {less_warm(VIS,'visible')!r}   "
          f"= more_cold(visible) = {more_cold(VIS,'visible')!r}")
    print(f"    expose = more_warm(shadowed) = {more_warm(VIS,'shadowed')!r}   "
          f"= less_cold(shadowed)= {less_cold(VIS,'shadowed')!r}")
    print(f"    toward(visible,'shadowed')   = {toward(VIS,'visible','shadowed')!r}  (pole-named)")
    print("  READ TEST: a SUPPRESSION-framed dev thinks 'suppress more' -> more_cold")
    print("             a VISIBILITY-framed dev thinks 'show more'      -> more_warm")
    print("             'less_warm' for hide reads awkwardly to the suppression-framed dev")

    banner("3. THAC0 -- verbosity is naturally warm-framed")
    print(f"    louder/more verbose = more_warm(default) = {more_warm(THAC0,'default')!r}")
    print(f"    quieter             = less_warm(default)  = {less_warm(THAC0,'default')!r}")
    print("  'more_warm' reads perfectly here; 'more_cold' (=quieter) also sensible.")
    print("  But 'warm' is a METAPHOR -- verbosity isn't temperature. Honest? Mostly.")

    banner("4. Does 'warm/cold' fit every domain? (the pushback)")
    for c in (VIS, THAC0):
        print(f"    {c.name:<10} warm-pole={c.warm_pole()!r:<10} cold-pole={c.cold_pole()!r:<10} "
              f"neutral(0)={c.neutral()!r}")
    print("  visibility's poles aren't 'warm'/'cold' -- they're 'visible'/'shadowed'.")
    print("  load's would be 'loaded'/'removed'; activation 'enabled'/'disabled'.")
    print("  So a SINGLE metaphor (warm) at the primitive is uniform but lossy per-domain.")

    print("\nFINDINGS -> see my written take. Spoiler: anchor-to-absolute is RIGHT;")
    print("the open question is WHICH absolute vocabulary (fixed warm/cold metaphor")
    print("vs per-axis pole names) and whether to expose both framings or 2 + domain verbs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
