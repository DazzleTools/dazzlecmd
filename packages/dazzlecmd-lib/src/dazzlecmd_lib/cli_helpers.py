"""CLI scaffolding helpers for aggregator authors.

These are low-level argparse helpers shared across the library's default
meta-commands and available to downstream aggregators that bypass the
``MetaCommandRegistry`` (via the ``parser_builder=`` escape hatch).

**When to use**: if you're writing your own ``parser_builder`` callback
instead of using the registry, import these helpers to avoid duplicating
the standard subparser-scaffolding boilerplate.

**When NOT to use**: if you're using the registry (the default /
recommended path), don't call these directly — the registry's
``build_parsers()`` takes care of parser construction via the
registered factories.
"""

from __future__ import annotations

import sys as _sys
from typing import Iterable, Optional


def build_tool_subparsers(
    subparsers,
    projects: Iterable[dict],
    reserved_commands: Optional[set] = None,
    *,
    add_help: bool = False,
    warn_on_conflict: bool = True,
) -> list:
    """Register one subparser per discovered tool.

    This is the "tool dispatch" half of an aggregator's argparse parser —
    complementing the meta-command subparsers (list, info, etc.) that
    the registry or ``default_meta_commands`` factories install.

    Args:
        subparsers: an ``argparse._SubParsersAction`` obtained from
            ``parser.add_subparsers(...)``.
        projects: iterable of project dicts (each must have a ``name``
            key; ``description`` and ``_fqcn`` are optional).
        reserved_commands: set of names that cannot be used as tool names
            (typically ``engine.reserved_commands``). Tools matching
            reserved names are skipped with a warning to stderr.
        add_help: forwarded to ``add_parser``. Default ``False`` — tools
            handle their own ``--help`` via dispatch.
        warn_on_conflict: if True (default), print a stderr warning for
            tools skipped due to reserved-command collision. Set False
            to silence (test environments, repeated invocations).

    Returns:
        List of the subparsers that were registered. Each has
        ``_project`` set via ``set_defaults`` so the dispatch-side can
        identify which tool was invoked.
    """
    reserved = reserved_commands or set()
    registered = []
    seen_names: set = set()

    for project in projects:
        name = project.get("name")
        if not name:
            continue

        if name in reserved:
            if warn_on_conflict:
                print(
                    f"Warning: Tool {name!r} conflicts with reserved command, skipping",
                    file=_sys.stderr,
                )
            continue

        if name in seen_names:
            # Duplicate short name across kits — skip subsequent ones.
            # The FQCN index handles collision resolution during dispatch;
            # this only affects short-name argparse registration.
            continue
        seen_names.add(name)

        description = project.get("description", "")
        sub = subparsers.add_parser(
            name,
            help=description,
            add_help=add_help,
        )
        sub.set_defaults(_project=project)
        registered.append(sub)

    return registered


def derive_reserved_from_registry(registry, extras: Optional[set] = None) -> set:
    """Combine a registry's registered names with extra reserved names.

    The result is suitable for passing as ``reserved_commands`` to
    ``build_tool_subparsers``. Engine's ``reserved_commands`` property
    uses this pattern internally.

    Args:
        registry: a ``MetaCommandRegistry`` instance.
        extras: optional additional names to reserve (for future
            meta-commands not yet registered, or aggregator-specific
            name guards).

    Returns:
        Set of reserved command names.
    """
    names = set(registry.registered()) if registry is not None else set()
    if extras:
        names = names | set(extras)
    return names


def add_version_flag(parser, version_info=None, app_name: Optional[str] = None):
    """Attach a ``--version`` / ``-V`` flag to the given parser.

    Produces output like ``wtf-windows 0.1.3 (0.1.3_main_5-20260418-abc123)``
    when ``version_info`` is a ``(display, full)`` tuple, or just the
    app name when ``version_info`` is None.

    Typically called on the top-level argparse parser during
    aggregator ``main()``. No-op if ``parser`` is None.
    """
    if parser is None:
        return
    if version_info:
        display, full = version_info
        name = app_name or "aggregator"
        version_string = f"{name} {display} ({full})"
    else:
        version_string = app_name or "aggregator"
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=version_string,
    )


def default_epilog_for(app_name: str, tool_count: int, kit_count: int = 0) -> str:
    """Produce a generic epilog string for aggregators without custom epilog.

    Used by the engine when ``epilog_builder`` isn't set. Aggregators
    with domain-specific help (wtf-style diagnostic badges, dazzlecmd's
    tree-organized categorization) provide their own ``epilog_builder``.
    """
    lines = []
    if tool_count > 0:
        lines.append(f"{tool_count} tool(s)" + (f" across {kit_count} kit(s)" if kit_count else ""))
    lines.append(f"Run '{app_name} list' to see available tools.")
    lines.append(f"Run '{app_name} <tool> --help' for tool-specific options.")
    return "\n".join(lines)
