# Principles

This file documents the architectural principles that have shaped dazzlecmd's
design across Phases 0-4. They're the constraints a new contributor (or a
future maintainer making a pull request) should keep in mind. Some are load-
bearing -- violating them would require a major redesign. Others are
conventions we've found valuable but aren't absolute.

Principles are numbered for reference in commit messages and issue
discussions (e.g., "see Principle #14"). Order reflects rough rationale
dependency, not importance.

---

## Product principles (how the engine behaves)

### 1. dazzlecmd is an instance, not the root

The engine is generic. "dazzlecmd" and its `dz` command are one
configuration of `AggregatorEngine`; other configurations (wtf-windows,
third-party aggregators) can exist with different names, different
meta-commands, different kits. Code should never assume it IS dazzlecmd.

### 2. Each layer describes only itself

A tool's manifest describes the tool, not the kit. A kit's manifest
describes the kit, not the aggregator. An aggregator's registry pointer
describes its local view. Moving a tool between kits doesn't require
rewriting the tool.

### 3. `:` is the namespace separator; FQCN is authoritative

Fully Qualified Collection Names (`kit:tool`, `aggregator:kit:tool`) are
the source of truth. Short names and kit-qualified names are convenience
for users at the command line. The engine resolves via FQCN internally.

### 4. Convention over configuration

If `kits/` exists in a directory, it's an aggregator. If a manifest declares
`setup.platforms.linux.debian`, that's where Debian setup lives. Magic paths
and schema shapes beat extensive configuration files.

### 5. Precedence with notification, not hard error

Two kits declaring the same short name `list` -> the user's FQCN or kit-
qualified form wins. Core wins by default when no user preference is set.
Collisions notify ("two tools named `list`; disambiguate with FQCN") but
don't block discovery.

### 6. Auto-remap on import; children don't know about parents

When wtf-windows is imported as a kit into dazzlecmd, wtf's tools become
`wtf:<toolname>` in dazzlecmd's namespace. wtf-windows itself doesn't know
it's been imported; the aggregator handles the remapping.

### 7. Suppress meta-commands on import (`is_root` flag)

An imported aggregator's meta-commands (`list`, `info`, `kit`, `tree`) are
NOT exposed at the parent level. Only the parent's own meta-commands show.
Prevents command-name collision and mental-model confusion.

### 8. Cycle detection via loading stack

Kit A imports Kit B which imports Kit A would infinite-loop during
discovery. The loader maintains a stack of kits being loaded and errors
cleanly on re-entry.

### 9. Git is the distribution channel; no central registry

