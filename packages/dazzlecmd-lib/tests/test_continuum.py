"""The Continuum primitive (the signed ordered-axis with an invariant-bearing
zero) -- validated against BOTH backings the design must serve: the visibility
ladder (channel-backed) and the THAC0 logger (scalar). See the continuum DWP
(2026-06-13__12-50-32...).
"""
import pytest

from dazzlecmd_lib.continuum import (
    Continuum,
    ContinuumProtocol,
    ContinuumError,
    ContinuumBoundaryError,
)


# --- the two real continua -------------------------------------------------
def _visibility():
    """The visibility ladder as a channel-backed continuum: visible(0, neutral)
    .. shadowed(-3, cold pole). Mirrors groupable.VISIBILITY_LADDER."""
    return Continuum(
        name="visibility",
        ranks={"visible": 0, "silenced": -1, "hidden": -2, "shadowed": -3},
        invariant="canonical_dispatch",
        channels={
            "visible": frozenset(),
            "silenced": frozenset({"hints"}),
            "hidden": frozenset({"hints", "display"}),
            "shadowed": frozenset({"hints", "display", "resolution"}),
        },
    )


def _thac0():
    """The THAC0 log-verbosity continuum (scalar): NOTHING(-4) .. DEFAULT(0) ..
    DEBUG(+3). The asymmetric signed range THAC0 actually uses."""
    return Continuum(
        name="verbosity",
        ranks={"nothing": -4, "error": -3, "warning": -2, "minimal": -1,
               "default": 0, "timing": 1, "config": 2, "debug": 3},
        invariant="default_output",
    )


class TestOrderAndPoles:
    def test_rank_and_neutral(self):
        v = _visibility()
        assert v.rank("visible") == 0 and v.rank("shadowed") == -3
        assert v.neutral() == "visible"             # the invariant-bearing 0
        assert v.cold_pole() == "shadowed"
        assert v.warm_pole() == "visible"           # asymmetric: 0 is the warm end here

    def test_thac0_zero_is_default_not_an_end(self):
        t = _thac0()
        assert t.neutral() == "default"             # 0 is the center, not a pole
        assert t.cold_pole() == "nothing" and t.warm_pole() == "debug"
        assert t.rank("default") == 0

    def test_levels_ordered_cold_to_warm(self):
        assert _visibility().levels() == ("shadowed", "hidden", "silenced", "visible")

    def test_compare_warmer_colder(self):
        v = _visibility()
        assert v.is_colder("shadowed", "visible")
        assert v.is_warmer("visible", "hidden")
        assert v.compare("hidden", "hidden") == 0

    def test_duplicate_ranks_rejected(self):
        with pytest.raises(ContinuumError, match="duplicate ranks"):
            Continuum(name="bad", ranks={"a": 0, "b": 0})

    def test_unknown_level_raises(self):
        with pytest.raises(ContinuumError, match="not a level"):
            _visibility().rank("bogus")


class TestStepping:
    def test_step_walks_one_rung(self):
        v = _visibility()
        assert v.step("visible", -1) == "silenced"   # colder
        assert v.step("shadowed", +1) == "hidden"    # warmer
        assert v.step("hidden", 0) == "hidden"       # identity

    def test_step_past_pole_raises_boundary(self):
        v = _visibility()
        with pytest.raises(ContinuumBoundaryError, match="cold pole"):
            v.step("shadowed", -1)                   # already at the cold pole
        with pytest.raises(ContinuumBoundaryError, match="warm pole"):
            v.step("visible", +1)                    # already at the warm pole


