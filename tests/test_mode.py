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
from dazzlecmd_lib.paths import is_linked_project, remove_link


class TestDetectToolState:
    """Tests for tool state detection."""

    def test_missing_path(self):
        """Non-existent path is STATE_MISSING."""
        state = detect_tool_state("/nonexistent/path/12345", {}, "/nonexistent")
        assert state == STATE_MISSING

    def test_plain_dir_no_submodule(self):
        """Regular directory with no submodule entry is EMBEDDED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
            os.makedirs(tool_dir)
            state = detect_tool_state(tool_dir, {}, tmpdir)
            assert state == STATE_EMBEDDED

    def test_plain_dir_with_submodule(self):
        """Regular directory with matching submodule entry is SUBMODULE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
            os.makedirs(tool_dir)
            gitmodules = {"projects/core/mytool": {"url": "https://example.com"}}
            state = detect_tool_state(tool_dir, gitmodules, tmpdir)
            assert state == STATE_SUBMODULE

    def test_symlink_with_submodule(self):
        """Symlink with matching submodule entry is SYMLINK (dev mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "source")
            os.makedirs(source)
            tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
            os.makedirs(os.path.dirname(tool_dir), exist_ok=True)

            # Create link
            from dazzlecmd_lib.paths import create_link
            result = create_link(source, tool_dir)
            if result is None:
                pytest.skip("Could not create link (permissions)")

            gitmodules = {"projects/core/mytool": {"url": "https://example.com"}}
            state = detect_tool_state(tool_dir, gitmodules, tmpdir)
            assert state == STATE_SYMLINK

            remove_link(tool_dir)

    def test_symlink_no_submodule(self):
        """Symlink without submodule entry is LOCAL_ONLY."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "source")
            os.makedirs(source)
            tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
            os.makedirs(os.path.dirname(tool_dir), exist_ok=True)

            from dazzlecmd_lib.paths import create_link
            result = create_link(source, tool_dir)
            if result is None:
                pytest.skip("Could not create link (permissions)")

            state = detect_tool_state(tool_dir, {}, tmpdir)
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
        from dazzlecmd_lib.testing import make_tool

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
            cache_manifest(tmpdir, "core:mytool", make_tool(
                name="mytool",
                version="1.0.0",
                description="A cached tool",
                runtime={"type": "python", "script_path": "mytool.py"},
            ))

            # Now discover_projects should find it via cache
            found = discover_projects(projects_dir)
            names = [p["name"] for p in found]
            assert "mytool" in names

            cached_project = [p for p in found if p["name"] == "mytool"][0]
            assert cached_project["_cached"] is True
            assert cached_project["description"] == "A cached tool"

    def test_cache_manifest_accepts_entity(self):
        """Regression: cache_manifest must work when passed a DazzleEntity.

        The discovered-tool path (cmd_switch -> _switch_to_publish) passes a
        Tool ENTITY, not a dict. cache_manifest does `manifest.items()`, which
        crashed with AttributeError in v0.8.1 (the shim had no .items()). The
        prior tests only ever passed dict literals, so the crash was invisible.
        """
        from dazzlecmd.mode import cache_manifest, get_cached_manifest
        from dazzlecmd_lib.entity import build_entity

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = build_entity(
                {
                    "name": "mytool",
                    "namespace": "core",
                    "version": "1.0.0",
                    "description": "Entity tool",
                    "runtime": {"type": "python", "script_path": "mytool.py"},
                    "_fqcn": "core:mytool",         # computed key -> must be stripped
                    "_dir": os.path.join(tmpdir, "x"),
                },
                entity_type="tool",
            )

            # Must not raise (this is the regression).
            cache_manifest(tmpdir, "core:mytool", tool)

            cached = get_cached_manifest(tmpdir, "core:mytool")
            assert cached is not None
            assert cached["name"] == "mytool"
            assert cached["description"] == "Entity tool"
            assert cached["runtime"] == {"type": "python", "script_path": "mytool.py"}
            # computed _-prefixed keys are stripped on cache (as for dicts)
            assert not any(k.startswith("_") for k in cached)

    def test_on_disk_manifest_preferred_over_cache(self):
        """When .dazzlecmd.json exists on disk, cache is ignored."""
        from dazzlecmd.loader import discover_projects
        from dazzlecmd.mode import cache_manifest
        from dazzlecmd_lib.testing import make_tool

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
            cache_manifest(tmpdir, "core:mytool", make_tool(
                name="mytool",
                version="1.0.0",
                description="Cached version",
            ))

            found = discover_projects(projects_dir)
            project = [p for p in found if p["name"] == "mytool"][0]
            assert project["description"] == "On-disk version"
            # `cached` is now a promoted typed field (default False) -- an
            # on-disk tool is not loaded from cache. (Pre-promotion this was
            # `"_cached" not in project`; the field always exists now, so check
            # the value.)
            assert project["_cached"] is False

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


