"""Tests for the aggregator self-setup routing in ``dz setup`` (#103).

``dz setup dz`` / ``dz setup dazzlecmd`` (or the ``python -m`` package
name) must route to the lib's PATH bootstrap instead of tool
resolution -- including when the engine is None, because a broken
install is exactly when this command matters. The bootstrap machinery
itself is tested in dazzlecmd-lib (tests/test_self_setup.py there);
this file covers the app-side wiring only.
"""

import pytest

from dazzlecmd.commands import setup as setup_mod


class _Args:
    def __init__(self, tool=None, yes=False, dry_run=False, level_args=None):
        self.tool = tool
        self.yes = yes
        self.dry_run = dry_run
        self.level_args = list(level_args or [])


class _Engine:
    command = "dz"
    name = "dazzlecmd"
    projects = []
    all_projects = []

    def resolve_command(self, name):
        return None, None


class _ShadowProject:
    fqcn = "dazzletools:dz"
    name = "dz"


class _ShadowEngine(_Engine):
    def resolve_command(self, name):
        if name == "dz":
            return _ShadowProject(), None
        return None, None


@pytest.fixture
def captured_run(monkeypatch):
    """Intercept the lib's run_self_setup; record calls."""
    from dazzlecmd_lib import self_setup

    calls = []

    def fake_run(names, **kwargs):
        calls.append((list(names), kwargs))
        return 0

    monkeypatch.setattr(self_setup, "run_self_setup", fake_run)
    return calls


class TestSelfNames:
    def test_static_names_present_even_with_broken_engine(self):
        names = setup_mod._self_names(None)
        assert "dz" in names
        assert "dazzlecmd" in names

    def test_engine_names_included(self):
        class Odd:
            command = "mycmd"
            name = "myagg"

        names = setup_mod._self_names(Odd())
        assert "mycmd" in names and "myagg" in names


class TestSelfRouting:
    @pytest.mark.parametrize("target", ["dz", "dazzlecmd"])
    def test_self_target_routes_to_bootstrap(self, target, captured_run):
        rc = setup_mod._cmd_setup(_Args(tool=target, yes=True), _Engine())
        assert rc == 0
        assert len(captured_run) == 1
        names, kwargs = captured_run[0]
        assert "dz" in names
        assert kwargs["assume_yes"] is True
        assert kwargs["package_name"] == "dazzlecmd"

    def test_flags_flow_through(self, captured_run):
        setup_mod._cmd_setup(_Args(tool="dz", dry_run=True), _Engine())
        assert captured_run[0][1]["dry_run"] is True
        assert captured_run[0][1]["assume_yes"] is False

    def test_self_setup_works_without_engine(self, captured_run):
        rc = setup_mod._cmd_setup(_Args(tool="dz"), None)
        assert rc == 0
        assert len(captured_run) == 1

    def test_tool_name_falls_through(self, captured_run):
        # engine=None + a non-self tool -> the classic engine guard.
        rc = setup_mod._cmd_setup(_Args(tool="some-tool"), None)
        assert rc == 1
        assert captured_run == []

    def test_no_arg_lists_and_exits_zero(self, captured_run, capsys):
        rc = setup_mod._cmd_setup(_Args(tool=None), _Engine())
        assert rc == 0
        assert captured_run == []
        assert "No tools have setup" in capsys.readouterr().out


class TestWarnings:
    """#103 criterion 5 + the tester-unbounded orphan-tail finding."""

    def test_orphan_tail_warns_not_silent(self, captured_run, capsys):
        rc = setup_mod._cmd_setup(
            _Args(tool=None, level_args=["--force"]), _Engine())
        assert rc == 0
        err = capsys.readouterr().err
        assert "ignored" in err and "--force" in err

    def test_reserved_self_tail_warns(self, captured_run, capsys):
        rc = setup_mod._cmd_setup(
            _Args(tool="dz", level_args=["extra"]), _Engine())
        assert rc == 0
        assert len(captured_run) == 1  # still routes to self-setup
        assert "reserved" in capsys.readouterr().err

    def test_shadowed_tool_name_is_surfaced(self, captured_run, capsys):
        rc = setup_mod._cmd_setup(_Args(tool="dz"), _ShadowEngine())
        assert rc == 0
        assert len(captured_run) == 1  # self-setup still wins
        err = capsys.readouterr().err
        assert "also a tool" in err and "dazzletools:dz" in err

    def test_no_shadow_no_noise(self, captured_run, capsys):
        setup_mod._cmd_setup(_Args(tool="dz"), _Engine())
        assert "also a tool" not in capsys.readouterr().err
