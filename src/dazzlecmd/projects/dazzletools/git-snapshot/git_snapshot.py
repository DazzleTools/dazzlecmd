"""dz git-snapshot -- lightweight named checkpoints for git working state.

Uses git stash create + custom refs (refs/snapshots/) to provide named,
stable checkpoints that don't pollute the stash stack or commit history.

Subcommands:
    save     Save current working state as a named snapshot
    list     List all snapshots for this repo
    show     Show snapshot details and file summary
    diff     Diff a snapshot against current working state
    apply    Reapply snapshot (merge mode, preserves local changes)
    restore  Hard restore working tree from snapshot
    drop     Delete a snapshot
    clean    Prune old snapshots
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta


SNAPSHOT_REF_PREFIX = "refs/snapshots/"


# -- git helpers --

def git(*args):
    """Run a git command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def find_repo_root():
    """Find the git repo root from cwd."""
    rc, out, _ = git("rev-parse", "--show-toplevel")
    if rc != 0:
        print("Error: not inside a git repository.", file=sys.stderr)
        sys.exit(1)
    return out.strip()


def get_head_hash():
    """Get the current HEAD commit hash (short)."""
    rc, out, _ = git("rev-parse", "--short", "HEAD")
    if rc != 0:
        return "unknown"
    return out.strip()


def get_head_hash_full():
    """Get the current HEAD commit hash (full)."""
    rc, out, _ = git("rev-parse", "HEAD")
    if rc != 0:
        return "unknown"
    return out.strip()


def get_branch():
    """Get the current branch name."""
    rc, out, _ = git("rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return "detached"
    return out.strip()


def has_changes():
    """Check if working tree has any changes (staged, unstaged, or untracked)."""
    rc, out, _ = git("status", "--porcelain")
    return bool(out.strip())


def slugify(message):
    """Convert a message to a filesystem/ref-safe slug."""
    slug = message.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:50] if slug else "snapshot"


# -- ref management --

