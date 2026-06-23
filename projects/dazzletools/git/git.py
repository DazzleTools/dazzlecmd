"""dz git -- git repo state inspector.

Answers questions about repo composition, workspace layout, and form
using quick subcommands instead of verbose git commands.

Subcommands:
    (bare)          Quick summary: branch, composition counts, form
    composition     Detailed table of submodules, subtrees, worktrees
    workspace       Worktrees, sparse checkout, stashes, detached HEAD
    form            Repo form: bare, shallow, mirror, partial clone, fork
"""

import argparse
import configparser
import json
import os
import re
import subprocess
import sys


# -- verbosity --

# Global verbosity level, set by main() from -v flags
VERBOSITY = 0


def vprint(level, text, file=None):
    """Print only if verbosity >= level."""
    if VERBOSITY >= level:
        safe_print(text, file=file)


def show_cmd(cmd_parts):
    """At -vv+, print the git command being run."""
    if VERBOSITY >= 2:
        safe_print(f"  $ {' '.join(cmd_parts)}", file=sys.stderr)


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


def git(*args, cwd=None):
    """Run a git command."""
    show_cmd(["git"] + list(args))
    rc, out, err = run_cmd("git", *args, cwd=cwd)
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


def find_repo_root():
    """Find the git repo root from cwd, scanning subdirectories if needed."""
    rc, out, _ = git("rev-parse", "--show-toplevel")
    if rc == 0:
        return out.strip()

    # Not in a git repo -- scan child directories
    chosen = _scan_subdirs_for_repo()
    if chosen:
        # chdir so subsequent git commands operate on the found repo
        os.chdir(chosen)
        return chosen

    print("Error: not inside a git repository.", file=sys.stderr)
    sys.exit(1)


def _scan_subdirs_for_repo():
    """Scan immediate subdirectories for git repos.

    Auto-selects if one repo or all point to the same root.
    Prompts if multiple distinct repos found.
    Returns repo root path or None.
    """
    cwd = os.getcwd()
    found = []  # list of (dirname, repo_root)

    try:
        entries = sorted(os.listdir(cwd))
    except OSError:
        return None

    for entry in entries:
        subdir = os.path.join(cwd, entry)
        if not os.path.isdir(subdir):
            continue
        git_marker = os.path.join(subdir, ".git")
        if not os.path.exists(git_marker):
            continue
        # Get the repo root (might differ from subdir for worktrees)
        rc, out, _ = git("rev-parse", "--show-toplevel", cwd=subdir)
        if rc == 0:
            root = out.strip()
            found.append((entry, root))

    if not found:
        return None

    # Deduplicate by repo root
    unique_roots = set(root for _, root in found)

    if len(unique_roots) == 1:
        root = unique_roots.pop()
        dirs = ", ".join(f"./{d}/" for d, _ in found)
        print(f"  Found repo in: {dirs}", file=sys.stderr)
        return root

    # Multiple distinct repos -- prompt
    # Group by root for display
    by_root = {}
    for dirname, root in found:
        by_root.setdefault(root, []).append(dirname)

    items = sorted(by_root.items())
    print(f"Found {len(items)} repos in subdirectories:", file=sys.stderr)
    for i, (root, dirs) in enumerate(items, 1):
        dir_list = ", ".join(f"./{d}/" for d in dirs)
        print(f"  {i}) {os.path.basename(root)}  ({dir_list})", file=sys.stderr)

    try:
        choice = input(f"Which repo? [1-{len(items)}]: ")
        idx = int(choice) - 1
        if 0 <= idx < len(items):
            return items[idx][0]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass

    print("Cancelled.", file=sys.stderr)
    return None


def get_branch():
    """Get current branch name, or None if detached."""
    rc, out, _ = git("branch", "--show-current")
    if rc != 0:
        return None
    branch = out.strip()
    return branch if branch else None


def get_head_short():
    """Get short HEAD hash."""
    rc, out, _ = git("rev-parse", "--short", "HEAD")
    return out.strip() if rc == 0 else "unknown"


# -- detection functions --

def detect_submodules(repo_root):
    """Detect git submodules and their status.

    Returns list of dicts: [{type, path, url, branch, status}]
    """
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
    rc, out, _ = git("submodule", "status")
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


