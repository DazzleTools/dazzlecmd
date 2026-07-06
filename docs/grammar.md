# The dz command grammar

How `dz` reads a command line. This is the **specification** of the shipped behavior (dazzlecmd 0.11.17+ / dazzlecmd-lib 0.10.2+); the implementation is a hand-written linear tokenizer (`dazzlecmd_lib/fqcn_grammar.py`), not a grammar engine — the grammar is regular (with one mode switch), so nothing heavier is needed.

## The bang-path (addressing)

Every tool, kit, verb, and property is a node in one FQCN tree, addressed by a *bang-path*. Four operators, one direction each:

| Operator | Reads as | Direction |
|---|---|---|
| `:` | descend to a contained entity | lateral (the current level) |
| `.` | a property of | inward (the property plane) |
| `:.` | into the internals of | inward (the fiber/mechanism plane) |
| `:+` | up to the containing world | outward (supra — reserved, not yet active) |

```ebnf
path        ::= root step* | step+            (* root elidable at the CLI:   *)
root        ::= name                          (* the RUNNING aggregator is   *)
                                              (* implied -- ".note" = "dz.note" under dz, "wtf.note" under wtf *)
step        ::= ":" name                      (* entity step                 *)
              | ":." name                     (* fiber step                  *)
              | ":+" name                     (* supra step (reserved)       *)
              | "." name                      (* property step -- enters the  *)
                                              (* PROPERTY PLANE, one-way     *)
              | ":" subkey                    (* ONLY inside the property    *)
                                              (* plane: a sub-key INTO the   *)
                                              (* property's value            *)
name        ::= [a-z0-9] [a-z0-9_-]*          (* tree segments: lowercase    *)
subkey      ::= [A-Za-z0-9_] [A-Za-z0-9_-]*   (* sub-keys: CASE-PRESERVING   *)
                                              (* (.env-vars:DEBUG != :debug) *)
listing     ::= path? ":."                    (* a TRAILING bare ":." lists  *)
                                              (* the node's plane            *)
```

Rules the tokenizer enforces: compound operators match first (`:.`/`:+` are never `:` + `.`); once a path enters the property plane, `:.` and `:+` are errors there (a property has no fiber plane); a `:.`-led path whose first segment is not fiber vocabulary is *forgiven* to the property plane and the canonical form is echoed once (`dz :.note` → `dz.note`).

## Command routing (what the first token means)

```ebnf
command     ::= global-flag* ( "--" argparse-form   (* leading bare "--" disables the intercept *)
                             | path-form
                             | argparse-form )      (* bare words: verbs, tools -- as always     *)
path-form   ::= listing                             (* dz :.            -> list the plane        *)
              | path                                (* dz .note         -> READ (get)            *)
              | path value                          (* dz .note "hi"    -> WRITE (upsert + echo) *)
```

The routing mnemonic is the locked doctrine — **dot anywhere = look, all colons = run**:

- `.`/`:.`-led, or any `.` in the path → the **property surface** (never dispatches a tool).
- All-`:` entity path → the leading `:` is stripped and normal dispatch proceeds (`dz :core:safedel` invokes it — root elision for the entity plane).
- `:+`-led → reserved error (supra navigation lands later).

## Values

One token. Quote multi-word values. A bare negative number is a value (`dz :.kit.channels.verbosity -3` — same rule as argparse's own matcher); any other `-`-led value needs a `--` before it. Values parse as: counted verbosity (`vvvv` = +4, `qqq` = −3) → int → float → JSON literal (`true`, `null`, `["a"]`) → plain string. Deleting always requires the explicit verb (`dz prop delete .note`) — no sugar deletes.

## The `=` assignment marker (shipped 0.11.27-alpha / lib 0.10.8-alpha)

```ebnf
assignment  ::= lhs "=" rhs                   (* ONE shell token, split at the FIRST "=" *)
lhs         ::= path | assignable-word        (* assignable-word: reserved property-backed
                                                 bare words -- "level" today *)
rhs         ::= any-text                      (* opaque: multi-word (quote the whole token),
                                                 negatives, "=", or EMPTY (lhs= sets "") *)
```

`dz level=kit` · `dz .note="some words"` · `dz :.kit.channels.verbosity=-3` · `dz .note=` (empty). Spacing is forgiven: `dz level = kit`, `dz level= kit`, and `dz level =kit` all mean `dz level=kit`. The rule: *operator-led addresses are disambiguated by position (the space form stays); bare-word addresses require the marker.* Once rung nodes ship, the space form `dz level kit` flips from SET to NAVIGATE — the marker is what makes that flip safe.

## Not a grammar engine

The RHS of an assignment is never evaluated — `dz .x=(a+b)` stores the string `(a+b)`. If property values ever grow *computed* expressions, an expression grammar (operator precedence, nesting) becomes warranted; until then this grammar stays linear by design.

## Navigating the system: the tree, fibers, and rings

Everything in a dazzlecmd aggregator — levels, kits, tools, verbs, machinery, properties — is a node in **one derived tree**, and every node is addressable and inspectable. `dz info <anything>` renders its card:

```
> dz info :.level              > dz info kit                  > dz info version
dz:.level                      dz:.level:kit                  dz:.meta:verb:version
  kind: Continuum                kind: ContinuumSpace           kind: verb
  contains:                      rung of: dz:.level (rank -1)   help: Show version info
    fiber   rung (rank -5)       contains:
    ...                            activation ...
    supra   rung (rank +1)         visibility ...
```

Three ideas make the layout make sense:

**A rung is a position AND a class.** `dz:media` is *a* kit (an instance, in the containment tree). `dz:.level:kit` is the kit *rung* — both a position on the level ladder and the class of all kits. The structure hanging beneath it (`:visibility`, `:activation`) is what kit-*ness* is made of: policy and machinery that belongs to no single kit and to no other level. That inner structure is a **fiber** — reachable through the `:.` step, and the reason the step exists: without it, class-level structure would have no address.

**Fibers form rings of "aboutness."** Each `:.` step moves one level of indirection inward *about the same subject*: the instance, then the machinery about it, then the structure about that. Named paths address every ring (`dz:.level:kit:visibility:silenced` is "what *silenced* means for kits").

**Per-class defaults are fiber properties.** Because properties cascade down the tree, one write at a rung governs its whole class: `dz :.level:tool.channels.verbosity=-2` quiets *every tool* — no instance path could say that.

### Numeric addresses (shipping incrementally)

Ranks are addresses. The rule is one law: **a segment key selects from the left node's children — a name selects by name, a number selects by rank.** `membership:1` and `membership:add` are the same slot. Siblings ride the parent step: `remove:+1` = up to `membership`, then rank +1 = `add` (and `:++` climbs two levels, like `../..`). `X:0` is the invariant seat — the node itself when the seat is unoccupied. Vacant ranks answer with a hint naming what *is* there. Anonymous rungs created between existing ones self-name as their position (`"5/2"`) until christened with a real name — *names are christenings of positions, not prerequisites*.

### What we're shooting for

The end state is a CLI that is **constructed from its axes** rather than hand-assembled: the tree derives from the live structures, help and cards derive from each item's own metadata, the option surfaces derive from the tree — so adding a verb, a level, or an axis is a *declaration*, and every surface (dispatch, help, info, completion) follows. The operators are deliberately few and single-meaning — `:` select, `.` look, `:.` step inward a ring, `:+` step up — because the power is meant to come from the *structure being uniform*, not from the notation being rich.
