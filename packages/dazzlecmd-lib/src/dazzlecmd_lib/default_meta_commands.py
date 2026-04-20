"""Default meta-commands for dazzlecmd-pattern aggregators.

Exposes the built-in ``list``, ``info``, ``kit``, ``version``, ``tree``,
and ``setup`` commands as parser factories + handlers + render functions.
``AggregatorEngine`` auto-registers them on construction via
``register_all()``; aggregators can opt out (``include_default_meta_commands=False``),
unregister specific ones (``engine.meta_registry.unregister("tree")``),
or override them (``engine.meta_registry.override("info", handler=...)``).

Public surface for aggregator authors:

- ``render_*(args, projects, ...) -> int``: the printing logic for each
  command, decoupled from engine context. Import these to **compose** —
  call ``render_info()`` from your override, then append domain fields.

- ``*_parser_factory(subparsers)``: argparse subparser setup. Import
  these to reuse the argument shape while replacing the handler.

- ``*_handler(args, engine, projects, kits, project_root) -> int``: the
  handlers the registry calls. These are thin wrappers around ``render_*``
  that unpack engine context. Override at the handler level when your
  domain logic needs ``engine`` or ``project_root``.

- ``register_all(registry)``: bulk-register every default. Invoked by the
  engine at construction time.

- ``register_selected(registry, include=[...])``: opt-in helper — register
  only the defaults you want.

These implementations are intentionally **minimal**. They cover the
common-case output for a generic aggregator. Aggregators with rich
domain fields (diagnostic badges, Docker-specific rendering, collision
markers, terminal-width wrapping, etc.) should override the handler and
compose with the stock render function OR replace it outright.
"""

from __future__ import annotations

import json as _json
import os as _os
import sys as _sys
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def list_parser_factory(subparsers):
    """Register the ``list`` subparser.

    Flags:
        --namespace / -n: filter by namespace
        --kit / -k: filter by kit import name
        --tag / -t: filter by taxonomy.tags
        --platform / -p: filter by platform
    """
    p = subparsers.add_parser("list", help="List available tools")
    p.add_argument("--namespace", "-n", help="Filter by namespace")
    p.add_argument("--kit", "-k", help="Filter by kit")
    p.add_argument("--tag", "-t", help="Filter by tag")
    p.add_argument("--platform", "-p", help="Filter by platform")
    p.set_defaults(_meta="list")


def render_list(args, projects) -> int:
    """Print a table of tools, optionally filtered.

    This is the pure printing function — aggregators can import and call
    it from their own handler, optionally appending domain-specific
    output afterwards.
    """
    filtered = list(projects)

    ns = getattr(args, "namespace", None)
    plat = getattr(args, "platform", None)
    tag = getattr(args, "tag", None)
    kit = getattr(args, "kit", None)

    if ns:
        filtered = [p for p in filtered if p.get("namespace") == ns]
    if plat:
        filtered = [
            p for p in filtered
            if p.get("platform", "cross-platform") == plat
        ]
    if tag:
        filtered = [
            p for p in filtered
            if tag in p.get("taxonomy", {}).get("tags", [])
        ]
    if kit:
        filtered = [p for p in filtered if p.get("_kit_import_name") == kit]

    if not filtered:
        print("No tools found.")
        return 0

    # Column widths
    name_width = max(len(p["name"]) for p in filtered)
    name_width = max(name_width, len("Name"))
    kit_col_width = max(
        (len(p.get("_kit_import_name", "")) for p in filtered),
        default=0,
    )
    kit_col_width = max(kit_col_width, len("Kit"))

    header = f"  {'Name':<{name_width}}  {'Kit':<{kit_col_width}}  Description"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for project in filtered:
        name = project["name"]
        kit_name = project.get("_kit_import_name", "")
        desc = project.get("description", "")
        if len(desc) > 60:
            desc = desc[:57] + "..."
        print(f"  {name:<{name_width}}  {kit_name:<{kit_col_width}}  {desc}")

    print(f"\n  {len(filtered)} tool(s) found")
    return 0


def list_handler(args, engine, projects, kits, project_root) -> int:
    """Default handler for ``list``. Delegates to ``render_list``."""
    return render_list(args, projects)


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


def info_parser_factory(subparsers):
    """Register the ``info`` subparser.

    Flags:
        tool: tool name or FQCN to inspect
    """
    p = subparsers.add_parser("info", help="Show detailed info about a tool")
    p.add_argument("tool", help="Tool name or FQCN to inspect")
    p.set_defaults(_meta="info")


