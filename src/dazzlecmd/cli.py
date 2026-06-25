"""Main CLI entry point for dazzlecmd.

This module provides the dazzlecmd-specific configuration and the
build_parser/dispatch functions that the AggregatorEngine delegates to.
New aggregator projects should use AggregatorEngine directly rather than
importing from this module.
"""

import argparse
import json
import os
import re
import sys

from dazzlecmd._version import DISPLAY_VERSION, __version__
from dazzlecmd._constants import RESERVED_COMMANDS  # noqa: F401  (re-exported)
from dazzlecmd.kit_verbs import (
    LIFECYCLE_PAIRS,
    add_flat_verb,
    build_lifecycle_axis_groups,
    render_kit_help,
)
from dazzlecmd.loader import (
    discover_kits,
    discover_projects,
    get_active_kits,
    resolve_entry_point,
)
from dazzlecmd_lib import colors as _colors


# v0.7.44 (4b-T3 + 4d-3): per-language scaffolding ships. The set of
# valid ``--language`` values is now derived from the template directory
# layout under ``packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/`` --
# any directory there (other than ``__*__`` overlay dirs) is a valid
# language. The v0.7.40 ``_SUPPORTED_LANGUAGES_V0740`` guard is gone.


def find_project_root():
    """Find the dazzlecmd project root by navigating from __file__.

    Legacy wrapper -- new code should use AggregatorEngine.find_project_root().
    """
    from dazzlecmd.engine import AggregatorEngine
    return AggregatorEngine().find_project_root()


def build_parser(projects, engine=None):
    """Build argparse parser with dynamic subparsers for discovered tools."""
    # Build categorized epilog for help display
    # Use engine config if available, fall back to dazzlecmd defaults
    prog = engine.command if engine else "dz"
    desc = engine.description if engine else "dazzlecmd - Unified CLI for the DazzleTools collection"
    reserved = engine.reserved_commands if engine else RESERVED_COMMANDS

    if engine and engine.version_info:
        display_ver, full_ver = engine.version_info
        version_str = f"{engine.name} {display_ver} ({full_ver})"
    else:
        version_str = f"dazzlecmd {DISPLAY_VERSION} ({__version__})"

    epilog = _build_categorized_help(projects)

    parser = argparse.ArgumentParser(
        prog=prog,
        description=desc,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=version_str,
    )

    # Suppress default subparser listing — we show our own categorized version
    subparsers = parser.add_subparsers(dest="command", metavar="<command>",
                                       help=argparse.SUPPRESS)

    # Register meta-commands (only if root aggregator)
    is_root = engine.is_root if engine else True
    if is_root:
        _register_meta_commands(subparsers)

    # Register discovered tool commands
    for project in projects:
        name = project.name
        if name in reserved:
            print(
                f"Warning: Tool '{name}' conflicts with reserved command, skipping",
                file=sys.stderr,
            )
            continue

        desc = project.description or ""
        sub = subparsers.add_parser(
            name,
            help=desc,
            add_help=False,  # Let the tool handle its own --help
        )
        sub.set_defaults(_project=project)

    return parser


# Display helpers: canonical implementations live in dazzlecmd_lib.
# (The kit-list renderer itself moved to the lib in the unification DWP,
# 2026-06-11 -- dazzlecmd no longer carries a custom _cmd_kit_list.)
from dazzlecmd_lib.default_meta_commands import (  # noqa: F401
    _wrap_description,
    KIT_NAME_COL,
    MIN_DESC_WIDTH,
    SUMMARY_INDENT,
    TERM_SIZE_FALLBACK,
)


def _build_categorized_help(projects):
    """Build a categorized command listing for the help epilog."""
    # Meta-commands (builtins)
    builtins = [
        ("list", "List available tools"),
        ("info <tool>", "Show detailed info about a tool"),
        ("kit", "Manage {kits, aggregators, virtual kits, ...}"),
        ("new <name>", "Create a new tool project"),
        ("add", "Import an existing tool/repo"),
        ("mode", "Toggle dev/publish mode"),
        ("tree", "Show the aggregator tree"),
        ("setup <tool>", "Run a tool's declared setup script"),
        ("version", "Show version info"),
    ]

    # Group tools by kit import name (the top-level kit a tool belongs to)
    namespaces = {}
    for project in projects:
        name = project.name
        if name in RESERVED_COMMANDS:
            continue
        kit = project.kit_import_name or project.namespace or "other"
        desc = project.description or ""
        namespaces.setdefault(kit, []).append((name, desc))

    # Detect terminal width for description truncation
    import shutil
    term_width = shutil.get_terminal_size(TERM_SIZE_FALLBACK).columns

    # Build output
    lines = []
    name_width = 16

    def _one_line_row(name, desc):
        """One row, truncated to the REAL line budget. A name longer than
        ``name_width`` overflows its column, so the description budget must
        be computed from the ACTUAL printed prefix (2 indent + name-or-column
        + 2 gap) -- a fixed budget let long-named rows exceed the terminal
        width and the terminal hard-wrapped the tail mid-word."""
        used = 2 + max(name_width, len(name)) + 2
        avail = term_width - used
        if avail > MIN_DESC_WIDTH and len(desc) > avail:
            desc = desc[:avail - 3] + "..."
        return f"  {name:<{name_width}}  {desc}"

    lines.append("commands:")
    for cmd, desc in builtins:
        lines.append(_one_line_row(cmd, desc))

    # Tool categories by namespace
    for ns in sorted(namespaces.keys()):
        tools = namespaces[ns]
        lines.append("")
        lines.append(f"{ns} tools:")
        for name, desc in sorted(tools):
            lines.append(_one_line_row(name, desc))

    lines.append("")
    lines.append("Run 'dz <command> --help' for details on a specific command.")

    return "\n".join(lines)


