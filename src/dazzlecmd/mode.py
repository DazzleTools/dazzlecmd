"""Dev/publish mode toggle for dazzlecmd -- thin wrapper around ``dazzlecmd_lib.mode``.

As of v0.7.48 (Tier 1 T1-H), the business logic lives in
``dazzlecmd_lib.mode``. This module exists to:

1. Re-export the public API for backward compatibility with callers that
   ``from dazzlecmd.mode import ...`` (existing tests, ``loader.py``,
   ``cli.py``).
2. Wrap the parameterized library functions with dazzlecmd's defaults
   (``tools_dir="projects"``, ``command="dz"``, default schema) so
   existing callers don't need to thread those parameters.

For an aggregator-agnostic surface, import directly from
``dazzlecmd_lib.mode`` and pass the configuration explicitly -- that's
what wtf-windows / amdead / future aggregators do via their own
``aggregator.json`` + ``AggregatorEngine.from_project()`` plumbing.

Pre-v0.7.48 this file contained ~730 LOC of business logic. The whole
file is now a re-export shim plus 5 wrapper functions; the implementation
is in ``packages/dazzlecmd-lib/src/dazzlecmd_lib/mode.py``.
"""

# Re-export state constants + labels + non-parameterized functions.
# These have identical behavior to the pre-v0.7.48 versions.
from dazzlecmd_lib.mode import (  # noqa: F401
    STATE_SYMLINK,
    STATE_SUBMODULE,
    STATE_EMBEDDED,
    STATE_MISSING,
    STATE_LOCAL_ONLY,
    STATE_LABELS,
    load_local_config,
    save_local_config,
    cache_manifest,
    get_cached_manifest,
)

# Import parameterized functions with private aliases so we can wrap them
# below with dazzlecmd's defaults.
from dazzlecmd_lib.mode import parse_gitmodules as _lib_parse_gitmodules
from dazzlecmd_lib.mode import detect_tool_state as _lib_detect_tool_state
from dazzlecmd_lib.mode import resolve_dev_path as _lib_resolve_dev_path
from dazzlecmd_lib.mode import cmd_status as _lib_cmd_status
from dazzlecmd_lib.mode import cmd_switch as _lib_cmd_switch


# dazzlecmd's aggregator-specific defaults. wtf-windows / amdead supply
# different values via their own aggregator.json.
_TOOLS_DIR = "projects"
_COMMAND = "dz"


def parse_gitmodules(project_root):
    """Parse ``.gitmodules`` for dazzlecmd (defaults ``tools_dir="projects"``).

    Library-agnostic callers can use ``dazzlecmd_lib.mode.parse_gitmodules``
    directly with an explicit ``tools_dir``.
    """
    return _lib_parse_gitmodules(project_root, tools_dir=_TOOLS_DIR)


def detect_tool_state(tool_dir, gitmodules, project_root):
    """Detect the current mode of a tool, dazzlecmd-style."""
    return _lib_detect_tool_state(
        tool_dir, gitmodules, project_root, tools_dir=_TOOLS_DIR
    )


def resolve_dev_path(qualified_name, project_root, explicit_path=None):
    """Resolve the local dev path for a dazzlecmd tool."""
    return _lib_resolve_dev_path(
        qualified_name, project_root, explicit_path,
        tools_dir=_TOOLS_DIR,
    )


def cmd_status(projects, project_root, tool_filter=None, kit_filter=None):
    """Show mode status for dazzlecmd tools.

    Threads ``tools_dir="projects"`` and ``command="dz"`` to the library
    implementation; passes the dazzlecmd-specific message texts.
    """
    return _lib_cmd_status(
        projects, project_root,
        tool_filter=tool_filter, kit_filter=kit_filter,
        tools_dir=_TOOLS_DIR, command=_COMMAND,
    )


def cmd_switch(tool_name, projects, project_root, dev_path=None,
               force_mode=None, dry_run=False, url=None, force=False):
    """Toggle a dazzlecmd tool between dev and publish mode."""
    return _lib_cmd_switch(
        tool_name, projects, project_root,
        dev_path=dev_path, force_mode=force_mode,
        dry_run=dry_run, url=url, force=force,
        tools_dir=_TOOLS_DIR, command=_COMMAND, schema=None,
    )
