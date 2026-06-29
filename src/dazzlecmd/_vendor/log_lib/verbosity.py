"""The verbosity axis, materialized as a `dazzle_lib.Continuum` (DWP-B / B-1).

THAC0 ("to hit armor class 0") was always a signed Continuum with an invariant
zero -- and `dazzle_lib.continuum` was literally written around it (its docstring
names this logger as the canonical scalar axis; `Continuum.passes()` IS the THAC0
gate). This module connects that wire: `VERBOSITY_CONTINUUM` is the named-rung
axis, and `shows()` is the single emit gate every call routes through.

DEVELOPMENT NOTE: added for dazzlecmd (not in the original wtf-windows `log_lib`,
which used raw ints inline) -- the first step of the log_lib continuum redesign.
This makes the vendored copy depend on `dazzle_lib` (the bedrock; a valid
down-only dependency the future `dazzle_loglib` will declare). See `_VENDORED.md`.
"""
from dazzle_lib.continuum import Continuum

from .levels import (
    NOTHING, ERROR, WARNING, MINIMAL, DEFAULT, TIMING, CONFIG, DEBUG)

# The verbosity Continuum: 4 quiet rungs, the invariant 0 (DEFAULT), 3 verbose
# rungs. The int constants ARE the signed ranks -- `rank(level) <= rank(threshold)`
# (Continuum.passes) is the THAC0 gate, byte-for-byte the historical `level <=
# threshold`. The asymmetry (4 cold : 3 warm) is intentional (continuum.py docstring).
VERBOSITY_CONTINUUM = Continuum(
    name="verbosity",
    ranks={
        "nothing": NOTHING, "error": ERROR, "warning": WARNING, "minimal": MINIMAL,
        "default": DEFAULT, "timing": TIMING, "config": CONFIG, "debug": DEBUG,
    },
    invariant="default output",
)

# The silence floor = the cold pole, derived FROM the Continuum (not a magic -4).
SILENCE_FLOOR = VERBOSITY_CONTINUUM.ranks[VERBOSITY_CONTINUUM.cold_pole()]  # NOTHING


def shows(level: int, threshold: int) -> bool:
    """The THAC0 emit gate, materialized: a message at ``level`` shows when the
    channel's ``threshold`` admits it -- ``level <= threshold`` (the Continuum's
    ``passes``, since the levels ARE the ranks) AND the threshold is above the
    silence floor. Nothing is ever emitted AT the floor, so threshold==floor =
    "exit code only" (the hard wall falls out of the gate, no separate check)."""
    return threshold > SILENCE_FLOOR and level <= threshold


def rank_of(name: str) -> int:
    """The signed rank of a named rung (``rank_of('config') == 2``) -- the
    name->rank lookup channel specs will use (`--show timing:config`, DWP-B/B-2)."""
    return VERBOSITY_CONTINUUM.rank(name)
