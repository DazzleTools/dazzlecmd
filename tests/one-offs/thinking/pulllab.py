"""pulllab -- does our pull guard agree with git?

USER REPORT 2026-08-08: `dz dazzle-update . --fix` refused to pull
dazzlesum with "dirty tree -- refusing to pull (will not stash)". The
tree held ONE untracked file, `.vscode/settings.json`, and the incoming
commits added `docs/platforms.md` and a checklist. Nothing collided.
The pull would have been a clean fast-forward.

The guard at dazzle_update.py:858 refuses on `dirty_count > 0 OR
untracked_count > 0` -- a PROXY for the real question, which is whether
what is coming in touches what you have. This harness answers the real
question empirically instead of arguing about it, because git is the
oracle here: it already decides this precisely, and its decision is
observable.

For each scenario it builds a real origin + clone, puts the clone in a
known state, runs a REAL `git pull`, and records what git did. Then it
scores three predicates against that ground truth:

    git      -- what actually happened (the oracle)
    current  -- dirty_count > 0 or untracked_count > 0
    proposed -- incoming paths intersect uncommitted paths

Two failure modes are NOT symmetric, so they are scored separately:

    OVER-REFUSE   we blocked a pull git would have completed.
                  Costs the user a working fix and lies about why.
    UNDER-REFUSE  we would have attempted a pull git rejects.
                  Costs nothing IF git aborts atomically -- which is
                  the thing this harness has to prove, not assume.

Sibling of setlab.py (set-rule language) and querylab.py (query
freshness): measure out-of-tree, then change production code.

Read-only against real repos. Fixtures are built in a temp dir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

# git reports paths with forward slashes; the FS here is case-insensitive.
# Casefolding can only make the intersection LARGER, i.e. more cautious,
# and on Windows a case-differing path genuinely does collide.
WINDOWS = os.name == "nt"


def git(cwd, *args, check=True):
    p = subprocess.run(["git"] + list(args), cwd=str(cwd), text=True,
                       capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}:\n"
                           f"{p.stdout}\n{p.stderr}")
    return p


def git_z(cwd, *args):
    """NUL-separated output -- git QUOTES paths with special characters
    in its normal output, so a filename with a space or a non-ASCII
    byte would be compared in its escaped form and never match."""
    p = git(cwd, *args)
    return [x for x in p.stdout.split("\0") if x]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def init_repo(path):
    os.makedirs(path, exist_ok=True)
    git(path, "init", "-b", "main")
    # No signing: the host signs commits globally and a fixture that
    # inherits that pops pinentry mid-run (it did, in _repo_common).
    git(path, "config", "user.email", "lab@example.invalid")
    git(path, "config", "user.name", "Lab")
    git(path, "config", "commit.gpgsign", "false")
    return path


# ---------------------------------------------------------------- probe

def probe(clone):
    """The three quantities the guards reason about, measured."""
    dirty = git_z(clone, "diff", "--name-only", "-z", "HEAD")
    untracked = git_z(clone, "ls-files", "--others", "--exclude-standard",
                      "-z")
    incoming_all = git_z(clone, "diff", "--name-only", "-z", "HEAD..@{u}")
    incoming_adds = git_z(clone, "diff", "--name-only", "-z",
                          "--diff-filter=A", "HEAD..@{u}")
    return {"dirty": dirty, "untracked": untracked,
            "incoming_all": incoming_all, "incoming_adds": incoming_adds}


def _fold(paths):
    return {p.casefold() if WINDOWS else p for p in paths}


def predicate_current(m):
    """dazzle_update.py:858 as it stands today."""
    return bool(m["dirty"]) or bool(m["untracked"])


def collisions(m):
    """Paths where what is coming in touches what you have.

    An untracked file can only be hit by an incoming ADD: if upstream
    MODIFIES a path, that path exists in HEAD, so it is tracked here too
    and belongs to the other half of this union.
    """
    hit_untracked = _fold(m["incoming_adds"]) & _fold(m["untracked"])
    hit_tracked = _fold(m["incoming_all"]) & _fold(m["dirty"])
    return sorted(hit_untracked | hit_tracked)


def predicate_proposed(m):
    return bool(collisions(m))


# ------------------------------------------------------------ scenarios

def _origin_with_history(root, name):
    """An origin holding one commit, plus a clone of it. The origin then
    gains a second commit, so the clone is behind by one."""
    origin = init_repo(os.path.join(root, name + "-origin"))
    write(os.path.join(origin, "kept.txt"), "base\n")
    write(os.path.join(origin, "other.txt"), "base\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-m", "base")

    clone = os.path.join(root, name)
    git(root, "clone", "-q", origin, clone)
    git(clone, "config", "user.email", "lab@example.invalid")
    git(clone, "config", "user.name", "Lab")
    git(clone, "config", "commit.gpgsign", "false")
    return origin, clone


def _advance_origin(origin, adds=(), mods=()):
    for p in adds:
        write(os.path.join(origin, p), "added upstream\n")
    for p in mods:
        write(os.path.join(origin, p), "changed upstream\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-m", "upstream work")


SCENARIOS = {}


def scenario(fn):
    SCENARIOS[fn.__name__] = fn
    return fn


@scenario
def clean(root):
    """Nothing local. The baseline: a pull that must work."""
    origin, clone = _origin_with_history(root, "clean")
    _advance_origin(origin, mods=["other.txt"])
    return clone, {}


@scenario
def untracked_no_collision(root):
    """THE REPORTED CASE. An untracked file upstream knows nothing about.

    dazzlesum: `.vscode/settings.json` untracked, incoming adds
    `docs/platforms.md`.
    """
    origin, clone = _origin_with_history(root, "untracked_no_collision")
    _advance_origin(origin, adds=["docs/platforms.md"])
    write(os.path.join(clone, ".vscode/settings.json"), "{}\n")
    return clone, {".vscode/settings.json": "{}\n"}


@scenario
def untracked_collision(root):
    """Upstream adds the very path you are holding untracked. This is
    the case the blanket guard was reaching for -- the question is
    whether git handles it safely on its own."""
    origin, clone = _origin_with_history(root, "untracked_collision")
    _advance_origin(origin, adds=["docs/platforms.md"])
    write(os.path.join(clone, "docs/platforms.md"), "MINE -- do not lose\n")
    return clone, {"docs/platforms.md": "MINE -- do not lose\n"}


@scenario
def modified_no_collision(root):
    """A tracked file edited locally; upstream touched a different one."""
    origin, clone = _origin_with_history(root, "modified_no_collision")
    _advance_origin(origin, mods=["other.txt"])
    write(os.path.join(clone, "kept.txt"), "MINE -- do not lose\n")
    return clone, {"kept.txt": "MINE -- do not lose\n"}


@scenario
def modified_collision(root):
    """Both sides edited the same tracked file."""
    origin, clone = _origin_with_history(root, "modified_collision")
    _advance_origin(origin, mods=["kept.txt"])
    write(os.path.join(clone, "kept.txt"), "MINE -- do not lose\n")
    return clone, {"kept.txt": "MINE -- do not lose\n"}


@scenario
def staged_no_collision(root):
    """Staged rather than merely modified -- `git diff HEAD` covers both,
    but only if the probe uses HEAD and not the default index compare."""
    origin, clone = _origin_with_history(root, "staged_no_collision")
    _advance_origin(origin, mods=["other.txt"])
    write(os.path.join(clone, "kept.txt"), "MINE -- staged\n")
    git(clone, "add", "kept.txt")
    return clone, {"kept.txt": "MINE -- staged\n"}


@scenario
def untracked_in_incoming_dir(root):
    """An untracked file INSIDE a directory the pull creates, but not at
    a path the pull writes. Directory-level thinking would refuse; git
    works at path level."""
    origin, clone = _origin_with_history(root, "untracked_in_incoming_dir")
    _advance_origin(origin, adds=["docs/platforms.md"])
    write(os.path.join(clone, "docs/scratch.md"), "mine\n")
    return clone, {"docs/scratch.md": "mine\n"}


@scenario
def untracked_case_differs(root):
    """Upstream adds `docs/Platforms.md`; you hold `docs/platforms.md`.
    On a case-insensitive filesystem these are the same file."""
    origin, clone = _origin_with_history(root, "untracked_case_differs")
    _advance_origin(origin, adds=["docs/Platforms.md"])
    write(os.path.join(clone, "docs/platforms.md"), "MINE -- do not lose\n")
    return clone, {"docs/platforms.md": "MINE -- do not lose\n"}


@scenario
def untracked_spaces_in_name(root):
    """A space in the path. Measured, not assumed: git does NOT quote
    these -- `--name-only` prints `docs/my notes.md` bare. Kept because
    a space is the shape that LOOKS like it needs escaping, and someone
    will eventually 'fix' the probe by splitting on whitespace."""
    origin, clone = _origin_with_history(root, "untracked_spaces_in_name")
    _advance_origin(origin, adds=["docs/my notes.md"])
    write(os.path.join(clone, "docs/my notes.md"), "MINE -- do not lose\n")
    return clone, {"docs/my notes.md": "MINE -- do not lose\n"}


@scenario
def churn_no_collision(root):
    """A hook-restamped version file, upstream touching something else.

    Churn is excluded from `dirty_count` for REPORTING, which is why a
    SEPARATE blanket guard exists for it. But git knows nothing about
    churn -- a restamped file is simply a modified tracked file, so the
    collision probe sees it without being told. If this pulls cleanly,
    the separate churn guard is the same over-refusal wearing a
    different name.
    """
    origin, clone = _origin_with_history(root, "churn_no_collision")
    _advance_origin(origin, mods=["other.txt"])
    write(os.path.join(clone, "kept.txt"), "version = 1.2.3-abcdef\n")
    return clone, {"kept.txt": "version = 1.2.3-abcdef\n"}


@scenario
def churn_collision(root):
    """The case the churn guard was reaching for: upstream bumped the
    very file the hook restamps. Every version bump touches it, so this
    is the common half -- and the probe must still catch it."""
    origin, clone = _origin_with_history(root, "churn_collision")
    _advance_origin(origin, mods=["kept.txt"])
    write(os.path.join(clone, "kept.txt"), "version = 1.2.3-abcdef\n")
    return clone, {"kept.txt": "version = 1.2.3-abcdef\n"}


@scenario
def untracked_non_ascii_name(root):
    """THE case that makes -z load-bearing. git DOES quote non-ASCII:

        $ git show --name-only --format=
        "docs/caf\\303\\251.md"

    Without -z the probe compares that escaped literal against the real
    filename, never matches, and reports no collision on a pull git is
    about to reject -- the guard would be measuring git's error format
    rather than the tree.
    """
    origin, clone = _origin_with_history(root, "untracked_non_ascii_name")
    _advance_origin(origin, adds=["docs/café.md"])
    write(os.path.join(clone, "docs/café.md"), "MINE -- do not lose\n")
    return clone, {"docs/café.md": "MINE -- do not lose\n"}


# ----------------------------------------------------------------- run

def run_one(name, fn, root):
    clone, guard = fn(root)
    git(clone, "fetch", "-q", "origin")

    m = probe(clone)
    cur = predicate_current(m)
    prop = predicate_proposed(m)
    coll = collisions(m)

    head_before = git(clone, "rev-parse", "HEAD").stdout.strip()

    # The oracle. --ff-only because a fast-forward is the only thing the
    # tool ever performs; a merge is refused upstream of this guard.
    p = subprocess.run(["git", "pull", "--ff-only"], cwd=clone, text=True,
                       capture_output=True)
    git_ok = p.returncode == 0

    head_after = git(clone, "rev-parse", "HEAD").stdout.strip()
    moved = head_before != head_after

    # Did the user's uncommitted content survive, byte for byte?
    survived = True
    for rel, want in guard.items():
        full = os.path.join(clone, rel)
        if not os.path.exists(full):
            survived = False
            break
        with open(full, encoding="utf-8") as fh:
            if fh.read() != want:
                survived = False
                break

    return {"name": name, "git_ok": git_ok, "moved": moved,
            "survived": survived, "current_refuses": cur,
            "proposed_refuses": prop, "collisions": coll,
            "dirty": m["dirty"], "untracked": m["untracked"],
            "git_msg": (p.stderr or p.stdout).strip().splitlines()[:1]}


def verdict(r):
    """Compare each predicate to what git actually did."""
    out = {}
    for which in ("current", "proposed"):
        refuses = r[f"{which}_refuses"]
        if refuses and r["git_ok"]:
            out[which] = "OVER-REFUSE"
        elif not refuses and not r["git_ok"]:
            out[which] = "under-refuse"
        else:
            out[which] = "agrees"
    return out


def main():
    root = tempfile.mkdtemp(prefix="pulllab-")
    rows = []
    try:
        for name, fn in SCENARIOS.items():
            rows.append(run_one(name, fn, root))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    w = max(len(r["name"]) for r in rows) + 1
    print()
    print("  git pull --ff-only, real repos. 'git ok' is the oracle.")
    print()
    print(f"  {'scenario':<{w}} {'git ok':>7} {'kept':>5} "
          f"{'current':>9} {'proposed':>9}   verdict")
    print("  " + "-" * (w + 48))

    over_cur = over_prop = under_cur = under_prop = 0
    lost = []
    for r in rows:
        v = verdict(r)
        over_cur += v["current"] == "OVER-REFUSE"
        over_prop += v["proposed"] == "OVER-REFUSE"
        under_cur += v["current"] == "under-refuse"
        under_prop += v["proposed"] == "under-refuse"
        if not r["survived"]:
            lost.append(r["name"])
        note = ""
        if v["current"] != v["proposed"]:
            note = f"  current={v['current']} proposed={v['proposed']}"
        else:
            note = f"  both {v['current']}"
        print(f"  {r['name']:<{w}} {str(r['git_ok']):>7} "
              f"{str(r['survived']):>5} "
              f"{str(r['current_refuses']):>9} "
              f"{str(r['proposed_refuses']):>9} {note}")

    print()
    print(f"  OVER-REFUSE (blocked a pull git completes):  "
          f"current={over_cur}  proposed={over_prop}")
    print(f"  under-refuse (attempted one git rejects):    "
          f"current={under_cur}  proposed={under_prop}")
    print()
    if lost:
        print(f"  !! UNCOMMITTED CONTENT LOST in: {', '.join(lost)}")
        print("     git does NOT abort atomically -- under-refusing is "
              "NOT free, and the guard must stay conservative.")
    else:
        print("  Uncommitted content survived EVERY scenario, including "
              "every one git rejected.")
        print("  git aborts before touching the tree, so an under-refusal "
              "costs a failed command, not work.")
    print()

    print("  collisions detected per scenario:")
    for r in rows:
        print(f"    {r['name']:<{w}} {r['collisions'] or '--'}"
              f"   (dirty={r['dirty'] or '--'}, "
              f"untracked={r['untracked'] or '--'})")
    print()
    for r in rows:
        if not r["git_ok"]:
            print(f"    {r['name']}: {r['git_msg']}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
