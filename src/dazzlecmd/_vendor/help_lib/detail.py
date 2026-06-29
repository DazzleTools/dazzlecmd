"""Help-DETAIL as a Continuum + the coordinate-query seam (DWP-C).

help_lib's `contexts` ('minimal'/'standard'/'full') was an unordered `Set[str]` with
an IMPLICIT ordering `minimal < standard < full`. This materializes that ordering as
a `dazzle_lib.Continuum` and adds `items_for_rank()` -- the "content at a coordinate"
hook `cli_lib` (DWP-D) uses to ask "what applies at THIS detail level?", generalizing
the bare `context in item.contexts` string membership filter.

DEVELOPMENT NOTE: added for dazzlecmd (NOT in the original wtf-windows `help_lib`,
which used unordered string sets) -- the help_lib continuum integration. When help_lib
extracts to `dazzle_helplib` this travels with it (and gains the `dazzle_lib` dep).
See `_VENDORED.md`. `Hint.context` ('error'/'result'/'verbose') is a TRIGGER enum, NOT
a detail rung -- it stays off this axis.
"""
from typing import Iterable, List

from dazzle_lib.continuum import Continuum

# Help detail: terser <-> richer. The invariant (rank 0) is the DEFAULT detail
# (standard); `minimal` is colder (less), `full` warmer (more).
DETAIL_CONTINUUM = Continuum(
    name="detail",
    ranks={"minimal": -1, "standard": 0, "full": 1},
    invariant="standard detail",
)

_DETAIL_RUNGS = set(DETAIL_CONTINUUM.ranks)
_DEFAULT_RANK = DETAIL_CONTINUUM.rank("standard")  # 0


def min_detail_rank(contexts: Iterable[str]) -> int:
    """An item's COLDEST declared detail rung -- the least detail at which it shows.
    Non-detail contexts (trigger names, etc.) are ignored; an item with no detail
    context defaults to `standard` (the invariant)."""
    rungs = [DETAIL_CONTINUUM.rank(c) for c in contexts if c in _DETAIL_RUNGS]
    return min(rungs) if rungs else _DEFAULT_RANK


def items_for_rank(items: Iterable, rank: int) -> List:
    """The content items that show AT detail ``rank`` -- those whose coldest detail
    rung is ``<= rank`` (so they appear at that detail and every RICHER one). The
    coordinate-query seam: filter content by a position on the detail Continuum, not
    by a bare string. ``items`` are any objects exposing a ``contexts`` iterable
    (e.g. help_lib ``HelpContent``)."""
    return [it for it in items if min_detail_rank(it.contexts) <= rank]
