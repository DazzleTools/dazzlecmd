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
    import contextlib
    import io as _io
    from dazzlecmd_lib.default_meta_commands import render_info
    from dazzlecmd.tree_plane import instance_card_sections
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = render_info(args, projects, engine)
    out = buf.getvalue()
    level_line, fibers = instance_card_sections(
        engine, getattr(args, "tool", None) or res.name)
    if level_line:
        lines = out.splitlines()
        # "Short FQCN" when a DIFFERING Absolute exists (user directive:
        # users should know the actual root -- the aggregator sits at
        # the co-level of .meta on the one tree)
        fq = next((i for i, ln in enumerate(lines)
                   if ln.startswith("FQCN:")), None)
        ab = next((ln for ln in lines if ln.startswith("Absolute:")), None)
        if fq is not None and ab is not None:
            fq_val = lines[fq].split(":", 1)[1].strip()
            ab_val = ab.split(":", 1)[1].strip().split()[0]
            if ab_val != fq_val:
                lines[fq] = f"{'Short FQCN:':<13}{fq_val}"
        # Level joins the IDENTITY block (after Namespace:, else Kit:)
        for anchor in ("Namespace:", "Kit:", "FQCN:"):
            idx = next((i for i, ln in enumerate(lines)
                        if ln.startswith(anchor)), None)
            if idx is not None:
                lines.insert(idx + 1, level_line)
                break
        # the FIBERS section (the ring, visibly distinct) sits before
        # the internal-state block
        if fibers:
            state_idx = next((i for i, ln in enumerate(lines)
                              if ln.startswith("Current state:")),
                             len(lines))
            block = ["Fibers:"] + fibers + [""]
            lines[state_idx:state_idx] = block
        out = "\n".join(lines) + ("\n" if out.endswith("\n") else "")
    # space-conscious state block (user nit): no blank line between
    # "Current state:" and its rows -- consistent with Fibers:
    out = out.replace("Current state:\n\n", "Current state:\n")
    print(out, end="")
    return rc


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
    # 2f (AC-2-7 universality): before the legacy not-found, try the
    # DERIVED TREE -- fiber paths (`dz info :.level`), rung/axis bare
    # names (`dz info level`, `dz info kit`), verb poles. Everything
    # addressable is info-able.
    if engine is not None and _info_tree_node(engine, args.tool):
        return 0
    from dazzlecmd_lib.default_meta_commands import render_info
    return render_info(args, projects, engine)


def _graft_app_verbs(engine, tree):
    """2f slice 2: the APP's verb inventory joins the tree. Verb->help
    pairs come from the LIVE argparse tree (no second registry). A verb
    whose name already matches an existing node (a pole like `enable`,
    a rung-surface like `kit`) ATTACHES its help there (one-node); the
    rest gain flat nodes under `<root>:.meta:verb:<name>` (family
    refinement -- e.g. an inspect axis -- is a later slice)."""
    try:
        from dazzlecmd.parsers import build_parser
        parser = build_parser([], engine=None)
        sub = parser._subparsers._group_actions[0]
        pairs = [(a.dest, a.help) for a in sub._choices_actions]
    except Exception:
        return
    verb_root = f"{engine.command}:.meta:verb"
    by_segment = {}
    for n in tree.nodes:
        by_segment.setdefault(n.rsplit(":", 1)[-1].lstrip("."), []).append(n)
    for name, help_text in pairs:
        hits = by_segment.get(name, [])
        if len(hits) > 1:
            # Row-3 fix: an ambiguous segment (attach exists under BOTH
            # kit:loading and meta:verb:loading) attaches to the VERB
            # PLANE's own pole -- never silently dropped
            verb_hits = [h for h in hits if ":.meta:verb" in h]
            hits = verb_hits[:1] or hits[:1]
        if len(hits) == 1:
            tree.nodes[hits[0]].setdefault("help", help_text)
        elif not hits:
            from dazzle_lib.groupable import Unified
            key = f"{verb_root}:{name}"
            tree.add_node(key, obj=Unified(label=name), kind="Unified",
                          role="verb", help=help_text)
            tree.add_edge(verb_root, key)


