"""argparse construction for the dazzlecmd CLI.

Moved out of cli.py (decomposition R4, DWP 2026-06-25__16-14-19). Holds
build_parser (the top-level parser + dynamic tool subparsers), the categorized
--help epilog builder, and _register_meta_commands (every built-in subparser and
its `_meta` dispatch tag). cli.py re-exports build_parser (the engine wiring +
tests import it from dazzlecmd.cli). Imports nothing from cli.py.
"""
import argparse
import sys

from dazzlecmd._version import DISPLAY_VERSION, __version__
from dazzlecmd._constants import RESERVED_COMMANDS
from dazzlecmd.kit_verbs import (
    add_flat_verb,
    build_lifecycle_axis_groups,
    render_kit_help,
)
from dazzlecmd_lib.default_meta_commands import MIN_DESC_WIDTH, TERM_SIZE_FALLBACK

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
    info_parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Emit the card as JSON (structured facets) for programmatic use.",
    )
    info_parser.set_defaults(_meta="info")

    # dz enable <kit> / dz disable <kit> -- the bare-verb cross-level toggles
    # (B4-mutate). The activation axis applies_at={'kit'}; the generic verb x
    # level dispatcher resolves the target's level and fails loud at the wrong
    # level. `dz kit enable <name>` remains the explicit form.
    for _verb, _help in (("enable", "Enable a kit (activation warm pole)"),
                         ("disable", "Disable a kit (activation cold pole)"),
                         ("attach", "Attach a kit (loading warm pole)"),
                         ("detach", "Detach a kit to a pointer (loading cold pole)")):
        _vp = subparsers.add_parser(_verb, help=_help)
        _vp.add_argument("target", help=f"Kit to {_verb}")
        _vp.add_argument(
            "--as", dest="as_level",
            choices=["tool", "kit", "aggregator"],
            help="Force the level when the name is ambiguous across levels.")
        _vp.set_defaults(_meta=_verb)

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
