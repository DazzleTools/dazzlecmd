"""dz github -- open GitHub project pages, issues, and releases from any git repo.

Auto-detects the GitHub remote from the current git repo so you never
need to run `gh repo set-default`. Wraps `gh` CLI where possible and
fills gaps with direct URL construction.

Resolving which project you mean:
    1. the repo you are standing in, if it has a GitHub remote
    2. otherwise the nearest enclosing repo that has one -- so commands
       still work from inside a remote-less nested repo such as the
       `private/` notes store, and the resolved project is announced
    3. otherwise, when cwd is not a repo at all, immediate subdirectories
       are scanned for one

Subcommands / targets:
    (bare)      Open repo home page
    <number>    Open issue or PR by number
    <repo>#<N>  Issue N in another repo -- GitHub's cross-reference
                notation, made typeable. The repo part is a bare name
                resolved through your orgs, or OWNER/REPO verbatim; the
                part after '#' takes the whole issue grammar (a number,
                a keyword like 'roadmap', or nothing for the issues
                tab). Bare '#N' means this project's issue N.
    isu         Issue lookup (by number, label, or title search)
    issues      Open issues tab
    pr          Open pull requests tab
    release     Open releases tab
    forks       Open forks / network page
    projects    Open GitHub Projects (kanban)
    actions     Open Actions tab
    wiki        Open wiki
    settings    Open settings
"""

import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Add projects/dazzletools/ to sys.path so _repo_common (sibling dir) imports.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from _repo_common.gh_identity import is_repo_slug, parse_slug  # noqa: E402


# Cache settings
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "dz-github")
CACHE_FILE = os.path.join(CACHE_DIR, "repos.json")
CACHE_TTL = 86400  # 24 hours in seconds


# -- helpers --

