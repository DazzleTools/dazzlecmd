"""SD-B -- `dz meta use <level>` / `dz use` / `dz meta reset` (the re-choosable
foreground level). The resolver TIEBREAK that consumes the foreground is
unit-tested in dazzlecmd-lib `test_target_resolution::TestForegroundTiebreak`;
here we verify the dz-side surface: the parser routing + the handlers' config
read/write."""
import json
import types

import pytest

from dazzlecmd.cli import build_parser
from dazzlecmd.commands.meta import (
    foreground_level, _cmd_meta_use, _cmd_meta_reset,
    FOREGROUND_KEY, DEFAULT_FOREGROUND,
)


def _engine(tmp_path, monkeypatch):
    from dazzlecmd_lib.engine import AggregatorEngine
    monkeypatch.delenv("DAZZLECMD_CONFIG", raising=False)
    return AggregatorEngine(name="dz", command="dz", config_dir=str(tmp_path))


class TestParser:
    def test_meta_use_routes_with_level(self):
        a = build_parser([]).parse_args(["meta", "use", "kit"])
        assert a._meta == "meta_use" and a.level == "kit"

    def test_meta_use_no_level(self):
        a = build_parser([]).parse_args(["meta", "use"])
        assert a._meta == "meta_use" and a.level is None

    def test_meta_reset_routes(self):
        assert build_parser([]).parse_args(["meta", "reset"])._meta == "meta_reset"

    def test_bare_meta_routes(self):
        assert build_parser([]).parse_args(["meta"])._meta == "meta"

    def test_use_alias_routes(self):
        a = build_parser([]).parse_args(["use", "aggregator"])
        assert a._meta == "meta_use" and a.level == "aggregator"

    def test_use_rejects_unknown_level(self, tmp_path, monkeypatch, capsys):
        # R1.7: validation moved from argparse choices= to the runtime
        # validator (LEVEL_CONTINUUM rungs at call time) -- exit-2 parity.
        eng = _engine(tmp_path, monkeypatch)
        assert _cmd_meta_use(types.SimpleNamespace(level="planet"), eng) == 2
        assert "invalid level" in capsys.readouterr().err

    def test_level_alias_routes(self):
        # `dz level <rung>` -- the canonical name of the switcher (R1.7).
        a = build_parser([]).parse_args(["level", "kit"])
        assert a._meta == "meta_use" and a.level == "kit"


class TestForegroundState:
    def test_default_is_tool(self, tmp_path, monkeypatch):
        assert foreground_level(_engine(tmp_path, monkeypatch)) == "tool"

    def test_use_sets_and_persists(self, tmp_path, monkeypatch, capsys):
        eng = _engine(tmp_path, monkeypatch)
        assert _cmd_meta_use(types.SimpleNamespace(level="kit"), eng) == 0
        assert foreground_level(eng) == "kit"
        # R1.7: the foreground IS the <root>.level property now.
        props = json.loads(
            (tmp_path / "properties.json").read_text(encoding="utf-8"))
        assert props["dz.level"] == "kit"

    def test_legacy_key_migrates_on_read(self, tmp_path, monkeypatch):
        # R1.7 MOVE migration: legacy config value honored, then MOVED.
        eng = _engine(tmp_path, monkeypatch)
        eng.config.write({FOREGROUND_KEY: "kit"})
        assert foreground_level(eng) == "kit"
        eng.config.invalidate()
        assert FOREGROUND_KEY not in eng.config.read()  # legacy key gone
        assert eng.property_store.get("dz.level") == "kit"

    def test_reset_kills_stale_legacy(self, tmp_path, monkeypatch, capsys):
        # C-8: reset BEFORE any other touch must not resurrect the
        # legacy value (the move wraps delete too).
        eng = _engine(tmp_path, monkeypatch)
        eng.config.write({FOREGROUND_KEY: "kit"})
        assert _cmd_meta_reset(eng) == 0
        assert foreground_level(eng) == DEFAULT_FOREGROUND

    def test_sugar_write_validates_like_verb(self, tmp_path, monkeypatch, capsys):
        # C-7: the registered validator guards the property write path.
        from dazzlecmd.commands.meta import register_level_property
        from dazzlecmd_lib.prop_commands import cmd_upsert
        eng = _engine(tmp_path, monkeypatch)
        register_level_property(eng)
        assert cmd_upsert(eng, ".level", "bogus") == 2
        assert "invalid level" in capsys.readouterr().err
        assert cmd_upsert(eng, ".level", "kit") == 0
        assert foreground_level(eng) == "kit"

    def test_use_no_level_reports_current(self, tmp_path, monkeypatch, capsys):
        eng = _engine(tmp_path, monkeypatch)
        eng.config.write({FOREGROUND_KEY: "aggregator"})
        _cmd_meta_use(types.SimpleNamespace(level=None), eng)
        assert capsys.readouterr().out.strip() == "aggregator"

    def test_reset_returns_to_default(self, tmp_path, monkeypatch):
        eng = _engine(tmp_path, monkeypatch)
        eng.config.write({FOREGROUND_KEY: "kit"})
        _cmd_meta_reset(eng)
        assert foreground_level(eng) == DEFAULT_FOREGROUND

    def test_foreground_level_tolerates_no_engine(self):
        assert foreground_level(None) == DEFAULT_FOREGROUND


