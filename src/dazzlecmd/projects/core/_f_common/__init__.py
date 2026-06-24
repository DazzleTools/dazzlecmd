"""Shared adapter library for the dz f-* file operation tools (f-mv, f-cp).

Wraps dazzle_preservelib behind a stable dz-facing API: dataclass results,
dz-convention exit codes, and explicit policy enums. Not a dispatched
tool -- the underscore-prefix directory and absent .dazzlecmd.json
keep AggregatorEngine from registering this as a command.
"""

from .safe_ops import (
    ConflictPolicy,
    OpResult,
    PRESERVELIB_AVAILABLE,
    safe_cp,
    safe_mv,
)

__all__ = [
    "ConflictPolicy",
    "OpResult",
    "PRESERVELIB_AVAILABLE",
    "safe_cp",
    "safe_mv",
]
