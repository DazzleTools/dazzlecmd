"""Tests for the MetaCommandRegistry class (per-engine meta-command registry).

These are pure Python data-structure tests — no mocks needed. They cover:

- register / override / unregister / registered / resolve
- Override semantics (handler-only, parser-only, both)
- Error paths (already-registered, not-registered, invalid override)
- Locking semantics (locked registry raises on mutation)
- Dispatch routing via ``_meta`` attribute
- Container dunders (__contains__, __len__, __repr__)
"""

from __future__ import annotations

import argparse
import pytest

from dazzlecmd_lib.meta_command_registry import (
    MetaCommandAlreadyRegisteredError,
    MetaCommandNotRegisteredError,
    MetaCommandRegistry,
    RegistryLockedError,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _dummy_parser(subparsers):
    """Simple parser_factory for tests: adds a subparser named 'x' with _meta=x."""
    p = subparsers.add_parser("x")
    p.set_defaults(_meta="x")


def _dummy_parser_named(name):
    """Factory producing a parser_factory that registers the given name."""

    def factory(subparsers):
        p = subparsers.add_parser(name)
        p.set_defaults(_meta=name)

    return factory


def _dummy_handler(args, engine, projects, kits, project_root):
    return 0


def _make_return_handler(value):
    def handler(args, engine, projects, kits, project_root):
        return value

    return handler


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_adds_command(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser, _dummy_handler)
        assert "list" in r
        assert r.registered() == ["list"]

    def test_register_duplicate_raises(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser, _dummy_handler)
        with pytest.raises(MetaCommandAlreadyRegisteredError) as exc:
            r.register("list", _dummy_parser, _dummy_handler)
        assert "already registered" in str(exc.value).lower()

    def test_register_multiple_commands(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _dummy_handler)
        r.register("info", _dummy_parser_named("info"), _dummy_handler)
        r.register("version", _dummy_parser_named("version"), _dummy_handler)
        assert r.registered() == ["info", "list", "version"]  # sorted

    def test_register_stores_parser_and_handler(self):
        r = MetaCommandRegistry()
        parser = _dummy_parser_named("foo")
        handler = _make_return_handler(42)
        r.register("foo", parser, handler)
        resolved_parser, resolved_handler = r.resolve("foo")
        assert resolved_parser is parser
        assert resolved_handler is handler


# ---------------------------------------------------------------------------
# override
# ---------------------------------------------------------------------------


class TestOverride:
    def test_override_handler_only(self):
        r = MetaCommandRegistry()
        original_parser = _dummy_parser_named("list")
        original_handler = _make_return_handler(1)
        r.register("list", original_parser, original_handler)

        new_handler = _make_return_handler(2)
        r.override("list", handler=new_handler)

        parser, handler = r.resolve("list")
        assert parser is original_parser  # unchanged
        assert handler is new_handler  # replaced

    def test_override_parser_only(self):
        r = MetaCommandRegistry()
        original_parser = _dummy_parser_named("list")
        original_handler = _make_return_handler(1)
        r.register("list", original_parser, original_handler)

        new_parser = _dummy_parser_named("list-custom")
        r.override("list", parser=new_parser)

        parser, handler = r.resolve("list")
        assert parser is new_parser  # replaced
        assert handler is original_handler  # unchanged

    def test_override_parser_factory_kwarg(self):
        """``parser_factory=`` works as an alias for ``parser=``."""
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _dummy_handler)
        new_parser = _dummy_parser_named("list-new")
        r.override("list", parser_factory=new_parser)
        parser, _ = r.resolve("list")
        assert parser is new_parser

    def test_override_both_parser_and_handler(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _make_return_handler(1))

        new_parser = _dummy_parser_named("list-v2")
        new_handler = _make_return_handler(2)
        r.override("list", parser=new_parser, handler=new_handler)

        parser, handler = r.resolve("list")
        assert parser is new_parser
        assert handler is new_handler

    def test_override_positional_args(self):
        """``override("name", parser_factory, handler)`` positional form still works."""
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _make_return_handler(1))
        new_parser = _dummy_parser_named("list-v2")
        new_handler = _make_return_handler(2)
        r.override("list", new_parser, new_handler)
        parser, handler = r.resolve("list")
        assert parser is new_parser
        assert handler is new_handler

    def test_override_not_registered_raises(self):
        r = MetaCommandRegistry()
        with pytest.raises(MetaCommandNotRegisteredError):
            r.override("nonexistent", handler=_dummy_handler)

    def test_override_with_no_args_raises(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _dummy_handler)
        with pytest.raises(ValueError) as exc:
            r.override("list")
        assert "at least one of parser" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# unregister
# ---------------------------------------------------------------------------


