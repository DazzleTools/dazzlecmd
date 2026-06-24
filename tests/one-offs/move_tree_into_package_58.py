#!/usr/bin/env python3
"""#58 move: relocate the TRACKED tool tree into the package for PyPI.

Moves ``projects/``, ``kits/``, and ``aggregator.json`` from the repo root into
``src/dazzlecmd/`` via per-file ``git mv`` -- which stages ONLY the tracked
renames and never touches the untracked parked WIP (honoring the
never-stage-parked-WIP rule). The ``projects/core/listall`` submodule is moved
first so git 2.52 updates ``.gitmodules`` + ``.git/modules`` for it.

Safety: a full backup exists at ``C:\\code\\dazzlecmd\\github.2026.6.21`` and a
git-snapshot was taken before running. Idempotent-ish: re-running after a partial
move will just move whatever tracked files still sit at the old root.

After this script: update pyproject (packages.find exclude + package-data globs),
repoint the ~4 live-repo tests, verify editable `dz` + suite + a built wheel.
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def git(args, check=True):
    r = subprocess.run(["git"] + args, cwd=REPO, text=True, capture_output=True)
    if check and r.returncode != 0:
        sys.stderr.write(f"FAIL: git {' '.join(args)}\n{r.stdout}\n{r.stderr}\n")
        sys.exit(1)
    return r


def ls(*paths):
    out = git(["ls-files", "-z", *paths]).stdout
    return [p for p in out.split("\0") if p]


def mv(src, dst):
    os.makedirs(os.path.dirname(os.path.join(REPO, dst)), exist_ok=True)
    git(["mv", src, dst])


def main():
    # 1. submodule FIRST -- git mv updates .gitmodules + .git/modules
    if os.path.exists(os.path.join(REPO, "projects", "core", "listall")):
        print("[1] git mv submodule: projects/core/listall")
        mv("projects/core/listall", "src/dazzlecmd/projects/core/listall")
    else:
        print("[1] submodule already moved -- skipping")

    # 2. all remaining tracked files under projects/ + kits/ + aggregator.json
    files = ls("projects", "kits")
    if git(["ls-files", "aggregator.json"]).stdout.strip():
        files.append("aggregator.json")
    print(f"[2] git mv {len(files)} tracked files -> src/dazzlecmd/")
    skipped = []
    for f in files:
        # Skip deleted-but-tracked files (a parked pending-deletion, e.g.
        # claude-lost-sessions): git mv can't move a file that's gone from disk.
        # Leave the parked deletion untouched at its old path.
        if not os.path.exists(os.path.join(REPO, f)):
            skipped.append(f)
            continue
        mv(f, "src/dazzlecmd/" + f)
    if skipped:
        print(f"    skipped {len(skipped)} deleted-but-tracked (parked deletion, left as-is):")
        for s in skipped:
            print(f"      - {s}")

    print(f"[done] moved {len(files)} tracked files + the submodule")
    print("       (untracked parked WIP left at the old root, unstaged)")


if __name__ == "__main__":
    main()
