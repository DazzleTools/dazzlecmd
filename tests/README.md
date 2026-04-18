# Testing Strategy for dazzlecmd

This document describes the project's testing philosophy, what each layer of tests catches (and misses), and how they fit together. Read this before writing new tests or interpreting failures.

## The three-layer strategy at a glance

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 3 — Human checklists  (tests/checklists/*.md)              │
│   What: step-by-step manual scenarios a person runs              │
│   Catches: UX, cross-shell rendering, real interactive flows,    │
│            "technically works but feels broken"                  │
│   When: before any release or phase ship                         │
├──────────────────────────────────────────────────────────────────┤
│ Layer 2 — Integration tests  (@pytest.mark.*_integration)        │
│   What: real subprocesses, real Docker, real shells, real files  │
│   Catches: argv syntax errors, subprocess behavior, env passthru,│
│            file-system quirks, real-world failure modes          │
│   When: before major features ship; opt-in via markers           │
├──────────────────────────────────────────────────────────────────┤
│ Layer 1 — Mock tests  (everything in tests/test_*.py by default) │
│   What: fast unit tests with MagicMock, tmp_path, capsys         │
│   Catches: control flow, argument plumbing, error handling,      │
│            state transitions, regression fencing                 │
│   When: every code change; runs in ~50 seconds                   │
└──────────────────────────────────────────────────────────────────┘
```

**Each layer catches what the others miss. All three are load-bearing.**

---

## Layer 1: Mock tests

### What they are

Fast, deterministic unit tests that use `unittest.mock` (or stdlib equivalents) to stub external dependencies — subprocess invocations, file I/O, network calls, environment reads. They test the **control flow** of our code in isolation.

### What they verify well

| Category | Example from this codebase |
|---|---|
| **Branch coverage** | `tests/test_user_override_integration.py::test_override_empty_returns_original_setup` — fast path when no override file exists |
| **Argument plumbing** | `tests/test_docker_runner.py::test_make_docker_runner_builds_argv` — verifies `docker run` argv construction |
| **Error handling** | `tests/test_cli_setup.py::test_setup_malformed_override_json_clean_error` — `json.JSONDecodeError` → exit 1 + no traceback |
| **State transitions** | `tests/test_registry.py` — factory registration, dispatch resolution, reset behavior |
| **Edge cases you thought of** | Empty lists, missing fields, malformed input — most of the 687 tests |

### Operational benefits

- **Fast**: 687 tests in ~50 seconds. Every save triggers a full green/red signal within a minute.
- **Deterministic**: no timing, no network, no platform variance. Same result every run.
- **CI-friendly**: runs on any OS, any Python ≥3.10. No Docker, no external services, no network.
- **Cheap refactor confidence**: change an internal API, re-run mocks, see what broke.
- **Regression fence**: once a bug is caught and a mock test is written, it can never silently regress.

### What they DON'T catch

1. **Real subprocess behavior**: mocked `subprocess.run` doesn't have real stdout buffering, signal handling, or environment passthrough.
2. **Real file-system quirks**: metadata preservation, symlink following, codepage encoding, atomic writes — invisible to `mock_open()`.
3. **Argv syntax validity**: mock verifies the list structure; real subprocess verifies whether the target accepts the arguments.
4. **Cross-layer integration bugs**: mock tests verify each layer independently and can miss bugs that only manifest when data flows through multiple layers.
5. **UX / readability**: mock tests assert strings; they don't assert whether a human finds the output readable, aligned, or helpful.

### Idioms used in this codebase

```python
# Env-var isolation (used everywhere — never pollute the real environment)
def test_something(tmp_path, monkeypatch):
    monkeypatch.setenv("DAZZLECMD_CONFIG_DIR", str(tmp_path))
    # ... test body ...

# Stdout/stderr capture
def test_output_format(capsys):
    _cmd_list(args, engine)
    out = capsys.readouterr().out
    assert "Name" in out

# Subprocess mocking
from unittest.mock import patch, MagicMock
with patch("subprocess.run") as mock_run:
    mock_run.return_value = MagicMock(returncode=0, stdout=b"...")
    result = runner(argv)

# Engine / project fixtures (common pattern)
def _fake_engine(projects):
    engine = MagicMock()
    engine.all_projects = projects
    engine.projects = projects
    return engine
```

### Running

```bash
# All mocks (default)
pytest

# Faster, quieter
pytest -q

# Specific module
pytest tests/test_user_override_integration.py -v

# One test
pytest tests/test_cli_setup.py::TestMalformedOverrideCleanError -v
```

---

## Layer 2: Integration tests

### What they are

Tests that exercise real systems — actual subprocesses, actual Docker containers, actual shells — at a slower tempo. Opt-in via `@pytest.mark.*_integration` markers so CI can skip them when the required environment isn't present.

### Current integration test categories

| Marker | What it exercises | Gated by |
|---|---|---|
| `docker_integration` | Real `docker build` + `docker run`; verifies env passthrough, inner_runtime dispatch, container isolation | `shutil.which("docker")` |
| `venv_integration` | Creates a real venv with `python -m venv`, installs packages, runs tools under the venv interpreter | Needs network + Python + ~2min |
| `shell_cmd` | Real Windows `cmd.exe` subprocess | `sys.platform == "win32"` |
| `shell_bash` | Real bash subprocess | `shutil.which("bash")` |
| `shell_pwsh` | Real PowerShell Core | `shutil.which("pwsh")` |
| `shell_zsh` | Real zsh | `shutil.which("zsh")` |
| `shell_csh` | Real csh/tcsh | `shutil.which("csh")` or `tcsh` |
| `node`, `npm`, `npx`, `bun`, `deno`, `tsx`, `ts_node` | Real JS interpreter/runner | each tool in PATH |
| `shell_env` | Shell environment chain (source + script) | varies |
| `shell_interactive` | Interactive mode (`cmd /k`, pwsh without `-NoProfile`) | may need TTY |

### What they catch that mocks don't

From this project's history:

- **v0.7.21 BUG-1** (stdout flush ordering): `dz setup` header printed AFTER subprocess output. No mock test caught this because mocked subprocess.run has no real stdout interleaving. Integration test + tester-agent sweep caught it.
- **Docker volume syntax on different hosts**: Mock tests verify argv list; integration tests confirm Docker Desktop vs WSL2 path handling (`/c/...` vs `C:\...`).
- **Env passthrough value preservation**: mock tests can't verify that a value actually arrives inside a subprocess's environment.
- **Exit code propagation from containers**: mock tests can assert we propagate what we get; integration tests verify we get what docker actually sent.

### Auto-skip mechanism

`tests/conftest.py` inspects each test's markers and skips it if the required tool isn't available:

```python
_SKIP_CONDITIONS = {
    "shell_cmd": lambda: sys.platform != "win32",
    "docker_integration": lambda: shutil.which("docker") is None,
    "node": lambda: shutil.which("node") is None,
    # ... etc
}
```

This keeps CI green on runners that don't have every shell/tool installed. Tests marked `shell_cmd` on a Linux runner skip silently rather than erroring.

### Running

```bash
# Run only docker integration tests
pytest -m docker_integration -v

# Run everything including integration (on a full-featured dev box)
pytest -m ""  # or just `pytest` — markers gate skipping, not inclusion

# Run everything EXCEPT docker integration (e.g., on a machine without docker)
pytest -m "not docker_integration"

# See which markers are registered
pytest --markers
```

### Writing a new integration test

```python
import pytest
import subprocess
import shutil

@pytest.mark.docker_integration
def test_real_docker_invocation():
    """Exercise make_docker_runner with a real Docker build + run."""
    # conftest auto-skips if docker not in PATH
    # build the fixture image if not already built
    fixture_dir = Path(__file__).parent / "fixtures" / "docker_tool"
    subprocess.run(["docker", "build", "-t", "test-img", str(fixture_dir)], check=True)
    # ... rest of test
```

---

## Layer 3: Human checklists

### What they are

Step-by-step manual test scripts in `tests/checklists/` that a person executes before a release or phase ship. They catch what automated tests systematically miss: UX, cross-shell rendering, real interactive flows, and "technically works but feels broken."

### Why they exist as a discrete layer

A command can be functionally correct (all mocks pass, all integration tests pass) but confusing to invoke, clunky to read, or solve the wrong problem entirely. Only a human running the checklist notices when:

- A table's columns are cramped in an 80-col terminal
- Error messages use jargon a new user wouldn't recognize
- A command's verb/argument order feels backwards
- Help text is technically accurate but not actually useful
- The command is correct but slow in a way tests don't expose

### File naming convention

```
tests/checklists/vX.Y.Z__<Type>__<slug>.md
```

Examples:
```
v0.7.22__Feature__user-override-integration.md
v0.7.21__Phase4c-4__docker-runtime.md
v0.7.11__Phase3__kit-management-and-config-write.md
```

Version-first = sortable project history. Type is one of `PhaseN`, `Feature`, `Tool`, `Refactor`, `Epic`.

### What goes in a checklist

1. **Target version + commit + companion automated test count**
2. **Planning lineage** (public docs + project-private references)
3. **Prerequisites** with state isolation (env vars, backups)
4. **High-Value Verification section** (~5-min smoke tests of the 4–6 most important user-facing behaviors)
5. **Detailed sections** with step-by-step checkboxes, expected output, file-state checks
6. **"What the automated tests DO cover" table** (quantitative — don't re-test what's verified)
7. **"What the automated tests DON'T cover"** (the reason this checklist exists)
8. **Cleanup section** (restore any backed-up state)

See the `test-checklist` skill for full template and conventions. See any `tests/checklists/v0.7.*.md` file for real examples.

### Cross-shell discipline

Every command in a checklist that touches env vars, file operations, or redirection MUST appear in **cmd.exe**, **PowerShell**, AND **POSIX** forms. Common pitfalls:

| POSIX form (BROKEN on cmd.exe) | Why |
|---|---|
| `export VAR=value` | `export` is bash-only |
| `$VAR` | cmd.exe uses `%VAR%`; PowerShell uses `$env:VAR` |
| `rm -f file` | No `rm` on cmd.exe; use `del` or `Remove-Item` |
| `cat file` | No `cat` on cmd.exe; use `type` or `Get-Content` |
| `command \| grep x` | No `grep`; use `findstr` (cmd) or `Select-String` (pwsh) |
| `/tmp/path` | No `/tmp` on Windows; use `%TEMP%` or `$env:TEMP` |

---

## Test infrastructure patterns

### conftest.py autouse fixtures

**Registry reset** (Phase 4c.6): tests that modify `RunnerRegistry` see a clean built-in-only registry on every test. Prevents order-dependent flakes.

```python
@pytest.fixture(autouse=True)
def _reset_runner_registry():
    yield
    from dazzlecmd_lib.registry import RunnerRegistry
    RunnerRegistry.reset()
```

**Shell / tool auto-skip**: described in Layer 2 above.

### Environment isolation

NEVER write to the user's real config during tests. Always use:

```python
# Pattern 1: monkeypatch env var
def test_config_behavior(tmp_path, monkeypatch):
    monkeypatch.setenv("DAZZLECMD_CONFIG_DIR", str(tmp_path))
    # test writes/reads config under tmp_path, auto-cleaned by pytest

# Pattern 2: explicit config_dir argument (when available)
engine = AggregatorEngine(command="test", config_dir=tmp_path, ...)
```

Key env vars for isolation:
- `DAZZLECMD_CONFIG_DIR` — main config location
- `DAZZLECMD_OVERRIDES_DIR` — user override location (v0.7.22+)

### Fixtures directory layout

```
tests/fixtures/
├── docker_tool/          — Dockerfile + app.py + .dazzlecmd.json for docker integration
├── node/                 — sample Node.js tools for node runner tests
├── shells/               — shell script fixtures (bash, pwsh, cmd, zsh variants)
└── venv_exercise/        — sample package for venv integration tests
```

Create a new fixture dir when a test needs "a real thing to work with" (a real manifest, a real script, a real image).

### one-offs and reports

```
tests/one-offs/   — throwaway diagnostic scripts (not run by pytest by default)
tests/reports/    — tester-agent output, checklist run results
```

one-offs graduate to regular tests (`tests/test_*.py`) or utility scripts (`scripts/*.py`) once they prove reusable.

---

## Decision tree: which layer for a new feature?

```
┌─ Does it touch external systems (subprocess, Docker, network, FS metadata)?
│
│  YES → Write mocks for happy path + error paths
│         PLUS an integration test for the real behavior
│
│  NO  → Is it user-facing output (CLI command, error message, help text)?
│
│        YES → Mock tests for content; human checklist for UX
│
│        NO  → Mock tests are probably sufficient
```

### Always include

- **Mock tests** for every new function/class. Cover branches, errors, edge cases.
- **Human checklist entry** if the change is user-visible. Even internal refactors with subtle behavior changes (metadata preservation, dispatch semantics) need a checklist.

### Include if applicable

- **Integration test** if real subprocess / Docker / network / filesystem behavior matters.
- **Fixture** if the integration test needs a reusable artifact (script, image, manifest).

### Usually skip

- Integration tests for pure-Python data structures (just mock tests)
- Human checklists for single-line bug fixes with no user-visible change
- Human checklists for doc-only or CHANGELOG-only commits

---

## Real bugs caught at each layer (project history)

### Caught by mock tests
- All 17 user-override integration bugs during v0.7.22 development (override merging, _vars scope, schema versioning, cross-layer isolation)
- `resolve_runtime` fast-path bypass when override empty (v0.7.22)
- Node runner package-mode vs script-mode dispatch (v0.7.17)
- Binary runner `dev_command` fallback precedence (v0.7.15)

### Caught by integration tests
- Docker env passthrough actually delivering values into containers (v0.7.21)
- Container hostname differs from host (isolation verification) (v0.7.21)
- Exit code 7 propagating from container to runner correctly (v0.7.21)
- Shell profile variations across bash/zsh/csh/pwsh (v0.7.16)

### Caught by tester-agent (human-equivalent) sweeps
- **v0.7.21 BUG-1**: `dz setup` header printed AFTER subprocess output (stdout buffering). No mock caught this; the tester agent noticed the visual ordering.
- **v0.7.21 BUG-2**: `dz info --raw` omitted `_vars` block from output. Mock tests verified the main dispatch fields but missed the `_vars` rendering.
- **v0.7.21 BUG-3**: `dz info` silently passed through unresolved `{{var}}` templates. No mock asserted "output should not contain `{{`".
- **v0.7.21 BUG-4**: `UnresolvedTemplateVariableError` / `TemplateRecursionError` escaped as tracebacks. Mock tests raised the exception; no mock verified "CLI must not show a traceback."
- **v0.7.22 BUG-1**: malformed override JSON → Python traceback. Mock tests verified `json.JSONDecodeError` was raised; no mock verified "CLI wraps it in a clean error message."

**Pattern**: the tester-agent and human checklists consistently catch **the layer that mocks can't assert** — visual ordering, "what shouldn't be in the output," traceback leaks into user-facing messages, and UX smell.

---

## The tester-agent workflow

The project uses an `tester` Claude Code agent (see `~/.claude/agents/tester.md`) as a scouting party for "things I didn't think to test."

**Workflow:**
1. Write the feature + automated tests (mocks + integration as appropriate)
2. Run `/test-checklist` to produce the human checklist
3. Spawn the `tester` agent with the checklist
4. Agent executes each checkable step, reports PASS/FAIL/REVIEW
5. Agent also probes edge cases beyond the checklist
6. Agent's output becomes the pre-commit validation gate

Each phase/feature of this project has a tester report in `tests/reports/` (when preserved) or inline in the release postmortem.

---

## Running tests — quick reference

```bash
# All mocks (fast, default)
pytest

# Quiet, terse
pytest -q

# With markers visible
pytest -v --tb=short

# Only a specific module/class/test
pytest tests/test_registry.py
pytest tests/test_registry.py::TestRunnerRegistry::test_register
pytest -k "override"  # all tests with "override" in name

# See what markers exist
pytest --markers

# Run integration tests
pytest -m docker_integration
pytest -m venv_integration

# Skip integration, run only fast mocks
pytest -m "not docker_integration and not venv_integration"

# Ignore submodules (when wtf submodule collection fails)
pytest tests/ -q --ignore=projects

# Timing: slowest 20 tests
pytest --durations=20
```

---

## Adding a new test — quick recipes

### Mock test for a new CLI meta-command

```python
# tests/test_cli_<feature>.py
from dazzlecmd import cli
from unittest.mock import MagicMock


def _fake_engine(projects):
    engine = MagicMock()
    engine.all_projects = projects
    engine.projects = projects
    return engine


class TestMyNewCommand:
    def test_happy_path(self, capsys):
        engine = _fake_engine([...])
        exit_code = cli._cmd_my_new(args_stub, engine)
        assert exit_code == 0
        assert "expected output" in capsys.readouterr().out

    def test_error_path_shows_clean_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("DAZZLECMD_CONFIG_DIR", str(tmp_path))
        # ... trigger error, assert exit != 0, assert no traceback
```

### Integration test for a real subprocess

```python
# tests/test_<feature>_integration.py
import pytest
import subprocess

@pytest.mark.my_feature_integration  # register marker in pyproject.toml first
def test_real_invocation(tmp_path):
    # conftest auto-skips if tool isn't available
    result = subprocess.run([...], capture_output=True, text=True)
    assert result.returncode == 0
    assert "expected marker" in result.stdout
```

### Human checklist

Invoke the `test-checklist` skill:
```
/test-checklist Feature: my new feature, phase X.Y, ships with vA.B.C
```

The skill produces `tests/checklists/vA.B.C__<Type>__<slug>.md` with the template filled in.

---

## Meta-principle

**Mock tests prove the code does what I thought it should do. They don't prove I thought of the right thing.**

Every "we should have caught that" bug in this project's history is an example of this limit: mocks verify what you assert; they don't assert what you forgot. That's why integration tests catch failures mocks can't see, and human checklists catch failures integration tests can't express.

All three layers are load-bearing. Write at least the two that apply to your change.
