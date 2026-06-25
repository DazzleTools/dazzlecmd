"""Kit-lifecycle command handlers: the activation and favorite axes.

Moved out of cli.py (decomposition R1, DWP 2026-06-25__16-14-19). These are the
``dz kit enable|disable|focus|reset|favorite|unfavorite`` handlers plus the
``_kit_exists`` predicate and the favorite-migration helpers. cli.py re-exports
every public name here (dispatch_meta and the test-suite import them from
``dazzlecmd.cli``). This module imports nothing from cli.py -- one-directional.
"""
import os
import sys

def _kit_exists(kits, name):
    """Return True if a kit with the given name is discovered."""
    return any(
        (k.kit_name or k.name) == name for k in kits
    )


def _cmd_kit_enable(args, engine):
    """Enable a kit: add to active_kits, drop from disabled_kits.

    The activation 'enable' transition -- a lateral (reversible) toggle run through
    ActivationContext (the activation analog of the visibility hide/expose contexts).
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # Warn if the kit doesn't exist on disk (informational -- the toggle still
    # applies, so it takes effect if the kit becomes available later).
    if engine.kits and not _kit_exists(engine.kits, name):
        print(
            f"Warning: kit '{name}' not found among discovered kits. "
            f"Change will apply if the kit becomes available later.",
            file=sys.stderr,
        )

    from dazzlecmd_lib.contexts import ActivationContext
    ActivationContext(engine).enable(name)
    print(f"Enabled kit: {name}")
    return 0


def _cmd_kit_disable(args, engine):
    """Disable a kit: add to disabled_kits, drop from active_kits.

    The activation 'disable' transition -- the lateral inverse of enable, run
    through ActivationContext.
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    if engine.kits and not _kit_exists(engine.kits, name):
        print(
            f"Warning: kit '{name}' not found among discovered kits.",
            file=sys.stderr,
        )

    from dazzlecmd_lib.contexts import ActivationContext
    ActivationContext(engine).disable(name)
    print(f"Disabled kit: {name}")
    return 0


def _cmd_kit_focus(args, kits, engine):
    """Enable the named kit and disable all others (except always_active)."""
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    if not _kit_exists(kits, name):
        print(f"Error: kit '{name}' not found.", file=sys.stderr)
        return 1

    new_active = [name]
    new_disabled = []
    preserved = []
    for kit in kits:
        kname = kit.kit_name or kit.name
        if kname == name:
            continue
        if kit.always_active:
            preserved.append(kname)
            continue
        new_disabled.append(kname)

    engine._write_user_config({
        "active_kits": new_active,
        "disabled_kits": new_disabled,
    })
    print(f"Focused on '{name}'.")
    if new_disabled:
        print(f"  Disabled: {', '.join(new_disabled)}")
    if preserved:
        print(f"  Preserved (always_active): {', '.join(preserved)}")
    return 0


