"""Tests for dz git-snapshot tool.

Uses temporary git repos to test snapshot save/list/show/diff/apply/restore/drop/clean.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest


# Temp repos must live OUTSIDE any git repo to prevent nesting issues.
# The dazzlecmd project is a git worktree, and nested git repos inside
# it confuse hooks and ref operations.
_ISOLATED_TMP = os.path.join(tempfile.gettempdir(), "dz-snapshot-tests")


# -- helpers --

def git(repo_dir, *args):
    """Run git command in a specific directory."""
    env = os.environ.copy()
    env["GIT_DIR"] = os.path.join(repo_dir, ".git")
    env["GIT_WORK_TREE"] = repo_dir
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, cwd=repo_dir, env=env,
        encoding="utf-8", errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


def dz_snapshot(repo_dir, *args):
    """Run dz git-snapshot in a specific directory.

    Forces git to use the temp repo via GIT_DIR and GIT_WORK_TREE,
    preventing operations from leaking into the parent dazzlecmd repo.
    """
    env = os.environ.copy()
    env["GIT_DIR"] = os.path.join(repo_dir, ".git")
    env["GIT_WORK_TREE"] = repo_dir
    result = subprocess.run(
        [sys.executable, "-m", "dazzlecmd", "git-snapshot"] + list(args),
        capture_output=True, text=True, cwd=repo_dir, env=env,
        encoding="utf-8", errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


@pytest.fixture
def git_repo():
    """Create a temporary git repo with an initial commit.

    Repos are created in an isolated temp directory outside the project
    tree to avoid nested git repo issues with worktrees and hooks.
    """
    os.makedirs(_ISOLATED_TMP, exist_ok=True)
    repo_dir = tempfile.mkdtemp(dir=_ISOLATED_TMP)

    git(repo_dir, "init")
    git(repo_dir, "config", "user.email", "test@test.com")
    git(repo_dir, "config", "user.name", "Test")
    git(repo_dir, "config", "commit.gpgsign", "false")
    git(repo_dir, "config", "tag.gpgsign", "false")

    # Initial commit
    with open(os.path.join(repo_dir, "file.txt"), "w") as f:
        f.write("initial content\n")
    git(repo_dir, "add", "file.txt")
    git(repo_dir, "commit", "-m", "initial commit")

    yield repo_dir

    # Cleanup
    try:
        shutil.rmtree(repo_dir, ignore_errors=True)
    except OSError:
        pass


# -- save tests --

class TestSave:
    def test_save_basic(self, git_repo):
        """Save creates a snapshot and reports success."""
        # Make a change
        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("modified content\n")

        rc, out, err = dz_snapshot(git_repo, "save", "test save")
        assert rc == 0
        assert "Snapshot saved:" in out
        assert "test save" in out

    def test_save_clean_tree(self, git_repo):
        """Save on a clean tree returns error."""
        rc, out, err = dz_snapshot(git_repo, "save")
        assert rc == 1
        assert "clean" in err.lower()

    def test_save_default_message(self, git_repo):
        """Save without message uses 'snapshot'."""
        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("modified\n")

        rc, out, err = dz_snapshot(git_repo, "save")
        assert rc == 0
        assert "snapshot" in out.lower()

    def test_save_preserves_working_tree(self, git_repo):
        """Save does not modify the working tree."""
        filepath = os.path.join(git_repo, "file.txt")
        with open(filepath, "w") as f:
            f.write("my changes\n")

        dz_snapshot(git_repo, "save", "checkpoint")

        with open(filepath) as f:
            assert f.read() == "my changes\n"

    def test_save_captures_untracked(self, git_repo):
        """Save captures untracked files by default."""
        # Create a new untracked file
        with open(os.path.join(git_repo, "newfile.txt"), "w") as f:
            f.write("untracked content\n")

        rc, out, err = dz_snapshot(git_repo, "save", "with untracked")
        assert rc == 0
        assert "Snapshot saved:" in out

    def test_save_preserves_index(self, git_repo):
        """Save preserves staged changes in the index."""
        filepath = os.path.join(git_repo, "file.txt")
        with open(filepath, "w") as f:
            f.write("staged change\n")
        git(git_repo, "add", "file.txt")

        # Add another unstaged change
        with open(filepath, "a") as f:
            f.write("unstaged line\n")

        dz_snapshot(git_repo, "save", "index test")

        # Check that file.txt is still staged
        rc, out, _ = git(git_repo, "diff", "--cached", "--name-only")
        assert "file.txt" in out


# -- list tests --

class TestList:
    def test_list_empty(self, git_repo):
        """List with no snapshots shows message."""
        rc, out, err = dz_snapshot(git_repo, "list")
        assert rc == 0
        assert "No snapshots" in out

    def test_list_shows_snapshots(self, git_repo):
        """List shows saved snapshots."""
        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("change 1\n")
        dz_snapshot(git_repo, "save", "first")

        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("change 2\n")
        dz_snapshot(git_repo, "save", "second")

        rc, out, err = dz_snapshot(git_repo, "list")
        assert rc == 0
        assert "first" in out
        assert "second" in out

    def test_list_json(self, git_repo):
        """List --json outputs valid JSON."""
        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("change\n")
        dz_snapshot(git_repo, "save", "json test")

        rc, out, err = dz_snapshot(git_repo, "list", "--json")
        assert rc == 0
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert "json-test" in data[0]["name"]

    def test_list_count(self, git_repo):
        """List --count limits output."""
        for i in range(3):
            with open(os.path.join(git_repo, "file.txt"), "w") as f:
                f.write(f"change {i}\n")
            dz_snapshot(git_repo, "save", f"snap-{i}")

        # Verify we have 3 snapshots
        rc, out, _ = dz_snapshot(git_repo, "list", "--json")
        data = json.loads(out)
        assert len(data) == 3

        # --count 2 should show only 2
        rc, out, err = dz_snapshot(git_repo, "list", "--count", "2")
        assert rc == 0
        # Count data lines (skip header, separator, and trailing info)
        data_lines = [l for l in out.splitlines()
                      if l.strip() and not l.strip().startswith("#")
                      and not l.strip().startswith("-")
                      and "Name" not in l and "Showing" not in l]
        assert len(data_lines) == 2


# -- show tests --

class TestShow:
    def test_show_by_index(self, git_repo):
        """Show by numeric index."""
        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("show test\n")
        dz_snapshot(git_repo, "save", "show me")

        rc, out, err = dz_snapshot(git_repo, "show", "1")
        assert rc == 0
        assert "show me" in out.lower() or "show-me" in out.lower()
        assert "file.txt" in out

    def test_show_not_found(self, git_repo):
        """Show with invalid name returns error."""
        rc, out, err = dz_snapshot(git_repo, "show", "nonexistent")
        assert rc == 1
        assert "not found" in err.lower()


# -- diff tests --

class TestDiff:
    def test_diff_no_changes(self, git_repo):
        """Diff when working tree matches snapshot shows no differences."""
        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("diff test\n")
        dz_snapshot(git_repo, "save", "diff base")

        rc, out, err = dz_snapshot(git_repo, "diff", "1")
        assert rc == 0
        assert "No differences" in out

    def test_diff_with_changes(self, git_repo):
        """Diff shows changes made after snapshot."""
        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("before\n")
        dz_snapshot(git_repo, "save", "diff base")

        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("after\n")

        rc, out, err = dz_snapshot(git_repo, "diff", "1", "--stat")
        assert rc == 0
        assert "file.txt" in out

    def test_diff_not_found(self, git_repo):
        """Diff with invalid name returns error."""
        rc, out, err = dz_snapshot(git_repo, "diff", "nonexistent")
        assert rc == 1


# -- drop tests --

class TestDrop:
    def test_drop_by_index(self, git_repo):
        """Drop by index removes the snapshot."""
        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("drop test\n")
        dz_snapshot(git_repo, "save", "to drop")

        rc, out, err = dz_snapshot(git_repo, "drop", "1", "--force")
        assert rc == 0
        assert "Dropped" in out

        rc, out, err = dz_snapshot(git_repo, "list")
        assert "No snapshots" in out

    def test_drop_by_name_prefix(self, git_repo):
        """Drop by partial name match."""
        with open(os.path.join(git_repo, "file.txt"), "w") as f:
            f.write("prefix drop\n")
        dz_snapshot(git_repo, "save", "unique-name-123")

        # Get the full name
        rc, out, _ = dz_snapshot(git_repo, "list", "--json")
        data = json.loads(out)
        full_name = data[0]["name"]
        # Use just the date prefix
        prefix = full_name.split("_")[0]

        rc, out, err = dz_snapshot(git_repo, "drop", prefix, "--force")
        assert rc == 0
        assert "Dropped" in out


# -- apply tests --

class TestApply:
    def test_apply_merge(self, git_repo):
        """Apply restores changes in merge mode."""
        filepath = os.path.join(git_repo, "file.txt")
        with open(filepath, "w") as f:
            f.write("snapshot state\n")
        dz_snapshot(git_repo, "save", "to apply")

        # Reset to original
        git(git_repo, "checkout", "--", "file.txt")

        # Apply should restore
        rc, out, err = dz_snapshot(git_repo, "apply", "1")
        assert rc == 0
        assert "Applied" in out

        with open(filepath) as f:
            assert f.read() == "snapshot state\n"


# -- restore tests --

class TestRestore:
    def test_restore_requires_force(self, git_repo):
        """Restore refuses without --force when changes exist."""
        filepath = os.path.join(git_repo, "file.txt")
        with open(filepath, "w") as f:
            f.write("snap state\n")
        dz_snapshot(git_repo, "save", "to restore")

        with open(filepath, "w") as f:
            f.write("different state\n")

        rc, out, err = dz_snapshot(git_repo, "restore", "1")
        assert rc == 1
        assert "--force" in err

    def test_restore_with_force(self, git_repo):
        """Restore with --force replaces working tree."""
        filepath = os.path.join(git_repo, "file.txt")
        with open(filepath, "w") as f:
            f.write("snap state\n")
        dz_snapshot(git_repo, "save", "to restore")

        with open(filepath, "w") as f:
            f.write("different state\n")

        rc, out, err = dz_snapshot(git_repo, "restore", "1", "--force")
        assert rc == 0
        assert "Restored" in out

        with open(filepath) as f:
            assert f.read() == "snap state\n"


# -- clean tests --

class TestClean:
    def test_clean_keep(self, git_repo):
        """Clean --keep N removes excess snapshots."""
        for i in range(3):
            with open(os.path.join(git_repo, "file.txt"), "w") as f:
                f.write(f"v{i}\n")
            dz_snapshot(git_repo, "save", f"keep-test-{i}")

        rc, out, err = dz_snapshot(git_repo, "clean", "--keep", "1")
        assert rc == 0
        assert "2" in out  # dropped 2

        rc, out, _ = dz_snapshot(git_repo, "list", "--json")
        data = json.loads(out)
        assert len(data) == 1

    def test_clean_dry_run(self, git_repo):
        """Clean --dry-run shows what would be dropped without doing it."""
        for i in range(2):
            with open(os.path.join(git_repo, "file.txt"), "w") as f:
                f.write(f"v{i}\n")
            dz_snapshot(git_repo, "save", f"dry-{i}")

        rc, out, err = dz_snapshot(git_repo, "clean", "--keep", "1", "--dry-run")
        assert rc == 0
        assert "Would drop" in out

        # Verify nothing was actually dropped
        rc, out, _ = dz_snapshot(git_repo, "list", "--json")
        data = json.loads(out)
        assert len(data) == 2
