# Changelog

All notable changes to dazzlecmd are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/).

## [0.7.6] - 2026-04-08

### Added
- core: `safedel` -- safe file/directory deletion with link-aware classification,
  metadata-preserving trash store, and time-pattern-based recovery
  - Detects symlinks, junctions, hardlinks, shortcuts; uses correct delete method per type and platform
  - Stages files to timestamped trash folders (`YYYY-MM-DD__hh-mm-ss`) with JSON manifests
  - 4-tier protection zones (A: blocked, B: --force+interactive, C: interactive, D: relaxed)
    to prevent LLMs from aggressively cleaning up after destructive deletes
  - Time-pattern matching for recover/list/clean: `last`, `today`, `2026-04-08 10:4*`, `--age ">30d"`
  - Metadata-only recovery: apply timestamps/permissions without overwriting content
  - Embedded libraries in `_lib/`: preservelib, help_lib, log_lib, core_lib, ps1
    (future dazzlelib submodules, copied from preserve and wtf-windows projects)
  - Junction to dazzle-filekit for `normalize_path_no_resolve()` import (dev-time)

## [0.7.5] - 2026-04-08

### Added
- dazzletools: `claude-lost-sessions` (WIP, to be renamed `claude-session-metadata`)
  -- catalog lost Claude Code sessions with structured per-session folders
  (summary.md, known-docs/, folders-worked-on/, sesslog symlink, bidirectional
  junctions). Extracts metadata from sesslog command logs, cross-references
  authored docs by timeframe, and builds INDEX.md master table.
- claude-lost-sessions: Win32 symlink timestamp control via ctypes
  (CreateFileW + SetFileTime with FILE_FLAG_OPEN_REPARSE_POINT). Sets
  known-docs symlink ctime/mtime/atime independently of target files.
- claude-lost-sessions: filename-based ctime correction -- when a date-prefixed
  filename indicates an earlier creation time than the file's actual ctime,
  uses the filename date for the symlink's ctime.
- claude-lost-sessions: reverse junctions from sesslog folders back to
  lost-session catalog folders (appear as real directories in Explorer).
- dazzletools .kit.json: registered new tools

### Added (source not yet staged -- coming in next commit)
- dazzletools: `claude-sesslog-datefix` -- fix session log folder timestamps
- dazzletools: `private-init` -- initialize private/claude/ vault in a project
- dazzletools: `git` -- git utilities collection

### Changed
- claude-cleanup: added .claude/projects/ (session transcripts),
  .claude/session-env/, .claude/history.jsonl to noise tracking

## [0.7.4] - 2026-04-07

### Fixed
- CI: GitHub Pages deployment failing due to private submodule (wtf-windows)
  checkout. Replaced auto-generated `pages-build-deployment` workflow with
  custom `pages.yml` that skips submodules and deploys only `docs/`.
  Pages build_type switched from "legacy" to "workflow".

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
- fixpath: Everything is now an accelerator at steps 2-3 (not a replacement
  for fd). fd handles non-indexed drives; Everything speeds up indexed ones.

### Added
- fixpath: `--search-on` flag for composable scope control (base-path, broaden,
  local, drive, anywhere). `base-path` restricts to CWD/`--dir` only; `broaden`
  limits to vicinity of the resolved path; `local` is the default (vicinity +
  CWD + nearby parents); `drive` and `anywhere` widen further.
- fixpath: `--broaden N` flag to control vicinity walk-up depth (default: 3,
  configurable via `fixpath.json: search_broaden_levels`)
- fixpath: unquoted path reassembly -- when multiple args are given and none
  exist individually, joins them as a single space-separated path. Handles
  the common case of forgetting quotes around paths with spaces.
- fixpath: `--help` output grouped into logical sections: action (mutually
  exclusive), search, search scope, and general options

## [0.7.2] - 2026-04-07

### Fixed
- fixpath: trailing-slash paths (e.g., `dir/name/`) no longer produce empty search
  patterns. `os.path.basename("path/")` returns `""` -- now stripped before extraction.
- fixpath: search broadening when progressive resolve enters the wrong subtree.
  When the initial resolved directory doesn't contain the target, walks up parent
  directories and retries (up to 3 levels).

### Added
- fixpath: Everything (es.exe) integration as optional search backend. Tries
  Everything first on indexed drives (instant results), falls back to fd on
  non-indexed drives. Everything is optional -- not required.
