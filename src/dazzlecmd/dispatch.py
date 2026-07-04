"""The dazzlecmd dispatch fan-in hub (decomposition R7 + B4-dispatch).

dispatch_meta (meta-command router), the generic verb x level dispatcher
(verb_plan / _dispatch_verb_target / _VERB_LEVEL_HANDLERS -- SD-0's two
halves), the B4-mutate bare-verb handlers, dispatch_tool, and the sugar
flags hook. Extracted from cli.py (DWP 2026-06-25__16-14-19; landed with
SD-FQCN-2 slice 2b). Pure moves: bodies unchanged; cli.py re-exports.
"""
import sys

from dazzlecmd_lib.verb_axis import meta_tag_for, resolve_special
from dazzlecmd.loader import resolve_entry_point
from dazzlecmd.kit_verbs import render_kit_help  # noqa: F401
from dazzlecmd.commands.meta import (
    foreground_level,
    _cmd_meta,
    _cmd_meta_use,
    _cmd_meta_reset,
)
from dazzlecmd.commands.add import _cmd_add
from dazzlecmd.commands.mode import (
    _cmd_mode_status,
    _cmd_mode_switch,
    _cmd_mode_restore,
)
from dazzlecmd.commands.setup import _cmd_setup
from dazzlecmd.commands.new import (
    _cmd_new_tool,
    _cmd_new_kit,
    _cmd_new_aggregator,
)
from dazzlecmd.commands.kit import (
    _cmd_kit_enable,
    _cmd_kit_disable,
    _cmd_kit_focus,
    _cmd_kit_reset,
    _cmd_kit_favorite,
    _cmd_kit_unfavorite,
)
from dazzlecmd.commands.kit_visibility import (
    _cmd_kit_visibility_set,
    _cmd_kit_visibility_list,
    _cmd_kit_visibility_status,
)
from dazzlecmd.commands.kit_membership import (
    _cmd_kit_add,
    _cmd_kit_remove,
    _cmd_kit_detach,
    _cmd_kit_attach,
    _cmd_kit_management,
)
from dazzlecmd.commands.inspect import (
    _cmd_list,
    _cmd_info,
    _cmd_tree,
    _cmd_version,
    render_kit_info,
    _info_at_tool,
    _info_at_kit,
    _info_at_aggregator,
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



def _sugar_flags_hook(flag_tokens):
    """Parse the intercept's pre-path flag tokens (-v/-q/--show) and
    initialize the output manager -- the sugar path's _init_verbosity."""
    import argparse as _argparse
    p = _argparse.ArgumentParser(add_help=False)
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.add_argument("-q", "--quiet", action="count", default=0)
    p.add_argument("--show", dest="show_channels", action="append",
                   default=None)
    ns, _unknown = p.parse_known_args(flag_tokens)
    _init_verbosity(ns)

