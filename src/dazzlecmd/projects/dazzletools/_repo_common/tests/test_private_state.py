"""The private/ convention probe.

Design record: 2026-08-02__23-50-18__dev-workflow-process__private-folder-axis.md
plus two addenda that narrowed it twice, both from the user's practice:

  * correctness is STORAGE IDENTITY, not directory shape -- the claim
    the convention makes is "worktrees of a project share one private
    store", and junction / symlink / repo-in-place are three mechanisms
    for it, so the probe reports which store a checkout resolves to and
    never grades the mechanism;
  * scope is EVIDENCE, not ownership -- notes taken while reading
    someone else's code are real work, so a third-party clone holding
    private material is inspected exactly like anything else, while a
    checkout with no private/ is silent for everyone.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from _repo_common.private_state import (  # noqa: E402
    PRIVATE_BROKEN,
    PRIVATE_NONE,
    PRIVATE_OK,
    PRIVATE_SPLIT,
    PRIVATE_UNVERSIONED,
    has_private_material,
    judge_private,
    private_state,
)

WINDOWS = os.name == "nt"


def _mkrepo(path, commit=True):
    """Create a private store that is a git repository.

    Commits by default. `git init` alone leaves a repository holding no
    history at all, which this axis deliberately does NOT count as
    versioned -- so a fixture that skips the commit is asserting the
    empty-repo case, not the ordinary one. Pass commit=False for that.
    """
    path.mkdir(parents=True, exist_ok=True)
    for args in (["init", "-b", "main"],
                 ["config", "user.email", "t@example.invalid"],
                 ["config", "user.name", "T"],
                 ["config", "commit.gpgsign", "false"],
                 ["config", "tag.gpgsign", "false"]):
        subprocess.run(["git", "-C", str(path)] + args, check=True,
                       capture_output=True)
    if commit:
        # An EMPTY commit: history is what `versioned` measures, and
        # writing a seed file would also add working-tree content, which
        # is a different property these tests assert separately.
        subprocess.run(["git", "-C", str(path), "commit", "-qm", "seed",
                        "--allow-empty"], check=True, capture_output=True)
    return path


def _link(link_path, target):
    """Junction on Windows, symlink elsewhere -- the same claim."""
    if WINDOWS:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"New-Item -ItemType Junction -Path '{link_path}' "
             f"-Target '{target}' | Out-Null"],
            check=True, capture_output=True)
    else:
        os.symlink(str(target), str(link_path))


class TestShapes:
    def test_absent_is_none(self, tmp_path):
        st = private_state(tmp_path)
        assert st["shape"] == "none" and st["storage"] is None
        assert not st["versioned"] and not st["content"]

    def test_plain_directory_with_content(self, tmp_path):
        (tmp_path / "private").mkdir()
        (tmp_path / "private" / "notes.md").write_text("x", encoding="utf-8")
        st = private_state(tmp_path)
        assert st["shape"] == "plain"
        assert st["content"] and not st["versioned"] and not st["linked"]

    def test_empty_plain_directory_has_no_content(self, tmp_path):
        (tmp_path / "private").mkdir()
        st = private_state(tmp_path)
        assert st["shape"] == "plain" and st["content"] is False

    def test_standalone_repo(self, tmp_path):
        _mkrepo(tmp_path / "private")
        (tmp_path / "private" / "n.md").write_text("x", encoding="utf-8")
        st = private_state(tmp_path)
        assert st["shape"] == "repo" and st["versioned"] and st["content"]

    def test_git_dir_alone_is_not_content(self, tmp_path):
        _mkrepo(tmp_path / "private")
        assert private_state(tmp_path)["content"] is False

    def test_claude_subdir_detected(self, tmp_path):
        (tmp_path / "private" / "claude").mkdir(parents=True)
        (tmp_path / "private" / "claude" / "d.md").write_text("x",
                                                              encoding="utf-8")
        assert private_state(tmp_path)["claude"] is True

    def test_linked_to_repo_resolves_to_the_target_store(self, tmp_path):
        canonical = _mkrepo(tmp_path / "canonical" / "private")
        (canonical / "n.md").write_text("x", encoding="utf-8")
        wt = tmp_path / "worktree"
        wt.mkdir()
        _link(wt / "private", canonical)
        st = private_state(wt)
        assert st["shape"] == "linked" and st["linked"]
        assert st["versioned"] and st["content"]
        assert st["storage"] == os.path.normcase(str(canonical))

    def test_linked_to_plain_dir_is_linked_but_unversioned(self, tmp_path):
        target = tmp_path / "shared" / "private"
        target.mkdir(parents=True)
        (target / "n.md").write_text("x", encoding="utf-8")
        wt = tmp_path / "worktree"
        wt.mkdir()
        _link(wt / "private", target)
        st = private_state(wt)
        assert st["shape"] == "linked" and st["linked"]
        assert st["versioned"] is False

    def test_broken_link(self, tmp_path):
        target = tmp_path / "gone"
        target.mkdir()
        wt = tmp_path / "worktree"
        wt.mkdir()
        _link(wt / "private", target)
        target.rmdir()
        st = private_state(wt)
        assert st["shape"] == PRIVATE_BROKEN and st["linked"]

    def test_two_checkouts_of_one_store_share_a_storage_key(self, tmp_path):
        """The convention's actual claim: worktrees resolve to ONE store."""
        canonical = _mkrepo(tmp_path / "main" / "private")
        wt = tmp_path / "wt"
        wt.mkdir()
        _link(wt / "private", canonical)
        a = private_state(tmp_path / "main")
        b = private_state(wt)
        assert a["storage"] == b["storage"]


