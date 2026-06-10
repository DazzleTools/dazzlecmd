"""Stable public API for safedel.

This is the supported importable surface other dazzlecmd code uses to delete
recoverably -- notably dazzlecmd-lib's ``mode.py``, which stages a tool
directory to the trash store before a mode swap removes it (issue #38 /
Phase-3.5 item 3.5-14). Importing this module is the data-safe alternative to
calling ``shutil.rmtree`` directly: the trash store IS the recovery backup.

Import convention -- safedel's modules use BARE imports (``from _store import
...``) and run with the safedel directory on ``sys.path`` (the tool is
dispatched as a script, and its conftest/CLI put its own dir on the path).
This module follows that same convention, so an importer must place the
safedel directory on ``sys.path`` BEFORE importing ``api``. The canonical
loader that does this is ``dazzlecmd_lib.mode._load_safedel_api`` -- it locates
``<project_root>/<tools_dir>/core/safedel`` deterministically, puts it on
``sys.path``, and loads this file under a private cache name. Do not turn
safedel into a dotted package (``from ._store import ...``): its CLI is run as
a plain script and would break.

Public surface: only the names in ``__all__`` are supported. Everything else
(the leading-underscore modules ``_store``/``_platform``/``_classifier`` and
their internals) is private and may change without notice.
"""
from _store import TrashStore, TrashEntry, TrashResult, StoreStats
from _platform import stage_to_trash, safe_delete
from _classifier import classify

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
__api_version__ = "1"
