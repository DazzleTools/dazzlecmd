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
    NODE_INTERPRETERS,
    RunnerRegistry,
    SHELL_PROFILES,
    make_binary_runner,
    make_node_runner,
    make_script_runner,
    make_shell_runner,
)


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "shells")
NODE_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "node")


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

    def test_cmd_env_chain_uses_list_argv_not_shell_true(self, tmp_path):
        """Regression for v0.7.18: cmd env-chain dispatch uses list-argv form
        with an explicit /c flag interpreting the combined string. Using
        shell=True would double-wrap in an outer cmd /c, breaking the
        dispatch. Both the inner shell's exec flag AND list-argv invocation
        are required for env-chain to work correctly on Windows cmd."""
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
            # Must NOT use shell=True — we invoke cmd.exe directly with its
            # own /c (or /k) interpreting the combined command string.
            assert mock_run.call_args.kwargs.get("shell") is not True
            # Argv should be list form: [cmd, /c, "CALL env.cmd HOMEBOX && hello.bat"]
            call_args = mock_run.call_args[0][0]
            assert isinstance(call_args, list)
            assert call_args[0] == "cmd"
            assert "/c" in call_args
            # The combined command string should be the final arg
            assert "CALL" in call_args[-1]
            assert "&&" in call_args[-1]

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

    def test_cmd_shell_env_uses_CALL_prefix(self, tmp_path):
        """Regression for v0.7.18 Bug 1: env vars set in env.cmd propagate to
        the tool script only when CALL precedes the env-script invocation.
        Verified via the combined command string in the list-argv invocation."""
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "cmd", "hello.bat",
            runtime_overrides={
                "shell_env": {"script": "env_setup.cmd", "args": []},
            },
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert isinstance(call_args, list)
            # Combined string is the last argv entry: "CALL env_setup.cmd && hello.bat"
            assert "CALL" in call_args[-1]

    def test_cmd_shell_args_plus_shell_env_has_exec_flag(self, tmp_path):
        """Regression for v0.7.18: when both shell_args and shell_env are
        declared, engine must still inject the exec-style flag (/c) between
        shell_args and the combined command. Without it, cmd invocation
        lacks /c and blocks or errors. Example: cmd /E:ON /V:ON /c "CALL env.cmd && tool.bat"."""
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "cmd", "hello.bat",
            runtime_overrides={
                "shell_args": ["/E:ON", "/V:ON"],
                "shell_env": {"script": "env.cmd", "args": []},
            },
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # [cmd, /E:ON, /V:ON, /c, "CALL env.cmd && hello.bat"]
            assert call_args[0] == "cmd"
            assert call_args[1:3] == ["/E:ON", "/V:ON"]
            assert call_args[3] == "/c"
            assert "CALL" in call_args[4]
            assert "&&" in call_args[4]

    def test_cmd_interactive_plus_shell_env_uses_k_flag(self, tmp_path):
        """Interactive-mode with shell_env should use /k (keep-open) instead
        of /c for the exec flag."""
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "cmd", "hello.bat",
            runtime_overrides={
                "shell_args": ["/E:ON", "/V:ON"],
                "shell_env": {"script": "env.cmd", "args": []},
                "interactive": True,
            },
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert "/k" in call_args
            assert "/c" not in call_args

    def test_shell_env_relative_path_resolved_to_tool_dir(self, tmp_path):
        """Regression for v0.7.18 Review item: relative shell_env.script paths
        resolve against tool_dir (consistent with script_path semantics)."""
        from unittest.mock import patch
        # Create env_setup.cmd in tool_dir so the relative-path resolution hits
        (tmp_path / "env_setup.cmd").write_text("@set FROM_ENV=yes\n")
        project = _make_shell_project(
            tmp_path, "cmd", "hello.bat",
            runtime_overrides={
                "shell_env": {"script": "env_setup.cmd", "args": []},
            },
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            combined = mock_run.call_args[0][0]
            combined_str = combined if isinstance(combined, str) else " ".join(combined)
            # The env_script should have been resolved to tool_dir's absolute path
            assert str(tmp_path) in combined_str

    def test_shell_env_absolute_path_unchanged(self, tmp_path):
        """Absolute paths pass through unmodified (don't prepend tool_dir)."""
        from unittest.mock import patch
        abs_path = "/tmp/my_env.sh" if not sys.platform == "win32" else r"C:\tmp\my_env.cmd"
        project = _make_shell_project(
            tmp_path, "cmd" if sys.platform == "win32" else "bash",
            "hello.bat" if sys.platform == "win32" else "hello.sh",
            runtime_overrides={
                "shell_env": {"script": abs_path, "args": []},
            },
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            combined = mock_run.call_args[0][0]
            combined_str = combined if isinstance(combined, str) else " ".join(combined)
            assert abs_path in combined_str

    def test_shell_env_env_var_path_unchanged(self, tmp_path):
        """Env-var-prefixed paths (%USERPROFILE%, $HOME) pass through so the
        shell expands them."""
        from unittest.mock import patch
        project = _make_shell_project(
            tmp_path, "cmd", "hello.bat",
            runtime_overrides={
                "shell_env": {"script": "%USERPROFILE%\\setup.cmd", "args": []},
            },
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_shell_runner(project)
            runner([])
            combined = mock_run.call_args[0][0]
            combined_str = combined if isinstance(combined, str) else " ".join(combined)
            # %USERPROFILE% preserved; not prefixed with tool_dir
            assert "%USERPROFILE%" in combined_str
            assert f"{str(tmp_path)}\\%USERPROFILE%" not in combined_str

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


# ===========================================================================
# Phase 4c.3 — Node runner + script runner interpreter_args
# ===========================================================================


def _make_node_project(tool_dir, script_name=None, **runtime_fields):
    """Build a node-type project dict; optionally copy fixture script into tool_dir."""
    if script_name:
        fixture = os.path.join(NODE_FIXTURE_DIR, script_name)
        if os.path.isfile(fixture):
            import shutil as _sh
            _sh.copy(fixture, str(tool_dir))
    project = {
        "name": "test-node-tool",
        "_dir": str(tool_dir),
        "_fqcn": "test:test-node-tool",
        "runtime": {
            "type": "node",
        },
    }
    if script_name:
        project["runtime"]["script_path"] = script_name
    project["runtime"].update(runtime_fields)
    return project


class TestNodeInterpreterProfiles:
    """NODE_INTERPRETERS table sanity checks."""

    def test_all_expected_interpreters_registered(self):
        expected = {"node", "tsx", "ts-node", "bun", "deno"}
        assert expected == set(NODE_INTERPRETERS.keys())

    def test_profile_has_subcommand_field(self):
        for interp, profile in NODE_INTERPRETERS.items():
            assert "subcommand" in profile, f"{interp} missing subcommand"

    def test_bun_and_deno_use_run_subcommand(self):
        assert NODE_INTERPRETERS["bun"]["subcommand"] == "run"
        assert NODE_INTERPRETERS["deno"]["subcommand"] == "run"

    def test_node_tsx_tsnode_have_no_subcommand(self):
        assert NODE_INTERPRETERS["node"]["subcommand"] is None
        assert NODE_INTERPRETERS["tsx"]["subcommand"] is None
        assert NODE_INTERPRETERS["ts-node"]["subcommand"] is None


class TestNodeScriptDispatch:
    """script_path mode: per-interpreter argv construction."""

    def test_node_default_interpreter(self, tmp_path):
        from unittest.mock import patch
        project = _make_node_project(tmp_path, script_name="hello.js")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner(["a", "b"])
            call_args = mock_run.call_args[0][0]
            # [node, script, a, b] — no subcommand
            assert call_args[0] == "node"
            assert call_args[1].endswith("hello.js")
            assert call_args[-2:] == ["a", "b"]

    def test_node_default_for_js_when_no_interpreter(self, tmp_path):
        from unittest.mock import patch
        project = _make_node_project(tmp_path, script_name="hello.js")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner([])
            assert mock_run.call_args[0][0][0] == "node"

    def test_bun_inserts_run_subcommand(self, tmp_path):
        from unittest.mock import patch
        project = _make_node_project(
            tmp_path, script_name="hello.js", interpreter="bun",
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # [bun, run, script]
            assert call_args[0] == "bun"
            assert call_args[1] == "run"

    def test_deno_inserts_run_subcommand(self, tmp_path):
        from unittest.mock import patch
        project = _make_node_project(
            tmp_path, script_name="hello.js", interpreter="deno",
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "deno"
            assert call_args[1] == "run"

    def test_tsx_no_subcommand(self, tmp_path):
        from unittest.mock import patch
        project = _make_node_project(
            tmp_path, script_name="hello.ts", interpreter="tsx",
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # [tsx, script] — no subcommand
            assert call_args[0] == "tsx"
            assert call_args[1].endswith("hello.ts")

    def test_unknown_interpreter_warns_and_dispatches(self, tmp_path):
        """Unknown interpreter falls through with a stderr warning."""
        from unittest.mock import patch
        project = _make_node_project(
            tmp_path, script_name="hello.js", interpreter="custom-js-runtime",
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "custom-js-runtime"


class TestNodeInterpreterArgs:
    """interpreter_args are placed between interpreter (+subcommand) and script."""

    def test_deno_with_permission_flags(self, tmp_path):
        from unittest.mock import patch
        project = _make_node_project(
            tmp_path, script_name="hello.ts",
            interpreter="deno",
            interpreter_args=["--allow-read", "--allow-net"],
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # [deno, run, --allow-read, --allow-net, script]
            assert call_args[:4] == ["deno", "run", "--allow-read", "--allow-net"]
            assert call_args[4].endswith("hello.ts")

    def test_node_with_memory_flag(self, tmp_path):
        from unittest.mock import patch
        project = _make_node_project(
            tmp_path, script_name="hello.js",
            interpreter="node",
            interpreter_args=["--max-old-space-size=4096"],
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # [node, --max-old-space-size=4096, script] — no subcommand, then flags, then script
            assert call_args[:2] == ["node", "--max-old-space-size=4096"]


class TestNodeTypeScriptRejectsWithoutInterpreter:
    """TypeScript files require an explicit interpreter — fail loudly otherwise."""

    def test_ts_file_without_interpreter_errors(self, tmp_path):
        project = _make_node_project(tmp_path, script_name="hello.ts")
        runner = make_node_runner(project)
        result = runner([])
        assert result == 1

    def test_tsx_file_without_interpreter_errors(self, tmp_path):
        import shutil as _sh
        (tmp_path / "hello.tsx").write_text("")
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            "runtime": {"type": "node", "script_path": "hello.tsx"},
        }
        runner = make_node_runner(project)
        result = runner([])
        assert result == 1

    def test_mts_extension_requires_interpreter(self, tmp_path):
        (tmp_path / "tool.mts").write_text("")
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            "runtime": {"type": "node", "script_path": "tool.mts"},
        }
        runner = make_node_runner(project)
        result = runner([])
        assert result == 1

    def test_ts_check_fires_before_file_existence(self, tmp_path, capsys):
        """Regression for v0.7.18 Bug 2: TS-without-interpreter error must
        fire even when the .ts file doesn't exist yet (tool authoring case)."""
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            # hello.ts deliberately NOT created
            "runtime": {"type": "node", "script_path": "hello.ts"},
        }
        runner = make_node_runner(project)
        result = runner([])
        assert result == 1
        captured = capsys.readouterr()
        # The TS error should fire, NOT the "Script not found" error
        assert "TypeScript file" in captured.err
        assert "requires an explicit interpreter" in captured.err
        assert "Script not found" not in captured.err


class TestNpmScriptDispatch:
    """npm_script mode: dispatches `npm run <script> -- <argv>`."""

    def test_npm_script_argv_shape(self, tmp_path):
        from unittest.mock import patch
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            "runtime": {"type": "node", "npm_script": "build"},
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner(["--watch"])
            call_args = mock_run.call_args[0][0]
            assert call_args == ["npm", "run", "build", "--", "--watch"]

    def test_npm_script_cwd_is_tool_dir(self, tmp_path):
        from unittest.mock import patch
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            "runtime": {"type": "node", "npm_script": "start"},
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner([])
            assert mock_run.call_args.kwargs.get("cwd") == str(tmp_path)


class TestNpxDispatch:
    """npx mode: dispatches `npx <package> <argv>`."""

    def test_npx_argv_shape(self, tmp_path):
        from unittest.mock import patch
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            "runtime": {"type": "node", "npx": "@org/toolpkg"},
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_node_runner(project)
            runner(["--flag", "value"])
            call_args = mock_run.call_args[0][0]
            assert call_args == ["npx", "@org/toolpkg", "--flag", "value"]


class TestNodeMutualExclusion:
    """Exactly one dispatch mode must be declared."""

    def test_none_declared_errors(self, tmp_path):
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            "runtime": {"type": "node"},
        }
        runner = make_node_runner(project)
        result = runner([])
        assert result == 1

    def test_script_path_and_npm_script_errors(self, tmp_path):
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            "runtime": {
                "type": "node",
                "script_path": "tool.js",
                "npm_script": "build",
            },
        }
        runner = make_node_runner(project)
        result = runner([])
        assert result == 1

    def test_npm_script_and_npx_errors(self, tmp_path):
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            "runtime": {
                "type": "node",
                "npm_script": "build",
                "npx": "@org/pkg",
            },
        }
        runner = make_node_runner(project)
        result = runner([])
        assert result == 1

    def test_all_three_declared_errors(self, tmp_path):
        project = {
            "name": "test-node-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-node-tool",
            "runtime": {
                "type": "node",
                "script_path": "tool.js",
                "npm_script": "build",
                "npx": "@org/pkg",
            },
        }
        runner = make_node_runner(project)
        result = runner([])
        assert result == 1


class TestRunnerRegistryNodeResolution:
    def test_node_type_registered(self):
        assert "node" in RunnerRegistry.registered_types()

    def test_resolve_node_project(self, tmp_path):
        project = _make_node_project(tmp_path, script_name="hello.js")
        runner = RunnerRegistry.resolve(project)
        assert runner is not None
        assert callable(runner)


# -------------------------------------------------------------
# Script runner interpreter_args addition (Q7 fold-in)
# -------------------------------------------------------------


class TestScriptRunnerInterpreterArgs:
    """make_script_runner now supports interpreter_args between interp and script."""

    def test_cscript_style_flags(self, tmp_path):
        """JScript via cscript //Nologo //B tool.js"""
        from unittest.mock import patch
        (tmp_path / "tool.js").write_text("")
        project = {
            "name": "test-script-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-script-tool",
            "runtime": {
                "type": "script",
                "interpreter": "cscript",
                "interpreter_args": ["//Nologo", "//B"],
                "script_path": "tool.js",
            },
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_script_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            # [cscript, //Nologo, //B, tool.js]
            assert call_args[:3] == ["cscript", "//Nologo", "//B"]
            assert call_args[3].endswith("tool.js")

    def test_perl_with_taint_mode(self, tmp_path):
        """perl -w -T tool.pl"""
        from unittest.mock import patch
        (tmp_path / "tool.pl").write_text("")
        project = {
            "name": "test-script-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-script-tool",
            "runtime": {
                "type": "script",
                "interpreter": "perl",
                "interpreter_args": ["-w", "-T"],
                "script_path": "tool.pl",
            },
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_script_runner(project)
            runner([])
            call_args = mock_run.call_args[0][0]
            assert call_args[:3] == ["perl", "-w", "-T"]

    def test_no_interpreter_args_preserves_original_behavior(self, tmp_path):
        """When interpreter_args is absent, argv is [interpreter, script, argv]."""
        from unittest.mock import patch
        (tmp_path / "tool.py").write_text("")
        project = {
            "name": "test-script-tool",
            "_dir": str(tmp_path),
            "_fqcn": "test:test-script-tool",
            "runtime": {
                "type": "script",
                "interpreter": "python",
                "script_path": "tool.py",
            },
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            runner = make_script_runner(project)
            runner(["arg1"])
            call_args = mock_run.call_args[0][0]
            # [python, tool.py, arg1]
            assert call_args[0] == "python"
            assert call_args[1].endswith("tool.py")
            assert call_args[2] == "arg1"


# -------------------------------------------------------------
# Real-subprocess integration tests (auto-skipped via conftest)
# -------------------------------------------------------------


@pytest.mark.node
class TestNodeRealSubprocess:
    def test_hello_js_runs(self, tmp_path):
        project = _make_node_project(tmp_path, script_name="hello.js")
        runner = make_node_runner(project)
        result = runner(["world", "foo"])
        assert result == 0


@pytest.mark.bun
class TestBunRealSubprocess:
    def test_bun_runs_js(self, tmp_path):
        project = _make_node_project(
            tmp_path, script_name="hello.js", interpreter="bun",
        )
        runner = make_node_runner(project)
        result = runner(["world"])
        assert result == 0


@pytest.mark.deno
class TestDenoRealSubprocess:
    def test_deno_runs_js_with_permissions(self, tmp_path):
        project = _make_node_project(
            tmp_path, script_name="hello.js",
            interpreter="deno",
            interpreter_args=["--allow-read"],
        )
        runner = make_node_runner(project)
        result = runner(["world"])
        assert result == 0


class TestPythonPackageModeRelativeImports:
    """Regression test for wtf-windows adoption (Phase 2):
    when a tool directory has __init__.py (making it a Python package),
    the runner must put the PARENT of tool_dir on sys.path and import
    as <tool_dir_name>.<script_stem> so relative imports in the script
    resolve correctly.

    Prior to this fix, the runner put tool_dir on sys.path and imported
    the script as a flat module, causing relative imports like
    `from .channels import X` to fail with:
    'attempted relative import with no known parent package'.
    """

    def test_package_mode_resolves_relative_imports(self, tmp_path):
        # Create a package-structured tool:
        #   tools/core/mypkg/__init__.py
        #   tools/core/mypkg/helper.py  -- imported via relative import
        #   tools/core/mypkg/main.py    -- imports .helper and exposes main()
        from dazzlecmd_lib.registry import make_python_runner

        tool_dir = tmp_path / "tools" / "core" / "mypkg"
        tool_dir.mkdir(parents=True)
        (tool_dir / "__init__.py").write_text("")
        (tool_dir / "helper.py").write_text("VALUE = 42\n")
        (tool_dir / "main.py").write_text(
            "from .helper import VALUE\n"
            "def main(argv=None):\n"
            "    print(f'VALUE={VALUE}')\n"
            "    return 0\n"
        )

        project = {
            "name": "mypkg",
            "_dir": str(tool_dir),
            "runtime": {
                "type": "python",
                "entry_point": "main",
                "script_path": "main.py",
            },
        }

        runner = make_python_runner(project)
        import sys as _sys
        sys_path_before = list(_sys.path)
        try:
            exit_code = runner([])
        finally:
            _sys.path[:] = sys_path_before
            # Clear any lingering module cache so subsequent tests see
            # a clean state (this is a package import; leave hygiene)
            for mod_name in list(_sys.modules):
                if mod_name.startswith("mypkg"):
                    _sys.modules.pop(mod_name, None)

        assert exit_code == 0

    def test_flat_module_still_works(self, tmp_path, monkeypatch):
        """Tools without __init__.py continue to use flat-module import
        (the non-package path). Regression guard to ensure the package-
        mode fix didn't break non-package tools."""
        from dazzlecmd_lib.registry import make_python_runner

        tool_dir = tmp_path / "flatmod"
        tool_dir.mkdir()
        (tool_dir / "flatmod.py").write_text(
            "def main(argv=None):\n    return 7\n"
        )

        project = {
            "name": "flatmod",
            "_dir": str(tool_dir),
            "runtime": {
                "type": "python",
                "entry_point": "main",
                "script_path": "flatmod.py",
            },
        }

        runner = make_python_runner(project)
        import sys as _sys
        sys_path_before = list(_sys.path)
        try:
            exit_code = runner([])
        finally:
            _sys.path[:] = sys_path_before
            _sys.modules.pop("flatmod", None)

        assert exit_code == 7
