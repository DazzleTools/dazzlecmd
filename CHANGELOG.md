# Changelog

All notable changes to dazzlecmd are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/).

## [0.7.21] - 2026-04-18

### Added

- **Docker runtime type (Phase 4c.4)**. New `runtime.type: "docker"` dispatches
  tools via `docker run`. Manifest fields: `image` (required), `volumes`,
  `env`, `env_passthrough`, `docker_args`, `inner_runtime` (informational).
  Pre-flight `docker images -q <image>` check runs before dispatch; on miss,
  surfaces `Error: Docker image 'X' not found locally. Try: dz setup <fqcn>`
  with exit 1. Engine NEVER pulls or builds images -- the tool's declared
  `setup.command` is responsible. `make_docker_runner` in
  `dazzlecmd_lib.registry`. Closes the last Phase 4c runtime-type gap.
- **Conditional dispatch + `_vars` compose with Docker for free**: authors
  can declare `platforms.linux.image: "myimg:amd64"` vs
  `platforms.darwin.image: "myimg:arm64"`, OR `_vars: {tag: "1.0"}` + `image:
  "{{registry}}/{{tool}}:{{tag}}"`. The shared substrate established in
  v0.7.19/v0.7.20 handles both without Docker-specific code.
- **Docker-compatible engines work without code changes**: any CLI providing
  a docker-compatible binary (Docker, Podman via alias, Colima, Rancher
  Desktop, OrbStack, nerdctl) works. Engine abstraction via a dedicated
  `engine_cmd` field is deferred until demand emerges.
- **Synthetic Docker fixture at `tests/fixtures/docker_tool/`**: real
  Dockerfile + Python ENTRYPOINT + manifest using `_vars` + `env_passthrough`.
  Builds a ~84MB image (`dazzlecmd-test-docker-tool:v1`) on first test run.
  Integration test suite at `tests/test_docker_integration.py` (marked
  `@pytest.mark.docker_integration`, opt-in via skip-if-no-docker) creates
  the image, dispatches via the runner, asserts on a structured report the
  container emits. 8 tests cover image build, image substitution,
  runner-captures-output, env dict delivery, env_passthrough forwarding,
  passthrough-skips-missing-vars, container hostname isolation, exit code
  propagation.
- **`RunnerRegistry.reset()` classmethod + autouse conftest fixture**
  (Phase 4c.6). Reinstalls built-in factories after every test; drops any
  extension-registered types. Prevents test pollution when tests register
  custom runtime types. `docker_integration` pytest marker registered in
  `pyproject.toml` with auto-skip when `docker` binary is absent.
- **`dz setup` no-arg listing mode polish** (closes issue #33 listing-mode
  criterion). Detection now catches tools with ONLY `setup.platforms.*`
  declared (no top-level `setup.command`). Output sorted alphabetically by
  FQCN; dynamic column width (floor 20, ceiling 50 chars); missing notes
  show as `-`. 9 tests in `tests/test_cli_setup.py`.
- **`docs/guides/dz-setup.md`** -- new CLI reference file mirroring
  `dz-kit.md` / `dz-tree.md` pattern. Covers `dz setup` usage, platform
  resolution, `_vars` template integration, error cases, and the "what the
  engine will NOT do" boundary. Satisfies #33's docs criterion.
- **`docs/guides/manifests.md` Docker Tool section** -- schema, dispatch
  pattern, pre-flight check, conditional dispatch + `_vars` examples,
  docker-compatible engines note, NOT-supported list, reference fixture
  pointer.
- **43 new automated tests** (+ full suite 668 passing, 6 platform-skipped):
  - `test_docker_runner.py` (19) -- mocked argv construction, pre-flight,
    volumes, env, env_passthrough, docker_args, inner_runtime informational,
    exit code propagation, `_vars` substitution
  - `test_docker_integration.py` (8) -- real-Docker end-to-end
  - `test_cli_info.py` (+7) -- Docker field rendering in `--raw` and resolved
    views
  - `test_cli_setup.py` (+9) -- listing mode polish

