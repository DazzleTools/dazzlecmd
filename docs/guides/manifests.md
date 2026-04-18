# Manifest Reference

Every dazzlecmd tool has a `.dazzlecmd.json` manifest that describes how to discover, load, and run it.

## Full Schema

```json
{
    "name": "tool-name",
    "version": "0.1.0",
    "description": "What the tool does",
    "namespace": "core",
    "language": "python",
    "platform": "cross-platform",
    "platforms": ["windows", "linux", "macos"],
    "runtime": {
        "type": "python",
        "entry_point": "main",
        "script_path": "tool_name.py",
        "shell": "bash",
        "interpreter": "python"
    },
    "pass_through": false,
    "dependencies": {
        "python": ["requests>=2.28"],
        "python_optional": ["dazzle-filekit", "unctools"]
    },
    "source": {
        "type": "local",
        "path": "/path/to/source",
        "url": "https://github.com/org/repo",
        "added_at": "2026-01-15T10:30:00Z"
    },
    "taxonomy": {
        "category": "file-tools",
        "tags": ["utility", "files", "rename"]
    },
    "lifecycle": {
        "status": "active"
    }
}
```

## Field Reference

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Tool name (used as the command: `dz <name>`) |

### Identity

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `version` | string | `"0.0.0"` | Semantic version |
| `description` | string | `""` | One-line description (shown in `dz list`) |
| `namespace` | string | (from directory) | Kit namespace (e.g., `core`, `dazzletools`) |
| `language` | string | `"python"` | Primary language |

### Platform

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `platform` | string | `"cross-platform"` | Quick-glance platform support |
| `platforms` | string[] | - | Specific verified platforms: `windows`, `linux`, `macos`, `bsd` |

### Runtime

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `runtime.type` | string | `"python"` | Runtime type: `python`, `shell`, `script`, `binary` |
| `runtime.entry_point` | string | `"main"` | Function name to call (Python tools) |
| `runtime.script_path` | string | - | Path to the script file (relative to tool directory) |
| `runtime.shell` | string | `"bash"` | Shell for `shell` runtime: `bash`, `cmd`, `pwsh` |
| `runtime.interpreter` | string | `"python"` | Interpreter for `script` runtime |
| `pass_through` | boolean | `false` | If true, run via subprocess instead of import |

### Dependencies

| Field | Type | Description |
|-------|------|-------------|
| `dependencies.python` | string[] | Required pip packages |
| `dependencies.python_optional` | string[] | Optional pip packages (graceful fallback) |

### Source (for imported tools)

| Field | Type | Description |
|-------|------|-------------|
| `source.type` | string | `local`, `remote`, `submodule` |
| `source.path` | string | Local filesystem path (for dev mode) |
| `source.url` | string | Remote git URL (for submodule mode) |
| `source.added_at` | string | ISO timestamp of when the tool was imported |

### Taxonomy

| Field | Type | Description |
|-------|------|-------------|
| `taxonomy.category` | string | Tool category (e.g., `file-tools`, `dev-tools`, `network`) |
| `taxonomy.tags` | string[] | Searchable tags |

### Lifecycle

| Field | Type | Description |
|-------|------|-------------|
| `lifecycle.status` | string | `active`, `deprecated`, `experimental` |

### Setup

Declares how to install or initialize the tool's dependencies. The engine does
not install dependencies itself -- it dispatches the tool's own setup command.
Run via `dz setup <tool>`.

| Field | Type | Description |
|-------|------|-------------|
| `setup.command` | string | Default shell command for platforms not explicitly overridden. |
| `setup.note` | string | Human-readable description shown by `dz info` and `dz setup` before execution. |
| `setup.platforms` | object | Per-platform command overrides. Keys: `windows`, `linux`, `macos` (alias `darwin`), `bsd`, `other`. Values are strings (shorthand) or dicts (with `command`, optional `note`, optional subtype sub-dicts). |
| `setup._schema_version` | string | Schema version. Un-versioned manifests default to `"1"`. |

The setup command runs via `subprocess.run(cmd, shell=True, cwd=tool_dir)`, so
shell operators (`&&`, `;`, pipes) are interpreted by the host shell.

#### Flat-string shorthand (v0.7.20+)

