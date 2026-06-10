"""Step 3 tests for the Hidden visibility mechanism (``hidden_tools`` config).

Hidden is the ladder level between Silenced and Shadowed: a hidden tool is
omitted from DISPLAY (``dz list`` / ``dz tree`` / help epilog) but stays fully
dispatchable -- its short name is still claimed and its FQCN still resolves.
Unlike ``shadowed_tools`` (applied at discovery, frees the short name), the
hidden filter is RENDER-ONLY: ``engine.filter_hidden`` returns a filtered copy
and never touches ``engine.projects`` / the FQCN index. ``--show-hidden`` reveals.
The filter is a no-op (same object returned) when ``hidden_tools`` is empty, so
existing output is byte-identical (byte-gate unaffected).
"""

import json

import pytest

from dazzlecmd.engine import AggregatorEngine
from dazzlecmd.cli import _cmd_tree
from dazzlecmd_lib.default_meta_commands import render_list
from dazzlecmd_lib.testing import make_kit, make_tool


class _Args:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _engine(tmp_path, monkeypatch, hidden=None):
    cfg = {"_schema_version": 1}
    if hidden is not None:
        cfg["hidden_tools"] = hidden
    (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
    engine = AggregatorEngine(
        name="dazzlecmd", command="dz", tools_dir="projects", kits_dir="kits",
        manifest=".dazzlecmd.json", version_info=("0.0.0", "0.0.0_test"),
    )
    engine.project_root = str(tmp_path)
    engine.kits = [make_kit(_kit_name="core", name="core", always_active=True, tools=[])]
    engine.projects = [
        make_tool(name="fixpath", _fqcn="core:fixpath", _short_name="fixpath",
                  _kit_import_name="core", description="Fix mangled paths"),
        make_tool(name="zzsecret", _fqcn="core:zzsecret", _short_name="zzsecret",
                  _kit_import_name="core", description="A hidden tool"),
    ]
    return engine


# ---------------------------------------------------------------------------
# engine.filter_hidden -- the chokepoint shared by every render path
# ---------------------------------------------------------------------------
class TestFilterHidden:
    def test_omits_hidden_but_preserves_dispatch_source(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch, hidden=["core:zzsecret"])
        filtered = engine.filter_hidden(engine.projects)
        fqcns = {p.fqcn for p in filtered}
        assert "core:fixpath" in fqcns
        assert "core:zzsecret" not in fqcns            # display-off
        # dispatch-ON: the source list (and thus discovery/index/dispatch) is
        # untouched -- filter_hidden returns a COPY, never mutates engine.projects.
        assert "core:zzsecret" in {p.fqcn for p in engine.projects}

    def test_reveal_returns_full_list(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch, hidden=["core:zzsecret"])
        revealed = engine.filter_hidden(engine.projects, reveal=True)
        assert "core:zzsecret" in {p.fqcn for p in revealed}

    def test_empty_is_noop_same_object(self, tmp_path, monkeypatch):
        """No hidden_tools -> the SAME object is returned (byte-identical guarantee)."""
        engine = _engine(tmp_path, monkeypatch, hidden=None)
        projects = engine.projects
        assert engine.filter_hidden(projects) is projects

    def test_empty_list_is_noop_same_object(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch, hidden=[])
        projects = engine.projects
        assert engine.filter_hidden(projects) is projects


# ---------------------------------------------------------------------------
# dz tree -- end-to-end through the real command
# ---------------------------------------------------------------------------
class TestTreeHidden:
    def test_tree_omits_hidden(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch, hidden=["core:zzsecret"])
        rc = _cmd_tree(_Args(json=False, depth=None, kit=None,
                             show_disabled=False, show_hidden=False), engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "fixpath" in out
        assert "zzsecret" not in out

    def test_tree_show_hidden_reveals(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch, hidden=["core:zzsecret"])
        _cmd_tree(_Args(json=False, depth=None, kit=None,
                        show_disabled=False, show_hidden=True), engine)
        out = capsys.readouterr().out
        assert "zzsecret" in out

    def test_tree_no_hidden_config_shows_all(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch, hidden=None)
        _cmd_tree(_Args(json=False, depth=None, kit=None,
                        show_disabled=False, show_hidden=False), engine)
        out = capsys.readouterr().out
        assert "fixpath" in out and "zzsecret" in out


# ---------------------------------------------------------------------------
# dz list -- end-to-end through render_list
# ---------------------------------------------------------------------------
class TestListHidden:
    def _args(self, **over):
        base = dict(namespace=None, kit=None, tag=None, platform=None,
                    show=None, show_hidden=False)
        base.update(over)
        return _Args(**base)

    def test_list_omits_hidden(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch, hidden=["core:zzsecret"])
        render_list(self._args(), engine.projects, engine=engine)
        out = capsys.readouterr().out
        assert "fixpath" in out
        assert "zzsecret" not in out

    def test_list_show_hidden_reveals(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch, hidden=["core:zzsecret"])
        render_list(self._args(show_hidden=True), engine.projects, engine=engine)
        out = capsys.readouterr().out
        assert "zzsecret" in out


# ---------------------------------------------------------------------------
# dz kit hide / unhide -- the CLI sugar that WRITES hidden_tools
# ---------------------------------------------------------------------------
class TestKitHideCommands:
    def _args(self, **over):
        base = dict(namespace=None, kit=None, tag=None, platform=None,
                    show=None, show_hidden=False)
        base.update(over)
        return _Args(**base)

    def test_kit_hide_writes_config_and_list_omits(self, tmp_path, monkeypatch, capsys):
        from dazzlecmd.cli import _cmd_kit_hide
        engine = _engine(tmp_path, monkeypatch, hidden=None)
        rc = _cmd_kit_hide(_Args(fqcn="core:zzsecret"), engine)
        assert rc == 0
        cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert "core:zzsecret" in cfg["hidden_tools"]
        capsys.readouterr()  # discard the hide confirmation
        render_list(self._args(), engine.projects, engine=engine)
        out = capsys.readouterr().out
        assert "fixpath" in out and "zzsecret" not in out

    def test_kit_unhide_restores(self, tmp_path, monkeypatch, capsys):
        from dazzlecmd.cli import _cmd_kit_hide, _cmd_kit_unhide
        engine = _engine(tmp_path, monkeypatch, hidden=None)
        _cmd_kit_hide(_Args(fqcn="core:zzsecret"), engine)
        rc = _cmd_kit_unhide(_Args(fqcn="core:zzsecret"), engine)
        assert rc == 0
        cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert "core:zzsecret" not in cfg.get("hidden_tools", [])

    def test_kit_unhide_not_hidden_is_graceful(self, tmp_path, monkeypatch, capsys):
        from dazzlecmd.cli import _cmd_kit_unhide
        engine = _engine(tmp_path, monkeypatch, hidden=None)
        rc = _cmd_kit_unhide(_Args(fqcn="core:nope"), engine)
        assert rc == 0
        assert "was not hidden" in capsys.readouterr().out

    def test_kit_hide_is_idempotent(self, tmp_path, monkeypatch, capsys):
        from dazzlecmd.cli import _cmd_kit_hide
        engine = _engine(tmp_path, monkeypatch, hidden=None)
        _cmd_kit_hide(_Args(fqcn="core:zzsecret"), engine)
        _cmd_kit_hide(_Args(fqcn="core:zzsecret"), engine)
        cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert cfg["hidden_tools"].count("core:zzsecret") == 1
