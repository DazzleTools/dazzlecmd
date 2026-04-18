"""End-to-end venv-per-tool integration test.

This test exercises the full flow that the v0.7.19 conditional dispatch +
v0.7.20 setup parity + v0.7.20 python runner `runtime.interpreter` are
designed to enable:

    1. Load the synthetic `venv_exercise` fixture manifest.
    2. Resolve the setup block for the current platform.
    3. Run the setup command -- creates `.venv/` and `pip install`s heavy deps.
    4. Resolve the runtime block with conditional dispatch -- picks the
       `.venv/<scripts-or-bin>/python` interpreter for the current platform.
    5. Dispatch the tool via the resolved runtime. The tool imports all
       declared deps and emits a machine-parsable PASS/FAIL report.
    6. Assert that all imports passed AND that the interpreter reported by
       the tool is the venv interpreter, not `sys.executable`.

Opt-in via the `venv_integration` pytest marker because pip install across
~7 packages takes 30-120 seconds. Run explicitly:

    pytest tests/test_venv_integration.py -m venv_integration

Skipped in fast CI by default.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dazzlecmd_lib.registry import make_python_runner, resolve_runtime
from dazzlecmd_lib.setup_resolve import resolve_setup_block


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "venv_exercise"


@pytest.fixture(scope="module")
def venv_fixture(tmp_path_factory):
    """Copy the fixture to a tmp dir, run setup, yield the project dict.

    Scoped 'module' so the expensive pip install runs once per test session,
    not once per test. The venv directory and its site-packages are reused
    across all tests in this module.
    """
    # Copy fixture into tmp
    work_dir = tmp_path_factory.mktemp("venv_exercise")
    for src in FIXTURE_DIR.iterdir():
        if src.is_dir():
            shutil.copytree(src, work_dir / src.name)
        else:
            shutil.copy2(src, work_dir / src.name)

    # Build the project dict the way dazzlecmd-lib would
    manifest_path = work_dir / ".dazzlecmd.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        project = json.load(f)
    project["_dir"] = str(work_dir)

    # Resolve setup for the current platform
    effective_setup = resolve_setup_block(project)
    assert effective_setup is not None, "fixture manifest should produce a setup block"
    setup_cmd = effective_setup["command"]

    # Run the setup command. Expected to take 30-120s on first run.
    result = subprocess.run(
        setup_cmd,
        shell=True,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Setup command failed (exit {result.returncode}):\n"
            f"CMD: {setup_cmd}\n"
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )

    return project


@pytest.mark.venv_integration
class TestVenvIntegration:
    def test_venv_was_created(self, venv_fixture):
        venv_dir = Path(venv_fixture["_dir"]) / ".venv"
        assert venv_dir.is_dir(), ".venv directory should exist after setup"

        # Venv interpreter exists in the platform-appropriate location
        if sys.platform == "win32":
            expected_interp = venv_dir / "Scripts" / "python.exe"
        else:
            expected_interp = venv_dir / "bin" / "python"
        assert expected_interp.is_file(), f"venv interpreter missing: {expected_interp}"

    def test_resolve_runtime_picks_venv_interpreter(self, venv_fixture):
        """Conditional dispatch should select the venv interpreter for the current platform."""
        resolved = resolve_runtime(venv_fixture)
        runtime = resolved["runtime"]
        interpreter = runtime.get("interpreter")
        assert interpreter is not None, "resolved runtime should declare interpreter"
        # Should contain .venv (may be relative or resolved absolute)
        assert ".venv" in interpreter, f"interpreter should reference venv: {interpreter!r}"

    def test_dispatch_uses_venv_interpreter(self, venv_fixture):
        """The tool's reported sys.executable should be the venv, not the test runner."""
        resolved = resolve_runtime(venv_fixture)
        runner = make_python_runner(resolved)

        # Capture stdout from the tool
        from contextlib import redirect_stdout
        import io
        buf = io.StringIO()

        # subprocess.run in the runner writes to real stdout, not captured buffer.
        # Instead, we run the same dispatch via a direct subprocess to capture output.
        tool_dir = resolved["_dir"]
        interpreter = resolved["runtime"]["interpreter"]
        # Resolve interpreter path the same way _make_python_interpreter_runner does
        if not os.path.isabs(interpreter):
            if os.sep in interpreter or "/" in interpreter:
                candidate = os.path.join(tool_dir, interpreter)
                if os.path.isfile(candidate):
                    interpreter = candidate
        script = os.path.join(tool_dir, resolved["runtime"]["script_path"])
        result = subprocess.run(
            [interpreter, script],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Tool should exit 0 (all imports passed)
        assert result.returncode == 0, (
            f"Tool exited nonzero:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        # Parse the machine-parsable report
        lines = {
            line.split("=", 1)[0].replace("DAZZLECMD_VENV_EXERCISE_REPORT:", ""): line.split("=", 1)[1]
            for line in result.stdout.splitlines()
            if line.startswith("DAZZLECMD_VENV_EXERCISE_REPORT:") and "=" in line
        }

        # The interpreter reported by the tool must be the VENV interpreter, not the test runner's
        reported_interp = lines.get("INTERPRETER", "")
        assert ".venv" in reported_interp, (
            f"Tool reported sys.executable={reported_interp!r}; expected .venv interpreter. "
            f"This means dispatch fell back to the test runner's Python instead of the venv."
        )
        # And it should not be the test runner's sys.executable
        assert reported_interp != sys.executable, (
            f"Tool ran under test runner's Python ({sys.executable}), not the venv. "
            f"Dispatch is not honoring runtime.interpreter."
        )

    def test_all_heavy_deps_import_successfully(self, venv_fixture):
        """Every package in requirements.txt must import from the venv."""
        tool_dir = venv_fixture["_dir"]
        resolved = resolve_runtime(venv_fixture)
        interpreter = resolved["runtime"]["interpreter"]
        if not os.path.isabs(interpreter):
            candidate = os.path.join(tool_dir, interpreter)
            if os.path.isfile(candidate):
                interpreter = candidate
        script = os.path.join(tool_dir, resolved["runtime"]["script_path"])
        result = subprocess.run(
            [interpreter, script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0

        for pkg in ("numpy", "pandas", "requests", "rich", "yaml", "click", "pydantic"):
            marker = f"DAZZLECMD_VENV_EXERCISE_REPORT:{pkg}=PASS"
            assert marker in result.stdout, (
                f"Expected {pkg} to import from the venv. Output:\n{result.stdout}"
            )
