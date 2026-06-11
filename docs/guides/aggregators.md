# Aggregators -- how dz works inside, and how to build your own

> **"This is my tool! There are many like it, but this one is mine!"**

dazzlecmd is *a tool for tools* -- and the whole point of the aggregator design is that you can stand up your own: same engine, same discipline, your name on it.

This guide is for **developers** who want to understand how dazzlecmd's aggregator machinery works, and for anyone who wants to build their **own** dz-style command -- a standalone CLI with its own name that discovers and dispatches its own tool collection, powered by the same library (`dazzlecmd-lib`).

Audience: two groups. (1) Contributors working *inside* dazzlecmd who need the mental model of discovery/dispatch. (2) Authors creating an *external* aggregator -- the way [wtf-windows](https://github.com/djdarcy/wtf-windows) is its own `wtf` command built on the same engine. Users who just run `dz` don't need this; see `docs/guides/kits.md` and `docs/guides/dz-kit.md`.

For per-tool manifests see `docs/guides/manifests.md`; for kit mechanics see `docs/guides/kits.md`; for creating individual tools see `docs/guides/creating-tools.md`.

---

## The one idea

**dazzlecmd is not special.** `dz` is just one *instance* of an aggregator -- a thin CLI wrapped around `dazzlecmd_lib.AggregatorEngine`. The library is the product: discovery, the FQCN index, kit activation, dispatch, the meta-commands (`list`/`info`/`kit`/`tree`/`setup`/`version`/`mode`), display rendering, and the mode system all live in `dazzlecmd-lib`. Any aggregator built on it gets all of that for free, identically.

That means the answer to "how does dz work?" and "how do I build my own dz?" is the same answer.

## Anatomy of an aggregator

```
my-tools/
├── aggregator.json        # the aggregator's IDENTITY (the root marker)
├── pyproject.toml         # console entry point: `mt = "my_tools.cli:main"`
├── src/my_tools/
│   ├── cli.py             # ~30 lines: find root, build engine, run
│   └── _version.py
├── projects/              # the tools, grouped by namespace
│   └── core/
│       └── hello/
│           ├── .dazzlecmd.json   # per-tool manifest (runtime, description...)
│           └── hello.py
└── kits/                  # kit REGISTRY POINTERS (activation control)
    └── core.kit.json      # {"name": "core", "always_active": true}
```

### `aggregator.json` -- the identity

The presence of `aggregator.json` defines the project root (the engine walks up from the installed package location to find it). It declares *which aggregator this is*:

```json
{
    "_schema_version": 1,
    "name": "my-tools",
    "command": "mt",
    "description": "My tools -- many tools, one command",
    "tools_dir": "projects",
    "kits_dir": "kits",
    "manifest_name": ".dazzlecmd.json",
    "enabled_meta_commands": ["list", "info", "kit", "tree", "setup", "version", "mode"]
}
```

Everything user-facing derives from this: `command` is what error messages and hints print, `tools_dir`/`manifest_name` drive discovery, `enabled_meta_commands` selects which library meta-commands to register. dazzlecmd's own `aggregator.json` at the repo root is the same schema -- compare them.

### The CLI -- the canonical thin consumer

The whole entry point of a generated aggregator:

```python
from dazzlecmd_lib import AggregatorEngine
from dazzlecmd_lib.aggregator_config import find_aggregator_root

def main():
    project_root = find_aggregator_root(os.path.dirname(os.path.abspath(__file__)))
    engine = AggregatorEngine.from_project(
        project_root,
        version_info=(DISPLAY_VERSION, __version__),
        is_root=True,
    )
    return engine.run()
```

Two things matter here:

1. **Root-finding is anchored to the package's own location**, never the current directory. An aggregator's identity is *which package it is*, not where you invoke it from -- running `mt` from inside a dazzlecmd checkout must not turn `mt` into `dz`.
2. **`from_project` + `engine.run()` is the entire contract.** The engine reads `aggregator.json`, discovers tools, builds the parser (library meta-commands + one subcommand per tool), and dispatches. No registration boilerplate.

## How discovery and dispatch work

1. **Discovery** walks `<tools_dir>/<namespace>/<tool>/`, reading each tool's `<manifest_name>` manifest. Nested *aggregators* (a tool directory that itself contains a `kits/` dir) are recursed into -- aggregators compose fractally, so `dz wtf <tool>` can work when wtf is embedded as a kit.
2. **Kits** control activation. `kits/<name>.kit.json` is a *registry pointer* (`always_active`, source URL); the kit's own identity (description, tool list) lives with the kit at `projects/<name>/.kit.json`. *Virtual kits* declare alias names over existing tools (`f:rm` → `core:safedel`) without moving files. Embedded aggregators surface their `aggregator.json` description in `kit list`.
3. **The FQCN index** maps every name to a canonical tool: canonical FQCNs (`core:find`), virtual-kit aliases, short names (with precedence + favorites), and kit-qualified shortcuts. Every tool also has a derivable **absolute FQCN** -- `<aggregator>:<namespace>:<tool>` (e.g. `my-tools:core:hello`) -- which always resolves. Tools whose engine lives in the library itself (the constitutional primitives, e.g. `safedel`, `links`) show a `[lib]` marker: their absolute home is `dazzlecmd_lib:core:<name>`, overlaid onto your aggregator's surface.
4. **Dispatch** runs the tool via its declared runtime (`python`, `node`, `binary`, `powershell`, `docker`, ...) through the library's runner registry. The engine never installs anything -- it is a dispatcher; setup is the tool author's declared script, offered (never auto-run) via `setup`.

## Building your own aggregator

### The fast path

```
dz new aggregator MyTools --with-starter
cd MyTools
pip install -e .
mytools list        # discovers the starter tool
mytools hello       # dispatches it
```

The scaffold is a complete standalone project (the layout above, plus a README, .gitignore, and a smoke test). Flags: `--command/-c` (CLI name), `--description/-d`, `--tools-dir`, `--manifest`, `--with-starter`. Defaults resolve from your `~/.dazzlecmd/config.json` `new` section, then built-ins.

From there: add tools (`projects/<ns>/<tool>/` + a manifest -- or `dz new tool` from inside the project once it's also a dazzlecmd checkout consumer), group them into kits, and version it as a normal repo.

### Customizing beyond the defaults

The extension pattern is **override-and-chain** on the meta-command registry, *before* `engine.run()`:

```python
engine = AggregatorEngine.from_project(project_root, ...)

# Replace a meta-command's handler (and optionally call the library
# renderer inside your handler to keep the standard output):
engine.meta_registry.override("list", handler=my_list_handler)

# Register an aggregator-specific meta-command:
engine.meta_registry.register("doctor", parser_factory=..., handler=...)

return engine.run()
```

This is exactly how wtf-windows specializes: it overrides `list`/`info` to add its diagnostics framing, drops meta-commands that aren't in its vocabulary (via `enabled_meta_commands`), and registers its own commands -- while inheriting discovery, the FQCN index, color/width-aware rendering, and the mode system untouched. Treat wtf-windows as the canonical worked example of a "real" consumer.

### What you inherit for free

- `list` / `info` / `tree` / `kit` / `setup` / `version` with terminal-aware formatting, color discipline, collision (`[*]`) and alias (`[+]`) markers.
- The constitutional core primitives (recoverable delete, link detection/creation) -- present in every consumer by construction, marked `[lib]`.
- `mode switch` / `mode restore` -- the dev↔publish toggle with recoverable backups, for working on a tool in its own checkout.
- Kit activation (`kit enable/disable/focus`), user config (`DAZZLECMD_CONFIG`-style isolation works per-aggregator), favorites, and shadowing controls.

## Nesting: embedding one aggregator inside another

This is how wtf-windows lives inside dz (`dz wtf <tool>` works), and how your aggregator can host -- or be hosted. **Do not use `dz new aggregator` for this** (that *creates* a new standalone project; running it inside an existing aggregator just nests an unrelated project in that repo's tree, and it will warn you). Embedding an aggregator that already exists is a *kit* operation:

### The one-command path

From the HOST aggregator's root:

```
dz kit add https://github.com/you/your-aggregator.git
dz kit enable your-aggregator
dz list                          # its tools appear, namespaced
```

`dz kit add <url> [--name N] [--branch B]` runs `git submodule add` into `projects/<name>/` and writes the `kits/<name>.kit.json` registry pointer. That's the entire embedding: discovery sees a kit directory that itself contains a `kits/` dir, recognizes it as a nested aggregator, and recurses -- its tools surface under qualified FQCNs (`wtf:core:locked`), dispatchable from the parent.

### What's actually on disk (the manual path, same result)

```
projects/your-aggregator/        # the embedded repo (submodule, subtree, or plain copy)
kits/your-aggregator.kit.json    # {"name": "your-aggregator", "always_active": false,
                                 #  "source": "https://github.com/you/your-aggregator.git"}
```

Two pieces, nothing else. The registry pointer controls *activation only*; the embedded aggregator keeps its own identity (`aggregator.json`), description, and inner kit structure -- the parent reads structural hints from it but never overwrites identity.

### Things to know

- **Both directions keep working.** The embedded aggregator is still its own standalone command (`wtf ...` and `dz wtf ...` coexist); embedding adds a surface, it doesn't move the project.
- **Development on an embedded kit** uses the mode system: `dz mode switch <tool>` symlinks a tool to your local checkout; `dz mode restore` puts it back.
- **Don't create loops**: never point an embedded aggregator's kit registry back at its own host (parent embeds child embeds parent). Display dedup for accidental loops is tracked, but the rule is simply: embed downward.
- Planned polish (designed, not yet shipped): `--method submodule|subtree|copy`, `--pin <tag>`, and `dz kit update <name>` for refreshing pinned imports.

## Growing up: the promotion ladder

Aggregators participate in dazzlecmd's lifecycle story. A tool can start as a local script in your `projects/`, graduate into its own repo, and eventually become its own aggregator -- wtf-windows took exactly that path (standalone tool → aggregator of diagnostics) -- while staying reachable from a parent (`dz wtf ...`) through embedding. The same machinery runs in both directions: what an aggregator surfaces is a projection over canonical names, so reorganizing the surface never breaks the tools underneath.

## Reference

- `docs/guides/manifests.md` -- per-tool manifest schema
- `docs/guides/kits.md`, `docs/guides/dz-kit.md` -- kit mechanics and CLI
- `docs/guides/creating-tools.md` -- authoring tools
- `docs/guides/setup-scripts.md` -- setup policy for tool authors
- `packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/aggregator/` -- the scaffold source of truth
