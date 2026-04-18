"""Template variable substitution for setup and runtime manifests.

v0.7.20 feature. See issue #41 for the tracking epic.

Author experience: declare shared command fragments once via `_vars`, reference
via `{{name}}`. Covers cross-platform DRY-up that the platform-merge resolver
cannot handle (sibling branches: linux vs macos vs bsd).

Design decisions (locked in dev-workflow
`2026-04-17__21-24-13__dev-workflow-process_template-vars-scoping-and-nesting.md`):

    Syntax       {{var}} (whitespace tolerated inside braces)
    Identifiers  [A-Za-z_][A-Za-z0-9_]*
    Scoping      Dynamic -- lookup uses current resolution context, NOT
                 where the variable was declared. Enables per-platform
                 override of ingredients in composite vars.
    Lookup       Effective block's _vars -> manifest-top _vars -> error
    Unresolved   Hard error (UnresolvedTemplateVariableError)
    Recursion    Supported with cycle detection + max-depth 10
    Values       Strings only in v1 (list/dict deferred; see issue #41)

Integration pattern (for callers):

    effective = resolve_platform_block(base, platforms, platform_info)
    manifest_vars = project.get("_vars", {})
    block_vars = effective.pop("_vars", {})  # strip metadata before substitute
    combined_vars = {**manifest_vars, **block_vars}  # block wins over manifest
    substitute_vars(effective, combined_vars, context="setup")
    return effective

The `_vars` key is stripped BEFORE returning so downstream consumers only see
dispatch fields. Resolvers are responsible for gathering vars from the correct
scope chain (typically manifest-top + effective-block-merged).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


VAR_REGEX = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

# Max recursion depth for variable-referencing-variable chains. Bounds both
# genuine cycles (caught earlier by chain tracking) and pathological but
# non-cyclic deep chains. 10 is generous; real composite chains (venv_bin ->
# venv_dir) rarely exceed 2-3 levels.
MAX_SUBSTITUTION_DEPTH = 10


class TemplateError(ValueError):
    """Base for all template substitution errors."""


class UnresolvedTemplateVariableError(TemplateError):
    """Raised when `{{name}}` has no matching `_vars` entry in scope."""


class TemplateRecursionError(TemplateError):
    """Raised on cycle detection or max-depth excess during substitution."""


def _resolve_var(
    name: str,
    vars_map: Dict[str, str],
    *,
    chain: List[str],
    context: str,
) -> str:
    """Recursively resolve a single variable, substituting any nested refs.

    chain tracks the variable names currently being resolved in this substitution
    pass. Re-entry into a name already in the chain is a cycle. chain depth
    exceeding MAX_SUBSTITUTION_DEPTH is a safety net for pathological but
    non-cyclic cases.
    """
    if name in chain:
        cycle_display = " -> ".join(chain + [name])
        raise TemplateRecursionError(
            f"cycle detected in {context}: {cycle_display}"
        )
    if len(chain) >= MAX_SUBSTITUTION_DEPTH:
        raise TemplateRecursionError(
            f"max substitution depth ({MAX_SUBSTITUTION_DEPTH}) exceeded in "
            f"{context}; chain: {' -> '.join(chain + [name])}. Likely a cycle "
            f"or deeply nested vars."
        )

    if name not in vars_map:
        available = sorted(vars_map.keys())
        raise UnresolvedTemplateVariableError(
            f"'{{{{{name}}}}}' referenced in {context} but not declared in "
            f"_vars at any visible scope. Available vars: {available}"
        )

    value = vars_map[name]
    if not isinstance(value, str):
        raise TemplateError(
            f"_vars.{name} must be a string, got {type(value).__name__} "
            f"(in {context}). Non-string values are not supported in v1; see "
            f"issue #41 for deferred list/dict support."
        )

    # Recursively substitute any {{...}} references inside this var's value.
    return _substitute_string(value, vars_map, chain=chain + [name], context=context)


def _substitute_string(
    s: str,
    vars_map: Dict[str, str],
    *,
    chain: Optional[List[str]] = None,
    context: str,
) -> str:
    """Substitute all `{{name}}` occurrences in a string."""
    if chain is None:
        chain = []
    if "{{" not in s:
        return s  # fast path

    def _replace(match: "re.Match[str]") -> str:
        name = match.group(1)
        return _resolve_var(name, vars_map, chain=chain, context=context)

    return VAR_REGEX.sub(_replace, s)


def has_template_refs(block: Any) -> bool:
    """Return True if the block contains any `{{...}}` template marker.

    Recursive walk -- checks nested dicts and lists. Used by resolvers to
    decide whether substitution needs to run (and thus whether an
    UnresolvedTemplateVariableError should surface) when no `_vars` are
    declared. Without this check, a fast-path early-return would let
    unresolved `{{name}}` references pass through silently and fail later
    at dispatch time with a cryptic "executable not found" error.

    Uses a plain substring search on "{{" as a cheap positive signal. If
    "{{" is present, downstream substitute_vars will do the real regex
    match; false positives just trigger one extra substitution pass that
    does nothing.
    """
    if isinstance(block, str):
        return "{{" in block
    if isinstance(block, dict):
        return any(has_template_refs(v) for v in block.values())
    if isinstance(block, list):
        return any(has_template_refs(item) for item in block)
    return False


def substitute_vars(
    block: Any,
    vars_map: Dict[str, str],
    *,
    context: str = "manifest",
) -> Any:
    """Walk a block (dict, list, or scalar) and substitute `{{name}}` in every string.

    Returns a NEW structure with substitutions applied. The original `block`
    is not mutated (caller-safety guarantee).

    Args:
        block: Effective block -- typically a dict from resolve_platform_block,
               possibly containing nested dicts and lists (e.g., prefer entries).
        vars_map: Merged `_vars` dictionary for lookup. Caller responsible for
                  merging scope layers (effective block + manifest-top) before
                  passing.
        context: Human-readable label for error messages (e.g., "setup",
                 "runtime", "setup.platforms.linux").

    Raises:
        UnresolvedTemplateVariableError: when a `{{name}}` reference has no
            matching entry in `vars_map`.
        TemplateRecursionError: on cycle or max-depth.
        TemplateError: when a `_vars` value has an unsupported type.
    """
    if isinstance(block, str):
        return _substitute_string(block, vars_map, context=context)
    if isinstance(block, dict):
        out: dict = {}
        for key, value in block.items():
            # Do not substitute `_schema_version` (protocol field).
            # Keys themselves are never substituted (only values).
            if key == "_schema_version":
                out[key] = value
                continue
            sub_context = f"{context}.{key}" if context else key
            out[key] = substitute_vars(value, vars_map, context=sub_context)
        return out
    if isinstance(block, list):
        return [
            substitute_vars(item, vars_map, context=f"{context}[{i}]")
            for i, item in enumerate(block)
        ]
    # Scalars (int, float, bool, None) pass through unchanged.
    return block
