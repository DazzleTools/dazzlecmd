"""Unit tests for _repo_common.repo_state.

These build real throwaway git repos under tmp_path rather than
inspecting the developer's own checkout. That is deliberate: the
primitives were extracted from dz git precisely so they stop depending
on the process working directory, and a test that ran against the live
repo could pass for the wrong reason (right answer, wrong location).

The load-bearing property under test is location-explicitness: every
primitive must return facts about the repo it was POINTED at, while the
process cwd is somewhere else entirely.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# The module lives in a sibling directory under projects/dazzletools/ and
# is imported by path because it has no manifest (intentionally -- it is
# not a dispatched dz tool, just a shared library).
_HERE = Path(__file__).resolve().parent
_MODULE_DIR = _HERE.parent
sys.path.insert(0, str(_MODULE_DIR.parent))  # projects/dazzletools/ so '_repo_common' resolves

from _repo_common.repo_state import (  # noqa: E402
    describe_form,
    detect_form,
    detect_remotes,
    detect_sparse_checkout,
    detect_stashes,
    detect_stash_entries,
    detect_submodules,
    detect_subtrees,
    detect_worktrees,
    format_table,
    get_ahead_behind,
    get_branch,
    get_head_short,
    get_repo_root,
    get_status_counts,
    get_upstream,
    git,
    is_inside_repo,
    is_repo_root,
)


# -- helpers --

def _run(cwd, *args):
    """Run a git command in cwd, raising on failure so setup bugs are loud."""
    res = subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}:\n{res.stdout}\n{res.stderr}")
    return res.stdout


def _init_repo(path, initial_branch="main"):
    """Create a repo with one commit and deterministic identity."""
    path.mkdir(parents=True, exist_ok=True)
    _run(path, "init", "-b", initial_branch)
    _run(path, "config", "user.email", "test@example.invalid")
    _run(path, "config", "user.name", "Test User")
    _run(path, "config", "commit.gpgsign", "false")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _run(path, "add", "README.md")
    _run(path, "commit", "-m", "initial commit")
    return path


@pytest.fixture
def repo(tmp_path):
    """A plain repo with a single commit, on branch 'main'."""
    return _init_repo(tmp_path / "solo")


@pytest.fixture
def linked(tmp_path):
    """An (upstream, clone) pair so tracking-branch state is real."""
    origin = _init_repo(tmp_path / "origin")
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", str(origin), str(clone)],
        capture_output=True, text=True, check=True,
    )
    _run(clone, "config", "user.email", "test@example.invalid")
    _run(clone, "config", "user.name", "Test User")
    _run(clone, "config", "commit.gpgsign", "false")
    return origin, clone


@pytest.fixture
def elsewhere(tmp_path, monkeypatch):
    """Force the process cwd OUTSIDE any repo under test.

    Every location-explicitness assertion depends on this: if the cwd
    happened to be the repo, a cwd-coupled regression would still pass.
    """
    outside = tmp_path / "not_a_repo"
    outside.mkdir()
    monkeypatch.chdir(outside)
    return outside


# -- location-explicitness: the property the extraction exists to provide --

def test_primitives_read_the_repo_they_are_pointed_at(repo, elsewhere):
    """With cwd outside any repo, every primitive still answers correctly."""
    assert get_branch(repo) == "main"
    assert get_head_short(repo) != "unknown"
    assert len(get_head_short(repo)) >= 7
    assert detect_form(repo)["bare"] is False
    assert detect_stashes(repo) == 0
    assert detect_submodules(str(repo)) == []
    assert detect_subtrees(str(repo)) == []


def test_primitives_do_not_mutate_process_cwd(repo, elsewhere):
    """The shared module must never chdir -- that stays a CLI concern."""
    before = os.getcwd()
    get_branch(repo)
    get_head_short(repo)
    detect_worktrees(repo)
    detect_remotes(repo)
    detect_form(repo)
    detect_stashes(repo)
    get_status_counts(repo)
    assert os.getcwd() == before


def test_two_repos_do_not_bleed_into_each_other(tmp_path, elsewhere):
    """Distinct repos scanned in sequence report distinct state."""
    a = _init_repo(tmp_path / "a", initial_branch="main")
    b = _init_repo(tmp_path / "b", initial_branch="develop")
    assert get_branch(a) == "main"
    assert get_branch(b) == "develop"
    assert get_branch(a) == "main"  # re-read: no residue from b


# -- branch / head --

def test_get_branch_returns_none_when_detached(repo, elsewhere):
    head = _run(repo, "rev-parse", "HEAD").strip()
    _run(repo, "checkout", "--detach", head)
    assert get_branch(repo) is None


def test_get_head_short_unknown_on_empty_repo(tmp_path, elsewhere):
    """A repo with no commits has no HEAD to resolve."""
    empty = tmp_path / "empty"
    empty.mkdir()
    _run(empty, "init", "-b", "main")
    assert get_head_short(empty) == "unknown"


# -- sync state (Step 1c) --

def test_no_upstream_is_distinguishable_from_in_sync(repo, elsewhere):
    """A branch with no upstream must not look like a synced branch.

    This is the distinction that makes outbound drift detectable: work on
    an untracked branch exists nowhere else, and reporting it as (0, 0)
    would hide that.
    """
    assert get_upstream(repo) is None
    assert get_ahead_behind(repo) == (None, None)


def test_clone_starts_in_sync(linked, elsewhere):
    _origin, clone = linked
    assert get_upstream(clone) == "origin/main"
    assert get_ahead_behind(clone) == (0, 0)


def test_ahead_counts_unpushed_commits(linked, elsewhere):
    """The outbound-drift case: commits that exist only on this box."""
    _origin, clone = linked
    (clone / "local.txt").write_text("local work\n", encoding="utf-8")
    _run(clone, "add", "local.txt")
    _run(clone, "commit", "-m", "unpushed work")
    behind, ahead = get_ahead_behind(clone)
    assert (behind, ahead) == (0, 1)


def test_behind_counts_upstream_commits(linked, elsewhere):
    origin, clone = linked
    (origin / "upstream.txt").write_text("remote work\n", encoding="utf-8")
    _run(origin, "add", "upstream.txt")
    _run(origin, "commit", "-m", "upstream work")
    _run(clone, "fetch", "origin")
    behind, ahead = get_ahead_behind(clone)
    assert (behind, ahead) == (1, 0)


def test_diverged_reports_both_directions(linked, elsewhere):
    origin, clone = linked
    (origin / "u.txt").write_text("u\n", encoding="utf-8")
    _run(origin, "add", "u.txt")
    _run(origin, "commit", "-m", "upstream")
    (clone / "l.txt").write_text("l\n", encoding="utf-8")
    _run(clone, "add", "l.txt")
    _run(clone, "commit", "-m", "local")
    _run(clone, "fetch", "origin")
    assert get_ahead_behind(clone) == (1, 1)


def test_status_counts_separate_tracked_from_untracked(repo, elsewhere):
    """Untracked files are a weaker signal and must be counted apart."""
    assert get_status_counts(repo) == {"dirty_count": 0,
                                       "untracked_count": 0,
                                       "churn_count": 0}

    (repo / "README.md").write_text("modified\n", encoding="utf-8")
    (repo / "brand_new.txt").write_text("new\n", encoding="utf-8")
    counts = get_status_counts(repo)
    assert counts == {"dirty_count": 1, "untracked_count": 1,
                      "churn_count": 0}


class TestChurnPatterns:
    """Machine-made churn (hook-restamped files) split from real dirt.

    Trigger: a repokit-heavy machine listed repos as DIRTY whose only
    change was the commit hook rewriting `_version.py` build metadata --
    the report was measuring the tooling, not the work.
    """

    def _add_version_file(self, repo, nested=False):
        target = repo / "src" / "pkg" / "_version.py" if nested \
            else repo / "_version.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('__version__ = "1.0"\n', encoding="utf-8")
        _run(repo, "add", "-A")
        _run(repo, "commit", "-m", "add version file")
        return target

    def test_churn_reclassified_not_hidden(self, repo, elsewhere):
        target = self._add_version_file(repo)
        target.write_text('__version__ = "1.0+stamp"\n', encoding="utf-8")
        counts = get_status_counts(repo, churn_patterns=["_version.py"])
        assert counts == {"dirty_count": 0, "untracked_count": 0,
                          "churn_count": 1}

    def test_no_patterns_counts_churn_as_dirty(self, repo, elsewhere):
        """dz git passes nothing and must see the old behavior exactly."""
        target = self._add_version_file(repo)
        target.write_text('__version__ = "1.0+stamp"\n', encoding="utf-8")
        counts = get_status_counts(repo)
        assert counts["dirty_count"] == 1 and counts["churn_count"] == 0

    def test_basename_match_catches_nested_paths(self, repo, elsewhere):
        target = self._add_version_file(repo, nested=True)
        target.write_text('__version__ = "1.0+stamp"\n', encoding="utf-8")
        counts = get_status_counts(repo, churn_patterns=["_version.py"])
        assert counts == {"dirty_count": 0, "untracked_count": 0,
                          "churn_count": 1}

    def test_real_edit_alongside_churn_still_dirty(self, repo, elsewhere):
        """A repo with churn AND a real edit must never read clean."""
        target = self._add_version_file(repo)
        target.write_text('__version__ = "1.0+stamp"\n', encoding="utf-8")
        (repo / "README.md").write_text("real work\n", encoding="utf-8")
        counts = get_status_counts(repo, churn_patterns=["_version.py"])
        assert counts == {"dirty_count": 1, "untracked_count": 0,
                          "churn_count": 1}

    # -- content is the verdict, not just the filename ------------------

    def _commit(self, repo, name, content):
        f = repo / name
        f.write_text(content, encoding="utf-8")
        _run(repo, "add", "-A")
        _run(repo, "commit", "-m", f"add {name}")
        return f

    def test_plain_text_version_file_restamp_is_churn(self, repo, elsewhere):
        """USER DESIGN 2026-08-02: 'X.Y.Z -> A.B.C' works for ANY file
        format -- a bare version string in a txt file restamps the same
        way a Python assignment does."""
        f = self._commit(repo, "VERSION", "1.2.3\n")
        f.write_text("1.2.4\n", encoding="utf-8")
        counts = get_status_counts(repo, churn_patterns=["VERSION"])
        assert counts["churn_count"] == 1 and counts["dirty_count"] == 0

    def test_json_version_line_restamp_is_churn(self, repo, elsewhere):
        f = self._commit(repo, "version.py",
                         '{\n  "version": "1.2.3",\n  "name": "x"\n}\n')
        f.write_text('{\n  "version": "1.2.4",\n  "name": "x"\n}\n',
                     encoding="utf-8")
        counts = get_status_counts(repo, churn_patterns=["version.py"])
        assert counts["churn_count"] == 1 and counts["dirty_count"] == 0

    def test_real_logic_edit_in_version_file_is_dirty(self, repo, elsewhere):
        """Structural change fails the same-line-masked test."""
        f = self._commit(repo, "_version.py", '__version__ = "1.0"\n')
        f.write_text('__version__ = "1.0"\nimport os\n', encoding="utf-8")
        counts = get_status_counts(repo, churn_patterns=["_version.py"])
        assert counts["dirty_count"] == 1 and counts["churn_count"] == 0

    def test_manual_component_bump_is_dirty(self, repo, elsewhere):
        """A human editing MAJOR/MINOR/PATCH is doing version WORK; the
        changed line has no dotted version token, so it stays dirty."""
        f = self._commit(repo, "_version.py",
                         'MAJOR = 0\n__version__ = "0.1"\n')
        f.write_text('MAJOR = 1\n__version__ = "0.1"\n', encoding="utf-8")
        counts = get_status_counts(repo, churn_patterns=["_version.py"])
        assert counts["dirty_count"] == 1 and counts["churn_count"] == 0

    def test_more_than_two_changed_lines_is_dirty(self, repo, elsewhere):
        """'If it's just one or two lines that's a good tell in its own
        right' -- and past it, no stamp explanation is plausible."""
        f = self._commit(repo, "_version.py",
                         'a = "1.0"\nb = "2.0"\nc = "3.0"\n')
        f.write_text('a = "1.1"\nb = "2.1"\nc = "3.1"\n', encoding="utf-8")
        counts = get_status_counts(repo, churn_patterns=["_version.py"])
        assert counts["dirty_count"] == 1 and counts["churn_count"] == 0

    def test_staged_stamp_is_still_churn(self, repo, elsewhere):
        """Diffing HEAD, not the worktree: an added stamp is a stamp."""
        f = self._add_version_file(repo)
        f.write_text('__version__ = "1.0+stamp"\n', encoding="utf-8")
        _run(repo, "add", "-A")
        counts = get_status_counts(repo, churn_patterns=["_version.py"])
        assert counts["churn_count"] == 1 and counts["dirty_count"] == 0

    def test_deleted_version_file_is_dirty(self, repo, elsewhere):
        """A missing version file is a decision, never a restamp."""
        f = self._add_version_file(repo)
        f.unlink()
        counts = get_status_counts(repo, churn_patterns=["_version.py"])
        assert counts["dirty_count"] == 1 and counts["churn_count"] == 0


