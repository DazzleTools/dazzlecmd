"""Pytest configuration: auto-skip tests for shells not available on this runner.

Adds a collection hook that inspects each test's markers and skips if the
shell it requires isn't in PATH. Keeps CI green on runners that don't have
every shell installed (e.g., cmd on Linux, zsh on Windows).
"""

import shutil
import sys

import pytest


# Mapping: marker name -> predicate returning True if the shell IS NOT available
_SKIP_CONDITIONS = {
    "shell_cmd": lambda: sys.platform != "win32",
    "shell_bash": lambda: shutil.which("bash") is None,
    "shell_pwsh": lambda: shutil.which("pwsh") is None,
    "shell_zsh": lambda: shutil.which("zsh") is None,
    "shell_csh": lambda: shutil.which("csh") is None and shutil.which("tcsh") is None,
    "node": lambda: shutil.which("node") is None,
    "bun": lambda: shutil.which("bun") is None,
    "deno": lambda: shutil.which("deno") is None,
    "tsx": lambda: shutil.which("tsx") is None,
    "ts_node": lambda: shutil.which("ts-node") is None,
    "npm": lambda: shutil.which("npm") is None,
    "npx": lambda: shutil.which("npx") is None,
    "docker_integration": lambda: shutil.which("docker") is None,
}


@pytest.fixture(autouse=True)
def _reset_runner_registry():
    """Restore RunnerRegistry built-ins after every test (Phase 4c.6).

    Tests that register extension runtime types, override factories, or
    clear the registry should see a clean built-in-only registry on every
    test. Without this fixture, test pollution makes registry-dependent
    tests order-sensitive and occasionally flaky.

    Imports are deferred so conftest.py is importable without forcing
    registry construction on pytest's collection pass. The reset is a
    no-op in the common case where the test did not mutate the registry.
    """
    yield
    try:
        from dazzlecmd_lib.registry import RunnerRegistry
        RunnerRegistry.reset()
    except ImportError:
        # dazzlecmd-lib not installed; nothing to reset.
        pass


@pytest.fixture(autouse=True)
def _strip_git_hook_env(monkeypatch):
    """Strip repo-location GIT_* vars so the suite is immune to git hooks.

    git EXPORTS GIT_DIR (and friends) to hook subprocesses. When this suite
    runs under a hook (the repo's pre-push hook runs pytest), every git
    subprocess in the sandboxed tests would otherwise inherit them and
    silently operate against the HOOK'S repository -- `rev-parse
    --show-toplevel` reports the cwd as toplevel (work tree defaults to cwd
    when GIT_DIR is set), defeating the own-toplevel guards. Production code
    sanitizes its own git calls (`dazzlecmd_lib.mode.sanitized_git_env`);
    this fixture protects test-helper git calls and any future unsanitized
    site from flapping the suite. Found 2026-06-11: a blocked `git push`
    failed 4 tests that pass everywhere else.
    """
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE",
                "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR",
                "GIT_PREFIX", "GIT_INTERNAL_SUPER_PREFIX",
                "GIT_SHALLOW_FILE", "GIT_GRAFT_FILE", "GIT_NAMESPACE",
                "GIT_QUARANTINE_PATH"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _isolate_user_config(monkeypatch, tmp_path_factory):
    """Point ``DAZZLECMD_CONFIG`` at a nonexistent path for every test.

    Tests that build ``AggregatorEngine(is_root=True)`` without setting
    ``DAZZLECMD_CONFIG`` themselves would otherwise read the developer's
    real ``~/.dazzlecmd/config.json``. Its ``active_kits`` /
    ``disabled_kits`` state varies by machine and by whatever ``dz`` /
    ``wtf`` commands were run recently -- which made config-sensitive
    tests (e.g. the ``render_tree`` virtual-kit branches, which filter to
    active kits) pass or fail depending on ambient state. Pointing at a
    nonexistent path forces the engine onto its built-in defaults.

    Tests that need a real config set ``DAZZLECMD_CONFIG`` themselves;
    their ``monkeypatch.setenv`` runs after this fixture and wins.
    """
    nonexistent = tmp_path_factory.mktemp("dzcfg") / "nonexistent-config.json"
    monkeypatch.setenv("DAZZLECMD_CONFIG", str(nonexistent))


@pytest.fixture(autouse=True)
def _reset_user_override_root():
    """Reset per-aggregator user-override root after every test.

    ``AggregatorEngine.__init__`` calls ``user_overrides.set_override_root()``
    to route overrides through each engine's config_dir. Without this
    reset, an engine constructed in one test leaves the module-level
    override root pointing at a tmp_path that's gone in subsequent tests,
    causing order-dependent failures in tests that assume the default
    root.
    """
    yield
    try:
        from dazzlecmd_lib import user_overrides
        user_overrides.set_override_root(None)
    except ImportError:
        pass


@pytest.fixture
def assert_no_shim_access():
    """Pass-through helper (kept for back-compat with tests that wrap a call in it).

    The Phase-1 migration ratchet this fixture once enforced is now obsolete: the
    dict shim was DELETED in the 0.8.0 lib bump (entities expose typed attributes
    + ``extra_get``/``extra_set`` for the untyped remainder), so there is no shim
    to detect. The helper simply runs the callable.
    """
    def _run(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    return _run


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests whose shell marker is unavailable on this runner."""
    for item in items:
        for marker_name, is_unavailable in _SKIP_CONDITIONS.items():
            if marker_name in item.keywords and is_unavailable():
                item.add_marker(
                    pytest.mark.skip(
                        reason=f"requires {marker_name.replace('shell_', '')} on PATH"
                    )
                )
