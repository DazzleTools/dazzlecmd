"""Tests for make_python_runner with runtime.interpreter (4b.3)."""

from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest

from dazzlecmd_lib.registry import (
    make_python_runner,
    _make_python_interpreter_runner,
)


class TestInterpreterDispatch:
    """runtime.interpreter takes precedence over importlib / pass_through."""

    def test_interpreter_triggers_subprocess_dispatch(self, tmp_path):
        script = tmp_path / "tool.py"
        script.write_text("import sys; sys.exit(0)")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "python",
                "script_path": "tool.py",
                "interpreter": sys.executable,
            },
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            runner = make_python_runner(project)
            exit_code = runner(["--flag"])
        assert exit_code == 0
        # Called with [interpreter, full_script, --flag]
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == sys.executable
        assert call_args[1].endswith("tool.py")
        assert call_args[2] == "--flag"

    def test_interpreter_bypasses_importlib(self, tmp_path):
        """When interpreter is declared, importlib.import_module is NOT called."""
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "python",
                "script_path": "tool.py",
                "interpreter": sys.executable,
            },
        }
        with patch("subprocess.run") as mock_run, \
             patch("importlib.import_module") as mock_import:
            mock_run.return_value = MagicMock(returncode=0)
            runner = make_python_runner(project)
            runner([])
        assert mock_run.called
        assert not mock_import.called

    def test_interpreter_bypasses_pass_through(self, tmp_path):
        """interpreter wins over pass_through: true."""
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "pass_through": True,
            "runtime": {
                "type": "python",
                "script_path": "tool.py",
                "interpreter": "/some/venv/bin/python",
            },
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            runner = make_python_runner(project)
            runner([])
        # interpreter was used (no resolution since not a real path), not sys.executable
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/some/venv/bin/python"
        assert cmd[0] != sys.executable


class TestInterpreterPathResolution:
    def test_absolute_interpreter_used_as_is(self, tmp_path):
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"script_path": "tool.py", "interpreter": "/abs/python"},
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            make_python_runner(project)([])
        assert mock_run.call_args[0][0][0] == "/abs/python"

    def test_relative_interpreter_resolves_against_tool_dir_when_exists(self, tmp_path):
        # Create a fake venv layout
        venv_bin = tmp_path / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        fake_python = venv_bin / "python"
        fake_python.write_text("# fake")

        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "script_path": "tool.py",
                "interpreter": ".venv/bin/python",
            },
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            make_python_runner(project)([])
        resolved = mock_run.call_args[0][0][0]
        # Should be the full path to the venv python, not the relative string
        assert resolved.endswith("python")
        assert str(tmp_path) in resolved

    def test_relative_interpreter_unresolved_passes_through(self, tmp_path):
        """If relative path doesn't resolve to a real file, pass through unchanged."""
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "script_path": "tool.py",
                "interpreter": ".venv/bin/python",  # doesn't exist
            },
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            make_python_runner(project)([])
        # Relative path passed through (with separator, tried to resolve, file missing)
        assert mock_run.call_args[0][0][0] == ".venv/bin/python"

    def test_bare_name_interpreter_passes_through(self, tmp_path):
        """`python3.11` or similar bare names are handled by subprocess PATH lookup."""
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"script_path": "tool.py", "interpreter": "python3.11"},
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            make_python_runner(project)([])
        assert mock_run.call_args[0][0][0] == "python3.11"

    def test_env_var_prefix_passes_through(self, tmp_path):
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "script_path": "tool.py",
                "interpreter": "%USERPROFILE%\\.venv\\python.exe",
            },
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            make_python_runner(project)([])
        assert mock_run.call_args[0][0][0] == "%USERPROFILE%\\.venv\\python.exe"


class TestScriptPathResolution:
    def test_relative_script_joined_against_tool_dir(self, tmp_path):
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"script_path": "tool.py", "interpreter": sys.executable},
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            make_python_runner(project)([])
        full_script = mock_run.call_args[0][0][1]
        assert os.path.isabs(full_script)
        assert full_script.endswith("tool.py")

    def test_absolute_script_used_as_is(self, tmp_path):
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"script_path": str(script), "interpreter": sys.executable},
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            make_python_runner(project)([])
        assert mock_run.call_args[0][0][1] == str(script)

    def test_missing_script_errors(self, tmp_path, capsys):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"script_path": "nonexistent.py", "interpreter": sys.executable},
        }
        runner = make_python_runner(project)
        exit_code = runner([])
        assert exit_code == 1
        assert "Script not found" in capsys.readouterr().err


class TestModuleMode:
    def test_module_path_dispatches_via_dash_m(self, tmp_path):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "module": "mypkg.tool",
                "interpreter": sys.executable,
            },
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            make_python_runner(project)(["arg"])
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == sys.executable
        assert cmd[1] == "-m"
        assert cmd[2] == "mypkg.tool"
        assert cmd[3] == "arg"


class TestExitCodePropagation:
    def test_nonzero_exit_code_returned(self, tmp_path):
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"script_path": "tool.py", "interpreter": sys.executable},
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=42)
            exit_code = make_python_runner(project)([])
        assert exit_code == 42


class TestBackwardsCompat:
    def test_no_interpreter_no_pass_through_still_uses_importlib(self, tmp_path):
        """Legacy path: default python runner behavior unchanged when interpreter absent."""
        script = tmp_path / "tool.py"
        script.write_text("def main(argv=None): return 0")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        with patch("subprocess.run") as mock_run, \
             patch("importlib.import_module") as mock_import:
            # Mock successful import with a main()
            fake_mod = MagicMock()
            fake_mod.main = lambda *a, **kw: 0
            mock_import.return_value = fake_mod
            runner = make_python_runner(project)
            runner([])
        # importlib was used, subprocess was NOT
        assert mock_import.called
        assert not mock_run.called

    def test_pass_through_without_interpreter_uses_sys_executable(self, tmp_path):
        """Pass-through path: subprocess via sys.executable."""
        script = tmp_path / "tool.py"
        script.write_text("pass")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "pass_through": True,
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            runner = make_python_runner(project)
            runner([])
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == sys.executable
