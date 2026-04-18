"""User config read/write for dazzlecmd-pattern aggregators.

Config file: ``~/.dazzlecmd/config.json`` (overridable via
``DAZZLECMD_CONFIG`` environment variable).

Schema (Phase 3+):
    {
        "_schema_version": 1,
        "kit_precedence": [...],
        "active_kits": [...],
        "disabled_kits": [...],
        "favorites": {"short": "fqcn", ...},
        "silenced_hints": {"tools": [...], "kits": [...]},
        "shadowed_tools": [...],
        "kit_discovery": "auto"
    }

All keys are optional. Missing keys fall back to sensible defaults.
Malformed entries (wrong type, bad JSON) are tolerated with a stderr
warning and the malformed key is treated as absent.
"""

import json
import os
import sys
import tempfile


SCHEMA_VERSION = 1


class ConfigManager:
    """Reads and writes an aggregator's config file with caching and
    atomic writes.

    Path resolution order (highest priority first):
        1. ``DAZZLECMD_CONFIG`` env var (points to full file path;
           used for test isolation across all aggregators)
        2. ``config_dir`` constructor argument + ``config.json``
        3. Default ``~/.dazzlecmd/config.json`` (back-compat)

    Per-aggregator isolation: each ``AggregatorEngine`` passes its own
    ``config_dir`` (typically ``~/.<command>``) so wtf-windows uses
    ``~/.wtf/config.json`` while dazzlecmd uses ``~/.dz/config.json``
    — they don't share kit precedence, favorites, or silencing.

    Instantiate once per engine and reuse.
    """

    def __init__(self, config_dir=None):
        """Initialize.

        Args:
            config_dir: Directory containing ``config.json`` for this
                aggregator. If None, falls back to ``~/.dazzlecmd``.
                The ``DAZZLECMD_CONFIG`` env var, if set, overrides
                both.
        """
        self._cache = None
        self._config_dir_override = config_dir

    def config_path(self):
        """Return the active config file path (lazy, env-overridable)."""
        override = os.environ.get("DAZZLECMD_CONFIG")
        if override:
            return override
        if self._config_dir_override:
            return os.path.join(self._config_dir_override, "config.json")
        return os.path.expanduser("~/.dazzlecmd/config.json")

    def config_dir(self):
        """Return the directory containing the active config file."""
        return os.path.dirname(self.config_path())

    def read(self):
        """Return the parsed config as a dict (cached after first read).

        Tolerates missing file, malformed JSON, and non-dict root.
        """
        if self._cache is not None:
            return self._cache

        path = self.config_path()
        if not os.path.isfile(path):
            self._cache = {}
            return self._cache

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"Warning: could not read {path}: {exc}",
                file=sys.stderr,
            )
            self._cache = {}
            return self._cache

        if not isinstance(config, dict):
            print(
                f"Warning: {path} is not a JSON object, ignoring",
                file=sys.stderr,
            )
            self._cache = {}
            return self._cache

        self._cache = config
        return self._cache

    def get_list(self, key, default=None):
        """Return a list-valued config key, validated."""
        config = self.read()
        value = config.get(key)
        if value is None:
            return default
        if not isinstance(value, list):
            print(
                f"Warning: config key '{key}' is not a list, ignoring",
                file=sys.stderr,
            )
            return default
        return value

    def get_dict(self, key, default=None):
        """Return a dict-valued config key, validated."""
        config = self.read()
        value = config.get(key)
        if value is None:
            return default if default is not None else {}
        if not isinstance(value, dict):
            print(
                f"Warning: config key '{key}' is not a dict, ignoring",
                file=sys.stderr,
            )
            return default if default is not None else {}
        return value

    def write(self, updates):
        """Merge ``updates`` into the config and write atomically.

        Creates the config directory on first write. Injects
        ``_schema_version`` if missing. Invalidates the read cache.
        """
        path = self.config_path()
        dir_ = self.config_dir()

        existing = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    existing = loaded
            except (json.JSONDecodeError, OSError):
                existing = {}

        existing.setdefault("_schema_version", SCHEMA_VERSION)
        existing.update(updates)

        os.makedirs(dir_, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            prefix=".config.json.", suffix=".tmp", dir=dir_
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=4, sort_keys=False)
                f.write("\n")
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        self._cache = None

    def invalidate(self):
        """Clear the read cache so the next read() re-reads the file."""
        self._cache = None
