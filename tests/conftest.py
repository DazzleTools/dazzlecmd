"""Pytest configuration: auto-skip tests for shells not available on this runner.

Adds a collection hook that inspects each test's markers and skips if the
shell it requires isn't in PATH. Keeps CI green on runners that don't have
every shell installed (e.g., cmd on Linux, zsh on Windows).
"""

import shutil
import sys

import pytest


# Mapping: marker name -> predicate returning True if the shell IS NOT available
_SKIP_CONDITIONS = {
    "shell_cmd": lambda: sys.platform != "win32",
    "shell_bash": lambda: shutil.which("bash") is None,
    "shell_pwsh": lambda: shutil.which("pwsh") is None,
    "shell_zsh": lambda: shutil.which("zsh") is None,
    "shell_csh": lambda: shutil.which("csh") is None and shutil.which("tcsh") is None,
    "node": lambda: shutil.which("node") is None,
    "bun": lambda: shutil.which("bun") is None,
    "deno": lambda: shutil.which("deno") is None,
    "tsx": lambda: shutil.which("tsx") is None,
    "ts_node": lambda: shutil.which("ts-node") is None,
    "npm": lambda: shutil.which("npm") is None,
    "npx": lambda: shutil.which("npx") is None,
}


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests whose shell marker is unavailable on this runner."""
    for item in items:
        for marker_name, is_unavailable in _SKIP_CONDITIONS.items():
            if marker_name in item.keywords and is_unavailable():
                item.add_marker(
                    pytest.mark.skip(
                        reason=f"requires {marker_name.replace('shell_', '')} on PATH"
                    )
                )
