# Glossary

The vocabulary DazzleCMD uses for its commands and concepts. (For the deeper design theory, maintainers see the internal glossary.)

## Things you act on

- **Tool** — a single command (e.g. `find`, `safedel`). The base unit; running `dz <tool>` runs it.
- **Kit** — a named group of tools you can turn on or off as a set (e.g. the `media` kit).
- **Aggregator** — the top-level command that hosts tools and kits. `dz` itself is an aggregator; you can build your own (e.g. `wtf`).
- **Level** — where something sits in the containment ladder: `tool` < `kit` < `aggregator`. Verbs work at whichever level their target resolves to.

## Looking at things (reads)

- **`info`** — the full picture of a tool, kit, or aggregator: its identity *and* its current state. `dz info <name>`.
- **Reduced views** — a focused slice of `info`. Naming a coordinate before `info` narrows it: `dz mode info <tool>` shows just the tool's mode; `dz kit info <kit>` shows the kit. The presence of that coordinate is what tells you it's a slice, not the whole.
- **`list`** — the members of a kit/aggregator (its tools). **`tree`** — the same, shown recursively.

## Changing things (verbs)

Each lifecycle verb is one half of a pair (an *axis*); the other half is its inverse:

- **enable / disable** — turn a kit active or inactive (*activation*).
- **attach / detach** — load a kit's tools, or reduce it to a listed-but-not-loaded pointer (*loading*).
- **add / remove** — register a kit, or deregister it (*membership*).
- **favorite / unfavorite** — save or drop a shortcut name (*projection*).
- **mode** — switch a tool between dev and publish form (`dz mode switch`), or restore it.
- **promote** — move something up a level (a tool into a kit, a kit into an aggregator).

Every axis also accepts the universal **`on` / `off`** form: `dz kit loading on <kit>` is the same as `dz attach <kit>`.

- **new** — create a tool, kit, or aggregator from scratch using a template. Unlike `add` (which imports an existing one), `new` scaffolds fresh.

## How commands are addressed

- **Foreground / 0-level** — `dz` works on *tools* by default, so a tool's verbs are available bare (`dz mode …`). Verbs for higher levels are reached by naming the level (`dz kit …`).
- **`on`/`off` vs the special name** — the same operation has a general form (`<axis> on`) and a specific, hoistable form (the special name, e.g. `attach`). They route to the same handler.
- **`--as <level>`** — when a name exists at more than one level, add `--as tool`, `--as kit`, or `--as aggregator` to say exactly which one you mean. Required for mutating operations where the target is ambiguous.
- **`supra`** — the namespace for operations above the default tool level: `dz supra kit …` reaches kit-level verbs explicitly. Useful when you want to be unambiguous about which level a command targets.

## Info and status

- **`dz info <name>`** — shows a complete picture of a tool, kit, or aggregator: its identity (FQCN, version, source) plus its current lifecycle state (`enable`/`disable`/`attach` status, etc.) in a `Current state:` section. Works at any level; dz resolves the level from the name.
- **`dz kit info <kit>`** / **`dz kit status <kit>`** — `info` shows the full identity card plus state; `status` shows just the per-axis lifecycle state for a quick check.
- **`dz list`** — the tools registered in the active aggregator (or in a named kit). **`dz tree`** — the same, shown hierarchically.

## Addressing modes (axis / on / special)

Each verb can be invoked three equivalent ways — they all reach the same handler:

| Form | Example | When to use |
|---|---|---|
| `dz <axis> on\|off <target>` | `dz kit loading on media` | Uniform; works for every axis |
| `dz <axis> <special> <target>` | `dz kit loading attach media` | Explicit about both axis and action |
| `dz <special> <target>` | `dz attach media` | The shortest hoistable form |
