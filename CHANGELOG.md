# Changelog

All notable changes to dazzlecmd are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/).

## [0.7.13] - 2026-04-15

### Added
- **`dazzlecmd-lib` package** at `packages/dazzlecmd-lib/` (v0.1.0):
  the engine, loader, config, and runner registry extracted as an
  independently-importable library. Third-party aggregators can
  `pip install dazzlecmd-lib` and `from dazzlecmd_lib.engine import
  AggregatorEngine` without depending on the full dazzlecmd CLI.
- `dazzlecmd_lib.config.ConfigManager`: standalone config read/write
  with atomic writes, caching, and merge semantics. Extracted from
  engine.py's inline config methods.
- `dazzlecmd_lib.registry.RunnerRegistry`: extensible dispatch registry
  replacing the `if/elif` chain in `resolve_entry_point()`. Built-in
  types (python, shell, script, binary) registered at import time.
  Runner factories are now public API (`make_python_runner`, etc.).
- `dazzlecmd_lib.loader.set_manifest_cache_fn()`: callback hook for
  manifest caching. The library starts with no cache; dazzlecmd's
  loader shim injects `mode.get_cached_manifest` at import time.
- `meta_commands` constructor parameter on `AggregatorEngine`: allows
  non-dazzlecmd aggregators to specify their own meta-command set.
- 28 new library tests (`tests/test_library.py`): direct imports, class
  identity, RunnerRegistry standalone, ConfigManager standalone, manifest
  cache hook, meta_commands configurable, library isolation check.
- Human test checklist:
  `tests/checklists/v0.8.0__Phase4b__dazzlecmd-lib-extraction.md`

### Changed
- `src/dazzlecmd/engine.py` and `src/dazzlecmd/loader.py` replaced with
  backwards-compat shims that re-export from `dazzlecmd_lib`. Existing
  `from dazzlecmd.engine import AggregatorEngine` paths continue to work.
- `_make_*_runner` private functions renamed to public `make_*_runner` in
  the registry. Legacy `_make_*` aliases preserved in the loader shim
  for test compatibility.

Refs #27 (dazzlecmd-lib extraction — core modules extracted, templates + dz setup remain)
Refs #32 (runner registry implemented)
Refs #30 (Phase 4b in progress)

## [0.7.12] - 2026-04-15

### Fixed
- **#29 wtf dispatch ImportError**: `_make_subprocess_runner` now detects
  package-structured tools (via `runtime.module` manifest field or
  `__init__.py` heuristic) and uses `python -m module.path` instead of
  `python script.py`. Fixes `ImportError: attempted relative import with
  no known parent package` for wtf-restarted and wtf-locked.

