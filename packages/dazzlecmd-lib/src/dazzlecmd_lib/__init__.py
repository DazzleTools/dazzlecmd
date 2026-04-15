"""dazzlecmd-lib -- Engine library for dazzlecmd-pattern tool aggregators.

Build your own dz-pattern CLI in ~15 lines:

    from dazzlecmd_lib.engine import AggregatorEngine

    engine = AggregatorEngine(
        name="my-tools",
        command="mt",
        tools_dir="tools",
        manifest=".mt.json",
    )

Public API:
    - AggregatorEngine: configurable CLI tool aggregator
    - FQCNIndex: dual-index lookup for Fully Qualified Collection Names
    - RunnerRegistry: extensible runtime dispatch
    - CircularDependencyError, FQCNCollisionError: exception types
"""

from dazzlecmd_lib._version import __version__

# Public API — importable directly from dazzlecmd_lib
from dazzlecmd_lib.engine import (
    AggregatorEngine,
    FQCNIndex,
    FQCNCollisionError,
    CircularDependencyError,
)
from dazzlecmd_lib.registry import RunnerRegistry
from dazzlecmd_lib.config import ConfigManager
