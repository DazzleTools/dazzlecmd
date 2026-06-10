"""Main CLI entry point for dazzlecmd.

This module provides the dazzlecmd-specific configuration and the
build_parser/dispatch functions that the AggregatorEngine delegates to.
New aggregator projects should use AggregatorEngine directly rather than
importing from this module.
"""

import argparse
import json
import os
import sys

from dazzlecmd._version import DISPLAY_VERSION, __version__
from dazzlecmd.loader import (
    discover_kits,
    discover_projects,
    get_active_kits,
    resolve_entry_point,
)
from dazzlecmd_lib import colors as _colors


# Reserved command names that cannot be used as tool names
RESERVED_COMMANDS = {
    "new", "add", "list", "info", "kit", "search",
    "build", "tree", "version", "enhance", "graduate", "mode",
}


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


# _wrap_description: canonical implementation lives in dazzlecmd_lib.
# The remaining dazzlecmd consumer is `_cmd_kit_list`'s virtual-kit listing
# (Category C; deferred to X-22-full collapse). Re-export keeps that consumer
# working without import-path edits while eliminating duplicate-code drift.
from dazzlecmd_lib.default_meta_commands import _wrap_description  # noqa: F401


def _build_categorized_help(projects):
    """Build a categorized command listing for the help epilog."""
    # Meta-commands (builtins)
    builtins = [
        ("list", "List available tools"),
        ("info <tool>", "Show detailed info about a tool"),
        ("kit", "Manage kits"),
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
    term_width = shutil.get_terminal_size((80, 24)).columns

    # Build output
    lines = []
    name_width = 16
    desc_width = term_width - name_width - 4  # 2 indent + 2 gap

    lines.append("commands:")
    for cmd, desc in builtins:
        if desc_width > 20 and len(desc) > desc_width:
            desc = desc[:desc_width - 3] + "..."
        lines.append(f"  {cmd:<{name_width}}  {desc}")

    # Tool categories by namespace
    for ns in sorted(namespaces.keys()):
        tools = namespaces[ns]
        lines.append("")
        lines.append(f"{ns} tools:")
        for name, desc in sorted(tools):
            if desc_width > 20 and len(desc) > desc_width:
                desc = desc[:desc_width - 3] + "..."
            lines.append(f"  {name:<{name_width}}  {desc}")

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
    info_parser.set_defaults(_meta="info")

    # dz kit
    kit_parser = subparsers.add_parser("kit", help="Manage kits")
    kit_sub = kit_parser.add_subparsers(dest="kit_command")

    kit_list = kit_sub.add_parser(
        "list", help="List available kits, or tools in a kit"
    )
    kit_list.add_argument(
        "name", nargs="?", default=None, help="Kit name to show tools for"
    )
    kit_list.set_defaults(_meta="kit_list")

    kit_status = kit_sub.add_parser("status", help="Show active kits")
    kit_status.set_defaults(_meta="kit_status")

    kit_enable = kit_sub.add_parser(
        "enable", help="Enable a kit (include its tools in dispatch)"
    )
    kit_enable.add_argument("name", help="Kit name to enable")
    kit_enable.set_defaults(_meta="kit_enable")

    kit_disable = kit_sub.add_parser(
        "disable", help="Disable a kit (exclude its tools from dispatch)"
    )
    kit_disable.add_argument("name", help="Kit name to disable")
    kit_disable.set_defaults(_meta="kit_disable")

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

    kit_silence = kit_sub.add_parser(
        "silence",
        help="Silence the rerooting hint for a specific tool (by FQCN)",
    )
    kit_silence.add_argument("fqcn", help="FQCN to silence")
    kit_silence.set_defaults(_meta="kit_silence")

    kit_unsilence = kit_sub.add_parser(
        "unsilence", help="Restore the rerooting hint for a tool"
    )
    kit_unsilence.add_argument("fqcn", help="FQCN to unsilence")
    kit_unsilence.set_defaults(_meta="kit_unsilence")

    kit_shadow = kit_sub.add_parser(
        "shadow",
        help="Hide a tool entirely from dz (useful when it exists standalone)",
    )
    kit_shadow.add_argument("fqcn", help="FQCN to shadow")
    kit_shadow.set_defaults(_meta="kit_shadow")

    kit_unshadow = kit_sub.add_parser(
        "unshadow", help="Restore a shadowed tool to dz's dispatch"
    )
    kit_unshadow.add_argument("fqcn", help="FQCN to unshadow")
    kit_unshadow.set_defaults(_meta="kit_unshadow")

    kit_hide = kit_sub.add_parser(
        "hide",
        help="Hide a tool from listings (display-off) -- it stays dispatchable",
    )
    kit_hide.add_argument("fqcn", help="FQCN to hide")
    kit_hide.set_defaults(_meta="kit_hide")

    kit_unhide = kit_sub.add_parser(
        "unhide", help="Restore a hidden tool to listings"
    )
    kit_unhide.add_argument("fqcn", help="FQCN to unhide")
    kit_unhide.set_defaults(_meta="kit_unhide")

    kit_silenced = kit_sub.add_parser(
        "silenced",
        help="Show all silenced hints and shadowed tools",
    )
    kit_silenced.set_defaults(_meta="kit_silenced")

    kit_add = kit_sub.add_parser(
        "add", help="Add a kit from a git URL via submodule"
    )
    kit_add.add_argument("url", help="Git URL of the kit repo")
    kit_add.add_argument("--name", help="Override kit name (default: derive from URL)")
    kit_add.add_argument("--branch", help="Branch to check out (default: repo default)")
    kit_add.add_argument("--shallow", action="store_true", help="Shallow clone")
    kit_add.set_defaults(_meta="kit_add")

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

    # dz new kit <name>  -- stub in v0.7.40
    new_kit_parser = new_sub.add_parser(
        "kit", help="Create a new flat kit (full impl in v0.7.42)"
    )
    new_kit_parser.add_argument("name", help="Kit name")
    new_kit_parser.set_defaults(_meta="new_kit_stub")

    # dz new aggregator <name>  -- stub in v0.7.40
    new_agg_parser = new_sub.add_parser(
        "aggregator",
        help="Create a new aggregator project (full impl in v0.7.42)",
    )
    new_agg_parser.add_argument("name", help="Aggregator name")
    new_agg_parser.set_defaults(_meta="new_aggregator_stub")

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
    mode_switch.add_argument("--dry-run", action="store_true",
                             help="Show what would happen without doing it")
    mode_switch.set_defaults(_meta="mode_switch")

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
        return _cmd_info(args, projects, engine=engine)
    elif meta == "kit_list":
        return _cmd_kit_list(args, kits, projects, engine=engine)
    elif meta == "kit_status":
        return _cmd_kit_status(kits, engine=engine)
    elif meta == "kit":
        # bare "dz kit" with no subcommand
        return _cmd_kit_list(args, kits, projects, engine=engine)
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
    elif meta == "kit_silence":
        return _cmd_kit_silence(args, engine)
    elif meta == "kit_unsilence":
        return _cmd_kit_unsilence(args, engine)
    elif meta == "kit_shadow":
        return _cmd_kit_shadow(args, engine)
    elif meta == "kit_unshadow":
        return _cmd_kit_unshadow(args, engine)
    elif meta == "kit_hide":
        return _cmd_kit_hide(args, engine)
    elif meta == "kit_unhide":
        return _cmd_kit_unhide(args, engine)
    elif meta == "kit_silenced":
        return _cmd_kit_silenced(engine)
    elif meta == "kit_add":
        return _cmd_kit_add(args, project_root, engine)
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
    elif meta == "new_kit_stub":
        return _cmd_new_kit_stub(args)
    elif meta == "new_aggregator_stub":
        return _cmd_new_aggregator_stub(args)
    elif meta == "add":
        return _cmd_add(args, project_root)
    elif meta == "mode_status":
        return _cmd_mode_status(args, projects, project_root)
    elif meta == "mode_switch":
        return _cmd_mode_switch(args, projects, project_root)
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


def _cmd_info(args, projects, engine):
    """Show detailed info about a tool (thin wrapper over library render_info).

    Behavior identical to v0.7.33 -- the library now owns alias provenance
    (standard + qualified_alias variants), shadow-status block,
    runtime-dispatch resolution (default/--raw/--platform), pass-through
    marker, Python deps, setup hint, and "Linked to:" line. Library version
    reached byte-equivalence with this CLI's prior body across v0.7.32 + v0.7.33.
    """
    from dazzlecmd_lib.default_meta_commands import render_info
    return render_info(args, projects, engine)


def _cmd_kit_list(args, kits, projects, engine=None):
    """List available kits, or tools in a specific kit.

    When invoked without a kit name, shows all discovered kits with
    enabled/disabled/always-active status based on the user's config.
    """
    kit_name = getattr(args, "name", None)

    if not kits:
        print("No kits found.")
        return 0

    # Compute enabled/disabled status from config
    enabled_set = set()
    disabled_set = set()
    if engine is not None:
        config = engine._get_user_config()
        active_list = config.get("active_kits")
        disabled_list = config.get("disabled_kits") or []
        if isinstance(active_list, list):
            enabled_set = set(active_list)
        if isinstance(disabled_list, list):
            disabled_set = set(disabled_list)

    def _kit_status(kit):
        name = kit.kit_name or kit.name
        if name in disabled_set:
            return "disabled"
        if kit.always_active:
            return "always active"
        if enabled_set and name not in enabled_set:
            return "disabled (not in active_kits)"
        return "enabled"

    if kit_name:
        # Show tools in a specific kit
        matching = [k for k in kits if (k.kit_name or k.name) == kit_name]
        if not matching:
            print(f"Kit '{kit_name}' not found. Available kits:")
            for k in kits:
                print(f"  {k.kit_name or k.name}")
            return 1

        kit = matching[0]
        name = kit.kit_name or kit.name
        status = _kit_status(kit)
        is_virtual = kit.virtual is True
        label = "virtual, " + status if is_virtual else status
        print(f"Kit: {name} [{label}]")
        if kit.description:
            print(f"  {kit.description}")
        print()

        # Virtual-kit drill-in: show alias FQCN + canonical target +
        # description for each declared alias. Without this, users
        # see canonical short names and miss the whole point of the
        # virtual kit (its aliases).
        if is_virtual:
            return _render_virtual_kit_aliases(kit, projects, engine)

        tool_refs = kit.tools or []
        if not tool_refs:
            print("  No tools in this kit.")
            return 0

        # Build rows first so per-column widths can be computed from
        # actual data instead of the v0.7.28-and-earlier fixed 16-char
        # columns. Matches the `dz list` flat-fallback layout.
        rows = []  # (name, platform, description_or_notfound_marker)
        for ref in sorted(tool_refs):
            # Modern path: ref is a full FQCN as written by
            # ``engine._discover_aggregator``'s post-recursion populate
            # (e.g., ``wtf:core:locked``). Match by ``_fqcn`` directly so
            # multi-segment FQCNs resolve.
            match = [p for p in projects if p.fqcn == ref]
            if match:
                p = match[0]
                ref_name = p.name
            else:
                # Legacy fallback: parse ref as ``ns:name`` for existing
                # kit manifests that use 2-segment refs.
                if ":" in ref:
                    ns, ref_name = ref.split(":", 1)
                else:
                    ns, ref_name = "", ref
                match = [
                    p for p in projects
                    if p.name == ref_name
                    and (not ns or p.namespace == ns)
                ]
            if match:
                p = match[0]
                rows.append(
                    (ref_name, p.platform or "", p.description or "")
                )
            else:
                rows.append((ref_name, "", "(not found)"))

        import shutil
        term_width = shutil.get_terminal_size((80, 24)).columns

        name_width = max(len(r[0]) for r in rows)
        platform_width = max(len(r[1]) for r in rows)
        indent = "  "
        # 2 indent + name + 2 gap + platform + 2 gap = description column
        desc_col = len(indent) + name_width + 2 + platform_width + 2
        desc_max = term_width - desc_col

        for n, plat, desc in rows:
            wrapped = _wrap_description(desc, desc_max)
            print(
                f"{indent}{n:<{name_width}}  "
                f"{plat:<{platform_width}}  {wrapped[0]}"
            )
            wrap_indent = " " * desc_col
            for line in wrapped[1:]:
                print(f"{wrap_indent}{line}")

        print(f"\n  {len(tool_refs)} tool(s)")
        return 0

    # No name given — list all kits with status
    for i, kit in enumerate(kits):
        if i > 0:
            print()  # blank line separator for readability
        name = kit.kit_name or kit.name
        status = _kit_status(kit)
        tool_count = len(kit.tools or [])
        print(f"  {name:<16} {tool_count} tool(s)  [{status}]")
        if kit.description:
            print(f"    {kit.description}")
    return 0


def _render_virtual_kit_aliases(kit, projects, engine):
    """Drill-in rendering for a virtual kit: show each alias FQCN with
    its canonical target and canonical description.

    Works by iterating ``engine.fqcn_index.alias_index`` and filtering
    to aliases whose virtual-kit prefix matches this kit's name. Falls
    back to iterating ``kit["tools"]`` + ``kit["name_rewrite"]`` when
    no engine is available (which shouldn't happen in practice but
    makes the code robust).
    """
    vk_name = kit.kit_name or kit.name
    name_rewrite = kit.name_rewrite or {}
    tools = kit.tools or []

    # Build (alias_fqcn, canonical_fqcn, alias_short) rows
    rows = []
    if engine is not None and hasattr(engine, "fqcn_index"):
        for alias_fqcn, canonical_fqcn in engine.fqcn_index.alias_index.items():
            prefix = f"{vk_name}:"
            if not alias_fqcn.startswith(prefix):
                continue
            alias_short = alias_fqcn[len(prefix):]
            rows.append((alias_fqcn, canonical_fqcn, alias_short))
    else:
        # Fallback: derive from manifest directly
        for canonical_fqcn in tools:
            alias_short = name_rewrite.get(canonical_fqcn) or canonical_fqcn.rsplit(":", 1)[-1]
            rows.append((f"{vk_name}:{alias_short}", canonical_fqcn, alias_short))

    if not rows:
        print("  No aliases declared in this virtual kit.")
        return 0

    rows.sort(key=lambda r: r[2])  # sort by alias short

    # Build project lookup for descriptions
    by_fqcn = {p.fqcn: p for p in projects if p.fqcn}

    # Column widths
    alias_width = max(len(r[0]) for r in rows)
    alias_width = max(alias_width, len("Alias FQCN"))
    target_width = max(len(r[1]) for r in rows)
    target_width = max(target_width, len("-> Canonical"))

    header = f"  {'Alias FQCN':<{alias_width}}  {'-> Canonical':<{target_width}}  Description"
    print(header)
    print("  " + "-" * (len(header) - 2))

    import shutil
    term_width = shutil.get_terminal_size((80, 24)).columns
    desc_col = 2 + alias_width + 2 + target_width + 2
    desc_max = term_width - desc_col

    for alias_fqcn, canonical_fqcn, _alias_short in rows:
        target_project = by_fqcn.get(canonical_fqcn)
        desc = (target_project.description or "") if target_project else "(canonical not discovered)"
        wrapped = _wrap_description(desc, desc_max)
        arrow_target = f"-> {canonical_fqcn}"
        print(f"  {alias_fqcn:<{alias_width}}  {arrow_target:<{target_width}}  {wrapped[0]}")
        indent = " " * desc_col
        for line in wrapped[1:]:
            print(f"{indent}{line}")

    print(f"\n  {len(rows)} alias(es) -> canonical tools")
    return 0


def _cmd_kit_status(kits, engine=None):
    """Show active kits summary.

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


def _cmd_new_kit_stub(args):
    """Stub for ``dz new kit <name>`` -- full impl in v0.7.42 (4d-2).

    Prints a clear "coming soon" message so users see the planned shape
    without confusing argparse errors. Returns 2 (not 0) so scripts can
    detect that the command did not actually create anything.
    """
    print(
        f"'dz new kit {args.name}' is not yet implemented (v0.7.40).\n\n"
        "Planned shape (v0.7.42, item 4d-2):\n"
        "  dz new kit <name>                  Create a flat kit at projects/<name>/\n"
        "  dz new kit <name> --with-starter   Include a starter 'hello' tool\n\n"
        "For now, use 'dz new tool <name>' to create individual tools,\n"
        "and 'dz kit add <url>' to import existing kits from a repo.",
        file=sys.stderr,
    )
    return 2


def _cmd_new_aggregator_stub(args):
    """Stub for ``dz new aggregator <name>`` -- full impl in v0.7.42 (4d-2).

    Aggregator scaffolding always produces a standalone project (own
    pyproject.toml + entry point + tests). Local-kit creation is the
    separate ``dz new kit`` command (per Tier 2 design synthesis 2026-05-13
    Open Question A resolution A2).
    """
    print(
        f"'dz new aggregator {args.name}' is not yet implemented (v0.7.40).\n\n"
        "Planned shape (v0.7.42, item 4d-2):\n"
        "  dz new aggregator <name>                Standalone aggregator project\n"
        "  dz new aggregator <name> --command <c>  Override CLI command name\n"
        "  dz new aggregator <name> --with common,template,ci\n"
        "                                          Composable scaffolding components\n\n"
        "For now, use 'dz new tool <name>' to create tools inside the current\n"
        "dazzlecmd project.",
        file=sys.stderr,
    )
    return 2


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
    """Add a kit to active_kits and remove it from disabled_kits."""
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    active = list(config.get("active_kits") or [])
    disabled = list(config.get("disabled_kits") or [])

    if name in disabled:
        disabled.remove(name)
    if name not in active:
        active.append(name)

    # Warn if the kit doesn't exist on disk
    if engine.kits and not _kit_exists(engine.kits, name):
        print(
            f"Warning: kit '{name}' not found among discovered kits. "
            f"Change will apply if the kit becomes available later.",
            file=sys.stderr,
        )

    engine._write_user_config({
        "active_kits": active,
        "disabled_kits": disabled,
    })
    print(f"Enabled kit: {name}")
    return 0


def _cmd_kit_disable(args, engine):
    """Add a kit to disabled_kits and remove it from active_kits."""
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    active = list(config.get("active_kits") or [])
    disabled = list(config.get("disabled_kits") or [])

    if name in active:
        active.remove(name)
    if name not in disabled:
        disabled.append(name)

    if engine.kits and not _kit_exists(engine.kits, name):
        print(
            f"Warning: kit '{name}' not found among discovered kits.",
            file=sys.stderr,
        )

    engine._write_user_config({
        "active_kits": active,
        "disabled_kits": disabled,
    })
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


def _cmd_kit_silence(args, engine):
    """Add an FQCN to silenced_hints.tools."""
    fqcn = args.fqcn
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    silenced = dict(config.get("silenced_hints") or {})
    tools = list(silenced.get("tools") or [])
    if fqcn not in tools:
        tools.append(fqcn)
    silenced["tools"] = tools
    silenced.setdefault("kits", [])

    engine._write_user_config({"silenced_hints": silenced})
    print(f"Silenced rerooting hint for: {fqcn}")
    return 0


def _cmd_kit_unsilence(args, engine):
    """Remove an FQCN from silenced_hints.tools."""
    fqcn = args.fqcn
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    silenced = dict(config.get("silenced_hints") or {})
    tools = list(silenced.get("tools") or [])
    if fqcn not in tools:
        print(f"'{fqcn}' was not silenced.")
        return 0
    tools.remove(fqcn)
    silenced["tools"] = tools
    silenced.setdefault("kits", [])

    engine._write_user_config({"silenced_hints": silenced})
    print(f"Unsilenced rerooting hint for: {fqcn}")
    return 0


def _cmd_kit_shadow(args, engine):
    """Add an FQCN to shadowed_tools."""
    fqcn = args.fqcn
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    shadowed = list(config.get("shadowed_tools") or [])
    if fqcn not in shadowed:
        shadowed.append(fqcn)

    engine._write_user_config({"shadowed_tools": shadowed})
    print(f"Shadowed: {fqcn}")
    print(f"  This tool will not appear in 'dz list' or be dispatchable.")
    return 0


def _cmd_kit_unshadow(args, engine):
    """Remove an FQCN from shadowed_tools."""
    fqcn = args.fqcn
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    shadowed = list(config.get("shadowed_tools") or [])
    if fqcn not in shadowed:
        print(f"'{fqcn}' was not shadowed.")
        return 0
    shadowed.remove(fqcn)

    engine._write_user_config({"shadowed_tools": shadowed})
    print(f"Unshadowed: {fqcn}")
    return 0


def _cmd_kit_hide(args, engine):
    """Add an FQCN to hidden_tools (display-off, still dispatchable)."""
    fqcn = args.fqcn
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    hidden = list(config.get("hidden_tools") or [])
    if fqcn not in hidden:
        hidden.append(fqcn)

    engine._write_user_config({"hidden_tools": hidden})
    print(f"Hidden: {fqcn}")
    print("  Omitted from 'dz list'/'dz tree' but still dispatchable by name")
    print("  (reveal with 'dz list --show-hidden').")
    return 0


def _cmd_kit_unhide(args, engine):
    """Remove an FQCN from hidden_tools."""
    fqcn = args.fqcn
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    hidden = list(config.get("hidden_tools") or [])
    if fqcn not in hidden:
        print(f"'{fqcn}' was not hidden.")
        return 0
    hidden.remove(fqcn)

    engine._write_user_config({"hidden_tools": hidden})
    print(f"Unhidden: {fqcn}")
    return 0


def _cmd_kit_silenced(engine):
    """Show all silenced_hints and shadowed_tools entries."""
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    silenced = config.get("silenced_hints") or {}
    shadowed = config.get("shadowed_tools") or []
    favorites = config.get("favorites") or {}

    silenced_tools = silenced.get("tools") or []
    silenced_kits = silenced.get("kits") or []

    print("Silenced hints:")
    if silenced_tools:
        print("  tools:")
        for fqcn in silenced_tools:
            print(f"    - {fqcn}")
    else:
        print("  tools: (none)")
    if silenced_kits:
        print("  kits:")
        for kit in silenced_kits:
            print(f"    - {kit}")
    else:
        print("  kits: (none)")

    print()
    print("Shadowed tools:")
    if shadowed:
        for fqcn in shadowed:
            print(f"  - {fqcn}")
    else:
        print("  (none)")

    print()
    print("Favorites:")
    if favorites:
        for short, fqcn in favorites.items():
            print(f"  {short} -> {fqcn}")
    else:
        print("  (none)")

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
    try:
        result = _subprocess.run(cmd, cwd=project_root)
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