### Changed

- `_cmd_setup` no-arg listing branch replaced with the polished version
  (sorted, dynamic column width, platforms-only tool detection).
- `_print_runtime_dispatch_fields` extended with Docker-specific rendering
  (Image, Volumes, Env, Env passthru, Docker args, Inner runtime).

### Notes

- Issue #30 (Phase 4 epic) advances: Phase 4c.4 complete; Phase 4c.6 (registry
  test isolation) complete. Phase 4c is now fully shipped.
- Issue #33 (dz setup) -- listing-mode and docs criteria closed; first-run
  detection stays deferred.
- Issue #22 (Per-tool runtime environment) -- already closed v0.7.20 Option
  B; Option A (`runtime.venv` shorthand) remains parked.
- Three new tracking issues filed for future phases:
  - #42 Test matrix / cross-environment testing substrate
  - #43 VM-based runtime type complementing Docker
  - #44 Kit sandbox: user-policy-driven container/VM isolation

Refs #30 (Phase 4c.4 + 4c.6 checkboxes flipped in epic)
Refs #33 (listing mode + docs criteria closed)
Refs #42 (test matrix -- future; docker substrate reusable)
Refs #43 (VM runtime -- future; complements this work)
Refs #44 (kit sandbox -- future; built on this substrate)

## [0.7.20] - 2026-04-17

### Added