def run_cmd(cmd, *args, cwd=None):
    """Run a command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [cmd] + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
    )
    return result.returncode, result.stdout, result.stderr


def safe_stderr(text):
    """Sanitize text for Windows console output.

    Replaces non-ASCII characters (em dashes, smart quotes, etc.) with
    safe ASCII equivalents to avoid mojibake on codepage 437/1252.
    """
    replacements = {
        "\u2014": "--",   # em dash
        "\u2013": "-",    # en dash
        "\u2018": "'",    # left single quote
        "\u2019": "'",    # right single quote
        "\u201c": '"',    # left double quote
        "\u201d": '"',    # right double quote
        "\u2026": "...",  # ellipsis
        "\u2192": "->",   # right arrow
        "\u2190": "<-",   # left arrow
        "\u2713": "[OK]", # checkmark
        "\u2717": "[X]",  # ballot x
        "\u274c": "[X]",  # cross mark
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    # Fallback: replace any remaining non-ASCII with '?'
    try:
        text.encode(sys.stderr.encoding or "utf-8")
    except (UnicodeEncodeError, LookupError):
        text = text.encode("ascii", errors="replace").decode("ascii")
    return text


def git(*args):
    """Run a git command."""
    return run_cmd("git", *args)


def gh(*args):
    """Run a gh command."""
    return run_cmd("gh", *args)


def check_gh():
    """Check if gh CLI is available."""
    rc, _, _ = run_cmd("gh", "--version")
    if rc != 0:
        print("Error: 'gh' (GitHub CLI) is not installed or not in PATH.",
              file=sys.stderr)
        print("Install: https://cli.github.com/", file=sys.stderr)
        return False
    return True


def get_repo_slug(remote="origin"):
    """Parse OWNER/REPO from a git remote URL.

    Handles HTTPS, SSH, and ssh:// formats:
        https://github.com/Owner/Repo.git
        git@github.com:Owner/Repo.git
        ssh://git@github.com/Owner/Repo.git
    """
    rc, out, err = git("remote", "get-url", remote)
    if rc != 0:
        return None
    return parse_slug(out.strip())


def get_base_url(slug):
    """Build the base GitHub URL for a repo slug."""
    return f"https://github.com/{slug}"


def open_url(url, no_browser=False):
    """Open a URL in the browser, or print it if --no-browser."""
    if no_browser:
        print(url)
    else:
        webbrowser.open(url)
    return 0


def gh_browse(slug, *extra_args, no_browser=False):
    """Delegate to gh browse with -R OWNER/REPO.

    Uses gh for browser opening (handles auth, cross-platform).
    """
    cmd_args = ["browse", "-R", slug]
    if no_browser:
        cmd_args.append("-n")
    cmd_args.extend(extra_args)
    rc, out, err = gh(*cmd_args)
    if rc != 0:
        # If gh browse fails, fall back to webbrowser
        if no_browser:
            print(err.strip(), file=sys.stderr)
            return rc
        base = get_base_url(slug)
        return open_url(base, no_browser)
    if no_browser and out.strip():
        print(out.strip())
    return 0


# -- subdirectory scanning --

def scan_subdirs_for_repo(remote="origin"):
    """Scan immediate subdirectories for git repos with GitHub remotes.

    When run from a parent directory (e.g., C:\\code\\dazzlecmd) that isn't
    itself a git repo, checks each child directory for a .git folder and
    tries to extract a GitHub slug. If exactly one is found, uses it
    automatically. If multiple are found, prompts the user to choose.

    Returns a slug (OWNER/REPO) or None.
    """
    cwd = os.getcwd()
    found = []  # list of (dirname, slug)

    try:
        entries = sorted(os.listdir(cwd))
    except OSError:
        print("Error: not inside a git repository.", file=sys.stderr)
        return None

    for entry in entries:
        subdir = os.path.join(cwd, entry)
        if not os.path.isdir(subdir):
            continue
        git_dir = os.path.join(subdir, ".git")
        if not os.path.exists(git_dir):
            continue
        # Try to get a GitHub slug from this repo
        rc, out, _ = run_cmd("git", "remote", "get-url", remote, cwd=subdir)
        if rc != 0:
            continue
        slug = parse_slug(out.strip())
        if slug:
            found.append((entry, slug))

    if not found:
        print("Error: not inside a git repository.", file=sys.stderr)
        print(f"  (scanned {len(entries)} subdirectories, "
              f"no GitHub repos found)", file=sys.stderr)
        return None

    if len(found) == 1:
        dirname, slug = found[0]
        print(f"  Found: {slug} (in ./{dirname}/)", file=sys.stderr)
        return slug

    # Deduplicate: if all repos point to the same slug, no ambiguity
    unique_slugs = set(slug for _, slug in found)
    if len(unique_slugs) == 1:
        slug = unique_slugs.pop()
        dirs = ", ".join(f"./{d}/" for d, _ in found)
        print(f"  Found: {slug} (in {dirs})", file=sys.stderr)
        return slug

    # Multiple distinct repos found -- prompt user
    print(f"Found {len(found)} GitHub repos in subdirectories:",
          file=sys.stderr)
    for i, (dirname, slug) in enumerate(found, 1):
        print(f"  {i}) {slug}  (./{dirname}/)", file=sys.stderr)

    try:
        # Prompt to stderr, not via input()'s stdout-bound argument (#119)
        print("Which repo? [1-{}]: ".format(len(found)), end="",
              file=sys.stderr, flush=True)
        choice = input()
        idx = int(choice) - 1
        if 0 <= idx < len(found):
            return found[idx][1]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass

    print("Cancelled.", file=sys.stderr)
    return None


# -- ancestor scanning --

def scan_ancestors_for_repo(start=None, remote="origin", max_levels=10):
    """Walk UP for an enclosing git repo that has a GitHub remote.

    The counterpart to scan_subdirs_for_repo(), which searches downward
    when cwd is not a repo at all. This covers the mirror case: cwd IS
    inside a repo, but that repo yields no GitHub slug. The common cause
    is the `private/` convention -- a project's notes store is its own
    repo with no remotes by design, so the answer lives one repo up.

    Delegates the upward search to git itself (`rev-parse --show-toplevel`
    from each parent) rather than looking for `.git` markers by hand, so
    `.git`-as-a-file layouts (worktrees, submodules) resolve correctly and
    non-repo directories in between are skipped in a single step.

    A remote-less repo is not an error here -- it just means keep looking.

    Returns (slug, repo_root) for the nearest qualifying ancestor, or
    (None, None) when there is none.
    """
    rc, out, _ = run_cmd("git", "rev-parse", "--show-toplevel",
                         cwd=start or os.getcwd())
    if rc != 0 or not out.strip():
        return None, None
    current = os.path.abspath(out.strip())

    for _ in range(max_levels):
        parent = os.path.dirname(current)
        if not parent or parent == current or not os.path.isdir(parent):
            return None, None  # filesystem root, or nowhere left to go

        rc, out, _ = run_cmd("git", "rev-parse", "--show-toplevel", cwd=parent)
        if rc != 0 or not out.strip():
            return None, None  # no enclosing repo above this one
        ancestor = os.path.abspath(out.strip())
        if ancestor == current:
            return None, None  # no upward progress; refuse to spin

        rc, out, _ = run_cmd("git", "remote", "get-url", remote, cwd=ancestor)
        if rc == 0:
            slug = parse_slug(out.strip())
            if slug:
                return slug, ancestor

        current = ancestor

    return None, None


def resolve_via_ancestor(remote="origin"):
    """Try the ancestor walk and announce the result. Returns a slug or None.

    Announcing matters: the user asked about "here", and we answered about
    a different directory, so the resolved project is named explicitly.
    """
    slug, root = scan_ancestors_for_repo(remote=remote)
    if slug:
        print(safe_stderr(f"  Resolved via parent repo: {slug} ({root})"),
              file=sys.stderr)
    return slug


# -- issue resolution --

# Semantic aliases: keyword -> list of labels to try (in order)
LABEL_ALIASES = {
    "roadmap": ["roadmap"],
    "notes": ["notes", "ideas"],
    "ideas": ["ideas", "notes"],
}

# Keywords that open a label-filtered browser view (multi-issue)
MULTI_ISSUE_KEYWORDS = {
    "epics": "epic",
    "epic": "epic",
    "bugs": "bug",
}


def resolve_issue(slug, keyword):
    """Resolve a keyword to an issue number.

    Resolution order:
    1. Label match (try each label alias in order)
    2. Title search fallback
    Returns (issue_number, title) or (None, None).
    """
    labels_to_try = LABEL_ALIASES.get(keyword, [keyword])

    # 1. Try label matches
    for label in labels_to_try:
        rc, out, _ = gh(
            "issue", "list", "-R", slug,
            "-l", label,
            "--json", "number,title",
            "-L", "5",
            "--state", "all",
        )
        if rc == 0 and out.strip():
            try:
                issues = json.loads(out)
                if issues:
                    # Return lowest number (oldest/canonical)
                    issues.sort(key=lambda i: i["number"])
                    return issues[0]["number"], issues[0]["title"]
            except (json.JSONDecodeError, KeyError):
                pass

    # 2. Title search fallback
    rc, out, _ = gh(
        "issue", "list", "-R", slug,
        "--search", f"{keyword} in:title",
        "--json", "number,title",
        "-L", "5",
        "--state", "all",
    )
    if rc == 0 and out.strip():
        try:
            issues = json.loads(out)
            if issues:
                issues.sort(key=lambda i: i["number"])
                best = issues[0]
                if len(issues) > 1:
                    others = ", ".join(f"#{i['number']}" for i in issues[1:])
                    print(safe_stderr(f"  (also matched: {others})"),
                          file=sys.stderr)
                return best["number"], best["title"]
        except (json.JSONDecodeError, KeyError):
            pass

    return None, None


# -- command handlers --

def cmd_open(slug, no_browser):
    """Open repo home page."""
    return gh_browse(slug, no_browser=no_browser)


def cmd_number(slug, number, no_browser):
    """Open issue or PR by number."""
    return gh_browse(slug, str(number), no_browser=no_browser)


def cmd_isu(slug, target, no_browser):
    """Issue subcommand: open by number, label, or keyword."""
    if not target:
        # Bare 'dz github isu' -> open issues tab
        return open_url(f"{get_base_url(slug)}/issues", no_browser)

    # If target is a number, open directly
    if target.isdigit():
        return cmd_number(slug, int(target), no_browser)

    # Check multi-issue keywords (open filtered view, not single issue)
    if target in MULTI_ISSUE_KEYWORDS:
        label = MULTI_ISSUE_KEYWORDS[target]
        url = f"{get_base_url(slug)}/issues?q=is%3Aopen+label%3A{label}"
        return open_url(url, no_browser)

    # Resolve semantic alias / keyword
    number, title = resolve_issue(slug, target)
    if number is not None:
        print(safe_stderr(f"  #{number}: {title}"), file=sys.stderr)
        return gh_browse(slug, str(number), no_browser=no_browser)

    print(f"No issues found matching '{target}'.", file=sys.stderr)
    return 1


# -- repo cache --

def _load_cache():
    """Load the repo cache from disk. Returns (repos_list, is_fresh)."""
    if not os.path.isfile(CACHE_FILE):
        return [], False
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        age = time.time() - data.get("updated", 0)
        repos = data.get("repos", [])
        return repos, age < CACHE_TTL
    except (json.JSONDecodeError, OSError, KeyError):
        return [], False


def _save_cache(repos):
    """Save the repo list to the cache file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    data = {"updated": time.time(), "repos": repos}
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass  # cache write failure is non-fatal


