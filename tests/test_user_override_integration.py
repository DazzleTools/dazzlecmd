"""Integration tests for user-override loading in setup + runtime resolvers (v0.7.22, Option B)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dazzlecmd_lib.setup_resolve import resolve_setup_block
from dazzlecmd_lib.registry import resolve_runtime
from dazzlecmd_lib.platform_detect import PlatformInfo
from dazzlecmd_lib.schema_version import UnsupportedSchemaVersionError


@pytest.fixture
def linux_debian():
    return PlatformInfo(
        os="linux", subtype="debian", arch="x86_64", is_wsl=False, version="12",
    )


@pytest.fixture
def override_root(tmp_path, monkeypatch):
    """Isolate the override root to a tmp dir for the duration of the test."""
    monkeypatch.setenv("DAZZLECMD_OVERRIDES_DIR", str(tmp_path))
    return tmp_path


def _write_override(root: Path, layer: str, fqcn: str, content: dict):
    """Write an override file at the expected path."""
    layer_dir = root / layer
    layer_dir.mkdir(parents=True, exist_ok=True)
    safe_fqcn = fqcn.replace(":", "__")
    (layer_dir / f"{safe_fqcn}.json").write_text(json.dumps(content))


# ---------------------------------------------------------------------------
# Setup resolver with user overrides
# ---------------------------------------------------------------------------


class TestSetupOverrideBasic:
    def test_no_override_file_no_change(self, override_root, linux_debian, tmp_path):
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {"command": "pip install foo"},
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "pip install foo"

    def test_override_replaces_command(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "setup", "kit:t", {
            "command": "sudo pip install foo --user",
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {"command": "pip install foo"},
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "sudo pip install foo --user"

    def test_override_without_fqcn_skipped(self, override_root, linux_debian, tmp_path):
        """Projects with no _fqcn can't look up an override; should proceed unchanged."""
        _write_override(override_root, "setup", "unused", {"command": "X"})
        project = {
            "name": "t", "_dir": str(tmp_path),  # no _fqcn
            "setup": {"command": "pip install foo"},
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "pip install foo"


class TestSetupOverridePermissiveScoping:
    def test_override_adds_new_subtype(self, override_root, linux_debian, tmp_path):
        """Permissive: override can introduce subtypes the manifest doesn't declare."""
        _write_override(override_root, "setup", "kit:t", {
            "platforms": {"linux": {"debian": {"command": "apt-specific override"}}},
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {
                "command": "generic",
                "platforms": {"linux": {"general": {"command": "generic linux"}}},
            },
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        # Override added the debian branch; resolution picks it over general
        assert result["command"] == "apt-specific override"

    def test_override_adds_new_os(self, override_root, tmp_path):
        """Override can add platforms for OSes the manifest didn't cover."""
        bsd_freebsd = PlatformInfo(
            os="bsd", subtype="freebsd", arch="x86_64", is_wsl=False, version="13",
        )
        _write_override(override_root, "setup", "kit:t", {
            "platforms": {"bsd": {"command": "pkg install foo"}},
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {"command": "generic"},
        }
        result = resolve_setup_block(project, platform_info=bsd_freebsd)
        assert result["command"] == "pkg install foo"


class TestSetupOverrideVarsMerge:
    def test_override_vars_merge_into_manifest_vars(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "setup", "kit:t", {
            "_vars": {"python_cmd": "/opt/custom/python3"},
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {
                "_vars": {"python_cmd": "python3"},
                "command": "{{python_cmd}} -m pip install foo",
            },
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        # Override wins on collision
        assert result["command"] == "/opt/custom/python3 -m pip install foo"

    def test_override_vars_visible_in_nested_templates(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "setup", "kit:t", {
            "_vars": {"venv_dir": "/opt/my-venv"},
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {
                "_vars": {"venv_dir": ".venv"},
                "command": "python3 -m venv {{venv_dir}} && {{venv_dir}}/bin/pip install foo",
            },
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "python3 -m venv /opt/my-venv && /opt/my-venv/bin/pip install foo"


class TestSetupOverrideSchemaVersion:
    def test_override_with_bad_schema_version_raises(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "setup", "kit:t", {
            "_schema_version": "999",
            "command": "override command",
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {"command": "pip install foo"},
        }
        with pytest.raises(UnsupportedSchemaVersionError):
            resolve_setup_block(project, platform_info=linux_debian)


class TestSetupOverrideMalformed:
    def test_malformed_json_raises_at_load_time(self, override_root, linux_debian, tmp_path):
        layer_dir = override_root / "setup"
        layer_dir.mkdir(parents=True)
        (layer_dir / "kit__t.json").write_text("{not valid json")
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {"command": "pip install foo"},
        }
        with pytest.raises(json.JSONDecodeError):
            resolve_setup_block(project, platform_info=linux_debian)


# ---------------------------------------------------------------------------
# Runtime resolver with user overrides
# ---------------------------------------------------------------------------


class TestRuntimeOverrideBasic:
    def test_no_override_file_no_change(self, override_root, linux_debian, tmp_path):
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        assert resolved["runtime"]["type"] == "python"
        assert resolved["runtime"].get("interpreter") is None

    def test_override_adds_interpreter(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "runtime", "kit:t", {
            "interpreter": "/opt/my-venv/bin/python",
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        assert resolved["runtime"]["interpreter"] == "/opt/my-venv/bin/python"


class TestRuntimeOverrideVarsMerge:
    def test_override_vars_win_in_template(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "runtime", "kit:t", {
            "_vars": {"venv_path": "/opt/user-venv"},
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "runtime": {
                "type": "python",
                "_vars": {"venv_path": ".venv"},
                "interpreter": "{{venv_path}}/bin/python",
                "script_path": "tool.py",
            },
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        assert resolved["runtime"]["interpreter"] == "/opt/user-venv/bin/python"


class TestRuntimeOverrideIsolationFromSetup:
    def test_setup_override_does_not_affect_runtime(self, override_root, linux_debian, tmp_path):
        """setup overrides live in overrides/setup/; runtime overrides in overrides/runtime/.
        Writing ONLY a setup override should NOT change runtime resolution."""
        _write_override(override_root, "setup", "kit:t", {
            "command": "setup override",
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        # Runtime unchanged
        assert resolved["runtime"] == {"type": "python", "script_path": "tool.py"}

    def test_runtime_override_does_not_affect_setup(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "runtime", "kit:t", {
            "interpreter": "should-not-appear-in-setup",
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {"command": "pip install foo"},
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "pip install foo"
        assert "interpreter" not in result


class TestRuntimeOverridePlatforms:
    def test_override_adds_platform_branch(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "runtime", "kit:t", {
            "platforms": {
                "linux": {"debian": {"interpreter": "/usr/bin/python3.11"}},
            },
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "runtime": {
                "type": "python",
                "script_path": "tool.py",
                "platforms": {"linux": {"general": {"interpreter": "/usr/bin/python3"}}},
            },
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        # Override's debian branch wins over manifest's general
        assert resolved["runtime"]["interpreter"] == "/usr/bin/python3.11"


class TestRuntimeOverridePrefer:
    def test_override_replaces_prefer_array(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "runtime", "kit:t", {
            "prefer": [{"interpreter": "python"}],
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {"interpreter": "not-on-path-1"},
                    {"interpreter": "not-on-path-2"},
                ],
            },
        }
        # Deep-merge: arrays REPLACED. Override's prefer wins entirely.
        resolved = resolve_runtime(project, platform_info=linux_debian)
        assert resolved["runtime"]["interpreter"] == "python"


class TestCrossLayerIndependence:
    def test_setup_and_runtime_both_overridden(self, override_root, linux_debian, tmp_path):
        _write_override(override_root, "setup", "kit:t", {"command": "user setup"})
        _write_override(override_root, "runtime", "kit:t", {
            "interpreter": "/user/python",
        })
        project = {
            "name": "t", "_fqcn": "kit:t", "_dir": str(tmp_path),
            "setup": {"command": "default setup"},
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        setup_result = resolve_setup_block(project, platform_info=linux_debian)
        runtime_result = resolve_runtime(project, platform_info=linux_debian)
        assert setup_result["command"] == "user setup"
        assert runtime_result["runtime"]["interpreter"] == "/user/python"
