"""``dazzlecmd_lib.core.safedel`` -- the constitutional recoverable-delete primitive.

Part of the ``dazzlecmd_lib.core`` constitutional namespace (see
``dazzlecmd_lib/core/__init__.py``): every aggregator built on dazzlecmd-lib
gets recoverable deletion automatically -- it is NOT an opt-in kit tool that may
or may not be installed. This is what lets ``mode.py``'s swap stage a tool
directory to a recoverable trash store before removing it, on ANY aggregator
(dazzlecmd, wtf-windows, amdead) with no fallback path.

The engine here (trash store, link-aware staging, metadata preservation,
recovery) was relocated from the ``projects/core/safedel/`` tool. The tool now
imports this primitive and adds the user-facing CLI + trash-management UX
(``dz safedel list``/``recover``/``clean``, retention, protection zones) on top.

Metadata preservation (ACLs/ADS/timestamps/xattrs) comes from
``dazzle_filekit.metadata`` (a declared dependency -- the canonical home of that
cross-platform code). Link detection comes from the sibling constitutional
primitive ``dazzlecmd_lib.core.links``.
"""
from dazzlecmd_lib.core.safedel._store import (
    TrashStore,
    TrashEntry,
    TrashFolder,
    TrashResult,
    StoreStats,
)
from dazzlecmd_lib.core.safedel._platform import (
    stage_to_trash,
    safe_delete,
    get_trash_dir,
)
from dazzlecmd_lib.core.safedel._classifier import (
    classify,
    format_classification,
    Classification,
    FileType,
)
from dazzlecmd_lib.core.safedel._recover import (
    cmd_list,
    cmd_recover,
    cmd_clean,
    cmd_status,
)

__all__ = [
    "TrashStore",
    "TrashEntry",
    "TrashFolder",
    "TrashResult",
    "StoreStats",
    "stage_to_trash",
    "safe_delete",
    "get_trash_dir",
    "classify",
    "format_classification",
    "Classification",
    "FileType",
    "cmd_list",
    "cmd_recover",
    "cmd_clean",
    "cmd_status",
]

# Bump when the public surface changes in a way consumers must adapt to.
__api_version__ = "1"