def _fetch_all_repos():
    """Fetch all repos from the user's account and orgs via gh."""
    owners = _get_user_owners()
    all_repos = []
    seen = set()

    for owner in owners:
        rc, out, _ = gh(
            "repo", "list", owner,
            "--json", "name,nameWithOwner,description,url",
            "-L", "200",
        )
        if rc == 0 and out.strip():
            try:
                repos = json.loads(out)
                for r in repos:
                    full = r["nameWithOwner"]
                    if full not in seen:
                        seen.add(full)
                        all_repos.append({
                            "name": r["name"],
                            "fullName": full,
                            "description": r.get("description", "") or "",
                            "url": r["url"],
                        })
            except json.JSONDecodeError:
                pass

    _save_cache(all_repos)
    return all_repos


def _search_cache(name, repos):
    """Filter cached repos by substring match on name. Returns matches."""
    name_lower = name.lower()
    return [r for r in repos if name_lower in r["name"].lower()]


def cmd_repo(name, no_browser, force_refresh=False):
    """Find a repo by name across the user's orgs and open it.

    Uses a local cache (~/.cache/dz-github/repos.json) for instant
    lookups. Falls back to API if not found in cache, and refreshes
    the cache when stale (>24h) or on --refresh.
    """
    if not name:
        print("Usage: dz github repo <name>", file=sys.stderr)
        return 1

    # If it already looks like OWNER/REPO, open directly
    if "/" in name:
        return open_url(f"https://github.com/{name}", no_browser)

    # 1. Try cache first
    cached_repos, is_fresh = _load_cache()
    if cached_repos and not force_refresh:
        found = _search_cache(name, cached_repos)
        if found:
            return _pick_repo(name, found, no_browser)
        # Not in cache -- if cache is fresh, it's genuinely missing from
        # our orgs. Try a global search as last resort.
        if is_fresh:
            return _global_search_fallback(name, no_browser)

    # 2. Cache miss or stale -- refresh from API
    print("  Updating repo cache...", file=sys.stderr)
    all_repos = _fetch_all_repos()
    found = _search_cache(name, all_repos)
    if found:
        return _pick_repo(name, found, no_browser)

    # 3. Not in our orgs at all -- try global search
    return _global_search_fallback(name, no_browser)


