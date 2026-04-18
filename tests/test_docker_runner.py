"""Tests for dazzlecmd_lib.registry.make_docker_runner (Phase 4c.4, v0.7.21)."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from dazzlecmd_lib.registry import make_docker_runner, RunnerRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_subprocess_run_preflight_then_runtime(preflight_stdout="abc123\n", preflight_rc=0, runtime_rc=0):
    """Build a side_effect function for subprocess.run returning a pre-flight
    result first, then a run result. Used to mock the image-exists check then
    the actual docker run invocation.
    """
    preflight = MagicMock()
    preflight.returncode = preflight_rc
    preflight.stdout = preflight_stdout
    preflight.stderr = ""

    runtime = MagicMock()
    runtime.returncode = runtime_rc

    calls = [preflight, runtime]

    def side_effect(*args, **kwargs):
        return calls.pop(0) if calls else MagicMock(returncode=0)

    return side_effect


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestDockerRegistration:
    def test_docker_type_registered(self):
        assert "docker" in RunnerRegistry.registered_types()


# ---------------------------------------------------------------------------
# Required field: image
# ---------------------------------------------------------------------------


class TestMissingImage:
    def test_missing_image_returns_error_runner(self, tmp_path, capsys):
        project = {"name": "t", "_dir": str(tmp_path), "runtime": {"type": "docker"}}
        runner = make_docker_runner(project)
        exit_code = runner([])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "image required" in captured.err or "runtime.image required" in captured.err


# ---------------------------------------------------------------------------
# Pre-flight check
# ---------------------------------------------------------------------------


class TestPreflight:
    def test_image_present_proceeds_to_run(self, tmp_path):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"type": "docker", "image": "myimg:latest"},
        }
        runner = make_docker_runner(project)
        with patch("subprocess.run", side_effect=_mock_subprocess_run_preflight_then_runtime()):
            exit_code = runner([])
        assert exit_code == 0

    def test_image_missing_prints_setup_hint(self, tmp_path, capsys):
        project = {
            "name": "t",
            "_fqcn": "mykit:t",
            "_dir": str(tmp_path),
            "runtime": {"type": "docker", "image": "notpresent:latest"},
        }
        runner = make_docker_runner(project)
        with patch("subprocess.run", side_effect=_mock_subprocess_run_preflight_then_runtime(preflight_stdout="")):
            exit_code = runner([])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "not found locally" in captured.err
        assert "dz setup mykit:t" in captured.err

    def test_docker_binary_missing_prints_install_hint(self, tmp_path, capsys):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"type": "docker", "image": "myimg:latest"},
        }
        runner = make_docker_runner(project)
        with patch("subprocess.run", side_effect=FileNotFoundError("docker")):
            exit_code = runner([])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "'docker' command not found" in captured.err or "not found" in captured.err

    def test_daemon_error_surfaced(self, tmp_path, capsys):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"type": "docker", "image": "myimg:latest"},
        }
        preflight = MagicMock()
        preflight.returncode = 1
        preflight.stdout = ""
        preflight.stderr = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
        runner = make_docker_runner(project)
        with patch("subprocess.run", return_value=preflight):
            exit_code = runner([])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Cannot connect" in captured.err


# ---------------------------------------------------------------------------
# argv construction
# ---------------------------------------------------------------------------


class TestArgvBasic:
    def test_minimal_argv(self, tmp_path):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"type": "docker", "image": "myimg:1.0"},
        }
        runner = make_docker_runner(project)
        call_tracker = []

        def side_effect(*args, **kwargs):
            call_tracker.append((args, kwargs))
            result = MagicMock()
            if call_tracker[0][0][0][1] == "images":
                result.returncode = 0
                result.stdout = "abc\n"
                result.stderr = ""
            else:
                result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=side_effect):
            exit_code = runner(["--flag", "value"])
        assert exit_code == 0
        # Second call is the actual docker run
        run_cmd = call_tracker[1][0][0]
        assert run_cmd[:2] == ["docker", "run"]
        assert run_cmd[-3] == "myimg:1.0"
        assert run_cmd[-2:] == ["--flag", "value"]

    def test_docker_args_inserted(self, tmp_path):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "docker",
                "image": "myimg",
                "docker_args": ["--rm", "--network", "host"],
            },
        }
        runner = make_docker_runner(project)
        call_tracker = []
        def side_effect(*args, **kwargs):
            call_tracker.append(args[0])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc\n" if "images" in args[0] else ""
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=side_effect):
            runner([])
        run_cmd = call_tracker[1]
        # ["docker", "run", "--rm", "--network", "host", "myimg"]
        assert "--rm" in run_cmd
        assert "--network" in run_cmd
        assert "host" in run_cmd
        # docker_args appear between "run" and image
        run_idx = run_cmd.index("run")
        img_idx = run_cmd.index("myimg")
        args_segment = run_cmd[run_idx + 1:img_idx]
        assert args_segment == ["--rm", "--network", "host"]


class TestVolumes:
    def test_single_volume_with_mode(self, tmp_path):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "docker",
                "image": "myimg",
                "volumes": [{"host": "/host/path", "container": "/work", "mode": "rw"}],
            },
        }
        runner = make_docker_runner(project)
        call_tracker = []
        def side_effect(*args, **kwargs):
            call_tracker.append(args[0])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc\n" if "images" in args[0] else ""
            result.stderr = ""
            return result
        with patch("subprocess.run", side_effect=side_effect):
            runner([])
        run_cmd = call_tracker[1]
        assert "-v" in run_cmd
        v_idx = run_cmd.index("-v")
        assert run_cmd[v_idx + 1] == "/host/path:/work:rw"

    def test_multiple_volumes(self, tmp_path):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "docker",
                "image": "myimg",
                "volumes": [
                    {"host": "/a", "container": "/x"},
                    {"host": "/b", "container": "/y", "mode": "ro"},
                ],
            },
        }
        runner = make_docker_runner(project)
        call_tracker = []
        def side_effect(*args, **kwargs):
            call_tracker.append(args[0])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc\n" if "images" in args[0] else ""
            result.stderr = ""
            return result
        with patch("subprocess.run", side_effect=side_effect):
            runner([])
        run_cmd = call_tracker[1]
        # Two -v flags
        v_positions = [i for i, x in enumerate(run_cmd) if x == "-v"]
        assert len(v_positions) == 2
        assert run_cmd[v_positions[0] + 1] == "/a:/x"
        assert run_cmd[v_positions[1] + 1] == "/b:/y:ro"

    def test_relative_volume_host_resolved_against_tool_dir(self, tmp_path):
        marker = tmp_path / "data.json"
        marker.write_text("{}")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "docker",
                "image": "myimg",
                "volumes": [{"host": "data.json", "container": "/config.json"}],
            },
        }
        runner = make_docker_runner(project)
        call_tracker = []
        def side_effect(*args, **kwargs):
            call_tracker.append(args[0])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc\n" if "images" in args[0] else ""
            result.stderr = ""
            return result
        with patch("subprocess.run", side_effect=side_effect):
            runner([])
        run_cmd = call_tracker[1]
        v_spec = run_cmd[run_cmd.index("-v") + 1]
        # Resolved against tool_dir (absolute path to data.json in tmp_path)
        assert str(tmp_path) in v_spec
        assert "data.json:/config.json" in v_spec

    def test_malformed_volume_entry_errors(self, tmp_path, capsys):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"type": "docker", "image": "myimg", "volumes": ["/not/a/dict"]},
        }
        runner = make_docker_runner(project)
        with patch("subprocess.run", side_effect=_mock_subprocess_run_preflight_then_runtime()):
            exit_code = runner([])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "volumes" in captured.err

    def test_volume_missing_host_errors(self, tmp_path, capsys):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "docker",
                "image": "myimg",
                "volumes": [{"container": "/app"}],
            },
        }
        runner = make_docker_runner(project)
        with patch("subprocess.run", side_effect=_mock_subprocess_run_preflight_then_runtime()):
            exit_code = runner([])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "'host'" in captured.err or "host" in captured.err


class TestEnv:
    def test_env_dict_stitched(self, tmp_path):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "docker",
                "image": "myimg",
                "env": {"LOG_LEVEL": "info", "TZ": "UTC"},
            },
        }
        runner = make_docker_runner(project)
        call_tracker = []
        def side_effect(*args, **kwargs):
            call_tracker.append(args[0])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc\n" if "images" in args[0] else ""
            result.stderr = ""
            return result
        with patch("subprocess.run", side_effect=side_effect):
            runner([])
        run_cmd = call_tracker[1]
        # Each -e KEY=VALUE pair present
        assert "-e" in run_cmd
        e_positions = [i for i, x in enumerate(run_cmd) if x == "-e"]
        values = [run_cmd[i + 1] for i in e_positions]
        assert "LOG_LEVEL=info" in values
        assert "TZ=UTC" in values


class TestEnvPassthrough:
    def test_passthrough_present_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_TOKEN", "secret-value")
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "docker",
                "image": "myimg",
                "env_passthrough": ["TEST_TOKEN"],
            },
        }
        runner = make_docker_runner(project)
        call_tracker = []
        def side_effect(*args, **kwargs):
            call_tracker.append(args[0])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc\n" if "images" in args[0] else ""
            result.stderr = ""
            return result
        with patch("subprocess.run", side_effect=side_effect):
            runner([])
        run_cmd = call_tracker[1]
        # -e NAME without value (docker picks up host value at run time)
        assert "-e" in run_cmd
        # name passed as a bare flag, NOT "NAME=value" (value never logged)
        assert "TEST_TOKEN" in run_cmd
        # And the value never appears in argv
        assert "secret-value" not in run_cmd

    def test_passthrough_missing_env_var_skipped(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "docker",
                "image": "myimg",
                "env_passthrough": ["MISSING_VAR"],
            },
        }
        runner = make_docker_runner(project)
        call_tracker = []
        def side_effect(*args, **kwargs):
            call_tracker.append(args[0])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc\n" if "images" in args[0] else ""
            result.stderr = ""
            return result
        with patch("subprocess.run", side_effect=side_effect):
            runner([])
        run_cmd = call_tracker[1]
        assert "MISSING_VAR" not in run_cmd


class TestInnerRuntimeIsInformational:
    def test_inner_runtime_does_not_affect_dispatch(self, tmp_path):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "docker",
                "image": "myimg",
                "inner_runtime": {"type": "python", "script_path": "/app/tool.py"},
            },
        }
        runner = make_docker_runner(project)
        call_tracker = []
        def side_effect(*args, **kwargs):
            call_tracker.append(args[0])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc\n" if "images" in args[0] else ""
            result.stderr = ""
            return result
        with patch("subprocess.run", side_effect=side_effect):
            runner(["arg1"])
        run_cmd = call_tracker[1]
        # inner_runtime fields do NOT appear in docker run argv
        assert "/app/tool.py" not in run_cmd
        assert "python" not in run_cmd[-3:]  # image is myimg; inner_runtime.type ignored
        # Just: docker run ... myimg arg1
        assert run_cmd[-2] == "myimg"
        assert run_cmd[-1] == "arg1"


class TestExitCodePropagation:
    def test_nonzero_subprocess_exit_returned(self, tmp_path):
        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "runtime": {"type": "docker", "image": "myimg"},
        }
        runner = make_docker_runner(project)
        with patch(
            "subprocess.run",
            side_effect=_mock_subprocess_run_preflight_then_runtime(runtime_rc=42),
        ):
            exit_code = runner([])
        assert exit_code == 42


class TestVarsSubstitution:
    def test_image_field_substituted_via_resolve_runtime(self, tmp_path):
        """When _vars is declared, image substitution happens via resolve_runtime
        before the runner sees the project. Verify by running through the full
        pipeline."""
        from dazzlecmd_lib.registry import resolve_runtime

        project = {
            "name": "t",
            "_dir": str(tmp_path),
            "_vars": {"org": "myorg", "tag": "1.0"},
            "runtime": {
                "type": "docker",
                "image": "{{org}}/mytool:{{tag}}",
            },
        }
        resolved = resolve_runtime(project)
        assert resolved["runtime"]["image"] == "myorg/mytool:1.0"
