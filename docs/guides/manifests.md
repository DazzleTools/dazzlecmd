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

## See Also

- [Creating Tools](creating-tools.md) -- step-by-step guide
- [Kits](kits.md) -- how tools are organized into kits