def test_staged_changes_count_as_dirty(repo, elsewhere):
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    _run(repo, "add", "staged.txt")
    counts = get_status_counts(repo)
    assert counts["dirty_count"] == 1
    assert counts["untracked_count"] == 0


# -- remotes --

def test_detect_remotes_extracts_github_slug(repo, elsewhere):
    _run(repo, "remote", "add", "origin",
         "https://github.com/DazzleTools/dazzlecmd.git")
    remotes = detect_remotes(repo)
    assert len(remotes) == 1
    assert remotes[0]["name"] == "origin"
    assert remotes[0]["slug"] == "DazzleTools/dazzlecmd"


def test_detect_remotes_handles_ssh_and_missing_dot_git(repo, elsewhere):
    _run(repo, "remote", "add", "origin", "git@github.com:DazzleLib/dazzle-lib")
    assert detect_remotes(repo)[0]["slug"] == "DazzleLib/dazzle-lib"


def test_detect_remotes_leaves_slug_blank_for_non_github(repo, elsewhere):
    _run(repo, "remote", "add", "origin", "https://gitlab.com/someone/thing.git")
    assert detect_remotes(repo)[0]["slug"] == ""


def test_no_remote_yields_empty_list(repo, elsewhere):
    """The dazzle-loglib shape: a real repo that exists only on this box."""
    assert detect_remotes(repo) == []


