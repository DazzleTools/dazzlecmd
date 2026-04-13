# `dz kit` — Kit Management Reference

`dz kit` is the subcommand family for managing kits (collections of tools)
and per-user configuration. All commands that modify state write to
`~/.dazzlecmd/config.json` — see `docs/guides/config.md` for the schema.

This reference covers every `dz kit *` subcommand and `dz tree`.

## Read-only commands

### `dz kit list [name]`

List all discovered kits with enabled/disabled status, or show the tools
in a specific kit.

```
$ dz kit list
  core             6 tool(s)  [always active]
    Core tools that ship with dazzlecmd - fundamental utilities available everywhere

  dazzletools      11 tool(s)  [always active]
    DazzleTools collection - cross-platform utilities

  wtf              2 tool(s)  [enabled]
    Core Windows diagnostic tools - restart, lock, and crash analysis
```

With a kit name:

```
$ dz kit list wtf
Kit: wtf [enabled]
  Core Windows diagnostic tools - restart, lock, and crash analysis

  locked           windows          Why did my Windows PC lock? Diagnoses lock causes...
  restarted        windows          Why did my Windows PC restart? One command, instant...

  2 tool(s)
```

### `dz kit status`

Show a compact view of currently-active kits and their tool counts.

```
$ dz kit status
Active kits: 3
  core: 6 tool(s)
  dazzletools: 11 tool(s)
  wtf: 2 tool(s)
```

### `dz kit silenced`

Show all silenced hints, shadowed tools, and favorite bindings in one view.

```
$ dz kit silenced
Silenced hints:
  tools:
    - wtf:core:restarted
  kits: (none)

Shadowed tools:
  - core:safedel

Favorites:
  status -> core:status
```

### `dz tree`

Visualize the aggregator hierarchy using ASCII characters (Windows
codepage-safe — no Unicode box-drawing).

```
$ dz tree
dz (dazzlecmd PREALPHA 0.7.11)
+-- core [always_active]
|   +-- core:find        Cross-platform file search powered by fd
|   +-- core:fixpath     Fix mangled paths and optionally open, copy...
|   +-- core:rn          Rename files using regular expressions
|   ...
+-- dazzletools [always_active]
|   +-- dazzletools:dos2unix    Pure-Python cross-platform line ending...
|   ...
\-- wtf [aggregator]
    +-- wtf:core:locked     Why did my Windows PC lock? Diagnoses lock...
    \-- wtf:core:restarted  Why did my Windows PC restart? One command...

19 tools across 3 kit(s)
```

**Flags**:

| Flag | Purpose |
|---|---|
| `--json` | Emit structured JSON output for shell pipelines and tooling integration |
| `--depth N` | Limit recursion depth. `--depth 1` shows kits only (no tools). |
| `--kit NAME` | Show only one kit's subtree |
| `--show-disabled` | Include disabled kits in the output (default: hide them) |

JSON output example:

```bash
dz tree --json | jq '.kits.wtf.tools[].fqcn'
# "wtf:core:locked"
# "wtf:core:restarted"
```

## Kit enable / disable

### `dz kit enable <name>`

Add a kit to `active_kits` and remove it from `disabled_kits` if present.
Warns (but does not fail) if the named kit isn't among the currently
discovered kits — useful for preconfiguring a config before the kit is
actually installed.

```
$ dz kit enable wtf
Enabled kit: wtf
```

### `dz kit disable <name>`

Add a kit to `disabled_kits` and remove it from `active_kits`. Overrides
`always_active: true` in the kit's own manifest.

```
$ dz kit disable dazzletools
Disabled kit: dazzletools
```

### `dz kit focus <name>`

Shorthand for "enable this kit, disable all non-`always_active` kits
except this one." `always_active` kits (like `core`) are preserved
automatically. Useful for tight focus on a single domain (e.g.,
`dz kit focus wtf` when doing Windows diagnostics).

```
$ dz kit focus wtf
Focused on 'wtf'.
  Disabled: extra, comfy
  Preserved (always_active): core, dazzletools
```

