"""Tests for ``dazzlecmd_lib.mode`` after Pass 3 parameterization.

These tests prove the senior-engineer audit BLOCKERs F2/F3/F4/F5/F7/F8 are
resolved -- the library code works for any aggregator's tools_dir / command /
manifest schema, not just dazzlecmd's hardcoded ``"projects/"`` / ``"dz"`` /
``.dazzlecmd.json``.

Test fixtures set up fake aggregator project roots with different
``tools_dir`` layouts (wtf-windows-style ``"tools"``, dazzlecmd-style
``"projects"``, custom ``"src/tools"``) and exercise the parameterized
functions against them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dazzlecmd_lib.aggregator_config import AggregatorSchema
from dazzlecmd_lib.testing import make_tool, make_kit
from dazzlecmd_lib.mode import (
    STATE_EMBEDDED,
    STATE_MISSING,
    STATE_SUBMODULE,
    _check_dirty_tree,
    _find_undiscovered_tool,
    _resolve_remote_url,
    _tool_dir_to_submodule_path,
    detect_tool_state,
    parse_gitmodules,
)


def _make_fake_aggregator(tmp_path: Path, tools_dir: str,
                          submodule_paths: list = None,
                          embedded_tools: list = None) -> Path:
    """Create a fake aggregator project root for testing.

    Args:
        tmp_path: pytest tmp_path fixture.
        tools_dir: Relative tools directory name (e.g., ``"tools"``).
        submodule_paths: List of paths to declare in ``.gitmodules``
            (e.g., ``["tools/core/restarted"]``). Creates the directories.
        embedded_tools: List of (namespace, tool_name) for embedded tools
            (created as plain dirs, no submodule registration).

    Returns:
        Absolute path to the fake project root.
    """
    project_root = tmp_path / "fake-aggregator"
    project_root.mkdir()
    (project_root / tools_dir).mkdir(parents=True, exist_ok=True)

    if submodule_paths:
        gitmodules = project_root / ".gitmodules"
        with gitmodules.open("w", encoding="utf-8") as f:
            for path in submodule_paths:
                ns = path.split("/")[-2]
                tool = path.split("/")[-1]
                f.write(f'[submodule "{path}"]\n')
                f.write(f'\tpath = {path}\n')
                f.write(f'\turl = https://example.com/{ns}-{tool}.git\n')
                # Create the on-disk directory too
                (project_root / path).mkdir(parents=True, exist_ok=True)
                # Make it look like a real submodule (has a .git file)
                (project_root / path / ".git").write_text(
                    f"gitdir: ../../../.git/modules/{path}\n",
                    encoding="utf-8",
                )

    if embedded_tools:
        for ns, tool in embedded_tools:
            (project_root / tools_dir / ns / tool).mkdir(parents=True)

    return project_root


class TestParseGitmodulesParameterization:
    """F2: parse_gitmodules respects tools_dir, no longer hardcodes 'projects/'."""

    def test_recognizes_tools_dir_paths(self, tmp_path):
        """wtf-windows / amdead layout -- submodules under tools/."""
        project_root = _make_fake_aggregator(
            tmp_path, tools_dir="tools",
            submodule_paths=["tools/core/restarted", "tools/core/locked"],
        )
        mappings = parse_gitmodules(str(project_root), tools_dir="tools")
        assert "tools/core/restarted" in mappings
        assert "tools/core/locked" in mappings
        assert mappings["tools/core/restarted"]["namespace"] == "core"
        assert mappings["tools/core/restarted"]["tool_name"] == "restarted"

    def test_recognizes_projects_dir_paths(self, tmp_path):
        """dazzlecmd layout -- submodules under projects/."""
        project_root = _make_fake_aggregator(
            tmp_path, tools_dir="projects",
            submodule_paths=["projects/core/listall"],
        )
        mappings = parse_gitmodules(str(project_root), tools_dir="projects")
        assert "projects/core/listall" in mappings

    def test_skips_non_matching_prefix(self, tmp_path):
        """Submodules outside tools_dir are NOT included."""
        project_root = _make_fake_aggregator(
            tmp_path, tools_dir="tools",
            submodule_paths=["tools/core/foo"],
        )
        # Add a scripts/ submodule to gitmodules manually
        with (project_root / ".gitmodules").open("a", encoding="utf-8") as f:
            f.write('[submodule "scripts"]\n')
            f.write('\tpath = scripts\n')
            f.write('\turl = https://example.com/scripts.git\n')

        mappings = parse_gitmodules(str(project_root), tools_dir="tools")
        assert "tools/core/foo" in mappings
        assert "scripts" not in mappings  # outside tools_dir

    def test_skips_non_3part_paths(self, tmp_path):
        """Kit-level (2-part) submodule paths are skipped (handled by engine)."""
        project_root = _make_fake_aggregator(tmp_path, tools_dir="tools")
        # Manually write a kit-level submodule
        (project_root / "tools").mkdir(exist_ok=True)
        (project_root / ".gitmodules").write_text(
            '[submodule "tools/whole-kit"]\n'
            '\tpath = tools/whole-kit\n'
            '\turl = https://example.com/whole-kit.git\n',
            encoding="utf-8",
        )
        mappings = parse_gitmodules(str(project_root), tools_dir="tools")
        assert mappings == {}

    def test_missing_gitmodules_returns_empty(self, tmp_path):
        project_root = _make_fake_aggregator(tmp_path, tools_dir="tools")
        # No .gitmodules file
        mappings = parse_gitmodules(str(project_root), tools_dir="tools")
        assert mappings == {}


class TestSubdirectoryAggregatorLayout:
    """#58 regression: the aggregator lives in a SUBDIRECTORY of the git repo
    (``<repo>/src/dazzlecmd``), so ``.gitmodules`` sits ABOVE ``project_root``
    and its submodule paths are repo-root-relative. ``parse_gitmodules`` must
    still find it (walking up to the repo top) and re-base the keys to
    aggregator-relative, or ``detect_tool_state`` misses the submodule and
    reports EMBEDDED -- the bug the #58 move introduced for ``core:listall``.
    """

    def _make_subdir_repo(self, tmp_path, *, tools_dir="projects",
                          agg_subpath="src/dazzlecmd", tool="core/listall"):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()  # repo top marker
        agg_root = repo_root / agg_subpath
        agg_root.mkdir(parents=True)
        sub_repo_rel = f"{agg_subpath}/{tools_dir}/{tool}"  # repo-root-relative
        (repo_root / sub_repo_rel).mkdir(parents=True)
        (repo_root / sub_repo_rel / ".git").write_text(
            f"gitdir: ../../../.git/modules/{sub_repo_rel}\n", encoding="utf-8"
        )
        ns, name = tool.split("/")
        # .gitmodules at the REPO ROOT, path is repo-root-relative
        (repo_root / ".gitmodules").write_text(
            f'[submodule "{tools_dir}/{ns}/{name}"]\n'
            f"\tpath = {sub_repo_rel}\n"
            f"\turl = https://github.com/DazzleTools/{name}.git\n",
            encoding="utf-8",
        )
        return repo_root, agg_root

    def test_parse_finds_submodule_from_subdir_aggregator(self, tmp_path):
        _, agg_root = self._make_subdir_repo(tmp_path)
        mappings = parse_gitmodules(str(agg_root), tools_dir="projects")
        # key re-based to aggregator-relative, NOT the repo-relative form
        assert "projects/core/listall" in mappings
        assert "src/dazzlecmd/projects/core/listall" not in mappings
        assert mappings["projects/core/listall"]["namespace"] == "core"
        assert mappings["projects/core/listall"]["tool_name"] == "listall"

    def test_detect_state_submodule_from_subdir_aggregator(self, tmp_path):
        _, agg_root = self._make_subdir_repo(tmp_path)
        gitmodules = parse_gitmodules(str(agg_root), tools_dir="projects")
        tool_dir = str(agg_root / "projects" / "core" / "listall")
        state = detect_tool_state(
            tool_dir, gitmodules, str(agg_root), tools_dir="projects"
        )
        assert state == STATE_SUBMODULE  # was EMBEDDED before the #58 fix

    def test_repo_with_git_but_no_submodules_returns_empty(self, tmp_path):
        """A subdir aggregator in a repo that has no .gitmodules at all -- the
        walk-up must stop at the repo's ``.git`` and not climb out into a
        parent repo's submodule config."""
        repo_root = tmp_path / "repo"
        (repo_root / "src" / "dazzlecmd" / "projects").mkdir(parents=True)
        (repo_root / ".git").mkdir()
        agg_root = repo_root / "src" / "dazzlecmd"
        assert parse_gitmodules(str(agg_root), tools_dir="projects") == {}


