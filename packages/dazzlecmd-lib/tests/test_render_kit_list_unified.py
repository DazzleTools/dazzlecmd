"""The unified kit-list renderer (kit-list unification DWP, 2026-06-11).

`render_kit_list` gained `engine=None`: with an engine (what the registry's
`kit_list_handler` passes) every consumer gets the FULL view -- config-aware
status, data-computed drill-in columns, the virtual-kit alias drill-in. With
`engine=None` (legacy direct callers) the historical output is unchanged
(acceptance A2). dazzlecmd no longer carries its own handler (A4).
"""
from types import SimpleNamespace

from dazzlecmd_lib.default_meta_commands import render_kit_list
from dazzlecmd_lib.testing import make_kit, make_tool


def _args(name=None):
    return SimpleNamespace(name=name)


def _fixture():
    kits = [
        make_kit(name="alpha", description="Alpha kit", always_active=True,
                 tools=["alpha:t1"]),
        make_kit(name="beta", description="Beta kit", tools=["beta:t2"]),
    ]
    projects = [
        make_tool(name="t1", namespace="alpha", _fqcn="alpha:t1",
                  description="tool one", platform="cross-platform"),
        make_tool(name="t2", namespace="beta", _fqcn="beta:t2",
                  description="tool two", platform="windows"),
    ]
    return kits, projects


def _engine(config=None, aliases=None):
    """Duck-typed engine: just the two capabilities the renderer reads."""
    return SimpleNamespace(
        _get_user_config=lambda: (config or {}),
        fqcn_index=SimpleNamespace(alias_index=(aliases or {})),
    )


class TestEngineNoneLegacyUnchanged:
    """A2: no engine -> the historical output shape (no [status] brackets)."""

    def test_summary_uses_legacy_annotation(self, capsys):
        kits, projects = _fixture()
        assert render_kit_list(_args(), kits, projects) == 0
        out = capsys.readouterr().out
        assert "[enabled]" not in out and "[always active]" not in out
        assert "(always active)" in out          # the legacy DIM annotation
        assert "alpha" in out and "beta" in out


class TestEngineFullView:
    """A3: with an engine, consumers get status + the richer drill-in."""

    def test_summary_shows_config_status(self, capsys):
        kits, projects = _fixture()
        eng = _engine(config={"disabled_kits": ["beta"]})
        assert render_kit_list(_args(), kits, projects, engine=eng) == 0
        out = capsys.readouterr().out
        assert "[always active]" in out          # alpha
        assert "[disabled]" in out               # beta, from user config

    def test_drill_in_uses_data_computed_columns(self, capsys):
        kits, projects = _fixture()
        eng = _engine()
        assert render_kit_list(_args("alpha"), kits, projects, engine=eng) == 0
        out = capsys.readouterr().out
        assert "Kit: alpha [always active]" in out
        assert "tool one" in out
        assert "1 tool(s)" in out

    def test_virtual_kit_drill_in_lists_aliases(self, capsys):
        kits, projects = _fixture()
        vk = make_kit(name="vk", description="virtual", virtual=True,
                      tools=["alpha:t1"])
        eng = _engine(aliases={"vk:one": "alpha:t1"})
        assert render_kit_list(_args("vk"), kits + [vk], projects,
                               engine=eng) == 0
        out = capsys.readouterr().out
        assert "Kit: vk [virtual, enabled]" in out
        assert "vk:one" in out and "-> alpha:t1" in out
        assert "1 alias(es) -> canonical tools" in out

    def test_unknown_kit_lists_available(self, capsys):
        kits, projects = _fixture()
        assert render_kit_list(_args("nope"), kits, projects,
                               engine=_engine()) == 1
        assert "not found" in capsys.readouterr().out


class TestConfigBomTolerance:
    """A UTF-8 BOM in the config file (PowerShell `Out-File -Encoding utf8`
    writes one) must read cleanly -- no warning, values honored."""

    def test_bom_config_reads_clean(self, tmp_path, capsys, monkeypatch):
        import codecs
        from dazzlecmd_lib.config import ConfigManager
        cfg = tmp_path / "c.json"
        cfg.write_bytes(codecs.BOM_UTF8 + b'{"_schema_version": 1, "disabled_kits": ["x"]}')
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(cfg))
        data = ConfigManager().read()
        assert data.get("disabled_kits") == ["x"]
        assert "BOM" not in capsys.readouterr().err