### `dz kit reset`

Wipes `~/.dazzlecmd/config.json` entirely after confirmation. All user
preferences (kit selection, favorites, silencing, shadowing) are lost.

```
$ dz kit reset
This will delete ~/.dazzlecmd/config.json and clear all kit preferences.
Continue? [y/N]: y
Config cleared.
```

Skip the prompt with `-y` / `--yes`:

```
dz kit reset --yes
```

## Favorites (collision disambiguation)

### `dz kit favorite <short> <fqcn>`

Pin a short name to a specific FQCN. Favorites are checked BEFORE
precedence resolution, so they always win over the default kit ordering.

```
$ dz kit favorite find wtf:core:find
Favorite set: find -> wtf:core:find
```

Reserved command names (`list`, `kit`, `info`, etc.) cannot be favorites —
the command will error out. If the target FQCN isn't currently discovered,
the favorite is saved anyway with a warning (useful for preconfiguring).

### `dz kit unfavorite <short>`

Remove a favorite binding. Silently no-ops if the binding didn't exist.

```
$ dz kit unfavorite find
Favorite removed: find
```

## Silencing (hint suppression)

### `dz kit silence <fqcn>`

Add an FQCN to `silenced_hints.tools`. The rerooting hint will no longer
fire for this specific tool, but other deeply-nested tools still trigger
hints.

```
$ dz kit silence wtf:core:restarted
Silenced rerooting hint for: wtf:core:restarted
```

### `dz kit unsilence <fqcn>`

Remove an FQCN from the silenced list.

```
$ dz kit unsilence wtf:core:restarted
Unsilenced rerooting hint for: wtf:core:restarted
```

## Shadowing (tool hiding)

### `dz kit shadow <fqcn>`

Remove a tool from `dz` entirely. It won't appear in `dz list`, isn't
dispatchable, and its short name is freed. Useful when the tool is
better-served as a standalone install (e.g., `safedel` on PyPI).

```
$ dz kit shadow core:safedel
Shadowed: core:safedel
  This tool will not appear in 'dz list' or be dispatchable.
```

### `dz kit unshadow <fqcn>`

Restore a shadowed tool to normal discovery.

```
$ dz kit unshadow core:safedel
Unshadowed: core:safedel
```

## Kit import

### `dz kit add <url> [--branch X] [--name Y] [--shallow]`

Add a kit from a git URL. Wraps `git submodule add` into `projects/<name>`
and creates a registry pointer at `kits/<name>.kit.json` with
`always_active: false`.

```
$ dz kit add https://github.com/djdarcy/wtf-windows.git --name wtf
Running: git submodule add https://github.com/djdarcy/wtf-windows.git projects/wtf
...
Added kit: wtf
  Registry pointer: kits/wtf.kit.json
  Submodule: projects/wtf/
  Note: 'wtf' appears to be a nested aggregator (has its own kits/ directory).
        Tools will be namespace-remapped as 'wtf:<namespace>:<tool>'.

Enable with: dz kit enable wtf
```

**Flags**:

| Flag | Purpose |
|---|---|
| `--name NAME` | Override the kit name (default: derive from URL's repo name) |
| `--branch BRANCH` | Check out a specific branch |
| `--shallow` | Shallow clone (depth 1) |

The command detects if the newly-added kit is itself a nested aggregator
(has its own `kits/` directory) and prints a reminder about FQCN
namespace remapping.

## Environment variables

- `DZ_KITS=core,wtf` — full override of the config file's
  `active_kits`/`disabled_kits`. Comma-separated. Empty string means
  "no kits" (meta-commands only).
- `DZ_QUIET=1` — globally silence the rerooting hint and collision
  notifications for one invocation.
- `DAZZLECMD_CONFIG=/path/to/config.json` — override the config file
  path. Used by tests and per-project scripts.

## See also

- `docs/guides/config.md` — full config schema reference
- `docs/guides/kits.md` — kit architecture and authoring
- `docs/guides/manifests.md` — `.kit.json` and `.dazzlecmd.json` schema
