"""Tests for `dz setup` CLI behavior."""

from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest

from dazzlecmd import cli


def _fake_engine(projects):
    """Build a MagicMock engine with the given projects."""
    engine = MagicMock()
    engine.all_projects = projects
    engine.projects = projects
    return engine


class _Args:
    def __init__(self, tool=None):
        self.tool = tool


class TestBug1StdoutFlushBeforeSubprocess:
    """Regression: `dz setup` header output must flush BEFORE subprocess.run
    so the "Running setup for..." preamble appears above the command's output,
    not after. Found by the v0.7.20 tester sweep."""

    def test_sys_stdout_flush_called_before_subprocess_run(self, tmp_path):
        """Verify the flush-before-subprocess call ordering."""
        from dazzlecmd import cli

        # Minimal fake project that passes the earlier _cmd_setup checks
        project = {
            "name": "flush-test",
            "_fqcn": "test:flush-test",
            "_dir": str(tmp_path),
            "setup": {"command": "echo hi"},
        }

        # Fake engine exposing resolve_command + all_projects
        fake_engine = MagicMock()
        fake_engine.resolve_command.return_value = (project, None)
        fake_engine.all_projects = [project]
        fake_engine.projects = [project]

        # Track call order on a shared mock
        call_order = []

        def track_flush():
            call_order.append("flush")

        def track_run(*args, **kwargs):
            call_order.append("run")
            result = MagicMock()
            result.returncode = 0
            return result

        class FakeArgs:
            tool = "flush-test"

        with patch.object(sys.stdout, "flush", side_effect=track_flush), \
             patch("subprocess.run", side_effect=track_run):
            exit_code = cli._cmd_setup(FakeArgs(), fake_engine)

        assert exit_code == 0
        # flush must be called at least once BEFORE run. Both may appear
        # multiple times, but the first "run" must come after a "flush".
        assert "flush" in call_order
        assert "run" in call_order
        flush_idx = call_order.index("flush")
        run_idx = call_order.index("run")
        assert flush_idx < run_idx, (
            f"Expected sys.stdout.flush() BEFORE subprocess.run(). "
            f"Call order: {call_order}"
        )


