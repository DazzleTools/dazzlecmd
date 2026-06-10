"""Behavioral types for the ``Groupable`` verbs -- the state-transition operators.

This module houses the verb-support types so ``entity.py`` stays focused on the
entity model. It imports NOTHING from ``engine``/``mode`` -- each context
receives the handle it operates on (an ``FQCNIndex``, a filesystem context),
which keeps this module dependency-light and the verbs unit-testable against
real components.

Design (see the #84 behavioral-phase DWP + its 2026-06-09 hole-review addendum):

- The verbs are NOT entity-local: the mechanisms they drive (alias routing on
  ``FQCNIndex``, mode state on the filesystem) live outside the entity. So a
  verb takes an explicit ``context`` -- a :class:`RebindContext` -- that carries
  both the handle AND the identity the verb itself can't (e.g. WHICH alias).
- ``Groupable.rebind`` is a thin delegate: ``return context.apply(self, target)``.
  Each rebind sub-kind is a new context impl rather than a branch inside the
  verb -- this protocol IS the generalizable seam the PoC validates.
- C2 (the restorability invariant) is modeled as a per-transition
  :class:`RebindInvariant` naming the conserved quantity; :class:`RebindReceipt`
  records the transition so the round-trip (``rebind o rebind^-1 = identity``)
  is assertable. ``CriticalityBoundaryError`` marks where the invariant cannot
  be preserved (the transition would be irreversible -> refuse).

``Frame`` (reserved): a presentation/consumer context that ``hide``/``expose``
will consume (it ties to ``AggregatorConfig.presentation``). ``rebind`` is NOT
frame-relative, so Frame is only reserved here, not built.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class CriticalityBoundaryError(Exception):
    """Raised when a transition would cross a criticality boundary.

    The conserved invariant (C2) cannot be preserved, so the transition would
    be irreversible/non-restorable -- it is refused rather than performed.

    Example: a mode-switch ``rebind`` whose published state cannot be re-derived
    (no remote URL resolvable) would be a lossy, unrecoverable change.

    This is a PRE-FLIGHT refusal (the invariant check fails before any change).
    """


class RebindError(Exception):
    """Raised when a rebind transition fails to APPLY.

    Distinct from :class:`CriticalityBoundaryError` (a pre-flight refusal): the
    invariant was fine, but the underlying mechanism failed mid-apply (e.g. the
    mode-switch returned a non-zero exit code). The transition's success/failure
    is the mechanism's; this surfaces it as the verb's typed failure.
    """


@dataclass(frozen=True)
class RebindInvariant:
    """C2 descriptor: the quantity conserved across a ``rebind`` transition.

    Naming the invariant explicitly is what makes the round-trip property
    (``rebind o rebind^-1 = identity``) machine-checkable rather than vague.

    - alias rebind: the conserved quantity is the binding owner's canonical
      identity (C1 ``fqcn`` -- it never changes; only the alias pointer moves,
      under the single-hop rule).
    - mode-switch rebind (Phase 2): the remote URL (always re-derivable, so the
      published state can be restored).
    """

    conserved_quantity_name: str   # e.g. "single_hop_rule", "remote_url"
    conserved_value: Any           # the value at transition time
    restore_path: str = ""         # human note on how it is re-derived


@dataclass(frozen=True)
class RebindReceipt:
    """The record returned by ``entity.rebind()`` on success.

    Enables asserting the transition and composing its inverse: after
    ``r = e.rebind(B, context=ctx)``, rebinding back to ``r.previous_state``
    restores the prior state (while ``r.reversible`` is True).
    """

    entity_fqcn: str               # C1 identity of the binding owner (UNCHANGED)
    sub_kind: str                  # "alias" | "mode-switch"
    previous_state: Any            # the inverse target (e.g. prior canonical FQCN)
    new_state: Any                 # what it is now
    invariant: RebindInvariant
    reversible: bool               # True iff the inverse verb restores prior state
    verb: str = "rebind"


class RebindContext(Protocol):
    """The context a ``rebind`` operates within (the verb is not entity-local).

    Each rebind sub-kind implements this protocol, encapsulating its mechanism
    and carrying the identity the verb itself lacks. ``Groupable.rebind``
    delegates to ``context.apply(self, target)``; ``undo`` inverts a receipt so
    callers (and the ``assert_round_trip`` harness) need not track the new owner.
    """

    def apply(self, entity: Any, target: Any) -> RebindReceipt:  # pragma: no cover - protocol
        ...

    def undo(self, receipt: RebindReceipt) -> RebindReceipt:  # pragma: no cover - protocol
        ...


@dataclass
class AliasRebindContext:
    """Repoint the alias ``alias`` (currently owned by the receiver) to a
    different canonical FQCN, within the given ``FQCNIndex``.

    In-memory only: ``alias_index`` lives on the index. **Persistence is out of
    PoC scope** -- the index is rebuilt from manifests/config every CLI
    invocation, so a repoint evaporates with the process (DWP addendum H4). Do
    not wire a user-facing ``dz rebind`` to this path until a persistence design
    exists.

    The index (duck-typed) must expose ``alias_index`` and ``repoint_alias``.
    """

    index: Any
    alias: str

    def apply(self, entity: Any, target: str) -> RebindReceipt:
        # Receiver precondition: the receiver must CURRENTLY own this alias
        # (the alias must resolve to the receiver's canonical FQCN). This one
        # check catches both wrong-index and wrong-receiver. The inverse call is
        # therefore made on the NEW owner -- "receiver = current owner" stays
        # consistent across the round-trip (DWP addendum H1).
        current = self.index.alias_index.get(self.alias)
        if current is None:
            raise KeyError(
                f"alias {self.alias!r} is not registered in this index"
            )
        if current != entity.fqcn:
            raise ValueError(
                f"rebind receiver mismatch: alias {self.alias!r} currently "
                f"points at {current!r}, not the receiver {entity.fqcn!r}. "
                f"Call rebind on the alias's current owner."
            )
        previous = self.index.repoint_alias(self.alias, target)
        return RebindReceipt(
            entity_fqcn=entity.fqcn,        # C1 -- unchanged by the rebind
            sub_kind="alias",
            previous_state=previous,        # repoint back here to invert
            new_state=target,
            invariant=RebindInvariant(
                conserved_quantity_name="single_hop_rule",
                conserved_value=entity.fqcn,
                restore_path="repoint the alias back to previous_state",
            ),
            reversible=True,                # alias repoint is always reversible
        )

    def undo(self, receipt: RebindReceipt) -> RebindReceipt:
        """Invert a prior ``apply``: repoint the alias back to
        ``receipt.previous_state``.

        Entity-free -- the context owns the alias and the index, so it looks up
        the CURRENT owner itself. This is where the receiver asymmetry of
        ``apply`` dissolves (DWP addendum H1): after the apply the alias points at
        the apply's target, and ``undo`` simply points it back, without the caller
        having to know who the new owner is. Always reversible.
        """
        current = self.index.alias_index.get(self.alias)
        if current is None:
            raise KeyError(
                f"alias {self.alias!r} is not registered in this index"
            )
        self.index.repoint_alias(self.alias, receipt.previous_state)
        return RebindReceipt(
            entity_fqcn=receipt.entity_fqcn,    # C1 -- unchanged
            sub_kind="alias",
            previous_state=current,             # where it pointed before this undo
            new_state=receipt.previous_state,   # the restored target
            invariant=RebindInvariant(
                conserved_quantity_name="single_hop_rule",
                conserved_value=receipt.entity_fqcn,
                restore_path="repoint the alias back to previous_state",
            ),
            reversible=True,
        )
