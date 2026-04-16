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


# Reserved command names that cannot be used as tool names
RESERVED_COMMANDS = {
    "new", "add", "list", "info", "kit", "search",
    "build", "tree", "version", "enhance", "graduate", "mode",
}


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
        name = project["name"]
        if name in reserved:
            print(
                f"Warning: Tool '{name}' conflicts with reserved command, skipping",
                file=sys.stderr,
            )
            continue

        desc = project.get("description", "")
        sub = subparsers.add_parser(
            name,
            help=desc,
            add_help=False,  # Let the tool handle its own --help
        )
        sub.set_defaults(_project=project)

    return parser


def _wrap_description(text, width):
    """Wrap a description string to fit within a given width.

    Returns a list of lines. Wraps at word boundaries when possible,
    falls back to hard break with hyphen when a single word exceeds
    the width.
    """
    if not text or width < 10:
        return [text or ""]
    if len(text) <= width:
        return [text]

    lines = []
    remaining = text
    while remaining:
        if len(remaining) <= width:
            lines.append(remaining)
            break

        # Find the last space within the width
        break_at = remaining.rfind(" ", 0, width)
        if break_at > 0:
            lines.append(remaining[:break_at])
            remaining = remaining[break_at + 1:]
        else:
            # No space found -- hard break with hyphen
            lines.append(remaining[:width - 1] + "-")
            remaining = remaining[width - 1:]

    return lines


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
        name = project["name"]
        if name in RESERVED_COMMANDS:
            continue
        kit = project.get("_kit_import_name") or project.get("namespace", "other")
        desc = project.get("description", "")
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
    list_parser.add_argument("--kit", "-k", help="Filter by kit")
    list_parser.add_argument("--tag", "-t", help="Filter by tag")
    list_parser.add_argument("--platform", "-p", help="Filter by platform")
    list_parser.set_defaults(_meta="list")

    # dz info <tool>
    info_parser = subparsers.add_parser("info", help="Show detailed info about a tool")
    info_parser.add_argument("tool", help="Tool name to inspect")
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
    kit_favorite.add_argument("short", help="Short name to bind")
    kit_favorite.add_argument("fqcn", help="FQCN of the target tool")
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

    # dz new <name>
    new_parser = subparsers.add_parser("new", help="Create a new tool project")
    new_parser.add_argument("name", help="Tool name")
    new_parser.add_argument("--namespace", "-n", default="dazzletools", help="Namespace (default: dazzletools)")
    new_parser.add_argument("--kit", "-k", help="Register in this kit (e.g., core, dazzletools)")
    new_parser.add_argument("--simple", action="store_true", help="Add TODO.md and NOTES.md")
    new_parser.add_argument("--full", action="store_true", help="Add ROADMAP.md, private/claude/, tests/")
    new_parser.add_argument("--description", "-d", default="", help="Tool description")
    new_parser.add_argument("--language", "-l", default="python", help="Primary language (default: python)")
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
        return _cmd_info(args, projects)
    elif meta == "kit_list":
        return _cmd_kit_list(args, kits, projects, engine=engine)
    elif meta == "kit_status":
        return _cmd_kit_status(kits)
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
        return _cmd_new(args, project_root)
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
    """List available tools.

    If the engine is provided, tools that share a short name with another
    tool (collision) are marked with ``[*]`` after the name.
    """
    filtered = projects

    if args.namespace:
        filtered = [p for p in filtered if p.get("namespace") == args.namespace]
    if args.platform:
        filtered = [p for p in filtered if p.get("platform", "cross-platform") == args.platform]
    if args.tag:
        filtered = [
            p for p in filtered
            if args.tag in p.get("taxonomy", {}).get("tags", [])
        ]
    if args.kit:
        # Filter by kit import name (the top-level kit a tool belongs to)
        filtered = [
            p for p in filtered
            if p.get("_kit_import_name") == args.kit
        ]

    if not filtered:
        print("No tools found.")
        return 0

    # Build a set of colliding short names from the FQCN index
    colliding = set()
    if engine is not None and hasattr(engine, "fqcn_index"):
        for short, fqcns in engine.fqcn_index.short_index.items():
            if len(fqcns) > 1:
                colliding.add(short)

    def _label(project):
        name = project["name"]
        if name in colliding:
            return f"{name} [*]"
        return name

    # Table output
    name_width = max(len(_label(p)) for p in filtered)
    kit_width = max(len(p.get("_kit_import_name", "")) for p in filtered)
    kit_width = max(kit_width, len("Kit"))

    header = f"  {'Name':<{name_width}}  {'Kit':<{kit_width}}  Description"
    print(header)
    print("  " + "-" * (len(header) - 2))

    import shutil
    term_width = shutil.get_terminal_size((80, 24)).columns
    desc_col = 2 + name_width + 2 + kit_width + 2
    desc_max = term_width - desc_col

    for project in filtered:
        label = _label(project)
        kit = project.get("_kit_import_name", "")
        desc = project.get("description", "")
        wrapped = _wrap_description(desc, desc_max)
        print(f"  {label:<{name_width}}  {kit:<{kit_width}}  {wrapped[0]}")
        indent = " " * desc_col
        for line in wrapped[1:]:
            print(f"{indent}{line}")

    if colliding:
        print(f"\n  [*] marks tools with short-name collisions. Use 'dz info <fqcn>' or 'dz kit favorite' to disambiguate.")
    print(f"\n  {len(filtered)} tool(s) found")
    return 0


