# dz git-snapshot

Lightweight named checkpoints for git working state -- save, diff, apply, and restore without committing.

## Why not just git stash?

`git stash` is a LIFO stack with shifting indices. `stash@{3}` becomes `stash@{4}` when you add a new stash. Names are hard to find, and `stash list` output is dense. Stashes are also easy to accidentally drop.

`dz git-snapshot` uses **named refs** under `refs/snapshots/`. They don't shift, they're easy to find, and they don't interfere with your stash stack at all.

## Quick Start

```bash
# Save current working state (tracked + untracked files)
dz git-snapshot save "before refactor"

# List all snapshots
dz git-snapshot list

# Diff a snapshot against your current working tree
dz git-snapshot diff 1

# Reapply a snapshot (merge mode -- keeps your current changes)
dz git-snapshot apply 1

# Hard restore (replaces working tree)
dz git-snapshot restore 1 --force
```

## How It Works

### Save

```bash
dz git-snapshot save "my checkpoint"
```

1. Runs `git stash create` -- builds a stash-format commit capturing your working tree, but does NOT push to the stash stack
2. Stages untracked files temporarily to include them, then restores the index
3. Stores the commit as `refs/snapshots/YYYYMMDD-HHMMSS_<slug>`
4. Your working tree is untouched -- you keep working as normal

The result is a named, stable reference to your exact working state at that moment.

### Storage

Snapshots are stored as **git refs**, not stash entries:

```
refs/snapshots/20260328-011306_transient-seed-working-all-4-tests-passed
refs/snapshots/20260328-003625_before-seed-source-tracking
refs/snapshots/20260327-171805_pre-commit-cleanup-ready
```

This means:
- **Stable names** -- indices don't shift when you add or remove snapshots
- **Purely local** -- `git push` does NOT send snapshots to remotes (only branches and tags are pushed by default)
- **Native git operations** -- `git diff refs/snapshots/foo` works without any wrapper
- **No stash pollution** -- `git stash list` stays clean for manual use
- **Protected from gc** -- refs prevent git garbage collection from pruning the commits

### Diff

```bash
dz git-snapshot diff 1              # Full diff against working tree
dz git-snapshot diff 1 --stat       # Summary (files changed, insertions, deletions)
dz git-snapshot diff 1 --name-only  # Just file names
```

Shows what changed between the snapshot and your current working state.

### Apply vs Restore

**Apply** (merge mode):
```bash
dz git-snapshot apply 1
```
Reapplies the snapshot's changes on top of your current working tree. If there are conflicts, git reports them and you resolve manually. Your existing changes are preserved where they don't conflict.

**Restore** (hard replace):
```bash
dz git-snapshot restore 1 --force
```
Replaces your entire working tree with the snapshot's state. Requires `--force` if you have uncommitted changes (safety net to prevent accidental data loss). After restore, your working tree matches exactly what the snapshot captured.

### Referencing Snapshots

You can reference snapshots by:
- **Index** (newest = 1): `dz git-snapshot diff 1`
- **Full name**: `dz git-snapshot diff 20260328-011306_transient-seed-working-all-4-tests-passed`
- **Name prefix**: `dz git-snapshot diff 20260328-011306` (if unambiguous)

### Cleanup

Snapshots accumulate over time. Clean them up with:

```bash
dz git-snapshot clean --older 30           # Drop snapshots older than 30 days
dz git-snapshot clean --keep 10            # Keep only the 10 newest
dz git-snapshot clean --keep 5 --dry-run   # Preview what would be dropped
dz git-snapshot drop 3                     # Drop a specific snapshot
```

## Subcommand Reference

| Command | Description |
|---------|-------------|
| `save [message]` | Save current working state |
| `list` | List all snapshots (newest first) |
| `show <ref>` | Show snapshot details and file summary |
| `diff <ref>` | Diff snapshot against current working tree |
| `apply <ref>` | Merge-reapply snapshot (preserves local changes) |
| `restore <ref>` | Hard replace working tree (requires `--force`) |
| `drop <ref>` | Delete a snapshot |
| `clean` | Prune old snapshots |

### Flags

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--no-untracked` | save | Exclude untracked files |
| `--json` | list | Output as JSON |
| `-n`, `--count N` | list | Show only N most recent |
| `--stat` | diff | Show diffstat summary |
| `--name-only` | diff | Show only changed file names |
| `--force`, `-f` | restore, drop | Skip safety checks |
| `--older DAYS` | clean | Drop snapshots older than N days |
| `--keep N` | clean | Keep only N newest |
| `--dry-run` | clean | Preview without deleting |

## FAQ

**Q: Do snapshots get pushed to the remote?**
No. `refs/snapshots/` are purely local. `git push` only sends `refs/heads/` (branches) and `refs/tags/` by default. Your snapshots are private.

**Q: What about git garbage collection?**
Snapshots are protected. Git gc only prunes unreferenced objects -- the `refs/snapshots/` ref prevents the snapshot commit from being collected.

**Q: Can I see snapshots with git stash list?**
No. Snapshots are stored under `refs/snapshots/`, not `refs/stash`. This is intentional -- your stash stays clean for manual use. Use `dz git-snapshot list` or `git for-each-ref refs/snapshots/`.

**Q: What gets captured?**
By default: all tracked changes (staged + unstaged) and untracked files. Use `--no-untracked` to exclude untracked files.

**Q: Does save modify my working tree?**
No. Your working tree is identical before and after `save`. The snapshot is created as a git object without touching your files or index.

**Q: What happens if apply has conflicts?**
Git reports the conflicts just like `git stash apply` would. You resolve them manually with your normal merge conflict workflow.
