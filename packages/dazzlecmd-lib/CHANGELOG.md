# Changelog -- dazzlecmd-lib

All notable changes to the `dazzlecmd-lib` package are documented here.

The library is a standalone framework for building dazzlecmd-pattern tool aggregators. Existing consumers include [dazzlecmd](https://github.com/DazzleTools/dazzlecmd) itself, [amdead](https://github.com/DazzleTools/amdead), and `wtf-windows`. The library does not require dazzlecmd to be installed; it is meant to stand alone.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/). The library is pre-1.0 and reserves the right to make breaking changes during MINOR bumps until 1.0.

The library ships co-located with dazzlecmd today (in the `packages/dazzlecmd-lib/` subdirectory of the dazzlecmd repository). Future repo extraction is tracked as item X-1 in the dazzlecmd master closeout plan; once extracted, this CHANGELOG continues unchanged in its own repo.

## [0.4.1] - 2026-05-07

Ships with dazzlecmd v0.7.33 (Tier 1 commit 5 of the master closeout plan).

### Added

- **`dazzlecmd_lib.paths.is_linked_project(tool_dir)`** -- cross-platform symlink/junction detection. On Windows, uses `ctypes.windll.kernel32.GetFileAttributesW` to detect the `FILE_ATTRIBUTE_REPARSE_POINT` flag (catches both symlinks AND junctions); falls back to `os.path.islink` if the ctypes call fails. On POSIX, uses `os.path.islink` directly. Public API.

- **`dazzlecmd_lib.paths.get_link_target(tool_dir)`** -- returns the resolved target of a symlink/junction, or `None` for non-links. Uses `os.readlink`. Public API.

- **`render_info` "Linked to:" display line** -- when a project's `_dir` is a symlink/junction, surfaces the link target. Library consumers (amdead, wtf-windows, sysdiagnose, future personal aggregators) get this surface for free.

### Notes

- Helpers were ported verbatim from `dazzlecmd.importer:141-168` per copy-don't-rewrite discipline. dazzlecmd's `importer` keeps the import surface stable via a back-compat re-export.

## [0.4.0] - 2026-05-07

Ships with dazzlecmd v0.7.32 (info-parity port).

### Added

- **`render_info` parity with dazzlecmd's `_cmd_info`** -- library consumers now get the full info display surface. The library `render_info` is the canonical implementation; dazzlecmd's CLI continues to use its own copy until the v0.7.34 X-22-narrow collapse.
- **`--raw` flag in `info_parser_factory`** -- shows raw manifest fields without runtime resolution.
- **`--platform` flag in `info_parser_factory`** -- previews platform-conditional dispatch resolution (`runtime.platforms` + `prefer`).
- **Runtime-dispatch helpers** -- `_RUNTIME_DISPATCH_FIELDS` constant + `_print_runtime_dispatch_fields`, `_print_runtime_resolved`, `_print_runtime_raw`, `_print_runtime_platform_preview` (private but stable).
- **Qualified-alias provenance variant** -- `render_info` shows the provenance line in two forms: standard FQCN-only and qualified-alias (`dazzletools:claude:foo` style).
- **Pass-through marker** -- `render_info` flags pass-through tools (`pass_through: true`).
- **Python deps display** -- `render_info` lists `runtime.deps` for Python tools.
- **Setup hint with `engine.command`** -- the "run setup" hint uses the consumer's command name (e.g., `amdead setup foo`, not a hardcoded `dz setup foo`).

## [0.3.0] - 2026-05-07

Ships with dazzlecmd v0.7.31 (render_list parity port).

### Added

- **`render_list` parity with dazzlecmd's `_cmd_list`** -- library consumers get the full list display: `--show {default,canonical,alias,all}` modes, sectioned virtual-kit layout with `[+]` markers (dual-presence indicator), engine-aware FQCN/alias resolution.
- **Public `build_list_entries(projects, engine, show_mode, kit_filter)`** -- data-layer API for non-dazzlecmd consumers that want to compose their own renderers without inheriting the library's display.
- **`render_tree` virtual-kit branches** -- library tree command displays virtual kits as branches alongside canonical kits.
- **`_wrap_description` helper** -- terminal-aware description wrapping for list/tree displays.

## [0.2.0] - 2026-05-06

Ships with dazzlecmd v0.7.30 (closes dazzlecmd #56 -- shadow-aware warning + discoverability).

### Added

- **Shadow-aware behavior in `render_info`** -- when a tool is shadowed by a higher-precedence registration, the info display surfaces the shadow chain so users can see what's hiding what.
- **Shadow-aware behavior in `render_tree`** -- shadowed tools are flagged in the tree display.
- **Shadow detection helpers** -- ported from dazzlecmd's CLI to give all library consumers the same shadow visibility.

## [0.1.0] - 2026-04-15

Initial extraction (dazzlecmd v0.7.13 -- Phase 4b step 1+2).

### Added

- **`AggregatorEngine`** -- configurable CLI tool aggregator with recursive kit discovery.
- **`FQCNIndex`** -- dual-index lookup (exact FQCN + short-name precedence resolution).
- **`RunnerRegistry`** -- extensible runtime dispatch (python, shell, binary, docker, etc.).
- **`ConfigManager`** -- user config read/write with atomic writes and merge semantics.
- **Kit discovery** -- manifest-driven tool/kit loading with namespace remapping.
- **Default meta-command implementations** -- `render_list`, `render_info`, `render_tree`, `render_kit_list`, `render_kit_status`, `render_version`, `render_setup` (initial versions; parity with dazzlecmd CLI grew in subsequent MINORs).
