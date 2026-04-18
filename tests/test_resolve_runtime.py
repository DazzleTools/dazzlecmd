"""Integration tests for registry.resolve_runtime() conditional dispatch."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from dazzlecmd_lib.registry import (
    resolve_runtime,
    NoRuntimeResolutionError,
)
from dazzlecmd_lib.platform_detect import PlatformInfo
from dazzlecmd_lib.schema_version import UnsupportedSchemaVersionError


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


@pytest.fixture
def linux_arch():
    return PlatformInfo(
        os="linux", subtype="arch", arch="x86_64", is_wsl=False, version=None,
    )


class TestFastPath:
    def test_no_platforms_no_prefer_returns_original(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result is project  # same object, fast path

    def test_empty_runtime_returns_original(self, linux_debian, tmp_path):
        project = {"name": "x", "_dir": str(tmp_path), "runtime": {}}
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result is project

    def test_no_runtime_key_returns_original(self, linux_debian, tmp_path):
        project = {"name": "x", "_dir": str(tmp_path)}
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result is project


class TestPlatformsOverride:
    def test_platform_block_overrides_base(self, windows_win11, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "node",
                "script_path": "tool.js",
                "platforms": {
                    "windows": {
                        "type": "script",
                        "interpreter": "cscript",
                        "script_path": "tool_wsh.js",
                    },
                },
            },
        }
        result = resolve_runtime(project, platform_info=windows_win11)
        rt = result["runtime"]
        assert rt["type"] == "script"
        assert rt["interpreter"] == "cscript"
        assert rt["script_path"] == "tool_wsh.js"
        # platforms key is removed from the resolved block
        assert "platforms" not in rt

    def test_no_matching_platform_falls_through(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "python",
                "script_path": "tool.py",
                "platforms": {
                    "windows": {"interpreter": "cscript"},
                    "macos": {"interpreter": "python3"},
                },
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        rt = result["runtime"]
        assert rt["type"] == "python"
        assert rt["script_path"] == "tool.py"
        assert "interpreter" not in rt

    def test_subtype_match_overrides_general(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "platforms": {
                    "linux": {
                        "debian": {"script_path": "debian.sh"},
                        "general": {"script_path": "generic.sh"},
                    }
                },
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result["runtime"]["script_path"] == "debian.sh"

    def test_subtype_fallback_to_general(self, linux_arch, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "platforms": {
                    "linux": {
                        "debian": {"script_path": "debian.sh"},
                        "general": {"script_path": "generic.sh"},
                    }
                },
            },
        }
        result = resolve_runtime(project, platform_info=linux_arch)
        assert result["runtime"]["script_path"] == "generic.sh"


class TestPreferIteration:
    def test_first_match_wins(self, linux_debian, tmp_path):
        # python is definitely on PATH (running these tests); first entry picks it.
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {"interpreter": "python"},
                    {"interpreter": "this-is-not-on-path-xyz"},
                ],
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result["runtime"]["interpreter"] == "python"

    def test_fallthrough_to_second_entry(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {"interpreter": "this-is-not-on-path-xyz"},
                    {"interpreter": "python"},
                ],
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result["runtime"]["interpreter"] == "python"

    def test_no_entry_matches_raises(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {"interpreter": "this-is-not-on-path-xyz"},
                    {"interpreter": "also-not-on-path-abc"},
                ],
            },
        }
        with pytest.raises(NoRuntimeResolutionError) as exc:
            resolve_runtime(project, platform_info=linux_debian)
        msg = str(exc.value)
        assert "mytool" in msg
        assert "this-is-not-on-path-xyz" in msg
        assert "also-not-on-path-abc" in msg

    def test_script_path_must_exist(self, linux_debian, tmp_path):
        # First entry declares a script that doesn't exist; second has no script_path
        # but an interpreter on PATH (python).
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {"interpreter": "python", "script_path": "does-not-exist.py"},
                    {"interpreter": "python"},
                ],
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        # Second entry picked (no script_path precondition to fail)
        assert result["runtime"]["interpreter"] == "python"
        assert "script_path" not in result["runtime"] or result["runtime"].get("script_path") != "does-not-exist.py"

    def test_script_path_absolute_resolves(self, linux_debian, tmp_path):
        real_script = tmp_path / "real.py"
        real_script.write_text("# test")
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {"interpreter": "python", "script_path": str(real_script)},
                ],
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result["runtime"]["script_path"] == str(real_script)

    def test_selected_entry_merged_into_effective(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "interpreter_args": ["-u"],  # base field preserved
                "prefer": [
                    {"interpreter": "python"},
                ],
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        rt = result["runtime"]
        assert rt["interpreter"] == "python"
        assert rt["interpreter_args"] == ["-u"]
        assert "prefer" not in rt  # prefer key stripped after resolution


class TestDetectWhenInPrefer:
    def test_detect_when_fails_skips_entry(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {
                        "detect_when": {"uname_contains": "darwin"},
                        "interpreter": "python",
                    },
                    {"interpreter": "python"},
                ],
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        # First entry's detect_when didn't match on linux, fell through
        assert result["runtime"]["interpreter"] == "python"
        assert "detect_when" not in result["runtime"]

    def test_detect_when_passes_and_preconditions_pass(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {
                        "detect_when": {"uname_contains": "debian"},
                        "interpreter": "python",
                    },
                ],
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result["runtime"]["interpreter"] == "python"

    def test_detect_when_passes_but_preconditions_fail(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {
                        "detect_when": {"uname_contains": "debian"},
                        "interpreter": "not-on-path-xyz",
                    },
                ],
            },
        }
        with pytest.raises(NoRuntimeResolutionError):
            resolve_runtime(project, platform_info=linux_debian)


class TestPlatformsPlusPreferComposed:
    def test_platforms_override_then_prefer(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "platforms": {
                    "linux": {
                        "debian": {
                            "prefer": [
                                {"interpreter": "python"},
                            ],
                        },
                    },
                    "windows": {
                        "interpreter": "cscript",
                    },
                },
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result["runtime"]["interpreter"] == "python"

    def test_base_prefer_replaced_by_platform_prefer(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {"interpreter": "generic-interp-not-on-path"},
                ],
                "platforms": {
                    "linux": {
                        "prefer": [{"interpreter": "python"}],
                    },
                },
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result["runtime"]["interpreter"] == "python"


class TestSchemaVersionCheck:
    def test_unsupported_version_raises(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "_schema_version": "999",
                "type": "python",
                "script_path": "tool.py",
            },
        }
        with pytest.raises(UnsupportedSchemaVersionError):
            resolve_runtime(project, platform_info=linux_debian)

    def test_version_1_passes(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "_schema_version": "1",
                "type": "python",
                "script_path": "tool.py",
            },
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result["runtime"]["type"] == "python"

    def test_no_version_defaults_and_passes(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        result = resolve_runtime(project, platform_info=linux_debian)
        assert result["runtime"]["type"] == "python"


class TestProjectNotMutated:
    def test_original_project_unchanged(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "platforms": {"linux": {"interpreter": "python"}},
            },
        }
        original_runtime = dict(project["runtime"])
        original_platforms = dict(project["runtime"]["platforms"])
        _ = resolve_runtime(project, platform_info=linux_debian)
        assert project["runtime"] == original_runtime
        assert project["runtime"]["platforms"] == original_platforms


class TestErrorMessageQuality:
    def test_trace_includes_platform_info(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [{"interpreter": "not-a-real-cmd-xyz"}],
            },
        }
        with pytest.raises(NoRuntimeResolutionError) as exc:
            resolve_runtime(project, platform_info=linux_debian)
        msg = str(exc.value)
        assert "linux" in msg
        assert "debian" in msg
        assert "x86_64" in msg

    def test_trace_lists_each_attempt(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {"interpreter": "fake-one"},
                    {"interpreter": "fake-two"},
                    {"interpreter": "fake-three"},
                ],
            },
        }
        with pytest.raises(NoRuntimeResolutionError) as exc:
            resolve_runtime(project, platform_info=linux_debian)
        msg = str(exc.value)
        assert "fake-one" in msg
        assert "fake-two" in msg
        assert "fake-three" in msg

    def test_trace_includes_fix_hint(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [{"interpreter": "not-real-xyz"}],
            },
        }
        with pytest.raises(NoRuntimeResolutionError) as exc:
            resolve_runtime(project, platform_info=linux_debian)
        msg = str(exc.value).lower()
        assert "fix" in msg or "install" in msg or "add" in msg


class TestInvalidPreferType:
    def test_non_list_prefer_raises(self, linux_debian, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": "not a list",
            },
        }
        with pytest.raises(ValueError):
            resolve_runtime(project, platform_info=linux_debian)


class TestDispatchToolCatchesResolutionError:
    """Regression: NoRuntimeResolutionError must be caught by dispatch_tool.

    Discovered by the v0.7.19 tester run -- the error escaped as a full Python
    traceback at the top level because resolve_entry_point() was called outside
    the try block in cli.dispatch_tool(). dz info handled it gracefully; dz
    <tool> dispatch did not.
    """

    def test_dispatch_tool_returns_1_on_no_resolution(self, tmp_path, capsys):
        from dazzlecmd.cli import dispatch_tool

        project = {
            "name": "unresolvable",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [{"interpreter": "definitely-not-on-path-xyz-12345"}],
            },
        }
        result = dispatch_tool(project, [])
        assert result == 1

    def test_dispatch_tool_prints_clean_error_without_traceback(self, tmp_path, capsys):
        from dazzlecmd.cli import dispatch_tool

        project = {
            "name": "unresolvable",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [{"interpreter": "definitely-not-on-path-xyz-12345"}],
            },
        }
        dispatch_tool(project, [])
        captured = capsys.readouterr()
        # Error trace content is present
        assert "unresolvable" in captured.err
        assert "definitely-not-on-path" in captured.err
        assert "Fix:" in captured.err
        # Python traceback markers are absent -- no raw exception propagation
        assert "Traceback" not in captured.err
        assert "File \"" not in captured.err

    def test_dispatch_tool_catches_unsupported_schema_version(self, tmp_path, capsys):
        from dazzlecmd.cli import dispatch_tool

        project = {
            "name": "bad-schema",
            "_dir": str(tmp_path),
            "runtime": {
                "_schema_version": "999",
                "type": "python",
                "script_path": "tool.py",
            },
        }
        result = dispatch_tool(project, [])
        captured = capsys.readouterr()
        assert result == 1
        assert "999" in captured.err
        assert "Traceback" not in captured.err

    def test_dispatch_tool_catches_unresolved_template_var(self, tmp_path, capsys):
        """BUG-4 regression: UnresolvedTemplateVariableError must not escape as traceback."""
        from dazzlecmd.cli import dispatch_tool

        project = {
            "name": "broken",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "python",
                "interpreter": "{{undefined}}/python",
            },
        }
        result = dispatch_tool(project, [])
        captured = capsys.readouterr()
        assert result == 1
        assert "undefined" in captured.err
        assert "Traceback" not in captured.err
        assert "File \"" not in captured.err

    def test_dispatch_tool_catches_template_cycle(self, tmp_path, capsys):
        """BUG-4 regression: TemplateRecursionError must not escape as traceback."""
        from dazzlecmd.cli import dispatch_tool

        project = {
            "name": "cyclic",
            "_dir": str(tmp_path),
            "_vars": {"a": "{{b}}", "b": "{{a}}"},
            "runtime": {
                "type": "python",
                "interpreter": "{{a}}/python",
            },
        }
        result = dispatch_tool(project, [])
        captured = capsys.readouterr()
        assert result == 1
        assert "cycle" in captured.err.lower()
        assert "Traceback" not in captured.err

    def test_dispatch_tool_catches_malformed_override_json(
        self, tmp_path, monkeypatch, capsys
    ):
        """v0.7.22 BUG-1 regression: malformed override JSON at dispatch time
        surfaces clean error, not a Python traceback."""
        from dazzlecmd.cli import dispatch_tool

        monkeypatch.setenv("DAZZLECMD_OVERRIDES_DIR", str(tmp_path))
        (tmp_path / "runtime").mkdir()
        (tmp_path / "runtime" / "kit__mytool.json").write_text("{not valid json")

        project = {
            "name": "mytool",
            "_fqcn": "kit:mytool",
            "_dir": str(tmp_path),
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        result = dispatch_tool(project, [])
        captured = capsys.readouterr()
        assert result == 1
        assert "Error:" in captured.err
        assert "not valid JSON" in captured.err or "Expecting" in captured.err
        assert "Traceback" not in captured.err
        assert "File \"" not in captured.err