def _cmd_kit_reset(args, engine):
    """Wipe the user config after confirmation."""
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    path = engine._config_path()
    if not os.path.isfile(path):
        print("No config to reset.")
        return 0

    if not args.yes:
        print(f"This will delete {path} and clear all kit preferences.")
        try:
            answer = input("Continue? [y/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 1

    try:
        os.unlink(path)
    except OSError as exc:
        print(f"Error: could not remove {path}: {exc}", file=sys.stderr)
        return 1

    # Invalidate caches
    engine._config_cache = None
    engine._precedence_cache = None
    print("Config cleared.")
    return 0


def _cmd_kit_favorite(args, engine):
    """Set a favorite binding: short name -> FQCN.

    With ``--migrate-stale`` (and no positional args), enters the
    interactive stale-favorite migration flow instead. See
    :func:`_cmd_kit_favorite_migrate_stale`.
    """
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    if getattr(args, "migrate_stale", False):
        if args.short is not None or args.fqcn is not None:
            print(
                "Error: --migrate-stale takes no positional arguments.",
                file=sys.stderr,
            )
            return 1
        return _cmd_kit_favorite_migrate_stale(engine)

    if args.short is None or args.fqcn is None:
        print(
            "Error: 'dz kit favorite' requires <short> <fqcn> positional "
            "args, or use --migrate-stale.",
            file=sys.stderr,
        )
        return 1

    short = args.short
    fqcn = args.fqcn

    # Reject reserved command names
    reserved = engine.reserved_commands
    if short in reserved:
        print(
            f"Error: '{short}' is a reserved command name and cannot "
            f"be set as a favorite.",
            file=sys.stderr,
        )
        return 1

    # Warn if the target FQCN isn't discovered. Accepts either a
    # canonical FQCN or a virtual-kit alias FQCN -- both are valid
    # favorite targets (see FQCNIndex.resolve for favorite-on-alias
    # semantics).
    if hasattr(engine, "fqcn_index") and (
        fqcn not in engine.fqcn_index.canonical_index
        and fqcn not in engine.fqcn_index.alias_index
    ):
        print(
            f"Warning: target FQCN '{fqcn}' not found in the current "
            f"discovery. Favorite saved but may be stale.",
            file=sys.stderr,
        )

    config = engine._get_user_config()
    favorites = dict(config.get("favorites") or {})
    favorites[short] = fqcn

    engine._write_user_config({"favorites": favorites})
    print(f"Favorite set: {short} -> {fqcn}")
    return 0


def _suggest_favorite_replacement(short, stale_fqcn, engine):
    """Suggest a likely replacement for a stale favorite, or None.

    Heuristic: if exactly one currently-discovered tool registers ``short``
    as its short name (in ``engine.fqcn_index.short_index``), that's the
    suggestion. Returns its canonical FQCN.

    For ambiguous cases (zero or multiple short-name matches) we return
    None and let the user pick manually -- guessing wrong is worse than
    not guessing.
    """
    if not hasattr(engine, "fqcn_index"):
        return None
    candidates = engine.fqcn_index.short_index.get(short, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def _cmd_kit_favorite_migrate_stale(engine):
    """Interactively migrate stale favorites.

    Walks every favorite in user config, checks whether the target FQCN
    still resolves (matches a canonical OR an alias), and for each stale
    entry prompts the user to remap, drop, or skip. Writes the updated
    favorites map back to user config at the end.

    Non-TTY invocations print the stale list with suggestions and exit
    non-zero -- the migration requires interactive input.
    """
    config = engine._get_user_config()
    favorites = dict(config.get("favorites") or {})

    if not favorites:
        print("No favorites configured.")
        return 0

    canonical_index = (
        engine.fqcn_index.canonical_index
        if hasattr(engine, "fqcn_index") else {}
    )
    alias_index = (
        engine.fqcn_index.alias_index
        if hasattr(engine, "fqcn_index") else {}
    )

    stale = []
    for short, fqcn in favorites.items():
        # Same resolution rule as FQCNIndex.resolve favorite-check:
        # the favorite target must be either a canonical FQCN or an
        # alias FQCN whose canonical target is currently discovered.
        if fqcn in canonical_index:
            continue
        if fqcn in alias_index:
            canonical_target = alias_index[fqcn]
            if canonical_target in canonical_index:
                continue
        stale.append((short, fqcn))

    if not stale:
        print(
            f"No stale favorites. {len(favorites)} favorite(s) all resolve "
            f"correctly."
        )
        return 0

    if not sys.stdin.isatty():
        print(f"Found {len(stale)} stale favorite(s):", file=sys.stderr)
        for short, fqcn in stale:
            suggestion = _suggest_favorite_replacement(short, fqcn, engine)
            if suggestion:
                print(
                    f"  {short} -> {fqcn}  (suggestion: {suggestion})",
                    file=sys.stderr,
                )
            else:
                print(f"  {short} -> {fqcn}", file=sys.stderr)
        print(
            "\nMigration requires an interactive shell. Re-run from a "
            "TTY, or use 'dz kit unfavorite <short>' to drop entries "
            "manually.",
            file=sys.stderr,
        )
        return 1

    print(f"Found {len(stale)} stale favorite(s).\n")
    remapped = 0
    dropped = 0
    skipped = 0

    for short, fqcn in stale:
        suggestion = _suggest_favorite_replacement(short, fqcn, engine)
        print(f"Stale: {short} -> {fqcn}  (target not found)")
        if suggestion:
            print(f"  [r] remap to {suggestion}")
            choices = "r/d/s"
        else:
            print("  (no obvious replacement found)")
            choices = "d/s"
        print("  [d] drop this favorite")
        print("  [s] skip (keep stale)")
        try:
            response = input(f"Choose [{choices}]: ").strip().lower()
        except EOFError:
            response = "s"

        if response == "r" and suggestion:
            favorites[short] = suggestion
            remapped += 1
            print(f"  -> remapped to {suggestion}")
        elif response == "d":
            del favorites[short]
            dropped += 1
            print("  -> dropped")
        else:
            skipped += 1
            print("  -> skipped")
        print()

    if remapped or dropped:
        engine._write_user_config({"favorites": favorites})
    print(
        f"Migration complete: {len(stale)} stale, {remapped} remapped, "
        f"{dropped} dropped, {skipped} skipped."
    )
    return 0


def _cmd_kit_unfavorite(args, engine):
    """Remove a favorite binding."""
    short = args.short
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    config = engine._get_user_config()
    favorites = dict(config.get("favorites") or {})
    if short not in favorites:
        print(f"No favorite set for '{short}'.")
        return 0

    del favorites[short]
    engine._write_user_config({"favorites": favorites})
    print(f"Favorite removed: {short}")
    return 0
