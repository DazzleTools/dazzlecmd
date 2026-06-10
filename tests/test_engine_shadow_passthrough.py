"""Tests for issue #67's redesign: named tools own their name (Option A).

In ``engine._dispatch_registry_path``, the dispatcher checks
``resolve_command(name)`` BEFORE the meta-command path. If a tool exists
with that name, the tool wins and receives ``argv[1:]`` unchanged. The
lib does NOT parse, filter, or claim post-command args for tools.

These tests cover:

* Shadow case (the central new behavior): a tool whose name matches a
  reserved meta-command is dispatched as the tool. Argv after the name
  passes through verbatim.
* Non-shadowed meta-commands (e.g. ``dz list``) still work.
* Non-shadowed tools (e.g. ``dz find``) still work (no regression).
* Python tools' own ``-h`` argparse still works (regression guard).
* Top-level aggregator flags (``--version``) still parse correctly.

The previous attempt (commit 724fe0a, reverted) intercepted specific
flags (``-h`` / ``--help`` / ``-?``) in a per-flag set. This redesign
has NO per-flag enumeration; the lib is a transparent dispatcher.
"""

import json
import os
from unittest.mock import MagicMock

import pytest

from dazzlecmd_lib.engine import AggregatorEngine


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _build_shadowed_aggregator(root, tool_name="setup"):
    """Create an aggregator with a PS tool whose name shadows a meta-command.

    ``tool_name`` defaults to ``setup`` (which IS a reserved meta-command in
    dazzlecmd-lib's default registry). The fixture only declares the manifest
    -- no real .ps1 is needed because the dispatcher is exercised with a
    mock ``tool_dispatcher``.
    """
    _write_json(
        os.path.join(root, "kits", "core.kit.json"),
        {"name": "core", "always_active": True},
    )
    _write_json(
        os.path.join(root, "projects", "core", ".kit.json"),
        {"name": "core", "tools_dir": ".", "tools": [f"core:{tool_name}"]},
    )
    tool_dir = os.path.join(root, "projects", "core", tool_name)
    os.makedirs(tool_dir, exist_ok=True)
    _write_json(
        os.path.join(tool_dir, ".test.json"),
        {
            "name": tool_name,
            "namespace": "core",
            "version": "0.1.0",
            "description": f"shadowed PS tool (collides with reserved meta-command {tool_name!r})",
            "runtime": {
                "type": "shell",
                "shell": "powershell",
                "script_path": f"{tool_name}.ps1",
            },
        },
    )


def _build_non_shadowed_aggregator(root):
    """Aggregator with a single tool whose name does NOT collide with any meta-command."""
    _write_json(
        os.path.join(root, "kits", "core.kit.json"),
        {"name": "core", "always_active": True},
    )
    _write_json(
        os.path.join(root, "projects", "core", ".kit.json"),
        {"name": "core", "tools_dir": ".", "tools": ["core:my-cool-tool"]},
    )
    tool_dir = os.path.join(root, "projects", "core", "my-cool-tool")
    os.makedirs(tool_dir, exist_ok=True)
    _write_json(
        os.path.join(tool_dir, ".test.json"),
        {
            "name": "my-cool-tool",
            "namespace": "core",
            "version": "0.1.0",
            "description": "a non-shadowed PS tool",
            "runtime": {
                "type": "shell",
                "shell": "powershell",
                "script_path": "my-cool-tool.ps1",
            },
        },
    )


def _build_engine(tmp_path, dispatcher):
    engine = AggregatorEngine(
        name="test",
        command="test",
        tools_dir="projects",
        kits_dir="kits",
        manifest=".test.json",
        tool_dispatcher=dispatcher,
    )
    engine.discover(project_root=str(tmp_path))
    return engine


# ---------------------------------------------------------------------------
# Central new behavior: shadowed tool wins, ALL argv passes through
# ---------------------------------------------------------------------------


def test_shadowed_tool_wins_with_unknown_flag(tmp_path):
    """`<aggregator> setup -Install` dispatches the PS tool with ['-Install']."""
    _build_shadowed_aggregator(tmp_path, tool_name="setup")
    dispatcher = MagicMock(return_value=0)
    engine = _build_engine(tmp_path, dispatcher)

    # Fixture sanity: 'setup' is BOTH a reserved meta-command AND a tool.
    assert "setup" in engine.reserved_commands
    assert any(p.name == "setup" for p in engine.projects)

    rc = engine.run(["setup", "-Install"])
    assert rc == 0
    dispatcher.assert_called_once()
    project, forwarded_argv = dispatcher.call_args.args
    assert project.name == "setup"
    assert forwarded_argv == ["-Install"]


