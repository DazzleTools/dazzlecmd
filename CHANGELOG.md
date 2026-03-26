# Changelog

All notable changes to dazzlecmd are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/).

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
