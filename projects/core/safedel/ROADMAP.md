# safedel Roadmap

Long-term strategy and phase planning. For short-term concrete tasks see `TODO.md`.

## Vision

`dz safedel` is a cross-platform safe-delete tool designed as a safety net for
both humans and LLM agents. The core promise: files staged through safedel are
always recoverable within the configured hold period, and their metadata
(timestamps, permissions, ACLs, creation time, extended attributes) is
preserved wherever the platform allows.

The tool exists because LLM agents routinely issue destructive `rm -rf` commands
on symlinks, junctions, and important data that they misclassify. safedel acts
as a forced pause-and-validate layer between the LLM's intent and the
filesystem's irrevocable action.

## Completed Phases

### Phase 1 -- MVP (v0.7.6, commit 7969aff)
Core delete/list/recover/clean/status workflow, 7 modules, link safety matrix
(symlinks unlinked, junctions rmdir'd, hardlinks warn), timestamped trash
folders with JSON manifests, 4-tier protection zones.

### Phase 2 -- Polish (v0.7.6, commit 1a4df9a)
dazzle-filekit integration (no fallbacks), --json output, log_lib verbosity
(-v/-q/-qq), non-TTY enforcement, bug fixes (--to path, security descriptor
serialization, wildcard glob), 90-test pytest suite.

### Phase 3a -- Per-volume trash (v0.7.7, commit cce0229)
Zero-copy os.rename() staging via per-volume trash directories. Volume
detection using unctools `get_drive_type`/`is_network_drive`. Volume registry
at `~/.safedel/volumes.json` keyed by serial number (stable across USB eject).
Multi-store list/recover/clean. Test isolation via explicit `registry_path`.
14 new volume tests.

### Phase 3b -- Advanced metadata preservation (v0.7.8)
- Windows ctime restoration via pywin32 `SetFileTime` with `FILE_WRITE_ATTRIBUTES`
  and `FILE_FLAG_BACKUP_SEMANTICS`. Auto-invoked during recovery.
- WSL dual-path manifest storage: `original_path_alt` field stores the
  cross-runtime path form so recovery works from either WSL or Windows Python.
- pywin32 startup warning.

### Phase 3c -- Cross-platform metadata (v0.7.8)
- NTFS Alternate Data Stream detection via ctypes `FindFirstStreamW` with
  `::$DATA` and `:Zone.Identifier` filtering.
- Linux/macOS xattr preservation via `os.listxattr`/`getxattr`/`setxattr`
  stored as base64 in manifest. Skips `com.apple.quarantine`.
- 29 new tests (127 Windows, 107 WSL).

### Phase 8 -- filekit v0.2.4 primitives migration (commit d5a56b3, no version bump)

Internal refactor to use dazzle-filekit v0.2.4 primitives instead of
duplicated code. No user-visible behavior change; pure cleanup.

- `_save_manifest` and `save_registry` replaced with
  `dazzle_filekit.operations.atomic_write_json`. Removes two separate
  copies of the tmp-write + os.replace dance.
- `shutil.copytree(..., symlinks=True)` replaced with
  `dazzle_filekit.operations.copy_tree_preserving_links` in both
  `_stage_regular` and `_recover_entry` dir branches. Filekit's wrapper
  enforces `symlinks=True` and rejects reparse-point roots as a defense-
  in-depth safety net.
- `_lib/preservelib/metadata.py` replaced with a 74-line re-export shim
  pointing at `dazzle_filekit.metadata`. safedel's existing
  `from preservelib.metadata import ...` imports continue to work; the
  actual code now lives once, in filekit. Net -514 lines of duplicated
  code eliminated.
- 17 new golden invariant tests added as a permanent regression safety
  net, capturing safedel's end-state guarantees (classification
  determinism, roundtrip metadata preservation, manifest schema stability,
  folder naming, dry-run invariants).

Architectural outcome: safedel now has a clean one-way dependency on
filekit for primitives and a minimal dependency on preservelib (shim).
The layering rule documented in the integration analysis
(`2026-04-10__20-31-07__preservelib-filekit-integration.md`) is now
enforced in practice, not just on paper.

## Candidate Future Phases

These are not formally planned. They're captured here so the ideas aren't lost.

### Phase 4 -- Ecosystem Integration

**Goal**: Make safedel the default safety layer for LLM-driven workflows and
multi-runtime environments.

Candidates:
- **Shell hook integration**: opt-in Claude Code hook that intercepts `rm`
  calls and redirects to safedel. Similar for bash/zsh aliases. Would need
  a way to distinguish "genuinely wants to delete permanently" vs "just wants
  to delete" -- perhaps a `--real-rm` escape hatch.
