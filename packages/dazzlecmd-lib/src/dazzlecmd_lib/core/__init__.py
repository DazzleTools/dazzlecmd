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

Current inhabitants:

- ``dazzlecmd_lib.core.links`` -- link primitives (symlink/junction
  detection and creation) that ``mode.py`` and ``render_info`` depend on
  for correctness across every aggregator. Relocated here from
  ``dazzlecmd_lib.paths`` in v0.7.0 (dazzlecmd v0.8.0); ``paths`` re-exports
  them for backward compatibility.

Future inhabitants (tracked, not yet migrated): a safe-deletion primitive
(``core.safedel``, dazzlecmd #38) and dazzlelink sidecar detection
(``core.links`` extension, dazzlecmd #82). Both already exist as code inside
``projects/core/safedel/_lib/preservelib/`` and will consolidate here.
"""

from __future__ import annotations