Kits are distributed via git submodules, subtrees, or copies. `dz kit add
org/repo` uses GitHub shorthand. No centralized package registry, no
server-side blessing process. The trust model (#39, future) and kit
sandbox (#44, future) are the security layers; distribution stays
decentralized.

### 10. Dispatcher, not package manager

THE LOAD-BEARING PRINCIPLE. The engine faithfully executes what the manifest
declares. It does NOT:
- install dependencies (pip, npm, apt, etc.)
- create virtual environments
- build binaries from source
- download or pull container images
- manage setup state
- auto-update tools
- perform version resolution

`dz setup <tool>` runs the tool's declared setup command. That's it. The
line between "dispatcher" and "package manager" is the line between
running what you're told and making decisions on the user's behalf. We
stay on the dispatcher side.

### 11. Sugar is for scaffolding, not runtime

`dz new` can opinionate about how to structure a new tool (pyproject.toml,
tests/, README.md, etc.). `dz <tool>` cannot opinionate about how to run
an existing tool -- runtime behavior is strictly manifest-driven.
Scaffolding is a development-time convenience; dispatch is a user-time
contract.

### 12. The engine CAN dispatch setup

`dz setup <tool>` runs the tool's declared `setup.command`. This is NOT a
violation of Principle #10 -- the engine doesn't decide what to install;
it executes what the author declared, when the user asks. The engine
never runs setup automatically or infers that setup is needed.

### 13. User owns primacy

Any tool or kit can become "primary" via user config (enable, disable,
favorite, shadow, silence). The engine defers to the user's choices.
Third-party kit authors can't override the user's preferences; users can't
have their preferences overridden by the engine's defaults without
explicit action.

### 14. Listing is safe; execution is not

Discovery, listing, tree, info, search -- none of these execute tool code.
Only `dz <tool>` (dispatch) and `dz setup <tool>` run author-declared
code. This is the security boundary. A malicious tool in an added kit
cannot execute on `dz list` or `dz info` -- the user has to explicitly
opt in by running the tool.

Practical consequence: manifest fields that would trigger code execution
at listing time (e.g., `runtime_extensions` pointing at a Python module
path) are deferred until a trust-model story exists. See issue #32, #39.

### 15. Language-neutral data contracts

Manifest schemas are the spec; Python is one implementation of that spec.
Schema decisions should survive a rewrite in any language. No Python
callable references in manifests, no language-specific regex dialects, no
pickle. JSON structures are the spec; detection primitives are declarative
matchers; shell commands are universally consumable strings.

A future Rust or Go port of dazzlecmd should be able to read the same
manifests and produce identical dispatch behavior.

---

## Process principles (how we develop)

These emerged from session experience and are captured in feedback memories.
Less universal than the product principles but worth codifying.

### P1. Design before implementation for architecturally significant work

Complex features (conditional dispatch, `_vars` substitution, shared
library modules) get a dev-workflow-process doc BEFORE code. Simple
features and implementation details don't -- consult prior art (Ansible,
Jinja2, etc.) and iterate. The distinction is "is this a design
decision or an implementation detail?"

### P2. Ship small self-sufficient slices rather than waiting for full design

When a feature has many planned extensions, ship the minimum viable slice
first. `_vars` v1 ships base substitution + nesting; list values, filters,
escape hatches, env-var promotion are all deferred with clear unblock
conditions. Half-features depending on future phases get parked; flag
cross-phase dependencies explicitly.

### P3. Ecosystem momentum: weight migration cost higher than YAGNI purity

When deciding whether to share a concern as a library primitive, consider
how expensive adding it LATER would be if third-party kits already depend
on a non-shared shape. Waiting for pain only works when the cost of
adding the shared layer later is bounded; with multiple consumers
already depending on the API, it isn't. Ship shared substrate EARLY.

### P4. Tester agent after checklist

After a feature ships automated tests AND a human checklist, run the
tester agent against the checklist BEFORE commit. Automated tests catch
mocked-path regressions; the tester agent catches UX issues, shell
rendering quirks, real subprocess behavior, error-message quality. Five
minutes of tester time per release has paid off consistently -- every
invocation has caught at least one bug.

### P5. Commit granularity is for rollback, not topic tidiness

Clean commits serve as rollback boundaries, not as logical-narrative
organization. Fold small doc additions / single-file polish / minor
changes into the in-flight commit. Separate commits when the change could
need independent rollback, has a different risk profile (code vs docs),
or is genuinely large.

### P6. Commit size is not a target

LOC estimates are informational, not approval items. The right size for
a commit is however big it needs to be to ship a coherent unit of
correctness. Don't split a feature to hit a size budget; don't pad one
either. Correctness and future-compat fit matter; size is emergent.

---

## When principles conflict

Principle conflicts happen. Record examples:

**#10 (dumb dispatcher) vs #12 (engine CAN dispatch setup)**: setup
dispatch is a carve-out, not a violation. The engine still runs only
what's declared; declaring `setup.command` is the author opting in to
setup dispatch.

**#14 (listing is safe) vs runtime_extensions** (kit-declared custom
runtime types): letting kits auto-load Python modules at listing time
violates #14. Resolution: runtime_extensions is deferred until the trust
model (#39) lands with opt-in trust flags per-kit. See issue #32.

**#2 (each layer describes only itself) vs `inner_runtime`** (Docker
manifest field): `inner_runtime` describes what runs INSIDE the container,
blurring the "describe only yourself" line. Resolution: it's informational
only in v0.7.21 -- doesn't influence dispatch, just surfaces in `dz info`
for human readers. Doesn't actually violate #2 because the outer
manifest isn't making decisions based on inner-runtime values.

---

## When principles evolve

New principles added across releases (v0.7.0 onward):

- **v0.7.0 origins**: Principles 1-9 from the original Rnd4 architecture assessment
- **v0.7.9 (Phase 2)**: Principle #3 crystallized (`:` FQCN separator)
- **v0.7.11 (Phase 3)**: Principles #13 (user owns primacy), #5 (precedence with notification)
- **v0.7.13 (Phase 4b)**: Principle #10 (dispatcher not package manager) made explicit
- **v0.7.14 (Phase 4b)**: Principle #12 (engine CAN dispatch setup)
- **v0.7.17-19**: Principle #14 (listing is safe) crystallized during security discussion
- **v0.7.19**: Principle #15 (language-neutral data contracts) added in Addendum 4 of #40
- **This release (v0.7.21)**: Principles extracted into this file; no new principles added

When a new architectural decision establishes a durable constraint, add it
here. Don't retire a principle without marking it explicitly ("Superseded
by #N in vX.Y.Z") -- future readers need to see the evolution.

## Related

- Feedback memories in `~/.claude/projects/C--code-dazzlecmd-local/memory/` carry the development-process principles in more detail (one memory per calibration; this file summarizes and codifies)
- CHANGELOG.md traces when each principle's code-level manifestation shipped
- Project-private dev-workflow-process docs cite these principles throughout their "considerations" and "synthesis" sections