For simple single-command installs per OS, write the command as a **string**:

```json
{
    "setup": {
        "command": "pip install -r requirements.txt",
        "platforms": {
            "windows": "python -m pip install -r requirements.txt",
            "linux": "python3 -m pip install -r requirements.txt"
        }
    }
}
```

String values are normalized to `{"command": <string>}` at resolution time.

#### Nested-dict form (canonical, v0.7.20+)

When you need subtypes (`debian` vs `rhel`), per-platform notes, or future
features (multi-step `steps`, structured `detect_when`), use the **dict** form:

```json
{
    "setup": {
        "command": "pip install -r requirements.txt",
        "platforms": {
            "linux": {
                "debian":  {"command": "sudo apt install -y python3-pip && pip3 install -r requirements.txt"},
                "rhel":    {"command": "sudo dnf install -y python3-pip && pip3 install -r requirements.txt"},
                "general": {"command": "python3 -m pip install -r requirements.txt"}
            },
            "windows": {"command": "python -m pip install -r requirements.txt"},
            "macos":   {"command": "brew install python3 && python3 -m pip install -r requirements.txt"}
        }
    }
}
```

Resolution order (identical to `runtime.platforms`):

1. Start with base `setup` fields (`command`, `note`).
2. Merge `setup.platforms.<current_os>` top-level fields if the OS matches.
3. Merge `setup.platforms.<current_os>.<current_subtype>` if that subtype dict
   exists; else merge `setup.platforms.<current_os>.general` if present.

Array fields are **replaced** (not concatenated) when merged.

**Rule**: subtype values (`platforms.<os>.<subtype>`) must be dicts. Strings at
subtype positions are not recognized and will silently be merged as top-level
fields. Use the flat-string shorthand only at the `platforms.<os>` level.

#### Template variables (`_vars`, v0.7.20+)

Declare shared command fragments once, reference via `{{name}}`. Useful when
per-platform commands share substantial prefixes/suffixes (venv creation
paths, pip flag sets, download URLs).

Declaration sites (lowest-priority to highest-priority during lookup):

| Site | Visibility |
|---|---|
| Manifest-top `_vars` | Every block, every platform, every subtype |
| Block-level (`setup._vars`, `runtime._vars`) | Only within that block and its nested platforms/subtypes |
| Platform-level (`setup.platforms.linux._vars`) | That platform's subtypes + itself (via merge) |
| Subtype-level (`setup.platforms.linux.debian._vars`) | That subtype branch only (via merge) |

Lookup order when resolving `{{name}}`:

1. Effective block's merged `_vars` (platform/subtype wins over block-level)
2. Manifest-top `_vars`
3. Error: `UnresolvedTemplateVariableError` listing available var names

**Scoping is dynamic**: lookup uses the CURRENT resolution context, not the
scope where the variable was declared. This lets composite variables respect
per-platform overrides of their ingredients.

Example:
```json
{
    "_vars": {
        "venv_dir":    ".venv",
        "venv_bin":    "{{venv_dir}}/bin",
        "venv_python": "{{venv_bin}}/python"
    },
    "setup": {
        "platforms": {
            "linux": {"command": "python3 -m venv {{venv_dir}} && {{venv_bin}}/pip install -r requirements.txt"},
            "windows": {
                "_vars": {"venv_bin": "{{venv_dir}}\\Scripts"},
                "command": "python -m venv {{venv_dir}} && {{venv_bin}}\\pip install -r requirements.txt"
            }
        }
    },
    "runtime": {
        "type": "python",
        "script_path": "tool.py",
        "platforms": {
            "linux":   {"interpreter": "{{venv_python}}"},
            "windows": {
                "_vars": {"venv_bin": "{{venv_dir}}\\Scripts"},
                "interpreter": "{{venv_python}}.exe"
            }
        }
    }
}
```

Resolution for Windows: `venv_python` (declared at manifest-top as
`{{venv_bin}}/python`) resolves `venv_bin` in the CURRENT Windows scope, where
it's overridden to `.venv\Scripts`. Result: `venv_python` becomes
`.venv\Scripts/python` for Windows, `.venv/bin/python` for Linux.

