"""``dz meta`` -- the foreground/context namespace (SD-B).

``dz meta use <level>`` sets the re-choosable foreground level (persisted in the
user config; the layered persistence model -- session/override rungs, the
source-precedence fold, the SYSTEM/USER split -- is epic #99). ``dz meta reset``
drops it back to the default. ``dz use <level>`` is a top-level alias.

The foreground is a gentle DEFAULT, not an override: it breaks the tie on a bare
AMBIGUOUS read (``AggregatorEngine.resolve_target(..., foreground=...)``), but an
unambiguous name resolves to its one level regardless, and a mutating ambiguous
name still fails loud. So foregrounding never silently mutates the wrong entity.
"""

FOREGROUND_KEY = "foreground_level"
DEFAULT_FOREGROUND = "tool"


def foreground_level(engine):
    """The user's current foreground level (``dz meta use``), default ``tool``."""
    if engine is None or not hasattr(engine, "config"):
        return DEFAULT_FOREGROUND
    return engine.config.read().get(FOREGROUND_KEY, DEFAULT_FOREGROUND)


def _cmd_meta(engine):
    """``dz meta`` -- report the foreground + the available context actions."""
    print(f"Foreground level: {foreground_level(engine)}")
    print("  dz meta use <tool|kit|aggregator>   set the foreground")
    print("  dz meta reset                        back to the default (tool)")
    return 0


def _cmd_meta_use(args, engine):
    """``dz meta use <level>`` -- set the foreground (persisted); omit to report."""
    level = getattr(args, "level", None)
    if level is None:
        print(foreground_level(engine))
        return 0
    engine.config.write({FOREGROUND_KEY: level})
    print(f"Foreground level set to: {level}")
    return 0


def _cmd_meta_reset(engine):
    """``dz meta reset`` -- foreground back to the default (``tool``).

    Scoped to the foreground for now; a broader "reset all user overrides" lands
    with the config-model epic #99. ``ConfigManager.write`` merges, so this sets
    the key to the default rather than removing it -- functionally identical, the
    default IS ``tool``.
    """
    engine.config.write({FOREGROUND_KEY: DEFAULT_FOREGROUND})
    print(f"Foreground level reset to the default ({DEFAULT_FOREGROUND}).")
    return 0
