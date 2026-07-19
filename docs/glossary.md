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

## The three relations (why one thing can appear in several places)

Everything has exactly **one defining home** in the tree. When you meet the same thing somewhere else, that appearance is one of three declared kinds — never an unexplained copy:

- **Alias** — another *name* for the same node. `f:rm` runs `core:safedel`; nothing new exists, the spelling just lands on the one node. Every rewrite is echoed so you always see where you landed.
- **Projection** — a real *derived node* that shows something from another vantage, and whose card always names its `source:`. `dz:dazzletools:claude` is the claude kit's view over dazzletools' tools; the kit-frame verb views work the same way. A projection exists because a second, honest way of *looking* at something is useful — and it stays honest by declaring what it reflects.
- **Instance-of** — the link from a concrete item to its class rung (`safedel` → `internaltool`). It says what kind of thing you're holding.

The rule that makes these a system instead of a hodge-podge: **an appearance must declare its kind.** If a card shows `source:`, you're on a projection; if a spelling gets echoed to another, you used an alias; if a `Fibers:` section says `instance of`, you're reading a classification. No node ever silently appears twice.

*(Naming note: the verb axis called "projection" — `favorite`/`unfavorite`, a saved shortcut — is an unrelated, older sense of the word.)*

## Navigating the structure (the tree behind the CLI)

- **Rung** — one named position on an axis's ladder. The level ladder's rungs are `fiber < lib < internaltool < tool < kit < aggregator < supra`; a verb pair's rungs are its two poles (`enable` at the warm end, `disable` at the cold). A rung is two things at once: a *position* (its rank — a signed number, 0 being the axis's conserved center) and a *class* (everything at that level: `dz info :.level:kit` describes kit-ness itself, not any particular kit).
- **Axis** — a ladder of rungs with one meaning ("what is conserved") at its center. `dz:.level` is the containment axis; `activation` is a verb axis.
- **Pole** — a rung at an axis's end; for verb pairs, the two actions (`add`/`remove`).
- **Fiber** — the structure *behind* a thing, reached with `:.`: what a rung's class is made of (`dz :.level:kit:.` lists kit-ness's machinery), or a tool's own backing details. Each `:.` step goes one ring of "aboutness" inward.
- **Instance of** — the link from a concrete item to its class rung, shown in a card's `Fibers:` section (`safedel` → `dz:.level:internaltool`). Follow it with the command printed beside it.
- **Rank** — a rung's signed position. `0` is the axis's fixed point (for the level ladder, the aggregator itself); fractions (like `-3/2`) mark rungs inserted between whole positions without renumbering anything.
