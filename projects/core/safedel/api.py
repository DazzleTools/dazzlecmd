"""Stable public API for safedel (a thin shim over the lib primitive).

The recoverable-delete ENGINE now lives in the library as the constitutional
``dazzlecmd_lib.core.safedel`` primitive (relocated v0.9.4). This module simply
re-exports it as the tool's stable public surface, so any external importer of
``safedel.api`` keeps working. dazzlecmd-lib's ``mode.py`` imports the lib
primitive directly (it no longer loads this tool).

Public surface: only the names in ``__all__`` are supported.
"""
# The engine now lives in the lib (the constitutional core.safedel primitive);
# this module re-exports it as the tool's stable public surface. Kept as a thin
# shim so any external importer of `safedel.api` keeps working.
from dazzlecmd_lib.core.safedel import (
    TrashStore,
    TrashEntry,
    TrashResult,
    StoreStats,
    stage_to_trash,
    safe_delete,
    classify,
)

__all__ = [
    "TrashStore",
    "TrashEntry",
    "TrashResult",
    "StoreStats",
    "stage_to_trash",
    "safe_delete",
    "classify",
]

# Bump when the public surface changes in a way consumers must adapt to.
__api_version__ = "2"