def _register_meta_commands(subparsers):
    """Register built-in meta-commands."""
    # dz list
    list_parser = subparsers.add_parser("list", help="List available tools")
    list_parser.add_argument("--namespace", "-n", help="Filter by namespace")
    list_parser.add_argument("--kit", "-k", help="Filter by kit (canonical OR virtual)")
    list_parser.add_argument("--tag", "-t", help="Filter by tag")
    list_parser.add_argument("--platform", "-p", help="Filter by platform")
    list_parser.add_argument(
        "--show",
        choices=["default", "canonical", "alias", "all"],
        default=None,
        help=(
            "Content selector. 'default' (alias-preferred): virtual-kit "
            "aliases replace their canonical targets. 'canonical': "
            "canonicals only (script-stable legacy view). 'alias': aliases "
            "only. 'all': both canonicals and aliases. Falls back to "
            "config key 'list_view' then to 'default' if unset."
        ),
    )
    list_parser.add_argument(
        "--show-hidden", action="store_true",
        help="Include tools hidden via the 'hidden_tools' config (still dispatchable).",
    )
    list_parser.set_defaults(_meta="list")

    # dz info <tool>
    info_parser = subparsers.add_parser("info", help="Show detailed info about a tool")
    info_parser.add_argument("tool", help="Tool name to inspect")
    info_parser.add_argument(
        "--raw",
        action="store_true",
        help="Show the manifest as declared, without conditional-dispatch resolution.",
    )
    info_parser.add_argument(
        "--platform",
        metavar="SPEC",
        help=(
            "Preview runtime resolution for a specific platform "
            "(e.g., 'linux.debian', 'windows', 'macos.macos14'). "
            "Enumerates the prefer array without evaluating preconditions."
        ),
    )
    info_parser.add_argument(
        "--as",
        dest="as_level",
        choices=["tool", "kit", "aggregator"],
        help=(
            "Force the level when the name matches more than one of "
            "tool/kit/aggregator (otherwise the more-specific level wins, "
            "with a note)."
        ),
    )
    info_parser.set_defaults(_meta="info")

    # dz kit -- `kit -h` is rendered as a de-duped by-axis hierarchy (the
    # format_help override below, set after all subcommands are registered so it
    # reads their real help) instead of argparse's default positional restatement.
    kit_parser = subparsers.add_parser(
        "kit", help="Manage {kits, aggregators, virtual kits, ...}")
    kit_sub = kit_parser.add_subparsers(dest="kit_command")

    kit_list = kit_sub.add_parser(
        "list", help="List available kits, or tools in a kit"
    )
    kit_list.add_argument(
        "name", nargs="?", default=None, help="Kit name to show tools for"
    )
    kit_list.set_defaults(_meta="kit_list")

    kit_status = kit_sub.add_parser(
        "status", help="Show active kits (or `status <kit>` for one kit's axis-state)")
    kit_status.add_argument(
        "name", nargs="?",
        help="A kit to show its per-axis state for (omit for the active-kits summary)")
    kit_status.set_defaults(_meta="kit_status")

    # dz kit info <kit> -- the STATIC identity card (vs `status`'s dynamic axes).
    kit_info = kit_sub.add_parser(
        "info", help="Show a kit's static identity card (`info <kit>`)")
    kit_info.add_argument("name", help="Kit to show the identity card for")
    kit_info.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Emit the card as JSON instead of the aligned text card.")
    kit_info.set_defaults(_meta="kit_info")

    # Flat lifecycle verbs (kept as aliases). Their arg-setup is shared with the
    # nested per-axis groups below via kit_verbs.VERB_SPEC -- one source, so
    # `dz kit enable` and `dz kit activation enable` are byte-identical.
    add_flat_verb(kit_sub, "enable")
    add_flat_verb(kit_sub, "disable")

    kit_focus = kit_sub.add_parser(
        "focus",
        help="Focus on one kit: enable it and disable all others (except always_active)",
    )
    kit_focus.add_argument("name", help="Kit name to focus on")
    kit_focus.set_defaults(_meta="kit_focus")

    kit_reset = kit_sub.add_parser(
        "reset", help="Reset user config -- clears all kit preferences"
    )
    kit_reset.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip confirmation prompt",
    )
    kit_reset.set_defaults(_meta="kit_reset")

    kit_favorite = kit_sub.add_parser(
        "favorite",
        help="Pin a favorite tool to win short-name resolution on collision",
    )
    kit_favorite.add_argument(
        "short", nargs="?", default=None,
        help="Short name to bind (omit when using --migrate-stale)",
    )
    kit_favorite.add_argument(
        "fqcn", nargs="?", default=None,
        help="FQCN of the target tool (omit when using --migrate-stale)",
    )
    kit_favorite.add_argument(
        "--migrate-stale", action="store_true", dest="migrate_stale",
        help=(
            "Interactively walk through favorites whose target FQCN is no "
            "longer discovered (tool removed, renamed, or shadowed). For "
            "each stale entry, choose to remap, drop, or skip. Non-TTY "
            "invocations print the stale list and exit non-zero."
        ),
    )
    kit_favorite.set_defaults(_meta="kit_favorite")

    kit_unfavorite = kit_sub.add_parser(
        "unfavorite", help="Remove a favorite binding"
    )
    kit_unfavorite.add_argument("short", help="Short name to unbind")
    kit_unfavorite.set_defaults(_meta="kit_unfavorite")

    # ----- Visibility: how PRESENT a tool is on one presence axis
    # (visible -> silenced -> hidden -> shadowed). Nested under `dz kit
    # visibility` so the top level stays legible; the toggles keep their original
    # `_meta` (dispatch unchanged). The bare form lists all non-default; `status`
    # shows a tool's level + the next stronger/weaker move (KIT_PRESENCE_SPACE).
    kit_visibility = kit_sub.add_parser(
        "visibility",
        help="How present a tool is: silence/hide/shadow + the presence spectrum",
    )
    vis_sub = kit_visibility.add_subparsers(dest="visibility_command")

    # `status` first -- the generic inspect verb (not a domain toggle). The
    # blank-line separator + the wider generic-first grouping land with the
    # v0.9.37 kit -h help formatter.
    vis_status = vis_sub.add_parser(
        "status",
        help="Show a tool's presence level + the less/more visible move")
    vis_status.add_argument("fqcn", help="FQCN to inspect")
    vis_status.set_defaults(_meta="kit_visibility_status")

    # The six toggles all route to ONE handler (_cmd_kit_visibility_set); each
    # carries its (level, direction) -- the per-verb knowledge is the typed rung
    # in KIT_PRESENCE_SPACE, not here.
    vis_silence = vis_sub.add_parser(
        "silence", help="Suppress the rerooting hint for a tool (presence: silenced)")
    vis_silence.add_argument("fqcn", help="FQCN (or short name) to silence")
    vis_silence.set_defaults(_meta="kit_visibility_set", level="silenced", direction="suppress")

    vis_unsilence = vis_sub.add_parser(
        "unsilence", help="Restore the rerooting hint")
    vis_unsilence.add_argument("fqcn", help="FQCN (or short name) to unsilence")
    vis_unsilence.set_defaults(_meta="kit_visibility_set", level="silenced", direction="restore")

    vis_hide = vis_sub.add_parser(
        "hide", help="Omit a tool from listings -- still dispatchable (presence: hidden)")
    vis_hide.add_argument("fqcn", help="FQCN (or short name) to hide")
    vis_hide.set_defaults(_meta="kit_visibility_set", level="hidden", direction="suppress")

    vis_unhide = vis_sub.add_parser(
        "unhide", help="Restore a hidden tool to listings")
    vis_unhide.add_argument("fqcn", help="FQCN (or short name) to unhide")
    vis_unhide.set_defaults(_meta="kit_visibility_set", level="hidden", direction="restore")

    vis_shadow = vis_sub.add_parser(
        "shadow",
        help="Remove a tool from dispatch + free its short name (presence: shadowed)")
    vis_shadow.add_argument("fqcn", help="FQCN (or short name) to shadow")
    vis_shadow.set_defaults(_meta="kit_visibility_set", level="shadowed", direction="suppress")

    vis_unshadow = vis_sub.add_parser(
        "unshadow", help="Restore a shadowed tool to dispatch")
    vis_unshadow.add_argument("fqcn", help="FQCN (or short name) to unshadow")
    vis_unshadow.set_defaults(_meta="kit_visibility_set", level="shadowed", direction="restore")

    # `--cascade` (B2c) -- the general ContinuumSpace apply-mode: apply a SLICE of
    # adjacent presence rungs in one move instead of just this one. Bare = to
    # neutral (subsume the weaker rungs); `=lo,hi` = a signed offset window
    # (+ = warmer/more visible, - = colder); `=up|down[:N]` = toward a pole / N
    # steps. Default OFF = the single-rung write (unchanged). Use the `=` form for
    # values so a leading `-` isn't read as a flag (e.g. `--cascade=-1,2`).
    for _vp in (vis_silence, vis_unsilence, vis_hide, vis_unhide, vis_shadow, vis_unshadow):
        _vp.add_argument(
            "--cascade", nargs="?", const="@neutral", default=None, metavar="RANGE",
            help="also apply adjacent presence rungs (bare=to-neutral; "
                 "=lo,hi window e.g. =-1,2; =up|down[:N] toward a pole / N steps)")

    kit_visibility.set_defaults(_meta="kit_visibility")

    add_flat_verb(kit_sub, "add")
    add_flat_verb(kit_sub, "remove")
    add_flat_verb(kit_sub, "detach")
    add_flat_verb(kit_sub, "attach")

    # `dz kit management [<kit>]` -- the lifecycle STATE view (like `dz kit
    # visibility`): activation + loading per kit. Each axis group also shows its
    # own slice with no verb (dispatch below).
    kit_management = kit_sub.add_parser(
        "management",
        help="Show kit lifecycle state (activation/loading) for all kits or one",
    )
    kit_management.add_argument("name", nargs="?", default=None,
                                help="Show just this kit")
    kit_management.set_defaults(_meta="kit_management")

    # The nested per-axis groups -- the SAME shape as `dz kit visibility`:
    # `dz kit activation {enable,disable}`, `dz kit loading {attach,detach}`,
    # `dz kit membership {add,remove}` (registry-driven; verbs share the handler
    # with the flat aliases above).
    build_lifecycle_axis_groups(kit_sub)

    # Render `dz kit -h` as the de-duped by-axis hierarchy. Set AFTER all
    # subcommands (incl. visibility + the axis groups) are registered, so the
    # render reads their real help. Overriding the instance method is intentional.
    kit_parser.format_help = lambda: render_kit_help(kit_parser)

    kit_parser.set_defaults(_meta="kit")

    # dz tree
    tree_parser = subparsers.add_parser(
        "tree",
        help="Visualize the aggregator tree (kits and tools with FQCNs)",
    )
    tree_parser.add_argument("--json", action="store_true",
                             help="Output as JSON")
    tree_parser.add_argument("--depth", type=int, default=None,
                             help="Limit display depth")
    tree_parser.add_argument("--kit", "-k", default=None,
                             help="Show only this kit's subtree")
    tree_parser.add_argument("--show-disabled", action="store_true",
                             help="Include disabled kits in the output")
    tree_parser.add_argument("--show-hidden", action="store_true",
                             help="Include tools hidden via 'hidden_tools' config (still dispatchable)")
    tree_parser.add_argument("--show-empty", action="store_true",
                             help="Include enabled kits that have no tools (childless branches)")
    tree_parser.set_defaults(_meta="tree")

    # dz setup <tool>
    setup_parser = subparsers.add_parser(
        "setup",
        help="Run a tool's declared setup script (install deps, build, etc.)",
    )
    setup_parser.add_argument(
        "tool", nargs="?", default=None,
        help="Tool name (or FQCN). Omit to list tools with setup commands.",
    )
    setup_parser.set_defaults(_meta="setup")

    # dz new <type> <name>  -- sub-parser redesign (4d-1)
    # Replaces flat ``dz new <name>``. Three types:
    #   tool       -- fully implemented in v0.7.40
    #   kit        -- stub in v0.7.40; full impl in v0.7.42 (4d-2)
    #   aggregator -- stub in v0.7.40; full impl in v0.7.42 (4d-2)
    new_parser = subparsers.add_parser(
        "new", help="Create a new tool, kit, or aggregator"
    )
    new_sub = new_parser.add_subparsers(
        dest="new_type", title="entity types",
        description="Choose the kind of entity to create",
    )

    # dz new tool <name>
    new_tool_parser = new_sub.add_parser(
        "tool", help="Create a new tool"
    )
    new_tool_parser.add_argument("name", help="Tool name")
    new_tool_parser.add_argument(
        "--namespace", "-n", default=None,
        help="Namespace (default: from user config 'new.default_namespace' "
             "or 'dazzletools')",
    )
    new_tool_parser.add_argument(
        "--kit", "-k", help="Register in this kit (e.g., core, dazzletools)"
    )
    new_tool_parser.add_argument(
        "--simple", action="store_true",
        help="Add TODO.md and NOTES.md",
    )
    new_tool_parser.add_argument(
        "--full", action="store_true",
        help="Add ROADMAP.md, private/claude/, tests/",
    )
    new_tool_parser.add_argument(
        "--description", "-d", default="", help="Tool description"
    )
    new_tool_parser.add_argument(
        "--long-description", default="",
        help="Long-form description (mini man-page text; supports multi-line)",
    )
    new_tool_parser.add_argument(
        "--language", "-l", default=None,
        help="Primary language. v0.7.40 supports 'python' only; "
             "rust/node/powershell/c_cpp/docker/generic land in v0.7.44 (4d-3). "
             "Default: user config 'new.default_language' or 'python'.",
    )
    new_tool_parser.set_defaults(_meta="new_tool")

    # dz new kit <name>  -- local kit inside THIS aggregator (4d-2, OQ-A2)
    new_kit_parser = new_sub.add_parser(
        "kit", help="Create a new local kit (projects/<name>/ + registry pointer)"
    )
    new_kit_parser.add_argument("name", help="Kit name")
    new_kit_parser.add_argument(
        "--description", "-d", default="", help="Kit description"
    )
    new_kit_parser.add_argument(
        "--with-starter", action="store_true",
        help="Include a starter 'hello' tool inside the kit",
    )
    new_kit_parser.set_defaults(_meta="new_kit")

    # dz new aggregator <name>  -- standalone aggregator project (4d-2, OQ-A2:
    # an aggregator is ALWAYS standalone; the local form is `dz new kit`).
    new_agg_parser = new_sub.add_parser(
        "aggregator",
        help="Create a standalone aggregator project (own CLI + pyproject)",
    )
    new_agg_parser.add_argument("name", help="Aggregator/project name")
    new_agg_parser.add_argument(
        "--command", "-c", default=None,
        help="CLI command name (default: derived from the project name)",
    )
    new_agg_parser.add_argument(
        "--description", "-d", default="", help="Project description"
    )
    new_agg_parser.add_argument(
        "--tools-dir", default=None,
        help="Tools directory name (default: config 'new.tools_dir' or 'projects')",
    )
    new_agg_parser.add_argument(
        "--manifest", default=None,
        help="Per-tool manifest filename (default: config 'new.manifest' or "
             "'.dazzlecmd.json')",
    )
    new_agg_parser.add_argument(
        "--with-starter", action="store_true",
        help="Include a starter 'hello' tool in <tools-dir>/core/",
    )
    new_agg_parser.add_argument(
        "--with", dest="with_components", default=None, metavar="C1,C2",
        help="Composable scaffolding components (comma-separated): "
             "docker-test, docker-deploy, ci, common, template, all",
    )
    new_agg_parser.set_defaults(_meta="new_aggregator")

    # Bare ``dz new`` with no type -> show help
    new_parser.set_defaults(_meta="new")

    # dz add
    add_parser = subparsers.add_parser("add", help="Import an existing tool/repo")
    add_parser.add_argument("--repo", "-r", required=True,
                            help="Path to source repo (or URL in future)")
    add_parser.add_argument("--namespace", "-n", default="core",
                            help="Namespace (default: core)")
    add_parser.add_argument("--name", help="Override tool name")
    add_parser.add_argument("--link", action="store_true",
                            help="Create symlink to source (editable install)")
    add_parser.add_argument("--kit", "-k", help="Register in this kit")
    add_parser.set_defaults(_meta="add")

    # dz mode
    mode_parser = subparsers.add_parser("mode", help="Toggle dev/publish mode")
    mode_sub = mode_parser.add_subparsers(dest="mode_command")

    mode_status = mode_sub.add_parser("status", help="Show tool modes")
    mode_status.add_argument("tool", nargs="?", default=None,
                             help="Tool name (optional, show all if omitted)")
    mode_status.add_argument("--kit", "-k", help="Filter by kit")
    mode_status.set_defaults(_meta="mode_status")

    mode_switch = mode_sub.add_parser("switch", help="Toggle dev/publish mode")
    mode_switch.add_argument("tool", help="Tool name to switch")
    mode_switch.add_argument("--path", "-p",
                             help="Path to local source repo (for dev mode)")
    mode_switch.add_argument("--dev", action="store_true",
                             help="Force switch to dev mode")
    mode_switch.add_argument("--publish", action="store_true",
                             help="Force switch to publish mode")
    mode_switch.add_argument("--url", help="Remote URL for submodule "
                             "(reads from manifest if not given)")
    mode_switch.add_argument("--force", action="store_true",
        help="Bypass the dirty-tree safety check (DATA LOSS: any "
             "uncommitted work in the tool directory is destroyed).")
    mode_switch.add_argument("--immediate", action="store_true",
        help="Delete the old tool directory immediately, with NO recovery "
             "backup (by default it is staged to the recoverable trash store; "
             "recover with 'dz safedel recover last').")
    mode_switch.add_argument("--dry-run", action="store_true",
                             help="Show what would happen without doing it")
    mode_switch.set_defaults(_meta="mode_switch")

    mode_restore = mode_sub.add_parser(
        "restore", help="Restore a tool to its prior on-disk form (undo a dev switch)")
    mode_restore.add_argument("tool", help="Tool name to restore")
    mode_restore.add_argument("--dry-run", action="store_true",
                              help="Show what would happen without doing it")
    mode_restore.set_defaults(_meta="mode_restore")

    mode_parser.set_defaults(_meta="mode")

    # dz version (alternate to --version)
    version_parser = subparsers.add_parser("version", help="Show version info")
    version_parser.set_defaults(_meta="version")


def dispatch_meta(args, projects, kits, project_root, engine=None):
    """Handle built-in meta-commands.

    ``engine`` is the ``AggregatorEngine`` instance. Phase 3 commands that
    write to the user config (``dz kit enable`` etc.) need the engine to
    call ``_write_user_config``. Optional for Phase 1/2 backwards compat.
    """
    meta = getattr(args, "_meta", None)

    if meta == "list":
        return _cmd_list(args, projects, engine=engine)
    elif meta == "info":
        return _cmd_info(
            args, projects, engine=engine, kits=kits, project_root=project_root)
    elif meta == "kit_list":
        # Unified renderer: the lib handler passes engine (kit-list DWP).
        from dazzlecmd_lib.default_meta_commands import kit_list_handler
        return kit_list_handler(args, engine, projects, kits, project_root)
    elif meta == "kit_status":
        return _cmd_kit_status(
            kits, engine=engine, args=args, project_root=project_root)
    elif meta == "kit_info":
        return render_kit_info(
            args.name, engine, project_root=project_root,
            as_json=getattr(args, "as_json", False))
    elif meta == "kit":
        # bare "dz kit" with no subcommand behaves like "dz kit list"
        # (routed to the same unified lib renderer; the v0.9.26 unification
        # deleted dz's _cmd_kit_list but left this branch pointing at it --
        # caught by CI's F821 gate, missed by the suite because nothing
        # exercised the bare form).
        from dazzlecmd_lib.default_meta_commands import kit_list_handler
        return kit_list_handler(args, engine, projects, kits, project_root)
    # Phase 3: kit management
    elif meta == "kit_enable":
        return _cmd_kit_enable(args, engine)
    elif meta == "kit_disable":
        return _cmd_kit_disable(args, engine)
    elif meta == "kit_focus":
        return _cmd_kit_focus(args, kits, engine)
    elif meta == "kit_reset":
        return _cmd_kit_reset(args, engine)
    elif meta == "kit_favorite":
        return _cmd_kit_favorite(args, engine)
    elif meta == "kit_unfavorite":
        return _cmd_kit_unfavorite(args, engine)
    elif meta == "kit_visibility_set":
        return _cmd_kit_visibility_set(args, engine)
    elif meta == "kit_visibility":
        return _cmd_kit_visibility_list(engine)
    elif meta == "kit_visibility_status":
        return _cmd_kit_visibility_status(args, engine)
    elif meta == "kit_add":
        return _cmd_kit_add(args, project_root, engine)
    elif meta == "kit_remove":
        return _cmd_kit_remove(args, project_root, engine)
    elif meta == "kit_detach":
        return _cmd_kit_detach(args, project_root, engine)
    elif meta == "kit_attach":
        return _cmd_kit_attach(args, project_root, engine)
    elif meta == "kit_management":
        return _cmd_kit_management(args, project_root, engine, axis=None)
    elif meta and meta.startswith("kit_axis_"):
        # `dz kit <axis>` with no verb -> that sub-axis's state (state-on-invoke).
        return _cmd_kit_management(args, project_root, engine,
                                   axis=meta[len("kit_axis_"):])
    elif meta == "tree":
        return _cmd_tree(args, engine)
    elif meta == "setup":
        return _cmd_setup(args, engine)
    # Legacy paths
    elif meta == "new":
        # Bare ``dz new`` (no type chosen) -- print help and exit non-zero.
        print(
            "Usage: dz new {tool|kit|aggregator} <name> [flags]\n"
            "  dz new tool <name>        Create a new tool (fully supported)\n"
            "  dz new kit <name>         Create a new flat kit (v0.7.42)\n"
            "  dz new aggregator <name>  Create a new aggregator (v0.7.42)\n"
            "Run 'dz new tool --help' for tool-specific flags.",
            file=sys.stderr,
        )
        return 2
    elif meta == "new_tool":
        return _cmd_new_tool(args, project_root, engine)
    elif meta == "new_kit":
        return _cmd_new_kit(args, project_root)
    elif meta == "new_aggregator":
        return _cmd_new_aggregator(args, engine)
    elif meta == "add":
        return _cmd_add(args, project_root)
    elif meta == "mode_status":
        return _cmd_mode_status(args, projects, project_root)
    elif meta == "mode_switch":
        return _cmd_mode_switch(args, projects, project_root)
    elif meta == "mode_restore":
        return _cmd_mode_restore(args, projects, project_root)
    elif meta == "mode":
        # bare "dz mode" with no subcommand — show status
        return _cmd_mode_status(args, projects, project_root)
    elif meta == "version":
        return _cmd_version()

    return 1


def _cmd_list(args, projects, engine=None):
    """List available tools (thin wrapper over library render_list).

    Behavior identical to v0.7.33 -- the library now owns the full --show
    enum (default/canonical/alias/all), sectioned layout (Option O), [*]/[+]
    markers, virtual-kit empty-section injection, footer counts, and the
    public ``build_list_entries`` data API. Library reached parity in v0.7.31.
    """
    from dazzlecmd_lib.default_meta_commands import render_list
    return render_list(args, projects, engine=engine)


