"""Pytest configuration for safedel tests.

Sets up sys.path so safedel modules and their dependencies are importable.
"""

import os
import sys

# Add safedel root to path
_safedel_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _safedel_dir)

# Add _lib for log_lib, help_lib, etc.
sys.path.insert(0, os.path.join(_safedel_dir, "_lib"))

# Add sibling links tool for detect_link imports
sys.path.insert(0, os.path.join(_safedel_dir, "..", "links"))

import pytest

_LEAK_IGNORE = {"__pycache__", ".pytest_cache"}


def _top_level_names(folder):
    try:
        return {n for n in os.listdir(folder) if n not in _LEAK_IGNORE}
    except OSError:
        return set()


@pytest.fixture(scope="session", autouse=True)
def _no_test_writes_outside_its_temp_folder():
    """Fail the run if a test left anything new beside the source.

    A test that builds a path from a Windows-style drive name on Linux, or
    forgets to give a store its own temp folder, writes into whatever
    directory the suite was started from -- which is how folders literally
    named ``C:`` holding ``.safedel-trash-1000`` came to sit in this checkout
    (2026-11-09; one dated 2026-04-10). This watches the folders a stray
    would land in: the current directory, the safedel folder, and the tests
    folder. New top-level names there after the session are a failure.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    watched = {os.path.abspath(os.getcwd()),
               os.path.abspath(_safedel_dir), here}
    before = {d: _top_level_names(d) for d in watched}
    yield
    leaks = {d: sorted(_top_level_names(d) - before[d]) for d in watched}
    leaks = {d: names for d, names in leaks.items() if names}
    assert not leaks, (
        "a test wrote outside its temp folder: "
        + "; ".join(f"{d}: {names!r}" for d, names in leaks.items())
    )
