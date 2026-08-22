"""The `private/` convention -- inspect it, never prescribe it.

Some projects keep working notes, design docs, and postmortems in a
gitignored `private/` directory backed by its own git repository, with
sibling worktrees linked to one shared copy so related documents stay
findable together. Because the directory is gitignored, it is invisible
to every other axis a repo scanner has: git status will not mention it,
pip does not know it exists, and no namespace listing includes it. A
directory full of design documents can therefore sit in exactly one
place, with no history and no backup, and nothing anywhere reports it.

This module answers what IS, per checkout. It deliberately does not
answer what SHOULD be:

  * Whether the convention applies at all is decided by EVIDENCE (does
    this checkout actually hold private material?), never by who owns
    the repo. Notes taken while reading someone else's code are real
    work -- often the only record of understanding a codebase its
    authors never documented -- so a third-party clone with private
    material is checked exactly like anything else. A checkout with no
    `private/` is silent, always: proposing that one be created would
    be lecturing about a convention the reader may not share.
  * Linked-vs-standalone is not reported as right or wrong. What
    matters is which STORAGE a checkout resolves to, because the claim
    the convention makes is "worktrees of a project share one private
    store". Junction, symlink, or a repo sitting directly in the
    canonical checkout are three mechanisms for the same claim.
  * Junctions and symlinks are collapsed to "linked". The Windows
    convention is a junction and the POSIX one a symlink; reporting the
    distinction would read as a portability warning that is not there.
"""

import io
import os


def _is_reparse(path):
    """True for a junction or a symlink, without following it."""
    if os.path.islink(path):
        return True
    try:
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & 0x400)          # FILE_ATTRIBUTE_REPARSE_POINT


def _has_content(path, ignore=(".git",)):
    """Does the store hold anything at all? Stops at the first file.

    A full walk of every private/ on a real machine took seconds; a
    scanner cannot pay that per checkout. The question is only whether
    the directory is empty, and one file answers it.
    """
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    if entry.name in ignore:
                        continue
                    try:
                        if entry.is_file(follow_symlinks=False):
                            return True
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return False


def _git_dir(store_path):
    """Resolve a store's git directory, following a gitfile pointer.

    `.git` is a directory for an ordinary repo and a FILE holding
    `gitdir: <path>` for a worktree or submodule. Returns the resolved
    directory, or None when there is no repository or the pointer does
    not resolve -- an unresolvable pointer is not evidence of anything.
    """
    entry = os.path.join(store_path, ".git")
    if os.path.isdir(entry):
        return entry
    if not os.path.isfile(entry):
        return None
    try:
        with io.open(entry, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline().strip()
    except OSError:
        return None
    if not first.lower().startswith("gitdir:"):
        return None
    target = first.split(":", 1)[1].strip()
    if not target:
        return None
    resolved = target if os.path.isabs(target) else os.path.join(store_path, target)
    resolved = os.path.normpath(resolved)
    return resolved if os.path.isdir(resolved) else None


def _has_history(store_path):
    """True only if the store's repository holds at least one commit.

    A repository can exist and hold nothing: `git init` in a notes
    directory creates `.git` before anything is committed, and the store
    then reads as versioned while holding no recoverable history at all.
    That is precisely the state this axis exists to notice -- docs living
    in one place with no recovery point -- so the presence of `.git` is
    not, by itself, evidence of a backup.

    Read from disk rather than by subprocess: this runs once per checkout
    on a scan of hundreds, and this module's cost is stat-only by design.
    A repository with loose heads answers on the first entry; one whose
    refs have been packed is answered from packed-refs.
    """
    git_dir = _git_dir(store_path)
    if git_dir is None:
        return False
    try:
        with os.scandir(os.path.join(git_dir, "refs", "heads")) as it:
            for _ in it:
                return True
    except OSError:
        pass
    try:
        with io.open(os.path.join(git_dir, "packed-refs"),
                     encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "refs/heads/" in line:
                    return True
    except OSError:
        pass
    return False


def private_state(checkout_path, dirname="private"):
    """Inspect one checkout's private store.

    Returns a dict, always with the same keys:

        shape      none | plain | repo | linked | broken
        linked     bool -- reached through a junction or symlink
        versioned  bool -- the store's repository holds at least one
                   commit; a `git init` with nothing committed is NOT
                   versioned, because nothing is recoverable from it
        storage    normalized real path of the store, or None
        content    bool -- the store holds at least one file
        claude     bool -- a `claude/` subdirectory exists (the docs
                   convention within the convention; informational)

    `shape` is deliberately coarse: `linked` covers junction and
    symlink, and says nothing about whether the target is versioned --
    that is what `versioned` is for, and the two vary independently
    (a link to an unversioned directory is a real, observed state).
    """
    blank = {"shape": "none", "linked": False, "versioned": False,
             "storage": None, "content": False, "claude": False}
    if not checkout_path:
        return blank
    path = os.path.join(str(checkout_path), dirname)
    if not os.path.lexists(path):
        return blank

    linked = _is_reparse(path)
    if not os.path.isdir(path):
        # A link whose target is gone: the notes are unreachable from
        # here and nothing errors until something tries to read them.
        return {**blank, "shape": "broken" if linked else "none",
                "linked": linked}

    try:
        storage = os.path.normcase(os.path.realpath(path))
    except OSError:
        storage = os.path.normcase(os.path.abspath(path))
    versioned = _has_history(storage)
    return {
        "shape": "linked" if linked else ("repo" if versioned else "plain"),
        "linked": linked,
        "versioned": versioned,
        "storage": storage,
        "content": _has_content(storage),
        "claude": os.path.isdir(os.path.join(storage, "claude")),
    }


#: Record-level verdicts. Ordered by how much they want attention.
PRIVATE_OK = "ok"                    # versioned, and shared if plural
PRIVATE_SPLIT = "split"              # versioned, but stores differ
PRIVATE_UNVERSIONED = "unversioned"  # material with no history behind it
PRIVATE_BROKEN = "broken"            # a link with no target
PRIVATE_NONE = "none"                # nothing here; never reported


def judge_private(states):
    """Reduce a record's per-checkout states to one verdict.

    `states` are the private_state dicts of a record's LIVE checkouts
    (excluded snapshots do not speak for a repo -- an archive keeps
    whatever it was frozen with, which is not actionable).

    The verdict encodes the convention's actual claim -- one shared,
    versioned store per project -- while refusing to treat any of it as
    mandatory. In particular `split` is not an error: separate private
    repositories are a legitimate way to keep sensitive work apart, so
    the caller is expected to surface it as encouragement rather than
    as a fault, and to let a project opt out entirely.
    """
    present = [s for s in states if s and s["shape"] != "none"]
    if not present:
        return PRIVATE_NONE
    if any(s["shape"] == "broken" for s in present):
        return PRIVATE_BROKEN
    if not any(s["versioned"] for s in present):
        return PRIVATE_UNVERSIONED
    stores = {s["storage"] for s in present if s["storage"]}
    return PRIVATE_OK if len(stores) <= 1 else PRIVATE_SPLIT


def has_private_material(states):
    """True when any live checkout's store actually holds something.

    The finding is about material that exists with no history -- an
    empty scaffold directory is not worth anyone's attention.
    """
    return any(s and s.get("content") for s in states)
