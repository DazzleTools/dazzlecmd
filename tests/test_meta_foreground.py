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
