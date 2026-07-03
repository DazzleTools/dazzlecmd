"""Main CLI entry point for dazzlecmd.

This module provides the dazzlecmd-specific configuration and the
build_parser/dispatch functions that the AggregatorEngine delegates to.
New aggregator projects should use AggregatorEngine directly rather than
importing from this module.
"""

import argparse
import json
import os
import re
import sys

from dazzlecmd._version import DISPLAY_VERSION, __version__
from dazzlecmd._constants import RESERVED_COMMANDS  # noqa: F401  (re-exported)
from dazzlecmd.engine import AggregatorEngine
from dazzlecmd.kit_verbs import (
    LIFECYCLE_PAIRS,
    add_flat_verb,
    build_lifecycle_axis_groups,
    render_kit_help,
)
from dazzlecmd.loader import (
    discover_kits,
    discover_projects,
    resolve_entry_point,
)
from dazzlecmd_lib import colors as _colors
from dazzlecmd_lib.verb_axis import meta_tag_for, resolve_special
from dazzlecmd_lib.aggregator_config import find_aggregator_root
# The read surface lives in the lib (SD-A): one interrogation function + one
# renderer power every level's card. cli.py keeps the public names below as
# thin delegators (engine wiring + tests import them from dazzlecmd.cli).
from dazzlecmd_lib.interrogation import (  # noqa: F401
    axis_state as _kit_axis_state,
    interrogate as _interrogate,
    render_interrogation as _render_interrogation,
    _print_entity_card,
    _print_axis_rows,
)


# v0.7.44 (4b-T3 + 4d-3): per-language scaffolding ships. The set of
# valid ``--language`` values is now derived from the template directory
# layout under ``packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/`` --
# any directory there (other than ``__*__`` overlay dirs) is a valid
# language. The v0.7.40 ``_SUPPORTED_LANGUAGES_V0740`` guard is gone.


def find_project_root():
    """Find the dazzlecmd project root by navigating from __file__.

    Legacy wrapper -- new code should use AggregatorEngine.find_project_root().
    """
    return AggregatorEngine().find_project_root()


# ---------------------------------------------------------------------------
# The parser builder moved to dazzlecmd/parsers.py (cli.py decomposition R4,
# DWP 2026-06-25__16-14-19). Re-exported so AggregatorEngine.run()'s wiring in
# main() and the test-suite keep importing build_parser from dazzlecmd.cli.
# ---------------------------------------------------------------------------
from dazzlecmd.parsers import (  # noqa: F401,E402
    build_parser,
    _build_categorized_help,
    _register_meta_commands,
)


# Display helpers: canonical implementations live in dazzlecmd_lib.
# (The kit-list renderer itself moved to the lib in the unification DWP,
# 2026-06-11 -- dazzlecmd no longer carries a custom _cmd_kit_list.)
from dazzlecmd_lib.default_meta_commands import (  # noqa: F401
    _wrap_description,
    KIT_NAME_COL,
    MIN_DESC_WIDTH,
    SUMMARY_INDENT,
    TERM_SIZE_FALLBACK,
)


def _init_verbosity(args):
    """D-3: move the log_lib verbosity-Continuum coordinate from the global
    ``-v``/``-q``/``--show`` flags. ``-v`` louder, ``-q`` quieter (they compose:
    verbosity = #-v - #-q); ``--show CHANNEL[:LEVEL]`` pins one channel. Safe on any
    namespace (the flags default to 0 / None). Returns the OutputManager singleton."""
    from dazzlecmd._vendor.log_lib.manager import init_output
    verbosity = getattr(args, "verbose", 0) - getattr(args, "quiet", 0)
    return init_output(verbosity=verbosity,
                       channels=getattr(args, "show_channels", None))