def make_ref_name(message):
    """Create a ref name from timestamp and message."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = slugify(message)
    return f"{SNAPSHOT_REF_PREFIX}{timestamp}_{slug}"


def list_snapshot_refs():
    """List all snapshot refs with metadata.

    Returns list of dicts: {ref, name, date, subject, hash}
    """
    fmt = "%(refname)%09%(creatordate:iso)%09%(subject)%09%(objectname:short)"
    rc, out, _ = git("for-each-ref", f"--format={fmt}",
                     "--sort=-creatordate", SNAPSHOT_REF_PREFIX)
    if rc != 0:
        return []

    snapshots = []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        ref, date, subject, obj_hash = parts[0], parts[1], parts[2], parts[3]
        # Extract short name from ref
        name = ref.replace(SNAPSHOT_REF_PREFIX, "")
        snapshots.append({
            "ref": ref,
            "name": name,
            "date": date,
            "subject": subject,
            "hash": obj_hash,
        })
    return snapshots


def find_snapshot(name_or_index):
    """Find a snapshot by name (prefix match) or index.

    Returns the full ref name, or None.
    """
    snapshots = list_snapshot_refs()
    if not snapshots:
        return None

    # Try numeric index (1-based, newest first)
    try:
        idx = int(name_or_index)
        if 1 <= idx <= len(snapshots):
            return snapshots[idx - 1]["ref"]
    except ValueError:
        pass

    # Try exact name match
    for s in snapshots:
        if s["name"] == name_or_index:
            return s["ref"]

    # Try prefix match
    matches = [s for s in snapshots if s["name"].startswith(name_or_index)]
    if len(matches) == 1:
        return matches[0]["ref"]
    if len(matches) > 1:
        print(f"Ambiguous snapshot name '{name_or_index}', matches:", file=sys.stderr)
        for m in matches:
            print(f"  {m['name']}", file=sys.stderr)
        return None

    return None


# -- subcommands --

def cmd_save(args):
    """Save current working state as a named snapshot."""
    if not has_changes():
        print("Nothing to snapshot -- working tree is clean.", file=sys.stderr)
        return 1

    message = args.message or "snapshot"

    # git stash create builds a stash-format commit from the working tree
    # without modifying the stash stack or working tree. It captures all
    # tracked changes (staged + unstaged). Untracked files require -u
    # but stash create doesn't support that, so we use a two-step approach
    # only when --include-untracked is requested.
    include_untracked = not args.no_untracked
    untracked_files = []
    staged_before = None

    if include_untracked:
        rc, untracked_out, _ = git("ls-files", "--others", "--exclude-standard")
        untracked_files = [f for f in untracked_out.strip().splitlines() if f.strip()]

        if untracked_files:
            # Remember what was already staged so we can restore index state
            _, staged_before, _ = git("diff", "--cached", "--name-only")
            # Stage untracked files so stash create captures them
            git("add", *untracked_files)

    full_message = f"dz-snapshot: {message}"
    rc, stash_hash, err = git("stash", "create", full_message)

    if untracked_files:
        # Restore index: unstage the untracked files we added
        git("reset", "--", *untracked_files)
        # Re-stage anything that was staged before (if any)
        if staged_before and staged_before.strip():
            previously_staged = [f for f in staged_before.strip().splitlines() if f.strip()]
            if previously_staged:
                git("add", *previously_staged)

    if rc != 0 or not stash_hash.strip():
        print(f"Error: failed to create snapshot: {err}", file=sys.stderr)
        return 1

    stash_hash = stash_hash.strip()

    # Store as a named ref
    ref_name = make_ref_name(message)
    rc, _, err = git("update-ref", ref_name, stash_hash)
    if rc != 0:
        print(f"Error: failed to store snapshot ref: {err}", file=sys.stderr)
        return 1

    head_hash = get_head_hash()
    branch = get_branch()
    short_name = ref_name.replace(SNAPSHOT_REF_PREFIX, "")

    print(f"Snapshot saved: {short_name}")
    print(f"  Branch: {branch} @ {head_hash}")
    print(f"  Message: {message}")
    print(f"  Ref: {stash_hash[:12]}")

    return 0


def cmd_list(args):
    """List all snapshots."""
    snapshots = list_snapshot_refs()

    if not snapshots:
        print("No snapshots found.")
        return 0

    if args.json:
        import json
        print(json.dumps(snapshots, indent=2))
        return 0

    count = args.count or len(snapshots)
    snapshots = snapshots[:count]

    # Table output
    print(f"  {'#':<4} {'Name':<45} {'Date':<20} {'Hash':<10}")
    print(f"  {'-'*4} {'-'*45} {'-'*20} {'-'*10}")
    for i, s in enumerate(snapshots, 1):
        # Trim date to just YYYY-MM-DD HH:MM
        date_short = s["date"][:16] if len(s["date"]) >= 16 else s["date"]
        name = s["name"]
        if len(name) > 45:
            name = name[:42] + "..."
        print(f"  {i:<4} {name:<45} {date_short:<20} {s['hash']:<10}")

    total = len(list_snapshot_refs())
    if count < total:
        print(f"\n  Showing {count} of {total} snapshots.")

    return 0


def cmd_show(args):
    """Show snapshot details and file summary."""
    ref = find_snapshot(args.name)
    if not ref:
        print(f"Snapshot not found: {args.name}", file=sys.stderr)
        return 1

    short_name = ref.replace(SNAPSHOT_REF_PREFIX, "")

    # Get commit info
    rc, out, _ = git("log", "--format=%H%n%s%n%ci%n%P", "-1", ref)
    if rc != 0:
        print(f"Error reading snapshot: {ref}", file=sys.stderr)
        return 1

    lines = out.strip().splitlines()
    full_hash = lines[0] if len(lines) > 0 else "unknown"
    subject = lines[1] if len(lines) > 1 else ""
    date = lines[2] if len(lines) > 2 else ""
    parents = lines[3].split() if len(lines) > 3 else []

    # The first parent of a stash commit is the HEAD it was created from
    base_commit = parents[0][:12] if parents else "unknown"

    print(f"Snapshot: {short_name}")
    print(f"  Hash:    {full_hash[:12]}")
    print(f"  Date:    {date}")
    print(f"  Message: {subject.replace('dz-snapshot: ', '')}")
    print(f"  Base:    {base_commit}")
    print()

    # Show file summary
    rc, stat_out, _ = git("diff", "--stat", f"{base_commit}...{ref}")
    if rc == 0 and stat_out.strip():
        print(stat_out)
    else:
        # Fallback: diff against first parent
        rc, stat_out, _ = git("diff", "--stat", ref + "^", ref)
        if rc == 0:
            print(stat_out)

    return 0


def cmd_diff(args):
    """Diff a snapshot against current working state."""
    ref = find_snapshot(args.name)
    if not ref:
        print(f"Snapshot not found: {args.name}", file=sys.stderr)
        return 1

    # Build diff command
    diff_args = ["diff"]

    if args.stat:
        diff_args.append("--stat")
    elif args.name_only:
        diff_args.append("--name-only")

    # Diff snapshot against working tree
    # stash commits have the working tree state in the commit itself
    diff_args.append(ref)

    rc, out, err = git(*diff_args)
    if rc != 0:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    if out.strip():
        print(out, end="")
    else:
        print("No differences.")

    return 0


def cmd_apply(args):
    """Reapply snapshot (merge mode, preserves local changes)."""
    ref = find_snapshot(args.name)
    if not ref:
        print(f"Snapshot not found: {args.name}", file=sys.stderr)
        return 1

    short_name = ref.replace(SNAPSHOT_REF_PREFIX, "")

    # git stash apply works on any stash-format commit
    rc, out, err = git("stash", "apply", ref)
    if rc != 0:
        if "CONFLICT" in (out + err):
            print(f"Applied with conflicts. Resolve manually.", file=sys.stderr)
            print(out, end="")
            return 1
        print(f"Error applying snapshot: {err}", file=sys.stderr)
        return 1

    print(f"Applied: {short_name} (merge mode)")
    return 0


def cmd_restore(args):
    """Hard restore working tree from snapshot."""
    ref = find_snapshot(args.name)
    if not ref:
        print(f"Snapshot not found: {args.name}", file=sys.stderr)
        return 1

    short_name = ref.replace(SNAPSHOT_REF_PREFIX, "")

    # Safety check
    if has_changes() and not args.force:
        print("Working tree has uncommitted changes.", file=sys.stderr)
        print("Use --force to overwrite, or save a snapshot first.", file=sys.stderr)
        return 1

    # Hard restore: checkout all files from the snapshot
    rc, out, err = git("checkout", ref, "--", ".")
    if rc != 0:
        print(f"Error restoring snapshot: {err}", file=sys.stderr)
        return 1

    # Unstage everything (checkout stages all changes)
    git("reset", "HEAD")

    print(f"Restored: {short_name} (working tree replaced)")
    return 0


def cmd_drop(args):
    """Delete a snapshot."""
    ref = find_snapshot(args.name)
    if not ref:
        print(f"Snapshot not found: {args.name}", file=sys.stderr)
        return 1

    short_name = ref.replace(SNAPSHOT_REF_PREFIX, "")

    if not args.force:
        print(f"Delete snapshot '{short_name}'? [y/N] ", end="", flush=True)
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 1
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 0

    rc, _, err = git("update-ref", "-d", ref)
    if rc != 0:
        print(f"Error deleting snapshot: {err}", file=sys.stderr)
        return 1

    print(f"Dropped: {short_name}")
    return 0


def cmd_clean(args):
    """Prune old snapshots."""
    snapshots = list_snapshot_refs()
    if not snapshots:
        print("No snapshots to clean.")
        return 0

    to_drop = []

    if args.older:
        cutoff = datetime.now() - timedelta(days=args.older)
        for s in snapshots:
            try:
                # Parse ISO date from git
                date_str = s["date"][:19]  # "2026-03-27 16:13:32"
                snap_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                if snap_date < cutoff:
                    to_drop.append(s)
            except (ValueError, IndexError):
                continue

    if args.keep is not None:
        # Keep the N newest, drop the rest
        if len(snapshots) > args.keep:
            keep_set = set(s["ref"] for s in snapshots[:args.keep])
            for s in snapshots:
                if s["ref"] not in keep_set and s not in to_drop:
                    to_drop.append(s)

    if not to_drop:
        print("Nothing to clean.")
        return 0

    if args.dry_run:
        print(f"Would drop {len(to_drop)} snapshot(s):")
        for s in to_drop:
            print(f"  {s['name']}")
        return 0

    print(f"Dropping {len(to_drop)} snapshot(s):")
    for s in to_drop:
        rc, _, err = git("update-ref", "-d", s["ref"])
        if rc != 0:
            print(f"  Error dropping {s['name']}: {err}", file=sys.stderr)
        else:
            print(f"  {s['name']}")

    return 0


# -- CLI --

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="dz git-snapshot",
        description="Lightweight named checkpoints for git working state",
        epilog=(
            "Examples:\n"
            "  dz git-snapshot save \"before refactor\"\n"
            "  dz git-snapshot list\n"
            "  dz git-snapshot diff 1\n"
            "  dz git-snapshot apply 1\n"
            "  dz git-snapshot restore 20260327-161332_before-refactor\n"
            "  dz git-snapshot clean --older 30 --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", help="Subcommand")

    # save
    p_save = sub.add_parser("save", help="Save current working state")
    p_save.add_argument("message", nargs="?", default=None,
                        help="Snapshot message (default: 'snapshot')")
    p_save.add_argument("--no-untracked", action="store_true",
                        help="Exclude untracked files from snapshot")

    # list
    p_list = sub.add_parser("list", help="List all snapshots")
    p_list.add_argument("--json", action="store_true",
                        help="Output as JSON")
    p_list.add_argument("--count", "-n", type=int, default=None,
                        help="Show only the N most recent")

    # show
    p_show = sub.add_parser("show", help="Show snapshot details")
    p_show.add_argument("name", help="Snapshot name or index")

    # diff
    p_diff = sub.add_parser("diff", help="Diff snapshot against working state")
    p_diff.add_argument("name", help="Snapshot name or index")
    p_diff.add_argument("--stat", action="store_true",
                        help="Show diffstat summary only")
    p_diff.add_argument("--name-only", action="store_true",
                        help="Show changed file names only")

    # apply
    p_apply = sub.add_parser("apply", help="Reapply snapshot (merge mode)")
    p_apply.add_argument("name", help="Snapshot name or index")

    # restore
    p_restore = sub.add_parser("restore", help="Hard restore from snapshot")
    p_restore.add_argument("name", help="Snapshot name or index")
    p_restore.add_argument("--force", "-f", action="store_true",
                           help="Overwrite uncommitted changes")

    # drop
    p_drop = sub.add_parser("drop", help="Delete a snapshot")
    p_drop.add_argument("name", help="Snapshot name or index")
    p_drop.add_argument("--force", "-f", action="store_true",
                        help="Skip confirmation")

    # clean
    p_clean = sub.add_parser("clean", help="Prune old snapshots")
    p_clean.add_argument("--older", type=int, metavar="DAYS",
                         help="Drop snapshots older than N days")
    p_clean.add_argument("--keep", type=int, metavar="N",
                         help="Keep only the N newest snapshots")
    p_clean.add_argument("--dry-run", action="store_true",
                         help="Show what would be dropped without doing it")

    return parser


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Ensure we're in a git repo
    find_repo_root()

    commands = {
        "save": cmd_save,
        "list": cmd_list,
        "show": cmd_show,
        "diff": cmd_diff,
        "apply": cmd_apply,
        "restore": cmd_restore,
        "drop": cmd_drop,
        "clean": cmd_clean,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
