"""Re-export shim -- the ``Continuum`` primitive lifted to the dazzle-lib
foundation (B3a of the Groupable<->Continuum<->states unification's lift).

``dazzlecmd-lib`` now imports the primitive from ``dazzle_lib.continuum``; this
module keeps the historical ``dazzlecmd_lib.continuum`` import path working
byte-for-byte (every existing ``from dazzlecmd_lib.continuum import ...`` is
unchanged). The DOMAIN-specific spaces (``VISIBILITY_CONTINUUM`` in states.py,
``KIT_PRESENCE_SPACE`` in groupable.py) stay in dazzlecmd -- only the pure,
domain-neutral primitive moved to the bedrock.

See the B3 DWP + dazzle-lib's CHANGELOG (0.3 -- the "types only" -> "types + pure
primitives" charter evolution).
"""
from dazzle_lib.continuum import (  # noqa: F401  (re-export -- moved to the bedrock)
    Continuum,
    ContinuumBoundaryError,
    ContinuumError,
    ContinuumProtocol,
    ContinuumSpace,
    ContinuumSpaceProtocol,
    _ContinuumLens,
)
