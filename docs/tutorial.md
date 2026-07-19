# The dazzlecmd Tour — one tree, four operators

Everything in dazzlecmd — every tool, kit, verb, level, alias, and config entry — is a node in **one addressable tree**. Every command is a *read* or a *move* on that tree. Once you hold that single idea, the rest of this page is just learning four operators and where they take you.

This is the tutorial. The formal spec lives in [grammar.md](grammar.md); the vocabulary lives in [glossary.md](glossary.md). This page links to them instead of repeating them — read here first, dip there for precision.

## The map: three worlds, one tree

| World | Operator to enter | What lives there | Shell parallel |
|---|---|---|---|
| **Entities** | `:` | the things you use: kits, tools, projections (`dz:core:safedel`) | `cd sub/folder` — a path step |
| **Machinery** | `:.` | the system's own structure: levels, verbs, config, presentation (`dz:.meta:level`) | `ls` or `dir` of a hidden area — discovery |
| **Properties** | `.` | data ON a node: version, notes, settings (`dz:core:safedel.version`) | reading a file attribute |

Those are the **worlds** — where things live. Getting between them is a small set of **moves**:

| Move | Direction | Lands in | Shell parallel |
|---|---|---|---|
| `:name` | down | an entity child | `cd name` |
| `:.name` | down, inner | the ring (machinery) | entering a hidden area |
| `.name` | a look, not a move | a property's value | reading an attribute |
| `:+` | **up** | the parent (whatever world it's in) | `cd ..` |

(`:+` is a *direction*, not a world — that's why it has no row in the first table: ascent returns you along the path you came, so it needs no destination name and may even repeat bare: `:++`.)

The mnemonic the project uses: **"dot to look, colon to run"** — `.` reads data, `:` selects things:

```
> dz .level                    # LOOK: read the root's level property -> tool
> dz info :core:safedel        # RUN:  select down to a thing and ask about it
```

The compound `:.` selects *within the machinery* (the "ring") of whatever node the address has reached so far — in `safedel:.`, that's `safedel`; in `dz:.meta`, that's the root itself. Don't take the word "ring" on faith — enumerate one and it explains itself:

```
> dz info safedel:.            # safedel's ring: the STRUCTURE behind this tool 
                               # (its properties are the DATA behind it -- see 
                               #  "The two dots" below)
dz:core:safedel:.  (the ring)
  instance of  dz:.meta:level:internaltool   (dz info :.meta:level:internaltool)
  alias        f:rm   (dz info :core:safedel:.alias:f-rm)
```

## The operators, one by one

### `:` — select a child (why: entities need paths)

`dz :core:safedel` steps root (in this case `dz` or its fully-qualified-name`dazzlecmd` is implicit as the `aggregator` being called at the CLI) → the `core` kit → the `safedel` tool. Rules: names are lowercase; numbers select **by rank** (see "Numbers" below). It exists because entities nest, and paths are how we as humans address nested things (like folders on a computer).

```
> dz info dz:core:safedel      # the tool's card (same as, dz info :core:safedel)
> dz info :dazzletools:claude  # a projection: the 'claude' view over dazzletools' tools
```

That second one is worth pausing on: virtual kits project their views into the namespaces they cover, so `dz:dazzletools:claude` is a real node whose card names its **source** (`dz:claude`). Follow any handle a card prints — they are all real addresses.

If that feels like things referencing themselves in too many ways: there are exactly **three** ways a thing can appear outside its one home {alias, projection, instance-of} and each appearance declares which it is. The [glossary.md](glossary.md#the-three-relations-why-one-thing-can-appear-in-several-places) explains when each is used and why they're not interchangeable.

### `.` — read a property (why: nodes carry data, and data is not structure)

`dz :core:safedel.version` → `0.1.1 (derived)`. The value comes from the tool's own manifest (a *derived* read — you cannot overwrite it; the system tells you so and names the real mechanism). Rules: an **interior** dot is always a property step; properties never nest structure. You might ask does this have overlap with the `:` operator? None by design, the `:` selects *things*, `.` reads *data on a thing*. When a spelling could be either, position decides (see grammar.md §planes).

```
> dz :core:safedel.version     # 0.1.1 (derived)
> dz :.meta:config.list_view   # all (derived)  — config is read-through, file-truth
```

### `:.` — enter the ring (why: every node has machinery behind it)

The signature operator. `X:.b` selects `b` **within X's ring**, X being the node the address has reached so far — the machinery world of that node: its relations, its hidden structure. Trailing `X:.` *enumerates* the ring, which is how you discover what's there:

```
> dz info safedel:.
dz:core:safedel:.  (the ring)
  instance of  dz:.meta:level:internaltool   (dz info :.meta:level:internaltool)
  alias        f:rm   (dz info :core:safedel:.alias:f-rm)
```

Every entry is followable. The alias line points at a *relation object* — the alias itself, which can carry its own notes (`dz :core:safedel:.alias:f-rm.note=...`). Rules: `:.` has **one meaning** (ring select); it never repeats bare (`:..` is a parse error — see grammar.md §rejected); a leading dot on a name is always this operator's serialization, never part of the name.

### The two dots — why `.` and `:.` rhyme

Both dots point "behind" a node, and that is not a coincidence: **the dot is the aboutness mark**. Alone, it reads a *value* about the node; after a colon, it *enters the world* of about-things that are themselves nodes. The difference is what you get back:

```
> dz :core:safedel.version              # a PROPERTY: a value ABOUT safedel -- you read it, that's all
0.1.1 (derived)

> dz info :core:safedel:.alias:f-rm     # a RING ENTRY: a NODE about safedel -- it has its own card...
dz:core:safedel:.alias:f-rm
  kind: Unified (alias-relation)

> dz :core:safedel:.alias:f-rm.note     # ...and its OWN properties (both dots, composed: step then look)
```

The test to carry with you: **if you can `dz info` it, it's in the ring; if you can only read it, it's a property.** A property is a leaf value; a ring entry is a place you can stand and look around from — including at *its* properties, which is what the third command shows.

**Overlap warning — the one that catches everyone:** `:` and `:.` look similar but enter different worlds. `dz :dazzletools:claude` (entity) is a real projection node; `dz :.dazzletools:claude` (machinery) is not — `dazzletools` is not machinery, so the system forgives the spelling toward the property plane and then *tells you* where the real node lives. When you get a "has no value set" with a note attached, read the note: the hints are the tutorial's live form.

### `:+` — go up (why: you already know where you came from)

Ascent is deterministic — every node has exactly one parent — so `:+` needs no name, and may repeat: `:++` is the grandparent. With a key it does the *co-level move*: up one, then select (`remove:+1` → `add`, its opposite pole). It composes with everything: `dz info :.meta:level:.0:+` dereferences to the level axis's seat and walks back up to the axis.

### `=` — assign (why: reads and writes should share addresses)

`dz .note=hello` writes; `dz .note` reads; `dz prop delete .note` unsets. Same address either side of the `=`. Derived and file-truth keys refuse writes and say why — the refusal names the real mechanism (e.g. config changes go through `dz kit enable/disable`, never the property store).

## Reading at different depths

The same node answers at several depths — this is itself a machinery axis you can inspect:

```
> dz info :.meta:presentation
  contains: value (rank -2) · row (-1) · card (0) · full (+1) · dump (+2)
```

`dz :core:safedel.version` is a **value** read. A `dz list` row is a **row**. `dz info safedel` is the **card** — the standard answer about one thing. Commands compose a *scope* (one node, children, subtree) with one of these depths: `list` = children@row, `tree` = subtree@row, `info` = self@card. That's the whole relationship between those three commands.

## Levels and verbs — the machinery worth knowing first

Two doors under `dz:.meta` organize most of the system:

- **`dz:.meta:level`** — the containment ladder every item sits on: `fiber < lib < internaltool < tool < kit < aggregator < supra`. Every instance card shows its level with a followable handle; `dz info :.meta:level:kit` describes *kit-ness itself* (the class), and the rung is also addressable by rank: `dz info :.meta:level:-2` → tool.
- **`dz:.meta:verb`** — the verbs, organized by what they do: lifecycle pairs live in the composed `management` space (`membership: add↔remove`, `loading: attach↔detach`, `activation: enable↔disable`), each verb a pole with a rank and an opposite. `dz info info` works — verbs are nodes too.

Kit-frame views of the verbs are **projections** — derived nodes whose cards name their source. Projection is the system's answer to "one thing, several honest appearances": one defining home, every other appearance declares what it reflects. See one for yourself:

```
> dz info :.level:kit:management:membership:add
dz:.meta:level:kit:management:membership:add
  kind: Unified (projection)
  source: dz:.meta:verb:management:membership:add   (dz info :.meta:verb:management:membership:add)
```

(Notice the header: you typed the old `:.level` spelling, the card answers with the canonical `:.meta:level` home — the alias carried you, visibly.)

## Numbers — coordinates, not names

Numeric segments select **by rank**: `:.meta:level:-2` is whatever sits at rank −2 (today: tool). Two rules keep this sane. First, **`X:0` is X itself** — zero is the fixed point; the *seat* at rank 0 is reached through the ring:

```
> dz info :.meta:level:0       # -> dz:.meta:level (the axis ITSELF -- zero = self)
> dz info :.meta:level:.0      # -> dz:.meta:level:aggregator (the ring's rank-0 seat)
```

Second, **ranks shift when rungs are inserted** — they are coordinates, never identities, so never store a rank as a reference; use names. (Permanent numbers are coming as node-ids — a separate, append-only numbering that never shifts.)

## Advanced: one tool, many faces — data per appearance

Because an appearance is a real address, **each appearance can carry its own data**. The same tool reached three ways is one tool — but the *relationship* and the *surface* are distinct places, and each takes notes:

```
> dz ":core:safedel:.alias:f-rm.note=we may retire this alias"     # a note on the RELATIONSHIP itself
> dz ":core:f:rm.note=the f-kit face of safedel"                   # a note on the PROJECTION surface
> dz :core:f:rm.note                                                # each address answers -- and reads
the f-kit face of safedel                                           #   round-robin to counterparts when
> dz :core:safedel:.alias:f-rm.note                                 #   one side is unset, naming the true
we may retire this alias                                            #   source: `x  (from dz:core:...)`
```

Why would you want this? Because "the same tool, used a particular way" often deserves its own facts: why this alias exists, what this view is for, who relies on it. The tool's own properties stay untouched; the *appearance* carries the appearance's story.

**Where this is heading — recipes.** The same mechanism is the foundation for user-created *variants*: a `git-snapshot` that always runs with your favorite flag, a `find` preset for one project's layout — each a projection of the real tool, carrying its own configuration on its own surface, without forking the tool or touching its defaults. The plumbing you just used (appearances with their own data, sources always declared) is exactly what makes that safe: a variant can never silently diverge from its source, because it *names* its source.

## When you get lost

- Any node, any spelling: `dz info <address>` — if it exists in any world, the card explains what it is and where its relations lead.
- A read that misses *teaches*: "not set" comes with the nearest real node and the operator rule you probably wanted — run the overlap-warning example above (`dz :.dazzletools:claude`) and read what comes back.
- `dz :.` at any prefix lists what is actually there (`dz :.`, `dz :core:safedel:.`, `dz info :.meta`).
- Old spellings keep working: renames and folds leave aliases behind, and every rewrite is echoed — the system never silently reinterprets you. Try one: `dz info :.level` still answers (the level machinery moved inside `:.meta` long ago; the alias carries you, and the card shows the canonical home `dz:.meta:level`).

## Reserved words

The vocabulary is deliberately small: the four operators, the verb pairs, the level rungs, and a short list of property names. The full inventory with definitions is [glossary.md](glossary.md); the machine-enforced list lives in the property registry (issue #101). If a word does something special, the glossary has it; if it's not there, it's yours to use.