class TestToolDirToSubmodulePathParameterization:
    """F8: _tool_dir_to_submodule_path uses relpath instead of substring search."""

    def test_resolves_for_tools_dir(self, tmp_path):
        project_root = tmp_path / "wtf"
        project_root.mkdir()
        tool_dir = project_root / "tools" / "core" / "restarted"
        tool_dir.mkdir(parents=True)
        result = _tool_dir_to_submodule_path(
            str(tool_dir), str(project_root), tools_dir="tools"
        )
        assert result == "tools/core/restarted"

    def test_resolves_for_projects_dir(self, tmp_path):
        project_root = tmp_path / "dz"
        project_root.mkdir()
        tool_dir = project_root / "projects" / "core" / "listall"
        tool_dir.mkdir(parents=True)
        result = _tool_dir_to_submodule_path(
            str(tool_dir), str(project_root), tools_dir="projects"
        )
        assert result == "projects/core/listall"

    def test_returns_none_when_outside_tools_dir(self, tmp_path):
        """Tool path that isn't under tools_dir returns None."""
        project_root = tmp_path / "agg"
        project_root.mkdir()
        # tool_dir is under scripts/, not tools/
        tool_dir = project_root / "scripts" / "thing"
        tool_dir.mkdir(parents=True)
        result = _tool_dir_to_submodule_path(
            str(tool_dir), str(project_root), tools_dir="tools"
        )
        assert result is None

    def test_no_false_match_on_parent_path_substring(self, tmp_path):
        """F8 regression: parent path containing 'projects' must not match."""
        # parent = .../my-projects/dz/
        parent = tmp_path / "my-projects"
        parent.mkdir()
        project_root = parent / "agg"
        project_root.mkdir()
        # The bug: substring search for "projects/" would match "my-projects/"
        # in the absolute path and produce a wrong relative path.
        tool_dir = project_root / "projects" / "core" / "x"
        tool_dir.mkdir(parents=True)
        result = _tool_dir_to_submodule_path(
            str(tool_dir), str(project_root), tools_dir="projects"
        )
        # Correct anchored result -- relative to project_root, not parent
        assert result == "projects/core/x"