class TestModeSwitchEntityBehavior:
    """Drive the real cmd_switch flow with REAL DazzleEntity projects.

    The Phase 0 byte-identical gate covered `dz mode status` but never
    `dz mode switch`, and the unit tests passed dict literals -- so the
    `cache_manifest().items()` crash on an entity shipped undetected. These
    sandboxed behavioral tests close that gap: they pass discovered-style
    entities through cmd_switch in --dry-run, against a temp project_root and
    a temp config, never touching real submodules.
    """

    def _make_tool_entity(self, tmpdir):
        from dazzlecmd_lib.entity import build_entity
        tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
        os.makedirs(tool_dir)
        with open(os.path.join(tool_dir, "mytool.py"), "w") as f:
            f.write("# placeholder")
        return build_entity(
            {
                "name": "mytool",
                "namespace": "core",
                "version": "1.0.0",
                "description": "sandbox tool",
                "source": {"url": "https://example.com/mytool.git"},
                "runtime": {"type": "python", "script_path": "mytool.py"},
                "directory": tool_dir,   # promoted computed field (was "_dir")
                "_fqcn": "core:mytool",  # property-backed; stays in extra
            },
            entity_type="tool",
        )

    def test_switch_to_publish_dry_run_with_entity(self):
        """--publish --dry-run on an ENTITY runs the crash path and returns 0.

        cmd_switch -> _switch_to_publish -> cache_manifest(entity) executes
        BEFORE the dry-run gate, so this exercises the exact path that crashed
        in v0.8.1, then returns cleanly without any git/fs mutation.
        """
        from dazzlecmd_lib.mode import cmd_switch, get_cached_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = self._make_tool_entity(tmpdir)
            rc = cmd_switch(
                "mytool", [tool], tmpdir,
                force_mode="publish", dry_run=True,
                url="https://example.com/mytool.git",
                tools_dir="projects", command="dz", schema=None,
            )
            assert rc == 0
            # cache_manifest ran with the ENTITY (the crash path) and stored it
            cached = get_cached_manifest(tmpdir, "core:mytool")
            assert cached is not None
            assert cached["name"] == "mytool"
            assert not any(k.startswith("_") for k in cached)

    def test_switch_to_dev_dry_run_with_entity(self):
        """--dev --dry-run on an ENTITY plans a symlink without mutation."""
        from dazzlecmd_lib.mode import cmd_switch

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = self._make_tool_entity(tmpdir)
            dev_src = os.path.join(tmpdir, "devsrc")
            os.makedirs(dev_src)
            rc = cmd_switch(
                "mytool", [tool], tmpdir,
                dev_path=dev_src, force_mode="dev", dry_run=True,
                tools_dir="projects", command="dz", schema=None,
            )
            assert rc == 0

    def test_switch_to_dev_real_mutation_with_entity(self):
        """Non-dry-run --dev on an ENTITY actually creates the link.

        The stronger guard: exercises the full _switch_to_dev mutate path
        (rmtree the embedded dir -> create_link -> remember dev path) with a
        real entity, not just the dry-run plan. Sandboxed entirely in a temp
        dir; the created link is a junction/symlink to a temp source.
        """
        from dazzlecmd_lib.mode import cmd_switch
        from dazzlecmd_lib.core.links import is_linked_project

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = self._make_tool_entity(tmpdir)
            tool_dir = tool["_dir"]
            dev_src = os.path.join(tmpdir, "devsrc")
            os.makedirs(dev_src)
            with open(os.path.join(dev_src, "mytool.py"), "w") as f:
                f.write("# dev version")

            rc = cmd_switch(
                "mytool", [tool], tmpdir,
                dev_path=dev_src, force_mode="dev", dry_run=False, force=True,
                tools_dir="projects", command="dz", schema=None,
            )
            assert rc == 0
            # tool_dir is now a real link...
            assert is_linked_project(tool_dir)
            # ...and resolves to the dev source's content
            linked_file = os.path.join(tool_dir, "mytool.py")
            assert os.path.exists(linked_file)
            with open(linked_file) as f:
                assert f.read() == "# dev version"
