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
        ("version", "Show version info"),
    ]

    # Group tools by namespace (kit)
    namespaces = {}
    for project in projects:
        name = project["name"]
        if name in RESERVED_COMMANDS:
            continue
        ns = project.get("namespace", "other")
        desc = project.get("description", "")
        namespaces.setdefault(ns, []).append((name, desc))

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
    kit_list = kit_sub.add_parser("list", help="List available kits, or tools in a kit")
    kit_list.add_argument("name", nargs="?", default=None, help="Kit name to show tools for")
    kit_list.set_defaults(_meta="kit_list")
    kit_status = kit_sub.add_parser("status", help="Show active kits")
    kit_status.set_defaults(_meta="kit_status")
    kit_parser.set_defaults(_meta="kit")

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


def dispatch_meta(args, projects, kits, project_root):
    """Handle built-in meta-commands."""
    meta = getattr(args, "_meta", None)

    if meta == "list":
        return _cmd_list(args, projects)
    elif meta == "info":
        return _cmd_info(args, projects)
    elif meta == "kit_list":
        return _cmd_kit_list(args, kits, projects)
    elif meta == "kit_status":
        return _cmd_kit_status(kits)
    elif meta == "kit":
        # bare "dz kit" with no subcommand
        return _cmd_kit_list(args, kits, projects)
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


def _cmd_list(args, projects):
    """List available tools."""
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
        # Filter by kit name — find tools in that kit
        kit_tools = set()
        # We'd need access to kits here; for now filter by namespace as proxy
        filtered = [p for p in filtered if p.get("namespace") == args.kit]

    if not filtered:
        print("No tools found.")
        return 0

    # Table output
    name_width = max(len(p["name"]) for p in filtered)
    ns_width = max(len(p.get("namespace", "")) for p in filtered)

    header = f"  {'Name':<{name_width}}  {'Namespace':<{ns_width}}  Description"
    print(header)
    print("  " + "-" * (len(header) - 2))

    import shutil
    term_width = shutil.get_terminal_size((80, 24)).columns
    # Column where description starts
    desc_col = 2 + name_width + 2 + ns_width + 2  # indent + name + gap + ns + gap
    desc_max = term_width - desc_col

    for project in filtered:
        name = project["name"]
        ns = project.get("namespace", "")
        desc = project.get("description", "")
        wrapped = _wrap_description(desc, desc_max)
        # First line includes name and namespace
        print(f"  {name:<{name_width}}  {ns:<{ns_width}}  {wrapped[0]}")
        # Continuation lines aligned to description column
        indent = " " * desc_col
        for line in wrapped[1:]:
            print(f"{indent}{line}")

    print(f"\n  {len(filtered)} tool(s) found")
    return 0


def _cmd_info(args, projects):
    """Show detailed info about a tool."""
    tool_name = args.tool
    matches = [p for p in projects if p["name"] == tool_name]

    if not matches:
        print(f"Tool '{tool_name}' not found. Use 'dz list' to see available tools.")
        return 1

    if len(matches) > 1:
        print(f"Multiple tools named '{tool_name}':")
        for p in matches:
            print(f"  {p['namespace']}:{p['name']}")
        print(f"Use 'dz info namespace:{tool_name}' to be specific.")
        return 1

    project = matches[0]
    print(f"Name:        {project['name']}")
    print(f"Namespace:   {project.get('namespace', 'unknown')}")
    print(f"Version:     {project.get('version', 'unknown')}")
    print(f"Description: {project.get('description', '')}")
    print(f"Platform:    {project.get('platform', 'cross-platform')}")
    print(f"Language:    {project.get('language', 'unknown')}")

    runtime = project.get("runtime", {})
    print(f"Runtime:     {runtime.get('type', 'python')}")
    if runtime.get("script_path"):
        print(f"Script:      {runtime['script_path']}")
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

    # Show link status
    from dazzlecmd.importer import is_linked_project, get_link_target
    if is_linked_project(project["_dir"]):
        target = get_link_target(project["_dir"])
        print(f"Linked to:   {target or 'unknown'}")

    return 0


def _cmd_kit_list(args, kits, projects):
    """List available kits, or tools in a specific kit."""
    kit_name = getattr(args, "name", None)

    if not kits:
        print("No kits found.")
        return 0

    if kit_name:
        # Show tools in a specific kit
        matching = [k for k in kits if k["name"] == kit_name]
        if not matching:
            print(f"Kit '{kit_name}' not found. Available kits:")
            for k in kits:
                print(f"  {k['name']}")
            return 1

        kit = matching[0]
        active = " (always active)" if kit.get("always_active") else ""
        print(f"Kit: {kit['name']}{active}")
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

    # No name given — list all kits
    for kit in kits:
        active = " (always active)" if kit.get("always_active") else ""
        tool_count = len(kit.get("tools", []))
        print(f"  {kit['name']:<16} {tool_count} tool(s){active}")
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
            "status": "active",
        },
    }

    manifest_path = os.path.join(tool_dir, ".dazzlecmd.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
        f.write("\n")

    # Create starter script (always)
    script_name = f"{name.replace('-', '_')}.py"
    script_path = os.path.join(tool_dir, script_name)

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
    and delegates to engine.run().
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
    )

    return engine.run()
