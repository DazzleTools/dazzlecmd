"""Tests for `dz new kit` and `dz new aggregator` (4d-2, Tier 2B.1).

Per the Tier-2 synthesis (OQ-A2): a KIT is a directory of tools registered
into the parent's discovery (local form); an AGGREGATOR is always a standalone
project with its own dispatch. Both functions are exercised against sandbox
roots -- never the real repo (the dz CLI anchors to its own package, so these
call the implementation functions directly).
"""
import json
import os
import subprocess
import sys
from argparse import Namespace

import pytest

from dazzlecmd.cli import _cmd_new_kit, _cmd_new_aggregator


def _kit_args(name, **kw):
    return Namespace(name=name, description=kw.get("description", ""),
                     with_starter=kw.get("with_starter", False))


def _agg_args(name, **kw):
    return Namespace(
        name=name, command=kw.get("command"), description=kw.get("description", ""),
        tools_dir=kw.get("tools_dir"), manifest=kw.get("manifest"),
        with_starter=kw.get("with_starter", False),
        with_components=kw.get("with_components"),
    )


# -- dz new kit --------------------------------------------------------------

class TestNewKit:
    def test_creates_manifest_and_registry_pointer(self, tmp_path):
        root = str(tmp_path)
        assert _cmd_new_kit(_kit_args("mykit", description="my desc"), root) == 0
        manifest = json.load(open(tmp_path / "projects" / "mykit" / ".kit.json"))
        assert manifest["name"] == "mykit"
        assert manifest["description"] == "my desc"
        assert manifest["tools"] == []
        registry = json.load(open(tmp_path / "kits" / "mykit.kit.json"))
        assert registry["name"] == "mykit"
        assert registry["always_active"] is False  # opt-in activation

    def test_with_starter_adds_hello_tool(self, tmp_path):
        root = str(tmp_path)
        assert _cmd_new_kit(_kit_args("mykit", with_starter=True), root) == 0
        hello = tmp_path / "projects" / "mykit" / "hello"
        assert (hello / ".dazzlecmd.json").is_file()
        tool_manifest = json.load(open(hello / ".dazzlecmd.json"))
        assert tool_manifest["name"] == "hello"
        assert tool_manifest["namespace"] == "mykit"
        kit_manifest = json.load(open(tmp_path / "projects" / "mykit" / ".kit.json"))
        assert "mykit:hello" in kit_manifest["tools"]

    def test_refuses_existing(self, tmp_path):
        root = str(tmp_path)
        assert _cmd_new_kit(_kit_args("dup"), root) == 0
        assert _cmd_new_kit(_kit_args("dup"), root) == 1  # second time refused

    def test_rejects_bad_name(self, tmp_path):
        assert _cmd_new_kit(_kit_args("9bad name!"), str(tmp_path)) == 1
        assert not (tmp_path / "projects").exists()


# -- dz new aggregator -------------------------------------------------------

