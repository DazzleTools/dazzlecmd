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
    _cmd_kit_remove,
    _cmd_kit_detach,
    _cmd_kit_attach,
    _kit_is_submodule,
    _cmd_kit_focus,
    _cmd_kit_reset,
    _cmd_kit_favorite,
    _cmd_kit_favorite_migrate_stale,
    _cmd_kit_unfavorite,
    _cmd_kit_visibility_set,
    _cmd_kit_visibility_list,
    _cmd_kit_visibility_status,
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

    def test_enable_disable_enable_round_trips(self, tmp_path, monkeypatch):
        # The activation axis is a LATERAL round-trip: enable -> disable -> enable
        # returns to the enabled config state.
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_enable(_Args(name="wtf"), engine)
        _cmd_kit_disable(_Args(name="wtf"), engine)
        mid = _read_config(tmp_path)
        assert "wtf" in mid["disabled_kits"]
        assert "wtf" not in (mid.get("active_kits") or [])
        _cmd_kit_enable(_Args(name="wtf"), engine)
        end = _read_config(tmp_path)
        assert "wtf" in end["active_kits"]
        assert "wtf" not in (end.get("disabled_kits") or [])

    def test_activation_context_reports_lateral_kind(self, tmp_path, monkeypatch):
        # enable/disable run on the generic TransitionContext; the receipt carries
        # the DECLARED edge's reversibility class (Transition.kind == "lateral").
        from dazzlecmd_lib.contexts import ActivationContext
        engine = _engine(tmp_path, monkeypatch)
        r = ActivationContext(engine).enable("wtf")
        assert r.verb == "enable" and r.new_state == "active"
        assert r.kind == "lateral" and r.reversible is True
        r2 = ActivationContext(engine).disable("wtf")
        assert r2.previous_state == "active" and r2.new_state == "inactive"
        assert r2.kind == "lateral"


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
# dz kit remove (strong-remove: deregister + safedel + deactivate)
# ---------------------------------------------------------------------------


