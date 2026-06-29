"""DWP-B / B-1: the verbosity axis materialized as a `dazzle_lib.Continuum`, and
the THAC0 emit gate routed through `shows()`. These pin the MUST-PRESERVE gate
behavior (the redesign must not change what shows at what threshold).
"""
import pytest

from dazzlecmd._vendor.log_lib.verbosity import (
    VERBOSITY_CONTINUUM, SILENCE_FLOOR, shows, rank_of)
from dazzlecmd._vendor.log_lib.levels import (
    NOTHING, ERROR, DEFAULT, DEBUG)
from dazzlecmd._vendor.log_lib.manager import OutputManager


class TestVerbosityContinuum:
    def test_eight_named_rungs_with_the_invariant_zero(self):
        c = VERBOSITY_CONTINUUM
        assert c.rank("default") == 0                      # the invariant
        assert c.rank("nothing") == -4 and c.rank("debug") == 3
        assert c.cold_pole() == "nothing" and c.warm_pole() == "debug"
        assert len(c.levels()) == 8

    def test_silence_floor_is_the_cold_pole(self):
        assert SILENCE_FLOOR == NOTHING == -4

    def test_rank_of_named_rung(self):
        assert rank_of("config") == 2 and rank_of("error") == -3


class TestShowsGate:
    """`shows(level, threshold)` == the THAC0 gate (must-preserve)."""

    @pytest.mark.parametrize("level,threshold,expected", [
        (DEFAULT, DEFAULT, True),     # default shows at default
        (1, DEFAULT, False),          # timing too loud for default
        (DEFAULT, 1, True),           # default shows when louder allowed
        (ERROR, ERROR, True),         # errors show at error threshold
        (ERROR, NOTHING, False),      # the HARD WALL: errors off at the floor
        (NOTHING, NOTHING, False),    # nothing shows at/under the floor
        (DEBUG, DEBUG, True),         # debug shows at -vvv
        (DEBUG, DEFAULT, False),      # debug hidden at default
    ])
    def test_thaco_gate_preserved(self, level, threshold, expected):
        assert shows(level, threshold) is expected


class TestOutputManagerGate:
    """The OutputManager routes its gate through `shows()` (one path)."""

    def test_is_level_active_uses_the_gate(self):
        om = OutputManager(verbosity=1)               # -v
        assert om.is_level_active(1, "general") is True     # timing shows
        assert om.is_level_active(2, "general") is False    # config hidden

    def test_hard_wall_suppresses_even_errors(self):
        om = OutputManager(verbosity=NOTHING)         # -qqqq
        assert om.is_level_active(ERROR, "error") is False

    def test_per_channel_override_beats_global(self):
        om = OutputManager(verbosity=0)
        om.channel_overrides["timing"] = 1            # raise just the timing channel
        assert om.is_level_active(1, "timing") is True      # timing now shows
        assert om.is_level_active(1, "general") is False    # but not elsewhere


class TestChannelSpecsAndSpace:
    """DWP-B/B-2: named-rank channel specs + the channels x verbosity ContinuumSpace."""

    def test_named_rank_channel_spec(self):
        from dazzlecmd._vendor.log_lib.channels import parse_channel_spec
        assert parse_channel_spec("timing:config").level == 2   # named -> rank 2
        assert parse_channel_spec("parse:debug").level == 3     # the continuum surface

    def test_int_channel_spec_still_works(self):
        from dazzlecmd._vendor.log_lib.channels import parse_channel_spec
        assert parse_channel_spec("timing:2").level == 2        # int preserved
        assert parse_channel_spec("timing").level == 0          # default

    def test_verbosity_space_is_channels_x_verbosity(self):
        from dazzlecmd._vendor.log_lib.channels import (
            VERBOSITY_SPACE, KNOWN_CHANNELS)
        assert set(VERBOSITY_SPACE.axes) == set(KNOWN_CHANNELS)
        # each channel axis carries the verbosity continuum (8 rungs, 'config'==2)
        assert VERBOSITY_SPACE.axes["timing"].rank("config") == 2

    def test_opt_in_channels_declared_cold(self):
        from dazzlecmd._vendor.log_lib.channels import default_channel_overrides
        assert default_channel_overrides() == {"vals": -1, "trace": -1}


class TestHintRouting:
    """DWP-B/B-3: hint() routes through emit() (ONE gate path); dedup + context +
    level gating all preserved (the must-preserve hint behavior)."""

    def _om(self, verbosity, sink):
        om = OutputManager(verbosity=verbosity)
        om.default_renderer = sink.append      # capture emit()'s layer-3 output
        return om

    def test_hint_shows_when_level_and_context_pass(self):
        from dazzlecmd._vendor.log_lib.hints import register_hint, Hint
        register_hint(Hint(id="t.show", message="a tip", min_level=0,
                           context={"result"}))
        out = []
        self._om(0, out).hint("t.show", context="result")
        assert out == ["a tip"]

    def test_hint_gated_when_too_verbose_for_threshold(self):
        from dazzlecmd._vendor.log_lib.hints import register_hint, Hint
        register_hint(Hint(id="t.gated", message="deep", min_level=2,
                           context={"result"}))
        out = []
        self._om(0, out).hint("t.gated", context="result")    # 0 < 2 -> gated
        assert out == []

    def test_hint_dedup_shows_once(self):
        from dazzlecmd._vendor.log_lib.hints import register_hint, Hint
        register_hint(Hint(id="t.dedup", message="once", min_level=0,
                           context={"result"}))
        out = []
        om = self._om(0, out)
        om.hint("t.dedup", context="result")
        om.hint("t.dedup", context="result")
        assert out == ["once"]                                # dedup preserved

    def test_hint_context_mismatch_suppresses(self):
        from dazzlecmd._vendor.log_lib.hints import register_hint, Hint
        register_hint(Hint(id="t.ctx", message="err only", min_level=0,
                           context={"error"}))
        out = []
        self._om(0, out).hint("t.ctx", context="result")      # context mismatch
        assert out == []