def _global_search_fallback(name, no_browser):
    """Last resort: search all of GitHub for a repo name."""
    rc, out, _ = gh(
        "search", "repos", name,
        "--json", "fullName,description,url",
        "-L", "10",
    )
    if rc == 0 and out.strip():
        try:
            results = json.loads(out)
            if results:
                # Add 'name' field for consistency
                for r in results:
                    if "name" not in r:
                        r["name"] = r["fullName"].split("/")[1]
                return _pick_repo(name, results, no_browser)
        except json.JSONDecodeError:
            pass

    print(f"No repos found matching '{name}'.", file=sys.stderr)
    return 1


def _pick_candidate(name, found):
    """Select one repo from matches: exact-first auto-select, else prompt.

    Returns the chosen repo dict, or None on cancel. The selection rules
    are the ones the repo finder has always used; they live here so that
    resolution-to-a-slug (issue refs) and resolution-to-an-open (cmd_repo)
    share one behavior instead of drifting apart.
    """
    name_lower = name.lower()

    # Sort: exact name matches first, then by name length
    exact = [r for r in found if r.get("name", "").lower() == name_lower]
    rest = [r for r in found if r not in exact]
    rest.sort(key=lambda r: len(r.get("name", r["fullName"])))
    candidates = exact + rest

    # Single result or single exact match -- auto-select
    if len(candidates) == 1 or len(exact) == 1:
        repo = candidates[0]
        print(safe_stderr(f"  {repo['fullName']}"), file=sys.stderr)
        return repo

    # Multiple results -- prompt
    print(f"Found {len(candidates)} repos matching '{name}':",
          file=sys.stderr)
    for i, repo in enumerate(candidates, 1):
        desc = repo.get("description", "") or ""
        if len(desc) > 50:
            desc = desc[:47] + "..."
        print(safe_stderr(f"  {i}) {repo['fullName']:40s}  {desc}"),
              file=sys.stderr)

    try:
        # The prompt goes to stderr explicitly: input()'s own prompt
        # argument prints to STDOUT, which is the one stream this tool
        # keeps pure for -n piping -- a prompted resolution was gluing
        # "Which repo? [1-N]:" onto the front of the captured URL (#119).
        print(f"Which repo? [1-{len(candidates)}]: ", end="",
              file=sys.stderr, flush=True)
        choice = input()
        idx = int(choice) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx]
    except (ValueError, EOFError, KeyboardInterrupt, OSError):
        # OSError: stdin closed or captured (pipes, test harnesses) --
        # the same "cannot ask" condition as EOF.
        pass

    print("Cancelled.", file=sys.stderr)
    return None


