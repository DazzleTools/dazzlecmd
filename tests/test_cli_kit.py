"""Tests for the Phase 3 dz kit * CLI command handlers.

Uses DAZZLECMD_CONFIG env var for config isolation -- no test touches the
real ~/.dazzlecmd/config.json.
"""

import json
import os

import pytest

from dazzlecmd.engine import AggregatorEngine
from dazzlecmd_lib.testing import make_tool, make_kit
# The kit-list renderer moved to the lib (kit-list unification DWP,
# 2026-06-11); same signature -- these tests now pin the LIB renderer,
# which every consumer (dz included) routes through.
from dazzlecmd_lib.default_meta_commands import (
    render_kit_list as _cmd_kit_list,
)
from dazzlecmd.cli import (
    _cmd_kit_enable,
    _cmd_kit_disable,
    _cmd_kit_focus,
    _cmd_kit_reset,
    _cmd_kit_favorite,
    _cmd_kit_favorite_migrate_stale,
    _cmd_kit_unfavorite,
    _cmd_kit_silence,
    _cmd_kit_unsilence,
    _cmd_kit_shadow,
    _cmd_kit_unshadow,
    _cmd_kit_silenced,
    _suggest_favorite_replacement,
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
        make_kit(_kit_name="core", name="core", always_active=True, tools=[]),
        make_kit(_kit_name="dazzletools", name="dazzletools", always_active=True, tools=[]),
        make_kit(_kit_name="wtf", name="wtf", always_active=False, tools=[]),
        make_kit(_kit_name="extra", name="extra", always_active=False, tools=[]),
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
# dz kit favorite --migrate-stale (4e-T2, v0.7.35)
# ---------------------------------------------------------------------------


def _engine_with_canonical(tmp_path, monkeypatch, canonicals=(), aliases=()):
    """Build an engine with a populated FQCNIndex.

    ``canonicals`` is an iterable of FQCN strings; each becomes a project
    in ``canonical_index`` keyed on its FQCN. Each canonical also gets a
    ``short_index`` entry under its last colon-segment so that
    `_suggest_favorite_replacement` can find single-match short names.

    ``aliases`` is an iterable of ``(alias_fqcn, canonical_fqcn)`` tuples.
    """
    engine = _engine(tmp_path, monkeypatch)
    for fqcn in canonicals:
        project = make_tool(
            name=fqcn.rsplit(":", 1)[-1] if ":" in fqcn else fqcn,
            _fqcn=fqcn,
        )
        engine.fqcn_index.canonical_index[fqcn] = project
        engine.fqcn_index.short_index.setdefault(project.name, []).append(fqcn)
    for alias_fqcn, canonical_fqcn in aliases:
        engine.fqcn_index.alias_index[alias_fqcn] = canonical_fqcn
    return engine


class TestKitFavoriteMigrateStale:

    def test_no_favorites_returns_zero(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_favorite_migrate_stale(engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "No favorites" in out

    def test_all_valid_favorites_returns_zero(self, tmp_path, monkeypatch, capsys):
        engine = _engine_with_canonical(
            tmp_path, monkeypatch, canonicals=["core:safedel"]
        )
        # Pre-populate a valid favorite via the existing handler
        _cmd_kit_favorite(
            _Args(short="sd", fqcn="core:safedel", migrate_stale=False), engine
        )
        capsys.readouterr()  # drain
        rc = _cmd_kit_favorite_migrate_stale(engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "No stale favorites" in out

    def test_stale_favorite_listed_when_not_tty(
        self, tmp_path, monkeypatch, capsys
    ):
        engine = _engine_with_canonical(tmp_path, monkeypatch, canonicals=[])
        # Bypass the stale-target warning so we set a stale favorite cleanly
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"favorites": {"sd": "core:gone"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        rc = _cmd_kit_favorite_migrate_stale(engine)
        assert rc == 1
        err = capsys.readouterr().err
        assert "stale favorite" in err.lower()
        assert "sd -> core:gone" in err
        assert "interactive shell" in err.lower()

    def test_stale_with_suggestion_listed_when_not_tty(
        self, tmp_path, monkeypatch, capsys
    ):
        # Populate a canonical 'core:safedel' so its short 'safedel' has a
        # single discoverable target -> _suggest_favorite_replacement returns it.
        engine = _engine_with_canonical(
            tmp_path, monkeypatch, canonicals=["core:safedel"]
        )
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"favorites": {"safedel": "old:safedel-deprecated"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        rc = _cmd_kit_favorite_migrate_stale(engine)
        assert rc == 1
        err = capsys.readouterr().err
        assert "suggestion: core:safedel" in err

    def test_interactive_remap(self, tmp_path, monkeypatch, capsys):
        engine = _engine_with_canonical(
            tmp_path, monkeypatch, canonicals=["core:safedel"]
        )
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"favorites": {"safedel": "old:safedel-deprecated"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "r")
        rc = _cmd_kit_favorite_migrate_stale(engine)
        assert rc == 0
        config = _read_config(tmp_path)
        assert config["favorites"] == {"safedel": "core:safedel"}
        out = capsys.readouterr().out
        assert "remapped" in out

    def test_interactive_drop(self, tmp_path, monkeypatch, capsys):
        engine = _engine_with_canonical(tmp_path, monkeypatch, canonicals=[])
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"favorites": {"sd": "old:safedel-deprecated"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "d")
        rc = _cmd_kit_favorite_migrate_stale(engine)
        assert rc == 0
        config = _read_config(tmp_path)
        assert config.get("favorites", {}) == {}
        out = capsys.readouterr().out
        assert "dropped" in out

    def test_interactive_skip_keeps_stale(self, tmp_path, monkeypatch, capsys):
        engine = _engine_with_canonical(tmp_path, monkeypatch, canonicals=[])
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"favorites": {"sd": "old:gone"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "s")
        rc = _cmd_kit_favorite_migrate_stale(engine)
        assert rc == 0
        config = _read_config(tmp_path)
        # Skip preserves the stale entry
        assert config.get("favorites", {}) == {"sd": "old:gone"}
        out = capsys.readouterr().out
        assert "skipped" in out

    def test_alias_target_resolves_canonical(
        self, tmp_path, monkeypatch, capsys
    ):
        # A favorite that targets an alias whose canonical IS discovered
        # is NOT stale -- mirrors FQCNIndex.resolve favorite-on-alias.
        # Real virtual-kit alias_index keys are two-segment <vk>:<short>
        # (e.g., 'claude:cleanup' -> 'dazzletools:claude-cleanup'), NOT
        # the fully-qualified <agg>:<vk>:<short> dispatch form. A
        # favorite must use the two-segment form to be alias-resolved.
        engine = _engine_with_canonical(
            tmp_path, monkeypatch,
            canonicals=["dazzletools:claude-cleanup"],
            aliases=[("claude:cleanup", "dazzletools:claude-cleanup")],
        )
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"favorites": {"cleanup": "claude:cleanup"}}),
            encoding="utf-8",
        )
        rc = _cmd_kit_favorite_migrate_stale(engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "No stale" in out

    def test_qualified_alias_form_is_stale(
        self, tmp_path, monkeypatch, capsys
    ):
        # The fully-qualified <agg>:<vk>:<short> form is a valid dispatch
        # path (resolved at find_project time, not via alias_index lookup),
        # but it's NOT a key in alias_index -- so migrate-stale flags
        # favorites that use it. Suggestion typically points at the
        # canonical, which is the right migration target.
        engine = _engine_with_canonical(
            tmp_path, monkeypatch,
            canonicals=["dazzletools:claude-cleanup"],
            aliases=[("claude:cleanup", "dazzletools:claude-cleanup")],
        )
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"favorites": {
                "cleanup": "dazzletools:claude:cleanup"
            }}),
            encoding="utf-8",
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        rc = _cmd_kit_favorite_migrate_stale(engine)
        assert rc == 1
        err = capsys.readouterr().err
        assert "stale" in err.lower()
        assert "dazzletools:claude:cleanup" in err

    def test_dispatch_via_handler_with_migrate_stale_flag(
        self, tmp_path, monkeypatch, capsys
    ):
        """The handler entry point dispatches --migrate-stale correctly."""
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_favorite(
            _Args(short=None, fqcn=None, migrate_stale=True), engine
        )
        assert rc == 0  # no favorites configured

    def test_migrate_stale_with_positional_args_errors(
        self, tmp_path, monkeypatch, capsys
    ):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_favorite(
            _Args(short="foo", fqcn="core:foo", migrate_stale=True), engine
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "no positional" in err.lower()

    def test_no_args_no_flag_errors(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_favorite(
            _Args(short=None, fqcn=None, migrate_stale=False), engine
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "requires" in err.lower()


class TestSuggestFavoriteReplacement:

    def test_single_match_returned(self, tmp_path, monkeypatch):
        engine = _engine_with_canonical(
            tmp_path, monkeypatch, canonicals=["core:safedel"]
        )
        result = _suggest_favorite_replacement(
            "safedel", "old:safedel-deprecated", engine
        )
        assert result == "core:safedel"

    def test_no_match_returns_none(self, tmp_path, monkeypatch):
        engine = _engine_with_canonical(tmp_path, monkeypatch, canonicals=[])
        result = _suggest_favorite_replacement("ghost", "old:ghost", engine)
        assert result is None

    def test_ambiguous_returns_none(self, tmp_path, monkeypatch):
        engine = _engine_with_canonical(
            tmp_path, monkeypatch,
            canonicals=["core:tool", "extra:tool"],
        )
        result = _suggest_favorite_replacement("tool", "old:tool", engine)
        assert result is None


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
            make_kit(name="core", _kit_name="core", tools=["core:a", "core:b"],
                     always_active=True),
            # Wtf imported as "wtf" but its in-repo manifest has name="core"
            make_kit(name="core", _kit_name="wtf",
                     tools=["wtf:core:locked", "wtf:core:restarted"],
                     always_active=True),
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
            make_kit(name="legacy", tools=["legacy:a"], always_active=True),
        ]
        rc = _cmd_kit_status(kits)
        assert rc == 0
        assert "legacy: 1 tool(s)" in capsys.readouterr().out


class TestKitStatusActiveFilter:
    """`dz kit status` must honor the user config (active_kits /
    disabled_kits), matching `dz kit list`. Regression: `_cmd_kit_status`
    used to call `get_active_kits(kits)` without the engine's config, so it
    showed every discovered kit (e.g. a disabled `media` still appeared
    under "Active kits").
    """

    def test_kit_status_excludes_disabled_kit(self, tmp_path, monkeypatch, capsys):
        from dazzlecmd.cli import _cmd_kit_status

        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"disabled_kits": ["dazzletools"]}), encoding="utf-8"
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = _engine(tmp_path, monkeypatch)

        rc = _cmd_kit_status(engine.kits, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # disabled_kits wins even over an always_active kit
        assert "dazzletools" not in out
        assert "core" in out

    def test_kit_status_honors_active_kits_allowlist(self, tmp_path, monkeypatch, capsys):
        from dazzlecmd.cli import _cmd_kit_status

        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"active_kits": ["wtf"]}), encoding="utf-8"
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = _engine(tmp_path, monkeypatch)

        rc = _cmd_kit_status(engine.kits, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # wtf is allow-listed; core/dazzletools stay active (always_active);
        # extra is neither -> excluded.
        assert "wtf" in out
        assert "extra" not in out

    def test_kit_status_without_engine_shows_all(self, capsys):
        """No engine/config -> legacy all-active fallback (back-compat)."""
        from dazzlecmd.cli import _cmd_kit_status

        kits = [
            make_kit(_kit_name="core", name="core", always_active=True, tools=["core:a"]),
            make_kit(_kit_name="extra", name="extra", always_active=False, tools=["extra:b"]),
        ]
        rc = _cmd_kit_status(kits)
        assert rc == 0
        out = capsys.readouterr().out
        assert "core" in out and "extra" in out


# ---------------------------------------------------------------------------
# dz kit list <kit> drill-in column-width parity (#48, v0.7.36)
# ---------------------------------------------------------------------------


class TestKitListDrillInColumnWidths:
    """Regression guard for #48: canonical-kit drill-in computes column
    widths from data instead of fixed 16-char columns and uses
    `_wrap_description` for terminal-aware wrapping instead of the
    hardcoded 55-char truncation.
    """

    def _kit_with_tools(self, kit_name, tool_specs):
        """Build (kits, projects) for a single-kit drill-in test.

        ``tool_specs`` is a list of (short_name, platform, description) tuples.
        """
        kit = make_kit(
            _kit_name=kit_name,
            name=kit_name,
            always_active=True,
            tools=[f"{kit_name}:{name}" for name, _, _ in tool_specs],
        )
        projects = [
            make_tool(
                name=name,
                namespace=kit_name,
                _fqcn=f"{kit_name}:{name}",
                platform=platform,
                description=desc,
            )
            for name, platform, desc in tool_specs
        ]
        return [kit], projects

    def test_short_name_renders_cleanly(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        kits, projects = self._kit_with_tools("kit", [
            ("a", "cross-platform", "First tool"),
        ])
        rc = _cmd_kit_list(_Args(name="kit"), kits, projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "a" in out
        assert "cross-platform" in out
        assert "First tool" in out
        assert "1 tool(s)" in out

    def test_long_name_does_not_collide_with_platform(
        self, tmp_path, monkeypatch, capsys
    ):
        # 24-char name (longer than the old 16-char fixed column).
        # Old behavior: name overflowed and ate the platform column gap.
        # New behavior: column widths derived from data; gap preserved.
        engine = _engine(tmp_path, monkeypatch)
        kits, projects = self._kit_with_tools("kit", [
            ("claude-session-metadata", "cross-platform", "Long-named tool"),
            ("short", "windows", "Short-named tool"),
        ])
        rc = _cmd_kit_list(_Args(name="kit"), kits, projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # Both rows present
        assert "claude-session-metadata" in out
        assert "short" in out
        # The platform column should appear consistently AFTER the longest
        # name + at least 2-char gap. Verify by checking column alignment
        # in the long-name row.
        long_row_lines = [
            line for line in out.splitlines()
            if "claude-session-metadata" in line and "cross-platform" in line
        ]
        assert long_row_lines, "expected long-name row to render on one line"
        line = long_row_lines[0]
        # After the name and at least one space, "cross-platform" should appear
        name_end = line.index("claude-session-metadata") + len("claude-session-metadata")
        platform_start = line.index("cross-platform")
        assert platform_start > name_end + 1  # at least one gap char

    def test_description_wraps_to_terminal_width(
        self, tmp_path, monkeypatch, capsys
    ):
        # Description longer than the v0.7.28 hardcoded 55-char truncation;
        # the fix should wrap (not truncate) to whatever the terminal width
        # allows.
        engine = _engine(tmp_path, monkeypatch)
        long_desc = (
            "A description that easily exceeds the v0.7.28 hardcoded "
            "55-character truncation and should wrap to multiple lines "
            "rather than being chopped off with an ellipsis suffix."
        )
        kits, projects = self._kit_with_tools("kit", [
            ("a", "cross-platform", long_desc),
        ])
        rc = _cmd_kit_list(_Args(name="kit"), kits, projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # No "..." suffix from the dropped hardcoded truncation
        # (we still allow `...` if it's part of the description body, but
        # the description doesn't contain literal "..." here)
        assert "..." not in out
        # Full description text reachable across wrapped lines
        # (rejoin wrapped output by stripping leading whitespace + newlines)
        joined = " ".join(line.strip() for line in out.splitlines() if line.strip())
        # Every word from the long description appears somewhere in the
        # joined output -- proves nothing was truncated.
        for word in [
            "description", "exceeds", "v0.7.28",
            "truncation", "should", "wrap", "chopped",
        ]:
            assert word in joined, f"word {word!r} missing from output"

    def test_mixed_short_and_long_names(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        kits, projects = self._kit_with_tools("kit", [
            ("a", "cross-platform", "A"),
            ("claude-session-metadata", "cross-platform", "B"),
            ("z", "windows", "C"),
        ])
        rc = _cmd_kit_list(_Args(name="kit"), kits, projects, engine=engine)
        assert rc == 0
        out = capsys.readouterr().out
        # All three present, in alphabetical order via sorted(tool_refs)
        a_idx = out.index("kit:a") if "kit:a" in out else out.index(" a ")
        long_idx = out.index("claude-session-metadata")
        z_idx = out.index(" z ")
        assert a_idx < long_idx < z_idx
        assert "3 tool(s)" in out

    def test_not_found_marker_preserved(self, tmp_path, monkeypatch, capsys):
        # When a tool ref doesn't match any discovered project, the row
        # should render with "(not found)" in the description column.
        engine = _engine(tmp_path, monkeypatch)
        kit = make_kit(
            _kit_name="kit",
            name="kit",
            always_active=True,
            tools=["kit:ghost"],
        )
        rc = _cmd_kit_list(
            _Args(name="kit"), [kit], projects=[], engine=engine
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "ghost" in out
        assert "(not found)" in out
