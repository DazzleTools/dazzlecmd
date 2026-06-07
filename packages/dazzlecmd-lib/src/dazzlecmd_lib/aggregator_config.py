"""Declarative aggregator configuration via ``aggregator.json``.

Every dazzlecmd-lib consumer (dazzlecmd, wtf-windows, amdead, etc.) declares
its identity and layout in an ``aggregator.json`` file at its project root.
The library reads this file to construct an ``AggregatorEngine`` with the
right parameters, replacing the previous pattern of hand-coded
``AggregatorEngine(name=..., command=..., tools_dir=..., ...)`` calls in
each aggregator's main module.

The file is **required** -- no backward-compat fallback. An aggregator
without ``aggregator.json`` at its project root cannot construct an engine
via the canonical ``AggregatorEngine.from_project(project_root)`` path.

Schema (v1)::

    {
        "_schema_version": 1,
        "name": "dazzlecmd",
        "command": "dz",
        "description": "one-line description",
        "tools_dir": "projects",
        "kits_dir": "kits",
        "manifest_name": ".dazzlecmd.json",
        "enabled_meta_commands": ["list", "info", "kit", "tree", "setup",
                                  "version", "add", "mode", "new"],
        "extra_reserved_commands": ["find", "git", ...],
        "schema": {
            "remote_url_paths": ["source.url", "lifecycle.remote"],
            "lifecycle_path": "lifecycle"
        },
        "discovery": {
            "tool_patterns": ["${tools_dir}/*/*"],
            "scan_hidden": false
        }
    }

Field semantics:

- ``_schema_version``: integer; ``1`` for this format. Forward-compat
  hook -- future library versions can migrate older files.
- ``name``: human-readable aggregator name (appears in ``--help``).
- ``command``: CLI command name (``dz``, ``wtf``, ``amdead``). Substituted
  into user-facing strings (no more hardcoded ``"dz"``).
- ``description``: one-line description for ``--help``.
- ``tools_dir``: relative directory name where tool projects live. Replaces
  the hardcoded ``"projects/"`` literals throughout the codebase
  (issue #37 BLOCKERs F2/F3/F4/F8).
- ``kits_dir``: relative directory name for kit registry pointers.
- ``manifest_name``: per-tool manifest filename
  (``.dazzlecmd.json`` / ``.wtf.json`` / ``.amdead.json`` / ...).
- ``enabled_meta_commands``: list of meta-command names this aggregator
  registers as CLI subcommands. Subset of ``DEFAULT_RESERVED_COMMANDS``.
  Defaults to ``DEFAULT_META_COMMANDS_USER`` when omitted.
- ``extra_reserved_commands``: additional names reserved beyond
  ``DEFAULT_RESERVED_COMMANDS``. Use sparingly -- only for names that
  the aggregator wants to keep available as future meta-commands but
  isn't using yet. Existing tools' names should NOT appear here (the
  library would silently skip them during discovery; pre-v0.7.51 had
  this regression in the dazzlecmd fixture).
- ``schema.remote_url_paths``: ordered list of dotted paths the library
  tries when resolving a tool's remote URL. Each entry is a fallback.
  Replaces hardcoded ``project["source"]["url"]`` / ``project["lifecycle"]["remote"]``
  (BLOCKER F7 schema decoupling).
- ``schema.lifecycle_path``: dotted path for the lifecycle metadata block.
- ``discovery.tool_patterns``: list of glob patterns for finding tools
  beyond the standard ``<tools_dir>/<ns>/<tool>`` layout. ``${tools_dir}``
  is interpolated from the same JSON.
- ``discovery.scan_hidden``: whether ``.dotdirs`` are scanned (default
  ``false``).

Subprocess environment contract
-------------------------------

The library injects the following environment variables before invoking
any tool subprocess. Tool scripts (PowerShell, bash, Python, etc.) can
read these to adapt branding strings, log paths, and behavior to the
host aggregator without each aggregator hand-rolling its own bridge:

- ``DZ_APP_NAME``: the engine's ``name`` field (e.g., ``"dazzlecmd"``,
  ``"wtf-windows"``, ``"amdead"``). Reflects engine IDENTITY, not
  per-invocation context. Set at every dispatch site.
- ``DZ_COMMAND``: the engine's ``command`` field (e.g., ``"dz"``,
  ``"wtf"``, ``"amdead"``). Same semantics as ``DZ_APP_NAME``.
- ``DZ_CANONICAL_FQCN``: canonical FQCN of the dispatched tool (e.g.,
  ``"core:rn"``). Set only when a ``ResolutionContext`` is supplied to
  the dispatcher. Tools writing persistent state (caches, logs,
  checkpoints) MUST key on this to avoid divergent state across
  alias-vs-canonical-vs-short-name invocation paths (v0.7.28).
- ``DZ_INVOKED_FQCN``: what the user actually typed (alias, short name,
  or canonical). Equal to ``DZ_CANONICAL_FQCN`` for canonical
  invocations. Same gating as ``DZ_CANONICAL_FQCN``.

All four vars are restored to their pre-dispatch values in a
``finally`` block after the subprocess completes, so dz's own process
environment is not permanently modified.

Nested-aggregator behavior: when one aggregator embeds another as a kit
(e.g., dazzlecmd embeds wtf-windows so ``dz wtf:locked`` dispatches a
wtf tool), ``DZ_APP_NAME`` and ``DZ_COMMAND`` reflect the **ROOT
ENGINE** (``"dazzlecmd"`` / ``"dz"``), not the kit's owning aggregator.
This matches the user's experience (they typed ``dz``, not ``wtf``) but
tool authors should not assume their original aggregator's identity is
present in these vars at runtime.

A ``DZ_PROJECT_ROOT`` env var was considered (would expose the
aggregator's project_root absolute path so tools can resolve log
destinations etc. relative to it) but is deferred to a follow-up issue.
It introduces tool-to-aggregator filesystem coupling that warrants a
separate design pass. Tools needing the project root today can read
``DZ_APP_NAME`` and look the project up via ``find_aggregator_root()``
or via configuration.
"""