class TestNewAggregator:
    def _generate(self, tmp_path, monkeypatch, name="AggDemo", **kw):
        monkeypatch.chdir(tmp_path)  # target is cwd-relative by design
        assert _cmd_new_aggregator(_agg_args(name, **kw)) == 0
        return tmp_path / name

    def test_generates_standalone_project(self, tmp_path, monkeypatch):
        target = self._generate(tmp_path, monkeypatch)
        for rel in ("aggregator.json", "pyproject.toml", "README.md",
                    ".gitignore", "src/aggdemo/cli.py", "src/aggdemo/_version.py",
                    "src/aggdemo/__init__.py", "tests/test_cli_smoke.py",
                    "projects", "kits"):
            assert (target / rel).exists(), rel

    def test_aggregator_json_identity(self, tmp_path, monkeypatch):
        target = self._generate(tmp_path, monkeypatch, name="My-Tools",
                                command="mt", tools_dir="tools",
                                manifest=".mt.json")
        cfg = json.load(open(target / "aggregator.json"))
        assert cfg["name"] == "My-Tools"
        assert cfg["command"] == "mt"
        assert cfg["tools_dir"] == "tools"
        assert cfg["manifest_name"] == ".mt.json"
        assert (target / "tools").is_dir()  # tools_dir honored on disk

    def test_generated_cli_compiles_and_has_nest_stub(self, tmp_path, monkeypatch):
        import py_compile
        target = self._generate(tmp_path, monkeypatch)
        cli = target / "src" / "aggdemo" / "cli.py"
        py_compile.compile(str(cli), doraise=True)
        src = cli.read_text(encoding="utf-8")
        assert "# engine.meta_registry.nest_all_under(" in src  # OQ-E stub
        assert "{name" not in src  # all placeholders substituted

    def test_generated_aggregator_runs_end_to_end(self, tmp_path, monkeypatch):
        """The generated project's own CLI discovers + lists its starter tool
        (the v0.7.42 acceptance: a working aggregator out of the box)."""
        target = self._generate(tmp_path, monkeypatch, with_starter=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(target / "src") + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, "-m", "aggdemo.cli", "list"],
            capture_output=True, text=True, env=env, cwd=str(target),
        )
        assert result.returncode == 0, result.stderr
        assert "hello" in result.stdout

    def test_refuses_existing_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        os.makedirs(tmp_path / "Taken")
        assert _cmd_new_aggregator(_agg_args("Taken")) == 1

    def test_inside_existing_aggregator_warns_and_never_clobbers(
            self, tmp_path, monkeypatch, capsys):
        """Running from INSIDE an existing aggregator must never touch the
        host: existing dirs are refused, the host's aggregator.json is
        untouched, and a loud nesting note goes to stderr (the scaffold is
        allowed -- non-destructive, occasionally intentional)."""
        host = tmp_path / "hostagg"
        os.makedirs(host / "projects")
        os.makedirs(host / "kits")
        host_manifest = host / "aggregator.json"
        host_manifest.write_text(
            '{"_schema_version": 1, "name": "hostagg", "command": "ha", '
            '"tools_dir": "projects", "kits_dir": "kits", '
            '"manifest_name": ".dazzlecmd.json"}',
            encoding="utf-8",
        )
        before = host_manifest.read_text(encoding="utf-8")
        monkeypatch.chdir(host)

        # Colliding with the host's structural dirs is refused outright.
        assert _cmd_new_aggregator(_agg_args("projects")) == 1
        assert _cmd_new_aggregator(_agg_args("kits")) == 1
        capsys.readouterr()

        # A fresh name succeeds, nested, with the warning on stderr.
        assert _cmd_new_aggregator(_agg_args("Nested")) == 0
        err = capsys.readouterr().err
        assert "inside the aggregator at" in err
        assert "NESTED" in err
        assert (host / "Nested" / "aggregator.json").is_file()
        # Host untouched.
        assert host_manifest.read_text(encoding="utf-8") == before
        assert sorted(os.listdir(host / "projects")) == []


