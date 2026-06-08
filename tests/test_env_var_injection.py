"""Phase 4e Commit 4: verify DZ_CANONICAL_FQCN and DZ_INVOKED_FQCN env
vars are set during tool dispatch.

Tools writing persistent state (caches, logs, checkpoints) MUST key on
DZ_CANONICAL_FQCN so that alias-invocation and canonical-invocation
don't produce divergent state. These tests verify the dispatcher
injects the vars before invoking the tool and restores them after.
"""

import os

import pytest

from dazzlecmd_lib.engine import AggregatorEngine
from dazzlecmd_lib.testing import make_tool


def _proj(fqcn, short, kit, **extra):
    return make_tool(**{
        "_fqcn": fqcn,
        "_short_name": short,
        "_kit_import_name": kit,
        "name": short,
        "namespace": kit,
        **extra,
    })


class TestEnvVarInjection:
    """DZ_CANONICAL_FQCN and DZ_INVOKED_FQCN are set before dispatch,
    visible to the tool, and restored after."""

    def _engine_with_capture(self, projects, captured):
        """Build an engine with a tool_dispatcher that captures env vars
        at dispatch time into the ``captured`` dict."""
        engine = AggregatorEngine(is_root=True)
        engine.projects = list(projects)
        engine._build_fqcn_index()

        def _capturing_dispatcher(project, argv):
            captured["DZ_CANONICAL_FQCN"] = os.environ.get("DZ_CANONICAL_FQCN")
            captured["DZ_INVOKED_FQCN"] = os.environ.get("DZ_INVOKED_FQCN")
            captured["project_fqcn"] = project.get("_fqcn")
            return 0

        engine._dispatch_tool = _capturing_dispatcher
        return engine

    def test_canonical_dispatch_sets_env_vars(self, monkeypatch):
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        projects = [_proj("core:rn", "rn", "core")]
        captured = {}
        engine = self._engine_with_capture(projects, captured)

        rc = engine._run_tool(
            projects[0], [],
            context=engine.fqcn_index.resolve("core:rn")[1],
        )
        assert rc == 0
        assert captured["DZ_CANONICAL_FQCN"] == "core:rn"
        assert captured["DZ_INVOKED_FQCN"] == "core:rn"

    def test_alias_dispatch_records_alias_as_invoked(self, monkeypatch):
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        projects = [_proj("dz:claude-cleanup", "claude-cleanup", "dz")]
        captured = {}
        engine = self._engine_with_capture(projects, captured)
        engine.fqcn_index.insert_alias("claude:cleanup", "dz:claude-cleanup")

        # Resolve via alias
        project, ctx = engine.fqcn_index.resolve("claude:cleanup")
        rc = engine._run_tool(project, [], context=ctx)
        assert rc == 0
        # Canonical is always the real FQCN
        assert captured["DZ_CANONICAL_FQCN"] == "dz:claude-cleanup"
        # Invoked reflects what the user typed
        assert captured["DZ_INVOKED_FQCN"] == "claude:cleanup"

    def test_short_name_dispatch_records_short_as_invoked(self, monkeypatch):
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        projects = [_proj("core:rn", "rn", "core")]
        captured = {}
        engine = self._engine_with_capture(projects, captured)

        project, ctx = engine.fqcn_index.resolve("rn")
        rc = engine._run_tool(project, [], context=ctx)
        assert rc == 0
        assert captured["DZ_CANONICAL_FQCN"] == "core:rn"
        assert captured["DZ_INVOKED_FQCN"] == "rn"

    def test_env_vars_restored_after_dispatch(self, monkeypatch):
        """Parent process environment is restored after dispatch."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        monkeypatch.setenv("DZ_CANONICAL_FQCN", "pre-existing")
        projects = [_proj("core:rn", "rn", "core")]
        captured = {}
        engine = self._engine_with_capture(projects, captured)

        project, ctx = engine.fqcn_index.resolve("rn")
        engine._run_tool(project, [], context=ctx)
        # Tool saw the engine-set value
        assert captured["DZ_CANONICAL_FQCN"] == "core:rn"
        # After dispatch, parent env restored to pre-existing value
        assert os.environ.get("DZ_CANONICAL_FQCN") == "pre-existing"

    def test_env_vars_not_set_without_context(self, monkeypatch):
        """Backward compat: if context is not passed to _run_tool, the
        FQCN vars are not injected (preserves legacy dispatch behavior).
        Branding vars (DZ_APP_NAME/DZ_COMMAND) ARE always injected per
        issue #74 -- tested in TestBrandingEnvVarInjection below."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        # Make sure env is clean
        monkeypatch.delenv("DZ_CANONICAL_FQCN", raising=False)
        monkeypatch.delenv("DZ_INVOKED_FQCN", raising=False)
        projects = [_proj("core:rn", "rn", "core")]
        captured = {}
        engine = self._engine_with_capture(projects, captured)

        engine._run_tool(projects[0], [])  # no context
        # Tool did not see injected FQCN vars
        assert captured["DZ_CANONICAL_FQCN"] is None
        assert captured["DZ_INVOKED_FQCN"] is None