def dispatch_meta(args, projects, kits, project_root, engine=None):
    """Handle built-in meta-commands.

    ``engine`` is the ``AggregatorEngine`` instance. Phase 3 commands that
    write to the user config (``dz kit enable`` etc.) need the engine to
    call ``_write_user_config``. Optional for Phase 1/2 backwards compat.
    """
    meta = getattr(args, "_meta", None)

    # D-3: the first live consumer of the log_lib verbosity Continuum. Graded
    # diagnostics on the (non-opt-in) `general` channel -> stderr, gated by the
    # THAC0 threshold: -v shows the command, -vv the discovery counts, -vvv the
    # parsed namespace. At default verbosity all three are gated (byte-gate clean).
    out = _init_verbosity(args)
    out.emit(1, "meta-command: {m}", channel="general", m=meta)
    out.emit(2, "discovered {np} project(s), {nk} kit(s)", channel="general",
             np=len(projects or []), nk=len(kits or []))
    out.emit(3, "parsed args: {a}", channel="general",
             a={k: v for k, v in vars(args).items() if not k.startswith("_")})

    if meta == "list":
        return _cmd_list(args, projects, engine=engine)
    elif meta == "info":
        return _cmd_info(
            args, projects, engine=engine, kits=kits, project_root=project_root)
    elif meta in ("enable", "disable", "attach", "detach"):
        return _dispatch_bare_verb(
            meta, args, projects, kits, project_root, engine)
    elif meta == "meta":
        return _cmd_meta(engine)
    elif meta == "meta_use":
        return _cmd_meta_use(args, engine)
    elif meta == "meta_reset":
        return _cmd_meta_reset(engine)
    elif meta in ("prop", "prop_get", "prop_set", "prop_add",
                  "prop_delete", "prop_list"):
        # The prop verb family (v2 contract 3b"): thin routing into the
        # lib's ONE implementation (prop_commands) -- the same handlers
        # the sugar intercept reuses. FQCNParseError renders uniformly.
        from dazzlecmd_lib.fqcn_grammar import FQCNParseError
        from dazzlecmd_lib import prop_commands as _pc
        try:
            if meta == "prop_get":
                return _pc.cmd_get(engine, args.path)
            elif meta == "prop_set":
                return _pc.cmd_set(engine, args.path, args.value)
            elif meta == "prop_add":
                return _pc.cmd_add(engine, args.path, args.value)
            elif meta == "prop_delete":
                return _pc.cmd_delete(engine, args.path)
            elif meta == "prop_list":
                return _pc.cmd_list(engine, args.path)
            # bare `dz meta prop` -> the family listing (discoverability)
            return _pc.cmd_list(engine, None)
        except FQCNParseError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    elif meta == "kit_list":
        # Unified renderer: the lib handler passes engine (kit-list DWP).
        from dazzlecmd_lib.default_meta_commands import kit_list_handler
        return kit_list_handler(args, engine, projects, kits, project_root)
    elif meta == "kit_info":
        return render_kit_info(
            args.name, engine, project_root=project_root,
            as_json=getattr(args, "as_json", False))
    elif meta == "kit":
        # bare "dz kit" with no subcommand behaves like "dz kit list"
        # (routed to the same unified lib renderer; the v0.9.26 unification
        # deleted dz's _cmd_kit_list but left this branch pointing at it --
        # caught by CI's F821 gate, missed by the suite because nothing
        # exercised the bare form).
        from dazzlecmd_lib.default_meta_commands import kit_list_handler
        return kit_list_handler(args, engine, projects, kits, project_root)
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
    elif meta == "kit_visibility_set":
        return _cmd_kit_visibility_set(args, engine)
    elif meta == "kit_visibility":
        return _cmd_kit_visibility_list(engine)
    elif meta == "kit_visibility_status":
        return _cmd_kit_visibility_status(args, engine)
    elif meta == "kit_add":
        return _cmd_kit_add(args, project_root, engine)
    elif meta == "kit_remove":
        return _cmd_kit_remove(args, project_root, engine)
    elif meta == "kit_detach":
        return _cmd_kit_detach(args, project_root, engine)
    elif meta == "kit_attach":
        return _cmd_kit_attach(args, project_root, engine)
    elif meta == "kit_management":
        return _cmd_kit_management(args, project_root, engine, axis=None)
    elif meta and meta.startswith("kit_axis_"):
        # `dz kit <axis>` with no verb -> that sub-axis's state (state-on-invoke).
        return _cmd_kit_management(args, project_root, engine,
                                   axis=meta[len("kit_axis_"):])
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
    elif meta == "new_kit":
        return _cmd_new_kit(args, project_root)
    elif meta == "new_aggregator":
        return _cmd_new_aggregator(args, engine)
    elif meta == "add":
        return _cmd_add(args, project_root)
    elif meta == "mode_status":
        return _cmd_mode_status(args, projects, project_root)
    elif meta == "mode_switch":
        return _cmd_mode_switch(args, projects, project_root)
    elif meta == "mode_restore":
        return _cmd_mode_restore(args, projects, project_root)
    elif meta == "mode":
        # bare "dz mode" with no subcommand — show status
        return _cmd_mode_status(args, projects, project_root)
    elif meta == "version":
        return _cmd_version()

    return 1


