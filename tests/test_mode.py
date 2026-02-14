"""Tests for dazzlecmd.mode — dev/publish mode toggle."""

import json
import os
import subprocess
import sys
import tempfile

import pytest

from dazzlecmd.mode import (
    detect_tool_state,
    load_local_config,
    parse_gitmodules,
    save_local_config,
    STATE_EMBEDDED,
    STATE_LOCAL_ONLY,
    STATE_MISSING,
    STATE_SUBMODULE,
    STATE_SYMLINK,
)
from dazzlecmd.importer import is_linked_project, remove_link


class TestDetectToolState:
    """Tests for tool state detection."""

    def test_missing_path(self):
        """Non-existent path is STATE_MISSING."""
        state = detect_tool_state("/nonexistent/path/12345", {})
        assert state == STATE_MISSING

    def test_plain_dir_no_submodule(self):
        """Regular directory with no submodule entry is EMBEDDED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
            os.makedirs(tool_dir)
            state = detect_tool_state(tool_dir, {})
            assert state == STATE_EMBEDDED

    def test_plain_dir_with_submodule(self):
        """Regular directory with matching submodule entry is SUBMODULE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
            os.makedirs(tool_dir)
            gitmodules = {"projects/core/mytool": {"url": "https://example.com"}}
            state = detect_tool_state(tool_dir, gitmodules)
            assert state == STATE_SUBMODULE

    def test_symlink_with_submodule(self):
        """Symlink with matching submodule entry is SYMLINK (dev mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "source")
            os.makedirs(source)
            tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
            os.makedirs(os.path.dirname(tool_dir), exist_ok=True)

            # Create link
            from dazzlecmd.importer import create_link
            result = create_link(source, tool_dir)
            if result is None:
                pytest.skip("Could not create link (permissions)")

            gitmodules = {"projects/core/mytool": {"url": "https://example.com"}}
            state = detect_tool_state(tool_dir, gitmodules)
            assert state == STATE_SYMLINK

            remove_link(tool_dir)

    def test_symlink_no_submodule(self):
        """Symlink without submodule entry is LOCAL_ONLY."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "source")
            os.makedirs(source)
            tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
            os.makedirs(os.path.dirname(tool_dir), exist_ok=True)

            from dazzlecmd.importer import create_link
            result = create_link(source, tool_dir)
            if result is None:
                pytest.skip("Could not create link (permissions)")

            state = detect_tool_state(tool_dir, {})
            assert state == STATE_LOCAL_ONLY

            remove_link(tool_dir)


class TestParseGitmodules:
    """Tests for .gitmodules parsing."""

    def test_no_gitmodules(self):
        """Returns empty dict when .gitmodules doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = parse_gitmodules(tmpdir)
            assert result == {}

    def test_parse_valid_gitmodules(self):
        """Correctly parses .gitmodules with project submodules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gitmodules_content = (
                '[submodule "projects/core/listall"]\n'
                '\tpath = projects/core/listall\n'
                '\turl = https://github.com/DazzleTools/listall.git\n'
                '[submodule "projects/core/rn"]\n'
                '\tpath = projects/core/rn\n'
                '\turl = https://github.com/DazzleTools/rn.git\n'
            )
            with open(os.path.join(tmpdir, ".gitmodules"), "w") as f:
                f.write(gitmodules_content)

            result = parse_gitmodules(tmpdir)
            assert "projects/core/listall" in result
            assert result["projects/core/listall"]["url"] == (
                "https://github.com/DazzleTools/listall.git"
            )
            assert result["projects/core/listall"]["namespace"] == "core"
            assert result["projects/core/listall"]["tool_name"] == "listall"
            assert "projects/core/rn" in result

    def test_ignores_non_project_submodules(self):
        """Ignores submodules not under projects/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gitmodules_content = (
                '[submodule "libs/somelib"]\n'
                '\tpath = libs/somelib\n'
                '\turl = https://example.com/somelib.git\n'
            )
            with open(os.path.join(tmpdir, ".gitmodules"), "w") as f:
                f.write(gitmodules_content)

            result = parse_gitmodules(tmpdir)
            assert result == {}


class TestLocalConfig:
    """Tests for mode_local.json load/save."""

    def test_load_missing_file(self):
        """Returns empty dict when mode_local.json doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_local_config(tmpdir)
            assert result == {}

    def test_round_trip(self):
        """Save and load preserves dev paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = {
                "core:listall": "C:\\code\\listall",
                "core:rn": "C:\\code\\rn",
            }
            save_local_config(tmpdir, paths)

            loaded = load_local_config(tmpdir)
            assert loaded == paths

            # Verify file structure
            config_path = os.path.join(tmpdir, "mode_local.json")
            with open(config_path) as f:
                data = json.load(f)
            assert "dev_paths" in data

    def test_load_invalid_json(self):
        """Returns empty dict for invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "mode_local.json")
            with open(config_path, "w") as f:
                f.write("not valid json{{{")
            result = load_local_config(tmpdir)
            assert result == {}


