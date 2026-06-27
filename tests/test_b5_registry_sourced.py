"""B5: the kit lifecycle verbs are sourced from the lib VERB_AXES registry.

`LIFECYCLE_PAIRS` (dazzlecmd's `kit_verbs`) used to be a hand-written second
declaration of the same data the lib registry holds. B5 makes it a DERIVED VIEW
over `VERB_AXES` -- one source -- so a new aligned `VerbAxis` surfaces in
`dz kit` for free, and the deprecated `KitVerbPair` tuple can't drift from the
registry. `commands/kit_membership` reads the registry directly (`axis_by_name`).
"""
from dazzlecmd.kit_verbs import LIFECYCLE_PAIRS
from dazzlecmd_lib.verb_axis import VERB_AXES, COUPLING_ALIGNED, KIT, axis_by_name


def _aligned_kit_axes():
    return [va for va in VERB_AXES
            if va.coupling == COUPLING_ALIGNED and KIT in va.applies_at]


def test_lifecycle_pairs_derive_from_verb_axes():
    aligned = _aligned_kit_axes()
    assert len(LIFECYCLE_PAIRS) == len(aligned)
    for pair, va in zip(LIFECYCLE_PAIRS, aligned):
        assert pair.axis == va.axis
        assert pair.warm == va.warm and pair.cold == va.cold
        assert pair.coupling == va.coupling and pair.gloss == va.gloss


def test_lifecycle_ranks_run_the_gradient():
    # The coldward rank is the negative position along the aligned gradient
    # (activation -1, loading -2, membership -3) -- the historical ranks.
    assert [p.rank for p in LIFECYCLE_PAIRS] == [-1, -2, -3]


def test_lifecycle_axes_are_the_three_aligned():
    assert [p.axis for p in LIFECYCLE_PAIRS] == [
        "activation", "loading", "membership"]
    assert [p.warm for p in LIFECYCLE_PAIRS] == ["enable", "attach", "add"]


def test_favorite_excluded_from_lifecycle():
    # projection (favorite/unfavorite) is COUPLING_INDEPENDENT -- not on the
    # lifecycle gradient, so it is NOT a lifecycle pair (it's context-bound).
    assert "favorite" not in [p.warm for p in LIFECYCLE_PAIRS]
    assert axis_by_name("projection") is not None  # but it IS in the registry