from __future__ import annotations

import json
import os
import warnings
from typing import List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict

from dazzlecmd_lib.reserved import (
    DEFAULT_META_COMMANDS_USER,
    DEFAULT_RESERVED_COMMANDS,
)


AGGREGATOR_CONFIG_FILENAME = "aggregator.json"
CURRENT_SCHEMA_VERSION = 1

# Defaults referenced by BOTH the model fields and the parse helpers, so the
# parse helpers don't reach into model internals (the old code read
# ``__dataclass_fields__[...].default``, which Pydantic models don't expose).
_DEFAULT_REMOTE_URL_PATHS = ("source.url", "lifecycle.remote")
_DEFAULT_LIFECYCLE_PATH = "lifecycle"
_DEFAULT_TOOL_PATTERNS = ("${tools_dir}/*/*",)


class AggregatorConfigError(Exception):
    """Raised when ``aggregator.json`` is missing, malformed, or invalid."""


def find_aggregator_root(start_path=None, max_depth=12):
    """Walk up from ``start_path`` to find a directory with ``aggregator.json``.

    The first ancestor (including ``start_path`` itself) containing the
    canonical marker file is the project root. This is the new
    discovery strategy (Phase 3.5 T1-M): the presence of
    ``aggregator.json`` itself defines the project root, instead of
    requiring tools_dir + kits_dir hardcoded knowledge to find it.

    **Entry points MUST pass an explicit ``start_path`` anchored to their
    own package location** -- typically
    ``os.path.dirname(os.path.abspath(__file__))`` of the aggregator's
    ``cli`` module. This pins the aggregator's identity to *which package
    it is*, not *where it is invoked from*. An aggregator that calls this
    bare (relying on the cwd default) will impersonate whatever other
    aggregator the user happens to be standing in: running ``dz`` from
    inside a ``wtf-windows`` checkout would load wtf's ``aggregator.json``
    and ``dz`` would become ``wtf``. The package anchor avoids that
    because the entry point's ``__file__`` is fixed at install time.

    When ``start_path`` is ``None`` the walk starts from ``os.getcwd()``.
    This "find from the current directory" behavior is for tests and
    ad-hoc tooling that genuinely want cwd-relative discovery -- NOT for
    production entry points. (Earlier revisions also fell back to this
    module's own ``__file__``; that was removed because the library lives
    co-located with dazzlecmd in dev mode, so the fallback made every
    aggregator that called this bare resolve to dazzlecmd.)

    Args:
        start_path: Directory to start the walk from. Production entry
            points pass their package's ``__file__`` directory. Defaults
            to ``os.getcwd()`` (tests / ad-hoc cwd-relative discovery).
        max_depth: Maximum number of parent directories to walk before
            giving up. Defaults to 12 (deep enough for any sane layout,
            shallow enough to terminate quickly when the marker is
            absent).

    Returns:
        Absolute path to the project root, or ``None`` if no
        ``aggregator.json`` was found within ``max_depth`` ancestors of
        the starting point.
    """
    if start_path is None:
        start_path = os.getcwd()
    current = os.path.abspath(start_path)
    for _ in range(max_depth + 1):
        if os.path.isfile(os.path.join(current, AGGREGATOR_CONFIG_FILENAME)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return None


class AggregatorSchema(BaseModel):
    """How the engine reads tool-manifest values.

    Decouples library code from any single manifest format
    (.dazzlecmd.json vs .wtf.json vs .amdead.json).
    """

    model_config = ConfigDict(frozen=True)

    remote_url_paths: Tuple[str, ...] = _DEFAULT_REMOTE_URL_PATHS
    lifecycle_path: str = _DEFAULT_LIFECYCLE_PATH


class AggregatorDiscovery(BaseModel):
    """Glob patterns + flags for finding tools beyond the standard layout."""

    model_config = ConfigDict(frozen=True)

    tool_patterns: Tuple[str, ...] = _DEFAULT_TOOL_PATTERNS
    scan_hidden: bool = False


# The ``schema`` field name deliberately shadows Pydantic's deprecated
# ``BaseModel.schema()`` (callers use ``config.schema`` throughout). Suppress
# the one benign class-definition UserWarning so it never reaches a ``dz``
# user's stderr (which would also break the byte-identical output baseline).
# The model functions correctly -- verified empirically on pydantic 2.11.7.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r'Field name "schema".*shadows an attribute.*',
        category=UserWarning,
    )

    class AggregatorConfig(BaseModel):
        """Parsed ``aggregator.json``.

        Constructed by ``load_aggregator_config(project_root)``. Frozen so it
        can be safely passed around as engine state.
        """

        model_config = ConfigDict(frozen=True)

        project_root: str
        schema_version: int
        name: str
        command: str
        description: str
        tools_dir: str
        kits_dir: str
        manifest_name: str
        enabled_meta_commands: frozenset
        reserved_commands: frozenset
        schema: AggregatorSchema
        discovery: AggregatorDiscovery
        # Reserved slot (v0.8.0): the "skin" half of same-bones -- per-aggregator
        # presentation/projection config (visibility frames, render hints). Read
        # but not yet consumed; the grouping/ungrouping projection layer that
        # interprets it lands in a later release. Kept as a plain dict so the
        # eventual schema can evolve without a config-format migration.
        presentation: Optional[dict] = None

        def resolved_discovery_patterns(self) -> Tuple[str, ...]:
            """Return ``discovery.tool_patterns`` with ``${tools_dir}`` expanded."""
            return tuple(
                pattern.replace("${tools_dir}", self.tools_dir)
                for pattern in self.discovery.tool_patterns
            )


