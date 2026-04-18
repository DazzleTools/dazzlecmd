"""Integration tests for `_vars` template substitution through the resolvers.

Covers the full pipeline: platform merge -> `_vars` collection (manifest-top +
effective block) -> substitution -> prefer iteration (for runtime) or return
(for setup). Verifies scope layering, dynamic scoping, and cross-block
visibility rules.
"""

from __future__ import annotations

import pytest

from dazzlecmd_lib.setup_resolve import resolve_setup_block
from dazzlecmd_lib.registry import resolve_runtime, NoRuntimeResolutionError
from dazzlecmd_lib.platform_detect import PlatformInfo
from dazzlecmd_lib.templates import (
    UnresolvedTemplateVariableError,
    TemplateRecursionError,
)


@pytest.fixture
def linux_debian():
    return PlatformInfo(
        os="linux", subtype="debian", arch="x86_64", is_wsl=False, version="12",
    )


@pytest.fixture
def windows_win11():
    return PlatformInfo(
        os="windows", subtype="win11", arch="x86_64", is_wsl=False, version="10.0.22621",
    )


# ---------------------------------------------------------------------------
# Setup resolver _vars integration
# ---------------------------------------------------------------------------

class TestSetupManifestTopVars:
    def test_manifest_top_vars_visible_in_setup(self, linux_debian, tmp_path):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"venv_dir": ".venv"},
            "setup": {
                "platforms": {
                    "linux": {"command": "python3 -m venv {{venv_dir}}"}
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "python3 -m venv .venv"

    def test_manifest_top_vars_with_nesting(self, linux_debian, tmp_path):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {
                "venv_dir": ".venv",
                "venv_pip": "{{venv_dir}}/bin/pip"
            },
            "setup": {
                "platforms": {
                    "linux": {"command": "{{venv_pip}} install -r requirements.txt"}
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == ".venv/bin/pip install -r requirements.txt"


class TestSetupBlockVars:
    def test_setup_local_vars(self, linux_debian, tmp_path):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "setup": {
                "_vars": {"pip_flags": "--no-cache-dir"},
                "platforms": {
                    "linux": {"command": "pip install {{pip_flags}} foo"}
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "pip install --no-cache-dir foo"
        # _vars stripped from output
        assert "_vars" not in result

    def test_block_vars_override_manifest_top(self, linux_debian, tmp_path):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"x": "manifest-value"},
            "setup": {
                "_vars": {"x": "setup-value"},
                "platforms": {
                    "linux": {"command": "echo {{x}}"}
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "echo setup-value"


class TestSetupPlatformLevelVars:
    def test_platform_vars_override(self, linux_debian, windows_win11, tmp_path):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"python_cmd": "python3"},
            "setup": {
                "platforms": {
                    "linux": {"command": "{{python_cmd}} -m venv .venv"},
                    "windows": {
                        "_vars": {"python_cmd": "py"},
                        "command": "{{python_cmd}} -m venv .venv"
                    }
                }
            }
        }
        linux_result = resolve_setup_block(project, platform_info=linux_debian)
        windows_result = resolve_setup_block(project, platform_info=windows_win11)
        assert linux_result["command"] == "python3 -m venv .venv"
        assert windows_result["command"] == "py -m venv .venv"

    def test_dynamic_scoping_composite_var(self, linux_debian, windows_win11, tmp_path):
        """Composite var resolves in the CURRENT platform scope, not manifest-top."""
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {
                "python_cmd": "python3",
                "venv_create": "{{python_cmd}} -m venv .venv"
            },
            "setup": {
                "platforms": {
                    "linux": {"command": "{{venv_create}} && ..."},
                    "windows": {
                        "_vars": {"python_cmd": "py"},
                        "command": "{{venv_create}} && ..."
                    }
                }
            }
        }
        linux_result = resolve_setup_block(project, platform_info=linux_debian)
        windows_result = resolve_setup_block(project, platform_info=windows_win11)
        assert linux_result["command"] == "python3 -m venv .venv && ..."
        # Dynamic scoping -- Windows' python_cmd=py used inside composite
        assert windows_result["command"] == "py -m venv .venv && ..."


class TestSetupSubtypeVars:
    def test_subtype_vars_win_over_platform(self, linux_debian, tmp_path):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "setup": {
                "platforms": {
                    "linux": {
                        "_vars": {"pkg_mgr": "pkg"},
                        "debian": {
                            "_vars": {"pkg_mgr": "apt"},
                            "command": "sudo {{pkg_mgr}} install foo"
                        }
                    }
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "sudo apt install foo"


class TestSetupErrors:
    def test_unresolved_var_in_setup_raises(self, linux_debian, tmp_path):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "setup": {
                "platforms": {
                    "linux": {"command": "{{undefined}} install"}
                }
            }
        }
        with pytest.raises(UnresolvedTemplateVariableError) as exc:
            resolve_setup_block(project, platform_info=linux_debian)
        assert "undefined" in str(exc.value)

    def test_cycle_in_vars_raises(self, linux_debian, tmp_path):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"a": "{{b}}", "b": "{{a}}"},
            "setup": {
                "platforms": {"linux": {"command": "{{a}}"}}
            }
        }
        with pytest.raises(TemplateRecursionError):
            resolve_setup_block(project, platform_info=linux_debian)


# ---------------------------------------------------------------------------
# Runtime resolver _vars integration
# ---------------------------------------------------------------------------

class TestRuntimeVars:
    def test_manifest_top_vars_in_runtime(self, linux_debian, tmp_path):
        script = tmp_path / "tool.py"
        script.write_text("")
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"venv_bin": ".venv/bin"},
            "runtime": {
                "type": "python",
                "script_path": "tool.py",
                "platforms": {
                    "linux": {"interpreter": "{{venv_bin}}/python"}
                }
            }
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        assert resolved["runtime"]["interpreter"] == ".venv/bin/python"

    def test_runtime_vars_local_to_runtime_block(self, linux_debian, tmp_path):
        script = tmp_path / "tool.py"
        script.write_text("")
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "runtime": {
                "_vars": {"my_interp": "python3"},
                "type": "python",
                "script_path": "tool.py",
                "platforms": {
                    "linux": {"interpreter": "{{my_interp}}"}
                }
            }
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        assert resolved["runtime"]["interpreter"] == "python3"

    def test_setup_vars_NOT_visible_in_runtime(self, linux_debian, tmp_path):
        """setup._vars is scoped to setup -- runtime can't see them."""
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "setup": {"_vars": {"x": "setup-only"}, "command": "echo {{x}}"},
            "runtime": {
                "type": "python",
                "interpreter": "{{x}}"   # should fail -- x not in runtime scope
            }
        }
        with pytest.raises(UnresolvedTemplateVariableError):
            resolve_runtime(project, platform_info=linux_debian)


class TestRuntimePreferSubstitution:
    def test_prefer_entries_substituted_before_precondition_check(
        self, linux_debian, tmp_path
    ):
        """Prefer iteration must check preconditions on substituted values."""
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"py": "python"},   # python is on PATH
            "runtime": {
                "type": "script",
                "prefer": [
                    {"interpreter": "definitely-not-on-path"},
                    {"interpreter": "{{py}}"}   # substituted to "python"
                ]
            }
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        # Second entry should win after substitution: interpreter=python
        assert resolved["runtime"]["interpreter"] == "python"

    def test_detect_when_values_substituted(self, linux_debian, tmp_path):
        marker = tmp_path / ".marker"
        marker.write_text("")
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"marker_path": str(marker)},
            "runtime": {
                "type": "script",
                "prefer": [
                    {
                        "detect_when": {"file_exists": "{{marker_path}}"},
                        "interpreter": "python"
                    }
                ]
            }
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        assert resolved["runtime"]["interpreter"] == "python"


