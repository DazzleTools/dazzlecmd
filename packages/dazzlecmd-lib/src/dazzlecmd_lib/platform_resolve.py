"""Platform resolution and deep-merge helpers -- shared library.

`resolve_platform_block` takes a base block + a platforms sub-dict + a PlatformInfo
and returns the effective block for the current host. Both the runtime resolver
(conditional dispatch) and the setup resolver (multi-platform install) use this
single implementation so subtype fallback behavior cannot drift between layers.

Schema shape inside `platforms.<os>`:

    platforms:
      linux:
        prefer: [...]              <- top-level field (scalar/list) applied unconditionally
        debian: {prefer: [...]}    <- subtype sub-dict (dict value)
        general: {prefer: [...]}   <- fallback sub-dict for unmatched subtypes

Rule for distinguishing fields from subtypes inside `platforms.<os>`:

    - Keys with scalar or list values are TOP-LEVEL FIELDS. Applied unconditionally
      when the OS matches.
    - Keys with DICT values are subtype sub-dicts. The resolver selects at most
      one: the current host's subtype (if a matching key exists), or "general"
      (if present and no subtype match).

Resolution order:

    1. Start with `base`.
    2. Merge non-dict fields from `platforms.<current_os>` (top-level fields).
    3. If `platforms.<current_os>.<current_subtype>` is a dict, merge it.
    4. Else if `platforms.<current_os>.general` is a dict, merge it.

Deep-merge semantics:

    - Dicts are merged recursively.
    - Arrays are REPLACED (not concatenated). Rationale: "the later spec wins
      entirely" matches how most override mechanisms (env vars, config files)
      behave and keeps semantics predictable.
    - Scalars are replaced.
    - None in the overriding dict removes the key.

Depth limit: this helper does not recurse into nested `platforms` blocks. The
schema limits conditional dispatch to two levels (platform -> prefer).
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from dazzlecmd_lib.platform_detect import PlatformInfo


def deep_merge(a: dict, b: dict) -> dict:
    """Return a NEW dict with `b` merged over `a`.

    Semantics:
        - Dicts: recursively merged.
        - Lists: REPLACED (b's list wins entirely).
        - Scalars: REPLACED.
        - `None` in b: removes the key from the result.

    Neither `a` nor `b` is mutated.
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        # Shouldn't normally be called with non-dicts, but be defensive.
        return copy.deepcopy(b) if isinstance(b, dict) else copy.deepcopy(a)

    result: dict = copy.deepcopy(a)
    for key, value in b.items():
        if value is None:
            result.pop(key, None)
            continue
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _split_platform_os_block(os_block: dict) -> (dict, dict):  # type: ignore[syntax]
    """Split a `platforms.<os>` block into (top_level_fields, subtype_subdicts).

    Top-level fields are keys with non-dict values (scalars, lists, None).
    Subtype subdicts are keys with dict values.

    Underscore-prefixed keys are treated as metadata and kept with top-level
    fields (so _schema_version etc. flow through).
    """
    top_level: dict = {}
    subtypes: dict = {}
    for key, value in os_block.items():
        if isinstance(value, dict) and not key.startswith("_"):
            subtypes[key] = value
        else:
            top_level[key] = value
    return top_level, subtypes


def resolve_platform_block(
    base: dict,
    platforms: Optional[dict],
    platform_info: PlatformInfo,
) -> dict:
    """Resolve a platforms dict against the current host.

    Args:
        base: The base block (e.g., contents of `runtime` minus the `platforms`
            key, or contents of `setup` minus `platforms`).
        platforms: The `platforms` sub-dict keyed by os -> subtype/field -> ...
            May be None or empty; returns `base` unchanged.
        platform_info: Current host info.

    Returns:
        A NEW dict with the effective merged block for this host. Input dicts
        are not mutated.
    """
    if not platforms:
        return copy.deepcopy(base) if base else {}

    if not isinstance(platforms, dict):
        # Defensive: malformed input, return base unchanged.
        return copy.deepcopy(base) if base else {}

    os_block = platforms.get(platform_info.os)
    if not isinstance(os_block, dict):
        return copy.deepcopy(base) if base else {}

    top_level_fields, subtype_subdicts = _split_platform_os_block(os_block)

    # Step 2: merge top-level fields of platforms.<os>.
    result = deep_merge(base or {}, top_level_fields)

    # Step 3/4: try subtype, fall back to general.
    selected_subdict: Optional[dict] = None
    if platform_info.subtype and platform_info.subtype in subtype_subdicts:
        selected_subdict = subtype_subdicts[platform_info.subtype]
    elif "general" in subtype_subdicts:
        selected_subdict = subtype_subdicts["general"]

    if selected_subdict is not None:
        result = deep_merge(result, selected_subdict)

    return result