- **Template variables (`_vars`) for setup and runtime manifests** (issue #41).
  Declare shared command fragments at manifest-top, block level (`setup._vars`,
  `runtime._vars`), platform level, or subtype level; reference via
  `{{name}}` in any string field. Four-tier scope chain with lexical
  declaration and dynamic lookup -- enables per-platform override of
  ingredients in composite variables without redefining the composite.
  Nested references supported (variable values may contain `{{...}}`) with
  cycle detection and max-depth guard. Unresolved references raise
  `UnresolvedTemplateVariableError` with a list of available vars at the
  error site. Syntax `{{var}}` (whitespace `{{ var }}` tolerated); identifier
  rule `[A-Za-z_][A-Za-z0-9_]*`; case-sensitive. Values are strings only in
  v1; list/dict deferred. Implementation in
  `dazzlecmd_lib.templates` (40 unit tests); integration in
  `resolve_setup_block` and `resolve_runtime` (18 integration tests).
  Substitution runs BEFORE prefer iteration so precondition checks
  (`shutil.which`, `os.path.isfile`) see substituted values.
- **Setup schema parity with runtime.** `setup.platforms` now accepts the same
  nested-dict shape that `runtime.platforms` established in v0.7.19:
  `setup.platforms.<os>.<subtype>` with `general` fallback. Resolution goes
  through the shared `platform_resolve.resolve_platform_block` helper so subtype
  chaining behaves identically between setup and runtime.
- **Flat-string shorthand retained** for simple single-command installs per OS:
  `"platforms": {"linux": "apt install foo"}` is normalized to
  `{"command": "apt install foo"}` at resolution time. Canonical dict form is
  required for subtypes and future features (multi-step, detect_when).
- **`setup._schema_version`** checked on load via
  `schema_version.check_schema_version`. Un-versioned blocks default to "1"
  for backwards compatibility.
- **New shared library module `setup_resolve.py`** exports
  `resolve_setup_block(project) -> dict | None`. Mirrors `resolve_runtime()`
  in registry.py. Issue #40's multi-platform setup work will extend this
  module with `steps`, `detect_when`, user-override loading, and PR-back
  without the cli layer changing shape.
- **Python runner honors `runtime.interpreter`** (closes 4b.3 of #22).
  When declared, `make_python_runner` dispatches via
  `subprocess.run([interpreter, script, *argv])` instead of importlib.
  Enables per-tool venvs (`.venv/Scripts/python.exe`), alternative Pythons
  (`python3.11`), and arbitrary python binaries. Relative interpreter paths
  with a separator resolve against the tool directory; bare names rely on
  subprocess PATH lookup; env-var-prefixed paths (`$VAR`, `%VAR%`) pass
  through unchanged. `pass_through: true` preserved as legacy path.
- **Synthetic venv stress-test fixture** at `tests/fixtures/venv_exercise/`
  with 7 heavy real deps (numpy, pandas, requests, rich, pyyaml, click,
  pydantic). End-to-end integration test in
  `tests/test_venv_integration.py` creates the venv, runs setup, dispatches
  via the venv interpreter, asserts all imports pass and that the reported
  interpreter is the venv (not the test runner's). Marked
  `@pytest.mark.venv_integration`.
- **Documentation**: `docs/guides/manifests.md` Setup section rewritten to
  cover both flat-string and nested-dict forms, resolution order, subtype
  rules, and the venv-per-tool pattern.
- 102 new automated tests (25 in `test_setup_resolve.py`, 15 in
  `test_python_runner_interpreter.py`, 4 in `test_venv_integration.py`,
  40 in `test_templates.py`, 18 in `test_vars_integration.py`).
  Full suite: 616 passing, 6 platform-skipped (up from 514).

### Changed

- `_cmd_setup` now resolves via the shared `resolve_setup_block` preprocessor
  instead of the hand-rolled platform selection. Error messages include the
  current `<os>.<subtype>` tag and actionable hints for which manifest keys
  to add.
- The "Setup" section in `docs/guides/manifests.md` -- previously a one-line
  reference plus a "future #40" footnote -- now documents both schemas with
  worked examples and the venv-per-tool composition pattern. The "future"
  footnote for nested platforms is removed; #40 retains scope for
  multi-step, `detect_when` at setup, user-override loading, and PR-back.

### Notes

- **4b.3 (python runner `runtime.interpreter`, #22) closed.** Partial status
  carried from Phase 4b through Phase 4c; closed this release with the
  synthetic fixture validating the end-to-end flow. No in-repo tool currently
  requires venv isolation; the pattern is available for tools that need it.
- **Ecosystem pilot (real-tool venv migration) deferred.** `claude-sesslog-datefix`
  was considered but rejected -- its rare-use-fix UX doesn't benefit from
  forcing `dz setup` friction. Unblock condition: a tool authored with genuine
  version-isolation needs (ML tooling, Windows COM interop with pinned
  pywin32, etc.) should migrate first.
- **v0.7.19 human test checklist gaps fixed** (HV.2 setup instructions use
  manual kit-file creation rather than `dz kit add <path>` which only accepts
  git URLs; HV.5 replaced the non-existent `wtf` tool reference with
  `restarted` and `locked`).
- **No in-repo tool uses flat-string `setup.platforms.<os>` today**
  (verified: zero matches of `"setup":` across `projects/` and `kits/`).
  The shorthand form is retained for author ergonomics; zero-migration-risk
  promise for third-party kits arriving later.

Refs #30 (Phase 4 epic -- 4b.3 closed, setup parity unlocks #40 groundwork)
Refs #22 (Python runner interpreter support -- closed)
Refs #40 (shared setup_resolve.py scaffolds the multi-platform setup expansion)
Refs #41 (template variables `_vars` base implementation -- extensions tracked for future)

## [0.7.19] - 2026-04-17

### Added

- **Conditional dispatch (`runtime.platforms` + `runtime.prefer`).** A single
  manifest can now express different dispatch behavior per platform and
  declare ordered alternatives when multiple implementations are viable.
  `runtime.platforms.<os>.<subtype>` overrides the base runtime for the
  matching host; `runtime.prefer` is an ordered array of dispatch
  alternatives whose first viable entry is selected. Inferred preconditions
  (interpreter on PATH, script file exists, npx/npm available) gate each
  prefer entry. Optional `detect_when` structured matchers provide explicit
  gating beyond the inferred preconditions.
- **Seven shared library modules in `dazzlecmd-lib`** forming the substrate
  for both runtime conditional dispatch (this release) and multi-platform
  setup (issue #40, forthcoming):
  - `platform_detect` -- `PlatformInfo` dataclass + cached `get_platform_info()`
    with optional `distro` dependency and stdlib fallback via `/etc/os-release`.
    Detects Linux/Windows/macOS/BSD/WSL with normalized OS names, subtypes,
    and architectures.
  - `conditions` -- `detect_when` evaluator with six leaf matchers
    (`file_exists`, `dir_exists`, `env_var`, `env_var_equals`,
    `command_available`, `uname_contains`) and two combinators (`all`,
    `any`). Env var values are never logged. `_`-prefixed keys are metadata.
  - `platform_resolve` -- `resolve_platform_block` (subtype fallback:
    `<subtype>` -> `general` -> base) and `deep_merge` (arrays REPLACED, not
    concatenated).
  - `resolution_trace` -- `ResolutionAttempt` + `ResolutionTrace` dataclasses
    used to build structured diagnostic output when a resolution fails.
  - `paths` -- cross-platform helpers: `resolve_relative_path` (generalizes
    the v0.7.18 shell_env fix), `ensure_windows_executable_suffix`,
    `translate_wsl_path`, `which_with_pathext`.
  - `schema_version` -- `CURRENT_SCHEMA_VERSION`, `SUPPORTED_SCHEMA_VERSIONS`,
    `get_schema_version`, `check_schema_version`. Un-versioned manifests
    default to version "1" for backwards compat.
  - `user_overrides` -- groundwork for per-user override files. Honors
    `DAZZLECMD_OVERRIDES_DIR`, defaults to `~/.dazzlecmd/overrides/`. FQCN
    `:` characters translate to `__` on disk. Runtime does not yet call
    `load_override` at dispatch time; issue #40 becomes the first production
    caller.
- **`resolve_runtime()` preprocessor in `registry.py`.** Every
  `RunnerRegistry.resolve()` call now passes the project through
  `resolve_runtime` first, applying platforms merge + prefer iteration
  before the runner factory sees the project. Runners stay dumb; the
  resolver owns the platform logic. `NoRuntimeResolutionError` surfaces a
  full trace (platform info, each tried entry, reason for each failure,
  actionable fix hint) when no entry matches.
- **`dz info --raw` and `dz info --platform SPEC` flags.**
  - Default `dz info <tool>` now shows the runtime resolved for the current
    host. Tools without `platforms`/`prefer` render identically to v0.7.18.
  - `--raw` shows the manifest as declared, with `platforms` and `prefer`
    arrays enumerated.
  - `--platform <spec>` (e.g., `linux.debian`, `windows`, `macos.macos14`)
    previews platform-level resolution for a host you may not own. `prefer`
    entries are enumerated without evaluating preconditions (since the
    current host's PATH isn't the target platform's).
- **213 new automated tests** across nine test files, organized by module
  concern. Full suite: 511 passing, 6 platform-skipped (up from 298).
- `docs/guides/manifests.md` gains a "Conditional Dispatch" section with
  worked examples for `platforms`, `prefer`, `detect_when`, and the three
  inspection modes.
- Human test checklist at
  `tests/checklists/v0.7.19__Phase4c-5__conditional-dispatch.md`.

### Changed

- `RunnerRegistry.resolve(project)` now runs `resolve_runtime(project)`
  first. Existing manifests without `platforms`/`prefer` take a fast path
  and behave identically; manifests that declare conditional dispatch
  receive the effective block.
- `_print_runtime_*` helpers extracted from `_cmd_info` for reuse across
  the three display modes.

### Notes

- Conditional dispatch ships as the first feature built on the shared
  library substrate. Issue #40 (multi-platform setup) is the second
  consumer and will reuse `platform_detect`, `conditions`,
  `platform_resolve`, `resolution_trace`, and `user_overrides` unchanged.
- The design explicitly preserves the "dumb dispatcher" principle: authors
  declare intent (what runs where, in what preference order); the engine
  faithfully evaluates and picks. No auto-detection beyond what the
  manifest declares.
- Schema version 1 is the current and only supported version. Future
  breaking changes to the manifest schema will bump the supported version
  set and land alongside a migration hook.
- All error messages preserve the "env var values are never logged"
  security invariant. Conditions checking secret-bearing env vars surface
  presence/absence only.

Refs #30 (Phase 4c polish), #40 (setup sibling uses the same shared modules)

## [0.7.18] - 2026-04-17

### Fixed
- **Bug 1 (shell runner cmd `shell_env` env propagation)**: cmd's
  `source_template` now prefixes invoked env scripts with `CALL`. Without
  it, chaining `env.cmd && tool.bat` with cmd's `&&` runs each as a
  separate child process and env vars set in `env.cmd` never reach
  `tool.bat`. This silently broke the advertised `dazzle_env.cmd`
  pattern. Change: one-line update to `SHELL_PROFILES["cmd"]
  ["source_template"]`.
- **Bug 2 (node runner TS-without-interpreter error ordering)**: the
  `.ts`-requires-explicit-interpreter check in `make_node_runner` now
  fires before the file-existence check. Previously, declaring a `.ts`
  `script_path` without an `interpreter` field would produce the generic
  "Script not found" error when the file didn't exist yet (common during
  tool authoring), instead of the actionable TypeScript-specific message.
- **Shell runner `shell_env.script` path resolution**: relative paths in
  `shell_env.script` now resolve against the tool directory (consistent
  with `runtime.script_path` semantics). Absolute paths and
  env-var-prefixed paths (`%USERPROFILE%`, `$HOME`) pass through
  unchanged so the shell handles expansion. Previously, relative paths
  were resolved against the caller's cwd, which failed for most real
  invocations.

### Added
- 5 new regression tests in `tests/test_registry.py` covering:
  - `TestShellEnvChaining::test_cmd_shell_env_uses_CALL_prefix`
  - `TestShellEnvChaining::test_shell_env_relative_path_resolved_to_tool_dir`
  - `TestShellEnvChaining::test_shell_env_absolute_path_unchanged`
  - `TestShellEnvChaining::test_shell_env_env_var_path_unchanged`
  - `TestNodeTypeScriptRejectsWithoutInterpreter::test_ts_check_fires_before_file_existence`

### Notes
- Fixes identified by tester agent run against the v0.7.15-v0.7.17
  checklists after those commits landed. No functional regressions found
  in the binary polish (v0.7.15) or node runtime (v0.7.17); all three
  issues in this patch are in the shell runner (v0.7.16) and node runner
  (v0.7.17).
- Conditional dispatch (originally planned as v0.7.18) shifts to v0.7.19
  to keep bug fixes segregated from new features.

Refs #30 (Phase 4c polish)

## [0.7.17] - 2026-04-16

### Added
- **Phase 4c.3 node runtime type** — dedicated `runtime.type: "node"` for
  the Node.js / npm / TypeScript ecosystem. Three mutually-exclusive
  dispatch modes:
  - **`script_path`** — dispatch via `[interpreter, <subcommand?>, args..., script, argv]`
  - **`npm_script`** — dispatch via `npm run <script> -- <argv>`
  - **`npx`** — dispatch via `npx <package> <argv>` (downloads package on first use)
- **`NODE_INTERPRETERS` profile dict** supporting 5 JS interpreters:
  `node`, `tsx`, `ts-node`, `bun`, `deno`. Bun and deno auto-insert the
  `run` subcommand; others use no subcommand. Unknown interpreters fall
  through with a stderr warning.
- **`runtime.interpreter`** (for `.js`/`.ts`) — pick which interpreter
  runs the script. Defaults to `node` for `.js`. Required for `.ts`/`.tsx`/
  `.mts`/`.cts` files (fails loudly if absent — no auto-detection of
  TypeScript runner preference, user picks).
- **`runtime.interpreter_args`** — flags placed between interpreter (and
  its subcommand, if any) and the script. Enables `deno --allow-read`,
  `node --max-old-space-size=4096`, `bun --watch`, etc.
- **Script runner `interpreter_args`** — same field added to
  `runtime.type: "script"`. Unblocks `cscript //Nologo //B tool.js`
  (Windows JScript/WSH), `perl -w -T tool.pl`, `ruby -r tool.rb`, etc.
- **Mutual exclusion** for node dispatch modes — declaring multiple
  (script_path + npm_script, etc.) errors loudly with a list of declared
  modes. None declared also errors.
- `dz info` displays `Interp args:`, `NPM script:`, `Npx:` fields when
  declared on a node-type tool.
- 28 new tests in `tests/test_registry.py` covering node profile
  dispatch, interpreter_args placement, TypeScript-rejection-without-
  interpreter, npm_script argv shape, npx argv shape, mutual exclusion,
  script runner interpreter_args, and real-subprocess integration
  (auto-skipped when node/bun/deno absent).
- New pytest markers: `node`, `bun`, `deno`, `tsx`, `ts_node`, `npm`,
  `npx`. Auto-skip via conftest `shutil.which` checks.
- Test fixtures in `tests/fixtures/node/`: `hello.js`, `hello.ts`,
  `check_args.js`, `package.json`.

### Changed
- Treatment of npx **aligned with other package-manager invocations**
  (no special gate or warning). `npx` downloading a package on first
  use is structurally identical to `pip install` in `setup.command`,
  `cargo install` in `dev_command`, etc. The security model is
  "listing is safe; dispatch is user-opted-in" — applies uniformly
  across all runtimes and package managers.

### Deferred
- `runtime.platforms` per-platform dispatch override → v0.7.18
  (micro-commit, ~30 LOC)
- Platform gating enforcement (`platform: "windows"` filters list/dispatch)
  → Phase 5

Refs #30 (Phase 4c.3 -- node runtime type: NODE_INTERPRETERS, script_path/npm_script/npx dispatch modes, interpreter_args)
Related: #39 (trust model — npx treatment reaffirms "no special treatment per runtime; class-level capability metadata deferred")

## [0.7.16] - 2026-04-16

### Added
- **Phase 4c.2 shell runner enhancements** — per-shell dispatch profile
  table (`SHELL_PROFILES` in `registry.py`) supporting 7 shells: `cmd`,
  `bash`, `sh`, `zsh`, `csh`, `pwsh`, `powershell`. Replaces the
  previous 3-branch `if/elif` in `make_shell_runner`.

  Scripting-language interpreters (perl, ruby, lua, etc.) are
  deliberately NOT in the shell profile table — they lack shell
  semantics (no chain operators, no source syntax, no interactive
  keep-open). Use `runtime.type: "script"` with `interpreter: "perl"`
  (or ruby/lua/etc.) for those. The shell runner errors loudly with
  a pointer to the correct runtime type when a non-shell interpreter
  is declared as `shell:`.
- New manifest fields under `runtime` for shell-type tools:
  - **`shell_args`** (list): flags inserted between shell and script.
    Replaces default flags when present. Supports patterns like
    `["/E:ON", "/V:ON", "/c"]` for cmd extensions + delayed expansion,
    `["-NoProfile", "-ExecutionPolicy", "Bypass"]` for pwsh, or
    `["--login"]` for bash.
  - **`shell_env`** (dict `{script, args}`): environment-setup script
    chained before the tool via the shell's canonical source syntax
    (`source` for bash/zsh, `.` for sh/pwsh/powershell, direct
    invocation for cmd/csh). Covers patterns like `dazzle_env.cmd`
    that require VS vcvarsall, PATH setup, etc. Fails loudly for
    shells that don't support env chaining (e.g., `perl`).
  - **`interactive`** (bool or `"exec"`, default `false`): keeps the
    shell open after the tool runs (cmd `/k`, pwsh `-NoExit`). Value
    `"exec"` uses `os.execvp` to fully hand off the dz process to the
    shell — enables agentic-task scenarios where dz spawns a shell
    environment for continued interaction. Shells without interactive
    support (`sh`, `csh`, `perl`) error loudly when requested.
- `dz info` displays shell-type fields (`Shell:`, `Shell args:`,
  `Shell env:`, `Interactive:`) when declared in the manifest.
- 19 new shell runner tests in `tests/test_registry.py` covering
  profile dispatch, shell_args replacement, env chaining semantics,
  interactive modes (including exec handoff via mocked `os.execvp`),
  and per-shell edge cases (perl rejection, sh/csh interactive rejection).
- Real-subprocess integration tests with auto-skip markers:
  `shell_cmd`, `shell_bash`, `shell_pwsh`, `shell_zsh`, `shell_csh`,
  `shell_perl`, `shell_env`, `shell_interactive`, `shell_exec`.
  `tests/conftest.py` provides per-runner auto-skip via `shutil.which`.
- Shell test fixtures in `tests/fixtures/shells/`:
  `hello.{sh,bat,ps1}`, `env_setup.{sh,cmd,ps1}`, `check_env.{sh,bat,ps1}`.

### Changed
- `make_shell_runner` in `dazzlecmd_lib/registry.py` rewritten from 27
  lines of hardcoded if/elif branching to ~120 lines of profile-driven
  dispatch. Zero existing shell-type tools in the repo were affected
  (grep confirmed pre-migration). No backward-compat shim needed.

Refs #30 (Phase 4c.2 -- shell runner enhancements)
Refs #22 (runtime shell fields align with interpreter dispatch model)

## [0.7.15] - 2026-04-15

### Changed
- **Binary runner `dev_command` polish**: documented dispatch precedence
  (binary exists -> run it; binary missing + dev_command -> fallback;
  FORCE_DEV -> always dev_command). Added `DAZZLECMD_FORCE_DEV=1` env
  var override for active development workflows (e.g., always use
  `cargo run` even when the release binary exists).
- `dz info` now shows `Binary:` (instead of `Script:`) for binary
  runtime tools, plus `Dev command:` and `Interpreter:` fields when
  declared in the manifest.

### Added
- 11 new registry tests (`tests/test_registry.py`): binary runner
  dispatch precedence, FORCE_DEV override, arg forwarding, registry
  resolution.

Refs #30 (Phase 4c.1 -- binary runner polish)

## [0.7.14] - 2026-04-15

### Added
- **`dz setup <tool>`** command: runs a tool's declared setup script.
  Platform-aware (reads `setup.platforms` for cross-platform variants).
  `dz setup` without a tool lists tools with setup commands. `dz info`
  now surfaces setup notes when declared. The engine never installs
  dependencies -- it dispatches what the tool author declares.
- `lifecycle` field in `dz new` scaffolding now includes `type: "tool"`
  and `created_as: "tool"` alongside `status`, for Phase 5 entity
  promotion tracking. The library JSON template mirrors this.
- Human test checklist:
  `tests/checklists/v0.8.0__Phase4b-addendum__templates-setup-lifecycle.md`

### Changed
- Tool scaffolding templates moved from `src/dazzlecmd/templates/` to
  the library at `packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/`.
  The CLI resolver prefers the library location and falls back to the
  local path if the library is not installed. `package_data` in the
  library's `pyproject.toml` ensures the templates ship with the wheel.
- `dz --help` commands section now lists `tree` and `setup` alongside
  the other meta-commands (`_build_categorized_help` was out of sync
  with the actual subparser registration).

Refs #27 (dazzlecmd-lib extraction -- templates + dz setup landed; PyPI, tutorial, examples, wtf adoption still open)
Refs #33 (dz setup core implemented; first-run detection, automated tests, docs deferred)
Refs #30 (Phase 4b Step 3 complete; interpreter field and multi-language templates still open under 4b)

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

Refs #27 (dazzlecmd-lib extraction -- core modules extracted)
Refs #32 (runner registry implemented)
Refs #30 (Phase 4b Step 1+2)

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
