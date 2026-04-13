# User Configuration

dazzlecmd reads a per-user configuration file at `~/.dazzlecmd/config.json`.
The file is optional — if it doesn't exist, all defaults apply. It controls
kit selection, short-name resolution on collisions, hint silencing, tool
shadowing, and a few related knobs.

This guide documents the schema, semantics, and precedence rules. For the
CLI commands that read and write this file, see `docs/guides/dz-kit.md`.

## File location

- **Default**: `~/.dazzlecmd/config.json`
- **Override**: set `DAZZLECMD_CONFIG` to an alternate path (used by tests
  and per-project scripts). Absolute paths only.

The directory is created on first write. You can also create it manually
and hand-edit `config.json` — the commands use merge semantics, so unknown
keys you add are preserved across writes.

## Schema

```json
{
    "_schema_version": 1,
    "kit_precedence": ["core", "dazzletools", "wtf"],
    "active_kits": ["core", "wtf"],
    "disabled_kits": ["dazzletools"],
    "favorites": {
        "status": "core:status",
        "find": "core:find"
    },
    "silenced_hints": {
        "tools": ["wtf:core:restarted"],
        "kits": []
    },
    "shadowed_tools": ["core:safedel"],
    "kit_discovery": "auto"
}
```

All keys are optional. Malformed values (wrong type, unparseable JSON) are
tolerated with a stderr warning and treated as absent.

### Key reference

| Key | Type | Purpose |
|---|---|---|
| `_schema_version` | integer | Reserved for future migration tooling. Do not modify. |
| `kit_precedence` | list of strings | Ordered list of kit names used to break ties on short-name resolution. Kits earlier in the list win. Unknown kits are ignored. |
| `active_kits` | list of strings | Explicit allow-list of enabled kits. If set, only these kits (plus `always_active` kits) contribute tools. |
| `disabled_kits` | list of strings | Explicit deny-list. Always wins over `active_kits` on overlap. Overrides `always_active` for a given kit. |
| `favorites` | dict `{short: fqcn}` | Pin a short name to a specific tool. Checked BEFORE precedence. Stale favorites (target not found) emit a warning and fall through. |
| `silenced_hints.tools` | list of FQCNs | Suppress the rerooting hint for these specific tools. |
| `silenced_hints.kits` | list of kit names | Suppress the rerooting hint for any tool whose top-level kit is listed. |
| `shadowed_tools` | list of FQCNs | Remove these tools from discovery entirely. They don't appear in `dz list`, aren't dispatchable, and their short names are freed for other tools. |
| `kit_discovery` | string | Reserved. Currently only `"auto"` is honored. |

## Precedence rules

### Kit selection (active vs disabled)

The order of precedence for "is this kit active?" is:

1. **`DZ_KITS` environment variable** — if set, it fully overrides the
   config file. Comma-separated list. Empty string means "no kits active"
   (meta-commands only).
2. **`disabled_kits`** — any kit in this list is excluded, even if it's
   `always_active` in its own manifest.
3. **`active_kits`** — if set, only these kits contribute tools. Kits not
   in this list are excluded UNLESS they have `always_active: true`.
4. **`always_active` in kit manifest** — kits declared `always_active: true`
   (e.g., `core`) stay on by default unless explicitly disabled.
5. **Default** — if no filtering config is set, all discovered kits are
   active.

#### Overlap rule

If a kit appears in both `active_kits` and `disabled_kits`, `disabled_kits`
wins and dazzlecmd emits a stderr warning. This is a safety mechanism —
"disable" is the stricter intent.

### Short-name resolution on collision

When two or more tools share a short name (e.g., both `core:find` and
`wtf:core:find` exist), `dz find` uses this resolution order:

1. **Exact FQCN input** — if the user typed `dz wtf:core:find`, use that
   directly. Favorites and precedence do not apply.
2. **Favorites** — if `favorites["find"]` is set and the target FQCN
   exists, dispatch to it silently. If the target doesn't exist (stale),
   warn and fall through.
3. **Kit precedence** — apply `kit_precedence` order. First kit to have
   a matching tool wins. Notification emitted to stderr.
4. **Default precedence** — if no `kit_precedence` is set, the default
   order is `core` first, then `dazzletools`, then other kits in
   discovery order.

### Rerooting hint gating

The rerooting hint fires when any tool's FQCN has 4+ segments (3+ colons).
Silencing filters the candidate list BEFORE computing the deepest FQCN:

1. If `DZ_QUIET=1`, no hint fires (globally silenced).
2. Tools whose FQCN is in `silenced_hints.tools` are removed from
   consideration.
3. Tools whose `_kit_import_name` is in `silenced_hints.kits` are removed.
4. If any candidates remain and the deepest has 3+ colons, the hint fires.

### Shadowing

`shadowed_tools` is applied at the end of top-level discovery, after
recursive merge and before the FQCN index is built. Shadowed tools are
**completely absent** from `engine.projects`:

- Not shown in `dz list`
- Not dispatchable (argparse produces "invalid choice")
- Their short names are freed — another tool with the same short name can
  claim it unambiguously

Shadowing is useful when a tool exists as a standalone install (e.g.,
`safedel` published to PyPI) and the user wants `dz` to step out of the
way.

## Backwards compatibility

- v0.7.9's `kit_precedence` key is read unchanged. Existing configs work.
- Unknown keys added by users (including future Phase 4+ keys) are
  preserved across writes.
- Missing keys fall back to their defaults. You can create a `config.json`
  with only one key and dazzlecmd handles it gracefully.

## Writing by hand vs CLI commands

The config file is plain JSON. You can edit it with any text editor.
Commands like `dz kit enable`, `dz kit favorite`, etc. use merge
semantics — they read the existing file, update the specific keys they
care about, and write back with the rest preserved.

See `docs/guides/dz-kit.md` for the full list of commands that manipulate
this file.

## Example: primacy and rerooting

Scenario: a user has `safedel` installed standalone via PyPI. They want
`safedel` to be primary (typed directly), and they don't want `dz safedel`
cluttering `dz`'s namespace.

```
dz kit shadow core:safedel
```

Result:

```json
{
    "_schema_version": 1,
    "shadowed_tools": ["core:safedel"]
}
```

Now `dz list` doesn't show `safedel`, `dz safedel` produces
"invalid choice", and the short name `safedel` is freed — so if some
future kit ships a different tool also named `safedel`, it can claim the
name cleanly.

## Example: kit focus

Scenario: a user wants to work exclusively with the `wtf` kit for a
session. Core and dazzletools are `always_active` so they stay on, but
everything else should be off.

```
dz kit focus wtf
```

Result:

```json
{
    "_schema_version": 1,
    "active_kits": ["wtf"],
    "disabled_kits": ["extra", "comfy", ...]
}
```

`always_active` kits (core, dazzletools) are preserved automatically.
