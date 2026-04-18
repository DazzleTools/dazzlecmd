"""Setup block resolution -- shared library.

`resolve_setup_block(project)` returns the effective setup block for the
current host. Mirrors `resolve_runtime()` in registry.py but for the setup
layer. Both layers consume the same `platform_resolve` + `platform_detect` +
`schema_version` primitives so subtype fallback and schema versioning behave
identically.

Schema shape (v0.7.20+):

    "setup": {
        "command": "<default shell command>",
        "note": "<optional human-readable description>",
        "platforms": {
            "<os>": "<shell command>"                           -- shorthand
            "<os>": {"command": "<cmd>", "note": "..."}         -- canonical simple
            "<os>": {                                           -- with subtypes
                "command": "<default for this OS>",
                "<subtype>": {"command": "..."},
                "general": {"command": "<fallback>"}
            }
        }
    }

Flat-string shorthand rule:
    - `platforms.<os>` MAY be a string when the author only needs one shell
      command per OS. The string is normalized to `{"command": <string>}` at
      resolution time.
    - Subtype-level values (`platforms.<os>.<subtype>`) must be dicts.
      Strings at that level are not normalized and will not be recognized
      as subtypes by the resolver.

Schema version: `setup._schema_version` follows the same rules as runtime.
Un-versioned blocks default to "1". Unsupported versions raise
UnsupportedSchemaVersionError.

Returned effective block contains the merged fields (command, note, plus any
future fields #40 adds) ready for `_cmd_setup` to dispatch. Returns None if
the project has no setup declared.
"""

from __future__ import annotations

from typing import Optional

from dazzlecmd_lib.platform_detect import PlatformInfo, get_platform_info
from dazzlecmd_lib.platform_resolve import resolve_platform_block
from dazzlecmd_lib.schema_version import check_schema_version
from dazzlecmd_lib.templates import has_template_refs, substitute_vars


def _normalize_platforms(platforms: dict) -> dict:
    """Convert flat-string `platforms.<os>` values to `{"command": <string>}`.

    Subtypes are not recursively normalized -- strings at subtype positions
    are a schema error (documented), but this function does not validate.
    The resolver treats non-dict values at subtype positions as top-level
    fields, which is silently wrong for "subtype: string-command" typos but
    does not crash. Add explicit validation only when a real user trips.
    """
    if not isinstance(platforms, dict):
        return platforms
    normalized: dict = {}
    for os_key, os_value in platforms.items():
        if isinstance(os_value, str):
            normalized[os_key] = {"command": os_value}
        else:
            normalized[os_key] = os_value
    return normalized


def resolve_setup_block(
    project: dict,
    *,
    platform_info: Optional[PlatformInfo] = None,
) -> Optional[dict]:
    """Resolve the effective setup block for the current host.

    Args:
        project: Tool manifest dict. May or may not contain a `setup` key.
        platform_info: Override for testing; defaults to `get_platform_info()`.

    Returns:
        - None if the project has no setup block or the setup block is empty.
        - A merged dict containing the effective fields (command, note, ...)
          after platforms override + subtype fallback.

    Raises:
        UnsupportedSchemaVersionError: setup declares an unsupported
            `_schema_version`.
    """
    setup = project.get("setup")
    if not setup or not isinstance(setup, dict):
        return None

    check_schema_version(
        setup, context=f"setup for {project.get('name', '?')}"
    )

    platforms = setup.get("platforms")
    base_setup = {k: v for k, v in setup.items() if k != "platforms"}

    if not platforms:
        effective = dict(base_setup) if base_setup else None
    else:
        if platform_info is None:
            platform_info = get_platform_info()

        normalized_platforms = _normalize_platforms(platforms)
        effective = resolve_platform_block(
            base_setup, normalized_platforms, platform_info
        )

    if not effective:
        return None

    # Template variable substitution (v0.7.20, issue #41).
    # Gather _vars from manifest-top (shared across setup + runtime) and from
    # the effective block (block-specific, merged through platform resolution).
    # Block-level entries win over manifest-top for matching keys.
    manifest_vars = project.get("_vars", {}) or {}
    block_vars = effective.pop("_vars", {}) if isinstance(effective.get("_vars"), dict) else {}
    combined_vars = {**manifest_vars, **block_vars}

    # Run substitution when either (a) vars are available for lookup OR
    # (b) the effective block contains any `{{...}}` references (so that an
    # unresolved reference surfaces as a clear UnresolvedTemplateVariableError
    # instead of propagating to the shell as a literal string).
    if combined_vars or has_template_refs(effective):
        effective = substitute_vars(effective, combined_vars, context="setup")

    return effective or None