def detect_subtrees(repo_root):
    """Detect git subtrees from commit message trailers.

    Returns list of dicts: [{type, path}]
    """
    # Grep commit messages for subtree markers -- limit to avoid slow scans
    rc, out, _ = git(
        "log", "--all", "--format=%B---END---",
        "--grep=git-subtree-dir:",
        "--max-count=500",
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


def detect_worktrees():
    """Detect git worktrees.

    Returns list of dicts: [{type, path, branch, status, head}]
    """
    rc, out, _ = git("worktree", "list", "--porcelain")
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

    # Mark the current worktree
    cwd = os.path.normpath(os.getcwd())
    for wt in results:
        if os.path.normpath(wt["path"]) == cwd:
            wt["status"] += " *"

    return results


# -- form detection --

def detect_remotes():
    """Detect git remotes with their fetch/push URLs.

    Returns list of dicts: [{name, fetch_url, push_url, slug}]
    """
    rc, out, _ = git("remote", "-v")
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


def detect_form():
    """Detect repo form characteristics.

    Returns dict of form flags.
    """
    form = {}

    # Bare
    rc, out, _ = git("rev-parse", "--is-bare-repository")
    form["bare"] = out.strip() == "true" if rc == 0 else False

    # Shallow
    rc, out, _ = git("rev-parse", "--is-shallow-repository")
    form["shallow"] = out.strip() == "true" if rc == 0 else False

    # Mirror
    rc, out, _ = git("config", "--get", "remote.origin.fetch")
    form["mirror"] = "+refs/*:refs/*" in out if rc == 0 else False

    # Partial clone
    rc, out, _ = git("config", "--get", "remote.origin.promisor")
    form["partial_clone"] = out.strip() == "true" if rc == 0 else False

    rc, out, _ = git("config", "--get", "remote.origin.partialclonefilter")
    form["partial_filter"] = out.strip() if rc == 0 and out.strip() else None

    return form


def detect_stashes():
    """Count stash entries."""
    rc, out, _ = git("stash", "list")
    if rc != 0 or not out.strip():
        return 0
    return len(out.strip().splitlines())


def detect_sparse_checkout():
    """Check if sparse checkout is active."""
    rc, out, _ = git("sparse-checkout", "list")
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


# -- command handlers --

def cmd_info(json_output=False):
    """Default: show a quick summary of the repo."""
    repo_root = find_repo_root()

    branch = get_branch()
    head = get_head_short()
    branch_str = f"{branch} @ {head}" if branch else f"detached @ {head}"

    remotes = detect_remotes()
    submodules = detect_submodules(repo_root)
    subtrees = detect_subtrees(repo_root)
    worktrees = detect_worktrees()
    form = detect_form()
    stash_count = detect_stashes()
    sparse = detect_sparse_checkout()

    if json_output:
        data = {
            "branch": branch,
            "head": head,
            "detached": branch is None,
            "remotes": remotes,
            "submodules": len(submodules),
            "subtrees": len(subtrees),
            "worktrees": len(worktrees),
            "stashes": stash_count,
            "sparse_checkout": sparse,
            "form": form,
        }
        print(json.dumps(data, indent=2))
        return 0

    # Submodule status summary
    sub_statuses = {}
    for s in submodules:
        sub_statuses[s["status"]] = sub_statuses.get(s["status"], 0) + 1
    sub_detail = ", ".join(f"{v} {k}" for k, v in sorted(sub_statuses.items()))

    # Worktree status summary
    wt_statuses = {}
    for w in worktrees:
        st = w["status"].replace(" *", "")
        wt_statuses[st] = wt_statuses.get(st, 0) + 1
    wt_detail = ", ".join(f"{v} {k}" for k, v in sorted(wt_statuses.items()))

    safe_print(f"  Branch:      {branch_str}")

    # Remotes
    if remotes:
        for i, r in enumerate(remotes):
            label = r["slug"] if r["slug"] else r["fetch_url"]
            # Determine push/fetch symmetry
            if r["fetch_url"] == r["push_url"]:
                direction = "push & fetch"
            elif r["fetch_url"] and r["push_url"]:
                direction = "fetch != push"
            elif r["fetch_url"]:
                direction = "fetch only"
            else:
                direction = "push only"
            prefix = "  Remotes:     " if i == 0 else "               "
            safe_print(f"{prefix}{r['name']} -> {label} ({direction})")
            # At -v, also show full URLs
            if VERBOSITY >= 1 and r["slug"]:
                safe_print(f"               fetch: {r['fetch_url']}")
                if r["push_url"] != r["fetch_url"]:
                    safe_print(f"               push:  {r['push_url']}")

    if worktrees:
        safe_print(f"  Worktrees:   {len(worktrees)} ({wt_detail})")
    if submodules:
        safe_print(f"  Submodules:  {len(submodules)} ({sub_detail})")
    else:
        safe_print(f"  Submodules:  0")
    safe_print(f"  Subtrees:    {len(subtrees)}")
    safe_print(f"  Form:        {describe_form(form)}")
    if stash_count:
        safe_print(f"  Stashes:     {stash_count}")
    if sparse:
        safe_print(f"  Sparse:      active")

    return 0


def cmd_composition(json_output=False):
    """Show detailed repo composition: submodules, subtrees, worktrees."""
    repo_root = find_repo_root()

    submodules = detect_submodules(repo_root)
    subtrees = detect_subtrees(repo_root)
    worktrees = detect_worktrees()

    all_items = submodules + subtrees

    # Add worktree info with consistent fields
    for wt in worktrees:
        branch_info = wt["branch"]
        if wt["head"]:
            branch_info = f"{branch_info} @ {wt['head']}" if branch_info else f"@ {wt['head']}"
        all_items.append({
            "type": "worktree",
            "path": wt["path"],
            "url": f"({wt['status'].replace(' *', '')})" if not branch_info else branch_info,
            "status": wt["status"].replace(" *", "").strip(),
        })

    if json_output:
        print(json.dumps(all_items, indent=2))
        return 0

    if not all_items:
        print("  No submodules, subtrees, or worktrees found.")
        return 0

    # Build table
    rows = []
    for item in all_items:
        rows.append([
            item["type"],
            item["path"],
            item.get("url", ""),
            item.get("status", ""),
        ])

    table = format_table(rows, ["Type", "Path", "Source", "Status"])
    print(table)
    print(f"\n  {len(all_items)} item(s)")

    return 0


def cmd_workspace(json_output=False):
    """Show workspace state: worktrees, sparse checkout, stashes, HEAD."""
    find_repo_root()

    branch = get_branch()
    head = get_head_short()
    worktrees = detect_worktrees()
    stash_count = detect_stashes()
    sparse = detect_sparse_checkout()

    if json_output:
        # Get stash details
        stashes = []
        if stash_count:
            rc, out, _ = git("stash", "list", "--format=%gd|%s")
            if rc == 0:
                for line in out.strip().splitlines():
                    parts = line.split("|", 1)
                    stashes.append({
                        "ref": parts[0] if parts else "",
                        "message": parts[1] if len(parts) > 1 else "",
                    })

        data = {
            "branch": branch,
            "head": head,
            "detached": branch is None,
            "worktrees": worktrees,
            "stashes": stashes,
            "sparse_checkout": sparse,
        }
        print(json.dumps(data, indent=2))
        return 0

    # Branch / HEAD
    if branch:
        safe_print(f"  HEAD:        {branch} @ {head}")
    else:
        safe_print(f"  HEAD:        detached @ {head}")

    # Worktrees
    if worktrees:
        print()
        rows = []
        for wt in worktrees:
            label = wt["branch"] or "(bare)" if wt["status"] == "bare" else wt["branch"] or "(detached)"
            status = wt["status"]
            rows.append([wt["path"], label, status])
        print(format_table(rows, ["Worktree", "Branch", "Status"]))

    # Sparse checkout
    if sparse:
        print(f"\n  Sparse checkout: active")

    # Stashes
    if stash_count:
        print(f"\n  Stashes ({stash_count}):")
        rc, out, _ = git("stash", "list")
        if rc == 0:
            for line in out.strip().splitlines()[:10]:
                safe_print(f"    {line}")
            if stash_count > 10:
                print(f"    ... and {stash_count - 10} more")

    if not worktrees and not stash_count and not sparse:
        print("  Default workspace, no worktrees or stashes.")

    return 0


def cmd_form(json_output=False):
    """Show repo form: bare, shallow, mirror, partial clone."""
    find_repo_root()
    form = detect_form()

    if json_output:
        print(json.dumps(form, indent=2))
        return 0

    safe_print(f"  Form:           {describe_form(form)}")
    safe_print(f"  Bare:           {'yes' if form['bare'] else 'no'}")
    safe_print(f"  Shallow:        {'yes' if form['shallow'] else 'no'}")
    safe_print(f"  Mirror:         {'yes' if form['mirror'] else 'no'}")
    if form["partial_clone"]:
        safe_print(f"  Partial clone:  yes (filter: {form.get('partial_filter', 'unknown')})")
    else:
        safe_print(f"  Partial clone:  no")

    return 0


# -- subcommand routing --

SUBCOMMANDS = {
    "composition": cmd_composition,
    "comp": cmd_composition,
    "workspace": cmd_workspace,
    "ws": cmd_workspace,
    "form": cmd_form,
    "info": cmd_info,
}


# -- parser and main --

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="dz git",
        description="Git repo state inspector -- composition, workspace, and form at a glance.",
        epilog=(
            "examples:\n"
            "  dz git                  Quick summary of the repo\n"
            "  dz git composition      Detailed table: submodules, subtrees, worktrees\n"
            "  dz git comp             Same (short alias)\n"
            "  dz git workspace        Worktrees, stashes, sparse checkout, HEAD state\n"
            "  dz git ws               Same (short alias)\n"
            "  dz git form             Repo form: bare, shallow, mirror, partial clone\n"
            "  dz git --json           Full summary as JSON\n"
            "  dz git -v               Show full remote URLs\n"
            "  dz git -vv              Show git commands being run (learn mode)\n"
            "  dz git -vvv             Show raw git output\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v full URLs, -vv show commands, -vvv raw output)",
    )
    parser.add_argument(
        "subcommand",
        nargs="?",
        default=None,
        help="Subcommand: composition, workspace, form, info",
    )
    return parser


def main(argv=None):
    """Entry point for dz git."""
    global VERBOSITY

    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    VERBOSITY = args.verbose
    json_output = args.json
    subcommand = args.subcommand

    # No subcommand -> default info summary
    if subcommand is None:
        return cmd_info(json_output)

    # Known subcommand
    if subcommand in SUBCOMMANDS:
        return SUBCOMMANDS[subcommand](json_output)

    # Unknown
    print(f"Unknown subcommand '{subcommand}'.", file=sys.stderr)
    print("Available: composition (comp), workspace (ws), form, info",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
