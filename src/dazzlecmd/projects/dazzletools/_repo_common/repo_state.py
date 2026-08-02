"""Git repo state primitives -- location-explicit, cwd-side-effect-free.

Moved verbatim from dazzletools/git/git.py so a multi-repo scanner can
reuse them without chdir-ing per repo. Bodies are unchanged; the only
modification is that each function takes the repo path explicitly
instead of relying on the process working directory.

Two constraints, because this module is a candidate for extraction into
a standalone library later:

    1. No imports from dazzlecmd. Standard library only.
    2. No process-cwd reads or writes in the primitives. Callers pass paths.

Repo discovery, interactive prompts, and output layout are CLI concerns
and stay in the consuming tool. This directory has no .dazzlecmd.json
manifest, which is what keeps it out of tool discovery.
"""

import configparser
import os
import re
import subprocess
import sys

# -- verbosity --

# Global verbosity level, set by the consuming CLI via set_verbosity().
# Controls diagnostic output on stderr only; never affects return values.
VERBOSITY = 0


def set_verbosity(level):
    """Set diagnostic verbosity for this module."""
    global VERBOSITY
    VERBOSITY = level


def get_verbosity():
    """Return the current diagnostic verbosity."""
    return VERBOSITY


def vprint(level, text, file=None):
    """Print only if verbosity >= level."""
    if VERBOSITY >= level:
        safe_print(text, file=file)


def show_cmd(cmd_parts):
    """At -vv+, print the git command being run."""
    if VERBOSITY >= 2:
        safe_print(f"  $ {' '.join(cmd_parts)}", file=sys.stderr)


# -- helpers --

