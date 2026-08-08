"""pull_collisions against REAL git.

USER REPORT 2026-08-08: `dz dazzle-update . --fix` refused to pull
dazzlesum with "dirty tree -- refusing to pull (will not stash)". The
tree held one untracked file, `.vscode/settings.json`; the incoming
commits added `docs/platforms.md` and a checklist. Nothing collided and
the fast-forward would have succeeded.

The old guard asked "is the tree dirty?" -- a PROXY. The question git
answers is whether what is coming in touches what you have, and this
module is the only place that can be verified, because the oracle is
git's own behaviour and no fake can stand in for it.

WHY REAL REPOSITORIES HERE, when test_apply_fixes is deliberately
isolated from the payload: that file tests the WRITE path, where a
regression writes to 140 real repositories. This one tests a READ-ONLY
probe -- four queries, no mutation -- against throwaway repos under
tmp_path. Nothing here can reach a repository the user owns, and
nothing here runs `git pull`.

The full 12-scenario sweep, including the runs that execute a real
`git pull` and confirm git aborts atomically, lives out-of-tree in
tests/one-offs/thinking/pulllab.py. This is the subset worth paying for
on every suite run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent.parent))

import dazzle_update as du  # noqa: E402


def _git(cwd, *args):
    p = subprocess.run(["git"] + list(args), cwd=str(cwd), text=True,
                       capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stdout}{p.stderr}")
    return p.stdout


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _init(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    # No signing: the host signs commits globally, and a fixture that
    # inherits that pops pinentry mid-run (it did, in _repo_common).
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "commit.gpgsign", "false")
    return path


@pytest.fixture
def behind(tmp_path):
    """A clone one commit behind its origin, with the origin's second
    commit under the caller's control."""
    origin = _init(tmp_path / "origin")
    _write(origin / "kept.txt", "base\n")
    _write(origin / "other.txt", "base\n")
    # A mixed-case name, because the comparison key is casefolded on
    # Windows and reporting the KEY instead of the spelling is a real
    # bug this fixture has to be able to catch.
    _write(origin / "CHANGELOG.md", "base\n")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-m", "base")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "config", "user.email", "test@example.invalid")
    _git(clone, "config", "user.name", "Test User")
    _git(clone, "config", "commit.gpgsign", "false")

    def advance(adds=(), mods=()):
        for p in adds:
            _write(origin / p, "added upstream\n")
        for p in mods:
            _write(origin / p, "changed upstream\n")
        _git(origin, "add", "-A")
        _git(origin, "commit", "-m", "upstream work")
        _git(clone, "fetch", "-q", "origin")

    return clone, advance


class TestNoCollision:
    """Cases the old guard refused and git completes cleanly."""

    def test_the_reported_case_untracked_file_upstream_never_touches(
            self, behind):
        clone, advance = behind
        advance(adds=["docs/platforms.md"])
        _write(clone / ".vscode" / "settings.json", "{}\n")

        hits, measured = du.pull_collisions(str(clone))

        assert measured
        assert hits == []

    def test_a_modified_tracked_file_upstream_never_touches(self, behind):
        clone, advance = behind
        advance(mods=["other.txt"])
        _write(clone / "kept.txt", "mine\n")

        assert du.pull_collisions(str(clone)) == ([], True)

    def test_a_staged_change_counts_as_uncommitted_but_still_no_collision(
            self, behind):
        """`git diff --name-only HEAD` covers staged AND unstaged; the
        default index compare would miss this half."""
        clone, advance = behind
        advance(mods=["other.txt"])
        _write(clone / "kept.txt", "mine\n")
        _git(clone, "add", "kept.txt")

        assert du.pull_collisions(str(clone)) == ([], True)

    def test_an_untracked_file_beside_an_incoming_one(self, behind):
        """Same directory, different path. Directory-level reasoning
        would refuse; git works at path level."""
        clone, advance = behind
        advance(adds=["docs/platforms.md"])
        _write(clone / "docs" / "scratch.md", "mine\n")

        assert du.pull_collisions(str(clone)) == ([], True)

    def test_a_clean_tree_has_nothing_to_collide_with(self, behind):
        clone, advance = behind
        advance(mods=["other.txt"])

        assert du.pull_collisions(str(clone)) == ([], True)


class TestCollision:
    """Cases git rejects. The probe must catch every one, or the tool
    starts attempting pulls that fail mid-fix."""

    def test_upstream_adds_a_path_held_untracked(self, behind):
        clone, advance = behind
        advance(adds=["docs/platforms.md"])
        _write(clone / "docs" / "platforms.md", "mine\n")

        hits, measured = du.pull_collisions(str(clone))

        assert measured
        assert hits == ["docs/platforms.md"]

    def test_both_sides_edited_the_same_tracked_file(self, behind):
        clone, advance = behind
        advance(mods=["kept.txt"])
        _write(clone / "kept.txt", "mine\n")

        assert du.pull_collisions(str(clone)) == (["kept.txt"], True)

    @pytest.mark.skipif(sys.platform != "win32",
                        reason="case-insensitive filesystem")
    def test_a_case_differing_untracked_path_collides_on_windows(self, behind):
        """`docs/Platforms.md` and `docs/platforms.md` are ONE file here,
        so git refuses -- and an exact string compare would miss it."""
        clone, advance = behind
        advance(adds=["docs/Platforms.md"])
        _write(clone / "docs" / "platforms.md", "mine\n")

        hits, measured = du.pull_collisions(str(clone))

        assert measured
        assert hits, "case difference read as a different file"

    def test_the_reported_path_keeps_the_case_it_has_on_disk(self, behind):
        """Found by TIMING the probe against this repo -- it reported
        `changelog.md` for a file named CHANGELOG.md. The comparison key
        is casefolded on Windows, and returning the KEY names a file the
        reader cannot find. Match on the key, report the spelling."""
        clone, advance = behind
        advance(mods=["CHANGELOG.md"])
        _write(clone / "CHANGELOG.md", "mine\n")

        hits, measured = du.pull_collisions(str(clone))

        assert measured
        assert hits == ["CHANGELOG.md"], (
            f"reported the casefolded key, not the real path: {hits}")

    def test_a_non_ascii_path_collides(self, behind):
        """THE case that makes -z load-bearing. Without it git returns
        the quoted literal `"docs/caf\\303\\251.md"`, which never matches
        the real filename -- so the probe would compare against git's
        display format and report no collision on a pull git rejects.
        (Measured: git does NOT quote spaces, only non-ASCII.)"""
        clone, advance = behind
        advance(adds=["docs/café.md"])
        _write(clone / "docs" / "café.md", "mine\n")

        hits, measured = du.pull_collisions(str(clone))

        assert measured
        assert hits == ["docs/café.md"]


class TestUnmeasurable:
    def test_no_upstream_reports_unmeasured_rather_than_clean(self, tmp_path):
        """A failed measurement must never read as permission: `@{u}`
        cannot resolve, and returning ([], True) would say 'nothing in
        the way' about a question that was never answered."""
        repo = _init(tmp_path / "solo")
        _write(repo / "f.txt", "x\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "only")

        assert du.pull_collisions(str(repo)) == ([], False)

    def test_a_path_that_is_not_a_repository_is_unmeasured(self, tmp_path):
        assert du.pull_collisions(str(tmp_path)) == ([], False)