**Rules**:
- Syntax: `{{name}}` or `{{ name }}` (whitespace tolerated).
- Identifier: `[A-Za-z_][A-Za-z0-9_]*` (ASCII letters/digits/underscore, starting with letter or underscore).
- Case-sensitive: `{{FOO}}` and `{{foo}}` are distinct lookups.
- Values must be strings in v1. List/dict values rejected with a clear error. Tracking issue: #41.
- Nesting: a variable's value may reference other variables. Chain tracking detects cycles (`a -> b -> a`); max depth 10 catches pathological non-cyclic chains.
- `_vars` block is stripped from the resolved output (metadata, not dispatch data).
- `_vars` at prefer-entry level not supported in v1 -- declare at the containing platform/subtype scope instead.
- `setup._vars` and `runtime._vars` are scope-isolated; for vars shared between setup AND runtime, declare at manifest-top.
- `_schema_version` is a protocol field and never substituted.

Escape hatch for literal `{{...}}`: not available in v1. Authors needing a literal `{{foo}}` in a command string should restructure or await v2. See issue #41.

#### Venv-per-tool pattern

Combine a setup command that creates a venv with `runtime.platforms` declaring
the venv interpreter:

```json
{
    "setup": {
        "platforms": {
            "windows": {"command": "python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt"},
            "linux":   {"command": "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"},
            "macos":   {"command": "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"}
        }
    },
    "runtime": {
        "type": "python",
        "script_path": "mytool.py",
        "platforms": {
            "windows": {"interpreter": ".venv\\Scripts\\python.exe"},
            "linux":   {"interpreter": ".venv/bin/python"},
            "macos":   {"interpreter": ".venv/bin/python"}
        }
    }
}
```

The relative `.venv/...` interpreter path resolves against the tool's directory
at dispatch time. `dz setup` creates the venv; subsequent `dz <tool>` invocations
dispatch via the venv's Python, fully isolated from the user's ambient install.

See `tests/fixtures/venv_exercise/` in the repo for a working reference with
heavy dependencies (numpy, pandas, etc.).

## Reserved Names