class TestCrossBlockSharing:
    def test_manifest_top_vars_shared_setup_and_runtime(self, linux_debian, tmp_path):
        """The primary use case -- venv path shared between install and dispatch."""
        script = tmp_path / "tool.py"
        script.write_text("")
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {
                "venv_dir": ".venv",
                "venv_bin": "{{venv_dir}}/bin"
            },
            "setup": {
                "platforms": {
                    "linux": {"command": "python3 -m venv {{venv_dir}} && {{venv_bin}}/pip install -r requirements.txt"}
                }
            },
            "runtime": {
                "type": "python",
                "script_path": "tool.py",
                "platforms": {
                    "linux": {"interpreter": "{{venv_bin}}/python"}
                }
            }
        }
        setup_result = resolve_setup_block(project, platform_info=linux_debian)
        runtime_result = resolve_runtime(project, platform_info=linux_debian)
        assert setup_result["command"] == (
            "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
        )
        assert runtime_result["runtime"]["interpreter"] == ".venv/bin/python"


class TestFastPath:
    def test_no_vars_no_platforms_no_prefer_fast_path(self, linux_debian, tmp_path):
        """Manifest without any of (_vars, platforms, prefer) returns unchanged."""
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "runtime": {"type": "python", "script_path": "tool.py"}
        }
        resolved = resolve_runtime(project, platform_info=linux_debian)
        assert resolved is project  # same reference

    def test_no_setup_block_returns_none(self, linux_debian, tmp_path):
        project = {"name": "tool", "_dir": str(tmp_path)}
        assert resolve_setup_block(project, platform_info=linux_debian) is None

    def test_vars_without_references_still_substitutes_nothing(self, linux_debian, tmp_path):
        """Manifest with _vars but no {{...}} references -- substitution is a no-op."""
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"unused": "never-referenced"},
            "setup": {
                "platforms": {"linux": {"command": "apt install foo"}}
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "apt install foo"
