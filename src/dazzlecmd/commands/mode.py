"""``dz mode`` -- dev/publish mode handlers (thin wrappers over dazzlecmd.mode).

Moved out of cli.py (decomposition R3, DWP 2026-06-25__16-14-19). Each handler
lazily imports its implementation from dazzlecmd.mode; this module needs no
top-level imports. cli.py re-exports these handlers.
"""

def _cmd_mode_status(args, projects, project_root):
    """Show mode status for tools."""
    from dazzlecmd.mode import cmd_status
    tool_filter = getattr(args, "tool", None)
    kit_filter = getattr(args, "kit", None)
    return cmd_status(projects, project_root, tool_filter=tool_filter,
                      kit_filter=kit_filter)


def _cmd_mode_switch(args, projects, project_root):
    """Toggle a tool between dev and publish mode."""
    from dazzlecmd.mode import cmd_switch

    force_mode = None
    if getattr(args, "dev", False):
        force_mode = "dev"
    elif getattr(args, "publish", False):
        force_mode = "publish"

    return cmd_switch(
        tool_name=args.tool,
        projects=projects,
        project_root=project_root,
        dev_path=getattr(args, "path", None),
        force_mode=force_mode,
        dry_run=getattr(args, "dry_run", False),
        url=getattr(args, "url", None),
        force=getattr(args, "force", False),
        immediate=getattr(args, "immediate", False),
    )


def _cmd_mode_restore(args, projects, project_root):
    """Restore a tool to its prior on-disk form (undo a dev-mode switch)."""
    from dazzlecmd.mode import cmd_restore

    return cmd_restore(
        tool_name=args.tool,
        projects=projects,
        project_root=project_root,
        dry_run=getattr(args, "dry_run", False),
    )
