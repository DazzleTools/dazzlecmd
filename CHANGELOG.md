# Changelog

All notable changes to dazzlecmd are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/).

## [0.11.4] - 2026-06-25

### Changed

- **`dz info <kit>` now shows the kit's current state inline.** The identity card is followed by a `Current state:` section listing the kit's rung on each lifecycle axis (activation/loading/membership) -- the same rows `dz kit status <kit>` shows on its own. So a single read verb gives the whole picture (identity + state), in the shape of `systemctl status`. `dz kit status <kit>` stays as the focused state-only view; `dz kit info --json` gains a `state` object. This replaces the earlier plan for a separate top-level `dz status` verb: identity and state are two sections of one card, not two commands. (Tool and aggregator cards are unchanged -- those levels carry no per-axis state yet.)

## [0.11.3] - 2026-06-25

### Added

- **`dz info <target>` is now level-agnostic.** It resolves the target across tool / kit / aggregator and renders the matching card: a tool shows the existing detailed card (unchanged), a kit shows its identity card (as `dz kit info`), and the aggregator itself (`dz info dz` or `dz info dazzlecmd`) shows a new aggregator card -- name, command, description, version, tool/kit counts, and root. When a bare name matches more than one level the more-specific one wins (tool > kit > aggregator) with a note naming the others; `--as tool|kit|aggregator` forces the level. FQCN-qualified tool names (`dz info core:find`) and unknown names behave exactly as before. This is the first verb to dispatch through the new cross-level resolver -- the `dz <verb> <target>` shape the 0.11.x line generalizes.

### Versions

- dazzlecmd 0.11.2 -> 0.11.3 (PATCH); dazzle-dz -> 0.11.3. dazzlecmd-lib floor raised to `>=0.9.4` (`dz info` now dispatches through the library's `resolve_target`). dazzle-lib unchanged (0.6.7).

## [0.11.2] - 2026-06-25

### Added

- **`dz kit info <kit>` shows a kit's static identity card.** A new inspect verb alongside `list`/`status`: where `status <kit>` shows the kit's *dynamic* per-axis state, `info <kit>` shows its *static* identity -- name, kind (kit vs virtual kit), description, version, tool/alias count, import name, directory, and the `.kit.json` source path. Absent fields render `(none)` rather than being dropped, so the card's shape is stable across kits. `--json` emits the same card as a JSON object (absent fields are `null`). This is the `info` side of the 0.11.x verb x level status/info split (the static card vs the dynamic axes).

### Versions

- dazzlecmd 0.11.1 -> 0.11.2 (PATCH); dazzle-dz -> 0.11.2. dazzlecmd-lib floor unchanged (>=0.9.0 -- the identity card reads only engine state, no new library import). dazzle-lib unchanged (0.6.7).

## [0.11.1] - 2026-06-25

### Added

- **`dz kit status <kit>` shows a per-axis state card.** With no name, `dz kit status` keeps its active-kits summary; given a kit name it now renders that kit's state on each lifecycle axis -- activation (active/disabled), loading (loaded/pointer), and membership -- read from the shared verb-axis registry rather than a hand-written field list. A new lifecycle axis added to the registry appears here automatically; axes with no per-kit rung are omitted. This is the first `dz <verb> <target>` cross-level state view of the 0.11.x "verb x level" line.

### Versions

- dazzlecmd 0.11.0 -> 0.11.1 (PATCH); dazzle-dz -> 0.11.1. dazzlecmd-lib floor raised to `>=0.9.0` (the per-axis card imports the library's verb-axis registry). dazzle-lib unchanged (0.6.7).

## [0.11.0] - 2026-06-25

### Added

- **Universal `on`/`off` poles on every kit lifecycle axis.** Each `dz kit <axis>` group now accepts `on`/`off` alongside its special verbs, routing to the same action: `dz kit loading on` == `dz kit loading attach`, `dz kit activation off` == `dz kit activation disable`, `dz kit membership on <url>` == `dz kit membership add <url>`. `on` is the warm (more-present) pole, `off` the cold inverse -- so every binary axis is addressable uniformly without recalling the special name. (`on`/`off` are the grouped form and require the axis noun; the special verb stays the hoistable shorthand.) This opens the 0.11.x "verb x level" CLI homogenization line, where every verb becomes a `{P, not-P}` axis usable across levels.

### Versions

- dazzlecmd 0.10.14 -> 0.11.0 (MINOR -- opens the 0.11.x verb x level line); dazzle-dz -> 0.11.0. dazzlecmd-lib floor unchanged (>=0.8.55); dazzle-lib unchanged (0.6.7).

## [0.10.14] - 2026-06-24

### Fixed

- **`pipx install dazzle-dz` now exposes the `dz` command directly** (no `--include-deps` needed). The `dazzle-dz` alias package now declares the same `dz`/`dazzlecmd` console scripts as `dazzlecmd` (pointing at its entry point, importable because `dazzlecmd` is a dependency). Isolated installers only surface the *named* package's apps, so previously -- with the scripts living only in the `dazzlecmd` dependency -- `pipx install dazzle-dz` installed nothing runnable.

### Changed

- **README install instructions** now lead with `pip install dazzlecmd`, note the `dazzle-dz` alias, and document the virtualenv / `pipx install dazzlecmd` path for externally-managed Python (PEP 668 -- e.g. recent Debian/Ubuntu, where a system-wide `pip install` is blocked).
- **Internal:** the monorepo no longer carries an in-tree copy of `dazzlecmd-lib`; CI and development use the published library, whose source lives in its own repo. No packaging change -- the published `dazzlecmd` already resolved the library from PyPI.

### Versions

- dazzlecmd 0.10.13 -> 0.10.14 (PATCH); dazzle-dz -> 0.10.14. dazzlecmd-lib unchanged (0.8.55); dazzle-lib unchanged (0.6.7).

## [0.10.13] - 2026-06-24

### Changed

- **safedel no longer bundles copies of published libraries; it depends on their PyPI releases.** The tool previously vendored several libraries under `safedel/_lib/` and prepended that directory to `sys.path`, so its imports shadowed any installed version. De-vendored to real dependencies: `dazzle-filekit>=0.3.2`, `unctools>=0.2.2` (Windows-only, for UNC->local path conversion), and `dazzle-preservelib>=0.8.1` (the metadata-preservation backend for the `f-cp`/`f-mv` tools, migrated from the vendored `preservelib` import to `dazzle_preservelib`). The orphaned internal `core_lib` bundle (no remaining importers) was removed. The internal `log_lib`/`help_lib` (slated to become standalone `dazzle-loglib`/`dazzle-helplib`) and the `ps1` PowerShell helpers stay bundled for now, so the `sys.path` shim remains until those publish.
- **Fixed a hard-coded local install path in `f-cp`/`f-mv`'s "backend not installed" error.** The message pointed at a developer-specific editable path; it now reads `pip install dazzle-preservelib`. Also repointed the adapter's ACL/metadata warning capture to the new `dazzle_preservelib` logger tree (the old `preservelib` logger name would otherwise silently drop those warnings).

### Versions

- dazzlecmd 0.10.12 -> 0.10.13 (PATCH); dazzle-dz -> 0.10.13. New direct deps: `dazzle-filekit>=0.3.2`, `unctools>=0.2.2` (win32), `dazzle-preservelib>=0.8.1`. dazzlecmd-lib unchanged (0.8.55); dazzle-lib unchanged (0.6.7).

## [0.10.12] - 2026-06-24

### Added

- **`core:listall` is now a registered tool.** The `listall` file/directory lister (backed by the `DazzleTools/listall` submodule) gained a tool manifest, so `dz listall` -- and the `f` kit's `f:ls` alias -- resolve and dispatch. The submodule's files now ship in the built wheel via a submodule-aware checkout.
- **A build-time privacy guard for the published artifacts.** `scripts/check_dist_no_leak.py` scans the built sdist and wheel for any `private/` design-doc path or the local-only `wtf` tree and fails the publish workflow before upload, so internal content cannot reach PyPI even from an accidental dev-tree build. The exclusion is depth-proof -- it matches path components, not globs.

### Fixed

- **`dz mode` mislabeled submodule-backed tools as `EMBEDDED`** when the aggregator lives in a repository subdirectory (the layout from #58, where the tool tree moved under `src/dazzlecmd/`). Submodule detection looked for `.gitmodules` relative to the aggregator root rather than the git repo root, and did not re-base the repo-relative submodule paths -- so it found no submodules and fell through to `EMBEDDED`. `dz mode` now correctly reports such tools as `PUBLISH (submodule)`, and the dev<->publish mode toggle works for them again. Development tree only -- an installed package has no `.gitmodules`, so its tools are correctly all-embedded. (dazzlecmd-lib)
- **#58 (sdist): the source distribution shipped no tools**, so a `pip install` that built from the sdist produced a `dz` with zero tools. `MANIFEST.in` excluded the per-tool `private/` directories with a `recursive-exclude` whose trailing pattern was a bare `*` -- which matches *every* file, wiping the grafted tool tree out of the sdist. (The earlier #58 wheel check missed it because it built the wheel directly, bypassing the sdist.) The exclude patterns are now path-anchored, so the sdist carries the full tool tree (manifests, kits, `aggregator.json`) while still omitting `private/` and the local-only `wtf` aggregator.

### Changed

- The CI and publish workflows now check out git submodules recursively, so submodule-backed tools (e.g. `core:listall`) materialize during test and build runs.
- **Raised the `dazzlecmd-lib` dependency floor to `>=0.8.55`** (from `>=0.8.34`) so a fresh install pulls the library version with the submodule mode-detection fix this release relies on.

### Versions

- dazzlecmd 0.10.11 -> 0.10.12 (PATCH); dazzle-dz -> 0.10.12; dazzlecmd-lib 0.8.54 -> 0.8.55 (submodule mode-detection fix). dazzle-lib unchanged (0.6.7).

## [0.10.11] - 2026-06-23

### Fixed

- **#58: the PyPI wheel now ships the tools (`pip install dazzlecmd` gives a working `dz`).** Relocated the tracked tool tree -- `projects/`, `kits/`, and `aggregator.json` -- from the repo root into `src/dazzlecmd/`, so it is inside the installable package. Added a `MANIFEST.in` + `package-data` globs (including the `.dazzlecmd.json` dotfile pattern that setuptools' `*` skips) to ship the tool files, and excluded the tool dirs from `packages.find` (they are data, not importable packages). A built wheel now contains `aggregator.json` + the kit manifests + the tracked `projects/**` tools, and excludes the local-only `wtf` recursion-proof aggregator and the per-tool `private/` design-doc repos (release builds must come from a clean checkout / CI). The editable dev `dz` is unchanged (110 tools) -- the runtime was already `aggregator.json`-anchored, so discovery follows the tree to its new location with no code change.

### Notes

- Live-repo tests that hardcoded the old `projects/...` root path were repointed to `src/dazzlecmd/projects/...`; full suite green (1590 passed). The byte-gate `dz info` goldens are stale (they predate the 0.10.x tool batch) and surface a pre-existing `listall` discovery gap (no `.dazzlecmd.json`, not registered in the core kit) -- re-baselining the goldens and the `listall` fix are tracked as a follow-up, as are the remaining #58 acceptance items (a `dazzlecmd-lib` publish job + a pip-install-and-dispatch wheel test). dazzlecmd-lib unchanged.

### Versions

- dazzlecmd 0.10.10 -> 0.10.11 (PATCH); dazzle-dz -> 0.10.11. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.10] - 2026-06-23

### Changed

- **Housekeeping (tooling/test artifacts; no functional change).** Committed straggler test/one-off files that belonged with earlier work but were never staged: the #58 move/revert tooling, the kit-lifecycle detach/attach demo, the v0.9.49 multiaxis-activation tester result, and `claude-session-metadata`'s symlink-timestamp research one-off (scrubbed of a hardcoded private path and made self-contained). Also stopped tracking the auto-generated `scripts/.vscode/settings.json` editor noise (`scripts/.gitignore`).

### Versions

- dazzlecmd 0.10.9 -> 0.10.10 (PATCH); dazzle-dz -> 0.10.10. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.9] - 2026-06-23

### Fixed

- **Manifest schema `runtime.type` enum was out of sync with the runner registry.** Added `node` and `docker` -- both have been implemented and shipped (since v0.7.17 / v0.7.21) but were never added to the schema, so a `node`/`docker` tool could fail strict manifest validation. Removed `managed` -- it was in the schema from v0.1.0-alpha but never had a runner factory, so a tool declaring it would warn-and-fail at dispatch. The enum now matches the registered factories: `python`, `binary`, `script`, `shell`, `node`, `docker`. The `managed` ambition (delegate dispatch to a package-manager-installed binary) is tracked in #92.

### Versions

- dazzlecmd 0.10.8 -> 0.10.9 (PATCH); dazzle-dz -> 0.10.9. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.8] - 2026-06-23

### Changed

- **Documentation refresh for the 0.10.x tool batch.** A new tool reference under `docs/tools/` -- a top-level [index](docs/tools/README.md) (canonical kits + the virtual-kit alias overlays), a new `media/` kit reference, and updated `core/` (now incl. `f-cp` / `f-mv` / `safedel`) and `dazzletools/` (5 -> 19 tools, grouped by area) references.
- **Slimmed the README.** "Included Tools" is now a compact kits-overview that points at the tool reference (instead of two inline tables that had drifted stale); "Project Structure" updated to the real namespaces (incl. the `media` namespace and `docs/tools/`); added a short "argparse for a whole toolbox" framing of the aggregator pattern.

### Fixed

- **`.gitignore`:** nested per-directory `.vscode/` folders (auto-generated editor cruft) are now ignored at any depth, while the shared root `.vscode/` config stays tracked (the un-ignore is anchored to root). Previously the scattered `.vscode/settings.json` files showed as untracked noise.

### Versions

- dazzlecmd 0.10.7 -> 0.10.8 (PATCH); dazzle-dz -> 0.10.8. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.7] - 2026-06-23

### Added

- **`dz find` -- fd escape hatches: `--` passthrough and `-0` / `--print0`.** Two ways for power users to reach `fd`'s full surface without dazzlecmd re-exposing every flag.
  - **`--`** -- everything after a literal `--` is appended verbatim to the `fd` command (after dazzlecmd's generated flags and pattern). Use it for flags `dz find` doesn't surface (`--strip-cwd-prefix`, `--owner`, `--prune`, ...); the passthrough can also carry its own positional pattern when `dz find`'s is empty. dazzlecmd does not validate passthrough args -- `fd` does.
  - **`-0` / `--print0`** -- emit NUL-delimited results (mirrors `fd --print0`), for safe piping into `xargs -0` (then `rg` / `sed` / ...) even with paths containing spaces.

### Notes

- 13 new tests in `tests/test_find_passthrough.py` (the command-build + split logic is pure and tested without invoking `fd`); ships with a human checklist for the real-`fd` / real-pipe behavior. dazzlecmd-lib unchanged.

### Versions

- dazzlecmd 0.10.6 -> 0.10.7 (PATCH); dazzle-dz -> 0.10.7. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.6] - 2026-06-23

### Added

- **The `media` kit -- seven ffmpeg-based media tools.** A new kit (`kits/media.kit.json`, opt-in: `dz kit enable media`) collecting video / audio / image / gif tasks. All cross-platform, all built on `ffmpeg` (plus `gifsicle` for `vid2gif`); registered under the `media:` namespace.
  - **`vid2gif`** -- high-quality video-to-GIF via an ffmpeg two-pass palette + `gifsicle` optimization.
  - **`vidresize`** -- aspect-ratio-preserving video resize, with metadata strip + optional audio injection.
  - **`img2vid`** -- build a video from N images plus an audio track, with sequential fade transitions (the general image-to-video tool).
  - **`crossfade`** -- build a video from exactly two images with a crossfade and an audio track (the simple 2-image shortcut). Named `crossfade` rather than the original `vid2img`, which read backwards (it is image-to-video, not video-to-image).
  - **`song-to-vid`** -- make a video per audio file from its embedded album art.
  - **`vid-preview-maker`** -- build a preview clip with a banner overlay and an audio fade-out.
  - **`mp3me`** -- batch FLAC -> MP3 / V0 / V2 / Ogg / AAC / ALAC transcoder with tag copy.

### Notes

- The seventh 0.10.x new-tools release. `vid2gif` is new in-repo; `vidresize` was ported from `comfyui_experiment`; the other five were migrated from the `omnitools` media-script collection (each tool records its origin via a `provenance:<source>` tag). Flat kit by design -- it can graduate to a nested aggregator (and an eventual `DazzleTools/media-kit` extraction, like `dazzletools`) later without renaming tools. Ships with a human test checklist; no formal pytest suite (these shell out to `ffmpeg`). `ffmpeg` / `gifsicle` must be on PATH. dazzlecmd-lib unchanged.

### Versions

- dazzlecmd 0.10.5 -> 0.10.6 (PATCH); dazzle-dz -> 0.10.6. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.5] - 2026-06-23

### Added

- **`extract-all` -- recursive archive extractor + file locator.** `dz extract-all <source> <pattern>...` stages a source archive (exe / zip / cab / msi / 7z / ...) under `%USERPROFILE%/extract-all/<sha12>/`, recursively unpacks every nested archive into sibling `.extracted/` dirs (showing the archive lineage live as it descends -- `L0 -> L1 Setup.exe -> L2 Setup.exe::$PLUGINSDIR/x.exe`), then searches the resulting tree for the given patterns (auto-classified as glob or regex) and reports matches grouped by pattern. Disk-saving modes: `--print-locate` (extract, print the archive-lineage path of each match, then delete the staging tree -- for "where does X live?" queries) and `--extract-matches` (keep only files matching a pattern and prune the rest). Also `--first` (shallowest match per pattern), `--max-depth` (bound recursion), `--re-extract`, sha12-keyed cache management (`--list-cache` / `--clear-cache`), and `--staging-root`. 7-Zip is auto-discovered (PATH, a bundled `7zz`, Program Files, or the `DZ_SEVEN_ZIP` env / `--seven-zip-path`). Registered in the dazzletools kit.

### Notes

- v0.1.0 "full eager extraction": correct, but peak disk equals the full extracted tree -- a `ROADMAP.md` ships alongside the tool documenting the deferred layer-by-layer / list-then-descend disk optimizations. Built fresh in-repo from a design doc (Apr 2026, while inspecting a driver installer). The sixth 0.10.x new-tools release; no formal pytest suite. dazzlecmd-lib unchanged.

### Versions

- dazzlecmd 0.10.4 -> 0.10.5 (PATCH); dazzle-dz -> 0.10.5. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.4] - 2026-06-22

### Added

- **`git` + `private-init` -- repo-workflow tools.** Two DazzleTools utilities for working with git repositories, landing together as the fifth 0.10.x new-tools release.
  - **`git`** (`dz git`, cross-platform) -- a read-only git repo-state inspector that answers composition/layout/form questions with quick subcommands instead of verbose git invocations. Bare `dz git` prints a summary (branch, composition counts, form); `dz git composition` tables submodules / subtrees / worktrees; `dz git workspace` covers worktrees, sparse checkout, stashes, detached HEAD; `dz git form` classifies the repo (bare / shallow / mirror / partial clone / fork). stdlib + `git`. (`dazzletools:git` is a deliberate, conflict-checked name -- it is not in dazzlecmd's reserved meta-command set, and `dz git` dispatches to this tool, not the system binary.)
  - **`private-init`** (`dz private-init`, cross-platform) -- initializes (or converts) a project's `private/` directory into its own standalone git repository, invisible to the parent repo. This replaces the older 4-layer private-content protection (gitignore + `.git/info/exclude` + pre-commit hooks + content stripping) with simple architectural separation: `private/` is literally a different repo. `--remote <url>` (backup remote), `--adopt` (convert existing content), `--status` (check). stdlib + `git`.

### Notes

- Both were built fresh in-repo (Apr 2026) and are registered in the dazzletools kit; committing their files resolves two `dazzletools/.kit.json` registrations that were previously dangling (the entries existed but the tool dirs had never been committed). They ship without formal pytest suites. dazzlecmd-lib unchanged.

### Versions

- dazzlecmd 0.10.3 -> 0.10.4 (PATCH); dazzle-dz -> 0.10.4. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.3] - 2026-06-22

### Added

- **`claude-session-metadata` + `claude-recover-sesslogs` + `claude-sesslog-datefix` + `claudeview` -- Claude Code session tools.** Four tools for cataloguing, recovering, and viewing Claude Code session transcripts, grouped under the existing `claude` virtual kit.
  - **`claude-session-metadata`** (cross-platform) -- catalogs Claude Code sessions (lost or live): cross-references session artifacts, discovers the on-disk docs a session referenced, and lays down navigable symlinks. Supersedes the retired `claude-lost-sessions` (it handles both lost and live sessions).
  - **`claude-recover-sesslogs`** (cross-platform) -- salvages the surviving logger channels (`.sesslog` / `.shell` / `.convo`) of sessions that ran in a now-missing working directory: it ranks session logs by folder-affinity and copies the survivors out. The original transcript is usually already gone, so these channels are the surviving record of the conversation. Kept as a standalone tool (not folded into `claude-session-metadata`). (Refs #90.)
  - **`claude-sesslog-datefix`** (Windows) -- repairs the timestamps on Claude Code session-log directories after a git operation corrupts them. `pywin32` is optional: `mtime` fixing works without it; only `ctime` (creation time) needs it.
  - **`claudeview`** (cross-platform) -- opens a Claude Code session in the history viewer from the command line. Depends on `claude-session-backup` (`csb`) plus the claude-code-history-viewer (installed or built from source).
  - **`claude` virtual kit** (`kits/claude.kit.json`): gains `claude:recover-sesslogs`, alongside the existing `claude:cleanup` / `claude:session-metadata` / `claude:sesslog-datefix` / `claude:view`. Committing the four tool dirs also resolves three `claude.kit.json` aliases that were previously dangling (their tool dirs had never been committed).

### Removed

- **`claude-lost-sessions`** -- retired; its lost-session cataloguing is subsumed by `claude-session-metadata`, which handles both lost and live sessions. The dazzletools kit drops the registration and the tool's files are removed.

### Notes

- The fourth 0.10.x new-tools release, ahead of the #58 packaging move. These tools ship without formal pytest suites (validated via local one-off scripts kept out of the public tree). dazzlecmd-lib unchanged.

### Versions

- dazzlecmd 0.10.2 -> 0.10.3 (PATCH); dazzle-dz -> 0.10.3. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.2] - 2026-06-22

### Added

- **`safe-icacls` + `redact-msinfo` + `fixuser` -- Windows sysadmin tools + the `windows` virtual kit.**
  - **`safe-icacls`** (alias `sicacls`, Windows-only) -- a loop-safe passthrough wrapper around `icacls`. With no `/T` it runs `icacls` verbatim; with `/T` it walks the tree itself and **prunes reparse points** (junctions/symlinks), because `icacls <profile> /T` otherwise loops forever on the self-referential `AppData\Local\Application Data` junction. Wrapper-only flags `--safe-dry-run` / `--safe-verbose` / `--safe-dirs-only` / `--safe-skip-reparse` / `--safe-progress N` / `--unsafe` (the `--safe-` prefix never collides with `icacls`'s `/`-style args). stdlib + `icacls.exe`.
  - **`redact-msinfo`** (cross-platform) -- redacts a Windows `msinfo32` text export for safe sharing: section selection (default-keeps System Summary / Display / Problem Devices; `--include` / `--exclude` / `--list-sections`) plus PII scrubbing (hostname, user, owner/org, product ID/key, UUID, serials, MACs, IP/subnet/gateway -> `[REDACTED-*]` tokens) with a self-verify pass (`--no-verify`, `--hostname`). stdlib-only; runs anywhere (the input is just a text file).
  - **`fixuser`** (alias `fixusr`, Windows-only) -- diagnoses and repairs a broken Windows user profile (the "signed in with a temporary profile" / `C:\Users\TEMP` state from a stripped profile ACL). Names + handles 6 shapes (`HEALTHY` / `BAK-ONLY` / `TEMP-ACTIVE+BAK` / `TEMP-ACTIVE-no-BAK` / `STATE-FLAGGED` / `MISSING`); repairs ACLs first (via `safe-icacls`, loop-safe) then the `ProfileList` registry. Read-only by default; `--repair` (elevated) backs up `ProfileList` + ACLs first; `--acls-only` / `--registry-only` / `--harden` / `--backup-dir` / `--yes`. stdlib (`winreg`/`ctypes`) + `icacls`/`reg`.
  - **`windows` virtual kit** (`kits/windows.kit.json`): `windows:sicacls` -> `safe-icacls`, `windows:fixusr` -> `fixuser`, `windows:redact-msinfo` -> `redact-msinfo`.

### Notes

- All three are pure stdlib (no `pywin32`). `safe-icacls` generalizes a loop-safe one-off; `redact-msinfo` pre-existed and was grouped into the `windows` kit; `fixuser` was built alongside (and depends on `safe-icacls`). Ships with three human test checklists; the tool tests run without elevation (they mock the OS-touching `icacls`/registry calls). The third 0.10.x new-tools release, ahead of the #58 packaging move. dazzlecmd-lib unchanged.

### Versions

- dazzlecmd 0.10.1 -> 0.10.2 (PATCH); dazzle-dz -> 0.10.2. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.1] - 2026-06-22

### Added

- **`md-rm-img` + `md-unwrap` -- markdown tools + the `md` virtual kit.**
  - **`md-rm-img`** strips inline base64 `data:` image blobs from markdown (preserving alt text). By default writes a `<stem>.no-graphics` sidecar (original untouched); `-D` overwrites in place. Relinks references to on-disk sources via a local sibling-directory walk plus a `dz fixpath --search-on local` fallback (`--no-relink` / `--no-fixpath` opt out; `--fence` opts into fence protection). stdlib-only; `dz fixpath` is an optional subprocess that degrades gracefully when `dz` isn't on PATH. 54 tests.
  - **`md-unwrap`** collapses hard-wrapped markdown paragraphs back to one line per paragraph (render-identical in any CommonMark/GFM viewer), preserving fenced code, HTML blocks, HTML comments, tables, recursive blockquotes, list items, headings, YAML frontmatter, hard-break trailing spaces, AND link reference definitions (`[label]: url` -- the fix that keeps CHANGELOG compare-links intact). stdin->stdout by default; `-i` rewrites in place, `-b` keeps a `.bak-pre-unwrap`, `--check` exits 1 if changes are needed. stdlib-only. 24 tests. (`dz md-unwrap -i <file>` is the un-wrapper referenced in the project's markdown conventions.)
  - **`md` virtual kit** (`kits/md.kit.json`): `md:unwrap` -> `dazzletools:md-unwrap`, `md:rm-img` -> `dazzletools:md-rm-img`. Both tools registered in the dazzletools kit.

### Notes

- `md-unwrap` graduated from amdead's `tests/one-offs/unwrap_markdown.py` (amdead `bfadf01` / `6a37f2d`), with the dazzlecmd-only LINK_REF_DEF pass-through added. `md-rm-img` was built in-repo (DWP 2026-04-26). Both landed now as the second 0.10.x new-tools release, ahead of the #58 packaging move. Verification: full suite green; the 54 + 24 tool-local tests pass; byte-gate dz-info goldens unaffected (clean checkout passes). dazzlecmd-lib unchanged.

### Versions

- dazzlecmd 0.10.0 -> 0.10.1 (PATCH); dazzle-dz -> 0.10.1. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.10.0] - 2026-06-21

> Opens the **0.10.x line** -- new-functionality releases landing the parked tool batch (each as its own release), ahead of the #58 packaging move and the eventual PyPI baseline.

### Added

- **`f-cp` / `f-mv` -- safe copy/move with full metadata preservation + the `f` virtual kit.** Two core tools that copy/move files while preserving `mtime`/`atime`/`ctime`, ACLs, and attributes, with clobber protection -- built as thin argparse shims over a shared adapter (`projects/core/_f_common/safe_ops.py`) that wraps [`preservelib`](https://github.com/dazzletools). `f-cp` exposes `--no-verify` (legitimate for copy -- no source-deletion invariant); **`f-mv` always verifies** -- the post-copy hash check is the gate for deleting the source and cannot be disabled, and in rename mode the copy step is slipped between verify and delete so the source survives any failure. If `preservelib` is absent, both tools **hard-fail with an install hint** -- no silent degradation. Includes POSIX rename-style detection, tempdir-staged same-directory conflict avoidance, and `ctime`-honesty derivation (the result only claims `ctime_restored` when preservelib's log confirms it). Registered in the core kit (`core:f-cp`, `core:f-mv`).
- **`f` virtual kit** -- a verb-grouped UX overlay for file operations: `f:cp`/`f:mv` resolve to the new tools, with additive convenience aliases `f:ls` -> `core:listall` and `f:rm` -> `core:safedel` (the canonicals are untouched).

### Notes

- Dependencies: `dazzle-preserve` (`preservelib`, required) + `pywin32` (optional, for Windows `ctime`/ACL preservation). 41 tool-local tests in `projects/core/_f_common/tests/test_safe_ops.py`. Provenance: built fresh 2026-05-16/17 as a `preservelib` adapter (git-snapshot `20260517-050312`); landed now as a standalone release ahead of the #58 packaging move. Deferred follow-ups: POSIX-rename integration tests, a human test checklist, a streaming-hash I/O optimization (current 5x read/write -> 3x), and publishing `dazzle-preserve` to PyPI.
- Verification: full suite green; byte-gate at the parked-WIP baseline (`dz info` unaffected); the 41 `_f_common` tests pass with `preservelib` installed. dazzlecmd-lib unchanged.

### Versions

- dazzlecmd 0.9.60 -> 0.10.0 (MINOR -- opens the 0.10.x new-tools line); dazzle-dz -> 0.10.0. dazzlecmd-lib unchanged (0.8.54); dazzle-lib unchanged (0.6.7).

## [0.9.60] - 2026-06-21

### Added

- **`[pointer]` marker for detached kits in `dz kit list` and `dz tree` (kit-lifecycle slice-4 step 4).** A detached kit carries a `pointer` block on its registry (written by `dz kit detach`): it is marked a pointer, so it loads no tools (the LOADING axis, orthogonal to the activation `[status]`). `dz kit list` now flags such a kit with a YELLOW `[pointer]` marker beside its status, a footer legend, and -- on drill-in (`dz kit list <kit>`) -- a `[..., pointer]` header tag plus a one-line "a pointer; tools not loaded; `dz kit attach <name>` to reconnect" note. `dz tree` surfaces detached kits as their own leaf branches (they never enter `by_kit` because they load no tools), mirroring how virtual kits render, with the count in the footer (`N detached pointer kit(s)`). The markers are conditional, so kits without a pointer block render byte-identically to before. Wording: "tools not loaded" (the LOADING axis), NOT "not materialized" -- a detached kit's files stay on disk (`materialized: true`); only its tools are unloaded. `materialized: false` (a not-yet-fetched remote pointer) is the #80 surface.
- **`dz tree --show-empty`** -- a reveal flag (sibling of `--show-disabled` / `--show-hidden`) that includes enabled kits with no tools as childless branches. Default off (the tree stays tool-centric, byte-identical to before). Restores detach->attach symmetry: a re-attached empty kit reappears under `--show-empty`, just as the detached one shows under `--show-disabled` with `[pointer]`.

### Notes

- Completes the slice-4 lifecycle surface (detach/attach + the visible pointer state). Refs #80 (pointer kits / materialization), #86. Verification: suite 1583 (+6: 3 kit-list + 3 tree); byte-gate identical (4 OK / 6 FAIL parked-WIP baseline; `dz info` is untouched). Full tree-branch repoint display (source-target arrows) stays with the #52/#80 repoint surface (0.10.x).

### Versions

- dazzlecmd 0.9.59 -> 0.9.60 (PATCH); dazzle-dz -> 0.9.60; dazzlecmd-lib 0.8.53 -> 0.8.54 (the renderer lives in the lib). dazzle-lib unchanged (0.6.7).

## [0.9.59] - 2026-06-20

### Added

- **`dz kit management [<kit>]` -- the lifecycle STATE view (state-on-invoke, like `dz kit visibility`).** `management` is the COMPOSED lifecycle axis (`{KitOff..KitOn}`) that fuses the activation/loading/membership sub-axes (a kit must be a member to load, loaded to activate). `dz kit management` shows each kit's POSITION on that unified continuum -- `active` / `disabled (loaded, inactive)` / `detached (pointer; not loaded)`, with `[always-active]` flagged; `dz kit management <kit>` filters to one. The per-axis groups now also show their slice with no verb: `dz kit activation` (active vs disabled), `dz kit loading` (loaded vs pointer), `dz kit membership` (members) -- replacing the v0.9.57 static summary. One shared handler (`_cmd_kit_management`); state read from the engine config (`disabled_kits`) + the registry pointer blocks (`KitMembershipContext.pointer_of`).

### Notes

- Completes the PoC's state-on-invoke parity with `dz kit visibility`. The unused `render_axis_summary` was removed. Verification: suite 1577; byte-gate identical (4 OK / 6 FAIL parked-WIP baseline). dazzlecmd-lib UNCHANGED. Refs #80, #86, #188.

### Versions

- dazzlecmd 0.9.58 -> 0.9.59 (PATCH); dazzle-dz -> 0.9.59. dazzlecmd-lib UNCHANGED (0.8.53). dazzle-lib unchanged.

## [0.9.58] - 2026-06-20

### Changed

- **`dz kit -h` is now a de-duplicated, by-axis hierarchy** (replacing the v0.9.57 over-verbose help, where verbs appeared in the usage line, the argparse positional list, AND the grouped epilog). `kit_parser.format_help` is overridden (after all subcommands register) to render: the usage line, a one-line orientation, then `inspect:` / `management:` (membership/loading/activation, each axis with its verbs nested) / `visibility:` (its verbs pulled up from the `dz kit visibility` sub-group) / `favorite:` / `options:`. Each verb appears exactly once; argparse's positional restatement is gone. The render is **registry-driven for structure** but reads each verb's **description from the actual sub-parsers** (`_kit_help_sources`) -- single source of truth, no duplicated help strings. This is the generalized-enough render that ships now; the cross-aggregator help *toolset* (help_lib adoption, the CLI-surface capability) remains the 0.10.x/0.11.x homogenization.

### Notes

- The flat verbs + the nested `dz kit <axis> <verb>` groups (v0.9.57) are unchanged; only the `-h` rendering changed. Verification: suite 1577 (the test_kit_verbs help tests re-pointed at the hierarchy); byte-gate identical (4 OK / 6 FAIL parked-WIP baseline; `dz kit -h` doesn't touch `dz info`). dazzlecmd-lib UNCHANGED. Refs #59, #57, #80, #86.

### Versions

- dazzlecmd 0.9.57 -> 0.9.58 (PATCH); dazzle-dz -> 0.9.58. dazzlecmd-lib UNCHANGED (0.8.53). dazzle-lib unchanged.

## [0.9.57] - 2026-06-20

### Added

- **Kit inverse-verb registry + nested per-axis groups -- the groupable/continuum CLI proof-of-concept.** `src/dazzlecmd/kit_verbs.py` declares the kit `{P, not-P}` verb-pairs (`KitVerbPair`: warm/cold/axis/coldward-rank/cascade-coupling), and `dz kit` gains nested per-axis groups mirroring `dz kit visibility`: `dz kit activation {enable,disable}`, `dz kit loading {attach,detach}`, `dz kit membership {add,remove}` (registry-driven via `build_lifecycle_axis_groups`). The flat verbs (`dz kit enable`/`attach`/`add`/...) are kept as aliases; both forms share one arg-spec (`VERB_SPEC`) and route to the same handler, so `dz kit activation enable` == `dz kit enable`. `dz kit <axis>` with no verb prints a short summary. This is the first cut showing the lifecycle continuum (activation < loading < membership, the coldward gradient with the implicit detach->disable cascade) driving the `dz kit *` surface.

### Notes

- **The `dz kit -h` help in this version is deliberately over-verbose** (the verbs appear in the usage line, the argparse positional list, AND the grouped epilog) -- committed AS-IS as the comparison baseline before the help is refined to the hierarchical by-axis view (next). The de-duplicated, generalized help rendering + the broader CLI/help/object homogenization are tracked for the 0.10.x/0.11.x line (DWP `2026-06-20__12-12-35`; epic issue drafted). Verification: suite 1571 -> 1577; byte-gate 4 OK / 6 FAIL (parked-WIP baseline; `dz kit -h` doesn't touch `dz info`). dazzlecmd-lib UNCHANGED (registry is in `src/dazzlecmd`). Refs #80, #86, #188, #84, #59.

### Versions

- dazzlecmd 0.9.56 -> 0.9.57 (PATCH); dazzle-dz -> 0.9.57. dazzlecmd-lib UNCHANGED (0.8.53). dazzle-lib unchanged.

## [0.9.56] - 2026-06-19

### Added

- **`dz kit attach <name>` -- kit-lifecycle slice 4, step 3 (the inverse of `detach`).** A detached (pointer) kit is loaded again AND enabled: `clear_pointer` (pointer -> loaded -- discovery loads its tools) composed with the activation `enable`. Attaching a kit that isn't a pointer is a friendly no-op (it does NOT enable a merely-disabled kit -- that's `dz kit enable`'s job). A `materialized:false` pointer (the #80 not-yet-fetched case) needs a fetch first -> routed to the deferred `_materialize_pointer` stub, which refuses cleanly until #80 lands. `--dry-run` prints the plan. The full `detach` -> `attach` round-trip restores the registry byte-identically and returns the kit to active.

### Notes

- The cascade is ASYMMETRIC (the per-coupling Gauss-Jordan structure made concrete): `detach`'s `loading -> inactive` is FORCED (you cannot dispatch what isn't loaded -- a pointer kit must be inactive), but `attach`'s `loading -> active` is a FREE choice -- defaulted to enable per the corrected detach-saga meaning ("upon attach -> enable"). A future `dz kit attach --no-enable` (land at loaded-but-disabled) is coherent but deferred (build-to-need), matching `detach`'s no-flag shape. End-to-end test pins the `detach -> attach` reload round-trip. Byte-gate identical (4 OK / 6 FAIL parked-WIP baseline); suite 1558 -> 1565. dazzlecmd-lib UNCHANGED (attach reuses the slice-2 `clear_pointer` + existing `ActivationContext.enable` -- the new code is all in `dz`'s `cli.py`). Refs #80/#86.

### Versions

- dazzlecmd 0.9.55 -> 0.9.56 (PATCH); dazzle-dz -> 0.9.56. dazzlecmd-lib UNCHANGED (0.8.53 -- no lib code changed). dazzle-lib unchanged.

## [0.9.55] - 2026-06-19

### Added

- **`dz kit detach <name>` -- kit-lifecycle slice 4, step 2 (the weak, keep-as-a-pointer pole).** Detach is a `CompositeTransition` across two presence axes: it writes a `pointer:{materialized:true}` block to the kit's `kits/<name>.kit.json` (LOADING -> pointer: discovery then LISTS the kit but loads none of its tools, via the slice-4-step-1 skip) AND disables the kit (the implicit `loading -> activation` cascade -- a detached kit is also deactivated). The files are KEPT on disk (`materialized:true`); de-materializing is a separate step (#80). Constitutional / `always_active` kits are refused (C3 -- they must stay loaded); only registered kits (with a `kits/<name>.kit.json`) can be detached; `--dry-run` prints the plan and changes nothing; the operation is idempotent. Re-attach with `dz kit attach` (next step). The strong, delete-the-files form is `dz kit remove`.
- **`KitMembershipContext` gains the LOADING-axis pointer operations (lib).** `set_pointer(kit, materialized=)` / `clear_pointer(kit)` / `pointer_of(kit)` add/remove/read the `pointer` block WITHIN the registry file (group/ungroup add/remove the file itself -- membership; these are loading). The registry is rewritten in the same `indent=4` shape `dz kit add` writes, so set-then-clear round-trips.

### Notes

- The implicit cascade is the per-coupling design from the slice-4 DWP (`2026-06-19__18-38-07`, addenda 1-3): the removal continuum's `loading -> activation` is a dependent pivot (detach ALWAYS disables -- no flag), while `loading -> materialization` is free (detach keeps the files; de-materialize is the separate #80 step). The Gauss-Jordan lens, declared not derived. An end-to-end test pins the detach->rediscover contract (the pointer block detach writes is the shape discovery consumes). Byte-gate identical (4 OK / 6 FAIL parked-WIP baseline); suite 1549 -> 1558. Refs #80/#86.

### Versions

- dazzlecmd 0.9.54 -> 0.9.55 (PATCH); dazzlecmd-lib 0.8.52 -> 0.8.53 (PATCH -- the `KitMembershipContext` pointer ops); dazzle-dz -> 0.9.55. dazzle-lib unchanged.

## [0.9.54] - 2026-06-19

### Added

- **Pointer-kit discovery skip -- kit-lifecycle slice 4, step 1 (the LOADING-axis pole).** A kit whose `kits/<name>.kit.json` carries a `pointer` block (written by the forthcoming `dz kit detach`, or a #80 not-yet-fetched pointer) is now DISCOVERED + LISTED (`dz kit list`/`tree`) but its tools are NOT loaded into the index (`engine._discover_aggregator` skips it from the load set). `discover_kits` carries the `pointer` block across the in-repo-manifest merge so it survives for kits with their own `.kit.json`. Default OFF -- no kit is a pointer unless detached -- so discovery + the byte-gate are unaffected. This is the substrate the `detach`/`attach` verbs (next steps) and #80 build on.

### Notes

- The removal/letting-go continuum design (slice-4 DWP `2026-06-19__18-38-07`): `disable < detach < remove` is ONE presence gradient; the cascade default is a PER-SPACE / per-coupling property (the removal continuum's `loading->activation` is a dependent pivot -> `detach` implicitly disables; `loading->materialization` is free -> de-materialize is separate). Byte-gate identical; suite +2 (pointer-skip + control). dazzle-lib unchanged.

### Versions

- dazzlecmd 0.9.53 -> 0.9.54 (PATCH); dazzlecmd-lib 0.8.51 -> 0.8.52 (PATCH -- the pointer discovery-skip + merge-carry); dazzle-dz -> 0.9.54. dazzle-lib unchanged.

## [0.9.53] - 2026-06-19

### Fixed

- **`dz mode status` no longer lists a nested aggregator's subdirectories as phantom tools.** The undiscovered-tool scan (`mode.cmd_status`) and `_find_undiscovered_tool` flat-scanned `projects/<ns>/<name>` and bucketed every `<name>` as a tool `<ns>:<name>` -- so a nested aggregator-as-kit like `projects/wtf/` (which has its own `kits/`) surfaced its structure dirs (`config`, `docs`, `kits`, `scripts`, `src`, `tests`) as phantom `wtf` tools (live: 43 -> 36 rows after the fix), and `dz mode switch <subdir>` could mis-resolve a non-tool directory. Fix: both scans now skip a directory that is itself an aggregator (`os.path.isdir(ns_dir/"kits")` -- the same marker the engine uses); its real tools are namespace-remapped (`<ns>:<inner-ns>:<tool>`) and resolved by the engine, not the flat scan. The second path-shape bug surfaced by the v0.9.52 audit.

### Versions

- dazzlecmd 0.9.52 -> 0.9.53 (PATCH); dazzlecmd-lib 0.8.50 -> 0.8.51 (PATCH -- the `mode.py` scan guards); dazzle-dz -> 0.9.53. dazzle-lib unchanged.

## [0.9.52] - 2026-06-19

### Fixed

- **`dz kit remove` now actually untracks a submodule kit (was a silent no-op).** The submodule detection reused the TOOL-only `parse_gitmodules` (which drops 2-part kit paths via its `len(parts) != 2` filter), so `is_submodule` was always `False` for any `dz kit add` kit (they live at `projects/<name>`, 2-part) -- the git untrack never fired, the dirty-guard was bypassed, and remove left an orphan staged gitlink + a stale `.gitmodules` section. Found by the tester-unbounded dummy-submodule run (HOLD). Fix: detect the kit submodule by reading `.gitmodules` directly (`_kit_is_submodule`); and the git sequence is now **non-destructive + recoverable** -- `git rm --cached` keeps the worktree so safedel can back it up, then the `.gitmodules`/`.git/config` sections are removed surgically via `git config --remove-section` (NOT `git submodule deinit`/`git rm -f`, which would delete the files *before* safedel could recover them), plus a read-only-aware `.git/modules` cache cleanup. Validated end-to-end in an isolated tmp git repo (`tests/one-offs/check_kit_remove_submodule.py`, 9/9 -- clean index, recoverable files, `.gitmodules`/`.git/config`/`.git/modules` all clean) plus 3 detection unit tests.

### Notes

- This is the exemplar of a "fixed path-depth assumption" bug class (assuming 3-part tool paths, not honoring 2-part kit paths). A full audit (general-purpose agent) confirmed `parse_gitmodules`'s 3-part filter is correct in all 7 OTHER callers and found one further instance: `dz mode status` / `_find_undiscovered_tool` flat-scan a nested aggregator's subdirs as phantom tools (tracked for a follow-up fix). No fixed-index FQCN-segment bugs (the codebase uses depth-robust first/last anchors). Byte-gate identical; suite green; dazzlecmd-lib UNCHANGED (0.8.50 -- the fix is in `dz`'s `cli.py`). Refs #80/#86.

### Versions

- dazzlecmd 0.9.51 -> 0.9.52 (PATCH); dazzle-dz -> 0.9.52. dazzlecmd-lib UNCHANGED (0.8.50). dazzle-lib unchanged.

## [0.9.51] - 2026-06-19

### Added

- **`dz kit remove <name>` -- the strong-remove pole of the kit lifecycle (slice 3).** Deregisters a kit (git untrack for a submodule -- `git submodule deinit` + `git rm` -- plus the registry entry, routed through the membership `ungroup` verb / `KitMembershipContext` from slice 2), `safedel`-trashes its `projects/<name>/` files (recoverable ~30d -- NEVER a raw delete), and drops any `active_kits`/`disabled_kits` refs. Constitutional / `always_active` kits are refused (C3); `--dry-run` prints the plan and changes nothing; an interactive confirm guards the delete (skip with `--yes`); a dirty submodule worktree is refused without `--force`. The source URL is recorded before any mutation for the re-add hint. The weak, keep-as-a-pointer form (`detach`) is the next slice.

### Notes

- The git-untrack path was rewound in the detach saga and is rebuilt here against the gold-standard spec (DWP `2026-06-18__04-49-12`). Unit tests cover the local-only path (registry ungroup + safedel + deactivate) + C3 + dry-run + not-found; the real `git submodule` surgery is covered by a human checklist (`tests/checklists/v0.9.51__...`). Byte-gate identical (the new `kit remove` verb doesn't touch `dz info`/`list` output); suite 1538 -> 1542. dazzlecmd-lib UNCHANGED at 0.8.50 (the new code is in `dz`'s `cli.py`, consuming the slice-2 lib context). Refs #80/#86; #52.

### Versions

- dazzlecmd 0.9.50 -> 0.9.51 (PATCH); dazzle-dz -> 0.9.51. dazzlecmd-lib UNCHANGED (0.8.50 -- no lib code changed). dazzle-lib unchanged.

## [0.9.50] - 2026-06-19

### Added

- **`KitMembershipContext` + the `membership` axis -- kit-lifecycle slice 2 (the gold-standard build).** Kit-in-aggregator membership is now a declared state axis: `build_default_registry()` registers `membership` with REVERSIBLE `group`/`ungroup` edges (conserved `kit_registration`), DISTINCT from the tool-in-kit `containment` axis (which keeps `local_incorporability`). `KitMembershipContext` (`contexts.py`) is the persisting SIBLING of `ContainmentContext` -- NOT a subclass: it runs the same Groupable group/ungroup verbs on the generic `TransitionContext`, but its substrate is the `kits/*.kit.json` registry FILES and it persists to disk (`group` registers a kit; `ungroup` deregisters it, capturing the bytes so the move round-trips byte-identically). C3 refuses ungrouping an `always_active` kit. This is the seam `remove` (slice 3) and `detach` (slice 4) compose onto.

### Notes

- Byte-transparent (no CLI surface consumes it yet): byte-gate identical at the parked-WIP baseline; suite 1534 -> 1538 (+ membership-edge / round-trip / C3 / sibling-not-subclass tests). No `dazzle-lib` change (consumer-side only). Build spec: the gold-standard DWP `2026-06-18__04-49-12` (its Reference Pattern + slices). Refs #80/#86; #52.

### Versions

- dazzlecmd 0.9.49 -> 0.9.50 (PATCH); dazzlecmd-lib 0.8.49 -> 0.8.50 (PATCH -- `membership` axis + `KitMembershipContext`); dazzle-dz -> 0.9.50. dazzle-lib unchanged (consumer-side only).

## [0.9.49] - 2026-06-19

### Added

- **`ActivationContext` (`dazzlecmd_lib.contexts`) -- `dz kit enable`/`disable` run on the generic transition executor.** The enable/disable verbs now route through `ActivationContext` (the activation analog of `VisibilityContext`): it runs on the lifted `TransitionContext`, so `reversible`/`conserved`/`kind` come from the DECLARED activation edges instead of hardcoded literals. The substrate is unchanged (`active_kits`/`disabled_kits`); the config writes + stdout are byte-identical; the move is recorded as an `ActivationReceipt` carrying `Transition.kind == "lateral"` (enable<->disable round-trips). `build_default_registry()` now declares the `enable`/`disable` activation transitions (REVERSIBLE) -- the B4 activation-as-Groupable seam the registry docstring anticipated; they are no longer "absent".

### Notes

- Byte-transparent: enable/disable config mutation + output unchanged (byte-gate identical at the parked-WIP baseline; suite 1531 -> 1534 with the activation round-trip / receipt-kind / registry-edge tests). The "production uses the new dazzle-lib symbols" grep now also hits `.kind` (`ActivationContext` reads the declared edge's `Transition.kind`). No `dazzle-lib` change (consumer-side only). Refs #188/#84; activation substrate for the #80/#86 capstone.

### Versions

- dazzlecmd 0.9.48 -> 0.9.49 (PATCH); dazzlecmd-lib 0.8.48 -> 0.8.49 (PATCH -- `ActivationContext` + declared activation transitions); dazzle-dz -> 0.9.49. dazzle-lib unchanged (consumer-side only).

## [0.9.48] - 2026-06-19

### Added

- **`ACTIVATION_CONTINUUM` (`dazzlecmd_lib.states`)** -- the kit-activation axis as a signed `Continuum` mirroring `VISIBILITY_CONTINUUM`: `active` is the neutral/fully-present pole (rank 0, a kit's default), `inactive` is suppressed (-1). Giving activation a Continuum (not just a value tuple) lets it COMPOSE as a presence axis. `ACTIVATION_VALUES` now DERIVES from it (`...levels()[::-1]`), byte-identical to the prior `("active","inactive")` literal.
- **The multi-axis kit-presence space -- the first production consumer of the SH-redesign's multi-axis `ContinuumSpace`.** `KIT_PRESENCE_SPACE` is now the PRODUCT of `visibility x activation` (`ContinuumSpace.compose(...)`, `presence=None`). The former single-axis aligned space is split out as **`VISIBILITY_PRESENCE_SPACE`** (the aligned visibility ladder whose merged spectrum the `dz kit visibility` navigator + `EntityState.coordinates_in` read); `KIT_PRESENCE_SPACE` composes it with `ACTIVATION_CONTINUUM`. The `dz kit visibility` navigator reads the aligned `KIT_PRESENCE_SPACE.axes["visibility"]` sub-space **byte-identically**, the SH pairwise `QuadrantView(visibility, activation)` now has a real production axis pair, and the product refuses cross-axis navigation by design (scale-safety). This is the production-resident substrate the activation re-expression (next) + the attach/detach capstone (#80/#86: visibility x activation x membership x materialization) build on.

### Changed

- `tests/test_states.py` `TestEntityStateAsPoint` (B1: "an `EntityState` is a point") evolved with the infrastructure: a point is located in the aligned `VISIBILITY_PRESENCE_SPACE` (the concept, preserved), and a new case asserts `KIT_PRESENCE_SPACE` is now the 2-axis product whose merged coordinate is refused at the product level and read per aligned sub-space.

### Notes

- Byte-transparent integration: `dz kit visibility` output unchanged (byte-gate identical at the parked-WIP baseline); suite 1530 -> 1531 (+ the product-shape test). The "production uses the new dazzle-lib symbols" grep flips from empty to a hit (`ACTIVATION_CONTINUUM` consumed in production). Refs #188/#84 (the redesign threads), #80/#86 (the capstone the substrate feeds).

### Versions

- dazzlecmd 0.9.47 -> 0.9.48 (PATCH); dazzlecmd-lib 0.8.47 -> 0.8.48 (PATCH -- `ACTIVATION_CONTINUUM` + the multi-axis `KIT_PRESENCE_SPACE` product); dazzle-dz -> 0.9.48. dazzle-lib unchanged (consumer-side composition only).

## [0.9.47] - 2026-06-18

### Changed

- **`ContinuumSpace` is now closed under composition (the functionally-complete composition algebra), via `dazzle-lib>=0.6.0`.** A dimension may be a `Continuum` or a `ContinuumSpace` (recursive); `ContinuumSpace.compose(...)` returns a `ContinuumSpace` (closure) and `normal_form()` folds arbitrary nesting to the flat leaf product -- so `{Continuum, ContinuumSpace, compose}` is complete the way `{+, x, ^}` is. Alignment (the single merged presence spectrum) is now a per-(sub-)space **property** rather than a hard requirement: aligned spaces (e.g. `KIT_PRESENCE_SPACE`) behave exactly as before; `compose`d product spaces hold differently-scaled dimensions and refuse cross-axis navigation by design (scale-safety). No dazzlecmd behavior change (suite 1530 + byte-gate identical; `KIT_PRESENCE_SPACE` byte-identical). Validated experiment-first by representing the arithmetic operation hierarchy in the system (`tests/one-offs/arithmetic_as_continuumspace_completeness.py`, 15/15): `+/-`,`x/div` = degenerate/commutative continuums (= "Groupables"), `^/log/root` = the full non-commutative continuum, `group` = the compression between levels. This finalizes the bedrock composition algebra ahead of the gold-standard kit-lifecycle build.

### Versions

- dazzlecmd 0.9.46 -> 0.9.47 (PATCH); dazzlecmd-lib 0.8.46 -> 0.8.47 (PATCH -- `dazzle-lib>=0.6.0` dep); dazzle-dz -> 0.9.47. dazzle-lib 0.5.0 -> 0.6.0 (closed-composition algebra).

## [0.9.46] - 2026-06-18

### Changed

- **`dazzlecmd_lib.groupable` renamed to `dazzlecmd_lib.contexts` (B3d).** Once the generic machinery lifted to the bedrock (B3a-B3c), the module's honest content is dazzlecmd's per-verb *contexts* (`AliasRebindContext`, `VisibilityContext`, `ContainmentContext`, `ProjectionContext`) + their `*Receipt`/`*Invariant` types + `KIT_PRESENCE_SPACE` + `Frame`, which BIND the bedrock's `TransitionContext` to dazzlecmd's substrates. Renamed via `git mv` (history preserved); all importers updated (`engine.py`, `mode.py`, `cli.py`, tests). No back-compat shim -- the module is internal (not re-exported by `__init__`), so it's a clean break, not a fallback. The lifted primitives are still re-exported at the top of `contexts.py`; `RebindError` remains a `TransitionError` alias.

### Added

- **Import-layering contract (`tests/test_layering.py`, B3e) -- the capstone of the lift.** A stdlib AST test (same idiom as dazzle-lib's `test_charter.py`, no import-linter dependency, always runs) that locks the downward-only layering `dazzlecmd -> dazzlecmd_lib -> dazzle_lib`: (A) `dazzlecmd_lib` never imports the `dazzlecmd` app; (B) the lift-shims (`continuum`/`states`/`contexts`) import their primitives FROM `dazzle_lib` (consume the bedrock, don't re-derive it); (C) `dazzle_lib` imports nothing from the consumers above it. Nothing can drift back into the bedrock without failing the suite.

### Versions

- dazzlecmd 0.9.45 -> 0.9.46 (PATCH); dazzlecmd-lib 0.8.45 -> 0.8.46 (PATCH -- module rename + layering contract); dazzle-dz -> 0.9.46. dazzle-lib unchanged (consumer-side only).

## [0.9.45] - 2026-06-18

### Changed

- **The generic transition executor lifted to the `dazzle-lib` foundation (B3c of the unification's lift).** `Receipt` + `TransitionContext` (and the typed failures `CriticalityBoundaryError` / `TransitionError`) moved to `dazzle_lib.transitions` (dazzle-lib 0.5.0; charter-safe: stdlib + `dazzle_lib.states` only). `dazzlecmd_lib.groupable` re-exports them, so every existing `from dazzlecmd_lib.groupable import ...` is unchanged; `RebindError` stays as a back-compat alias of `TransitionError`. The per-verb contexts (`AliasRebindContext`, `VisibilityContext`, `ContainmentContext`, plus mode switch / projection) keep binding the executor to their substrates and stay in dazzlecmd. `dazzlecmd-lib` now requires `dazzle-lib>=0.5.0`.
- **The executor's one consumer-coupling neutralized.** It reached into `entity.fqcn`; that is now a domain-neutral `identity_of` hook (the same shape as the `detect`/`write` hooks), and the generic `Receipt.entity_fqcn` field became `Receipt.entity_identity` (carrying B3b's `fqcn`->`identity` neutralization through to the executor). dazzlecmd's contexts pass `identity_of=lambda e: e.fqcn`; the per-verb `*Receipt` domain types keep their own `entity_fqcn` (it IS the dazzlecmd FQCN). Unlike B3a/B3b (verbatim lifts), this is a lift-with-generalization -- behavior-equivalence is proven by the suite (1527 passed + byte-gate unchanged). Move-code fidelity is still proven, adapted: `tests/one-offs/verify_transitions_lift.py` applies the enumerated seam transforms to the verbatim baseline and asserts the executor's `_edge`/`apply`/`undo`/`current` logic is AST-identical -- so ONLY the deliberate seam changes differ, nothing was dropped. The dead `Reversibility` import dropped from `groupable.py`.

### Versions

- dazzlecmd 0.9.44 -> 0.9.45 (PATCH); dazzlecmd-lib 0.8.44 -> 0.8.45 (PATCH -- groupable executor re-export shim + `dazzle-lib>=0.5.0` dep); dazzle-dz -> 0.9.45.

## [0.9.44] - 2026-06-17

### Changed

- **The generic state-system machinery lifted to the `dazzle-lib` foundation (B3b of the unification's lift).** The L0 types -- `StateAxis`, `EntityState`, `Transition`, `CompositeTransition`, `TransitionRegistry`, `Reversibility`, `OPEN`, `assert_round_trip`, `observe` -- moved to `dazzle_lib.states` (dazzle-lib 0.4.0; charter-safe: stdlib + the `Continuum` primitive only, no I/O). `dazzlecmd_lib.states` is now a **partial** shim: it re-exports those types (every `from dazzlecmd_lib.states import ...` is unchanged) and KEEPS what is genuinely dazzlecmd's -- the reference registry (`build_default_registry`, the MODE/VISIBILITY/KIND/ACTIVATION value sets, `VISIBILITY_CONTINUUM`). The bedrock ships the vocabulary; the consumer declares its instances. `dazzlecmd-lib` now requires `dazzle-lib>=0.4.0`. No behavior change (suite 1527 + byte-gate green). Verbatim-faithful: the lifted definitions are AST-identical to the pre-lift source (proven by `tests/one-offs/verify_states_lift.py`), per the move-code discipline.
- **Identity vocabulary neutralized in the bedrock.** The lifted state system named its identity field `fqcn` -- the *aggregator* addressing concept, which doesn't belong in the domain-neutral bedrock. Renamed to a generic `identity`: `EntityState.fqcn` -> `.identity`, `Transition.fqcn_fate` / `CompositeTransition.fqcn_fate` -> `.identity_fate`, `observe(reg, fqcn, ...)` -> `observe(reg, identity, ...)`, and the REVERSIBLE-edge error dropped the constitutional `C1` label. The concept is unchanged (dazzlecmd fills `identity` with its FQCN); only the dazzlecmd-specific NAME left the bedrock. Done before any consumer shipped against dazzle-lib 0.4.0. `verify_states_lift.py` proves the lift changed nothing *except* this decided neutralization.

### Versions

- dazzlecmd 0.9.43 -> 0.9.44 (PATCH); dazzlecmd-lib 0.8.43 -> 0.8.44 (PATCH -- states partial shim + `dazzle-lib>=0.4.0` dep); dazzle-dz -> 0.9.44.

## [0.9.43] - 2026-06-17

### Changed

- **The `Continuum` primitive lifted to the `dazzle-lib` foundation (B3a of the Groupable<->Continuum<->states unification's lift).** `Continuum`/`ContinuumSpace` + their protocols moved verbatim to `dazzle_lib.continuum` (dazzle-lib 0.3.0; its charter evolved "types only" -> "types + pure primitives", still stdlib-only + side-effect-free). `dazzlecmd_lib.continuum` is now a transparent re-export shim, so every existing `from dazzlecmd_lib.continuum import ...` is unchanged; `dazzlecmd-lib` declares `dazzle-lib>=0.3.0` as a dependency. The domain spaces (`VISIBILITY_CONTINUUM`, `KIT_PRESENCE_SPACE`) stay in dazzlecmd. No behavior change (suite 1527 + byte-gate green; the lift surfaced + fixed one module-location test). Also folds in the B3-pre test hygiene (`Continuum.compare`/positive-slice/amplified-cascade coverage; the misleading single-axis-GENERATIVE test clarified). The shared-package distribution (dazzle-lib on GitHub + PyPI, fresh install) is the lift's final test, deferred to the consumer-functional declaration.

### Versions

- dazzlecmd 0.9.42 -> 0.9.43 (PATCH); dazzlecmd-lib 0.8.42 -> 0.8.43 (PATCH -- continuum re-export shim + `dazzle-lib>=0.3.0` dep); dazzle-dz -> 0.9.43.

## [0.9.42] - 2026-06-17

### Added

- **`dz kit visibility ... --cascade` — apply a SLICE of presence rungs in one move (B2c of the Groupable<->Continuum<->states unification).** The general `ContinuumSpace` apply-mode: bare `--cascade` = slice-to-0 (subsume the current rung + all weaker toward neutral, e.g. `hide --cascade` also silences); `--cascade=down`/`=up[:N]` = toward a pole / N rung-steps; `--cascade=lo,hi` = a signed offset window (`+` = warmer / more visible). Additive (turns the slice's rungs on/off; leaves rungs outside it untouched); prints the affected rungs + their verbs; C3 applies the safe rungs but refuses the constitutional cold-pole (`shadowed`) rung. Default (no flag) is the single-rung write, unchanged. Backed by two pure `ContinuumSpace` primitives -- `slice` (a signed rung-step window) and `cascade_to_neutral` (the bare default) -- reusable by any presence-space surface in any app.

### Versions

- dazzlecmd 0.9.41 -> 0.9.42 (PATCH); dazzlecmd-lib 0.8.41 -> 0.8.42 (PATCH -- `ContinuumSpace.slice`/`cascade_to_neutral`); dazzle-dz -> 0.9.42.

## [0.9.41] - 2026-06-17

### Changed

- **`AliasRebindContext.apply` now runs on the generic `TransitionContext` (B2b-2 of the Groupable<->Continuum<->states unification).** The alias `rebind` executes through the one generic executor over the `routing` axis (`detect` = the alias's current canonical, `check` = the receiver-precondition, `write` = `repoint_alias`); its `RebindReceipt`'s `reversible` + conserved-invariant NAME now trace to the declared routing/rebind edge (`single_hop_rule`) rather than a hardcoded literal. Behavior is byte-identical (the receiver/existence guards, idempotence, short-index coherence). `undo` stays bespoke — it is ENTITY-FREE by design (repoints back without needing the new owner). This closes **B2b**: containment + rebind are migrated; `ProjectionContext` stays bespoke (a multi-valued add/remove-named-member shape, not a single-value axis move) and `mode.py`'s `ModeRebindContext` folds in when mode-switch becomes a Groupable verb.

### Versions

- dazzlecmd 0.9.40 -> 0.9.41 (PATCH); dazzlecmd-lib 0.8.40 -> 0.8.41 (PATCH -- `AliasRebindContext` on `TransitionContext`); dazzle-dz -> 0.9.41.

## [0.9.40] - 2026-06-17

### Changed

- **`ContainmentContext` now runs on the generic `TransitionContext` (B2b-1 of the Groupable<->Continuum<->states unification).** The `group`/`ungroup` in-tree membership verbs execute through the one generic executor (B2) — a `detect`/`write`/`check`/`invert` hook-set over the `containment` axis. Behavior is byte-identical (same idempotent add/remove, the GRADUATE `#73` refusal and the C3 "a constitutional item may be grouped/hidden but never ungrouped" refusal, the `ContainmentReceipt` shape), but `reversible` + the conserved-invariant NAME now trace to the declared containment edge (`local_incorporability`) in `build_default_registry()` rather than a hardcoded literal. `ProjectionContext` stays bespoke (a multi-valued add/remove-named-member shape, not a single-value axis move); `AliasRebindContext` migrates next (B2b-2).

### Versions

- dazzlecmd 0.9.39 -> 0.9.40 (PATCH); dazzlecmd-lib 0.8.39 -> 0.8.40 (PATCH -- `ContainmentContext` on `TransitionContext`); dazzle-dz -> 0.9.40.

## [0.9.39] - 2026-06-17

### Added

- **Generic `TransitionContext` + `Receipt` (dazzlecmd-lib) — the N-Contexts→1 collapse (B2 of the Groupable<->Continuum<->states unification).** One executor for any state axis: it resolves the DECLARED edge for `(verb, axis)` so a receipt's `reversible`/`conserved` come FROM the registry (not a hardcoded literal — the F3 "receipts stop hardcoding truth" intent), enforces `REFUSED_AT_BOUNDARY` generically, and orchestrates detect→check→write→Receipt. The per-axis substrate I/O + policy are small consumer-supplied hooks (`detect`/`write`/`check`/`invert`) bound to a handle, so `states`/`continuum` stay import-pure.

### Changed

- **`VisibilityContext` now runs on the generic `TransitionContext`** — byte-identical behavior (same direction guards + messages, the C3 cold-pole refusal, and the `VisibilityReceipt` shape incl. channel deltas), but its `reversible` + conserved-invariant NAME now trace to the declared visibility edge in `build_default_registry()` rather than being hardcoded. The visibility verb path is the first axis on the generic executor; containment/projection/rebind migrate onto it next (B2b), and the CLI `dz kit visibility` rung surface — a separate, unchanged encoding — unifies onto the verb path later (B2c).

### Versions

- dazzlecmd 0.9.38 -> 0.9.39 (PATCH); dazzlecmd-lib 0.8.38 -> 0.8.39 (PATCH -- generic `TransitionContext`/`Receipt`; `VisibilityContext` re-expressed over it); dazzle-dz -> 0.9.39.

## [0.9.38] - 2026-06-17

### Changed

- **`states.py` and `continuum.py` are now connected at L0 (B1 of the Groupable<->Continuum<->states unification).** A `StateAxis` may carry its signed/ordered backing as a `Continuum` -- the *StateAxis HAS-A Continuum* seam; when it does, the axis's ordered value set DERIVES from the continuum (one source -- no `values`/`ranks` drift) and a guard refuses a `values=` that disagrees with it. The pure `VISIBILITY_CONTINUUM` instance moved from `groupable.py` (L2) down into `states.py` (L0, where the state registry that DECLARES the axes owns it); `groupable.py` re-imports the SAME instance, so `KIT_PRESENCE_SPACE` and the visibility shims are byte-identical and `VISIBILITY_VALUES` now derives from it. No behavior change: `states.py` stays off the runtime dispatch path, the `dz kit visibility` surface is byte-identical, and both L0 modules stay import-pure.
- `build_default_registry()` docstring corrected: the VISIBILITY/CONTAINMENT/PROJECTION edges are declared (each added by the commit that made its verb a live Groupable method); only the ACTIVATION transitions remain absent (until `dz kit enable`/`disable` become Groupable verbs).

### Added

- **`EntityState.coordinates_in(space)`** -- locates an observed state as a POINT in a `ContinuumSpace` (its per-axis presence coordinate), the executable reading of "an `EntityState` is a point in the space"; `ContinuumSpaceProtocol` gains `axes` so the tie is cleanly typed.

### Versions

- dazzlecmd 0.9.37 -> 0.9.38 (PATCH); dazzlecmd-lib 0.8.37 -> 0.8.38 (PATCH -- `StateAxis.continuum` seam + `VISIBILITY_CONTINUUM` relocation + `EntityState.coordinates_in` + `ContinuumSpaceProtocol.axes`); dazzle-dz -> 0.9.38.

## [0.9.37] - 2026-06-17

### Fixed

- **`dz kit visibility {silence,hide,shadow} <short-name>` now resolves to the canonical FQCN before writing.** Previously a short name (e.g. `safedel`) was written verbatim, which never matched the FQCN-keyed filters (a silent inert no-op) AND let `shadow <short-name>` BYPASS the C3 constitutional guard. The verbs now resolve via the engine (dispatch-grade): a resolved short name writes the canonical FQCN (effective), an unresolved name warns instead of silently writing an inert entry, and C3 (a constitutional tool may be hidden but never shadowed) can no longer be dodged by passing the short name.

### Changed

- **Visibility verbs consolidated into one container-driven handler.** The six toggle handlers (silence/unsilence, hide/unhide, shadow/unshadow) collapse into a single `_cmd_kit_visibility_set` driven by the TYPED `VisibilityRung` payload now carried on `KIT_PRESENCE_SPACE`. The verb<->rung<->config binding lives in one typed object (the container), not per-handler string tables (`SUPPRESS`/`RESTORE`) and hardcoded config keys; `dz kit visibility status` reads the same rungs. This avoids the dict-everything regression the 0.8.x DazzleEntity migration removed (deeper `states.py` `Transition` unification tracked for #188).
- `dz kit visibility -h`: `status` is listed first (the generic inspect verb) ahead of the domain toggles.
- **`dz kit visibility status` is C3-aware**: for a constitutional tool at `hidden`, it annotates that `shadow` is refused (the cold rung is unreachable -- "hidden is the max veil") instead of recommending a move the surface would reject. The navigator no longer suggests dead-end actions.

### Added

- **`ContinuumSpace` typed-payload slot** (`payloads` + `payload_for`): each rung can carry a caller-supplied TYPED object (the "templated object"); the space holds + returns it opaquely (never interprets or calls it), so the primitive stays pure + domain-neutral while consumers get a typed object, not a string dict. `VisibilityRung` is the first payload.

### Versions

- dazzlecmd 0.9.36 -> 0.9.37 (PATCH); dazzlecmd-lib 0.8.36 -> 0.8.37 (PATCH -- `ContinuumSpace.payloads` + `VisibilityRung`); dazzle-dz -> 0.9.37.

## [0.9.36] - 2026-06-16

### Added

- **`dz kit visibility` -- one home for the presence verbs + a navigator.** The visibility toggles move under `dz kit visibility` (status, then silence/unsilence, hide/unhide, shadow/unshadow), de-cluttering the top-level `dz kit` menu from 16 subcommands to 10. `dz kit visibility status <fqcn>` is the `KIT_PRESENCE_SPACE` navigator: it shows the tool's presence level (visible/silenced/hidden/shadowed) and both neighbor moves -- the verb to run, labelled in the surface's own frame (`less visible` / `more visible`, not frame-leaking "stronger/weaker"). e.g. `hidden` -> less visible: `shadow`, more visible: `unhide`. Bare `dz kit visibility` lists every tool at a non-default rung INCLUDING hidden (which the old `dz kit silenced` query omitted).
- **`KIT_PRESENCE_SPACE`** (`groupable.py`) -- the visibility ladder as a `ContinuumSpace` presence axis; the seam the navigator reads and where activation / load axes will compose.

### Changed

- **`dz kit shadow <fqcn>` now refuses a constitutional tool (C3).** A constitutional item (e.g. `core:safedel`) may be hidden but never shadowed -- shadowing removes it from dispatch, and dz depends on it. Previously the shadow silently succeeded.

### Removed

- **Top-level `dz kit silence|unsilence|hide|unhide|shadow|unshadow` and `dz kit silenced`** -- moved under `dz kit visibility ...` (with `silenced` becoming the bare `dz kit visibility` overview). Pre-release surface change; no back-compat aliases.

### Versions

- dazzlecmd 0.9.35 -> 0.9.36 (PATCH); dazzlecmd-lib 0.8.35 -> 0.8.36 (PATCH -- `KIT_PRESENCE_SPACE`); dazzle-dz -> 0.9.36.

## [0.9.35] - 2026-06-16

### Added

- **`ContinuumSpace` -- composing N parallel `Continuum` axes on one shared PRESENCE scale.** A new pure dazzlecmd-lib type (in `continuum.py`), domain-NEUTRAL: each member axis is a distinct mechanism but all align to one SIGNED presence coordinate -- `<0` less present (cold), `0` the axis's neutral, `>0` more present (warm) -- so the non-zero coordinates form one strict merged order, the *spectrum*. `colder_than`/`warmer_than` navigate it, hopping axes at adjacent presence (e.g. `shadowed` on a visibility axis to `disabled` on an activation axis), so a surface can offer the "next stronger / next weaker" (or `--adjacent`) move across the whole verb family with no special-casing. **Presence is a GENERAL abstraction -- "how much of a quality is expressed" -- NOT tied to visibility:** it ranks wet/dry (water), hot/cold (heat), visible/hidden (listing), enabled/disabled (dispatch), priority, cost, ... It is the grouping<->ungrouping reading of `warm`/`cold` (warm = more present / group, cold = less present / ungroup); navigation is framing-NEUTRAL, so a surface binds "stronger/weaker" to its own figure pole. A caller-supplied `meaning` makes each space self-describing via `describe()` (interrogate what it measures + what fits). Membership is LOOSE -- structural (`ContinuumProtocol`) + a presence-alignment contract checked at construction, not inheritance -- keeping axes pure and effectful Contexts separate. `ContinuumSpaceProtocol` is the lift-to-`dazzle-lib` interface; the purity guard still holds. 18 tests (cross-axis + amplification navigation, the alignment/uniqueness contract, `meaning`/`describe`, the protocol).

### Notes

- **Generality validated against two composition shapes** (one-off proofs under `tests/one-offs/thinking/`): the presence spectrum (`continuumspace_presence_spectrum.py` -- visibility + activation share one warmth spine, "stronger than shadowed" hops to disabled) and the log-lib `intensity x tags` (`continuumspace_loglib_composition.py`). The loglib spike confirmed `Continuum` covers the loglib's intensity + the `passes()` gate exactly, and that `ContinuumSpace` correctly scopes to the *presence* composition: the loglib's channels are HOMOGENEOUS cursors on one Continuum (a sibling "CursorBank" shape), which `ContinuumSpace` rightly rejects (its merged-order uniqueness fires). Both compositions rest on `Continuum`; the dazzle-lib lift (#188) should name both.

### Versions

- dazzlecmd 0.9.34 -> 0.9.35 (PATCH); dazzlecmd-lib 0.8.34 -> 0.8.35 (PATCH -- new `ContinuumSpace` in the `continuum` module); dazzle-dz -> 0.9.35.

## [0.9.34] - 2026-06-16

### Added

- **`Continuum` -- the signed ordered-axis primitive (the bones of every Groupable verb's ladder).** A new pure, import-clean dazzlecmd-lib module (`continuum.py`): states totally ordered by a SIGNED rank with an invariant-bearing ZERO (`cold pole (-N) ... 0 (neutral/invariant) ... warm pole (+M)`), generalizing the THAC0 logger model so one primitive serves visibility, activation, the load spectrum, and log verbosity. Provides `rank`/`neutral`/`cold_pole`/`warm_pole`/`step`/`passes` (the THAC0 emit gate) + a channel backing (`channels_at`/`level_for_channels`), and the **`warm`/`cold` lens** directional framings ({P, not-P} / RGB-CMYK duality): `c.warm.more` / `c.cold.more` are unambiguous within a lens, cross-lens identity `warm.more == cold.less` (replaces an ambiguous bare `more`/`less`). A `ContinuumProtocol` is the lift-to-`dazzle-lib` interface; a purity guard keeps it effect-free so it can become a bedrock interface importable by every project. 23 tests, both backings.

### Changed

- **`VisibilityContext` re-homed onto the `Continuum`** (behavior-identical; the abstraction proving itself on a live, tested Groupable). `VISIBILITY_CONTINUUM` is the source of truth; direction enforcement (signed rank), channel presets, cold-pole C3 refusal, and undo all flow through it. `VISIBILITY_LADDER`/`VISIBILITY_ORDER`/`level_for_channels` remain derived shims (public surface intact). No dispatch/output change -- visibility tests + full suite green.

### Versions

- dazzlecmd 0.9.33 -> 0.9.34 (PATCH); dazzlecmd-lib 0.8.33 -> 0.8.34 (PATCH -- new `continuum` module + visibility re-home); dazzle-dz -> 0.9.34. (NOTE: 0.9.34-37 also exist on the abandoned `archive/detach-attach-v0.9.34-37` branch -- a preserved, rewound-past experiment; main's 0.9.34 is this Continuum work.)

## [0.9.33] - 2026-06-12

### Changed

- **`action` joins `DEFAULT_RESERVED_COMMANDS`.** Forward namespace protection for the planned `dz action <type> <dot-expr>` metadata-plane framework (#87: pluggable action types operating on annotations, `run` native first) -- reserving the verb now means no tool can squat the name before the framework lands. A tool named `action` can no longer be created in any aggregator; no existing tool uses the name. Regression test pins the reservation.

### Versions

- dazzlecmd 0.9.32 -> 0.9.33 (PATCH); dazzlecmd-lib 0.8.32 -> 0.8.33 (PATCH -- the reserved-set change is lib-side); dazzle-dz -> 0.9.33.

## [0.9.32] - 2026-06-12

### Fixed

- **Bare `dz kit` (no subcommand) crashed with NameError.** The v0.9.26 kit-list unification deleted dz's local `_cmd_kit_list` but the bare-`kit` dispatch branch still referenced it. Caught by CI's flake8 F821 gate on the first post-hold push -- the full suite, two tester passes, and the byte-gate all missed it because nothing exercised the bare form (the v0.9.26 acceptance check grepped for the *definition* being gone, not for stale *references*). Bare `dz kit` now routes to the same unified lib renderer as `dz kit list` (verified byte-identical) and a dispatch-level regression test pins it.

### Versions

- dazzlecmd 0.9.31 -> 0.9.32 (PATCH); dazzlecmd-lib 0.8.31 -> 0.8.32 (PATCH, lockstep -- no lib changes); dazzle-dz -> 0.9.32.

## [0.9.31] - 2026-06-11

**The wtf-windows kit/aggregator hookup is detached from the public repo.** It was wired in (as a git submodule + `kits/wtf.kit.json` pointer) to prove dazzlecmd's recursion story -- an aggregator embedding another aggregator, each able to incorporate the other -- and that proof is complete and regression-tested (`tests/test_engine_recursive.py`, including `CircularDependencyError` cycle detection for the mutual-embed case). wtf-windows is pre-release; the hookup returns when it reaches its public milestone. The public repo's `projects/wtf` pointer was also stale (it referenced an unpublished commit, breaking `--recurse-submodules` clones) -- detaching fixes that. Local development setups keep the kit by placing the checkout at `projects/wtf/` + the registry at `kits/wtf.kit.json` (both now gitignored). **Noted gap, promoted to the kit-lifecycle work (#52):** detaching took raw git surgery (`git rm --cached`, `.gitmodules` edit, ignore entries); `dz kit` has `add` but no `detach`/`remove` inverse.

### Versions

- dazzlecmd 0.9.30 -> 0.9.31 (PATCH); dazzlecmd-lib 0.8.30 -> 0.8.31 (PATCH, lockstep -- no lib changes); dazzle-dz -> 0.9.31.

## [0.9.30] - 2026-06-11

**Git subprocess calls are immune to hook-exported GIT_* environment variables.** git exports repo-location variables (GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, ...) to hook subprocesses -- so any `dz` git operation running under a git hook (e.g. a pre-push hook that runs the test suite, or `dz` invoked from a hook script) silently addressed the HOOK'S repository instead of the one named with `-C`: `rev-parse --show-toplevel` reports the cwd as toplevel when GIT_DIR is set (defeating the own-toplevel safety guards of v0.9.29), and write commands like `git subtree add` mutate the wrong repo. Found when the repo's own pre-push hook ran pytest and 4 sandboxed tests failed against dazzlecmd's working tree. Fix: new `dazzlecmd_lib.mode.sanitized_git_env()` strips the repo-location set (the `git rev-parse --local-env-vars` family; author/committer/ssh vars preserved) and EVERY production git call site passes it -- mode.py's dirty-tree pre-check + submodule add/update, dz's `_run_git` (all `--with` appliers and template clones), and `dz kit add`'s submodule add. Autouse conftest fixtures additionally strip the set for the test suite itself; regression tests pin the leak scenario verbatim (`tests/test_git_env_sanitization.py`).

### Versions

- dazzlecmd 0.9.29 -> 0.9.30 (PATCH); dazzlecmd-lib 0.8.29 -> 0.8.30 (PATCH; new `sanitized_git_env` export); dazzle-dz -> 0.9.30.

## [0.9.29] - 2026-06-11

**`--with common` and `--with template` are real (4d-6 -- RepoKit integration; completes the `dz new` redesign #35 cluster).** `common` adds the git-repokit-common subtree at `scripts/` (initializing git + an initial commit on a fresh scaffold, with local `core.autocrlf=false` and a racy-git index refresh -- both Windows-bitten in development); `template` resolves local-first (`new.repokit_template_path`) -> shallow-clone of git-repokit-template -> the lib-bundled FALLBACK-MINIMAL LICENSE/CONTRIBUTING stubs with a clear warning (OQ-D2/G), never overwriting scaffold files. Unavailability is a warning, never a block (OQ-G1). **Safety fix found by the hermetic tests:** ambient `rev-parse` discovery could walk up to an ANCESTOR repo (e.g. a scaffold under the user's home, itself a git repo) and subtree into the WRONG repository -- the applier now requires the target to be its own toplevel, else initializes a fresh nested-safe repo. Config: `new.repokit_common_url` / `new.repokit_template_path` / `new.repokit_template_url`. Delegation to repokit-the-tool tracked in git-repokit#14.

### Versions

- dazzlecmd 0.9.28 -> 0.9.29 (PATCH); dazzlecmd-lib 0.8.28 -> 0.8.29 (PATCH; ships templates/repokit_fallback/); dazzle-dz -> 0.9.29.

## [0.9.28] - 2026-06-11

**`--with` composable scaffolding components (4d-5).** `dz new aggregator <name> --with docker-test,docker-deploy,ci` (or `all`) layers reproducible-test/distribution Dockerfiles and GitHub Actions workflow stubs onto the scaffold. Composition is BEST-EFFORT (OQ-D1): a failed component warns and the rest continue, with an end summary (`--with summary: ok: ... | skipped: ...`). Unknown components fail clean BEFORE any disk writes. `common`/`template` (RepoKit) report unavailable with actionable hints until 4d-6 lands. Templates ship in the lib under `templates/__with__/` (the `__*__` convention keeps them out of language scaffolds).

### Versions

- dazzlecmd 0.9.27 -> 0.9.28 (PATCH); dazzlecmd-lib 0.8.27 -> 0.8.28 (PATCH; ships the __with__ templates); dazzle-dz -> 0.9.28.

## [0.9.27] - 2026-06-11

**Config reader tolerates a UTF-8 BOM.** PowerShell's `Out-File -Encoding utf8` writes a BOM; the config reader now uses `utf-8-sig` on its read paths (reads BOM'd and BOM-less files identically; the write path still never emits one). Found by the tester-unbounded run. Also: HV.6 verified live -- a wtf-windows checkout on lib 0.8.26 renders the FULL kit-list view (status brackets, wrapped descriptions, data-computed drill-in) with zero wtf-side changes.

### Versions

- dazzlecmd 0.9.26 -> 0.9.27 (PATCH); dazzlecmd-lib 0.8.26 -> 0.8.27 (PATCH); dazzle-dz -> 0.9.27.

## [0.9.26] - 2026-06-11

**Kit-list renderer unified into the lib (X-22-full bite 1).** `render_kit_list` gains `engine=None` -- the renderer-contract convention (renderers take the engine as the capability handle, like `render_info`). With the engine (which the registry handler already received and previously dropped) the renderer does everything dazzlecmd's custom handler did: config-aware enabled/disabled status, the #48 data-computed drill-in columns with wrapped descriptions, and the virtual-kit alias drill-in. dazzlecmd **deletes its 219-line `_cmd_kit_list`/`_render_virtual_kit_aliases`** and routes through the lib -- and every lib consumer (wtf-style aggregators) is UPGRADED from the legacy view to the full view for free. `engine=None` direct callers get the historical output unchanged. Verified: `dz kit list` / drill-in / virtual drill-in goldens byte-identical before/after.

### Versions

- dazzlecmd 0.9.25 -> 0.9.26 (PATCH); dazzlecmd-lib 0.8.25 -> 0.8.26 (PATCH); dazzle-dz -> 0.9.26.

## [0.9.25] - 2026-06-11

**`dz new aggregator` inside-an-aggregator guard.** The target is CWD-relative, so running it from within an existing aggregator's tree nested the new project there silently. Clobbering was already impossible (existing paths refused; verified empirically against a sandbox host -- `projects`/`kits` collisions refuse, the host's `aggregator.json` is untouched), but there was no warning. Now a loud stderr note explains the nesting and suggests `cd` elsewhere; the scaffold still proceeds (non-destructive, occasionally intentional). New regression test pins refusal + host-untouched + the warning.

### Versions

- dazzlecmd 0.9.24 -> 0.9.25 (PATCH); dazzlecmd-lib unchanged (0.8.25); dazzle-dz -> 0.9.25.

## [0.9.24] - 2026-06-11

**Embedded-aggregator kit descriptions + the rest of the magic-number sweep.** `dz kit list` showed no description for `wtf`: an embedded AGGREGATOR has no `.kit.json`, and the loader never fell back to its `aggregator.json` -- it now surfaces that description (identity fields still excluded; the registry pointer keeps naming authority). Also: the lib's legacy kit-list drill-in rows are width-aware (was a hardcoded 55-char cut); the `find_project_root` walk limit and the git/PowerShell subprocess timeouts are named constants (`GIT_CLONE_TIMEOUT` 120 / `GIT_UPDATE_TIMEOUT` 60 / `GIT_QUERY_TIMEOUT` 10 -- the clone-vs-update asymmetry is now documented).

### Versions

- dazzlecmd 0.9.23 -> 0.9.24 (PATCH); dazzlecmd-lib 0.8.24 -> 0.8.25 (PATCH); dazzle-dz -> 0.9.24.

## [0.9.23] - 2026-06-11

**`dz -h` long-name overflow fixed + display-layout constants (no behavior change).** The help epilog truncated descriptions against a fixed budget, so a tool name longer than the 16-char column (e.g. `claude-session-metadata`) pushed its description past the terminal edge and the terminal hard-wrapped the tail mid-word; each row now budgets from its ACTUAL printed prefix (still one line per tool). The display magic numbers are now named constants in the lib (`TERM_SIZE_FALLBACK`, `MIN_DESC_WIDTH`, `KIT_NAME_COL`, `SUMMARY_INDENT` + a `_term_width()` helper), consumed by both the lib renderers and dazzlecmd's CLI -- data-computed widths (the #48 discipline) remain the preferred pattern for columns.

### Versions

- dazzlecmd 0.9.22 -> 0.9.23 (PATCH); dazzlecmd-lib 0.8.23 -> 0.8.24 (PATCH); dazzle-dz -> 0.9.23.

## [0.9.22] - 2026-06-11

**`dz kit list` kit names render BOLD** -- the row anchor stands out (matches the lib's `render_kit_status`, which already bolded names). Color-gated (`should_use_color`): piped output stays plain, so scripts and the byte-gate see identical bytes. dazzlecmd-side only (`cli.py`'s custom kit-list handler); the lib is unchanged.

### Versions

- dazzlecmd 0.9.21 -> 0.9.22 (PATCH); dazzlecmd-lib unchanged (0.8.23); dazzle-dz -> 0.9.22.

## [0.9.21] - 2026-06-11

**Terminal-width-aware display: `dz kit list` descriptions wrap, `dz tree` fills the terminal.** Kit summary descriptions word-wrap with a hanging indent (the `dz list` discipline); `dz tree` and the flat-list fallback truncate to the REAL terminal width instead of hardcoded 57 chars. The #48 data-computed drill-in is untouched. `dz_tree` baseline refreshed (deliberate).

### Versions

- dazzlecmd 0.9.20 -> 0.9.21 (PATCH); dazzlecmd-lib 0.8.22 -> 0.8.23 (PATCH); dazzle-dz -> 0.9.21.

## [0.9.20] - 2026-06-11

**`dz new kit` and `dz new aggregator` are real (4d-2 / Tier 2B.1 — the v0.7.42 plan row, finally shipped).** The two v0.7.40 stubs are replaced with implementations per the Tier-2 scaffolding synthesis (OQ-A2): a **kit** is the local form — `dz new kit <name>` creates `projects/<name>/.kit.json` + the `kits/<name>.kit.json` registry pointer (opt-in activation) inside the current aggregator; an **aggregator** is *always standalone* — `dz new aggregator <name>` scaffolds a complete project (`aggregator.json`, `pyproject.toml` with console entry point, `src/<pkg>/cli.py` as the canonical thin dazzlecmd-lib consumer with the commented `nest_all_under` stub per OQ-E, smoke test, README, .gitignore). Both support `--with-starter` (a hello tool); aggregator flags: `--command`, `--description`, `--tools-dir`, `--manifest`, with defaults resolving CLI flag > config `new` section > built-in (4d-7). **Verified end-to-end:** a generated aggregator's own CLI (`mytools list`) discovers and dispatches its starter tool out of the box, and its generated smoke test passes.

### Added

- `dz new kit <name> [-d] [--with-starter]` and `dz new aggregator <name> [-c command] [-d] [--tools-dir] [--manifest] [--with-starter]`; the `aggregator/` template tree in `dazzlecmd_lib/templates/`; `tests/test_cli_new_scaffold.py` (9 tests incl. the generated-aggregator E2E run).

### Removed

- The v0.7.40 `new kit`/`new aggregator` stubs (exit-2 "not yet implemented" messages).

### Versions

- dazzlecmd 0.9.19 -> 0.9.20 (PATCH).
- dazzlecmd-lib 0.8.21 -> 0.8.22 (PATCH; ships the aggregator template).
- dazzle-dz alias -> 0.9.20; deps re-pinned to >=0.9.20 / >=0.8.22.

## [0.9.19] - 2026-06-11

**Fix the links fork — engine/CLI split completed + the constitutional boundary contract, enforced.** The user caught `links [lib]` rendering in `dz list`; recon found worse: the v0.9.4 relocation had copied the links tool's *entire file* (CLI included) into the lib **byte-identically**, and the tool was never rewired — two 28.6KB engines destined to drift, argparse/display dead weight inside the lib, and a `[lib]`/`Absolute:` claim describing a copy that wasn't the one running. Fixed to safedel-parity: the lib keeps the ENGINE only (detection, `LinkInfo`, `scan_directory`); the tool is now a thin CLI importing it. Golden-output capture proves the tool's help/table/JSON output is **byte-identical** before/after. The boundary contract (engine in lib; CLI in tool; no second engine; lib admission only when lib code itself needs the primitive) is now written in `core/__init__.py` and **enforced by `test_constitutional_contract.py`** — a constitutional name whose tool doesn't wrap its lib engine fails CI (verified to catch a revert of this very fix).

### Fixed

- `links [lib]` / `Absolute: dazzlecmd_lib:core:links` is now a true claim: `projects/core/links/links.py` wraps `dazzlecmd_lib.core.links` (was a self-contained byte-identical fork). The lib's `core/links/_detect.py` sheds its ~150-line CLI tail (`display_*`, `build_parser`, `main`).

### Added

- `tests/test_constitutional_contract.py` (lib): per-constitutional-name checks — engine package exists, tool imports it, tool defines no duplicate engine symbols. `core.links` exports widened (`scan_directory`, `matches_filter`, `canonicalize_target`, `ALL_LINK_TYPES`). Golden capture script `tests/one-offs/golden_links_v0.9.18/`.

### Versions

- dazzlecmd 0.9.18 -> 0.9.19 (PATCH).
- dazzlecmd-lib 0.8.20 -> 0.8.21 (PATCH).
- links tool 0.1.0 -> 0.1.1 (rewired onto the lib engine; CLI surface unchanged).
- dazzle-dz alias -> 0.9.19; deps re-pinned to >=0.9.19 / >=0.8.21.

## [0.9.18] - 2026-06-11

**Overlay + virtual-kit alias creation now routes through the Groupable verbs (the symmetric interface completed).** v0.9.10–9.11 *declared* overlay (`group`) and virtual-kit (`ungroup`) as the `{group, ungroup}` primitive on the PROJECTION axis, but the engine still materialized both with raw `fqcn_index.insert_alias` calls. They now dispatch through `entity.group()` / `entity.ungroup()` with a single new `ProjectionContext` — so the naming-axis symmetry has ONE mechanism, the conserved invariant (`canonical_fqcn`) is pinned where aliases are created, and `undo()` (drop the alias) makes the reversibility real. This also clarifies the cross-axis asymmetry: projection group/ungroup are both REVERSIBLE, vs the CONTAINMENT axis where graduation is GENERATIVE/one-way. Behavior is byte-identical (verified by the full suite + byte-gate). Overhead measured at ~0.5 µs/alias — ~0.05% of one `discover()`; benchmark in `tests/one-offs/bench_grouping_dispatch.py`.

### Added

- `groupable.ProjectionContext` / `ProjectionReceipt` — the runtime mechanism for the PROJECTION-axis group/ungroup (overlay / virtual kit). `FQCNIndex.remove_alias` — the inverse of `insert_alias` (the projection `undo`). `tests/one-offs/bench_grouping_dispatch.py`.

### Changed

- `engine._apply_constitutional_overlay` routes through `project.group(home, context=ProjectionContext(...))`; `engine._apply_virtual_kits` routes through `target.ungroup(alias, context=ProjectionContext(...))`. No user-visible change.

### Versions

- dazzlecmd 0.9.17 -> 0.9.18 (PATCH).
- dazzlecmd-lib 0.8.19 -> 0.8.20 (PATCH).
- dazzle-dz alias -> 0.9.18; deps re-pinned to >=0.9.18 / >=0.8.20.

## [0.9.17] - 2026-06-11

**`dz safedel list` defaults to the 10 most recent entries (new `--count` filter).** A long-lived trash store can hold hundreds of folders (e.g. 209); `dz safedel list` used to dump them all. It now shows only the **10 most recent** by default, with a clear note (`10 most recent of 209 folder(s) (--count 0 or --all to show all)`). `--count N` sets the cap; `--count 0` or `--all` shows everything. The library `cmd_list` default stays `None` (show all) so non-CLI consumers are unaffected.

### Added

- `dz safedel list --count N` (default 10) and `--all`. `core.safedel.cmd_list` gains a `count` param (most-recent-N cap; `None`/0 = all).

### Versions

- dazzlecmd 0.9.16 -> 0.9.17 (PATCH).
- dazzlecmd-lib 0.8.18 -> 0.8.19 (PATCH).
- safedel tool 0.1.0 -> 0.1.1 (new `--count`/`--all` flags).
- dazzle-dz alias -> 0.9.17; deps re-pinned to >=0.9.17 / >=0.8.19.

## [0.9.16] - 2026-06-11

**`dz list` footer marker legend: word-boundary wrapping + colorized markers.** The `[*]`/`[+]`/`[lib]` legend was emitted as one long line and the terminal hard-wrapped it mid-word (e.g. `alias` → `ali`/`as`). It now wraps at word boundaries with a hanging indent — continuation lines align under the start of the text so the marker stands out — mirroring tool-description wrapping. The marker token is also colorized to match the row markers (`[*]` bold-red, `[+]` cyan, `[lib]` green); width/indent math uses the plain marker length so ANSI never disturbs alignment, and color is off for pipes/byte-gate.

### Fixed

- `dz list` footer legend wrapped mid-word and ignored terminal width; now word-wraps with a hanging indent (`_print_legend_entry`).

### Changed

- `dz list` footer legend markers are colorized to match the in-list markers.

### Versions

- dazzlecmd 0.9.15 -> 0.9.16 (PATCH).
- dazzlecmd-lib 0.8.17 -> 0.8.18 (PATCH).
- dazzle-dz alias -> 0.9.16; deps re-pinned to >=0.9.16 / >=0.8.18.

## [0.9.15] - 2026-06-10

**#37 Tier-1 closeout: PowerShell links + aggregator-name audit.** Two of the remaining (non-parked) #37 Tier-1 acceptance criteria. The constitutional `core.links.create_link` now creates Windows directory links via PowerShell `New-Item` (SymbolicLink → Junction fallback) instead of `cmd /c mklink`, which fails silently when invoked as a subprocess from bash/WSL (CLAUDE.md rule #4 self-violation). A `mode.py` audit for aggregator-name hardcoding found one user-facing string (the `ModeRebindContext.undo()` error said `dz mode restore` literally) and fixed it to use the aggregator's `command` — so wtf-windows/amdead see their own CLI name. (Tier-3 convenience features `mode status --complete` / `switch --all` remain parked per the issue, awaiting concrete user demand.)

### Changed

- `core.links._create_link_windows`: PowerShell `New-Item -ItemType SymbolicLink/Junction` (reliable exit codes across invocation contexts; correct single-quote path escaping for spaces). `ModeRebindContext.undo()` error uses `self.command`, not a hardcoded `dz`.

### Added

- `packages/dazzlecmd-lib/tests/test_core_links.py` — create/remove round-trip, spaced-path quoting (the PowerShell-rewrite regression), occupied-target refusal.

### Versions

- dazzlecmd 0.9.14 -> 0.9.15 (PATCH).
- dazzlecmd-lib 0.8.16 -> 0.8.17 (PATCH).
- dazzle-dz alias -> 0.9.15; deps re-pinned to >=0.9.15 / >=0.8.17.

## [0.9.14] - 2026-06-10

**Refactor (DRY): consolidate the two trash-recovery loops.** `cmd_recover` (fuzzy time-pattern, multi-folder) and the new `recover_folder` (exact-name, single-folder) shared their per-entry recovery loop; it's now extracted into one private `_recover_folder_entries` helper that both call. No behavior change — each keeps its own folder-resolution front-end, remove-on-success policy, and summary wording. `recover_folder` gains `metadata_only` parity.

### Changed

- `dazzlecmd_lib.core.safedel._recover`: extracted `_recover_folder_entries(store, folder, …)`; `cmd_recover` + `recover_folder` delegate the shared loop to it. Pure internal refactor (suite + byte-gate unchanged).

### Versions

- dazzlecmd 0.9.13 -> 0.9.14 (PATCH).
- dazzlecmd-lib 0.8.15 -> 0.8.16 (PATCH).
- dazzle-dz alias -> 0.9.14; deps re-pinned to >=0.9.14 / >=0.8.16.

## [0.9.13] - 2026-06-10

**#37 mode-swap reversibility — `dz mode restore` (the symmetric inverse of a dev switch).** Building on the 0.9.12 origins foundation: `dz mode restore <tool>` reads the recorded origin and re-materializes the prior on-disk form — the *group* that inverts the dev-switch *ungroup*. An EMBEDDED origin recovers the exact backed-up content from the safedel trash; a SUBMODULE origin re-clones via `git submodule update --init`. Refuses cleanly when there's no origin, the tool isn't in dev mode, or the backup is gone; for the EMBEDDED path the symlink is removed only after a pre-check, and a recovery failure re-creates the symlink (best-effort rollback) so the tool is never left missing. `dz mode restore <tool> --dry-run` previews. The state system reclassifies EMBEDDED→SYMLINK as REVERSIBLE (the inverse mechanism now exists) while LOCAL_ONLY stays ONE_WAY.

### Added

- `dz mode restore <tool>` (+ `--dry-run`): CLI subcommand, `mode.cmd_restore`, and a `recover_folder` primitive in `dazzlecmd_lib.core.safedel` for exact-name programmatic recovery (safedel API v2).

### Changed

- `states`: EMBEDDED→SYMLINK is REVERSIBLE (conserved `embedded_content`); LOCAL_ONLY→SYMLINK stays ONE_WAY. `ModeRebindContext.undo()` on an out-of-orbit entry now points the user at `dz mode restore`.

### Versions

- dazzlecmd 0.9.12 -> 0.9.13 (PATCH).
- dazzlecmd-lib 0.8.14 -> 0.8.15 (PATCH).
- dazzle-dz alias -> 0.9.13; deps re-pinned to >=0.9.13 / >=0.8.15.

## [0.9.12] - 2026-06-10

**#37 mode-swap reversibility — origins-tracking foundation.** Entering dev mode (`dz mode switch <tool>`) is an *ungroup* (the tool's content leaves the tree; a symlink replaces it); coming back is the *group*. This slice records what was there before so the symmetric restore (next slice) can re-materialize it. `mode_local.json` gains an `origins` key (schema **v2**, transparently migrated): for each tool that entered dev mode it stores the prior on-disk form (`embedded`/`submodule`), the safedel backup pointer (EMBEDDED only — SUBMODULE re-clones from `.gitmodules`), the original path (rename cross-check), and a timestamp. Origins are written after the symlink lands (never for an aborted swap) and cleared when the user intentionally moves to publish. No user-visible behavior yet — `dz mode restore` arrives next.

### Added

- `mode._record_origin` / `_clear_origin` helpers + `origins` in `mode_local.json` (schema v1→v2). `_remove_tool_dir` now returns `(rc, trash_folder)` so the switch path can capture the safedel backup pointer.

### Versions

- dazzlecmd 0.9.11 -> 0.9.12 (PATCH).
- dazzlecmd-lib 0.8.13 -> 0.8.14 (PATCH).
- dazzle-dz alias -> 0.9.12; deps re-pinned to >=0.9.12 / >=0.8.14.

## [0.9.11] - 2026-06-10

**Phase 2 — the overlay body: the constitutional home is a real FQCN-index entry (FQCN-identity DWP Phase 2, slice 2).** The overlay grouping transition declared in 0.9.10 now materializes: each constitutional tool's home canonical (`dazzlecmd_lib:core:safedel`, Scheme O / "bones") is registered in the FQCN index as a real **overlay alias** pointing at the surfaced projection (`core:safedel`, Scheme P / "skin"). `dz dazzlecmd_lib:core:safedel` now dispatches through the real index — the v0.9.9 `_absolute_to_local` lib-prefix string-rewrite special-case is **deleted**; only this aggregator's own redundant self-prefix is still string-stripped. `[lib]` stops being a special-case: the overlay rides the same alias machinery as virtual kits, in the opposite (grouping) direction. The alias is dispatch-only (the auto-realpath precedent) — `dz list` stays byte-identical (overlay shown via `[lib]` + epilogue, never a `[+]` or an alias row).

### Added

- `engine._apply_constitutional_overlay` — registers each constitutional home FQCN as a `source="overlay"` alias in the FQCN index (the runtime artifact of the PROJECTION-axis `group` transition). `dz info <home-fqcn>` shows overlay provenance.

### Changed

- `engine._absolute_to_local` now strips only this aggregator's own self-prefix; cross-home (constitutional) absolutes resolve through the real overlay alias. Overlay aliases are excluded from the `dz list` `[+]`/alias-row surfaces (dispatch-only, shown via `[lib]`).

### Versions

- dazzlecmd 0.9.10 -> 0.9.11 (PATCH).
- dazzlecmd-lib 0.8.12 -> 0.8.13 (PATCH).
- dazzle-dz alias -> 0.9.11; deps re-pinned to >=0.9.11 / >=0.8.13.

## [0.9.10] - 2026-06-10

**Phase 1→2 — overlay declared as a grouping transition in the state system (FQCN-identity DWP Phase 2, slice 1: the contract).** Virtual kits and overlays are the two directions of the `{group, ungroup}` primitive on a new PROJECTION (naming) axis — a virtual kit **ungroups** (splits a canonical into alias names), an overlay **groups** (collapses a home namespace onto a consumer surface, e.g. `dazzlecmd_lib:core` onto `dazzlecmd:core`). Both conserve the canonical FQCN. Declared as data (the graduation precedent); the FQCN-index re-root body — making the home canonical a real index entry with the projection as an alias, replacing the v0.9.9 `_absolute_to_local` shim — is the next slice.

### Added

- `states` PROJECTION axis + `group`(overlay)/`ungroup`(virtual-kit) transitions. Tests updated (group/ungroup now span containment + projection).

### Versions

- dazzlecmd 0.9.9 -> 0.9.10 (PATCH).
- dazzlecmd-lib 0.8.11 -> 0.8.12 (PATCH).
- dazzle-dz alias -> 0.9.10; deps re-pinned to >=0.9.10 / >=0.8.12.

## [0.9.9] - 2026-06-10

**Phase 1 base finalization — absolute FQCNs are always honored (resolvable everywhere).** A real path now resolves like the prefixless name: `dz dazzlecmd:core:f-cp` ≡ `dz core:f-cp`, and `dz info dazzlecmd_lib:core:safedel` resolves to safedel (both previously failed with "invalid choice" / "not found"). `dz list` stays prefixless (the aggregator prefix is redundant in its own runtime) but gains a `[lib]` epilogue legend explaining the absolute FQCN + the constitutional `dazzlecmd_lib:core:` home.

### Added

- `engine._absolute_to_local` normalizes absolute→local at the `resolve_command` chokepoint (covers dispatch + `dz info`). `dz list` `[lib]` legend.

### Fixed

- `dz info` / dispatch now resolve absolute FQCNs (`dazzlecmd:core:*`, `dazzlecmd_lib:core:<constitutional>`).

### Versions

- dazzlecmd 0.9.8 -> 0.9.9 (PATCH).
- dazzlecmd-lib 0.8.10 -> 0.8.11 (PATCH).
- dazzle-dz alias -> 0.9.9; deps re-pinned to >=0.9.9 / >=0.8.11.

## [0.9.8] - 2026-06-10

**Phase 1 base finalization — absolute FQCN is now a real, derivable core concept; walk back the v0.9.7 fake `Canonical:` field.** v0.9.7 shipped a `dz info … Canonical: dazzlecmd_lib:core:safedel` line that **wasn't dispatchable** (a fake rival FQCN, only on constitutional tools). It's replaced by `Absolute:` — the TRUE globally-unique FQCN, derived via the new `engine.absolute_fqcn`, shown for EVERY tool. The prefixless `core:safedel` is a projection of the absolute (`dazzlecmd:core:f-cp` for native, `dazzlecmd_lib:core:safedel` for overlaid constitutional tools). The dispatchable-home-canonical + overlay-as-Groupable model is the **gated Phase 2** (see the FQCN-identity DWP).

### Added

- `dz info` `Absolute:` line for all tools; `AggregatorEngine.absolute_fqcn(project)` (a real, always-derivable core method).

### Removed

- The v0.9.7 fake `Canonical:` line (non-dispatchable rival FQCN, constitutional-only).

### Versions

- dazzlecmd 0.9.7 -> 0.9.8 (PATCH).
- dazzlecmd-lib 0.8.9 -> 0.8.10 (PATCH).
- dazzle-dz alias -> 0.9.8; deps re-pinned to >=0.9.8 / >=0.8.10.

## [0.9.7] - 2026-06-10

**Phase 1 base finalization — constitutional core identity in `dz list` / `dz info` (#179 follow-up).** After relocating safedel + links into the lib's constitutional `dazzlecmd_lib.core` namespace, `dz list` now marks them `[lib]` and `dz info` shows their canonical FQCN (`dazzlecmd_lib:core:safedel`), distinguishing them from ordinary `core:` kit tools. The canonical (bones) is the real home; `core:safedel` is the projection (skin).

### Added

- `dz list` `[lib]` marker on constitutional core tools; `dz info` `Canonical:` line. The `dazzlecmd_lib.core.is_constitutional`/`canonical_fqcn`/`constitutional_names` API. `tests/test_constitutional_identity.py` (5).

### Changed

- Byte-gate: 5 surfaces (4 `dz list` variants + `dz info core:safedel`) re-baselined for this deliberate display change — the first intentional output change since the v0.7.54 byte-identical-migration anchor.

### Versions

- dazzlecmd 0.9.6 -> 0.9.7 (PATCH).
- dazzlecmd-lib 0.8.8 -> 0.8.9 (PATCH; the constitutional-identity API + display).
- dazzle-dz alias -> 0.9.7; deps re-pinned to >=0.9.7 / >=0.8.9.

## [0.9.6] - 2026-06-10

**Phase 1 base finalization — the safedel engine dedup completes (slice 3 of 3; #38 reframe / #179).** The `projects/core/safedel/` tool now imports its engine from the lib (`dazzlecmd_lib.core.safedel`); the duplicate tool-side engine modules are removed (one engine, in the lib — no duplication). Verified end-to-end: `dz safedel` delete → list → recover round-trips off the lib engine.

### Changed

- safedel tool (`safedel.py` CLI + `api.py` shim + 12 test files) imports the engine from the lib. The 7 duplicate engine modules are removed (preserved in `private/revisions/` per convention, not deleted).
- `dazzlecmd-lib` gains a Windows-only `unctools` dependency (the trash engine's per-volume routing needs Windows drive-type detection). Flagged for review.

### Removed

- `projects/core/safedel/{_store,_platform,_classifier,_recover,_timepattern,_volumes,_zones}.py` — the duplicate engine, now lib-only.

### Versions

- dazzlecmd 0.9.5 -> 0.9.6 (PATCH).
- dazzlecmd-lib 0.8.7 -> 0.8.8 (PATCH; tool imports lib engine + win32 `unctools` dep + a latent-import fix).
- dazzle-dz alias -> 0.9.6; deps re-pinned to >=0.9.6 / >=0.8.8.

## [0.9.5] - 2026-06-10

**Phase 1 base finalization — `dz mode switch` removes via the lib `core.safedel` primitive; the fallback is GONE (slice 2 of 3; #38 reframe / #179).** The mode swap previously loaded the safedel tool from the tools dir and fell back to `shutil.rmtree` when it was absent (wtf/amdead). That tool-loading shim + the fallback are DELETED — removal now always goes through the constitutional `dazzlecmd_lib.core.safedel` primitive (no fallback paths; the capability is internal to the lib). CLI byte-identical for the gated surfaces.

### Added

- `dz mode switch --immediate` — delete the old tool directory immediately with NO recovery backup (the default stages it to the recoverable trash store; recover with `dz safedel recover last`). A deliberate choice, not a fallback.

### Removed

- The `_load_safedel_api` tool-loading shim + the "safedel absent → rmtree" fallback branch in `mode.py`. No dead-code paths.

### Versions

- dazzlecmd 0.9.4 -> 0.9.5 (PATCH; CLI byte-identical).
- dazzlecmd-lib 0.8.6 -> 0.8.7 (PATCH).
- dazzle-dz alias -> 0.9.5; deps re-pinned to >=0.9.5 / >=0.8.7.

## [0.9.4] - 2026-06-10

**Phase 1 base finalization — recoverable-delete becomes a constitutional lib primitive (slice 1 of 3; #38 reframe / #37).** The recoverable-delete engine is relocated from the `projects/core/safedel/` tool into `dazzlecmd_lib.core.safedel`, so every aggregator gets it automatically. This is the foundation for **removing the mode-swap "safedel absent → rmtree" fallback** — no fallback paths: the capability is internal to the lib, so there is no "absent" case. This slice is purely additive (the lib gains the engine; mode.py adoption + the tool rewire follow). CLI byte-identical.

### Added

- `dazzlecmd_lib.core.safedel` (the relocated engine) + `dazzlecmd_lib.core.links` link-detection re-exports. `packages/dazzlecmd-lib/tests/test_core_safedel.py` (4).

### Changed

- `dazzlecmd-lib` gains a `dazzle-filekit>=0.2.2` runtime dependency (cross-platform metadata preservation — the canonical home of that code).

### Versions

- dazzlecmd 0.9.3 -> 0.9.4 (PATCH; CLI byte-identical).
- dazzlecmd-lib 0.8.5 -> 0.8.6 (PATCH; additive — the `core.safedel` primitive).
- dazzle-dz alias -> 0.9.4; deps re-pinned to >=0.9.4 / >=0.8.6.

## [0.9.3] - 2026-06-10

**Phase 1 base finalization — `dz mode switch` now works for embedded tools (#37 Phase-3.5 Bucket D, items 3.5-1 / 3.5-12).** Previously a tool checked out directly into the aggregator tree (STATE_EMBEDDED, e.g. imported via `git clone`/subtree/copy) could not be mode-switched — `dz mode switch <tool>` printed "no mode toggle available". It now toggles an embedded checkout to a dev symlink. This was gated on data safety and is unblocked by v0.9.2: the embedded directory (whose content exists ONLY in this checkout) is staged to safedel's recoverable trash store before removal.

### Added

- `mode_local.json` now carries a `_schema_version` stamp (item 3.5-12) so a future on-disk format change can migrate old configs.

### Changed

- `dz mode switch <embedded-tool>` toggles to dev (symlink) instead of refusing (item 3.5-1). Use `--publish` to register a submodule instead; `--path` points at the local dev repo. The embedded content is recoverable via `dz safedel recover last` after the swap.

### Deferred (next Bucket D slice)

- `origins` tracking + restore-to-embedded, `dz mode status --complete`, `dz mode switch --all`, and backup list/clean remain open under #37 (they need the restore consumer; tracked in the Act-II audit).

### Versions

- dazzlecmd 0.9.2 -> 0.9.3 (PATCH; CLI byte-identical).
- dazzlecmd-lib 0.8.4 -> 0.8.5 (PATCH; additive).
- dazzle-dz alias -> 0.9.3; deps re-pinned to >=0.9.3 / >=0.8.5.

## [0.9.2] - 2026-06-10

**Phase 1 base finalization — recoverable mode swaps via safedel (#38 / Phase-3.5 item 3.5-10).** `dz mode switch` previously removed a tool directory (a submodule checkout or embedded dir) with an unrecoverable `shutil.rmtree`. It now stages that directory to safedel's recoverable trash store first — a mistaken switch is recoverable via `dz safedel recover last`. This is the foundation for #37's embedded-swap backup machinery (Bucket D). CLI is byte-identical (the change is on the destructive write path only).

### Added

- `projects/core/safedel/api.py` — safedel's stable public API surface (`stage_to_trash`, `safe_delete`, `classify`, `TrashStore`, `TrashEntry`, `TrashResult`, `StoreStats`; `__api_version__ = "1"`). The importable entry point other dazzlecmd code uses to delete recoverably. Closes the near-term scope of #38.
- `dazzlecmd-lib` `mode._load_safedel_api` + `_remove_tool_dir_recoverable` — locate + load safedel anchored on the aggregator's `project_root`, and remove a tool dir recoverably at both swap sites. `tests/test_mode_safedel.py` (7) + the import-mechanism DWP.

### Changed

- The existing dirty-tree gate (T1-E) still refuses on uncommitted changes; safedel adds a recovery backup on top. A backup failure aborts the swap (nothing deleted) unless `--force`. Aggregators without safedel (wtf-windows, amdead) keep the prior `rmtree` behavior with a note — the "clean tree switches freely" contract is preserved.

### Versions

- dazzlecmd 0.9.1 -> 0.9.2 (PATCH; CLI byte-identical).
- dazzlecmd-lib 0.8.3 -> 0.8.4 (PATCH; additive — `_load_safedel_api` + recoverable removal).
- dazzle-dz alias -> 0.9.2; deps re-pinned to >=0.9.2 / >=0.8.4.

## [0.9.1] - 2026-06-10

**Phase 1 base finalization — dazzlecmd-lib version-record reconciliation.** The library's `_version.py` and CHANGELOG had frozen at `0.7.17` (dazzlecmd v0.8.21) while `pyproject.toml` walked to `0.8.3` (dazzlecmd v0.8.22–v0.8.34). The public attribute `dazzlecmd_lib.__version__` (re-exported from `_version.py`) therefore reported `0.7.17` for a `0.8.3` package, and the lib CHANGELOG omitted all 11 of those versions — including the headline **BREAKING 0.8.0** dict-shim deletion. dazzlecmd's CLI is byte-identical (a `chore(lib)` record fix); the library's actual version is unchanged at 0.8.3.

### Fixed

- `dazzlecmd-lib` `_version.py` corrected `0.7.17` -> `0.8.3` to match the shipped package (a correction, not a version bump — the lib stays 0.8.3).
- `dazzlecmd-lib` CHANGELOG backfilled with the missing entries 0.7.18 through 0.8.3 (reconstructed from the per-commit history), so the record finally documents the state-system steps and the breaking 0.8.0 shim deletion.

### Changed

- `dazzlecmd-lib` `pyproject.toml` now derives its version dynamically from `_version.py` (`[tool.setuptools.dynamic]`, mirroring dazzlecmd's own root pyproject) — single-sourcing the version so the static-pyproject vs `_version.py` drift that caused this can't recur.

### Versions

- dazzlecmd 0.9.0 -> 0.9.1 (PATCH; CLI byte-identical).
- dazzlecmd-lib unchanged at 0.8.3 (its self-report corrected to match).
- dazzle-dz alias -> 0.9.1; dazzlecmd dep re-pinned to >=0.9.1 (lib pin unchanged at >=0.8.3).

## [0.9.0] - 2026-06-10 — opens the 0.9.x line

**0.9.x begins.** 0.8.x is distinctly the grouping-mechanics work (Act I; closed at v0.8.34, the rollback anchor). 0.9.x is the design-settlement Act II: finalize the base + consumers, then ship the parked tools. This first commit is **Phase 0 consumer finalization** — reconciling the wtf-windows consumer for the dazzlecmd-lib 0.8.0 shim deletion.

### Changed

- Submodule `projects/wtf` bumped to wtf-windows **v0.1.7-alpha** (`a2f993b`): wtf's own aggregator CLI (`wtf list` / `wtf info`) migrated 3 `project.get("diagnostics")` reads to `extra_get`. The 0.8.0 shim removal exposed this break in wtf's **standalone** entry point only — dazzlecmd dispatches wtf's tools through its own already-migrated render code, so the byte-gate never surfaced it. The fix propagated to both the in-tree submodule and the standalone checkout (`c:\code\wtf-windows`); both wtf suites green on lib 0.8.x.

### Note

- **amdead** (the other consumer) was already green on 0.8.x — its entity-access fix shipped earlier (amdead `2941a26`); no change needed.
- wtf's `diagnostics` block is correctly a wtf-domain manifest extension (read via `extra_get`), **not** a missing dazzlecmd-lib core type (`.wtf.json` extends `.dazzlecmd.json` with it). The adjacent "should the lib offer *typed* aggregator manifest extensions?" question is tracked for the #77 framework — see `2026-06-10__09-40-42__dev-workflow-process__post-shim-untyped-access-design-review.md` §5.

### Versions

- dazzlecmd 0.8.34 -> 0.9.0 (MINOR — opens the 0.9.x line).
- dazzlecmd-lib unchanged at 0.8.3 (consumer/submodule reconciliation only — no lib change).
- dazzle-dz alias -> 0.9.0; dazzlecmd dep re-pinned to >=0.9.0.

## [0.8.34] - 2026-06-10

#84 certification cleanup. With all five Groupable verbs live, the orphaned `_CAP_DEFERRED` stub scaffolding (defined but no longer referenced -- no `NotImplementedError` remains on any verb) is removed from `Groupable`, making #84's "the stubs are gone" acceptance criterion literally true. #84 closed against this arc (v0.8.20-v0.8.34).

### Removed

- `Groupable._CAP_DEFERRED` -- orphaned stub-era scaffolding.

### Versions

- dazzlecmd 0.8.33 -> 0.8.34 (PATCH); dazzlecmd-lib 0.8.2 -> 0.8.3 (PATCH); dazzle-dz -> 0.8.34.

## [0.8.33] - 2026-06-10

The manifest↔entity **boundary contract** as a standing regression (tested rather than asserted). Empirical finding: the dict↔entity boundary IS a group/ungroup pair (`build_entity` groups, `to_manifest` ungroups; conserved invariant = the manifest's own content), and the existing `states.assert_round_trip` harness expresses it with **zero new machinery** — verified over all 41 real manifests in the repo (0 lost / 0 changed post-v0.8.32; the projection only ADDS materialized defaults — the L2-semantic vs L2.5-byte gap, measured). Also measured the wild `source` population: 3 blocks, all str-form — too small/skewed to justify a typed `SourceRef` now; a prototype validated against the population with 0 failures, so typing it at #73 (when graduation starts *writing* source blocks) is low-risk and the right time.

### Added

- `tests/test_boundary_roundtrip.py` (3): the live-repo-population round-trip (every real manifest, via the states harness), a worst-case synthetic manifest (typed + `_`-prefixed + both polymorphic source forms + novel keys), and the additive-only L2.5-gap pin.
- `tests/one-offs/thinking/boundary_contract_experiments.py` — the E1/E2/E3 experiments (population identity, SourceRef prototype, harness-fit) that produced the evidence.

### Versions

- dazzlecmd 0.8.32 -> 0.8.33 (PATCH; lib unchanged at 0.8.2 — tests only).
- dazzle-dz alias -> 0.8.33 (dazzlecmd pin only).

## [0.8.32] - 2026-06-10

Post-shim untyped-access review (the `extra_get` DWP the v0.8.30 quick-decision deserved). Verdict: the mechanism was right but **4 of the 5 extra keys were mis-filed**, and the review surfaced a real data-loss bug. All fixes additive; byte-identical (byte-gate 10 OK).

### Fixed

- **`to_manifest()` no longer strips `_vars`** (or `_schema_version`). Pre-fix, every `_`-prefixed key was dropped from the manifest projection — including `_vars`, which is user manifest data (template variables, #41) — so `mode.cache_manifest` silently lost a tool's template variables on mode switch. A `_MANIFEST_UNDERSCORE_KEYS` whitelist now separates `_`-prefixed MANIFEST data (preserved) from computed `_`-annotations (`_fqcn`, still stripped).

### Changed

- `tools_dir` / `manifest` promoted to **typed fields** (kit-manifest schema keys for nested-aggregator child layout — Stage 5 missed them because they only occur off the main sweep path). Absent values stay out of the `to_manifest()` projection (no `null` noise).
- `_override_tools_dir` / `_override_manifest` promoted to **computed fields** `override_tools_dir` / `override_manifest` (the `_dir`→`directory` pattern); the loader normalizes the registry's raw keys at the single pre-`build_entity` chokepoint.
- `extra_get` now documents its **three-category contract** (also in the lib README freeze section): (1) genuinely polymorphic blocks (`source`), (2) `_`-prefixed manifest data (`_vars`/`_schema_version`, a Pydantic field-naming constraint), (3) novel/unmodeled keys. Every remaining extra key is there for a stated reason.
- `cli_helpers.build_tool_subparsers` type hint tells the truth (entities or dicts).

### Tests

- `packages/dazzlecmd-lib/tests/test_entity.py` — `TestUntypedAccessContract` (6): the `_vars`/`_schema_version` round-trip survival (the bug), computed keys still stripped, the typed/computed promotions, and absent-optional projection hygiene. Suite 1362 / byte-gate 10 OK.

### Design

- `2026-06-10__09-40-42__dev-workflow-process__post-shim-untyped-access-design-review.md`

### Versions

- dazzlecmd 0.8.31 -> 0.8.32 (PATCH).
- dazzlecmd-lib 0.8.1 -> 0.8.2 (PATCH -- additive promotions + the `_vars` round-trip fix).
- dazzle-dz alias -> 0.8.32; deps re-pinned to >=0.8.32 / >=0.8.2.

## [0.8.31] - 2026-06-10 — Gate I: contracts settled

State system, Step 7 — **the contracts are settled (Gate I)**. The final Act-I step: the DazzleEntity object model and the Groupable verb/state contracts are declared **frozen until 1.0**. With all five verbs live (`rebind`/`hide`/`expose`/`group`/`ungroup`), the state system underpinning them (axes / transitions / registry / round-trip harness / `CompositeTransition`), and the dict shim removed (0.8.0), the public API of `dazzlecmd-lib` is the stable seam consumers build on — the design milestone the 0.8.x line was built toward.

### Added

- `dazzlecmd_lib.entity.__all__` and `dazzlecmd_lib.groupable.__all__` — explicit public-API surfaces (states.py already had one), making the frozen contract concrete and `from … import *`-checkable.
- A **"Public API — frozen until 1.0 (Gate I)"** section in `packages/dazzlecmd-lib/README.md` documenting the settled surface (`entity` / `groupable` / `states` / `aggregator_config`) and the access model (typed attributes + `extra_get`/`extra_set`; the dict shim is gone).

### Gate I

All five Groupable verbs are live; the dict shim is gone; the state system (axes / transitions / registry / round-trip harness / `CompositeTransition`) underpins them; the public API surface is declared and frozen. **The design is settled.** (Act II — the parked 0.7.x tool batch, lib repo extraction, log_lib/help_lib graduation, and release — is tracked in the design-settlement ultraplan, and includes the amdead consumer follow-up.)

### Versions

- dazzlecmd 0.8.30 -> 0.8.31 (PATCH).
- dazzlecmd-lib 0.8.0 -> 0.8.1 (PATCH — README + `__all__`, additive).
- dazzle-dz alias -> 0.8.31; deps re-pinned to >=0.8.31 / >=0.8.1.

## [0.8.30] - 2026-06-10 — dazzlecmd-lib 0.8.0 (BREAKING)

State system, Step 6 — the DazzleEntity **dict shim is DELETED** (the migration's close; lib **0.8.0**, breaking). Entities no longer support dict-style access (`entity["x"]`, `entity.get()`, `entity.keys()/items()`) — the backward-compat Mapping shim + `_LEGACY_KEY_MAP` + the `_warn_on_shim` ratchet are gone. Access is now typed attributes (`entity.runtime`, `entity.fqcn`) + `extra_get`/`extra_set`/`has_extra` for the untyped remainder (`source`, `_vars`, `manifest`). ~293 call sites across prod + tests were migrated. dazzlecmd's own CLI is **byte-identical** (byte-gate 10 OK); the break is for LIBRARY CONSUMERS that used dict-access.

### Removed (BREAKING — dazzlecmd-lib 0.8.0)

- `DazzleEntity.__getitem__` / `__setitem__` / `get` / `__contains__` / `keys` / `values` / `items` (the dict shim), plus `_LEGACY_KEY_MAP`, `_warn_on_shim`, and the migration ratchet. Consumers migrate: `entity["x"]` → `entity.x` (typed) or `entity.extra_get("x")` (untyped); `entity.get("x", d)` likewise; `entity["x"] = v` → `entity.x = v` / `entity.extra_set("x", v)`; `entity.fqcn` for `entity["_fqcn"]`.

### Added

- `DazzleEntity.extra_get(key, default=None)` / `extra_set(key, value)` / `has_extra(key)` — the sanctioned path for untyped/extra manifest data (the polymorphic `source` block, `_vars`, `_schema_version`, the nested-aggregator `manifest` key).

### Changed

- ~293 call sites (prod: `loader.py`, `engine.py`, `default_meta_commands.py`, `registry.py`, `cli_helpers.py`, `setup_resolve.py`; plus tests) migrated from dict-access to attribute / `extra_get`. Behavior preserved (byte-gate 10 OK).
- `tests/test_ratchet_enforcement.py` repurposed as a post-shim regression (key ops run end-to-end + shim gone + `extra_get`/`extra_set`); the obsolete shim test classes (`TestShimTransparency` / `TestShimMapping`) deleted.

### Tests

- Full suite **1356 passed / 14 skipped**; byte-gate **10 OK / 0 FAIL**; `tests/checklists/v0.8.30__Epic__dict-shim-deletion-lib-0.8.0.md` (human verification).

### Note

The **amdead** consumer's staged entity fix + its suite verification remain the maintainer's follow-up (separate repo, GPG). **wtf-windows** was already shim-clean (0 shim reads) and is unaffected.

### Versions

- dazzlecmd 0.8.29 -> 0.8.30 (PATCH — CLI byte-identical).
- dazzlecmd-lib 0.7.24 -> **0.8.0** (BREAKING MINOR, pre-1.0 — the dict shim removed).
- dazzle-dz alias -> 0.8.30; deps re-pinned to >=0.8.30 / >=0.8.0.

## [0.8.29] - 2026-06-10

State system, Step 5 — the group/ungroup verbs + `CompositeTransition` (#84 behavioral phase, Act I). The fifth and final Groupable verb family, and the first transition that actually crosses the criticality boundary. group/ungroup are the {P, ¬P} boundary primitive at full strength: this slice wires the REVERSIBLE in-tree regime (move an entity in/out of a boundary's membership; `group ∘ ungroup = identity`, C2 = `local_incorporability`) and declares the GENERATIVE graduation regime as DATA — a `CompositeTransition` (KIND+MODE+identity) whose fs+git body is #73, so requesting it is refused at the boundary. **All five Groupable verbs are now live.** Additive; byte-identical (byte-gate 10 OK).

### Added

- `dazzlecmd_lib.states.CompositeTransition` — a multi-axis move as an ORDERED composition of single-axis legs, with composite-criticality computed from leg INTERACTION (a leg's `creates` feeding a later leg's conserved invariant ⇒ GENERATIVE), **not** the union of the legs' classes. Plus `TransitionRegistry.register_composite` / `composites` / `composite`.
- `states.build_default_registry`: the CONTAINMENT axis + reversible `group`/`ungroup` transitions (conserved = `local_incorporability`) + the GENERATIVE `graduation` composite (creates `own_repo`/`remote_url`, loses `in_tree_coupling`, `fqcn_fate="reborn"`).
- `dazzlecmd_lib.groupable`: `ContainmentInvariant` / `ContainmentReceipt` / `ContainmentContext` (in-tree membership move; `apply`/`undo`; C3 refusal on ungrouping a constitutional item; graduation requested via `ContainmentContext.GRADUATE` → refused until #73).
- `dazzlecmd_lib.entity.Groupable.group(target, *, context)` / `ungroup(target=None, *, context)` — live delegates. All five verbs (`rebind`/`hide`/`expose`/`group`/`ungroup`) are now live for their regimes.

### Tests

- `tests/test_containment.py` (NEW, 16): in-tree group/ungroup round-trip via the harness, idempotence, C3 refusal (+ group-constitutional-allowed), the graduation-boundary refusal, the `CompositeTransition` criticality-from-interaction rule (incl. the ≠union demonstration), and the registry declarations.
- `packages/dazzlecmd-lib/tests/test_entity.py` — all five verbs now assert live signatures (no verb is `NotImplementedError`).

### Design

- `2026-06-10__00-38-07__dev-workflow-process__group-ungroup-containment-graduation-composite.md`

### Versions

- dazzlecmd 0.8.28 -> 0.8.29 (PATCH).
- dazzlecmd-lib 0.7.23 -> 0.7.24 (PATCH -- group/ungroup verbs + CompositeTransition).
- dazzle-dz alias -> 0.8.29; deps re-pinned to >=0.8.29 / >=0.7.24.

## [0.8.28] - 2026-06-10

State system, Step 4b — the `dz kit hide` / `dz kit unhide` CLI sugar + the Hidden/verbs human checklist. Makes the Hidden level (mechanism in 0.8.26, verbs in 0.8.27) user-operable: `dz kit hide <fqcn>` adds a tool to `hidden_tools` (display-off, still dispatchable); `dz kit unhide <fqcn>` removes it — mirroring the existing `dz kit silence`/`shadow` channel toggles (silence = hints, hide = display, shadow = resolution). Reveal with `dz list --show-hidden`.

### Added

- `dz kit hide <fqcn>` / `dz kit unhide <fqcn>` — single-key toggles of `hidden_tools`, mirroring `dz kit shadow`/`unshadow`. (The programmatic `entity.hide(to="hidden")` verb sets the full ladder level cumulatively; the CLI command toggles the one display channel — both coexist, `visibility_in` reports the level.)
- `tests/checklists/v0.8.28__Feature__hidden-visibility-and-hide-expose-verbs.md` — public human checklist; the load-bearing manual check is that a hidden tool still runs by name.

### Tests

- `tests/test_hidden_tools.py` — 4 added: `dz kit hide` writes config + list omits, `unhide` restores, unhide-not-hidden is graceful, hide is idempotent.

### Versions

- dazzlecmd 0.8.27 -> 0.8.28 (PATCH).
- dazzlecmd-lib unchanged at 0.7.23 (this slice is CLI-only — no lib source change).
- dazzle-dz alias -> 0.8.28; dazzlecmd dep re-pinned to >=0.8.28 (lib pin unchanged).

## [0.8.27] - 2026-06-10

State system, Step 4a — the hide/expose verbs (the visibility ladder). #84's third and fourth live Groupable verbs: `hide`/`expose` walk the monotone channel ladder (Visible → Silenced → Hidden → Shadowed) with an explicit target level and direction enforcement. The verbs WRITE the existing config keys — which ARE the per-channel suppression sets (`silenced_hints`=hints, `hidden_tools`=display, `shadowed_tools`=resolution) — so the monotone effect falls out of the existing filters with no new engine logic. Additive; byte-identical (byte-gate 10 OK).

### Added

- `dazzlecmd_lib.groupable`: `VISIBILITY_CHANNELS` + `VISIBILITY_LADDER` (the monotone preset map) + `level_for_channels`; `Frame` (a consumer/projection context, with a reserved unwired `channel_overrides` field); `VisibilityInvariant` (C2 = `canonical_dispatch`); `VisibilityReceipt` (carries per-channel deltas); `VisibilityContext` (global path; writes via `engine._write_user_config`; `undo`).
- `dazzlecmd_lib.entity.Groupable.hide(to=..., *, context)` / `expose(to=..., *, context)` — live ladder-walk delegates with direction enforcement and the first real C3 enforcement (shadowing a constitutional `always_active` item raises `CriticalityBoundaryError`; Hidden is the maximum veil it may take). `visibility_in(frame=None, *, context=None)` is now real for the global path.
- `states.build_default_registry` now declares the VISIBILITY `hide`/`expose` transitions (REVERSIBLE, conserved = `canonical_dispatch`).

### Changed

- Frame-relative visibility writes are refused (clear error) until #79 environments; only the global frame is wired.

### Tests

- `tests/test_visibility.py` (NEW, 18): ladder walks + the cumulative/monotone config, direction enforcement, C3 refusal (+ Hidden-allowed, ordinary-shadow-allowed), Frame refusal, `visibility_in`, round-trip via `ctx.undo` (the Step-1 harness), and the registry cross-check.
- `packages/dazzlecmd-lib/tests/test_entity.py` — only `group`/`ungroup` remain deferred; `hide`/`expose` join `rebind` as live verbs with real signatures.

### Note

`dz kit hide` / `dz kit unhide` CLI sugar + the Hidden/verbs human checklist land in Step 4b.

### Versions

- dazzlecmd 0.8.26 -> 0.8.27 (PATCH).
- dazzlecmd-lib 0.7.22 -> 0.7.23 (PATCH -- hide/expose verbs + the Visibility* types).
- dazzle-dz alias -> 0.8.27; deps re-pinned to >=0.8.27 / >=0.7.23.

## [0.8.26] - 2026-06-10

State system, Step 3 — the Hidden visibility level (#84 behavioral phase, Act I). A new `hidden_tools` user-config key plus a render-only filter: a hidden tool is omitted from `dz list` / `dz tree` / the help epilog but stays fully dispatchable (its short name is still claimed, its FQCN still resolves). This is the ladder level between Silenced (hints suppressed) and Shadowed (removed at discovery, short name freed) — the one net-new mechanism the verbs need. `--show-hidden` reveals. No-op when `hidden_tools` is empty (the default), so output is byte-identical (byte-gate 10 OK).

### Added

- `dazzlecmd_lib.engine.AggregatorEngine.filter_hidden(projects, *, reveal=False)` — the render-only chokepoint shared by all display surfaces; returns a filtered copy (never mutates `engine.projects` / the FQCN index / dispatch), or the same object unchanged when no tools are hidden.
- `hidden_tools` config key, documented in `config.py` alongside the `silenced_hints` / `shadowed_tools` visibility ladder.
- `--show-hidden` on `dz list` and `dz tree` (mirrors the existing `--show-disabled` reveal-flag convention).

### Tests

- `tests/test_hidden_tools.py` (NEW, 9): `filter_hidden` (omit + dispatch-source preserved, reveal, empty-is-noop-same-object), and `dz list` / `dz tree` end-to-end (omit, reveal, no-config-shows-all).
- `tests/test_default_meta_commands.py` — the MagicMock engine stub now mirrors `filter_hidden`'s no-op pass-through.

### Note

The `dz kit hide` / `dz kit unhide` management commands (which WRITE `hidden_tools`) ship with the `hide`/`expose` verbs in Step 4 — this commit lands the mechanism the verbs drive. Until then `hidden_tools` is populated via config.

### Versions

- dazzlecmd 0.8.25 -> 0.8.26 (PATCH).
- dazzlecmd-lib 0.7.21 -> 0.7.22 (PATCH -- the Hidden render-filter mechanism).
- dazzle-dz alias -> 0.8.26; deps re-pinned to >=0.8.26 / >=0.7.22.

## [0.8.25] - 2026-06-09

State system, Step 2 — `undo(receipt)` (#84 behavioral phase, Act I). The context-level inverse, so callers and the round-trip harness need not track the new owner; `assert_round_trip`'s `invert` is now just `ctx.undo`. Additive — `undo` is not called on any dispatch path, so existing behavior is byte-identical (byte-gate 10 OK).

### Added

- `dazzlecmd_lib.groupable.RebindContext.undo(receipt)` (protocol) + two implementations:
  - `AliasRebindContext.undo` — entity-free: the context owns the alias and the index, so it looks up the current owner itself and repoints back to `receipt.previous_state`. Always reversible (this is where the receiver asymmetry of `apply` dissolves).
  - `dazzlecmd_lib.mode.ModeRebindContext.undo` — re-drives the inverse switch on the entity captured at `apply` time, iff `receipt.reversible`. A one-way orbit entry (`reversible=False`) refuses with `CriticalityBoundaryError`; calling `undo` before any `apply` refuses with `RebindError`.

### Tests

- `tests/test_groupable_rebind.py` — `TestUndo` (6): alias undo round-trip driven through the Step-1 harness (`invert=ctx.undo`), the inverse-receipt shape, the unknown-alias guard; mode undo refusing one-way, returning the inverse receipt in-orbit, and refusing without a prior apply. Suite 1324 / byte-gate 10 OK.

### Versions

- dazzlecmd 0.8.24 -> 0.8.25 (PATCH).
- dazzlecmd-lib 0.7.20 -> 0.7.21 (PATCH -- undo on the rebind contexts).
- dazzle-dz alias -> 0.8.25; deps re-pinned to >=0.8.25 / >=0.7.21.

## [0.8.24] - 2026-06-09

State system, slice 0 (#84 behavioral phase, the design-settlement Act I). A new generic module giving every grouping/ungrouping mechanism one vocabulary for the states it moves between, which transitions are reversible/critical, and what each preserves/creates/destroys — the `group ∘ ungroup = identity` contract becomes generated tests rather than markdown. Additive: imported nowhere in the dispatch hot path, so existing behavior is byte-identical.

### Added

- `dazzlecmd_lib.states` (NEW module, generic — imports nothing from `engine`/`mode`/`groupable`, so it ships in the standalone lib and any aggregator registers its own axes):
  - `StateAxis` / `EntityState` (frozen, OBSERVED not stored — the `ResolutionContext` precedent) / `Transition` / `TransitionRegistry` — the four-type vocabulary.
  - `Reversibility` (`REVERSIBLE` / `ONE_WAY` / `REFUSED_AT_BOUNDARY` / `GENERATIVE`) — the criticality algebra as data; the `Transition` type enforces its contracts (GENERATIVE must declare `creates`/`loses`; REVERSIBLE must preserve C1).
  - `assert_round_trip(read, apply, invert)` — substrate-agnostic identity-contract harness (L2-semantic equality); forward-compatible with `ctx.undo` (Step 2).
  - `observe(registry, fqcn, **readings)` — the platform→model bridge: validates a real substrate reading against the registered axes (a state the model can't express raises, rather than being silently stored).
  - `build_default_registry()` — registers KIND/MODE/VISIBILITY/ACTIVATION + the index-level ROUTING axis and retro-declares the live `rebind` transitions (alias repoint; dev↔publish orbit; enter-orbit one-way; underivable-invariant refusal). Reserves `CompositeTransition` (graduation) as a documented extension point.

### Tests

- `tests/test_states.py` (NEW, 32): the four types, registry-enumeration property tests (every REVERSIBLE preserves C1 + names its invariant; the GENERATIVE contract is enforced; MODE declares a REFUSED class), the round-trip harness, live cross-checks against BOTH rebind contexts (a full in-memory alias round-trip via the harness + receipt-level mode agreement), and platform integration — a real discovery pass over this repo observing all 33 discovered tools across the axes (`observe()` proves the model spans the real platform). Suite 1318 / byte-gate 10 OK.

### Versions

- dazzlecmd 0.8.23 -> 0.8.24 (PATCH).
- dazzlecmd-lib 0.7.19 -> 0.7.20 (PATCH -- new states.py module, additive).
- dazzle-dz alias -> 0.8.24; deps re-pinned to >=0.8.24 / >=0.7.20.

## [0.8.23] - 2026-06-09

Drop Python 3.8 + tagline refresh. The DazzleEntity model imports `typing.Annotated` (a 3.9+ feature, used at *runtime* for the discriminated union), so the lib has effectively required Python 3.9+ since the 0.8.x rearchitecture — CI surfaced it on 3.8 (`ImportError: cannot import name 'Annotated' from 'typing'`) once the v0.8.22 pydantic-dep fix let the import chain run far enough to reach it. Python 3.8 is EOL (Oct 2024) and pydantic 2.10 already dropped it, so 3.8 is dropped rather than shimmed.

### Changed

- **Python requirement raised to `>=3.9`** across the root `pyproject.toml`, `dazzlecmd-lib`, and the `dazzle-dz` alias; the `3.8` classifier and the `3.8` CI matrix entry (with its now-moot macOS exclude) are removed.
- **Tagline:** "Many tools, one command." → "A tool for tools." The README intro and the PyPI summary now frame DazzleCMD as a framework for tools and how tools compound on each other — nesting and graduating into kits and whole aggregators.

### Versions

- dazzlecmd 0.8.22 -> 0.8.23 (PATCH).
- dazzlecmd-lib 0.7.18 -> 0.7.19 (PATCH -- requires-python >=3.9).
- dazzle-dz alias -> 0.8.23; deps re-pinned to >=0.8.23 / >=0.7.19.

## [0.8.22] - 2026-06-09

CI hotfix — `dazzlecmd-lib` now declares its Pydantic runtime dependency. A clean `pip install` (e.g. CI) never pulled Pydantic, so `dz --version` (which imports `cli` → `loader` → the `DazzleEntity` model) died with `ModuleNotFoundError: No module named 'pydantic'` on every platform/Python combination. Local dev was unaffected because the dev environment already had Pydantic installed. Latent since the 0.8.x object-model rearchitecture; surfaced on the first push to CI.

### Fixed

- `packages/dazzlecmd-lib/pyproject.toml` now declares `dependencies = ["pydantic>=2.0"]`. The DazzleEntity model (`entity.py` / `aggregator_config.py`) is built on Pydantic v2 — a hard runtime dependency since 0.8.0 — but the lib declared no core dependencies, so clean installs lacked it. (`colorama` and `distro` stay undeclared/optional: both are imported best-effort under `try/except`, so neither breaks a clean install.)
- Root `pyproject.toml` now requires `dazzlecmd-lib>=0.7.18` (was `>=0.6.4`): the root imports the DazzleEntity model, which only exists in the 0.7.x+ lib, so the stale floor could otherwise resolve an entity-less lib.

### Versions

- dazzlecmd 0.8.21 -> 0.8.22 (PATCH).
- dazzlecmd-lib 0.7.17 -> 0.7.18 (PATCH -- declare the Pydantic runtime dep).
- dazzle-dz alias -> 0.8.22; deps re-pinned to >=0.8.22 / >=0.7.18.

## [0.8.21] - 2026-06-09

Behavioral phase (#84) — `rebind` PoC, Phase 2 (mode-switch). The *same* `rebind` verb now also drives dev↔publish mode switching, via a second context — proving the context-delegate pattern generalizes (the verb didn't change; a new context did). Also fixes a latent entity-migration bug it surfaced.

### Added

- `dazzlecmd_lib.mode.ModeRebindContext` — a `RebindContext` for dev↔publish. The conserved invariant (C2) is the **remote URL**: `dev↔publish` reverses within the orbit (`SUBMODULE↔SYMLINK`). Criticality is **invariant-derivability**, not a state blocklist: no derivable remote URL → `CriticalityBoundaryError` (pre-flight). Entering the orbit from `EMBEDDED`/`LOCAL_ONLY` is permitted (when a URL exists) but one-way → `receipt.reversible = False`. Delegates the switch to the existing `_switch_to_dev`/`_switch_to_publish` (so `entity.py` stays decoupled from the filesystem); a non-zero exit surfaces as the new `dazzlecmd_lib.groupable.RebindError`.

### Fixed

- `dz mode switch <tool> --publish` (without `--url`) was **broken for entities**: `mode._resolve_remote_url` → `_dotted_lookup` rejected a `DazzleEntity` (its `isinstance(dict)` guard returned `None`), so `source.url` / `lifecycle.graduated_to` couldn't be read — a latent regression from the Phase-1 dict→entity migration, masked because the mode tests always passed an explicit `--url`. `_resolve_remote_url` now resolves against the manifest projection (`to_manifest()`), fixing it for entity *and* dict callers. Surfaced by the Phase-2 `ModeRebindContext`.

### Tests

- `tests/test_groupable_rebind.py` — `TestModeRebind` (5): invalid target, criticality refusal (no remote URL), publish dry-run receipt + one-way-entry `reversible=False`, in-orbit dev `reversible=True`, and a direct `_resolve_remote_url`-reads-from-entity regression. 17 rebind tests total; suite 1286 / byte-gate 10 OK.

### Versions

- dazzlecmd 0.8.20 -> 0.8.21 (PATCH).
- dazzlecmd-lib 0.7.16 -> 0.7.17 (PATCH -- ModeRebindContext + RebindError + the _resolve_remote_url entity fix).
- dazzle-dz alias -> 0.8.21; deps re-pinned to >=0.8.21 / >=0.7.17.

## [0.8.20] - 2026-06-09

Behavioral phase (#84) — `rebind` PoC, Phase 1 (alias). The first live `Groupable` verb: a `DazzleEntity` can now re-route one of its name bindings to a different canonical without changing its own canonical identity (C1). Additive; existing behavior byte-identical.

### Added

- `dazzlecmd_lib.groupable` (NEW module) — the behavioral-verb types: `RebindReceipt`, `RebindInvariant` (the C2 conserved-quantity descriptor), `CriticalityBoundaryError`, the `RebindContext` protocol, and `AliasRebindContext`. Each rebind sub-kind is a context impl (`context.apply(entity, target) -> receipt`); the verb delegates to it — this protocol is the generalizable seam for the remaining verbs.
- `dazzlecmd_lib.engine.FQCNIndex.repoint_alias(alias_fqcn, new_canonical_fqcn)` — the alias-rebind primitive. `insert_alias` deliberately *refuses* a different-target remap, so repointing gets its own method that owns the index's coherence (single-hop/existence guards, idempotence, and `short_index` re-bookkeeping a raw `alias_index` poke would skip).

### Changed

- `dazzlecmd_lib.entity.Groupable.rebind` — implemented (was `NotImplementedError`): `rebind(target, *, context)` delegates to the context, preserving C1. `group`/`ungroup`/`hide`/`expose` remain deferred. `Frame` reserved (not built) — `hide`/`expose` will consume it.

### Tests

- `tests/test_groupable_rebind.py` (NEW) — alias round-trip (`rebind ∘ rebind⁻¹ = identity`) against a real `FQCNIndex`, the receiver precondition, single-hop/existence guards, idempotence, and `short_index` coherence after a repoint (10 tests). `test_entity.py` updated: `rebind` is no longer in the deferred-verbs assertion.

### Notes

- Alias-rebind persistence is **out of PoC scope**: `alias_index` is rebuilt from manifests/config each invocation, so a repoint is in-memory only. No user-facing `dz rebind` is wired. Phase 2 (mode-switch rebind + the criticality boundary) is next.

### Versions

- dazzlecmd 0.8.19 -> 0.8.20 (PATCH).
- dazzlecmd-lib 0.7.15 -> 0.7.16 (PATCH -- additive: groupable module + repoint_alias + live rebind).
- dazzle-dz alias -> 0.8.20; deps re-pinned to >=0.8.20 / >=0.7.16.

## [0.8.19] - 2026-06-08

Phase 1 (DazzleEntity migration) — Stage 4: the `wtf` consumer is migrated. Bumps the `projects/wtf` submodule pointer to wtf-windows v0.1.6-alpha, whose CLI now reads engine-produced entities via typed attribute access instead of the dict shim (19 sites in `cli.py`; wtf's own 7 smoke tests stay green). One of the two external consumers is now shim-free; `amdead` (separate repo) is the remaining one before the shim can be deleted.

### Changed

- `projects/wtf` submodule → wtf-windows `00c601f` (v0.1.6-alpha). wtf-specific manifest extensions (the `diagnostics` block, nested `taxonomy.tags`) correctly remain dict access; wtf now pins `dazzlecmd-lib>=0.7.15`. Local-only (held; the wtf commit is ahead of its origin until the coordinated un-hold push).

### Versions

- dazzlecmd 0.8.18 -> 0.8.19 (PATCH).
- dazzlecmd-lib unchanged at 0.7.15 (submodule-pointer + consumer change, no library code change).
- dazzle-dz alias -> 0.8.19; dep re-pinned to >=0.8.19 (lib dep stays >=0.7.15).

## [0.8.18] - 2026-06-08

Phase 1 (DazzleEntity call-site migration) — Stage 3: ratchet enforcement. Phase 1 is now provably complete for in-scope production code — every key `dz` operation reaches its entities' typed fields via attribute access, with a regression gate to keep it that way.

### Changed

- `dazzlecmd_lib.registry.RunnerRegistry.resolve` — the last typed-field shim straggler on the dispatch path: `project.get("runtime", {})` → `project.runtime` (typed field, default `{}`; byte-identical). Found by flipping the `_warn_on_shim` ratchet over the dispatch path.

### Tests

- `tests/test_ratchet_enforcement.py` (NEW) — drives each key operation (list, list --show all, info, tree, mode status, kit list, kit status, dispatch by short name, dispatch by FQCN) through the real CLI with `DazzleEntity._warn_on_shim` ON and asserts NO production typed-field shim `DeprecationWarning` fires. D2-safe: only dazzlecmd's own suite flips the ratchet; wtf/amdead run with it off. 9 parametrized cases.
- `tests/one-offs/ratchet_recon.py` (NEW) — the manual end-to-end diagnostic that measures production stragglers (the in-suite gate above is its sibling).

### Versions

- dazzlecmd 0.8.17 -> 0.8.18 (PATCH).
- dazzlecmd-lib 0.7.14 -> 0.7.15 (PATCH -- last dispatch-path straggler + ratchet gate).
- dazzle-dz alias -> 0.8.18; deps re-pinned to >=0.8.18 / >=0.7.15.

## [0.8.17] - 2026-06-07

Fixes two pre-existing bugs surfaced during the engine-sweep verification (neither related to the DazzleEntity migration): `dz kit status` ignored the user's kit config, and `dz mode switch` didn't accept a fully-qualified tool name.

### Fixed

- `dz kit status` now honors `active_kits` / `disabled_kits` — its active set matches `dz kit list`. Root cause: `dazzlecmd.cli._cmd_kit_status` called `get_active_kits(kits)` without the engine's user config, hitting the legacy "all kits active" default. It now threads `engine._get_user_config()` through. The parallel lib renderer `dazzlecmd_lib.default_meta_commands.render_kit_status` (used by lib-based aggregators via `kit_status_handler`) had the same class of bug — it filtered by the manifest `always_active` flag only; the handler now passes `engine.active_kits` (the config-resolved set) and the renderer just displays what it's given.
- `dz mode switch <fqcn>` now resolves an exact FQCN (e.g. `core:find`) in addition to the short name. Root cause: `dazzlecmd_lib.mode.cmd_switch` matched `p.name == tool_name` only, so an FQCN argument fell through to the undiscovered-tool directory scan and errored with "not found". It now also matches an exact `p.fqcn` and normalizes the argument to the resolved short name. Match is **exact** (short name OR exact FQCN) — `mode switch` deliberately does NOT use the fuzzy precedence/favorites resolver, since it rewrites a submodule and must act on exactly the named tool. (This also fixes a leftover `p["name"]` dict-shim access the mode.py sweep missed.)

### Tests

- `tests/test_cli_kit.py` — `TestKitStatusActiveFilter`: `kit status` excludes a `disabled_kits` entry (even an `always_active` one), honors an `active_kits` allowlist, and falls back to all-active when no engine/config is supplied.
- `tests/test_mode.py` — `cmd_switch` resolves an exact FQCN argument (`core:mytool`), and an unknown FQCN still errors cleanly (no false match).

### Versions

- dazzlecmd 0.8.16 -> 0.8.17 (PATCH).
- dazzlecmd-lib 0.7.13 -> 0.7.14 (PATCH -- kit-status active-filter + mode-switch FQCN fixes).
- dazzle-dz alias -> 0.8.17; deps re-pinned to >=0.8.17 / >=0.7.14.

## [0.8.16] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 2 cleanups. Byte-identical refactor: removes the last dead `else dict(...)` entity-or-dict duality guards and the `cache_manifest` dict fallback now that all entity construction flows through the loader/engine. No user-visible change.

### Changed

- `dazzlecmd_lib.engine._rewrite_virtual_kit` — dropped the dead `vk.model_copy() if hasattr(...) else dict(vk)` clone guard (`vk` is always an entity); migrated the `rewritten[...]` writes to attribute access (`rewritten.name`/`.kit_name`/`.original_name`/`.tools`/`.name_rewrite`, and the `rewritten.kit_active` write in `_discover_aggregator`).
- `dazzlecmd_lib.registry.resolve_runtime` — dropped both `project.model_copy() if hasattr(...) else dict(project)` clone guards; the runtime writes are now `project.runtime = ...` / `resolved_project.runtime = ...`. (`_vars` reads stay dict access — manifest data in extra.)
- `dazzlecmd_lib.mode.cache_manifest` — dropped the `hasattr(manifest, "to_manifest")` dict fallback; `manifest` is always a DazzleEntity, so it's now `clean = manifest.to_manifest()`.
- `dazzlecmd_lib.mode.cmd_status` — the inline undiscovered-tool raw dict is now built as a `Tool` entity via `build_entity(..., entity_type="tool")` (legacy `_dir` → the promoted `directory` field), and the status reads migrated to attribute access (`p.name`, `p.namespace`, `p.directory`).

### Tests

- `tests/test_mode.py` — the two `cache_manifest` callers that passed raw dict literals now pass `make_tool(...)` entities (the dict fallback they relied on is gone).

### Versions

- dazzlecmd 0.8.15 -> 0.8.16 (PATCH).
- dazzlecmd-lib 0.7.12 -> 0.7.13 (PATCH -- Stage 2 cleanups).
- dazzle-dz alias -> 0.8.16; deps re-pinned to >=0.8.16 / >=0.7.13.

## [0.8.15] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — completes the `engine.py` sweep: the FQCN-index core (`FQCNIndex.insert_canonical`, `_build_fqcn_index`) is now entity-native, after its direct-call test fixtures moved to entities (fixtures-first). With this, **all six production files are fully swept** — no typed-field dict access remains in the dispatch path. Byte-identical; suite + byte-gate green. Local-only.

### Changed

- `dazzlecmd_lib.engine.FQCNIndex.insert_canonical` + `AggregatorEngine._build_fqcn_index` — migrated to attribute access (`project.fqcn`/`.short_name`/`.kit_import_name`, `existing.directory or '?'`, the `"_fqcn" not in project` membership check → the value check `project.fqcn is None`, the realpath-dedup reads `(p.fqcn or "")`, and the auto-realpath alias writes `alias_project.auto_realpath_alias = True` / `alias_project.canonical_fqcn = ...`).

### Tests

- `test_engine_fqcn`, `test_fqcn_index_alias`, `test_path_form_convergence`, `test_stale_favorites_warning`, `test_env_var_injection` — their `_proj()` fixture helpers now build real `Tool` entities via `dazzlecmd_lib.testing.make_tool(**fixture)` instead of raw dicts, so they exercise the entity-native index methods directly. (Assertion reads via the shim are left unchanged; they migrate in the eventual pre-shim-deletion test cleanup.)

### Verification

- Added the human test checklist `tests/checklists/v0.8.15__Refactor__engine-dazzleentity-attribute-sweep.md` — targets the WRITE/MUTATE and real-dispatch paths the byte-gate doesn't cover (real tool dispatch, `mode switch` write path, cross-aggregator `wtf` recursion, `kit_active` propagation, auto-realpath dedup, reroot hint). Executed via `tester-unbounded`: **SHIP** (suite 1254 passed / 14 skipped, byte-gate 10 OK / 0 FAIL); no attribute-access regressions found. Two flagged behaviors (`kit status` not filtering by `active_kits`; `mode switch` resolving by short name not FQCN) are pre-existing, outside `engine.py`, not regressions of this sweep.
- Committed the byte-identical-gate harness it relies on: `tests/one-offs/run_byte_gate.py` + `tests/one-offs/baselines_v0.7.54/` (golden `dz list`/`info`/`tree`/`mode status` outputs — the ground truth for the whole 0.8.x byte-identical guarantee). Scratch tooling under `tests/one-offs/`, committed to preserve it.
- Also committed the previously-uncommitted `tests/checklists/v0.8.2__Refactor__shim-mapping-and-mode-switch-crashfix.md` (the v0.8.2 shim-Mapping completion + `cache_manifest` crash-fix checklist).

### Versions

- dazzlecmd 0.8.14 -> 0.8.15 (PATCH).
- dazzlecmd-lib 0.7.11 -> 0.7.12 (PATCH -- FQCN-index core sweep).
- dazzle-dz alias -> 0.8.15; deps re-pinned to >=0.8.15 / >=0.7.12.

## [0.8.14] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — `engine.py` attribute sweep (the last production file). The discovery-pipeline entity sites in the dispatch core are now typed attribute access; byte-identical; full suite + byte-gate green. Local-only.

### Changed

- `dazzlecmd_lib.engine` — entity field reads/writes across `discover()`/partition, `_discover_aggregator`, `_recurse_into_nested`, `_rewrite_virtual_kit`, `_apply_virtual_kits`, `_annotate_project_fqcn`, the reroot-hint scan, and tool dispatch migrated from dict access to attribute access (`p.kit_active`, `k.kit_name or k.name`, `kit.virtual is True`, `project.kit_import_name or ""`, `kit.tools = [p.fqcn for ...]`, `project.fqcn = fqcn` via the set-once C1 property, `(p.fqcn or "")`, `project.name`, etc.). The `.get(k, "")`/`.get(k, "?")` string-default sites became `entity.attr or default`; bool fields with a True default (`_kit_active`) became plain `entity.kit_active`; the `"_fqcn" not in project` membership check became the value check `project.fqcn is None`.

### Notes (remaining follow-ons)

- `FQCNIndex.insert_canonical` and `_build_fqcn_index` are intentionally left on dict-style access in this commit: several tests (`test_engine_fqcn`, `test_fqcn_index_alias`, `test_path_form_convergence`, `test_stale_favorites_warning`, `test_env_var_injection`) call them directly with raw dict fixtures. They migrate in the next commit after those fixtures move to entities (the established fixtures-first sequencing).
- The clone-site `else dict(...)` guards (`_rewrite_virtual_kit` writes on `rewritten`, the `rewritten["_kit_active"]` write) stay until the guard-drop cleanup; extra/manifest keys (`tools_dir`, `manifest`, `_override_*`) correctly stay dict access.

### Versions

- dazzlecmd 0.8.13 -> 0.8.14 (PATCH).
- dazzlecmd-lib 0.7.10 -> 0.7.11 (PATCH -- engine.py discovery-pipeline sweep).
- dazzle-dz alias -> 0.8.14; deps re-pinned to >=0.8.14 / >=0.7.11.

## [0.8.13] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 6b cont.: `mode.py` attribute sweep + the dict-or-entity unification of `_find_undiscovered_tool`. Byte-identical; mode-switch behavioral tests + dispatch verified. Local-only.

### Changed

- `dazzlecmd_lib.mode._find_undiscovered_tool` — now returns a real `Tool` entity (via `build_entity`) from all three return paths (cached-manifest hit, minimal on-disk, orphan-cache) instead of a raw dict. This is the dict-or-entity unification for the mode-switch path: `cmd_switch`'s `project` is now always an entity.
- `dazzlecmd_lib.mode` — entity field reads in `cmd_switch` / `_switch_to_publish` / `_switch_to_dev` migrated to attribute access (`project.directory`, `project.name`, `project.namespace`, `if project.name:`). Config/gitmodules/raw-JSON dicts stay dict access. `cache_manifest`'s `hasattr(..., "to_manifest")` guard is kept (some test callers still pass raw dicts directly).

### Notes (remaining follow-ons)

- `cmd_status` builds its `all_projects` list with inline raw dicts (not entities) — left as dict access; a future cleanup should route it through entity construction.
- `_resolve_remote_url` stays shim-compatible (called from tests with raw topology dicts).
- The clone-site `else dict(project)` guards in `registry`/`engine` and the `cache_manifest` raw-dict fallback remain until their callers are fully entity-only.

### Versions

- dazzlecmd 0.8.12 -> 0.8.13 (PATCH).
- dazzlecmd-lib 0.7.9 -> 0.7.10 (PATCH -- mode.py sweep + _find_undiscovered_tool unification).
- dazzle-dz alias -> 0.8.13; deps re-pinned to >=0.8.13 / >=0.7.10.

## [0.8.12] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 6b cont.: `src/dazzlecmd/cli.py` attribute sweep (the dazzlecmd package CLI). Byte-identical; dispatch verified. Local-only. (Package-only change — `dazzlecmd-lib` unchanged.)

### Changed

- `dazzlecmd.cli` — entity field reads in the parser registration, help epilog (`_build_categorized_help`), `_cmd_kit_list` / kit-status / kit-focus / virtual-kit rendering, `_cmd_add`, the setup listing/handler, and tool dispatch migrated from dict access to attribute access (`project.name`, `project.fqcn or tool_name`, `project.directory or "."`, `kit.kit_name or kit.name`, `kit.always_active`, `kit.tools or []`, `(p.setup or {}).get("note")`, etc.). Raw-JSON kit dicts (`json.load` in `_register_in_kit`), nested setup-block dicts, user-config dicts (`engine._get_user_config()`), and `add_from_local` result dicts correctly stay dict access. No test files needed changes (cli fixtures were already migrated).

### Versions

- dazzlecmd 0.8.11 -> 0.8.12 (PATCH).
- dazzlecmd-lib unchanged at 0.7.9 (cli.py is package code, not library).
- dazzle-dz alias -> 0.8.12; deps re-pinned to >=0.8.12 / >=0.7.9.

## [0.8.11] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 6b cont.: `registry.py` attribute sweep (the dispatch-critical runtime-resolution + runner-factory module). Byte-identical; dispatch verified. Local-only.

### Changed

- `dazzlecmd_lib.registry` — entity field reads in `resolve_runtime` and the runner factories (`make_docker_runner`, `_make_subprocess_runner`, `_make_python_runner`) migrated to attribute access (`project.runtime`, `project.directory`, `project.name`, `project.pass_through`, etc.). Nested-block manipulation (`runtime`/`effective`/`selected`/`env`/`platforms`, `.pop`/`.items`/comprehensions) stays dict access. The clone-site guards (`project.model_copy() if hasattr(...) else dict(project)`) and the subsequent `project["runtime"] = ...` stay as-is — they straddle the entity-or-dict duality until the unification stage. `_vars` stays `.get("_vars")` (extra key).
- Fixtures migrated to `make_tool`: `tests/test_registry.py`, `test_resolve_runtime.py`, `test_vars_integration.py`, `test_user_override_integration.py` (runtime-resolver classes), `test_venv_integration.py`, `test_docker_runner.py`, `test_docker_integration.py`, `test_python_runner_interpreter.py`, and `test_engine_recursive.py` (`TestModuleDispatch`) — the resolver/runner inputs the earlier fixture pass deferred.

### Versions

- dazzlecmd 0.8.10 -> 0.8.11 (PATCH).
- dazzlecmd-lib 0.7.8 -> 0.7.9 (PATCH -- registry attribute sweep).
- dazzle-dz alias -> 0.8.11; deps re-pinned to >=0.8.11 / >=0.7.9.

## [0.8.10] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 6b cont.: `loader.py` attribute sweep. Byte-identical. Local-only.

### Changed

- `dazzlecmd_lib.loader` — entity-READ sites migrated to attribute access: `get_active_kits` (`kit.kit_name or kit.name`, `kit.always_active`), `discover_projects` (`kit.tools`), `_scan_tool_dirs` (`p.namespace`, `p.name`). Raw-construction dict access (the `registry`/`kit`/`manifest`/`cached`/`inner` dicts assembled *before* `build_entity`) correctly stays dict access — it's not entity access. Extra keys (`manifest`, `tools_dir`) stay `.get()`.
- Fixture: `tests/test_engine_config.py` `_mk_kit` helper migrated to `make_kit` (it fed raw-dict kits directly to `get_active_kits`).

### Versions

- dazzlecmd 0.8.9 -> 0.8.10 (PATCH).
- dazzlecmd-lib 0.7.7 -> 0.7.8 (PATCH -- loader attribute sweep).
- dazzle-dz alias -> 0.8.10; deps re-pinned to >=0.8.10 / >=0.7.8.

## [0.8.9] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 6b cont.: completes the `default_meta_commands.py` attribute sweep by migrating `render_tree` and the virtual-kit paths (deferred in 0.8.8 because their fixtures were still plain dicts). Byte-identical. Local-only.

### Changed

- `dazzlecmd_lib.default_meta_commands` — `render_tree` (ASCII + JSON output paths, sort lambdas), the virtual-kit `engine.kits` iteration in `build_list_entries`, and the empty-virtual-kit injection block in `render_list` migrated from dict access to typed attribute access (`project.fqcn or ""`, `kit.kit_name or kit.name`, `kit.virtual`, `kit.kit_active`, `kit.tools or []`, etc.). Display-dict keys (`result`, `tools_data`, `info`, `by_kit`) stay dict access. **`default_meta_commands.py` is now fully swept.**
- Fixtures: `tests/test_cli_tree.py` (3 tools + 2 kits) and the `_engine_with_virtual_kit` helper in `tests/test_default_meta_commands.py` migrated to the `make_tool`/`make_kit` factories.

### Versions

- dazzlecmd 0.8.8 -> 0.8.9 (PATCH).
- dazzlecmd-lib 0.7.6 -> 0.7.7 (PATCH -- render_tree + virtual-kit attribute sweep).
- dazzle-dz alias -> 0.8.9; deps re-pinned to >=0.8.9 / >=0.7.7.

## [0.8.8] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 6b (first prod file): the `default_meta_commands.py` attribute sweep. Migrates dict-style entity access in the list/info/kit/setup render paths to typed attribute access. Byte-identical (the byte-gate is the per-site oracle); no behavior change. Local-only.

### Changed

- `dazzlecmd_lib.default_meta_commands` — entity access migrated from dict-style (`project["name"]`, `project.get("_fqcn")`, `.get("description", "")`) to attribute access (`project.name`, `project.fqcn`, `project.description`) across `render_list`, `build_list_entries`, `render_info`, `render_kit_list`, `render_kit_status`, `render_setup_listing`, `setup_handler`, and the runtime-print helpers (~50 logical sites). Nested-block values stay dict access (`entity.runtime["type"]`, `entity.taxonomy.get("tags")`); extra keys (`_vars`, `source`, etc.) stay `.get()`; `.get(key, default)` on `Optional` fields became `entity.field or default` to preserve exact semantics. Companion fixtures in `tests/test_default_meta_commands.py` migrated to the `make_tool`/`make_kit` factories (fully-annotated entities mirroring production; `short_name == name`), with the `_engine_with` `.setdefault` helper replaced by attribute assignment and a membership assertion changed to a value check.

### Notes

- `render_tree` (and the virtual-kit `engine.kits` iteration in `build_list_entries`) is intentionally **deferred**: its tests (`test_cli_tree.py`, `_engine_with_virtual_kit`) still pass plain-dict fixtures, so attribute access there would break them. That's the next follow-on (migrate those fixtures → sweep `render_tree`). The green-gate caught this automatically.
- The bulk of this sweep was produced by a senior-engineer agent under a precise rule + the dual oracle (full suite + byte-gate), then reviewed: scope verified (only `default_meta_commands.py`), both oracles independently re-run green, one `.get`-default site tightened (`p.fqcn or ""`).

### Versions

- dazzlecmd 0.8.7 -> 0.8.8 (PATCH).
- dazzlecmd-lib 0.7.5 -> 0.7.6 (PATCH -- default_meta_commands attribute sweep).
- dazzle-dz alias -> 0.8.8; deps re-pinned to >=0.8.8 / >=0.7.6.

## [0.8.7] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 6a: the test-fixture migration. Adds the public `dazzlecmd_lib.testing` entity factory and ports test fixtures from ad-hoc dict literals to real entities, so the upcoming prod attribute-sweep won't break dict-based tests. Test-only + a new test-support module; byte-identical (no prod call-site changes). Local-only.

### Added

- `dazzlecmd_lib.testing` — public, permanent test factory: `make_tool(**fields)` / `make_kit(**fields)` / `make_aggregator(**fields)` build real `DazzleEntity` objects via `build_entity`, normalizing legacy `_`-prefixed keys (`_dir`→`directory`, etc.) and applying the set-once `fqcn`. The blessed way to construct test entities — for dazzlecmd and any consumer (wtf, amdead, third-party aggregators). Not a transitional shim; it stays.

### Changed

- Test fixtures migrated from dict literals to `make_tool`/`make_kit` in: `tests/test_engine_recursive.py`, `tests/test_cli_helpers.py`, `tests/test_cli_list_sections.py`, `tests/test_cli_setup.py`, `tests/test_cli_kit.py`, `tests/test_library.py`, `packages/dazzlecmd-lib/tests/test_mode_parameterization.py`. Only genuine tool/kit ENTITY fixtures were converted; non-entity dicts (runtime/condition/template/setup blocks, resolver inputs, JSON-written-to-disk, config, expected-output) intentionally remain dicts. Nine candidate files were confirmed to contain no entity fixtures (no change).

### Notes

- Groundwork for the prod attribute-sweep (Stage 6b+): with fixtures now producing real entities, prod call sites can migrate `entity["x"]` → `entity.x` without breaking dict-based tests. Resolver/runner-factory test inputs (`test_resolve_runtime`, `test_docker_runner`, `_resolve_remote_url`, etc.) stay dicts until those specific prod paths are swept.

### Versions

- dazzlecmd 0.8.6 -> 0.8.7 (PATCH).
- dazzlecmd-lib 0.7.4 -> 0.7.5 (PATCH -- new `testing` factory module).
- dazzle-dz alias -> 0.8.7; deps re-pinned to >=0.8.7 / >=0.7.5.

## [0.8.6] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 5: type the full manifest schema. The foundation for the complete dict→attribute migration (the project is now committed to removing the dict shim entirely, not keeping it indefinitely). Additive and byte-identical: manifest keys move from `extra` to typed fields, so attribute access (`entity.runtime`, `entity.taxonomy`) is always safe — while the shim keeps working. No call-site changes yet. Local-only.

### Changed

- `dazzlecmd_lib.entity.DazzleEntity` — the known manifest schema is now typed fields (defaults chosen to match each field's dominant `.get(key, default)` call site, so adding them is byte-identical): `language`, `platform` (`"cross-platform"`), `runtime`/`taxonomy`/`lifecycle`/`dependencies`/`name_rewrite` (dict), `platforms` (list of supported-platform names — distinct from the per-platform dict nested under `runtime`), `tools` (list), `pass_through`/`always_active`/`virtual` (bool), `setup` (`Optional[dict]`), `long_description` (str). `extra="allow"` stays, so novel/tool-specific keys still round-trip — read via `entity.model_extra` (the explicit no-shim path). `source` is intentionally left in `extra`: it's polymorphic (a kit's is a URL string, a tool's is a `{"url": ...}` dict) and can't be one typed field on the shared base. `_`-prefixed manifest keys (`_vars`, `_schema_version`) stay in `extra` too (Pydantic can't have `_`-prefixed fields).

### Notes

- Internal: `"runtime" in entity` (and other now-typed keys) is always true (the field exists). The shim ratchet now warns for these as typed-field access. Membership-on-typed-key checks should test the value.
- This is additive only — the per-file attribute sweep (converting `entity["x"]` → `entity.x`) and the test-fixture migration (dict literals → `build_entity`) are the following stages.

### Tests

- `test_entity.py` ratchet tests updated: `runtime`/`taxonomy` are now typed (shim access warns); a novel key like `script`/`tags` is the `extra` example.

### Versions

- dazzlecmd 0.8.5 -> 0.8.6 (PATCH).
- dazzlecmd-lib 0.7.3 -> 0.7.4 (PATCH -- typed manifest schema on the entity model).
- dazzle-dz alias -> 0.8.6; deps re-pinned to >=0.8.6 / >=0.7.4.

## [0.8.5] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 4: the ratchet foundation. Establishes the test-time migration ratchet that the per-file attribute sweep will use. No production behavior change (the ratchet is off by default); byte-identical. Local-only.

### Changed

- `dazzlecmd_lib.entity` — the shim deprecation ratchet now warns **only for typed-field/property access** (`entity["name"]`, `entity["_dir"]`), not for extra/nested-block access (`entity["runtime"]`, `entity.get("tools")`). Extra keys have no safe attribute form (`entity.always_active` raises when absent), so dict access to them is legitimate and permanent — the ratchet targets exactly the access that *should* migrate. Also fixed a pre-existing double-warn in `get()` (now routes through the no-warn `_raw_get`). The ratchet stays **off by default** (`_warn_on_shim = False`), so production / wtf / amdead are unaffected (D2).

### Added

- `assert_no_shim_access(callable)` test fixture (in both `tests/conftest.py` and `packages/dazzlecmd-lib/tests/conftest.py`) — flips the ratchet on for one operation and asserts it triggers no typed-field shim access. This is the D2-safe enforcement mechanism (replaces the DWP's global-flip plan, which would have leaked warnings into wtf/amdead since they share the `DazzleEntity` class). The per-file sweep adds an assertion per fully-migrated operation.

### Tests

- `test_entity.py` — `test_ratchet_warns_only_for_typed_keys` (typed warns; extra and `in` stay silent) and `test_assert_no_shim_access_helper` (helper passes attribute/extra access, fails typed shim access).

### Versions

- dazzlecmd 0.8.4 -> 0.8.5 (PATCH).
- dazzlecmd-lib 0.7.2 -> 0.7.3 (PATCH -- typed-only ratchet + `get()` double-warn fix).
- dazzle-dz alias -> 0.8.5; deps re-pinned to >=0.8.5 / >=0.7.3.

## [0.8.4] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 3: promote the computed runtime fields from `_`-prefixed extra keys to typed model fields. The first dispatch-touching stage. Byte-identical across every `dz`/`wtf`/`amdead` surface (verified); the engine and all readers are untouched — a legacy-key alias map keeps existing `project["_dir"]`/`project["_fqcn"]` access working transparently while readers migrate later. Local-only.

### Changed

- `dazzlecmd_lib.entity.DazzleEntity` — 11 computed runtime values are now typed fields instead of `_`-prefixed extra keys: `short_name`, `kit_import_name`, `directory` (was `_dir`), `manifest_path`, `cached`, `kit_source` (was `_source` — renamed to avoid colliding with the manifest `source` block), `kit_name`, `kit_active`, `auto_realpath_alias`, `canonical_fqcn`, `original_name`. The canonical `fqcn` stays a set-once property (C1). A `_LEGACY_KEY_MAP` routes legacy dict access (`["_dir"]`, `.get("_kit_active")`, `["_fqcn"] = ...`) — read and write — to the promoted field/property, so no reader had to change yet. `to_manifest()` strips the computed fields (via `_COMPUTED_FIELDS`) so they never leak into a serialized manifest.
- `dazzlecmd_lib.loader` — discovery now writes the promoted field names (`directory`/`manifest_path`/`cached`/`kit_source`/`kit_name`) into the manifest dict before `build_entity`, so validation populates the typed fields.
- `dazzlecmd_lib.mode.cache_manifest` — uses `manifest.to_manifest()` for entities (and the legacy `_`-prefix filter for the dict path), so the now-non-underscore computed fields are not cached as manifest data.

### Notes

- Behavior change (internal): `"_cached" in entity` (and other promoted keys) is now always true because the field always exists — membership should check the value (`entity["_cached"] is False`). The only production membership check is on `_fqcn`, which remains a property (extra-backed), so its membership semantics are unchanged. `_vars` (manifest data that starts with `_`) is still stripped by `to_manifest`/`cache_manifest` as before — rescuing it is a separate, deferred fix.

### Tests

- `test_entity.py::TestShimMapping::test_items_view_after_field_promotion` — promoted keys surface under their field names; `_fqcn` stays extra-backed; `to_manifest` strips both.
- `test_mode.py` — the entity behavioral tests + the cache-fallback test updated for the field-based model (`cached` value check instead of key membership).

### Versions

- dazzlecmd 0.8.3 -> 0.8.4 (PATCH).
- dazzlecmd-lib 0.7.1 -> 0.7.2 (PATCH -- entity field promotion + loader/mode wiring).
- dazzle-dz alias -> 0.8.4; deps re-pinned to >=0.8.4 / >=0.7.2.

## [0.8.3] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 2: the write-path safety net. Test-only; no source change (ratchet stays off). Builds entity-fixture coverage for the mutate commands before the big attribute sweep — closing the gap that let the 0.8.1 `dz mode switch` crash ship undetected. Local-only.

### Tests

- `test_mode.py::TestModeSwitchEntityBehavior` — drives the real `cmd_switch` flow with REAL `DazzleEntity` projects (not dict literals), against a temp project_root + temp config (never real submodules): `test_switch_to_publish_dry_run_with_entity` exercises the exact crash path (`cmd_switch` → `_switch_to_publish` → `cache_manifest(entity)` runs before the dry-run gate) and asserts the cached manifest is written without `_`-keys; `test_switch_to_dev_dry_run_with_entity` covers the dev plan; `test_switch_to_dev_real_mutation_with_entity` runs a **non-dry-run** dev switch — actually creating a junction/symlink and verifying it resolves to the dev source — to prove the full mutate path (rmtree → `create_link` → remember) works with an entity, not just the plan.
- Coverage note: the kit enable/disable write path is already entity-exercised via `test_cli_kit.py` (real `AggregatorEngine`); `add`/`new` carry no `.items()`-on-entity crash class. The mode-switch publish path was the one untested mutate path.

### Versions

- dazzlecmd 0.8.2 -> 0.8.3 (PATCH -- tests only; full suite 1252 passed / 14 skipped).
- dazzlecmd-lib unchanged at 0.7.1 (no library source change).
- dazzle-dz alias -> 0.8.3; deps re-pinned to >=0.8.3 / >=0.7.1.

## [0.8.2] - 2026-06-07

Phase 1 (DazzleEntity call-site migration) — Stage 1. Completes the entity shim into a faithful read-Mapping and fixes a latent crash the 0.8.1 byte-identical gate missed. Local-only milestone; no push until the full 0.8.x port is verified.

### Fixed

- `dz mode switch <tool>` (publish) no longer crashes. `mode.cache_manifest()` does `{k: v for k, v in manifest.items() ...}`, and for any *discovered* tool `manifest` is a `DazzleEntity` — but the shim had no `.items()`, so the common path raised `AttributeError`. The byte-identical gate covered `dz mode status`, never `dz mode switch`, and the `cache_manifest` tests passed dict literals (never an entity), so the regression was invisible.

### Changed

- `dazzlecmd_lib.entity.DazzleEntity` — the backward-compat shim is now a faithful read-Mapping: added `keys()` / `values()` / `items()` (plus a no-warn `_raw_get` so they warn once per call, not once per item). Each routes through the deprecation ratchet, so they're still flagged for the Phase 1 migration. `__iter__` / `__len__` are deliberately NOT overridden — pydantic v2's `BaseModel.__iter__` yields `(field, value)` tuples and `dict(entity)` relies on that contract; no top-level call site iterates a single entity.

### Tests

- `test_entity.py::TestShimMapping` — keys/values/items fidelity (fields + extra incl computed `_`-keys), `__contains__` agreement, `dict(entity)` still works, ratchet-warns, silent-by-default.
- `test_mode.py::test_cache_manifest_accepts_entity` — the missing real-object regression: `cache_manifest` with an actual `Tool` entity (not a dict literal).

### Versions

- dazzlecmd 0.8.1 -> 0.8.2 (PATCH).
- dazzlecmd-lib 0.7.0 -> 0.7.1 (PATCH -- shim Mapping methods on `entity.py`).
- dazzle-dz alias -> 0.8.2; deps re-pinned to >=0.8.2 / >=0.7.1.

## [0.8.1] - 2026-06-07

Foundational redesign: a typed `DazzleEntity` object model replaces anonymous dicts for tools / kits / aggregators, with the {grouping, ungrouping} primitive as a capability (`Groupable`). The 0.8.x line is a deliberate cheap-rollback fork point (the 0.7.54 baseline is the fallback). Built in staged sub-commits: 0.8.0 (Stage 1, the standalone model) and this 0.8.1 (Stages 2-5, wiring + release). Design: the DazzleEntity synthesis DWP + a 5-round /collaborate3 validation (project-private design folder). The migration boundary is the top-level entity only -- nested blocks (`runtime`, `_vars`, `volumes`, `platforms`, `setup`) stay plain dicts -- and the backward-compat shim keeps the ~252 existing dict-access call sites working unchanged, so the user-facing output of `dz` / `wtf` / `amdead` is byte-identical to 0.7.54 (verified against captured baselines; only the version string changes).

### Added

- `dazzlecmd_lib.entity` -- the object model. `Groupable` (the universal grouping/ungrouping capability mixin: the 5 verbs GROUP/UNGROUP/HIDE/EXPOSE/REBIND + the C1/C2/C3 canonical-identity contract); `DazzleEntity(Groupable, BaseModel)` (base for on-tree co-level occupants -- `extra="allow"` + a backward-compat shim so existing dict access keeps working, set-once canonical FQCN, `to_manifest`); the `Tool`/`Kit`/`Aggregator` discriminated union (open for future `Property`/`Environment`) with `detect_type`/`build_entity` and `AmbiguousEntityTypeError` (hard-fail on ambiguous markers). Standalone in Stage 1 -- not yet wired into the loader/engine. (Stage 1)
- `dazzlecmd_lib.core.links` -- the first inhabitant of the constitutional `dazzlecmd_lib.core` namespace. The four public link primitives (`is_linked_project`, `get_link_target`, `create_link`, `remove_link`) relocated verbatim from `dazzlecmd_lib.paths`; `paths` re-exports them (import identity preserved) so existing `from dazzlecmd_lib.paths import is_linked_project` call sites keep working. (Stage 5)
- `AggregatorConfig.presentation` -- reserved `Optional[dict]` slot for the "skin" half of same-bones (per-aggregator presentation / projection config). Parsed and validated-as-object when present, but not yet consumed; the projection layer that interprets it lands in a later release. (Stage 5)

### Changed

- `dazzlecmd_lib.aggregator_config` -- `AggregatorConfig` / `AggregatorSchema` / `AggregatorDiscovery` converted from frozen dataclasses to frozen Pydantic models (uniform validation + JSON-Schema export; composable into the `Aggregator` entity). Public API (`config.schema.remote_url_paths`, etc.) and all validation / error messages unchanged. (Stage 2)
- `dazzlecmd_lib.loader` -- discovery now constructs typed `DazzleEntity` instances instead of returning bare dicts: `discover_kits` builds `Kit` entities and `_load_manifest` / `_load_cached_manifest` build `Tool` entities via `build_entity`. The loader is the sole author of entities (one canonical instance per canonical FQCN). (Stage 3)
- `dazzlecmd_lib.registry` / `dazzlecmd_lib.engine` -- entity-clone sites switched from `dict(project)` (which would silently drop a BaseModel to its field names) to `model_copy()`, guarded for the transitional dict-or-entity period. (Stages 3-4)
- `dazzlecmd_lib.engine._annotate_project_fqcn` -- now calls `reserve_field_axis(...)`, the single enforcement point that rejects `.` in any name / namespace segment. This reserves `.` for the future field-access axis (two-axis FQCN: `:` for hierarchy, `.` for field descent) without touching the ~13 scattered `:`-parse sites. (Stage 4)

### Versions

- dazzlecmd 0.8.0 -> 0.8.1 (PATCH -- completes the object-model redesign begun in 0.8.0; user-facing output unchanged. The 0.7 -> 0.8 MINOR bump landed at 0.8.0).
- dazzlecmd-lib 0.6.15 -> 0.7.0 (MINOR -- new `entity` + `core.links` modules; `aggregator_config` internals reworked, public API unchanged. First library release carrying the entity model).
- dazzle-dz alias -> 0.8.1; deps re-pinned to >=0.8.1 / >=0.7.0.

## [0.7.54] - 2026-06-07

Final 0.7.x housekeeping commit, landed to give the 0.8.0 DazzleEntity foundational redesign a clean baseline to diff against. No new tools: the dazzletools / media / file-ops batch sitting in the working tree is parked and each ships as its own MINOR after the refactor. Pure framework / infra / test-doc cleanup.

### Changed

- `dazzlecmd_lib.mode._print_no_toggle` -- replaced a Unicode em dash with `--` in the embedded-tool error message (Windows codepage safety, per the no-Unicode-in-shell-output rule).
- `pyproject.toml` -- `[tool.pytest.ini_options].norecursedirs` now includes `one-offs`, so `tests/one-offs/` (the scratchpad) is excluded from regression discovery.

### Added

- `tests/checklists/v0.7.54__Phase3.5__T1-J-mode-and-aggregator-chain.md` -- consolidated human checklist for the Phase 3.5 mode + cross-aggregator chain (covers v0.7.47-v0.7.53), plus its tester-unbounded run result under `tests/checklists/results/`.
- `tests/one-offs/wrap_commit_msg.py` -- commit-message body re-wrap utility (72-col), preserving subject / blank / header / list lines.

### Refs

- Refs #37 (Phase 3.5 EPIC). Closes the 0.7.x housekeeping tail; 0.8.0 begins the DazzleEntity universal-polymorphic-base redesign (design + /collaborate3 validation recorded in the project's private design folder).

### Versions

- dazzlecmd 0.7.53 -> 0.7.54 (PATCH).
- dazzlecmd-lib 0.6.14 -> 0.6.15 (PATCH -- the mode.py cosmetic fix).
- dazzle-dz alias -> 0.7.54; deps re-pinned to >=0.7.54 / >=0.6.15.

## [0.7.53] - 2026-05-27

Closes the Phase 3.5 T1-M cross-aggregator loop: bumps the embedded `projects/wtf` submodule to wtf-windows `d48a334` (v0.1.5-alpha, the T1-M2 migration) and validates the recursive chain end-to-end. dazzlecmd (T1-M1) now embeds the fully-declarative wtf (T1-M2, with its own `aggregator.json`), and `dz wtf:core:locked` resolves into the nested aggregator's tool.

### Changed

- `projects/wtf` submodule pointer bumped `25af04e` -> `d48a334` (wtf-windows v0.1.4-alpha -> v0.1.5-alpha). The embedded wtf now carries its own `aggregator.json` and consumes `dazzlecmd_lib.mode` instead of a forked copy.

### Verified (recursive-chain validation)

With the `wtf` kit enabled (`dz kit enable wtf`): `dz list` shows the `wtf:core:` section (locked, restarted); `dz wtf:core:locked --help` dispatches into the nested wtf tool (`wtf-locked` usage). Confirms dazzlecmd discovers the embedded declarative aggregator and 3-tier FQCN dispatch resolves through to its tools -- the whole T1-M arc (M1 dazzlecmd + M2 wtf + the v0.7.52 impersonation fix) works as a chain, not just per-aggregator.

### Notes

- The `wtf` kit is opt-in (`[disabled (not in active_kits)]` by default). `dz wtf:...` only resolves after `dz kit enable wtf`; this is deliberate (wtf is a diagnostic aggregator users opt into), not a discovery failure.
- `kits/wtf.kit.json` still carries `_override_tools_dir` / `_override_manifest` fields. Now that the embedded wtf declares those in its own `aggregator.json`, a future commit can retire the overrides and have dazzlecmd's nested-aggregator discovery read wtf's `aggregator.json` directly. Left as-is here to keep this commit a pure submodule bump.

### Refs

- Refs #37 (Phase 3.5 EPIC). Completes the T1-M sub-arc (M1 + M2 + the v0.7.52 fix); the embedded-wtf override cleanup is the remaining T1-M tail.

### Versions

- dazzlecmd 0.7.52 -> 0.7.53 (PATCH -- submodule pointer bump + recursive-chain validation; no library or CLI code change).
- dazzlecmd-lib unchanged at 0.6.14.
- dazzle-dz alias bumped to 0.7.53; deps re-pinned to >=0.7.53 / >=0.6.14.

## [0.7.52] - 2026-05-26

Fixes the cross-aggregator impersonation regression introduced by v0.7.51's `find_aggregator_root()`, surfaced during the wtf-windows T1-M2 migration. Pre-fix, `dz` run from inside another aggregator's tree (e.g. `C:\code\wtf-windows`) loaded *that* aggregator's `aggregator.json` and became `wtf` -- `dz github` would error with `wtf: invalid choice: 'github'`. An entry point's identity must be fixed by which package it is, not by the directory it's invoked from.

### Fixed

- **`dz` no longer impersonates a sibling aggregator based on cwd.** `src/dazzlecmd/cli.py:main()` now anchors `find_aggregator_root()` to the dazzlecmd package's own `__file__` (`os.path.dirname(os.path.abspath(__file__))`) instead of calling it bare. Since dazzlecmd is installed (editable) from its project tree, the package `__file__` resolves to that tree, so `dz` always finds dazzlecmd's `aggregator.json` regardless of cwd. The bug was dormant in v0.7.51 (no sibling `aggregator.json` existed yet) and went live the moment T1-M2 deployed one to wtf-windows -- exactly the cross-aggregator coexistence the cwd-first default couldn't handle.
- **`dazzlecmd_lib.aggregator_config.find_aggregator_root()` simplified** to remove the footgun. v0.7.51's `None`-default did a two-stage walk: cwd first, then the library's own `__file__`. The cwd-first stage caused the impersonation; the lib-`__file__` stage was *worse* for multi-aggregator dev (the library lives co-located with dazzlecmd, so any aggregator calling it bare resolved to dazzlecmd). Now: `start_path=None` walks cwd only (a deliberate "find from here" for tests/ad-hoc), and the documented contract is that **production entry points MUST pass their package anchor**. The original temp-dir `dz git-snapshot` test stays green because dazzlecmd's `main()` anchors to its package, found from any cwd.
- **wtf-windows test fixture corrected.** `packages/dazzlecmd-lib/tests/fixtures/aggregator-json/wtf-windows.aggregator.json` was wrong on four fields vs wtf's actual config (discovered authoring T1-M2): `enabled_meta_commands` (had tree/setup/mode; should be `[list, info, kit, version]`), `extra_reserved_commands` (had `[]`; should be `[mode, new, add, enhance, graduate]`), `schema.remote_url_paths` (had `lifecycle.remote`; should be `[source.url]` to match wtf's real tool manifests), and `description`. Now matches what shipped to the real wtf-windows repo.
- **Test config isolation.** Added an autouse `_isolate_user_config` fixture in `tests/conftest.py` that points `DAZZLECMD_CONFIG` at a nonexistent path for every test. Unit tests that build `AggregatorEngine(is_root=True)` without isolating config previously read the developer's real `~/.dazzlecmd/config.json`; its active-kits state varies by machine and by recently-run `dz`/`wtf` commands, making config-sensitive tests (the `render_tree` virtual-kit branches, which filter to active kits) pass/fail on ambient state. The fixture forces built-in defaults; tests that need a real config still override `DAZZLECMD_CONFIG` themselves.

### Tests

- `test_default_falls_back_to_lib_file_when_cwd_misses` replaced by `test_default_is_cwd_only_no_lib_fallback` (asserts the removed lib-fallback) + `test_explicit_anchor_ignores_cwd` (regression guard: an anchored call resolves to ITS project even when cwd is inside a different aggregator's tree).
- `test_wtf_windows_draft_parses` updated for the corrected fixture (enabled_meta_commands = {list,info,kit,version}; mode/new/add/enhance/graduate reserved-not-enabled; schema = (source.url,)).
- The 4 `render_tree` virtual-kit/shadow tests now pass deterministically (were failing on this machine due to the config leakage above).
- 1223 passed, 14 skipped (was 1222 / 14 in v0.7.51; +1 net from the find_aggregator_root test split).

### What's NOT in this commit (gated on the wtf-windows push)

- Bump the `projects/wtf` submodule pointer to wtf-windows `d48a334` (the T1-M2 commit) -- requires that commit pushed to `github.com/djdarcy/wtf-windows.git` first.
- Recursive-chain validation (`dz wtf:core:locked`) against the new declarative wtf -- meaningful only after the submodule bump.

### Refs

- Refs #37 (Phase 3.5 EPIC). Companion to dazzlecmd v0.7.51 (T1-M1) and wtf-windows v0.1.5-alpha (T1-M2); fixes the regression those surfaced.

### Versions

- dazzlecmd 0.7.51 -> 0.7.52 (PATCH -- bugfix: cwd-impersonation regression + test isolation).
- dazzlecmd-lib 0.6.13 -> 0.6.14 (PATCH -- `find_aggregator_root` default simplified; behavior change is a footgun removal).
- dazzle-dz alias bumped to 0.7.52; deps re-pinned to >=0.7.52 / >=0.6.14.

## [0.7.51] - 2026-05-24

Phase 3.5 Tier 1 commit 4 of N (refs #37, closes #74) -- bundles T1-M1 (dazzlecmd's own declarative-config deployment) with the resolution of issue #74. Both changes are runtime-vs-static halves of the same architectural shift: `aggregator.json` declares the aggregator's IDENTITY statically; `DZ_APP_NAME` / `DZ_COMMAND` env-var injection makes that identity flow to subprocess tool scripts at runtime. Shipping them together means downstream aggregators get one coherent declarative+runtime story instead of stair-stepped commits with a gap in between.

T1-M1 retires the hardcoded-kwargs constructor in `src/dazzlecmd/cli.py:main()`. The new shape is a 5-line `find_aggregator_root() + AggregatorEngine.from_project()` pattern that's identical across aggregators -- per-aggregator knobs (name, command, tools_dir, kits_dir, manifest_name, enabled_meta_commands, extra_reserved_commands, schema, discovery) all live in the new `aggregator.json` at the project root. Closes the dazzlecmd side of T1-M; wtf-windows and amdead adopt the same pattern in their own repos as T1-M2 and T1-M3 (separate downstream commits).

Issue #74 closes the symmetric runtime gap: pre-fix, downstream aggregators each hand-rolled an `os.environ["AGGREGATOR_APP_NAME"]` bridge so their PowerShell / bash / Python tool scripts could read the aggregator's branding strings. The lib now injects `DZ_APP_NAME` / `DZ_COMMAND` automatically at every subprocess dispatch site; tool scripts read `$env:DZ_APP_NAME` / `$env:DZ_COMMAND` (or equivalent) and adapt to whichever aggregator invoked them. One mechanism, all consumers benefit.

### Added

- `aggregator.json` at the dazzlecmd project root. Declares dazzlecmd's identity (`name: "dazzlecmd"`, `command: "dz"`, 11 fields total including layout, meta-command policy, schema, discovery patterns). Read by `AggregatorEngine.from_project()` at startup. Copied verbatim from the existing fixture at `packages/dazzlecmd-lib/tests/fixtures/aggregator-json/dazzlecmd.aggregator.json`.
- `dazzlecmd_lib.aggregator_config.find_aggregator_root(start_path=None, max_depth=12)` -- helper that walks up from `start_path` looking for the canonical `aggregator.json` marker file. The first ancestor with the marker IS the project root. When `start_path=None`, a two-stage fallback chain runs: first `os.getcwd()` (user inside the project tree), then `os.path.dirname(__file__)` of the helper module itself (dev-mode fallback where the lib lives co-located with the project tree). This second stage preserves the pre-T1-M behavior of "dz works when invoked from any cwd in a dev-mode install" -- without it, `dz git-snapshot` invoked from a temp directory during a test (or from `C:\code\wtf-windows` for that matter) would fail because the test cwd has no `aggregator.json` ancestor.
- `DZ_APP_NAME` and `DZ_COMMAND` environment variables injected before every tool dispatch (issue #74). Both injection sites covered: `_run_tool()` (the registry path that drives all modern aggregators) and `_run_escape_hatch()` (the backward-compat path that dazzlecmd's own `cli.py` currently uses). Restore semantics match the existing `DZ_CANONICAL_FQCN` / `DZ_INVOKED_FQCN` pattern -- prior values backed up before injection, restored in a `finally` block via `os.environ.pop(key, None)` (handles "not present before" correctly).

### Changed

- `src/dazzlecmd/cli.py:main()` -- rewritten as a thin wrapper around `find_aggregator_root() + AggregatorEngine.from_project()`. Was 17 lines of hardcoded constructor kwargs; now 15 lines including the project-root-not-found error path. Identity / layout / policy moved to `aggregator.json`; runtime callbacks (`build_parser` / `dispatch_meta` / `dispatch_tool`) remain code because they are code (argparse builders and dispatch logic can't be declarative). Pattern copies cleanly to wtf-windows / amdead / any future aggregator.
- `dazzlecmd_lib.engine.AggregatorEngine._run_tool()` -- branding env-var injection block added at the start, OUTSIDE the `if context is not None:` gate. Branding vars reflect engine identity (not per-invocation context) so they're always set, regardless of whether the FQCN ResolutionContext is passed. The `env_backup` dict accumulates both branding and FQCN vars; the restore block in `finally:` iterates the whole dict, so the gate at restore time was removed too (was previously also `if context is not None:` -- safe to drop because the same dict is the source of truth in either case).
- `dazzlecmd_lib.engine.AggregatorEngine._run_escape_hatch()` -- same branding env-var injection block added in the escape-hatch path that dazzlecmd's own legacy `dispatch_tool` callback uses today. Without this, dazzlecmd itself wouldn't see its own DZ_APP_NAME / DZ_COMMAND vars in tool subprocesses (because dazzlecmd dispatches through escape-hatch, not registry). Future commits migrating dazzlecmd to the registry path get the branding vars for free from `_run_tool()`.

### Tests

- 11 new tests across two files. `packages/dazzlecmd-lib/tests/test_aggregator_config.py::TestFindAggregatorRoot` (6 cases): direct-hit, walks-up-from-deep-ancestor, returns-None-on-miss, honors-max-depth, max-depth-zero-finds-self, default-falls-back-to-lib-`__file__`-when-cwd-misses. `tests/test_env_var_injection.py::TestBrandingEnvVarInjection` (5 cases): branding-vars-match-engine-identity, branding-vars-reflect-arbitrary-aggregator-identity (proves wtf-windows / amdead would get their own values), branding-vars-injected-without-context (engine identity is not context-gated), branding-vars-restored-after-dispatch, branding-vars-popped-when-not-pre-existing.
- Test totals: 1222 passed, 14 skipped (was 1211 / 14 in v0.7.50; +11 new).

### Fixed

- Mid-commit regression caught + fixed: the deployed `aggregator.json` (and its fixture) listed `find`, `git`, `github`, `f`, `safedel`, `snapshot`, `fixpath` in `extra_reserved_commands`. Those names are ACTUAL TOOLS in `projects/core/` (e.g., `projects/core/find/`), not reserved-but-unused names. Post-T1-M1 the new `from_project()` path threaded that list through to the discovery layer, which silently skipped the matching tools -- so `dz find`, `dz git`, `dz safedel`, `dz fixpath`, `dz github` would have stopped working as short-name commands. Fix: clear `extra_reserved_commands` to `[]` in both the deployed file and the fixture; add a regression-guard assertion to `test_dazzlecmd_draft_parses` that `"find" not in cfg.reserved_commands`. Pre-T1-M1's hardcoded constructor never passed `extra_reserved_commands`, so the tools loaded fine then; the bug was a fixture-authoring error that only surfaced after `from_project()` read the file.

### Refs

- Refs #37 (Phase 3.5 EPIC -- mode-system expansion for non-submodule tool sources). T1-M1 completes the dazzlecmd-side declarative-config deployment.
- Closes #74 (dazzlecmd-lib: inject DZ_APP_NAME / DZ_COMMAND env vars in `_run_tool()` for child-process branding access). Implements all 9 acceptance criteria items: (1+2) injection in both `_run_tool` registry path and `_run_escape_hatch`, un-gated from `context is not None`; (3) env_backup/restore-in-finally semantics match the existing `DZ_CANONICAL_FQCN` pattern; (4) env-var contract documented in `aggregator_config.py` module docstring; (6) nested-aggregator behavior documented in the same docstring (root engine's name/command reach kit-imported tool subprocesses); (7) tests assert that a tool dispatcher sees `os.environ["DZ_APP_NAME"]` equal to `engine.name` -- this is the unit-level assertion; a real-subprocess shellout test is deferred to a follow-up issue alongside item (5) the `_branding.ps1` reference template; (8) CHANGELOG entry references this issue; (9) `DZ_PROJECT_ROOT` deferral decision recorded in the env-var contract docstring (deferred to a follow-up issue; introduces tool-to-aggregator filesystem coupling that warrants a separate design pass).

### What's NOT in this commit (scheduled for v0.7.52+)

- T1-M2 (wtf-windows side): deploy `wtf-windows.aggregator.json` at the wtf-windows project root + rewrite wtf's `main()` to use `find_aggregator_root() + from_project()` + DELETE wtf's duplicated `mode.py` and migrate callers to `dazzlecmd_lib.mode` + optionally add `_branding.ps1` consuming the new DZ_APP_NAME/DZ_COMMAND vars. Ships as a commit in the wtf-windows repo with its own version bump.
- T1-M3 (amdead side): same as T1-M2 in the amdead repo.
- After both downstream commits land: dazzlecmd v0.7.52 bumps the wtf-windows submodule pointer and runs the recursive-chaining tests (`dz wtf <subtool>`) to validate the dazzlecmd <-> wtf chain end-to-end on the new declarative pattern.
- T1-J (consolidated human test checklist) ships with v0.7.52 once the chain is real.

### Design

- 2026-05-17__22-38-36__dev-workflow-process__phase-3-5-mode-system-hardening-shipped-vs-missing.md
- 2026-05-07__00-07-55__claude-plan__0-7-x-closeout-ultraplan-with-x28-copy-dont-rewrite-addendum.md
- GitHub issue #74 (issue body documents the parallel-invention prototype from amdtoy that this commit retires)

### Versions

- dazzlecmd 0.7.50 -> 0.7.51 (PATCH -- internal `main()` refactor + additive env-var injection; default behavior preserved for end users; new behavior is purely additive for tool-script authors).
- dazzlecmd-lib 0.6.12 -> 0.6.13 (PATCH -- additive `find_aggregator_root()` helper + additive branding env-var injection in two engine code paths).
- dazzle-dz alias bumped to 0.7.51; deps re-pinned to >=0.7.51 / >=0.6.13.

## [0.7.50] - 2026-05-19

Phase 3.5 Tier 1 commit 3 of N (refs #37). Ships the T1-E safety primitive flagged as CRITICAL by the senior-engineer audit: a dirty-tree refuse-or-force gate at every `shutil.rmtree(tool_dir)` call site in `dazzlecmd_lib.mode`. Pre-fix, `dz mode switch` would silently destroy uncommitted work in a tool subtree -- a user who had been mid-edit in a submodule checkout (or in a local-only directory that happened to be its own git repo) lost their changes the moment they ran the switch. Post-fix, the switch refuses with exit code 1 and prints the dirty file list plus an actionable hint; the new `--force` flag bypasses the check for users who genuinely want the destructive behavior.

### Added

- `dazzlecmd_lib.mode._check_dirty_tree(tool_dir)` -- new helper. Returns `git status --porcelain` output for `tool_dir` if it is its own git worktree root; returns the empty string (clean / no work to lose) when `tool_dir` is not a directory, not a git checkout, or is only inside an ancestor's repo. The "own worktree root" check uses `git rev-parse --show-toplevel` and compares the realpath against `tool_dir` -- without it, `git status` walks up the directory tree and reports an ancestor repo's dirty state (e.g., your `~/.git` if `tool_dir` happens to live under `$HOME`).
- `dazzlecmd_lib.mode._print_dirty_refusal(tool_name, tool_dir, dirty_output, command)` -- new helper. Prints the standard refusal-to-overwrite message. Truncates the dirty file list at 10 lines (full list is one `git status` away). Substitutes the aggregator's `command` into the suggested `<command> mode switch <tool> --force` recovery line.
- `--force` flag on `dz mode switch`. Threads to `cmd_switch(force=True, ...)` which threads to `_switch_to_dev(force, ...)` and `_switch_to_publish(force, ...)` to gate the `shutil.rmtree` call sites.

### Changed

- `dazzlecmd_lib.mode.cmd_switch(...)` signature gained `force=False`. Default behavior is the safe one: refuse to destroy uncommitted work; require explicit opt-in via `--force` or `force=True`. The dazzlecmd `cmd_switch` wrapper in `src/dazzlecmd/mode.py` accepts the new parameter and passes through.
- `dazzlecmd_lib.mode._switch_to_dev` and `_switch_to_publish` -- each gained a required `force` positional parameter. Each gates its `shutil.rmtree(tool_dir)` call site behind `if not force: dirty = _check_dirty_tree(tool_dir); if dirty: _print_dirty_refusal(...); return 1`.
- Dry-run output for both `_switch_to_dev` and `_switch_to_publish` now prints `[WARNING] Would refuse: <tool_dir> has uncommitted changes (rerun with --force).` ahead of the would-remove line when the tree is dirty -- users learn about the gate during dry-run instead of being surprised by the refusal during the live run.

### Tests

- 8 new tests in `packages/dazzlecmd-lib/tests/test_mode_parameterization.py`. `TestCheckDirtyTree` covers the 5 input shapes: non-existent path, plain non-git dir (verifies the `git rev-parse --show-toplevel` ancestor check works -- without it the test would report the home-repo's dirty state when run on a developer machine whose `%TEMP%` lives under `$HOME`), clean git repo, modified tracked file, untracked file. `TestSwitchRefusesDirty` exercises the gate end-to-end with real git fixtures: dirty submodule refuses with exit 1 and an "uncommitted changes" stderr message; the same scenario with `force=True` does NOT print the refusal; dry-run with a dirty tree prints the `[WARNING] Would refuse` line and does not delete anything.
- Test fixture `_init_git_repo` sets `commit.gpgsign=false` and `tag.gpgsign=false` locally on every test repo immediately after `git init`. Developer machines that have global `commit.gpgsign=true` (e.g., Kleopatra-signed dev configs) previously had the fixture's `git commit` invoke GPG signing per test run; the local override prevents the pinentry popups.
- Test totals: 1211 passed, 14 skipped (was 1203 / 14 in v0.7.49; +8 new).

### What's NOT in this commit (scheduled for v0.7.51+)

- T1-M1/M2/M3: deploy `aggregator.json` to dazzlecmd / wtf-windows / amdead project roots. The fixtures already exist; this is the rollout step.
- T1-I: migrate `dazzlecmd_lib.mode` tests from `tests/test_mode.py` (thin-wrapper-based) to `packages/dazzlecmd-lib/tests/test_mode_*.py` (library-native).
- T1-J: consolidated Phase 3.5 Tier 1 human test checklist covering v0.7.47 + v0.7.48 + v0.7.49 + v0.7.50 + the M1/M2/M3 deployment. Real end-to-end mode-switching testing requires the aggregator.json files to be in place, so the checklist makes more sense after T1-M lands.

### Refs

- Refs #37 (Phase 3.5 EPIC -- mode-system expansion for non-submodule tool sources). Closes the CRITICAL audit finding from v0.7.48; the remaining audit findings (MEDIUM x2 + LOW x1) were closed in v0.7.49.

### Design

- 2026-05-17__22-38-36__dev-workflow-process__phase-3-5-mode-system-hardening-shipped-vs-missing.md
- 2026-05-07__00-07-55__claude-plan__0-7-x-closeout-ultraplan-with-x28-copy-dont-rewrite-addendum.md

### Versions

- dazzlecmd 0.7.49 -> 0.7.50 (PATCH -- additive `--force` flag; the default-behavior change is a SAFETY tightening: pre-fix the switch silently destroyed user data, post-fix it refuses by default. PATCH semantics on the basis that "stop destroying user data without consent" is universally desirable).
- dazzlecmd-lib 0.6.11 -> 0.6.12 (PATCH -- additive `force` keyword parameter on `cmd_switch`/`_switch_to_dev`/`_switch_to_publish`; new `_check_dirty_tree` / `_print_dirty_refusal` helpers; behavioral default change is the safety-tightening above).
- dazzle-dz alias bumped to 0.7.50; deps re-pinned to >=0.7.50 / >=0.6.12.

## [0.7.49] - 2026-05-19

Phase 3.5 Tier 1 commit 2.5 of N (refs #37). Audit cleanup of the v0.7.48 mode-system parameterization. Four small surgical fixes that close audit findings without behavior regressions: tighten the `detect_tool_state` wrapper signature; thread `tools_dir` through `_print_no_toggle` so error messages no longer print the literal placeholder `<tools-dir>`; restore `_resolve_remote_url`'s default probe order to byte-match the v0.7.47 verbatim baseline (drop the unintentional `lifecycle.remote` probe drift); retire the `dazzlecmd.importer` link-helper re-export shim and update the four test files that referenced it to import from `dazzlecmd_lib.paths` directly.

### Changed

- `dazzlecmd.mode.detect_tool_state(tool_dir, gitmodules, project_root)` -- `project_root` is now a required positional parameter (was `project_root=None` with a fragile triple-`dirname` heuristic to derive it from `tool_dir`). The heuristic only worked for the standard `<project_root>/projects/<ns>/<tool>` layout; any non-standard layout silently returned `STATE_MISSING` instead of raising. The wrapper now matches the library's required-parameter signature 1:1. Five call sites in `tests/test_mode.py` updated to pass `project_root=tmpdir` (already in scope from the surrounding `tempfile.TemporaryDirectory()`).
- `dazzlecmd_lib.mode._print_no_toggle(tool_name, state, *, command, tools_dir)` -- gained a required `tools_dir` keyword-only parameter so the STATE_LOCAL_ONLY hint substitutes the aggregator's tool-root directory name. Pre-fix it printed `git submodule add <url> <tools-dir>/<ns>/<tool>` with `<tools-dir>` as a literal placeholder; now it prints `git submodule add <url> projects/<ns>/<tool>` for dazzlecmd, `tools/<ns>/<tool>` for wtf-windows / amdead, etc. The single call site in `cmd_switch` already had `tools_dir` in scope.
- `dazzlecmd_lib.mode._resolve_remote_url` default probe list is now `("source.url",)` -- matches the v0.7.47 verbatim baseline byte-for-byte. The previous v0.7.48 default `("source.url", "lifecycle.remote")` was an unintentional drift; `lifecycle.remote` was a new undocumented key that probed before the `lifecycle.graduated_to` fallback. Aggregators that legitimately want `lifecycle.remote` in their lookup chain should declare it in their `AggregatorSchema.remote_url_paths`.
- `tests/test_mode.py` -- updated 5 `detect_tool_state` call sites to pass the now-required `project_root` argument, and switched the top-of-file `from dazzlecmd.importer import is_linked_project, remove_link` (and two inline `from dazzlecmd.importer import create_link` imports) to `from dazzlecmd_lib.paths import ...`.
- `tests/test_importer.py` -- split the line `from dazzlecmd.importer import (add_from_local, is_linked_project, get_link_target, remove_link)` into the legitimate `from dazzlecmd.importer import add_from_local` plus a separate `from dazzlecmd_lib.paths import is_linked_project, get_link_target, remove_link`.
- `src/dazzlecmd/importer.py` -- the bottom-of-file `from dazzlecmd_lib.paths import (...)` re-export block is replaced with a top-of-file `from dazzlecmd_lib.paths import create_link, is_linked_project` (only the two helpers actually used inside the module's own `add_from_local` function). The re-export shim is gone.

### Removed

- `tests/test_paths.py::TestLibraryReExportFromDazzlecmdImporter` -- the test class that existed solely to verify the `dazzlecmd.importer` re-export shim worked. It was the only consumer of the now-removed shim aside from the four test imports updated above.

### Tests

1203 passed, 14 skipped (was 1204 / 14 in v0.7.48; -1 deleted shim test, no regressions).

### Refs

- Refs #37 (Phase 3.5 EPIC). Closes the audit-cleanup follow-up surfaced by the senior-engineer review of v0.7.48.

### Versions

- dazzlecmd 0.7.48 -> 0.7.49 (PATCH -- internal cleanup; the tighter `detect_tool_state` signature is a contract change but the only callers were 5 dazzlecmd tests, all updated in this commit; no external consumers).
- dazzlecmd-lib 0.6.10 -> 0.6.11 (PATCH -- additive `tools_dir` parameter on `_print_no_toggle`; default-probe behavior of `_resolve_remote_url` restored to match v0.7.47 baseline).
- dazzle-dz alias bumped to 0.7.49; deps re-pinned to >=0.7.49 / >=0.6.11.

## [0.7.48] - 2026-05-18

Phase 3.5 Tier 1 commit 2 of N (refs #37). Parameterizes the verbatim-moved `dazzlecmd_lib.mode` module so every aggregator can use it -- closes BLOCKERs F1-F8 from the senior-engineer audit. The X-28 copy-don't-rewrite discipline split the move (v0.7.47) from the modify (this commit) so the diff for the parameterization pass is reviewable against the verbatim baseline. `src/dazzlecmd/mode.py` becomes a 111-LOC thin wrapper -- it threads dazzlecmd's `tools_dir="projects"` and `command="dz"` defaults to the library and re-exports the public API for the existing tests that `from dazzlecmd.mode import ...`. The library's mode module is now aggregator-agnostic; wtf-windows (`tools_dir="tools"`) and amdead (`tools_dir="tools"`) can adopt it without forking.

### Added

- 25 new tests in `packages/dazzlecmd-lib/tests/test_mode_parameterization.py`. Parametric coverage across the three observed layouts (`projects/<ns>/<tool>`, `tools/<ns>/<tool>`, `src/tools/<ns>/<tool>`): `parse_gitmodules` correctly identifies submodules under any `tools_dir`; `_tool_dir_to_submodule_path` returns the right relative path via `os.path.relpath` regardless of layout (F8 fix); `detect_tool_state` returns SUBMODULE / EMBEDDED / LOCAL_ONLY correctly per layout; `cmd_status` formats output with the aggregator's `command` name; `_resolve_remote_url` honors schema-driven lookups for custom manifest layouts (F7 fix).

### Changed

- `dazzlecmd_lib.mode` -- all functions parameterized. Keyword-only `tools_dir` is required for every function that previously hardcoded the string `"projects/"`. `parse_gitmodules(project_root, *, tools_dir)` uses `tools_dir.rstrip("/") + "/"` as the gitmodules prefix check. `_tool_dir_to_submodule_path(tool_dir, project_root, *, tools_dir)` now uses `os.path.relpath(tool_dir, project_root)` plus `posixpath` normalization instead of substring search on `"projects/"` (F8 fix -- the substring search broke under any layout that wasn't `projects/`). `detect_tool_state(tool_dir, gitmodules, project_root, *, tools_dir)` threads the value through; `cmd_status(projects, project_root, tool_filter, kit_filter, *, tools_dir, command)` reports paths and hint text relative to the aggregator's layout; `cmd_switch(tool_name, projects, project_root, ..., *, tools_dir, command, schema)` accepts the optional schema for `_resolve_remote_url`. `_resolve_remote_url(project, explicit_url, *, schema)` uses a new `_dotted_lookup` helper that walks dotted paths from the `AggregatorSchema.remote_url_paths` config (F7 fix -- the library no longer assumes the dazzlecmd-specific manifest key names).
- `src/dazzlecmd/mode.py` -- rewritten as a 111-LOC thin wrapper (was 730 LOC). Re-exports state constants (`STATE_SUBMODULE`, `STATE_EMBEDDED`, `STATE_LOCAL_ONLY`, `STATE_SYMLINK`, `STATE_MISSING`, `STATE_LABELS`) and non-parameterized helpers (`load_local_config`, `save_local_config`, `cache_manifest`, `get_cached_manifest`) from `dazzlecmd_lib.mode`. Wraps the five parameterized functions (`parse_gitmodules`, `detect_tool_state`, `resolve_dev_path`, `cmd_status`, `cmd_switch`) with dazzlecmd's defaults so existing callers (`loader.py`, `cli.py`, tests) keep working unchanged. `detect_tool_state(tool_dir, gitmodules, project_root=None)` -- the optional `project_root` derives from the tool_dir via `os.path.dirname` x3, matching the standard layout, so the wrapper's contract is identical to the pre-extraction function.
- `src/dazzlecmd/importer.py:add_from_local` -- `reserved_commands` is now a required keyword-only parameter (F1 fix). The inline `from dazzlecmd.cli import RESERVED_COMMANDS` is removed; the caller (`_cmd_add` in `cli.py`) passes the set explicitly. `command="dz"` and `manifest_name=".dazzlecmd.json"` are also keyword-only parameters defaulted for dazzlecmd's case; aggregators that override either can pass their own values.
- `src/dazzlecmd/cli.py:_cmd_add` -- updated to pass `reserved_commands=RESERVED_COMMANDS` to `add_from_local`.
- `tests/test_importer.py::test_reserved_name_rejected` -- updated to pass `RESERVED_COMMANDS` explicitly, matching the F1 fix's new required parameter.

### Tests

- 1204 passed, 14 skipped (up from 1179 / 14 in v0.7.47; +25 new). All 20 existing dazzlecmd mode tests pass via the thin wrapper, demonstrating that the parameterization preserves the public contract.

### What's NOT in this commit (scheduled for v0.7.49+)

- Safety primitives: dirty-tree refuse-or-force gate at every `shutil.rmtree` call site (T1-E, the CRITICAL hazard from the senior-engineer audit) and `New-Item -ItemType Junction` PowerShell replacement for `cmd.exe /c mklink` (T1-D, CLAUDE.md rule #4 self-consistency).
- Per-aggregator `aggregator.json` deployment to dazzlecmd / wtf-windows / amdead project roots (T1-M1/M2/M3) -- the fixtures already exist; this is the rollout step.
- `dazzlecmd_lib.mode` test migration (T1-I) from `tests/test_mode.py` to `packages/dazzlecmd-lib/tests/test_mode_*.py`.
- Human test checklist (T1-J) covering the parameterization across the three layouts -- ships with v0.7.49 once T1-D/T1-E land alongside it.

### Refs

- Refs #37 (Phase 3.5 EPIC -- mode-system expansion for non-submodule tool sources). v0.7.47 + v0.7.48 jointly land the aggregator-decoupling half of the EPIC; the safety-primitive half (T1-D + T1-E) lands in v0.7.49.

### Design

- `2026-05-17__22-38-36__dev-workflow-process__phase-3-5-mode-system-hardening-shipped-vs-missing.md` -- live DWP with 6 addendums; the Option B decision (extract + parameterize during Tier 1, no duplication) drove the v0.7.47/v0.7.48 split.
- `2026-05-07__00-07-55__claude-plan__0-7-x-closeout-ultraplan-with-x28-copy-dont-rewrite-addendum.md` -- the X-28 copy-don't-rewrite discipline applied (verbatim cp in v0.7.47, parameterize in v0.7.48).

### Versions

- dazzlecmd `0.7.47` -> `0.7.48` (PATCH -- internal refactor; the thin wrapper preserves the public `dazzlecmd.mode` API for all existing callers).
- dazzlecmd-lib `0.6.9` -> `0.6.10` (PATCH -- additive parameterization; the library's mode module is now aggregator-agnostic).
- dazzle-dz alias bumped to `0.7.48`; deps re-pinned to `>=0.7.48` / `>=0.6.10`.

## [0.7.47] - 2026-05-18

Phase 3.5 Tier 1 commit 1 of N (refs #37). Aggregator-decoupling scaffolding for the mode-system extraction. Three additions to dazzlecmd-lib that ship together: `aggregator.json` declarative configuration; `dazzlecmd_lib.reserved` module with the namespace contract; `AggregatorEngine.from_project()` classmethod as the new canonical constructor. Link helpers (`create_link`/`remove_link`) moved from `dazzlecmd.importer` to `dazzlecmd_lib.paths` so any aggregator can use them. `dazzlecmd_lib.mode` module added as a verbatim copy of `src/dazzlecmd/mode.py` (the working version); parameterization for senior-engineer audit BLOCKERs F1-F8 lands in Tier 1 commit 2 (v0.7.48+).

### Added

- `dazzlecmd_lib.aggregator_config` module -- declarative aggregator schema. `AggregatorConfig` dataclass + `load_aggregator_config(project_root)` + `AggregatorConfigError`. 11 top-level fields covering identity (name, command, description), layout (tools_dir, kits_dir, manifest_name), command policy (enabled_meta_commands, extra_reserved_commands), manifest schema decoupling (schema.remote_url_paths, schema.lifecycle_path), and discovery patterns (discovery.tool_patterns with `${tools_dir}` interpolation, discovery.scan_hidden). Required at every aggregator project root for the new `AggregatorEngine.from_project()` constructor; the library refuses to instantiate without it (no backward compat -- we are the only consumer right now and would rather break things now and do it right).
- `dazzlecmd_lib.reserved` module -- the namespace contract. `DEFAULT_RESERVED_COMMANDS` (9 names: list/info/kit/new/add/mode/tree/setup/version) blocks tool names from colliding with meta-command semantics across all aggregators. `DEFAULT_META_COMMANDS_USER` (6 names: list/info/kit/tree/setup/version) is the "complete-unto-itself" registration set; `DEFAULT_META_COMMANDS_DEV_EXTRAS` (add/mode/new) is the opt-in dev-mode addition. Aggregators choose their registration set via `enabled_meta_commands` in aggregator.json -- amdead opts into the user set only (it ships as a focused diagnostic suite, no third-party imports); dazzlecmd opts into both (it is a developer toolchain); wtf-windows opts into user + mode (submodule lifecycle for its core tools).
- `AggregatorEngine.from_project(project_root, **overrides)` classmethod -- canonical engine constructor. Reads `aggregator.json` via `load_aggregator_config`, maps its fields onto the constructor kwargs, then applies any caller-supplied overrides. The kwargs `__init__` remains for tests and ad-hoc construction; `from_project` is intended for production code in every aggregator's `cli.py` main.
- `dazzlecmd_lib.mode` module -- verbatim copy of `src/dazzlecmd/mode.py` (730 LOC). Single change from the source: `from dazzlecmd.importer import (create_link, get_link_target, is_linked_project, remove_link)` becomes `from dazzlecmd_lib.paths import (create_link, get_link_target, is_linked_project, remove_link)`. Tier 1 commit 2 parameterizes the verbatim-moved code for BLOCKERs F1-F8 (thread tools_dir, command, schema through every code path that currently hardcodes "projects/", "dz", and `.dazzlecmd.json`-schema-specific keys).
- `dazzlecmd_lib.paths` link helpers -- `create_link()`, `_create_link_windows()`, `_create_link_unix()`, `remove_link()`. Moved verbatim from `src/dazzlecmd/importer.py` so the library's `dazzlecmd_lib.mode` (and any future consumer) can use them without depending on the dazzlecmd package layout. `is_linked_project` and `get_link_target` were already in `dazzlecmd_lib.paths` since v0.7.33; this commit completes the link-primitive set.
- `packages/dazzlecmd-lib/tests/fixtures/aggregator-json/` -- canonical aggregator.json drafts for dazzlecmd, wtf-windows, amdead. Used by the new test suite as real-world fixtures and double as the production drafts that will deploy to each aggregator's project root in Tier 1 commit T1-M1/M2/M3.

### Changed

- `src/dazzlecmd/importer.py` -- thinned. The `create_link`/`remove_link` function bodies plus their Windows/Unix helpers moved to `dazzlecmd_lib.paths`; importer.py now re-exports them for backward compatibility with any external caller that already imports from `dazzlecmd.importer`. The `add_from_local` function still imports `RESERVED_COMMANDS` from `dazzlecmd.cli` (F1 BLOCKER); that lands in Tier 1 commit 2 as the `reserved_commands` parameter.

### Tests

- 14 new tests in `packages/dazzlecmd-lib/tests/test_aggregator_config.py`. `TestRealWorldDrafts` parses all 3 production drafts and verifies the field values (tools_dir / command / enabled_meta_commands / extra_reserved_commands resolution); `TestFieldValidation` covers missing required keys, wrong types, unknown meta-command names, invalid JSON, mismatched schema versions; `TestDiscoveryPatternInterpolation` proves `${tools_dir}` substitutes correctly; `TestSchemaDecoupling` validates the custom-manifest-layout path that fixes F7.
- Total: 1179 passed, 14 skipped (was 1165 / 14 in v0.7.46; +14 new).

### What's NOT in this commit (scheduled for v0.7.48+)

- Parameterization of `dazzlecmd_lib.mode` for BLOCKERs F1-F8: thread `tools_dir`, `command`, `schema` through `parse_gitmodules`, `cmd_status`, `_find_undiscovered_tool`, `_tool_dir_to_submodule_path`, `_resolve_remote_url`. The moved code currently still hardcodes `"projects/"` and `"dz"` everywhere -- the move and the parameterization are separate passes per the X-28 copy-don't-rewrite discipline.
- Safety primitives: dirty-tree refuse-or-force gate at every `shutil.rmtree` call site (T1-E, the CRITICAL hazard from the senior-engineer audit) and `New-Item -ItemType Junction` PowerShell replacement for `cmd.exe /c mklink` (T1-D, CLAUDE.md rule #4 self-consistency).
- `src/dazzlecmd/mode.py` thin-wrapper conversion (T1-H) -- delete the ~650 LOC of business logic, replace with re-exports from `dazzlecmd_lib.mode`.
- Migration of `src/dazzlecmd/importer.py:add_from_local`'s `RESERVED_COMMANDS` import (T1-Z, F1 BLOCKER fix) -- add `reserved_commands: set` parameter; caller (dazzlecmd's `_cmd_add`) supplies its set.
- Per-aggregator `aggregator.json` deployment to dazzlecmd / wtf-windows / amdead project roots (T1-M1/M2/M3) -- the fixtures already exist; this is the rollout step.
- `dazzlecmd_lib.mode` test migration (T1-I) from `tests/test_mode.py` to `packages/dazzlecmd-lib/tests/test_mode_*.py`.

### Refs

- Refs #37 (Phase 3.5 EPIC -- mode-system expansion for non-submodule tool sources). The body of #37 was updated 2026-05-17 with the revised Tier 1/2/3 split this commit advances.

### Design

- `2026-05-17__22-38-36__dev-workflow-process__phase-3-5-mode-system-hardening-shipped-vs-missing.md` -- the live DWP with 6 addendums covering the survey findings (oracle + senior-engineer + DazzleNodes prior art), the no-backward-compat decision, the aggregator.json schema, and the no-duplication mandate that drove Option B (library extraction during Tier 1).
- `2026-05-07__00-07-55__claude-plan__0-7-x-closeout-ultraplan-with-x28-copy-dont-rewrite-addendum.md` -- the master 0.7.x closeout plan (X-28 copy-don't-rewrite discipline applies).

## [0.7.46] - 2026-05-17

Tier 2C (4b-T4 + 4b-T5 + Setup API formalization + first real-world validator). Closes the engine half of #33's "tools should be runnable on a fresh machine after `dz setup`" arc AND ships the first cross-platform `setup.script` consumer (`dz find`) so the API is proven end-to-end on real hardware. Four reinforcing changes compose into a real install surface (not just a documentation hint), plus the scaffolding templates and a developer guide that codify the conventions.

The four changes are independent design moves that compose: (1) `setup.script` lets a manifest point at a file in the tool directory instead of inlining a shell one-liner -- the engine infers the interpreter from the extension and dispatches; (2) `runtime.venv` shorthand synthesizes the python interpreter path from a venv directory + platform conventions, so the manifest only needs to declare the venv; (3) `SetupRequiredError` translates "interpreter not found" into an actionable `Run: dz setup <fqcn>` hint at the dispatch layer when the tool declares a setup block, or "ask the tool's creator" otherwise; (4) `PlatformInfo.id_like` exposes the Linux ID_LIKE chain so tool setup scripts can write `"debian" in pi.id_like` and have it match Debian itself plus every debian-derived distro (Ubuntu, Mint, Kali, ...) without enumeration. The Python `--full` template now uses (1)+(2)+(3) to produce a tool that, on first dispatch, says `Run: dz setup ...`, and on setup runs an installer-detection script that picks the right Python install path (uv, poetry, pdm, pipenv, conda, pip+pyproject, pip+requirements) for whatever the user has on disk. The `dz find` tool now uses all four to install `fd` on any supported platform via the right package manager (`winget`/`scoop`/`choco` on Windows; `brew` on macOS; `apt-get`/`dnf`/`pacman`/`apk`/`zypper` on Linux by `id_like`; `pkg` / `pkg_add` with `doas` on BSD).

### Added

- **`setup.script` schema field** in `dazzlecmd_lib/setup_resolve.py`. Sibling of `setup.command`; XOR-validated at top-level AND per-platform branches via the new `InvalidSetupBlockError`. Supported extensions map to interpreters via `SETUP_SCRIPT_INTERPRETERS`: `.py` -> `python`, `.sh` -> `bash`, `.cmd`/`.bat` -> `cmd /c`, `.ps1` -> `powershell -File`. Helper `infer_setup_script_interpreter(path)` returns the argv prefix (case-insensitive on the extension) or `None` for unknown extensions. The engine's `_cmd_setup` dispatches scripts with `shell=False` (a real argv) and rejects absolute paths so setup scripts always live in the tool directory. CLI's `_cmd_setup` catches `InvalidSetupBlockError` and surfaces it as a clean `Error:` line on stderr (not a Python traceback).
- **`PlatformInfo.id_like`** in `dazzlecmd_lib/platform_detect.py`. New tuple field that exposes the Linux `/etc/os-release` `ID_LIKE` chain (e.g. `("ubuntu", "debian")` for Ubuntu, `("centos", "rhel", "fedora")` for CentOS Stream). The tuple always includes the subtype itself first so `"debian" in pi.id_like` matches Debian directly AND every debian-derived distro without enumeration. Empty tuple on non-Linux or when `ID_LIKE` isn't declared. Lets cross-platform installer scripts write distro-family decisions instead of long alternation chains. Detection works via the optional `distro` package (uses `distro.like()`) OR the stdlib `/etc/os-release` parser fallback.
- **`runtime.venv` shorthand (4b-T4)** in `dazzlecmd_lib/registry.py`. When `runtime.venv` is declared but `runtime.interpreter` is not, the python runner synthesizes the interpreter as `<venv>/Scripts/python.exe` on Windows or `<venv>/bin/python` on POSIX. Explicit `runtime.interpreter` still wins on collision; venv is shorthand for the no-interpreter case. The synthesized path threads through the existing `_resolve_interpreter` helper so relative venv paths resolve against the tool directory (matching how `runtime.interpreter` already works). Path-resolution shorthand only: the engine never creates the venv -- `dz setup` is the only venv-creation surface.
- **`SetupRequiredError` (4b-T5)** in `dazzlecmd_lib/registry.py`. Raised at python dispatch when the resolved interpreter path doesn't exist (pre-flight check before subprocess), or when subprocess.run raises `FileNotFoundError` on a bare-name interpreter that's not on PATH. Carries the tool's `_fqcn` and a `has_setup` flag so the dispatch layer can pick the right hint: `Run: dz setup <fqcn>` when the tool declares a setup block, or `Ask the tool's creator to add one` when it doesn't. `_setup_required_message(project, missing_what)` is the shared message builder. The `dispatch_tool` handler in `src/dazzlecmd/cli.py` catches the exception type explicitly so the user sees the hint without a Python traceback.
- **Template setup blocks** for rust, node, c_cpp, and docker (`packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/<lang>/.dazzlecmd.json.tmpl`). Rust: `setup.command: "cargo build"` plus `runtime.dev_command: "cargo run --"` for the binary-not-yet-built case. Node: `setup.command: "npm install"`. C/C++: `setup.command: "make"` plus `dev_command: "make run"`. Docker: `setup.command: "docker build -t {name}:latest ."`. Rust and c_cpp also migrated from the old `binary_path`/`build_hint` shape to the canonical `runtime.script_path` + `dev_command` shape the binary runner consumes (the old shape was set-and-never-read).
- **`dz find` cross-platform installer** at `projects/core/find/dz_setup.py` -- the first real-world `setup.script` consumer. Uses `dazzlecmd_lib.platform_detect.get_platform_info()` to dispatch the right `fd` installer per host: `winget`/`scoop`/`choco` (Windows precedence order); `brew` (macOS); `apt-get`/`dnf`/`pacman`/`apk`/`zypper` (Linux, dispatched by `pi.id_like` so Ubuntu/Mint/Kali all route through `apt-get`); `pkg install` (FreeBSD) and `pkg_add` with `doas` (OpenBSD). Honors `--dry-run` (preview commands without executing) and `--force` (reinstall when fd is already on PATH). Idempotent: short-circuits with the existing fd path when `fd` or `fdfind` is already installed. Sudo handling: detects non-root POSIX and prepends `sudo` (or `doas` for OpenBSD) before privileged commands. Post-install verification re-checks `shutil.which("fd")` and `shutil.which("fdfind")` -- the installer's exit code alone isn't trusted. Verified end-to-end via `dz setup core:find` on Windows (winget); all other platforms covered by 26 unit tests with mocked `shutil.which` + synthetic `PlatformInfo`.
- **`docs/guides/setup-scripts.md`** -- developer guide codifying setup-script conventions: when to pick `setup.command` vs `setup.script`; the eight conventions tools SHOULD follow (`--dry-run`, idempotency, command-echo, post-install verification, `platform_detect` usage, sudo prepending, loud failure messages, tool-dir-only writes); three worked examples (one-liner, Python venv+requirements, cross-platform installer); explicit non-goals (`dz setup --all`, automatic dispatch, installer picking, state tracking) that codify the dispatcher-not-package-manager promise. The conventions are policy, not engine-enforced.
- **`--dry-run` convention** in the `python/__full__/dz_setup.py.tmpl` scaffold. The rendered `dz_setup.py` now ships with `argparse` + a module-level `DRY_RUN` flag consulted by `_run()`. New `--full` Python tools encourage the `--dry-run` convention by default; the engine does not enforce it (per the dispatcher-not-package-manager invariant -- enforcement is via policy, in `docs/guides/setup-scripts.md`).
- **Python `--full` template overhaul** (Phase 7, "gold standard" install path). `packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/python/__full__/` now contains three new files in addition to the existing README and tests:
  - **`.dazzlecmd.json.tmpl`** -- overrides the base manifest with `runtime.venv: ".venv"` and `setup.script: "dz_setup.py"`. The `--full` overlay layer copy-overwrites the base manifest so a `--full` Python tool ships venv-using out of the box.
  - **`dz_setup.py.tmpl`** -- self-contained Python script (no third-party deps) that detects the project's Python installer from on-disk markers (precedence: `uv.lock` / `[tool.uv]` -> `poetry.lock` / `[tool.poetry]` -> `pdm.lock` / `[tool.pdm]` -> `Pipfile` -> `environment.yml` -> `pyproject.toml` -> `requirements.txt` -> empty venv) and dispatches the appropriate install flow into `.venv/`. Each installer flow targets the same `.venv/` directory so `runtime.venv: ".venv"` works regardless of which installer the user prefers. The script forces in-project venvs for poetry / pdm / pipenv via their respective config flags / env vars.
  - **`requirements.txt.tmpl`** -- starter file with explanatory comments. Default content is empty; the pip-install step is a no-op when there are no dependencies declared, but the structure is in place.

### Changed

- **`_cmd_setup` in `src/dazzlecmd/cli.py`** now reads `effective.get("script")` in addition to `effective.get("command")`. Script paths are rejected if absolute (must live in the tool directory), then verified to exist on disk and dispatched as `[<interpreter>, <full_script>, ...]` with `shell=False`. Command-string dispatch is unchanged (`shell=True`). The "Setup" display lines distinguish `Script:` + `Invocation:` (file pointer) from `Command:` (one-liner) so authors see exactly what will run.
- **Python runner FileNotFoundError handling**. `_make_python_interpreter_runner` previously let `FileNotFoundError` from subprocess propagate as a generic "Error running ...: ..." message. The runner now adds a pre-flight existence check for separator-bearing paths (relative or absolute, excluding `$VAR` / `%VAR%` env-var paths the shell expands later) AND catches `FileNotFoundError` from subprocess.run for bare-name interpreters. Both paths surface as `SetupRequiredError` with the appropriate hint.
- **Rust + c_cpp manifest templates** moved from `binary_path` (unread by the binary runner) to `script_path` (canonical field). Rust adds `dev_command: "cargo run --"` so `DAZZLECMD_FORCE_DEV=1` -- or a missing binary -- falls back to `cargo run`. C/C++ adds `dev_command: "make run"`.

### Removed

- **`runtime.build_hint`** field from the rust and c_cpp templates. The information now lives in `setup.note`. The hint field was advisory text that the engine never consumed; the setup block is the structured location for the same information.

### Tests

1165 passed, 14 skipped (up from 1104 / 14 in v0.7.45; +61 new):

- 9 in `tests/test_setup_resolve.py` covering `setup.script` parsing, XOR validation (top-level and per-platform branch), per-platform script dispatch, the `command-at-top + script-at-platform` no-collision case, and the new `infer_setup_script_interpreter` helper (4 extensions plus case-insensitivity and unknown-extension behavior).
- 7 in `tests/test_registry.py` covering `runtime.venv` shorthand (Windows synthesizes `Scripts/python.exe`, POSIX synthesizes `bin/python`, explicit interpreter wins over venv) and `SetupRequiredError` (missing relative interpreter with setup -> `dz setup` hint; missing without setup -> "ask creator" hint; bare-name interpreter triggers `FileNotFoundError` catch path; missing venv directory raises with the setup hint).
- 3 in `tests/test_cmd_new_tool_languages.py::TestLanguagePython` verifying the `--full` overlay scaffolds `dz_setup.py` + `requirements.txt`, that the overlay manifest uses `runtime.venv` + `setup.script`, and that the rendered `dz_setup.py` correctly detects `pip-requirements` when only `requirements.txt` is present.
- 2 updated in `tests/test_cmd_new_tool_languages.py` (rust + c_cpp `test_manifest_runtime_is_binary`) to assert the new `script_path` + `setup.command` shape instead of the removed `binary_path` field.
- 3 updated in `tests/test_python_runner_interpreter.py` (`test_interpreter_bypasses_pass_through`, `test_absolute_interpreter_used_as_is`, `test_relative_interpreter_unresolved_passes_through` renamed to `..._raises_setup_required`) to reflect the v0.7.46 contract change: missing interpreter paths now raise `SetupRequiredError` instead of silently passing through to subprocess. `test_env_var_prefix_passes_through` still works because env-var paths skip the pre-flight check.
- 34 new in `tests/test_find_setup.py` covering `dz find`'s two-tier installer-selection logic with synthetic `PlatformInfo` + mocked `shutil.which`: Windows precedence (winget > scoop > choco); macOS brew; Linux Tier 1 dispatch via `pi.id_like` (Debian/Ubuntu/Mint -> apt-get, Fedora/CentOS-Stream -> dnf, Arch/Manjaro -> pacman, Alpine -> apk, openSUSE -> zypper, Gentoo -> emerge, Solus -> eopkg); FreeBSD pkg with sudo when not root; OpenBSD pkg_add with doas; Linux Tier 2 binary-detection fallback when `id_like` doesn't match (Void -> xbps-install, NixOS -> nix-env, Solus-derivative -> eopkg, bespoke distros with apt-get); dnf > yum precedence within rhel-family + yum fallback on legacy RHEL/CentOS 7; unsupported distros return None with a manual-install hint; idempotency (`fd` or `fdfind` already on PATH); `--dry-run` doesn't call subprocess.run; already-installed short-circuit takes priority over the dry-run path.
- 2 new in `tests/test_cli_setup.py::TestInvalidSetupBlockCleanError` covering Scenario 5's clean-error path: top-level XOR violation surfaces as `Error: ... declares both 'command' and 'script'` with no Python traceback; per-platform-branch XOR violation includes the `platforms.<os>` context.
- 5 new in `tests/test_platform_detect.py::TestDetectLinuxSubtype` covering `id_like` parsing via the `distro` package (debian, with id_like, with multi id_like) and via the `/etc/os-release` stdlib fallback (with ID_LIKE, without ID_LIKE).

### Human test checklist

`tests/checklists/v0.7.46__Tier2C__setup-api-formalization.md` covers `dz setup` dispatch of both `command` and `script` shapes across `.py` / `.sh` / `.cmd` / `.ps1` (HV section), per-platform script selection, `runtime.venv` synthesis on Windows and POSIX, the `SetupRequiredError` hint flow on first dispatch of a venv-using tool, and the `dz new tool --language python --full` round trip through `dz setup` on a fresh checkout (validates installer-detection covers `pip-requirements` and gracefully reports `pip-pyproject` / `uv` / `poetry` / `pdm` when their markers are present).

### Versions

- dazzlecmd `0.7.45` -> `0.7.46` (PATCH -- additive schema field, additive runtime shorthand, additive exception type. Behavior change for "missing interpreter" tools is acceptable in PATCH because no existing tool relied on `FileNotFoundError` propagation as a feature).
- dazzlecmd-lib `0.6.7` -> `0.6.8` (PATCH -- setup_resolve schema extension, registry venv shorthand, new exception type, template content updates).
- dazzle-dz alias bumped to `0.7.46`; deps re-pinned to `>=0.7.46` / `>=0.6.8`.

### Refs

Refs #33 (first-run setup detection -- engine half closed; CLI-side first-run UX detection deferred to v0.7.47). Refs #35 (`dz new` template polish -- rust/c_cpp manifest shape corrected; setup blocks now part of each language's default scaffold).

### Design

Design doc: `2026-05-16__19-54-45__dev-workflow-process__setup-api-formalization-and-real-world-validation.md` (3-commit arc: v0.7.46 schema + templates + 4b-T4 + 4b-T5; v0.7.47 first-run UX + auto-setup; v0.7.48 real-world validation against dazzle-locate32, comfyui-triton-sageattention-installer, wtf-windows).

## [0.7.45] - 2026-05-16

Adds three more language templates to the v0.7.44 multi-language scaffolding set: `bash`, `cmd`, and `binary`. The engine's shell runner and binary runner already support these via the existing `runtime.shell` / `runtime.binary_path` fields -- this commit is pure template addition, no engine changes.

Resolves two gaps surfaced after v0.7.44 shipped:

1. User feedback that bash/cmd scripts are common scaffolding targets. #35's acceptance criteria listed "shell" as a supported language; v0.7.44 only covered the shell case via PowerShell.
2. The acceptance criteria also explicitly listed "binary" as a supported language; v0.7.44 conflated this with `generic` (which is broader -- the generic README mentions runtime could end up shell, node, docker, etc.). `binary` is now its own template for the narrower "I have a pre-built executable, register a manifest pointing at it" case.

The seven-language set from v0.7.44 (python, rust, node, powershell, c_cpp, docker, generic) is now ten.

### Added

- `templates/bash/` -- `.dazzlecmd.json.tmpl` (`language: "bash"`, `runtime.type: "shell"`, `runtime.shell: "bash"`, `platforms: ["linux", "macos"]`) + `{name}.sh.tmpl` (bash hashbang, `set -euo pipefail`, `$*` argv passthrough).
- `templates/cmd/` -- `.dazzlecmd.json.tmpl` (`language: "cmd"`, `runtime.type: "shell"`, `runtime.shell: "cmd"`, `platforms: ["windows"]`) + `{name}.cmd.tmpl` (`@echo off`, `setlocal`/`endlocal`, `%*` passthrough, `exit /b 0`).
- `templates/binary/` -- `.dazzlecmd.json.tmpl` (`language: "binary"`, `runtime.type: "binary"`, `binary_path: "{name}"`, cross-platform) + `README.md.tmpl` explaining drop-in vs PATH-lookup vs absolute/relative binary_path patterns and when to prefer `binary` over `generic`.

### Changed

- `TestAvailableLanguagesError::test_unknown_language_error_lists_all_seven` renamed to `test_unknown_language_error_lists_all_ten`; the assertion set now includes `bash`, `cmd`, and `binary`.

### Tests

1104 passed, 14 skipped (up from 1096 / 14 in v0.7.44; +8 new):

- 3 in `tests/test_cmd_new_tool_languages.py::TestLanguageBash` (scaffold produces `<name>.sh`; manifest runtime is shell/bash with POSIX platforms; entry has bash hashbang).
- 3 in `TestLanguageCmd` (scaffold produces `<name>.cmd`; manifest runtime is shell/cmd with windows-only platform; entry has `@echo off` and `%*` passthrough).
- 2 in `TestLanguageBinary` (scaffold produces manifest + README only, no source files; manifest runtime is binary with cross-platform metadata and the drop-in binary_path default).

### Versions

- dazzlecmd `0.7.44` -> `0.7.45` (PATCH -- additive language templates).
- dazzlecmd-lib `0.6.6` -> `0.6.7` (PATCH -- template content bundled with the lib package).
- dazzle-dz alias bumped to `0.7.45`; deps re-pinned to `>=0.7.45` / `>=0.6.7`.

### Refs

Refs #35 (`dz new` redesign -- shell-language and binary-language gaps surfaced post-v0.7.44 and addressed here).

## [0.7.44] - 2026-05-16

Tier 2A.2 (4b-T3 + 4d-3) — multi-language scaffolding templates and `--language` dispatch. Replaces v0.7.40's python-only `_SUPPORTED_LANGUAGES_V0740` guard with a real per-language scaffolder. Seven languages ship: `python` (full depth — manifest + entry + `--full` overlay with README and pytest stub), `rust` (manifest + `Cargo.toml` + `src/main.rs`), `node` (manifest + `package.json` + `index.js`), `powershell` (manifest + `<name>.ps1` with `param` block), `c_cpp` (manifest + `Makefile` + `main.c`), `docker` (manifest + `Dockerfile`), and `generic` (manifest + README explaining the runtime block — for tools that already exist as a binary or script). Resolves v0.7.40's coming-soon promise and closes the scaffolding side of #35.

The CLI rewrite is small (~80 LOC). `_cmd_new_tool` now derives the template directory from `--language`, recursively copies the tree with placeholder substitution applied to BOTH file contents AND filenames (so `python/{name_underscore}.py.tmpl` -> `my_tool.py`), and applies the `__full__/` overlay for Python `--full`. The validation set is derived from the directory layout under `packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/`, so adding a future language is purely additive (drop in a new directory).

### Added

- **Per-language template directories** under `packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/`: `python/`, `rust/`, `node/`, `powershell/`, `c_cpp/`, `docker/`, `generic/`. Each contains a per-language `.dazzlecmd.json.tmpl` (with the correct `runtime.type` for that language) plus the entry-point source files appropriate to the language.
- **`python/__full__/` overlay** containing `README.md.tmpl` and `tests/test_{name_underscore}.py.tmpl`. Applied when `dz new tool --language python --full <name>` so Python-tier users get a fully-fledged starter (universal `_layer_extras` items still apply: TODO.md, NOTES.md, ROADMAP.md, private/claude/).
- **Filename placeholder substitution.** Template filenames may contain `{name}` / `{name_underscore}` markers; on copy, those are replaced with the user-supplied tool name before writing to disk. Required for Python (`{name_underscore}.py`), PowerShell (`{name}.ps1`), and Python `--full` tests (`tests/test_{name_underscore}.py`).
- **`_find_templates_root`, `_available_languages`, `_substitute_placeholders`, `_copy_template_tree` helpers** in `src/dazzlecmd/cli.py`. The copy helper handles recursive directory walks, `.tmpl` suffix stripping, overlay-dir skipping (`__*__`), and both file and filename substitution.

### Changed

- **`_cmd_new_tool` rewrite.** Replaced inline manifest construction + ad-hoc script copy with the template-tree dispatch. The function now picks a language, validates its template dir exists, then delegates the entire scaffold to `_copy_template_tree`. ~80 LOC down from ~120; clearer separation of concerns.
- **Validation: language must have a template dir.** Replaces v0.7.40's hardcoded `_SUPPORTED_LANGUAGES_V0740 = {"python"}` set. Error message lists all available languages so users can see what's valid. The validation runs against config-derived AND CLI-derived language values.
- **Package data layout (`packages/dazzlecmd-lib/pyproject.toml`).** `package-data` now uses recursive globs (`templates/*`, `templates/**/*`, `templates/**/**/*`) so subdirectory template files ship in the wheel.

### Removed

- **`_SUPPORTED_LANGUAGES_V0740` guard** in `src/dazzlecmd/cli.py`. The v0.7.40 coming-soon message that pointed at v0.7.44 is gone — v0.7.44 IS that release.
- **`_default_python_template` fallback** in `src/dazzlecmd/cli.py`. Templates are bundled with the lib package; if they're missing the install is broken (not a recoverable case). Cleaner than maintaining a parallel inline copy.
- **Old flat templates** `dazzlecmd.json.tmpl` and `python_tool.py.tmpl` (under `templates/` root). Replaced by `templates/python/.dazzlecmd.json.tmpl` and `templates/python/{name_underscore}.py.tmpl`.

### Tests

1096 passed, 14 skipped (up from 1068 / 14 in v0.7.41 + the v0.7.42/v0.7.43 commits; +28 new):

- 20 in `tests/test_cmd_new_tool_languages.py` covering all seven languages: scaffolded file structure, manifest schema correctness, `runtime.type` matches language conventions, hyphenated-name placeholder substitution, Python `--full` overlay produces README + tests/, generic ships no source file, unknown language error lists all seven, kit registration works for non-Python tools, description placeholder appears in non-manifest files (Cargo.toml).
- 2 replaced in `tests/test_cmd_new_tool.py`: v0.7.40's `_config_language_unsupported_rejected` / `_cli_language_unsupported_rejected` (asserted the python-only guard) repurposed to assert that truly unknown language names (`klingon`, `brainfuck`) are rejected. The 26 other v0.7.40 tests continue to pass unchanged.

### Human test checklist

`tests/checklists/v0.7.44__Tier2A__multi-language-templates.md` covers per-language scaffold round-trips, manifest schema verification, `dz info` output for each language, Python `--full` overlay verification, the placeholder-substitution-in-filenames mechanic, and a regression check that v0.7.40's `dz new tool <name>` (defaults to Python) still works end-to-end.

### Versions

- dazzlecmd `0.7.43` -> `0.7.44` (PATCH — additive scaffolding surface, no breaking CLI change; the v0.7.40 python-only guard is gone but the behavior `dz new tool foo` produces is unchanged).
- dazzlecmd-lib `0.6.5` -> `0.6.6` (PATCH — templates content bundled with the lib package).
- dazzle-dz alias bumped to `0.7.44`; deps re-pinned to `>=0.7.44` / `>=0.6.6`.

### Refs

Refs #35 (`dz new` redesign — the kit/aggregator sub-parsers are still stubs; planned for v0.7.45+).
Refs #30 (Phase 4 epic — Tier 2 continues).

### Design

- `2026-05-15__21-29-29__dev-workflow-process__4b-T3-multi-language-templates.md`

## [0.7.43] - 2026-05-16

### Fixed

- **Shadowed tool names now dispatch to the tool, not the meta-command** (`dazzlecmd-lib`). When a tool's short name matches a reserved meta-command name (e.g. AMDead's `setup` PowerShell tool vs the library's `setup` meta-command), the tool wins and receives the full argv after the command name unchanged. Previously the meta-command's argparse rejected any flag it didn't recognize, blocking tool invocation with anything other than the FQCN form (`amdead core:setup -Install`). The FQCN workaround still works; it just isn't required anymore. Closes #67.

### Added

- **`docs/guides/help-conventions.md`** — guidance for tool authors on handling `-h` in PowerShell, bash, cmd, and binary tools. The library does not intercept help flags for non-Python runtimes; tools receive argv exactly as the user typed it.

## [0.7.42] - 2026-05-14

Internal tooling refresh — replaces project-local `scripts/` with the shared `git-repokit-common@v0.2.4` toolbox consumed as a git subtree at `scripts/`. No user-visible CLI or library behavior changes. Hook checks (pre-commit version sync + private-content guard + 10MB file blocker; post-commit hash refresh; pre-push syntax/test/debug scan) all continue to run with the same semantics. What's new is the toolbox underneath: a richer version manager (`sync-versions.py` supersedes the legacy `update-version.sh` and adds `--check`, `--dry-run`, `--bump`, `--demote`, `--set X.Y.Z`, `--phase {alpha,beta,rc1}`, and automatic CHANGELOG compare-link maintenance), GitHub issue tooling (`gh_issue_full.py`, `gh_sub_issues.py` — the issue-context viewer that was previously referenced from a sibling project now ships in-repo), Claude session tools (`search_sesslog.py`, `extract_tool_result.py`), demo recording scaffolding (`demo/`), `paths.sh`/`safe_move.sh` utilities, a tag-only push fast path in `pre-push`, and bidirectional sync with the upstream toolbox via `bash scripts/update-common.sh`. Project configuration lives in a new `[tool.repokit-common]` block in `pyproject.toml`.

### Added

- **`scripts/` is now a git subtree of `git-repokit-common@v0.2.4`** (`https://github.com/DazzleTools/git-repokit-common`). Pull updates with `bash scripts/update-common.sh`; check status with `bash scripts/update-common.sh --check`; push local improvements upstream with `bash scripts/update-common.sh --push`.
- **`[tool.repokit-common]` block in `pyproject.toml`** wiring `version-source = "src/dazzlecmd/_version.py"`, `changelog = "CHANGELOG.md"`, `repo-url`, `tag-prefix = "v"`, `tag-format = "pep440"`, and `private-patterns` (the file/dir patterns blocked by the pre-commit private-content guard).
- **CHANGELOG compare-links scaffolding** (`[Unreleased]` + `[0.7.39]` reference links at the bottom of this file) so `python scripts/sync-versions.py --check` validates cleanly and auto-maintains the link block on future bumps.

### Changed

- **Version bump workflow** — the canonical command for version edits is now `python scripts/sync-versions.py --bump {major,minor,patch}` (or `--set X.Y.Z`, `--phase alpha`, etc.). The legacy `scripts/update-version.sh` is still present in the subtree but deprecated upstream. Pre-commit hook auto-runs `sync-versions.py --auto`.
- **Pre-push hook** — gains the tag-only push fast path from `git-repokit-common@v0.2.3`: `git push --tags` no longer runs the full pytest sweep.

### Refs

- Closes #24 (Replace legacy scripts/ with git-repokit-common subtree). Two deliberate divergences from the issue's draft acceptance criteria: chose `tag-format = "pep440"` (matches existing dazzlecmd tag style: v0.7.39 through v0.7.42 are all PEP 440 compatible) rather than `"human"`; expanded `private-patterns` to match the existing pre-commit private-content regex (`private/`, `convos/`, `logs/`, `test-runs/`, `test_runs/`, `.env`, `credentials/`, `secrets/`, `revisions/`) rather than the minimal `["private/", ".env"]` the issue suggested. Both divergences preserve dazzlecmd's pre-existing conventions.
- Refs #27 (dazzlecmd-lib extraction prep — shared tooling smoothes the multi-project workflow)
- Refs #30 (Phase 4 EPIC — tooling alignment supports library extraction work)
## [0.7.41] - 2026-05-14

Closes #65 (duplicate-FQCN display when discovery loops back via filesystem). Implements Solution B from the dev-workflow analysis: realpath-based auto-aliasing at discovery time. When two or more FQCNs reach the same on-disk script (junction loop, symlink, or two aggregators that cross-embed each other with shared physical files), only the shortest FQCN registers as canonical; the others register as aliases with `source="auto-realpath"`. Dispatch via any FQCN still works (alias mechanism forwards to canonical). Display surfaces collapse to one row per physical script automatically.

This is the recursion-architecture follow-up to v0.7.38's `discover_kits` aggregator-as-kit fix (#63). Together they make "any aggregator can attach to any other" a coherent claim: physical identity is detected, dispatch is correct, display is duplicate-free.

Note on wtf-windows visible duplicates: the v0.7.38 + v0.7.41 fixes do not collapse duplicates that arise from two *distinct* physical copies of the same tool (e.g., dazzlecmd's `projects/wtf` submodule at one commit + standalone wtf-windows at another). Those are real separate files with different SHAs — a separate "two installs of the same logical tool" problem, not realpath equality.

### Added

- **`AggregatorEngine._realpath_index`** — per-engine `{realpath: canonical_fqcn}` map populated during `_build_fqcn_index`. Records the canonical FQCN chosen for each physical script.
- **`FQCNIndex._alias_sources`** — side-table mapping each alias FQCN to its source ("auto-realpath" for realpath dedup, virtual-kit manifest path for declared virtual aliases). Used by `render_info` to surface alias provenance accurately.
- **`render_info` auto-realpath provenance banner** (lib) — when the user dispatches via an auto-realpath alias FQCN, `dz info` shows `(auto-realpath alias '...' -> canonical '...'; same physical script reached via two discovery paths)` instead of the virtual-kit alias banner.

### Changed

- **`_build_fqcn_index` (engine)** — now groups projects by `realpath(_dir)` before insertion. Within each group: shortest FQCN (by segment count, then alphabetical) wins canonical; the rest register as auto-realpath aliases via `insert_alias(..., source="auto-realpath")`. Demoted projects are marked with `_auto_realpath_alias=True` and `_canonical_fqcn=<winner>`.
- **`engine.projects` filtering** — auto-realpath aliases are filtered out after `_build_fqcn_index`. Custom list handlers iterating `engine.projects` directly (wtf's `_wtf_list_handler`, amdead's similar) see one project per physical script automatically. `engine.all_projects` retains everything for consumers that need the full set.
- **`_apply_virtual_kits` (engine)** — when a virtual-kit alias's declared target was demoted to an auto-realpath alias, the new alias points directly at the actual canonical instead of failing with KeyError. Preserves the single-hop alias invariant.
- **`build_list_entries` (lib)** — skips projects marked `_auto_realpath_alias` from canonical iteration; skips auto-realpath alias entries from the alias iteration (they don't get their own row). The `[+]` marker on the canonical signals their existence; `dz info` is the inspection path.
- **`render_list` (lib)** — `[+]` footer message extended to acknowledge auto-realpath aliases alongside virtual-kit overlays.

### Fixed

- **Duplicate rows in `dz list`/`wtf list`/aggregator-custom list handlers** when the discovery path reaches the same physical script via two FQCNs. Pre-v0.7.41 the second FQCN registered as a separate canonical; now it registers as an alias and the row collapses.
- **"missing canonical" warnings from virtual-kit application** when the virtual kit targets a canonical that was demoted to an auto-realpath alias. The alias-following logic in `_apply_virtual_kits` now resolves these correctly.

### Tests

1068 passed, 14 skipped (up from 1059 / 13 in v0.7.40; +9 new):

- 9 in `tests/test_engine_recursive.py::TestRealpathDedup` covering same-realpath aliases the longer FQCN, distinct dirs stay distinct canonicals, three-way collision picks shortest, alphabetical tiebreak, `_realpath_index` populated, dispatch via alias resolves to canonical, demoted project marker, `build_list_entries` omits auto-realpath aliases, virtual-kit alias follows demoted target.
- 1 POSIX-only integration test (`test_symlink_loop_real_discovery`) skipped on Windows.

### Human test checklist

`tests/checklists/v0.7.41__Bugfix__realpath-dedup.md` covers synthetic junction setup, dispatch correctness across both FQCNs, `dz info` banner content, and the wtf-windows live verification confirming no regression for the separate two-physical-copies case.

### Versions

- dazzlecmd `0.7.40` -> `0.7.41` (PATCH — bug-fix; closes #65).
- dazzlecmd-lib `0.6.3` -> `0.6.4` (PATCH — engine + display layer touch).
- dazzle-dz alias bumped to `0.7.41`; deps re-pinned to `>=0.7.41` / `>=0.6.4`.

### Refs

Closes #65 (duplicate-FQCN display when discovery loops back).
Refs #30 (Phase 4 epic — recursion architecture).
Refs #50 (Phase 4e retro — cross-aggregator dispatch correctness).

### Design

- `2026-05-13__00-33-46__dev-workflow-process__duplicate-fqcn-display-when-recursion-loops-back.md`

## [0.7.40] - 2026-05-13

Tier 2A.1 (4d-1) — first commit of the Phase 4b/4d scaffolding redesign. The flat `dz new <name>` command is replaced with a sub-parser surface `dz new <type> <name>` covering three entity types: `tool` (fully implemented this commit), `kit` and `aggregator` (stubs printing planned-shape messages; full impls land in v0.7.42 / 4d-2). The redesign follows the synthesis design in `2026-05-13__16-27-57__dev-workflow-process__tier2-scaffolding-synthesis.md` (Open Question A2: separate `kit` and `aggregator` rather than collapsed under `--standalone` flag).

`_cmd_new_tool` (renamed from `_cmd_new`) now reads the user-config `new` section (a new config schema area) for defaults: `default_namespace` and `default_language` apply when the corresponding CLI flag is omitted. Precedence is CLI flag > config > built-in (`dazzletools` / `python`). The generated `.dazzlecmd.json` manifest now includes the `long_description` field (closes #61) — empty by default; populated from a new `--long-description` CLI flag. The library's `render_info` is extended to render the `long_description` content as a `Details:` mini-manpage block below the standard field rows so the feature is end-to-end usable: scaffolding writes the field, `dz info` displays it.

### Breaking

- **`dz new <name>` no longer works.** Replace with `dz new tool <name>`. The argparse error message lists the three sub-types. Migration is a one-token addition (`tool`); no flag changes for tool creation.
- Bare `dz new` (no type) now prints a usage hint to stderr and exits 2. Previously it was an argparse error.
- **`--language` accepts only `python` in v0.7.40.** Other values (`rust`, `node`, `powershell`, `c_cpp`, `docker`, `generic`) are rejected with exit code 2 and a coming-soon message pointing at v0.7.44 (4d-3). This prevents users from creating internally-inconsistent manifests (`language: "rust"` with a Python `.py` script and `runtime.type: "python"`). The guard is removed in v0.7.44 when per-language scaffolding lands. Affects users who set `~/.dazzlecmd/config.json` `new.default_language` to anything other than `python` — they'll need to either change the config or temporarily omit the field until v0.7.44.

### Added

- **`dz new tool <name>`** — fully wired sub-parser. Same flags as the legacy flat `dz new` plus `--long-description <text>` for mini-manpage content. CLI > config > built-in precedence for `--namespace` and `--language`.
- **`dz new kit <name>`** — stub printing the planned shape ("Create a flat kit at projects/<name>/") and pointing users at `dz new tool <name>` / `dz kit add <url>` for today's workflows. Exits 2.
- **`dz new aggregator <name>`** — stub printing the planned shape (standalone aggregator project with `--with common,template,ci` composition) and pointing users at `dz new tool` for today's workflows. Exits 2.
- **User-config `new` section** — new schema area in `~/.dazzlecmd/config.json` read by `_cmd_new_tool`. Initial keys: `default_namespace` (string), `default_language` (string). Extends naturally as Tier 2 progresses with `license`, `author`, `github_org`, `repokit_common_url`, etc. (v0.7.47).
- **`long_description` field in generated manifest** — empty default; populated from `--long-description` CLI flag. Surfaces in `dz info <tool>` via v0.7.37's render_info long-description display.
- **`packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/dazzlecmd.json.tmpl`** — extended with `"long_description": "{long_description}"` placeholder so future template-driven scaffolding stays in sync with the in-CLI inline generation.
- **`render_info` `Details:` block** — library's `render_info` now renders `long_description` content (when non-empty) as a `Details:` section below the standard field rows. BOLD section header (when color enabled); body indented two spaces and wrapped to terminal width using `_wrap_description`. Multi-line `long_description` content preserves paragraph breaks. Closes the rendering side of #61.

### Changed

- **`_cmd_new` → `_cmd_new_tool`** — renamed to disambiguate from the forthcoming `_cmd_new_kit` / `_cmd_new_aggregator` handlers in v0.7.42. Signature gained `engine=None` parameter for config-section access via `engine._get_config_dict("new")`.
- **`dispatch_meta`** in `src/dazzlecmd/cli.py` — `meta == "new"` now prints usage hint instead of calling the legacy handler. Three new dispatch branches: `new_tool`, `new_kit_stub`, `new_aggregator_stub`.
- **`dazzlecmd-lib` version**: `0.6.2` → `0.6.3` (PATCH — additive `render_info` extension).

### Fixed

- **`_register_in_kit` wrote to the wrong file** — pre-fix it wrote `tools` entries to the registry pointer (`kits/<kit>.kit.json`), but the loader's merge order (`loader.py:55-71`) makes the in-repo manifest's `tools` list authoritatively override the registry pointer's when both exist. So `dz new tool foo --kit core` would silently fail to register: the entry landed in the registry pointer but the merge replaced it with the in-repo manifest's untouched list. Now writes to the in-repo manifest (`projects/<kit>/.kit.json`) when present, falling back to the registry pointer only for registry-only kits. Affects `dz new tool --kit X` AND `dz add --kit X`. 4 regression tests in `TestRegisterInKit`.

### Tests

- 1059 passed, 13 skipped (up from 1025 in v0.7.39; +28 new in `tests/test_cmd_new_tool.py`, +6 new in `tests/test_default_meta_commands.py::TestRenderInfoLongDescription`).
- New test classes: `TestNewToolScaffold` (file structure, `long_description` field, existing-project error), `TestNewToolConfigDefaults` (config-namespace default, CLI override, language guard: unsupported config-language rejected, unsupported CLI-language rejected, python-explicit accepted, python-default accepted, malformed-config safety), `TestNewKitStub` and `TestNewAggregatorStub` (exit code 2, planned-shape messages, workaround references), `TestRegisterInKit` (in-repo manifest preferred, registry-pointer fallback, missing-kit warning, duplicate-no-double-write), `TestResolveNewDefaults` (helper-level robustness: None engine, malformed config, exception during read), `TestRenderInfoLongDescription` (header rendering, absent/missing/whitespace cases, terminal-width wrapping, multi-line paragraph preservation).

### Refs

- Refs #35 (`dz new` redesign — this commit lands the sub-parser scaffolding; `kit` / `aggregator` full impls follow in v0.7.42).
- Closes #61 (long_description schema + render_info `Details:` block — end-to-end usable: scaffolding writes the field, `dz info` displays it).
- Refs #30 (Phase 4 epic — Tier 2 begin).

### Design

- `2026-05-13__16-27-57__dev-workflow-process__tier2-scaffolding-synthesis.md` — the synthesis doc that resolved Open Question A (separate `kit` vs `aggregator`) and laid out the 11-commit Tier 2 sequence
- `2026-04-13__06-56-42__dev-workflow-process_new-aggregator-scaffolding-and-repokit-integration.md` (6 addenda) — the foundational design corpus
- `2026-05-12__15-32-50__dev-workflow-process__full-recursion-and-tier2-scaffolding-sequencing.md` — sequencing decisions placing X-6 at the 4d-2/4d-3 seam

## [0.7.39] - 2026-05-12

Bug-fix patch — closes #64. Removes the last user-visible dazzlecmd-isms from the library code path and fixes a `render_kit_list` regression that surfaced when v0.7.38 started honestly populating `kit["tools"]` for aggregator-as-kit. Surfaced by the post-v0.7.38 wtf-windows recursion sweep where every tool in the embedded `dz` kit rendered as `(not found)`.

The fix has two halves. **Half 1 — FQCN-aware kit-list matching:** the kit-tool-to-project lookup in both the library's `render_kit_list` (`default_meta_commands.py:1178`) and dazzlecmd's `_cmd_kit_list` (`cli.py:558`) used a naive `ref.split(":", 1)` which only handles 2-segment refs (`core:find`, `dazzletools:git`). For multi-segment FQCN refs produced by `_discover_aggregator`'s post-recursion populate (`dz:core:find`, `wtf:core:locked`), the splitter yielded `ns="dz"`, `name_part="core:find"`, and the matcher then looked for a project with name `"core:find"` which never exists. Now matches by `_fqcn` first, falls back to legacy `ns:name` parsing for backward compatibility with existing kit manifests.

**Half 2 — `engine.command` plumbing through user-facing messages:** five places in the library hardcoded `'dz'` in user-facing hint and warning text, giving non-dazzlecmd consumers (wtf-windows, amdead, future personal aggregators) bad advice ("Use 'dz core:locked' to be explicit" when invoked through wtf). Threaded `engine.command` through: the FQCN-index precedence-note (`engine.py:412/414`), the deeply-nested-tool hint (`engine.py:1244-1248`), the stale-favorite warning (`engine.py:742-749`), and the short-name-collision hint in `render_list` (`default_meta_commands.py:445-447`). `FQCNIndex.__init__` now accepts a `command` parameter (default `"dz"` for legacy callers); the engine instantiates it as `FQCNIndex(command=self.command)`.

### Fixed

- **`render_kit_list` and `_cmd_kit_list` FQCN matching** — kit tools containing full FQCNs (e.g. `dz:core:find`, `wtf:core:locked`) now resolve correctly. Affected both forward (`dz kit list wtf`) and inverse (`wtf kit list dz`) directions. Same fix applied to both the library renderer and dazzlecmd's pre-X-22-full CLI implementation (the two still duplicate this logic — Category C migration is deferred).
- **Hardcoded `'dz'` in `FQCNIndex` precedence-note** (`engine.py:412/414`) — used `self.command` (threaded in via the new `FQCNIndex(command=...)` parameter). Affects every consumer that hits an ambiguous short-name resolution (`wtf locked`, etc.).
- **Hardcoded `'dz'` in deeply-nested-tool hint** (`engine.py:1244-1248`) — used `self.command`. wtf users invoking a 4+ segment tool now see `'wtf kit silence ...'` instead of `'dz kit silence ...'`.
- **Hardcoded `'dz'` in stale-favorite warning** (`engine.py:742-749`) — used `self.command`.
- **Hardcoded `'dz'` in short-name collision hint in `render_list`** (`default_meta_commands.py:445-447`) — uses `getattr(engine, "command", None) or "dz"`. Visible in `dz list` / `wtf list` output when collisions exist.

### Tests

- 1025 passed, 13 skipped (up from 1021 in v0.7.38; +4 new: 3 in `tests/test_default_meta_commands.py::TestRenderKitList` covering FQCN-match path, leaf-name display, and legacy `ns:name` fallback; 1 in `tests/test_engine_recursive.py::TestRerootHint::test_hint_uses_engine_command` regression guard).

### Changed

- **`FQCNIndex.__init__` signature** — adds `command="dz"` kwarg. Backward-compatible default for legacy callers; engine passes `self.command` so consumer-specific messages render correctly.
- **`dazzlecmd-lib` version**: `0.6.1` → `0.6.2` (PATCH — bug fix, backward-compatible API change).

### Known deferred

- **DockerRunner image-not-found hint** (`registry.py:1200`) still emits `Try: dz setup <fqcn>`. The runner factory doesn't have `engine.command` plumbed in; fixing requires either threading the engine through or stashing command on the project at discovery. Low priority (only fires when Docker tool pre-flight fails).

### Refs

- Closes #64 (`render_kit_list` FQCN matching + hardcoded `'dz'` in ambiguity message).
- Refs #63 (v0.7.38 fix exposed Half 1 by populating `kit["tools"]` honestly).
- Refs #30 (Phase 4 epic — lib is the product; remove dazzlecmd-isms).
- Refs #50 (Phase 4e retro — cross-aggregator dispatch correctness).

## [0.7.38] - 2026-05-12

Bug-fix patch — closes #63. The `discover_kits` / `_load_in_repo_kit_manifest` machinery for "aggregator-as-kit" embedding was structurally wrong: when an embedded thing was a full aggregator (had its own `kits/` subdirectory with multiple kit registry pointers), the loader treated it as a single self-describing kit, merging an arbitrary inner kit's fields (including identity fields like `name`, `tools`, `description`, `version`) into the outer pointer. The forward direction (dazzlecmd embeds wtf-windows) happened to work because wtf's `kits/core.kit.json` declares `tools_dir: "tools"` and `manifest: ".wtf.json"` — those merged fields happened to be correct. The inverse direction (wtf-windows embeds dazzlecmd) broke because dazzlecmd's per-kit pointers are minimal (no `tools_dir` declared), leaving the merge with no useful structural hints and a misconstructed absolute `tools_dir` that the engine then mis-normalized via `os.path.basename`.

Empirically surfaced during a recursion-proof experiment on 2026-05-12 — wtf-windows configured to embed dazzlecmd via `kits/dz.kit.json` + a junction at `tools/dz/`. Pre-fix: `wtf kit list dz` showed `0 tool(s)` despite the engine seeing the dz kit and its virtual sub-kit `dz:claude`. Post-fix: `wtf kit list dz` shows `22 tool(s)` (5 core + 14 dazzletools + 2 wtf-recursive + 1 virtual-related counting). The 3-tier recursion `dz:wtf:core:locked` works correctly (wtf embeds dazzlecmd embeds wtf), with the "deeply nested tool" hint firing as designed.

### Fixed

- **`_load_in_repo_kit_manifest` Pattern 2 (aggregator-as-kit)** — `packages/dazzlecmd-lib/src/dazzlecmd_lib/loader.py:88`. The old code picked the first inner kit file (alphabetically) and merged ALL its fields into the outer pointer. The new code:
  - Detects single-kit-using-kits-subdir-convention case (exactly one inner kit, named after the outer pointer) and merges fully (legacy compatibility, rare in practice).
  - Detects aggregator-as-kit case (multiple inner kits OR no name-matching kit) and extracts ONLY structural hints (`tools_dir`, `manifest`) from the first non-virtual inner kit that declares them. Never identity fields.
  - Keeps `tools_dir` RELATIVE (not absolute), so the engine's `_recurse_into_nested` joins it with `nested_root` correctly without needing the `basename` workaround.
  - Returns `None` if no inner kits declare hints — the engine falls back to defaults (`tools_dir="projects"`, `manifest=".dazzlecmd.json"`).

- **`discover_kits` always sets `kit["name"]` from the registry pointer** — `loader.py:73-83`. Previously the kit dict's `name` field could come from an inner kit's manifest (Pattern 2 merge) or the registry pointer (Pattern 2 fallback) depending on which path was taken. With the bug-fix, identity always comes from the registry-derived `kit_name`. This is the explicit semantic the architecture intended; the merge accidentally hid it.

- **`_discover_aggregator` populates aggregator-as-kit's `tools` list post-recursion** — `engine.py:864-872`. After the nested aggregator's projects are discovered, the parent kit's `tools` field is populated with the FQCNs of contributed projects. This is a derived view that makes `dz kit list` show the correct tool count for embedded aggregators. Pre-v0.7.38 the count came from the buggy merge.

### Recursion proof

The "any aggregator can attach to any other" architectural claim is now **empirically validated in both directions**:

- Forward (dazzlecmd embeds wtf-windows): `dz tree` shows `wtf [aggregator]` branch with `wtf:core:locked` + `wtf:core:restarted`. Same as before this commit (no regression).
- Inverse (wtf-windows embeds dazzlecmd): `wtf list` shows all 19 dazzlecmd tools + 2 wtf own. `wtf kit list` shows `dz 22 tool(s) (always active)`. Three-tier recursion `dz:wtf:core:locked` works (wtf → dazzlecmd → wtf-tools), with the deeply-nested-tool hint firing.

The recursion proof was scoped by the design analysis `2026-05-12__15-32-50__dev-workflow-process__full-recursion-and-tier2-scaffolding-sequencing.md` (Solution D — empirical config experiment first) and the experimental setup is documented in `2026-05-12__inverse-recursion-wtf-embeds-dazzlecmd.md` (Patterns and recipe for re-test).

### Tests

- 1021 passed, 13 skipped (up from 1016 in v0.7.37; +5 new in `tests/test_library.py::TestAggregatorAsKitDiscovery`).
- New test class covers: pointer-name preservation in aggregator case, structural-hint extraction from inner kits, no-hints fallback to engine defaults, Pattern 1 single-kit unchanged regression guard, end-to-end engine recursion populating `kit.tools` with discovered FQCNs.

### Changed

- **`dazzlecmd-lib` version**: `0.6.0` → `0.6.1` (PATCH — bug fix, no API addition or breaking change).

### Refs

- Closes #63 (`discover_kits` incorrectly merges in-repo manifest fields for aggregator-as-kit embedding).
- Refs #30 (Phase 4 epic — recursion proof unblocks Tier 2 scaffolding work).
- Refs #50 (Phase 4e retro — architectural foundation for cross-aggregator dispatch).
- Refs #51 (Inverse recursion — this fix is a prerequisite for the `nest_all_under` UX work in #47/#51; the underlying dispatch now works).

### Design

- `2026-05-12__15-32-50__dev-workflow-process__full-recursion-and-tier2-scaffolding-sequencing.md`
- `private/claude/experiments/2026-05-12__inverse-recursion-wtf-embeds-dazzlecmd.md`

## [0.7.37] - 2026-05-12

Phase 4e closeout, Tier 1 commit 9 (final) — closes #49. Terminal color taxonomy lands in `dazzlecmd-lib` as a slim, 8-color ANSI palette wired into the meta-command render surfaces (`render_list`, `render_info`, `render_tree`, `render_kit_list`, `render_kit_status`) and the user-facing stderr warning paths. dazzlecmd itself ships zero color code in this commit — the styling rides on the v0.7.34 X-22-narrow collapse, which already made dazzlecmd a thin wrapper over the library's renderers. amdead and wtf-windows pick up the styling automatically. This closes Tier 1 of the 0.7.x master closeout plan.

The /dev-workflow-process (`2026-05-11__04-14-42__dev-workflow-process__v0-7-37-color-taxonomy.md`) framed three orthogonal decisions: (1) **lib or per-consumer** — looking at amdead and wtf-windows cli.py, both consume the same library renderers, so adding color in dazzlecmd would force every other consumer to reimplement it; (2) **rich vs ANSI** — slim 8-color ANSI palette only (compatible with PuTTY, Windows Terminal, legacy cmd.exe via colorama, modern conhost with VT processing); (3) **flag vs config vs env** — env vars (`NO_COLOR`, `DZ_COLOR`, `FORCE_COLOR`) plus `isatty()` gating. No new argparse flags. Rationale: keep the surface minimal and let users disable via the community-standard `NO_COLOR=1` if their terminal can't handle ANSI.

The new `dazzlecmd_lib.colors` module exports the 8-color palette (`RESET`/`BOLD`/`DIM`/`RED`/`GREEN`/`YELLOW`/`CYAN`/`BRIGHT_RED`), a `should_use_color(stream)` probe (NO_COLOR > DZ_COLOR=always|FORCE_COLOR > DZ_COLOR=never > isatty), a `colorize(text, *codes)` wrapper, a `colorize_for(stream, text, *codes)` convenience wrapper for the stderr-warning pattern, and two semantic stderr-class wrappers — `warn(text)` (YELLOW) and `error(text)` (BRIGHT_RED) — that default the stream to `sys.stderr` so call sites collapse from `print(colorize_for(sys.stderr, f"...", YELLOW), file=sys.stderr)` to `print(warn(f"..."), file=sys.stderr)`. On Windows the module lazily imports colorama; for the forced-color paths (`DZ_COLOR=always` / `FORCE_COLOR`) it calls `colorama.init(strip=False)` so ANSI bytes survive into a redirected pipe — colorama's default strips them.

### Added

- **`dazzlecmd_lib.colors`** — new module. 8-color ANSI palette, `should_use_color(stream=None)`, `colorize(text, *codes)`, `colorize_for(stream, text, *codes)`, semantic stderr wrappers `warn(text, stream=None)` and `error(text, stream=None)`, `_init_windows_ansi(force=False)`. Lazy colorama import on Windows. Public API documented in module docstring.

- **`dazzlecmd-lib[color]` optional extra** — colorama as a Windows-only optional dep. Modern Windows (1511+) doesn't need colorama; legacy cmd.exe does. Keeping it optional preserves the lib's slim-defaults constraint.

### Changed

- **Library `render_list`** — section headers BOLD, virtual-kit annotation (`(virtual: <vk_name>)`) DIM, shadow `[*]` marker BOLD+RED, dual-presence `[+]` marker CYAN, flat-fallback header row BOLD. Plain/styled label split so column-width math stays correct in the presence of ANSI codes.

- **Library `render_info`** — alias provenance line DIM (both qualified and standard variants), shadow-status banner "Shadow status:" BOLD+YELLOW. **Description field now wraps to terminal width** (closes #60) — continuation lines indent to the value column (13 spaces past `Description: `) so multi-line descriptions align cleanly. Same `_wrap_description` helper that `render_list` and `dz kit list <kit>` use, applied uniformly. Previously the `Description:` line was a bare `print()` that ran off-screen on narrow terminals or hard-wrapped at terminal width with no continuation indent.

- **Library `render_tree`** — root header BOLD, kit names BOLD, kit markers (`[always_active]` / `[aggregator]` / `[disabled]` / `[virtual]`) DIM, shadow `[shadowed]` marker BOLD+RED, virtual-kit alias arrows DIM.

- **Library `render_kit_list`** — kit names BOLD, `(always active)` annotation DIM, "cross-platform" platform value DIM (OS-specific values stay plain so they stand out), `(not found)` marker DIM.

- **Library `render_kit_status`** — kit names BOLD.

- **Library stderr paths** — user-facing meta-command stderr writes in `default_meta_commands.py` and `cli_helpers.py` now use `colorize_for(sys.stderr, ...)` with YELLOW (advisories: tool-not-found, no-setup, conflicts-with-reserved) or BRIGHT_RED (errors: tree-requires-engine, kit-not-found, override-file-parse-failure, etc). Engine/loader/registry subprocess-orchestration stderr writes are intentionally untouched in this commit; those are higher-risk plumbing paths and the user-facing value of styling them is lower. Sweep deferred to a follow-up.

- **dazzlecmd `_cmd_setup`** — adopts the same `colorize_for(sys.stderr, ...)` pattern for the user-facing tool-not-found / override-file-parse / platform-not-available paths. The remaining cli.py-side stderr writes (`_cmd_add`, `_cmd_kit_show`, `_cmd_kit_remove`, `dispatch_tool` error path, etc.) are deferred to a follow-up — same boundary as the engine/loader/registry sweep.

- **`dazzlecmd-lib` version**: `0.5.0` → `0.6.0` (MINOR — new public `dazzlecmd_lib.colors` module, new `colorize_for` API, visible behavior change on every meta-command render surface).

### Color detection precedence

1. `NO_COLOR` set (any value, including empty string) → no color. Community standard (https://no-color.org/).
2. `DZ_COLOR=always` OR `FORCE_COLOR` set → color on (overrides isatty).
3. `DZ_COLOR=never` → no color.
4. Fallback: `stream.isatty()` — TTY gets color, redirected/piped output stays plain.

### Tests

- 1016 passed, 13 skipped (up from 979 in v0.7.36; +33 new tests in `tests/test_colors.py` plus +4 wrap tests in `tests/test_default_meta_commands.py::TestRenderInfoDescriptionWrap`).
- `tests/test_colors.py` — 33 tests covering `colorize` (empty codes, single code, multiple codes, empty string), env precedence (NO_COLOR vs FORCE_COLOR, NO_COLOR vs DZ_COLOR=always, DZ_COLOR=always vs non-TTY, FORCE_COLOR vs non-TTY, DZ_COLOR=never vs TTY, DZ_COLOR=never loses to FORCE_COLOR, case-insensitive DZ_COLOR, garbage DZ_COLOR falls through), isatty fallback (TTY True, non-TTY False, stream without isatty, default `sys.stdout`), public constants regression guard (8-color palette only, no 256-color or RGB), the `colorize_for` stream-aware wrapper (TTY/non-TTY/NO_COLOR/FORCE_COLOR/empty-codes), and the semantic stderr wrappers `warn` and `error` (TTY/non-TTY/NO_COLOR/explicit-stream, with a regression guard that warn and error use distinct colors).
- `tests/test_default_meta_commands.py::TestRenderInfoDescriptionWrap` — 4 tests covering short-description-unwrapped, long-description-wraps-to-terminal-width, continuation-indent-aligns-with-value-column, empty-description-renders-single-line.
- Human checklist: `tests/checklists/v0.7.37__Tier1B__color-taxonomy.md`.

### Refs

- Closes #49 (terminal color taxonomy across `dz list` / `dz tree` / `dz info` / `dz kit list` / stderr).
- Closes #60 (`dz info` Description field wraps to terminal width — folded into this commit per scope discussion; ~10 LOC + 4 tests).
- Refs #50 (Phase 4e retrospective; Tier 1 commit 9 of master plan — Tier 1 now closes).
- Refs #30 (Phase 4 epic; Tier 1 of master closeout plan completes).
- Refs #61 (extended description / mini-manpage surface; new feature deferred to /dev-workflow-process).

### Design

- `private/claude/2026-05-11__04-14-42__dev-workflow-process__v0-7-37-color-taxonomy.md`

## [0.7.36] - 2026-05-11

Phase 4e closeout, Tier 1 commit 8 — closes #48. The `dz kit list <kit>` canonical-kit drill-in had retained a pre-v0.7.27 rendering pattern: fixed 16-character columns for name and platform, plus a hardcoded 55-character description truncation with ellipsis. Result: names longer than 16 chars (like `claude-session-metadata`) collided with the platform column, and descriptions got chopped even when the terminal had plenty of room. Every other display surface (`dz list`, `dz tree`, the `dz` help builder, and the v0.7.27 virtual-kit drill-in via `_render_virtual_kit_aliases`) already computed widths from actual data and used `_wrap_description` for terminal-aware wrapping. v0.7.36 brings the canonical-kit drill-in into parity.

The fix is localized to a single branch in `src/dazzlecmd/cli.py::_cmd_kit_list`. The virtual-kit drill-in (which uses `_render_virtual_kit_aliases`) is untouched.

### Changed

- **`dz kit list <kit>` canonical-kit drill-in** — column widths are now derived from actual row data (longest name + longest platform), and descriptions wrap to the available terminal width via `_wrap_description` (which already lives in `dazzlecmd_lib.default_meta_commands` and is re-exported through `dazzlecmd.cli` for the kit-list path). The fixed 16-char columns and the 55-char truncation are gone.

### Tests

- 979 passed, 13 skipped (up from 974 in v0.7.35; +5 new tests).
- `tests/test_cli_kit.py::TestKitListDrillInColumnWidths` — 5 tests: short-name-renders-cleanly, long-name-does-not-collide-with-platform, description-wraps-to-terminal-width (no `...` truncation), mixed-short-and-long-names, not-found-marker-preserved.
- Live-verified: `dz kit list dazzletools` now displays `claude-session-metadata` (24 chars) without column collision, descriptions wrap to terminal width with proper indent alignment.
- Human checklist: `tests/checklists/v0.7.36__Tier1B__kit-list-column-parity.md`.

### Refs

- Closes #48 (`dz kit list <kit>` drill-in: column-width parity with dz list).
- Refs #50 (Phase 4e retrospective; Tier 1 commit 8 of master plan).
- Refs #30 (Phase 4 epic; Tier 1 of master closeout plan).

## [0.7.35] - 2026-05-10

Phase 4e closeout, Tier 1 commit 7 — `dz kit favorite --migrate-stale` interactive subcommand (4e-T2 from the master closeout plan).

The v0.7.27 commit shipped detection-and-warning for stale favorites: when `FQCNIndex.resolve` is asked to look up a name with a favorite mapping whose target FQCN is no longer discovered, the engine prints a warning and falls through to precedence. That detection is fine for surfacing the problem but doesn't help the user fix it — they had to manually `dz kit unfavorite <short>` and `dz kit favorite <short> <new-fqcn>` for each stale entry.

`dz kit favorite --migrate-stale` is the maintenance-cleanup flow: walks every favorite in user config, checks whether its target FQCN still resolves (against canonical_index OR the alias chain), and for each stale entry prompts the user interactively to remap, drop, or skip. Auto-suggests a replacement when exactly one currently-discovered tool registers the same short name (the unambiguous case).

Non-TTY invocations print the stale list with suggestions to stderr and exit non-zero, instructing the user to re-run from an interactive shell or use `dz kit unfavorite <short>` manually. Same logic as a `--check` / read-only mode without adding a separate flag.

### Added

- **`dz kit favorite --migrate-stale`** — interactive maintenance subcommand. Detects stale favorites (target FQCN not in `engine.fqcn_index.canonical_index` AND not resolvable via the alias chain), prompts per-entry, writes the cleaned-up favorites map back to user config when remap/drop choices are made.

- **`_suggest_favorite_replacement(short, stale_fqcn, engine)`** helper — returns the canonical FQCN of the unique discovered tool whose short name matches, or `None` for ambiguous cases (zero matches or multiple matches). Conservative by design: better to make the user pick than to suggest the wrong tool.

### Changed

- **`dz kit favorite` parser** — positional `short` and `fqcn` now `nargs="?"` so `--migrate-stale` can be invoked without them. Validation in `_cmd_kit_favorite` rejects the cases (no flag + no positional args) and (flag + positional args).

### Tests

- 974 passed, 13 skipped (up from 959 in v0.7.34 — 15 new tests).
- `tests/test_cli_kit.py::TestKitFavoriteMigrateStale` — 11 tests covering: no favorites, all-valid favorites, stale + non-TTY listing, stale + non-TTY with suggestion, interactive remap, interactive drop, interactive skip-keeps-stale, alias-target resolves canonical (two-segment `<vk>:<short>` form), qualified-alias dispatch form IS stale (three-segment `<agg>:<vk>:<short>` not in alias_index), dispatch via handler entry point, validation errors for arg combinations.
- `tests/test_cli_kit.py::TestSuggestFavoriteReplacement` — 3 tests covering single-match return, no-match returns None, ambiguous-match returns None.
- Live-verified: non-TTY path correctly detects stale favorite, prints to stderr, exits 1. Two-segment alias-form favorite (`claude:cleanup`) correctly identified as NOT stale. Interactive path covered by `monkeypatch.setattr("builtins.input", ...)` in unit tests.

### Notes on alias FQCN forms

Worth recording for future reference: virtual-kit aliases populate `engine.fqcn_index.alias_index` with **two-segment** keys of the form `<vk_name>:<short>` (e.g., `claude:cleanup` → `dazzletools:claude-cleanup`). The **three-segment** fully-qualified form `<agg>:<vk>:<short>` (e.g., `dazzletools:claude:cleanup`) is a valid dispatch path — `dz dazzletools:claude:cleanup` works because `engine.find_project()` parses it — but it's NOT a key in `alias_index`. So a favorite stored in qualified-form IS flagged stale by `--migrate-stale`; the migration suggestion will typically point at the canonical, which is the correct fix. Initial test mock + checklist used the qualified form incorrectly; tester-unbounded sweep caught the discrepancy and both were corrected before commit.
- Human checklist: `tests/checklists/v0.7.35__Tier1B__kit-favorite-migrate-stale.md`.

### Refs

- Refs #50 (Phase 4e retrospective; Tier 1 commit 7 of master plan).
- Refs #30 (Phase 4 epic; Tier 1 of master closeout plan).

## [0.7.34] - 2026-05-07

Phase 4e closeout, Tier 1 commit 6 — the X-22-narrow CLI collapse. dazzlecmd's `_cmd_list`, `_cmd_info`, and `_cmd_tree` collapse to thin wrappers over the library equivalents (`render_list` / `render_info` / `render_tree`). The library now owns every behavior these three commands ever had — sectioned `dz list` with `--show {default,canonical,alias,all}` and `[*]`/`[+]` markers, full `dz info` with `--raw` / `--platform` / shadow status / linked-project line, and `dz tree` with `--show-disabled` and `[always_active]` / `[aggregator]` / `[disabled]` markers. The library version was extended in this commit to reach byte-equivalence with dazzlecmd's prior tree behavior, so no user-visible surface was dropped.

This is the structural payoff for the v0.7.30 → v0.7.33 library-parity arc. Cumulative net delete from `cli.py`: about 950 lines (2521 → 1571). dazzlecmd is now a "thin instance" of dazzlecmd-lib for the list/info/tree surface, the same shape as amdead and wtf-windows. The remaining dazzlecmd-specific surfaces (kit management, mode switching, scaffolding, setup) stay on the original dispatch pattern and are addressed by the future X-22-full work.

`dazzlecmd-lib` bumps `0.4.1` → `0.5.0` (MINOR) for the new public API surface added to `render_tree` (`--show-disabled` flag, kit-state computation from user config, canonical-kit `[always_active]` / `[aggregator]` / `[disabled]` markers, JSON output keys `always_active` / `is_aggregator` / `state`). The lib also fixes one small `render_info` discrepancy: the "tool not found" message now uses `engine.command` for the hint (matches the dazzlecmd CLI's prior wording for any consumer; previously the lib emitted a bare `'list'` hint and printed to stderr).

The thorough-cleanup discipline applied: pre-implementation grep across `_build_list_entries`, `_wrap_description`, `_print_runtime_*`, `_RUNTIME_DISPATCH_FIELDS`; full-suite pytest before AND after the collapse; golden-output capture of `dz list` (default + 3 `--show` modes), `dz tree`, `dz info` for safedel + a missing tool — all 7 surfaces verified byte-equivalent to v0.7.33 post-collapse. Live consumer verification: `amdead info detect`, `amdead list`, `wtf list` all unchanged.

Test-suite cleanup: `tests/test_cli_info.py` (23 tests, 406 LOC) deleted. The tests covered the dazzlecmd-side `_print_runtime_raw` / `_print_runtime_resolved` / `_print_runtime_platform_preview` helpers that no longer exist in dazzlecmd; the library's `tests/test_default_meta_commands.py::TestRenderInfo` provides equivalent integration coverage. One test (`TestRenderInfo::test_not_found`) updated to check stdout instead of stderr (matches the new behavior; was checking that the not-found message went to stderr).

### Changed

- **`src/dazzlecmd/cli.py` `_cmd_list`** — collapses from ~262 LOC to a 9-LOC thin wrapper that calls `dazzlecmd_lib.default_meta_commands.render_list(args, projects, engine=engine)`. All `--show` modes, sectioned layout, marker rendering, footer counts, and virtual-kit empty-section injection now sourced from the library.

- **`src/dazzlecmd/cli.py` `_cmd_info`** — collapses from ~104 LOC to an 8-LOC thin wrapper that calls `render_info(args, projects, engine)`. Alias provenance, shadow status, runtime-dispatch resolution, pass-through marker, deps display, setup hint, and "Linked to:" line all sourced from the library.

- **`src/dazzlecmd/cli.py` `_cmd_tree`** — collapses from ~217 LOC to a 12-LOC thin wrapper that calls `render_tree(args, engine, engine.projects, engine.kits, engine.project_root)`. The `--show-disabled` flag, kit-info computation, kit markers, JSON output extensions, and disabled-state filtering are all now in the library.

- **`src/dazzlecmd/cli.py` `_build_list_entries`** — deleted (~150 LOC). The public `dazzlecmd_lib.default_meta_commands.build_list_entries` (added in v0.7.31) is the canonical implementation.

- **`src/dazzlecmd/cli.py` `_wrap_description`** — deleted as a local definition; replaced with a back-compat re-export from `dazzlecmd_lib.default_meta_commands._wrap_description` so the remaining consumer (`_cmd_kit_list`'s virtual-kit listing path; Category C, deferred to X-22-full) keeps working without import-path edits.

- **`src/dazzlecmd/cli.py` runtime helpers** — `_RUNTIME_DISPATCH_FIELDS` constant + `_print_runtime_dispatch_fields` / `_print_runtime_resolved` / `_print_runtime_raw` / `_print_runtime_platform_preview` (~230 LOC) deleted. The library's equivalents (added verbatim in v0.7.32) are the canonical implementations.

- **Library `render_tree`** — extended to match dazzlecmd's prior CLI behavior: accepts `args.show_disabled` and switches the project source to `engine.all_projects`; computes `kit_info` (`always_active`, `is_aggregator` based on whether the kit has a nested `kits/` subdir); computes `_kit_state` from `engine._get_user_config()` (`active_kits` / `disabled_kits`); renders `[always_active]` / `[aggregator]` / `[disabled]` markers on canonical-kit headers; adds disabled-state markers to virtual-kit headers; adds `always_active` / `is_aggregator` / `state` keys to JSON output. The dazzlecmd CLI's `_cmd_tree` `--show-disabled` flag is preserved on the dazzlecmd parser side and the wrapper passes it through unchanged.

- **Library `tree_parser_factory`** — adds the `--show-disabled` argument (matching dazzlecmd's prior parser).

- **Library `render_info` "not found" message** — now `f"Tool '{tool_name}' not found. Use '{engine.command} list' to see available tools."` printed to stdout. Previously the message used a bare `'list'` hint and went to stderr. This matches dazzlecmd's prior wording and means amdead, wtf, and any future consumer get a hint that uses their own command name.

- **`dazzlecmd-lib` version**: `0.4.1` → `0.5.0` (MINOR — new public API surface in `tree_parser_factory` + `render_tree`; small change in `render_info` not-found message).

- **dazzlecmd's `dazzlecmd-lib` pin**: `>=0.4.1` → `>=0.5.0`. The alias package's pin advances accordingly.

- **`packages/dazzlecmd-lib/CHANGELOG.md`** — adds the [0.5.0] entry.

### Removed

- **`src/dazzlecmd/cli.py` private helpers** — `_build_list_entries`, the runtime helpers (`_RUNTIME_DISPATCH_FIELDS` + 4 `_print_runtime_*`), and the local definition of `_wrap_description`. Total: ~430 LOC removed (the library now owns these). `_wrap_description` retained as a back-compat re-export.

- **`tests/test_cli_info.py`** — 23 tests, 406 LOC. Library has equivalent integration coverage.

### Tests

- 959 passed, 13 skipped (down from 984 in v0.7.33 — net −23 from `test_cli_info.py` deletion; library coverage unchanged at 24 `TestRenderInfo` tests + 14 `TestRenderTree` tests + 14 `TestRenderList` tests + 9 `TestBuildListEntries` tests).

- `tests/test_default_meta_commands.py::TestRenderInfo::test_not_found` updated for the not-found message stdout change.

- Golden-output verification: 7 surfaces captured pre-collapse (`tests/one-offs/x22-narrow-golden/`) and diffed post-collapse — all byte-equivalent.

- Human checklist: `tests/checklists/v0.7.34__Tier1B__x-22-narrow-cli-collapse.md`.

### Verification

- `dz list` / `dz list --show all/canonical/alias` / `dz tree` / `dz info safedel` / `dz info dz` (not-found) — all byte-equivalent to v0.7.33 baseline.

- `amdead info detect` — full info banner unchanged. `amdead list` — sectioned output unchanged.

- `wtf list` unchanged. `wtf info` has a pre-existing wtf-windows bug (`_wtf_info_handler` calls `render_info(args, projects)` with the v0.7.31 signature, missing `engine`); not introduced by this commit, out of scope. Future wtf upstream PR (4e-T1) will address.

### Refs

- Refs #50 (Phase 4e retrospective; Tier 1 commit 6 of master plan).
- Refs #30 (Phase 4 epic; Tier 1 of master closeout plan).
- Refs #27 (dazzlecmd-lib package — full list/info/tree parity now in the library).

## [0.7.33] - 2026-05-07

Phase 4e closeout, Tier 1 commit 5 (the linked-project-helpers port — final library prerequisite before the v0.7.34 X-22-narrow CLI collapse). Library `dazzlecmd-lib::paths` gains `is_linked_project()` and `get_link_target()` helpers, ported verbatim from `dazzlecmd.importer`. Library `render_info` now displays a "Linked to: <target>" line when a project's `_dir` is a symlink or Windows junction. dazzlecmd's `importer` module keeps the old import surface stable via a back-compat re-export, so `mode.py`, `tests/test_importer.py`, and any external consumer that imports from `dazzlecmd.importer` continue to work unchanged.

This is the third and final library-parity port preparing for the X-22-narrow CLI collapse. After v0.7.33, every dazzlecmd-CLI behavior in `_cmd_list`/`_cmd_info`/`_cmd_tree` has a library equivalent, so the v0.7.34 collapse can convert all three to thin wrappers without losing any user-visible surface.

dazzlecmd's `cli.py` is unchanged in this commit. `_cmd_info` continues to print "Linked to:" via its existing local code (now resolves through the back-compat re-export to the library helpers). v0.7.34 will collapse `_cmd_info` to a thin wrapper and the library version will own the display.

Caught at v0.7.32 sign-off audit: dazzlecmd's `_cmd_info` had a 4-line linked-project block (`cli.py:1213-1218`) using `dazzlecmd.importer.is_linked_project` — a dazzlecmd-package coupling that the library version didn't have. Per the thorough-cleanup discipline: don't ship a collapse that silently drops behavior. Port the helpers + display first as their own scoped commit, then collapse.

The helpers are also useful to wtf-windows (which has its own duplicate at `projects/wtf/src/wtf_windows/importer.py:137,151`); after v0.7.33, wtf-windows can switch its `_wtf_info_handler` augmentation to call the library version too, eliminating its duplicate. (Future cleanup; not in v0.7.33 scope.)

Applied disciplines: copy-don't-rewrite (verbatim OS-level capture from `src/dazzlecmd/importer.py:141-168`, paste into `paths.py`, no modifications) and thorough cleanup (back-compat re-export from `dazzlecmd.importer` so all 14 existing consumers — including `mode.py`'s 9 call sites and 2 test files — keep working without import-path edits).

### Added

- **`dazzlecmd_lib.paths.is_linked_project(tool_dir)`** — cross-platform symlink/junction detection. On Windows, uses `ctypes.windll.kernel32.GetFileAttributesW` to detect the `FILE_ATTRIBUTE_REPARSE_POINT` flag (catches symlinks AND junctions); falls back to `os.path.islink` if the ctypes call fails. On POSIX, uses `os.path.islink` directly. Public API.

- **`dazzlecmd_lib.paths.get_link_target(tool_dir)`** — returns the resolved target of a symlink/junction, or `None` for non-links. Uses `os.readlink`. Public API.

- **Library `render_info` "Linked to:" line** — when a project's `_dir` is a symlink/junction, surfaces the link target. Library consumers (amdead, wtf-windows, sysdiagnose, future personal aggregators) get this surface for free; previously only dazzlecmd's CLI displayed it.

### Changed

- **`dazzlecmd.importer`** — `is_linked_project` and `get_link_target` are now re-exports from `dazzlecmd_lib.paths` (replacing the previous local implementations). Identical behavior; no changes for any caller. Preserves backward compat for `mode.py`, `tests/test_importer.py`, `tests/test_mode.py`, and any external code that already imports from `dazzlecmd.importer`.

- **`dazzlecmd-lib` version**: `0.4.0` → `0.4.1` (PATCH bump — additive helpers + one display line; surface is intentionally small relative to the 0.2.0/0.3.0/0.4.0 MINORs that shipped large API additions).

- **dazzlecmd's `dazzlecmd-lib` pin**: `>=0.4.0` → `>=0.4.1`. The alias package's pin advances accordingly.

- **`packages/dazzlecmd-lib/CHANGELOG.md`** — new file, backfilled with entries for 0.1.0 / 0.2.0 / 0.3.0 / 0.4.0 / 0.4.1. The lib is meant to stand alone as a framework for custom aggregators (amdead, wtf-windows, sysdiagnose, and future user-built tools); it has been bumping versions independently for four commits without a changelog of its own. Adding it here makes future repo extraction (master plan item X-1) cleaner and gives lib-only consumers a tracking record.

### Tests

- `tests/test_paths.py::TestIsLinkedProject` — 3 new tests: normal-dir-returns-false, nonexistent-path-returns-false, symlink-returns-true (skips on Windows where symlink creation requires admin/Developer Mode).
- `tests/test_paths.py::TestGetLinkTarget` — 3 new tests: returns-none-for-normal-dir, returns-none-for-nonexistent, returns-target-for-symlink (same skip condition).
- `tests/test_paths.py::TestLibraryReExportFromDazzlecmdImporter` — 1 new test verifying `dazzlecmd.importer.is_linked_project is dazzlecmd_lib.paths.is_linked_project` (back-compat regression guard).
- `tests/test_default_meta_commands.py::TestRenderInfo` — 2 new tests: regression guard (no "Linked to:" line for normal dirs), positive case (line shown for symlinks; skips when symlink creation isn't available).
- Total: 984 passed, 13 skipped (up from 975 in v0.7.32 — 9 new tests).
- Human checklist: `tests/checklists/v0.7.33__Tier1B__library-link-helpers-port.md`.

### Verification

- `amdead info detect` — clean output (no spurious "Linked to:" line for non-linked tools).
- `dz info safedel` — unchanged from v0.7.32 (dazzlecmd's `_cmd_info` still uses its own code, which now resolves through the back-compat re-export).
- `python -m pytest tests/test_importer.py tests/test_mode.py` — all existing importer + mode tests still pass against the back-compat shim.

### Refs

- Refs #50 (Phase 4e retrospective; Tier 1 commit 5 of master plan).
- Refs #30 (Phase 4 epic; Tier 1 of master closeout plan).
- Refs #27 (dazzlecmd-lib package — link-helpers added; library now ready for v0.7.34 X-22-narrow collapse).


## [0.7.32] - 2026-05-07

Phase 4e closeout, Tier 1 commit 4 (the info-parity port). Library `dazzlecmd-lib::render_info` reaches behavioral parity with dazzlecmd's `_cmd_info` so library consumers (amdead, wtf-windows, sysdiagnose, future personal aggregators) get the full info display surface — `--raw` and `--platform` flags, full conditional-dispatch runtime resolution, qualified-alias provenance, pass-through marker, Python deps display, and a setup hint that uses the consumer's command name (not a hardcoded `dz`).

This is a prerequisite commit for v0.7.33 (X-22-narrow), where dazzlecmd's `_cmd_list`/`_cmd_info`/`_cmd_tree` collapse to thin library wrappers. The collapse was pre-empted at v0.7.32 sign-off when the audit caught that dazzlecmd's `_cmd_info` had behavior the library version didn't (per the thorough-cleanup discipline). Rather than ship a collapse that silently dropped behavior, the missing surface is ported to the library first as its own scoped commit.

dazzlecmd's `cli.py` is unchanged in this commit — the helpers and `_cmd_info` continue to work as before. `cli.py` will collapse in v0.7.33 to delete the now-duplicated dazzlecmd-side helpers.

Applied disciplines: copy-don't-rewrite (verbatim OS-level capture from dazzlecmd `cli.py:889-1116`, then paste/trim/modify with the engine.command rename for the setup hint) and thorough cleanup (live-verified amdead `info` consumer post-port, full pytest suite green at 975).

### Added

- **Library `_RUNTIME_DISPATCH_FIELDS` constant** — declarative table of runtime fields with display labels and optional render functions. Used by all three runtime helpers.

- **Library `_print_runtime_dispatch_fields(runtime)`** — concrete dispatch field printer covering `script_path`, `interpreter`, `interpreter_args`, `npm_script`, `npx`, `shell`, `shell_args`, `shell_env`, `interactive`, plus Docker-specific fields (`image`, `volumes`, `env`, `env_passthrough`, `docker_args`, `inner_runtime`).

- **Library `_print_runtime_resolved(project)`** — default view: resolves the runtime for the current host using `dazzlecmd_lib.registry.resolve_runtime`, with the BUG-3 fix that triggers resolution when the manifest contains `{{var}}` references (catches unresolved vars at inspection time rather than silently passing through). Falls back to a clean error message when resolution fails (`NoRuntimeResolutionError`, schema-version errors, unresolved-template errors, etc.).

- **Library `_print_runtime_raw(project)`** — `--raw` view: shows the manifest as declared, no resolution. Surfaces manifest-top `_vars` AND runtime-block `_vars` so authors debugging template references see what's declared at each scope level (BUG-2 fix). Shows `platforms` keys, per-platform overrides with subtype names, and `prefer` ladder entries with their detect_when status.

- **Library `_print_runtime_platform_preview(project, spec)`** — `--platform SPEC` view: previews per-platform resolution without PATH checks. Uses `dazzlecmd_lib.platform_resolve.resolve_platform_block` for the platform-specific resolution; shows the resolved runtime fields and the prefer ladder (preconditions not evaluated in preview).

- **`--raw` and `--platform SPEC` flags in `info_parser_factory`** — library consumers' info subcommand now accepts these flags out of the box.

### Changed

- **Library `render_info` qualified-alias provenance** — when the input was a qualified alias (`ctx.resolution_kind == "qualified_alias"`), the provenance line now shows `(qualified alias '<original>' = '<alias>' -> canonical '<canonical>')` matching dazzlecmd's `_cmd_info`. Regular alias resolution still produces the simpler `(resolved via virtual-kit alias 'X' -> 'Y')` form.

- **Library `render_info` runtime dispatch** — replaced the simple Runtime/Script/Interpreter block with conditional dispatch via the three new helpers (`_print_runtime_raw` for `--raw`, `_print_runtime_platform_preview` for `--platform`, `_print_runtime_resolved` for default). Library consumers running `aggregator info <tool>` against tools with conditional runtime now see proper resolution.

- **Library `render_info` pass-through display** — `Pass-through: yes` line surfaces when `project["pass_through"]` is truthy.

- **Library `render_info` Python deps display** — `Python deps: <list>` line surfaces when `project["dependencies"]["python"]` is set.

- **Library `render_info` setup hint** — when a tool declares `setup`, the hint now reads `Run: <engine.command> setup <fqcn>` (using the consumer's actual command name from `engine.command` — `dz` for dazzlecmd, `amdead` for amdead, etc.). Falls back to literal `dz` when `engine.command` is unset (safety net for ad-hoc usage).

- **`dazzlecmd-lib` version**: `0.3.0` → `0.4.0` (MINOR bump for new public surface in `info_parser_factory` and `render_info`).

- **dazzlecmd's `dazzlecmd-lib` pin**: `>=0.3.0` → `>=0.4.0`. The alias package's pin advances accordingly.

### Tests

- `tests/test_default_meta_commands.py::TestRenderInfo` — 8 new tests for the info-parity port: `test_pass_through_displayed`, `test_python_deps_displayed`, `test_setup_hint_uses_engine_command`, `test_raw_flag_marks_runtime_unresolved`, `test_platform_flag_shows_preview`, `test_qualified_alias_provenance`, `test_runtime_resolved_for_simple_python_runtime`, `test_docker_runtime_fields`.
- Total: 975 passed, 13 skipped (up from 967 in v0.7.31).
- Human checklist: `tests/checklists/v0.7.32__Tier1B__library-render-info-parity.md`.

### Verification

Live-verified post-port that library consumers gain the new surfaces:

- `amdead info setup` — full info display including shadow block, standard fields, Runtime + Script + Shell dispatch fields.
- `amdead info setup --raw` — same display with `(raw, unresolved)` marker on the Runtime line. The `--raw` flag now works in amdead.
- `amdead info detect` — non-shadowed tool renders cleanly (no shadow block, no spurious markers).

### Refs

- Refs #50 (Phase 4e retrospective; Tier 1 commit 4 of master plan).
- Refs #30 (Phase 4 epic; Tier 1 of master closeout plan).
- Refs #27 (dazzlecmd-lib package — info parity now matches dazzlecmd CLI; ready for v0.7.33 X-22-narrow collapse).


## [0.7.31] - 2026-05-07

Phase 4e closeout, Tier 1 commit 3 (Phase A of the 4b-T9 / X-22-narrow two-commit sequence). Library-only release: `dazzlecmd-lib` reaches parity with dazzlecmd's CLI for the `list` and `tree` rendering surfaces, and exposes `build_list_entries` as a public stable API for aggregators that want to render their own display layer.

dazzlecmd's `cli.py` is unchanged in this release. The CLI still uses its own `_cmd_list`/`_cmd_info`/`_cmd_tree` duplicates. The duplication collapse ships in v0.7.32 (Phase B of the same sequence).

Library consumers (amdead, wtf-windows, sysdiagnose, future personal aggregators) get the parity surfaces immediately — sectioned virtual-kit layout in `list`, `--show {default,canonical,alias,all}` enum, `[+]` markers for canonicals that have aliases, `[*]` collision markers, `(virtual kit '<name>')` section annotations, virtual-kit branches in `tree` with `-> canonical` arrows, and the `build_list_entries(...)` data-layer hook for custom renderers.

Design source: `2026-05-06__19-43-51__dev-workflow-process_library-render-list-parity-and-override-abstraction.md` (Solution D — full parity port + public `build_list_entries`). Sequencing source: `2026-05-06__23-21-32__dev-workflow-process__4b-T9-render-list-parity-and-dazzlecmd-as-library-consumer.md` (Solution C — two-commit sequencing).

Applied disciplines: copy-don't-rewrite (verbatim OS-level capture of source, paste, trim, then modify) and thorough cleanup (grep + run tests + verify with downstream consumers; no half-migrations left behind). The verbatim source for the library port came from dazzlecmd `cli.py:97-126` (`_wrap_description`), `cli.py:473-732` (`_cmd_list`), `cli.py:735-881` (`_build_list_entries`), and `cli.py:2202-2312` (`_cmd_tree`'s virtual-kit branches). Renames at the modify step: `_cmd_list` → `render_list`, `_build_list_entries` → `build_list_entries` (public), `shutil` → `_shutil` (library import alias).

### Added

- **`build_list_entries(projects, engine, show_mode, kit_filter)`** — PUBLIC stable API. Returns a list of entry dicts (documented schema with stable keys) for aggregators that want to render their own display layer. The library's `render_list` uses this internally; consumers can call it directly to get the data-layer output and write their own renderer with custom colors, columns, markers, JSON output, etc. Entry dict keys: `name`, `kit`, `description`, `entry_type` (canonical|alias), `namespace`, `platform`, `tags`, `_fqcn`, `_canonical_fqcn`, `section_key`, `section_kind` (canonical|virtual), `section_vk_name` (alias-only), `has_aliases` (canonical-only).

- **Library `render_list(args, projects, engine=None)`** sectioned + `--show`-aware. Default behavior unchanged for `engine=None` callers (flat output, backward-compat). When `engine` is passed, full parity with dazzlecmd's `_cmd_list`: virtual-kit sections, `[+]` markers on canonicals with aliases, `[*]` collision markers on short-name conflicts, virtual-kit annotations (`(virtual kit '<name>')`), `--show {default,canonical,alias,all}` content selector, `list_view` config-key fallback, `show_empty_virtual_kits` config key for rendering empty virtual-kit sections, kit filter accepts canonical OR virtual-kit name.

- **`--show {default,canonical,alias,all}`** flag in `list_parser_factory`. Content selector for the four display modes: `default` (alias-preferred), `canonical` (script-stable legacy), `alias` (virtual-kit aliases only), `all` (canonicals + aliases).

- **Library `render_tree`** virtual-kit branches. Virtual kits now render as separate top-level branches with `[virtual]` markers and `-> canonical` arrows from each alias. Footer reports alias count and virtual-kit count when applicable. Aggregators with no virtual kits keep the existing simple footer.

- **`_wrap_description(text, width)`** helper (private) — word-boundary wrapping with hard-break-with-hyphen fallback. Used by `render_list`.

### Changed

- **`list_handler` now passes `engine` to `render_list`**. Consumers who don't care about the engine-aware path keep working: the backward-compat `engine=None` path emits the legacy flat output.

- **`dazzlecmd-lib` version**: `0.2.0` → `0.3.0` (MINOR bump for new public API surface).

- **dazzlecmd's `dazzlecmd-lib` pin**: `>=0.2.0` → `>=0.3.0`. The alias package's pin advances accordingly.

### Tests

- `tests/test_default_meta_commands.py::TestRenderList` — 6 new tests for the parity surfaces: backward-compat flat output (no engine), `--show canonical`, `--show alias`, `--show all` (with `[+]` markers), default mode (alias-preferred), sectioned multi-kit layout, virtual-kit section annotation.
- `tests/test_default_meta_commands.py::TestBuildListEntries` — 9 new tests covering the public data-layer API: canonical-only entries, alias entries from virtual kits, `has_aliases` marker, default-mode hiding of aliased canonicals, `--show all` returning both, canonical-kit filter, virtual-kit filter, entry dict shape stability.
- `tests/test_default_meta_commands.py::TestRenderTree` — 4 new tests for virtual-kit branches: `[virtual]` marker + `-> canonical` arrows, alias count in summary footer, regression guard for no virtual kits (no spurious "0 alias(es)" footer), `--kit <vk_name>` filter parity-limitation note (matches dazzlecmd's `_cmd_tree` early short-circuit; improving is a separate enhancement).
- Total: 967 passed, 13 skipped (up from 947 in v0.7.30).
- Human checklist: `tests/checklists/v0.7.31__Tier1B__library-render-list-parity.md`.

### Verification

Live-verified post-port that library consumers still work:

- `amdead list` (uses amdead's `_amdead_list_handler` override) — unchanged behavior.
- `amdead tree` — uses library `render_tree`; `[shadowed]` marker preserved.
- `amdead info setup` — uses library `render_info`; shadow-status block preserved.

### Refs

- Refs #50 (Phase 4e retrospective; Tier 1 commit 3 of master plan).
- Refs #30 (Phase 4 epic; Tier 1 of master closeout plan).
- Refs #27 (dazzlecmd-lib package — new public API `build_list_entries`).


## [0.7.30] - 2026-05-06

Phase 4e closeout, Tier 1 commit 1. Closes issue #56: the spurious reserved-command warning that fired on every invocation when an aggregator deliberately overrode a library meta-command (e.g. amdead's `core:setup` plus `engine.meta_registry.override("setup", ...)`) is now suppressed for acknowledged overrides. The warning still fires for unintended conflicts, so the original diagnostic value is preserved.

Surfaced during sysdiagnose adoption. The override IS the acknowledgment that the aggregator knows about the shadow and is deliberately chaining the library default — the library was warning on the very pattern it provides as the supported escape hatch.

Approach (per issue #56 design discussion): suppress only when the shadow has been acknowledged via `override()`, and ship two new discoverability surfaces alongside the suppression so shadow state remains visible without a noisy per-invocation warning. Library mechanism is a new `MetaCommandRegistry.user_overrides()` API that distinguishes deliberate-shadow registrations from library defaults; `build_tool_subparsers` now accepts an `exempt_from_warning` set which the engine populates from that API. Downstream library consumers can pass their own exempt set if they need finer control.

### Added

- **`MetaCommandRegistry.user_overrides()`** — returns a frozenset of meta-command names that were registered via `override()` (vs the library defaults installed by `register()`). Library-side mechanism for distinguishing "deliberate shadow acknowledgment" from "unintended name collision."

- **`build_tool_subparsers(..., exempt_from_warning=...)`** kwarg — optional set of names exempt from the conflict warning. The engine passes `meta_registry.user_overrides()` so deliberately-overridden conflicts don't fire the warning on every invocation. Names in the exempt set still skip parser registration (the meta-command's parser still wins); only the warning is suppressed.

- **Shadow-status block in `info`** (library `render_info` and dazzlecmd `_cmd_info`) — when a name is registered both as a library default meta-command AND as an aggregator tool, `info` surfaces both registrations and the override status. If the aggregator overrode the handler, the user sees the chain-the-default acknowledgment; if not, the user sees the FQCN dispatch path as the unblocked alternative. Lives in the library so any consumer (amdead, wtf-windows, sysdiagnose, ...) gets the surface "for free" without needing to override `info`.

- **`[shadowed]` marker in `tree`** (library `render_tree` and dazzlecmd `_cmd_tree`) — tools whose short name is reserved by a meta-command are now flagged in tree output. The inventory still shows them; the dispatch state is flagged. Same library-resident pattern as the `info` surface.

### Fixed

- **Issue #56**: amdead's `core:setup` tool plus `engine.meta_registry.override("setup", handler=...)` no longer produces `Warning: Tool 'setup' conflicts with reserved command, skipping` on every invocation. The warning fires only when the conflict is unintended (no override registered) — the original diagnostic value is preserved.

### Refs

- Closes #56 (warning suppression + discoverability replacements)
- Refs #50 (Phase 4e retrospective; Tier 1 commit 1)
- Refs #30 (Phase 4 epic; Tier 1 of master closeout plan)

### Tests

- `tests/test_meta_command_registry.py::TestOverride` — 4 new tests for `user_overrides()` tracking.
- `tests/test_cli_helpers.py::TestBuildToolSubparsers` — 4 new tests for `exempt_from_warning` behavior.
- `tests/test_default_meta_commands.py::TestRenderInfo` — 3 new tests for the library-side shadow-status block (no-override case, override-acknowledged case, regression guard for non-shadowed tools).
- `tests/test_default_meta_commands.py::TestRenderTree` — 2 new tests for the library-side `[shadowed]` marker.
- Human checklist: `tests/checklists/v0.7.30__Tier1A__issue-56-shadow-warning-and-discoverability.md`.
- Total: 947 passed, 13 skipped.


## [0.7.29] - 2026-05-06

Phase 4e closeout housekeeping. Test infrastructure fixes, backfill of the v0.7.25 test checklist that should have shipped with the FQCN data model refactor, and new automated coverage for `show_empty_virtual_kits`. No production-code behavior change.

This commit is part of the broader 0.7.x closeout effort tracked by the master plan and the #30 epic comment summarizing dependency-ordered tier sequencing for the remaining Phase 4 / Phase 4e tail / Phase 3.5 / Phase 5 work.

**Note on testing**: local `pytest -q --ignore=projects` is green (934 passed, 13 skipped). The tester agent has NOT been re-run against the patched test files or fixed v0.7.25 checklist text — the prior sweep was on the unfixed state. Re-run tester before tagging the next release that depends on these tests.

### Added

- **`tests/checklists/v0.7.25__Phase4e_C1__fqcn-data-model-refactor.md`** — backfill checklist for the v0.7.25 FQCN data model refactor (~910 LOC / 9 files / API surface change). Covers FQCNIndex three-index split (canonical / alias / shortcut), `ResolutionContext` returns, rule 9b enforcement, `engine.find_project()` alias-aware behavior, `shortcut_candidates` O(1) correctness, `.fqcn_index` removal regression, CLI integration sanity. 5-test high-value-verification section + 7 detailed sections + cross-shell commands + tester guidance for temp-copy isolation. Closes one of three blockers on Phase 4e clean close (master-plan item 4e-T6).

- **Tester sweep results** in `tests/checklists/results/` for v0.7.25/26/27/28 — SHIP verdict on all four (zero genuine regressions).

- **`TestShowEmptyVirtualKitsConfig`** in `tests/test_cli_list_sections.py` — three new tests covering the `show_empty_virtual_kits` config option: default behavior renders empty virtual-kit sections; `false` suppresses them; `true` (explicit) matches default. Closes the automated-coverage gap surfaced by the v0.7.28 tester sweep.

- **Preserved one-off test artifacts** in `tests/one-offs/`: `test_dz_env_vars.py` (v0.7.27 env-var injection investigation), `test_fixpath_dir_search.py`, `test_fixpath_progressive.py`, `fix_sesslog_timestamps.py`. Per project rule, one-offs are kept for reference; not part of CI regression.

### Fixed

- **Test isolation gap (`DAZZLECMD_CONFIG` env var leak)** — five tests in `test_engine_meta_registry.py::TestConfigDir` and `test_user_overrides_per_aggregator.py::TestEngineConfiguresOverrideRoot` were not clearing the `DAZZLECMD_CONFIG` env var before constructing engines with explicit `config_dir=`. The env var correctly takes precedence in production code, but tests assumed it was unset. Result: the 5 tests passed in the default-no-env-var case but failed when the test runner's parent shell had `DAZZLECMD_CONFIG` set. Fix: `monkeypatch.delenv("DAZZLECMD_CONFIG", raising=False)` added to each affected test. Pre-existing gap (not a v0.7.25-28 regression); surfaced by the tester sweep on 2026-04-29.

- **v0.7.25 checklist text defects** (in the new checklist filed by this commit) — Section 3.1 referenced a non-existent `TestInsertCanonical` class; corrected to `TestInsertAlias::test_alias_shadowing_canonical_raises_9b` which exercises rule 9b in both directions. Section 7.2 had wrong `dz kit favorite` syntax (one-arg form); corrected to the actual two-argument interface (`<short> <fqcn>`) with both canonical-target and alias-target examples.

### Refs

- Refs #50 (Phase 4e retrospective) — backfills the v0.7.25 test checklist (one of 3 close blockers for #50; the others are 4e-T2 `dz kit favorite --migrate-stale` interactive subcommand and 4e-T1 wtf-windows upstream PR for `_fqcn ==` patterns)
- Refs #30 (Phase 4 epic) — Tier 0 housekeeping work per the closeout master plan

### Test docs (refs for the work that hasn't been re-tested yet)

- `tests/checklists/v0.7.25__Phase4e_C1__fqcn-data-model-refactor.md` (the new checklist; tester agent run against this fixed text is pending)
- `tests/checklists/results/v0.7.25__...` and three sibling result files (the prior tester sweep results; were against the unfixed state of v0.7.25 checklist + pre-isolation-fix tests)


## [0.7.28] - 2026-04-25

Phase 4e v0.7.28: sectioned `dz list` (Option O) — virtual kits render adjacent to their canonical parent, with section headers replacing the flat-table layout that v0.7.27 shipped.

Display revision driven by `2026-04-20__07-13-15__dev-workflow-process_virtual-kit-display-format-headered-sections.md`. v0.7.27's flat-table layout (Option I) is preserved as the single-section fallback for `--kit <kit>` and similar narrowing filters.

### Added

- **Sectioned `dz list` layout (Option O)**: tools render under section headers (`<kit_path>:`); virtual kits get a `(virtual kit '<name>')` annotation. Two columns per section (name + description); the kit info lives in the header so there's no per-row Kit column inside sections. One blank line between sections.

- **Virtual-kit sections render adjacent to their canonical parent**. `dazzletools:claude:` sits immediately after `dazzletools:`, not alphabetically at the bottom — visually preserves the parent-extension relationship.

- **`[+]` marker on aliased canonicals in `--show all`**: distinct from the existing `[*]` collision marker. Footer note explains both when present.

- **Single-section fallback to flat layout**: when `--kit <kit>`, `--show alias` (with one virtual kit), or any filter narrows to one section, render the v0.7.27-style flat table (Name + Kit + Description columns). Headers only add value when there are ≥2 sections; this gives `--canonical`-pinned scripts a familiar shape.

- **`show_empty_virtual_kits` config key** (default `true`): when true, virtual kits with zero active aliases (target canonicals disabled) still render an empty section header so users know the virtual kit exists. Set false to suppress.

- **Qualified-alias dispatch**: `dz dazzletools:claude:cleanup` (the qualified form shown in sectioned `dz list` headers) now resolves to the same canonical project as `dz claude:cleanup`. New `resolution_kind = "qualified_alias"` in `ResolutionContext`. The resolver tries this path AFTER canonical-direct-hit, alias-direct-hit, and kit-shortcut have all missed: parses input as `<canonical_kit_path>:<vk_name>:<alias_short>` and looks up the alias. Aligns dispatch with display — every form a user sees in the list output is invocable.

- **`dz info` provenance banner for qualified alias**: shows both the qualified form and the underlying short-alias path (`(qualified alias 'X' = 'Y' -> canonical 'Z')`).

- 14 new pytest modules in `tests/test_cli_list_sections.py` covering: multi-section default/canonical/alias/all rendering, single-section fallback, `[+]` marker logic, virtual-kit header annotation, footer count strings per mode, and section adjacency ordering.

- 14 new pytest modules in `tests/test_path_form_convergence.py` encoding the **convergence invariant**: canonical FQCN, canonical short, alias FQCN, alias short, and qualified alias all resolve to the same canonical project. Plus negative tests for prefix mismatches and direct-hit precedence over qualified resolution.

### Changed

- **Default `dz list` output is sectioned, not flat.** Scripts pinned to `--show canonical` are unaffected; they still see canonical kits but in sectioned form. Scripts that need v0.7.27-style flat output can use `--show canonical -k <kit>` to force single-section flat.

- `_build_list_entries` adds `section_key`, `section_kind`, `section_vk_name`, and `has_aliases` fields to entry dicts. Internal API; no external callers.

### Fixed

- **Virtual-kit warning batching**: `_apply_virtual_kits` now collects alias-insert failures per virtual kit and emits ONE consolidated diagnostic instead of N near-identical lines. Common case (target canonical kit disabled): single `Warning: virtual kit 'X': N alias(es) unavailable -- target kit 'Y' disabled. ...` line that names the cause and remediation. Mixed-cause failures fall back to a capped list (3 + "+N more"). `silenced_hints.kits` lets users opt out per virtual kit. Reduced verbosity from ~1600 chars per `dz` invocation to ~230 chars when a kit is disabled.

### Deferred

- **Library-side `render_list` parity** with the new sectioned layout. v0.7.27 deferred this; v0.7.28 continues the deferral. Library's `render_list` still produces a flat table. No third-party adopter is using it today (wtf-windows has its own custom render path); will fold in when demand emerges.

## [0.7.27] - 2026-04-20

Phase 4e Commits 3+4 (folded): alias-blindness audit, rule 7c relaxation, `dz list --show` enum + Option I default rendering, virtual-kit filter on `-k`, `dz kit list` drill-in with alias columns, `dz tree` virtual-kit branch with `->` arrows, `dz kit status` "alias(es)" label, runtime env-var injection, grouped stale-favorite warning.

Virtual kits are now FIRST-CLASS kits — they contribute to short-name resolution (rule 7c), display as distinct branches in the tree, surface in `dz list` by default (alias-preferred view), and inject canonical identity as env vars for tools to use in cache/state keys.

### Added

- **Rule 7c relaxation: alias shorts populate `short_index`** alongside canonical shorts. A virtual kit declaring `claude:cleanup` with alias short `cleanup` makes `dz cleanup` resolve to the canonical target via the existing short-name precedence mechanism. Users no longer need separate `favorites` to get short-name access to aliased tools — the virtual kit delivers it. Collisions (alias short vs canonical short, or alias-short-vs-alias-short across virtual kits) resolve by precedence + notification, same as canonical collisions.

- **`engine.find_project(name)`**: alias-aware lookup helper is now the canonical lookup path. Replaces raw `[p for p in projects if p.get("_fqcn") == name]` comparisons everywhere in the codebase. `_cmd_info`, `render_info`, `setup_handler` all route through it. `engine` parameter is now REQUIRED on these entry points (the legacy alias-blind fallback was tech debt that's been removed — see commit message).

- **`dz list --show {default,canonical,alias,all}`**: explicit content selector. `default` (alias-preferred) hides canonicals that have aliases; `canonical` is script-stable legacy view; `alias` shows only virtual-kit aliases; `all` shows both. Config key `list_view` overrides the default per-user.

- **Option I default rendering for aliases**: alias short in Name column, `virtual-kit:canonical-kit` hierarchy in Kit column. The shortening that virtual kits promise is now visible at a glance. Short-name collisions marked `[*]` as before (now includes alias shorts per rule 7c).

- **`dz list -k <virtual-kit>`**: surfaces the virtual kit's aliases (previously returned "No tools found" because `render_list` was alias-blind). Canonical-kit filter behavior preserved.

- **`dz kit list <virtual-kit>` drill-in**: new columns for virtual kits — Alias FQCN, `-> Canonical`, Description. Users can see every alias the virtual kit declares and what canonical tool it maps to.

- **`dz tree` virtual-kit branch**: virtual kits render as separate top-level branches marked `[virtual, ...]` with `->` arrows to canonical FQCNs. Footer counts aliases separately from tools: "20 tools across 3 kit(s), 4 alias(es) in 1 virtual kit(s)".

- **`dz kit status` alias terminology**: virtual kits report "N alias(es)" instead of "N tool(s)" — resolves the R3b double-counting confusion.

- **`DZ_CANONICAL_FQCN` / `DZ_INVOKED_FQCN` env vars**: injected into the tool's environment during dispatch. `DZ_CANONICAL_FQCN` is the canonical identity (stable across invocation paths); `DZ_INVOKED_FQCN` is what the user typed (alias FQCN, short name, canonical FQCN, or kit-qualified shortcut). Tools writing persistent state (caches, logs, checkpoints) MUST key on `DZ_CANONICAL_FQCN` to avoid divergent state across invocation surfaces. Parent-process env is restored after dispatch.

- **Grouped stale-favorite warning**: on `discover()`, the engine scans user favorites and emits ONE stderr warning listing up to 3 stale FQCNs (plus a "+N more" summary if >3). Respects `silenced_hints` and `DZ_QUIET`. Remediation: manual via `dz kit favorite --remove <short>` or re-pointing.

### Fixed

- `tests/test_library.py::test_library_version` no longer pins a hardcoded `"0.1.0"` string. The brittle assertion failed every release bump and blocked the v0.7.27 pre-push hook. Now asserts the export is a non-empty semver-ish `major.minor[.patch]` string.

- `tests/test_docker_integration.py::docker_image` fixture skips cleanly when the docker daemon is unreachable (Docker Desktop stopped on Windows; missing socket on Linux). Previously the fixture only checked the docker CLI binary and then errored on `docker build` when the daemon was down — which the pre-push hook treats as failure. The fixture now runs `docker info` first and skips on daemon-connectivity errors, with a fallback skip path if the daemon goes down between info and build.

### Changed

- **`render_info` / `setup_handler` signatures now require `engine`** as a positional arg (was optional). Library consumers building their own dispatchers must pass engine context. The legacy alias-blind path has been removed — it was tech debt that silently bypassed virtual-kit resolution.

- **`FQCNIndex.insert_alias` also populates `short_index`** with the alias short, pointing at the canonical FQCN. Short-name dispatch works the same as for canonicals.

### Deferred to follow-ups

- **`dz kit favorite --migrate-stale` subcommand** (interactive remapping). The detection + warning ship in this release; the interactive tooling can land separately if demand emerges.
- **wtf-windows upstream PR** for its own `_fqcn ==` patterns — deferred per user's "this is still experimental work" direction; revisit once v0.7.27 proves stable in-tree.

### Design references

- `2026-04-19__23-44-05__DISCUSS_Rnd5_FINAL_ASSESSMENT_virtual-kits-graduation-fqcn-semantics.md`
- `2026-04-20__04-53-20__dev-workflow-process_virtual-kit-display-visibility-modes.md`
- `notes/cli/2026-04-20__04-39-32__both_virtual-kit-alias-discoverability-gap.md`

## [0.7.26] - 2026-04-20

Phase 4e Commit 2: virtual-kit loading, `_apply_virtual_kits`, and cross-aggregator Option A.

Ships the first real virtual kit (`kits/claude.kit.json`): four `dazzletools:claude-*` tools become dispatchable as `claude:cleanup`, `claude:session-metadata`, `claude:sesslog-datefix`, `claude:view`. Canonical FQCNs continue to work; short names continue to work; aliases do NOT pollute short-name resolution (rule 7c).

### Added

- **Loader virtual-kit detection** (`loader.py`): registry pointers with `"virtual": true` carry through as virtual kits. The loader skips `_load_in_repo_kit_manifest` for virtual kits so a virtual kit accidentally named after a canonical kit can no longer inherit that canonical's tool list.

- **`AggregatorEngine._apply_virtual_kits(virtual_kits)`**: second pass run after `_build_fqcn_index` has populated `canonical_index`. For each active virtual kit, iterates its `tools` list, derives the alias short from `name_rewrite` (defaulting to the canonical FQCN's last segment when absent), constructs the alias FQCN as `<vk_name>:<alias_short>`, and inserts via `FQCNIndex.insert_alias`. Emits structured stderr warnings for §9a (virtual kit name shadows canonical kit name) and §9b (alias FQCN collides with canonical FQCN). §9a is a warning, not an error — the migration use case (replace a canonical kit with a virtual overlay) is legitimate.

- **Cross-aggregator Option A** (`_discover_aggregator` + `_recurse_into_nested`): virtual kits defined inside a nested aggregator are collected during the recursive discovery walk, rewritten with the parent FQCN prefix via `_rewrite_virtual_kit`, and applied at the root after canonical discovery completes. Fixes the silent-failure gap confirmed by the R3b validation experiment (a virtual kit inside `projects/wtf/kits/` was invisible from root). Example: wtf-windows shipping `virtual-claude.kit.json` with `name: "claude"` and `tools: ["core:locked"]` is now rewritten to `name: "wtf:claude"` and `tools: ["wtf:core:locked"]` when embedded under dazzlecmd — alias FQCN `wtf:claude:<short>`. Rewritten nested virtuals are also merged into `engine.kits` and `engine.active_kits` so `dz kit list` and `dz kit status` surface them (caught by the v0.7.26 tester-agent checklist run; regression guarded by `TestCrossAggregatorOptionA.test_nested_virtual_kit_visible_in_kits_list`).

- **`AggregatorEngine._rewrite_virtual_kit(vk, kit_prefix)`**: pure helper that prefixes a virtual-kit manifest's `name`, `tools`, and `name_rewrite` keys with `kit_prefix`. At depth 0 (`kit_prefix is None`) it's a no-op shallow copy. At nested levels, rewrites into the root namespace for safe application.

- **`kits/claude.kit.json`**: first real virtual kit ships with dazzlecmd. Aliases the four `dazzletools:claude-*` tools under the `claude:*` namespace.

- **`tests/test_virtual_kits.py`** (13 tests): loader detection (including skip-in-repo-manifest for same-name case), single-level alias installation, `name_rewrite` partial/defaulting, short_index isolation (rule 7c), inactive virtual kits contributing no aliases, cross-aggregator discovery + rewrite + dispatch, disabling a nested aggregator disables its virtual kits, rule 9a warning emission, rule 9b alias shadowing rejected even under 9a, end-to-end dispatch via `resolve_command` and `find_project`.

### Changed

- **`_discover_aggregator` return signature**: now returns `(projects, virtual_kit_manifests)` tuple. Virtual kits are collected during the recursive walk and rewritten by the current frame before returning. Internal API; no external callers.

- **`AggregatorEngine.discover()`**: assigns `self.all_virtual_kits` and calls `self._apply_virtual_kits(...)` after `_build_fqcn_index`.

### Known gaps addressed in later commits

- `dz info claude:cleanup` still reports "not found" because `_cmd_info` uses a raw `_fqcn ==` comparison that is alias-blind. Fixed in Commit 3 (v0.7.27) via the alias-blindness audit and migration to `engine.find_project`.
- `dz tree` does not yet render the virtual `[virtual]` branch or `->` arrows for aliases. Fixed in Commit 4 (v0.7.28).
- `DZ_CANONICAL_FQCN` / `DZ_INVOKED_FQCN` env vars are not yet injected during tool dispatch. Fixed in Commit 4.

### Design references

- `2026-04-19__23-44-05__DISCUSS_Rnd5_FINAL_ASSESSMENT_virtual-kits-graduation-fqcn-semantics.md`
- `2026-04-19__23-25-00__experiment-r3b-validation-findings.md`
- `2026-04-19__23-05-00__DISCUSS_Rnd3b_Gemini25_adversarial-critique.md` (cross-aggregator Option A spec)

## [0.7.25] - 2026-04-20

Phase 4e Commit 1: FQCN data model refactor for virtual kits.

Foundational change preparing the aggregator engine for virtual-kit aliases (Commit 2) and the alias-blindness audit (Commit 3). Ships the data structures, collision invariants, and resolve API; virtual-kit loading, env-var injection, and display-UX polish arrive in later commits. See the locked Phase 4e spec for the full plan.

### Added

- **`ResolutionContext` dataclass** (`dazzlecmd_lib.resolution_context`): Returned alongside the project from `FQCNIndex.resolve` and `AggregatorEngine.find_project`. Records how a name resolved — `resolution_kind` is a single Literal (`canonical`, `alias`, `kit_shortcut`, `favorite`, `precedence`) instead of parallel booleans, making impossible states unrepresentable. Optional `alias_fqcn` surfaces the traversed alias when resolution went through a virtual kit (or a favorite that pointed at an alias).

- **`FQCNIndex.insert_alias(alias_fqcn, canonical_fqcn, source=None)`**: Registers an alias pointer. Enforces §9b (alias FQCN must not equal any canonical FQCN — a virtual kit cannot shadow a real tool), idempotent for same-target re-registration, and fails loud on different-target conflicts (first virtual kit wins). `KeyError` when the target canonical does not exist (dangling pointer).

- **`FQCNIndex.insert_canonical(project)`**: New name for the old `insert(project)`. Enforces §9b mirror (canonical cannot be added after an alias claimed the same FQCN) and populates the precomputed `shortcut_candidates` index.

- **`FQCNIndex.shortcut_candidates`**: Precomputed `{(kit_first, tool_last): [canonical_fqcn, ...]}` index replacing the previous O(n) list comprehension in kit-qualified shortcut resolution (e.g., `wtf:locked` -> `wtf:core:locked`). O(1) lookup; ambiguity resolved by stable alphabetical sort on insert.

- **`FQCNIndex.alias_index`**: New `{alias_fqcn: canonical_fqcn}` store for virtual-kit aliases. Resolution consults aliases after canonical direct-hit and before kit-qualified shortcut fallback. Aliases do NOT populate `short_index` — their purpose is to provide prettier FQCNs, not to create new short-name competition (users who want short-name shortcuts should use `favorites`, not virtual kits).

- **`AggregatorEngine.find_project(name)`**: Alias-aware canonical lookup helper. Intended replacement for raw `[p for p in projects if p["_fqcn"] == name]` comparisons (those are alias-blind). Commit 3 will migrate remaining call sites.

### Changed

- **`FQCNIndex.resolve(name, ...)`** signature: returns `(project, ResolutionContext | None)` instead of `(project, str | None)`. Breaking change authorized during the 0.7.x rearchitecture. The notification string is now `context.notification`. `engine.run()` dispatch path and all meta-command call sites updated to access `.notification` explicitly.

- **`FQCNIndex.fqcn_index` attribute removed**: callers should use `FQCNIndex.canonical_index` for the canonical `{fqcn: project}` store. The `fqcn_index` name previously served as both the attribute AND the outer class name, which made code hard to read once aliases were introduced.

### Design references

- `2026-04-19__23-44-05__DISCUSS_Rnd5_FINAL_ASSESSMENT_virtual-kits-graduation-fqcn-semantics.md`
- `2026-04-19__23-25-00__experiment-r3b-validation-findings.md`
- `2026-04-20__01-12-34__full-postmortem_collaborate4-virtual-kits-design-session.md`

## [0.7.24] - 2026-04-18

### Added

- **`AggregatorEngine(project_root=...)` kwarg**. Installed aggregators (e.g. wtf-windows via pip) can now pass an explicit project-root hint at construction. The library's default `find_project_root` walks from its own `__file__` which resolves to `site-packages/dazzlecmd_lib/` for pip-installed consumers — useless for locating a consumer's own tools/kits directories. The kwarg precedence is: explicit construction hint -> `engine.discover(project_root=)` override -> `find_project_root()` walk.

### Fixed

- **Python runner package-mode dispatch** (`make_python_runner` in `registry.py`): tools whose directory contains `__init__.py` (package layout, e.g. wtf-windows' `locked` and `restarted`) now dispatch with the PARENT of `tool_dir` on `sys.path` and import as `<package_name>.<script_stem>`. Relative imports inside the tool's own module (e.g. `from .channels import ...`) resolve correctly. Bug surfaced during wtf-windows Phase 2 adoption; previous behavior placed `tool_dir` directly on `sys.path` which imported the script as a flat top-level module and broke its relative imports with "attempted relative import with no known parent package".

- **`dz kit status` shows correct import name for embedded sub-kits** (#45). Previously showed wtf's inner `"core"` kit name (from wtf's `kits/core.kit.json`) instead of the import name `"wtf"` (from `kits/wtf.kit.json` filename). `_cmd_kit_status` now prefers `kit["_kit_name"]` (set from the registry pointer's filename) over `kit["name"]` (set from the in-repo manifest). Affects display only; FQCN dispatch was always correct.

### Changed

- **`kits/wtf.kit.json`**: removed temporary `_override_tools_dir`, `_override_manifest`, and `_override_note` fields. wtf-windows' own `kits/core.kit.json` (shipped in wtf v0.1.4-alpha and earlier) already declares `tools_dir: "tools"` and `manifest: ".wtf.json"`; dazzlecmd's loader picks those up directly via `_load_in_repo_kit_manifest`. Phase 3 coordination of the wtf-windows adoption track.

- **`projects/wtf` submodule bumped**: `dabb30b` (v0.1.1-alpha) -> `25af04e` (v0.1.4-alpha). The new wtf commit adopts `dazzlecmd-lib` as its engine (Phase 2 of the Option C wtf-windows-adoption work). Validates "dazzlecmd is an instance, not the root" with a real third-party production adopter.

### Tests

- 2 regression tests in `tests/test_registry.py::TestPythonPackageModeRelativeImports` covering the package-mode + flat-module dispatch paths.
- 2 regression tests in `tests/test_cli_kit.py::TestKitStatusDisplay` covering the `_kit_name` preference and back-compat when `_kit_name` is absent.
- Full suite: 844 passing, 6 platform-skipped (up from 840 in v0.7.23).

### Notes

- **Phase 4d Phase 2 + Phase 3 both land here.** Phase 2 shipped in the wtf-windows repo (`25af04e`, v0.1.4-alpha) by deleting wtf's duplicated `loader.py` and rewriting `cli.py` to use `AggregatorEngine` + `MetaCommandRegistry`. Phase 3 (this dazzlecmd commit) bumps the submodule pointer and removes the temporary overrides.

- **wtf-windows is the first third-party production adopter of `dazzlecmd-lib`**. Second is sysdiagnose-public (tracked as #46, not yet started). Third will likely require the namespace-flexibility feature tracked as #47.

- **Library docs** (testing strategy, dev-workflow catalogs, human-checklist template) ship alongside in this commit.

- **Tester-agent sweep** for this version reported 15 PASS, 1 REVIEW (design call on standalone vs embedded FQCN display — Option A chosen: each aggregator shows its own perspective), 0 FAIL. Ship recommendation.

Closes #28 (wtf-windows full integration experiment -- Phase 2+3 delivers what this issue tracked) Closes #45 (dz kit status embedded sub-kit label fix) Refs #13 (recursive kit PoC -- subsumed by Option C completion; can close with this commit's adoption validation) Refs #27 (dazzlecmd-lib adoption -- production third-party adopter shipping; remaining criteria: PyPI publish, tutorial README, example starter aggregator) Refs #30 (Phase 4 epic -- 4d Phase 2 + Phase 3 shipped; Phase 4e optional polish; 4d's polyglot validation still pending a real non-Python tool end-to-end) Refs #46 (sysdiagnose-public adoption -- blocked on this; now unblocked) Refs #47 (namespace flexibility -- informed by sysdiagnose adoption; design-stage)

Design: `2026-04-18__17-15-54__dev-workflow-process_option-c-library-helper-surface-design.md`

## [0.7.23] - 2026-04-18

### Added

- **`MetaCommandRegistry`** — per-engine meta-command registry in `dazzlecmd_lib.meta_command_registry`. Replaces the fixed callback signature (`parser_builder=`, `meta_dispatcher=`, etc.) as the blessed API for downstream aggregators. Mirrors the `RunnerRegistry` pattern already shipped for runtime types. Methods: `register`, `override`, `unregister`, `registered`, `resolve`, `build_parsers`, `dispatch`, `lock`/`unlock`/`is_locked`, `clear`. `override` accepts keyword-only `parser=`/`handler=` for partial replacement (keep stock parser, replace only the handler; and vice versa).
- **`dazzlecmd_lib.default_meta_commands`** — stock `list`, `info`, `kit` (with `kit_list`/`kit_status` subcommands), `version`, `tree`, and `setup` as importable `parser_factory` + `handler` + `render_*()` public functions. Aggregators can call `render_info()` from their own handler to append domain-specific fields (compose rather than replace). `register_all(registry)` bulk-registers all defaults; `register_selected( registry, include=[...])` is the opt-in helper for minimal aggregators.
- **`dazzlecmd_lib.cli_helpers`** — shared argparse scaffolding helpers for aggregators using the `parser_builder=` escape-hatch path. Functions: `build_tool_subparsers(subparsers, projects, reserved)`, `derive_reserved_from_registry(registry, extras)`, `add_version_flag`, `default_epilog_for(app_name, tool_count, kit_count)`.
- **`AggregatorEngine` gains**:
  - `meta_registry: MetaCommandRegistry` attribute (per-engine)
  - `include_default_meta_commands: bool = True` kwarg — auto-register library defaults at construction (opt out for minimal aggregators)
  - `extra_reserved_commands: set | None = None` kwarg — reserve names beyond what the registry contains (e.g., planned future commands)
  - `config_dir: str | Path | None = None` kwarg — per-aggregator config directory (defaults to `~/.<command>`, e.g., `~/.wtf` for wtf)
  - `epilog_builder` instance attribute — callable `(projects) -> str` for custom help epilog rendering
  - `reserved_commands` property now derives dynamically from `meta_registry.registered() | extra_reserved_commands`
  - Internal `_run_registry()` path: when `parser_builder` is None, the engine builds the parser from the registry + tool subparsers and dispatches via `meta_registry.dispatch()`. Registry locks during dispatch to prevent mid-run mutations.
  - Internal `_run_escape_hatch()` path: preserved for backward compat when `parser_builder` is explicitly passed (dazzlecmd's own `cli.py` continues to use this path).
- **Per-aggregator user-override paths**. `user_overrides.set_override_root(path)` module-level setter that the engine calls at construction. Each aggregator now reads/writes overrides under its own config_dir (e.g. `~/.wtf/overrides/setup/<fqcn>.json`). The `DAZZLECMD_OVERRIDES_DIR` env var still takes precedence (test-isolation pattern preserved).
- **Per-aggregator ConfigManager paths**. `ConfigManager(config_dir=...)` kwarg. Previously hardcoded `~/.dazzlecmd/config.json`; now defaults per-command via the engine's construction logic.
- **153 new tests** across four new test modules:
  - `tests/test_meta_command_registry.py` — 42 tests
  - `tests/test_default_meta_commands.py` — 56 tests
  - `tests/test_cli_helpers.py` — 19 tests
  - `tests/test_engine_meta_registry.py` — 27 tests
  - `tests/test_user_overrides_per_aggregator.py` — 9 tests

### Changed

- **`AggregatorEngine.reserved_commands`**: was a hardcoded set; now a dynamic property from `meta_registry.registered() | _extra_reserved`. Dazzlecmd's own `cli.py` uses its own `RESERVED_COMMANDS` constant (unchanged); no regression for dazzlecmd. The property now correctly reflects what's actually registered when aggregators customize the registry.
- **`ConfigManager.__init__()`**: accepts `config_dir=None` kwarg. When None, falls back to the legacy `~/.dazzlecmd/config.json` default.
- **`tests/conftest.py`**: adds an autouse `_reset_user_override_root` fixture to reset the module-level override root after each test (prevents cross-test pollution from engine construction).

### Notes

- **Backward compatibility**: dazzlecmd's own `cli.py` was NOT migrated to the registry pattern in this release. It continues to construct `AggregatorEngine` with `parser_builder=`, `meta_dispatcher=`, `tool_dispatcher=` callbacks (the escape-hatch path). The 840 full- suite test count (up from 687) reflects pure additions; zero regressions in existing behavior.
- **Migration for dazzlecmd's cli.py** remains future work (optional Phase 4e polish). Once migrated, the ~200 LOC of `_cmd_list`, `_cmd_kit_list`, `_cmd_version` etc. can delegate to library defaults.
- **Next**: Phase 2 — adopt dazzlecmd-lib in wtf-windows repo. wtf's `cli.py` rewritten to construct `AggregatorEngine` with registry-based customization; wtf's `loader.py` (392 LOC) deleted.

Refs #27 (dazzlecmd-lib adoption — primary API stabilized; wtf-windows adoption is the next production caller) Refs #30 (Phase 4 epic — MetaCommandRegistry is the Phase 4b library surface that enables Phase 4d polyglot aggregator ecosystem) Design: `2026-04-18__17-15-54__dev-workflow-process_option-c-library-helper-surface-design.md`

## [0.7.22] - 2026-04-18

### Added

- **User-override integration (Option B)**. `user_overrides.load_override()` (shipped v0.7.19 as groundwork) is now called at the top of `resolve_setup_block` and `resolve_runtime`. If a file exists at `~/.dazzlecmd/overrides/setup/<fqcn>.json` or `~/.dazzlecmd/overrides/runtime/<fqcn>.json`, it deep-merges OVER the manifest block BEFORE platform resolution, `_vars` substitution, and prefer iteration. Override wins on collision at every scope level; permissive scoping means override can introduce new subtype branches or prefer entries the manifest didn't declare. Override's `_vars` participate in the same scope chain lookup as manifest `_vars`, with override winning on matching keys. Missing override file = no change (fast path preserved for unchanged manifests).
- **Cross-layer isolation**: `overrides/setup/<fqcn>.json` only affects setup resolution; `overrides/runtime/<fqcn>.json` only affects runtime. Neither crosses the layer boundary. Manifest-top `_vars` (project-level) are unaffected by per-layer overrides.
- **Permissive scoping**: if an override declares `platforms.linux.gentoo.command` but the manifest has no `gentoo` subtype, deep-merge adds the new branch. Users can extend dispatch coverage for platforms / subtypes the kit author didn't declare, without waiting for an upstream PR.
- **17 new integration tests** in `tests/test_user_override_integration.py` covering: override file present/absent, override without FQCN skipped, permissive scoping (new subtype + new OS), `_vars` merge + override wins, unsupported schema version, malformed JSON, cross-layer isolation (setup doesn't affect runtime, runtime doesn't affect setup), runtime platform-branch addition, prefer-array replacement (deep-merge array semantics), dual-layer composition (both setup and runtime overridden).

### Changed

- `resolve_setup_block` and `resolve_runtime` now each call `load_override()` as a first step when the project has an `_fqcn`. The override merges over the manifest's layer-specific block before any other resolution logic. Projects without `_fqcn` skip the lookup (back-compat for any programmatic callers building project dicts without a kit context).

### Notes

- **Closes Phase 4b groundwork from v0.7.19**: `user_overrides.py` shipped as groundwork and has been sitting idle; this is the first production caller that exercises the full load -> merge -> resolve flow.
- **CLI override management** (`dz override set/clear/show/export`) remains deferred. Authors and advanced users can hand-edit override JSON files at `~/.dazzlecmd/overrides/<layer>/<fqcn>.json` today; a dedicated CLI will be revisited at the end of B+C work.
- **PR-back flow** (export user override as a unified diff for upstream contribution) stays in issue #40's scope.
- **Next**: Option C wtf-windows adoption experiment, attempted as one monolithic commit; library gaps discovered during C bundle with that commit (not pre-split).

Refs #30 (Phase 4 epic -- Option B closes the user_overrides.py groundwork from v0.7.19) Refs #27 (dazzlecmd-lib adoption -- wtf-windows experiment next as Option C) Refs #40 (multi-platform setup -- user-override integration is the groundwork for user-contributable configs + PR-back flow)

## [0.7.21] - 2026-04-18

### Added

- **Docker runtime type (Phase 4c.4)**. New `runtime.type: "docker"` dispatches tools via `docker run`. Manifest fields: `image` (required), `volumes`, `env`, `env_passthrough`, `docker_args`, `inner_runtime` (informational). Pre-flight `docker images -q <image>` check runs before dispatch; on miss, surfaces `Error: Docker image 'X' not found locally. Try: dz setup <fqcn>` with exit 1. Engine NEVER pulls or builds images -- the tool's declared `setup.command` is responsible. `make_docker_runner` in `dazzlecmd_lib.registry`. Closes the last Phase 4c runtime-type gap.
- **Conditional dispatch + `_vars` compose with Docker for free**: authors can declare `platforms.linux.image: "myimg:amd64"` vs `platforms.darwin.image: "myimg:arm64"`, OR `_vars: {tag: "1.0"}` + `image: "{{registry}}/{{tool}}:{{tag}}"`. The shared substrate established in v0.7.19/v0.7.20 handles both without Docker-specific code.
- **Docker-compatible engines work without code changes**: any CLI providing a docker-compatible binary (Docker, Podman via alias, Colima, Rancher Desktop, OrbStack, nerdctl) works. Engine abstraction via a dedicated `engine_cmd` field is deferred until demand emerges.
- **Synthetic Docker fixture at `tests/fixtures/docker_tool/`**: real Dockerfile + Python ENTRYPOINT + manifest using `_vars` + `env_passthrough`. Builds a ~84MB image (`dazzlecmd-test-docker-tool:v1`) on first test run. Integration test suite at `tests/test_docker_integration.py` (marked `@pytest.mark.docker_integration`, opt-in via skip-if-no-docker) creates the image, dispatches via the runner, asserts on a structured report the container emits. 8 tests cover image build, image substitution, runner-captures-output, env dict delivery, env_passthrough forwarding, passthrough-skips-missing-vars, container hostname isolation, exit code propagation.
- **`RunnerRegistry.reset()` classmethod + autouse conftest fixture** (Phase 4c.6). Reinstalls built-in factories after every test; drops any extension-registered types. Prevents test pollution when tests register custom runtime types. `docker_integration` pytest marker registered in `pyproject.toml` with auto-skip when `docker` binary is absent.
- **`dz setup` no-arg listing mode polish** (closes issue #33 listing-mode criterion). Detection now catches tools with ONLY `setup.platforms.*` declared (no top-level `setup.command`). Output sorted alphabetically by FQCN; dynamic column width (floor 20, ceiling 50 chars); missing notes show as `-`. 9 tests in `tests/test_cli_setup.py`.
- **`docs/guides/dz-setup.md`** -- new CLI reference file mirroring `dz-kit.md` / `dz-tree.md` pattern. Covers `dz setup` usage, platform resolution, `_vars` template integration, error cases, and the "what the engine will NOT do" boundary. Satisfies #33's docs criterion.
- **`docs/guides/manifests.md` Docker Tool section** -- schema, dispatch pattern, pre-flight check, conditional dispatch + `_vars` examples, docker-compatible engines note, NOT-supported list, reference fixture pointer.
- **43 new automated tests** (+ full suite 668 passing, 6 platform-skipped):
  - `test_docker_runner.py` (19) -- mocked argv construction, pre-flight, volumes, env, env_passthrough, docker_args, inner_runtime informational, exit code propagation, `_vars` substitution
  - `test_docker_integration.py` (8) -- real-Docker end-to-end
  - `test_cli_info.py` (+7) -- Docker field rendering in `--raw` and resolved views
  - `test_cli_setup.py` (+9) -- listing mode polish

### Changed

- `_cmd_setup` no-arg listing branch replaced with the polished version (sorted, dynamic column width, platforms-only tool detection).
- `_print_runtime_dispatch_fields` extended with Docker-specific rendering (Image, Volumes, Env, Env passthru, Docker args, Inner runtime).

### Notes

- Issue #30 (Phase 4 epic) advances: Phase 4c.4 complete; Phase 4c.6 (registry test isolation) complete. Phase 4c is now fully shipped.
- Issue #33 (dz setup) -- listing-mode and docs criteria closed; first-run detection stays deferred.
- Issue #22 (Per-tool runtime environment) -- already closed v0.7.20 Option B; Option A (`runtime.venv` shorthand) remains parked.
- Three new tracking issues filed for future phases:
  - #42 Test matrix / cross-environment testing substrate
  - #43 VM-based runtime type complementing Docker
  - #44 Kit sandbox: user-policy-driven container/VM isolation

Refs #30 (Phase 4c.4 + 4c.6 checkboxes flipped in epic) Refs #33 (listing mode + docs criteria closed) Refs #42 (test matrix -- future; docker substrate reusable) Refs #43 (VM runtime -- future; complements this work) Refs #44 (kit sandbox -- future; built on this substrate)

## [0.7.20] - 2026-04-17

### Added

- **Template variables (`_vars`) for setup and runtime manifests** (issue #41). Declare shared command fragments at manifest-top, block level (`setup._vars`, `runtime._vars`), platform level, or subtype level; reference via `{{name}}` in any string field. Four-tier scope chain with lexical declaration and dynamic lookup -- enables per-platform override of ingredients in composite variables without redefining the composite. Nested references supported (variable values may contain `{{...}}`) with cycle detection and max-depth guard. Unresolved references raise `UnresolvedTemplateVariableError` with a list of available vars at the error site. Syntax `{{var}}` (whitespace `{{ var }}` tolerated); identifier rule `[A-Za-z_][A-Za-z0-9_]*`; case-sensitive. Values are strings only in v1; list/dict deferred. Implementation in `dazzlecmd_lib.templates` (40 unit tests); integration in `resolve_setup_block` and `resolve_runtime` (18 integration tests). Substitution runs BEFORE prefer iteration so precondition checks (`shutil.which`, `os.path.isfile`) see substituted values.
- **Setup schema parity with runtime.** `setup.platforms` now accepts the same nested-dict shape that `runtime.platforms` established in v0.7.19: `setup.platforms.<os>.<subtype>` with `general` fallback. Resolution goes through the shared `platform_resolve.resolve_platform_block` helper so subtype chaining behaves identically between setup and runtime.
- **Flat-string shorthand retained** for simple single-command installs per OS: `"platforms": {"linux": "apt install foo"}` is normalized to `{"command": "apt install foo"}` at resolution time. Canonical dict form is required for subtypes and future features (multi-step, detect_when).
- **`setup._schema_version`** checked on load via `schema_version.check_schema_version`. Un-versioned blocks default to "1" for backwards compatibility.
- **New shared library module `setup_resolve.py`** exports `resolve_setup_block(project) -> dict | None`. Mirrors `resolve_runtime()` in registry.py. Issue #40's multi-platform setup work will extend this module with `steps`, `detect_when`, user-override loading, and PR-back without the cli layer changing shape.
- **Python runner honors `runtime.interpreter`** (closes 4b.3 of #22). When declared, `make_python_runner` dispatches via `subprocess.run([interpreter, script, *argv])` instead of importlib. Enables per-tool venvs (`.venv/Scripts/python.exe`), alternative Pythons (`python3.11`), and arbitrary python binaries. Relative interpreter paths with a separator resolve against the tool directory; bare names rely on subprocess PATH lookup; env-var-prefixed paths (`$VAR`, `%VAR%`) pass through unchanged. `pass_through: true` preserved as legacy path.
- **Synthetic venv stress-test fixture** at `tests/fixtures/venv_exercise/` with 7 heavy real deps (numpy, pandas, requests, rich, pyyaml, click, pydantic). End-to-end integration test in `tests/test_venv_integration.py` creates the venv, runs setup, dispatches via the venv interpreter, asserts all imports pass and that the reported interpreter is the venv (not the test runner's). Marked `@pytest.mark.venv_integration`.
- **Documentation**: `docs/guides/manifests.md` Setup section rewritten to cover both flat-string and nested-dict forms, resolution order, subtype rules, and the venv-per-tool pattern.
- 102 new automated tests (25 in `test_setup_resolve.py`, 15 in `test_python_runner_interpreter.py`, 4 in `test_venv_integration.py`, 40 in `test_templates.py`, 18 in `test_vars_integration.py`). Full suite: 616 passing, 6 platform-skipped (up from 514).

### Changed

- `_cmd_setup` now resolves via the shared `resolve_setup_block` preprocessor instead of the hand-rolled platform selection. Error messages include the current `<os>.<subtype>` tag and actionable hints for which manifest keys to add.
- The "Setup" section in `docs/guides/manifests.md` -- previously a one-line reference plus a "future #40" footnote -- now documents both schemas with worked examples and the venv-per-tool composition pattern. The "future" footnote for nested platforms is removed; #40 retains scope for multi-step, `detect_when` at setup, user-override loading, and PR-back.

### Notes

- **4b.3 (python runner `runtime.interpreter`, #22) closed.** Partial status carried from Phase 4b through Phase 4c; closed this release with the synthetic fixture validating the end-to-end flow. No in-repo tool currently requires venv isolation; the pattern is available for tools that need it.
- **Ecosystem pilot (real-tool venv migration) deferred.** `claude-sesslog-datefix` was considered but rejected -- its rare-use-fix UX doesn't benefit from forcing `dz setup` friction. Unblock condition: a tool authored with genuine version-isolation needs (ML tooling, Windows COM interop with pinned pywin32, etc.) should migrate first.
- **v0.7.19 human test checklist gaps fixed** (HV.2 setup instructions use manual kit-file creation rather than `dz kit add <path>` which only accepts git URLs; HV.5 replaced the non-existent `wtf` tool reference with `restarted` and `locked`).
- **No in-repo tool uses flat-string `setup.platforms.<os>` today** (verified: zero matches of `"setup":` across `projects/` and `kits/`). The shorthand form is retained for author ergonomics; zero-migration-risk promise for third-party kits arriving later.

Refs #30 (Phase 4 epic -- 4b.3 closed, setup parity unlocks #40 groundwork) Refs #22 (Python runner interpreter support -- closed) Refs #40 (shared setup_resolve.py scaffolds the multi-platform setup expansion) Refs #41 (template variables `_vars` base implementation -- extensions tracked for future)

## [0.7.19] - 2026-04-17

### Added

- **Conditional dispatch (`runtime.platforms` + `runtime.prefer`).** A single manifest can now express different dispatch behavior per platform and declare ordered alternatives when multiple implementations are viable. `runtime.platforms.<os>.<subtype>` overrides the base runtime for the matching host; `runtime.prefer` is an ordered array of dispatch alternatives whose first viable entry is selected. Inferred preconditions (interpreter on PATH, script file exists, npx/npm available) gate each prefer entry. Optional `detect_when` structured matchers provide explicit gating beyond the inferred preconditions.
- **Seven shared library modules in `dazzlecmd-lib`** forming the substrate for both runtime conditional dispatch (this release) and multi-platform setup (issue #40, forthcoming):
  - `platform_detect` -- `PlatformInfo` dataclass + cached `get_platform_info()` with optional `distro` dependency and stdlib fallback via `/etc/os-release`. Detects Linux/Windows/macOS/BSD/WSL with normalized OS names, subtypes, and architectures.
  - `conditions` -- `detect_when` evaluator with six leaf matchers (`file_exists`, `dir_exists`, `env_var`, `env_var_equals`, `command_available`, `uname_contains`) and two combinators (`all`, `any`). Env var values are never logged. `_`-prefixed keys are metadata.
  - `platform_resolve` -- `resolve_platform_block` (subtype fallback: `<subtype>` -> `general` -> base) and `deep_merge` (arrays REPLACED, not concatenated).
  - `resolution_trace` -- `ResolutionAttempt` + `ResolutionTrace` dataclasses used to build structured diagnostic output when a resolution fails.
  - `paths` -- cross-platform helpers: `resolve_relative_path` (generalizes the v0.7.18 shell_env fix), `ensure_windows_executable_suffix`, `translate_wsl_path`, `which_with_pathext`.
  - `schema_version` -- `CURRENT_SCHEMA_VERSION`, `SUPPORTED_SCHEMA_VERSIONS`, `get_schema_version`, `check_schema_version`. Un-versioned manifests default to version "1" for backwards compat.
  - `user_overrides` -- groundwork for per-user override files. Honors `DAZZLECMD_OVERRIDES_DIR`, defaults to `~/.dazzlecmd/overrides/`. FQCN `:` characters translate to `__` on disk. Runtime does not yet call `load_override` at dispatch time; issue #40 becomes the first production caller.
- **`resolve_runtime()` preprocessor in `registry.py`.** Every `RunnerRegistry.resolve()` call now passes the project through `resolve_runtime` first, applying platforms merge + prefer iteration before the runner factory sees the project. Runners stay dumb; the resolver owns the platform logic. `NoRuntimeResolutionError` surfaces a full trace (platform info, each tried entry, reason for each failure, actionable fix hint) when no entry matches.
- **`dz info --raw` and `dz info --platform SPEC` flags.**
  - Default `dz info <tool>` now shows the runtime resolved for the current host. Tools without `platforms`/`prefer` render identically to v0.7.18.
  - `--raw` shows the manifest as declared, with `platforms` and `prefer` arrays enumerated.
  - `--platform <spec>` (e.g., `linux.debian`, `windows`, `macos.macos14`) previews platform-level resolution for a host you may not own. `prefer` entries are enumerated without evaluating preconditions (since the current host's PATH isn't the target platform's).
- **213 new automated tests** across nine test files, organized by module concern. Full suite: 511 passing, 6 platform-skipped (up from 298).
- `docs/guides/manifests.md` gains a "Conditional Dispatch" section with worked examples for `platforms`, `prefer`, `detect_when`, and the three inspection modes.
- Human test checklist at `tests/checklists/v0.7.19__Phase4c-5__conditional-dispatch.md`.

### Changed

- `RunnerRegistry.resolve(project)` now runs `resolve_runtime(project)` first. Existing manifests without `platforms`/`prefer` take a fast path and behave identically; manifests that declare conditional dispatch receive the effective block.
- `_print_runtime_*` helpers extracted from `_cmd_info` for reuse across the three display modes.

### Notes

- Conditional dispatch ships as the first feature built on the shared library substrate. Issue #40 (multi-platform setup) is the second consumer and will reuse `platform_detect`, `conditions`, `platform_resolve`, `resolution_trace`, and `user_overrides` unchanged.
- The design explicitly preserves the "dumb dispatcher" principle: authors declare intent (what runs where, in what preference order); the engine faithfully evaluates and picks. No auto-detection beyond what the manifest declares.
- Schema version 1 is the current and only supported version. Future breaking changes to the manifest schema will bump the supported version set and land alongside a migration hook.
- All error messages preserve the "env var values are never logged" security invariant. Conditions checking secret-bearing env vars surface presence/absence only.

Refs #30 (Phase 4c polish), #40 (setup sibling uses the same shared modules)

## [0.7.18] - 2026-04-17

### Fixed
- **Bug 1 (shell runner cmd `shell_env` env propagation)**: cmd's `source_template` now prefixes invoked env scripts with `CALL`. Without it, chaining `env.cmd && tool.bat` with cmd's `&&` runs each as a separate child process and env vars set in `env.cmd` never reach `tool.bat`. This silently broke the advertised `dazzle_env.cmd` pattern. Change: one-line update to `SHELL_PROFILES["cmd"] ["source_template"]`.
- **Bug 2 (node runner TS-without-interpreter error ordering)**: the `.ts`-requires-explicit-interpreter check in `make_node_runner` now fires before the file-existence check. Previously, declaring a `.ts` `script_path` without an `interpreter` field would produce the generic "Script not found" error when the file didn't exist yet (common during tool authoring), instead of the actionable TypeScript-specific message.
- **Shell runner `shell_env.script` path resolution**: relative paths in `shell_env.script` now resolve against the tool directory (consistent with `runtime.script_path` semantics). Absolute paths and env-var-prefixed paths (`%USERPROFILE%`, `$HOME`) pass through unchanged so the shell handles expansion. Previously, relative paths were resolved against the caller's cwd, which failed for most real invocations.

### Added
- 5 new regression tests in `tests/test_registry.py` covering:
  - `TestShellEnvChaining::test_cmd_shell_env_uses_CALL_prefix`
  - `TestShellEnvChaining::test_shell_env_relative_path_resolved_to_tool_dir`
  - `TestShellEnvChaining::test_shell_env_absolute_path_unchanged`
  - `TestShellEnvChaining::test_shell_env_env_var_path_unchanged`
  - `TestNodeTypeScriptRejectsWithoutInterpreter::test_ts_check_fires_before_file_existence`

### Notes
- Fixes identified by tester agent run against the v0.7.15-v0.7.17 checklists after those commits landed. No functional regressions found in the binary polish (v0.7.15) or node runtime (v0.7.17); all three issues in this patch are in the shell runner (v0.7.16) and node runner (v0.7.17).
- Conditional dispatch (originally planned as v0.7.18) shifts to v0.7.19 to keep bug fixes segregated from new features.

Refs #30 (Phase 4c polish)

## [0.7.17] - 2026-04-16

### Added
- **Phase 4c.3 node runtime type** — dedicated `runtime.type: "node"` for the Node.js / npm / TypeScript ecosystem. Three mutually-exclusive dispatch modes:
  - **`script_path`** — dispatch via `[interpreter, <subcommand?>, args..., script, argv]`
  - **`npm_script`** — dispatch via `npm run <script> -- <argv>`
  - **`npx`** — dispatch via `npx <package> <argv>` (downloads package on first use)
- **`NODE_INTERPRETERS` profile dict** supporting 5 JS interpreters: `node`, `tsx`, `ts-node`, `bun`, `deno`. Bun and deno auto-insert the `run` subcommand; others use no subcommand. Unknown interpreters fall through with a stderr warning.
- **`runtime.interpreter`** (for `.js`/`.ts`) — pick which interpreter runs the script. Defaults to `node` for `.js`. Required for `.ts`/`.tsx`/ `.mts`/`.cts` files (fails loudly if absent — no auto-detection of TypeScript runner preference, user picks).
- **`runtime.interpreter_args`** — flags placed between interpreter (and its subcommand, if any) and the script. Enables `deno --allow-read`, `node --max-old-space-size=4096`, `bun --watch`, etc.
- **Script runner `interpreter_args`** — same field added to `runtime.type: "script"`. Unblocks `cscript //Nologo //B tool.js` (Windows JScript/WSH), `perl -w -T tool.pl`, `ruby -r tool.rb`, etc.
- **Mutual exclusion** for node dispatch modes — declaring multiple (script_path + npm_script, etc.) errors loudly with a list of declared modes. None declared also errors.
- `dz info` displays `Interp args:`, `NPM script:`, `Npx:` fields when declared on a node-type tool.
- 28 new tests in `tests/test_registry.py` covering node profile dispatch, interpreter_args placement, TypeScript-rejection-without- interpreter, npm_script argv shape, npx argv shape, mutual exclusion, script runner interpreter_args, and real-subprocess integration (auto-skipped when node/bun/deno absent).
- New pytest markers: `node`, `bun`, `deno`, `tsx`, `ts_node`, `npm`, `npx`. Auto-skip via conftest `shutil.which` checks.
- Test fixtures in `tests/fixtures/node/`: `hello.js`, `hello.ts`, `check_args.js`, `package.json`.

### Changed
- Treatment of npx **aligned with other package-manager invocations** (no special gate or warning). `npx` downloading a package on first use is structurally identical to `pip install` in `setup.command`, `cargo install` in `dev_command`, etc. The security model is "listing is safe; dispatch is user-opted-in" — applies uniformly across all runtimes and package managers.

### Deferred
- `runtime.platforms` per-platform dispatch override → v0.7.18 (micro-commit, ~30 LOC)
- Platform gating enforcement (`platform: "windows"` filters list/dispatch) → Phase 5

Refs #30 (Phase 4c.3 -- node runtime type: NODE_INTERPRETERS, script_path/npm_script/npx dispatch modes, interpreter_args) Related: #39 (trust model — npx treatment reaffirms "no special treatment per runtime; class-level capability metadata deferred")

## [0.7.16] - 2026-04-16

### Added
- **Phase 4c.2 shell runner enhancements** — per-shell dispatch profile table (`SHELL_PROFILES` in `registry.py`) supporting 7 shells: `cmd`, `bash`, `sh`, `zsh`, `csh`, `pwsh`, `powershell`. Replaces the previous 3-branch `if/elif` in `make_shell_runner`.

  Scripting-language interpreters (perl, ruby, lua, etc.) are   deliberately NOT in the shell profile table — they lack shell   semantics (no chain operators, no source syntax, no interactive   keep-open). Use `runtime.type: "script"` with `interpreter: "perl"`   (or ruby/lua/etc.) for those. The shell runner errors loudly with   a pointer to the correct runtime type when a non-shell interpreter   is declared as `shell:`.
- New manifest fields under `runtime` for shell-type tools:
  - **`shell_args`** (list): flags inserted between shell and script. Replaces default flags when present. Supports patterns like `["/E:ON", "/V:ON", "/c"]` for cmd extensions + delayed expansion, `["-NoProfile", "-ExecutionPolicy", "Bypass"]` for pwsh, or `["--login"]` for bash.
  - **`shell_env`** (dict `{script, args}`): environment-setup script chained before the tool via the shell's canonical source syntax (`source` for bash/zsh, `.` for sh/pwsh/powershell, direct invocation for cmd/csh). Covers patterns like `dazzle_env.cmd` that require VS vcvarsall, PATH setup, etc. Fails loudly for shells that don't support env chaining (e.g., `perl`).
  - **`interactive`** (bool or `"exec"`, default `false`): keeps the shell open after the tool runs (cmd `/k`, pwsh `-NoExit`). Value `"exec"` uses `os.execvp` to fully hand off the dz process to the shell — enables agentic-task scenarios where dz spawns a shell environment for continued interaction. Shells without interactive support (`sh`, `csh`, `perl`) error loudly when requested.
- `dz info` displays shell-type fields (`Shell:`, `Shell args:`, `Shell env:`, `Interactive:`) when declared in the manifest.
- 19 new shell runner tests in `tests/test_registry.py` covering profile dispatch, shell_args replacement, env chaining semantics, interactive modes (including exec handoff via mocked `os.execvp`), and per-shell edge cases (perl rejection, sh/csh interactive rejection).
- Real-subprocess integration tests with auto-skip markers: `shell_cmd`, `shell_bash`, `shell_pwsh`, `shell_zsh`, `shell_csh`, `shell_perl`, `shell_env`, `shell_interactive`, `shell_exec`. `tests/conftest.py` provides per-runner auto-skip via `shutil.which`.
- Shell test fixtures in `tests/fixtures/shells/`: `hello.{sh,bat,ps1}`, `env_setup.{sh,cmd,ps1}`, `check_env.{sh,bat,ps1}`.

### Changed
- `make_shell_runner` in `dazzlecmd_lib/registry.py` rewritten from 27 lines of hardcoded if/elif branching to ~120 lines of profile-driven dispatch. Zero existing shell-type tools in the repo were affected (grep confirmed pre-migration). No backward-compat shim needed.

Refs #30 (Phase 4c.2 -- shell runner enhancements) Refs #22 (runtime shell fields align with interpreter dispatch model)

## [0.7.15] - 2026-04-15

### Changed
- **Binary runner `dev_command` polish**: documented dispatch precedence (binary exists -> run it; binary missing + dev_command -> fallback; FORCE_DEV -> always dev_command). Added `DAZZLECMD_FORCE_DEV=1` env var override for active development workflows (e.g., always use `cargo run` even when the release binary exists).
- `dz info` now shows `Binary:` (instead of `Script:`) for binary runtime tools, plus `Dev command:` and `Interpreter:` fields when declared in the manifest.

### Added
- 11 new registry tests (`tests/test_registry.py`): binary runner dispatch precedence, FORCE_DEV override, arg forwarding, registry resolution.

Refs #30 (Phase 4c.1 -- binary runner polish)

## [0.7.14] - 2026-04-15

### Added
- **`dz setup <tool>`** command: runs a tool's declared setup script. Platform-aware (reads `setup.platforms` for cross-platform variants). `dz setup` without a tool lists tools with setup commands. `dz info` now surfaces setup notes when declared. The engine never installs dependencies -- it dispatches what the tool author declares.
- `lifecycle` field in `dz new` scaffolding now includes `type: "tool"` and `created_as: "tool"` alongside `status`, for Phase 5 entity promotion tracking. The library JSON template mirrors this.
- Human test checklist: `tests/checklists/v0.8.0__Phase4b-addendum__templates-setup-lifecycle.md`

### Changed
- Tool scaffolding templates moved from `src/dazzlecmd/templates/` to the library at `packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/`. The CLI resolver prefers the library location and falls back to the local path if the library is not installed. `package_data` in the library's `pyproject.toml` ensures the templates ship with the wheel.
- `dz --help` commands section now lists `tree` and `setup` alongside the other meta-commands (`_build_categorized_help` was out of sync with the actual subparser registration).

Refs #27 (dazzlecmd-lib extraction -- templates + dz setup landed; PyPI, tutorial, examples, wtf adoption still open) Refs #33 (dz setup core implemented; first-run detection, automated tests, docs deferred) Refs #30 (Phase 4b Step 3 complete; interpreter field and multi-language templates still open under 4b)

## [0.7.13] - 2026-04-15

### Added
- **`dazzlecmd-lib` package** at `packages/dazzlecmd-lib/` (v0.1.0): the engine, loader, config, and runner registry extracted as an independently-importable library. Third-party aggregators can `pip install dazzlecmd-lib` and `from dazzlecmd_lib.engine import AggregatorEngine` without depending on the full dazzlecmd CLI.
- `dazzlecmd_lib.config.ConfigManager`: standalone config read/write with atomic writes, caching, and merge semantics. Extracted from engine.py's inline config methods.
- `dazzlecmd_lib.registry.RunnerRegistry`: extensible dispatch registry replacing the `if/elif` chain in `resolve_entry_point()`. Built-in types (python, shell, script, binary) registered at import time. Runner factories are now public API (`make_python_runner`, etc.).
- `dazzlecmd_lib.loader.set_manifest_cache_fn()`: callback hook for manifest caching. The library starts with no cache; dazzlecmd's loader shim injects `mode.get_cached_manifest` at import time.
- `meta_commands` constructor parameter on `AggregatorEngine`: allows non-dazzlecmd aggregators to specify their own meta-command set.
- 28 new library tests (`tests/test_library.py`): direct imports, class identity, RunnerRegistry standalone, ConfigManager standalone, manifest cache hook, meta_commands configurable, library isolation check.
- Human test checklist: `tests/checklists/v0.8.0__Phase4b__dazzlecmd-lib-extraction.md`

### Changed
- `src/dazzlecmd/engine.py` and `src/dazzlecmd/loader.py` replaced with backwards-compat shims that re-export from `dazzlecmd_lib`. Existing `from dazzlecmd.engine import AggregatorEngine` paths continue to work.
- `_make_*_runner` private functions renamed to public `make_*_runner` in the registry. Legacy `_make_*` aliases preserved in the loader shim for test compatibility.

Refs #27 (dazzlecmd-lib extraction -- core modules extracted) Refs #32 (runner registry implemented) Refs #30 (Phase 4b Step 1+2)

## [0.7.12] - 2026-04-15

### Fixed
- **#29 wtf dispatch ImportError**: `_make_subprocess_runner` now detects package-structured tools (via `runtime.module` manifest field or `__init__.py` heuristic) and uses `python -m module.path` instead of `python script.py`. Fixes `ImportError: attempted relative import with no known parent package` for wtf-restarted and wtf-locked.

### Changed
- **#31 engine->cli layering violation resolved**: `engine.run()` no longer imports from `cli.py`. The engine accepts `parser_builder`, `meta_dispatcher`, and `tool_dispatcher` as callbacks injected at construction time. `cli.py:main()` passes its functions. This enables clean library extraction (#27) — `dazzlecmd-lib` can contain the engine without depending on the CLI package.
- Reserved commands: added `promote`, `demote`, `migrate` (Phase 5, #36) and `setup` (Phase 4b, #33) to prevent tool name collisions.

### Housekeeping
- Closed stale issues: #12 (terminal-aware help, shipped v0.3.1),
  #15 (fixpath --find, shipped v0.4.0), #16 (dz find, shipped v0.4.0)

Closes #29 Closes #31 Refs #30 (Phase 4a tactical fixes) Related: #36 (Phase 5 reserved commands)

## [0.7.11] - 2026-04-11

### Added
- **Phase 3 of the architectural epoch**: kit management UX and user config write path. The engine now has a complete read + write config story, and users have CLI commands for kit enable/disable/focus/reset, favorite tool disambiguation, per-tool hint silencing, tool shadowing, kit import via git submodule, and aggregator tree visualization.
- **`engine._get_user_config()` / `_write_user_config()`**: the config infrastructure foundation. Reads ``~/.dazzlecmd/config.json`` with per-key defaults and caching; writes atomically via temp-file + ``os.replace()`` with merge semantics (preserves unknown user-added keys). ``DAZZLECMD_CONFIG`` env var overrides the path (test isolation). Injects ``_schema_version: 1`` on first write; reserved for future migration tooling.
- **`_get_config_list()` / `_get_config_dict()`**: type-validated helpers that return a default (or warn to stderr) on malformed values.
- **`loader.get_active_kits(kits, user_config=None)`**: now consults the user config for ``active_kits``/``disabled_kits`` filtering. Legacy callers (no config) get all kits. Overlap rule: ``disabled_kits`` wins with a stderr warning.
- **`DZ_KITS` environment variable**: comma-separated kit list that fully overrides the config's ``active_kits``/``disabled_kits``. Empty string means "no kits" (meta-commands only). Distinct from unset.
- **`FQCNIndex.resolve(..., favorites=...)`**: favorites bypass precedence when the short name is in the favorites dict and the target FQCN exists. Stale favorites (target not in index) emit a warning notification and fall through to precedence resolution.
- **`engine._maybe_emit_reroot_hint()`** now consults ``silenced_hints.tools`` and ``silenced_hints.kits``. Silenced tools are filtered out before computing the deepest FQCN, so users can acknowledge individual deep tools without disabling the hint globally.
- **`engine._discover_aggregator()`** filters ``shadowed_tools`` at the top level after recursive merge. Shadowed tools are removed from ``engine.projects`` entirely — they don't appear in ``dz list``, aren't dispatchable, and their short names are freed for other tools.
- **`dz kit enable <name>`** / **`dz kit disable <name>`**: add/remove a kit from the user's active/disabled lists. Warns if the named kit is not among the discovered kits.
- **`dz kit focus <name>`**: shorthand for "enable this kit, disable all non-always_active kits except the named one." ``always_active: true`` kits are preserved automatically.
- **`dz kit reset`**: wipes ``~/.dazzlecmd/config.json`` after confirmation. ``-y/--yes`` flag skips the prompt.
- **`dz kit favorite <short> <fqcn>`** / **`dz kit unfavorite <short>`**: pin a favorite to win short-name resolution on collision. Rejects reserved command names at set time. Warns if the target FQCN isn't in the current discovery (saves anyway; may be stale).
- **`dz kit silence <fqcn>`** / **`dz kit unsilence <fqcn>`**: per-tool rerooting hint silencing.
- **`dz kit shadow <fqcn>`** / **`dz kit unshadow <fqcn>`**: hide a tool entirely from ``dz`` dispatch. Useful when the tool exists standalone (e.g., ``safedel`` installed via PyPI).
- **`dz kit silenced`**: show all silenced hints, shadowed tools, and favorites in one view.
- **`dz kit add <url>`**: wraps ``git submodule add`` into ``projects/<name>`` and creates a registry pointer at ``kits/<name>.kit.json``. Detects nested aggregator structure and informs the user. Flags: ``--name``, ``--branch``, ``--shallow``.
- **`dz tree`**: visualize the aggregator tree. ASCII output by default (using ``+--``/``|``/``\--`` characters, no Unicode box-drawing for Windows codepage safety). Flags: ``--json`` for machine-readable structured output, ``--depth N`` to limit depth, ``--kit NAME`` to show only one subtree, ``--show-disabled`` to include disabled kits.
- **`dz list`** now marks tools with short-name collisions using ``[*]`` after the name, with a footer note explaining how to disambiguate.
- **`dz kit list`** now shows enabled/disabled/always_active status per kit in the output.
- Tests: 75 new Phase 3 tests across ``test_engine_config.py`` (28), ``test_cli_kit.py`` (23), ``test_cli_tree.py`` (11), plus favorites extension in ``test_engine_fqcn.py`` (+7) and silence/shadow extension in ``test_engine_recursive.py`` (+6). Full suite: 190 passing.

### Changed
- `engine.resolve_command()` now applies ``favorites`` before precedence, so favorites take precedence over the default kit ordering when a collision exists.
- `engine._discover_aggregator()` passes the user config into ``get_active_kits()`` only at the top level (depth 0 and ``is_root``). Imported child aggregators are not filtered by the parent's user config — they honor their own kit selection.
- Config read path is lazy: ``_config_path()`` calls ``os.path.expanduser`` at invocation time (not module import time) so test fixtures that monkeypatch ``HOME`` / ``USERPROFILE`` work correctly.

### Config schema (new as of v0.7.11)

```json
{
    "_schema_version": 1,
    "kit_precedence": ["core", "dazzletools", "wtf"],
    "active_kits": ["core", "wtf"],
    "disabled_kits": ["dazzletools"],
    "favorites": {"status": "core:status"},
    "silenced_hints": {"tools": [], "kits": []},
    "shadowed_tools": [],
    "kit_discovery": "auto"
}
```

All keys optional; missing keys fall back to defaults. Malformed values are tolerated with a stderr warning. Unknown user-added keys are preserved across writes.

### Design
- `private/claude/2026-04-11__07-02-02__dev-workflow-process_phase3-kit-management-and-config-write.md` — focused 5-axis dev-workflow analysis (config schema, command surface, sub-feature ordering, Phase 3/4 boundary, acceptance criteria consolidation)
- `private/claude/2026-04-11__07-15-11__phase3-decisions-and-command-surface.md` — user Q&A resolving the open decisions from the dev-workflow

### Versioning note
Phase 3 ships as a PATCH bump (0.7.10 -> 0.7.11) following the project convention of treating architectural-phase work as incremental within the current MINOR. MAJOR/MINOR bump is reserved for the completion milestone of the architectural refactor — when `dazzlecmd-lib` extracts (#27) and wtf-windows validates the library layering (#28).

Refs #9 (collision detection + favorites landed) Refs #18 (kit focus/enable/disable + rerooting principle all landed) Refs #26 (per-tool silencing and tool shadowing landed) Related: #27 (forward pointer -- dazzlecmd-lib extraction, Phase 4) Related: #28 (forward pointer -- wtf-windows full integration, Phase 4)

## [0.7.10] - 2026-04-11

### Changed
- **safedel Phase 8**: migrated to filekit v0.2.4 primitives, eliminating ~514 lines of duplicated code (commit `d5a56b3`). Pure refactor with zero user-visible behavior change.
  - `_save_manifest` and `save_registry` now use `dazzle_filekit.operations.atomic_write_json` (removes two copies of the tmp-write + `os.replace` idiom).
  - `_stage_regular` and `_recover_entry` directory branches now use `dazzle_filekit.operations.copy_tree_preserving_links` in place of `shutil.copytree(..., symlinks=True)`. Filekit's wrapper enforces `symlinks=True` and rejects reparse-point roots as defense-in-depth.
  - `_lib/preservelib/metadata.py` replaced with a 74-line re-export shim pointing at `dazzle_filekit.metadata` (was 883 lines of duplicated metadata capture/apply code). Existing `from preservelib.metadata import ...` call sites continue to work; the canonical code now lives once, in filekit.

### Added
- **safedel golden invariant test suite** (`tests/test_golden_invariants.py`): 17 behavioral invariant tests capturing safedel's end-state guarantees as a permanent regression safety net. Covers classification determinism, roundtrip metadata preservation, manifest schema stability, folder naming convention, dry-run invariants, list/status consistency, and platform detection.
- **safedel TODO.md and ROADMAP.md**: short-term task list and long-term phase strategy committed to the tool's folder. ROADMAP.md adds two new Design Principles:
  - Principle 8: Golden invariants over text-based goldens -- capture end-state properties rather than text fixtures that drift.
  - Principle 9: Defense in depth, even against our own code -- e.g., `safe_delete` checks for reparse points even when the classifier said it's a regular directory.

### Architectural outcome
safedel now has a clean one-way dependency on filekit for primitives and a minimal dependency on preservelib (shim only). The layering rule documented in the integration analysis (`2026-04-10__20-31-07__preservelib-filekit-integration.md`) is now enforced in practice, not just on paper: filekit = primitives, preservelib = workflow, safedel = tool.

### Test counts
- Windows: 144 passed, 7 skipped (127 pre-Phase-8 + 17 new golden invariants)
- WSL Ubuntu-22.04: 124 passed, 27 skipped

## [0.7.9] - 2026-04-10

### Added
- **Recursive aggregator discovery** (Phase 2): kits whose directory contains a `kits/` subdirectory are now treated as nested aggregators. The engine instantiates a child `AggregatorEngine(is_root=False)` for each, discovers its structure independently, namespace-remaps the returned tools, and merges them into the parent's project list.
- **FQCN dispatch**: every tool is addressable by its fully qualified collection name (`kit:namespace:tool`, e.g., `wtf:core:restarted`). Short names still work when unambiguous.
- **Precedence-aware resolution**: when a short name resolves to multiple tools, the engine picks by precedence (core wins by default) and prints a stderr notification showing the picked tool and alternatives. Users can override precedence via `~/.dazzlecmd/config.json` `kit_precedence` list. Silenceable via `DZ_QUIET=1`.
- `FQCNIndex` class (`engine.py`): dual-index data structure with `fqcn_index` (exact match) and `short_index` (candidate lookup for precedence resolution).
- `CircularDependencyError`: loading-stack cycle detection via `os.path.realpath()` keys prevents infinite recursion when an aggregator tree contains a cycle.
- **Rerooting hint**: nesting depth is unlimited, but when discovery surfaces a tool with 4+ FQCN segments the engine prints a one-time hint suggesting the user consider extracting that subtree as a standalone install (PyPI package, separate `dz`-pattern aggregator). This implements the *primacy* principle: any tool or aggregator can become its own root based on how the user wants to access it. Example: `dz safedel` today, `safedel` tomorrow once safedel ships standalone -- both paths coexist. Hint is silenceable via `DZ_QUIET=1`. Per-tool silencing and tool shadowing deferred to #26 (Phase 3).
- `is_root=False` propagation: imported aggregators suppress meta-commands (`list`, `info`, `kit`, etc.) and expose only their tools.
- `_fqcn`, `_short_name`, `_kit_import_name` fields on every project dict for traceability and correct display.
- `dz info` now shows `FQCN` and `Kit` fields. Accepts FQCN input: `dz info wtf:core:locked`.
- `dz list` column changed from "Namespace" to "Kit" -- shows the actual import-level kit a tool came from, not the raw internal namespace.
- `dz list --kit wtf` now filters by kit import name, not raw namespace.
- Tests: 15 new recursive discovery tests (`test_engine_recursive.py`), 24 new FQCN index/resolver tests (`test_engine_fqcn.py`), 11 one-off prototype tests (`tests/one-offs/test_fqcn_prototype.py`).

### Changed
- `loader.py:_scan_tool_dirs` dedupes by `(namespace, tool_name)` tuple instead of bare short name, preventing silent drops when recursive discovery introduces tools with colliding short names.
- `loader.py:discover_projects` namespace extraction uses `rsplit(":", 1)` to handle 3-part FQCNs like `wtf:core:restarted` (was `split(":")[0]`).
- `loader.py:discover_projects` accepts a `default_manifest` parameter so child engines with custom manifest names (e.g., `.wtf.json`) work.
- `loader.py:discover_kits` propagates `_override_tools_dir` and `_override_manifest` from registry pointers, enabling temporary parent-level overrides when a nested aggregator's in-repo manifest is missing tools_dir/manifest declarations.
- `engine.run()` dispatches tools through `resolve_command()` instead of `p["name"] == command_name`, enabling both FQCN and precedence-aware short-name dispatch.
- `kits/wtf.kit.json` temporarily declares `_override_tools_dir: "tools"` and `_override_manifest: ".wtf.json"` until the wtf-windows upstream commits these fields into its own `kits/core.kit.json` (see #28).

### Forward pointers
- Phase 3 work: kit management UI, per-tool silencing (#26), `dz kit enable/disable/shadow` commands, config write path.
- Phase 4 work: `dazzlecmd-lib` engine extraction as importable library (#27), wtf-windows full integration experiment (#28), ecosystem scaffolding.

### Versioning note
Phase 2 ships as a PATCH bump (0.7.8 -> 0.7.9) following the project's convention of treating architectural-phase work as incremental within the current MINOR. Phase 1 (AggregatorEngine, v0.7.1) set this precedent. The MINOR/MAJOR bump is reserved for the completion milestone of the architectural refactor -- likely when `dazzlecmd-lib` extracts (#27) and wtf-windows validates the library layering (#28).

### Design
- 9-axis DEV WORKFLOW PROCESS analysis (`2026-04-10__12-15-00__dev-workflow-process_phase2-recursive-fqcn-dispatch.md`)
- Oracle agent trace of architectural history and existing dispatch code
- FQCN prototype in `tests/one-offs/` validated data structure before engine integration

## [0.7.8] - 2026-04-10

### Added
- safedel phase 3b: Windows creation time (ctime) restoration
  - `preservelib.metadata.restore_windows_creation_time()` using pywin32 with `FILE_WRITE_ATTRIBUTES=0x100`, `FILE_FLAG_BACKUP_SEMANTICS` for directories, and readonly clear/restore handling
  - Auto-invoked by `apply_file_metadata()` on Windows recovery
  - `is_win32_available()` helper with startup warning in safedel.py when pywin32 is missing
- safedel phase 3b: WSL dual-path manifest storage
  - `TrashEntry.original_path_alt` field stores the cross-runtime path form (e.g., `/mnt/c/...` for Windows `C:\...` and vice versa)
  - `_compute_alt_path()` in _store.py converts between Windows and WSL forms
  - Recovery falls back to alt path when native path parent is unreachable
- safedel phase 3c: NTFS Alternate Data Stream detection
  - `_platform.detect_alternate_streams()` via ctypes `FindFirstStreamW`/ `FindNextStreamW` (pywin32 doesn't expose these)
  - Filters `::$DATA` and `:Zone.Identifier` to reduce alert fatigue
  - Warns during cross-device staging when significant ADS are present
- safedel phase 3c: Linux/macOS extended attribute (xattr) preservation
  - `_collect_unix_xattrs()` captures xattrs as base64 in manifest
  - `_apply_unix_xattrs()` restores via `os.setxattr`
  - Skips `com.apple.quarantine` to avoid Gatekeeper security surprises
- safedel: 29 new tests (127 total on Windows, 107 on WSL)
  - `test_ctime.py` (6 Windows-only)
  - `test_wsl_dual_paths.py` (10 cross-platform)
  - `test_ads.py` (8 Windows-only)
  - `test_xattr.py` (5 Unix-only)
- safedel: `run_tests.py` uses `sys.executable` for cross-platform test runs
- safedel: `TODO.md` and `ROADMAP.md` for project planning (short-term tasks and long-term phase strategy). Will migrate to standalone repo when safedel extracts from dazzlecmd.
- safedel: `docs/USAGE.md` -- quick reference, recipes for common scenarios, trash store locations, protection zone behavior, platform capability matrix, configuration reference, and the "oh shit" first-response guide
- safedel: `docs/MANIFEST_SCHEMA.md` -- complete JSON manifest schema with field-by-field reference, file type values, stat + preservelib metadata structures, jq inspection examples, and schema evolution policy

## [0.7.7] - 2026-04-10

### Added
- safedel: per-volume trash store for zero-copy rename staging
  - `_volumes.py` module with volume detection, per-volume trash path resolution, and JSON registry at `~/.safedel/volumes.json`
  - Uses `unctools.detector` for drive type detection (local/network/removable)
  - Uses `dazzle_filekit.utils.disk` for disk utilities
  - Stable volume identification via serial number (not mount path)
  - Multi-store discovery: list/recover/clean scan central + all per-volume stores
  - Test isolation via explicit `registry_path` parameter to TrashStore
  - Junction to unctools at `_lib/unctools` for dev-time imports
- safedel: 14 new tests in `test_volumes.py` (104 total, up from 90)

### Fixed
- safedel: `cmd_list`/`cmd_recover`/`cmd_clean` now scan all trash stores via new `_resolve_folders()` helper (previously only searched central store)

## [0.7.6] - 2026-04-08

### Added
- core: `safedel` -- safe file/directory deletion with link-aware classification, metadata-preserving trash store, and time-pattern-based recovery
  - Detects symlinks, junctions, hardlinks, shortcuts; uses correct delete method per type and platform
  - Stages files to timestamped trash folders (`YYYY-MM-DD__hh-mm-ss`) with JSON manifests
  - 4-tier protection zones (A: blocked, B: --force+interactive, C: interactive, D: relaxed) to prevent LLMs from aggressively cleaning up after destructive deletes
  - Time-pattern matching for recover/list/clean: `last`, `today`, `2026-04-08 10:4*`, `--age ">30d"`
  - Metadata-only recovery: apply timestamps/permissions without overwriting content
  - Embedded libraries in `_lib/`: preservelib, help_lib, log_lib, core_lib, ps1 (future dazzlelib submodules, copied from preserve and wtf-windows projects)
  - Junction to dazzle-filekit for `normalize_path_no_resolve()` import (dev-time)

## [0.7.5] - 2026-04-08

### Added
- dazzletools: `claude-lost-sessions` (WIP, to be renamed `claude-session-metadata`) -- catalog lost Claude Code sessions with structured per-session folders (summary.md, known-docs/, folders-worked-on/, sesslog symlink, bidirectional junctions). Extracts metadata from sesslog command logs, cross-references authored docs by timeframe, and builds INDEX.md master table.
- claude-lost-sessions: Win32 symlink timestamp control via ctypes (CreateFileW + SetFileTime with FILE_FLAG_OPEN_REPARSE_POINT). Sets known-docs symlink ctime/mtime/atime independently of target files.
- claude-lost-sessions: filename-based ctime correction -- when a date-prefixed filename indicates an earlier creation time than the file's actual ctime, uses the filename date for the symlink's ctime.
- claude-lost-sessions: reverse junctions from sesslog folders back to lost-session catalog folders (appear as real directories in Explorer).
- dazzletools .kit.json: registered new tools

### Added (source not yet staged -- coming in next commit)
- dazzletools: `claude-sesslog-datefix` -- fix session log folder timestamps
- dazzletools: `private-init` -- initialize private/claude/ vault in a project
- dazzletools: `git` -- git utilities collection

### Changed
- claude-cleanup: added .claude/projects/ (session transcripts), .claude/session-env/, .claude/history.jsonl to noise tracking

## [0.7.4] - 2026-04-07

### Fixed
- CI: GitHub Pages deployment failing due to private submodule (wtf-windows) checkout. Replaced auto-generated `pages-build-deployment` workflow with custom `pages.yml` that skips submodules and deploys only `docs/`. Pages build_type switched from "legacy" to "workflow".

### Changed
- _version.py: bump to 0.7.4
- dazzle-dz alias: bump to 0.7.4

## [0.7.3] - 2026-04-07

### Changed
- fixpath: refactored search to a graduated 4-step pipeline:
  1. Exact path check
  2. Vicinity search (progressive resolve + walk up N levels)
  3. CWD-based search (Everything on indexed drives, fd otherwise)
  4. Scope widening per `--search-on` flags
- fixpath: Everything is now an accelerator at steps 2-3 (not a replacement for fd). fd handles non-indexed drives; Everything speeds up indexed ones.

### Added
- fixpath: `--search-on` flag for composable scope control (base-path, broaden, local, drive, anywhere). `base-path` restricts to CWD/`--dir` only; `broaden` limits to vicinity of the resolved path; `local` is the default (vicinity + CWD + nearby parents); `drive` and `anywhere` widen further.
- fixpath: `--broaden N` flag to control vicinity walk-up depth (default: 3, configurable via `fixpath.json: search_broaden_levels`)
- fixpath: unquoted path reassembly -- when multiple args are given and none exist individually, joins them as a single space-separated path. Handles the common case of forgetting quotes around paths with spaces.
- fixpath: `--help` output grouped into logical sections: action (mutually exclusive), search, search scope, and general options

## [0.7.2] - 2026-04-07

### Fixed
- fixpath: trailing-slash paths (e.g., `dir/name/`) no longer produce empty search patterns. `os.path.basename("path/")` returns `""` -- now stripped before extraction.
- fixpath: search broadening when progressive resolve enters the wrong subtree. When the initial resolved directory doesn't contain the target, walks up parent directories and retries (up to 3 levels).

### Added
- fixpath: Everything (es.exe) integration as optional search backend. Tries Everything first on indexed drives (instant results), falls back to fd on non-indexed drives. Everything is optional -- not required.
- fixpath: `--anywhere` flag to include cross-drive search results. Default behavior now filters to same drive as CWD.
- fixpath: directory-aware search -- trailing slash triggers `--type d` (fd) or `folder:` prefix (Everything) to find directories specifically.
- fixpath: locality-weighted result ranking -- same-drive bonus and shared base path bonus so local results rank above cross-drive matches.
- fixpath: UTF-8 subprocess encoding for `gh`/`git` calls on Windows (prevents mojibake from em dashes in API responses).

## [0.7.1] - 2026-04-03

### Added
- `AggregatorEngine` class (`engine.py`): configurable engine that powers any tool aggregator. Parameters: name, command, tools_dir, kits_dir, manifest, description, version_info, is_root
- Engine importable: `from dazzlecmd.engine import AggregatorEngine`
- `is_root` flag: suppresses meta-commands for imported aggregators
- `reserved_commands` property: empty set when is_root=False

### Changed
- `cli.py:main()` reduced to thin wrapper -- creates engine, calls engine.run()
- `find_project_root()` delegates to engine (parameterized by tools_dir/kits_dir)
- `build_parser()` accepts engine parameter for command name, description, version

## [0.7.0] - 2026-04-02

### Added
- In-repo kit manifests: kits now carry their own `.kit.json` describing tools, tools_dir, and manifest filename. Source of truth travels with the code.
- `discover_kits()` hybrid loading: reads in-repo manifests from `projects/<kit>/.kit.json` or `projects/<kit>/kits/*.kit.json`, merges with registry pointers from `kits/` (activation overrides only)
- `_load_in_repo_kit_manifest()`: scans three locations for kit self-description (root `.kit.json`, kit's own `kits/` dir, fallback to any `.kit.json`)
- wtf-windows three-tier nesting fully working: dazzlecmd -> wtf-windows (submodule) -> wtf-restarted (nested submodule with `.wtf.json`)

### Changed
- `kits/core.kit.json` reduced to registry pointer (activation only)
- `kits/dazzletools.kit.json` reduced to registry pointer (activation only)
- `kits/wtf.kit.json` reduced to registry pointer (source URL + activation only)
- Architecture: "each layer describes only itself" principle enforced -- aggregator never describes tool structure, kit repo carries its own manifest
- Architecture: "dazzlecmd is an instance, not the root" -- core kit follows the same discovery path as external kits

### Design
- 3-round Gemini 2.5 Pro consultation on recursive aggregator architecture
- Adopted `:` as FQCN separator (not `/`, avoids shell conflicts)
- Convention-based aggregator detection: `kits/` dir exists = aggregator
- Ansible Collections studied as reference architecture (FQCN, galaxy.yml)
- 10 design principles established for the generic engine vision

## [0.6.0] - 2026-04-02

### Added
- **dz github**: open GitHub project pages, issues, and releases from any git repo
  - Auto-detects GitHub remote from cwd (no `gh repo set-default` needed)
  - Page shortcuts: `pr`, `issues`, `release`, `forks`, `projects`, `actions`, `wiki`, `settings`
  - Issue lookup by number: `dz github 3`
  - Semantic issue aliases: `dz github isu roadmap`, `isu notes`, `isu epics` (resolves by label first, then title search fallback)
  - Repo finder: `dz github repo <name>` searches across all user orgs by substring
  - Implicit repo lookup: `dz github preserve` from any directory finds and opens the repo
  - Subdirectory scanning: detects git repos in child directories when not in a repo
  - Repo cache: `~/.cache/dz-github/repos.json` for instant lookups (24h TTL, `--refresh`)
  - `-n` flag to print URL without opening browser
  - Safe ASCII output for Windows consoles (no mojibake from Unicode titles)

## [0.5.1] - 2026-03-28

### Fixed
- fixpath: search fallback now triggers for all non-existent paths, not just bare filenames. Previously `dz fixpath some/path/file.md` would fail with "not found" instead of searching. Progressive resolution extracts the filename and searches from the deepest valid directory.

### Added
- git-snapshot README.md: storage model, FAQ, subcommand reference

## [0.5.0] - 2026-03-27

### Added
- **dz git-snapshot**: lightweight named checkpoints for git working state
  - `save`: capture working tree as a named snapshot (uses `git stash create` + custom refs)
  - `list`: show all snapshots with date, hash, and index
  - `show`: snapshot details and file change summary
  - `diff`: compare snapshot against current working state
  - `apply`: merge-reapply snapshot (preserves local changes)
  - `restore`: hard replace working tree from snapshot (requires `--force`)
  - `drop`: delete a snapshot by name or index
  - `clean`: prune old snapshots (`--older`, `--keep`, `--dry-run`)
  - Captures untracked files by default, preserves index state
  - Snapshots stored as `refs/snapshots/` -- stable names, no stash index drift
- 22 new tests for git-snapshot (save, list, show, diff, apply, restore, drop, clean)

## [0.4.1] - 2026-03-23

### Added
- fixpath `--all`: show all search results (best match first, ranked by path similarity)
- fixpath `--fast`: take first match instantly (fd stops after 1 result, skips ranking)
- fixpath `-d` shorthand for `--dir`
- fixpath result ranking: picks the closest match to the original input path, not just fd's first result

### Fixed
- fixpath `--dir` now implies `--find` (search was silently skipped when passing a relative path with `--dir`)

### Changed
- fixpath: extracted `_search_and_select()` to eliminate duplicated search/rank/select logic
- claude-cleanup: v0.2.0 -- added `--user` mode to stage user artifacts (configs, skills, session logs) separately from noise, updated dir/file lists

## [0.4.0] - 2026-03-20

### Added
- **dz find**: cross-platform file search powered by fd (sharkdp/fd)
  - Glob and regex patterns, extension/size/date filters, depth control
  - Actions: `--open`, `--lister`, `--copy` (same as fixpath)
  - Auto-detects `fd` / `fdfind` (Debian naming), prints install instructions if missing
  - Examples in `--help` for quick reference
- **fixpath --find**: search fallback when path doesn't resolve
  - Progressive path resolution: walks path left-to-right, finds deepest existing directory, searches from there for the filename portion
  - Auto-detects bare filenames and glob patterns, searches via fd
  - `--find` / `-f`: explicit search mode
  - `--skip` / `-s`: skip path fixing, go straight to search
  - `--dir`: specify search directories (repeatable)
  - Configurable `search_dirs` and `search_dirs_mode` in fixpath.json
- **fixpath -p / --print**: override config default, just print (no open/copy/lister)
- `dz list` word-wraps descriptions to terminal width with aligned continuation lines

### Changed
- README: added find to core kit table and project structure
- Core kit docs: added find.md, updated core README

## [0.3.1] - 2026-03-18

### Added
- `dz links --depth N`: limit recursive scan depth, powered by dazzle-tree-lib when available (falls back to os.walk with manual depth tracking)
- `dz new --kit`: auto-register new tools in a kit during scaffolding
- `dz new` now generates `platforms` and `lifecycle` fields in manifests
- Terminal-width-aware help: `dz --help` truncates descriptions to fit terminal
- Registered dazzletools:claude-cleanup in dazzletools kit and docs

### Changed
- dz links uses dazzle-tree-lib for recursive traversal when available
- Version bump to 0.3.1

## [0.3.0] - 2026-03-18

### Added
- **dz fixpath**: fix mangled paths from terminals, copy-paste, and mixed-OS environments
  - Handles mixed slashes, cmd.exe `>` artifacts, MSYS/WSL paths, URL encoding, quotes
  - Action modes: `--open` (default app), `--lister` (file manager), `--copy` (clipboard)
  - Per-user config: `dz fixpath config default <action>`, `dz fixpath config lister dopus`
  - File manager presets: Directory Opus, Total Commander, Windows Explorer
  - Cross-platform clipboard via teeclip (optional) or native tools
  - Bidirectional path probing: finds files across WSL/MSYS/Windows boundaries
  - UNC path support: `//server/share` and shell-mangled `\\server\share`, with automatic local drive conversion via unctools when available
  - Uses dazzle-filekit's `resolve_cross_platform_path()` when available
- Documentation suite:
  - Per-tool docs for all core tools (fixpath, links, listall, rn)
  - Developer guide: Creating Tools (how to build a dz tool)
  - Kits guide: kit system, recursive architecture, "build your own dz"
  - Manifest reference: `.dazzlecmd.json` schema
  - Platform support matrix
  - DazzleTools kit stub (external ownership)
- Categorized `dz --help` output: builtins, core tools, and kit tools in separate sections

### Changed
- README: tool table links to docs, new Documentation section, fixpath in project structure
- cli.py: custom help epilog replaces flat argparse subparser listing
- Registered dazzletools:claude-cleanup in dazzletools kit

## [0.2.2-alpha] - 2026-03-16

### Added
- `dazzle-dz` alias package on PyPI (forwarder, depends on `dazzlecmd`)
- Manual publish trigger (`workflow_dispatch`) in publish workflow
- Dual-package build: publish.yml builds and publishes both `dazzlecmd` and `dazzle-dz`

### Changed
- Version bump to 0.2.2-alpha

## [0.2.1-alpha] - 2026-03-16

### Added
- GitHub traffic tracking via ghtraf (badges, dashboard, daily history)
- PyPI publishing workflow (Trusted Publisher via GitHub Actions)

### Changed
- Version bump to 0.2.1-alpha

## [0.2.0-alpha] - 2026-03-16

### Added
- **dz links**: filesystem link detection tool (core kit)
  - Detects symlinks, junctions, hardlinks, .lnk shortcuts, .url internet shortcuts, .dazzlelink descriptors
  - .lnk binary parser (MS-SHLLINK format) with relative path resolution
  - .url INI parser for web resource shortcuts
  - Windows junction detection via ctypes DeviceIoControl reparse tag
  - Hardlink target resolution via FindFirstFileNameW on Windows
  - Path canonicalization: MSYS/Git Bash (/c/path), forward slashes, \\?\ prefix stripping
  - Optional dazzle-filekit/unctools integration for enhanced normalization
  - Flags: -r (recursive), -t (type filter), -b (broken), -j (JSON), -v (verbose)

### Changed
- README: updated core kit table (added links, listall), usage examples, project structure diagram

## [0.1.1-alpha] - 2026-02-14

### Added
- CI/CD pipeline: smoke tests, flake8 linting, package build verification (Python 3.8-3.13)

### Changed
- License switched from MIT to GPL-3.0-or-later
- README rewritten with badges, narrative intro, tool tables, architecture overview

## [0.1.0-alpha] - 2026-02-13

### Added
- Initial release of dazzlecmd CLI framework
- Kit-aware tool discovery with `.dazzlecmd.json` manifests
- Progressive scaffolding: `dz new` (bare/--simple/--full)
- Multi-runtime dispatch: Python (direct import + subprocess), shell, script, binary
- Meta-commands: list, info, kit, new, version
- Core kit: rn (regex file renamer)
- DazzleTools kit: dos2unix, delete-nul, srch-path, split

[Unreleased]: https://github.com/DazzleTools/dazzlecmd/compare/v0.11.4...HEAD
[0.7.42]: https://github.com/DazzleTools/dazzlecmd/compare/v0.7.41...v0.7.42
[0.7.41]: https://github.com/DazzleTools/dazzlecmd/compare/v0.7.40...v0.7.41
[0.7.40]: https://github.com/DazzleTools/dazzlecmd/compare/v0.7.39...v0.7.40
[0.7.39]: https://github.com/DazzleTools/dazzlecmd/releases/tag/v0.7.39
