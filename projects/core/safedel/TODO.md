# safedel TODO

Short-term, concrete tasks. For longer-term strategy and phase planning see `ROADMAP.md`.

## Completed since last update

- [x] ~~Push commits to origin (0.7.6, 0.7.7, 0.7.8 all local)~~ -- these landed through subsequent sessions; v0.7.8 is on origin, v0.7.9 added FQCN dispatch
- [x] ~~Filetoolkit `normalize_path_no_resolve()` commit~~ -- superseded by filetoolkit v0.2.4 which shipped the full consolidation
- [x] ~~Update safedel WhereWeAre snapshot after Phase 3c~~ -- done (`2026-04-10__07-39-00__whereweare_safedel.md`)
- [x] **Phase 8: safedel migration to filekit v0.2.4 primitives** -- shipped as `d5a56b3`
  - [x] `_save_manifest` -> `dazzle_filekit.operations.atomic_write_json`
  - [x] `save_registry` -> `dazzle_filekit.operations.atomic_write_json`
  - [x] `_stage_regular` dir branch -> `copy_tree_preserving_links`
  - [x] `_recover_entry` dir branch -> `copy_tree_preserving_links`
  - [x] `_lib/preservelib/metadata.py` -> 74-line re-export shim to `dazzle_filekit.metadata`
- [x] 17 golden invariant tests (`test_golden_invariants.py`) added as regression safety net

## Housekeeping

- [ ] Push commits to origin when ready (Phase 8 commit `d5a56b3` still local)
- [ ] Decide whether to also push private repo sync (`aec71fe`) -- private repo is local-only per convention
- [ ] Post the catch-up comment to dazzlecmd issue #25 (DONE as of 2026-04-11)

## Known Issues (not blocking)

- [ ] Hardlink recovery doesn't reconnect the link topology -- only restores file content to the original path. Manifest records other known paths but they aren't auto-reconnected.
- [ ] `apply_file_metadata()` silently ignores failures during full recovery (line 282 of `_recover.py` has a "best effort" comment but no logging of what failed). Consider wiring through `log_lib` at debug level.
- [ ] `list_entries()` scans all stores via folder listing -- O(n) via directory scan. Not an issue for typical stores (<1000 entries); would need SQLite index if a user accumulates 10k+ entries.
- [ ] `_check_pywin32_startup_warning()` is defined in `safedel.py` but never called. With pywin32 now a required filekit dependency, the warning is unlikely to ever fire -- either wire it up or delete the dead code.

## Improvements

- [ ] Add integration tests that exercise filekit disk utilities, preservelib manifest/metadata, and log_lib verbosity through safedel's actual code paths (not just unit tests of each lib).
- [ ] `status` subcommand could show per-volume store breakdown, not just total.
- [ ] `clean --force --yes` path: current behavior is correct (Zone B still requires interactive) but the UX could clarify WHY `--yes` was rejected.
- [ ] `recover` could show a preview of what would be restored before actually doing it (like `--dry-run` but automatic for multi-folder recovery).
- [ ] `recover` across multiple trash folders doesn't short-circuit on error -- should collect all errors and report them at the end.
- [ ] Consider making `_compute_alt_path` delegate to the v0.2.4 `dazzle_filekit.paths.normalize_cross_platform_path` now that filekit can do bidirectional conversion -- currently safedel has its own regex-based helper.

## Tests to Add

- [ ] Junction safety assertion test: verify `safe_delete` never calls `shutil.rmtree` on a junction even if the classifier is wrong (defense-in-depth is in place but not explicitly asserted by a test).
- [ ] Cross-device staging test with a real second volume (currently can't easily simulate in pytest -- would need a loopback mount or a VHDX fixture).
- [ ] ADS roundtrip test: create file with significant ADS, stage via same-volume rename, verify streams survive (requires being on NTFS with same-volume trash).
- [ ] Integration test: macOS `com.apple.quarantine` handling (needs actual macOS; xattr code path is currently theoretical on Mac since WSL runs Linux).
- [ ] Nested path test for the `--to` fix: `safedel recover last --to /tmp/deeply/nested/new/path` when the parent doesn't exist at all.
- [ ] Test verifying the `_lib/preservelib/metadata.py` shim correctly re-exports ALL 14 functions from `dazzle_filekit.metadata` (prevents accidental export drift if filekit changes its API).

## Filekit-side issues discovered but deferred

These came up during the Phase 8 audit. They are **filekit's** concerns, not safedel's:

- [ ] Filekit `create_symlink` uses `cmd /c mklink` for the Windows fallback. Per dazzlecmd's CLAUDE.md rule about never using `cmd.exe` for symlinks/junctions (it fails silently when invoked from bash/WSL), this should be PowerShell `New-Item -ItemType SymbolicLink`. Worth filing as a filekit issue.
- [ ] Filekit `remove_file` has no readonly handling -- raises `PermissionError` on Windows readonly files instead of stripping the attribute and retrying.
- [ ] Filekit `remove_directory` has no reparse-point guard before `shutil.rmtree` -- safedel has this guard in `_platform.safe_delete` but filekit's generic wrapper doesn't. Pre-Python-3.12 consumers are at risk.

None of these block safedel's use of filekit -- safedel's own `safe_delete` handles the cases filekit doesn't.

## Documentation

- [ ] README.md for the safedel tool itself -- currently USAGE.md in docs/ covers most of this, but a brief README pointing at USAGE.md would help discoverability in the GitHub file listing.
- [ ] Update main dazzlecmd README/docs with safedel examples (once dazzlecmd stabilizes its doc structure).
- [ ] Document the `~/.safedel/config.json` schema with all zone options -- partially done in USAGE.md Zone Reference section, could be its own doc.
- [ ] Write a brief note in preservelib upstream (`C:\code\preserve\preservelib\`) pointing at filekit v0.2.4's metadata module -- the upstream still has the 665-line version, and whoever next updates preservelib should know the 883-line version is now in filekit (per the filetoolkit v0.2.4 whereweare doc).

## Migration / Cleanup

- [ ] When safedel gets its own GitHub repo, migrate TODO.md and ROADMAP.md
- [ ] **Low priority**: consider also extracting `help_lib`, `log_lib`, `core_lib`, `ps1` into proper dazzlelib submodules (preservelib is effectively already "moved" since metadata now lives in filekit)
- [ ] Remove `_lib/dazzle_filekit` and `_lib/unctools` junctions once pip-installed versions are used exclusively (filekit is on PyPI as of v0.2.4; unctools is unreleased).
- [ ] Consider shrinking `_lib/preservelib/` further -- the `manifest.py`, `restore.py`, and other modules are still local copies. Only `metadata.py` is now a shim.
