"""Leaf constants for the dazzlecmd CLI.

This module imports nothing from elsewhere in ``dazzlecmd`` so it can be
imported by any command module (``dazzlecmd.commands.*``), the parser
builder, and ``cli.py`` without forming an import cycle. ``cli.py``
re-exports ``RESERVED_COMMANDS`` for backward compatibility
(``from dazzlecmd.cli import RESERVED_COMMANDS`` -- used by importer.py).
"""

# Reserved command names that cannot be used as tool names.
# P-5 (the keyword-hygiene sweep, finding #1): the app IMPORTS-AND-
# EXTENDS the lib's registry -- previously two uncoordinated sets
# (the lib's was never imported, leaving prop/level/setup/action
# unprotected against tool-name collisions). One source + the app's
# own pipeline verbs.
from dazzlecmd_lib.reserved import DEFAULT_RESERVED_COMMANDS

RESERVED_COMMANDS = set(DEFAULT_RESERVED_COMMANDS) | {
    # dz-specific pipeline verbs (not universal across aggregators)
    "search", "build", "enhance", "graduate",
}
