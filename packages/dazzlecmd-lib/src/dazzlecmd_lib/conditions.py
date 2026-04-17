"""detect_when condition evaluator -- shared library for setup and runtime.

A `detect_when` block is a JSON object describing a boolean predicate over the
host environment. Both the setup resolver (is this platform's install branch
active?) and the runtime resolver (should this `prefer` entry be selected?)
consume the same evaluator.

Supported matcher keys (leaf):

    file_exists: "/path/to/file"
        True if the path exists and is a regular file.

    dir_exists: "/path/to/dir"
        True if the path exists and is a directory.

    env_var: "VAR_NAME"
        True if the env var is set AND non-empty. Values are never logged.

    env_var_equals: {"name": "VAR_NAME", "value": "expected"}
        True if os.environ[name] == value (strict string equality).
        Values are never logged.

    command_available: "bun"
        True if shutil.which(name) resolves (PATH + PATHEXT on Windows).

    uname_contains: "microsoft"
        Case-insensitive substring match against a composite PlatformInfo
        string: "<os> <subtype> <arch> <version> [wsl]".

Combinators:

    all: [<condition>, ...]   AND of sub-conditions. `all: []` is vacuously True.
    any: [<condition>, ...]   OR of sub-conditions. `any: []` is vacuously False.

Composition:

    - Multiple keys in the SAME dict are AND'd:
        {"file_exists": "/etc/debian_version", "command_available": "apt"}
        passes only if both hold.

    - Keys beginning with "_" are treated as metadata (e.g. "_schema_version",
      "_comment") and ignored by the evaluator.

    - An empty condition dict is vacuously True.

    - Unknown matcher keys raise ConditionSyntaxError. Authors hitting a typo
      see it immediately rather than silently falling through.

Security: env var VALUES are never included in error messages or return values,
only names and presence. A condition checking a secret-bearing env var will
not leak the secret via a diagnostic trace.
"""

from __future__ import annotations

import os
import shutil
from typing import Any, List, Optional

from dazzlecmd_lib.platform_detect import PlatformInfo


class ConditionSyntaxError(ValueError):
    """Raised when a condition dict contains unknown keys or malformed values."""


_LEAF_MATCHERS = {
    "file_exists",
    "dir_exists",
    "env_var",
    "env_var_equals",
    "command_available",
    "uname_contains",
}
_COMBINATORS = {"all", "any"}


def _file_exists(path: str) -> bool:
    if not isinstance(path, str) or not path:
        return False
    return os.path.isfile(path)


def _dir_exists(path: str) -> bool:
    if not isinstance(path, str) or not path:
        return False
    return os.path.isdir(path)


def _env_var(name: str) -> bool:
    if not isinstance(name, str) or not name:
        return False
    value = os.environ.get(name)
    return bool(value)


def _env_var_equals(spec: dict) -> bool:
    if not isinstance(spec, dict):
        raise ConditionSyntaxError(
            f"env_var_equals requires a dict with 'name' and 'value', got {type(spec).__name__}"
        )
    name = spec.get("name")
    expected = spec.get("value")
    if not isinstance(name, str) or not name:
        raise ConditionSyntaxError("env_var_equals.name must be a non-empty string")
    if expected is None:
        raise ConditionSyntaxError("env_var_equals.value is required")
    actual = os.environ.get(name)
    return actual == str(expected)


def _command_available(name: str) -> bool:
    if not isinstance(name, str) or not name:
        return False
    return shutil.which(name) is not None


def _uname_composite(platform_info: PlatformInfo) -> str:
    parts = [platform_info.os]
    if platform_info.subtype:
        parts.append(platform_info.subtype)
    parts.append(platform_info.arch)
    if platform_info.version:
        parts.append(platform_info.version)
    if platform_info.is_wsl:
        parts.append("wsl")
    return " ".join(parts).lower()


def _uname_contains(substring: str, platform_info: PlatformInfo) -> bool:
    if not isinstance(substring, str) or not substring:
        return False
    return substring.lower() in _uname_composite(platform_info)


def _evaluate_leaf(
    key: str, value: Any, platform_info: PlatformInfo
) -> bool:
    if key == "file_exists":
        return _file_exists(value)
    if key == "dir_exists":
        return _dir_exists(value)
    if key == "env_var":
        return _env_var(value)
    if key == "env_var_equals":
        return _env_var_equals(value)
    if key == "command_available":
        return _command_available(value)
    if key == "uname_contains":
        return _uname_contains(value, platform_info)
    raise ConditionSyntaxError(f"unknown leaf matcher: {key!r}")


def _evaluate_all(conditions: List[Any], platform_info: PlatformInfo) -> bool:
    if not isinstance(conditions, list):
        raise ConditionSyntaxError(
            f"'all' requires a list of conditions, got {type(conditions).__name__}"
        )
    # Vacuous: empty `all` is True.
    return all(evaluate_condition(c, platform_info) for c in conditions)


def _evaluate_any(conditions: List[Any], platform_info: PlatformInfo) -> bool:
    if not isinstance(conditions, list):
        raise ConditionSyntaxError(
            f"'any' requires a list of conditions, got {type(conditions).__name__}"
        )
    # Vacuous: empty `any` is False.
    return any(evaluate_condition(c, platform_info) for c in conditions)


def evaluate_condition(
    condition: Optional[dict],
    platform_info: PlatformInfo,
) -> bool:
    """Evaluate a detect_when dict against the given platform.

    Returns True if all declared matchers pass. See module docstring for
    schema details.

    An empty or None condition is vacuously True (no conditions declared ==
    unconditionally active).
    """
    if condition is None:
        return True
    if not isinstance(condition, dict):
        raise ConditionSyntaxError(
            f"condition must be a dict or None, got {type(condition).__name__}"
        )
    if not condition:
        return True

    results: List[bool] = []
    for key, value in condition.items():
        if key.startswith("_"):
            # Metadata (e.g., _schema_version, _comment) -- ignore.
            continue
        if key in _LEAF_MATCHERS:
            results.append(_evaluate_leaf(key, value, platform_info))
        elif key == "all":
            results.append(_evaluate_all(value, platform_info))
        elif key == "any":
            results.append(_evaluate_any(value, platform_info))
        else:
            raise ConditionSyntaxError(
                f"unknown condition key: {key!r}. "
                f"Valid keys: {sorted(_LEAF_MATCHERS | _COMBINATORS)}"
            )

    # Multiple keys in same dict are AND'd. Empty results (only metadata keys) -> True.
    return all(results) if results else True
