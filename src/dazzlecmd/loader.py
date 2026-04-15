"""Backwards-compat shim — loader code lives in dazzlecmd-lib.

All public names are re-exported so existing code that does
``from dazzlecmd.loader import discover_kits`` continues to work.
New code should import from ``dazzlecmd_lib.loader`` directly.
"""

# Re-export everything from the library
from dazzlecmd_lib.loader import *  # noqa: F401,F403
from dazzlecmd_lib.loader import (  # noqa: F811
    discover_kits,
    discover_projects,
    get_active_kits,
    resolve_entry_point,
    set_manifest_cache_fn,
)

# Re-export public runner factories from the registry
from dazzlecmd_lib.registry import (  # noqa: F401
    RunnerRegistry,
    make_python_runner,
    make_subprocess_runner,
    make_shell_runner,
    make_script_runner,
    make_binary_runner,
)

# Legacy aliases for tests that import private names
_make_python_runner = make_python_runner
_make_subprocess_runner = make_subprocess_runner
_make_shell_runner = make_shell_runner
_make_script_runner = make_script_runner
_make_binary_runner = make_binary_runner

# Wire up the manifest cache from mode.py (dazzlecmd-specific)
try:
    from dazzlecmd.mode import get_cached_manifest
    set_manifest_cache_fn(get_cached_manifest)
except ImportError:
    pass  # mode.py not available (library-only usage)
