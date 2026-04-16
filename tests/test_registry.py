"""Tests for RunnerRegistry and individual runner factories.

Phase 4c.1 — binary runner polish (v0.7.15).
Phase 4c.2 — shell runner enhancements (v0.7.16).
"""

import os
import shutil
import subprocess
import sys
import textwrap

import pytest

from dazzlecmd_lib.registry import (
    RunnerRegistry,
    SHELL_PROFILES,
    make_binary_runner,
    make_shell_runner,
)


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "shells")


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


# ===========================================================================
# Phase 4c.2 — Shell runner tests
# ===========================================================================


def _make_shell_project(tool_dir, shell, script_name="hello.sh", runtime_overrides=None):
    """Build a shell-type project dict. Copies fixture script into tool_dir."""
    fixture = os.path.join(FIXTURE_DIR, script_name)
    dest = os.path.join(str(tool_dir), script_name)
    if os.path.isfile(fixture):
        import shutil as _sh
        _sh.copy(fixture, dest)
    project = {
        "name": "test-shell-tool",
        "_dir": str(tool_dir),
        "_fqcn": "test:test-shell-tool",
        "runtime": {
            "type": "shell",
            "shell": shell,
            "script_path": script_name,
        },
    }
    if runtime_overrides:
        project["runtime"].update(runtime_overrides)
    return project


class TestShellProfiles:
    """Sanity checks on the SHELL_PROFILES dispatch table."""

    def test_all_expected_shells_registered(self):
        expected = {"cmd", "bash", "sh", "zsh", "csh", "pwsh", "powershell"}
        assert expected == set(SHELL_PROFILES.keys())

    def test_profile_fields_present(self):
        required_fields = {
            "script_flag", "string_flag", "interactive_flag",
            "source_template", "chain_sep", "needs_shell_true",
        }
        for shell, profile in SHELL_PROFILES.items():
            assert required_fields.issubset(set(profile.keys())), \
                f"shell '{shell}' missing required fields"

    def test_perl_not_in_shell_profiles(self):
        """perl (and other scripting-language interpreters) belong in the
        'script' runtime type, not 'shell'. They lack shell semantics
        (no chain operators, no source syntax, no interactive keep-open)."""
        assert "perl" not in SHELL_PROFILES
        assert "ruby" not in SHELL_PROFILES
        assert "lua" not in SHELL_PROFILES

    def test_sh_and_csh_lack_interactive_flag(self):
        assert SHELL_PROFILES["sh"]["interactive_flag"] is None
        assert SHELL_PROFILES["csh"]["interactive_flag"] is None


class TestShellArgsReplace:
    """shell_args replaces the default exec flag (not layered)."""

    def test_shell_args_present_overrides_exec_flag(self, tmp_path):
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "bash",
            runtime_overrides={"shell_args": ["--custom-flag", "-c"]},
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert "--custom-flag" in call_args
            # Default bash exec flag "-c" is provided by user explicitly;
            # should NOT have been injected separately by the runner
            assert call_args.count("-c") == 1

    def test_shell_args_absent_uses_profile_defaults(self, tmp_path):
        """When shell_args absent, engine uses script_flag (may be None for bash)."""
        from unittest.mock import patch
        project = _make_shell_project(tmp_path, "bash")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # bash script_flag is None so argv is [bash, script_path, ...argv]
            assert call_args[0] == "bash"
            # No injected flag before the script
            assert call_args[1].endswith("hello.sh")

    def test_shell_args_absent_cmd_injects_slash_c(self, tmp_path):
        """cmd has script_flag=/c, so engine injects it when shell_args absent."""
        from unittest.mock import patch
        project = _make_shell_project(tmp_path, "cmd", "hello.bat")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert call_args[:2] == ["cmd", "/c"]


class TestShellProfileDispatch:
    """Each shell profile produces expected argv."""

    def test_cmd_default_flag(self, tmp_path):
        from unittest.mock import patch
        project = _make_shell_project(tmp_path, "cmd", "hello.bat")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "cmd"
            # No shell_args, no env chain: [cmd, /c, script]
            assert "/c" in call_args

    def test_pwsh_uses_file_flag_for_scripts(self, tmp_path):
        """pwsh plain script invocation uses -File (script_flag)."""
        from unittest.mock import patch
        project = _make_shell_project(tmp_path, "pwsh", "hello.ps1")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "pwsh"
            assert "-File" in call_args

    def test_bash_plain_script_no_flag(self, tmp_path):
        """bash plain script invocation uses no flag (script_flag is None)."""
        from unittest.mock import patch
        project = _make_shell_project(tmp_path, "bash")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # [bash, /path/to/hello.sh] — no -c flag for plain script
            assert call_args[0] == "bash"
            assert "-c" not in call_args
            assert call_args[1].endswith("hello.sh")

    def test_unknown_shell_errors(self, tmp_path):
        project = _make_shell_project(tmp_path, "nonexistent-shell")
        runner = make_shell_runner(project)
        result = runner([])
        assert result == 1


