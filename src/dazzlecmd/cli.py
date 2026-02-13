"""Main CLI entry point for dazzlecmd."""

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
    "build", "tree", "version", "enhance", "graduate",
}


def find_project_root():
    """Find the dazzlecmd project root by navigating from __file__.

    Looks for the presence of both projects/ and kits/ directories.
    """
    # Start from the package location and go up
    current = os.path.dirname(os.path.abspath(__file__))

    # In installed mode: __file__ is in site-packages/dazzlecmd/
    # In dev mode: __file__ is in src/dazzlecmd/
    # Either way, we need to find projects/ and kits/ relative to the repo root

    for _ in range(5):  # Don't go more than 5 levels up
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
        if os.path.isdir(os.path.join(current, "projects")) and os.path.isdir(
            os.path.join(current, "kits")
        ):
            return current

    return None


def build_parser(projects):
    """Build argparse parser with dynamic subparsers for discovered tools."""
    parser = argparse.ArgumentParser(
        prog="dz",
        description="dazzlecmd - Unified CLI for the DazzleTools collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"dazzlecmd {DISPLAY_VERSION} ({__version__})",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Register meta-commands
    _register_meta_commands(subparsers)

    # Register discovered tool commands
    for project in projects:
        name = project["name"]
        if name in RESERVED_COMMANDS:
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
    new_parser.add_argument("--simple", action="store_true", help="Add TODO.md and NOTES.md")
    new_parser.add_argument("--full", action="store_true", help="Add ROADMAP.md, private/claude/, tests/")
    new_parser.add_argument("--description", "-d", default="", help="Tool description")
    new_parser.add_argument("--language", "-l", default="python", help="Primary language (default: python)")
    new_parser.set_defaults(_meta="new")

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

    for project in filtered:
        name = project["name"]
        ns = project.get("namespace", "")
        desc = project.get("description", "")
        # Truncate description if too long
        if len(desc) > 60:
            desc = desc[:57] + "..."
        print(f"  {name:<{name_width}}  {ns:<{ns_width}}  {desc}")

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
    """Main entry point for dazzlecmd CLI."""
    project_root = find_project_root()

    if project_root is None:
        # Installed mode without project root — show basic help
        parser = build_parser([])
        if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
            print(f"dazzlecmd {DISPLAY_VERSION} ({__version__})")
            return 0
        parser.print_help()
        return 0

    # Discover kits and projects
    kits_dir = os.path.join(project_root, "kits")
    projects_dir = os.path.join(project_root, "projects")

    kits = discover_kits(kits_dir)
    active_kits = get_active_kits(kits)
    projects = discover_projects(projects_dir, active_kits)

    # Build parser with discovered tools
    parser = build_parser(projects)

    # Handle no arguments
    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    # For tool commands, we need to separate dz args from tool args
    command_name = sys.argv[1]

    # Check if it's a meta-command
    meta_commands = {"list", "info", "kit", "new", "version"}
    if command_name in meta_commands or command_name.startswith("-"):
        args = parser.parse_args()
        if hasattr(args, "_meta"):
            return dispatch_meta(args, projects, kits, project_root)
        return 0

    # Check if it's a tool command
    tool_matches = [p for p in projects if p["name"] == command_name]
    if tool_matches:
        project = tool_matches[0]
        # Pass remaining args to the tool
        tool_argv = sys.argv[2:]
        return dispatch_tool(project, tool_argv)

    # Unknown command — try argparse for error message
    args = parser.parse_args()
    return 0
