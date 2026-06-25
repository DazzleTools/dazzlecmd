"""B2 -- the grammar-axis contract test (SD-0 AC0-2/AC0-3/AC0-6, master contract H1).

Binds three things so they cannot silently drift:
  - the dazzlecmd-lib ``VERB_AXES`` registry + ``meta_tag_for`` bridge (the oracle),
  - this repo's ``LIFECYCLE_PAIRS`` (the axes wired as ``on``/``off`` groups),
  - the actual CLI grammar (``build_parser``).

For every lifecycle axis, ``dz kit <axis> on|off|<special>`` must parse to the
canonical ``_meta`` tag the registry generates (``on`` -> warm, ``off`` -> cold).
As the registry grows (tool/aggregator axes, new levels), extend the wiring and
this contract covers them automatically. Off-model grammar -- a github axis with
no matching ``VerbAxis`` -- fails here (``meta_tag_for`` raises rather than invent
a tag). The whole file ``importorskip``s the lib registry (ships in
dazzlecmd-lib >= 0.9.1), so it is inert on an older library.
"""
import pytest

from dazzlecmd.cli import build_parser
from dazzlecmd.kit_verbs import LIFECYCLE_PAIRS

verb_axis = pytest.importorskip("dazzlecmd_lib.verb_axis")
ON, OFF, WARM, COLD, KIT = (
    verb_axis.ON, verb_axis.OFF, verb_axis.WARM, verb_axis.COLD, verb_axis.KIT)
meta_tag_for = verb_axis.meta_tag_for
axis_by_name = verb_axis.axis_by_name


def _arg_for(axis, pole):
    """The positional the parser needs: membership-warm (add) takes a git URL;
    everything else takes a kit name."""
    if axis == "membership" and pole == WARM:
        return "https://example.com/y.git"
    return "foo"


@pytest.mark.parametrize("pair", LIFECYCLE_PAIRS, ids=lambda p: p.axis)
class TestGrammarAxisContract:
    def test_lib_axis_exists_for_this_github_axis(self, pair):
        # Off-model guard: a github lifecycle axis must have a matching VerbAxis.
        assert axis_by_name(pair.axis) is not None, \
            f"github axis {pair.axis!r} has no dazzlecmd-lib VerbAxis"

    def test_on_off_and_specials_parse_to_the_registry_tag(self, pair):
        # The heart of the contract: every addressing form at this axis parses to
        # the canonical tag meta_tag_for generates -- the parser and the registry
        # agree, by construction.
        parser = build_parser([])
        for token, pole in [(ON, WARM), (pair.warm, WARM),
                            (OFF, COLD), (pair.cold, COLD)]:
            ns = parser.parse_args(
                ["kit", pair.axis, token, _arg_for(pair.axis, pole)])
            expected = meta_tag_for(pair.axis, pole, KIT)
            assert ns._meta == expected, \
                f"`kit {pair.axis} {token}` -> {ns._meta!r}, expected {expected!r}"

    def test_warm_is_is_the_warm_pole(self, pair):
        va = axis_by_name(pair.axis)
        assert va.warm_is == va.warm == pair.warm


def test_off_model_axis_has_no_registry_tag():
    # A made-up axis is not in the registry -> meta_tag_for raises (the contract
    # rejects off-model grammar rather than inventing a dispatch tag).
    with pytest.raises(KeyError):
        meta_tag_for("teleportation", WARM, KIT)