def test_shadowed_tool_wins_with_no_args(tmp_path):
    """`<aggregator> setup` (no args) dispatches the PS tool with []."""
    _build_shadowed_aggregator(tmp_path, tool_name="setup")
    dispatcher = MagicMock(return_value=0)
    engine = _build_engine(tmp_path, dispatcher)

    rc = engine.run(["setup"])
    assert rc == 0
    dispatcher.assert_called_once()
    project, forwarded_argv = dispatcher.call_args.args
    assert project.name == "setup"
    assert forwarded_argv == []


def test_shadowed_tool_receives_help_flags_unchanged(tmp_path):
    """`<aggregator> setup -h` passes ['-h'] to the runner (no lib interception).

    Under Option A the lib is transparent — it does NOT special-case help
    flags. The runner receives ``-h`` and decides what to do with it
    (PowerShell scripts that don't handle ``-h`` will footgun, same as
    if invoked directly; the script author is responsible for that).
    """
    _build_shadowed_aggregator(tmp_path, tool_name="setup")
    dispatcher = MagicMock(return_value=0)
    engine = _build_engine(tmp_path, dispatcher)

    for help_flag in ("-h", "--help", "-?"):
        dispatcher.reset_mock()
        rc = engine.run(["setup", help_flag])
        assert rc == 0
        dispatcher.assert_called_once()
        _, forwarded_argv = dispatcher.call_args.args
        assert forwarded_argv == [help_flag], (
            f"Expected {help_flag!r} to pass through to the runner; "
            f"got {forwarded_argv!r}. Per Option A the lib must NOT consume "
            f"help flags for tools."
        )


def test_shadowed_tool_receives_multiple_args_unchanged(tmp_path):
    """Argv after the tool name passes through verbatim, regardless of shape."""
    _build_shadowed_aggregator(tmp_path, tool_name="setup")
    dispatcher = MagicMock(return_value=0)
    engine = _build_engine(tmp_path, dispatcher)

    argv = ["-Foo", "bar", "-h", "--baz=qux", "positional", "-Quiet"]
    rc = engine.run(["setup"] + argv)
    assert rc == 0
    dispatcher.assert_called_once()
    _, forwarded_argv = dispatcher.call_args.args
    assert forwarded_argv == argv


# ---------------------------------------------------------------------------
# Regression guards: non-shadowed behavior must be unchanged
# ---------------------------------------------------------------------------


def test_non_shadowed_meta_command_still_works(tmp_path, capsys):
    """`<aggregator> list` (a meta-command, not shadowed) still runs the meta-command."""
    _build_non_shadowed_aggregator(tmp_path)  # tool name is 'my-cool-tool'
    dispatcher = MagicMock(return_value=0)
    engine = _build_engine(tmp_path, dispatcher)

    rc = engine.run(["list"])
    assert rc == 0
    # The 'list' meta-command runs, printing tool info to stdout. Just verify
    # the dispatcher was NOT called (no tool was dispatched).
    dispatcher.assert_not_called()
    out = capsys.readouterr().out
    # Meta-command's list output includes the tool name(s).
    assert "my-cool-tool" in out


def test_non_shadowed_tool_dispatch_unchanged(tmp_path):
    """`<aggregator> my-cool-tool -Foo` (non-shadowed tool) still dispatches normally."""
    _build_non_shadowed_aggregator(tmp_path)
    dispatcher = MagicMock(return_value=0)
    engine = _build_engine(tmp_path, dispatcher)

    rc = engine.run(["my-cool-tool", "-Foo", "bar"])
    assert rc == 0
    dispatcher.assert_called_once()
    project, forwarded_argv = dispatcher.call_args.args
    assert project.name == "my-cool-tool"
    assert forwarded_argv == ["-Foo", "bar"]


def test_unknown_command_still_errors(tmp_path, capsys):
    """Unknown command names still go through argparse's standard error path."""
    _build_non_shadowed_aggregator(tmp_path)
    dispatcher = MagicMock(return_value=0)
    engine = _build_engine(tmp_path, dispatcher)

    with pytest.raises(SystemExit):
        engine.run(["totally-unknown-command"])
    dispatcher.assert_not_called()


# ---------------------------------------------------------------------------
# Top-level aggregator flags
# ---------------------------------------------------------------------------


def test_top_level_version_flag_still_works(tmp_path, capsys):
    """`<aggregator> --version` is handled by the engine before any dispatch."""
    _build_non_shadowed_aggregator(tmp_path)
    dispatcher = MagicMock(return_value=0)
    engine = AggregatorEngine(
        name="test",
        command="test",
        tools_dir="projects",
        kits_dir="kits",
        manifest=".test.json",
        tool_dispatcher=dispatcher,
        version_info=("0.0.1", "0.0.1-test"),
    )
    engine.discover(project_root=str(tmp_path))

    rc = engine.run(["--version"])
    assert rc == 0
    dispatcher.assert_not_called()
    out = capsys.readouterr().out
    assert "0.0.1" in out
