"""Leaf constants for the dazzlecmd CLI.

This module imports nothing from elsewhere in ``dazzlecmd`` so it can be
imported by any command module (``dazzlecmd.commands.*``), the parser
builder, and ``cli.py`` without forming an import cycle. ``cli.py``
re-exports ``RESERVED_COMMANDS`` for backward compatibility
(``from dazzlecmd.cli import RESERVED_COMMANDS`` -- used by importer.py).
"""

# Reserved command names that cannot be used as tool names.
RESERVED_COMMANDS = {
    "new", "add", "list", "info", "kit", "search",
    "build", "tree", "version", "enhance", "graduate", "mode",
    # B4-mutate: the bare-verb cross-level toggles (`dz enable <kit>` etc.).
    # Listed here so engine.run treats them as meta-commands, not tool names.
    "enable", "disable", "attach", "detach",
    # SD-B: the foreground namespace (`dz meta use <level>`) + its top alias.
    "meta", "use",
}
