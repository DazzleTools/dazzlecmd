"""2f slice-1 (AC-2-7): `dz info` resolves DERIVED-TREE nodes -- fiber
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
        assert "rung of: tst:.level" in out
        assert "class of kit entities" in out
        assert "visibility" in out  # the grafted machinery listed

    def test_bare_axis_and_rung_names_resolve(self, engine, capsys):
        ok, out = _info(engine, "level", capsys)
        assert ok and "tst:.level" in out
        ok, out = _info(engine, "supra", capsys)
        assert ok and "rank 1" in out

    def test_verb_pole_resolves(self, engine, capsys):
        ok, out = _info(engine, ":.meta:verb:activation:enable", capsys)
        assert ok and "rung of: tst:.meta:verb:activation" in out

    def test_ambiguous_bare_name_lists_candidates(self, engine, capsys):
        # "visibility" appears twice (the space and its inner axis)
        ok, out = _info(engine, "visibility", capsys)
        assert ok and "ambiguous" in out

    def test_unknown_falls_through(self, engine, capsys):
        ok, _ = _info(engine, "nosuchnode", capsys)
        assert not ok

    def test_alias_spelling_resolves(self, engine, capsys):
        ok, out = _info(engine, ":.kit", capsys)  # the alias -> the rung
        assert ok and "tst:.level:kit" in out

    def test_stored_properties_listed(self, engine, capsys):
        engine.property_store.set("tst:.level:kit.note", "x")
        ok, out = _info(engine, ":.level:kit", capsys)
        assert ok and "tst:.level:kit.note = 'x'" in out