class TestJudge:
    def _s(self, shape="repo", versioned=True, storage="s1", content=True):
        return {"shape": shape, "linked": False, "versioned": versioned,
                "storage": storage, "content": content, "claude": False}

    def test_no_states_is_none(self):
        assert judge_private([]) == PRIVATE_NONE
        assert judge_private([{"shape": "none"}]) == PRIVATE_NONE

    def test_single_versioned_is_ok(self):
        assert judge_private([self._s()]) == PRIVATE_OK

    def test_shared_versioned_is_ok(self):
        assert judge_private([self._s(), self._s()]) == PRIVATE_OK

    def test_distinct_stores_is_split(self):
        assert judge_private([self._s(storage="a"),
                              self._s(storage="b")]) == PRIVATE_SPLIT

    def test_unversioned_anywhere_with_none_versioned(self):
        assert judge_private([self._s(shape="plain", versioned=False)]) \
            == PRIVATE_UNVERSIONED

    def test_one_versioned_store_beats_unversioned_siblings(self):
        """A repo plus an unlinked plain dir is SPLIT, not unversioned --
        material exists in two places and one of them has history."""
        got = judge_private([self._s(storage="a"),
                             self._s(shape="plain", versioned=False,
                                     storage="b")])
        assert got == PRIVATE_SPLIT

    def test_broken_outranks_everything(self):
        got = judge_private([self._s(),
                             self._s(shape=PRIVATE_BROKEN, versioned=False,
                                     storage=None)])
        assert got == PRIVATE_BROKEN

    def test_material_detection(self):
        assert has_private_material([self._s(content=True)])
        assert not has_private_material([self._s(content=False)])
        assert not has_private_material([None])


class TestHistoryIsWhatVersionedMeans:
    """#116 -- `.git` existing is not evidence that anything is recoverable.

    The axis exists to find notes living in one place with no recovery
    point. A `git init` with nothing committed is exactly that state, and
    reporting it as versioned told the reader their work was safe when
    none of it was -- the one direction of error this axis must not make.
    """

    def test_repo_with_no_commits_is_not_versioned(self, tmp_path):
        store = _mkrepo(tmp_path / "proj" / "private", commit=False)
        (store / "n.md").write_text("28 files of design notes", encoding="utf-8")
        st = private_state(tmp_path / "proj")
        assert st["versioned"] is False
        assert st["shape"] == "plain"
        assert st["content"] is True, "the notes are still there to lose"

    def test_repo_with_one_commit_is_versioned(self, tmp_path):
        _mkrepo(tmp_path / "proj" / "private")
        st = private_state(tmp_path / "proj")
        assert st["versioned"] is True
        assert st["shape"] == "repo"

    def test_packed_refs_only_still_counts(self, tmp_path):
        """A repo whose refs are packed has no loose heads to find."""
        store = _mkrepo(tmp_path / "proj" / "private")
        subprocess.run(["git", "-C", str(store), "pack-refs", "--all"],
                       check=True, capture_output=True)
        assert not any((store / ".git" / "refs" / "heads").iterdir())
        st = private_state(tmp_path / "proj")
        assert st["versioned"] is True

    def test_linked_store_with_no_commits_is_not_versioned(self, tmp_path):
        """The link resolves; what it resolves TO still has no history."""
        canonical = _mkrepo(tmp_path / "canonical" / "private", commit=False)
        (canonical / "n.md").write_text("x", encoding="utf-8")
        wt = tmp_path / "worktree"
        wt.mkdir()
        _link(wt / "private", canonical)
        st = private_state(wt)
        assert st["linked"] is True
        assert st["versioned"] is False
