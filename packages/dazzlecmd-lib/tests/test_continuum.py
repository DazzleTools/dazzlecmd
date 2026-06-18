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
    ContinuumSpace,
    ContinuumSpaceProtocol,
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
        from dazzlecmd_lib.contexts import (
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


# --- ContinuumSpace: N parallel axes on one shared presence scale -----------
def _activation():
    """The activation axis: enabled(0, neutral) .. disabled(-1, cold pole)."""
    return Continuum(
        name="activation",
        ranks={"enabled": 0, "disabled": -1},
        invariant="dispatch_active",
    )


def _kit_presence_space():
    """Two PARALLEL presence axes composed on one scale -- visibility (the
    existing 4-level ladder) and activation (enabled/disabled). The declared
    presence projection places `disabled` colder than `shadowed`, so the merged
    spectrum is the proof they share 'presence':
        visible/enabled(0) > silenced(-1) > hidden(-2) > shadowed(-3) > disabled(-4)
    """
    return ContinuumSpace(
        name="kit_presence",
        meaning="how present a tool is to dz (listing + dispatch)",
        axes={"visibility": _visibility(), "activation": _activation()},
        presence={
            "visibility": {"visible": 0, "silenced": -1, "hidden": -2, "shadowed": -3},
            "activation": {"enabled": 0, "disabled": -4},
        },
    )


class TestContinuumSpace:
    def test_presence_of_and_neutral(self):
        s = _kit_presence_space()
        assert s.presence_of("visibility", "visible") == 0
        assert s.presence_of("visibility", "shadowed") == -3
        assert s.presence_of("activation", "disabled") == -4
        assert s.is_neutral("visibility", "visible")
        assert s.is_neutral("activation", "enabled")
        assert not s.is_neutral("visibility", "hidden")

    def test_spectrum_is_the_merged_warmth_ladder(self):
        """The shared scale orders the SUPPRESSION states across both axes,
        warm->cold -- the visible proof the axes share 'presence'."""
        assert _kit_presence_space().spectrum() == (
            ("visibility", "silenced"),
            ("visibility", "hidden"),
            ("visibility", "shadowed"),
            ("activation", "disabled"),
        )

    def test_stronger_weaker_within_an_axis(self):
        """Matches the user's example: hidden -> stronger=shadow, weaker=silence."""
        s = _kit_presence_space()
        assert s.colder_than("visibility", "hidden") == ("visibility", "shadowed")
        assert s.warmer_than("visibility", "hidden") == ("visibility", "silenced")

    def test_stronger_crosses_axes(self):
        """The point of the SPACE: the next-stronger move can hop axes -- colder
        than shadowed (visibility) is disabled (activation)."""
        s = _kit_presence_space()
        assert s.colder_than("visibility", "shadowed") == ("activation", "disabled")
        assert s.warmer_than("activation", "disabled") == ("visibility", "shadowed")

    def test_poles_return_none(self):
        s = _kit_presence_space()
        assert s.colder_than("activation", "disabled") is None    # cold pole
        assert s.warmer_than("visibility", "visible") is None      # warm pole (fully present)

    def test_from_fully_present_stronger_is_gentlest_suppression(self):
        s = _kit_presence_space()
        # from neutral on either axis, "stronger" = the warmest suppression.
        assert s.colder_than("visibility", "visible") == ("visibility", "silenced")
        assert s.colder_than("activation", "enabled") == ("visibility", "silenced")

    def test_warmest_suppression_returns_to_its_axis_neutral(self):
        s = _kit_presence_space()
        assert s.warmer_than("visibility", "silenced") == ("visibility", "visible")

    def test_satisfies_protocol(self):
        assert isinstance(_kit_presence_space(), ContinuumSpaceProtocol)

    def test_payload_for_holds_typed_objects_opaquely(self):
        """A rung can carry a caller-supplied TYPED payload (the 'templated
        object'); the space returns it by identity and never interprets it --
        the typed-rung mechanism, not a string dict."""
        marker = object()
        s = ContinuumSpace(
            name="p", axes={"activation": _activation()},
            presence={"activation": {"enabled": 0, "disabled": -1}},
            payloads={"activation": {"disabled": marker}},
        )
        assert s.payload_for("activation", "disabled") is marker  # exact object
        assert s.payload_for("activation", "enabled") is None     # none supplied

    def test_amplification_navigates_above_neutral(self):
        """A >0 (amplified) axis composed with visibility: 'warmer than visible'
        now EXISTS (featured), and the merged spectrum spans both signs -- proof
        the signed scale (the >0 refinement) navigates end to end."""
        prominence = Continuum(
            name="prominence",
            ranks={"dimmed": -1, "normal": 0, "featured": 1},
            invariant="display_prominence",
        )
        s = ContinuumSpace(
            name="kit_presence_amp",
            axes={"visibility": _visibility(), "prominence": prominence},
            presence={
                "visibility": {"visible": 0, "silenced": -1, "hidden": -2, "shadowed": -3},
                "prominence": {"dimmed": -5, "normal": 0, "featured": 5},
            },
        )
        # featured (+5) is warmer than the (formerly top) visible(0):
        assert s.warmer_than("visibility", "visible") == ("prominence", "featured")
        # from an amplified state, colder returns to that axis's own neutral:
        assert s.colder_than("prominence", "featured") == ("prominence", "normal")
        # the merged spectrum spans both signs, warm -> cold:
        assert s.spectrum()[0] == ("prominence", "featured")     # warmest
        assert s.spectrum()[-1] == ("prominence", "dimmed")      # coldest

    def test_meaning_is_supplied_and_describable(self):
        """A space carries a caller-supplied MEANING so it is self-describing /
        interrogable -- and presence is GENERAL (wet/dry here), not visibility."""
        moisture = Continuum(name="moisture", ranks={"dry": -1, "damp": 0, "wet": 1})
        s = ContinuumSpace(
            name="wetness", meaning="how much water is present (wet <-> dry)",
            axes={"moisture": moisture},
            presence={"moisture": {"dry": -1, "damp": 0, "wet": 1}},
        )
        assert s.meaning == "how much water is present (wet <-> dry)"
        desc = s.describe()
        assert "wetness" in desc and "wet <-> dry" in desc   # the meaning is surfaced
        assert "moisture" in desc                            # the axis is surfaced
        assert "wet[+1]" in desc and "dry[-1]" in desc       # rungs with coords
        # presence navigates the general scale just like any other:
        assert s.colder_than("moisture", "wet") == ("moisture", "damp")  # wet -> damp -> dry
        assert s.warmer_than("moisture", "dry") == ("moisture", "damp")

    def test_describe_without_meaning_is_graceful(self):
        s = ContinuumSpace(
            name="bare", axes={"activation": _activation()},
            presence={"activation": {"enabled": 0, "disabled": -1}},
        )
        assert "(no stated meaning)" in s.describe()


class TestContinuumSpaceContract:
    """The membership contract -- structural + presence-aligned + unique merged
    order -- verified by construction-time validation (the loose, test-enforced
    alternative to inheritance)."""

    def test_axes_and_presence_must_match(self):
        with pytest.raises(ContinuumError, match="name the same axes"):
            ContinuumSpace(
                name="bad", axes={"visibility": _visibility()},
                presence={"activation": {"enabled": 0, "disabled": -1}},
            )

    def test_presence_must_cover_exactly_the_levels(self):
        with pytest.raises(ContinuumError, match="cover exactly"):
            ContinuumSpace(
                name="bad", axes={"activation": _activation()},
                presence={"activation": {"enabled": 0}},  # missing 'disabled'
            )

    def test_neutral_must_be_at_presence_zero(self):
        with pytest.raises(ContinuumError, match="neutral .*level"):
            ContinuumSpace(
                name="bad", axes={"activation": _activation()},
                presence={"activation": {"enabled": -1, "disabled": -2}},  # no 0
            )

    def test_amplification_presence_accepted(self):
        """>0 presence (MORE present than neutral -- verbosity, GUI prominence)
        is VALID: 0=neutral is not a ceiling (the 2026-06-16 signed-scale
        refinement). <0 suppressed, 0 neutral, >0 amplified."""
        prominence = Continuum(
            name="prominence",
            ranks={"dimmed": -1, "normal": 0, "featured": 1},
            invariant="display_prominence",
        )
        s = ContinuumSpace(
            name="amp", axes={"prominence": prominence},
            presence={"prominence": {"dimmed": -1, "normal": 0, "featured": 1}},
        )
        assert s.presence_of("prominence", "featured") == 1
        assert s.presence_of("prominence", "dimmed") == -1

    def test_misaligned_presence_rejected(self):
        """presence must increase cold->warm; a warmer level mustn't be colder."""
        with pytest.raises(ContinuumError, match="presence-aligned"):
            ContinuumSpace(
                name="bad",
                axes={"visibility": _visibility()},
                # hidden(-2 rank) given a WARMER presence than silenced(-1 rank): misaligned
                presence={"visibility": {"visible": 0, "silenced": -2,
                                         "hidden": -1, "shadowed": -3}},
            )

    def test_duplicate_suppression_coord_rejected(self):
        with pytest.raises(ContinuumError, match="unique across the space"):
            ContinuumSpace(
                name="bad",
                axes={"visibility": _visibility(), "activation": _activation()},
                presence={
                    "visibility": {"visible": 0, "silenced": -1, "hidden": -2, "shadowed": -3},
                    "activation": {"enabled": 0, "disabled": -3},  # collides with shadowed
                },
            )


class TestContinuumSpacePurityShim:
    """Post-B3a the Continuum primitive lives in the dazzle-lib FOUNDATION
    (``dazzle_lib.continuum``, charter-guarded there); ``dazzlecmd_lib.continuum``
    re-exports it, so the historical import path resolves to the SAME class."""

    def test_space_is_lifted_to_the_foundation(self):
        import dazzlecmd_lib.continuum as shim
        import dazzle_lib.continuum as foundation
        # the primitive now lives in the bedrock...
        assert shim.ContinuumSpace.__module__ == "dazzle_lib.continuum"
        # ...and the dazzlecmd re-export is the SAME object (the shim is transparent).
        assert shim.ContinuumSpace is foundation.ContinuumSpace
        assert shim.Continuum is foundation.Continuum


class TestContinuumSpaceSlice:
    """B2c-1: the `--cascade` apply-mode primitives -- a signed RANGE window
    (`slice`) and the bare-cascade default (`cascade_to_neutral`)."""

    def test_slice_single_rung_is_default(self):
        s = _kit_presence_space()
        assert s.slice("visibility", "hidden") == ("hidden",)

    def test_slice_signed_window(self):
        s = _kit_presence_space()
        # one colder + current + two warmer -- the `--cascade {-1,+2}` window.
        assert s.slice("visibility", "hidden", lo=-1, hi=2) == (
            "shadowed", "hidden", "silenced", "visible")

    def test_slice_warmer_only(self):
        s = _kit_presence_space()
        assert s.slice("visibility", "hidden", lo=0, hi=1) == ("hidden", "silenced")

    def test_slice_clamps_at_poles(self):
        s = _kit_presence_space()
        assert s.slice("visibility", "visible", lo=0, hi=2) == ("visible",)
        assert s.slice("visibility", "shadowed", lo=-2, hi=0) == ("shadowed",)

    def test_slice_unknown_level_raises(self):
        s = _kit_presence_space()
        with pytest.raises(ContinuumError):
            s.slice("visibility", "nope")

    def test_cascade_to_neutral_subsumes_current_and_weaker(self):
        s = _kit_presence_space()
        # hide --cascade => {hidden, silenced} (current + weaker toward 0), NOT shadowed.
        assert s.cascade_to_neutral("visibility", "hidden") == ("hidden", "silenced")
        assert s.cascade_to_neutral("visibility", "shadowed") == (
            "shadowed", "hidden", "silenced")
        assert s.cascade_to_neutral("visibility", "silenced") == ("silenced",)

    def test_cascade_to_neutral_at_neutral_is_empty(self):
        s = _kit_presence_space()
        assert s.cascade_to_neutral("visibility", "visible") == ()
        assert s.cascade_to_neutral("activation", "enabled") == ()

    def test_cascade_to_neutral_other_axis(self):
        s = _kit_presence_space()
        assert s.cascade_to_neutral("activation", "disabled") == ("disabled",)

    def test_slice_positive_only_window(self):
        # a window entirely WARMER than the anchor (+1..+2 from hidden).
        s = _kit_presence_space()
        assert s.slice("visibility", "hidden", lo=1, hi=2) == ("silenced", "visible")

    def test_cascade_to_neutral_from_amplified(self):
        # a space WITH a >0 (amplified) level exercises the p>0 branch of
        # cascade_to_neutral (the visibility/activation spaces are all <=0).
        s = ContinuumSpace(
            name="prom", meaning="prominence",
            axes={"prominence": Continuum(name="prominence",
                                          ranks={"dimmed": -1, "normal": 0, "featured": 1})},
            presence={"prominence": {"dimmed": -1, "normal": 0, "featured": 1}},
        )
        assert s.cascade_to_neutral("prominence", "featured") == ("featured",)
        assert s.cascade_to_neutral("prominence", "dimmed") == ("dimmed",)
        assert s.cascade_to_neutral("prominence", "normal") == ()


def test_continuum_compare_is_signed():
    # `compare` (the signed -1/0/+1 order check) had no coverage; it lifts to
    # dazzle-lib in B3a, so it must travel with a test.
    c = _visibility()
    assert c.compare("visible", "shadowed") == 1     # visible is warmer
    assert c.compare("shadowed", "visible") == -1
    assert c.compare("hidden", "hidden") == 0
