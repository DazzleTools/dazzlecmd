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