def _cmd_info(args, projects):
    """Show detailed info about a tool."""
    tool_name = args.tool

    # Accept FQCN input (e.g., 'wtf:core:locked') as well as short name
    if ":" in tool_name:
        matches = [p for p in projects if p.get("_fqcn") == tool_name]
    else:
        matches = [p for p in projects if p["name"] == tool_name]

    if not matches:
        print(f"Tool '{tool_name}' not found. Use 'dz list' to see available tools.")
        return 1

    if len(matches) > 1:
        print(f"Multiple tools named '{tool_name}':")
        for p in matches:
            print(f"  {p.get('_fqcn', p['name'])}")
        print(f"Use 'dz info <fqcn>' to be specific.")
        return 1

    project = matches[0]
    print(f"Name:        {project['name']}")
    print(f"FQCN:        {project.get('_fqcn', 'unknown')}")
    print(f"Kit:         {project.get('_kit_import_name', 'unknown')}")
    print(f"Namespace:   {project.get('namespace', 'unknown')}")
    print(f"Version:     {project.get('version', 'unknown')}")
    print(f"Description: {project.get('description', '')}")
    print(f"Platform:    {project.get('platform', 'cross-platform')}")
    print(f"Language:    {project.get('language', 'unknown')}")

    runtime = project.get("runtime", {})
    runtime_type = runtime.get("type", "python")
    print(f"Runtime:     {runtime_type}")
    if runtime.get("script_path"):
        label = "Binary:" if runtime_type == "binary" else "Script:"
        print(f"{label:13}{runtime['script_path']}")
    if runtime.get("dev_command"):
        print(f"Dev command:  {runtime['dev_command']}")
    if runtime.get("interpreter"):
        print(f"Interpreter: {runtime['interpreter']}")
    if project.get("pass_through"):
        print(f"Pass-through: yes")

    taxonomy = project.get("taxonomy", {})
    if taxonomy.get("category"):
        print(f"Category:    {taxonomy['category']}")
    if taxonomy.get("tags"):
        print(f"Tags:        {', '.join(taxonomy['tags'])}")

    deps = project.get("dependencies", {})
    if deps.get("python"):
        print(f"Python deps: {', '.join(deps['python'])}")

    # Show setup info if declared
    setup = project.get("setup")
    if setup:
        print(f"Setup:       {setup.get('note', setup.get('command', 'available'))}")
        print(f"             Run: dz setup {project.get('_fqcn', project['name'])}")

    # Show link status
    from dazzlecmd.importer import is_linked_project, get_link_target
    if is_linked_project(project["_dir"]):
        target = get_link_target(project["_dir"])
        print(f"Linked to:   {target or 'unknown'}")

    return 0


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
        name = kit.get("_kit_name") or kit.get("name")
        if name in disabled_set:
            return "disabled"
        if kit.get("always_active"):
            return "always active"
        if enabled_set and name not in enabled_set:
            return "disabled (not in active_kits)"
        return "enabled"

    if kit_name:
        # Show tools in a specific kit
        matching = [k for k in kits if (k.get("_kit_name") or k.get("name")) == kit_name]
        if not matching:
            print(f"Kit '{kit_name}' not found. Available kits:")
            for k in kits:
                print(f"  {k.get('_kit_name') or k.get('name')}")
            return 1

        kit = matching[0]
        name = kit.get("_kit_name") or kit.get("name")
        status = _kit_status(kit)
        print(f"Kit: {name} [{status}]")
        if kit.get("description"):
            print(f"  {kit['description']}")
        print()

        tool_refs = kit.get("tools", [])
        if not tool_refs:
            print("  No tools in this kit.")
            return 0

        # Match tool refs (namespace:name) to discovered projects
        for ref in sorted(tool_refs):
            # Parse "namespace:name" format
            if ":" in ref:
                ns, name = ref.split(":", 1)
            else:
                ns, name = "", ref

            match = [p for p in projects if p["name"] == name and (not ns or p.get("namespace") == ns)]
            if match:
                p = match[0]
                desc = p.get("description", "")
                if len(desc) > 55:
                    desc = desc[:52] + "..."
                platform = p.get("platform", "")
                print(f"  {name:<16} {platform:<16} {desc}")
            else:
                print(f"  {name:<16} {'':16} (not found)")

        print(f"\n  {len(tool_refs)} tool(s)")
        return 0

    # No name given — list all kits with status
    for i, kit in enumerate(kits):
        if i > 0:
            print()  # blank line separator for readability
        name = kit.get("_kit_name") or kit.get("name")
        status = _kit_status(kit)
        tool_count = len(kit.get("tools", []))
        print(f"  {name:<16} {tool_count} tool(s)  [{status}]")
        if kit.get("description"):
            print(f"    {kit['description']}")
    return 0


