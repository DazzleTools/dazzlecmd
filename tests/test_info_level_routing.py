"""B4 inc2 -- `dz info <target>` routes by resolved level (SD-1 + SD-3).

The level resolution itself is the library's `resolve_target` (unit-tested in
dazzlecmd-lib `test_target_resolution`). Here we verify the dazzlecmd-side
dispatch: `_cmd_info` branches on the resolved level to the right card, passes
the `--as` pin through, and surfaces a read auto-pick notification. The tool
path delegates to the unchanged library `render_info` (byte-gate covers it),
so it is not re-exercised here.
"""
import json
import types

import pytest

from dazzlecmd.cli import build_parser, _cmd_info

pytest.importorskip("dazzlecmd_lib.target_resolution")
from dazzlecmd_lib.target_resolution import TargetResolution  # noqa: E402


def _kit(name="demo"):
    return types.SimpleNamespace(
        kit_name=name, name=name, virtual=False, tools=[1, 2],
        version="1.0", description="A demo kit.", kit_import_name=None,
        directory=None, kit_source="/x/demo.kit.json", always_active=False)


def _engine(res, *, kits=()):
    """A duck-typed engine whose resolve_target returns ``res``."""
    return types.SimpleNamespace(
        resolve_target=lambda name, as_level=None, mutating=False: res,
        command="dz", name="dazzlecmd",
        description="A demo aggregator.", version_info=("1.2.3", "1.2.3-full"),
        kits=list(kits), _get_user_config=lambda: {})


class TestParser:
    def test_info_has_the_as_pin_flag(self):
        a = build_parser([]).parse_args(["info", "foo", "--as", "kit"])
        assert a.tool == "foo" and a.as_level == "kit"

    def test_info_as_rejects_unknown_level(self):
        with pytest.raises(SystemExit):
            build_parser([]).parse_args(["info", "foo", "--as", "planet"])

    def test_info_json_flag_sets_as_json(self):
        a = build_parser([]).parse_args(["info", "foo", "--json"])
        assert a.as_json is True

    def test_info_without_json_defaults_off(self):
        a = build_parser([]).parse_args(["info", "foo"])
        assert getattr(a, "as_json", False) is False


class TestJson:
    """`--json` emits a structured, facet-shaped card at every level (the
    capability the kit/aggregator handlers already supported via
    `render_interrogation(as_json=...)`, now exposed on the unified `dz info`)."""

    def test_kit_json_emits_structured_card(self, tmp_path, capsys):
        kit = _kit("demo")
        eng = _engine(TargetResolution(kit, "kit"), kits=[kit])
        args = types.SimpleNamespace(tool="demo", as_level=None, as_json=True)
        assert _cmd_info(args, [], eng, kits=[kit],
                         project_root=str(tmp_path)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["kind"] == "kit"
        assert "state" in payload

    def test_aggregator_json_emits_structured_card(self, capsys):
        eng = _engine(None)
        eng.resolve_target = (
            lambda name, as_level=None, mutating=False:
            TargetResolution(eng, "aggregator"))
        args = types.SimpleNamespace(tool="dz", as_level=None, as_json=True)
        assert _cmd_info(args, [1, 2, 3], eng, kits=[],
                         project_root="/root") == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["kind"] == "aggregator"


class TestRouting:
    def test_kit_level_renders_the_kit_card(self, tmp_path, capsys):
        kit = _kit("demo")
        eng = _engine(TargetResolution(kit, "kit"), kits=[kit])
        args = types.SimpleNamespace(tool="demo", as_level=None)
        assert _cmd_info(args, [], eng, kits=[kit],
                         project_root=str(tmp_path)) == 0
        out = capsys.readouterr().out
        assert "Kit 'demo' -- identity card:" in out and "2 tool(s)" in out
        assert "Current state:" in out          # identity + state, one card

    def test_aggregator_level_renders_the_aggregator_card(self, capsys):
        eng = _engine(None)            # patched below to point at itself
        eng.resolve_target = (
            lambda name, as_level=None, mutating=False:
            TargetResolution(eng, "aggregator"))
        args = types.SimpleNamespace(tool="dz", as_level=None)
        assert _cmd_info(args, [1, 2, 3], eng, kits=[], project_root="/root") == 0
        out = capsys.readouterr().out
        assert "Aggregator 'dazzlecmd' -- identity card:" in out
        assert "3 tool(s)" in out and "Root:" in out and "/root" in out

    def test_read_auto_pick_notification_goes_to_stderr(self, tmp_path, capsys):
        kit = _kit("dup")
        note = "dz: 'dup' matches more than one level; using the kit."
        eng = _engine(TargetResolution(kit, "kit", notification=note), kits=[kit])
        args = types.SimpleNamespace(tool="dup", as_level=None)
        _cmd_info(args, [], eng, kits=[kit], project_root=str(tmp_path))
        captured = capsys.readouterr()
        assert "matches more than one level" in captured.err
        assert "identity card" in captured.out      # still rendered the picked card
