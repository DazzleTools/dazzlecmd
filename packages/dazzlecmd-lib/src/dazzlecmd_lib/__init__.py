"""dazzlecmd-lib -- Engine library for dazzlecmd-pattern tool aggregators.

Build your own dz-pattern CLI in ~10 lines:

    from dazzlecmd_lib import AggregatorEngine

    def main():
        engine = AggregatorEngine(
            name="my-tools",
            command="mt",
            tools_dir="tools",
            manifest=".mt.json",
            version_info=("1.0", "1.0.0_main_1"),
        )
        return engine.run()

That gets you default ``mt list``, ``mt info <tool>``, ``mt kit``,
``mt version``, ``mt tree``, ``mt setup``. Customize via:

    engine.meta_registry.register("mycmd", parser_factory, handler)
    engine.meta_registry.override("list", handler=my_custom_list)
    engine.meta_registry.unregister("tree")

Public API:
    - AggregatorEngine: configurable CLI tool aggregator
    - FQCNIndex: dual-index lookup for Fully Qualified Collection Names
    - RunnerRegistry: extensible runtime dispatch (runtime types)
    - MetaCommandRegistry: per-engine meta-command registry
    - cli_helpers: argparse scaffolding helpers for escape-hatch paths
    - default_meta_commands: stock list/info/kit/version/tree/setup
    - ConfigManager: per-aggregator config reading/writing
    - CircularDependencyError, FQCNCollisionError: exception types
"""

from dazzlecmd_lib._version import __version__

# Core engine + FQCN
from dazzlecmd_lib.engine import (
    AggregatorEngine,
    FQCNIndex,
    FQCNCollisionError,
    CircularDependencyError,
)

# Runtime dispatch
from dazzlecmd_lib.registry import RunnerRegistry

# Config + meta-command machinery
from dazzlecmd_lib.config import ConfigManager
from dazzlecmd_lib.meta_command_registry import (
    MetaCommandRegistry,
    MetaCommandAlreadyRegisteredError,
    MetaCommandNotRegisteredError,
    RegistryLockedError,
)

# CLI helpers + defaults (available as modules; not re-exported at top level
# to keep the namespace clean. Import them explicitly:
#     from dazzlecmd_lib import cli_helpers, default_meta_commands)
from dazzlecmd_lib import cli_helpers
from dazzlecmd_lib import default_meta_commands