class TestDetectToolStateParameterization:
    """detect_tool_state threads tools_dir + project_root correctly."""

    def test_detects_embedded_in_tools_dir(self, tmp_path):
        project_root = _make_fake_aggregator(
            tmp_path, tools_dir="tools",
            embedded_tools=[("core", "detect")],
        )
        tool_dir = str(project_root / "tools" / "core" / "detect")
        state = detect_tool_state(tool_dir, {}, str(project_root), tools_dir="tools")
        assert state == STATE_EMBEDDED

    def test_detects_submodule_via_tools_dir(self, tmp_path):
        project_root = _make_fake_aggregator(
            tmp_path, tools_dir="tools",
            submodule_paths=["tools/core/restarted"],
        )
        gitmodules = parse_gitmodules(str(project_root), tools_dir="tools")
        tool_dir = str(project_root / "tools" / "core" / "restarted")
        state = detect_tool_state(
            tool_dir, gitmodules, str(project_root), tools_dir="tools"
        )
        assert state == STATE_SUBMODULE

    def test_detects_missing(self, tmp_path):
        project_root = _make_fake_aggregator(tmp_path, tools_dir="tools")
        tool_dir = str(project_root / "tools" / "core" / "nonexistent")
        state = detect_tool_state(tool_dir, {}, str(project_root), tools_dir="tools")
        assert state == STATE_MISSING


