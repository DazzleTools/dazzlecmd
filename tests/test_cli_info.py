"""Tests for `dz info` display helpers (--raw and --platform flags)."""

from __future__ import annotations

import pytest

from dazzlecmd.cli import (
    _print_runtime_raw,
    _print_runtime_resolved,
    _print_runtime_platform_preview,
)


@pytest.fixture
def plain_python_project(tmp_path):
    return {
        "name": "mytool",
        "_dir": str(tmp_path),
        "runtime": {"type": "python", "script_path": "tool.py"},
    }


@pytest.fixture
def binary_project(tmp_path):
    return {
        "name": "mytool",
        "_dir": str(tmp_path),
        "runtime": {
            "type": "binary",
            "script_path": "target/release/mytool",
            "dev_command": "cargo run --",
        },
    }


@pytest.fixture
def conditional_project(tmp_path):
    return {
        "name": "mytool",
        "_dir": str(tmp_path),
        "runtime": {
            "type": "node",
            "prefer": [
                {"interpreter": "bun", "script_path": "tool.ts"},
                {"interpreter": "node", "script_path": "tool.js"},
                {"npx": "@myorg/mytool"},
            ],
            "platforms": {
                "windows": {
                    "type": "script",
                    "interpreter": "cscript",
                    "script_path": "tool_wsh.js",
                }
            },
        },
    }


class TestPrintRuntimeRaw:
    def test_plain_python_shows_type_and_script(self, plain_python_project, capsys):
        _print_runtime_raw(plain_python_project)
        out = capsys.readouterr().out
        assert "python" in out
        assert "raw, unresolved" in out
        assert "tool.py" in out

    def test_binary_uses_binary_label(self, binary_project, capsys):
        _print_runtime_raw(binary_project)
        out = capsys.readouterr().out
        assert "Binary:" in out
        assert "Script:" not in out
        assert "Dev command" in out
        assert "cargo run" in out

    def test_conditional_lists_platforms_and_prefer(self, conditional_project, capsys):
        _print_runtime_raw(conditional_project)
        out = capsys.readouterr().out
        assert "Platforms:" in out
        assert "windows" in out
        assert "Prefer:" in out
        assert "3 entries" in out
        assert "bun" in out
        assert "node" in out
        assert "npx" in out

    def test_prefer_entries_numbered(self, conditional_project, capsys):
        _print_runtime_raw(conditional_project)
        out = capsys.readouterr().out
        assert "[0]" in out
        assert "[1]" in out
        assert "[2]" in out


class TestPrintRuntimeResolved:
    def test_plain_runtime_no_conditional_tag(self, plain_python_project, capsys):
        _print_runtime_resolved(plain_python_project)
        out = capsys.readouterr().out
        assert "python" in out
        assert "resolved for" not in out  # No conditional => no resolution tag
        assert "raw, unresolved" not in out

    def test_conditional_with_failing_preconditions_shows_unresolved(self, capsys, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [{"interpreter": "definitely-not-on-path-xyz"}],
            },
        }
        _print_runtime_resolved(project)
        out = capsys.readouterr().out
        assert "unresolved" in out
        assert "Tried:" in out or "definitely-not-on-path-xyz" in out

    def test_conditional_that_resolves_shows_resolved_tag(self, capsys, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [{"interpreter": "python"}],
            },
        }
        _print_runtime_resolved(project)
        out = capsys.readouterr().out
        assert "resolved for" in out
        assert "Interpreter" in out
        assert "python" in out


class TestPrintRuntimePlatformPreview:
    def test_preview_for_windows_shows_platform_tag(self, conditional_project, capsys):
        _print_runtime_platform_preview(conditional_project, "windows")
        out = capsys.readouterr().out
        assert "preview for windows" in out
        # Windows override: type=script, interpreter=cscript
        assert "script" in out
        assert "cscript" in out
        assert "tool_wsh.js" in out

    def test_preview_for_linux_debian_shows_subtype(self, conditional_project, capsys):
        _print_runtime_platform_preview(conditional_project, "linux.debian")
        out = capsys.readouterr().out
        assert "preview for linux.debian" in out

    def test_preview_enumerates_prefer_without_precondition_eval(
        self, conditional_project, capsys
    ):
        # On linux there's no platform override, so base prefer applies
        _print_runtime_platform_preview(conditional_project, "linux")
        out = capsys.readouterr().out
        assert "preconditions not evaluated" in out
        assert "bun" in out
        assert "node" in out
        assert "npx" in out

    def test_preview_without_platforms_still_works(self, plain_python_project, capsys):
        _print_runtime_platform_preview(plain_python_project, "linux.debian")
        out = capsys.readouterr().out
        assert "preview for linux.debian" in out
        assert "python" in out
        assert "tool.py" in out

    def test_detect_when_annotated(self, capsys, tmp_path):
        project = {
            "name": "mytool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "script",
                "prefer": [
                    {
                        "detect_when": {"uname_contains": "wsl"},
                        "interpreter": "bun",
                    },
                    {"interpreter": "node"},
                ],
            },
        }
        _print_runtime_platform_preview(project, "linux")
        out = capsys.readouterr().out
        assert "detect_when=<set>" in out