class TestUnregister:
    def test_unregister_removes_command(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _dummy_handler)
        r.register("info", _dummy_parser_named("info"), _dummy_handler)
        r.unregister("list")
        assert "list" not in r
        assert r.registered() == ["info"]

    def test_unregister_not_registered_raises(self):
        r = MetaCommandRegistry()
        with pytest.raises(MetaCommandNotRegisteredError):
            r.unregister("nonexistent")

    def test_unregister_then_register_same_name(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _make_return_handler(1))
        r.unregister("list")
        # Re-registering after unregister should succeed (not duplicate)
        r.register("list", _dummy_parser_named("list"), _make_return_handler(2))
        _, handler = r.resolve("list")
        assert handler(None, None, None, None, None) == 2


# ---------------------------------------------------------------------------
# resolve / registered
# ---------------------------------------------------------------------------


class TestResolveAndRegistered:
    def test_resolve_nonexistent_returns_none(self):
        r = MetaCommandRegistry()
        assert r.resolve("nonexistent") is None

    def test_resolve_returns_tuple(self):
        r = MetaCommandRegistry()
        parser = _dummy_parser_named("x")
        handler = _dummy_handler
        r.register("x", parser, handler)
        result = r.resolve("x")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result == (parser, handler)

    def test_registered_empty_returns_empty_list(self):
        r = MetaCommandRegistry()
        assert r.registered() == []

    def test_registered_is_sorted(self):
        r = MetaCommandRegistry()
        r.register("zulu", _dummy_parser_named("zulu"), _dummy_handler)
        r.register("alpha", _dummy_parser_named("alpha"), _dummy_handler)
        r.register("mike", _dummy_parser_named("mike"), _dummy_handler)
        assert r.registered() == ["alpha", "mike", "zulu"]


# ---------------------------------------------------------------------------
# build_parsers
# ---------------------------------------------------------------------------


class TestBuildParsers:
    def test_build_parsers_calls_each_factory(self):
        r = MetaCommandRegistry()
        called = []

        def factory_a(subparsers):
            called.append("a")
            subparsers.add_parser("a")

        def factory_b(subparsers):
            called.append("b")
            subparsers.add_parser("b")

        r.register("a", factory_a, _dummy_handler)
        r.register("b", factory_b, _dummy_handler)

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        r.build_parsers(subparsers)

        assert set(called) == {"a", "b"}

    def test_build_parsers_empty_registry_is_noop(self):
        r = MetaCommandRegistry()
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        r.build_parsers(subparsers)  # should not raise


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_dispatch_routes_by_meta_attribute(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _make_return_handler(42))
        r.register("info", _dummy_parser_named("info"), _make_return_handler(7))

        args = argparse.Namespace(_meta="list")
        assert r.dispatch(args, None, [], [], None) == 42

        args = argparse.Namespace(_meta="info")
        assert r.dispatch(args, None, [], [], None) == 7

    def test_dispatch_missing_meta_returns_1(self):
        r = MetaCommandRegistry()
        args = argparse.Namespace()  # no _meta attribute
        assert r.dispatch(args, None, [], [], None) == 1

    def test_dispatch_unknown_meta_returns_1(self):
        r = MetaCommandRegistry()
        args = argparse.Namespace(_meta="never-registered")
        assert r.dispatch(args, None, [], [], None) == 1

    def test_dispatch_passes_all_arguments_to_handler(self):
        r = MetaCommandRegistry()
        captured = {}

        def capturing_handler(args, engine, projects, kits, project_root):
            captured["args"] = args
            captured["engine"] = engine
            captured["projects"] = projects
            captured["kits"] = kits
            captured["project_root"] = project_root
            return 0

        r.register("test", _dummy_parser_named("test"), capturing_handler)
        args = argparse.Namespace(_meta="test", extra="foo")
        r.dispatch(args, "ENGINE", ["P1"], ["K1"], "/root")

        assert captured["args"].extra == "foo"
        assert captured["engine"] == "ENGINE"
        assert captured["projects"] == ["P1"]
        assert captured["kits"] == ["K1"]
        assert captured["project_root"] == "/root"


# ---------------------------------------------------------------------------
# Lifecycle: lock / unlock / is_locked
# ---------------------------------------------------------------------------


