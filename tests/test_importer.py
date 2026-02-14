"""Tests for dazzlecmd.importer — tool import and linking."""

import json
import os
import subprocess
import sys
import tempfile

import pytest

from dazzlecmd.importer import (
    add_from_local,
    is_linked_project,
    get_link_target,
    remove_link,
)


class TestIsLinkedProject:
    """Tests for symlink/junction detection."""

    def test_regular_dir_not_linked(self):
        """A regular directory is not a linked project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert not is_linked_project(tmpdir)

    def test_nonexistent_path_not_linked(self):
        """A nonexistent path is not a linked project."""
        assert not is_linked_project("/nonexistent/path/12345")


class TestAddFromLocal:
    """Tests for add_from_local import logic."""

    def test_missing_source_path(self):
        """Fails gracefully for non-existent source path."""
        with tempfile.TemporaryDirectory() as projects:
            result = add_from_local("/nonexistent/path", projects, "test")
            assert result is None

    def test_no_manifest(self):
        """Fails when .dazzlecmd.json is missing from source."""
        with tempfile.TemporaryDirectory() as source:
            with tempfile.TemporaryDirectory() as projects:
                result = add_from_local(source, projects, "test",
                                        link_mode="link")
                assert result is None

    def test_reserved_name_rejected(self):
        """Rejects tool names that conflict with reserved commands."""
        with tempfile.TemporaryDirectory() as source:
            with tempfile.TemporaryDirectory() as projects:
                manifest = {
                    "name": "add",
                    "version": "0.1.0",
                    "description": "Test"
                }
                manifest_path = os.path.join(source, ".dazzlecmd.json")
                with open(manifest_path, "w") as f:
                    json.dump(manifest, f)
                result = add_from_local(source, projects, "test",
                                        link_mode="link")
                assert result is None

    def test_link_creates_accessible_dir(self):
        """Linking creates a directory accessible through the link."""
        with tempfile.TemporaryDirectory() as source:
            with tempfile.TemporaryDirectory() as projects:
                # Create manifest and a test file in source
                manifest = {
                    "name": "testtool",
                    "version": "0.1.0",
                    "description": "Test tool"
                }
                with open(os.path.join(source, ".dazzlecmd.json"), "w") as f:
                    json.dump(manifest, f)
                with open(os.path.join(source, "test.py"), "w") as f:
                    f.write("print('hello')\n")

                result = add_from_local(source, projects, "test",
                                        link_mode="link")

                if result is None:
                    pytest.skip("Could not create link (permissions)")

                assert result["name"] == "testtool"
                assert result["namespace"] == "test"

                target = os.path.join(projects, "test", "testtool")
                assert os.path.isdir(target)

                # Verify files are accessible through the link
                assert os.path.isfile(os.path.join(target, ".dazzlecmd.json"))
                assert os.path.isfile(os.path.join(target, "test.py"))

                # Verify it's detected as a link
                assert is_linked_project(target)

                # Verify link target resolves
                link_target = get_link_target(target)
                assert link_target is not None

                # Cleanup
                remove_link(target)
                assert not os.path.exists(target)

    def test_duplicate_add_rejected(self):
        """Cannot add a tool that already exists."""
        with tempfile.TemporaryDirectory() as source:
            with tempfile.TemporaryDirectory() as projects:
                manifest = {
                    "name": "testtool",
                    "version": "0.1.0",
                    "description": "Test"
                }
                with open(os.path.join(source, ".dazzlecmd.json"), "w") as f:
                    json.dump(manifest, f)

                # First add
                result1 = add_from_local(source, projects, "test",
                                         link_mode="link")
                if result1 is None:
                    pytest.skip("Could not create link (permissions)")

                # Second add should fail
                result2 = add_from_local(source, projects, "test",
                                         link_mode="link")
                assert result2 is None

                # Cleanup
                target = os.path.join(projects, "test", "testtool")
                remove_link(target)

    def test_name_override(self):
        """--name overrides the manifest name."""
        with tempfile.TemporaryDirectory() as source:
            with tempfile.TemporaryDirectory() as projects:
                manifest = {
                    "name": "original",
                    "version": "0.1.0",
                    "description": "Test"
                }
                with open(os.path.join(source, ".dazzlecmd.json"), "w") as f:
                    json.dump(manifest, f)

                result = add_from_local(source, projects, "test",
                                        link_mode="link",
                                        tool_name="custom-name")
                if result is None:
                    pytest.skip("Could not create link (permissions)")

                assert result["name"] == "custom-name"
                target = os.path.join(projects, "test", "custom-name")
                assert os.path.isdir(target)

                # Cleanup
                remove_link(target)


class TestCliAdd:
    """Smoke tests for dz add CLI command."""

    def test_add_no_args_fails(self):
        """dz add with no arguments shows error."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzlecmd", "add"],
            capture_output=True, text=True
        )
        assert result.returncode != 0

    def test_add_nonexistent_repo_fails(self):
        """dz add with non-existent path fails."""
        result = subprocess.run(
            [sys.executable, "-m", "dazzlecmd", "add",
             "--repo", "/nonexistent/path/12345", "--link"],
            capture_output=True, text=True
        )
        assert result.returncode != 0
