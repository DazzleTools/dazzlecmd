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


class TestBug2RawShowsVars:
    """Regression for v0.7.20 BUG-2: --raw must surface _vars declarations
    and per-platform manifest values so authors debugging {{...}} references
    can see what's declared at each scope."""

    def test_manifest_top_vars_shown_in_raw(self, tmp_path, capsys):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"venv_dir": ".venv", "venv_bin": "{{venv_dir}}/bin"},
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        _print_runtime_raw(project)
        out = capsys.readouterr().out
        assert "_vars (manifest-top)" in out
        assert "venv_dir" in out
        assert ".venv" in out
        assert "venv_bin" in out

    def test_runtime_block_vars_shown_in_raw(self, tmp_path, capsys):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "python",
                "_vars": {"my_var": "foo"},
                "script_path": "tool.py",
            },
        }
        _print_runtime_raw(project)
        out = capsys.readouterr().out
        assert "_vars (runtime block)" in out
        assert "my_var" in out
        assert "foo" in out

    def test_platform_overrides_shown_in_raw(self, tmp_path, capsys):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "python",
                "platforms": {
                    "linux": {"interpreter": "{{venv_bin}}/python"},
                    "windows": "C:\\Python311\\python.exe",
                },
            },
        }
        _print_runtime_raw(project)
        out = capsys.readouterr().out
        # Linux platform's interpreter with unresolved {{...}} visible
        assert "{{venv_bin}}/python" in out
        # Windows flat-string shorthand shown
        assert "C:\\Python311\\python.exe" in out or "Python311" in out


class TestBug3InfoCatchesUnresolvedAtInfoTime:
    """Regression for v0.7.20 BUG-3: `dz info` must catch unresolved {{...}}
    references at inspection time, not silently pass them through."""

    def test_unresolved_var_shown_as_error(self, tmp_path, capsys):
        # Manifest with {{undefined_var}} but no _vars anywhere
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "runtime": {
                "type": "python",
                "interpreter": "{{undefined_var}}/python",
            },
        }
        _print_runtime_resolved(project)
        out = capsys.readouterr().out
        # Should report the resolution error, not silently show the literal string
        assert "resolution error" in out or "undefined_var" in out

    def test_cycle_shown_as_error(self, tmp_path, capsys):
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "_vars": {"a": "{{b}}", "b": "{{a}}"},
            "runtime": {
                "type": "python",
                "interpreter": "{{a}}/python",
            },
        }
        _print_runtime_resolved(project)
        out = capsys.readouterr().out
        assert "resolution error" in out.lower() or "cycle" in out.lower()

    def test_plain_manifest_without_refs_not_affected(self, tmp_path, capsys):
        # Backwards compat: no refs, no _vars -> still takes the plain path
        project = {
            "name": "tool",
            "_dir": str(tmp_path),
            "runtime": {"type": "python", "script_path": "tool.py"},
        }
        _print_runtime_resolved(project)
        out = capsys.readouterr().out
        assert "Runtime:" in out
        assert "resolution error" not in out
        assert "resolved for" not in out  # no annotation when no conditional dispatch
