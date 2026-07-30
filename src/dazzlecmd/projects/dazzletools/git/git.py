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
import json
import os
import sys
from pathlib import Path

# Add projects/dazzletools/ to sys.path so _repo_common (sibling dir) imports.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from _repo_common.repo_state import (  # noqa: E402
    describe_form,
    detect_form,
    detect_remotes,
    detect_sparse_checkout,
    detect_stash_entries,
    detect_stashes,
    detect_submodules,
    detect_subtrees,
    detect_worktrees,
    format_table,
    get_ahead_behind,
    get_branch,
    get_head_short,
    get_status_counts,
    get_upstream,
    git,
    safe_print,
    set_verbosity,
)

# Mirrors _repo_common.repo_state.VERBOSITY for this CLI's own display
# decisions (e.g. -v expands remote URLs). main() sets both in lockstep.
VERBOSITY = 0


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
        # Sync state is computed only for --json: the text summary is a
        # composition view and stays as it was.
        upstream = get_upstream()
        behind, ahead = get_ahead_behind(upstream=upstream)
        counts = get_status_counts()
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
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
            "dirty_count": counts["dirty_count"],
            "untracked_count": counts["untracked_count"],
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
        stashes = detect_stash_entries() if stash_count else []

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
    set_verbosity(args.verbose)
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
