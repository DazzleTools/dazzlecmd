"""
preservelib.metadata -- re-export shim pointing at dazzle_filekit.metadata.

This module used to contain a full 883-line implementation of file
metadata collection and application (ctime restoration, SDDL ACL
round-trip, xattrs, etc.). As of filekit v0.2.4, that exact
implementation was ported into `dazzle_filekit.metadata` as the canonical
primitives home, and this file now re-exports from there.

Dependency direction:
    preservelib -> dazzle_filekit (one-way, never the reverse)

Why this matters:
- Eliminates code duplication between preservelib and filekit
- Bug fixes only need to happen in filekit
- safedel (which embeds this preservelib copy at _lib/preservelib/) now
  uses filekit primitives under the hood via the existing import paths
- Upstream preservelib at C:\\code\\preserve\\preservelib\\ can follow the
  same pattern when it is next updated

Requirements:
- `dazzle_filekit >= 0.2.4` must be importable. In safedel this is
  arranged via the junction at `_lib/dazzle_filekit/`.

If filekit is not importable, we fall back to the old behavior -- but
filekit v0.2.4 is a hard requirement for safedel's embedded preservelib
to stay in sync.

See also:
  - docs/preservelib-integration.md in filetoolkit repo
  - private/claude/2026-04-10__20-31-07__preservelib-filekit-integration.md
    in safedel's design docs
"""

import logging

# Set up module-level logger (matches the original module's behavior
# so any preservelib users inheriting this logger keep working)
logger = logging.getLogger(__name__)

# Re-export EVERYTHING from dazzle_filekit.metadata. The filekit version
# is byte-identical (plus filekit's own docstring) to the preservelib
# original that used to live here.
from dazzle_filekit.metadata import (
    # Public API
    collect_file_metadata,
    apply_file_metadata,
    compare_metadata,
    get_metadata_summary,
    metadata_to_json,
    restore_windows_creation_time,
    is_win32_available,
    collect_timestamp_info,
    apply_timestamp_strategy,
    # Private helpers (re-exported because some preservelib users
    # historically imported these directly)
    _collect_windows_metadata,
    _apply_windows_metadata,
    _apply_unix_metadata,
    _collect_unix_xattrs,
    _apply_unix_xattrs,
)

__all__ = [
    "collect_file_metadata",
    "apply_file_metadata",
    "compare_metadata",
    "get_metadata_summary",
    "metadata_to_json",
    "restore_windows_creation_time",
    "is_win32_available",
    "collect_timestamp_info",
    "apply_timestamp_strategy",
]