class TestBrandingEnvVarInjection:
    """Issue #74: ``DZ_APP_NAME`` and ``DZ_COMMAND`` reflect the engine's
    identity and are always injected before tool dispatch -- so subprocess
    tool scripts (PowerShell, bash, Python) can read $env:DZ_APP_NAME /
    $env:DZ_COMMAND for branding strings without each aggregator
    hand-rolling its own AGGREGATOR_APP_NAME / AGGREGATOR_CLI_CMD bridge."""

    def _engine_with_capture(self, projects, captured, *, name=None, command=None):
        kwargs = {"is_root": True}
        if name is not None:
            kwargs["name"] = name
        if command is not None:
            kwargs["command"] = command
        engine = AggregatorEngine(**kwargs)
        engine.projects = list(projects)
        engine._build_fqcn_index()

        def _capturing_dispatcher(project, argv):
            captured["DZ_APP_NAME"] = os.environ.get("DZ_APP_NAME")
            captured["DZ_COMMAND"] = os.environ.get("DZ_COMMAND")
            return 0

        engine._dispatch_tool = _capturing_dispatcher
        return engine

    def test_branding_vars_match_engine_identity(self, monkeypatch):
        """Tool sees engine.name in DZ_APP_NAME and engine.command in DZ_COMMAND."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        projects = [_proj("core:rn", "rn", "core")]
        captured = {}
        engine = self._engine_with_capture(
            projects, captured, name="dazzlecmd", command="dz",
        )
        engine._run_tool(projects[0], [])
        assert captured["DZ_APP_NAME"] == "dazzlecmd"
        assert captured["DZ_COMMAND"] == "dz"

    def test_branding_vars_reflect_arbitrary_aggregator_identity(self, monkeypatch):
        """A non-dazzlecmd aggregator's name/command propagate correctly."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        projects = [_proj("core:rn", "rn", "core")]
        captured = {}
        engine = self._engine_with_capture(
            projects, captured, name="wtf-windows", command="wtf",
        )
        engine._run_tool(projects[0], [])
        assert captured["DZ_APP_NAME"] == "wtf-windows"
        assert captured["DZ_COMMAND"] == "wtf"

    def test_branding_vars_injected_without_context(self, monkeypatch):
        """Branding vars are engine-identity (not per-invocation context),
        so they're set even when _run_tool is called without context."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        projects = [_proj("core:rn", "rn", "core")]
        captured = {}
        engine = self._engine_with_capture(
            projects, captured, name="amdead", command="amdead",
        )
        engine._run_tool(projects[0], [])  # no context
        assert captured["DZ_APP_NAME"] == "amdead"
        assert captured["DZ_COMMAND"] == "amdead"

    def test_branding_vars_restored_after_dispatch(self, monkeypatch):
        """Parent process environment is restored after dispatch."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        monkeypatch.setenv("DZ_APP_NAME", "pre-existing-app")
        monkeypatch.setenv("DZ_COMMAND", "pre-existing-cmd")
        projects = [_proj("core:rn", "rn", "core")]
        captured = {}
        engine = self._engine_with_capture(
            projects, captured, name="dazzlecmd", command="dz",
        )
        engine._run_tool(projects[0], [])
        # Tool saw the engine-set values
        assert captured["DZ_APP_NAME"] == "dazzlecmd"
        assert captured["DZ_COMMAND"] == "dz"
        # After dispatch, parent env restored to pre-existing values
        assert os.environ.get("DZ_APP_NAME") == "pre-existing-app"
        assert os.environ.get("DZ_COMMAND") == "pre-existing-cmd"

    def test_branding_vars_popped_when_not_pre_existing(self, monkeypatch):
        """If DZ_APP_NAME/DZ_COMMAND weren't set before dispatch, they
        are NOT left in the environment after."""
        monkeypatch.setenv("DAZZLECMD_CONFIG", "/tmp/nonexistent.json")
        monkeypatch.delenv("DZ_APP_NAME", raising=False)
        monkeypatch.delenv("DZ_COMMAND", raising=False)
        projects = [_proj("core:rn", "rn", "core")]
        captured = {}
        engine = self._engine_with_capture(
            projects, captured, name="dazzlecmd", command="dz",
        )
        engine._run_tool(projects[0], [])
        assert captured["DZ_APP_NAME"] == "dazzlecmd"
        assert captured["DZ_COMMAND"] == "dz"
        # After dispatch, env is back to "not present"
        assert "DZ_APP_NAME" not in os.environ
        assert "DZ_COMMAND" not in os.environ
