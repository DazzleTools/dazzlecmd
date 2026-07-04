"""``dz`` read surfaces -- list / info / tree / version (the CARDS cluster).

Extracted from cli.py (decomposition R6, DWP 2026-06-25__16-14-19; landed with
the FQCN arc's SD-FQCN-2 slice 2b). Pure moves: bodies unchanged; cli.py
re-exports every name for engine wiring + test back-compat.
"""
import sys

from dazzlecmd._version import DISPLAY_VERSION, __version__

from dazzlecmd_lib.interrogation import (  # noqa: F401
    axis_state as _kit_axis_state,
    interrogate as _interrogate,
    render_interrogation as _render_interrogation,
    _print_entity_card,
    _print_axis_rows,
)
from dazzlecmd.commands.meta import foreground_level  # noqa: F401


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
    """The aggregator's identity card -- delegates to the lib interrogation
    surface (SD-A). ``resolve_target`` returns the engine itself for the
    aggregator level, so ``engine`` IS the entity here."""
    interro = _interrogate(
        engine, engine, level="aggregator",
        project_root=project_root, projects=projects, kits=kits)
    return _render_interrogation(interro, as_json=as_json)


def _info_at_tool(res, args, projects, kits, project_root, engine):
    """``tool_info`` handler: the library ``render_info`` card -- the human card
    is UNCHANGED, byte-identical to v0.7.33 (the byte-gate's dz_info_* goldens
    guard it). ``--json`` routes through the interrogation surface for a
    structured, facet-shaped card -- uniform with the kit/aggregator JSON."""
    if getattr(args, "as_json", False):
        interro = _interrogate(res.entity, engine, level="tool",
                               project_root=project_root)
        return _render_interrogation(interro, as_json=True)
    from dazzlecmd_lib.default_meta_commands import render_info
    return render_info(args, projects, engine)


def _info_at_kit(res, args, projects, kits, project_root, engine):
    """``kit_info`` handler: the kit identity + current-state card."""
    kit_name = getattr(res.entity, "kit_name", None) or res.entity.name
    return render_kit_info(kit_name, engine, project_root=project_root,
                           as_json=getattr(args, "as_json", False))


def _info_at_aggregator(res, args, projects, kits, project_root, engine):
    """``aggregator_info`` handler: the aggregator identity card."""
    return render_aggregator_info(res.entity, projects, kits, project_root,
                                  as_json=getattr(args, "as_json", False))



def _cmd_info(args, projects, engine, kits=None, project_root=None):
    """Show detailed info about a tool, kit, or aggregator -- the level-agnostic
    ``dz info <target>`` (SD-1/SD-3), now routed through the generic verb x level
    dispatcher (B4-dispatch). ``_dispatch_verb_target`` resolves the target's
    level and calls the ``<level>_info`` handler; a name that resolves to
    nothing falls through to ``render_info`` so the legacy "Tool 'X' not found"
    message + exit code are preserved exactly.
    """
    # function-local import: dispatch.py imports THIS module (the
    # tag->handler table needs the info handlers), so the reverse edge
    # must bind at call time -- the codebase's standard cycle-breaker.
    from dazzlecmd.dispatch import _dispatch_verb_target
    rc = _dispatch_verb_target(
        "info", args.tool, args, projects, kits, project_root, engine)
    if rc is not None:
        return rc
    from dazzlecmd_lib.default_meta_commands import render_info
    return render_info(args, projects, engine)



# _kit_axis_state and _print_axis_rows moved to dazzlecmd_lib.interrogation
# (SD-A) -- re-exported at module top. The state read is the projection of the
# verb-axis registry, so it belongs in the lib next to VERB_AXES.


# _print_entity_card moved to dazzlecmd_lib.interrogation (SD-A), re-exported
# at module top. It is the one card walker every level's table renders through.


def render_kit_info(kit_name, engine, project_root=None, as_json=False):
    """A kit's identity card AND its current state, in one read (the user's
    'fold state into info' decision). Delegates to the lib interrogation surface
    (SD-A): the identity facet (name/kind/version/source/...) plus the state
    facet (the kit's rung on each lifecycle axis -- the same rows
    `dz kit status <kit>` shows on its own). ``--json`` mirrors both. Distinct
    from ``dz kit list <kit>`` (which lists the kit's *tools*); this is the kit
    itself. The caller-side 'No kit found' message + exit 1 are preserved."""
    kit_list = getattr(engine, "kits", []) or []
    match = next(
        (k for k in kit_list
         if (getattr(k, "kit_name", None) or getattr(k, "name", None)) == kit_name),
        None)
    if match is None:
        print(f"No kit '{kit_name}' found.", file=sys.stderr)
        return 1
    interro = _interrogate(match, engine, level="kit", project_root=project_root)
    return _render_interrogation(interro, as_json=as_json)


def _cmd_version():
    """Show version info (alternate to --version flag)."""
    print(f"dazzlecmd {DISPLAY_VERSION} ({__version__})")
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


