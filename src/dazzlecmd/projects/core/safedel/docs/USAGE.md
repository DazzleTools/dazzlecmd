# safedel Usage Guide

A practical reference for using `dz safedel` day-to-day. For architecture and
design decisions see `../ROADMAP.md`; for manifest internals see
`MANIFEST_SCHEMA.md`.

## Contents

1. [Quick Reference](#quick-reference)
2. [Recipes](#recipes)
3. [Trash Store Locations](#trash-store-locations)
4. [Protection Zones](#protection-zones)
5. [Platform Capability Matrix](#platform-capability-matrix)
6. [Configuration](#configuration)
7. [The "Oh Shit" Guide](#the-oh-shit-guide)

---

## Quick Reference

### Core operations

| Command | Action |
|---------|--------|
| `dz safedel <path>...` | Stage file(s) for deletion to the trash store |
| `dz safedel --dry-run <path>` | Preview classification and destination without changing anything |
| `dz safedel --yes <path>` | Skip interactive confirmation (LLM mode) |
| `dz safedel --json <path>` | Machine-readable output (LLM tool-use APIs) |
| `dz safedel list [pattern]` | List trash contents |
| `dz safedel recover [pattern]` | Recover file(s) from trash |
| `dz safedel clean [pattern]` | Permanently delete trash entries (zone-enforced) |
| `dz safedel status` | Show trash store statistics |

### Time patterns (work for list, recover, clean)

| Pattern | Matches |
|---------|---------|
| `last` | Most recent deletion |
| `today` | Everything deleted today |
| `today 10:46` | Deletions in that minute today |
| `today 10:4*` | Deletions in the 10:40-10:49 window today |
| `2026-04-08` | Everything deleted on that date |
| `2026-04-08 10:46` | Exact minute match |
| `2026-04-08 10:4*` | Wildcard time |
| `2026-04-0*` | Wildcard date |
| `2026-03-*` | All of March 2026 |
| `--age ">30d"` | By age (supports `>`, `>=`, `<`, `<=` and `d`/`h`/`m`/`s`) |
| `--contains foo.txt` | Match by filename (fnmatch) |
| `--path "*/projects/*"` | Match by original path |

### Flags

| Flag | Applies to | Meaning |
|------|------------|---------|
| `--yes`, `-y` | delete, clean | Skip interactive prompts |
| `--dry-run`, `-n` | delete, recover | Preview without acting |
| `--force`, `-f` | clean | Required for Zone B (< 48h) entries |
| `--json`, `-j` | delete, list | JSON output |
| `-v` | delete | Verbose (timing, config) |
| `-q` | delete, clean | Quiet (shortened warnings) |
| `-qq` | delete, clean | Minimal (just prompts) |
| `--to PATH` | recover | Recover to alternate parent directory |
| `--metadata-only` | recover | Apply metadata only, don't touch content |
| `--contains NAME` | list, recover, clean | Search by filename |
| `--path PATTERN` | list, recover, clean | Search by original path |
| `--age SPEC` | list, clean | Filter by age |

---

## Recipes

### "I want to delete this file safely"

```bash
dz safedel /path/to/file.txt
```

The file is staged to the trash store. You can recover it with
`dz safedel recover last` at any time up to the hold period.

### "I'm an LLM agent deleting a file"

```bash
dz safedel --yes /path/to/file.txt
```

`--yes` skips the interactive prompt (which you can't answer anyway in
non-TTY mode). The file is staged with full metadata capture. The tool
emits a recovery notice in stderr so you see the folder name to recover
from later if needed.

### "I'm not sure -- show me what would happen first"

```bash
dz safedel --dry-run /path/to/suspicious
```

Classifies the target and shows:
- File type (regular_file, symlink_file, junction, hardlink, regular_dir, ...)
- Which delete method will be used (`os.unlink`, `os.rmdir`, `shutil.rmtree`)
- Link target if applicable
- Any warnings (hardlink count, ADS presence, etc.)

No file is touched. Always use `--dry-run` when deleting something you're
not certain about -- especially symlinks and junctions.

### "I accidentally deleted the wrong file -- get it back NOW"

```bash
dz safedel recover last
```

Recovers the most recent deletion to its original path. If the original
path now has a different file, recovery will refuse; use `--to` to recover
to an alternate location:

```bash
dz safedel recover last --to /tmp/recovered
```

The file goes to `/tmp/recovered/<original_name>` (the target path is
treated as a parent directory).

### "I want just the timestamps back, keep my new content"

```bash
dz safedel recover last --metadata-only
```

Applies the preserved metadata (timestamps, permissions, ACLs, xattrs,
Windows creation time) to the file currently at the original path,
WITHOUT overwriting its content. Useful when you've regenerated a file
but want to preserve its original creation date, or when restoring a
config file's original permissions.

### "What did I delete today?"

```bash
dz safedel list today
```

Shows all trash entries from today across all stores (central + per-volume),
with zone labels and ages.

### "What did I delete in the 10 am hour this morning?"

```bash
dz safedel list today 10:*
```

### "Search for a file by name in the trash"

```bash
dz safedel list --contains "config.json"
```

### "Search for anything I deleted from a specific directory"

```bash
dz safedel list --path "*/projects/old-thing/*"
```

### "Recover everything I deleted in the 5-minute window around 10:46"

```bash
dz safedel recover today 10:4*
```

Recovers all trash folders whose timestamps start with `10-4`. Useful for
"I was doing a bulk cleanup at 10:46 and realized I deleted too much."

### "How much space is my trash using?"

```bash
dz safedel status
```

Shows folder count, entry count, total size, oldest/newest entry, and
breakdown by protection zone. Scans all known stores (central + per-volume).

### "I want to clean up old trash entries"

```bash
dz safedel clean --age ">30d"
```

Prompts interactively for each matching entry. Zone A/B/C entries can't
be cleaned this way (protection zones); only Zone D (>30 days by default).

### "I'm sure about cleaning this recent thing -- LLM-proof is getting in my way"

```bash
dz safedel clean last --force
```

`--force` is required for Zone B (< 48h). It still prompts interactively
and shows teaching-signal warnings. `--yes` does NOT work for Zone B --
this is intentional, to prevent LLMs from pipelining cleanup after
destructive operations.

### "Show me what's recoverable before I clean"

```bash
dz safedel list --age ">30d"
dz safedel clean --age ">30d" -qq
```

`-qq` suppresses educational warnings but keeps the interactive Y/N prompt.

---

## Trash Store Locations

safedel uses up to two types of stores:

### Central store (fallback)

| Platform | Path |
|----------|------|
| Windows | `%LOCALAPPDATA%\safedel\trash\` (typically `C:\Users\<user>\AppData\Local\safedel\trash\`) |
| Linux | `~/.safedel/trash/` |
| macOS | `~/.safedel/trash/` |
| WSL | `~/.safedel/trash/` (WSL-side, NOT Windows Recycle Bin) |

Override with `SAFEDEL_STORE` environment variable.

### Per-volume store (preferred when eligible)

| Platform | Path |
|----------|------|
| Windows | `<drive>:\Users\<user>\.safedel-trash\` |
| Linux/macOS | `<mountpoint>/.safedel-trash-<uid>/` |

Per-volume stores enable zero-copy `os.rename()` staging which preserves
ALL metadata. They're created automatically when you delete a file on a
local, writable, non-subst volume. Network drives, read-only volumes, and
SUBST drives fall back to the central store.

### Checking which store was used

After deletion, the report shows the folder name (e.g.,
`2026-04-09__20-26-26`). To find which store it's in:

```bash
# Check per-volume first (more common for local files)
ls "<drive>:\Users\<user>\.safedel-trash\<folder_name>"
# Or central
ls "%LOCALAPPDATA%\safedel\trash\<folder_name>"
```

Or just use `dz safedel status` which scans all known stores.

### Volume registry

```
~/.safedel/volumes.json
```

Tracks known per-volume stores by volume serial number (Windows) or
filesystem UUID (Linux), so USB ejection doesn't silently orphan entries.

---

## Protection Zones

safedel has 4 tiers of protection for the `clean` command, based on entry age:

| Zone | Default Age | Requires | LLM Can Clean? |
|------|-------------|----------|----------------|
| **A: Blocked** | disabled | nothing works | No |
| **B: Max Friction** | 0 - 48h | `--force` + interactive Y/N + teaching warnings | No (non-TTY rejected) |
| **C: Standard** | 48h - 30d | interactive Y/N + warnings | No by default (can pipe past) |
| **D: Relaxed** | > 30d | interactive by default, `--yes` accepted | Yes |

Zones are configurable in `~/.safedel/config.json`:

```json
{
    "protection": {
        "zone_a_enabled": false,
        "zone_a_hours": 6,
        "zone_b_hours": 48,
        "zone_c_days": 30
    }
}
```

### What happens if you hit a zone

| Scenario | Behavior |
|----------|----------|
| `safedel clean last` (Zone B, interactive shell) | "Requires --force" error, skipped |
| `safedel clean last --force` (Zone B, interactive) | Shows teaching warnings + Y/N prompt |
| `safedel clean last --force` (Zone B, non-TTY) | Refused: "stdin is not a TTY" |
| `safedel clean last --force --yes` (Zone B) | Shows warnings + still prompts (--yes ignored) |
| `safedel clean last` (Zone C) | Shows warnings + Y/N prompt |
| `safedel clean last --yes` (Zone C, non-TTY) | Refused: "--yes is not accepted" |
| `safedel clean last --yes` (Zone D) | Proceeds without prompting |

### The LLM safety model

LLM agents running in non-TTY environments physically cannot clean Zone B
or C entries -- interactive prompts require a real terminal. This is not a
flag check; it's a fundamental property of how the protection works.

The trash store itself is the primary safety net. Zones only apply to
permanent deletion.

---

## Platform Capability Matrix

What metadata is preserved on each platform:

| Metadata | Windows (same-vol) | Windows (cross-vol) | Linux (same-vol) | Linux (cross-vol) | macOS (same-vol) | macOS (cross-vol) |
|----------|-------------------|---------------------|------------------|-------------------|------------------|-------------------|
| Content | Full | Full | Full | Full | Full | Full |
| mtime | Full | Full | Full | Full | Full | Full |
| atime | Full | Full | Full | Full | Full | Full |
| ctime / creation time | Full | Restored via pywin32 | Capture only* | Capture only* | Full | Capture only* |
| Permissions (mode) | Full | Full | Full | Full | Full | Full |
| Windows ACLs | Full | Full via SDDL | N/A | N/A | N/A | N/A |
| Windows file attributes | Full | Full | N/A | N/A | N/A | N/A |
| NTFS ADS | Full | Detected + warned** | N/A | N/A | N/A | N/A |
| Linux xattrs (user.*) | N/A | N/A | Full | Full | Full | Full |
| macOS xattrs | N/A | N/A | Full | Full | Full | Full |
| Hardlink count | Captured | Captured | Captured | Captured | Captured | Captured |
| Symlink target | Full | Full | Full | Full | Full | Full |
| Junction target | Full | Full | N/A | N/A | N/A | N/A |

\* ctime on Unix is the inode change time and cannot be set by non-root.
Captured in manifest for reference but not restored.

\*\* NTFS Alternate Data Streams are lost on cross-device copy. safedel
detects significant streams (filters `:Zone.Identifier`) and warns during
staging. Full backup/restore via `BackupRead`/`BackupWrite` is not yet
implemented (would require elevated privileges).

### Same-volume vs cross-volume

The key insight: when safedel can use `os.rename()` (same-volume staging),
all metadata is preserved atomically. Per-volume trash directories are
designed to make rename possible whenever the local filesystem is writable.

For unavoidable cross-volume cases (e.g., USB drive to central store),
metadata is captured in the JSON manifest and restored on recovery to the
extent the platform allows.

---

## Configuration

Location: `~/.safedel/config.json`

Default config is created automatically on first use. To customize:

```json
{
    "protection": {
        "zone_a_enabled": false,
        "zone_a_hours": 6,
        "zone_b_hours": 48,
        "zone_c_days": 30
    }
}
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `SAFEDEL_STORE` | Override the central trash store path |
| `LOCALAPPDATA` (Windows) | Used to compute default central store path |

---

## The "Oh Shit" Guide

**If you think you've lost data**, read this section first.

### First 30 seconds

1. **Don't panic.** safedel stages files before deleting them. Most "deletions"
   are recoverable.
2. **Don't run `dz safedel clean`** -- this is the only way to permanently
   destroy staged files.
3. **Check the trash:**
   ```bash
   dz safedel status
   dz safedel list today
   dz safedel list --contains "<some part of the filename>"
   ```

### If you find the file in the trash

```bash
# Recover to original location
dz safedel recover <folder_name>

# Or recover to a safe alternate location first
dz safedel recover <folder_name> --to /tmp/safe

# Or just the metadata if you've recreated the file elsewhere
dz safedel recover <folder_name> --metadata-only --to /path/to/new/file
```

### If you DON'T find it in the trash

Possible reasons:

1. **The delete wasn't done via safedel.** Check if `rm` or `del` was used
   directly. safedel only protects deletions that go through it.
2. **The file was cleaned already.** Check if you ran `dz safedel clean` or
   if the file aged past the hold period. (Default: 30 days before Zone D.)
3. **Per-volume store orphaned.** Check the volume registry:
   ```bash
   cat ~/.safedel/volumes.json
   ```
   If a volume is marked `is_reachable: false`, the per-volume store may be
   on a disconnected drive. Reconnect and run `dz safedel status` to rescan.
4. **Test isolation leak.** If you've been running tests, a test suite might
   have created an isolated store in a temp dir. Check `$TEMP/safedel_test_store_*`.

### Files in the trash but content appears missing

1. **Check the manifest first** -- it always contains the metadata even if
   content staging failed:
   ```bash
   cat "<store_path>/<folder_name>/manifest.json"
   ```
2. **content_preserved: false** entries are symlinks/junctions where only
   the link target is recorded (not the target's content). The link itself
   can be recreated, but if the original link target is gone, the content
   is gone too.
3. **content_path: null** means the file was staged as metadata-only
   (usually because it was a symlink or junction).

### When in doubt

- **Stop using the filesystem.** Don't create new files in the same location.
- **Copy the entire trash store to a backup** before any recovery attempt:
  ```bash
  cp -a ~/.safedel /tmp/safedel-backup-$(date +%s)
  cp -a "%LOCALAPPDATA%\safedel" "%LOCALAPPDATA%\safedel-backup"
  ```
- **Work from the backup.** If something goes wrong during recovery, you
  still have the original trash contents.

### Known data loss scenarios (NOT recoverable)

- **Cleaned entries.** Once `safedel clean` completes, data is gone.
- **Per-volume store on a failed drive.** The drive itself is the store.
- **Files deleted before safedel was installed** or without `dz safedel`.
- **Zone A blocked but the user disabled Zone A and then cleaned.** If you
  change config mid-stream, old protections may not apply.
