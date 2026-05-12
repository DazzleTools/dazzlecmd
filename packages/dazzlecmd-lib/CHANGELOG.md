# Changelog -- dazzlecmd-lib

All notable changes to the `dazzlecmd-lib` package are documented here.

The library is a standalone framework for building dazzlecmd-pattern tool aggregators. Existing consumers include [dazzlecmd](https://github.com/DazzleTools/dazzlecmd) itself, [amdead](https://github.com/DazzleTools/amdead), and `wtf-windows`. The library does not require dazzlecmd to be installed; it is meant to stand alone.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/). The library is pre-1.0 and reserves the right to make breaking changes during MINOR bumps until 1.0.

The library ships co-located with dazzlecmd today (in the `packages/dazzlecmd-lib/` subdirectory of the dazzlecmd repository). Future repo extraction is tracked as item X-1 in the dazzlecmd master closeout plan; once extracted, this CHANGELOG continues unchanged in its own repo.

## [0.6.0] - 2026-05-12

Ships with dazzlecmd v0.7.37 (Tier 1 commit 9, final -- closes #49). New top-level module `dazzlecmd_lib.colors` lands a slim ANSI color taxonomy that all the default meta-command renderers consume. Consumers (dazzlecmd, amdead, wtf-windows, sysdiagnose, future personal aggregators) inherit color output on every render surface automatically -- no per-consumer wiring required.

Slim by design: 8-color ANSI palette (RESET / BOLD / DIM / RED / GREEN / YELLOW / CYAN / BRIGHT_RED), broadly supported across PuTTY, cmd.exe, PowerShell, Windows Terminal, conhost.exe with VT processing, bash, zsh, WSL. No 256-color or truecolor (RGB) codes because those break older terminals. colorama is an optional Windows-only extra; modern Windows 1511+ handles ANSI natively via `ENABLE_VIRTUAL_TERMINAL_PROCESSING` so colorama isn't required for most users. Disable color via `NO_COLOR=1` (community standard) or `DZ_COLOR=never` (project-specific). Force color through a pipe via `DZ_COLOR=always` or `FORCE_COLOR=1`.

### Added

- **`dazzlecmd_lib.colors`** -- new module. Public API: `RESET`, `BOLD`, `DIM`, `RED`, `GREEN`, `YELLOW`, `CYAN`, `BRIGHT_RED` (ANSI escape strings), `should_use_color(stream=None) -> bool` (env-aware TTY probe; precedence `NO_COLOR > DZ_COLOR=always|FORCE_COLOR > DZ_COLOR=never > stream.isatty()`), `colorize(text, *codes) -> str` (wrap text in ANSI codes terminated with RESET), `colorize_for(stream, text, *codes) -> str` (convenience wrapper combining `should_use_color(stream)` + `colorize` for explicit-stream/explicit-codes call sites), `warn(text, stream=None) -> str` (YELLOW; defaults stream to `sys.stderr`), `error(text, stream=None) -> str` (BRIGHT_RED; defaults stream to `sys.stderr`). The semantic `warn` / `error` wrappers are the recommended pattern for stderr advisories and errors; `colorize_for` and `colorize` remain available for non-standard styling. On Windows the module lazily initializes colorama; forced-color paths (`DZ_COLOR=always` / `FORCE_COLOR`) call `colorama.init(strip=False)` so ANSI bytes survive into redirected pipes (colorama's default strips them).

- **`[color]` optional extra** -- `colorama>=0.4.0` declared as a Windows-only optional dependency. Install via `pip install dazzlecmd-lib[color]` for legacy cmd.exe (codepage 437/1252) terminals. Most modern Windows installations don't need it because Win10 1511+ supports ANSI natively.

### Changed

- **`render_list`** -- section headers BOLD; virtual-kit annotation `(virtual: <vk_name>)` DIM; shadow `[*]` marker BOLD+RED; dual-presence `[+]` marker CYAN; flat-fallback header row BOLD. Column-width math handles ANSI codes correctly via a plain/styled label split.

- **`render_info`** -- alias provenance line (both qualified and standard variants) DIM; "Shadow status:" banner BOLD+YELLOW. Tool field labels stay plain (BOLD on every label would be noisy).

- **`render_tree`** -- root header BOLD; kit names BOLD; markers `[always_active]` / `[aggregator]` / `[disabled]` / `[virtual]` DIM; shadow `[shadowed]` marker BOLD+RED (consistency with `render_list`); virtual-kit alias arrows (`->`) DIM.

- **`render_kit_list`** -- kit names BOLD; `(always active)` annotation DIM; `cross-platform` platform value DIM (OS-specific values like `windows` / `linux` stay plain to stand out); `(not found)` marker DIM.

- **`render_kit_status`** -- kit names BOLD.

- **stderr warning paths in `default_meta_commands.py` and `cli_helpers.py`** -- user-facing meta-command stderr writes now use `colorize_for(sys.stderr, ...)` with YELLOW for advisories (tool-not-found, no-setup, conflicts-with-reserved) or BRIGHT_RED for errors (tree-requires-engine, kit-not-found, override-file-parse-failure, override-file-read-failure, generic setup-resolve failure). engine/loader/registry subprocess-orchestration stderr paths are intentionally untouched in this commit; sweep deferred to a follow-up so the higher-risk plumbing paths get their own attention.

### Notes

- `colors.py` is documented with detection-priority commentary in the module docstring, plus per-function docstrings showing the recommended usage patterns. The `_init_windows_ansi(force=False)` helper is module-private but documented for maintainers; `force=True` is the escape hatch for forced-color piped output on Windows.

- Test fixtures (`reset_ansi_init`, `clear_color_env`, `_TTYStream`, `_NonTTYStream`) in `tests/test_colors.py` are the recommended pattern for any future test that exercises color-detection paths.

## [0.5.0] - 2026-05-07

Ships with dazzlecmd v0.7.34 (Tier 1 commit 6 -- the X-22-narrow CLI collapse). The library reaches full byte-equivalence parity with dazzlecmd's pre-collapse `_cmd_list` / `_cmd_info` / `_cmd_tree` so dazzlecmd can collapse those commands to thin wrappers without losing any user-visible surface.

### Added

- **`tree_parser_factory --show-disabled`** -- the `dz tree` parser now accepts `--show-disabled`, matching dazzlecmd's pre-collapse CLI parser. Library consumers (amdead, wtf-windows, sysdiagnose, future personal aggregators) inherit the flag automatically.

- **`render_tree` engine-aware tree behaviors** -- when `args.show_disabled` is set, the function uses `engine.all_projects` in place of the supplied `projects`. Kit headers render `[always_active]` / `[aggregator]` / `[disabled]` markers, computed from `engine.kits` (always_active flag, presence of a nested `kits/` subdir) and from `engine._get_user_config()` (`active_kits` / `disabled_kits`). Virtual-kit headers also render `[disabled]` when the kit's state computes as disabled. JSON output gains `always_active`, `is_aggregator`, and `state` keys per kit.

### Changed

- **`render_info` "tool not found" message** -- now `f"Tool '{tool_name}' not found. Use '{engine.command} list' to see available tools."` printed to stdout. Previously the message was `f"Tool {tool_name!r} not found. Run 'list' to see available tools."` printed to stderr. The new wording uses the consumer's command name (so amdead users see `Use 'amdead list' to see available tools.` rather than a bare `list` hint), and prints to stdout to match dazzlecmd's pre-collapse CLI behavior. Behavior change for any consumer that was relying on the message going to stderr or the exact prior wording. Justified for v0.5.0 because both consumers (amdead, wtf) get a more useful message and the pre-1.0 lib version policy permits the minor wording change.

### Notes

- `render_tree` and `render_info` were ported from dazzlecmd's `cli.py` (lines 2098-2312 and 1119-1220 respectively) per copy-don't-rewrite discipline. The dazzlecmd CLI's `_cmd_tree` then collapsed to a thin wrapper calling `render_tree`. Same pattern as the v0.4.0 (info-parity port) and v0.4.1 (link-helpers port) commits.

- The library's `_wrap_description` is now also imported by dazzlecmd's `cli.py` as a back-compat shim (the remaining consumer is `_cmd_kit_list`'s virtual-kit listing path; Category C, deferred to a future X-22-full collapse).

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
