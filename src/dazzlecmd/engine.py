"""Backwards-compat shim — engine code lives in dazzlecmd-lib.

All public names are re-exported so existing code that does
``from dazzlecmd.engine import AggregatorEngine`` continues to work.
New code should import from ``dazzlecmd_lib.engine`` directly.
"""

# Re-export everything from the library
from dazzlecmd_lib.engine import *  # noqa: F401,F403
from dazzlecmd_lib.engine import (  # noqa: F811 — explicit for IDE support
    AggregatorEngine,
    FQCNIndex,
    FQCNCollisionError,
    CircularDependencyError,
)