def _require(data: dict, key: str, source: str) -> object:
    if key not in data:
        raise AggregatorConfigError(
            f"{source}: required key '{key}' missing"
        )
    return data[key]


def _str_field(data: dict, key: str, source: str) -> str:
    value = _require(data, key, source)
    if not isinstance(value, str) or not value.strip():
        raise AggregatorConfigError(
            f"{source}: '{key}' must be a non-empty string (got {value!r})"
        )
    return value


def _optional_str(data: dict, key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise AggregatorConfigError(
            f"'{key}' must be a string (got {value!r})"
        )
    return value


def _optional_list_of_str(data: dict, key: str, default: List[str],
                          source: str) -> List[str]:
    value = data.get(key, default)
    if not isinstance(value, list):
        raise AggregatorConfigError(
            f"{source}: '{key}' must be a list (got {type(value).__name__})"
        )
    for item in value:
        if not isinstance(item, str):
            raise AggregatorConfigError(
                f"{source}: '{key}' entries must be strings (got {item!r})"
            )
    return list(value)


def _parse_schema(data: dict, source: str) -> AggregatorSchema:
    block = data.get("schema") or {}
    if not isinstance(block, dict):
        raise AggregatorConfigError(
            f"{source}: 'schema' must be an object (got {type(block).__name__})"
        )
    remote_paths = _optional_list_of_str(
        block, "remote_url_paths",
        list(_DEFAULT_REMOTE_URL_PATHS),
        f"{source}: schema",
    )
    lifecycle_path = _optional_str(
        block, "lifecycle_path",
        _DEFAULT_LIFECYCLE_PATH,
    )
    return AggregatorSchema(
        remote_url_paths=tuple(remote_paths),
        lifecycle_path=lifecycle_path,
    )


def _parse_discovery(data: dict, source: str) -> AggregatorDiscovery:
    block = data.get("discovery") or {}
    if not isinstance(block, dict):
        raise AggregatorConfigError(
            f"{source}: 'discovery' must be an object (got {type(block).__name__})"
        )
    patterns = _optional_list_of_str(
        block, "tool_patterns",
        list(_DEFAULT_TOOL_PATTERNS),
        f"{source}: discovery",
    )
    scan_hidden = block.get("scan_hidden", False)
    if not isinstance(scan_hidden, bool):
        raise AggregatorConfigError(
            f"{source}: discovery.scan_hidden must be a boolean "
            f"(got {scan_hidden!r})"
        )
    return AggregatorDiscovery(
        tool_patterns=tuple(patterns),
        scan_hidden=scan_hidden,
    )


def load_aggregator_config(project_root: str) -> AggregatorConfig:
    """Load and validate ``aggregator.json`` from ``project_root``.

    Raises ``AggregatorConfigError`` if the file is missing, unreadable,
    not valid JSON, has an unknown ``_schema_version``, or fails field
    validation.
    """
    project_root = os.path.abspath(project_root)
    config_path = os.path.join(project_root, AGGREGATOR_CONFIG_FILENAME)
    source = f"{config_path}"

    if not os.path.isfile(config_path):
        raise AggregatorConfigError(
            f"aggregator.json not found at {config_path}. "
            f"Every dazzlecmd-lib aggregator must declare an aggregator.json "
            f"at its project root. See docs/guides/aggregator-config.md for "
            f"the schema."
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise AggregatorConfigError(
            f"Could not read {source}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise AggregatorConfigError(
            f"{source} is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise AggregatorConfigError(
            f"{source}: top-level value must be a JSON object "
            f"(got {type(data).__name__})"
        )

    schema_version = data.get("_schema_version", 1)
    if not isinstance(schema_version, int):
        raise AggregatorConfigError(
            f"{source}: '_schema_version' must be an integer "
            f"(got {schema_version!r})"
        )
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise AggregatorConfigError(
            f"{source}: unsupported _schema_version {schema_version}; "
            f"this library supports version {CURRENT_SCHEMA_VERSION}"
        )

    name = _str_field(data, "name", source)
    command = _str_field(data, "command", source)
    tools_dir = _str_field(data, "tools_dir", source)
    kits_dir = _str_field(data, "kits_dir", source)
    manifest_name = _str_field(data, "manifest_name", source)
    description = _optional_str(data, "description", f"{name} - tool aggregator")

    enabled_list = _optional_list_of_str(
        data, "enabled_meta_commands",
        list(DEFAULT_META_COMMANDS_USER),
        source,
    )
    enabled_meta_commands = frozenset(enabled_list)
    unknown = enabled_meta_commands - DEFAULT_RESERVED_COMMANDS
    if unknown:
        raise AggregatorConfigError(
            f"{source}: 'enabled_meta_commands' contains names not in the "
            f"reserved set: {sorted(unknown)}. Allowed: "
            f"{sorted(DEFAULT_RESERVED_COMMANDS)}"
        )

    extra_reserved_list = _optional_list_of_str(
        data, "extra_reserved_commands", [], source,
    )
    reserved_commands = DEFAULT_RESERVED_COMMANDS | frozenset(extra_reserved_list)

    schema = _parse_schema(data, source)
    discovery = _parse_discovery(data, source)

    presentation = data.get("presentation")
    if presentation is not None and not isinstance(presentation, dict):
        raise AggregatorConfigError(
            f"{source}: 'presentation' must be an object "
            f"(got {type(presentation).__name__})"
        )

    return AggregatorConfig(
        project_root=project_root,
        schema_version=schema_version,
        name=name,
        command=command,
        description=description,
        tools_dir=tools_dir,
        kits_dir=kits_dir,
        manifest_name=manifest_name,
        enabled_meta_commands=enabled_meta_commands,
        reserved_commands=reserved_commands,
        schema=schema,
        discovery=discovery,
        presentation=presentation,
    )
