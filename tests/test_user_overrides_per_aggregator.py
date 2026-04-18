"""Tests for per-aggregator user-override path routing.

Covers:
- set_override_root() redirects load_override() lookups
- DAZZLECMD_OVERRIDES_DIR env var takes precedence over set_override_root
- AggregatorEngine construction wires the override root correctly
- Two engines with different config_dirs have isolated override paths
"""

from __future__ import annotations

import json
import os
import pytest
from pathlib import Path

from dazzlecmd_lib import user_overrides
from dazzlecmd_lib.engine import AggregatorEngine


@pytest.fixture(autouse=True)
def _reset_override_root():
    """Reset the module-level override root between tests."""
    yield
    user_overrides.set_override_root(None)


class TestSetOverrideRoot:
    def test_set_override_root_changes_lookup(self, tmp_path, monkeypatch):
        monkeypatch.delenv(user_overrides.OVERRIDE_ENV_VAR, raising=False)
        user_overrides.set_override_root(tmp_path)
        assert user_overrides.get_override_root() == tmp_path

    def test_set_override_root_none_resets(self, tmp_path, monkeypatch):
        monkeypatch.delenv(user_overrides.OVERRIDE_ENV_VAR, raising=False)
        user_overrides.set_override_root(tmp_path)
        assert user_overrides.get_override_root() == tmp_path
        user_overrides.set_override_root(None)
        # Falls back to default
        assert user_overrides.get_override_root() == Path.home() / ".dazzlecmd" / "overrides"

    def test_env_var_takes_precedence_over_setter(self, tmp_path, monkeypatch):
        setter_path = tmp_path / "from-setter"
        env_path = tmp_path / "from-env"
        monkeypatch.setenv(user_overrides.OVERRIDE_ENV_VAR, str(env_path))
        user_overrides.set_override_root(setter_path)
        assert user_overrides.get_override_root() == Path(str(env_path))

    def test_load_override_uses_setter_path(self, tmp_path, monkeypatch):
        """Full end-to-end: set_override_root → load_override reads from it."""
        monkeypatch.delenv(user_overrides.OVERRIDE_ENV_VAR, raising=False)

        # Create an override file at the expected per-aggregator location
        (tmp_path / "setup").mkdir(parents=True)
        (tmp_path / "setup" / "kit__tool.json").write_text(
            json.dumps({"_schema_version": "1", "command": "echo FROM_SETTER"})
        )

        user_overrides.set_override_root(tmp_path)

        result = user_overrides.load_override("setup", "kit:tool")
        assert result is not None
        assert result["command"] == "echo FROM_SETTER"

    def test_load_override_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv(user_overrides.OVERRIDE_ENV_VAR, raising=False)
        user_overrides.set_override_root(tmp_path)
        assert user_overrides.load_override("setup", "kit:tool") is None


class TestEngineConfiguresOverrideRoot:
    def test_engine_with_config_dir_sets_override_root(self, tmp_path, monkeypatch):
        monkeypatch.delenv(user_overrides.OVERRIDE_ENV_VAR, raising=False)
        engine = AggregatorEngine(
            name="t", command="t", config_dir=str(tmp_path),
        )
        expected = Path(str(tmp_path)) / "overrides"
        actual = user_overrides.get_override_root()
        assert actual == expected

    def test_engine_override_file_loaded_from_config_dir(self, tmp_path, monkeypatch):
        """Engine writes to per-aggregator override dir; load_override reads it."""
        monkeypatch.delenv(user_overrides.OVERRIDE_ENV_VAR, raising=False)

        # Create override at the expected per-aggregator location
        overrides_dir = tmp_path / "overrides" / "setup"
        overrides_dir.mkdir(parents=True)
        (overrides_dir / "kit__tool.json").write_text(
            json.dumps(
                {"_schema_version": "1", "command": "echo FROM_AGGREGATOR"}
            )
        )

        engine = AggregatorEngine(
            name="t", command="t", config_dir=str(tmp_path),
        )
        result = user_overrides.load_override("setup", "kit:tool")
        assert result is not None
        assert result["command"] == "echo FROM_AGGREGATOR"

    def test_two_engines_have_isolated_override_paths(self, tmp_path, monkeypatch):
        """Last-constructed engine's root wins (module-level state)."""
        monkeypatch.delenv(user_overrides.OVERRIDE_ENV_VAR, raising=False)

        a = tmp_path / "a"
        b = tmp_path / "b"

        engine_a = AggregatorEngine(name="a", command="a", config_dir=str(a))
        root_after_a = user_overrides.get_override_root()
        assert root_after_a == Path(str(a)) / "overrides"

        engine_b = AggregatorEngine(name="b", command="b", config_dir=str(b))
        root_after_b = user_overrides.get_override_root()
        assert root_after_b == Path(str(b)) / "overrides"

    def test_env_var_wins_over_engine_config(self, tmp_path, monkeypatch):
        """If DAZZLECMD_OVERRIDES_DIR is set, it overrides engine's config_dir."""
        env_path = tmp_path / "env-forced"
        monkeypatch.setenv(user_overrides.OVERRIDE_ENV_VAR, str(env_path))

        engine = AggregatorEngine(
            name="t", command="t", config_dir=str(tmp_path / "ignored"),
        )
        assert user_overrides.get_override_root() == Path(str(env_path))
