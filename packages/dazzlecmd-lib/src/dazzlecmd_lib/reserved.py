"""Reserved-command namespace contract for dazzlecmd-lib aggregators.

The library publishes two sets:

- ``DEFAULT_RESERVED_COMMANDS`` -- the namespace contract. Any name in this
  set is reserved across every aggregator: a tool cannot be created with
  these names because they would collide with meta-command semantics.

- ``DEFAULT_META_COMMANDS_USER`` -- the minimal "user-facing aggregator"
  registration set. Aggregators that want a focused, completable surface
  (amdead, sysdiagnose-public, sample distros) register these by default.

- ``DEFAULT_META_COMMANDS_DEV`` -- adds the "dev-mode" meta-commands
  (``add``, ``mode``, ``new``) on top of the user set. Aggregators that
  serve as developer toolchains (dazzlecmd itself, eventually wtf-windows
  with submodule lifecycle management) opt into this set.

Reserved-set vs registered-set:

- *Reserved* names cannot be used as tool names (preserves dispatch
  unambiguity). This is the policy.
- *Registered* meta-commands are what actually appears in the aggregator's
  CLI surface. An aggregator can reserve "mode" without registering it --
  the namespace is protected, but the subcommand isn't exposed.

Aggregators choose their meta-command set via ``aggregator.json``::

    "meta_commands": ["list", "info", "kit", "tree", "setup", "version"]
"""

# All 9 are reserved as a namespace contract (you can't name a tool "mode").
DEFAULT_RESERVED_COMMANDS = frozenset({
    "list",     # List available tools
    "info",     # Show detailed info about a tool
    "kit",      # Manage kits
    "new",      # Create a new tool project
    "add",      # Import an existing tool/repo
    "mode",     # Toggle dev/publish mode
    "tree",     # Show the aggregator tree
    "setup",    # Run a tool's declared setup script
    "version",  # Show version info
    "action",   # Operate on metadata-plane annotations (dz action <type>
                # <dot-expr>; pluggable types, `run` native first). Reserved
                # AHEAD of the #87 framework so no tool can squat the verb.
})

# The minimal user-facing meta-command set -- what an aggregator that is a
# "complete package unto itself" exposes by default. No tool-import, no mode
# switching, no new-tool scaffolding -- those are dev features.
DEFAULT_META_COMMANDS_USER = frozenset({
    "list", "info", "kit", "tree", "setup", "version",
})

# The dev-mode additions. An aggregator that adds these becomes a full
# developer toolchain capable of importing third-party tools, swapping
# modes, and scaffolding new tool projects.
DEFAULT_META_COMMANDS_DEV_EXTRAS = frozenset({
    "add", "mode", "new",
})

# Convenience: the union, for aggregators that want everything.
DEFAULT_META_COMMANDS_DEV = DEFAULT_META_COMMANDS_USER | DEFAULT_META_COMMANDS_DEV_EXTRAS
