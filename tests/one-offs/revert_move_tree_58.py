#!/usr/bin/env python3
"""Reverse the #58 partial move: git mv everything back from src/dazzlecmd/ to
the repo root. Uses `git mv` (NOT reset --hard) so parked working-tree
modifications (README/find.py/.kit.json edits) ride back intact and stay
unstaged, exactly as before the move. Submodule reversed first.
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREFIX = "src/dazzlecmd/"


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
    sub = "src/dazzlecmd/projects/core/listall"
    if os.path.exists(os.path.join(REPO, sub)):
        print("[1] reverse submodule -> projects/core/listall")
        mv(sub, "projects/core/listall")

    moved = ls("src/dazzlecmd/projects", "src/dazzlecmd/kits",
               "src/dazzlecmd/aggregator.json")
    print(f"[2] reversing {len(moved)} tracked files back to root")
    for f in moved:
        assert f.startswith(PREFIX), f
        mv(f, f[len(PREFIX):])
    print(f"[done] reversed {len(moved)} files + the submodule")


if __name__ == "__main__":
    main()