- **`safedel sync`**: merge per-volume trash stores across WSL and Windows
  boundaries. Currently each runtime sees only its own registry; a sync
  command would let a user recover from the other runtime's trash.
- **Cross-session handoff**: manifest format stable enough to share trash
  stores across users, machines, or backups.

### Phase 5 -- Scale and Performance

**Goal**: Handle large trash stores efficiently and integrate with enterprise
backup systems.

Candidates:
- **SQLite index**: optional acceleration layer when trash entry count exceeds
  ~10,000. Folder-scan is O(n) and gets slow. An index would bring listing to
  O(log n) with minimal complexity increase.
- **Incremental manifest updates**: currently each trash folder writes a full
  manifest. For large trees, incremental updates would reduce I/O.
- **Backup integration**: hooks for restic/duplicati/etc. to scan trash store
  for deleted files before they're cleaned.
- **Retention policies**: more expressive than the current 4-zone system.
  e.g., "keep 10 most recent of any file matching /projects/*" or
  "keep everything deleted during work hours."

### Phase 6 -- Advanced Data Preservation

**Goal**: Full fidelity metadata preservation even in hostile edge cases.

Candidates:
- **Full NTFS ADS backup/restore** via `BackupRead`/`BackupWrite` (currently
  detection-only). Requires `SE_BACKUP_NAME` privilege.
- **Hardlink topology reconstruction**: on recovery, detect existing links
  to the same inode and reconnect rather than creating a separate file.
- **macOS resource fork preservation**: current xattr support covers the
  common case but resource forks on ancient HFS data need explicit handling.
- **Sparse file preservation**: currently cross-device copy materializes
  sparse files. Should detect and warn, or use `CopyFileExW` with
  `COPY_FILE_COPY_SYMLINK | COPY_FILE_ALLOW_DECRYPTED_DESTINATION`.
- **Windows EFS (encrypted files)**: currently unhandled -- may fail or
  silently decrypt on copy.

### Phase 7 -- Extraction to its Own Project

**Goal**: Move safedel out of the dazzlecmd umbrella into a dedicated
GitHub project with its own release cadence.

Candidates:
- **Standalone package**: `pip install dazzle-safedel`
- **Dazzlelib submodule migration**: `preservelib`, `help_lib`, `log_lib`,
  `core_lib`, `ps1` become proper package dependencies instead of embedded
  `_lib/` copies
- **GUI companion**: optional tray app that shows recent deletions and
  exposes recover with a right-click menu
- **Cross-IDE integration**: VSCode extension, JetBrains plugin

## Non-Goals

Explicit non-goals to prevent scope creep:

- **NOT a full backup tool**: safedel stages at delete time, not on a
  schedule. If you want time-machine-style snapshots, use a real backup tool.
- **NOT a file history system**: safedel tracks the last deletion, not the
  full edit history of a file.
- **NOT a replacement for git**: version control is not in scope.
- **NOT an undo system for general filesystem operations**: only delete is
  tracked, not move/rename/overwrite.
- **NOT a cryptographic secure-delete tool**: the opposite -- safedel
  specifically PREVENTS secure deletion by keeping copies around.

## Design Principles

These should guide any future work:

1. **Reversibility is the default**. Every destructive operation should have
   a clear recovery path.
2. **LLM-safe by default**. The tool should be usable by an LLM agent without
   human supervision without causing data loss.
3. **Platform parity where possible**. Same conceptual model on Windows, Mac,
   Linux, WSL, even when the underlying APIs differ.
4. **Prefer platform libraries over reimplementation**. Use dazzle-filekit
   for path/disk operations, metadata capture/apply, atomic writes, and
   link-safe tree copy; unctools for Windows drive detection; preservelib
   for manifest format. When you spot duplicated code between safedel and
   a shared library, the shared library wins -- migrate safedel to use it.
5. **Metadata fidelity proportional to staging path**. Same-device rename
   preserves everything; cross-device copy preserves what the platform allows
   and records what it can't in the manifest.
6. **Teaching signals over mechanical barriers**. Zone warnings tell LLMs
   what they should check before cleaning up, rather than just blocking them.
7. **Test isolation**. The tool's own test suite must be isolated from user
   data and from other test runs.
8. **Golden invariants over text-based goldens**. When we need to prove
   "no behavior change across a refactor", we capture end-state properties
   (classification determinism, roundtrip metadata preservation, manifest
   schema stability) rather than text fixtures that drift with timestamps
   and paths. See `tests/test_golden_invariants.py` for the model.
9. **Defense in depth, even against our own code**. `safe_delete` checks
   for reparse points even when the classifier said it's a regular
   directory -- because the cost of a wrong `shutil.rmtree` on a junction
   is catastrophic. Apply the same rule to any safety-critical code path.
