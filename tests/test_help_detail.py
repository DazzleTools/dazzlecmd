"""DWP-C: help-detail materialized as a `dazzle_lib.Continuum`, and the
`items_for_rank` coordinate-query seam (the hook cli_lib uses to ask "what content
applies at THIS detail level?")."""
from dazzlecmd._vendor.help_lib.detail import (
    DETAIL_CONTINUUM, min_detail_rank, items_for_rank)
from dazzlecmd._vendor.help_lib.core import HelpContent


def _item(item_id, contexts):
    return HelpContent(id=item_id, command="c", description="d",
                       contexts=set(contexts))


def test_detail_continuum_ordered_with_standard_invariant():
    c = DETAIL_CONTINUUM
    assert c.rank("standard") == 0                # the invariant rung
    assert c.is_warmer("full", "standard")        # full = MORE detail
    assert c.is_colder("minimal", "standard")     # minimal = LESS detail


def test_min_detail_rank_is_the_coldest_declared_rung():
    assert min_detail_rank({"minimal"}) == -1
    assert min_detail_rank({"standard", "full"}) == 0    # coldest wins
    assert min_detail_rank({"full"}) == 1
    assert min_detail_rank({"tutorial"}) == 0            # non-detail -> standard


def test_items_for_rank_filters_by_detail_coordinate():
    items = [_item("a", {"minimal"}), _item("b", {"standard"}),
             _item("c", {"full"})]
    assert {it.id for it in items_for_rank(items, -1)} == {"a"}            # minimal
    assert {it.id for it in items_for_rank(items, 0)} == {"a", "b"}        # +standard
    assert {it.id for it in items_for_rank(items, 1)} == {"a", "b", "c"}   # +full
