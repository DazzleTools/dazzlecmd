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

## PROPOSED (pending ratification): the `=` assignment marker

```ebnf
assignment  ::= lhs "=" rhs                   (* ONE shell token, split at the FIRST "=" *)
lhs         ::= path | assignable-word        (* assignable-word: reserved property-backed
                                                 bare words -- "level" today *)
rhs         ::= any-text                      (* opaque: multi-word (quote the whole token),
                                                 negatives, "=", or EMPTY (lhs= sets "") *)
```

`dz level=kit` · `dz .note="some words"` · `dz :.kit.channels.verbosity=-3` · `dz .note=` (empty). The rule: *operator-led addresses are disambiguated by position (the space form stays); bare-word addresses require the marker.* Once rung nodes ship, the space form `dz level kit` flips from SET to NAVIGATE — the marker is what makes that flip safe.

## Not a grammar engine

The RHS of an assignment is never evaluated — `dz .x=(a+b)` stores the string `(a+b)`. If property values ever grow *computed* expressions, an expression grammar (operator precedence, nesting) becomes warranted; until then this grammar stays linear by design.