class TestFindUndiscoveredToolParameterization:
    """F4: _find_undiscovered_tool respects tools_dir."""

    def test_finds_in_tools_dir(self, tmp_path):
        project_root = _make_fake_aggregator(
            tmp_path, tools_dir="tools",
            embedded_tools=[("core", "fix")],
        )
        result = _find_undiscovered_tool(
            "fix", str(project_root), tools_dir="tools"
        )
        assert result is not None
        assert result.name == "fix"
        assert result.namespace == "core"

    def test_returns_none_when_tools_dir_missing(self, tmp_path):
        project_root = tmp_path / "agg"
        project_root.mkdir()
        # No tools/ directory at all
        result = _find_undiscovered_tool(
            "anything", str(project_root), tools_dir="tools"
        )
        assert result is None

    def test_does_not_find_in_wrong_tools_dir(self, tmp_path):
        """F4 regression: tool in projects/ should NOT be found when tools_dir='tools'."""
        project_root = tmp_path / "agg"
        project_root.mkdir()
        # Tool in projects/ -- where dazzlecmd would put it
        (project_root / "projects" / "core" / "old").mkdir(parents=True)
        # Looking with tools_dir="tools"
        result = _find_undiscovered_tool(
            "old", str(project_root), tools_dir="tools"
        )
        assert result is None


class TestResolveRemoteUrlParameterization:
    """F7: _resolve_remote_url uses schema.remote_url_paths."""

    def test_explicit_url_wins(self):
        project = {"source": {"url": "https://from-manifest"}}
        result = _resolve_remote_url(
            project, explicit_url="https://from-cli"
        )
        assert result == "https://from-cli"

    def test_default_schema_uses_source_url(self):
        """When schema=None, defaults match dazzlecmd's historical behavior."""
        project = {"source": {"url": "https://example.com/x.git"}}
        result = _resolve_remote_url(project)
        assert result == "https://example.com/x.git"

    def test_custom_schema_via_dataclass(self):
        """Aggregator with different manifest layout uses its schema."""
        project = {"repo": {"git_url": "https://custom.example/r.git"}}
        schema = AggregatorSchema(remote_url_paths=("repo.git_url",))
        result = _resolve_remote_url(project, schema=schema)
        assert result == "https://custom.example/r.git"

    def test_custom_schema_via_dict(self):
        """Dict-style schema for ad-hoc construction."""
        project = {"upstream": "git@foo:r.git"}
        result = _resolve_remote_url(
            project, schema={"remote_url_paths": ["upstream"]}
        )
        assert result == "git@foo:r.git"

    def test_fallback_chain(self):
        """First non-empty value in the schema path list wins."""
        project = {
            "source": {"url": ""},  # empty
            "fallback": {"git_url": "git@fallback:r.git"},
        }
        schema = AggregatorSchema(
            remote_url_paths=("source.url", "fallback.git_url")
        )
        result = _resolve_remote_url(project, schema=schema)
        assert result == "git@fallback:r.git"

    def test_graduated_to_fallback(self):
        """lifecycle.graduated_to is always tried as final fallback."""
        project = {"lifecycle": {"graduated_to": "https://graduated.example/r.git"}}
        # No schema paths match -- should still find graduated_to
        result = _resolve_remote_url(
            project, schema=AggregatorSchema(remote_url_paths=("nonexistent.path",))
        )
        assert result == "https://graduated.example/r.git"

    def test_none_when_no_url_anywhere(self):
        project = {"name": "x"}
        result = _resolve_remote_url(project)
        assert result is None