class TestLocking:
    def test_new_registry_is_unlocked(self):
        r = MetaCommandRegistry()
        assert not r.is_locked()

    def test_lock_sets_locked_state(self):
        r = MetaCommandRegistry()
        r.lock()
        assert r.is_locked()

    def test_register_after_lock_raises(self):
        r = MetaCommandRegistry()
        r.lock()
        with pytest.raises(RegistryLockedError) as exc:
            r.register("x", _dummy_parser, _dummy_handler)
        assert "locked" in str(exc.value).lower()

    def test_override_after_lock_raises(self):
        r = MetaCommandRegistry()
        r.register("x", _dummy_parser, _dummy_handler)
        r.lock()
        with pytest.raises(RegistryLockedError):
            r.override("x", handler=_make_return_handler(1))

    def test_unregister_after_lock_raises(self):
        r = MetaCommandRegistry()
        r.register("x", _dummy_parser, _dummy_handler)
        r.lock()
        with pytest.raises(RegistryLockedError):
            r.unregister("x")

    def test_clear_after_lock_raises(self):
        r = MetaCommandRegistry()
        r.register("x", _dummy_parser, _dummy_handler)
        r.lock()
        with pytest.raises(RegistryLockedError):
            r.clear()

    def test_resolve_after_lock_allowed(self):
        """Reads are fine; only mutations are blocked."""
        r = MetaCommandRegistry()
        r.register("x", _dummy_parser, _dummy_handler)
        r.lock()
        assert r.resolve("x") is not None

    def test_dispatch_after_lock_allowed(self):
        r = MetaCommandRegistry()
        r.register("x", _dummy_parser, _make_return_handler(7))
        r.lock()
        args = argparse.Namespace(_meta="x")
        assert r.dispatch(args, None, [], [], None) == 7

    def test_registered_after_lock_allowed(self):
        r = MetaCommandRegistry()
        r.register("x", _dummy_parser, _dummy_handler)
        r.lock()
        assert r.registered() == ["x"]

    def test_unlock_re_enables_mutations(self):
        r = MetaCommandRegistry()
        r.lock()
        r.unlock()
        assert not r.is_locked()
        r.register("x", _dummy_parser, _dummy_handler)  # does not raise


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_all(self):
        r = MetaCommandRegistry()
        r.register("a", _dummy_parser_named("a"), _dummy_handler)
        r.register("b", _dummy_parser_named("b"), _dummy_handler)
        r.clear()
        assert r.registered() == []
        assert len(r) == 0

    def test_clear_on_empty_registry_is_noop(self):
        r = MetaCommandRegistry()
        r.clear()
        assert r.registered() == []


# ---------------------------------------------------------------------------
# Container dunders
# ---------------------------------------------------------------------------


class TestContainerDunders:
    def test_contains(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _dummy_handler)
        assert "list" in r
        assert "info" not in r

    def test_len(self):
        r = MetaCommandRegistry()
        assert len(r) == 0
        r.register("a", _dummy_parser_named("a"), _dummy_handler)
        assert len(r) == 1
        r.register("b", _dummy_parser_named("b"), _dummy_handler)
        assert len(r) == 2
        r.unregister("a")
        assert len(r) == 1

    def test_repr_unlocked(self):
        r = MetaCommandRegistry()
        r.register("list", _dummy_parser_named("list"), _dummy_handler)
        r.register("info", _dummy_parser_named("info"), _dummy_handler)
        s = repr(r)
        assert "mutable" in s
        assert "info" in s
        assert "list" in s

    def test_repr_locked(self):
        r = MetaCommandRegistry()
        r.lock()
        s = repr(r)
        assert "locked" in s

    def test_repr_empty(self):
        r = MetaCommandRegistry()
        s = repr(r)
        assert "empty" in s.lower()


# ---------------------------------------------------------------------------
# Integration: realistic wtf-like usage
# ---------------------------------------------------------------------------


class TestRealisticUsage:
    def test_wtf_style_customization(self):
        """Reproduce the wtf-windows configuration: override list/info,
        add mode/new/add, unregister tree/setup."""
        r = MetaCommandRegistry()

        # Simulate library auto-registering defaults
        for name in ["list", "info", "kit", "version", "tree", "setup"]:
            r.register(name, _dummy_parser_named(name), _make_return_handler(0))

        # wtf drops defaults it doesn't want
        r.unregister("tree")
        r.unregister("setup")

        # wtf overrides list + info with domain-enriched handlers
        r.override("list", handler=_make_return_handler(100))
        r.override("info", handler=_make_return_handler(200))

        # wtf adds its own commands
        r.register("mode", _dummy_parser_named("mode"), _make_return_handler(10))
        r.register("new", _dummy_parser_named("new"), _make_return_handler(11))
        r.register("add", _dummy_parser_named("add"), _make_return_handler(12))

        # Final state
        assert set(r.registered()) == {
            "list", "info", "kit", "version", "mode", "new", "add"
        }
        assert "tree" not in r
        assert "setup" not in r

        # Dispatch verification
        assert r.dispatch(argparse.Namespace(_meta="list"), None, [], [], None) == 100
        assert r.dispatch(argparse.Namespace(_meta="info"), None, [], [], None) == 200
        assert r.dispatch(argparse.Namespace(_meta="mode"), None, [], [], None) == 10
        assert r.dispatch(argparse.Namespace(_meta="version"), None, [], [], None) == 0