def _pick_repo(name, found, no_browser):
    """Given a list of matching repos, pick one and open it."""
    repo = _pick_candidate(name, found)
    if repo is None:
        return 1
    return open_url(repo["url"], no_browser)


def resolve_repo_name(name, refresh=False):
    """Resolve a bare repo name to an OWNER/REPO slug via the user's orgs.

    The resolution half of cmd_repo(), without the open: cache first,
    refresh on staleness, exact-match auto-select, prompt on ambiguity.

    Deliberately NO global-GitHub fallback, unlike cmd_repo(): this
    exists for issue jumps, where a typo'd name resolving to a
    stranger's repo would open THEIR issue N -- an answer that looks
    legitimate. Wrong-but-plausible is worse than no-answer here, so a
    miss returns None and the caller points at OWNER/REPO as the
    explicit escape.

    Returns a slug, or None (not found in your orgs, or prompt
    cancelled).
    """
    if not name:
        return None

    # Already OWNER/REPO -- nothing to resolve. Shape-checked first:
    # gh reads a three-segment "a/b/c" as HOST/OWNER/REPO and blames
    # the network for what is actually a malformed reference (#120).
    if "/" in name:
        candidate = name.strip()
        if is_repo_slug(candidate):
            return candidate
        print(f"'{name}' is not an OWNER/REPO reference.", file=sys.stderr)
        return None

    cached_repos, is_fresh = _load_cache()
    if cached_repos and not refresh:
        found = _search_cache(name, cached_repos)
        if found:
            repo = _pick_candidate(name, found)
            return repo["fullName"] if repo else None
        if is_fresh:
            print(f"No repo matching '{name}' in your orgs.", file=sys.stderr)
            return None

    # Cache miss or stale -- refresh from API
    print("  Updating repo cache...", file=sys.stderr)
    all_repos = _fetch_all_repos()
    found = _search_cache(name, all_repos)
    if found:
        repo = _pick_candidate(name, found)
        return repo["fullName"] if repo else None

    print(f"No repo matching '{name}' in your orgs.", file=sys.stderr)
    return None


def _get_user_owners():
    """Get the authenticated user's login + org logins for scoped search."""
    owners = []

    # Get username
    rc, out, _ = gh("api", "user", "--jq", ".login")
    if rc == 0 and out.strip():
        owners.append(out.strip())

    # Get orgs
    rc, out, _ = gh("api", "user/orgs", "--jq", ".[].login")
    if rc == 0 and out.strip():
        owners.extend(out.strip().splitlines())

    return owners


def cmd_issues(slug, no_browser):
    """Open issues tab."""
    return open_url(f"{get_base_url(slug)}/issues", no_browser)


def cmd_pr(slug, no_browser):
    """Open pull requests tab."""
    return open_url(f"{get_base_url(slug)}/pulls", no_browser)


def cmd_release(slug, no_browser):
    """Open releases page."""
    return gh_browse(slug, "--releases", no_browser=no_browser)


def cmd_forks(slug, no_browser):
    """Open network/forks page."""
    return open_url(f"{get_base_url(slug)}/forks", no_browser)


def cmd_projects(slug, no_browser):
    """Open GitHub Projects tab."""
    return gh_browse(slug, "--projects", no_browser=no_browser)