class TestDiscoverProjectsCacheFallback:
    """Tests that discover_projects() finds tools via cached manifests."""

    def test_tool_without_manifest_uses_cache(self):
        """A tool dir with no .dazzlecmd.json is found via manifest cache."""
        from dazzlecmd.loader import discover_projects
        from dazzlecmd.mode import cache_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project structure: projects/core/mytool/ (no manifest)
            projects_dir = os.path.join(tmpdir, "projects")
            tool_dir = os.path.join(projects_dir, "core", "mytool")
            os.makedirs(tool_dir)
            # Put a dummy file so it's not empty
            with open(os.path.join(tool_dir, "mytool.py"), "w") as f:
                f.write("# placeholder")

            # Without cache, tool should NOT be discovered
            found = discover_projects(projects_dir)
            names = [p["name"] for p in found]
            assert "mytool" not in names

            # Cache a manifest
            cache_manifest(tmpdir, "core:mytool", {
                "name": "mytool",
                "version": "1.0.0",
                "description": "A cached tool",
                "runtime": {"type": "python", "script_path": "mytool.py"},
            })

            # Now discover_projects should find it via cache
            found = discover_projects(projects_dir)
            names = [p["name"] for p in found]
            assert "mytool" in names

            cached_project = [p for p in found if p["name"] == "mytool"][0]
            assert cached_project["_cached"] is True
            assert cached_project["description"] == "A cached tool"

    def test_on_disk_manifest_preferred_over_cache(self):
        """When .dazzlecmd.json exists on disk, cache is ignored."""
        from dazzlecmd.loader import discover_projects
        from dazzlecmd.mode import cache_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            projects_dir = os.path.join(tmpdir, "projects")
            tool_dir = os.path.join(projects_dir, "core", "mytool")
            os.makedirs(tool_dir)

            # Write on-disk manifest
            manifest = {
                "name": "mytool",
                "version": "2.0.0",
                "description": "On-disk version",
            }
            with open(os.path.join(tool_dir, ".dazzlecmd.json"), "w") as f:
                json.dump(manifest, f)

            # Also cache a different version
            cache_manifest(tmpdir, "core:mytool", {
                "name": "mytool",
                "version": "1.0.0",
                "description": "Cached version",
            })

            found = discover_projects(projects_dir)
            project = [p for p in found if p["name"] == "mytool"][0]
            assert project["description"] == "On-disk version"
            assert "_cached" not in project

    def test_empty_dir_no_cache_skipped(self):
        """A tool dir with no manifest and no cache is skipped."""
        from dazzlecmd.loader import discover_projects

        with tempfile.TemporaryDirectory() as tmpdir:
            projects_dir = os.path.join(tmpdir, "projects")
            tool_dir = os.path.join(projects_dir, "core", "orphan")
            os.makedirs(tool_dir)

            found = discover_projects(projects_dir)
            names = [p["name"] for p in found]
            assert "orphan" not in names


class TestCliMode:
    """Smoke tests for dz mode CLI commands."""

    def test_mode_status_runs(self):
        """dz mode status exits cleanly."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzlecmd", "mode", "status"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "tool(s)" in result.stdout

    def test_mode_status_single_tool(self):
        """dz mode status <tool> filters to one tool."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzlecmd", "mode", "status", "rn"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "rn" in result.stdout
        assert "1 tool(s)" in result.stdout

    def test_mode_status_nonexistent(self):
        """dz mode status <nonexistent> fails."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzlecmd", "mode", "status",
             "nonexistent"],
            capture_output=True, text=True
        )
        assert result.returncode != 0

    def test_mode_switch_nonexistent(self):
        """dz mode switch <nonexistent> fails."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzlecmd", "mode", "switch",
             "nonexistent"],
            capture_output=True, text=True
        )
        assert result.returncode != 0

    def test_mode_switch_dry_run(self):
        """dz mode switch --dry-run doesn't change anything."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzlecmd", "mode", "switch", "rn",
             "--dev", "--dry-run", "--path", "C:\\code"],
            capture_output=True, text=True
        )
        # rn is embedded, so --dev with --dry-run should show the plan
        assert "DRY-RUN" in result.stdout or "DRY-RUN" in result.stderr

    def test_bare_mode_shows_status(self):
        """dz mode with no subcommand shows status."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzlecmd", "mode"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "tool(s)" in result.stdout
