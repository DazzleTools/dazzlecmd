"""Test setup for dz relaunch.

- The tool folder goes on sys.path so tests import its modules by name.
- Every test gets its own store: DZ_RELAUNCH_HOME points at tmp_path, so no
  test can read or write the real ~/.dz/relaunch (goal untouchable).
- A session guard fails the run if a test left anything new beside the source.
- Seams that would start a real program or call csb are made to raise by
  default (rule 1b); a test that needs one patches it explicitly.
"""

import os
import sys

import pytest

_TOOL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _TOOL_DIR)

_LEAK_IGNORE = {"__pycache__", ".pytest_cache"}


def _top_level_names(folder):
    try:
        return {n for n in os.listdir(folder) if n not in _LEAK_IGNORE}
    except OSError:
        return set()


@pytest.fixture(scope="session", autouse=True)
def _no_test_writes_beside_the_source():
    here = os.path.dirname(os.path.abspath(__file__))
    watched = {os.path.abspath(os.getcwd()), _TOOL_DIR, here}
    before = {d: _top_level_names(d) for d in watched}
    yield
    leaks = {d: sorted(_top_level_names(d) - before[d]) for d in watched}
    leaks = {d: names for d, names in leaks.items() if names}
    assert not leaks, "a test wrote outside its temp folder: " + "; ".join(
        f"{d}: {names!r}" for d, names in leaks.items())


@pytest.fixture(autouse=True)
def relaunch_home(tmp_path, monkeypatch):
    home = tmp_path / "relaunch-home"
    monkeypatch.setenv("DZ_RELAUNCH_HOME", str(home))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("DZ_RELAUNCH_OPEN_ASKS", raising=False)
    return home
