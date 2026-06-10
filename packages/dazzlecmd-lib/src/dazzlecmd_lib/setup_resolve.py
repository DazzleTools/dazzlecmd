"""Setup block resolution -- shared library.

`resolve_setup_block(project)` returns the effective setup block for the
current host. Mirrors `resolve_runtime()` in registry.py but for the setup
layer. Both layers consume the same `platform_resolve` + `platform_detect` +
`schema_version` primitives so subtype fallback and schema versioning behave
identically.

Schema shape (v0.7.20+, extended in v0.7.46):

    "setup": {
        "command": "<default shell command>",                   -- one-liner
        "script": "<path/to/setup-file>",                       -- file pointer (v0.7.46+)
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

`command` and `script` are mutually exclusive at any single resolution level:
declaring both at the top level OR both inside the same platform branch
raises `InvalidSetupBlockError`. The author picks ONE based on complexity:

    - `command` -- single shell line; the simplest case (e.g., venv + pip).
    - `script` -- pointer to a file in the tool directory; engine dispatches
      via the right interpreter inferred from the file extension. Use when
      setup needs multiple steps, conditional logic, or external downloads.
      Supported extensions: .py (-> python), .sh (-> bash), .cmd/.bat
      (-> cmd /c), .ps1 (-> powershell -File).

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

Returned effective block contains the merged fields (command OR script, note,
plus any future fields #40 adds) ready for `_cmd_setup` to dispatch.
Returns None if the project has no setup declared.
"""

from __future__ import annotations

import os
from typing import Optional

from dazzlecmd_lib.platform_detect import PlatformInfo, get_platform_info
from dazzlecmd_lib.platform_resolve import deep_merge, resolve_platform_block
from dazzlecmd_lib.schema_version import check_schema_version
from dazzlecmd_lib.templates import has_template_refs, substitute_vars
from dazzlecmd_lib.user_overrides import load_override


class InvalidSetupBlockError(ValueError):
    """Raised when a setup block declares both `command` and `script` at
    the same level (top-level or within a single platform branch).
    """


# Map of supported setup.script file extensions -> interpreter argv prefix.
# The full command is constructed as: <prefix> + [<absolute script path>].
SETUP_SCRIPT_INTERPRETERS = {
    ".py": ["python"],
    ".sh": ["bash"],
    ".cmd": ["cmd", "/c"],
    ".bat": ["cmd", "/c"],
    ".ps1": ["powershell", "-File"],
}


def infer_setup_script_interpreter(script_path: str) -> Optional[list[str]]:
    """Return the argv prefix to dispatch a setup.script by extension.

    Args:
        script_path: The script's path (or just its name -- only the
            extension is consulted).

    Returns:
        Argv prefix list (e.g., ``["python"]``) for the known extensions,
        or ``None`` for unrecognized extensions.
    """
    _, ext = os.path.splitext(script_path)
    return SETUP_SCRIPT_INTERPRETERS.get(ext.lower())


def _check_command_xor_script(block: dict, context: str) -> None:
    """Raise InvalidSetupBlockError if both ``command`` and ``script`` are
    declared at the same level. Either can be absent; both being absent is
    fine (the resolver returns None higher up).
    """
    if isinstance(block, dict) and block.get("command") and block.get("script"):
        raise InvalidSetupBlockError(
            f"Setup block {context} declares both 'command' and 'script'. "
            f"Pick one: 'command' for a single shell line; 'script' for a "
            f"file pointer (engine dispatches via extension)."
        )


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


def _proj_get(project, key, default=None):
    """Read a field from either a DazzleEntity or a plain dict.

    DazzleEntity typed fields are accessed via attribute; extra/unknown
    fields via ``extra_get``; plain dicts fall through to ``dict.get``.
    """
    if isinstance(project, dict):
        return project.get(key, default)
    # DazzleEntity: try typed attribute first, then extra_get
    typed_val = getattr(project, key, _SENTINEL)
    if typed_val is not _SENTINEL:
        return typed_val if typed_val is not None else default
    return project.extra_get(key, default)


_SENTINEL = object()


def resolve_setup_block(
    project,
    *,
    platform_info: Optional[PlatformInfo] = None,
) -> Optional[dict]:
    """Resolve the effective setup block for the current host.

    Args:
        project: Tool entity (DazzleEntity) or plain manifest dict.
            May or may not contain a ``setup`` key.
        platform_info: Override for testing; defaults to `get_platform_info()`.

    Returns:
        - None if the project has no setup block or the setup block is empty.
        - A merged dict containing the effective fields (command, note, ...)
          after platforms override + subtype fallback.

    Raises:
        UnsupportedSchemaVersionError: setup declares an unsupported
            `_schema_version`.
    """
    setup = _proj_get(project, "setup")
    if not setup or not isinstance(setup, dict):
        return None

    # User-override integration (v0.7.22, Option B). If the user has dropped a
    # setup override file at ~/.dazzlecmd/overrides/setup/<fqcn>.json, deep-
    # merge it OVER the manifest's setup block BEFORE platform resolution.
    # Override wins on collision at every scope level; permissive scoping
    # (override can introduce new subtype branches the manifest didn't declare).
    # Override's `_vars` merge into the setup block's _vars scope via deep-merge.
    # Missing override file = no change (load_override returns None).
    fqcn = _proj_get(project, "fqcn") or _proj_get(project, "_fqcn")
    if fqcn:
        override = load_override("setup", fqcn)
        if override:
            setup = deep_merge(setup, override)

    name = _proj_get(project, "name") or "?"
    check_schema_version(
        setup, context=f"setup for {name}"
    )

    # XOR validation: command and script are mutually exclusive at every
    # level. Check the top-level block first; per-platform branches are
    # checked after normalization.
    tool_label = fqcn or name
    _check_command_xor_script(setup, context=f"for {tool_label}")

    platforms = setup.get("platforms")
    base_setup = {k: v for k, v in setup.items() if k != "platforms"}

    if not platforms:
        effective = dict(base_setup) if base_setup else None
    else:
        if platform_info is None:
            platform_info = get_platform_info()

        normalized_platforms = _normalize_platforms(platforms)
        # XOR check each platform branch (post-normalization). The flat-string
        # shorthand becomes {"command": "..."} which can't conflict; only
        # author-written dicts can declare both fields at this level.
        for os_key, branch in normalized_platforms.items():
            if isinstance(branch, dict):
                _check_command_xor_script(
                    branch, context=f"for {tool_label} (platforms.{os_key})"
                )
        effective = resolve_platform_block(
            base_setup, normalized_platforms, platform_info
        )

    if not effective:
        return None

    # Template variable substitution (v0.7.20, issue #41).
    # Gather _vars from manifest-top (shared across setup + runtime) and from
    # the effective block (block-specific, merged through platform resolution).
    # Block-level entries win over manifest-top for matching keys.
    manifest_vars = _proj_get(project, "_vars", {}) or {}
    block_vars = effective.pop("_vars", {}) if isinstance(effective.get("_vars"), dict) else {}
    combined_vars = {**manifest_vars, **block_vars}

    # Run substitution when either (a) vars are available for lookup OR
    # (b) the effective block contains any `{{...}}` references (so that an
    # unresolved reference surfaces as a clear UnresolvedTemplateVariableError
    # instead of propagating to the shell as a literal string).
    if combined_vars or has_template_refs(effective):
        effective = substitute_vars(effective, combined_vars, context="setup")

    return effective or None