def cmd_actions(slug, no_browser):
    """Open Actions tab."""
    return open_url(f"{get_base_url(slug)}/actions", no_browser)


def cmd_wiki(slug, no_browser):
    """Open wiki."""
    return gh_browse(slug, "--wiki", no_browser=no_browser)


def cmd_settings(slug, no_browser):
    """Open settings."""
    return gh_browse(slug, "--settings", no_browser=no_browser)


# -- page keyword routing --

PAGE_COMMANDS = {
    "issues": cmd_issues,
    "pr": cmd_pr,
    "prs": cmd_pr,
    "pull": cmd_pr,
    "pulls": cmd_pr,
    "release": cmd_release,
    "releases": cmd_release,
    "forks": cmd_forks,
    "fork": cmd_forks,
    "network": cmd_forks,
    "projects": cmd_projects,
    "project": cmd_projects,
    "kanban": cmd_projects,
    "actions": cmd_actions,
    "ci": cmd_actions,
    "wiki": cmd_wiki,
    "settings": cmd_settings,
}


def _split_issue_ref(target):
    """Split a '<repo>#<issue>' reference. Returns (repo_part, issue_part).

    GitHub's own cross-reference notation, made typeable: the part before
    the first '#' names a repository (bare name, or OWNER/REPO), the part
    after is anything the issue grammar accepts -- a number, a semantic
    keyword like 'roadmap', or nothing (that repo's issues tab). Either
    side may be empty: '#112' means "issue 112 of the project I'm
    standing in".

    Returns None when target carries no '#' at all -- i.e. this is not
    an issue reference and the ordinary target grammar applies.
    """
    if not target or "#" not in target:
        return None
    repo_part, issue_part = target.split("#", 1)
    return repo_part.strip(), issue_part.strip()


def _looks_like_repo_name(target):
    """True when a bare target should be read as a repo name to look up.

    `dz github <name>` is the implicit repo finder, so an unrecognized word
    means "find that repo". Page keywords, `isu`, and `.` are commands, not
    names. An all-digits target is an ISSUE NUMBER: searching GitHub for a
    repo called "61" returns noise (b612, CS61A, ud615) and never what was
    meant, so digits are never treated as a name. A target containing '#'
    is an issue REFERENCE -- GitHub forbids '#' in repository names, so it
    cannot be one.
    """
    if not target:
        return False
    if target in PAGE_COMMANDS or target in ("isu", "."):
        return False
    if "#" in target:
        return False
    return not target.isdigit()


