# Changelog -- dazzlecmd-lib

All notable changes to the `dazzlecmd-lib` package are documented here.

The library is a standalone framework for building dazzlecmd-pattern tool aggregators. Existing consumers include [dazzlecmd](https://github.com/DazzleTools/dazzlecmd) itself, [amdead](https://github.com/DazzleTools/amdead), and `wtf-windows`. The library does not require dazzlecmd to be installed; it is meant to stand alone.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/). The library is pre-1.0 and reserves the right to make breaking changes during MINOR bumps until 1.0.

The library ships co-located with dazzlecmd today (in the `packages/dazzlecmd-lib/` subdirectory of the dazzlecmd repository). Future repo extraction is tracked as item X-1 in the dazzlecmd master closeout plan; once extracted, this CHANGELOG continues unchanged in its own repo.

## [0.6.7] - 2026-05-16

Ships with dazzlecmd v0.7.45. Adds three more language templates to the bundled scaffolding set: `bash` (POSIX shell scripts), `cmd` (Windows batch files), and `binary` (pre-built executable registration). Pure template addition; no library API change. The seven-language set bundled in v0.6.6 (python, rust, node, powershell, c_cpp, docker, generic) is now ten.

### Added

- `templates/bash/.dazzlecmd.json.tmpl` + `templates/bash/{name}.sh.tmpl` -- bash scaffold with `#!/usr/bin/env bash`, `set -euo pipefail`, `$*` passthrough; `runtime.shell: "bash"`, `platforms: ["linux", "macos"]`.
- `templates/cmd/.dazzlecmd.json.tmpl` + `templates/cmd/{name}.cmd.tmpl` -- cmd scaffold with `@echo off`, `setlocal`/`endlocal`, `%*` passthrough, `exit /b 0`; `runtime.shell: "cmd"`, `platforms: ["windows"]`.
- `templates/binary/.dazzlecmd.json.tmpl` + `templates/binary/README.md.tmpl` -- binary scaffold for pre-built executables. Manifest has `runtime.type: "binary"`, `binary_path: "{name}"` (drop-in default), cross-platform metadata. README explains drop-in vs PATH-lookup vs absolute-path patterns and clarifies when to pick `binary` over `generic`.

### Refs

Ships with dazzlecmd v0.7.45.
Refs dazzlecmd #35.

## [0.6.5] - 2026-05-16

Ships with dazzlecmd v0.7.43 (closes dazzlecmd #67). Engine + cli_helpers updates so shadowed tools win short-name dispatch: `_dispatch_registry_path` attempts tool lookup before the meta-command path, and the build-time conflict warning is reworded to reflect the new precedence. See dazzlecmd CHANGELOG `[0.7.43]` for full details. CHANGELOG entry retroactively added in 0.6.6 commit.

### Changed

- `engine._dispatch_registry_path` -- tool lookup precedes meta-command lookup. Non-shadowed reserved names route to the meta-command path as before (resolve_command returns None for names without a registered tool).
- `cli_helpers.build_tool_subparsers` -- shadowed-tool warning reworded ("tool wins short-name dispatch" instead of "skipping").

### Refs

- Closes dazzlecmd #67. Ships with dazzlecmd v0.7.43.

## [0.6.6] - 2026-05-16

Ships with dazzlecmd v0.7.44 (Tier 2A.2). Bundles per-language scaffolding templates under `dazzlecmd_lib/templates/`: seven directories (`python`, `rust`, `node`, `powershell`, `c_cpp`, `docker`, `generic`) with manifest + entry-point source templates for each. Python additionally ships a `__full__/` overlay (README + pytest stub) for `dz new tool --full --language python`. No library API change; the lib continues to expose its existing `AggregatorEngine`, `FQCNIndex`, `default_meta_commands`, etc. The new content is the templates themselves.

### Added

- **Seven per-language template directories** under `src/dazzlecmd_lib/templates/`:
  - `python/` -- `.dazzlecmd.json.tmpl`, `{name_underscore}.py.tmpl`, and `__full__/README.md.tmpl` + `__full__/tests/test_{name_underscore}.py.tmpl`
  - `rust/` -- `.dazzlecmd.json.tmpl`, `Cargo.toml.tmpl`, `src/main.rs.tmpl`
  - `node/` -- `.dazzlecmd.json.tmpl`, `package.json.tmpl`, `index.js.tmpl`
  - `powershell/` -- `.dazzlecmd.json.tmpl`, `{name}.ps1.tmpl`
  - `c_cpp/` -- `.dazzlecmd.json.tmpl`, `Makefile.tmpl`, `main.c.tmpl`
  - `docker/` -- `.dazzlecmd.json.tmpl`, `Dockerfile.tmpl`
  - `generic/` -- `.dazzlecmd.json.tmpl`, `README.md.tmpl` (for tools that already exist as a binary or script)
- **Recursive package-data globs** in `pyproject.toml` so subdirectory template files ship in the wheel.

### Changed

- Templates dir layout migrated from flat (`dazzlecmd.json.tmpl` + `python_tool.py.tmpl` at the root) to per-language subdirs. Consumers calling into the new `dz new tool --language X` flow get scaffolds appropriate to X; the consumer-facing API surface (the engine, default_meta_commands, render functions) is unchanged.

### Tests

Coverage in dazzlecmd's `tests/test_cmd_new_tool_languages.py` (20 new tests). Lib-package-internal test surface remains the responsibility of the consumer (see X-1 / X-8 in the closeout plan for the dedicated lib test suite).

### Refs

Ships with dazzlecmd v0.7.44.
Companion to Tier 2A.2 work; refs #35 (`dz new` redesign).

## [0.6.4] - 2026-05-14

Ships with dazzlecmd v0.7.41 (closes dazzlecmd #65). Adds realpath-based auto-aliasing at discovery time so the same on-disk script reached via two FQCNs (junction loop, symlink, cross-embedded aggregators with shared physical files) collapses to one canonical + one auto-realpath alias. Display surfaces inherit the `[+]` marker semantics for free; dispatch via any FQCN still works.

### Added

- **`AggregatorEngine._realpath_index`** -- per-engine `{realpath: canonical_fqcn}` map populated during `_build_fqcn_index`.
- **`FQCNIndex._alias_sources`** -- side-table `{alias_fqcn: source}` where `source` is `"auto-realpath"` for realpath dedup or the virtual-kit manifest path for declared aliases. Consumed by `render_info` for accurate provenance banners.
- **`render_info` auto-realpath provenance banner** -- distinct DIM banner shown when the user dispatches via an auto-realpath alias FQCN, distinguishing it from virtual-kit alias resolutions.

### Changed

- **`_build_fqcn_index`** -- groups projects by `realpath(_dir)`; per group, shortest FQCN wins canonical (segment count then alphabetical); rest register as auto-realpath aliases. Marks demoted projects with `_auto_realpath_alias=True` and `_canonical_fqcn=<winner>`.
- **`engine.projects` filter** -- auto-realpath aliases excluded from the active dispatch list after `_build_fqcn_index`. Custom list handlers (consumer-side `_wtf_list_handler` etc.) see one project per physical script automatically without each handler needing dedup logic.
- **`_apply_virtual_kits`** -- when the virtual-kit's declared target was demoted to an auto-realpath alias, the new alias points directly at the actual canonical instead of raising KeyError. Single-hop alias invariant preserved.
- **`build_list_entries`** -- omits projects marked `_auto_realpath_alias` from canonical iteration; omits auto-realpath alias entries from alias iteration (they would otherwise render under bogus "(virtual kit '<path>')" section headers). The `[+]` marker on the canonical signals their existence.
- **`render_list` footer** -- `[+]` marker explanation updated to acknowledge both virtual-kit overlays and auto-realpath dedup.

### Fixed

- **Duplicate rows in `dz list`-class commands** when the same physical script is reachable via two FQCNs.
- **"missing canonical" warnings from virtual-kit application** when the virtual kit targets an FQCN that was demoted to an auto-realpath alias.

### Tests

Coverage in dazzlecmd's `tests/test_engine_recursive.py::TestRealpathDedup` (9 new tests). All 1068 dazzlecmd tests pass; lib-package-internal test surface remains the responsibility of the consumer (see X-1 / X-8 in the closeout plan for the dedicated lib test suite).

### Refs

Closes dazzlecmd #65.
Companion to dazzlecmd v0.7.41.

## [0.6.3] - 2026-05-13

Ships with dazzlecmd v0.7.40 (Tier 2A.1 -- closes dazzlecmd #61). Adds the rendering-side of the `long_description` mini-manpage feature -- the schema field landed in dazzlecmd v0.7.40 (scaffolding side); this surface is the rendering complement so the feature is end-to-end usable in one release.

### Added

- **`render_info` renders `long_description`** -- when the manifest's optional `long_description` field is non-empty, render a `Details:` section below the standard field rows. BOLD section header (when color enabled); body indented two spaces and wrapped to terminal width using the existing `_wrap_description` helper. Multi-line `long_description` content preserves paragraph breaks (blank lines in input render as blank lines in output).

### Tests

- +6 new in `tests/test_default_meta_commands.py::TestRenderInfoLongDescription` covering: present-renders-with-header, absent-no-block, missing-field-backward-compat, whitespace-only-no-block, wraps-to-terminal-width, multi-line-preserved.
- 1053 passed, 13 skipped (up from 1047 in dazzlecmd v0.7.39 / lib v0.6.2).

### Notes

This commit closes the rendering gap that the v0.7.40 scaffolding side would have left open. Per the cross-phase-dependencies-park-partials feedback, we ship the smallest self-sufficient slice: scaffold the field + render the field in the same release.

## [0.6.2] - 2026-05-12

Ships with dazzlecmd v0.7.39 (bug-fix patch -- closes dazzlecmd #64). Fixes a regression in `render_kit_list` that v0.6.1's honest `kit["tools"]` populate exposed, plus four hardcoded `'dz'` strings in user-facing hint and warning text that gave non-dazzlecmd consumers bad advice.

### Fixed

- **`render_kit_list` FQCN matching** (`default_meta_commands.py:1178-1207`) -- the kit-tool-to-project lookup used `ref.split(":", 1)` which only handles 2-segment refs. For multi-segment FQCNs (e.g. `dz:core:find`, `wtf:core:locked`) produced by the v0.6.1 post-recursion populate, the splitter yielded the wrong `name_part` and every tool rendered as `(not found)`. Now matches by `_fqcn` first; falls back to legacy `ns:name` parsing for backward compat. Display column shows the project's leaf name, not the full FQCN.

- **Hardcoded `'dz'` in `FQCNIndex` precedence-note** (`engine.py:412/414`) -- non-dazzlecmd consumers now see `"Use 'wtf core:locked' to be explicit"` instead of `"Use 'dz core:locked' to be explicit"`.

- **Hardcoded `'dz'` in deeply-nested-tool hint** (`engine.py:1244-1248`) -- now `"{cmd} kit silence ..."`.

- **Hardcoded `'dz'` in stale-favorite warning** (`engine.py:742-749`) -- now `"{cmd} kit favorite list"` / `"{cmd} kit favorite --remove ..."`.

- **Hardcoded `'dz'` in short-name-collision hint in `render_list`** (`default_meta_commands.py:445-447`) -- uses `getattr(engine, "command", None) or "dz"`.

### Changed

- **`FQCNIndex.__init__` signature** -- adds `command="dz"` kwarg. Backward-compatible default; engine passes `self.command` so consumer-specific messages render correctly. Legacy callers that instantiate `FQCNIndex()` directly without an engine context continue to work.

### Known deferred

- **DockerRunner image-not-found hint** (`registry.py:1200`) still emits `Try: dz setup <fqcn>`. The runner factory doesn't have `engine.command` plumbed in; fixing requires either threading the engine through or stashing command on the project at discovery. Low priority (only fires when Docker pre-flight fails).

### Tests

- +4 new (1025 total in main repo, up from 1021): 3 in `TestRenderKitList` covering FQCN-match path, leaf-name display, and legacy `ns:name` fallback; 1 in `TestRerootHint::test_hint_uses_engine_command` regression guard.

## [0.6.1] - 2026-05-12

Ships with dazzlecmd v0.7.38 (bug-fix patch -- closes dazzlecmd #63). Fixes a structural bug in `discover_kits` / `_load_in_repo_kit_manifest` that made the "aggregator-as-kit" embedding path produce wrong identity fields and a misconstructed `tools_dir`. The forward direction (dazzlecmd embeds wtf-windows) happened to work because the inner kits' declared structural fields aligned by coincidence; the inverse direction (wtf-windows embeds dazzlecmd) broke because dazzlecmd's per-kit pointers are minimal. Empirically surfaced during a recursion-proof experiment.

### Fixed

- **`_load_in_repo_kit_manifest` Pattern 2 (aggregator-as-kit)** -- `loader.py:88`. The old code picked the first inner kit file (alphabetically) and merged ALL its fields into the outer pointer, including identity fields like `name`, `tools`, `description`, `version`. The new code:
  - Detects single-kit-using-kits-subdir-convention case (exactly one inner kit, named after the outer pointer) and merges fully (legacy compatibility).
  - Detects aggregator-as-kit case (multiple inner kits OR no name-matching kit) and extracts ONLY structural hints (`tools_dir`, `manifest`) from the first non-virtual inner kit that declares them. Never identity fields.
  - Keeps `tools_dir` RELATIVE, so the engine's `_recurse_into_nested` joins it with `nested_root` correctly.
  - Returns `None` if no inner kits declare hints -- engine falls back to defaults (`tools_dir="projects"`, `manifest=".dazzlecmd.json"`).

- **`discover_kits` always sets `kit["name"]` from the registry pointer** -- `loader.py:73-83`. Identity now always comes from the registry-derived `kit_name`. Previously the kit dict's `name` field could come from an inner kit's manifest or the registry pointer depending on which Pattern-2 branch was taken. The merge accidentally hid the intended semantic.

- **`_discover_aggregator` populates aggregator-as-kit's `tools` list post-recursion** -- `engine.py:864-872`. After the nested aggregator's projects are discovered, the parent kit's `tools` field is populated with the FQCNs of contributed projects. Makes `dz kit list` show the correct tool count for embedded aggregators. Pre-v0.6.1 the count came from the buggy merge.

### Recursion proof

The "any aggregator can attach to any other" architectural claim is now **empirically validated in both directions**:

- Forward (dazzlecmd embeds wtf-windows): unchanged from v0.6.0 (no regression).
- Inverse (wtf-windows embeds dazzlecmd): `wtf list` shows all 19 dazzlecmd tools + 2 wtf own. `wtf kit list` shows `dz 22 tool(s) (always active)`. Three-tier recursion `dz:wtf:core:locked` works (wtf embeds dazzlecmd embeds wtf, with the deeply-nested-tool hint firing).

### Tests

- +5 new tests in `tests/test_library.py::TestAggregatorAsKitDiscovery` covering: pointer-name preservation in aggregator case, structural-hint extraction from inner kits, no-hints fallback to engine defaults, Pattern 1 single-kit unchanged regression guard, end-to-end engine recursion populating `kit.tools` with discovered FQCNs. Full suite 1021 passed, 13 skipped.

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