class TestWithComponents:
    """4d-5: the --with composable scaffolding framework (best-effort, OQ-D1)."""

    def test_parse_expands_all_and_dedups(self):
        from dazzlecmd.cli import _parse_with_spec
        assert _parse_with_spec("docker-test,ci,docker-test") == ["docker-test", "ci"]
        assert _parse_with_spec("all") == [
            "common", "template", "docker-test", "docker-deploy", "ci"]
        assert _parse_with_spec(None) == []
        with pytest.raises(ValueError):
            _parse_with_spec("nope")

    def test_unknown_component_fails_before_any_writes(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert _cmd_new_aggregator(_agg_args("W0", with_components="bogus")) == 1
        assert not (tmp_path / "W0").exists()

    def test_docker_and_ci_components_apply(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert _cmd_new_aggregator(
            _agg_args("W1", with_components="docker-test,docker-deploy,ci")) == 0
        t = tmp_path / "W1"
        for rel in ("Dockerfile.test", "docker-compose.test.yml", "Dockerfile",
                    ".github/workflows/test.yml", ".github/workflows/release.yml"):
            assert (t / rel).is_file(), rel
        # placeholders substituted, GitHub ${{ }} syntax untouched
        df = (t / "Dockerfile.test").read_text(encoding="utf-8")
        assert "w1-test" in df and "{name" not in df
        ci = (t / ".github/workflows/test.yml").read_text(encoding="utf-8")
        assert "${{ matrix.os }}" in ci
        assert "ok: docker-test, docker-deploy, ci" in capsys.readouterr().out

    def test_all_is_best_effort_with_summary(self, tmp_path, monkeypatch, capsys):
        """`all` composes best-effort. Hermetic: repokit URLs point at
        nonexistent LOCAL paths so `common` fails fast offline and `template`
        falls through to the bundled fallback (4d-6 OQ-G)."""
        from dazzlecmd import cli as _cli
        monkeypatch.setattr(_cli, "_resolve_new_defaults", lambda e: {
            "repokit_common_url": str(tmp_path / "no_such_remote"),
            "repokit_template_url": str(tmp_path / "no_such_template"),
        })
        monkeypatch.chdir(tmp_path)
        assert _cmd_new_aggregator(_agg_args("W2", with_components="all")) == 0
        out = capsys.readouterr().out
        assert "docker-test" in out and "ci" in out
        assert "skipped: common" in out                  # offline -> hint
        assert "FALLBACK-MINIMAL" in out                 # template fell back
        t = tmp_path / "W2"
        assert (t / "Dockerfile.test").is_file()
        assert (t / "LICENSE").is_file()                 # bundled fallback
        assert (t / "CONTRIBUTING.md").is_file()


class TestRepoKitComponents:
    """4d-6: the real common/template appliers (hermetic -- local sources)."""

    def _local_remote(self, tmp_path):
        """A local git repo standing in for git-repokit-common."""
        import subprocess
        remote = tmp_path / "fake_repokit_common"
        os.makedirs(remote / "hooks")
        (remote / "install-hooks.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        for cmd in (["git", "init", "-q", "-b", "main"],
                    ["git", "config", "commit.gpgsign", "false"],
                    ["git", "config", "tag.gpgsign", "false"],
                    ["git", "add", "-A"],
                    ["git", "-c", "user.name=t", "-c", "user.email=t@t",
                     "commit", "-q", "-m", "x"]):
            subprocess.run(cmd, cwd=str(remote), check=True,
                           capture_output=True)
        return remote

    def test_with_common_subtree_from_local_remote(self, tmp_path, monkeypatch,
                                                   capsys):
        from dazzlecmd import cli as _cli
        remote = self._local_remote(tmp_path)
        monkeypatch.setattr(_cli, "_resolve_new_defaults", lambda e: {
            "repokit_common_url": str(remote)})
        monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
        monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
        monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
        monkeypatch.chdir(tmp_path)
        assert _cmd_new_aggregator(_agg_args("WC", with_components="common")) == 0
        out = capsys.readouterr().out
        assert "ok: common" in out
        assert "initialized git repository" in out       # fresh scaffold path
        t = tmp_path / "WC"
        assert (t / "scripts" / "install-hooks.sh").is_file()
        assert (t / ".git").exists()

    def test_with_template_local_path_no_clobber(self, tmp_path, monkeypatch,
                                                 capsys):
        from dazzlecmd import cli as _cli
        src = tmp_path / "tmpl_src"
        os.makedirs(src)
        (src / "LICENSE.tmpl").write_text("License for {name}\n", encoding="utf-8")
        (src / "README.md").write_text("TEMPLATE README\n", encoding="utf-8")
        monkeypatch.setattr(_cli, "_resolve_new_defaults", lambda e: {
            "repokit_template_path": str(src)})
        monkeypatch.chdir(tmp_path)
        assert _cmd_new_aggregator(_agg_args("WT", with_components="template")) == 0
        t = tmp_path / "WT"
        assert (t / "LICENSE").read_text(encoding="utf-8") == "License for WT\n"
        # never clobber: the scaffold's README wins over the template's
        assert "TEMPLATE README" not in (t / "README.md").read_text(encoding="utf-8")
        assert "source: local path" in capsys.readouterr().out