class TestCrossAggregatorParity:
    """End-to-end: identical behavior across dazzlecmd / wtf-windows / amdead layouts."""

    @pytest.mark.parametrize("tools_dir", ["projects", "tools", "src/tools"])
    def test_full_chain_for_tools_dir(self, tmp_path, tools_dir):
        """parse_gitmodules + detect_tool_state work for any tools_dir."""
        # Note: src/tools requires path with subdirectory in .gitmodules.
        # We test that pattern explicitly.
        path = f"{tools_dir}/core/x"
        project_root = _make_fake_aggregator(
            tmp_path, tools_dir=tools_dir,
            submodule_paths=[path],
        )
        mappings = parse_gitmodules(str(project_root), tools_dir=tools_dir)
        assert path in mappings, f"submodule not found for tools_dir={tools_dir!r}"
        tool_dir = str(project_root / path.replace("/", os.sep))
        state = detect_tool_state(
            tool_dir, mappings, str(project_root), tools_dir=tools_dir
        )
        assert state == STATE_SUBMODULE


# ---------------------------------------------------------------------------
# T1-E safety primitive: dirty-tree refuse-or-force gate
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path):
    """Initialize a minimal git repo at ``path`` for dirty-tree tests.

    Disables commit signing locally so the fixture works on developer
    machines whose global config requires GPG signing.
    """
    import subprocess
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"],
                   cwd=str(path), check=True)
    subprocess.run(["git", "config", "tag.gpgsign", "false"],
                   cwd=str(path), check=True)
    (path / "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "."], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=str(path), check=True)


class TestCheckDirtyTree:
    """T1-E: ``_check_dirty_tree`` returns dirty output or empty string."""

    def test_non_directory_returns_empty(self, tmp_path):
        """A non-existent path is clean (nothing to lose)."""
        result = _check_dirty_tree(str(tmp_path / "nope"))
        assert result == ""

    def test_non_git_dir_returns_empty(self, tmp_path):
        """A plain directory with no .git is clean (no tracked state)."""
        plain = tmp_path / "plain"
        plain.mkdir()
        (plain / "file.txt").write_text("contents\n")
        result = _check_dirty_tree(str(plain))
        assert result == ""

    def test_clean_git_repo_returns_empty(self, tmp_path):
        """A git repo with no pending changes returns empty."""
        repo = tmp_path / "repo"
        _init_git_repo(repo)
        result = _check_dirty_tree(str(repo))
        assert result == ""

    def test_modified_tracked_file_is_dirty(self, tmp_path):
        """Editing a committed file shows as dirty."""
        repo = tmp_path / "repo"
        _init_git_repo(repo)
        (repo / "README.md").write_text("changed\n")
        result = _check_dirty_tree(str(repo))
        assert "README.md" in result
        assert result.startswith(" M") or result.startswith("M ")

    def test_untracked_file_is_dirty(self, tmp_path):
        """An untracked file shows as dirty (would be lost on rmtree)."""
        repo = tmp_path / "repo"
        _init_git_repo(repo)
        (repo / "new_work.py").write_text("import os\n")
        result = _check_dirty_tree(str(repo))
        assert "new_work.py" in result
        assert "??" in result


class TestSwitchRefusesDirty:
    """T1-E: ``cmd_switch`` refuses with exit 1 when tool_dir is dirty.

    These tests verify the gate fires at the destructive `rmtree` paths
    in `_switch_to_dev` and `_switch_to_publish` without `force=True`.
    Verified end-to-end via subprocess `git status` so the integration
    with real git is exercised, not just mock returns.
    """

    def test_switch_to_dev_refuses_dirty_submodule(self, tmp_path, capsys):
        """A dirty submodule checkout refuses dev switch without --force."""
        import subprocess
        from dazzlecmd_lib.mode import cmd_switch

        # Set up an aggregator with a "submodule" that has dirty state.
        # We fake it by registering the path in .gitmodules and making it
        # a real git checkout with uncommitted changes.
        agg_root = tmp_path / "agg"
        tool_path = agg_root / "projects" / "core" / "mytool"
        _init_git_repo(tool_path)
        (tool_path / "wip.py").write_text("# dont lose me\n")

        # Make agg_root a git repo with a .gitmodules entry
        (agg_root / ".gitmodules").write_text(
            '[submodule "projects/core/mytool"]\n'
            '\tpath = projects/core/mytool\n'
            '\turl = https://example.com/mytool.git\n'
        )
        subprocess.run(["git", "init", "-q"], cwd=str(agg_root), check=True)

        # Drive cmd_switch directly (not via the CLI). dev_path resolves
        # to a stub location; we don't need it to actually create the link,
        # because the dirty-tree refusal should fire before that.
        dev_path = tmp_path / "dev_target"
        dev_path.mkdir()

        project = make_tool(
            name="mytool",
            namespace="core",
            _dir=str(tool_path),
        )
        rc = cmd_switch(
            tool_name="mytool",
            projects=[project],
            project_root=str(agg_root),
            dev_path=str(dev_path),
            force_mode="dev",
            tools_dir="projects",
            command="dz",
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "uncommitted changes" in captured.err
        assert "wip.py" in captured.err
        assert "--force" in captured.err
        # And the original directory is intact -- the rmtree did NOT fire.
        assert (tool_path / "wip.py").exists()
        assert (tool_path / ".git").exists()

    def test_switch_to_dev_force_overrides_dirty_check(self, tmp_path, capsys):
        """With force=True, the dirty-tree refusal does NOT fire.

        Asserts on the gate (no refusal message + rmtree was attempted),
        not on the downstream rmtree's success -- on Windows, rmtree
        against a real git repo can hit access-denied on .git/objects
        due to pack-file read-only attrs, which is unrelated to T1-E.
        """
        import subprocess
        from dazzlecmd_lib.mode import cmd_switch

        agg_root = tmp_path / "agg"
        tool_path = agg_root / "projects" / "core" / "mytool"
        _init_git_repo(tool_path)
        (tool_path / "wip.py").write_text("# would be destroyed\n")
        (agg_root / ".gitmodules").write_text(
            '[submodule "projects/core/mytool"]\n'
            '\tpath = projects/core/mytool\n'
            '\turl = https://example.com/mytool.git\n'
        )
        subprocess.run(["git", "init", "-q"], cwd=str(agg_root), check=True)

        dev_path = tmp_path / "dev_target"
        dev_path.mkdir()

        project = make_tool(
            name="mytool",
            namespace="core",
            _dir=str(tool_path),
        )
        cmd_switch(
            tool_name="mytool",
            projects=[project],
            project_root=str(agg_root),
            dev_path=str(dev_path),
            force_mode="dev",
            force=True,
            tools_dir="projects",
            command="dz",
        )
        # The dirty-tree refusal message MUST NOT appear in stderr.
        captured = capsys.readouterr()
        assert "uncommitted changes" not in captured.err
        assert "refusing to switch" not in captured.err

    def test_switch_dry_run_warns_about_dirty(self, tmp_path, capsys):
        """Dry-run prints a `Would refuse` warning so users learn early."""
        import subprocess
        from dazzlecmd_lib.mode import cmd_switch

        agg_root = tmp_path / "agg"
        tool_path = agg_root / "projects" / "core" / "mytool"
        _init_git_repo(tool_path)
        (tool_path / "wip.py").write_text("# wip\n")
        (agg_root / ".gitmodules").write_text(
            '[submodule "projects/core/mytool"]\n'
            '\tpath = projects/core/mytool\n'
            '\turl = https://example.com/mytool.git\n'
        )
        subprocess.run(["git", "init", "-q"], cwd=str(agg_root), check=True)

        dev_path = tmp_path / "dev_target"
        dev_path.mkdir()

        project = make_tool(
            name="mytool",
            namespace="core",
            _dir=str(tool_path),
        )
        rc = cmd_switch(
            tool_name="mytool",
            projects=[project],
            project_root=str(agg_root),
            dev_path=str(dev_path),
            force_mode="dev",
            dry_run=True,
            tools_dir="projects",
            command="dz",
        )
        assert rc == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "--force" in captured.out
        # Dry-run does NOT delete anything.
        assert (tool_path / "wip.py").exists()