def run_cmd(cmd, *args, cwd=None, timeout=None):
    """Run a command and return (returncode, stdout, stderr).

    A missing or non-directory `cwd` returns a failure tuple instead of
    raising. A multi-repo scan must survive paths that are stale or
    vanish mid-walk -- notably a broken editable install whose recorded
    source directory has since moved. A timeout likewise returns a
    failure tuple: one unreachable remote must not hang a whole sweep.
    """
    try:
        result = subprocess.run(
            [cmd] + list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"
    except (NotADirectoryError, FileNotFoundError) as exc:
        return 1, "", str(exc)
    except OSError as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def git(*args, cwd=None, timeout=None):
    """Run a git command."""
    show_cmd(["git"] + list(args))
    rc, out, err = run_cmd("git", *args, cwd=cwd, timeout=timeout)
    if VERBOSITY >= 3 and out.strip():
        for line in out.strip().splitlines():
            safe_print(f"    {line}", file=sys.stderr)
    return rc, out, err


def safe_print(text, file=None):
    """Print text with Windows codepage safety."""
    replacements = {
        "\u2014": "--",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u2192": "->",
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    try:
        text.encode(sys.stdout.encoding or "utf-8")
    except (UnicodeEncodeError, LookupError):
        text = text.encode("ascii", errors="replace").decode("ascii")
    print(text, file=file)


# -- branch / head --

def get_branch(repo_path=None):
    """Get current branch name, or None if detached."""
    rc, out, _ = git("branch", "--show-current", cwd=repo_path)
    if rc != 0:
        return None
    branch = out.strip()
    return branch if branch else None


def get_head_short(repo_path=None):
    """Get short HEAD hash."""
    rc, out, _ = git("rev-parse", "--short", "HEAD", cwd=repo_path)
    return out.strip() if rc == 0 else "unknown"


# -- repo identity --
#
# git searches UPWARD for a .git directory, so every primitive below
# reports on the nearest ENCLOSING repo, not necessarily on the path it
# was handed. That is git's real behavior and these functions do not
# fight it -- but a scanner walking a directory tree must not treat an
# ordinary subdirectory as a repo, or it will attribute an ancestor's
# state to it. (Observed: pytest tmp dirs under %USERPROFILE% resolve to
# the home-directory repo.) Callers that enumerate candidates must gate
# on is_repo_root() rather than assuming.

def get_repo_root(repo_path=None):
    """Return the toplevel of the repo containing repo_path, or None."""
    rc, out, _ = git("rev-parse", "--show-toplevel", cwd=repo_path)
    if rc != 0:
        return None
    root = out.strip()
    return root if root else None


def is_repo_root(repo_path):
    """True only if repo_path IS a repo's toplevel (not merely inside one).

    This is the guard that keeps a tree walk honest: it rejects both
    non-repo directories and subdirectories of a repo.
    """
    if not repo_path:
        return False
    root = get_repo_root(repo_path)
    if root is None:
        return False
    return os.path.normcase(os.path.abspath(root)) == \
        os.path.normcase(os.path.abspath(str(repo_path)))


def is_inside_repo(repo_path):
    """True if repo_path is inside any git repo (possibly an ancestor)."""
    return get_repo_root(repo_path) is not None


# -- sync state --
#
# Inbound drift (behind) is visible to anyone with the remote. Outbound
# drift (ahead, dirty, untracked, no upstream) is visible ONLY from the
# box holding the repo, which is why these are reported, not inferred.

def get_last_commit_epoch(repo_path=None, ref="HEAD"):
    """Unix timestamp of `ref`'s commit, or None.

    Used to sort a report by recency: with 150 repos, the ones you
    touched this week matter more than the ones you touched in 2023, and
    alphabetical order buries them.
    """
    rc, out, _ = git("log", "-1", "--format=%ct", ref, cwd=repo_path)
    if rc != 0:
        return None
    try:
        return int(out.strip())
    except (TypeError, ValueError):
        return None


def fetch_remote(repo_path=None, remote="origin", timeout=60):
    """Refresh remote-tracking refs. Returns (ok, detail).

    Without this, `behind` is measured against whatever the last fetch
    left behind -- so a repo with commits waiting upstream reports 0
    behind and reads as current. That silent false-negative defeats the
    entire point of an update scanner, so fetching is on by default.

    Only remote-tracking refs are touched: no local branch, no working
    tree, no index. Safe to run against a repo mid-edit.
    """
    rc, _out, err = git("fetch", remote, "--quiet", "--prune",
                        cwd=repo_path, timeout=timeout)
    if rc == 0:
        return True, None
    return False, (err or "").strip().splitlines()[:1]


def get_upstream(repo_path=None):
    """Return HEAD's upstream tracking ref, or None if it has none."""
    rc, out, _ = git(
        "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}",
        cwd=repo_path)
    if rc != 0:
        return None
    ref = out.strip()
    return ref if ref else None


def get_ahead_behind(repo_path=None, upstream=None):
    """Return (behind, ahead) commit counts relative to upstream.

    Returns (None, None) when there is no upstream, so callers can tell
    "no tracking branch" apart from "in sync" -- a distinction that
    matters, because a branch with no upstream can hold work that exists
    nowhere else.
    """
    if upstream is None:
        upstream = get_upstream(repo_path)
    if not upstream:
        return (None, None)
    rc, out, _ = git(
        "rev-list", "--left-right", "--count", f"{upstream}...HEAD",
        cwd=repo_path)
    if rc != 0:
        return (None, None)
    parts = out.split()
    if len(parts) != 2:
        return (None, None)
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return (None, None)


def get_status_counts(repo_path=None, churn_patterns=None):
    """Return {dirty_count, untracked_count, churn_count} from porcelain.

    dirty_count counts tracked paths with staged or unstaged changes;
    untracked_count counts '??' entries separately, because an untracked
    file is a much weaker signal than a modified tracked one.

    churn_patterns names files whose modifications are MACHINE-MADE
    (version files restamped by commit hooks): a tracked change whose
    path or basename fnmatches a pattern moves from dirty_count to
    churn_count, so a caller can distinguish "someone edited this repo"
    from "the tooling rewrote a stamp". With no patterns (the default)
    behavior is exactly as before -- dz git passes nothing and must not
    change output.

    The filename is only the GATE; content is the verdict. A matched
    file counts as churn only when its diff is a version restamp: at
    most two changed line-pairs, where each removed line equals its
    added counterpart once version-shaped tokens are masked -- "the
    same line, only the version moved". Format-agnostic on purpose:
    `__version__ = "..."` in Python, a bare `1.2.3` in a VERSION file,
    and `"version": "1.2.3",` in JSON all restamp the same way. A real
    edit that lives in a version file (new logic, a manual MAJOR/MINOR/
    PATCH bump, a deletion) fails the shape test and stays dirty.
    """
    import fnmatch
    counts = {"dirty_count": 0, "untracked_count": 0, "churn_count": 0}
    rc, out, _ = git("status", "--porcelain", cwd=repo_path)
    if rc != 0:
        return counts
    pats = [str(p).lower() for p in (churn_patterns or ()) if p]
    for line in out.splitlines():
        if not line.strip():
            continue
        if line.startswith("??"):
            counts["untracked_count"] += 1
            continue
        if pats:
            code = line[:2]
            path = line[3:].strip()
            if " -> " in path:          # rename: the destination is the file
                path = path.split(" -> ", 1)[1]
            raw = path.strip('"')
            p = raw.replace("\\", "/").lower()
            base = p.rsplit("/", 1)[-1]
            # Only plain modifications can be stamps; an added, deleted,
            # renamed, or conflicted version file is a decision, not churn.
            if (set(code) <= {"M", " "}
                    and any(fnmatch.fnmatch(p, q) or fnmatch.fnmatch(base, q)
                            for q in pats)
                    and _stamp_only_change(repo_path, raw)):
                counts["churn_count"] += 1
                continue
        counts["dirty_count"] += 1
    return counts


#: A version-shaped token: at least X.Y, with an optional prerelease /
#: build tail (0.4.0-alpha_main_5-20260224-0c11da0 is one token).
_VERSION_TOKEN = None  # compiled lazily


def _stamp_only_change(repo_path, rel_path):
    """True when the file's diff is a version restamp and nothing else.

    The test is structural, not syntactic, so it works for any file
    format: mask every version-shaped token in each changed line, then
    require the removed lines to equal the added lines -- the same line
    with only the version moved. Two extra tells bound it: at most two
    changed line-pairs (hooks restamp one or two lines; humans editing
    write more), and at least one version token must actually have been
    masked (a whitespace-only wiggle is not a restamp).

    Diffs against HEAD so staged and unstaged edits are judged together
    (a stamp that was `git add`ed is still a stamp). Every uncertainty
    -- no HEAD, unreadable diff, no textual change, pure addition or
    deletion -- answers False: misreading real work as churn is the
    failure this check exists to prevent, so doubt lands dirty.
    """
    global _VERSION_TOKEN
    if _VERSION_TOKEN is None:
        import re
        _VERSION_TOKEN = re.compile(r'\d+\.\d+[0-9A-Za-z._+\-]*')
    rc, out, _ = git("diff", "HEAD", "--", rel_path, cwd=repo_path)
    if rc != 0:
        return False
    minus, plus, masked = [], [], 0

    def norm(text):
        nonlocal masked
        replaced, n = _VERSION_TOKEN.subn("~V~", text.rstrip())
        masked += n
        return replaced

    for ln in out.splitlines():
        if ln.startswith(("+++", "---")):
            continue
        if ln[:1] == "-":
            minus.append(norm(ln[1:]))
        elif ln[:1] == "+":
            plus.append(norm(ln[1:]))
    if not minus or not plus or len(minus) > 2 or len(plus) > 2:
        return False
    if not masked:
        return False
    return sorted(minus) == sorted(plus)


# -- detection functions --

def detect_submodules(repo_root, repo_path=None):
    """Detect git submodules and their status.

    Returns list of dicts: [{type, path, url, branch, status}]
    """
    if repo_path is None:
        repo_path = repo_root

    gitmodules_path = os.path.join(repo_root, ".gitmodules")
    if not os.path.isfile(gitmodules_path):
        return []

    # Parse .gitmodules for path and url
    cp = configparser.ConfigParser()
    try:
        cp.read(gitmodules_path, encoding="utf-8")
    except (configparser.Error, OSError):
        return []

    modules = {}
    for section in cp.sections():
        path = cp[section].get("path")
        url = cp[section].get("url", "")
        branch = cp[section].get("branch", "")
        if path:
            modules[path] = {"url": url, "branch": branch}

    if not modules:
        return []

    # Get sync status from git submodule status
    rc, out, _ = git("submodule", "status", cwd=repo_path)
    status_map = {}
    if rc == 0:
        for line in out.strip().splitlines():
            if not line:
                continue
            # Format: "<prefix><hash> <path> (<describe>)"
            # prefix: ' '=synced, '+'=modified, '-'=uninitialized, 'U'=conflict
            # Note: some git versions/platforms omit the leading space for synced
            first = line[0]
            if first in (" ", "+", "-", "U"):
                prefix = first
                rest = line[1:]
            else:
                # No prefix character -- treat as synced
                prefix = " "
                rest = line
            tokens = rest.strip().split()
            if len(tokens) >= 2:
                path_part = tokens[1]
                if prefix == " ":
                    status_map[path_part] = "synced"
                elif prefix == "+":
                    status_map[path_part] = "modified"
                elif prefix == "-":
                    status_map[path_part] = "uninitialized"
                elif prefix == "U":
                    status_map[path_part] = "conflict"

    results = []
    for path, info in sorted(modules.items()):
        status = status_map.get(path, "unknown")
        results.append({
            "type": "submodule",
            "path": path,
            "url": info["url"],
            "branch": info["branch"],
            "status": status,
        })

    return results


def detect_subtrees(repo_root, repo_path=None):
    """Detect git subtrees from commit message trailers.

    Returns list of dicts: [{type, path}]
    """
    if repo_path is None:
        repo_path = repo_root

    # Grep commit messages for subtree markers -- limit to avoid slow scans
    rc, out, _ = git(
        "log", "--all", "--format=%B---END---",
        "--grep=git-subtree-dir:",
        "--max-count=500",
        cwd=repo_path,
    )
    if rc != 0 or not out.strip():
        return []

    # Extract unique subtree-dir paths
    paths = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("git-subtree-dir:"):
            path = line.split(":", 1)[1].strip()
            if path:
                paths.add(path)

    results = []
    for path in sorted(paths):
        results.append({
            "type": "subtree",
            "path": path,
            "url": "(from commit history)",
            "status": "tracked",
        })

    return results


def detect_worktrees(repo_path=None, current_path=None):
    """Detect git worktrees.

    Returns list of dicts: [{type, path, branch, status, head}]
    """
    rc, out, _ = git("worktree", "list", "--porcelain", cwd=repo_path)
    if rc != 0:
        return []

    results = []
    current = {}

    for line in out.splitlines():
        if line.startswith("worktree "):
            if current:
                results.append(current)
            path = line[9:].strip()
            current = {
                "type": "worktree",
                "path": os.path.normpath(path),
                "branch": "",
                "status": "",
                "head": "",
            }
        elif line == "bare":
            current["status"] = "bare"
        elif line.startswith("HEAD "):
            current["head"] = line[5:].strip()[:8]
        elif line.startswith("branch "):
            ref = line[7:].strip()
            # refs/heads/main -> main
            current["branch"] = ref.replace("refs/heads/", "")
            current["status"] = "active"
        elif line == "detached":
            current["status"] = "detached"
        elif line.startswith("prunable"):
            current["status"] = "prunable"

    if current:
        results.append(current)

    # Mark the current worktree. Defaults to process cwd, which preserves
    # the original CLI behavior exactly: invoking from a SUBDIRECTORY of a
    # worktree marks nothing, because the comparison is against cwd and not
    # against the worktree root. Callers scanning many repos pass this in.
    if current_path is None:
        current_path = os.getcwd()
    cwd = os.path.normpath(current_path)
    for wt in results:
        if os.path.normpath(wt["path"]) == cwd:
            wt["status"] += " *"

    return results


# -- form detection --

def detect_remotes(repo_path=None):
    """Detect git remotes with their fetch/push URLs.

    Returns list of dicts: [{name, fetch_url, push_url, slug}]
    """
    rc, out, _ = git("remote", "-v", cwd=repo_path)
    if rc != 0 or not out.strip():
        return []

    # Parse: "origin\thttps://github.com/Owner/Repo.git (fetch)"
    remotes = {}
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name = parts[0]
        url = parts[1]
        direction = parts[2].strip("()")

        if name not in remotes:
            remotes[name] = {"name": name, "fetch_url": "", "push_url": "", "slug": ""}
        if direction == "fetch":
            remotes[name]["fetch_url"] = url
        elif direction == "push":
            remotes[name]["push_url"] = url

    # Extract OWNER/REPO slug from URL
    for remote in remotes.values():
        url = remote["fetch_url"] or remote["push_url"]
        m = re.search(r'github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$', url)
        if m:
            remote["slug"] = m.group(1)

    return list(remotes.values())


def detect_form(repo_path=None):
    """Detect repo form characteristics.

    Returns dict of form flags.
    """
    form = {}

    # Bare
    rc, out, _ = git("rev-parse", "--is-bare-repository", cwd=repo_path)
    form["bare"] = out.strip() == "true" if rc == 0 else False

    # Shallow
    rc, out, _ = git("rev-parse", "--is-shallow-repository", cwd=repo_path)
    form["shallow"] = out.strip() == "true" if rc == 0 else False

    # Mirror
    rc, out, _ = git("config", "--get", "remote.origin.fetch", cwd=repo_path)
    form["mirror"] = "+refs/*:refs/*" in out if rc == 0 else False

    # Partial clone
    rc, out, _ = git(
        "config", "--get", "remote.origin.promisor", cwd=repo_path)
    form["partial_clone"] = out.strip() == "true" if rc == 0 else False

    rc, out, _ = git(
        "config", "--get", "remote.origin.partialclonefilter", cwd=repo_path)
    form["partial_filter"] = out.strip() if rc == 0 and out.strip() else None

    return form


def detect_stashes(repo_path=None):
    """Count stash entries."""
    rc, out, _ = git("stash", "list", cwd=repo_path)
    if rc != 0 or not out.strip():
        return 0
    return len(out.strip().splitlines())


def detect_stash_entries(repo_path=None):
    """Return stash entries as [{ref, message}].

    New here, not moved: dz git had this inline in cmd_workspace. Lifted
    so a multi-repo scan can report stash contents without duplicating
    the parse. Returns [] when there are no stashes, which matches the
    caller's previous short-circuit on a zero count.
    """
    stashes = []
    rc, out, _ = git("stash", "list", "--format=%gd|%s", cwd=repo_path)
    if rc != 0:
        return stashes
    for line in out.strip().splitlines():
        if not line:
            continue
        parts = line.split("|", 1)
        stashes.append({
            "ref": parts[0] if parts else "",
            "message": parts[1] if len(parts) > 1 else "",
        })
    return stashes


def detect_sparse_checkout(repo_path=None):
    """Check if sparse checkout is active."""
    rc, out, _ = git("sparse-checkout", "list", cwd=repo_path)
    return rc == 0


# -- output formatting --

def format_table(rows, headers):
    """Format rows as an aligned table."""
    if not rows:
        return ""

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Build output
    lines = []
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    lines.append(header_line)
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        line = "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
        lines.append(line)

    return "\n".join(lines)


def describe_form(form):
    """Return a human-readable form description."""
    flags = []
    if form.get("bare"):
        flags.append("bare")
    if form.get("shallow"):
        flags.append("shallow")
    if form.get("mirror"):
        flags.append("mirror")
    if form.get("partial_clone"):
        f = form.get("partial_filter", "")
        flags.append(f"partial clone ({f})" if f else "partial clone")

    return ", ".join(flags) if flags else "normal clone"