# ---------------------------------------------------------------------------
# The generic verb x level dispatcher (B4-dispatch, DWP 2026-06-25__16-01-41).
# Assembles SD-0's two designed halves -- the lib's tag generator
# (meta_tag_for / resolve_special) and the CLI's tag->handler table -- so that
# `dz <verb> <target>` routes with ZERO per-verb / per-level branches. Adding a
# verb means adding a handler (below), never editing the dispatcher.
# ---------------------------------------------------------------------------

# The pole-less READ verbs (ordered continua, not {warm,cold} toggles). A subset
# of kit_verbs.GENERIC_VERBS -- it EXCLUDES focus/reset (those are mutating kit
# operations, not level-agnostic inspects). Toggle verbs are recognised via
# resolve_special instead, so they are not listed here.
INSPECT_VERBS = frozenset({"info", "list", "tree"})
# `status` (the per-axis state reduction) is intentionally NOT here for now --
# info-only, to avoid status/info confusion before `dz` has a wider audience.
# The reduction SHAPE is kept: `_kit_axis_state` + `interrogate(facets={"state"})`
# still feed `dz info`'s "Current state:" section, so re-adding a `dz <level>
# status` verb later is a thin slice (a parser + dispatch + a handler over that
# infra), not a rebuild. See the Gate-E DWP (2026-06-27__10-02-13).


def verb_plan(token):
    """Resolve a bare verb token to ``(applies_at, mutating, tag_fn)`` or ``None``.

    - An INSPECT verb -> ``(None, False, lambda level: f"{level}_{token}")``
      (applies at every level, non-mutating, keyed as ``<level>_<verb>``).
    - A TOGGLE special (enable/disable/attach/...) -> via ``resolve_special`` ->
      ``(va.applies_at, True, lambda level: meta_tag_for(va.axis, pole, level))``.
    - Anything else -> ``None`` (unknown verb).

    Both verb kinds collapse to one ``<level>_<verb>`` tag -- the inspect/toggle
    keying tension, resolved (spike GT7). This is the ONLY place that knows how a
    verb keys; the dispatcher below is verb-agnostic.
    """
    if token in INSPECT_VERBS:
        return (None, False, lambda level: f"{level}_{token}")
    hit = resolve_special(token)
    if hit is not None:
        va, pole = hit
        return (va.applies_at, True,
                lambda level: meta_tag_for(va.axis, pole, level))
    return None


def _dispatch_verb_target(token, target, args, projects, kits,
                          project_root, engine):
    """Apply ``token`` to ``target`` at whichever level ``target`` resolves to.

    ``verb_plan`` -> ``engine.resolve_target`` (read auto-picks + notifies;
    mutate fails loud; ``applies_at`` prunes off-level) -> ``<level>_<verb>``
    tag -> the registered handler. The body has NO ``verb ==`` / ``level ==``
    branch (AC-D1). Returns the handler's exit code, or ``None`` when the verb
    is unknown or the target does not resolve -- the caller supplies the
    fallback (e.g. ``dz info``'s legacy not-found message).
    """
    plan = verb_plan(token)
    if plan is None:
        return None
    applies_at, mutating, tag_fn = plan
    kwargs = {} if applies_at is None else {"applies_at": frozenset(applies_at)}
    res = engine.resolve_target(
        target, mutating=mutating,
        as_level=getattr(args, "as_level", None),
        foreground=foreground_level(engine), **kwargs)
    if res is None:
        return None
    if res.notification:
        print(res.notification, file=sys.stderr)
    tag = tag_fn(res.level)
    handler = _VERB_LEVEL_HANDLERS.get(tag)
    if handler is None:
        print(f"No handler registered for '{tag}'.", file=sys.stderr)
        return 1
    return handler(res, args, projects, kits, project_root, engine)