class TestKitRemove:
    """kit-lifecycle slice 3 -- the strong-remove pole, end-to-end via the handler.
    Real git submodule surgery is exercised by the human checklist; here the
    local-only path (registry ungroup + safedel + deactivate) is the unit coverage."""

    def _make_kit_on_disk(self, tmp_path, name, source="https://x/y.git"):
        proj = tmp_path / "projects" / name
        proj.mkdir(parents=True)
        (proj / "tool.py").write_text("print('hi')\n", encoding="utf-8")
        kits = tmp_path / "kits"
        kits.mkdir(exist_ok=True)
        reg = kits / f"{name}.kit.json"
        reg.write_text(
            json.dumps({"name": name, "always_active": False, "source": source}),
            encoding="utf-8")
        return proj, reg

    def _patch_trash(self, tmp_path, monkeypatch):
        import shutil
        import types as _types
        trashdir = tmp_path / "trash"
        trashdir.mkdir()

        class _FakeTrash:
            def trash(self, paths, dry_run=False):
                for p in paths:
                    shutil.move(str(p), str(trashdir / os.path.basename(str(p))))
                return _types.SimpleNamespace(success=True, folder_name="x", errors=[])

        monkeypatch.setattr(
            "dazzlecmd_lib.core.safedel.TrashStore", lambda *a, **k: _FakeTrash())
        return trashdir

    def test_remove_local_only_deregisters_trashes_deactivates(self, tmp_path, monkeypatch):
        proj, reg = self._make_kit_on_disk(tmp_path, "sandbox")
        trashdir = self._patch_trash(tmp_path, monkeypatch)
        engine = _engine(tmp_path, monkeypatch)
        (tmp_path / "config.json").write_text(
            json.dumps({"active_kits": ["sandbox"], "disabled_kits": []}),
            encoding="utf-8")

        rc = _cmd_kit_remove(
            _Args(name="sandbox", dry_run=False, yes=True, force=False),
            str(tmp_path), engine)
        assert rc == 0
        assert not reg.exists()                  # registry deregistered (ungroup)
        assert not proj.exists()                 # dir trashed (moved)
        assert (trashdir / "sandbox").exists()   # ... and recoverable
        cfg = _read_config(tmp_path)
        assert "sandbox" not in (cfg.get("active_kits") or [])   # deactivated

    def test_remove_constitutional_refused_C3(self, tmp_path, monkeypatch):
        # 'core' is always_active in the _engine fixture's kits -> C3 refusal.
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_remove(
            _Args(name="core", dry_run=False, yes=True, force=False),
            str(tmp_path), engine)
        assert rc == 1

    def test_remove_dry_run_changes_nothing(self, tmp_path, monkeypatch):
        proj, reg = self._make_kit_on_disk(tmp_path, "sandbox")
        self._patch_trash(tmp_path, monkeypatch)
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_remove(
            _Args(name="sandbox", dry_run=True, yes=True, force=False),
            str(tmp_path), engine)
        assert rc == 0
        assert reg.exists() and proj.exists()    # nothing changed

    def test_remove_not_found(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_remove(
            _Args(name="ghost", dry_run=False, yes=True, force=False),
            str(tmp_path), engine)
        assert rc == 1

    def test_kit_is_submodule_honors_2part_kit_path(self, tmp_path):
        # The bug fix: a KIT lives at the 2-part path projects/<name>; the original
        # detection reused the TOOL-only parse_gitmodules (which drops 2-part paths)
        # so is_submodule was always False. _kit_is_submodule reads .gitmodules
        # directly and MUST see the 2-part kit path.
        (tmp_path / ".gitmodules").write_text(
            '[submodule "projects/mykit"]\n'
            '\tpath = projects/mykit\n'
            '\turl = https://x/y.git\n', encoding="utf-8")
        assert _kit_is_submodule(str(tmp_path), "mykit") is True
        assert _kit_is_submodule(str(tmp_path), "notthere") is False

    def test_kit_is_submodule_not_fooled_by_3part_tool_path(self, tmp_path):
        # A 3-part TOOL submodule (projects/core/find) must NOT register the kit
        # name 'core' as a submodule -- the 2-part check is exact on the path.
        (tmp_path / ".gitmodules").write_text(
            '[submodule "projects/core/find"]\n'
            '\tpath = projects/core/find\n'
            '\turl = https://x/find.git\n', encoding="utf-8")
        assert _kit_is_submodule(str(tmp_path), "core") is False

    def test_kit_is_submodule_no_gitmodules(self, tmp_path):
        assert _kit_is_submodule(str(tmp_path), "anything") is False


# ---------------------------------------------------------------------------
# dz kit detach -- slice 4 step 2 (the weak, keep-as-a-pointer pole)
# ---------------------------------------------------------------------------


class TestKitDetach:
    """detach = a CompositeTransition across two presence axes: LOADING -> pointer
    (write pointer:{materialized:true} to the registry) COMPOSED WITH the implicit
    ACTIVATION -> inactive cascade (a detached kit is also disabled). Files are KEPT
    (non-destructive, reversible by `dz kit attach`)."""

    def _make_kit_on_disk(self, tmp_path, name, source="https://x/y.git"):
        proj = tmp_path / "projects" / name
        proj.mkdir(parents=True)
        (proj / "tool.py").write_text("print('hi')\n", encoding="utf-8")
        kits = tmp_path / "kits"
        kits.mkdir(exist_ok=True)
        reg = kits / f"{name}.kit.json"
        reg.write_text(
            json.dumps({"name": name, "always_active": False, "source": source},
                       indent=4) + "\n",
            encoding="utf-8")
        return proj, reg

    def _pointer_of(self, reg):
        return json.loads(reg.read_text(encoding="utf-8")).get("pointer")

    def test_detach_writes_pointer_and_disables(self, tmp_path, monkeypatch):
        proj, reg = self._make_kit_on_disk(tmp_path, "sandbox")
        engine = _engine(tmp_path, monkeypatch)
        (tmp_path / "config.json").write_text(
            json.dumps({"active_kits": ["sandbox"], "disabled_kits": []}),
            encoding="utf-8")

        rc = _cmd_kit_detach(
            _Args(name="sandbox", dry_run=False), str(tmp_path), engine)
        assert rc == 0
        # LOADING -> pointer: the registry gains pointer:{materialized:true} ...
        assert self._pointer_of(reg) == {"materialized": True}
        # ... the registry file and the content both STAY (non-destructive).
        assert reg.exists() and proj.exists()
        # ACTIVATION -> inactive: the implicit cascade disabled it.
        cfg = _read_config(tmp_path)
        assert "sandbox" in (cfg.get("disabled_kits") or [])
        assert "sandbox" not in (cfg.get("active_kits") or [])

    def test_detach_constitutional_refused_C3(self, tmp_path, monkeypatch):
        # 'core' is always_active in the _engine fixture -> must stay loaded (C3).
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_detach(
            _Args(name="core", dry_run=False), str(tmp_path), engine)
        assert rc == 1

    def test_detach_dry_run_changes_nothing(self, tmp_path, monkeypatch):
        proj, reg = self._make_kit_on_disk(tmp_path, "sandbox")
        engine = _engine(tmp_path, monkeypatch)
        (tmp_path / "config.json").write_text(
            json.dumps({"active_kits": ["sandbox"], "disabled_kits": []}),
            encoding="utf-8")
        rc = _cmd_kit_detach(
            _Args(name="sandbox", dry_run=True), str(tmp_path), engine)
        assert rc == 0
        assert self._pointer_of(reg) is None          # no pointer written
        cfg = _read_config(tmp_path)
        assert "sandbox" in (cfg.get("active_kits") or [])   # not disabled

    def test_detach_not_registered_errors(self, tmp_path, monkeypatch):
        # No kits/ghost.kit.json -> only registered kits can be detached.
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_detach(
            _Args(name="ghost", dry_run=False), str(tmp_path), engine)
        assert rc == 1

    def test_detach_idempotent(self, tmp_path, monkeypatch):
        proj, reg = self._make_kit_on_disk(tmp_path, "sandbox")
        engine = _engine(tmp_path, monkeypatch)
        for _ in range(2):
            rc = _cmd_kit_detach(
                _Args(name="sandbox", dry_run=False), str(tmp_path), engine)
            assert rc == 0
        assert self._pointer_of(reg) == {"materialized": True}
        cfg = _read_config(tmp_path)
        assert (cfg.get("disabled_kits") or []).count("sandbox") == 1   # no dup


# ---------------------------------------------------------------------------
# dz kit attach -- slice 4 step 3 (the inverse of detach)
# ---------------------------------------------------------------------------


class TestKitAttach:
    """attach = clear_pointer (pointer -> loaded) + enable (the free-choice pole;
    detach's loading->inactive is FORCED, attach's loading->active is a CHOICE we
    default to enable). materialized:false -> the deferred #80 fetch stub."""

    def _make_kit_on_disk(self, tmp_path, name, pointer=None,
                          source="https://x/y.git"):
        proj = tmp_path / "projects" / name
        proj.mkdir(parents=True)
        (proj / "tool.py").write_text("print('hi')\n", encoding="utf-8")
        kits = tmp_path / "kits"
        kits.mkdir(exist_ok=True)
        reg = kits / f"{name}.kit.json"
        body = {"name": name, "always_active": False, "source": source}
        if pointer is not None:
            body["pointer"] = pointer
        reg.write_text(json.dumps(body, indent=4) + "\n", encoding="utf-8")
        return proj, reg

    def _pointer_of(self, reg):
        return json.loads(reg.read_text(encoding="utf-8")).get("pointer")

    def test_attach_clears_pointer_and_enables(self, tmp_path, monkeypatch):
        proj, reg = self._make_kit_on_disk(
            tmp_path, "sandbox", pointer={"materialized": True})
        engine = _engine(tmp_path, monkeypatch)
        (tmp_path / "config.json").write_text(
            json.dumps({"active_kits": [], "disabled_kits": ["sandbox"]}),
            encoding="utf-8")

        rc = _cmd_kit_attach(
            _Args(name="sandbox", dry_run=False), str(tmp_path), engine)
        assert rc == 0
        assert self._pointer_of(reg) is None              # pointer -> loaded
        cfg = _read_config(tmp_path)
        assert "sandbox" in (cfg.get("active_kits") or [])      # enabled
        assert "sandbox" not in (cfg.get("disabled_kits") or [])

    def test_detach_then_attach_round_trips_registry(self, tmp_path, monkeypatch):
        # The gold-standard AC: attach restores the registry (loading) -- detach
        # adds the trailing pointer key, attach removes it -> byte-identical.
        proj, reg = self._make_kit_on_disk(tmp_path, "sandbox")
        original = reg.read_text(encoding="utf-8")
        engine = _engine(tmp_path, monkeypatch)
        (tmp_path / "config.json").write_text(
            json.dumps({"active_kits": ["sandbox"], "disabled_kits": []}),
            encoding="utf-8")

        assert _cmd_kit_detach(
            _Args(name="sandbox", dry_run=False), str(tmp_path), engine) == 0
        assert self._pointer_of(reg) == {"materialized": True}    # detached
        assert _cmd_kit_attach(
            _Args(name="sandbox", dry_run=False), str(tmp_path), engine) == 0
        assert reg.read_text(encoding="utf-8") == original        # round-trips
        cfg = _read_config(tmp_path)
        assert "sandbox" in (cfg.get("active_kits") or [])        # back to active

    def test_attach_non_pointer_is_noop(self, tmp_path, monkeypatch):
        # Not detached -> nothing to attach; and it must NOT enable a disabled kit
        # (that's `dz kit enable`'s job, not attach's).
        proj, reg = self._make_kit_on_disk(tmp_path, "sandbox", pointer=None)
        engine = _engine(tmp_path, monkeypatch)
        (tmp_path / "config.json").write_text(
            json.dumps({"active_kits": [], "disabled_kits": ["sandbox"]}),
            encoding="utf-8")
        rc = _cmd_kit_attach(
            _Args(name="sandbox", dry_run=False), str(tmp_path), engine)
        assert rc == 0
        cfg = _read_config(tmp_path)
        assert "sandbox" in (cfg.get("disabled_kits") or [])   # left disabled

    def test_attach_unfetched_pointer_defers_to_80(self, tmp_path, monkeypatch):
        # materialized:false = declared-but-absent (#80); attach can't load what
        # isn't on disk -> the deferred fetch stub refuses cleanly.
        proj, reg = self._make_kit_on_disk(
            tmp_path, "sandbox", pointer={"materialized": False})
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_attach(
            _Args(name="sandbox", dry_run=False), str(tmp_path), engine)
        assert rc == 1
        assert self._pointer_of(reg) == {"materialized": False}  # unchanged

    def test_attach_dry_run_changes_nothing(self, tmp_path, monkeypatch):
        proj, reg = self._make_kit_on_disk(
            tmp_path, "sandbox", pointer={"materialized": True})
        engine = _engine(tmp_path, monkeypatch)
        (tmp_path / "config.json").write_text(
            json.dumps({"active_kits": [], "disabled_kits": ["sandbox"]}),
            encoding="utf-8")
        rc = _cmd_kit_attach(
            _Args(name="sandbox", dry_run=True), str(tmp_path), engine)
        assert rc == 0
        assert self._pointer_of(reg) == {"materialized": True}   # still a pointer
        cfg = _read_config(tmp_path)
        assert "sandbox" in (cfg.get("disabled_kits") or [])     # still disabled

    def test_attach_not_registered_errors(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_attach(
            _Args(name="ghost", dry_run=False), str(tmp_path), engine)
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


def _vis(engine, fqcn, level, direction):
    """Invoke the unified visibility handler (args carry level + direction)."""
    return _cmd_kit_visibility_set(
        _Args(fqcn=fqcn, level=level, direction=direction), engine)


def _vis_cascade(engine, fqcn, level, direction, cascade):
    """Invoke the visibility handler with a ``--cascade`` spec (B2c-2)."""
    return _cmd_kit_visibility_set(
        _Args(fqcn=fqcn, level=level, direction=direction, cascade=cascade), engine)


def _resolved(canonical):
    """A ``(project, ctx)`` pair as ``engine.resolve_command`` would return --
    lets a test exercise the name-resolution path without real discovery."""
    proj = type("_P", (), {
        "fqcn": canonical,
        "namespace": canonical.split(":", 1)[0],
        "name": canonical.rsplit(":", 1)[-1],
        "always_active": False,
    })()
    ctx = type("_Ctx", (), {"canonical_fqcn": canonical})()
    return proj, ctx


class TestKitSilence:

    def test_silence_adds_to_list(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _vis(engine, "a:b:c:d:leaf", "silenced", "suppress")
        config = _read_config(tmp_path)
        assert "a:b:c:d:leaf" in config["silenced_hints"]["tools"]

    def test_silence_idempotent(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _vis(engine, "a:b:c:d:leaf", "silenced", "suppress")
        _vis(engine, "a:b:c:d:leaf", "silenced", "suppress")
        config = _read_config(tmp_path)
        assert config["silenced_hints"]["tools"].count("a:b:c:d:leaf") == 1

    def test_unsilence_removes(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _vis(engine, "a:b:c:d:leaf", "silenced", "suppress")
        _vis(engine, "a:b:c:d:leaf", "silenced", "restore")
        config = _read_config(tmp_path)
        assert "a:b:c:d:leaf" not in config["silenced_hints"]["tools"]


# ---------------------------------------------------------------------------
# dz kit shadow / unshadow
# ---------------------------------------------------------------------------


class TestKitShadow:

    def test_shadow_adds_to_list(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _vis(engine, "x:y:tool", "shadowed", "suppress")
        config = _read_config(tmp_path)
        assert "x:y:tool" in config["shadowed_tools"]

    def test_shadow_idempotent(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _vis(engine, "x:y:tool", "shadowed", "suppress")
        _vis(engine, "x:y:tool", "shadowed", "suppress")
        config = _read_config(tmp_path)
        assert config["shadowed_tools"].count("x:y:tool") == 1

    def test_unshadow_removes(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _vis(engine, "x:y:tool", "shadowed", "suppress")
        _vis(engine, "x:y:tool", "shadowed", "restore")
        config = _read_config(tmp_path)
        assert "x:y:tool" not in config["shadowed_tools"]

    def test_short_name_resolves_to_canonical(self, tmp_path, monkeypatch):
        """A short name resolves to its canonical FQCN BEFORE writing -- so the
        entry is effective (matches the FQCN the filters use), not inert."""
        engine = _engine(tmp_path, monkeypatch)
        engine.resolve_command = (
            lambda name: _resolved("mykit:mytool") if name == "mt" else (None, None))
        _vis(engine, "mt", "silenced", "suppress")
        config = _read_config(tmp_path)
        assert config["silenced_hints"]["tools"] == ["mykit:mytool"]  # canonical, not "mt"

    def test_shadow_refuses_constitutional_C3(self, tmp_path, monkeypatch, capsys):
        """C3: a constitutional tool may be hidden but NEVER shadowed. The short
        name resolves to the canonical first, so the guard CANNOT be dodged by
        passing the short name (the bug this closes)."""
        engine = _engine(tmp_path, monkeypatch)
        engine.resolve_command = (
            lambda name: _resolved("core:safedel")
            if name in ("safedel", "core:safedel") else (None, None))
        rc = _vis(engine, "safedel", "shadowed", "suppress")  # SHORT name
        assert rc == 1                                          # refused
        config = _read_config(tmp_path)
        assert "core:safedel" not in (config.get("shadowed_tools") or [])
        assert "safedel" not in (config.get("shadowed_tools") or [])
        assert "constitutional" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# dz kit visibility (overview + status navigator)
# ---------------------------------------------------------------------------


class TestKitVisibilityList:

    def test_visibility_list_empty(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        rc = _cmd_kit_visibility_list(engine)
        assert rc == 0
        assert "(none)" in capsys.readouterr().out

    def test_visibility_list_shows_all_three_rungs(self, tmp_path, monkeypatch, capsys):
        """Includes the HIDDEN rung the old `silenced` query omitted (G11)."""
        engine = _engine(tmp_path, monkeypatch)
        _vis(engine, "a:b:c:d:leaf", "silenced", "suppress")
        _vis(engine, "m:n:widget", "hidden", "suppress")
        _vis(engine, "x:y:tool", "shadowed", "suppress")
        capsys.readouterr()  # drain setup output
        _cmd_kit_visibility_list(engine)
        out = capsys.readouterr().out
        assert "a:b:c:d:leaf" in out   # silenced
        assert "m:n:widget" in out     # hidden (the rung the old query missed)
        assert "x:y:tool" in out       # shadowed


class TestKitVisibilityStatus:
    """`dz kit status <fqcn>`: the per-item TRANSPOSE of the global
    `dz kit visibility` view -- one tool's state on each presence rung."""

    def test_status_visible(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        _cmd_kit_visibility_status(_Args(fqcn="x:y:tool"), engine)
        out = capsys.readouterr().out
        assert "x:y:tool: fully visible" in out           # the tool's level
        for rung in ("silenced", "hidden", "shadowed"):   # the same rungs as global
            assert rung in out
        assert "off" in out                               # not at any suppressed rung
        assert "dz kit visibility" in out                 # points to the global view

    def test_status_after_hide_marks_the_hidden_rung(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        _vis(engine, "x:y:tool", "hidden", "suppress")
        capsys.readouterr()
        _cmd_kit_visibility_status(_Args(fqcn="x:y:tool"), engine)
        out = capsys.readouterr().out
        assert "x:y:tool: hidden" in out
        hidden_line = next(ln for ln in out.splitlines()
                           if ln.strip().startswith("hidden "))
        assert "ON" in hidden_line                        # the hidden rung is active
        silenced_line = next(ln for ln in out.splitlines()
                             if ln.strip().startswith("silenced"))
        assert "off" in silenced_line                     # the others are not

    def test_status_is_c3_aware_for_constitutional(self, tmp_path, monkeypatch, capsys):
        """A constitutional tool can never be shadowed (C3): the shadowed rung
        reads `n/a`, not a value implying the move could apply."""
        engine = _engine(tmp_path, monkeypatch)
        engine.resolve_command = (
            lambda name: _resolved("core:safedel")
            if name in ("safedel", "core:safedel") else (None, None))
        _vis(engine, "safedel", "hidden", "suppress")  # hide allowed on constitutional
        capsys.readouterr()
        _cmd_kit_visibility_status(_Args(fqcn="safedel"), engine)
        out = capsys.readouterr().out
        assert "core:safedel: hidden" in out
        shadowed_line = next(ln for ln in out.splitlines()
                             if ln.strip().startswith("shadowed"))
        assert "n/a" in shadowed_line                  # the C3-blocked rung
        assert "dz kit visibility shadow" not in out   # not recommended as a command


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


class TestBareKitDispatch:
    """Bare ``dz kit`` (no subcommand) must behave exactly like ``dz kit list``.

    Regression pin for the v0.9.26 kit-list unification leftover: dz's
    ``_cmd_kit_list`` was deleted but the ``meta == "kit"`` dispatch branch
    still referenced it, so bare ``dz kit`` crashed with NameError. The full
    suite, two tester passes, and the byte-gate ALL missed it because nothing
    exercised the bare form; CI's flake8 F821 gate caught it post-push. This
    test goes through real argv parsing + dispatch (not a direct handler
    call) because the bug lived in dispatch.
    """

    def _run_main(self, monkeypatch, capsys, argv):
        import sys as _sys
        from dazzlecmd import cli as _cli
        monkeypatch.setattr(_sys, "argv", ["dz"] + argv)
        try:
            rc = _cli.main()
        except SystemExit as exc:  # argparse exits are part of the contract
            rc = exc.code
        return rc, capsys.readouterr().out

    def test_bare_kit_matches_kit_list(self, monkeypatch, capsys):
        rc_bare, out_bare = self._run_main(monkeypatch, capsys, ["kit"])
        rc_list, out_list = self._run_main(monkeypatch, capsys, ["kit", "list"])
        assert rc_bare == 0
        assert rc_list == 0
        assert out_bare == out_list
        assert out_bare.strip()  # renders something, not an empty pass


# ---------------------------------------------------------------------------
# dz kit visibility --cascade (B2c-2): apply a SLICE of presence rungs at once
# ---------------------------------------------------------------------------


class TestKitVisibilityCascade:
    def test_hide_cascade_bare_is_slice_to_neutral(self, tmp_path, monkeypatch):
        # hide --cascade => {hidden, silenced} (current + weaker toward 0), additive.
        engine = _engine(tmp_path, monkeypatch)
        rc = _vis_cascade(engine, "x:y:tool", "hidden", "suppress", "@neutral")
        assert rc == 0
        config = _read_config(tmp_path)
        assert "x:y:tool" in config["hidden_tools"]
        assert "x:y:tool" in config["silenced_hints"]["tools"]
        assert "x:y:tool" not in (config.get("shadowed_tools") or [])   # NOT shadowed

    def test_hide_cascade_down_escalates_toward_pole(self, tmp_path, monkeypatch):
        # hide --cascade=down => toward the cold pole = {hidden, shadowed}.
        engine = _engine(tmp_path, monkeypatch)
        rc = _vis_cascade(engine, "x:y:tool", "hidden", "suppress", "down")
        assert rc == 0
        config = _read_config(tmp_path)
        assert "x:y:tool" in config["hidden_tools"]
        assert "x:y:tool" in config["shadowed_tools"]
        assert "x:y:tool" not in ((config.get("silenced_hints") or {}).get("tools") or [])  # NOT silenced

    def test_silence_cascade_bare_is_just_silenced(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _vis_cascade(engine, "x:y:tool", "silenced", "suppress", "@neutral")
        config = _read_config(tmp_path)
        assert "x:y:tool" in config["silenced_hints"]["tools"]
        assert "x:y:tool" not in (config.get("hidden_tools") or [])

    def test_range_window_offsets(self, tmp_path, monkeypatch):
        # --cascade=-1,0 from hidden = {shadowed, hidden} (one colder + current).
        engine = _engine(tmp_path, monkeypatch)
        _vis_cascade(engine, "x:y:tool", "hidden", "suppress", "-1,0")
        config = _read_config(tmp_path)
        assert "x:y:tool" in config["hidden_tools"]
        assert "x:y:tool" in config["shadowed_tools"]

    def test_cascade_restore_clears_the_bundle(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        _vis_cascade(engine, "x:y:tool", "hidden", "suppress", "@neutral")  # set
        _vis_cascade(engine, "x:y:tool", "hidden", "restore", "@neutral")   # clear
        config = _read_config(tmp_path)
        assert "x:y:tool" not in (config.get("hidden_tools") or [])
        assert "x:y:tool" not in ((config.get("silenced_hints") or {}).get("tools") or [])

    def test_cascade_C3_applies_safe_rungs_refuses_cold_pole(self, tmp_path, monkeypatch, capsys):
        """shadow --cascade on a constitutional tool: applies the safe rungs
        (silenced+hidden), REFUSES the cold-pole (shadowed) rung (C3), rc 0."""
        engine = _engine(tmp_path, monkeypatch)
        engine.resolve_command = (
            lambda name: _resolved("core:safedel")
            if name in ("safedel", "core:safedel") else (None, None))
        rc = _vis_cascade(engine, "safedel", "shadowed", "suppress", "@neutral")
        assert rc == 0                                          # apply-rest, not whole refusal
        config = _read_config(tmp_path)
        assert "core:safedel" in config["hidden_tools"]
        assert "core:safedel" in config["silenced_hints"]["tools"]
        assert "core:safedel" not in (config.get("shadowed_tools") or [])  # C3 refused
        assert "constitutional" in capsys.readouterr().err.lower()

    def test_bad_cascade_spec_errors(self, tmp_path, monkeypatch, capsys):
        engine = _engine(tmp_path, monkeypatch)
        rc = _vis_cascade(engine, "x:y:tool", "hidden", "suppress", "garbage,1,2")
        assert rc == 1
        assert "cascade" in capsys.readouterr().err.lower()

    def test_default_no_cascade_unchanged(self, tmp_path, monkeypatch):
        # No cascade attr => single-rung path (byte-identical to pre-B2c).
        engine = _engine(tmp_path, monkeypatch)
        _vis(engine, "x:y:tool", "hidden", "suppress")
        config = _read_config(tmp_path)
        assert "x:y:tool" in config["hidden_tools"]
        assert "x:y:tool" not in ((config.get("silenced_hints") or {}).get("tools") or [])  # ONLY hidden