# -- stashes --

def test_stash_count_and_entries(repo, elsewhere):
    assert detect_stashes(repo) == 0
    (repo / "README.md").write_text("dirty\n", encoding="utf-8")
    _run(repo, "stash", "push", "-m", "wip one")
    assert detect_stashes(repo) == 1
    entries = detect_stash_entries(repo)
    assert len(entries) == 1
    assert "wip one" in entries[0]["message"]


# -- worktrees --

def test_detect_worktrees_lists_linked_worktrees(repo, tmp_path, elsewhere):
    wt = tmp_path / "linked_wt"
    _run(repo, "worktree", "add", "-b", "feature", str(wt))
    worktrees = detect_worktrees(repo)
    branches = {w["branch"] for w in worktrees}
    assert "main" in branches
    assert "feature" in branches


def test_current_worktree_marker_is_caller_controlled(repo, tmp_path, elsewhere):
    """current_path drives the '*' marker, so a scanner can pass it in.

    The default (process cwd) is preserved for the CLI; this asserts the
    override works, which is what lets a multi-repo scan mark correctly
    without chdir-ing.
    """
    wt = tmp_path / "linked_wt2"
    _run(repo, "worktree", "add", "-b", "feature2", str(wt))

    marked = [w for w in detect_worktrees(repo, current_path=str(wt))
              if w["status"].endswith("*")]
    assert len(marked) == 1
    assert marked[0]["branch"] == "feature2"

    # cwd is outside every repo, so the default marks nothing
    assert not [w for w in detect_worktrees(repo) if w["status"].endswith("*")]


