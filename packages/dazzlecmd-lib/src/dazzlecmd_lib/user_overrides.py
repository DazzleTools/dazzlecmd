"""Per-user override file loading -- groundwork for v0.7.19 and beyond.

v0.7.19 ships this module as infrastructure. The runtime resolver does not
(yet) consult overrides at dispatch time; issue #40 (multi-platform setup)
will be the first production caller. Runtime may grow a per-host override
story later and use the same module.

Directory layout:

    <override-root>/
      setup/
        <namespace>__<tool>.json     # overrides for a setup block
      runtime/
        <namespace>__<tool>.json     # overrides for a runtime block (future)

`<override-root>` is:
    - os.environ["DAZZLECMD_OVERRIDES_DIR"] if set
    - else ~/.dazzlecmd/overrides/

FQCNs containing colons (e.g. "dazzletools:fixpath") map to "dazzletools__fixpath"
on disk to avoid Windows filesystem issues. Double-underscore is the separator
because colons and other reserved punctuation cannot appear in FQCN component
names.

Schema: override files are JSON objects. `_schema_version` is checked on load
via schema_version.check_schema_version. Absence defaults to current version.

All I/O is read-only: this module loads overrides; it does not create, write,
or delete them. Writing is a CLI concern, not a library concern.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from dazzlecmd_lib.schema_version import check_schema_version


OVERRIDE_ENV_VAR = "DAZZLECMD_OVERRIDES_DIR"
DEFAULT_OVERRIDE_SUBPATH = Path(".dazzlecmd") / "overrides"
FQCN_SEPARATOR_REPLACEMENT = "__"


# Module-level override set via set_override_root(). Used when the
# engine wants per-aggregator override isolation (e.g. wtf-windows
# uses ~/.wtf/overrides instead of ~/.dazzlecmd/overrides). Tests
# typically use the env var instead.
_override_root_override: Optional[Path] = None


def set_override_root(path) -> None:
    """Set the base directory for override file lookup.

    Called by ``AggregatorEngine`` at construction to route overrides
    through the engine's config_dir (e.g. ``~/.wtf/overrides`` for a
    wtf-windows engine). Passing ``None`` clears the override; the
    default ``~/.dazzlecmd/overrides`` is then used.

    Note: this is module-level state. In the typical single-aggregator
    process (the common case), this is fine. If multiple aggregators
    run in the same process, the last-constructed engine's root wins.
    """
    global _override_root_override
    _override_root_override = Path(path) if path is not None else None


def get_override_root() -> Path:
    """Return the base directory for user override files.

    Order of precedence (highest first):
        1. os.environ[DAZZLECMD_OVERRIDES_DIR] if set and non-empty.
           (test-isolation override; works across all aggregators)
        2. The path passed to ``set_override_root()`` if set.
           (per-engine override; typically engine's config_dir/overrides)
        3. Path.home() / ".dazzlecmd" / "overrides"
           (historical default; used when no aggregator context is set)
    """
    env_value = os.environ.get(OVERRIDE_ENV_VAR)
    if env_value:
        return Path(env_value)
    if _override_root_override is not None:
        return _override_root_override
    return Path.home() / DEFAULT_OVERRIDE_SUBPATH


def _fqcn_to_filename(fqcn: str) -> str:
    """Map an FQCN like 'dazzletools:fixpath' to a safe filesystem stem."""
    return fqcn.replace(":", FQCN_SEPARATOR_REPLACEMENT)


def get_override_path(layer: str, fqcn: str) -> Path:
    """Return the full path where a per-user override would live.

    Does not check for file existence. Use load_override() to actually load.
    """
    if not layer or not isinstance(layer, str):
        raise ValueError(f"layer must be a non-empty string, got {layer!r}")
    if not fqcn or not isinstance(fqcn, str):
        raise ValueError(f"fqcn must be a non-empty string, got {fqcn!r}")
    filename = _fqcn_to_filename(fqcn) + ".json"
    return get_override_root() / layer / filename


def load_override(layer: str, fqcn: str) -> Optional[dict]:
    """Load a per-user override file if it exists.

    Returns:
        The parsed dict on success (with _schema_version validated).
        None if no override file is present at the expected path.

    Raises:
        UnsupportedSchemaVersionError: file exists but declares a schema
            version this library does not support.
        json.JSONDecodeError: file exists but is not valid JSON.
        OSError: file exists but cannot be read (permissions, etc.).
    """
    path = get_override_path(layer, fqcn)
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(
            f"override file must contain a JSON object at top level, "
            f"got {type(data).__name__}: {path}"
        )
    check_schema_version(data, context=f"override {path}")
    return data
