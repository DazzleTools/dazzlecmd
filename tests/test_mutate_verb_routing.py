"""B4-mutate -- the bare-verb cross-level MUTATING dispatch.

`dz enable <kit>` / `dz disable <kit>` hoist the activation toggle to the bare
form: the generic verb x level dispatcher resolves the target's level
(`resolve_target`, mutating=True fails loud on ambiguity / wrong level) and runs
the `<level>_<verb>` handler. The kit-level activation handlers wrap the existing
`_cmd_kit_*`. The explicit `dz kit enable <name>` form is unchanged.
"""
import types

import pytest

from dazzlecmd.cli import build_parser, _dispatch_bare_verb, _VERB_LEVEL_HANDLERS


def _kit(name="wtf"):
    return types.SimpleNamespace(kit_name=name, name=name)


def _engine(resolve):
    """A duck-typed engine whose resolve_target is the supplied callable."""
    return types.SimpleNamespace(
        resolve_target=resolve, command="dz", name="dazzlecmd",
        kits=[], _get_user_config=lambda: {})


class TestParser:
    def test_enable_parses_to_meta_and_target(self):
        a = build_parser([]).parse_args(["enable", "wtf"])
        assert a._meta == "enable" and a.target == "wtf"

    def test_disable_parses(self):
        a = build_parser([]).parse_args(["disable", "media"])
        assert a._meta == "disable" and a.target == "media"

    def test_enable_has_the_as_pin(self):
        a = build_parser([]).parse_args(["enable", "wtf", "--as", "kit"])
        assert a.as_level == "kit"

    def test_attach_detach_parse(self):
        a = build_parser([]).parse_args(["attach", "wtf"])
        assert a._meta == "attach" and a.target == "wtf"
        b = build_parser([]).parse_args(["detach", "media"])
        assert b._meta == "detach" and b.target == "media"


class TestRegistration:
    def test_kit_enable_disable_handlers_registered(self):
        assert "kit_enable" in _VERB_LEVEL_HANDLERS
        assert "kit_disable" in _VERB_LEVEL_HANDLERS

    def test_kit_attach_detach_handlers_registered(self):
        assert "kit_attach" in _VERB_LEVEL_HANDLERS
        assert "kit_detach" in _VERB_LEVEL_HANDLERS


class TestDispatch:
    def test_enable_routes_to_cmd_kit_enable_with_resolved_name(self, monkeypatch):
        import dazzlecmd.commands.kit as kitmod
        seen = []
        monkeypatch.setattr(
            kitmod, "_cmd_kit_enable",
            lambda args, engine: (seen.append(args.name), 0)[1])
        res = types.SimpleNamespace(entity=_kit("wtf"), level="kit", notification=None)
        eng = _engine(lambda name, mutating=False, as_level=None, **kw: res)
        args = types.SimpleNamespace(target="wtf", as_level=None)
        rc = _dispatch_bare_verb("enable", args, [], [], None, eng)
        assert rc == 0 and seen == ["wtf"]

    def test_disable_routes_to_cmd_kit_disable(self, monkeypatch):
        import dazzlecmd.commands.kit as kitmod
        seen = []
        monkeypatch.setattr(
            kitmod, "_cmd_kit_disable",
            lambda args, engine: (seen.append(args.name), 0)[1])
        res = types.SimpleNamespace(entity=_kit("media"), level="kit", notification=None)
        eng = _engine(lambda name, mutating=False, as_level=None, **kw: res)
        args = types.SimpleNamespace(target="media", as_level=None)
        rc = _dispatch_bare_verb("disable", args, [], [], None, eng)
        assert rc == 0 and seen == ["media"]

    def test_attach_routes_to_cmd_kit_attach(self, monkeypatch):
        import dazzlecmd.commands.kit_membership as kmmod
        seen = []
        monkeypatch.setattr(
            kmmod, "_cmd_kit_attach",
            lambda args, project_root, engine: (seen.append(args.name), 0)[1])
        res = types.SimpleNamespace(entity=_kit("wtf"), level="kit", notification=None)
        eng = _engine(lambda name, mutating=False, as_level=None, **kw: res)
        args = types.SimpleNamespace(target="wtf", as_level=None)
        rc = _dispatch_bare_verb("attach", args, [], [], "/root", eng)
        assert rc == 0 and seen == ["wtf"]

    def test_detach_routes_to_cmd_kit_detach(self, monkeypatch):
        import dazzlecmd.commands.kit_membership as kmmod
        seen = []
        monkeypatch.setattr(
            kmmod, "_cmd_kit_detach",
            lambda args, project_root, engine: (seen.append(args.name), 0)[1])
        res = types.SimpleNamespace(entity=_kit("wtf"), level="kit", notification=None)
        eng = _engine(lambda name, mutating=False, as_level=None, **kw: res)
        args = types.SimpleNamespace(target="wtf", as_level=None)
        rc = _dispatch_bare_verb("detach", args, [], [], "/root", eng)
        assert rc == 0 and seen == ["wtf"]

    def test_ambiguous_target_fails_loud(self):
        # mutating=True + an ambiguous bare name -> AmbiguousLevelError -> rc 2.
        from dazzlecmd_lib.target_resolution import AmbiguousLevelError

        def _raise(name, mutating=False, as_level=None, **kw):
            raise AmbiguousLevelError(
                "foo", [("tool", object()), ("kit", object())])

        eng = _engine(_raise)
        args = types.SimpleNamespace(target="foo", as_level=None)
        rc = _dispatch_bare_verb("enable", args, [], [], None, eng)
        assert rc == 2

    def test_unresolved_target_returns_one(self):
        eng = _engine(lambda name, mutating=False, as_level=None, **kw: None)
        args = types.SimpleNamespace(target="ghost", as_level=None)
        rc = _dispatch_bare_verb("enable", args, [], [], None, eng)
        assert rc == 1
