"""Tests for `dz setup` CLI behavior."""

from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest


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
