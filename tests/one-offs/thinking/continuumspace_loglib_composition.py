"""Generality spike: how well do Continuum + ContinuumSpace model the log-lib's
COMPOSITIONAL shape (intensity x tags)?

The log-lib (wtf-windows lib/log_lib) is compositional in two dimensions:
  - INTENSITY: an integer verbosity level (NOTHING=-4 .. DEFAULT=0 .. DEBUG=+3).
  - TAGS / CHANNELS: named output categories; each channel holds its OWN
    threshold (a cursor on the intensity axis); a message carries a tag-set
    selecting which channels it targets. A message at `level` tagged `T` emits
    on channel C  iff  (C in T) and verbosity.passes(level, C.threshold).

This spike asks: does that fit Continuum / ContinuumSpace, and WHERE does it
fit vs. where does it reveal a different shape?  (Companion to the earlier
Continuum-only loglib spike in wtf-windows, which validated INTENSITY against
the live OutputManager.)  ASCII-only.

Run: python tests/one-offs/thinking/continuumspace_loglib_composition.py
"""
from dazzlecmd_lib.continuum import Continuum, ContinuumSpace, ContinuumError

print("=" * 72)
print("Spike: log-lib (intensity x tags) vs Continuum / ContinuumSpace")
print("=" * 72)

# ---------------------------------------------------------------------------
# 1. INTENSITY = a single Continuum (THAC0). The emit gate IS Continuum.passes.
# ---------------------------------------------------------------------------
verbosity = Continuum(
    name="verbosity",
    ranks={"nothing": -4, "error": -3, "warning": -2, "minimal": -1,
           "default": 0, "timing": 1, "config": 2, "debug": 3},
    invariant="default_output",
)
assert verbosity.passes("error", "default")        # -3 <= 0  -> emits
assert not verbosity.passes("debug", "default")    # +3 <= 0  -> suppressed
print("\n[1] INTENSITY")
print("    Continuum.passes(level, threshold) IS the per-channel THAC0 gate.")
print("    -> the intensity dimension fits Continuum exactly (proven again).")

# ---------------------------------------------------------------------------
# 2. TAGS / CHANNELS = independent CURSORS on the one verbosity Continuum,
#    selected per-message by a tag-set. This is plain composition + the gate.
# ---------------------------------------------------------------------------
channels = {"network": "debug", "disk": "default", "ui": "warning"}  # name -> threshold cursor

def emits_on(level, tags):
    return [c for c in tags if c in channels and verbosity.passes(level, channels[c])]

# THAC0: passes(level, threshold) == rank(level) <= rank(threshold), so a LOUDER
# (higher-rank) message reaches FEWER channels (only those with a high threshold).
assert emits_on("debug", {"network", "disk", "ui"}) == ["network"]            # +3: only network(debug) is loud enough
assert set(emits_on("error", {"network", "disk", "ui"})) == {"network", "disk", "ui"}  # -3: quiet enough for all
print("\n[2] TAGS / CHANNELS")
print("    Each channel = an independent CURSOR (threshold) on the SAME Continuum;")
print("    a message's tag-set selects channels; passes() gates each.")
print("    debug tagged {network,disk,ui} reaches:", emits_on("debug", {"network", "disk", "ui"}))
print("    error tagged {network,disk,ui} reaches:", sorted(emits_on("error", {"network", "disk", "ui"})))

# ---------------------------------------------------------------------------
# 3. THE REAL TEST: can the channels compose as a presence ContinuumSpace?
#    Each channel is the SAME verbosity Continuum; its 'presence' would be its
#    intensity. But channels are HOMOGENEOUS + independent -- two can sit at the
#    same intensity, so they do NOT form a strict merged order.
# ---------------------------------------------------------------------------
print("\n[3] CHANNELS as a presence ContinuumSpace?")
try:
    ContinuumSpace(
        name="loglib_as_presence",
        axes={"network": verbosity, "disk": verbosity},
        presence={
            "network": dict(verbosity.ranks),   # presence == intensity
            "disk":    dict(verbosity.ranks),
        },
    )
    print("    [??] unexpectedly accepted -- investigate")
except ContinuumError as e:
    print(f"    [OK] ContinuumSpace REJECTS it: {str(e)[:60]}...")
    print("         Two channels share an intensity (e.g. both at 'debug'=+3),")
    print("         which collides -- there is NO merged order. The loglib's")
    print("         channels are PARALLEL cursors, not heterogeneous axes.")

# ---------------------------------------------------------------------------
# CONCLUSION -- two distinct 'compositions of Continua':
# ---------------------------------------------------------------------------
print("\n" + "-" * 72)
print("FINDING")
print("-" * 72)
print("""\
Continuum            : GENERAL. Intensity + the passes() gate fit exactly
                       (the loglib's whole vertical dimension).

ContinuumSpace       : the PRESENCE composition -- N HETEROGENEOUS axes sharing
(what we just built)   one MEANING (presence), forming a MERGED ORDER you
                       navigate (silence < hide < shadow < disable). Uniqueness
                       of coords is load-bearing: it IS the merged order.

log-lib channels     : a DIFFERENT composition -- N HOMOGENEOUS channels sharing
                       one TYPE (verbosity), each an independent CURSOR, selected
                       by TAGS, queried by passes(). NO merged order, NO presence
                       navigation. ContinuumSpace correctly REJECTS it (its
                       uniqueness rule fires) -- it is not a presence space.

=> Both 'compose Continua', but along different sharing-relations:
     ContinuumSpace = shared-MEANING, merged, navigated   (presence)
     loglib         = shared-TYPE, parallel cursors, tag-selected, gated
   The loglib reveals a SIBLING primitive (a 'CursorBank' / channel-space:
   N cursors on ONE Continuum + a tag selector). Continuum is the shared
   substrate of both. This is a finding for the dazzle-lib interface set (#188):
   the lift should name BOTH compositions, not fold the loglib into the presence
   space.""")