### Changed
- **#31 engine->cli layering violation resolved**: `engine.run()` no
  longer imports from `cli.py`. The engine accepts `parser_builder`,
  `meta_dispatcher`, and `tool_dispatcher` as callbacks injected at
  construction time. `cli.py:main()` passes its functions. This enables
  clean library extraction (#27) — `dazzlecmd-lib` can contain the
  engine without depending on the CLI package.
- Reserved commands: added `promote`, `demote`, `migrate` (Phase 5, #36)
  and `setup` (Phase 4b, #33) to prevent tool name collisions.

### Housekeeping
- Closed stale issues: #12 (terminal-aware help, shipped v0.3.1),
  #15 (fixpath --find, shipped v0.4.0), #16 (dz find, shipped v0.4.0)

Closes #29
Closes #31
Refs #30 (Phase 4a tactical fixes)
Related: #36 (Phase 5 reserved commands)

## [0.7.11] - 2026-04-11

### Added
- **Phase 3 of the architectural epoch**: kit management UX and user
  config write path. The engine now has a complete read + write config
  story, and users have CLI commands for kit enable/disable/focus/reset,
  favorite tool disambiguation, per-tool hint silencing, tool shadowing,
  kit import via git submodule, and aggregator tree visualization.
- **`engine._get_user_config()` / `_write_user_config()`**: the config
  infrastructure foundation. Reads ``~/.dazzlecmd/config.json`` with
  per-key defaults and caching; writes atomically via temp-file +
  ``os.replace()`` with merge semantics (preserves unknown user-added
  keys). ``DAZZLECMD_CONFIG`` env var overrides the path (test isolation).
  Injects ``_schema_version: 1`` on first write; reserved for future
  migration tooling.
- **`_get_config_list()` / `_get_config_dict()`**: type-validated helpers
  that return a default (or warn to stderr) on malformed values.
- **`loader.get_active_kits(kits, user_config=None)`**: now consults the
  user config for ``active_kits``/``disabled_kits`` filtering. Legacy
  callers (no config) get all kits. Overlap rule: ``disabled_kits`` wins
  with a stderr warning.
- **`DZ_KITS` environment variable**: comma-separated kit list that
  fully overrides the config's ``active_kits``/``disabled_kits``. Empty
  string means "no kits" (meta-commands only). Distinct from unset.
- **`FQCNIndex.resolve(..., favorites=...)`**: favorites bypass precedence
  when the short name is in the favorites dict and the target FQCN exists.
  Stale favorites (target not in index) emit a warning notification and
  fall through to precedence resolution.
- **`engine._maybe_emit_reroot_hint()`** now consults
  ``silenced_hints.tools`` and ``silenced_hints.kits``. Silenced tools
  are filtered out before computing the deepest FQCN, so users can
  acknowledge individual deep tools without disabling the hint globally.
- **`engine._discover_aggregator()`** filters ``shadowed_tools`` at the
  top level after recursive merge. Shadowed tools are removed from
  ``engine.projects`` entirely — they don't appear in ``dz list``, aren't
  dispatchable, and their short names are freed for other tools.
- **`dz kit enable <name>`** / **`dz kit disable <name>`**: add/remove a
  kit from the user's active/disabled lists. Warns if the named kit is
  not among the discovered kits.
- **`dz kit focus <name>`**: shorthand for "enable this kit, disable all
  non-always_active kits except the named one." ``always_active: true``
  kits are preserved automatically.
- **`dz kit reset`**: wipes ``~/.dazzlecmd/config.json`` after confirmation.
  ``-y/--yes`` flag skips the prompt.
- **`dz kit favorite <short> <fqcn>`** / **`dz kit unfavorite <short>`**:
  pin a favorite to win short-name resolution on collision. Rejects
  reserved command names at set time. Warns if the target FQCN isn't in
  the current discovery (saves anyway; may be stale).
- **`dz kit silence <fqcn>`** / **`dz kit unsilence <fqcn>`**: per-tool
  rerooting hint silencing.
- **`dz kit shadow <fqcn>`** / **`dz kit unshadow <fqcn>`**: hide a tool
  entirely from ``dz`` dispatch. Useful when the tool exists standalone
  (e.g., ``safedel`` installed via PyPI).
- **`dz kit silenced`**: show all silenced hints, shadowed tools, and
  favorites in one view.
- **`dz kit add <url>`**: wraps ``git submodule add`` into
  ``projects/<name>`` and creates a registry pointer at
  ``kits/<name>.kit.json``. Detects nested aggregator structure and
  informs the user. Flags: ``--name``, ``--branch``, ``--shallow``.
- **`dz tree`**: visualize the aggregator tree. ASCII output by default
  (using ``+--``/``|``/``\--`` characters, no Unicode box-drawing for
  Windows codepage safety). Flags: ``--json`` for machine-readable
  structured output, ``--depth N`` to limit depth, ``--kit NAME`` to show
  only one subtree, ``--show-disabled`` to include disabled kits.
- **`dz list`** now marks tools with short-name collisions using
  ``[*]`` after the name, with a footer note explaining how to
  disambiguate.
- **`dz kit list`** now shows enabled/disabled/always_active status per
  kit in the output.
- Tests: 75 new Phase 3 tests across ``test_engine_config.py`` (28),
  ``test_cli_kit.py`` (23), ``test_cli_tree.py`` (11), plus favorites
  extension in ``test_engine_fqcn.py`` (+7) and silence/shadow extension
  in ``test_engine_recursive.py`` (+6). Full suite: 190 passing.

### Changed
- `engine.resolve_command()` now applies ``favorites`` before precedence,
  so favorites take precedence over the default kit ordering when a
  collision exists.
- `engine._discover_aggregator()` passes the user config into
  ``get_active_kits()`` only at the top level (depth 0 and ``is_root``).
  Imported child aggregators are not filtered by the parent's user
  config — they honor their own kit selection.
- Config read path is lazy: ``_config_path()`` calls ``os.path.expanduser``
  at invocation time (not module import time) so test fixtures that
  monkeypatch ``HOME`` / ``USERPROFILE`` work correctly.

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

All keys optional; missing keys fall back to defaults. Malformed values
are tolerated with a stderr warning. Unknown user-added keys are preserved
across writes.

### Design
- `private/claude/2026-04-11__07-02-02__dev-workflow-process_phase3-kit-management-and-config-write.md`
  — focused 5-axis dev-workflow analysis (config schema, command surface,
  sub-feature ordering, Phase 3/4 boundary, acceptance criteria consolidation)
- `private/claude/2026-04-11__07-15-11__phase3-decisions-and-command-surface.md`
  — user Q&A resolving the open decisions from the dev-workflow

### Versioning note
Phase 3 ships as a PATCH bump (0.7.10 -> 0.7.11) following the project
convention of treating architectural-phase work as incremental within
the current MINOR. MAJOR/MINOR bump is reserved for the completion
milestone of the architectural refactor — when `dazzlecmd-lib` extracts
(#27) and wtf-windows validates the library layering (#28).

Refs #9 (collision detection + favorites landed)
Refs #18 (kit focus/enable/disable + rerooting principle all landed)
Refs #26 (per-tool silencing and tool shadowing landed)
Related: #27 (forward pointer -- dazzlecmd-lib extraction, Phase 4)
Related: #28 (forward pointer -- wtf-windows full integration, Phase 4)

## [0.7.10] - 2026-04-11

### Changed
- **safedel Phase 8**: migrated to filekit v0.2.4 primitives, eliminating
  ~514 lines of duplicated code (commit `d5a56b3`). Pure refactor with
  zero user-visible behavior change.
  - `_save_manifest` and `save_registry` now use
    `dazzle_filekit.operations.atomic_write_json` (removes two copies of
    the tmp-write + `os.replace` idiom).
  - `_stage_regular` and `_recover_entry` directory branches now use
    `dazzle_filekit.operations.copy_tree_preserving_links` in place of
    `shutil.copytree(..., symlinks=True)`. Filekit's wrapper enforces
    `symlinks=True` and rejects reparse-point roots as defense-in-depth.
  - `_lib/preservelib/metadata.py` replaced with a 74-line re-export shim
    pointing at `dazzle_filekit.metadata` (was 883 lines of duplicated
    metadata capture/apply code). Existing
    `from preservelib.metadata import ...` call sites continue to work;
    the canonical code now lives once, in filekit.

### Added
- **safedel golden invariant test suite**
  (`tests/test_golden_invariants.py`): 17 behavioral invariant tests
  capturing safedel's end-state guarantees as a permanent regression
  safety net. Covers classification determinism, roundtrip metadata
  preservation, manifest schema stability, folder naming convention,
  dry-run invariants, list/status consistency, and platform detection.
- **safedel TODO.md and ROADMAP.md**: short-term task list and long-term
  phase strategy committed to the tool's folder. ROADMAP.md adds two new
  Design Principles:
  - Principle 8: Golden invariants over text-based goldens -- capture
    end-state properties rather than text fixtures that drift.
  - Principle 9: Defense in depth, even against our own code -- e.g.,
    `safe_delete` checks for reparse points even when the classifier
    said it's a regular directory.

### Architectural outcome
safedel now has a clean one-way dependency on filekit for primitives
and a minimal dependency on preservelib (shim only). The layering rule
documented in the integration analysis
(`2026-04-10__20-31-07__preservelib-filekit-integration.md`) is now
enforced in practice, not just on paper: filekit = primitives,
preservelib = workflow, safedel = tool.

### Test counts
- Windows: 144 passed, 7 skipped (127 pre-Phase-8 + 17 new golden
  invariants)
- WSL Ubuntu-22.04: 124 passed, 27 skipped

## [0.7.9] - 2026-04-10

### Added
- **Recursive aggregator discovery** (Phase 2): kits whose directory contains
  a `kits/` subdirectory are now treated as nested aggregators. The engine
  instantiates a child `AggregatorEngine(is_root=False)` for each, discovers
  its structure independently, namespace-remaps the returned tools, and
  merges them into the parent's project list.
- **FQCN dispatch**: every tool is addressable by its fully qualified
  collection name (`kit:namespace:tool`, e.g., `wtf:core:restarted`). Short
  names still work when unambiguous.
- **Precedence-aware resolution**: when a short name resolves to multiple
  tools, the engine picks by precedence (core wins by default) and prints
  a stderr notification showing the picked tool and alternatives. Users
  can override precedence via `~/.dazzlecmd/config.json` `kit_precedence`
  list. Silenceable via `DZ_QUIET=1`.
- `FQCNIndex` class (`engine.py`): dual-index data structure with
  `fqcn_index` (exact match) and `short_index` (candidate lookup for
  precedence resolution).
- `CircularDependencyError`: loading-stack cycle detection via
  `os.path.realpath()` keys prevents infinite recursion when an aggregator
  tree contains a cycle.
- **Rerooting hint**: nesting depth is unlimited, but when discovery
  surfaces a tool with 4+ FQCN segments the engine prints a one-time
  hint suggesting the user consider extracting that subtree as a
  standalone install (PyPI package, separate `dz`-pattern aggregator).
  This implements the *primacy* principle: any tool or aggregator can
  become its own root based on how the user wants to access it. Example:
  `dz safedel` today, `safedel` tomorrow once safedel ships standalone --
  both paths coexist. Hint is silenceable via `DZ_QUIET=1`. Per-tool
  silencing and tool shadowing deferred to #26 (Phase 3).
- `is_root=False` propagation: imported aggregators suppress meta-commands
  (`list`, `info`, `kit`, etc.) and expose only their tools.
- `_fqcn`, `_short_name`, `_kit_import_name` fields on every project dict
  for traceability and correct display.
- `dz info` now shows `FQCN` and `Kit` fields. Accepts FQCN input:
  `dz info wtf:core:locked`.
- `dz list` column changed from "Namespace" to "Kit" -- shows the actual
  import-level kit a tool came from, not the raw internal namespace.
- `dz list --kit wtf` now filters by kit import name, not raw namespace.
- Tests: 15 new recursive discovery tests (`test_engine_recursive.py`),
  24 new FQCN index/resolver tests (`test_engine_fqcn.py`), 11 one-off
  prototype tests (`tests/one-offs/test_fqcn_prototype.py`).

### Changed
- `loader.py:_scan_tool_dirs` dedupes by `(namespace, tool_name)` tuple
  instead of bare short name, preventing silent drops when recursive
  discovery introduces tools with colliding short names.
- `loader.py:discover_projects` namespace extraction uses `rsplit(":", 1)`
  to handle 3-part FQCNs like `wtf:core:restarted` (was `split(":")[0]`).
- `loader.py:discover_projects` accepts a `default_manifest` parameter so
  child engines with custom manifest names (e.g., `.wtf.json`) work.
- `loader.py:discover_kits` propagates `_override_tools_dir` and
  `_override_manifest` from registry pointers, enabling temporary
  parent-level overrides when a nested aggregator's in-repo manifest is
  missing tools_dir/manifest declarations.
- `engine.run()` dispatches tools through `resolve_command()` instead of
  `p["name"] == command_name`, enabling both FQCN and precedence-aware
  short-name dispatch.
- `kits/wtf.kit.json` temporarily declares `_override_tools_dir: "tools"`
  and `_override_manifest: ".wtf.json"` until the wtf-windows upstream
  commits these fields into its own `kits/core.kit.json` (see #28).

### Forward pointers
- Phase 3 work: kit management UI, per-tool silencing (#26),
  `dz kit enable/disable/shadow` commands, config write path.
- Phase 4 work: `dazzlecmd-lib` engine extraction as importable library
  (#27), wtf-windows full integration experiment (#28), ecosystem
  scaffolding.

### Versioning note
Phase 2 ships as a PATCH bump (0.7.8 -> 0.7.9) following the project's
convention of treating architectural-phase work as incremental within
the current MINOR. Phase 1 (AggregatorEngine, v0.7.1) set this precedent.
The MINOR/MAJOR bump is reserved for the completion milestone of the
architectural refactor -- likely when `dazzlecmd-lib` extracts (#27) and
wtf-windows validates the library layering (#28).

### Design
- 9-axis DEV WORKFLOW PROCESS analysis
  (`2026-04-10__12-15-00__dev-workflow-process_phase2-recursive-fqcn-dispatch.md`)
- Oracle agent trace of architectural history and existing dispatch code
- FQCN prototype in `tests/one-offs/` validated data structure before
  engine integration

## [0.7.8] - 2026-04-10

### Added
- safedel phase 3b: Windows creation time (ctime) restoration
  - `preservelib.metadata.restore_windows_creation_time()` using pywin32
    with `FILE_WRITE_ATTRIBUTES=0x100`, `FILE_FLAG_BACKUP_SEMANTICS` for
    directories, and readonly clear/restore handling
  - Auto-invoked by `apply_file_metadata()` on Windows recovery
  - `is_win32_available()` helper with startup warning in safedel.py when
    pywin32 is missing
- safedel phase 3b: WSL dual-path manifest storage
  - `TrashEntry.original_path_alt` field stores the cross-runtime path form
    (e.g., `/mnt/c/...` for Windows `C:\...` and vice versa)
  - `_compute_alt_path()` in _store.py converts between Windows and WSL forms
  - Recovery falls back to alt path when native path parent is unreachable
- safedel phase 3c: NTFS Alternate Data Stream detection
  - `_platform.detect_alternate_streams()` via ctypes `FindFirstStreamW`/
    `FindNextStreamW` (pywin32 doesn't expose these)
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
- safedel: `TODO.md` and `ROADMAP.md` for project planning (short-term tasks
  and long-term phase strategy). Will migrate to standalone repo when safedel
  extracts from dazzlecmd.
- safedel: `docs/USAGE.md` -- quick reference, recipes for common scenarios,
  trash store locations, protection zone behavior, platform capability matrix,
  configuration reference, and the "oh shit" first-response guide
- safedel: `docs/MANIFEST_SCHEMA.md` -- complete JSON manifest schema with
  field-by-field reference, file type values, stat + preservelib metadata
  structures, jq inspection examples, and schema evolution policy

## [0.7.7] - 2026-04-10

### Added
- safedel: per-volume trash store for zero-copy rename staging
  - `_volumes.py` module with volume detection, per-volume trash path resolution,
    and JSON registry at `~/.safedel/volumes.json`
  - Uses `unctools.detector` for drive type detection (local/network/removable)
  - Uses `dazzle_filekit.utils.disk` for disk utilities
  - Stable volume identification via serial number (not mount path)
  - Multi-store discovery: list/recover/clean scan central + all per-volume stores
  - Test isolation via explicit `registry_path` parameter to TrashStore
  - Junction to unctools at `_lib/unctools` for dev-time imports
- safedel: 14 new tests in `test_volumes.py` (104 total, up from 90)

### Fixed
- safedel: `cmd_list`/`cmd_recover`/`cmd_clean` now scan all trash stores via
  new `_resolve_folders()` helper (previously only searched central store)

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
