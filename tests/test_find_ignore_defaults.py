"""Tests for projects/core/find/find.py ignore-rules default flip (v0.12.1).

dz find is a locate-style finder: its contract is the filesystem, not the
VCS's opinion of it. fd's ignore filtering (.gitignore/.ignore/.fdignore)
is therefore bypassed by default (`--no-ignore` always passed), and
--gitignore opts back into fd's code-search filtering.

Regression anchor: `dz find locate32.exe` in a repo whose .gitignore
excludes `*.exe` and the vendored build tree reported "No matches" for a
file that existed on disk (diagnosed 2026-07-14, see the dev-workflow doc
of the same date).

Command-build logic is tested pure (no fd); the TestRealFd class runs
real fd against a temp dir when fd is installed, using .fdignore because
.gitignore rules only apply inside git repositories.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from types import SimpleNamespace

import pytest


_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.dirname(_HERE)
_FIND = os.path.join(_REPO_ROOT, "src", "dazzlecmd", "projects", "core", "find", "find.py")

_FD = shutil.which("fd") or shutil.which("fdfind")


@pytest.fixture(scope="module")
def find_mod():
    spec = importlib.util.spec_from_file_location("find_tool_ignore", _FIND)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _args(**overrides):
    """A minimal args Namespace carrying build_fd_command's expected attrs."""
    base = dict(
        regex=False, case_sensitive=False, hidden=False, no_ignore=False,
        gitignore=False, depth=None, type=None, extension=None, size=None,
        newer=None, older=None, exclude=None, print0=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# --- build_fd_command: ignore-rules default -----------------------------

class TestIgnoreDefault:
    def test_no_ignore_passed_by_default(self, find_mod):
        # AC1: a bare dz find bypasses ignore files
        cmd = find_mod.build_fd_command("fd", "pat", [], _args())
        assert "--no-ignore" in cmd

    def test_gitignore_flag_restores_fd_filtering(self, find_mod):
        # AC1: --gitignore suppresses our --no-ignore
        cmd = find_mod.build_fd_command("fd", "pat", [], _args(gitignore=True))
        assert "--no-ignore" not in cmd

    def test_legacy_no_ignore_flag_still_accepted(self, find_mod):
        # Backward compat: explicit --no-ignore matches the new default
        cmd = find_mod.build_fd_command("fd", "pat", [], _args(no_ignore=True))
        assert cmd.count("--no-ignore") == 1

    def test_parser_accepts_gitignore_flag(self, find_mod):
        args = find_mod.build_parser().parse_args(["pat", "--gitignore"])
        assert args.gitignore is True

    def test_parser_accepts_legacy_no_ignore_flag(self, find_mod):
        args = find_mod.build_parser().parse_args(["pat", "--no-ignore"])
        assert args.no_ignore is True


class TestContradictionGuard:
    def test_gitignore_plus_no_ignore_exits_2(self, find_mod, capsys):
        # AC2: contradictory flags fail loudly, before any search runs
        with pytest.raises(SystemExit) as excinfo:
            find_mod.main(["pat", "--gitignore", "--no-ignore"])
        assert excinfo.value.code == 2
        assert "contradictory" in capsys.readouterr().err


# --- real fd: ignored files are found by default -------------------------

@pytest.mark.skipif(_FD is None, reason="fd not installed")
class TestRealFd:
    @pytest.fixture()
    def ignored_exe_dir(self, tmp_path):
        # .fdignore (not .gitignore) so the rule applies without `git init`
        (tmp_path / ".fdignore").write_text("*.exe\n")
        (tmp_path / "foo.exe").write_bytes(b"MZ")
        return tmp_path

    def test_ignored_file_found_by_default(self, find_mod, ignored_exe_dir,
                                           monkeypatch, capsys):
        # AC3/AC4: the locate32.exe regression, in miniature
        monkeypatch.chdir(ignored_exe_dir)
        rc = find_mod.main(["foo.exe"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "foo.exe" in out

    def test_gitignore_mode_filters_ignored_file(self, find_mod,
                                                 ignored_exe_dir,
                                                 monkeypatch, capsys):
        # AC3: opting back into filtering restores the old behavior
        monkeypatch.chdir(ignored_exe_dir)
        rc = find_mod.main(["foo.exe", "--gitignore"])
        captured = capsys.readouterr()
        assert rc == 1
        assert "No matches" in captured.err

    def test_zero_result_hint_names_gitignore_when_filtering(
            self, find_mod, ignored_exe_dir, monkeypatch, capsys):
        # AC6: the hint points at the flag that caused the filtering
        monkeypatch.chdir(ignored_exe_dir)
        find_mod.main(["foo.exe", "--gitignore"])
        err = capsys.readouterr().err
        assert err.count("--gitignore") == 1

    def test_zero_result_hint_names_hidden_otherwise(self, find_mod,
                                                     tmp_path, monkeypatch,
                                                     capsys):
        # AC6: default-mode miss hints at the remaining blind spot (-H)
        monkeypatch.chdir(tmp_path)
        rc = find_mod.main(["no-such-file-xyzzy.abc"])
        err = capsys.readouterr().err
        assert rc == 1
        assert "add -H" in err

    def test_no_hidden_hint_when_hidden_already_on(self, find_mod, tmp_path,
                                                   monkeypatch, capsys):
        # AC6: hint only fires when its condition holds
        monkeypatch.chdir(tmp_path)
        find_mod.main(["no-such-file-xyzzy.abc", "-H"])
        err = capsys.readouterr().err
        assert "add -H" not in err
        assert "--gitignore" not in err