def render_info(args, projects, engine=None) -> int:
    """Print basic info for a tool identified by name or FQCN.

    Aggregators with domain-specific fields (diagnostics, taxonomy,
    custom runtime rendering) should override this via
    ``registry.override("info", handler=...)`` and optionally call
    ``render_info()`` themselves to emit the standard fields first.

    If ``engine`` is provided, FQCN lookups route through ``engine.resolve``
    so that virtual-kit alias FQCNs resolve to their canonical projects.
    """
    tool_name = args.tool
    matches = []
    if ":" in tool_name and engine is not None:
        # Route through resolve_command() to pick up alias FQCNs from
        # virtual kits. Falls back to direct comparison if engine lookup
        # returns nothing.
        project, _note = engine.resolve_command(tool_name)
        if project is not None:
            matches = [project]
    elif ":" in tool_name:
        matches = [p for p in projects if p.get("_fqcn") == tool_name]
    else:
        matches = [p for p in projects if p["name"] == tool_name]

    if not matches:
        print(
            f"Tool {tool_name!r} not found. Run 'list' to see available tools.",
            file=_sys.stderr,
        )
        return 1

    if len(matches) > 1:
        print(f"Multiple tools named {tool_name!r}:")
        for p in matches:
            print(f"  {p.get('_fqcn', p['name'])}")
        print("Use 'info <fqcn>' to disambiguate.")
        return 1

    project = matches[0]
    print(f"Name:        {project['name']}")
    if project.get("_fqcn"):
        print(f"FQCN:        {project['_fqcn']}")
    if project.get("_kit_import_name"):
        print(f"Kit:         {project['_kit_import_name']}")
    if project.get("namespace"):
        print(f"Namespace:   {project['namespace']}")
    print(f"Version:     {project.get('version', 'unknown')}")
    print(f"Description: {project.get('description', '')}")
    print(f"Platform:    {project.get('platform', 'cross-platform')}")
    if project.get("language"):
        print(f"Language:    {project['language']}")

    runtime = project.get("runtime", {})
    if runtime:
        print(f"Runtime:     {runtime.get('type', 'python')}")
        if runtime.get("script_path"):
            print(f"Script:      {runtime['script_path']}")
        if runtime.get("interpreter"):
            print(f"Interpreter: {runtime['interpreter']}")

    taxonomy = project.get("taxonomy", {})
    if taxonomy.get("category"):
        print(f"Category:    {taxonomy['category']}")
    if taxonomy.get("tags"):
        print(f"Tags:        {', '.join(taxonomy['tags'])}")

    setup = project.get("setup")
    if setup:
        note = setup.get("note") if isinstance(setup, dict) else None
        cmd_preview = None
        if isinstance(setup, dict):
            cmd_preview = setup.get("command")
        print(f"Setup:       {note or cmd_preview or 'available'}")

    return 0


def info_handler(args, engine, projects, kits, project_root) -> int:
    """Default handler for ``info``. Delegates to ``render_info``."""
    return render_info(args, projects, engine=engine)


# ---------------------------------------------------------------------------
# kit (list + status)
# ---------------------------------------------------------------------------


def kit_parser_factory(subparsers):
    """Register the ``kit`` subparser and its nested ``list``/``status``."""
    p = subparsers.add_parser("kit", help="Manage kits")
    sub = p.add_subparsers(dest="kit_command")

    kit_list_p = sub.add_parser(
        "list", help="List available kits, or tools in a kit"
    )
    kit_list_p.add_argument(
        "name", nargs="?", default=None, help="Kit name to show tools for"
    )
    kit_list_p.set_defaults(_meta="kit_list")

    kit_status_p = sub.add_parser("status", help="Show active kits")
    kit_status_p.set_defaults(_meta="kit_status")

    # Bare `kit` with no sub is treated as `kit list`
    p.set_defaults(_meta="kit_list")