def render_aggregator_info(engine, projects, kits, project_root, as_json=False):
    """The aggregator's static identity card (SD-3 per-level field-set, the
    aggregator level). Walks the same ``_print_entity_card`` table as the kit
    card. ``resolve_target`` returns the engine itself for the aggregator level,
    so ``engine`` IS the entity here."""
    import json as _json

    vi = getattr(engine, "version_info", None)
    version = vi[0] if (isinstance(vi, (tuple, list)) and vi) else None
    fields = [
        ("Name", getattr(engine, "name", None)),
        ("Command", getattr(engine, "command", None)),
        ("Kind", "aggregator"),
        ("Description", getattr(engine, "description", None)),
        ("Version", version),
        ("Tools", f"{len(projects or [])} tool(s)"),
        ("Kits", f"{len(kits or [])} kit(s)"),
        ("Root", project_root),
    ]
    if as_json:
        payload = {
            label.lower().replace(" ", "_").replace("-", "_"): value
            for label, value in fields}
        print(_json.dumps(payload, indent=2))
        return 0
    name = getattr(engine, "name", None) or "aggregator"
    return _print_entity_card(f"Aggregator '{name}' -- identity card:", fields)


def _cmd_info(args, projects, engine, kits=None, project_root=None):
    """Show detailed info about a tool, kit, or aggregator (the level-agnostic
    ``dz info <target>``, SD-1/SD-3).

    Resolves the target's level via ``engine.resolve_target`` (a READ verb:
    bare ambiguity auto-picks the more-specific level + prints a note; ``--as``
    pins it), then routes to the level's card:

    - **tool** -> the library ``render_info`` (UNCHANGED -- byte-identical to
      v0.7.33; the rich provenance/shadow/runtime-dispatch card);
    - **kit** -> :func:`render_kit_info`;
    - **aggregator** -> :func:`render_aggregator_info`.

    A name that resolves to nothing falls through to ``render_info`` so the
    legacy "Tool 'X' not found" message + exit code are preserved exactly.
    """
    from dazzlecmd_lib.default_meta_commands import render_info

    res = engine.resolve_target(
        args.tool,
        as_level=getattr(args, "as_level", None),
        mutating=False,
    )
    if res is None:
        # Unknown name -- preserve the exact legacy tool-not-found path.
        return render_info(args, projects, engine)
    if res.notification:
        print(res.notification, file=sys.stderr)
    if res.level == "kit":
        kit_name = getattr(res.entity, "kit_name", None) or res.entity.name
        return render_kit_info(kit_name, engine, project_root=project_root)
    if res.level == "aggregator":
        return render_aggregator_info(res.entity, projects, kits, project_root)
    # tool level (the default / FQCN-qualified path) -- unchanged renderer.
    return render_info(args, projects, engine)



def _kit_axis_state(kit_name, engine, project_root):
    """The kit's current rung on each lifecycle axis -- the read-side of the verb
    registry (SD-3). Iterates the dazzlecmd-lib ``VERB_AXES`` whose ``applies_at``
    includes the kit level; axes with no per-kit rung (the favorite/projection
    binding) are skipped. Returns ``(rows, always_active)`` where ``rows`` is a
    list of ``(axis, rung, warm, cold)``, or ``(None, False)`` if the kit is
    absent. Shared by ``render_kit_status_detail`` (the focused
    ``dz kit status`` view) and the 'Current state' section of
    ``render_kit_info`` -- so a new axis surfaces in BOTH for free (AC3-1)."""
    import types as _types
    from dazzlecmd_lib.contexts import KitMembershipContext
    from dazzlecmd_lib.verb_axis import VERB_AXES, KIT

    kit_list = getattr(engine, "kits", []) or []
    match = next(
        (k for k in kit_list
         if (getattr(k, "kit_name", None) or getattr(k, "name", None)) == kit_name),
        None)
    if match is None:
        return None, False
    always = bool(getattr(match, "always_active", False))
    membership = KitMembershipContext(
        project_root, kit_list, boundary_fqcn=getattr(engine, "command", "dz"))
    ref = _types.SimpleNamespace(
        name=kit_name, kit_name=kit_name, always_active=always)
    pointer = membership.pointer_of(ref) is not None
    cfg = engine._get_user_config() if hasattr(engine, "_get_user_config") else {}
    disabled = (not always) and (
        kit_name in set((cfg or {}).get("disabled_kits") or []))

    def _rung(axis):
        # The kit's current pole on `axis`, or None if the axis carries no kit rung.
        if axis == "activation":
            return "disabled" if disabled else "active"
        if axis == "loading":
            return "pointer (detached)" if pointer else "loaded (attached)"
        if axis == "membership":
            return "member"
        return None

    rows = []
    for va in VERB_AXES:
        if KIT not in va.applies_at:
            continue
        cur = _rung(va.axis)
        if cur is None:
            continue
        rows.append((va.axis, cur, va.warm, va.cold))
    return rows, always


def _print_axis_rows(rows):
    """Print the ``(axis, rung, warm, cold)`` rows as the aligned state block."""
    for axis, cur, warm, cold in rows:
        print(f"  {axis:<12} {cur:<20} ({warm} <-> {cold})")


def render_kit_status_detail(kit_name, engine, project_root):
    """One kit's dynamic per-axis state -- the focused `dz kit status <kit>` view
    (just the state block). The same rows also appear as the 'Current state'
    section of `dz info <kit>` / `dz kit info <kit>`. Distinct from `dz kit
    management <kit>` (the COMPOSED position); this is the per-axis breakdown."""
    rows, always = _kit_axis_state(kit_name, engine, project_root)
    if rows is None:
        print(f"No kit '{kit_name}' found.", file=sys.stderr)
        return 1
    tag = "  [always-active]" if always else ""
    print(f"Kit '{kit_name}' -- per-axis state{tag}:\n")
    _print_axis_rows(rows)
    print("\nMove with `dz kit <axis> on|off <kit>` (or the special verb).")
    return 0


def _print_entity_card(title, fields):
    """Walk a per-level field-set -- a list of ``(label, value)`` -- and print an
    aligned identity card (SD-3: the R-table render_info). Absent values render as
    ``(none)`` rather than being silently dropped (AC3-2), so the card's shape is
    the same for every entity at a level. One walker serves every level's table;
    a new level is a new field-set, not a new renderer (AC3-6)."""
    print(title)
    print()
    width = max((len(label) for label, _ in fields), default=0)
    for label, value in fields:
        shown = value if (value is not None and value != "") else "(none)"
        print(f"  {label + ':':<{width + 1}} {shown}")
    return 0


def render_kit_info(kit_name, engine, project_root=None, as_json=False):
    """A kit's identity card AND its current state, in one read (the user's
    'fold state into info' decision -- see the SD-3 addendum). The STATIC
    field-set (name/kind/version/source/...) is the identity; a 'Current state'
    section follows it with the kit's rung on each lifecycle axis (the same rows
    `dz kit status <kit>` shows on its own). ``--json`` mirrors both: the
    identity fields plus a ``state`` object. Distinct from ``dz kit list <kit>``
    (which lists the kit's *tools*); this is the kit itself."""
    import json as _json

    kit_list = getattr(engine, "kits", []) or []
    match = next(
        (k for k in kit_list
         if (getattr(k, "kit_name", None) or getattr(k, "name", None)) == kit_name),
        None)
    if match is None:
        print(f"No kit '{kit_name}' found.", file=sys.stderr)
        return 1

    virtual = bool(getattr(match, "virtual", False))
    tools = getattr(match, "tools", None) or []
    count_label = "alias(es)" if virtual else "tool(s)"
    version = getattr(match, "version", None)
    if version in (None, "", "0.0.0"):       # the entity default -> "unset"
        version = None

    fields = [
        ("Name", getattr(match, "kit_name", None) or getattr(match, "name", None)),
        ("Kind", "virtual kit" if virtual else "kit"),
        ("Description", getattr(match, "description", None)),
        ("Version", version),
        ("Tools", f"{len(tools)} {count_label}"),
        ("Import name", getattr(match, "kit_import_name", None)),
        ("Directory", getattr(match, "directory", None)),
        ("Source", getattr(match, "kit_source", None)),
        ("Always-active", "yes" if getattr(match, "always_active", False) else "no"),
    ]
    rows, _always = _kit_axis_state(kit_name, engine, project_root)

    if as_json:
        payload = {
            label.lower().replace(" ", "_").replace("-", "_"): value
            for label, value in fields}
        payload["state"] = {axis: cur for axis, cur, _w, _c in (rows or [])}
        print(_json.dumps(payload, indent=2))
        return 0

    _print_entity_card(f"Kit '{kit_name}' -- identity card:", fields)
    if rows:
        print()
        print("Current state:")
        _print_axis_rows(rows)
    return 0


def _cmd_kit_status(kits, engine=None, args=None, project_root=None):
    """Show active kits summary -- or, with ``args.name``, one kit's per-axis state.

    Virtual kits report 'alias(es)' instead of 'tool(s)' to reflect
    the distinct nature of the count — and avoid the double-counting
    confusion raised by R3b validation (virtual kit with 4 aliases
    + canonical kit with 12 tools don't sum to 16 unique tools because
    the 4 aliases REFER TO 4 of those canonical tools). See the
    'alias discoverability gap' note in private/claude/notes/cli/.

    The active set honors the user config (``active_kits`` / ``disabled_kits``)
    so the summary matches ``dz kit list`` — without the engine's config,
    ``get_active_kits`` falls back to its legacy all-active default.
    """
    if args is not None and getattr(args, "name", None):
        return render_kit_status_detail(args.name, engine, project_root)
    user_config = (
        engine._get_user_config()
        if engine is not None and hasattr(engine, "_get_user_config")
        else None
    )
    active = get_active_kits(kits, user_config=user_config)
    print(f"Active kits: {len(active)}")
    for kit in active:
        # Prefer _kit_name (set from filename in registry pointer) over kit["name"]
        # (which may reflect an embedded sub-kit's own inner name, e.g. wtf's
        # own core.kit.json declares name="core" but is imported as "wtf").
        # See #45.
        name = kit.kit_name or kit.name
        tool_count = len(kit.tools or [])
        label = "alias(es)" if kit.virtual else "tool(s)"
        print(f"  {name}: {tool_count} {label}")
    return 0


def _cmd_version():
    """Show version info (alternate to --version flag)."""
    print(f"dazzlecmd {DISPLAY_VERSION} ({__version__})")
    return 0


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


def _register_in_kit(project_root, kit_name, namespace, tool_name):
    """Add a tool reference to a kit's tools array.

    Writes to the kit's **in-repo manifest** (``projects/<kit>/.kit.json``)
    when present, falling back to the registry pointer
    (``kits/<kit>.kit.json``) only for registry-only kits.

    Why in-repo manifest first: ``loader.discover_kits`` merges in-repo
    fields OVER the registry pointer when both exist (loader.py:55-71).
    The in-repo manifest's ``tools`` list authoritatively overrides
    whatever the registry pointer carries. Pre-fix, this function wrote
    only to the registry pointer, which the merge silently ignored for
    every kit with an in-repo manifest (``core``, ``dazzletools``, ...).
    The registered entry never surfaced in ``dz list`` because the
    in-repo manifest's untouched ``tools`` list won the merge.
    """
    in_repo_manifest = os.path.join(
        project_root, "projects", kit_name, ".kit.json"
    )
    registry_pointer = os.path.join(
        project_root, "kits", f"{kit_name}.kit.json"
    )

    # Prefer in-repo manifest (authoritative when present).
    if os.path.isfile(in_repo_manifest):
        target = in_repo_manifest
        target_label = f"{kit_name} (in-repo manifest)"
    elif os.path.isfile(registry_pointer):
        target = registry_pointer
        target_label = f"{kit_name} (registry pointer)"
    else:
        print(
            f"  Warning: Kit '{kit_name}' not found (looked at "
            f"'{in_repo_manifest}' and '{registry_pointer}')",
            file=sys.stderr,
        )
        return

    try:
        with open(target, "r", encoding="utf-8") as f:
            kit = json.load(f)

        qualified = f"{namespace}:{tool_name}"
        if qualified not in kit.get("tools", []):
            kit.setdefault("tools", []).append(qualified)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(kit, f, indent=4)
                f.write("\n")
            print(f"  Registered in kit: {target_label}")
        else:
            print(f"  Already in kit: {target_label}")
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Warning: Could not update kit: {exc}", file=sys.stderr)


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


def _resolve_new_defaults(engine):
    """Read the user config's ``new`` section and return a defaults dict.

    Precedence applied at call site is: CLI flag > config > built-in.
    This helper returns the config layer; callers fall back to built-ins.
    """
    if engine is None:
        return {}
    try:
        cfg = engine._get_config_dict("new") or {}
    except Exception:
        cfg = {}
    return cfg if isinstance(cfg, dict) else {}


def _find_templates_root():
    """Locate the templates directory shipped with dazzlecmd-lib.

    Prefers the lib package (installed or editable). Falls back to a
    local ``templates/`` next to this module for the legacy single-repo
    layout.
    """
    import dazzlecmd_lib
    lib_dir = os.path.dirname(dazzlecmd_lib.__file__)
    template_dir = os.path.join(lib_dir, "templates")
    if os.path.isdir(template_dir):
        return template_dir
    return os.path.join(os.path.dirname(__file__), "templates")


def _available_languages(templates_root):
    """Return the sorted list of language template directory names.

    Filters out overlay directories (``__full__`` etc.) and any
    non-directory entries.
    """
    if not os.path.isdir(templates_root):
        return []
    return sorted(
        entry for entry in os.listdir(templates_root)
        if os.path.isdir(os.path.join(templates_root, entry))
        and not entry.startswith("__")
    )


def _substitute_placeholders(text, placeholders):
    """Replace ``{key}`` markers in text with their placeholder values.

    Order matters when one placeholder is a substring of another. The
    placeholder set is small (~5 entries) and stable; iterate the dict
    and replace each in turn.
    """
    for key, value in placeholders.items():
        text = text.replace("{" + key + "}", value)
    return text


