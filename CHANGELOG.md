# Changelog

All notable changes to dazzlecmd are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/).

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

[Unreleased]: https://github.com/DazzleTools/dazzlecmd/compare/v0.7.48...HEAD
[0.7.42]: https://github.com/DazzleTools/dazzlecmd/compare/v0.7.41...v0.7.42
[0.7.41]: https://github.com/DazzleTools/dazzlecmd/compare/v0.7.40...v0.7.41
[0.7.40]: https://github.com/DazzleTools/dazzlecmd/compare/v0.7.39...v0.7.40
[0.7.39]: https://github.com/DazzleTools/dazzlecmd/releases/tag/v0.7.39
