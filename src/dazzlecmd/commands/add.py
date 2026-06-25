"""``dz add`` -- import an existing repo as a dazzlecmd tool.

Moved out of cli.py (decomposition R3, DWP 2026-06-25__16-14-19). Imports the
shared _register_in_kit helper from commands/new.py (one-directional add->new).
cli.py re-exports _cmd_add. Imports nothing from cli.py.
"""
import os
import sys

from dazzlecmd._constants import RESERVED_COMMANDS
from dazzlecmd.commands.new import _register_in_kit

def _cmd_add(args, project_root):
    """Import an existing repo as a dazzlecmd tool."""
    from dazzlecmd.importer import add_from_local

    repo_path = args.repo
    namespace = args.namespace
    projects_dir = os.path.join(project_root, "projects")

    # Expand and resolve path
    repo_path = os.path.abspath(os.path.expanduser(repo_path))

    if not os.path.isdir(repo_path):
        print(f"Error: '{repo_path}' is not a directory", file=sys.stderr)
        return 1

    # Determine link mode
    link_mode = "link" if args.link else "copy"

    result = add_from_local(
        source_path=repo_path,
        projects_dir=projects_dir,
        namespace=namespace,
        link_mode=link_mode,
        tool_name=args.name,
        reserved_commands=RESERVED_COMMANDS,
    )

    if result is None:
        return 1

    mode_desc = "Linked" if result["link_mode"] in ("symlink", "junction") else "Copied"
    print(f"{mode_desc}: {result['namespace']}:{result['name']}")
    if result["link_mode"] in ("symlink", "junction"):
        print(f"  {result['link_mode']} -> {result['source_path']}")
    print(f"  Run: dz {result['name']} --help")

    # Register in kit if requested
    if args.kit:
        _register_in_kit(project_root, args.kit, result["namespace"],
                         result["name"])

    return 0