def render_kit_list(args, kits, projects) -> int:
    """List all kits or tools in a specific kit.

    Generic over any kit format — reads ``_kit_name`` / ``name``,
    ``description``, ``tools``, and ``always_active`` fields.
    """
    if not kits:
        print("No kits found.")
        return 0

    kit_name = getattr(args, "name", None)

    if kit_name:
        matching = [
            k for k in kits
            if (k.get("_kit_name") or k.get("name")) == kit_name
        ]
        if not matching:
            print(f"Kit {kit_name!r} not found. Available kits:")
            for k in kits:
                print(f"  {k.get('_kit_name') or k.get('name')}")
            return 1

        kit = matching[0]
        name = kit.get("_kit_name") or kit.get("name")
        active = " (always active)" if kit.get("always_active") else ""
        print(f"Kit: {name}{active}")
        if kit.get("description"):
            print(f"  {kit['description']}")
        print()

        tool_refs = kit.get("tools", [])
        if not tool_refs:
            print("  No tools in this kit.")
            return 0

        for ref in sorted(tool_refs):
            if ":" in ref:
                ns, name_part = ref.split(":", 1)
            else:
                ns, name_part = "", ref
            match = [
                p for p in projects
                if p["name"] == name_part
                and (not ns or p.get("namespace") == ns)
            ]
            if match:
                p = match[0]
                desc = p.get("description", "")
                if len(desc) > 55:
                    desc = desc[:52] + "..."
                platform = p.get("platform", "")
                print(f"  {name_part:<16} {platform:<16} {desc}")
            else:
                print(f"  {name_part:<16} {'':16} (not found)")
        print(f"\n  {len(tool_refs)} tool(s)")
        return 0

    # No kit name — list all kits
    for i, kit in enumerate(kits):
        if i > 0:
            print()
        name = kit.get("_kit_name") or kit.get("name")
        active = " (always active)" if kit.get("always_active") else ""
        tool_count = len(kit.get("tools", []))
        print(f"  {name:<16} {tool_count} tool(s){active}")
        if kit.get("description"):
            print(f"    {kit['description']}")
    return 0


def render_kit_status(kits) -> int:
    """Show a summary of active kits."""
    active = [k for k in kits if k.get("always_active")] or list(kits)
    print(f"Active kits: {len(active)}")
    for kit in active:
        name = kit.get("_kit_name") or kit.get("name")
        tool_count = len(kit.get("tools", []))
        print(f"  {name}: {tool_count} tool(s)")
    return 0


def kit_list_handler(args, engine, projects, kits, project_root) -> int:
    return render_kit_list(args, kits, projects)


def kit_status_handler(args, engine, projects, kits, project_root) -> int:
    return render_kit_status(kits)


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def version_parser_factory(subparsers):
    p = subparsers.add_parser("version", help="Show version info")
    p.set_defaults(_meta="version")


def render_version(engine) -> int:
    """Print the aggregator's version string.

    Uses ``engine.version_info`` if set (tuple of
    ``(display_version, full_version)``). Falls back to
    ``engine.name`` alone if version_info is absent.
    """
    if engine is not None and getattr(engine, "version_info", None):
        display, full = engine.version_info
        name = getattr(engine, "name", "aggregator")
        print(f"{name} {display} ({full})")
    elif engine is not None:
        print(getattr(engine, "name", "aggregator"))
    else:
        print("(no version info)")
    return 0


def version_handler(args, engine, projects, kits, project_root) -> int:
    return render_version(engine)


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------


def tree_parser_factory(subparsers):
    p = subparsers.add_parser(
        "tree",
        help="Visualize the aggregator tree (kits and tools)",
    )
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument(
        "--depth", type=int, default=None,
        help="Limit display depth (1=kits only, 2+=include tools)",
    )
    p.add_argument(
        "--kit", "-k", default=None,
        help="Show only this kit's subtree",
    )
    p.set_defaults(_meta="tree")


