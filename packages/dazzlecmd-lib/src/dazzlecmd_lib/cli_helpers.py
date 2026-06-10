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
from typing import Any, Iterable, Optional

from . import colors as _colors


def build_tool_subparsers(
    subparsers,
    projects: Iterable[Any],  # DazzleEntity instances or plain manifest dicts
    reserved_commands: Optional[set] = None,
    *,
    add_help: bool = False,
    warn_on_conflict: bool = True,
    exempt_from_warning: Optional[set] = None,
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
        exempt_from_warning: optional set of names that are exempt from
            the conflict warning. Used by the engine to pass
            ``meta_registry.user_overrides()`` so deliberately-overridden
            meta-commands don't fire the warning on every invocation.
            Names in this set still skip parser registration (the meta-
            command's parser wins), but no warning is emitted — the
            override is the acknowledgment.

    Returns:
        List of the subparsers that were registered. Each has
        ``_project`` set via ``set_defaults`` so the dispatch-side can
        identify which tool was invoked.
    """
    reserved = reserved_commands or set()
    exempt = exempt_from_warning or set()
    registered = []
    seen_names: set = set()

    for project in projects:
        if isinstance(project, dict):
            name = project.get("name")
        else:
            name = project.name
        if not name:
            continue

        if name in reserved:
            if warn_on_conflict and name not in exempt:
                # As of issue #67's redesign, shadowed tools WIN short-name
                # dispatch (engine._dispatch_registry_path checks tool
                # lookup before the meta-command path). The argparse
                # subparser is still skipped here because argparse can't
                # carry two subparsers with the same name; the meta-
                # command's subparser stays registered but is unreachable
                # by short name (FQCN access for meta-commands is a
                # planned future enhancement). The warning tells aggregator
                # authors about the collision so they can rename or
                # consciously accept the shadowing.
                print(
                    _colors.warn(
                        f"Warning: Tool {name!r} shadows reserved meta-command -- tool wins short-name dispatch"
                    ),
                    file=_sys.stderr,
                )
            continue

        if name in seen_names:
            # Duplicate short name across kits — skip subsequent ones.
            # The FQCN index handles collision resolution during dispatch;
            # this only affects short-name argparse registration.
            continue
        seen_names.add(name)

        if isinstance(project, dict):
            description = project.get("description") or ""
        else:
            description = project.description or ""
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
