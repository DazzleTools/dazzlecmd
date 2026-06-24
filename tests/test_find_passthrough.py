"""Tests for projects/core/find/find.py fd-passthrough + --print0 (v0.10.7).

Covers split_passthrough() -- the `--` escape hatch that hands raw args to
fd -- and build_fd_command()'s passthrough + --print0 handling. The fd
command line is built as a pure list, so the build/split logic is tested
directly without invoking fd itself.
"""

from __future__ import annotations

import importlib.util
import os
from types import SimpleNamespace

import pytest


_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.dirname(_HERE)
_FIND = os.path.join(_REPO_ROOT, "src", "dazzlecmd", "projects", "core", "find", "find.py")


@pytest.fixture(scope="module")
def find_mod():
    spec = importlib.util.spec_from_file_location("find_tool", _FIND)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _args(**overrides):
    """A minimal args Namespace carrying build_fd_command's expected attrs."""
    base = dict(
        regex=False, case_sensitive=False, hidden=False, no_ignore=False,
        depth=None, type=None, extension=None, size=None, newer=None,
        older=None, exclude=None, print0=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# --- split_passthrough -------------------------------------------------

class TestSplitPassthrough:
    def test_no_double_dash(self, find_mod):
        main, extra = find_mod.split_passthrough(["foo", "--regex"])
        assert main == ["foo", "--regex"]
        assert extra == []

    def test_splits_on_double_dash(self, find_mod):
        main, extra = find_mod.split_passthrough(["foo", "--", "--owner", "me"])
        assert main == ["foo"]
        assert extra == ["--owner", "me"]

    def test_double_dash_at_end_gives_empty_passthrough(self, find_mod):
        main, extra = find_mod.split_passthrough(["foo", "--"])
        assert main == ["foo"]
        assert extra == []

    def test_splits_on_first_double_dash_only(self, find_mod):
        main, extra = find_mod.split_passthrough(["a", "--", "b", "--", "c"])
        assert main == ["a"]
        assert extra == ["b", "--", "c"]

    def test_returns_copies_not_aliases(self, find_mod):
        argv = ["foo", "--", "bar"]
        main, extra = find_mod.split_passthrough(argv)
        main.append("X")
        extra.append("Y")
        assert argv == ["foo", "--", "bar"]  # original list untouched


# --- build_fd_command: passthrough ------------------------------------

class TestBuildFdPassthrough:
    def test_passthrough_is_the_tail(self, find_mod):
        cmd = find_mod.build_fd_command("fd", "pat", [], _args(),
                                        passthrough=["--owner", "me"])
        assert cmd[-2:] == ["--owner", "me"]

    def test_passthrough_comes_after_pattern(self, find_mod):
        cmd = find_mod.build_fd_command("fd", "pat", [], _args(),
                                        passthrough=["--owner"])
        assert cmd.index("pat") < cmd.index("--owner")

    def test_no_passthrough_omits_extra(self, find_mod):
        cmd = find_mod.build_fd_command("fd", "pat", [], _args())
        assert cmd[-1] == "pat"

    def test_empty_passthrough_appends_nothing(self, find_mod):
        cmd = find_mod.build_fd_command("fd", "pat", [], _args(),
                                        passthrough=[])
        assert cmd[-1] == "pat"

    def test_passthrough_carries_pattern_when_ours_empty(self, find_mod):
        # args.pattern empty -> passthrough can supply its own positional
        cmd = find_mod.build_fd_command("fd", "", [], _args(),
                                        passthrough=["mypat"])
        assert cmd[-1] == "mypat"

    def test_search_paths_follow_passthrough(self, find_mod):
        cmd = find_mod.build_fd_command("fd", "pat", ["/x"], _args(),
                                        passthrough=["--owner"])
        # paths land last, after passthrough
        assert cmd[-2:] == ["--search-path", "/x"]
        assert cmd.index("--owner") < cmd.index("--search-path")


# --- build_fd_command: --print0 ---------------------------------------

class TestBuildFdPrint0:
    def test_print0_flag_present_when_set(self, find_mod):
        cmd = find_mod.build_fd_command("fd", "pat", [], _args(print0=True))
        assert "--print0" in cmd

    def test_print0_absent_by_default(self, find_mod):
        cmd = find_mod.build_fd_command("fd", "pat", [], _args(print0=False))
        assert "--print0" not in cmd