These names cannot be used as tool names (they're dazzlecmd built-in commands):

`new`, `add`, `list`, `info`, `kit`, `search`, `build`, `tree`, `version`, `enhance`, `graduate`, `mode`

## Examples

### Minimal manifest
```json
{
    "name": "my-tool",
    "runtime": {
        "script_path": "my_tool.py"
    }
}
```

### Shell script tool

The `shell` runtime type supports 7 shells: `cmd`, `bash`, `sh`, `zsh`, `csh`, `pwsh`, `powershell`. Each has a dispatch profile that knows its canonical invocation syntax.

**For scripting-language interpreters** (perl, ruby, lua, php, R, etc.), use `runtime.type: "script"` with `interpreter: "<name>"` instead — those aren't shells (no chain operators, no source/dot-source syntax, no interactive keep-open semantics) and don't belong in the shell profile table.

Basic form:
```json
{
    "name": "deploy",
    "description": "Deploy to production",
    "runtime": {
        "type": "shell",
        "shell": "bash",
        "script_path": "deploy.sh"
    },
    "platform": "linux"
}
```

#### Optional `runtime.shell_args`

List of flags inserted between shell and script. **Replaces** default flags entirely when present.

```json
"runtime": {
    "type": "shell",
    "shell": "cmd",
    "shell_args": ["/E:ON", "/V:ON", "/c"],
    "script_path": "build.bat"
}
```

Other patterns:
- bash with login shell: `"shell_args": ["--login"]`
- pwsh with strict policy: `"shell_args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]`

#### Optional `runtime.shell_env`

Environment-setup script chained before the tool script. Uses the shell's canonical source syntax (`source` for bash/zsh, `.` for sh/pwsh, direct invocation for cmd/csh).

```json
"runtime": {
    "type": "shell",
    "shell": "cmd",
    "shell_args": ["/E:ON", "/V:ON"],
    "shell_env": {
        "script": "C:\\path\\to\\setenv.cmd",
        "args": ["HOMEBOX", "PLZWORK"]
    },
    "script_path": "build.bat"
}
```

Produces `cmd /E:ON /V:ON /c "setenv.cmd HOMEBOX PLZWORK && build.bat ..."` at dispatch. Not supported for `perl` (errors loudly).

#### Optional `runtime.interactive`

Keeps the sub-shell open after the tool runs. Values:

- `false` (default): normal dispatch; shell exits after tool completes
- `true`: uses interactive flag (cmd `/k`, pwsh `-NoExit`, bash/zsh `-i`); user types `exit` to return to dz
- `"exec"`: hand off via `os.execvp` — dz process is replaced by the shell (true hand-off; enables agentic-task scenarios where dz spawns a managed shell environment)

```json
"runtime": {
    "type": "shell",
    "shell": "bash",
    "script_path": "setup_dev_env.sh",
    "interactive": "exec"
}
```

Not all shells support interactive mode. `sh`, `csh`, and `perl` error loudly if `interactive: true` or `"exec"` is requested — use bash, zsh, cmd, pwsh, or powershell instead.

### Node.js / TypeScript / bun / deno tool

The `node` runtime type supports 5 interpreters (`node`, `tsx`, `ts-node`, `bun`, `deno`) and three mutually-exclusive dispatch modes.

#### Mode 1 — script dispatch

```json
{
    "runtime": {
        "type": "node",
        "interpreter": "node",
        "script_path": "tool.js"
    }
}
```

`.js` files default to `interpreter: "node"`. For TypeScript files (`.ts`/`.tsx`/`.mts`/`.cts`), an explicit `interpreter` is **required** — the engine won't guess between tsx, ts-node, bun, and deno.

Bun and deno auto-insert a `run` subcommand: `bun run script.ts`, `deno run script.ts`. Node, tsx, and ts-node don't.

Optional `interpreter_args` (list): flags between interpreter and script.

```json
"runtime": {
    "type": "node",
    "interpreter": "deno",
    "interpreter_args": ["--allow-read", "--allow-net"],
    "script_path": "tool.ts"
}
```

Produces `deno run --allow-read --allow-net tool.ts <argv>` at dispatch.

#### Mode 2 — npm script

```json
{
    "runtime": {
        "type": "node",
        "npm_script": "build"
    }
}
```

Produces `npm run build -- <argv>`. npm reads package.json in the tool directory, finds the named script, runs it via shell.

#### Mode 3 — npx package

```json
{
    "runtime": {
        "type": "node",
        "npx": "@org/toolpkg"
    }
}
```

Produces `npx @org/toolpkg <argv>`. **Note**: npx may download the package on first use. This is structurally identical to `pip install` in a setup command or `cargo install` via `dev_command` — the tool author declared it; the user's choice to run the tool is the trust boundary.

Exactly one of `script_path`, `npm_script`, `npx` must be declared. Multiple → error.

### Script (generic interpreter) tool

For any interpreter not covered by dedicated runtime types (`cscript`, `wscript`, `perl`, `ruby`, `lua`, `php`, `R`, etc.), use `runtime.type: "script"` with an explicit `interpreter`. Supports an optional `interpreter_args` list for flags between interpreter and script.

Windows JScript via WSH:
```json
{
    "runtime": {
        "type": "script",
        "interpreter": "cscript",
        "interpreter_args": ["//Nologo", "//B"],
        "script_path": "tool.js"
    },
    "platform": "windows"
}
```

Perl with taint mode and warnings:
```json
{
    "runtime": {
        "type": "script",
        "interpreter": "perl",
        "interpreter_args": ["-w", "-T"],
        "script_path": "tool.pl"
    }
}
```

### Binary tool
```json
{
    "name": "fast-search",
    "description": "Fast file search (compiled)",
    "runtime": {
        "type": "binary",
        "script_path": "fast-search.exe"
    },
    "platform": "windows"
}
```

### Docker tool (v0.7.21+)

For tools that ship as Docker images (or are distributed as containerized
environments), `runtime.type: "docker"` dispatches via `docker run`.

```json
{
    "name": "my-docker-tool",
    "runtime": {
        "type": "docker",
        "image": "myorg/mytool:1.0",
        "volumes": [
            {"host": ".", "container": "/work", "mode": "rw"}
        ],
        "env": {"LOG_LEVEL": "info"},
        "env_passthrough": ["GITHUB_TOKEN"],
        "docker_args": ["--rm"]
    },
    "setup": {
        "command": "docker build -t myorg/mytool:1.0 ."
    }
}
```

**Required field**:
- `image` (string) -- the local image tag. Must be present locally; pre-flight check runs `docker images -q <image>` before dispatch and errors with a `dz setup <fqcn>` hint on miss. The engine NEVER pulls or builds images -- the tool's declared `setup.command` is responsible for that.

**Optional fields**:
- `volumes` (list of dicts) -- each entry is `{host, container, mode}`. Host paths resolve relative to the tool directory via the shared `paths.resolve_relative_path` helper (so relative paths like `"data/"` join against the tool's dir). Mode is optional (`"rw"` / `"ro"`); omitted = docker default.
- `env` (dict) -- explicit container env vars. Keys and values both appear in argv as `-e KEY=VALUE`.
- `env_passthrough` (list of strings) -- names of host env vars to forward to the container via `-e NAME` (bare flag; docker picks up the value from the host at run time). Values are NEVER logged to stderr or `dz info` output -- only the names.
- `docker_args` (list of strings) -- raw docker CLI flags inserted between `docker run` and the image. Use for `--network host`, `--rm`, `-it` (interactive), `--entrypoint`, etc.
- `inner_runtime` (dict) -- INFORMATIONAL only. Rendered by `dz info` to describe what runs inside the container. Does NOT influence dispatch.

**Dispatch pattern**:

```
docker run [docker_args...] [-v host:container[:mode]]... [-e KEY=VALUE]... [-e NAME]... image [argv...]
```

**Pre-flight check**:

```
$ dz mytool
Error: Docker image 'myorg/mytool:1.0' not found locally.
       Try: dz setup mytool
```

Clean, actionable. Missing `docker` binary, unreachable daemon, etc. each surface dedicated errors.

**Cross-platform image selection** (via conditional dispatch, v0.7.19+):

```json
"runtime": {
    "type": "docker",
    "platforms": {
        "linux":   {"image": "myorg/mytool:amd64-linux"},
        "macos":   {"image": "myorg/mytool:arm64-macos"},
        "windows": {"image": "myorg/mytool:windows-server-core"}
    }
}
```

**Parameterized image tags** (via `_vars`, v0.7.20+):

```json
{
    "_vars": {
        "registry": "docker.io",
        "org": "myorg",
        "tag": "1.0"
    },
    "runtime": {
        "type": "docker",
        "image": "{{registry}}/{{org}}/mytool:{{tag}}"
    }
}
```

**Docker-compatible engines**: the `docker` runtime shells out to the literal
`docker` command. Any engine providing a docker-compatible CLI works without
code changes: Docker Desktop, Docker Engine, Podman (via alias/symlink),
Colima, Rancher Desktop, OrbStack, nerdctl. Users with non-docker CLIs can
PATH-alias or rename; the runtime honors whatever `docker` resolves to.

**NOT supported in v0.7.21**:

- Automatic image pull/build (author declares `setup.command`; user runs `dz setup`)
- Docker Compose (`docker compose run`) -- future runtime type
- Podman/nerdctl first-class field (`engine_cmd`) -- future addition if demand emerges
- VMware / VirtualBox / QEMU full-VM dispatch -- see issue #43 (separate `vm` runtime type)
- Windows path translation for volumes (author writes paths Docker Desktop / WSL2 accept; document-only today)

**Reference fixture**: `tests/fixtures/docker_tool/` in the repo has a working
end-to-end example (Dockerfile + manifest + Python ENTRYPOINT). Integration
tests live at `tests/test_docker_integration.py`, marked
`@pytest.mark.docker_integration`.

## Conditional Dispatch (v0.7.19+)

A single manifest can express different dispatch behavior per platform and
offer ordered alternatives when multiple implementations are viable. Two
features work together:

1. **`runtime.platforms.<os>.<subtype>`** -- per-platform overrides that merge
   into the base runtime for the matching host.
2. **`runtime.prefer`** -- an ordered array of dispatch alternatives. The
   first entry whose preconditions pass is selected.

### `runtime.platforms`

Nested by OS (`linux` / `windows` / `macos` / `bsd` / `other`) and subtype
(`debian` / `rhel` / `win11` / `macos14` / `freebsd` / `general` / etc.).
Resolution order for each host:

1. Start with the base `runtime` block (fields declared outside `platforms`).
2. Merge top-level fields of `platforms.<current_os>` if the OS matches.
3. Merge `platforms.<current_os>.<current_subtype>` if that subtype dict
   exists; else merge `platforms.<current_os>.general` if present.

Deep-merge semantics: nested dicts merge recursively, **arrays are replaced**
(not concatenated), `null` in the override removes the key.

Example:
```json
{
    "name": "my-tool",
    "runtime": {
        "type": "node",
        "script_path": "tool.js",
        "platforms": {
            "windows": {
                "type": "script",
                "interpreter": "cscript",
                "interpreter_args": ["//Nologo"],
                "script_path": "tool_wsh.js"
            },
            "linux": {
                "debian": {"interpreter_args": ["--use-openssl-ca"]},
                "general": {"interpreter_args": []}
            }
        }
    }
}
```

### `runtime.prefer`

Ordered array of dispatch alternatives. Each entry is a dict of runtime
fields. The engine iterates top-to-bottom and picks the first entry whose
preconditions pass. Preconditions are **inferred** from declared fields:

| Declared field | Precondition |
|---|---|
| `interpreter` | Interpreter must be on PATH (`shutil.which`) |
| `npx` | `npx` must be on PATH |
| `npm_script` | `npm` must be on PATH |
| `script_path` | File must exist (relative to tool directory) |

Optionally an entry may also declare **`detect_when`** -- a structured
condition evaluated before the inferred preconditions. Both must pass for
the entry to match.

Example:
```json
{
    "runtime": {
        "type": "node",
        "prefer": [
            {"interpreter": "bun", "script_path": "tool.ts"},
            {"interpreter": "tsx", "script_path": "tool.ts"},
            {"npx": "@myorg/tool"}
        ]
    }
}
```

On a host with `bun` installed: first entry wins. Without `bun` but with
`tsx`: second. With neither but `npx` available: third.

If no entry matches, `dz <tool>` fails with a full resolution trace showing
what was tried and why each was rejected.

### Combining platforms + prefer

A `platforms.<os>` or `platforms.<os>.<subtype>` block may itself contain a
`prefer` array. The platform override runs first (merging fields), then the
resulting effective block's `prefer` is iterated.

### `detect_when` matchers

The `detect_when` schema (shared with setup resolution) supports these
matchers:

- `file_exists: <path>` -- path exists and is a regular file
- `dir_exists: <path>` -- path exists and is a directory
- `env_var: <name>` -- env var is set AND non-empty (values never logged)
- `env_var_equals: {name, value}` -- strict string equality (values not logged)
- `command_available: <name>` -- `shutil.which(name)` resolves
- `uname_contains: <substring>` -- case-insensitive substring match against
  a composite platform string (`<os> <subtype> <arch> <version> [wsl]`)
- `all: [<condition>, ...]` -- AND (`all: []` is vacuously True)
- `any: [<condition>, ...]` -- OR (`any: []` is vacuously False)

Multiple keys in a single condition dict are AND'd together. Underscore-prefixed
keys (`_schema_version`, `_comment`) are treated as metadata and ignored.

### Inspecting resolution

- `dz info <tool>` -- default view shows the runtime resolved for the current host.
- `dz info <tool> --raw` -- shows the manifest as declared (platforms + prefer arrays visible).
- `dz info <tool> --platform <spec>` -- previews resolution for a specified
  platform (e.g., `linux.debian`, `windows`, `macos.macos14`). Enumerates
  `prefer` entries without evaluating preconditions, so you can verify
  platform-level resolution across hosts you do not own.

### Schema versioning

Manifest blocks may carry a `_schema_version` field. v0.7.19 ships schema
version `"1"`. Un-versioned blocks default to version 1 for backwards compat.
Future library versions that introduce breaking changes will bump the
supported version set and provide migration hooks.

## See Also

- [Creating Tools](creating-tools.md) -- step-by-step guide
- [Kits](kits.md) -- how tools are organized into kits