def _dispatch_bare_verb(verb, args, projects, kits, project_root, engine):
    """``dz <verb> <target>`` -- the bare-verb cross-level MUTATING form
    (B4-mutate). Resolves the target's level through ``_dispatch_verb_target``
    (``mutating=True`` fails loud on an ambiguous bare name; ``applies_at``
    prunes the wrong level) and runs the resolved ``<level>_<verb>`` handler.
    A clear message + non-zero exit replaces both the ambiguity raise and a
    target that does not resolve."""
    from dazzlecmd_lib.target_resolution import AmbiguousLevelError
    target = getattr(args, "target", None)
    try:
        rc = _dispatch_verb_target(
            verb, target, args, projects, kits, project_root, engine)
    except AmbiguousLevelError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if rc is None:
        print(f"'{target}' did not resolve to a kit for '{verb}'.",
              file=sys.stderr)
        return 1
    return rc


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


# --- MUTATING handlers (B4-mutate) -- the bare-verb cross-level toggles -------
# Each bridges the generic (res, args, projects, kits, project_root, engine)
# dispatch signature to the existing kit handler by binding the resolved kit
# name. resolve_target's mutating=True path already fails loud on an ambiguous
# bare name, and ``applies_at={'kit'}`` prunes tool/aggregator before we get
# here -- so these only ever run on a kit that genuinely resolved.


def _resolved_kit_name(res):
    return getattr(res.entity, "kit_name", None) or getattr(res.entity, "name", None)


def _enable_at_kit(res, args, projects, kits, project_root, engine):
    """``enable`` at the kit level -- the activation warm pole."""
    from dazzlecmd.commands.kit import _cmd_kit_enable
    args.name = _resolved_kit_name(res)
    return _cmd_kit_enable(args, engine)


def _disable_at_kit(res, args, projects, kits, project_root, engine):
    """``disable`` at the kit level -- the activation cold pole."""
    from dazzlecmd.commands.kit import _cmd_kit_disable
    args.name = _resolved_kit_name(res)
    return _cmd_kit_disable(args, engine)


def _attach_at_kit(res, args, projects, kits, project_root, engine):
    """``attach`` at the kit level -- the loading warm pole (pointer -> loaded,
    then enable). Wraps the existing kit handler verbatim."""
    from dazzlecmd.commands.kit_membership import _cmd_kit_attach
    args.name = _resolved_kit_name(res)
    return _cmd_kit_attach(args, project_root, engine)


def _detach_at_kit(res, args, projects, kits, project_root, engine):
    """``detach`` at the kit level -- the loading cold pole (loaded -> pointer,
    files kept; the implicit loading->activation cascade disables it)."""
    from dazzlecmd.commands.kit_membership import _cmd_kit_detach
    args.name = _resolved_kit_name(res)
    return _cmd_kit_detach(args, project_root, engine)


# The <level>_<verb> tag -> handler table -- SD-0's "tag->callable half". Each
# handler has the uniform signature
# ``(res, args, projects, kits, project_root, engine) -> int``. Adding a verb at
# a level = adding an entry here (AC-D2); _dispatch_verb_target never changes.
# B4-mutate registers enable/disable (activation) + attach/detach (loading) --
# the context-COMPLETE single-target toggles. favorite/unfavorite (projection)
# are context-BOUND (they need <short> <fqcn>, not just a kit), so they stay the
# explicit `dz kit favorite <short> <fqcn>` form -- not hoisted. B5 follows.
_VERB_LEVEL_HANDLERS = {
    "tool_info": _info_at_tool,
    "kit_info": _info_at_kit,
    "aggregator_info": _info_at_aggregator,
    "kit_enable": _enable_at_kit,
    "kit_disable": _disable_at_kit,
    "kit_attach": _attach_at_kit,
    "kit_detach": _detach_at_kit,
}


