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

    def test_use_rejects_unknown_level(self):
        with pytest.raises(SystemExit):
            build_parser([]).parse_args(["use", "planet"])


class TestForegroundState:
    def test_default_is_tool(self, tmp_path, monkeypatch):
        assert foreground_level(_engine(tmp_path, monkeypatch)) == "tool"

    def test_use_sets_and_persists(self, tmp_path, monkeypatch, capsys):
        eng = _engine(tmp_path, monkeypatch)
        assert _cmd_meta_use(types.SimpleNamespace(level="kit"), eng) == 0
        assert foreground_level(eng) == "kit"
        cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert cfg[FOREGROUND_KEY] == "kit"

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
