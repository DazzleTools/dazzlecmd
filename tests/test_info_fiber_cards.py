"""CONSCIOUS RE-BASELINE (the consumer lift, 2026-07-08): engines now
default to the FOLDED one-door mounts (lib 0.10.28) -- old input
spellings (:.level...) keep resolving via aliases, but canonical
OUTPUT spellings are :.meta:level... The vectors below assert the
canonical forms; the alias-input behavior is itself asserted.

2f slice-1 (AC-2-7): `dz info` resolves DERIVED-TREE nodes -- fiber
paths, bare axis/rung names, verb poles. The user's exact wall
(`dz info :.level` -> "Tool ':.level' not found") is the pinned origin."""
import types

import pytest

from dazzlecmd.commands import inspect as inspect_cmds


@pytest.fixture()
def engine(tmp_path):
    from dazzlecmd_lib.engine import AggregatorEngine
    return AggregatorEngine(name="t", command="tst",
                            config_dir=str(tmp_path))


def _info(engine, target, capsys):
    ok = inspect_cmds._info_tree_node(engine, target)
    return ok, capsys.readouterr().out


class TestFiberCards:
    def test_the_axis_card_shows_all_rungs(self, engine, capsys):
        ok, out = _info(engine, ":.level", capsys)
        assert ok
        for rung in ("fiber", "lib", "internaltool", "tool", "kit",
                     "aggregator", "supra"):
            assert rung in out
        assert "rank -5" in out and "rank 1" in out

    def test_the_rung_card_class_vs_instance(self, engine, capsys):
        ok, out = _info(engine, ":.level:kit", capsys)
        assert ok
        assert "rung of: tst:.meta:level" in out
        assert "class of kit entities" in out
        assert "visibility" in out  # the grafted machinery listed

    def test_bare_axis_and_rung_names_resolve(self, engine, capsys):
        ok, out = _info(engine, "level", capsys)
        assert ok and "tst:.meta:level" in out
        ok, out = _info(engine, "supra", capsys)
        assert ok and "rank 1" in out

    def test_verb_pole_resolves(self, engine, capsys):
        ok, out = _info(engine, ":.meta:verb:activation:enable", capsys)
        assert ok and "rung of: tst:.meta:verb:management:activation" in out

    def test_ambiguous_bare_name_lists_candidates(self, engine, capsys):
        # "visibility" appears twice (the space and its inner axis)
        ok, out = _info(engine, "visibility", capsys)
        assert ok and "ambiguous" in out

    def test_unknown_falls_through(self, engine, capsys):
        ok, _ = _info(engine, "nosuchnode", capsys)
        assert not ok

    def test_alias_spelling_resolves(self, engine, capsys):
        ok, out = _info(engine, ":.kit", capsys)  # the alias -> the rung
        assert ok and "tst:.meta:level:kit" in out

    def test_stored_properties_listed(self, engine, capsys):
        engine.property_store.set("tst:.meta:level:kit.note", "x")
        ok, out = _info(engine, ":.level:kit", capsys)
        assert ok and "tst:.meta:level:kit.note = 'x'" in out


class TestVerbCards:
    """2f slice 2: the app's verbs join the tree; info shows the one-line
    help FACET (the full page stays `dz <verb> -h`)."""

    def test_flat_verb_card_with_help(self, engine, capsys):
        ok, out = _info(engine, "version", capsys)
        assert ok and "kind: Unified (verb)" in out and "help:" in out

    def test_new_verb_resolves(self, engine, capsys):
        ok, out = _info(engine, "new", capsys)
        assert ok and "tst:.meta:verb:new" in out

    def test_pole_gains_attached_help(self, engine, capsys):
        ok, out = _info(engine, "enable", capsys)
        assert ok and "rung of: tst:.meta:verb:management:activation" in out
        assert "help:" in out
        assert "class of" not in out  # the doctrine line is level-only

    def test_kit_stays_the_rung_one_node(self, engine, capsys):
        ok, out = _info(engine, "kit", capsys)
        assert ok and "tst:.meta:level:kit" in out
        assert "kind: verb" not in out

    def test_verb_space_lists_verbs_and_management(self, engine, capsys):
        # post-V-C: the lifecycle axes NEST under management (the
        # composed space); verbs stay flat beside it
        ok, out = _info(engine, ":.meta:verb", capsys)
        assert ok and "version" in out and "management" in out
        ok2, out2 = _info(engine, ":.meta:verb:management", capsys)
        assert ok2 and "activation" in out2


class TestCurrentPosition:
    """The axis card shows WHERE WE ARE (one-node: the axis's value is
    its current position) -- user find 2026-07-05."""

    def _registered(self, tmp_path):
        from dazzlecmd_lib.engine import AggregatorEngine
        from dazzlecmd.commands.meta import register_level_property
        e = AggregatorEngine(name="t", command="tst",
                             config_dir=str(tmp_path))
        register_level_property(e)
        return e

    def test_default_current_shown_and_marked(self, tmp_path, capsys):
        e = self._registered(tmp_path)
        ok, out = _info(e, ":.level", capsys)
        assert ok and "current: tool (default)" in out
        assert "default: tool" in out
        assert "tool          Unified (rung) (rank -2)  <- current  (default)" in out

    def test_set_level_moves_the_marker(self, tmp_path, capsys):
        e = self._registered(tmp_path)
        e.property_store.set("tst.level", "kit")
        ok, out = _info(e, ":.level", capsys)
        assert "current: kit" in out
        assert "kit           ContinuumSpace (rung) (rank -1)  <- current" in out
        # current moved to kit; the default tag stays visible on tool
        assert "tool          Unified (rung) (rank -2)  (default)" in out


class TestMatrixSweepFixes:
    """The surface-matrix sweep's three findings (2026-07-06), fixed."""

    def _reg(self, tmp_path):
        from dazzlecmd_lib.engine import AggregatorEngine
        e = AggregatorEngine(name="t", command="tst",
                             config_dir=str(tmp_path))
        e.tree_extensions.append(inspect_cmds._graft_app_verbs)
        return e

    def test_row1_listing_shows_flat_verbs(self, tmp_path, capsys):
        from dazzlecmd_lib import prop_commands
        e = self._reg(tmp_path)
        assert prop_commands.cmd_list(e, ":.meta:verb") == 0
        out = capsys.readouterr().out
        for v in ("version", "new", "list"):
            assert v in out  # ONE tree, every surface

    def test_row3_ambiguous_segment_help_attaches_to_verb_plane(
            self, tmp_path, capsys):
        e = self._reg(tmp_path)
        ok, out = _info(e, ":.meta:verb:loading:attach", capsys)
        assert ok and "help:" in out  # never silently dropped

    def test_padding_survives_long_names(self, tmp_path, capsys):
        e = self._reg(tmp_path)
        ok, out = _info(e, ":.meta:verb:mode", capsys)
        assert ok and "materialization  Continuum" in out
        assert "materializationContinuum" not in out