class TestShellEnvChaining:
    """shell_env source template + chain separator produce correct command string."""

    def test_bash_env_chain(self, tmp_path):
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "bash",
            runtime_overrides={
                "shell_env": {"script": "/path/to/env.sh", "args": ["ARG1", "ARG2"]},
            },
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # bash uses `source` template and ` && ` separator
            combined = call_args[-1]  # the combined command string
            assert "source /path/to/env.sh ARG1 ARG2" in combined
            assert " && " in combined

    def test_cmd_env_chain_uses_shell_true(self, tmp_path):
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "cmd", "hello.bat",
            runtime_overrides={
                "shell_env": {"script": "env.cmd", "args": ["HOMEBOX"]},
            },
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            # cmd needs_shell_true=True for && chaining
            assert mock_run.call_args.kwargs.get("shell") is True

    def test_pwsh_uses_dot_source_and_semicolon(self, tmp_path):
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "pwsh", "hello.ps1",
            runtime_overrides={
                "shell_env": {"script": "env.ps1", "args": []},
            },
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            combined = mock_run.call_args[0][0][-1]
            assert ". env.ps1" in combined
            assert "; " in combined

    def test_perl_rejected_as_unknown_shell(self, tmp_path):
        """perl is not a shell — runner errors with pointer to script type."""
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "perl", "hello.sh",
            runtime_overrides={
                "shell_env": {"script": "env.sh", "args": []},
            },
        )
        # Capture stderr to verify the helpful error message
        import io
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            runner = make_shell_runner(project)
            result = runner([])
        assert result == 1
        stderr = stderr_buf.getvalue()
        assert "Unknown shell 'perl'" in stderr
        assert "script" in stderr  # points user at the correct runtime type

    def test_shell_env_missing_script_errors(self, tmp_path):
        project = _make_shell_project(
            tmp_path, "bash",
            runtime_overrides={"shell_env": {"args": ["no-script-field"]}},
        )
        runner = make_shell_runner(project)
        result = runner([])
        assert result == 1


class TestShellInteractive:
    """Interactive mode uses interactive_flag; unsupported shells error."""

    def test_interactive_true_uses_interactive_flag_cmd(self, tmp_path):
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "cmd", "hello.bat",
            runtime_overrides={"interactive": True},
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert "/k" in call_args

    def test_interactive_true_pwsh(self, tmp_path):
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "pwsh", "hello.ps1",
            runtime_overrides={"interactive": True},
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert "-NoExit" in call_args

    def test_interactive_sh_rejected(self, tmp_path):
        project = _make_shell_project(
            tmp_path, "sh",
            runtime_overrides={"interactive": True},
        )
        runner = make_shell_runner(project)
        result = runner([])
        assert result == 1  # sh has no interactive_flag

    def test_interactive_exec_calls_execvp(self, tmp_path):
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "bash",
            runtime_overrides={"interactive": "exec"},
        )
        with patch("os.execvp") as mock_exec:
            # execvp normally doesn't return; we need it to raise to exit the runner
            mock_exec.side_effect = SystemExit(0)
            runner = make_shell_runner(project)
            try:
                runner([])
            except SystemExit:
                pass
            mock_exec.assert_called_once()
            # First arg should be bash
            assert mock_exec.call_args[0][0] == "bash"


class TestRunnerRegistryShellResolution:
    def test_shell_type_registered(self):
        assert "shell" in RunnerRegistry.registered_types()

    def test_resolve_shell_project(self, tmp_path):
        project = _make_shell_project(tmp_path, "bash")
        runner = RunnerRegistry.resolve(project)
        assert runner is not None
        assert callable(runner)


# -------------------------------------------------------------
# Real-subprocess integration tests (auto-skipped via conftest)
# -------------------------------------------------------------


@pytest.mark.shell_bash
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Git Bash on Windows can't resolve native Windows tmp_path; "
           "tests run on Linux/macOS CI instead",
)
class TestShellRealBash:
    def test_hello_bash_runs(self, tmp_path):
        project = _make_shell_project(tmp_path, "bash", "hello.sh")
        runner = make_shell_runner(project)
        result = runner(["world", "foo"])
        assert result == 0


@pytest.mark.shell_cmd
class TestShellRealCmd:
    def test_hello_cmd_runs(self, tmp_path):
        project = _make_shell_project(tmp_path, "cmd", "hello.bat")
        runner = make_shell_runner(project)
        result = runner(["world", "foo"])
        assert result == 0


@pytest.mark.shell_pwsh
class TestShellRealPwsh:
    def test_hello_pwsh_runs(self, tmp_path):
        project = _make_shell_project(tmp_path, "pwsh", "hello.ps1")
        runner = make_shell_runner(project)
        result = runner(["world", "foo"])
        assert result == 0


@pytest.mark.shell_bash
@pytest.mark.shell_env
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Git Bash on Windows can't resolve native Windows tmp_path; "
           "tests run on Linux/macOS CI instead",
)
class TestShellRealEnvChain:
    def test_bash_env_chain_propagates(self, tmp_path):
        import shutil as _sh
        _sh.copy(os.path.join(FIXTURE_DIR, "env_setup.sh"), str(tmp_path))
        _sh.copy(os.path.join(FIXTURE_DIR, "check_env.sh"), str(tmp_path))
        project = {
            "name": "env-chain-test",
            "_dir": str(tmp_path),
            "_fqcn": "test:env-chain-test",
            "runtime": {
                "type": "shell",
                "shell": "bash",
                "script_path": "check_env.sh",
                "shell_env": {
                    "script": os.path.join(str(tmp_path), "env_setup.sh"),
                    "args": [],
                },
            },
        }
        # Use subprocess.run capturing stdout to verify env propagated
        from unittest.mock import patch
        captured = {}
        orig_run = subprocess.run

        def capture_run(*args, **kwargs):
            kwargs["capture_output"] = True
            kwargs["text"] = True
            result = orig_run(*args, **kwargs)
            captured["stdout"] = result.stdout
            return result

        with patch("subprocess.run", side_effect=capture_run):
            runner = make_shell_runner(project)
            exit_code = runner([])

        assert exit_code == 0
        assert "ENV_OK" in captured["stdout"]
        assert "marker=setup_ran" in captured["stdout"]
