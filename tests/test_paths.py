"""Tests for dazzlecmd_lib.paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from dazzlecmd_lib.paths import (
    resolve_relative_path,
    ensure_windows_executable_suffix,
    translate_wsl_path,
    which_with_pathext,
)


class TestResolveRelativePath:
    def test_absolute_path_unchanged(self, tmp_path):
        if os.name == "nt":
            abs_path = r"C:\Windows\System32"
        else:
            abs_path = "/usr/bin"
        assert resolve_relative_path(abs_path, str(tmp_path)) == abs_path

    def test_relative_resolves_against_tool_dir_when_file_exists(self, tmp_path):
        target = tmp_path / "script.py"
        target.write_text("# test")
        result = resolve_relative_path("script.py", str(tmp_path))
        assert os.path.isabs(result)
        assert result.endswith("script.py")

    def test_relative_passes_through_when_file_missing(self, tmp_path):
        # File doesn't exist in tool_dir -> return candidate unchanged
        result = resolve_relative_path("nonexistent.py", str(tmp_path))
        assert result == "nonexistent.py"

    def test_env_var_expansion_unchanged_posix(self, tmp_path):
        assert resolve_relative_path("$HOME/foo", str(tmp_path)) == "$HOME/foo"

    def test_env_var_expansion_unchanged_windows(self, tmp_path):
        assert resolve_relative_path("%USERPROFILE%\\foo", str(tmp_path)) == "%USERPROFILE%\\foo"

    def test_empty_candidate(self):
        assert resolve_relative_path("", "/any/dir") == ""


class TestEnsureWindowsExecutableSuffix:
    @pytest.mark.skipif(os.name != "nt", reason="Windows-only behavior")
    def test_adds_exe_on_windows_when_no_extension(self):
        assert ensure_windows_executable_suffix("mytool") == "mytool.exe"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only behavior")
    def test_preserves_existing_extension_on_windows(self):
        assert ensure_windows_executable_suffix("mytool.bat") == "mytool.bat"
        assert ensure_windows_executable_suffix("mytool.cmd") == "mytool.cmd"
        assert ensure_windows_executable_suffix("mytool.exe") == "mytool.exe"

    @pytest.mark.skipif(os.name == "nt", reason="POSIX-only behavior")
    def test_passes_through_on_posix(self):
        assert ensure_windows_executable_suffix("mytool") == "mytool"
        assert ensure_windows_executable_suffix("mytool.bat") == "mytool.bat"

    def test_empty_input(self):
        assert ensure_windows_executable_suffix("") == ""


class TestTranslateWslPath:
    def test_to_windows_simple(self):
        assert translate_wsl_path("/mnt/c/Users/Dustin", "to_windows") == r"C:\Users\Dustin"

    def test_to_windows_lowercase_drive_uppercased(self):
        assert translate_wsl_path("/mnt/d/projects", "to_windows") == r"D:\projects"

    def test_to_windows_non_wsl_path_unchanged(self):
        assert translate_wsl_path("/home/user/foo", "to_windows") == "/home/user/foo"

    def test_to_wsl_simple(self):
        assert translate_wsl_path(r"C:\Users\Dustin", "to_wsl") == "/mnt/c/Users/Dustin"

    def test_to_wsl_forward_slashes(self):
        assert translate_wsl_path("C:/Users/Dustin", "to_wsl") == "/mnt/c/Users/Dustin"

    def test_to_wsl_non_windows_path_unchanged(self):
        assert translate_wsl_path("/home/user/foo", "to_wsl") == "/home/user/foo"

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError):
            translate_wsl_path("/mnt/c/foo", "sideways")

    def test_to_windows_short_path_unchanged(self):
        # Too short to be /mnt/X/
        assert translate_wsl_path("/mnt", "to_windows") == "/mnt"
        assert translate_wsl_path("/mnt/", "to_windows") == "/mnt/"

    def test_to_wsl_bare_drive_unchanged(self):
        # "C:" alone (no separator) is drive-relative, don't touch
        assert translate_wsl_path("C:", "to_wsl") == "C:"


class TestWhichWithPathext:
    def test_finds_python(self):
        # Python must be on PATH to be running these tests
        result = which_with_pathext("python")
        assert result is not None

    def test_missing_returns_none(self):
        assert which_with_pathext("this-command-does-not-exist-12345") is None

    def test_empty_returns_none(self):
        assert which_with_pathext("") is None
