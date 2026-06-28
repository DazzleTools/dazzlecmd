"""Kit-lifecycle command handlers: the visibility axis.

Moved out of cli.py (decomposition R1, DWP 2026-06-25__16-14-19). The single
visibility-toggle handler (all six verbs route to ``_cmd_kit_visibility_set``),
its cascade machinery, and the visibility list/status navigators over
``KIT_PRESENCE_SPACE``. cli.py re-exports these names. Imports nothing from
cli.py -- one-directional.
"""
import sys

def _resolve_visibility_target(engine, name):
    """Resolve a user-typed name (short name | FQCN | alias) to
    ``(canonical_fqcn, project)`` via the engine's dispatch-grade resolver.
    Returns ``(name, None)`` when nothing matches -- the caller warns + writes the
    raw input (permissive for not-yet-discovered / pointer-kit tools). Resolving
    here is what makes a short name effective AND keeps C3 uncircumventable."""
    resolver = getattr(engine, "resolve_command", None)
    if resolver is None:
        return name, None
    try:
        project, ctx = resolver(name)
    except Exception:
        return name, None
    if project is None:
        return name, None
    canonical = (getattr(ctx, "canonical_fqcn", None)
                 or getattr(project, "fqcn", None) or name)
    return canonical, project


def _is_constitutional_entity(project):
    """True if a resolved project is constitutional / always_active (the C3 gate)."""
    if project is None:
        return False
    if getattr(project, "always_active", False):
        return True
    try:
        from dazzlecmd_lib.core import is_constitutional
    except Exception:
        return False
    return ((getattr(project, "namespace", "") or "") == "core"
            and is_constitutional(getattr(project, "name", "") or ""))


