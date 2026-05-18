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
- ``extra_reserved_commands``: additional names reserved beyond the library
  defaults -- blocks them from being used as tool names without exposing
  them as meta-commands (e.g., dazzlecmd reserves ``find``, ``git``,
  ``github``, ``safedel`` because those are top-level tool commands).
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
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

from dazzlecmd_lib.reserved import (
    DEFAULT_META_COMMANDS_USER,
    DEFAULT_RESERVED_COMMANDS,
)


AGGREGATOR_CONFIG_FILENAME = "aggregator.json"
CURRENT_SCHEMA_VERSION = 1


class AggregatorConfigError(Exception):
    """Raised when ``aggregator.json`` is missing, malformed, or invalid."""


@dataclass(frozen=True)
class AggregatorSchema:
    """How the engine reads tool-manifest values.

    Decouples library code from any single manifest format
    (.dazzlecmd.json vs .wtf.json vs .amdead.json).
    """

    remote_url_paths: Tuple[str, ...] = ("source.url", "lifecycle.remote")
    lifecycle_path: str = "lifecycle"


@dataclass(frozen=True)
class AggregatorDiscovery:
    """Glob patterns + flags for finding tools beyond the standard layout."""

    tool_patterns: Tuple[str, ...] = ("${tools_dir}/*/*",)
    scan_hidden: bool = False


@dataclass(frozen=True)
class AggregatorConfig:
    """Parsed ``aggregator.json``.

    Constructed by ``load_aggregator_config(project_root)``. Frozen so it
    can be safely passed around as engine state.
    """

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
        list(AggregatorSchema.__dataclass_fields__["remote_url_paths"].default),
        f"{source}: schema",
    )
    lifecycle_path = _optional_str(
        block, "lifecycle_path",
        AggregatorSchema.__dataclass_fields__["lifecycle_path"].default,
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
        list(AggregatorDiscovery.__dataclass_fields__["tool_patterns"].default),
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
    )