def _cmd_info(args, projects, engine, kits=None, project_root=None):
    """Show detailed info about a tool, kit, or aggregator -- the level-agnostic
    ``dz info <target>`` (SD-1/SD-3), now routed through the generic verb x level
    dispatcher (B4-dispatch). ``_dispatch_verb_target`` resolves the target's
    level and calls the ``<level>_info`` handler; a name that resolves to
    nothing falls through to ``render_info`` so the legacy "Tool 'X' not found"
    message + exit code are preserved exactly.
    """
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


# ---------------------------------------------------------------------------
# ADD / MODE / SETUP handlers moved to commands/{add,mode,setup}.py
# (cli.py decomposition R3, DWP 2026-06-25__16-14-19). Re-exported for
# dispatch_meta + back-compat (tests import _cmd_setup et al. from dazzlecmd.cli).
# ---------------------------------------------------------------------------
from dazzlecmd.commands.add import _cmd_add  # noqa: F401,E402
from dazzlecmd.commands.mode import (  # noqa: F401,E402
    _cmd_mode_status,
    _cmd_mode_switch,
    _cmd_mode_restore,
)
from dazzlecmd.commands.meta import (  # noqa: F401,E402
    foreground_level,
    _cmd_meta,
    _cmd_meta_use,
    _cmd_meta_reset,
)
from dazzlecmd.commands.setup import _cmd_setup  # noqa: F401,E402



# ---------------------------------------------------------------------------
# NEW/SCAFFOLD handlers moved to commands/new.py (cli.py decomposition R2,
# DWP 2026-06-25__16-14-19). Re-exported for dispatch_meta + back-compat
# (_cmd_add, tests, and one-offs import several of these from dazzlecmd.cli).
# ---------------------------------------------------------------------------
from dazzlecmd.commands.new import (  # noqa: F401,E402
    _resolve_new_defaults,
    _find_templates_root,
    _available_languages,
    _substitute_placeholders,
    _copy_template_tree,
    _cmd_new_tool,
    _cmd_new_kit,
    _scaffold_starter_tool,
    _with_copy_component,
    _ComponentUnavailable,
    _REPOKIT_COMMON_URL_DEFAULT,
    _REPOKIT_TEMPLATE_URL_DEFAULT,
    _GIT_SUBTREE_TIMEOUT,
    _run_git,
    _with_common,
    _with_template,
    _WITH_COMPONENTS,
    _WITH_ALL,
    _parse_with_spec,
    _apply_with_components,
    _cmd_new_aggregator,
    _layer_extras,
    _register_in_kit,
)



# ---------------------------------------------------------------------------
# Kit-lifecycle handlers moved to commands/kit*.py (cli.py decomposition R1,
# DWP 2026-06-25__16-14-19). Re-exported here so dispatch_meta resolves them by
# bare name and so the test-suite / one-offs can import them from dazzlecmd.cli.
# ---------------------------------------------------------------------------
from dazzlecmd.commands.kit import (  # noqa: F401,E402
    _kit_exists,
    _cmd_kit_enable,
    _cmd_kit_disable,
    _cmd_kit_focus,
    _cmd_kit_reset,
    _cmd_kit_favorite,
    _suggest_favorite_replacement,
    _cmd_kit_favorite_migrate_stale,
    _cmd_kit_unfavorite,
)
from dazzlecmd.commands.kit_visibility import (  # noqa: F401,E402
    _resolve_visibility_target,
    _is_constitutional_entity,
    _cmd_kit_visibility_set,
    _resolve_cascade_slice,
    _apply_visibility_cascade,
    _cmd_kit_visibility_list,
    _cmd_kit_visibility_status,
)
from dazzlecmd.commands.kit_membership import (  # noqa: F401,E402
    _cmd_kit_add,
    _kit_is_submodule,
    _cmd_kit_remove,
    _cmd_kit_detach,
    _materialize_pointer,
    _cmd_kit_attach,
    _print_axis_hint,
    _cmd_kit_management,
)



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