# -- form --

def test_detect_form_flags_a_plain_clone(repo, elsewhere):
    form = detect_form(repo)
    assert form == {
        "bare": False, "shallow": False, "mirror": False,
        "partial_clone": False, "partial_filter": None,
    }
    assert describe_form(form) == "normal clone"


def test_detect_form_identifies_bare(tmp_path, elsewhere):
    bare = tmp_path / "bare.git"
    bare.mkdir()
    _run(bare, "init", "--bare")
    assert detect_form(bare)["bare"] is True
    assert "bare" in describe_form(detect_form(bare))


def test_describe_form_composes_multiple_flags():
    assert describe_form({"bare": True, "shallow": True}) == "bare, shallow"
    assert describe_form(
        {"partial_clone": True, "partial_filter": "blob:none"}
    ) == "partial clone (blob:none)"


# -- submodules / subtrees --

def test_detect_submodules_reads_gitmodules(tmp_path, elsewhere):
    inner = _init_repo(tmp_path / "inner")
    outer = _init_repo(tmp_path / "outer")
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "submodule", "add",
         str(inner), "vendor/inner"],
        cwd=str(outer), capture_output=True, text=True, check=True,
    )
    _run(outer, "commit", "-m", "add submodule")

    mods = detect_submodules(str(outer))
    assert len(mods) == 1
    assert mods[0]["path"] == "vendor/inner"
    assert mods[0]["type"] == "submodule"
    assert mods[0]["status"] in {"synced", "modified", "unknown"}


