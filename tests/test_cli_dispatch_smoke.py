"""R6/R7 decomposition smoke -- the dispatch fan-in's regression net.

`dz version` broke silently in the split's first cut (F821: _cmd_version
referenced DISPLAY_VERSION/__version__ without importing them) because NO
test exercised it -- the suite was green while the live command
tracebacked. These pin every extracted read-path handler in-process, plus
the re-export surface the engine wiring and older tests rely on.
"""
import types

from dazzlecmd import cli, dispatch
from dazzlecmd.commands import inspect as inspect_cmds


class TestCmdVersion:
    def test_cmd_version_runs(self, capsys):
        # the exact handler the first cut broke
        assert inspect_cmds._cmd_version() == 0
        out = capsys.readouterr().out
        assert "dazzlecmd" in out

    def test_version_via_dispatch_meta(self, capsys):
        args = types.SimpleNamespace(_meta="version")
        assert dispatch.dispatch_meta(args, [], [], None, engine=None) == 0
        assert "dazzlecmd" in capsys.readouterr().out


class TestReExportSurface:
    """cli.py must keep re-exporting every moved name (engine wiring +
    the older tests import from dazzlecmd.cli)."""

    def test_dispatchers_reexported(self):
        assert cli.dispatch_meta is dispatch.dispatch_meta
        assert cli.dispatch_tool is dispatch.dispatch_tool
        assert cli._dispatch_verb_target is dispatch._dispatch_verb_target
        assert cli._sugar_flags_hook is dispatch._sugar_flags_hook

    def test_inspect_handlers_reexported(self):
        assert cli._cmd_list is inspect_cmds._cmd_list
        assert cli._cmd_info is inspect_cmds._cmd_info
        assert cli._cmd_tree is inspect_cmds._cmd_tree
        assert cli._cmd_version is inspect_cmds._cmd_version
        assert cli.render_kit_info is inspect_cmds.render_kit_info

    def test_handler_table_binds_inspect_handlers(self):
        # the tag->handler table must reference the REAL handlers
        t = dispatch._VERB_LEVEL_HANDLERS
        assert t["tool_info"] is inspect_cmds._info_at_tool
        assert t["kit_info"] is inspect_cmds._info_at_kit
        assert t["aggregator_info"] is inspect_cmds._info_at_aggregator
