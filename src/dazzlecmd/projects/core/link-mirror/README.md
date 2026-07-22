# link-mirror

Reconcile NTFS links between a source tree and a mirrored copy.

After a file-level mirror (robocopy, Beyond Compare, preserve COPY) the
destination holds the regular files but frequently NOT the links: symlinks
and junctions are silently dropped, and hardlink groups are materialized as
independent duplicate files. `link-mirror` scans the source for every link
object, diffs against the destination, and recreates what is missing --
same kind, verbatim target bytes (relative targets unresolved, intentionally
broken targets unrepaired), and the link's own creation/modified/accessed
timestamps at 100ns precision. Parent directories dirtied by link creation
get their timestamps restored.

## Safety posture

- **Dry-run by default** -- without `--apply` nothing is written, ever.
- **Additive only** -- existing entries are never modified; mismatches are
  reported as conflicts and left alone.
- **Idempotent** -- re-running reports everything as satisfied.
- **Hardlink reconciliation is opt-in** (`--hardlinks recreate`): the one
  destructive capability (replacing a duplicated file with a hardlink to its
  group canonical) is sha256-guarded and swaps atomically.

## Usage

```bash
# See what a mirror is missing (dry run; exit 2 = pending work)
dz link-mirror D:\ B:\d-mirror

# Recreate the missing links, then prove parity
dz link-mirror D:\M B:\M --apply --verify

# Drive retirement: rewrite absolute D:\ targets to B:\ while recreating
dz link-mirror D:\M B:\M --apply --rewrite-prefix D:\ B:\

# Big volumes: MFT/USN scan (elevated console), manifest kept for audit
dz link-mirror D:\ B:\ --backend mft --save-manifest d-links.json

# Merge robocopy'd duplicate files back into hardlink groups
dz link-mirror D:\M B:\M --apply --hardlinks recreate
```

Exit codes: `0` nothing to do / success; `1` errors; `2` pending work or
conflicts found.

## Engine

This is a thin CLI over `dazzle_preservelib.linkmirror` (scan / plan /
apply / verify), which builds on `dazzle-filekit` link primitives -- the
mirror-scoped implementation of DazzleTools/preserve#48 Phase 2
(`LinkHandlingMode.RECREATE`). Engine logic lives in the library per the
dazzlecmd constitutional contract; this file owns argument parsing, report
display, and exit codes only.

## Development

Run the tests:

```bash
pytest tests/
```

## Files

- `.dazzlecmd.json` -- tool manifest (consumed by dazzlecmd-lib at discovery)
- `link_mirror.py` -- the tool's entry point (`main(argv=None)`)
- `tests/` -- CLI-layer pytest suite (engine tests live in dazzle-preservelib)