def _copy_template_tree(src_dir, dest_dir, placeholders):
    """Recursively copy ``src_dir`` into ``dest_dir`` with placeholder
    substitution applied to file contents AND filenames.

    Files ending in ``.tmpl`` have the suffix stripped on output. Files
    without the suffix are copied verbatim (no substitution). Subdirectory
    names also receive placeholder substitution so e.g. ``src/`` stays
    ``src/`` but a hypothetical ``{name}-pkg/`` would be renamed.

    Overlay subdirectories matching ``__*__`` (e.g., ``__full__``) are
    skipped in the recursion -- callers apply them separately.

    Returns the list of relative paths created (for the success message).
    """
    created = []
    for entry in sorted(os.listdir(src_dir)):
        if entry.startswith("__") and entry.endswith("__"):
            continue
        src_path = os.path.join(src_dir, entry)
        dest_entry = _substitute_placeholders(entry, placeholders)
        if os.path.isdir(src_path):
            sub_dest = os.path.join(dest_dir, dest_entry)
            os.makedirs(sub_dest, exist_ok=True)
            sub_created = _copy_template_tree(src_path, sub_dest, placeholders)
            created.extend(os.path.join(dest_entry, p) for p in sub_created)
            continue
        # File
        if dest_entry.endswith(".tmpl"):
            dest_entry = dest_entry[:-len(".tmpl")]
            with open(src_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = _substitute_placeholders(content, placeholders)
            dest_path = os.path.join(dest_dir, dest_entry)
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            import shutil
            dest_path = os.path.join(dest_dir, dest_entry)
            shutil.copy2(src_path, dest_path)
        created.append(dest_entry)
    return created


def _cmd_new_tool(args, project_root, engine=None):
    """Create a new tool project with progressive scaffolding.

    Per-language template dispatch (v0.7.44, 4b-T3 + 4d-3): the
    ``--language`` flag (with config and built-in fallbacks) selects a
    template directory under
    ``packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/<language>/``.
    The whole tree is copied to the new tool's directory with placeholder
    substitution. For Python, ``--full`` additionally applies the
    ``python/__full__/`` overlay (README + test stub).
    """
    new_defaults = _resolve_new_defaults(engine)

    name = args.name
    namespace = (
        args.namespace
        or new_defaults.get("default_namespace")
        or "dazzletools"
    )
    description = args.description or f"A new dazzlecmd tool: {name}"
    long_description = getattr(args, "long_description", "") or ""
    language = (
        args.language
        or new_defaults.get("default_language")
        or "python"
    )

    templates_root = _find_templates_root()
    available = _available_languages(templates_root)
    if language not in available:
        source = (
            "config 'new.default_language'"
            if args.language is None and new_defaults.get("default_language")
            else "--language flag"
        )
        avail_str = ", ".join(available) if available else "(none found)"
        print(
            f"Error: language {language!r} not supported (from {source}).\n"
            f"Available: {avail_str}.",
            file=sys.stderr,
        )
        return 2

    projects_dir = os.path.join(project_root, "projects", namespace)
    tool_dir = os.path.join(projects_dir, name)

    if os.path.exists(tool_dir):
        if args.simple or args.full:
            return _layer_extras(tool_dir, name, args)
        print(f"Error: Project '{namespace}/{name}' already exists at {tool_dir}")
        return 1

    os.makedirs(tool_dir, exist_ok=True)

    placeholders = {
        "name": name,
        "name_underscore": name.replace("-", "_"),
        "description": description,
        "long_description": long_description,
        "namespace": namespace,
    }

    lang_template_dir = os.path.join(templates_root, language)
    created = _copy_template_tree(lang_template_dir, tool_dir, placeholders)

    # Python --full overlay: copy the python/__full__/ tree as well.
    if args.full and language == "python":
        full_dir = os.path.join(lang_template_dir, "__full__")
        if os.path.isdir(full_dir):
            extra = _copy_template_tree(full_dir, tool_dir, placeholders)
            created.extend(extra)

    print(f"Created project: {namespace}/{name}")
    print(f"  {tool_dir}/")
    for rel_path in created:
        print(f"  - {rel_path}")

    # Universal --simple/--full extras (TODO.md, NOTES.md, ROADMAP.md, etc.)
    if args.simple or args.full:
        _layer_extras(tool_dir, name, args)

    kit_name = getattr(args, "kit", None)
    if kit_name:
        _register_in_kit(project_root, kit_name, namespace, name)

    return 0


def _cmd_new_kit(args, project_root):
    """``dz new kit <name>`` -- create a LOCAL kit inside this aggregator.

    A kit is a directory of tools registered into the parent's discovery
    (Tier 2 synthesis OQ-A2: semantically distinct from an aggregator, which
    has its own dispatch). Creates ``projects/<name>/.kit.json`` (the in-tree
    manifest that travels with the kit if it ever migrates) and
    ``kits/<name>.kit.json`` (the registry pointer controlling activation).
    """
    name = args.name.strip().lower()
    if not re.match(r"^[a-z][a-z0-9_-]*$", name):
        print(f"Error: invalid kit name '{args.name}' (use lowercase letters, "
              "digits, '-', '_').", file=sys.stderr)
        return 1

    kit_dir = os.path.join(project_root, "projects", name)
    kit_manifest = os.path.join(kit_dir, ".kit.json")
    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")
    for existing in (kit_manifest, registry_path):
        if os.path.exists(existing):
            print(f"Error: {existing} already exists.", file=sys.stderr)
            return 1

    os.makedirs(kit_dir, exist_ok=True)
    manifest = {
        "name": name,
        "version": "0.1.0",
        "description": args.description or f"{name} kit",
        "tools_dir": ".",
        "manifest": ".dazzlecmd.json",
        "tools": [],
    }
    with open(kit_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
        f.write("\n")

    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    # OQ-J: warn against cross-embedding loops until #65's display dedup ships
    # everywhere. (Comment field, not a schema key the loader acts on.)
    registry = {
        "name": name,
        "always_active": False,
        "_note": "Registry pointer: controls activation only. Do not point a "
                 "parent aggregator back at a child that embeds this one.",
    }
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4)
        f.write("\n")

    created = [os.path.relpath(kit_manifest, project_root),
               os.path.relpath(registry_path, project_root)]

    if getattr(args, "with_starter", False):
        rc = _scaffold_starter_tool(project_root, kit=name)
        if rc == 0:
            manifest["tools"].append(f"{name}:hello")
            with open(kit_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=4)
                f.write("\n")
            created.append(os.path.join("projects", name, "hello", ""))

    print(f"Created kit '{name}':")
    for path in created:
        print(f"  {path}")
    print(f"\nEnable it with: dz kit enable {name}")
    return 0


def _scaffold_starter_tool(project_root, kit, tool_name="hello"):
    """Generate a starter 'hello' tool from the python template into
    ``projects/<kit>/<tool_name>/``. Returns 0/1."""
    templates_root = _find_templates_root()
    src = os.path.join(templates_root, "python")
    if not os.path.isdir(src):
        print("Warning: python template not found; skipping starter tool.",
              file=sys.stderr)
        return 1
    dest = os.path.join(project_root, "projects", kit, tool_name)
    os.makedirs(dest, exist_ok=True)
    placeholders = {
        "name": tool_name,
        "name_underscore": tool_name.replace("-", "_"),
        "namespace": kit,
        "description": "Starter tool -- replace me",
        "long_description": "",
    }
    _copy_template_tree(src, dest, placeholders)
    return 0


# --- `--with` composable scaffolding components (4d-5, Tier-2 synthesis) ----
#
# Each component is a function (target_dir, placeholders) -> list-of-added
# (relative paths), raising ComponentUnavailable with a reason when it cannot
# apply. Composition is BEST-EFFORT (OQ-D1): a failed component warns and the
# rest continue; a summary prints at the end. `common`/`template` (RepoKit,
# network/external) land in 4d-6 -- until then they report unavailable with
# the install pointer rather than failing silently.

class _ComponentUnavailable(Exception):
    pass


def _with_copy_component(component_dir_name):
    """An applier that copies templates/__with__/<name>/ into the target."""
    def _apply(target_dir, placeholders, defaults):
        src = os.path.join(_find_templates_root(), "__with__", component_dir_name)
        if not os.path.isdir(src):
            raise _ComponentUnavailable(f"template dir missing: {src}")
        return _copy_template_tree(src, target_dir, placeholders)
    return _apply


_REPOKIT_COMMON_URL_DEFAULT = (
    "https://github.com/DazzleTools/git-repokit-common.git")
_REPOKIT_TEMPLATE_URL_DEFAULT = (
    "https://github.com/DazzleTools/git-repokit-template.git")
_GIT_SUBTREE_TIMEOUT = 180  # network fetch of a whole repo


def _run_git(args_list, cwd, timeout):
    """Run git, return (rc, combined_output). Missing git -> (127, message).

    Runs with a sanitized environment (repo-location GIT_* vars stripped) so
    the repository is always resolved from ``cwd`` -- never from ambient hook
    state (git exports GIT_DIR to hook subprocesses, which would silently
    point every call here at the HOOK'S repository).
    """
    import subprocess as _sp
    from dazzlecmd_lib.mode import sanitized_git_env
    try:
        r = _sp.run(["git"] + args_list, cwd=cwd, capture_output=True,
                    text=True, timeout=timeout, env=sanitized_git_env())
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, "git not found on PATH"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _with_common(target_dir, placeholders, defaults):
    """`--with common`: the git-repokit-common subtree at scripts/ (4d-6).

    `git subtree add` requires a repo with at least one commit; a fresh
    scaffold has neither, so this initializes git + an initial commit first
    (clearly announced -- it is the documented next step anyway). Source URL:
    config `new.repokit_common_url` > the DazzleTools default. RepoKit
    unavailable (no git / network / bad URL) raises ComponentUnavailable with
    the manual command (OQ-G1: hint and proceed, never block).
    """
    url = (defaults or {}).get("repokit_common_url") or _REPOKIT_COMMON_URL_DEFAULT
    if os.path.isdir(os.path.join(target_dir, "scripts")):
        raise _ComponentUnavailable("scripts/ already exists in the target")
    # The target must be its OWN repo toplevel. Ambient rev-parse discovery
    # walks up to any ancestor repo (e.g. a scaffold under the user's HOME,
    # which is itself a git repo on this layout) -- subtree-ing into THAT
    # would pollute the wrong repository. If the discovered toplevel is not
    # the target itself, initialize a fresh (nested-safe) repo at the target.
    rc, _top = _run_git(["rev-parse", "--show-toplevel"], target_dir, 10)
    _is_own_repo = (
        rc == 0 and _top.strip()
        and os.path.normcase(os.path.realpath(_top.strip()))
        == os.path.normcase(os.path.realpath(target_dir))
    )
    if not _is_own_repo:
        # core.autocrlf=false locally: on Windows a global autocrlf=true
        # rewrites line endings right after the commit, leaving the tree
        # "modified" and making git-subtree refuse ("working tree has
        # modifications"). The generated scaffold is LF on disk already.
        for cmd in (["init", "-q"], ["config", "core.autocrlf", "false"],
                    ["add", "-A"],
                    ["commit", "-q", "-m", "Initial scaffold"]):
            rc, out = _run_git(cmd, target_dir, 30)
            if rc != 0:
                raise _ComponentUnavailable(
                    f"could not initialize git in the target ({out}); "
                    f"git init + commit, then: git subtree add "
                    f"--prefix=scripts {url} main --squash")
        print("  [with:common] initialized git repository (subtree requires "
              "a commit)")
    # git-subtree insists on running from the EXACT toplevel string (Windows
    # temp-path normalization can differ from the cwd we hold) -- resolve it.
    rc, toplevel = _run_git(["rev-parse", "--show-toplevel"], target_dir, 10)
    run_cwd = toplevel.strip() if rc == 0 and toplevel.strip() else target_dir
    # Refresh the stat cache first: files written milliseconds before the
    # commit leave racy-git index entries, and subtree's diff-index check
    # misreads them as "working tree has modifications".
    _run_git(["status", "--porcelain"], run_cwd, 10)
    rc, out = _run_git(["subtree", "add", "--prefix=scripts", url,
                        "main", "--squash"], run_cwd, _GIT_SUBTREE_TIMEOUT)
    if rc != 0:
        tail = out.splitlines()[-1] if out else "unknown"
        raise _ComponentUnavailable(
            f"subtree add failed ({tail}); retry later with: "
            f"git subtree add --prefix=scripts {url} main --squash")
    print("  [with:common] run scripts/install-hooks to enable the git hooks")
    return ["scripts/ (git-repokit-common subtree)"]


def _with_template(target_dir, placeholders, defaults):
    """`--with template`: project-shape files from git-repokit-template.

    Source resolution (OQ-D2, local-first): config `new.repokit_template_path`
    if set + valid -> copy with substitution; else shallow-clone the template
    URL; else the lib-bundled minimal fallback (README exists from the
    scaffold; this adds LICENSE/CONTRIBUTING stubs) with a clear
    "fallback minimal" warning (OQ-G2). Existing files are NEVER overwritten
    (the scaffold's README/.gitignore win).
    """
    import shutil as _sh
    import tempfile as _tf
    d = defaults or {}

    def _copy_no_clobber(src_root):
        added = []
        for entry in sorted(os.listdir(src_root)):
            if entry in (".git", "__pycache__"):
                continue
            sp = os.path.join(src_root, entry)
            dest_name = entry[:-len(".tmpl")] if entry.endswith(".tmpl") else entry
            dp = os.path.join(target_dir, dest_name)
            if os.path.exists(dp):
                continue  # never clobber scaffold output
            if os.path.isdir(sp):
                _sh.copytree(sp, dp)
                added.append(dest_name + "/")
            else:
                with open(sp, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                content = _substitute_placeholders(content, placeholders)
                with open(dp, "w", encoding="utf-8") as f:
                    f.write(content)
                added.append(dest_name)
        return added

    local = d.get("repokit_template_path")
    if local and os.path.isdir(local):
        added = _copy_no_clobber(local)
        print(f"  [with:template] source: local path {local}")
        return added

    url = d.get("repokit_template_url") or _REPOKIT_TEMPLATE_URL_DEFAULT
    tmp = _tf.mkdtemp(prefix="repokit_tmpl_")
    try:
        rc, _out = _run_git(["clone", "--depth", "1", url, tmp],
                            target_dir, _GIT_SUBTREE_TIMEOUT)
        if rc == 0:
            added = _copy_no_clobber(tmp)
            print(f"  [with:template] source: {url}")
            return added
    finally:
        # Windows: the clone's read-only .git objects make a plain rmtree
        # fail silently (ignore_errors) and leak the temp dir -- chmod+retry.
        def _on_rm_error(func, path, _exc):
            import stat as _stat
            try:
                os.chmod(path, _stat.S_IWRITE)
                func(path)
            except OSError:
                pass
        _sh.rmtree(tmp, onerror=_on_rm_error)

    # Bundled minimal fallback (OQ-G2)
    fallback = os.path.join(_find_templates_root(), "repokit_fallback")
    if not os.path.isdir(fallback):
        raise _ComponentUnavailable(
            f"template repo unreachable ({url}) and no bundled fallback")
    added = _copy_no_clobber(fallback)
    print("  [with:template] WARNING: template repo unreachable -- used the "
          "bundled FALLBACK-MINIMAL stubs; replace with the real "
          "git-repokit-template when available")
    return added


_WITH_COMPONENTS = {
    "docker-test": _with_copy_component("docker-test"),
    "docker-deploy": _with_copy_component("docker-deploy"),
    "ci": _with_copy_component("ci"),
    "common": _with_common,
    "template": _with_template,
}
_WITH_ALL = ("common", "template", "docker-test", "docker-deploy", "ci")


def _parse_with_spec(spec):
    """Parse a --with comma-list; expand `all`; reject unknown names."""
    requested = [c.strip().lower() for c in (spec or "").split(",") if c.strip()]
    expanded = []
    for c in requested:
        for name in (_WITH_ALL if c == "all" else (c,)):
            if name not in _WITH_COMPONENTS:
                raise ValueError(
                    f"unknown --with component '{c}' "
                    f"(valid: {', '.join([*_WITH_COMPONENTS, 'all'])})")
            if name not in expanded:
                expanded.append(name)
    return expanded


def _apply_with_components(target_dir, components, placeholders, defaults=None):
    """Apply components best-effort; print the summary; return 0 always
    (composition failures are warnings, not scaffold failures -- OQ-D1)."""
    ok, skipped = [], []
    for name in components:
        try:
            added = _WITH_COMPONENTS[name](target_dir, placeholders, defaults)
            ok.append(name)
            for rel in added:
                print(f"  [with:{name}] {rel}")
        except _ComponentUnavailable as exc:
            skipped.append((name, str(exc)))
        except Exception as exc:  # best-effort: never kill the scaffold
            skipped.append((name, f"failed: {exc}"))
    if ok or skipped:
        parts = []
        if ok:
            parts.append("ok: " + ", ".join(ok))
        if skipped:
            parts.append("skipped: " + "; ".join(f"{n} ({r})" for n, r in skipped))
        print(f"\n--with summary: {' | '.join(parts)}")
    return 0


def _cmd_new_aggregator(args, engine=None):
    """``dz new aggregator <name>`` -- scaffold a STANDALONE aggregator project.

    Always standalone (Tier 2 synthesis OQ-A2): own pyproject.toml, console
    entry point, aggregator.json, tools dir, kit registry, smoke test. The
    generated cli.py is the canonical thin dazzlecmd-lib consumer (the wtf
    pattern): ``AggregatorEngine.from_project(...)`` + ``engine.run()``, with
    a commented ``nest_all_under`` stub for when #47 ships (OQ-E: manual
    uncomment, no auto-rewrites of user code).

    Defaults resolve CLI flag > user config ``new`` section > built-in (4d-7).
    The target directory is ``./<name>`` relative to the CURRENT directory --
    a new project beside wherever you are, never inside dazzlecmd's tree.
    """
    name = args.name.strip()
    if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", name):
        print(f"Error: invalid project name '{args.name}'.", file=sys.stderr)
        return 1

    new_defaults = _resolve_new_defaults(engine)
    command = args.command or name.lower().replace("_", "-")
    tools_dir = args.tools_dir or new_defaults.get("tools_dir") or "projects"
    manifest = args.manifest or new_defaults.get("manifest") or ".dazzlecmd.json"
    description = args.description or f"{name} -- a dazzlecmd-lib aggregator"

    try:
        with_components = _parse_with_spec(getattr(args, "with_components", None))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    target = os.path.abspath(name)
    if os.path.exists(target):
        print(f"Error: {target} already exists.", file=sys.stderr)
        return 1

    # Inside-an-aggregator guard: the target is CWD-relative, so running this
    # from within an existing aggregator's tree nests the new standalone
    # project inside that repo (untracked litter + a stray aggregator.json).
    # Never destructive (the exists-check above refuses collisions), and
    # occasionally intentional -- so warn loudly and proceed.
    from dazzlecmd_lib.aggregator_config import find_aggregator_root
    enclosing = find_aggregator_root(os.getcwd())
    if enclosing:
        print(
            f"Note: you are inside the aggregator at {enclosing} -- the new "
            f"standalone project will be created NESTED in that repo's "
            f"working tree at {target} (it will show up untracked there). "
            f"cd elsewhere first if you wanted an independent sibling project.",
            file=sys.stderr,
        )

    templates_root = _find_templates_root()
    src = os.path.join(templates_root, "aggregator")
    if not os.path.isdir(src):
        print(f"Error: aggregator template not found at {src}.", file=sys.stderr)
        return 1

    from dazzlecmd_lib._version import __version__ as _lib_version
    placeholders = {
        "name": name,
        "name_underscore": name.lower().replace("-", "_"),
        "command": command,
        "description": description,
        "tools_dir": tools_dir,
        "manifest": manifest,
        "lib_min_version": _lib_version,
    }

    os.makedirs(target)
    created = _copy_template_tree(src, target, placeholders)

    # The discovery directories (template trees can't carry empty dirs).
    os.makedirs(os.path.join(target, tools_dir), exist_ok=True)
    os.makedirs(os.path.join(target, "kits"), exist_ok=True)

    if getattr(args, "with_starter", False):
        core_dir = os.path.join(target, tools_dir, "core")
        os.makedirs(core_dir, exist_ok=True)
        with open(os.path.join(core_dir, ".kit.json"), "w", encoding="utf-8") as f:
            json.dump({
                "name": "core", "version": "0.1.0",
                "description": f"Core tools for {name}",
                "tools_dir": ".", "manifest": manifest,
                "tools": ["core:hello"],
            }, f, indent=4)
            f.write("\n")
        with open(os.path.join(target, "kits", "core.kit.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"name": "core", "always_active": True}, f, indent=4)
            f.write("\n")
        # Reuse the python tool template for the hello tool (tools_dir-aware).
        hello_root = os.path.join(target, tools_dir, "core", "hello")
        os.makedirs(hello_root, exist_ok=True)
        py_src = os.path.join(templates_root, "python")
        if os.path.isdir(py_src):
            _copy_template_tree(py_src, hello_root, {
                "name": "hello", "name_underscore": "hello",
                "namespace": "core",
                "description": "Starter tool -- replace me",
                "long_description": "",
            })
            created.append(os.path.join(tools_dir, "core", "hello", ""))

    if with_components:
        _apply_with_components(target, with_components, placeholders,
                               defaults=new_defaults)

    print(f"Created aggregator '{name}' at {target}")
    for path in sorted(created):
        print(f"  {path}")
    print(
        f"\nNext steps:\n"
        f"  cd {name}\n"
        f"  pip install -e .\n"
        f"  {command} list\n"
        f"  git init && git add -A   # version it (RepoKit integration: --with common, later)"
    )
    return 0


def _layer_extras(tool_dir, name, args):
    """Add extra files to an existing project."""
    added = []

    if args.simple or args.full:
        # --simple: add TODO.md and NOTES.md
        for filename in ["TODO.md", "NOTES.md"]:
            filepath = os.path.join(tool_dir, filename)
            if not os.path.exists(filepath):
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"# {filename.replace('.md', '')} - {name}\n\n")
                added.append(filename)

    if args.full:
        # --full: add ROADMAP.md, private/claude/, tests/
        roadmap = os.path.join(tool_dir, "ROADMAP.md")
        if not os.path.exists(roadmap):
            with open(roadmap, "w", encoding="utf-8") as f:
                f.write(f"# Roadmap - {name}\n\n## Planned\n\n## In Progress\n\n## Done\n\n")
            added.append("ROADMAP.md")

        for subdir in ["private/claude", "tests"]:
            dirpath = os.path.join(tool_dir, subdir)
            if not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
                added.append(f"{subdir}/")

    if added:
        print(f"  Added: {', '.join(added)}")
    return 0


#
# Phase 3 command handlers: kit enable/disable/focus/reset/favorite/
# unfavorite/silence/unsilence/shadow/unshadow/silenced/add and dz tree.
# All write-path handlers take an ``engine`` parameter to call
# ``engine._write_user_config(updates)``.
#


def _kit_exists(kits, name):
    """Return True if a kit with the given name is discovered."""
    return any(
        (k.kit_name or k.name) == name for k in kits
    )


def _cmd_kit_enable(args, engine):
    """Enable a kit: add to active_kits, drop from disabled_kits.

    The activation 'enable' transition -- a lateral (reversible) toggle run through
    ActivationContext (the activation analog of the visibility hide/expose contexts).
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # Warn if the kit doesn't exist on disk (informational -- the toggle still
    # applies, so it takes effect if the kit becomes available later).
    if engine.kits and not _kit_exists(engine.kits, name):
        print(
            f"Warning: kit '{name}' not found among discovered kits. "
            f"Change will apply if the kit becomes available later.",
            file=sys.stderr,
        )

    from dazzlecmd_lib.contexts import ActivationContext
    ActivationContext(engine).enable(name)
    print(f"Enabled kit: {name}")
    return 0


def _cmd_kit_disable(args, engine):
    """Disable a kit: add to disabled_kits, drop from active_kits.

    The activation 'disable' transition -- the lateral inverse of enable, run
    through ActivationContext.
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    if engine.kits and not _kit_exists(engine.kits, name):
        print(
            f"Warning: kit '{name}' not found among discovered kits.",
            file=sys.stderr,
        )

    from dazzlecmd_lib.contexts import ActivationContext
    ActivationContext(engine).disable(name)
    print(f"Disabled kit: {name}")
    return 0


def _cmd_kit_focus(args, kits, engine):
    """Enable the named kit and disable all others (except always_active)."""
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    if not _kit_exists(kits, name):
        print(f"Error: kit '{name}' not found.", file=sys.stderr)
        return 1

    new_active = [name]
    new_disabled = []
    preserved = []
    for kit in kits:
        kname = kit.kit_name or kit.name
        if kname == name:
            continue
        if kit.always_active:
            preserved.append(kname)
            continue
        new_disabled.append(kname)

    engine._write_user_config({
        "active_kits": new_active,
        "disabled_kits": new_disabled,
    })
    print(f"Focused on '{name}'.")
    if new_disabled:
        print(f"  Disabled: {', '.join(new_disabled)}")
    if preserved:
        print(f"  Preserved (always_active): {', '.join(preserved)}")
    return 0


def _cmd_kit_reset(args, engine):
    """Wipe the user config after confirmation."""
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    path = engine._config_path()
    if not os.path.isfile(path):
        print("No config to reset.")
        return 0

    if not args.yes:
        print(f"This will delete {path} and clear all kit preferences.")
        try:
            answer = input("Continue? [y/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 1

    try:
        os.unlink(path)
    except OSError as exc:
        print(f"Error: could not remove {path}: {exc}", file=sys.stderr)
        return 1

    # Invalidate caches
    engine._config_cache = None
    engine._precedence_cache = None
    print("Config cleared.")
    return 0


def _cmd_kit_favorite(args, engine):
    """Set a favorite binding: short name -> FQCN.

    With ``--migrate-stale`` (and no positional args), enters the
    interactive stale-favorite migration flow instead. See
    :func:`_cmd_kit_favorite_migrate_stale`.
    """
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    if getattr(args, "migrate_stale", False):
        if args.short is not None or args.fqcn is not None:
            print(
                "Error: --migrate-stale takes no positional arguments.",
                file=sys.stderr,
            )
            return 1
        return _cmd_kit_favorite_migrate_stale(engine)

    if args.short is None or args.fqcn is None:
        print(
            "Error: 'dz kit favorite' requires <short> <fqcn> positional "
            "args, or use --migrate-stale.",
            file=sys.stderr,
        )
        return 1

    short = args.short
    fqcn = args.fqcn

    # Reject reserved command names
    reserved = engine.reserved_commands
    if short in reserved:
        print(
            f"Error: '{short}' is a reserved command name and cannot "
            f"be set as a favorite.",
            file=sys.stderr,
        )
        return 1

    # Warn if the target FQCN isn't discovered. Accepts either a
    # canonical FQCN or a virtual-kit alias FQCN -- both are valid
    # favorite targets (see FQCNIndex.resolve for favorite-on-alias
    # semantics).
    if hasattr(engine, "fqcn_index") and (
        fqcn not in engine.fqcn_index.canonical_index
        and fqcn not in engine.fqcn_index.alias_index
    ):
        print(
            f"Warning: target FQCN '{fqcn}' not found in the current "
            f"discovery. Favorite saved but may be stale.",
            file=sys.stderr,
        )

    config = engine._get_user_config()
    favorites = dict(config.get("favorites") or {})
    favorites[short] = fqcn

    engine._write_user_config({"favorites": favorites})
    print(f"Favorite set: {short} -> {fqcn}")
    return 0


def _suggest_favorite_replacement(short, stale_fqcn, engine):
    """Suggest a likely replacement for a stale favorite, or None.

    Heuristic: if exactly one currently-discovered tool registers ``short``
    as its short name (in ``engine.fqcn_index.short_index``), that's the
    suggestion. Returns its canonical FQCN.

    For ambiguous cases (zero or multiple short-name matches) we return
    None and let the user pick manually -- guessing wrong is worse than
    not guessing.
    """
    if not hasattr(engine, "fqcn_index"):
        return None
    candidates = engine.fqcn_index.short_index.get(short, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def _cmd_kit_favorite_migrate_stale(engine):
    """Interactively migrate stale favorites.

    Walks every favorite in user config, checks whether the target FQCN
    still resolves (matches a canonical OR an alias), and for each stale
    entry prompts the user to remap, drop, or skip. Writes the updated
    favorites map back to user config at the end.

    Non-TTY invocations print the stale list with suggestions and exit
    non-zero -- the migration requires interactive input.
    """
    config = engine._get_user_config()
    favorites = dict(config.get("favorites") or {})

    if not favorites:
        print("No favorites configured.")
        return 0

    canonical_index = (
        engine.fqcn_index.canonical_index
        if hasattr(engine, "fqcn_index") else {}
    )
    alias_index = (
        engine.fqcn_index.alias_index
        if hasattr(engine, "fqcn_index") else {}
    )

    stale = []
    for short, fqcn in favorites.items():
        # Same resolution rule as FQCNIndex.resolve favorite-check:
        # the favorite target must be either a canonical FQCN or an
        # alias FQCN whose canonical target is currently discovered.
        if fqcn in canonical_index:
            continue
        if fqcn in alias_index:
            canonical_target = alias_index[fqcn]
            if canonical_target in canonical_index:
                continue
        stale.append((short, fqcn))

    if not stale:
        print(
            f"No stale favorites. {len(favorites)} favorite(s) all resolve "
            f"correctly."
        )
        return 0

    if not sys.stdin.isatty():
        print(f"Found {len(stale)} stale favorite(s):", file=sys.stderr)
        for short, fqcn in stale:
            suggestion = _suggest_favorite_replacement(short, fqcn, engine)
            if suggestion:
                print(
                    f"  {short} -> {fqcn}  (suggestion: {suggestion})",
                    file=sys.stderr,
                )
            else:
                print(f"  {short} -> {fqcn}", file=sys.stderr)
        print(
            "\nMigration requires an interactive shell. Re-run from a "
            "TTY, or use 'dz kit unfavorite <short>' to drop entries "
            "manually.",
            file=sys.stderr,
        )
        return 1

    print(f"Found {len(stale)} stale favorite(s).\n")
    remapped = 0
    dropped = 0
    skipped = 0

    for short, fqcn in stale:
        suggestion = _suggest_favorite_replacement(short, fqcn, engine)
        print(f"Stale: {short} -> {fqcn}  (target not found)")
        if suggestion:
            print(f"  [r] remap to {suggestion}")
            choices = "r/d/s"
        else:
            print("  (no obvious replacement found)")
            choices = "d/s"
        print("  [d] drop this favorite")
        print("  [s] skip (keep stale)")
        try:
            response = input(f"Choose [{choices}]: ").strip().lower()
        except EOFError:
            response = "s"

        if response == "r" and suggestion:
            favorites[short] = suggestion
            remapped += 1
            print(f"  -> remapped to {suggestion}")
        elif response == "d":
            del favorites[short]
            dropped += 1
            print("  -> dropped")
        else:
            skipped += 1
            print("  -> skipped")
        print()

    if remapped or dropped:
        engine._write_user_config({"favorites": favorites})
    print(
        f"Migration complete: {len(stale)} stale, {remapped} remapped, "
        f"{dropped} dropped, {skipped} skipped."
    )
    return 0


def _cmd_kit_unfavorite(args, engine):
    """Remove a favorite binding."""
    short = args.short
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    favorites = dict(config.get("favorites") or {})
    if short not in favorites:
        print(f"No favorite set for '{short}'.")
        return 0

    del favorites[short]
    engine._write_user_config({"favorites": favorites})
    print(f"Favorite removed: {short}")
    return 0


def _resolve_visibility_target(engine, name):
    """Resolve a user-typed name (short name | FQCN | alias) to
    ``(canonical_fqcn, project)`` via the engine's dispatch-grade resolver.
    Returns ``(name, None)`` when nothing matches -- the caller warns + writes the
    raw input (permissive for not-yet-discovered / pointer-kit tools). Resolving
    here is what makes a short name effective AND keeps C3 uncircumventable."""
    resolver = getattr(engine, "resolve_command", None)
    if resolver is None:
        return name, None
    try:
        project, ctx = resolver(name)
    except Exception:
        return name, None
    if project is None:
        return name, None
    canonical = (getattr(ctx, "canonical_fqcn", None)
                 or getattr(project, "fqcn", None) or name)
    return canonical, project


def _is_constitutional_entity(project):
    """True if a resolved project is constitutional / always_active (the C3 gate)."""
    if project is None:
        return False
    if getattr(project, "always_active", False):
        return True
    try:
        from dazzlecmd_lib.core import is_constitutional
    except Exception:
        return False
    return ((getattr(project, "namespace", "") or "") == "core"
            and is_constitutional(getattr(project, "name", "") or ""))


def _cmd_kit_visibility_set(args, engine):
    """The single visibility-toggle handler for all six verbs.

    Resolves the name to its canonical FQCN, looks up the TYPED rung from
    ``KIT_PRESENCE_SPACE`` (``args.level``), enforces C3, and writes via the rung.
    The CLI carries no per-verb config keys or verb tables -- the container
    (the rung object) holds the binding. ``args.direction`` is "suppress" | "restore".
    """
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1
    from dazzlecmd_lib.contexts import KIT_PRESENCE_SPACE
    # KIT_PRESENCE_SPACE is the multi-axis PRODUCT (visibility x activation); the
    # visibility navigator reads its ALIGNED ``axes["visibility"]`` sub-space (the
    # product itself is non-aligned and refuses cross-axis nav -- scale-safety).
    space = KIT_PRESENCE_SPACE.axes["visibility"]

    add = args.direction == "suppress"
    canonical, project = _resolve_visibility_target(engine, args.fqcn)
    if project is None:
        print(f"Note: '{args.fqcn}' didn't resolve to a known tool; recording "
              f"as-is (it takes effect if that tool appears).", file=sys.stderr)

    # --cascade (B2c): apply a SLICE of adjacent presence rungs at once (the
    # general ContinuumSpace apply-mode), instead of just this one rung.
    if getattr(args, "cascade", None) is not None:
        return _apply_visibility_cascade(
            engine, space, canonical, project, args.level, add, args.cascade)

    rung = space.payload_for("visibility", args.level)
    # C3: a constitutional tool may be hidden but never shadowed (the rung
    # declares the policy; the resolved entity supplies the status).
    if add and rung.forbids_constitutional and _is_constitutional_entity(project):
        print(f"Refused: {canonical} is constitutional -- it may be hidden but "
              f"never shadowed (C3: dz depends on it; removing it would break "
              f"dispatch).", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    was = rung.present(config, canonical)
    if add:
        if was:
            print(f"{canonical} is already {rung.level}.")
            return 0
        engine._write_user_config(rung.write(config, canonical, add=True))
        print(f"{rung.level.capitalize()}: {canonical}")
    else:
        if not was:
            print(f"{canonical} was not {rung.level}.")
            return 0
        engine._write_user_config(rung.write(config, canonical, add=False))
        print(f"Restored: {canonical} (no longer {rung.level})")
    return 0


def _resolve_cascade_slice(space, axis, current, spec):
    """Resolve a ``--cascade`` spec to the ordered levels it touches.

    ``@neutral`` (bare) = the current rung + all weaker toward neutral
    (``space.cascade_to_neutral``); ``up``/``down``[``:N``] = toward the warm/cold
    pole, or N rung-steps; ``lo,hi`` = a signed rung-step offset window (``+`` =
    warmer / more present). Raises ``ValueError`` on a malformed spec."""
    if spec == "@neutral":
        return list(space.cascade_to_neutral(axis, current))
    n = len(space.axis(axis).levels())
    if spec in ("up", "down") or spec.startswith("up:") or spec.startswith("down:"):
        direction, _, count = spec.partition(":")
        steps = int(count) if count else n          # bare up/down = to the pole
        if steps < 0:
            raise ValueError("step count must be >= 0")
        if direction == "up":                       # warmer / more present
            return list(space.slice(axis, current, lo=0, hi=steps))
        return list(space.slice(axis, current, lo=-steps, hi=0))   # down = colder
    parts = spec.split(",")
    if len(parts) != 2:
        raise ValueError("expected 'lo,hi' (e.g. -1,2) or 'up|down[:N]'")
    return list(space.slice(axis, current, lo=int(parts[0]), hi=int(parts[1])))


def _apply_visibility_cascade(engine, space, canonical, project, current_level, add, spec):
    """Apply a visibility verb with ``--cascade``: set (suppress) or clear
    (restore) each rung in the resolved slice ADDITIVELY -- it turns the slice's
    rungs on/off and leaves rungs outside the slice untouched. Prints the affected
    rungs; refuses the constitutional cold-pole rung (C3) but applies the rest."""
    axis = "visibility"
    try:
        levels = _resolve_cascade_slice(space, axis, current_level, spec)
    except ValueError as e:
        print(f"Error: bad --cascade value {spec!r}: {e}", file=sys.stderr)
        return 1
    rungs = [r for r in (space.payload_for(axis, lvl) for lvl in levels) if r is not None]
    if not rungs:
        print(f"{canonical}: nothing to cascade (already at neutral).")
        return 0
    desc = ", ".join(f"{r.level} ({r.verb if add else r.unverb})" for r in rungs)
    print(f"Cascade {'suppress' if add else 'restore'} {canonical}: {desc}")
    applied, unchanged, refused = [], [], []
    for r in rungs:
        if add and r.forbids_constitutional and _is_constitutional_entity(project):
            refused.append(r.level)
            continue
        config = engine._get_user_config()
        if r.present(config, canonical) == add:
            unchanged.append(r.level)
            continue
        engine._write_user_config(r.write(config, canonical, add=add))
        applied.append(r.level)
    if applied:
        print(f"  {'set' if add else 'cleared'}: {', '.join(applied)}")
    if unchanged:
        print(f"  unchanged: {', '.join(unchanged)}")
    if refused:
        print(f"  refused (constitutional -- C3): {', '.join(refused)}", file=sys.stderr)
    return 0


def _cmd_kit_visibility_list(engine):
    """Overview: every tool at non-default presence, by rung -- silenced (hint
    off) / hidden (listing off) / shadowed (dispatch off). Replaces the old
    `silenced` query and adds the `hidden` rung it had omitted. Favorites are a
    different axis (short-name resolution) -- see `dz kit favorite`."""
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    silenced = config.get("silenced_hints") or {}
    silenced_tools = silenced.get("tools") or []
    silenced_kits = silenced.get("kits") or []
    hidden = config.get("hidden_tools") or []
    shadowed = config.get("shadowed_tools") or []

    def _rung(label, items):
        print(f"{label}")
        if items:
            for it in items:
                print(f"  - {it}")
        else:
            print("  (none)")

    print("Tool presence (non-default rungs; visible = default, not listed):")
    print()
    _rung("silenced  (rerooting hint off):", silenced_tools)
    if silenced_kits:
        print("  kits:")
        for kit in silenced_kits:
            print(f"    - {kit}")
    print()
    _rung("hidden    (omitted from listings, still dispatchable):", hidden)
    print()
    _rung("shadowed  (removed from dispatch, short name freed):", shadowed)

    if not (silenced_tools or silenced_kits or hidden or shadowed):
        print()
        print("Everything is fully present. Adjust with "
              "'dz kit visibility silence|hide|shadow <fqcn>'.")
    return 0


def _cmd_kit_visibility_status(args, engine):
    """Show a tool's current presence level + both neighbour moves -- the
    KIT_PRESENCE_SPACE navigator. Reads the TYPED rungs (no verb tables): the
    current channels via each rung's ``present``, the moves via the neighbour
    rungs' ``verb``/``unverb``. Labels are bound to this surface's frame
    ("visibility" reads warm = visible), so it says less/more visible -- the
    space's colder/warmer is framing-neutral, the surface names the direction."""
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1
    from dazzlecmd_lib.contexts import KIT_PRESENCE_SPACE, level_for_channels

    # KIT_PRESENCE_SPACE is the multi-axis PRODUCT (visibility x activation); read
    # its ALIGNED ``axes["visibility"]`` sub-space for the navigator (the product
    # itself refuses cross-axis nav, so read the sub-space -- scale-safety).
    vis = KIT_PRESENCE_SPACE.axes["visibility"]
    canonical, project = _resolve_visibility_target(engine, args.fqcn)
    config = engine._get_user_config()

    # Current channels, read THROUGH the typed rungs (no hardcoded config keys).
    suppressed = set()
    for lvl in ("silenced", "hidden", "shadowed"):
        rung = vis.payload_for("visibility", lvl)
        if rung is not None and rung.present(config, canonical):
            suppressed.add(rung.channel)
    level = level_for_channels(suppressed)  # visible | silenced | hidden | shadowed

    print(f"{canonical}")
    print(f"  presence: {level}")
    colder = vis.colder_than("visibility", level)
    warmer = vis.warmer_than("visibility", level)
    if colder:
        reach = vis.payload_for("visibility", colder[1])
        # C3-aware: don't recommend a move the surface will refuse. A
        # constitutional tool may be hidden but never shadowed, so at `hidden`
        # the colder rung is unreachable -- say so instead of suggesting it.
        if reach.forbids_constitutional and _is_constitutional_entity(project):
            print(f"  less visible -> (none: {canonical} is constitutional -- "
                  f"'{reach.verb}' refused by C3; {level} is the max veil)")
        else:
            print(f"  less visible -> dz kit visibility {reach.verb} {canonical}")
    else:
        print("  less visible -> (already least visible: shadowed)")
    if warmer:
        leave = vis.payload_for("visibility", level)
        print(f"  more visible -> dz kit visibility {leave.unverb} {canonical}")
    else:
        print("  more visible -> (already fully visible)")
    return 0


def _cmd_kit_add(args, project_root, engine):
    """Add a kit from a git URL via submodule."""
    import subprocess as _subprocess
    from urllib.parse import urlparse

    url = args.url
    name = args.name
    branch = args.branch
    shallow = args.shallow

    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # Derive name from URL if not provided
    if not name:
        parsed = urlparse(url)
        tail = parsed.path.rstrip("/").split("/")[-1]
        name = tail[:-4] if tail.endswith(".git") else tail
        # Strip common prefixes like "dazzle-" or "wtf-"? Leave as-is.
        if not name:
            print(
                f"Error: could not derive kit name from URL. "
                f"Pass --name explicitly.",
                file=sys.stderr,
            )
            return 1

    target_dir = os.path.join(project_root, "projects", name)
    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")

    if os.path.exists(target_dir):
        print(
            f"Error: projects/{name}/ already exists.",
            file=sys.stderr,
        )
        return 1

    if os.path.exists(registry_path):
        print(
            f"Error: kits/{name}.kit.json already exists.",
            file=sys.stderr,
        )
        return 1

    cmd = ["git", "submodule", "add"]
    if branch:
        cmd += ["-b", branch]
    if shallow:
        cmd += ["--depth", "1"]
    cmd += [url, f"projects/{name}"]

    print(f"Running: {' '.join(cmd)}")
    from dazzlecmd_lib.mode import sanitized_git_env
    try:
        result = _subprocess.run(cmd, cwd=project_root,
                                 env=sanitized_git_env())
    except FileNotFoundError:
        print(
            "Error: git not found. Install git and retry.",
            file=sys.stderr,
        )
        return 1

    if result.returncode != 0:
        print(
            f"Error: git submodule add failed with exit code {result.returncode}",
            file=sys.stderr,
        )
        return result.returncode

    # Create registry pointer
    registry = {
        "name": name,
        "always_active": False,
        "source": url,
    }
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4)
        f.write("\n")

    print(f"Added kit: {name}")
    print(f"  Registry pointer: kits/{name}.kit.json")
    print(f"  Submodule: projects/{name}/")

    # Detect nested aggregator structure
    nested_kits_dir = os.path.join(target_dir, "kits")
    if os.path.isdir(nested_kits_dir):
        print(
            f"  Note: '{name}' appears to be a nested aggregator "
            f"(has its own kits/ directory). Tools will be namespace-remapped "
            f"as '{name}:<namespace>:<tool>'."
        )

    print()
    print(f"Enable with: dz kit enable {name}")
    return 0


def _kit_is_submodule(project_root, name):
    """True if ``projects/<name>`` is registered as a git submodule.

    ``parse_gitmodules()`` is intentionally TOOL-only -- it drops 2-part KIT paths
    (its ``len(parts) != 2`` filter only keeps ``<dir>/<ns>/<tool>``). A KIT lives
    at ``projects/<name>`` (2-part), so kit-level submodule detection reads
    .gitmodules DIRECTLY for a section whose ``path`` == ``projects/<name>``. (The
    original is_submodule bug used the tool-filtered helper, so it never saw a kit
    submodule and the git-untrack never fired.)
    """
    import configparser
    gm = os.path.join(project_root, ".gitmodules")
    if not os.path.isfile(gm):
        return False
    cfg = configparser.ConfigParser()
    try:
        cfg.read(gm, encoding="utf-8")
    except configparser.Error:
        return False
    want = f"projects/{name}"
    for section in cfg.sections():
        if cfg.has_option(section, "path") and cfg.get(section, "path").strip() == want:
            return True
    return False


def _cmd_kit_remove(args, project_root, engine):
    """Remove a kit -- the strong-remove pole of the kit lifecycle.

    Deregisters the kit (git untrack for a submodule + the registry entry, via the
    membership ``ungroup`` verb / KitMembershipContext), safedel-trashes its files
    (recoverable -- NEVER a raw delete), and drops any active/disabled config refs.
    Constitutional / ``always_active`` kits are refused (C3). The weak, keep-as-a-
    pointer form is ``dz kit detach`` (a later slice).
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # Resolve the kit entity (for C3); it may not be loaded -- that's fine.
    kit = None
    for k in (getattr(engine, "kits", []) or []):
        if (getattr(k, "kit_name", None) or getattr(k, "name", None)) == name:
            kit = k
            break

    # C3: constitutional / always_active kits may not be removed.
    if kit is not None and getattr(kit, "always_active", False):
        print(f"Refused: '{name}' is constitutional (always_active) -- it may not be "
              f"removed (C3). Run `dz kit disable {name}` or clear always_active first.",
              file=sys.stderr)
        return 1

    target_dir = os.path.join(project_root, "projects", name)
    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")

    if not os.path.exists(target_dir) and not os.path.exists(registry_path):
        print(f"Error: no kit '{name}' found (neither projects/{name}/ nor "
              f"kits/{name}.kit.json exists).", file=sys.stderr)
        return 1

    # Record the source URL BEFORE any mutation (the re-add hint; crash-safe).
    source = None
    if os.path.exists(registry_path):
        try:
            with open(registry_path, encoding="utf-8") as f:
                source = (json.load(f) or {}).get("source")
        except Exception:  # noqa: BLE001
            source = None

    # Is it a git submodule? (governs the untrack mechanism + the dirty-guard.)
    from dazzlecmd_lib.mode import (
        sanitized_git_env, _check_dirty_tree, _print_dirty_refusal,
    )
    rel = f"projects/{name}"
    # Detect a KIT submodule directly -- parse_gitmodules is TOOL-only and drops
    # 2-part kit paths (the original is_submodule bug used it and always got False).
    is_submodule = _kit_is_submodule(project_root, name)

    # Dirty-tree guard for a submodule worktree -- refuse without --force.
    if is_submodule and os.path.isdir(target_dir):
        dirty = _check_dirty_tree(target_dir)
        if dirty and not getattr(args, "force", False):
            _print_dirty_refusal(name, target_dir, dirty,
                                 getattr(engine, "command", "dz"))
            return 1

    # The plan (shared by --dry-run and the live run).
    plan = []
    if is_submodule:
        plan.append(f"untrack the submodule (git submodule deinit + git rm projects/{name})")
    if os.path.exists(registry_path):
        plan.append(f"deregister kits/{name}.kit.json (membership ungroup)")
    if os.path.isdir(target_dir):
        plan.append(f"safedel projects/{name}/ -> recoverable trash")
    plan.append(f"drop '{name}' from active_kits / disabled_kits")

    if getattr(args, "dry_run", False):
        print(f"Dry run -- `dz kit remove {name}` would:")
        for step in plan:
            print(f"  - {step}")
        return 0

    # Confirmation unless --yes.
    if not getattr(args, "yes", False):
        try:
            resp = input(f"Remove kit '{name}'? Its files go to the recoverable "
                         f"trash. [y/N] ")
        except EOFError:
            resp = ""
        if resp.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 0

    # 1. git untrack for a submodule. Drop the gitlink from the INDEX with --cached
    # (KEEPS the worktree on disk so step 3's safedel can back it up), then remove
    # the .gitmodules + .git/config submodule sections via git's own config editor
    # (format-preserving; touches only the one section). We deliberately do NOT use
    # `git submodule deinit` / `git rm -f`: both empty/delete the worktree, which
    # would destroy the files BEFORE safedel can recover them. `dz kit add` names the
    # submodule by its path, so the section is `submodule.projects/<name>`.
    if is_submodule:
        import subprocess as _subprocess
        import shutil as _shutil
        env = sanitized_git_env()
        sub = f"submodule.{rel}"
        try:
            r = _subprocess.run(["git", "rm", "-f", "--cached", "--", rel],
                                cwd=project_root, env=env)
        except FileNotFoundError:
            print("Error: git not found.", file=sys.stderr)
            return 1
        if r.returncode != 0:
            print(f"Error: `git rm --cached {rel}` failed (exit {r.returncode}); "
                  f"nothing else changed.", file=sys.stderr)
            return r.returncode
        # Surgically drop the .gitmodules section (other submodules untouched), then
        # stage it; clear the .git/config entry (non-zero if absent -- tolerated).
        _subprocess.run(["git", "config", "--file", ".gitmodules",
                         "--remove-section", sub], cwd=project_root, env=env)
        gm = os.path.join(project_root, ".gitmodules")
        if os.path.isfile(gm):
            with open(gm, encoding="utf-8") as _f:
                gm_empty = not _f.read().strip()
            if gm_empty:
                os.remove(gm)   # no submodules left -> drop the empty file
        _subprocess.run(["git", "add", "-A", "--", ".gitmodules"],
                        cwd=project_root, env=env)
        _subprocess.run(["git", "config", "--remove-section", sub],
                        cwd=project_root, env=env)   # .git/config; ok if absent
        # Drop git's cached submodule repo (regenerable from the remote) so a later
        # re-add of the same name doesn't collide. git marks its objects read-only,
        # so clear the bit on error (Windows) rather than silently leaving the cache.
        cached = os.path.join(project_root, ".git", "modules", "projects", name)
        if os.path.isdir(cached):
            import stat as _stat

            def _clear_ro(func, _p, _exc):
                try:
                    os.chmod(_p, _stat.S_IWRITE)
                    func(_p)
                except OSError:
                    pass
            _shutil.rmtree(cached, onerror=_clear_ro)

    # 2. Deregister the registry entry via the membership `ungroup` verb.
    if os.path.exists(registry_path):
        import types as _types
        from dazzlecmd_lib.contexts import KitMembershipContext
        ref = kit if kit is not None else _types.SimpleNamespace(
            name=name, kit_name=name, always_active=False)
        KitMembershipContext(
            project_root, getattr(engine, "kits", []),
            boundary_fqcn=getattr(engine, "command", "dz"),
        ).apply(ref, None, verb="ungroup")

    # 3. safedel the kit dir (recoverable; never a raw delete).
    trashed = False
    if os.path.isdir(target_dir):
        from dazzlecmd_lib.core.safedel import TrashStore
        try:
            trashed = bool(TrashStore().trash([target_dir]).success)
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: safedel of projects/{name}/ failed: {exc}",
                  file=sys.stderr)

    # 4. Deactivate -- drop any dangling active/disabled config refs.
    config = engine._get_user_config()
    active = [k for k in (config.get("active_kits") or []) if k != name]
    disabled = [k for k in (config.get("disabled_kits") or []) if k != name]
    engine._write_user_config({"active_kits": active, "disabled_kits": disabled})

    print(f"Removed kit: {name}")
    if trashed:
        print("  Files -> trash (recover with `dz safedel recover last`)")
    if source:
        print(f"  Re-add with: dz kit add {source}")
    return 0


def _cmd_kit_detach(args, project_root, engine):
    """Detach a kit -- the weak, keep-as-a-pointer pole of the kit lifecycle.

    A ``CompositeTransition`` across two presence axes: write a
    ``pointer:{materialized:true}`` block to the kit's registry (LOADING -> pointer:
    discovery then LISTS the kit but loads none of its tools) AND disable it (the
    implicit loading->activation cascade -- a detached kit is also deactivated). The
    files are KEPT on disk (``materialized:true``); de-materializing is a separate
    step (#80). Re-attach with ``dz kit attach``. Constitutional / ``always_active``
    kits are refused (C3 -- they must stay loaded). The strong, delete-the-files form
    is ``dz kit remove``.
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # Resolve the kit entity (for C3); it may not be loaded -- that's fine.
    kit = None
    for k in (getattr(engine, "kits", []) or []):
        if (getattr(k, "kit_name", None) or getattr(k, "name", None)) == name:
            kit = k
            break

    # C3: constitutional / always_active kits must stay loaded -- refuse.
    if kit is not None and getattr(kit, "always_active", False):
        print(f"Refused: '{name}' is constitutional (always_active) -- it must stay "
              f"loaded and may not be detached (C3). Clear always_active first.",
              file=sys.stderr)
        return 1

    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")
    if not os.path.exists(registry_path):
        print(f"Error: no registered kit '{name}' found (kits/{name}.kit.json does "
              f"not exist). Only registered kits can be detached.", file=sys.stderr)
        return 1

    # The membership context owns the registry substrate -> the pointer block.
    import types as _types
    from dazzlecmd_lib.contexts import KitMembershipContext, ActivationContext
    ref = kit if kit is not None else _types.SimpleNamespace(
        name=name, kit_name=name, always_active=False)
    membership = KitMembershipContext(
        project_root, getattr(engine, "kits", []),
        boundary_fqcn=getattr(engine, "command", "dz"),
    )
    already = membership.pointer_of(ref) is not None

    if getattr(args, "dry_run", False):
        print(f"Dry run -- `dz kit detach {name}` would:")
        if already:
            print("  - (already a pointer; re-affirm the pointer block)")
        print(f"  - write pointer:{{materialized:true}} to kits/{name}.kit.json "
              f"(loading -> pointer; files kept on disk)")
        print(f"  - disable '{name}' (the implicit loading -> activation cascade)")
        return 0

    # 1. LOADING -> pointer: write the pointer block (content kept on disk).
    membership.set_pointer(ref, materialized=True)
    # 2. ACTIVATION -> inactive: the implicit cascade -- a detached kit is disabled.
    ActivationContext(engine).disable(name)

    print(f"Detached kit: {name}")
    print("  Now a pointer (listed, not loaded); files kept on disk.")
    print(f"  Re-attach with: dz kit attach {name}")
    return 0


def _materialize_pointer(project_root, name, source):
    """STUB (#80): fetch a not-yet-materialized pointer kit's content into
    ``projects/<name>/``. This is the deferred fetch tail of the pointer-kit
    lifecycle -- a ``materialized:false`` pointer is "declared but absent" and
    cannot be loaded until its content is fetched. Returns ``(ok, message)``;
    today it always defers (fetch is not yet implemented)."""
    return (False,
            f"'{name}' is an unfetched pointer (materialized:false) -- fetching "
            f"its content (#80) is not yet implemented. "
            + (f"Source: {source}." if source else "No source recorded."))


def _cmd_kit_attach(args, project_root, engine):
    """Attach a kit -- the inverse of ``dz kit detach`` (slice 4 step 3).

    A pointer kit (LOADING=pointer) is loaded again AND enabled: ``clear_pointer``
    (pointer -> loaded -- discovery loads its tools) composed with the activation
    ``enable``. Note the cascade ASYMMETRY: detach's ``loading->inactive`` is FORCED
    (you cannot dispatch what isn't loaded), but attach's ``loading->active`` is a
    FREE choice -- we default to enable (the corrected detach-saga meaning: "upon
    attach -> enable"). A ``materialized:false`` pointer (the #80 not-fetched case)
    needs a fetch first -> the deferred ``_materialize_pointer`` stub. Attaching a
    kit that isn't a pointer is a friendly no-op (use ``dz kit enable`` for that).
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    kit = None
    for k in (getattr(engine, "kits", []) or []):
        if (getattr(k, "kit_name", None) or getattr(k, "name", None)) == name:
            kit = k
            break

    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")
    if not os.path.exists(registry_path):
        print(f"Error: no registered kit '{name}' found (kits/{name}.kit.json does "
              f"not exist).", file=sys.stderr)
        return 1

    import types as _types
    from dazzlecmd_lib.contexts import KitMembershipContext, ActivationContext
    ref = kit if kit is not None else _types.SimpleNamespace(
        name=name, kit_name=name, always_active=False)
    membership = KitMembershipContext(
        project_root, getattr(engine, "kits", []),
        boundary_fqcn=getattr(engine, "command", "dz"),
    )

    pointer = membership.pointer_of(ref)
    if pointer is None:
        # Not a pointer -> nothing to attach (loading is already on).
        print(f"'{name}' is not detached (already loaded); nothing to attach. "
              f"Use `dz kit enable {name}` to activate it.")
        return 0
    materialized = (bool(pointer.get("materialized", True))
                    if isinstance(pointer, dict) else True)

    if getattr(args, "dry_run", False):
        print(f"Dry run -- `dz kit attach {name}` would:")
        if not materialized:
            print(f"  - fetch '{name}' content first (#80 -- not yet implemented)")
        print(f"  - clear the pointer block on kits/{name}.kit.json "
              f"(pointer -> loaded; tools load again)")
        print(f"  - enable '{name}' (attach defaults to active)")
        return 0

    # A not-yet-materialized (#80) pointer needs its content fetched before it can
    # load -- that is the deferred stub; refuse cleanly until it lands.
    if not materialized:
        source = None
        try:
            with open(registry_path, encoding="utf-8") as f:
                source = (json.load(f) or {}).get("source")
        except Exception:  # noqa: BLE001
            source = None
        ok, msg = _materialize_pointer(project_root, name, source)
        if not ok:
            print(f"Cannot attach: {msg}", file=sys.stderr)
            return 1

    # 1. LOADING -> loaded: drop the pointer block so discovery loads its tools.
    membership.clear_pointer(ref)
    # 2. ACTIVATION -> active: attach defaults to enable (the free-choice pole).
    ActivationContext(engine).enable(name)

    print(f"Attached kit: {name}")
    print("  Loaded again and enabled.")
    return 0


def _print_axis_hint(axis):
    pair = next((p for p in LIFECYCLE_PAIRS if p.axis == axis), None)
    if pair:
        print(f"\nChange with `dz kit {axis} {pair.warm}|{pair.cold} <kit>` "
              f"(or the flat alias `dz kit {pair.warm}|{pair.cold} <kit>`).")


def _cmd_kit_management(args, project_root, engine, axis=None):
    """Show kit lifecycle STATE -- the state-on-invoke view (like ``dz kit
    visibility``). ``management`` is the COMPOSED lifecycle axis ({KitOff..KitOn})
    that fuses the activation/loading/membership sub-axes (a kit must be a member to
    load, loaded to activate). ``axis=None`` (``dz kit management [<kit>]``) shows
    each kit's POSITION on that unified continuum; ``axis=<sub-axis>``
    (``dz kit activation|loading|membership``) shows that one sub-axis."""
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1
    import types as _types
    from dazzlecmd_lib.contexts import KitMembershipContext
    membership = KitMembershipContext(
        project_root, getattr(engine, "kits", []),
        boundary_fqcn=getattr(engine, "command", "dz"))
    disabled = set((engine._get_user_config() or {}).get("disabled_kits") or [])
    want = getattr(args, "name", None)

    rows = []
    for k in (getattr(engine, "kits", []) or []):
        kname = getattr(k, "kit_name", None) or getattr(k, "name", None)
        if want and kname != want:
            continue
        always = bool(getattr(k, "always_active", False))
        ref = _types.SimpleNamespace(name=kname, kit_name=kname, always_active=always)
        rows.append({
            "name": kname,
            "always": always,
            "pointer": membership.pointer_of(ref) is not None,
            "disabled": (not always) and (kname in disabled),
        })
    if not rows:
        if want:
            print(f"No kit '{want}' found.", file=sys.stderr)
            return 1
        print("No kits.")
        return 0

    w = max(len(r["name"]) for r in rows)
    if axis is None:
        print("Kit management state -- position on the lifecycle continuum")
        print("(member > loaded > active; colder = more let go):\n")
        for r in rows:
            if r["pointer"]:
                pos = "detached (pointer; not loaded)"
            elif r["disabled"]:
                pos = "disabled (loaded, inactive)"
            else:
                pos = "active"
            tag = "  [always-active]" if r["always"] else ""
            print(f"  {r['name']:<{w}}  {pos}{tag}")
        print("\nMove with `dz kit enable|disable|attach|detach|add|remove <kit>`;")
        print("inspect a sub-axis with `dz kit activation|loading|membership`.")
    elif axis == "activation":
        print("Activation sub-axis (active vs disabled):\n")
        for r in rows:
            st = "disabled" if r["disabled"] else "active"
            tag = "  [always-active]" if r["always"] else ""
            print(f"  {r['name']:<{w}}  {st}{tag}")
        _print_axis_hint("activation")
    elif axis == "loading":
        print("Loading sub-axis (loaded vs pointer):\n")
        for r in rows:
            print(f"  {r['name']:<{w}}  {'pointer' if r['pointer'] else 'loaded'}")
        _print_axis_hint("loading")
    elif axis == "membership":
        print("Membership sub-axis (registered members):\n")
        for r in rows:
            print(f"  {r['name']}")
        _print_axis_hint("membership")
    else:
        print(f"Unknown lifecycle axis: {axis}", file=sys.stderr)
        return 1
    return 0


def _cmd_tree(args, engine):
    """Visualize the aggregator tree (thin wrapper over library render_tree).

    Behavior identical to v0.7.33 -- the library now owns ``--show-disabled``,
    canonical-kit ``[always_active]``/``[aggregator]``/``[disabled]`` markers,
    ``_kit_state()`` computation, and JSON output keys. Library version was
    extended in v0.7.34 to reach byte-equivalence with this CLI's prior body.
    """
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1
    from dazzlecmd_lib.default_meta_commands import render_tree
    return render_tree(
        args, engine, engine.projects, engine.kits, engine.project_root
    )


def _cmd_setup(args, engine):
    """Run a tool's declared setup script.

    The engine doesn't install dependencies itself — it dispatches the
    tool's own ``setup.command`` (or platform-specific variant). The tool
    author writes the setup script; the engine runs it when the user asks.
    """
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    tool_name = getattr(args, "tool", None)

    # No tool specified: list tools that have setup declared (v0.7.21 polish).
    # Detection: `setup.command` OR any `setup.platforms.*` present -- catches
    # tools with ONLY platform-specific setup commands (no top-level default).
    if not tool_name:
        source = getattr(engine, "all_projects", engine.projects)

        def _has_setup(p):
            setup = p.setup
            if not setup or not isinstance(setup, dict):
                return False
            if setup.get("command"):
                return True
            platforms = setup.get("platforms")
            if isinstance(platforms, dict) and platforms:
                return True
            return False

        has_setup = [p for p in source if _has_setup(p)]
        if not has_setup:
            print("No tools have setup commands declared.")
            return 0

        # Sort alphabetically by FQCN for stable output
        has_setup.sort(key=lambda p: p.fqcn or p.name or "")

        # Dynamic column width: longest FQCN, with sane floor/ceiling
        max_fqcn_width = max(
            len(p.fqcn or p.name or "") for p in has_setup
        )
        fqcn_width = max(20, min(max_fqcn_width, 50))

        print("Tools with setup declared:")
        for p in has_setup:
            fqcn = p.fqcn or p.name or "?"
            note = (p.setup or {}).get("note") or "-"
            print(f"  {fqcn:<{fqcn_width}}  {note}")
        print(f"\nRun: dz setup <tool> to execute a tool's setup.")
        return 0

    # Resolve the tool name (supports FQCN, kit-qualified, short name,
    # alias FQCN). Context is unused here; setup doesn't surface
    # resolution provenance.
    project, _ctx = engine.resolve_command(tool_name)
    if project is None:
        # Try all_projects for disabled-kit tools
        source = getattr(engine, "all_projects", engine.projects)
        matches = [p for p in source if p.name == tool_name or p.fqcn == tool_name]
        if matches:
            project = matches[0]
        else:
            print(
                _colors.warn(f"Tool '{tool_name}' not found."),
                file=sys.stderr,
            )
            return 1

    if not project.setup:
        print(f"Tool '{project.fqcn or tool_name}' has no setup command declared.")
        print("Add a 'setup' block to the tool's manifest to enable this.")
        return 0

    # Resolve via shared library: applies platforms.<os>.<subtype> fallback,
    # normalizes flat-string platform values to {"command": <str>}, validates
    # _schema_version. See dazzlecmd_lib.setup_resolve.
    from dazzlecmd_lib.setup_resolve import (
        InvalidSetupBlockError,
        resolve_setup_block,
    )
    from dazzlecmd_lib.schema_version import UnsupportedSchemaVersionError
    import json as _json
    try:
        effective = resolve_setup_block(project)
    except InvalidSetupBlockError as exc:
        # v0.7.46: setup.command + setup.script XOR violation. Surface
        # the structured message cleanly instead of a Python traceback.
        print(_colors.error(f"Error: {exc}"), file=sys.stderr)
        return 1
    except UnsupportedSchemaVersionError as exc:
        print(_colors.error(f"Error: {exc}"), file=sys.stderr)
        return 1
    except _json.JSONDecodeError as exc:
        # Malformed user-override JSON (v0.7.22). Surface clean error with
        # path + parse position; no Python traceback.
        print(
            _colors.error(f"Error: user override file is not valid JSON: {exc}"),
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        # Override file exists but can't be read (permissions, etc.).
        print(
            _colors.error(f"Error: cannot read user override file: {exc}"),
            file=sys.stderr,
        )
        return 1

    # Determine the runnable form: either a shell `command` string or a
    # `script` file pointer. v0.7.46 (4d-3 follow-up) added `setup.script`
    # as a sibling of `setup.command`; XOR-validated by setup_resolve.
    cmd_str = effective.get("command") if effective else None
    script_path = effective.get("script") if effective else None

    tool_dir = project.directory or "."
    fqcn = project.fqcn or tool_name

    if not cmd_str and not script_path:
        from dazzlecmd_lib.platform_detect import get_platform_info
        pi = get_platform_info()
        tag = pi.os + (f".{pi.subtype}" if pi.subtype else "")
        print(
            _colors.warn(
                f"No setup command or script available for platform '{tag}'. "
                f"Add setup.command, setup.script, setup.platforms.{pi.os}, "
                f"or setup.platforms.{pi.os}.general to the manifest."
            ),
            file=sys.stderr,
        )
        return 1

    # Build the dispatch command. `command` runs via the system shell;
    # `script` runs via an interpreter inferred from the file extension.
    import subprocess as _subprocess
    if script_path:
        from dazzlecmd_lib.setup_resolve import infer_setup_script_interpreter
        prefix = infer_setup_script_interpreter(script_path)
        if prefix is None:
            print(
                _colors.error(
                    f"Error: setup.script '{script_path}' has an unsupported "
                    f"extension. Supported: .py, .sh, .cmd, .bat, .ps1."
                ),
                file=sys.stderr,
            )
            return 1
        # Resolve the script path relative to the tool directory. Reject
        # absolute paths to keep the setup contract scoped to the tool.
        if os.path.isabs(script_path):
            print(
                _colors.error(
                    f"Error: setup.script must be relative to the tool "
                    f"directory; got absolute path '{script_path}'."
                ),
                file=sys.stderr,
            )
            return 1
        full_script_path = os.path.join(tool_dir, script_path)
        if not os.path.isfile(full_script_path):
            print(
                _colors.error(
                    f"Error: setup.script '{script_path}' not found at "
                    f"{full_script_path}."
                ),
                file=sys.stderr,
            )
            return 1
        invocation = prefix + [full_script_path]
        # Display: human-readable form joining argv with spaces. Real
        # dispatch uses the argv list (no shell parsing, no quote
        # escaping concerns).
        display_form = " ".join(invocation)
    else:
        invocation = cmd_str
        display_form = cmd_str

    print(f"Running setup for {fqcn}...")
    if effective.get("note"):
        print(f"  Note: {effective['note']}")
    if script_path:
        print(f"  Script: {script_path}")
        print(f"  Invocation: {display_form}")
    else:
        print(f"  Command: {display_form}")
    print(f"  Working dir: {tool_dir}")
    print()
    sys.stdout.flush()

    # `script` path uses argv (shell=False); `command` path keeps shell=True
    # for legacy back-compat (existing setup.command strings often use && and
    # other shell operators).
    if script_path:
        result = _subprocess.run(invocation, cwd=tool_dir, shell=False)
    else:
        result = _subprocess.run(invocation, shell=True, cwd=tool_dir)
    if result.returncode == 0:
        print(f"\nSetup for {fqcn} completed successfully.")
    else:
        print(f"\nSetup for {fqcn} failed with exit code {result.returncode}.", file=sys.stderr)
    return result.returncode


def dispatch_tool(project, argv):
    """Dispatch to a tool's entry point."""
    from dazzlecmd_lib.registry import (
        NoRuntimeResolutionError,
        SetupRequiredError,
    )
    from dazzlecmd_lib.schema_version import UnsupportedSchemaVersionError
    from dazzlecmd_lib.templates import (
        UnresolvedTemplateVariableError,
        TemplateRecursionError,
    )
    import json as _json

    try:
        runner = resolve_entry_point(project)
    except _json.JSONDecodeError as exc:
        # User-override file is malformed (v0.7.22). Surface clean error.
        print(f"Error: user override file is not valid JSON: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: cannot read user override file: {exc}", file=sys.stderr)
        return 1
    except NoRuntimeResolutionError as exc:
        # Clean, actionable trace from the conditional-dispatch resolver.
        # Print its message as-is (already multi-line with platform info +
        # tried entries + fix hint); don't bury it behind a Python traceback.
        print(str(exc), file=sys.stderr)
        return 1
    except UnresolvedTemplateVariableError as exc:
        # BUG-4 fix: surface the already-formatted message cleanly rather
        # than as a Python traceback. Message includes var name + available
        # vars list at the error site.
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except TemplateRecursionError as exc:
        # BUG-4 fix: same for cycle/max-depth template errors.
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except UnsupportedSchemaVersionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if runner is None:
        print(f"Error: Could not resolve entry point for '{project.name}'", file=sys.stderr)
        return 1

    try:
        return runner(argv)
    except SetupRequiredError as exc:
        # v0.7.46 (4b-T5): interpreter/binary missing -> dz setup <fqcn> hint
        # (or "ask the tool creator" hint when the tool has no setup block).
        # Message is pre-formatted by the raiser; print as-is.
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error running '{project.name}': {exc}", file=sys.stderr)
        return 1


def main():
    """Main entry point for dazzlecmd CLI.

    As of v0.7.51 (Phase 3.5 T1-M1), aggregator identity + layout +
    policy are declared in ``aggregator.json`` at the project root
    instead of hardcoded constructor kwargs. The shape below is the
    canonical pattern for any dazzlecmd-lib-based aggregator; every
    per-aggregator knob lives in ``aggregator.json``. Runtime callbacks
    (``build_parser`` / ``dispatch_meta`` / ``dispatch_tool``) stay in
    code because they ARE code -- argparse builders and meta-command
    dispatchers can't be expressed declaratively.

    ``find_aggregator_root`` is anchored to THIS package's ``__file__``,
    not cwd (v0.7.52 fix). Anchoring to cwd would make ``dz`` impersonate
    whatever aggregator the user is standing in -- e.g., running ``dz``
    from inside a wtf-windows checkout would load wtf's ``aggregator.json``
    and ``dz`` would become ``wtf``. The entry point's identity is fixed
    by which package it is (``dazzlecmd``), pinned at install time.
    """
    import os
    import sys
    from dazzlecmd.engine import AggregatorEngine
    from dazzlecmd_lib.aggregator_config import find_aggregator_root

    project_root = find_aggregator_root(os.path.dirname(os.path.abspath(__file__)))
    if project_root is None:
        print(
            "Error: could not find aggregator.json. The dazzlecmd package "
            "must be installed alongside its project tree.",
            file=sys.stderr,
        )
        return 1

    engine = AggregatorEngine.from_project(
        project_root,
        version_info=(DISPLAY_VERSION, __version__),
        is_root=True,
        parser_builder=build_parser,
        meta_dispatcher=dispatch_meta,
        tool_dispatcher=dispatch_tool,
    )

    return engine.run()
