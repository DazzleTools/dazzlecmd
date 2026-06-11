"""``dazzlecmd_lib.core`` -- the constitutional namespace.

Items in this package are *constitutional*: every aggregator that consumes
dazzlecmd-lib at all gets them automatically. They are not opt-in kits and
they are not removable via kit policy. They are necessary for correctness
across every aggregator the library powers.

This is the library-level extension of the ``always_active`` kit flag that
already exists at the aggregator level (``kits/core.kit.json`` carries
``{"always_active": true}``, honored by ``dz kit focus`` / ``disable``).
Where an aggregator *declares* a kit always-active, ``dazzlecmd_lib.core``
items are always-active by *being in the library* -- present in every
consumer by construction.

The grouping/ungrouping contract for constitutional items (see
``docs/guides/grouping-ungrouping.md``):

- **Cannot be UNGROUPED.** A consumer cannot remove a constitutional item
  from dispatch; it is inside every consumer's boundary by construction.
  (This is the P-side "membership locked ON" property -- contract clause C3.)
- **MAY be display-HIDDEN.** A consumer that does not want a constitutional
  item cluttering its surface may hide it from ``dz list`` while it remains
  dispatchable via its canonical FQCN (the reserved ``presentation`` block
  on ``aggregator.json``; the "Hidden" visibility level, not yet wired).
  Display-hidden is a layer-7 projection, never a removal.
- **Canonical FQCN form:** ``dazzlecmd_lib:core:<name>`` (e.g.
  ``dazzlecmd_lib:core:links``). The canonical is axis-invariant: it
  survives every reframing (contract clause C1). A consumer may *project*
  it to render as ``<consumer>:core:<name>`` or collapse it at the display
  layer, but the canonical never changes.

**Default to EXPOSE.** Constitutional items are visible by default; hiding
is an explicit per-consumer opt-in. The framework never auto-hides a
constitutional item -- discoverability is a primary value (a hidden tool is
one a user can never stumble onto).

The **tool boundary contract** (the links-fork DWP, 2026-06-11). A
constitutional primitive is an ENGINE in ``dazzlecmd_lib.core.<name>``,
admitted only because lib code itself requires it -- the bloat guard: the lib
grows when the framework's own capabilities grow, never for convenience
(mode-switching needs ``links`` + ``safedel``; nothing in the lib needs
``find``/``rn``/``listall``, so they stay plain tools). When a user-facing
tool exposes a primitive:

1. **Engine in the lib** -- all logic, data types, and programmatic command
   bodies (functions that do + print and are usable without argparse, e.g.
   safedel's ``cmd_*`` / links' ``scan_directory``).
2. **CLI in the tool** -- argparse builders, ``main()``/dispatch, help text,
   display formatting, exit-code policy. The lib never imports argparse for a
   tool surface.
3. **No second engine** -- the tool imports the lib engine; a duplicate
   definition is a contract violation, ENFORCED by
   ``tests/test_constitutional_contract.py`` (the marker below is a checked
   claim, not a hand-asserted label).
4. The ``[lib]`` marker, the overlay alias, and the absolute FQCN
   ``dazzlecmd_lib:core:<name>`` are derived claims about 1-3 and are
   therefore always true.

This is the "library of engines wrapped by thin public-facing tools" model:
internalizing a tool (tool -> lib) and the inverse (demote) are mechanical
under it, and the future graduation/promotion verbs (#73) get a crisp
substrate.

A THIRD level is recognized but not yet designed: an engine here may itself
graduate OUT into an external sub-library (e.g. link/metadata primitives
finding a better home in dazzle-filekit or a preservelib successor), with
``core.<name>`` becoming a thin import surface over that dependency. That is
promotion at the CLASS/LIBRARY boundary -- a different level of indirection
from dazzlecmd's TOOL boundary -- and is deliberately deferred until a real
candidate forces the design (see the links-fork DWP addendum, 2026-06-11).

Current inhabitants:

- ``dazzlecmd_lib.core.links`` -- link primitives. Link creation/removal
  (``create_link``/``remove_link``/...) that ``mode.py`` depends on, PLUS the
  link DETECTION surface (``detect_link``/``LinkInfo``/the ``LINK_*``
  varieties), relocated from the ``links`` tool (dazzlecmd v0.9.4) so lib code
  imports it as a normal package. ``paths`` re-exports the creation helpers for
  backward compatibility.
- ``dazzlecmd_lib.core.safedel`` -- the recoverable-delete engine (the trash
  store, link-aware staging, metadata preservation, recovery). Relocated from
  the ``projects/core/safedel/`` tool (dazzlecmd v0.9.4-v0.9.6, #38 / #179) so
  every aggregator gets recoverable deletion automatically -- ``mode.py``'s
  swap stages a tool dir here before removing it, with no fallback path. The
  ``projects/core/safedel/`` tool now wraps this primitive with its CLI +
  trash-management UX.

Future inhabitants (tracked, not yet migrated): dazzlelink sidecar detection
(``core.links`` extension, dazzlecmd #82).
"""

from __future__ import annotations


# The names of the constitutional primitives that live in this namespace. A
# tool whose engine is one of these (e.g. the `core:safedel` CLI wrapping
# `dazzlecmd_lib.core.safedel`) is constitutional: its canonical "home" is
# `dazzlecmd_lib:core:<name>` (Scheme O), of which `core:<name>` is the
# consumer projection (Scheme P). Grows as primitives are added (e.g.
# dazzlelink, #82).
_CONSTITUTIONAL_NAMES = frozenset({"links", "safedel"})


def constitutional_names() -> frozenset:
    """Return the set of constitutional primitive names in this namespace."""
    return _CONSTITUTIONAL_NAMES


def is_constitutional(name: str) -> bool:
    """True if ``name`` names a constitutional ``dazzlecmd_lib.core`` primitive.

    ``name`` is the tool's short name (e.g. ``"safedel"``). The constitutional
    canonical for such a tool is ``dazzlecmd_lib:core:<name>``.
    """
    return name in _CONSTITUTIONAL_NAMES


def canonical_fqcn(name: str) -> str:
    """The canonical (Scheme O) FQCN for a constitutional primitive (bones).

    e.g. ``canonical_fqcn("safedel") -> "dazzlecmd_lib:core:safedel"``. This is
    axis-invariant (C1); ``core:<name>`` is the consumer projection (skin).
    """
    return f"dazzlecmd_lib:core:{name}"
