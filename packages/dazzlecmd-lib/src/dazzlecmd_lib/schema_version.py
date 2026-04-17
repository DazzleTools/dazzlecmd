"""Schema version constants and helpers.

Every manifest block consumed by the library (runtime, setup, user-override files)
may carry a _schema_version field. This module centralizes version constants,
the get/check helpers, and -- in the future -- migration functions that
transform older schema versions into the current one.

Design notes:
    - Un-versioned manifests (no _schema_version field) are treated as version 1.
      This keeps pre-v0.7.19 manifests working unchanged.
    - check_schema_version() raises UnsupportedSchemaVersionError with a clear
      message when a manifest declares a version this library does not know how
      to handle. This is the forward-compat boundary -- older library + newer
      manifest should fail loudly, not silently mis-interpret fields.
    - Future v2 handling will add a migrate_block(block) function here. Callers
      check the version, then call migrate_block() if needed, then proceed.
"""

from __future__ import annotations

from typing import Tuple


CURRENT_SCHEMA_VERSION: str = "1"
SUPPORTED_SCHEMA_VERSIONS: Tuple[str, ...] = ("1",)

SCHEMA_VERSION_FIELD: str = "_schema_version"


class UnsupportedSchemaVersionError(ValueError):
    """Raised when a manifest declares a schema version this library cannot handle."""


def get_schema_version(block: dict, default: str = CURRENT_SCHEMA_VERSION) -> str:
    """Return the declared schema version, or `default` if absent.

    Does not validate that the version is supported. Use check_schema_version()
    for that.
    """
    if not isinstance(block, dict):
        return default
    value = block.get(SCHEMA_VERSION_FIELD, default)
    return str(value)


def check_schema_version(block: dict, *, context: str = "manifest") -> str:
    """Verify the block's _schema_version is one this library supports.

    Returns the (normalized string) version. Raises UnsupportedSchemaVersionError
    if the declared version is not in SUPPORTED_SCHEMA_VERSIONS.

    `context` is included in the error message for diagnostics (e.g., which
    manifest or override file raised).
    """
    version = get_schema_version(block)
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(SUPPORTED_SCHEMA_VERSIONS)
        raise UnsupportedSchemaVersionError(
            f"{context} declares _schema_version={version!r}, "
            f"but this library only supports: {supported}. "
            f"Upgrade dazzlecmd-lib or downgrade the manifest."
        )
    return version
