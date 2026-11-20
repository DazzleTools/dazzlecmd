# safedel Usage Guide

A practical reference for using `dz safedel` day-to-day. For architecture and
design decisions see `../ROADMAP.md`; for manifest internals see
`MANIFEST_SCHEMA.md`.

## Contents

1. [Quick Reference](#quick-reference)
2. [Consent, the verdict, and exit codes](#consent-the-verdict-and-exit-codes)
3. [Recipes](#recipes)
4. [Trash Store Locations](#trash-store-locations)
5. [Protection Zones](#protection-zones)
6. [Platform Capability Matrix](#platform-capability-matrix)
7. [Configuration](#configuration)
8. [The "Oh Shit" Guide](#the-oh-shit-guide)

---

## Quick Reference

### Core operations

| Command | Action |
|---------|--------|
| `dz safedel <path>...` | Stage file(s) for deletion to the trash store |
| `dz safedel --dry-run <path>` | Show the plan the real run would carry out, without changing anything |
| `dz safedel --yes <path>` | Delete without a prompt. Required when nobody is at the keyboard (scripts, agents) |
| `dz safedel --yes --json <path>` | Machine-readable output; `--json` does not replace `--yes` |
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
| `--yes`, `-y` | delete, clean | Consent to proceed without a prompt. For delete it may carry scopes (see [Consent, the verdict, and exit codes](#consent-the-verdict-and-exit-codes)) |
| `--copy-first-max SIZE` | delete | Largest batch copy-first will copy (`10MB`, `1g`); a larger batch is refused while copy-first is on |
| `--dry-run`, `-n` | delete, recover | Preview without acting |
| `--force`, `-f` | clean | Required for Zone B (< 48h) entries |
| `--json`, `-j` | delete, list | JSON output |
| `-v` | delete | Verbose (timing, config) |
| `-q` | delete, clean | Quiet (shortened warnings) |
| `-qq` | delete, clean | Minimal (just prompts) |
| `--to PATH` | recover | Recover to alternate parent directory. Items of a batch that held several keep their place relative to each other under it |
| `--metadata-only` | recover | Apply metadata only, don't touch content |
| `--force-identity` | recover | Recover a stored file even when its size differs from what was recorded when it was deleted (by default it is refused and stays in the trash) |
| `--contains NAME` | list, recover, clean | Match items by name (wildcards allowed). With a batch named before it, only that batch is searched. `recover` recovers only the matching items and keeps the batch for the rest; `list` and `clean` act on the batches that hold a match |
| `--path PATTERN` | list, recover, clean | Match items by original path; same rules as `--contains` |
| `--age SPEC` | list, clean | Filter by age |

---

## Consent, the verdict, and exit codes

### Deleting asks first

Moving something into the trash is not free of consequences (a program may be writing to it; something may recreate it), so a delete always needs a yes:

- **At a console**, `dz safedel <path>` shows what it will do and asks `Proceed with deletion? [y/N]`. Anything but `y` refuses.
- **Anywhere else** (a script, an agent, a pipe, stdin redirected), nobody can answer, so it refuses unless `--yes` is given. It does not guess, and it does not report success.

"At a console" means a person can type: a real Windows console, or a Git Bash / mintty terminal. Redirected or empty input does not count, and neither does the Windows `NUL` device, which older versions mistook for a terminal.

### The last line is the verdict

Whatever happened, the final line of output says so, and the exit code matches. A caller that reads only the end of the output, or only the exit status, still learns the truth:

```
safedel: STAGED 2
safedel: REFUSED not interactive and --yes was not given
safedel: PARTIAL staged 1, not staged 1
safedel: DRY-RUN 3 would be staged
```

| Exit code | Meaning |
|---|---|
| 0 | Everything was staged (or a dry run completed) |
| 1 | An unexpected error; nothing was staged |
| 2 | A usage error (a bad flag, an unknown `--yes` scope) |
| 3 | Refused: nothing was moved. No `--yes`, a declined prompt, a folder that a link points at, an item inside a link that is also named, a drive root, a protected zone |
| 4 | Partial: some items were staged and some were not (for example, one path did not exist) |
| 6 | A check made after the move failed: something reported as moved is still there, or a link's target changed |

Any non-zero code stops a shell `&&` chain. With `--json`, the same facts are the `verdict` and `exit_code` fields of the one JSON object.

`clean` uses the same codes (3 when a protection zone refuses). `recover` returns 0 or 1.

### What `--yes` can carry

Bare `--yes` means "do not prompt". It can also carry a comma-separated list of scopes, each an explicit permission:

| Scope | Meaning |
|---|---|
| `noninteractive` | Do not prompt (what bare `--yes` means) |
| `delete-through-junction` | Also delete what a junction points at, not only the junction |
| `delete-through-symlink` | Also delete what a symlink points at, not only the symlink |
| `copy-first` | Make a verified copy before moving (see below) |
| `no-copy-first` | Stage without that copy |
| `dangerous` | Reserved for `dz guarded`; changes nothing in `safedel` itself |

```bash
dz safedel --yes delete-through-junction ./worktree/private
dz safedel --yes=noninteractive,no-copy-first ./big-folder
```

The word after `--yes` is read as scopes only when every comma-separated part is a scope name; otherwise it is a path, so `dz safedel --yes notes.txt` deletes `notes.txt`. A file that is literally named like a scope is written as `./dangerous` or placed after `--`. A list that mixes real scopes with a typo is an error (exit 2), never silent consent.

### Links: the link goes, the target stays

Naming a junction or symlink removes only the link; what it points at is not touched. To delete the target as well, say so with the matching `delete-through-...` scope. Giving the scope for the wrong kind of link, or when no path is a link, is refused.

The reverse direction is guarded too: if you name a real folder and a known junction or directory symlink elsewhere points at exactly that folder, `safedel` refuses and names the link, because deleting the folder empties what that link shows. "Known" links are those inside the worktrees of any git repository the folder sits in, plus any recorded in `~/.safedel/junctions.json`. Deleting something inside such a folder is ordinary work and is not refused.

### Two items with the same name

This works. Each item of a call is stored in the trash at its path relative to the folder the items have in common, so `a/x.json` and `b/x.json` are kept apart (`content/a/x.json`, `content/b/x.json`) and `recover` puts each back where it came from. `recover --to <dir>` keeps them apart too (`<dir>/a/x.json`, `<dir>/b/x.json`).

Related cases in one call:

- **The same path twice** is staged once, with a warning.
- **An item inside another item** (`build` and `build/out/a.o`) is carried by the outer one, with a warning.
- **An item inside a link that is also named** is refused: the link would be removed as a link, and the item is in what it points at. Name one or the other.
- **Items on different drives** are stored under numbered prefixes (`content/0/...`, `content/1/...`), with a warning: one trash store holds the batch, so items that are not on its drive are copied there, not moved.

This needs dazzlecmd-lib 0.10.39 or later. With 0.10.37 or 0.10.38 a call with two same-named items is refused whole before anything moves; delete them in separate calls.

### When recovery refuses a file

`recover` compares each stored file's size with the size recorded when it was deleted. If they differ, the file was changed or truncated while in the trash, or is not the item the record describes. It is not recovered and stays in the trash; the message names both sizes. `--force-identity` recovers it anyway. A modification time that differs is reported as a note and does not stop recovery.

A batch written by a very old version (before dazzlecmd-lib 0.10.36) may hold one stored item for several same-named entries. `recover` gives it to the entry it belongs to and reports `content lost to a name collision` for the others; their content was lost when that batch was written.

### Copy-first

While `safedel` is still earning trust, it can keep a second net: before an item is moved, a copy is made inside the batch (`<batch>/copy-first/`) and its contents verified against the original by SHA-256. The original is then moved as usual and remains the faithful item, with all its timestamps and attributes; the copy proves content only (its own timestamps are new). Links are never copied through: a link inside a folder is recorded, and a link named directly gets no copy.

- Mode `auto` (the default): on when nobody is at the keyboard, off at a console. `always` and `off` are the other modes.
- Limit: 10 MB per batch by default. A larger batch is refused (exit 3) and the message names both ways forward: `--yes no-copy-first` to stage without the copy, or `--copy-first-max <size>` to raise the limit for that call.
- Configure in `~/.safedel/config.json` under `copy_first` (`mode`, `max_bytes`), or with `SAFEDEL_COPY_FIRST` and `SAFEDEL_COPY_FIRST_MAX`.

---

## Recipes

### "I want to delete this file safely"

```bash
dz safedel /path/to/file.txt
```

At a console this shows the plan and asks before moving anything. The file is staged to the trash store, and the report names the batch so you can recover exactly it: `dz safedel recover <batch-name>` (or `dz safedel recover last` for the most recent complete deletion), at any time up to the hold period.

### "I'm an LLM agent deleting a file"

```bash
dz safedel --yes /path/to/file.txt
```

`--yes` is required: without it, a run with nobody at the keyboard refuses (exit 3) and moves nothing. Run the delete as its own command, read the last line (`safedel: STAGED 1`) or the exit code, and only then do the next step. The report names the batch folder to recover from.

### "I'm not sure -- show me what would happen first"

```bash
dz safedel --dry-run /path/to/suspicious
```

Prints the plan: for each path, what kind of thing it is (regular file, folder, symlink, junction, ...) and where a link points; what will happen to it (moved into the trash, or only the link removed); for a folder, what it holds (files, folders, links, hidden and system entries, total size); and which trash store it will go to. The real run carries out exactly this plan and prints the same lines first.

No file is touched, and no trash folder is created. If the real run would be refused, the dry run says so and exits with the same code. Always use `--dry-run` when deleting something you're not certain about -- especially symlinks and junctions.

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

Recovery works the same way (dazzlecmd-lib 0.10.40 and later). When the trash and the place being recovered to are on one drive, the item is moved back with a rename: a folder returns with every file and subfolder inside it exactly as it was stored, creation times included, and nothing is rewritten. Each recovered item is followed by one line:

- `times verified` -- the item's modification time (and creation time, where the platform records one) match what was recorded when it was deleted. For a folder it adds `moved back whole, so everything inside it is as it was`.
- `times verified; copied back from another drive, so files and folders inside it have new creation times` -- the trash was on a different drive, so the folder had to be copied. The folder itself has its recorded times; its contents are new files with the same data and modification times.
- `WARNING: times differ from the record: ...` -- something does not match; the content is recovered, and the line names what differs.

If the original parent folder no longer exists, recovery creates it and says so; that folder's own timestamps are new. Before dazzlecmd-lib 0.10.40, recovery always copied a folder back, so its contents came back with new creation times even on one drive.

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
- **Same-named items in one call, before dazzlecmd-lib 0.10.36a0.** Every
  item of a batch was staged at `content/<name>`, so two items with the same
  name (for example `session-states\<id>.json` and `context-window\<id>.json`)
  shared one trash path: the later one overwrote the earlier, and the batch
  still reported success. Batches written that way hold only the last item's
  bytes for that name. From dazzlecmd-lib 0.10.39 `recover` gives that item
  only to the entry it belongs to and says `content lost to a name collision`
  for the earlier ones, instead of putting the surviving bytes under the
  wrong path. 0.10.36 through 0.10.38 refused the second item (or the whole
  call) instead of overwriting; from 0.10.39 same-named items are staged side
  by side (see "Two items with the same name").
