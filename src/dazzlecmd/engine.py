"""Generic aggregator engine for dazzlecmd and compatible projects.

The AggregatorEngine is the shared core that powers any tool aggregator.
dazzlecmd, wtf-windows, and future aggregators are all instances of this
engine configured with different data (command name, directory layout,
manifest filename, etc.).

Usage:
    from dazzlecmd.engine import AggregatorEngine

    engine = AggregatorEngine(
        name="my-tools",
        command="mt",
        tools_dir="tools",
        kits_dir="kits",
        manifest=".mt.json",
        description="My tool collection",
    )

    def main():
        return engine.run()
"""

import os
import sys

from dazzlecmd.loader import (
    discover_kits,
    discover_projects,
    get_active_kits,
    resolve_entry_point,
)


class AggregatorEngine:
    """A configurable CLI tool aggregator.

    Each instance represents a specific aggregator (dazzlecmd, wtf-windows,
    etc.) with its own command name, directory layout, and manifest format.
    The engine handles kit discovery, tool loading, parser building, and
    dispatch.
    """

    def __init__(
        self,
        name="dazzlecmd",
        command="dz",
        tools_dir="projects",
        kits_dir="kits",
        manifest=".dazzlecmd.json",
        description=None,
        version_info=None,
        is_root=True,
    ):
        """Initialize the aggregator engine.

        Args:
            name: Human-readable name (e.g., "dazzlecmd", "wtf-windows")
            command: CLI command name (e.g., "dz", "wtf")
            tools_dir: Directory name for tool projects (e.g., "projects", "tools")
            kits_dir: Directory name for kit definitions (e.g., "kits")
            manifest: Default manifest filename (e.g., ".dazzlecmd.json", ".wtf.json")
            description: One-line description for --help
            version_info: Tuple of (display_version, full_version) or None
            is_root: If True, register meta-commands (list, info, kit, etc.).
                     If False (imported as kit), suppress meta-commands.
        """
        self.name = name
        self.command = command
        self.tools_dir = tools_dir
        self.kits_dir = kits_dir
        self.manifest = manifest
        self.description = description or f"{name} - tool aggregator"
        self.version_info = version_info
        self.is_root = is_root

        # Resolved at run time
        self.project_root = None
        self.kits = []
        self.active_kits = []
        self.projects = []

    def find_project_root(self, start_path=None):
        """Find the project root by looking for tools_dir/ and kits_dir/.

        Walks up from start_path (or the engine module location) looking
        for a directory that contains both the tools and kits directories.
        """
        if start_path:
            current = os.path.abspath(start_path)
        else:
            current = os.path.dirname(os.path.abspath(__file__))

        for _ in range(5):
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
            if (os.path.isdir(os.path.join(current, self.tools_dir)) and
                    os.path.isdir(os.path.join(current, self.kits_dir))):
                return current

        return None

    def discover(self, project_root=None):
        """Run the full discovery pipeline: kits -> active kits -> projects."""
        if project_root:
            self.project_root = project_root
        elif self.project_root is None:
            self.project_root = self.find_project_root()

        if self.project_root is None:
            return

        kits_path = os.path.join(self.project_root, self.kits_dir)
        tools_path = os.path.join(self.project_root, self.tools_dir)

        self.kits = discover_kits(kits_path, tools_path)
        self.active_kits = get_active_kits(self.kits)
        self.projects = discover_projects(tools_path, self.active_kits)

    def run(self, argv=None):
        """Run the aggregator: discover, parse, dispatch.

        This is the main entry point for the CLI. Equivalent to cli.py:main().
        """
        # Import here to avoid circular imports -- cli.py uses the engine,
        # and the engine delegates display/dispatch back to cli functions
        from dazzlecmd.cli import (
            build_parser,
            dispatch_meta,
            dispatch_tool,
        )

        if argv is None:
            argv = sys.argv[1:]

        self.discover()

        if self.project_root is None:
            # No project root found -- show basic help
            parser = build_parser([], engine=self)
            if argv and argv[0] in ("--version", "-V") and self.version_info:
                display, full = self.version_info
                print(f"{self.name} {display} ({full})")
                return 0
            parser.print_help()
            return 0

        parser = build_parser(self.projects, engine=self)

        if not argv:
            parser.print_help()
            return 0

        command_name = argv[0]

        # Meta-commands (only if is_root)
        if self.is_root:
            meta_commands = {"list", "info", "kit", "new", "version", "add", "mode"}
            if command_name in meta_commands or command_name.startswith("-"):
                sys_argv_backup = sys.argv
                sys.argv = [self.command] + list(argv)
                try:
                    args = parser.parse_args()
                    if hasattr(args, "_meta"):
                        return dispatch_meta(
                            args, self.projects, self.kits, self.project_root
                        )
                finally:
                    sys.argv = sys_argv_backup
                return 0

        # Tool dispatch
        tool_matches = [p for p in self.projects if p["name"] == command_name]
        if tool_matches:
            project = tool_matches[0]
            tool_argv = argv[1:]
            return dispatch_tool(project, tool_argv)

        # Unknown command
        sys_argv_backup = sys.argv
        sys.argv = [self.command] + list(argv)
        try:
            parser.parse_args()
        finally:
            sys.argv = sys_argv_backup
        return 1

    @property
    def reserved_commands(self):
        """Commands reserved by the engine (not available as tool names)."""
        if self.is_root:
            return {
                "new", "add", "list", "info", "kit", "search",
                "build", "tree", "version", "enhance", "graduate", "mode",
            }
        return set()
