"""Tests for RunnerRegistry and individual runner factories.

Phase 4c.1 — binary runner polish (v0.7.15).
"""

import os
import subprocess
import sys
import textwrap

import pytest

from dazzlecmd_lib.registry import (
    RunnerRegistry,
    make_binary_runner,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tool_dir, runtime_overrides=None):
    """Build a minimal project dict for binary runner tests."""
    base = {
        "name": "test-binary-tool",
        "_dir": str(tool_dir),
        "_fqcn": "test:test-binary-tool",
        "runtime": {"type": "binary", "script_path": "my-tool"},
    }
    if runtime_overrides:
        base["runtime"].update(runtime_overrides)
    return base


# ---------------------------------------------------------------------------
# Binary runner: dispatch precedence
# ---------------------------------------------------------------------------

class TestBinaryRunnerPrecedence:
    """Tests for make_binary_runner dispatch logic."""

    def test_binary_exists_runs_binary(self, tmp_path, monkeypatch):
        """When the binary exists on disk, run it (precedence 2)."""
        binary = tmp_path / "my-tool"
        # Create a script that acts like a binary
        if sys.platform == "win32":
            binary = tmp_path / "my-tool.bat"
            binary.write_text("@echo BINARY_OK\n")
            project = _make_project(tmp_path, {"script_path": "my-tool.bat"})
        else:
            binary.write_text("#!/bin/sh\necho BINARY_OK\n")
            binary.chmod(0o755)
            project = _make_project(tmp_path)

        runner = make_binary_runner(project)
        result = runner([])
        assert result == 0

    def test_binary_missing_dev_command_fallback(self, tmp_path):
        """Binary absent + dev_command set -> use dev_command (precedence 3)."""
        from unittest.mock import patch

        project = _make_project(tmp_path, {
            "script_path": "nonexistent-binary",
            "dev_command": "cargo run --",
        })

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_binary_runner(project)
            result = runner([])
            assert result == 0
            call_args = mock_run.call_args[0][0]
            assert call_args == ["cargo", "run", "--"]

    def test_binary_missing_no_dev_command_errors(self, tmp_path):
        """Binary absent + no dev_command -> error exit (precedence 4)."""
        project = _make_project(tmp_path, {
            "script_path": "nonexistent-binary",
        })
        runner = make_binary_runner(project)
        result = runner([])
        assert result == 1

    def test_no_script_path_errors(self, tmp_path):
        """No script_path at all -> error exit."""
        project = _make_project(tmp_path, {"script_path": None})
        # script_path is None, but the factory reads it from runtime
        project["runtime"].pop("script_path", None)
        runner = make_binary_runner(project)
        result = runner([])
        assert result == 1

    def test_force_dev_overrides_existing_binary(self, tmp_path, monkeypatch):
        """DAZZLECMD_FORCE_DEV=1 uses dev_command even when binary exists (precedence 1)."""
        binary = tmp_path / "my-tool"
        if sys.platform == "win32":
            binary = tmp_path / "my-tool.bat"
            binary.write_text("@echo BINARY_PATH\n")
            script_path = "my-tool.bat"
        else:
            binary.write_text("#!/bin/sh\necho BINARY_PATH\n")
            binary.chmod(0o755)
            script_path = "my-tool"

        project = _make_project(tmp_path, {
            "script_path": script_path,
            "dev_command": f"{sys.executable} -c \"print('FORCE_DEV_OK')\"",
        })

        monkeypatch.setenv("DAZZLECMD_FORCE_DEV", "1")
        runner = make_binary_runner(project)

        # Capture output to verify dev_command ran, not binary
        import io
        from unittest.mock import patch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner([])
            # The first call should be dev_command, not the binary path
            call_args = mock_run.call_args[0][0]
            assert sys.executable in call_args[0] or "python" in call_args[0].lower()

    def test_force_dev_without_dev_command_runs_binary(self, tmp_path, monkeypatch):
        """DAZZLECMD_FORCE_DEV=1 but no dev_command -> falls through to binary."""
        binary = tmp_path / "my-tool"
        if sys.platform == "win32":
            binary = tmp_path / "my-tool.bat"
            binary.write_text("@echo BINARY_OK\n")
            project = _make_project(tmp_path, {"script_path": "my-tool.bat"})
        else:
            binary.write_text("#!/bin/sh\necho BINARY_OK\n")
            binary.chmod(0o755)
            project = _make_project(tmp_path)

        monkeypatch.setenv("DAZZLECMD_FORCE_DEV", "1")
        runner = make_binary_runner(project)
        result = runner([])
        assert result == 0

    def test_force_dev_env_not_set_runs_binary(self, tmp_path, monkeypatch):
        """DAZZLECMD_FORCE_DEV not set -> binary takes precedence over dev_command."""
        monkeypatch.delenv("DAZZLECMD_FORCE_DEV", raising=False)

        binary = tmp_path / "my-tool"
        if sys.platform == "win32":
            binary = tmp_path / "my-tool.bat"
            binary.write_text("@echo BINARY_PATH\n")
            script_path = "my-tool.bat"
        else:
            binary.write_text("#!/bin/sh\necho BINARY_PATH\n")
            binary.chmod(0o755)
            script_path = "my-tool"

        project = _make_project(tmp_path, {
            "script_path": script_path,
            "dev_command": f"{sys.executable} -c \"print('DEV_CMD')\"",
        })

        from unittest.mock import patch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_binary_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # Should be the binary path, not dev_command
            assert str(tmp_path) in call_args[0]


class TestBinaryRunnerArgPassing:
    """Verify argv is correctly forwarded to the subprocess."""

    def test_args_forwarded_to_binary(self, tmp_path):
        """Arguments are appended to the binary command."""
        from unittest.mock import patch

        binary = tmp_path / "my-tool"
        binary.write_text("")  # Just needs to exist for os.path.isfile
        project = _make_project(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_binary_runner(project)
            runner(["--verbose", "file.txt"])
            call_args = mock_run.call_args[0][0]
            assert call_args[-2:] == ["--verbose", "file.txt"]

    def test_args_forwarded_to_dev_command(self, tmp_path):
        """Arguments are appended to dev_command."""
        from unittest.mock import patch

        project = _make_project(tmp_path, {
            "script_path": "nonexistent",
            "dev_command": "cargo run --",
        })

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_binary_runner(project)
            runner(["--verbose", "file.txt"])
            call_args = mock_run.call_args[0][0]
            assert call_args == ["cargo", "run", "--", "--verbose", "file.txt"]


class TestRunnerRegistryBinaryResolution:
    """Verify the 'binary' type is registered and resolves."""

    def test_binary_type_registered(self):
        assert "binary" in RunnerRegistry.registered_types()

    def test_resolve_binary_project(self, tmp_path):
        project = _make_project(tmp_path)
        runner = RunnerRegistry.resolve(project)
        assert runner is not None
        assert callable(runner)