class TestLevelNodeValueAlias:
    """F2 regression (sweep 2026-07-04): `dz :.level=<x>` routes to the
    VALIDATED level property -- never an inert fiber shadow key. The
    one-node doctrine: the axis node's bare value IS the property."""

    def _engine(self, tmp_path):
        import dazzlecmd_lib.prop_commands as pc
        from dazzlecmd_lib.engine import AggregatorEngine
        from dazzlecmd.commands.meta import register_level_property
        e = AggregatorEngine(name="t", command="tst",
                             config_dir=str(tmp_path))
        register_level_property(e)
        return e

    def test_fiber_spelled_write_validates(self, tmp_path, capsys):
        e = self._engine(tmp_path)
        assert e._intercept_path_form([":.level=bogus"]) == ("result", 2)
        assert "invalid level" in capsys.readouterr().err
        assert e.property_store.get("tst:.level") is None  # no shadow key

    def test_fiber_spelled_write_sets_the_level(self, tmp_path, capsys):
        e = self._engine(tmp_path)
        assert e._intercept_path_form([":.level=kit"]) == ("result", 0)
        assert e.property_store.get("tst.level") == "kit"

    def test_fiber_spelled_read_shows_the_level(self, tmp_path, capsys):
        e = self._engine(tmp_path)
        e.property_store.set("tst.level", "tool")
        assert e._intercept_path_form([":.level"]) == ("result", 0)
        assert "tool" in capsys.readouterr().out

    def test_bug2_spellings_agree_after_delete(self, tmp_path, capsys):
        from dazzlecmd_lib import prop_commands
        from dazzlecmd.commands.meta import foreground_level
        e = self._engine(tmp_path)
        e._intercept_path_form([":.level=kit"])
        capsys.readouterr()
        prop_commands.cmd_delete(e, ".level")
        capsys.readouterr()
        # the verb's view and the path form's view agree post-delete:
        assert foreground_level(e) == "tool"
        assert e._intercept_path_form([":.level"]) == ("result", 0)
        assert "tool (default)" in capsys.readouterr().out


class TestMetaLevelSubcommand:
    """User find 2026-07-06: dz -h promised `level` under meta but
    `dz meta level` was an invalid choice. Now real (routes to the same
    report-or-set handler as `use`); the dz -h row is removed in favor
    of discovery through meta; `dz level` stays as the shorthand."""

    def test_meta_level_parses_and_routes(self):
        from dazzlecmd.parsers import build_parser
        p = build_parser([], engine=None)
        ns = p.parse_args(["meta", "level", "kit"])
        assert ns._meta == "meta_use" and ns.level == "kit"
        ns = p.parse_args(["meta", "level"])
        assert ns.level is None  # report form

    def test_dz_h_epilog_drops_the_level_row(self):
        from dazzlecmd.parsers import build_parser
        p = build_parser([], engine=None)
        assert "level [<rung>]" not in (p.epilog or "")
        assert "dz:.meta" in (p.epilog or "")  # meta row remains

    def test_top_level_shorthand_still_works(self):
        from dazzlecmd.parsers import build_parser
        p = build_parser([], engine=None)
        ns = p.parse_args(["level", "kit"])
        assert ns.level == "kit"

    def test_version_row_removed_but_surfaces_stay(self):
        # 2026-07-06: version leaves the dz -h commands list (--version
        # is in options; dz info version has its card) -- the SUBCOMMAND
        # itself stays until spellings derive (the flags-note ledger).
        from dazzlecmd.parsers import build_parser
        p = build_parser([], engine=None)
        assert '("version"' not in (p.epilog or "")
        assert "version" not in (p.epilog or "").split("commands:")[-1].split("\n")[1:2]
        ns = p.parse_args(["version"])  # still parses
        assert ns._meta == "version"


class TestExposeFlipInHelp:
    """B-8's other half (certification 2026-07-07): the epilog derives
    generated rows -- flip expose and the dz -h row appears/vanishes."""

    def test_exposed_command_appears_in_epilog(self, tmp_path):
        from dazzlecmd_lib.engine import AggregatorEngine
        from dazzlecmd.tree_plane import configure_tree
        from dazzlecmd.parsers import build_parser
        e = AggregatorEngine(name="t", command="tst",
                             config_dir=str(tmp_path))
        configure_tree(e)
        e.property_store.set("tst:.meta:verb:management.expose", True)
        p = build_parser([], engine=e)
        assert "management" in (p.epilog or "")
        e.property_store.delete("tst:.meta:verb:management.expose")
        p2 = build_parser([], engine=e)
        assert "management" not in (p2.epilog or "")