def render_tree(args, engine, projects, kits, project_root) -> int:
    """Render an ASCII tree (or JSON) of kits and their tools.

    Groups projects by ``_kit_import_name``. Each tool prints its FQCN
    and (truncated) description.
    """
    if engine is None:
        print("Error: tree requires engine context", file=_sys.stderr)
        return 1

    as_json = getattr(args, "json", False)
    depth_limit = getattr(args, "depth", None)
    kit_filter = getattr(args, "kit", None)

    by_kit: dict[str, list] = {}
    for project in projects:
        kit_name = project.get("_kit_import_name", "?")
        by_kit.setdefault(kit_name, []).append(project)

    kit_names = sorted(by_kit.keys())
    if kit_filter:
        kit_names = [k for k in kit_names if k == kit_filter]
        if not kit_names:
            print(f"Error: kit {kit_filter!r} not found.", file=_sys.stderr)
            return 1

    if as_json:
        result = {
            "root": getattr(engine, "name", "aggregator"),
            "command": getattr(engine, "command", ""),
            "tools_dir": getattr(engine, "tools_dir", ""),
            "kits": {},
        }
        for kit_name in kit_names:
            tools_data = []
            for project in sorted(by_kit[kit_name], key=lambda p: p.get("_fqcn", "")):
                tools_data.append({
                    "fqcn": project.get("_fqcn", ""),
                    "short": project.get("_short_name", project.get("name", "")),
                    "description": project.get("description", ""),
                })
            result["kits"][kit_name] = {
                "name": kit_name,
                "tools": tools_data,
            }
        print(_json.dumps(result, indent=2))
        return 0

    # ASCII tree
    header = getattr(engine, "command", "root")
    if getattr(engine, "version_info", None):
        display, _ = engine.version_info
        name = getattr(engine, "name", "")
        header = f"{engine.command} ({name} {display})"
    print(header)

    total_tools = 0
    for i, kit_name in enumerate(kit_names):
        is_last_kit = (i == len(kit_names) - 1)
        kit_prefix = "\\-- " if is_last_kit else "+-- "
        print(f"{kit_prefix}{kit_name}")

        tools = sorted(by_kit[kit_name], key=lambda p: p.get("_fqcn", ""))
        total_tools += len(tools)

        if depth_limit is not None and depth_limit < 2:
            continue

        branch_indent = "    " if is_last_kit else "|   "
        for j, project in enumerate(tools):
            is_last_tool = (j == len(tools) - 1)
            tool_prefix = "\\-- " if is_last_tool else "+-- "
            fqcn = project.get("_fqcn", project.get("name", ""))
            desc = project.get("description", "")
            if len(desc) > 60:
                desc = desc[:57] + "..."
            print(f"{branch_indent}{tool_prefix}{fqcn}  {desc}")

    print()
    print(f"{total_tools} tools across {len(kit_names)} kit(s)")
    return 0


def tree_handler(args, engine, projects, kits, project_root) -> int:
    return render_tree(args, engine, projects, kits, project_root)


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


def setup_parser_factory(subparsers):
    p = subparsers.add_parser(
        "setup",
        help="Run a tool's declared setup script (install deps, build, etc.)",
    )
    p.add_argument(
        "tool", nargs="?", default=None,
        help="Tool name or FQCN. Omit to list tools with setup declared.",
    )
    p.set_defaults(_meta="setup")


def render_setup_listing(projects) -> int:
    """List tools that declare a setup block.

    Used when ``setup`` is invoked without a tool argument.
    """
    def _has_setup(project):
        setup = project.get("setup")
        if not isinstance(setup, dict):
            return False
        if setup.get("command"):
            return True
        if setup.get("steps"):
            return True
        if setup.get("script"):
            return True
        platforms = setup.get("platforms")
        if isinstance(platforms, dict) and platforms:
            return True
        return False

    with_setup = [p for p in projects if _has_setup(p)]
    if not with_setup:
        print("No tools have setup declared.")
        return 0

    with_setup.sort(key=lambda p: p.get("_fqcn", p.get("name", "")))
    longest = max(
        len(p.get("_fqcn", p.get("name", ""))) for p in with_setup
    )
    col_width = max(20, min(50, longest))

    print("Tools with setup declared:\n")
    for project in with_setup:
        fqcn = project.get("_fqcn", project.get("name", ""))
        setup = project.get("setup", {})
        note = setup.get("note") if isinstance(setup, dict) else None
        note = note or "-"
        print(f"  {fqcn:<{col_width}}  {note}")
    print("\nRun: setup <tool> to execute a tool's setup.")
    return 0