def _cmd_kit_visibility_set(args, engine):
    """The single visibility-toggle handler for all six verbs.

    Resolves the name to its canonical FQCN, looks up the TYPED rung from
    ``KIT_PRESENCE_SPACE`` (``args.level``), enforces C3, and writes via the rung.
    The CLI carries no per-verb config keys or verb tables -- the container
    (the rung object) holds the binding. ``args.direction`` is "suppress" | "restore".
    """
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1
    from dazzlecmd_lib.contexts import KIT_PRESENCE_SPACE
    # KIT_PRESENCE_SPACE is the multi-axis PRODUCT (visibility x activation); the
    # visibility navigator reads its ALIGNED ``axes["visibility"]`` sub-space (the
    # product itself is non-aligned and refuses cross-axis nav -- scale-safety).
    space = KIT_PRESENCE_SPACE.axes["visibility"]

    add = args.direction == "suppress"
    canonical, project = _resolve_visibility_target(engine, args.fqcn)
    if project is None:
        print(f"Note: '{args.fqcn}' didn't resolve to a known tool; recording "
              f"as-is (it takes effect if that tool appears).", file=sys.stderr)

    # --cascade (B2c): apply a SLICE of adjacent presence rungs at once (the
    # general ContinuumSpace apply-mode), instead of just this one rung.
    if getattr(args, "cascade", None) is not None:
        return _apply_visibility_cascade(
            engine, space, canonical, project, args.level, add, args.cascade)

    rung = space.payload_for("visibility", args.level)
    # C3: a constitutional tool may be hidden but never shadowed (the rung
    # declares the policy; the resolved entity supplies the status).
    if add and rung.forbids_constitutional and _is_constitutional_entity(project):
        print(f"Refused: {canonical} is constitutional -- it may be hidden but "
              f"never shadowed (C3: dz depends on it; removing it would break "
              f"dispatch).", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    was = rung.present(config, canonical)
    if add:
        if was:
            print(f"{canonical} is already {rung.level}.")
            return 0
        engine._write_user_config(rung.write(config, canonical, add=True))
        print(f"{rung.level.capitalize()}: {canonical}")
    else:
        if not was:
            print(f"{canonical} was not {rung.level}.")
            return 0
        engine._write_user_config(rung.write(config, canonical, add=False))
        print(f"Restored: {canonical} (no longer {rung.level})")
    return 0


def _resolve_cascade_slice(space, axis, current, spec):
    """Resolve a ``--cascade`` spec to the ordered levels it touches.

    ``@neutral`` (bare) = the current rung + all weaker toward neutral
    (``space.cascade_to_neutral``); ``up``/``down``[``:N``] = toward the warm/cold
    pole, or N rung-steps; ``lo,hi`` = a signed rung-step offset window (``+`` =
    warmer / more present). Raises ``ValueError`` on a malformed spec."""
    if spec == "@neutral":
        return list(space.cascade_to_neutral(axis, current))
    n = len(space.axis(axis).levels())
    if spec in ("up", "down") or spec.startswith("up:") or spec.startswith("down:"):
        direction, _, count = spec.partition(":")
        steps = int(count) if count else n          # bare up/down = to the pole
        if steps < 0:
            raise ValueError("step count must be >= 0")
        if direction == "up":                       # warmer / more present
            return list(space.slice(axis, current, lo=0, hi=steps))
        return list(space.slice(axis, current, lo=-steps, hi=0))   # down = colder
    parts = spec.split(",")
    if len(parts) != 2:
        raise ValueError("expected 'lo,hi' (e.g. -1,2) or 'up|down[:N]'")
    return list(space.slice(axis, current, lo=int(parts[0]), hi=int(parts[1])))


def _apply_visibility_cascade(engine, space, canonical, project, current_level, add, spec):
    """Apply a visibility verb with ``--cascade``: set (suppress) or clear
    (restore) each rung in the resolved slice ADDITIVELY -- it turns the slice's
    rungs on/off and leaves rungs outside the slice untouched. Prints the affected
    rungs; refuses the constitutional cold-pole rung (C3) but applies the rest."""
    axis = "visibility"
    try:
        levels = _resolve_cascade_slice(space, axis, current_level, spec)
    except ValueError as e:
        print(f"Error: bad --cascade value {spec!r}: {e}", file=sys.stderr)
        return 1
    rungs = [r for r in (space.payload_for(axis, lvl) for lvl in levels) if r is not None]
    if not rungs:
        print(f"{canonical}: nothing to cascade (already at neutral).")
        return 0
    desc = ", ".join(f"{r.level} ({r.verb if add else r.unverb})" for r in rungs)
    print(f"Cascade {'suppress' if add else 'restore'} {canonical}: {desc}")
    applied, unchanged, refused = [], [], []
    for r in rungs:
        if add and r.forbids_constitutional and _is_constitutional_entity(project):
            refused.append(r.level)
            continue
        config = engine._get_user_config()
        if r.present(config, canonical) == add:
            unchanged.append(r.level)
            continue
        engine._write_user_config(r.write(config, canonical, add=add))
        applied.append(r.level)
    if applied:
        print(f"  {'set' if add else 'cleared'}: {', '.join(applied)}")
    if unchanged:
        print(f"  unchanged: {', '.join(unchanged)}")
    if refused:
        print(f"  refused (constitutional -- C3): {', '.join(refused)}", file=sys.stderr)
    return 0


def _cmd_kit_visibility_list(engine):
    """Overview: every tool at non-default presence, by rung -- silenced (hint
    off) / hidden (listing off) / shadowed (dispatch off). Replaces the old
    `silenced` query and adds the `hidden` rung it had omitted. Favorites are a
    different axis (short-name resolution) -- see `dz kit favorite`."""
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    silenced = config.get("silenced_hints") or {}
    silenced_tools = silenced.get("tools") or []
    silenced_kits = silenced.get("kits") or []
    hidden = config.get("hidden_tools") or []
    shadowed = config.get("shadowed_tools") or []

    def _rung(label, items):
        print(f"{label}")
        if items:
            for it in items:
                print(f"  - {it}")
        else:
            print("  (none)")

    print("Tool presence (non-default rungs; visible = default, not listed):")
    print()
    _rung("silenced  (rerooting hint off):", silenced_tools)
    if silenced_kits:
        print("  kits:")
        for kit in silenced_kits:
            print(f"    - {kit}")
    print()
    _rung("hidden    (omitted from listings, still dispatchable):", hidden)
    print()
    _rung("shadowed  (removed from dispatch, short name freed):", shadowed)

    if not (silenced_tools or silenced_kits or hidden or shadowed):
        print()
        print("Everything is fully present. Adjust with "
              "'dz kit visibility silence|hide|shadow <fqcn>'.")
    return 0


def _cmd_kit_visibility_status(args, engine):
    """Show one tool's presence across EVERY visibility rung -- the per-item
    TRANSPOSE of the global `dz kit visibility` view (same rungs, same wording).
    `status` is the narrow SLICE of the visibility axis: the global view lists
    tools BY rung; this lists the rungs FOR one tool. Reads the TYPED rungs (each
    rung's ``present``), C3-aware via ``forbids_constitutional``."""
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1
    from dazzlecmd_lib.contexts import KIT_PRESENCE_SPACE, level_for_channels

    # KIT_PRESENCE_SPACE is the multi-axis PRODUCT (visibility x activation); read
    # its ALIGNED ``axes["visibility"]`` sub-space (the product refuses cross-axis
    # nav -- scale-safety).
    vis = KIT_PRESENCE_SPACE.axes["visibility"]
    canonical, project = _resolve_visibility_target(engine, args.fqcn)
    config = engine._get_user_config()
    constitutional = _is_constitutional_entity(project)

    # Rung descriptions mirror the global `dz kit visibility` view (one wording).
    descriptions = {
        "silenced": "rerooting hint off",
        "hidden": "omitted from listings, still dispatchable",
        "shadowed": "removed from dispatch, short name freed",
    }

    suppressed = set()
    marks = {}
    for lvl in ("silenced", "hidden", "shadowed"):
        rung = vis.payload_for("visibility", lvl)
        if rung is not None and rung.present(config, canonical):
            suppressed.add(rung.channel)
            marks[lvl] = "ON "
        elif rung is not None and rung.forbids_constitutional and constitutional:
            marks[lvl] = "n/a"  # C3: a constitutional tool can never reach this rung
        else:
            marks[lvl] = "off"
    level = level_for_channels(suppressed)  # visible | silenced | hidden | shadowed

    # "visible" is the default/no-suppression rung -- say "fully visible" so it
    # reads as "nothing is veiled" (silenced/hidden are still *visible*, just with
    # a layer suppressed; they keep their rung name).
    shown = "fully visible" if level == "visible" else level
    print(f"{canonical}: {shown}")
    for lvl in ("silenced", "hidden", "shadowed"):
        print(f"  {lvl:<9} {marks[lvl]}  ({descriptions[lvl]})")
    print()
    print(f"Across all tools: 'dz kit visibility'. "
          f"Adjust with 'dz kit silence|hide|shadow {canonical}'.")
    return 0
