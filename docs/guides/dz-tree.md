# `dz tree` — Aggregator Tree Visualization

`dz tree` walks the discovered FQCN index and renders the aggregator
hierarchy as either an ASCII tree (default) or structured JSON
(`--json`). It's the primary tool for answering "what does dz actually
think is installed?" and for building scripts/tooling on top of dazzlecmd.

## ASCII output (default)

```
$ dz tree
dz (dazzlecmd PREALPHA 0.7.11)
+-- core [always_active]
|   +-- core:find        Cross-platform file search powered by fd
|   +-- core:fixpath     Fix mangled paths and optionally open, copy...
|   +-- core:links       Detect and display filesystem links...
|   +-- core:listall     Flexible directory structure listing with sorting...
|   +-- core:rn          Rename files using regular expressions
|   \-- core:safedel     Safe file/directory deletion with link-aware...
+-- dazzletools [always_active]
|   +-- dazzletools:dos2unix    Pure-Python cross-platform line ending...
|   +-- dazzletools:github      Open GitHub project pages, issues, PRs...
|   ...
\-- wtf [aggregator]
    +-- wtf:core:locked     Why did my Windows PC lock? Diagnoses lock...
    \-- wtf:core:restarted  Why did my Windows PC restart? One command...

19 tools across 3 kit(s)
```

**Characters used**: only `+`, `|`, `\`, `-`, and spaces — no Unicode
box-drawing. This is intentional for Windows codepage safety (see
CLAUDE.md for background). It renders correctly in `cmd.exe`,
PowerShell 5.1, Git Bash, WSL, and any POSIX terminal.

**Kit markers** appear in brackets next to the kit name:

- `[always_active]` — kit has `always_active: true` in its manifest
- `[aggregator]` — kit is itself a nested aggregator (has its own
  `kits/` directory and contributes namespace-remapped tools)
- `[disabled]` — kit is disabled via `disabled_kits` config (only
  visible with `--show-disabled`)

## JSON output

```bash
dz tree --json
```

```json
{
  "root": "dazzlecmd",
  "command": "dz",
  "tools_dir": "projects",
  "kits": {
    "core": {
      "name": "core",
      "always_active": true,
      "is_aggregator": false,
      "state": "enabled (always_active)",
      "tools": [
        {
          "fqcn": "core:find",
          "short": "find",
          "description": "Cross-platform file search powered by fd"
        },
        ...
      ]
    },
    "wtf": {
      "name": "wtf",
      "always_active": false,
      "is_aggregator": true,
      "state": "enabled",
      "tools": [
        {
          "fqcn": "wtf:core:locked",
          "short": "locked",
          "description": "Why did my Windows PC lock?..."
        },
        {
          "fqcn": "wtf:core:restarted",
          "short": "restarted",
          "description": "Why did my Windows PC restart?..."
        }
      ]
    }
  }
}
```

### JSON use cases

**Shell pipelines with `jq`**:

```bash
# List all FQCNs
dz tree --json | jq -r '.kits[].tools[].fqcn'

# Count tools per kit
dz tree --json | jq -r '.kits | to_entries[] | "\(.key): \(.value.tools | length)"'

# Show only aggregator kits
dz tree --json | jq '.kits | to_entries[] | select(.value.is_aggregator)'
```

**Scripting in Python**:

```python
import json
import subprocess

result = subprocess.run(["dz", "tree", "--json"], capture_output=True, text=True)
tree = json.loads(result.stdout)
for kit_name, kit_data in tree["kits"].items():
    print(f"{kit_name}: {len(kit_data['tools'])} tools")
```

**Tooling integration**: IDE plugins, web UIs, shell completions, or
automated documentation generators can consume `dz tree --json` as a
stable data source.

## Flags

| Flag | Purpose |
|---|---|
| `--json` | Output as JSON instead of ASCII tree |
| `--depth N` | Limit display depth. `--depth 1` shows only kit names (no tools). |
| `--kit NAME` | Show only one kit's subtree |
| `--show-disabled` | Include disabled kits (default: hidden) |

### `--depth N`

Useful when you have many tools and just want a kit overview:

```
$ dz tree --depth 1
dz (dazzlecmd PREALPHA 0.7.11)
+-- core [always_active]
+-- dazzletools [always_active]
\-- wtf [aggregator]

19 tools across 3 kit(s)
```

### `--kit NAME`

Filter to a single kit subtree:

```
$ dz tree --kit wtf
dz (dazzlecmd PREALPHA 0.7.11)
\-- wtf [aggregator]
    +-- wtf:core:locked     Why did my Windows PC lock?...
    \-- wtf:core:restarted  Why did my Windows PC restart?...

2 tools across 1 kit(s)
```

### `--show-disabled`

By default, kits disabled via `dz kit disable` or the `disabled_kits`
config key are hidden from `dz tree`. Use `--show-disabled` to see them:

```
$ dz kit disable dazzletools
$ dz tree --show-disabled
dz (dazzlecmd PREALPHA 0.7.11)
+-- core [always_active]
+-- dazzletools [always_active, disabled]
\-- wtf [aggregator]
```

## Data source

`dz tree` reads from `engine.fqcn_index` and `engine.kits` — the same
data structures used for dispatch. No separate discovery pass. This
means it reflects EXACTLY what `dz <tool>` would see at dispatch time,
including:

- Shadowed tools (absent from the tree)
- Disabled kits (hidden unless `--show-disabled`)
- FQCN remapping from recursive discovery (e.g., `wtf:core:locked`)

## See also

- `docs/guides/dz-kit.md` — full `dz kit` command reference
- `docs/guides/config.md` — config schema and precedence rules
- `docs/guides/kits.md` — kit architecture