def _cmd_kit_status(kits):
    """Show active kits summary."""
    active = get_active_kits(kits)
    print(f"Active kits: {len(active)}")
    for kit in active:
        tool_count = len(kit.get("tools", []))
        print(f"  {kit['name']}: {tool_count} tool(s)")
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
    """Add a tool reference to a kit's tools array."""
    kits_dir = os.path.join(project_root, "kits")
    kit_file = os.path.join(kits_dir, f"{kit_name}.kit.json")

    if not os.path.isfile(kit_file):
        print(f"  Warning: Kit '{kit_name}' not found at {kit_file}",
              file=sys.stderr)
        return

    try:
        with open(kit_file, "r", encoding="utf-8") as f:
            kit = json.load(f)

        qualified = f"{namespace}:{tool_name}"
        if qualified not in kit.get("tools", []):
            kit.setdefault("tools", []).append(qualified)
            with open(kit_file, "w", encoding="utf-8") as f:
                json.dump(kit, f, indent=4)
                f.write("\n")
            print(f"  Registered in kit: {kit_name}")
        else:
            print(f"  Already in kit: {kit_name}")
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
    )


def _cmd_new(args, project_root):
    """Create a new tool project with progressive scaffolding."""
    name = args.name
    namespace = args.namespace
    description = args.description or f"A new dazzlecmd tool: {name}"
    language = args.language

    projects_dir = os.path.join(project_root, "projects", namespace)
    tool_dir = os.path.join(projects_dir, name)

    if os.path.exists(tool_dir):
        # Check if we're layering on extras
        if args.simple or args.full:
            return _layer_extras(tool_dir, name, args)
        print(f"Error: Project '{namespace}/{name}' already exists at {tool_dir}")
        return 1

    # Create the project directory
    os.makedirs(tool_dir, exist_ok=True)

    # Create .dazzlecmd.json manifest (always)
    manifest = {
        "name": name,
        "version": "0.1.0",
        "description": description,
        "namespace": namespace,
        "language": language,
        "platform": "cross-platform",
        "platforms": ["windows", "linux", "macos"],
        "runtime": {
            "type": "python",
            "entry_point": "main",
            "script_path": f"{name.replace('-', '_')}.py",
        },
        "pass_through": False,
        "taxonomy": {
            "category": "",
            "tags": [],
        },
        "lifecycle": {
            "type": "tool",
            "status": "active",
            "created_as": "tool",
        },
    }

    manifest_path = os.path.join(tool_dir, ".dazzlecmd.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
        f.write("\n")

    # Create starter script (always)
    script_name = f"{name.replace('-', '_')}.py"
    script_path = os.path.join(tool_dir, script_name)

    # Templates live in dazzlecmd-lib; fall back to local templates dir
    import dazzlecmd_lib
    lib_dir = os.path.dirname(dazzlecmd_lib.__file__)
    template_dir = os.path.join(lib_dir, "templates")
    if not os.path.isdir(template_dir):
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
    tmpl_path = os.path.join(template_dir, "python_tool.py.tmpl")

    if os.path.isfile(tmpl_path):
        with open(tmpl_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("{name}", name)
        content = content.replace("{description}", description)
    else:
        content = _default_python_template(name, description)

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Created project: {namespace}/{name}")
    print(f"  {tool_dir}/")
    print(f"  - .dazzlecmd.json")
    print(f"  - {script_name}")

    # Layer on extras if requested
    if args.simple or args.full:
        _layer_extras(tool_dir, name, args)

    # Register in kit if requested
    kit_name = getattr(args, "kit", None)
    if kit_name:
        _register_in_kit(project_root, kit_name, namespace, name)

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


def _default_python_template(name, description):
    """Fallback Python tool template when template file is not found."""
    safe_name = name.replace("-", "_")
    return f'''"""
{name} - {description}
"""

import sys


def main(argv=None):
    """Entry point for {name}."""
    if argv is None:
        argv = sys.argv[1:]

    print(f"{name}: not yet implemented")
    print(f"Arguments: {{argv}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


#
# Phase 3 command handlers: kit enable/disable/focus/reset/favorite/
# unfavorite/silence/unsilence/shadow/unshadow/silenced/add and dz tree.
# All write-path handlers take an ``engine`` parameter to call
# ``engine._write_user_config(updates)``.
#


def _kit_exists(kits, name):
    """Return True if a kit with the given name is discovered."""
    return any(
        (k.get("_kit_name") or k.get("name")) == name for k in kits
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
        kname = kit.get("_kit_name") or kit.get("name")
        if kname == name:
            continue
        if kit.get("always_active"):
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
    """Set a favorite binding: short name -> FQCN."""
    short = args.short
    fqcn = args.fqcn
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # Reject reserved command names
    reserved = engine.reserved_commands
    if short in reserved:
        print(
            f"Error: '{short}' is a reserved command name and cannot "
            f"be set as a favorite.",
            file=sys.stderr,
        )
        return 1

    # Warn if the target FQCN isn't discovered
    if hasattr(engine, "fqcn_index") and fqcn not in engine.fqcn_index.fqcn_index:
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
    """Visualize the aggregator tree.

    Renders an ASCII tree by default, or JSON with ``--json``.
    Uses Phase 2's FQCN index as the data source.
    """
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    as_json = getattr(args, "json", False)
    depth_limit = getattr(args, "depth", None)
    kit_filter = getattr(args, "kit", None)
    show_disabled = getattr(args, "show_disabled", False)

    # Build the hierarchical view from the appropriate project list.
    # --show-disabled uses all_projects (includes disabled kits' tools);
    # default uses engine.projects (active only).
    source = getattr(engine, "all_projects", engine.projects) if show_disabled else engine.projects
    by_kit = {}
    for project in source:
        kit = project.get("_kit_import_name", "?")
        by_kit.setdefault(kit, []).append(project)

    # Also build a kit info dict for metadata (always_active, is_aggregator)
    kit_info = {}
    for kit in engine.kits:
        name = kit.get("_kit_name") or kit.get("name")
        tools_path = os.path.join(engine.project_root or "", engine.tools_dir)
        candidate_root = os.path.join(tools_path, name)
        is_aggregator = os.path.isdir(os.path.join(candidate_root, "kits"))
        kit_info[name] = {
            "always_active": bool(kit.get("always_active")),
            "is_aggregator": is_aggregator,
        }

    # Compute enabled/disabled status
    config = engine._get_user_config()
    enabled_list = config.get("active_kits")
    disabled_list = config.get("disabled_kits") or []
    disabled_set = set(disabled_list) if isinstance(disabled_list, list) else set()
    enabled_set = set(enabled_list) if isinstance(enabled_list, list) else set()

    def _kit_state(kit_name):
        if kit_name in disabled_set:
            return "disabled"
        if enabled_set and kit_name not in enabled_set:
            info = kit_info.get(kit_name, {})
            if info.get("always_active"):
                return "enabled (always_active)"
            return "disabled (not in active_kits)"
        info = kit_info.get(kit_name, {})
        if info.get("always_active"):
            return "enabled (always_active)"
        return "enabled"

    # Filter by --kit if specified
    kit_names = sorted(by_kit.keys())
    if kit_filter:
        kit_names = [k for k in kit_names if k == kit_filter]
        if not kit_names:
            print(f"Error: kit '{kit_filter}' not found.", file=sys.stderr)
            return 1

    # Filter out disabled kits unless --show-disabled
    if not show_disabled:
        kit_names = [
            k for k in kit_names
            if _kit_state(k) not in ("disabled", "disabled (not in active_kits)")
        ]

    if as_json:
        result = {
            "root": engine.name,
            "command": engine.command,
            "tools_dir": engine.tools_dir,
            "kits": {},
        }
        for kit_name in kit_names:
            info = kit_info.get(kit_name, {})
            tools_data = []
            for project in sorted(by_kit[kit_name], key=lambda p: p.get("_fqcn", "")):
                tools_data.append({
                    "fqcn": project.get("_fqcn", ""),
                    "short": project.get("_short_name", project.get("name", "")),
                    "description": project.get("description", ""),
                })
            result["kits"][kit_name] = {
                "name": kit_name,
                "always_active": info.get("always_active", False),
                "is_aggregator": info.get("is_aggregator", False),
                "state": _kit_state(kit_name),
                "tools": tools_data,
            }
        print(json.dumps(result, indent=2))
        return 0

    # ASCII tree output
    version_str = ""
    if engine.version_info:
        display, _ = engine.version_info
        version_str = f" ({engine.name} {display})"
    print(f"{engine.command}{version_str}")

    total_tools = 0
    for i, kit_name in enumerate(kit_names):
        is_last_kit = (i == len(kit_names) - 1)
        kit_prefix = "\\-- " if is_last_kit else "+-- "
        info = kit_info.get(kit_name, {})
        state = _kit_state(kit_name)

        markers = []
        if info.get("always_active"):
            markers.append("always_active")
        if info.get("is_aggregator"):
            markers.append("aggregator")
        if "disabled" in state:
            markers.append("disabled")
        marker_str = f" [{', '.join(markers)}]" if markers else ""

        print(f"{kit_prefix}{kit_name}{marker_str}")

        tools = sorted(by_kit[kit_name], key=lambda p: p.get("_fqcn", ""))
        total_tools += len(tools)

        # Apply depth limit: depth 1 is "show kits", depth 2 is "show tools",
        # so tools appear at depth 2+
        if depth_limit is not None and depth_limit < 2:
            continue

        branch_indent = "    " if is_last_kit else "|   "
        for j, project in enumerate(tools):
            is_last_tool = (j == len(tools) - 1)
            tool_prefix = "\\-- " if is_last_tool else "+-- "
            fqcn = project.get("_fqcn", project.get("name", ""))
            desc = project.get("description", "")
            # Truncate long descriptions
            if len(desc) > 60:
                desc = desc[:57] + "..."
            print(f"{branch_indent}{tool_prefix}{fqcn}  {desc}")

    print()
    print(f"{total_tools} tools across {len(kit_names)} kit(s)")
    return 0


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

    # No tool specified: list tools that have setup commands
    if not tool_name:
        source = getattr(engine, "all_projects", engine.projects)
        has_setup = [
            p for p in source
            if p.get("setup") and p["setup"].get("command")
        ]
        if not has_setup:
            print("No tools have setup commands declared.")
            return 0
        print("Tools with setup commands:")
        for p in has_setup:
            fqcn = p.get("_fqcn", p.get("name", "?"))
            note = p.get("setup", {}).get("note", "")
            print(f"  {fqcn:30}  {note}")
        print(f"\nRun: dz setup <tool> to execute a tool's setup.")
        return 0

    # Resolve the tool name (supports FQCN, kit-qualified, short name)
    project, notification = engine.resolve_command(tool_name)
    if project is None:
        # Try all_projects for disabled-kit tools
        source = getattr(engine, "all_projects", engine.projects)
        matches = [p for p in source if p.get("name") == tool_name or p.get("_fqcn") == tool_name]
        if matches:
            project = matches[0]
        else:
            print(f"Tool '{tool_name}' not found.", file=sys.stderr)
            return 1

    setup = project.get("setup")
    if not setup:
        print(f"Tool '{project.get('_fqcn', tool_name)}' has no setup command declared.")
        print("Add a 'setup' block to the tool's manifest to enable this.")
        return 0

    # Determine the command to run (platform-specific or generic)
    import platform as _platform
    platforms = setup.get("platforms", {})
    system = _platform.system().lower()

    if system == "windows" and "windows" in platforms:
        cmd_str = platforms["windows"]
    elif system == "linux" and "linux" in platforms:
        cmd_str = platforms["linux"]
    elif system == "darwin" and ("macos" in platforms or "darwin" in platforms):
        cmd_str = platforms.get("macos") or platforms.get("darwin")
    else:
        cmd_str = setup.get("command")

    if not cmd_str:
        print(f"No setup command available for platform '{system}'.", file=sys.stderr)
        return 1

    tool_dir = project.get("_dir", ".")
    fqcn = project.get("_fqcn", tool_name)

    print(f"Running setup for {fqcn}...")
    if setup.get("note"):
        print(f"  Note: {setup['note']}")
    print(f"  Command: {cmd_str}")
    print(f"  Working dir: {tool_dir}")
    print()

    import subprocess as _subprocess
    result = _subprocess.run(cmd_str, shell=True, cwd=tool_dir)
    if result.returncode == 0:
        print(f"\nSetup for {fqcn} completed successfully.")
    else:
        print(f"\nSetup for {fqcn} failed with exit code {result.returncode}.", file=sys.stderr)
    return result.returncode


def dispatch_tool(project, argv):
    """Dispatch to a tool's entry point."""
    runner = resolve_entry_point(project)
    if runner is None:
        print(f"Error: Could not resolve entry point for '{project['name']}'", file=sys.stderr)
        return 1

    try:
        return runner(argv)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error running '{project['name']}': {exc}", file=sys.stderr)
        return 1


def main():
    """Main entry point for dazzlecmd CLI.

    Thin wrapper that creates an AggregatorEngine configured for dazzlecmd
    and delegates to engine.run(). The CLI functions (build_parser,
    dispatch_meta, dispatch_tool) are passed as callbacks so the engine
    never imports from cli.py — enabling clean library extraction (#27).
    """
    from dazzlecmd.engine import AggregatorEngine

    engine = AggregatorEngine(
        name="dazzlecmd",
        command="dz",
        tools_dir="projects",
        kits_dir="kits",
        manifest=".dazzlecmd.json",
        description="dazzlecmd - Unified CLI for the DazzleTools collection",
        version_info=(DISPLAY_VERSION, __version__),
        is_root=True,
        parser_builder=build_parser,
        meta_dispatcher=dispatch_meta,
        tool_dispatcher=dispatch_tool,
    )

    return engine.run()