class TestListingModeV0721:
    """v0.7.21: `dz setup` with no tool argument lists tools that have setup declared."""

    def test_no_tools_with_setup_prints_empty_message(self, capsys):
        engine = _fake_engine([
            {"name": "a", "_fqcn": "kit:a", "_dir": "/tmp/a"},
            {"name": "b", "_fqcn": "kit:b", "_dir": "/tmp/b", "setup": {}},
        ])
        exit_code = cli._cmd_setup(_Args(), engine)
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "No tools have setup" in out

    def test_tool_with_only_command_detected(self, capsys):
        engine = _fake_engine([
            {
                "name": "t",
                "_fqcn": "kit:t",
                "_dir": "/tmp/t",
                "setup": {"command": "pip install foo", "note": "Simple install"},
            },
        ])
        exit_code = cli._cmd_setup(_Args(), engine)
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "Tools with setup declared:" in out
        assert "kit:t" in out
        assert "Simple install" in out

    def test_tool_with_only_platforms_detected(self, capsys):
        # Tool with ONLY platform-specific setup, no top-level command --
        # the v0.7.20 listing missed this; v0.7.21 polish catches it.
        engine = _fake_engine([
            {
                "name": "t",
                "_fqcn": "kit:t",
                "_dir": "/tmp/t",
                "setup": {"platforms": {"linux": {"command": "apt install foo"}}},
            },
        ])
        exit_code = cli._cmd_setup(_Args(), engine)
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "kit:t" in out

    def test_tool_without_setup_not_listed(self, capsys):
        engine = _fake_engine([
            {"name": "a", "_fqcn": "kit:a", "_dir": "/tmp/a"},  # no setup
            {
                "name": "b",
                "_fqcn": "kit:b",
                "_dir": "/tmp/b",
                "setup": {"command": "pip install"},
            },
        ])
        exit_code = cli._cmd_setup(_Args(), engine)
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "kit:a" not in out
        assert "kit:b" in out

    def test_output_sorted_alphabetically_by_fqcn(self, capsys):
        engine = _fake_engine([
            {"name": "z", "_fqcn": "kit:z", "_dir": "/t", "setup": {"command": "x"}},
            {"name": "a", "_fqcn": "kit:a", "_dir": "/t", "setup": {"command": "x"}},
            {"name": "m", "_fqcn": "kit:m", "_dir": "/t", "setup": {"command": "x"}},
        ])
        cli._cmd_setup(_Args(), engine)
        out = capsys.readouterr().out
        a_idx = out.index("kit:a")
        m_idx = out.index("kit:m")
        z_idx = out.index("kit:z")
        assert a_idx < m_idx < z_idx

    def test_note_shown_when_present(self, capsys):
        engine = _fake_engine([
            {
                "name": "t",
                "_fqcn": "kit:t",
                "_dir": "/t",
                "setup": {"command": "pip", "note": "Installs the thing"},
            },
        ])
        cli._cmd_setup(_Args(), engine)
        out = capsys.readouterr().out
        assert "Installs the thing" in out

    def test_missing_note_shown_as_dash(self, capsys):
        engine = _fake_engine([
            {
                "name": "t",
                "_fqcn": "kit:t",
                "_dir": "/t",
                "setup": {"command": "pip"},
            },
        ])
        cli._cmd_setup(_Args(), engine)
        out = capsys.readouterr().out
        # Listing includes a placeholder dash instead of empty string
        assert "kit:t" in out
        # A "-" appears after the fqcn
        lines = [l for l in out.splitlines() if "kit:t" in l]
        assert lines and "-" in lines[0]

    def test_column_width_adapts_to_longest_fqcn(self, capsys):
        long_fqcn = "very-long-kit-name:very-long-tool-name"
        engine = _fake_engine([
            {"name": "t", "_fqcn": long_fqcn, "_dir": "/t", "setup": {"command": "x", "note": "n"}},
            {"name": "s", "_fqcn": "kit:short", "_dir": "/t", "setup": {"command": "x", "note": "m"}},
        ])
        cli._cmd_setup(_Args(), engine)
        out = capsys.readouterr().out
        # The short fqcn line should have its note aligned PAST the long fqcn's end
        short_line = next(l for l in out.splitlines() if "kit:short" in l)
        long_line = next(l for l in out.splitlines() if long_fqcn in l)
        # Both notes appear at the SAME column position
        assert short_line.index("m") >= len(f"  kit:short") + 10

    def test_run_hint_printed(self, capsys):
        engine = _fake_engine([
            {"name": "t", "_fqcn": "kit:t", "_dir": "/t", "setup": {"command": "x"}},
        ])
        cli._cmd_setup(_Args(), engine)
        out = capsys.readouterr().out
        assert "Run: dz setup <tool>" in out


class TestMalformedOverrideCleanError:
    """v0.7.22 BUG-1 regression: malformed override JSON surfaces clean error, no traceback."""

    def test_setup_malformed_override_json_clean_error(self, tmp_path, monkeypatch, capsys):
        # Isolate override root to tmp, write garbage JSON
        monkeypatch.setenv("DAZZLECMD_OVERRIDES_DIR", str(tmp_path))
        (tmp_path / "setup").mkdir()
        (tmp_path / "setup" / "kit__t.json").write_text("{not valid json")

        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": "/t",
            "setup": {"command": "pip install foo"},
        }
        engine = _fake_engine([project])
        engine.resolve_command.return_value = (project, None)

        exit_code = cli._cmd_setup(_Args(tool="kit:t"), engine)
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Error:" in captured.err
        assert "not valid JSON" in captured.err or "Expecting" in captured.err
        # No Python traceback markers
        assert "Traceback" not in captured.err
        assert "File \"" not in captured.err

