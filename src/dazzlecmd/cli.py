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


# ---------------------------------------------------------------------------
# NEW/SCAFFOLD handlers moved to commands/new.py (cli.py decomposition R2,
# DWP 2026-06-25__16-14-19). Re-exported for dispatch_meta + back-compat
# (_cmd_add, tests, and one-offs import several of these from dazzlecmd.cli).
# ---------------------------------------------------------------------------
from dazzlecmd.commands.new import (  # noqa: F401,E402
    _resolve_new_defaults,
    _find_templates_root,
    _available_languages,
    _substitute_placeholders,
    _copy_template_tree,
    _cmd_new_tool,
    _cmd_new_kit,
    _scaffold_starter_tool,
    _with_copy_component,
    _ComponentUnavailable,
    _REPOKIT_COMMON_URL_DEFAULT,
    _REPOKIT_TEMPLATE_URL_DEFAULT,
    _GIT_SUBTREE_TIMEOUT,
    _run_git,
    _with_common,
    _with_template,
    _WITH_COMPONENTS,
    _WITH_ALL,
    _parse_with_spec,
    _apply_with_components,
    _cmd_new_aggregator,
    _layer_extras,
    _register_in_kit,
)



# ---------------------------------------------------------------------------
# Kit-lifecycle handlers moved to commands/kit*.py (cli.py decomposition R1,
# DWP 2026-06-25__16-14-19). Re-exported here so dispatch_meta resolves them by
# bare name and so the test-suite / one-offs can import them from dazzlecmd.cli.
# ---------------------------------------------------------------------------
from dazzlecmd.commands.kit import (  # noqa: F401,E402
    _kit_exists,
    _cmd_kit_enable,
    _cmd_kit_disable,
    _cmd_kit_focus,
    _cmd_kit_reset,
    _cmd_kit_favorite,
    _suggest_favorite_replacement,
    _cmd_kit_favorite_migrate_stale,
    _cmd_kit_unfavorite,
)
from dazzlecmd.commands.kit_visibility import (  # noqa: F401,E402
    _resolve_visibility_target,
    _is_constitutional_entity,
    _cmd_kit_visibility_set,
    _resolve_cascade_slice,
    _apply_visibility_cascade,
    _cmd_kit_visibility_list,
    _cmd_kit_visibility_status,
)
from dazzlecmd.commands.kit_membership import (  # noqa: F401,E402
    _cmd_kit_add,
    _kit_is_submodule,
    _cmd_kit_remove,
    _cmd_kit_detach,
    _materialize_pointer,
    _cmd_kit_attach,
    _print_axis_hint,
    _cmd_kit_management,
)



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
