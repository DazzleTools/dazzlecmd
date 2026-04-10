# safedel TODO

Short-term, concrete tasks. For longer-term strategy and phase planning see `ROADMAP.md`.

## Housekeeping

- [ ] Push commits to origin (0.7.6, 0.7.7, 0.7.8 all local)
- [ ] Filetoolkit `normalize_path_no_resolve()` commit (currently staged at `C:\code\filetoolkit\github`, uncommitted since earlier session)
- [ ] Update safedel WhereWeAre snapshot after Phase 3c

## Known Issues

- [ ] Hardlink recovery doesn't reconnect the link topology -- only restores file content to the original path. Manifest records other known paths but they aren't auto-reconnected.
- [ ] `apply_file_metadata()` silently ignores failures during full recovery (line 282 of `_recover.py` has a "best effort" comment but no logging of what failed).
- [ ] Pre-Python 3.12 `shutil.rmtree` on junctions is dangerous -- we have defense-in-depth in `_platform.safe_delete`, but should add a test that asserts this doesn't happen.
- [ ] `list_entries()` scans all stores via folder listing -- slow for trash stores with >10k entries. Not an issue yet.

## Improvements

- [ ] Add integration tests that exercise filekit disk utilities, preservelib manifest/metadata, and log_lib verbosity through safedel's actual code paths (not just unit tests of each lib).
- [ ] `status` subcommand could show per-volume store breakdown, not just total.
- [ ] `clean --force --yes` path: current behavior is correct (Zone B still requires interactive) but the UX could clarify WHY `--yes` was rejected.
- [ ] `recover` could show a preview of what would be restored before actually doing it (like `--dry-run` but automatic for multi-folder recovery).
- [ ] `recover` across multiple trash folders doesn't short-circuit on error -- should collect all errors and report them at the end.

## Tests to Add

- [ ] Junction safety test: verify `safe_delete` never calls `shutil.rmtree` on a junction even if the classifier is wrong
- [ ] Cross-device staging test with a real second volume (currently can't easily simulate in pytest)
- [ ] ADS roundtrip test: create file with ADS on same-volume, verify rename preserves streams
- [ ] Integration test: macOS `com.apple.quarantine` handling (needs macOS)
- [ ] Regression test for the `--to` non-existent path fix (already have one, but test it with a nested path that needs multiple dir levels)

## Documentation

- [ ] README.md for the safedel tool itself (currently design docs only in `private/claude/`)
- [ ] Update main dazzlecmd README/docs with safedel examples
- [ ] Document the `~/.safedel/config.json` schema with all zone options

## Migration / Cleanup

- [ ] When safedel gets its own GitHub repo, migrate TODO.md and ROADMAP.md
- [ ] Consider extracting `preservelib`, `help_lib`, `log_lib`, `core_lib`, `ps1` into proper dazzlelib submodules
- [ ] Remove `_lib/dazzle_filekit` and `_lib/unctools` junctions once pip-installed versions are used exclusively
