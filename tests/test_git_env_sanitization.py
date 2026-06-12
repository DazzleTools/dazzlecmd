"""Git subprocess calls must be immune to hook-exported GIT_* env vars.

git EXPORTS repo-location variables (GIT_DIR, GIT_WORK_TREE, ...) to hook
subprocesses. Found 2026-06-11: the repo's pre-push hook runs pytest, the
tests inherited GIT_DIR, and 4 sandboxed tests failed -- `rev-parse
--show-toplevel` reports the cwd as toplevel when GIT_DIR is set (the work
tree defaults to cwd), which defeated the own-toplevel guards, and `git
subtree`/`status` operated against the HOOK'S repository (dazzlecmd itself).
The same leak in production would point `dz new --with common` / `dz mode
switch` at the wrong repo whenever dz runs under any git hook.

These tests pin the fix: `dazzlecmd_lib.mode.sanitized_git_env` strips the
repo-location set, and every production git call site passes it as ``env=``.
"""
import os
import subprocess

import pytest

from dazzlecmd_lib import mode


def _make_repo(path, dirty=False):
    """git init + one commit at ``path``; optionally leave the tree dirty."""
    os.makedirs(path, exist_ok=True)
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for var in mode._GIT_REPO_LOCATION_VARS:
        env.pop(var, None)
    tracked = os.path.join(path, "tracked.txt")
    with open(tracked, "w", encoding="utf-8") as f:
        f.write("content")
    for cmd in (["init", "-q"], ["add", "-A"],
                ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", path] + cmd, check=True, env=env,
                       capture_output=True, text=True)
    if dirty:
        os.remove(tracked)  # tracked file deleted -> ` D tracked.txt`
    return path


def test_sanitized_env_strips_repo_location_vars(monkeypatch):
    """Every repo-location var is stripped; identity vars survive."""
    for var in mode._GIT_REPO_LOCATION_VARS:
        monkeypatch.setenv(var, "C:/somewhere/.git")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "keep-me")
    env = mode.sanitized_git_env()
    for var in mode._GIT_REPO_LOCATION_VARS:
        assert var not in env
    assert env["GIT_AUTHOR_NAME"] == "keep-me"
    # The real environment is never mutated -- it's a copy.
    assert os.environ["GIT_DIR"] == "C:/somewhere/.git"


def test_dirty_check_immune_to_hook_git_dir(tmp_path, monkeypatch):
    """A plain (non-repo) tool dir stays clean even with GIT_DIR pointing at
    a DIRTY foreign repo -- the hook-leak scenario that flipped the suite."""
    dirty_repo = _make_repo(str(tmp_path / "foreign"), dirty=True)
    plain_dir = str(tmp_path / "agg" / "projects" / "core" / "find")
    os.makedirs(plain_dir)
    with open(os.path.join(plain_dir, "find.py"), "w", encoding="utf-8") as f:
        f.write("EMBEDDED CONTENT")

    monkeypatch.setenv("GIT_DIR", os.path.join(dirty_repo, ".git"))
    assert mode._check_dirty_tree(plain_dir) == ""


def test_run_git_immune_to_hook_git_dir(tmp_path, monkeypatch):
    """cli._run_git resolves the repo from cwd, not from a leaked GIT_DIR."""
    from dazzlecmd import cli as _cli

    own_repo = _make_repo(str(tmp_path / "own"))
    foreign = _make_repo(str(tmp_path / "foreign"))
    monkeypatch.setenv("GIT_DIR", os.path.join(foreign, ".git"))

    rc, out = _cli._run_git(["rev-parse", "--show-toplevel"], own_repo, 10)
    assert rc == 0
    assert os.path.realpath(out.strip()) == os.path.realpath(own_repo)


def test_hook_scenario_full_repro(tmp_path, monkeypatch):
    """The verbatim incident: with GIT_DIR leaked, the OLD code saw
    ` D tracked.txt` from the foreign repo and refused the mode switch.
    Pin that an UNSANITIZED status call really does cross repos (proving the
    test would catch a regression), then that the production path does not."""
    dirty_repo = _make_repo(str(tmp_path / "foreign"), dirty=True)
    plain_dir = str(tmp_path / "plain")
    os.makedirs(plain_dir)

    leaked = {**os.environ, "GIT_DIR": os.path.join(dirty_repo, ".git")}
    for var in mode._GIT_REPO_LOCATION_VARS:
        if var != "GIT_DIR":
            leaked.pop(var, None)
    raw = subprocess.run(
        ["git", "-C", plain_dir, "status", "--porcelain"],
        capture_output=True, text=True, env=leaked,
    )
    assert "D tracked.txt" in raw.stdout  # the leak is real without the fix

    monkeypatch.setenv("GIT_DIR", os.path.join(dirty_repo, ".git"))
    assert mode._check_dirty_tree(plain_dir) == ""  # production path: immune