- fixpath: `--anywhere` flag to include cross-drive search results. Default
  behavior now filters to same drive as CWD.
- fixpath: directory-aware search -- trailing slash triggers `--type d` (fd)
  or `folder:` prefix (Everything) to find directories specifically.
- fixpath: locality-weighted result ranking -- same-drive bonus and shared
  base path bonus so local results rank above cross-drive matches.
- fixpath: UTF-8 subprocess encoding for `gh`/`git` calls on Windows
  (prevents mojibake from em dashes in API responses).

## [0.7.1] - 2026-04-03

### Added
- `AggregatorEngine` class (`engine.py`): configurable engine that powers any
  tool aggregator. Parameters: name, command, tools_dir, kits_dir, manifest,
  description, version_info, is_root
- Engine importable: `from dazzlecmd.engine import AggregatorEngine`
- `is_root` flag: suppresses meta-commands for imported aggregators
- `reserved_commands` property: empty set when is_root=False

### Changed
- `cli.py:main()` reduced to thin wrapper -- creates engine, calls engine.run()
- `find_project_root()` delegates to engine (parameterized by tools_dir/kits_dir)
- `build_parser()` accepts engine parameter for command name, description, version

## [0.7.0] - 2026-04-02

### Added
- In-repo kit manifests: kits now carry their own `.kit.json` describing tools,
  tools_dir, and manifest filename. Source of truth travels with the code.
- `discover_kits()` hybrid loading: reads in-repo manifests from
  `projects/<kit>/.kit.json` or `projects/<kit>/kits/*.kit.json`, merges with
  registry pointers from `kits/` (activation overrides only)
- `_load_in_repo_kit_manifest()`: scans three locations for kit self-description
  (root `.kit.json`, kit's own `kits/` dir, fallback to any `.kit.json`)
- wtf-windows three-tier nesting fully working: dazzlecmd -> wtf-windows (submodule)
  -> wtf-restarted (nested submodule with `.wtf.json`)

### Changed
- `kits/core.kit.json` reduced to registry pointer (activation only)
- `kits/dazzletools.kit.json` reduced to registry pointer (activation only)
- `kits/wtf.kit.json` reduced to registry pointer (source URL + activation only)
- Architecture: "each layer describes only itself" principle enforced --
  aggregator never describes tool structure, kit repo carries its own manifest
- Architecture: "dazzlecmd is an instance, not the root" -- core kit follows
  the same discovery path as external kits

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
  - Semantic issue aliases: `dz github isu roadmap`, `isu notes`, `isu epics`
    (resolves by label first, then title search fallback)
  - Repo finder: `dz github repo <name>` searches across all user orgs by substring
  - Implicit repo lookup: `dz github preserve` from any directory finds and opens the repo
  - Subdirectory scanning: detects git repos in child directories when not in a repo
  - Repo cache: `~/.cache/dz-github/repos.json` for instant lookups (24h TTL, `--refresh`)
  - `-n` flag to print URL without opening browser
  - Safe ASCII output for Windows consoles (no mojibake from Unicode titles)

## [0.5.1] - 2026-03-28

### Fixed
- fixpath: search fallback now triggers for all non-existent paths, not just bare filenames.
  Previously `dz fixpath some/path/file.md` would fail with "not found" instead of
  searching. Progressive resolution extracts the filename and searches from the deepest
  valid directory.

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
- claude-cleanup: v0.2.0 -- added `--user` mode to stage user artifacts
  (configs, skills, session logs) separately from noise, updated dir/file lists

## [0.4.0] - 2026-03-20

### Added
- **dz find**: cross-platform file search powered by fd (sharkdp/fd)
  - Glob and regex patterns, extension/size/date filters, depth control
  - Actions: `--open`, `--lister`, `--copy` (same as fixpath)
  - Auto-detects `fd` / `fdfind` (Debian naming), prints install instructions if missing
  - Examples in `--help` for quick reference
- **fixpath --find**: search fallback when path doesn't resolve
  - Progressive path resolution: walks path left-to-right, finds deepest
    existing directory, searches from there for the filename portion
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
- `dz links --depth N`: limit recursive scan depth, powered by dazzle-tree-lib
  when available (falls back to os.walk with manual depth tracking)
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
  - UNC path support: `//server/share` and shell-mangled `\\server\share`,
    with automatic local drive conversion via unctools when available
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
