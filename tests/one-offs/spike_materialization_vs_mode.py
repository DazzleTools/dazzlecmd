"""Spike: where does MATERIALIZATION live?

Tension (surfaced reading #80/#86/#37 + the kit-lifecycle gold-standard):
  - SD-2 claimed `mode = tracking (perp) materialization` -- materialization a FIBER of mode.
  - The gold-standard (contexts.py:436-446) intends materialization a PRESENCE axis
    (a PRODUCT dimension of KIT_PRESENCE_SPACE), and MODE/tracking categorical + OUTSIDE.
  - The shipped `pointer:{materialized}` block (contexts.py:1039-1065) couples
    materialization to the LOADING state.

Test the shape in practice against the real dazzle-lib ContinuumSpace + the shipped
KIT_PRESENCE_SPACE. Run:  python tests/one-offs/spike_materialization_vs_mode.py
"""
from dazzle_lib.continuum import Continuum, ContinuumSpace
from dazzlecmd_lib.contexts import (
    KIT_PRESENCE_SPACE, ACTIVATION_CONTINUUM, VISIBILITY_CONTINUUM,
)


def hr(title):
    print("\n" + "=" * 70 + "\n" + title + "\n" + "=" * 70)


hr("Ground truth: the SHIPPED KIT_PRESENCE_SPACE")
print("axes        :", list(KIT_PRESENCE_SPACE.axes.keys()))
print("is_aligned? :", KIT_PRESENCE_SPACE.is_aligned, "  (False => a PRODUCT of dims)")
print("leaves      :", list(KIT_PRESENCE_SPACE.leaves().keys()))
print("=> intent (contexts.py:438): visibility x activation now; 'member? materialized?'")
print("   are further PRODUCT presence dimensions at the capstone.")

# The three concepts as Continuums (warm/present = 0, colder = negative).
MATERIALIZATION = Continuum("materialization", {"materialized": 0, "absent": -1})
LOADING = Continuum("loading", {"loaded": 0, "pointer": -1})
TRACKING = Continuum(
    "tracking", {"submodule": 0, "symlink": -1, "embedded": -2, "local-only": -3})

hr("Option A (SD-2): mode = compose(tracking, materialization)")
mode_A = ContinuumSpace.compose(
    "mode", {"tracking": TRACKING, "materialization": MATERIALIZATION})
print("mode axes   :", list(mode_A.axes.keys()), " is_aligned?", mode_A.is_aligned)
print("PROBLEM: compose() makes tracking & materialization INDEPENDENT product axes.")
print("But an UNMATERIALIZED (absent) entity has NO tracking kind -- you don't know if")
print("it's a submodule until fetched. tracking DEPENDS ON materialized=true; they are")
print("NOT co-equal/independent. The product flattens that dependency. Mismatch.")

hr("Option B (gold-standard): materialization is a PRESENCE axis;")
print("                          tracking is a FIBER over materialized=true, OUTSIDE presence")
# materialization joins the presence PRODUCT (same pattern as visibility/activation):
kit_presence_plus = ContinuumSpace.compose(
    "kit_presence_plus",
    {"visibility": VISIBILITY_CONTINUUM, "activation": ACTIVATION_CONTINUUM,
     "loading": LOADING, "materialization": MATERIALIZATION},
)
print("presence axes:", list(kit_presence_plus.axes.keys()))
print("is_aligned?  :", kit_presence_plus.is_aligned, "  (False => PRODUCT, scale-safe)")
assert not kit_presence_plus.is_aligned, "presence dims must compose as an independent product"
assert set(kit_presence_plus.leaves()) >= {"visibility", "activation", "loading", "materialization"}

# tracking hangs as a FIBER over the materialized rung (the dependency, represented):
MATERIALIZATION_FIBERED = Continuum(
    "materialization", {"materialized": 0, "absent": -1},
    fibers={"materialized": TRACKING},
)
fiber = MATERIALIZATION_FIBERED.fibers.get("materialized")
print("tracking fiber over 'materialized':", fiber.name if fiber is not None else None)
print("tracking fiber over 'absent'      :", MATERIALIZATION_FIBERED.fibers.get("absent"))
assert fiber is not None and fiber.name == "tracking"
assert "absent" not in MATERIALIZATION_FIBERED.fibers  # no tracking when unmaterialized
print("=> materialization composes cleanly as a presence product-axis; tracking hangs as a")
print("   fiber on the materialized rung only. The dependency is REPRESENTED, not flattened.")

hr("VERDICT")
print("Option B holds in practice and matches the shipped intent:")
print("  * materialization is a PRESENCE axis (a product dim of KIT_PRESENCE_SPACE),")
print("    coupled to loading (a pointer carries `materialized`).")
print("  * MODE/tracking is categorical, OUTSIDE the presence product, a FIBER over")
print("    materialized=true (no tracking kind until fetched).")
print("  * The three moves still separate: detach=LOADING (presence), de-materialize=")
print("    MATERIALIZATION (presence), mode-switch=TRACKING (the categorical fiber).")
print("SD-2's 'mode = tracking (perp) materialization' is WRONG: it absorbed a presence")
print("axis into mode and flattened the tracking-needs-materialization dependency.")
print("\nSPIKE OK.")