def _info_tree_node(engine, target):
    """Render the card for a DERIVED-TREE node (the fiber plane's read
    surface -- SD-FQCN-2 2f). Returns True when ``target`` resolves to a
    tree node; False lets the legacy fallback speak."""
    if not target:
        return False
    from dazzlecmd_lib.fqcn_grammar import canonicalize, FQCNParseError

    from dazzlecmd_lib.fqcn_tree import build_engine_tree, resolve_path
    # Row-1 (the surface matrix): every surface sees the SAME tree --
    # the engine-extension build, never a raw build_tree + manual graft
    # (that path silently missed registered extensions, e.g. the
    # instance plane).
    if _graft_app_verbs not in engine.tree_extensions:
        engine.tree_extensions.append(_graft_app_verbs)
    tree = build_engine_tree(engine)
    if target == ":.":
        # the ROOT CARD (B-2): the one graph's front door -- hidden
        # machinery children + the visible user namespaces
        key = engine.command
        target = engine.command
    else:
        key = None
    if key is not None:
        pass
    elif any(op in target for op in (":.", ":+")) or target.startswith(":"):
        try:
            canon, _ = canonicalize(target, implicit_root=engine.command)
        except FQCNParseError:
            return False
        canon = resolve_path(tree, canon)
        if canon in tree:
            key = canon
    else:
        # a bare name: unique last-segment match across the tree
        hits = [n for n in tree.nodes
                if n.rsplit(":", 1)[-1].lstrip(".") == target
                and n != engine.command]
        if len(hits) == 1:
            key = hits[0]
        elif len(hits) > 1:
            print(f"'{target}' is ambiguous in the fiber plane:")
            for h in sorted(hits):
                print(f"  {h}")
            return True
    if key is None:
        return False
    node = tree.nodes[key]
    kind = node.get("kind", "Unified")
    role = node.get("role")
    print(f"{key}")
    print(f"  kind: {kind}" + (f" ({role})" if role else ""))
    if "axis" in node:
        print(f"  rung of: {node['axis']}  (rank {node['rank']})")
        if node["axis"].endswith(":.level"):
            # the class-vs-instance doctrine line -- LEVEL rungs only
            # (a verb pole is a position, not a class of entities)
            rung = key.rsplit(":", 1)[-1]
            print(f"  -- a position on the axis AND the class of {rung} "
                  f"entities; the fiber below is {rung}-ness's machinery.")
    if node.get("level"):
        handles = node.get("instance_of") or []
        tail = f"   ({', '.join(handles)})" if handles else ""
        print(f"  level: {node['level']}{tail}")
    if node.get("help"):
        # the help FACET's degenerate renderer (the one-line info; the
        # full page stays `dz <verb> -h`)
        print(f"  help: {node['help']}")
    # one-node: an axis whose bare VALUE is property-backed shows its
    # CURRENT position on the card (and marks the active rung below)
    current = None
    default_val = None
    from dazzlecmd_lib.prop_commands import KEY_DEFAULTS, NODE_VALUE_ALIASES
    value_key = NODE_VALUE_ALIASES.get(key)
    if value_key is not None:
        default_val = KEY_DEFAULTS.get(value_key)
        current = engine.property_store.get(value_key)
        if current is None and default_val is not None:
            print(f"  current: {default_val} (default)")
            current = default_val
        elif current is not None:
            print(f"  current: {current}")
        if default_val is not None:
            # defaults expressed CLEARLY (user directive 2026-07-05):
            # the chart center, distinct from the structural invariant
            print(f"  default: {default_val}")
    obj = node.get("obj")
    if obj is not None and getattr(obj, "invariant", ""):
        print(f"  invariant: {obj.invariant} (conserved at 0)")
    kids = sorted(
        tree.successors(key),
        key=lambda n: (tree.nodes[n].get("rank") is None,
                       tree.nodes[n].get("rank", 0), n))
    if kids:
        print("  contains:")
        width = max([14] + [len(k.rsplit(":", 1)[-1]) + 2 for k in kids])
        for k in kids:
            kn = tree.nodes[k]
            rank = f" (rank {kn['rank']})" if "rank" in kn else ""
            rolet = f" ({kn['role']})" if kn.get("role") else ""
            seg = k.rsplit(":", 1)[-1]
            marker = ""
            if current is not None and seg == current:
                marker += "  <- current"
            if default_val is not None and seg == default_val:
                marker += "  (default)"
            print(f"    {seg:<{width}}{kn.get('kind', '')}{rolet}{rank}{marker}")
    props = engine.property_store.list_prefix(key)
    if props:
        print("  properties:")
        for pk in sorted(props):
            print(f"    {pk} = {props[pk]!r}")
    return True



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


