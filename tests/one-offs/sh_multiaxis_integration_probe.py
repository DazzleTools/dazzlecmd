"""SH integration probe -- 8b design test: can the multi-axis ContinuumSpace +
QuadrantView serve dazzlecmd, and HOW does activation compose with visibility?

Read-only / byte-transparent (builds NOTHING into production; constructs throwaway
spaces from the real VISIBILITY_CONTINUUM / KIT_PRESENCE_SPACE). Answers: when we
add an `activation` axis, do we (a) add it to the ALIGNED KIT_PRESENCE_SPACE (which
would merge it into the visibility navigator's spectrum -> change `dz kit
visibility` output), or (b) COMPOSE visibility-space x activation as a PRODUCT (the
v0.6.0 alignment-as-property design) so the visibility navigator is untouched and
the SH wheel lives at the product level?
"""
from dazzle_lib import Continuum, ContinuumSpace, ContinuumError
from dazzlecmd_lib.contexts import KIT_PRESENCE_SPACE as KPS

PASS = FAIL = 0
def check(label, cond, detail=""):
    global PASS, FAIL
    print(f"  {'[OK]' if cond else '[XX]'} {label}" + (f"  -- {detail}" if detail else ""))
    PASS += bool(cond); FAIL += (not cond)

print("== baseline: the real single-axis KIT_PRESENCE_SPACE (the visibility navigator) ==")
print("  axes:", tuple(KPS.axes), "| aligned:", KPS.is_aligned)
base_colder = KPS.colder_than("visibility", "hidden")
base_warmer = KPS.warmer_than("visibility", "hidden")
print("  colder_than(visibility,hidden):", base_colder, "| warmer_than:", base_warmer)
check("baseline navigator stays within the visibility axis", base_colder is None or base_colder[0] == "visibility")

print("\n== option (b): PRODUCT-compose visibility-space x activation (the design path) ==")
# activation as a 2-rung continuum (a Groupable-shaped axis: inactive | active)
act = Continuum("activation", {"inactive": -1, "active": 1}, invariant="dispatch")
product = ContinuumSpace.compose(
    "kit_presence_2axis",
    {"visibility": KPS, "activation": act},
    meaning="how present a tool is (listing+dispatch) x whether it dispatches",
    invariant="canonical_dispatch",
)
check("compose() yields a 2-axis PRODUCT space", set(product.axes) == {"visibility", "activation"})
check("the product is NOT aligned (no merged spectrum -> no cross-axis interference)", not product.is_aligned)

# the SH wheel -- FIRST time QuadrantView runs over a real dazzlecmd axis pair
qv = product.quadrants("visibility", "activation")
quads = qv.quadrants()
check("quadrants(visibility, activation) -> a working QuadrantView (4 sign-combos)",
      len(quads) == 4 and len(set(quads)) == 4, str(quads))
check("hidden_at recipe runs on the real pair", [qv.hidden_at(q) for q in ("Q1","Q2","Q3","Q4")] ==
      ["-", "activation", "+", "visibility"], str([qv.hidden_at(q) for q in ("Q1","Q2","Q3","Q4")]))
check("tau_steps alternate over the real pair", qv.tau_steps() ==
      ("activation", "visibility", "activation", "visibility"), str(qv.tau_steps()))

print("\n== the navigator is PRESERVED: read the visibility SUB-space, not the product ==")
vis_sub = product.axes["visibility"]   # this IS the original KIT_PRESENCE_SPACE
check("the visibility sub-space's nav is identical to the baseline (navigator untouched)",
      vis_sub.colder_than("visibility", "hidden") == base_colder
      and vis_sub.warmer_than("visibility", "hidden") == base_warmer)
# and the product itself REFUSES cross-axis nav (scale-safety) -- the REASON you
# navigate the sub-space, not the merged product:
try:
    product.colder_than("visibility", "hidden")
    check("product refuses cross-axis colder_than (scale-safety)", False, "did NOT raise")
except ContinuumError:
    check("product refuses cross-axis colder_than (scale-safety) -> read the sub-space", True)

print("\n" + "=" * 70)
print(f"RESULT: {PASS} passed, {FAIL} failed")
print("=" * 70)
raise SystemExit(0 if FAIL == 0 else 1)
