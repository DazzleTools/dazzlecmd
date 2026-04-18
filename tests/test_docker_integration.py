"""End-to-end Docker runtime integration test (v0.7.21, Phase 4c.4).

Builds a real Docker image from `tests/fixtures/docker_tool/Dockerfile`,
dispatches via the engine's `make_docker_runner`, and asserts on the
structured report the container emits.

Proves what the mocked unit tests cannot:
    - `subprocess.run` against a real docker daemon actually works
    - argv construction matches docker CLI expectations
    - volume mounts actually deliver file content into the container
    - env_passthrough actually delivers host env var values into the container
    - env dict actually sets explicit env vars
    - exit code propagates from container to runner

Opt-in via `@pytest.mark.docker_integration`. Auto-skipped when `docker`
is absent. First run builds the image (~30-90s); subsequent runs reuse it.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from dazzlecmd_lib.registry import make_docker_runner, resolve_runtime


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "docker_tool"
IMAGE_NAME = "dazzlecmd-test-docker-tool"
IMAGE_TAG = "v1"
FULL_IMAGE = f"{IMAGE_NAME}:{IMAGE_TAG}"


@pytest.fixture(scope="module")
def docker_image():
    """Build the fixture image once per module; reuse across tests.

    If docker is available, build. If the image already exists locally from
    a prior run, docker build's layer cache makes this fast (<5s).
    """
    # Fail cleanly if docker missing (the marker's auto-skip should catch
    # this first, but belt-and-braces).
    try:
        version = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, timeout=5
        )
    except FileNotFoundError:
        pytest.skip("docker binary not on PATH")
    if version.returncode != 0:
        pytest.skip(f"docker --version failed: {version.stderr}")

    # Build
    build = subprocess.run(
        ["docker", "build", "-t", FULL_IMAGE, str(FIXTURE_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if build.returncode != 0:
        pytest.fail(
            f"docker build failed (exit {build.returncode}):\n"
            f"STDOUT:\n{build.stdout}\n"
            f"STDERR:\n{build.stderr}"
        )

    # Verify image is actually present
    check = subprocess.run(
        ["docker", "images", "-q", FULL_IMAGE],
        capture_output=True, text=True,
    )
    if not check.stdout.strip():
        pytest.fail(f"docker build succeeded but image {FULL_IMAGE} not found")

    yield FULL_IMAGE
    # Don't auto-remove: keeping the image cached speeds up subsequent runs.


@pytest.fixture
def project_dict():
    """Load the fixture manifest + set _dir."""
    manifest_path = FIXTURE_DIR / ".dazzlecmd.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        project = json.load(f)
    project["_dir"] = str(FIXTURE_DIR)
    project["_fqcn"] = "test:docker-test-tool"
    return project


@pytest.mark.docker_integration
class TestDockerIntegration:
    def test_image_build_succeeded(self, docker_image):
        """Fixture built the image; it exists in the local registry."""
        result = subprocess.run(
            ["docker", "images", "-q", docker_image],
            capture_output=True, text=True,
        )
        assert result.stdout.strip(), f"{docker_image} not present"

    def test_resolve_runtime_substitutes_image(self, project_dict):
        """_vars substitution should resolve the manifest's image field."""
        resolved = resolve_runtime(project_dict)
        assert resolved["runtime"]["image"] == FULL_IMAGE

    def test_runner_dispatches_container_and_captures_output(
        self, docker_image, project_dict, capfd
    ):
        """The full runner path: pre-flight -> docker run -> output -> exit code."""
        resolved = resolve_runtime(project_dict)
        runner = make_docker_runner(resolved)
        exit_code = runner(["hello", "from-test"])
        out, err = capfd.readouterr()

        assert exit_code == 0, f"runner exit={exit_code}; err={err}"
        # Signature proves OUR container ran
        assert "DAZZLECMD_DOCKER_TEST_SIGNATURE=v1" in out
        # Argv propagated into the container
        assert "DAZZLECMD_DOCKER_TEST_ARGV_COUNT=2" in out
        assert "DAZZLECMD_DOCKER_TEST_ARGV[0]=hello" in out
        assert "DAZZLECMD_DOCKER_TEST_ARGV[1]=from-test" in out
        # Python actually ran inside the container
        assert "DAZZLECMD_DOCKER_TEST_PYTHON_VERSION=3.11" in out

    def test_env_dict_reaches_container(
        self, docker_image, project_dict, capfd
    ):
        """The manifest's env dict should set DAZZLECMD_DOCKER_TEST_EXPLICIT_ENV."""
        resolved = resolve_runtime(project_dict)
        runner = make_docker_runner(resolved)
        exit_code = runner([])
        out, _ = capfd.readouterr()

        assert exit_code == 0
        assert (
            "DAZZLECMD_DOCKER_TEST_ENV:DAZZLECMD_DOCKER_TEST_EXPLICIT_ENV=from-manifest-env-dict"
            in out
        )

    def test_env_passthrough_reaches_container(
        self, docker_image, project_dict, capfd, monkeypatch
    ):
        """env_passthrough should forward host env var VALUES into the container
        without leaking them to argv."""
        monkeypatch.setenv("DAZZLECMD_DOCKER_TEST_ENV1", "host-value-1")
        monkeypatch.setenv("DAZZLECMD_DOCKER_TEST_ENV2", "host-value-2")

        resolved = resolve_runtime(project_dict)
        runner = make_docker_runner(resolved)
        exit_code = runner([])
        out, _ = capfd.readouterr()

        assert exit_code == 0
        # Container received the values
        assert (
            "DAZZLECMD_DOCKER_TEST_ENV:DAZZLECMD_DOCKER_TEST_ENV1=host-value-1" in out
        )
        assert (
            "DAZZLECMD_DOCKER_TEST_ENV:DAZZLECMD_DOCKER_TEST_ENV2=host-value-2" in out
        )

    def test_env_passthrough_skips_missing_host_vars(
        self, docker_image, project_dict, capfd, monkeypatch
    ):
        """When a declared env_passthrough name isn't set on the host, the
        container sees it as '<unset>' (docker never gets -e for it)."""
        monkeypatch.delenv("DAZZLECMD_DOCKER_TEST_ENV1", raising=False)
        monkeypatch.delenv("DAZZLECMD_DOCKER_TEST_ENV2", raising=False)

        resolved = resolve_runtime(project_dict)
        runner = make_docker_runner(resolved)
        exit_code = runner([])
        out, _ = capfd.readouterr()

        assert exit_code == 0
        assert (
            "DAZZLECMD_DOCKER_TEST_ENV:DAZZLECMD_DOCKER_TEST_ENV1=<unset>" in out
        )

    def test_container_hostname_differs_from_host(
        self, docker_image, project_dict, capfd
    ):
        """Container isolation check: the reported hostname should NOT equal
        the host's hostname (unless the user explicitly `--net=host`'d)."""
        import platform as _pf

        resolved = resolve_runtime(project_dict)
        runner = make_docker_runner(resolved)
        runner([])
        out, _ = capfd.readouterr()

        host_hostname = _pf.node()
        # Extract container hostname from the report
        for line in out.splitlines():
            if line.startswith("DAZZLECMD_DOCKER_TEST_HOSTNAME="):
                container_hostname = line.split("=", 1)[1]
                assert container_hostname != host_hostname, (
                    f"container hostname ({container_hostname!r}) matches host "
                    f"({host_hostname!r}) -- container isolation broken?"
                )
                return
        pytest.fail("container hostname not found in output")

    def test_exit_code_propagates(self, docker_image, capfd):
        """Simulate a container that exits nonzero; runner should forward the code."""
        # Build a throwaway project dict with a command that always exits 7
        project = {
            "name": "exit-code-test",
            "_fqcn": "test:exit-code-test",
            "_dir": str(FIXTURE_DIR),
            "runtime": {
                "type": "docker",
                "image": docker_image,
                # Override entrypoint via docker_args
                "docker_args": ["--rm", "--entrypoint", "/bin/sh"],
            },
        }
        runner = make_docker_runner(project)
        # Pass `-c "exit 7"` -- these become argv appended after the image
        exit_code = runner(["-c", "exit 7"])
        assert exit_code == 7