def setup_handler(args, engine, projects, kits, project_root) -> int:
    """Default handler for ``setup``.

    With no tool argument: lists tools that declare a setup block.
    With a tool argument: resolves the tool's setup block (platform +
    user overrides + _vars) and executes the resolved command.
    """
    tool_name = getattr(args, "tool", None)

    if not tool_name:
        return render_setup_listing(projects)

    # Resolve the tool
    if ":" in tool_name:
        matches = [p for p in projects if p.get("_fqcn") == tool_name]
    else:
        matches = [p for p in projects if p["name"] == tool_name]

    if not matches:
        print(f"Tool {tool_name!r} not found.", file=_sys.stderr)
        return 1

    if len(matches) > 1:
        print(f"Multiple tools named {tool_name!r}:", file=_sys.stderr)
        for p in matches:
            print(f"  {p.get('_fqcn', p['name'])}", file=_sys.stderr)
        return 1

    project = matches[0]
    setup = project.get("setup")
    if not setup:
        print(
            f"Tool {project.get('_fqcn', project['name'])!r} has no setup declared.",
            file=_sys.stderr,
        )
        return 1

    # Resolve the setup block via the library's resolver (handles
    # platform selection, user overrides, _vars substitution).
    try:
        from dazzlecmd_lib.setup_resolve import resolve_setup_block

        resolved = resolve_setup_block(project)
    except _json.JSONDecodeError as exc:
        print(
            f"Error: user override file is not valid JSON: {exc}",
            file=_sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"Error: cannot read user override file: {exc}", file=_sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error resolving setup: {exc}", file=_sys.stderr)
        return 1

    if resolved is None:
        print(
            f"Tool {project.get('_fqcn', project['name'])!r} has no executable setup.",
            file=_sys.stderr,
        )
        return 1

    command = resolved.get("command")
    if not command:
        print(
            f"Tool {project.get('_fqcn', project['name'])!r} has no setup command "
            f"for this platform.",
            file=_sys.stderr,
        )
        return 1

    # Execute the resolved command. The engine is a dumb dispatcher —
    # we run the author-declared command via the platform shell.
    import subprocess as _subprocess

    print(f"Running setup for {project.get('_fqcn', project['name'])}...")
    print(f"  {command}")
    _sys.stdout.flush()  # flush before subprocess to avoid output interleaving

    result = _subprocess.run(command, shell=True, cwd=project.get("_dir"))
    return result.returncode


# ---------------------------------------------------------------------------
# Bulk registration
# ---------------------------------------------------------------------------


# Canonical mapping: meta-command name -> (parser_factory, handler)
_DEFAULTS = {
    "list": (list_parser_factory, list_handler),
    "info": (info_parser_factory, info_handler),
    "kit": (kit_parser_factory, kit_list_handler),  # parser sets _meta=kit_list by default
    "version": (version_parser_factory, version_handler),
    "tree": (tree_parser_factory, tree_handler),
    "setup": (setup_parser_factory, setup_handler),
}

# Sub-meta handlers (kit has kit_list and kit_status sub-commands).
# These are separately registered so the engine's dispatch can route
# kit_status -> kit_status_handler.
_SUB_HANDLERS = {
    "kit_list": kit_list_handler,
    "kit_status": kit_status_handler,
}


def register_all(registry) -> None:
    """Register every default meta-command against the given registry.

    Called by ``AggregatorEngine.__init__`` when
    ``include_default_meta_commands=True`` (the default).

    This registers the top-level commands (list, info, kit, version,
    tree, setup). Nested meta tags (kit_list, kit_status) are registered
    via ``_register_sub_handlers`` so the registry's dispatch can route
    them.
    """
    for name, (parser_factory, handler) in _DEFAULTS.items():
        registry.register(name, parser_factory, handler)
    _register_sub_handlers(registry)


def register_selected(
    registry, include: Optional[Iterable[str]] = None
) -> None:
    """Register only the named defaults.

    Useful when an aggregator wants an explicit subset. Unknown names
    raise ``KeyError``.

    Example::

        register_selected(registry, include=["list", "info", "version"])
        # tree, setup, kit excluded
    """
    if include is None:
        register_all(registry)
        return

    for name in include:
        if name not in _DEFAULTS:
            raise KeyError(
                f"Unknown default meta-command: {name!r}. "
                f"Available: {sorted(_DEFAULTS.keys())}"
            )
        parser_factory, handler = _DEFAULTS[name]
        registry.register(name, parser_factory, handler)

    # If kit is included, also register the sub handlers
    if "kit" in include:
        _register_sub_handlers(registry)


def _register_sub_handlers(registry) -> None:
    """Register the sub-meta handlers (kit_list, kit_status).

    These don't have parser factories (the kit parser factory builds
    the nested subparsers); they only need dispatch-side routing entries
    so ``args._meta = "kit_status"`` resolves to the right handler.
    """
    # A minimal "parser factory" that does nothing — the kit parser
    # already built the subparser when kit was registered.
    def _noop_parser(subparsers):
        pass

    for name, handler in _SUB_HANDLERS.items():
        if name not in registry:
            registry.register(name, _noop_parser, handler)
