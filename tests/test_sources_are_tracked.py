"""Every source file must be tracked by git.

v0.12.11 shipped broken: `_repo_common/private_state.py` was written,
imported by two modules, covered by its own test file, and passed the
full suite locally -- while `.gitignore`'s `**/private_*` silently
dropped it from every commit. `git add -A` reported success. The
package installed from a fresh clone raised

    Could not import dazzle_update: No module named
    '_repo_common.private_state'

and nothing on the authoring machine could have noticed, because the
file was present there.

This is the same class of bug the tools in this repo exist to catch --
a report describing the question ("do my tests pass?") rather than the
machine ("is this file in the commit?"). The check is one `git
ls-files` call per source file, and it is the only thing that can see
the difference between "exists" and "shipped".

It has now happened twice: `private-init/private_init.py` already
carries an explicit un-ignore exception for exactly this reason.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "dazzlecmd"

#: Directories whose contents are legitimately untracked.
SKIP_PARTS = {"__pycache__", ".pytest_cache", "node_modules", ".venv",
              "venv", "build", "dist", ".git", "private"}


def _foreign_repo_roots():
    """Directories under src/ that belong to ANOTHER git repository.

    Two shapes occur here and both must be excluded, because `git
    ls-files` in this repo rightly does not know their contents:

      * registered submodules (projects/core/listall) -- tracked as a
        single gitlink;
      * nested repos that are NOT submodules (projects/wtf) -- kits
        materialized on demand, owned entirely by their own clone.

    Detecting `.git` directly covers both without asking git to
    enumerate a relationship it may not have.
    """
    roots = []
    for git_entry in SRC.rglob(".git"):
        root = git_entry.parent
        if root != REPO:
            roots.append(root.relative_to(REPO).as_posix())
    return roots


def _source_files():
    if not SRC.is_dir():
        pytest.skip(f"no source tree at {SRC}")
    subs = _foreign_repo_roots()
    for p in SRC.rglob("*.py"):
        rel = p.relative_to(REPO).as_posix()
        if SKIP_PARTS & set(p.relative_to(REPO).parts):
            continue
        if any(rel.startswith(s.rstrip("/") + "/") for s in subs):
            continue
        yield p


def _untracked(paths):
    """Return the subset git does not have in its index."""
    missing = []
    for p in paths:
        rel = p.relative_to(REPO).as_posix()
        rc = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "--error-unmatch", rel],
            capture_output=True, text=True).returncode
        if rc != 0:
            missing.append(rel)
    return missing


def test_every_source_file_is_tracked():
    files = sorted(_source_files())
    assert files, "no source files discovered -- the walk itself is wrong"
    missing = _untracked(files)
    assert not missing, (
        "these source files exist on disk but are NOT tracked by git, so a "
        "fresh clone will not have them:\n  "
        + "\n  ".join(missing)
        + "\n\nIf a .gitignore rule is responsible, add an explicit "
          "un-ignore (!path) rather than renaming the file. Check with:\n"
          "  git check-ignore -v <path>")


def test_the_module_that_caused_this_is_tracked():
    """Named regression: the file whose absence shipped v0.12.11 broken."""
    target = SRC / "projects" / "dazzletools" / "_repo_common" / "private_state.py"
    if not target.exists():
        pytest.skip("private_state.py not present in this working tree")
    assert not _untracked([target]), (
        "private_state.py is untracked again -- .gitignore's '**/private_*' "
        "has re-eaten it; the un-ignore exception must have been removed")