def test_detect_subtrees_finds_commit_trailer(repo, elsewhere):
    """Subtrees are inferred from commit trailers, not from a config file."""
    (repo / "note.txt").write_text("x\n", encoding="utf-8")
    _run(repo, "add", "note.txt")
    _run(repo, "commit", "-m",
         "Squashed content\n\ngit-subtree-dir: scripts/vendored")
    subs = detect_subtrees(str(repo))
    assert [s["path"] for s in subs] == ["scripts/vendored"]
    assert subs[0]["type"] == "subtree"


# -- sparse checkout --

def test_sparse_checkout_false_by_default(repo, elsewhere):
    assert detect_sparse_checkout(repo) in (False, True)  # git-version dependent


# -- pure formatting helpers --

def test_format_table_pads_to_widest_cell():
    out = format_table([["a", "bb"], ["ccc", "d"]], ["H1", "H2"])
    lines = out.splitlines()
    assert lines[0].startswith("H1 ")
    assert set(lines[1]) <= {"-", " "}
    assert len(lines) == 4


def test_format_table_empty_returns_empty_string():
    assert format_table([], ["H1", "H2"]) == ""


# -- error tolerance --

def test_is_repo_root_rejects_plain_directories(tmp_path, elsewhere):
    """The guard a tree walk must use before treating a path as a repo.

    Regression test for a real hazard: git resolves paths against the
    nearest ENCLOSING repo, so a plain directory can silently report an
    ancestor's branch. Under %USERPROFILE% -- which is itself a repo on
    this machine -- get_branch() on a non-repo temp dir returned 'main'.
    A scanner gating on is_repo_root() cannot make that mistake.
    """
    plain = tmp_path / "plain"
    plain.mkdir()
    assert is_repo_root(plain) is False


def test_is_repo_root_accepts_only_the_toplevel(repo, elsewhere):
    nested = repo / "sub" / "deeper"
    nested.mkdir(parents=True)
    assert is_repo_root(repo) is True
    assert is_repo_root(nested) is False       # inside, but not the root
    assert is_inside_repo(nested) is True      # ...and we can say so


def test_get_repo_root_resolves_from_a_subdirectory(repo, elsewhere):
    nested = repo / "sub"
    nested.mkdir()
    root = get_repo_root(nested)
    assert root is not None
    assert Path(root).resolve() == repo.resolve()


def test_primitives_do_not_raise_on_a_plain_directory(tmp_path, elsewhere):
    """Whatever they resolve to, no primitive may raise."""
    plain = tmp_path / "plain2"
    plain.mkdir()
    get_branch(plain)
    get_head_short(plain)
    detect_remotes(plain)
    detect_worktrees(plain)
    detect_stashes(plain)
    get_upstream(plain)
    get_ahead_behind(plain)
    get_status_counts(plain)


def test_primitives_are_quiet_outside_any_repo(tmp_path, elsewhere, monkeypatch):
    """With GIT_CEILING_DIRECTORIES blocking the upward walk, all empty."""
    plain = tmp_path / "plain3"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert get_branch(plain) is None
    assert get_head_short(plain) == "unknown"
    assert detect_remotes(plain) == []
    assert detect_stashes(plain) == 0
    assert get_upstream(plain) is None
    assert get_ahead_behind(plain) == (None, None)
    assert get_status_counts(plain) == {"dirty_count": 0,
                                        "untracked_count": 0,
                                        "churn_count": 0}
