"""Prove-it: a ContinuumSpace makes N orthogonal axes (visibility, activation)
share ONE presence scale, so "next stronger / weaker" navigates across them.

This is the visible companion to test_continuum.py's TestContinuumSpace -- it
prints the merged spectrum + a stronger/weaker walk so a human can SEE that
silence/hide/shadow/disable are coordinates on one cool<->warm (group<->ungroup)
spine. ASCII-only (cmd/PowerShell safe).

Run: python tests/one-offs/thinking/continuumspace_presence_spectrum.py
"""
from dazzlecmd_lib.continuum import Continuum, ContinuumSpace

visibility = Continuum(
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
activation = Continuum(
    name="activation",
    ranks={"enabled": 0, "disabled": -1},
    invariant="dispatch_active",
)

space = ContinuumSpace(
    name="kit_presence",
    meaning="how present a tool is to dz (listing + dispatch)",
    axes={"visibility": visibility, "activation": activation},
    presence={
        "visibility": {"visible": 0, "silenced": -1, "hidden": -2, "shadowed": -3},
        "activation": {"enabled": 0, "disabled": -4},
    },
)

print("=" * 68)
print("ContinuumSpace 'kit_presence' -- two orthogonal axes, one presence scale")
print("=" * 68)
print("\nself-describing (describe() -- interrogate what it measures + what fits):")
print(space.describe())
print("\nAxes (the mechanisms):")
for name, cont in space.axes.items():
    print(f"  {name:12} {cont.levels()}   (cold -> warm)")

print("\nMerged presence spectrum  (WARMER = more present = GROUP):")
print("  [fully present / neutral]   <-- every axis's warm pole collapses here (presence 0)")
for axis, level in space.spectrum():                       # warm -> cold
    p = space.presence_of(axis, level)
    print(f"  {p:>3}  {axis}:{level}")
print("  [colder still: disable -> detach -> remove ... future axes]")

print("\n'Next STRONGER / WEAKER' navigation (the dz kit visibility --stronger flag):")
for axis, level in [("visibility", "visible"), ("visibility", "silenced"),
                    ("visibility", "hidden"), ("visibility", "shadowed"),
                    ("activation", "disabled")]:
    stronger = space.colder_than(axis, level)   # ungroup-more
    weaker = space.warmer_than(axis, level)     # group-more
    s = f"{stronger[0]}:{stronger[1]}" if stronger else "(cold pole)"
    w = f"{weaker[0]}:{weaker[1]}" if weaker else "(fully present)"
    star = "   <-- crosses axes!" if (stronger and stronger[0] != axis) else ""
    print(f"  at {axis}:{level:9}  stronger -> {s:22} weaker -> {w}{star}")

print("\nThe point: 'shadowed' (visibility) and 'disabled' (activation) are")
print("DIFFERENT mechanisms, yet the space ranks them on one warmth spine -- so")
print("'stronger than shadowed' hops to 'disabled' with no special-casing.")
