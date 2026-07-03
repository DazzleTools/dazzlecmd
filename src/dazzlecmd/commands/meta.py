"""``dz meta`` -- the foreground/context namespace (SD-B).

``dz meta use <level>`` sets the re-choosable foreground level; ``dz use``
and ``dz level`` are its aliases. ``dz meta reset`` removes it (back to
the default). As of the FQCN property surface (v2 contract R1.7) the
foreground IS the root property ``<root>.level`` in the property store --
``dz .level``, ``dz prop get .level``, and ``dz level`` are one value. The
legacy ``foreground_level`` config key is MOVED into the store on first
touch (read, write, or delete -- all three, so a ``reset`` before any
other touch cannot resurrect a stale legacy value).

The foreground is a gentle DEFAULT, not an override: it breaks the tie on
a bare AMBIGUOUS read (``AggregatorEngine.resolve_target(...,
foreground=...)``), but an unambiguous name resolves to its one level
regardless, and a mutating ambiguous name still fails loud. So
foregrounding never silently mutates the wrong entity. Extended rungs
(``fiber``/``supra``...) are storable once LEVEL_CONTINUUM grows them --
they are inert at tie-break by design (the tie only ever sees
tool/kit/aggregator candidates).
"""

FOREGROUND_KEY = "foreground_level"   # the LEGACY config.json key (migrated)
DEFAULT_FOREGROUND = "tool"


def level_property_key(engine):
    """The canonical property key for the foreground: ``<root>.level``
    (SELF-rooted -- ``wtf.level`` for a wtf engine; v2 contract R1.2)."""
    return f"{engine.command}.level"


def level_validator(value):
    """Reject a value that is not a LEVEL_CONTINUUM rung. Reads the rungs
    AT CALL TIME so extending the continuum auto-widens the CLI (R1.7).
    Registered in VALIDATED_KEYS so the sugar (``dz .level x``) and the
    verbs reject identically (C-7); the message mirrors argparse's."""
    from dazzlecmd_lib.verb_axis import LEVEL_CONTINUUM
    ranks = LEVEL_CONTINUUM.ranks
    if value not in ranks:
        choices = ", ".join(f"'{r}'" for r in sorted(ranks, key=ranks.get))
        raise ValueError(
            f"invalid level: '{value}' (choose from {choices})"
        )


def register_level_property(engine):
    """Wire the level property's validator into the shared write path.
    Called once at app startup (beside the sugar_flags_hook)."""
    from dazzlecmd_lib.prop_commands import register_validated_key
    register_validated_key(level_property_key(engine), level_validator)


def _migrate_legacy(engine):
    """The one-time MOVE of the legacy config key into the property store
    (R1.7 -- a move, NOT a permanent fallback). Crash-safe order: write
    the property FIRST, then delete the legacy key (a crash between
    leaves both; the property wins on read; the delete retries on the
    next touch). The legacy delete uses ``ConfigManager.replace`` --
    ``write`` merges and cannot remove a key. Runs at most once (guarded
    on the legacy key's presence). Returns the property key."""
    key = level_property_key(engine)
    legacy = engine.config.read().get(FOREGROUND_KEY)
    if legacy is not None:
        if engine.property_store.get(key) is None:
            engine.property_store.set(key, legacy)
        data = dict(engine.config.read())
        data.pop(FOREGROUND_KEY, None)
        engine.config.replace(data)
    return key


def foreground_level(engine):
    """The user's current foreground level, default ``tool``."""
    if engine is None or not hasattr(engine, "config"):
        return DEFAULT_FOREGROUND
    key = _migrate_legacy(engine)
    return engine.property_store.get(key, DEFAULT_FOREGROUND)


def _cmd_meta(engine):
    """``dz meta`` -- report the foreground + the available context actions."""
    print(f"Foreground level: {foreground_level(engine)}")
    print("  dz level <rung>       set the foreground (aliases: use, meta use)")
    print("  dz meta reset         back to the default (tool)")
    print("  dz meta prop ...      property CRUD (get/set/add/delete/list)")
    return 0


def _cmd_meta_use(args, engine):
    """``dz level <rung>`` / ``dz use`` / ``dz meta use`` -- set the
    foreground (a validated property write); omit the rung to report."""
    import sys

    level = getattr(args, "level", None)
    if level is None:
        print(foreground_level(engine))
        return 0
    key = _migrate_legacy(engine)
    try:
        level_validator(level)
    except ValueError as exc:
        # exit-2 parity with the old argparse choices= error (R1.7)
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    engine.property_store.set(key, level)
    print(f"Foreground level set to: {level}")
    print("(a gentle default: it tie-breaks ambiguous bare names on reads; "
          "level-scoped listings land in a later release)")
    return 0


def _cmd_meta_reset(engine):
    """``dz meta reset`` -- remove the foreground property (== ``dz meta
    prop delete .level``); the default (``tool``) then applies. The
    migration runs FIRST so a stale legacy key cannot resurrect the old
    value afterwards (C-8: the move wraps delete too)."""
    key = _migrate_legacy(engine)
    engine.property_store.delete(key)
    print(f"Foreground level reset to the default ({DEFAULT_FOREGROUND}).")
    return 0
