"""Tests for the Phase 3 dz kit * CLI command handlers.

Uses DAZZLECMD_CONFIG env var for config isolation -- no test touches the
real ~/.dazzlecmd/config.json.
"""

import json
import os

import pytest

from dazzlecmd.engine import AggregatorEngine
from dazzlecmd.cli import (
    _cmd_kit_enable,
    _cmd_kit_disable,
    _cmd_kit_focus,
    _cmd_kit_reset,
    _cmd_kit_favorite,
    _cmd_kit_unfavorite,
    _cmd_kit_silence,
    _cmd_kit_unsilence,
    _cmd_kit_shadow,
    _cmd_kit_unshadow,
    _cmd_kit_silenced,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Args:
    """Minimal argparse.Namespace stand-in for direct handler testing."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _engine(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
    engine = AggregatorEngine()
    # Pre-populate discovered kits for warnings/focus tests
    engine.kits = [
        {"_kit_name": "core", "name": "core", "always_active": True, "tools": []},
        {"_kit_name": "dazzletools", "name": "dazzletools", "always_active": True, "tools": []},
        {"_kit_name": "wtf", "name": "wtf", "always_active": False, "tools": []},
        {"_kit_name": "extra", "name": "extra", "always_active": False, "tools": []},
    ]
    return engine


def _read_config(tmp_path):
    path = tmp_path / "config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# dz kit enable / disable
# ---------------------------------------------------------------------------


class TestKitEnableDisable:

    def test_enable_adds_to_active(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_enable(_Args(name="wtf"), engine)
        assert rc == 0
        config = _read_config(tmp_path)
        assert "wtf" in config["active_kits"]

    def test_enable_removes_from_disabled(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"disabled_kits": ["wtf"]}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_enable(_Args(name="wtf"), engine)
        config = _read_config(tmp_path)
        assert "wtf" not in config["disabled_kits"]
        assert "wtf" in config["active_kits"]

    def test_disable_adds_to_disabled(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_disable(_Args(name="dazzletools"), engine)
        config = _read_config(tmp_path)
        assert "dazzletools" in config["disabled_kits"]

    def test_disable_removes_from_active(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"active_kits": ["wtf"]}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_disable(_Args(name="wtf"), engine)
        config = _read_config(tmp_path)
        assert "wtf" not in config["active_kits"]
        assert "wtf" in config["disabled_kits"]

    def test_enable_unknown_kit_warns_but_succeeds(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_enable(_Args(name="ghost-kit"), engine)
        assert rc == 0
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()

    def test_enable_idempotent(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_enable(_Args(name="wtf"), engine)
        _cmd_kit_enable(_Args(name="wtf"), engine)
        config = _read_config(tmp_path)
        # Should only appear once
        assert config["active_kits"].count("wtf") == 1


# ---------------------------------------------------------------------------
# dz kit focus
# ---------------------------------------------------------------------------


class TestKitFocus:

    def test_focus_preserves_always_active(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_focus(_Args(name="wtf"), engine.kits, engine)
        assert rc == 0
        config = _read_config(tmp_path)
        # wtf is explicitly active
        assert "wtf" in config["active_kits"]
        # extra is disabled (not always_active, not focused)
        assert "extra" in config["disabled_kits"]
        # core and dazzletools are NOT in disabled_kits (preserved via always_active)
        assert "core" not in config["disabled_kits"]
        assert "dazzletools" not in config["disabled_kits"]

    def test_focus_unknown_kit_errors(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_focus(_Args(name="ghost"), engine.kits, engine)
        assert rc == 1


# ---------------------------------------------------------------------------
# dz kit reset
# ---------------------------------------------------------------------------


class TestKitReset:

    def test_reset_deletes_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"kit_precedence": ["core"]}', encoding="utf-8")
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = AggregatorEngine()
        rc = _cmd_kit_reset(_Args(yes=True), engine)
        assert rc == 0
        assert not config_path.exists()

    def test_reset_with_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        engine = AggregatorEngine()
        rc = _cmd_kit_reset(_Args(yes=True), engine)
        assert rc == 0  # no-op success


# ---------------------------------------------------------------------------
# dz kit favorite / unfavorite
# ---------------------------------------------------------------------------


class TestKitFavorite:

    def test_favorite_sets_key(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_favorite(_Args(short="foo", fqcn="core:foo"), engine)
        assert rc == 0
        config = _read_config(tmp_path)
        assert config["favorites"] == {"foo": "core:foo"}

    def test_favorite_rejects_reserved_name(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        # "list" is a reserved meta-command
        rc = _cmd_kit_favorite(_Args(short="list", fqcn="core:foo"), engine)
        assert rc == 1

    def test_favorite_warns_on_stale_target(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        # FQCN index is empty, so any FQCN is "stale"
        rc = _cmd_kit_favorite(
            _Args(short="foo", fqcn="ghost:foo"), engine
        )
        assert rc == 0  # still saves, but warns
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower()
        assert "not found" in captured.err.lower()

    def test_unfavorite_removes_key(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_favorite(_Args(short="foo", fqcn="core:foo"), engine)
        _cmd_kit_unfavorite(_Args(short="foo"), engine)
        config = _read_config(tmp_path)
        assert config.get("favorites", {}) == {}

    def test_unfavorite_missing_is_noop(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_unfavorite(_Args(short="ghost"), engine)
        assert rc == 0


# ---------------------------------------------------------------------------
# dz kit silence / unsilence
# ---------------------------------------------------------------------------


class TestKitSilence:

    def test_silence_adds_to_list(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_silence(_Args(fqcn="a:b:c:d:leaf"), engine)
        config = _read_config(tmp_path)
        assert "a:b:c:d:leaf" in config["silenced_hints"]["tools"]

    def test_silence_idempotent(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_silence(_Args(fqcn="a:b:c:d:leaf"), engine)
        _cmd_kit_silence(_Args(fqcn="a:b:c:d:leaf"), engine)
        config = _read_config(tmp_path)
        assert config["silenced_hints"]["tools"].count("a:b:c:d:leaf") == 1

    def test_unsilence_removes(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_silence(_Args(fqcn="a:b:c:d:leaf"), engine)
        _cmd_kit_unsilence(_Args(fqcn="a:b:c:d:leaf"), engine)
        config = _read_config(tmp_path)
        assert "a:b:c:d:leaf" not in config["silenced_hints"]["tools"]


# ---------------------------------------------------------------------------
# dz kit shadow / unshadow
# ---------------------------------------------------------------------------


class TestKitShadow:

    def test_shadow_adds_to_list(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_shadow(_Args(fqcn="core:safedel"), engine)
        config = _read_config(tmp_path)
        assert "core:safedel" in config["shadowed_tools"]

    def test_shadow_idempotent(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_shadow(_Args(fqcn="core:safedel"), engine)
        _cmd_kit_shadow(_Args(fqcn="core:safedel"), engine)
        config = _read_config(tmp_path)
        assert config["shadowed_tools"].count("core:safedel") == 1

    def test_unshadow_removes(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_shadow(_Args(fqcn="core:safedel"), engine)
        _cmd_kit_unshadow(_Args(fqcn="core:safedel"), engine)
        config = _read_config(tmp_path)
        assert "core:safedel" not in config["shadowed_tools"]


# ---------------------------------------------------------------------------
# dz kit silenced (show)
# ---------------------------------------------------------------------------


class TestKitSilenced:

    def test_silenced_empty(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_silenced(engine)
        assert rc == 0
        captured = capsys.readouterr()
        assert "(none)" in captured.out

    def test_silenced_populated(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_silence(_Args(fqcn="a:b:c:d:leaf"), engine)
        _cmd_kit_shadow(_Args(fqcn="core:safedel"), engine)
        _cmd_kit_favorite(_Args(short="foo", fqcn="core:fixpath"), engine)
        capsys.readouterr()  # drain the output from the setup calls
        _cmd_kit_silenced(engine)
        captured = capsys.readouterr()
        assert "a:b:c:d:leaf" in captured.out
        assert "core:safedel" in captured.out
        assert "foo -> core:fixpath" in captured.out


class TestKitStatusDisplay:
    """Regression test for #45: _cmd_kit_status should use _kit_name when
    the kit's own 'name' field doesn't match the import name.

    This happens when a kit is imported as "wtf" (registry pointer
    filename) but its in-repo manifest declares name="core" (wtf's own
    inner kit name). The import name should win in the display.
    """

    def test_kit_status_uses_kit_name_for_embedded_sub_kit(self, capsys):
        from dazzlecmd.cli import _cmd_kit_status

        kits = [
            # Dazzlecmd's own core kit
            {"name": "core", "_kit_name": "core", "tools": ["core:a", "core:b"],
             "always_active": True},
            # Wtf imported as "wtf" but its in-repo manifest has name="core"
            {"name": "core", "_kit_name": "wtf",
             "tools": ["wtf:core:locked", "wtf:core:restarted"],
             "always_active": True},
        ]
        rc = _cmd_kit_status(kits)
        assert rc == 0
        out = capsys.readouterr().out
        # Both "core" and "wtf" should appear -- the second one was previously
        # shown as "core: 2 tool(s)" instead of "wtf: 2 tool(s)".
        assert "core: 2 tool(s)" in out  # dazzlecmd's own core
        assert "wtf: 2 tool(s)" in out   # wtf's import name, not inner "core"

    def test_kit_status_falls_back_to_name_when_kit_name_absent(self, capsys):
        """If _kit_name isn't set (legacy / direct construction), fall back to
        kit['name']."""
        from dazzlecmd.cli import _cmd_kit_status

        kits = [
            {"name": "legacy", "tools": ["legacy:a"], "always_active": True},
        ]
        rc = _cmd_kit_status(kits)
        assert rc == 0
        assert "legacy: 1 tool(s)" in capsys.readouterr().out