class TestLensDuality:
    """The warm/cold framings (the {P, not-P} / RGB-CMYK duality): `more`/`less`
    are unambiguous WITHIN a lens, and `warm.more == cold.less` across them."""

    def test_warm_lens_more_is_warmer(self):
        v = _visibility()
        assert v.warm.more("shadowed") == "hidden"   # toward warm (+)
        assert v.warm.less("visible") == "silenced"  # toward cold (-)

    def test_cold_lens_more_is_colder(self):
        v = _visibility()
        assert v.cold.more("visible") == "silenced"  # toward cold (-)
        assert v.cold.less("shadowed") == "hidden"   # toward warm (+)

    def test_cross_lens_identity(self):
        """warm.more == cold.less and warm.less == cold.more (the duality)."""
        v = _visibility()
        for lvl in ("silenced", "hidden"):
            assert v.warm.more(lvl) == v.cold.less(lvl)
            assert v.warm.less(lvl) == v.cold.more(lvl)

    def test_lens_pole(self):
        v = _visibility()
        assert v.warm.pole() == "visible"            # warm framing -> warm pole
        assert v.cold.pole() == "shadowed"           # cold framing -> cold pole

    def test_lens_respects_pole_boundary(self):
        v = _visibility()
        with pytest.raises(ContinuumBoundaryError):
            v.warm.more("visible")                   # can't go warmer than the warm pole
        with pytest.raises(ContinuumBoundaryError):
            v.cold.more("shadowed")                  # can't go colder than the cold pole

    def test_domain_verbs_bind_to_a_framing(self):
        """The user-facing verbs map onto a framing -- hide=cold.more (suppress
        more), expose=warm.more (show more) -- without ever saying 'warm'."""
        v = _visibility()
        hide = v.cold.more
        expose = v.warm.more
        assert hide("visible") == "silenced"
        assert expose("silenced") == "visible"

    def test_thac0_warm_framing(self):
        t = _thac0()
        assert t.warm.more("default") == "timing"    # louder / more verbose
        assert t.warm.less("default") == "minimal"   # quieter


class TestThresholdPredicate:
    def test_thac0_emit_gate(self):
        """passes(level, threshold) == level-rank <= threshold-rank (the logger
        emit gate). At DEFAULT(0) threshold: default+colder pass; warmer (debug)
        does not."""
        t = _thac0()
        assert t.passes("default", "default")        # 0 <= 0
        assert t.passes("error", "default")          # -3 <= 0
        assert t.passes("nothing", "default")        # -4 <= 0
        assert not t.passes("debug", "default")      # +3 <= 0 is False
        assert t.passes("debug", "debug")            # +3 <= +3
        assert t.passes("config", "debug")           # +2 <= +3


class TestChannelBacking:
    def test_channels_at(self):
        v = _visibility()
        assert v.channels_at("visible") == frozenset()
        assert v.channels_at("shadowed") == frozenset({"hints", "display", "resolution"})

    def test_level_for_channels_presets(self):
        v = _visibility()
        assert v.level_for_channels(frozenset()) == "visible"
        assert v.level_for_channels(frozenset({"hints"})) == "silenced"
        assert v.level_for_channels(frozenset({"hints", "display"})) == "hidden"
        assert v.level_for_channels(
            frozenset({"hints", "display", "resolution"})) == "shadowed"

    def test_level_for_channels_non_preset_highest_wins(self):
        """A manual non-preset edit maps to the level introducing the highest
        channel present -- {display} alone -> hidden (NOT visible). This is the
        exact semantics of groupable.level_for_channels."""
        v = _visibility()
        assert v.level_for_channels(frozenset({"display"})) == "hidden"
        assert v.level_for_channels(frozenset({"resolution"})) == "shadowed"

    def test_scalar_continuum_has_no_channels(self):
        with pytest.raises(ContinuumError, match="scalar"):
            _thac0().level_for_channels(frozenset())


class TestParity:
    """The Continuum reproduces groupable's inline visibility logic exactly --
    the re-home is behavior-identical (keystone of the vertical slice)."""

    def test_matches_groupable_level_for_channels(self):
        from dazzlecmd_lib.groupable import (
            level_for_channels as inline, VISIBILITY_LADDER, VISIBILITY_ORDER,
        )
        v = _visibility()
        # ranks/channels agree with the inline tables.
        assert v.levels()[::-1] == VISIBILITY_ORDER     # warm->cold == declared order
        for lvl, chans in VISIBILITY_LADDER.items():
            assert v.channels_at(lvl) == chans
        # level_for_channels agrees on every subset of the channel universe.
        import itertools
        universe = ["hints", "display", "resolution"]
        for r in range(len(universe) + 1):
            for combo in itertools.combinations(universe, r):
                s = frozenset(combo)
                assert v.level_for_channels(s) == inline(s), s

    def test_satisfies_protocol(self):
        assert isinstance(_visibility(), ContinuumProtocol)


class TestPurity:
    """The continuum module is PURE -- no effectful imports -- so it stays
    eligible to lift into the dazzle-lib bedrock (DWP charter)."""

    def test_continuum_is_pure(self):
        import dazzlecmd_lib.continuum as mod
        import inspect
        src = inspect.getsource(mod)
        for banned in ("import os", "import subprocess", "import sys",
                       "import pathlib", "from os", "from subprocess",
                       "import platform", "open("):
            assert banned not in src, f"continuum.py must not use {banned!r} (purity charter)"
