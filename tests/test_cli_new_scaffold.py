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