# -- parser and main --

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="dz github",
        description="Open GitHub project pages, issues, and releases from any git repo.",
        epilog=(
            "examples:\n"
            "  dz github                        Open repo home page\n"
            "  dz github 3                      Open issue or PR #3\n"
            "  dz github isu roadmap            Find and open the roadmap issue\n"
            "  dz github isu epics              Open epic-labeled issues\n"
            "  dz github pr                     Open pull requests tab\n"
            "  dz github release                Open releases page\n"
            "  dz github repo git-repokit       Find and open a repo by name\n"
            "  dz github dazzlecmd#112          Issue 112 in ANOTHER repo, from anywhere\n"
            "  dz github OWNER/REPO#7           Same, naming the owner exactly\n"
            "  dz github dazzlecmd#roadmap      Semantic issue lookup in another repo\n"
            "  dz github \"#112\"                 This project's issue 112 (quote it --\n"
            "                                   bare '#' starts a shell comment)\n"
            "  dz github -n isu 3               Print issue URL without opening\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-n", "--no-browser",
        action="store_true",
        help="Print URL instead of opening browser",
    )
    parser.add_argument(
        "--remote",
        default="origin",
        help="Git remote to use (default: origin)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force refresh the repo cache",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Page, issue number, or subcommand (isu, pr, release, ...)",
    )
    parser.add_argument(
        "target_args",
        nargs="*",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv=None):
    """Entry point for dz github."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    # Check gh availability
    if not check_gh():
        return 1

    refresh = args.refresh

    # 'repo' subcommand doesn't need cwd detection -- handle early
    if args.target == "repo":
        repo_name = args.target_args[0] if args.target_args else None
        return cmd_repo(repo_name, args.no_browser, force_refresh=refresh)

    # '<repo>#<issue>' -- a cross-repo issue reference. Claimed before cwd
    # detection for the same reason 'repo' is: a target that names its own
    # repository needs no cwd, and the whole point is jumping to another
    # project's issue from wherever you happen to be standing.
    from_issue_ref = False
    issue_ref = _split_issue_ref(args.target)
    if issue_ref:
        repo_part, issue_part = issue_ref
        if repo_part:
            ref_slug = resolve_repo_name(repo_part, refresh=refresh)
            if not ref_slug:
                print(f"Tip: use OWNER/REPO#{issue_part or 'N'} to name "
                      f"the repository exactly.", file=sys.stderr)
                return 1
            # Everything after '#' is the existing issue grammar: a
            # number, a semantic keyword, or nothing (issues tab).
            return cmd_isu(ref_slug, issue_part or None, args.no_browser)
        # Bare '#N' -- the current project's issue. Fall through to the
        # normal slug resolution (cwd -> ancestor -> subdir scan) with
        # just the issue part; the flag records that '#' already declared
        # this an issue, so nothing downstream may re-read it as a page
        # or a repo name.
        from_issue_ref = True
        args.target = issue_part

    # --refresh with no target: just refresh the cache
    if refresh and args.target is None:
        print("  Refreshing repo cache...", file=sys.stderr)
        repos = _fetch_all_repos()
        print(f"  Cached {len(repos)} repos.", file=sys.stderr)
        return 0

    # Detect repo from cwd
    slug = get_repo_slug(args.remote)
    if not slug:
        # Check if we're even in a git repo
        rc, _, _ = git("rev-parse", "--show-toplevel")
        if rc != 0:
            # Not in a git repo -- a bare name means "find that repo"
            # (unless '#' already declared the target an issue)
            if not from_issue_ref and _looks_like_repo_name(args.target):
                return cmd_repo(args.target, args.no_browser, force_refresh=refresh)
            # Otherwise scan subdirectories for repos
            slug = scan_subdirs_for_repo(args.remote)
            if not slug:
                return 1
        else:
            # The repo we are standing in has no GitHub identity of its own.
            # Under the `private/` convention that is by design, and the
            # project it belongs to is the next repo up.
            #
            # Resolve BEFORE classifying the target. Once a parent project is
            # found we are, for every purpose, standing in it -- so a target
            # has to mean there what it means at the project root. Deciding
            # "this word looks like a repo name" first is what made
            # `dz github roadmap` open issue #1 from the project root and run
            # a GitHub-wide search for repositories called "roadmap" one
            # directory down in private/.
            slug = resolve_via_ancestor(args.remote)
            if not slug:
                # Nothing encloses us, so there is no project for a bare word
                # to refer to -- fall back to reading it as a repo name
                # (unless '#' already declared the target an issue).
                if not from_issue_ref and _looks_like_repo_name(args.target):
                    return cmd_repo(args.target, args.no_browser,
                                    force_refresh=refresh)
                print(f"Error: remote '{args.remote}' is not a GitHub URL "
                      f"(or remote not found), and no enclosing repo has one "
                      f"either.", file=sys.stderr)
                print("Tip: use --remote <name> to specify a different remote.",
                      file=sys.stderr)
                return 1

    no_browser = args.no_browser
    target = args.target

    # A bare '#...' said "issue" -- dispatch the remainder through the
    # issue grammar and nothing else. Placed first so an empty remainder
    # ('#' alone -> this repo's issues tab) is not mistaken for no target.
    if from_issue_ref:
        return cmd_isu(slug, target or None, no_browser)

    # No target, or '.' (explicit "this repo") -> open repo home
    if target is None or target == ".":
        return cmd_open(slug, no_browser)

    # Number -> open issue/PR directly
    if target.isdigit():
        return cmd_number(slug, int(target), no_browser)

    # 'isu' subcommand
    if target == "isu":
        isu_target = args.target_args[0] if args.target_args else None
        return cmd_isu(slug, isu_target, no_browser)

    # Known page keywords
    if target in PAGE_COMMANDS:
        return PAGE_COMMANDS[target](slug, no_browser)

    # Unknown target -- try as issue keyword (be helpful)
    print(f"Unknown target '{target}'. Trying as issue keyword...",
          file=sys.stderr)
    return cmd_isu(slug, target, no_browser)


if __name__ == "__main__":
    sys.exit(main())
