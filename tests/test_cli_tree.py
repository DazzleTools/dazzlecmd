"""Tests for the dz tree command (Phase 3)."""

import io
import json
import os

import pytest

from dazzlecmd.engine import AggregatorEngine, FQCNIndex
from dazzlecmd.cli import _cmd_tree


class _Args:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _mk_engine_with_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
    engine = AggregatorEngine(
        name="dazzlecmd", command="dz",
        tools_dir="projects", kits_dir="kits",
        manifest=".dazzlecmd.json",
        version_info=("0.7.10", "0.7.10_test"),
    )
    engine.project_root = str(tmp_path)
    engine.kits = [
        {"_kit_name": "core", "name": "core", "always_active": True, "tools": []},
        {"_kit_name": "wtf", "name": "wtf", "always_active": False, "tools": []},
    ]
    engine.projects = [
        {
            "name": "fixpath",
            "_fqcn": "core:fixpath",
            "_short_name": "fixpath",
            "_kit_import_name": "core",
            "description": "Fix mangled paths",
        },
        {
            "name": "rn",
            "_fqcn": "core:rn",
            "_short_name": "rn",
            "_kit_import_name": "core",
            "description": "Rename files using regex",
        },
        {
            "name": "locked",
            "_fqcn": "wtf:core:locked",
            "_short_name": "locked",
            "_kit_import_name": "wtf",
            "description": "Windows lockout diagnostics",
        },
    ]
    return engine


class TestDzTreeASCII:

    def test_basic_ascii_output(self, tmp_path, monkeypatch, capsys):
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        rc = _cmd_tree(_Args(json=False, depth=None, kit=None, show_disabled=False), engine)
        assert rc == 0
        out = capsys.readouterr().out
        assert "dz" in out
        assert "core" in out
        assert "wtf" in out
        assert "core:fixpath" in out
        assert "wtf:core:locked" in out
        assert "3 tools across 2 kit(s)" in out

    def test_ascii_uses_plain_chars(self, tmp_path, monkeypatch, capsys):
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        _cmd_tree(_Args(json=False, depth=None, kit=None, show_disabled=False), engine)
        out = capsys.readouterr().out
        # No unicode box-drawing characters
        assert "+--" in out or "\\--" in out
        assert "\u2514" not in out  # BOX DRAWINGS LIGHT UP AND RIGHT
        assert "\u251c" not in out  # BOX DRAWINGS LIGHT VERTICAL AND RIGHT

    def test_depth_zero_hides_tools(self, tmp_path, monkeypatch, capsys):
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        _cmd_tree(_Args(json=False, depth=1, kit=None, show_disabled=False), engine)
        out = capsys.readouterr().out
        # Depth 1 shows kits but not tools
        assert "core" in out
        assert "wtf" in out
        assert "core:fixpath" not in out

    def test_kit_filter(self, tmp_path, monkeypatch, capsys):
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        _cmd_tree(_Args(json=False, depth=None, kit="core", show_disabled=False), engine)
        out = capsys.readouterr().out
        assert "core:fixpath" in out
        assert "wtf:core:locked" not in out

    def test_kit_filter_not_found(self, tmp_path, monkeypatch, capsys):
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        rc = _cmd_tree(_Args(json=False, depth=None, kit="ghost", show_disabled=False), engine)
        assert rc == 1

    def test_disabled_kit_hidden_by_default(self, tmp_path, monkeypatch, capsys):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"disabled_kits": ["wtf"]}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        _cmd_tree(_Args(json=False, depth=None, kit=None, show_disabled=False), engine)
        out = capsys.readouterr().out
        assert "wtf" not in out or "wtf:core:locked" not in out

    def test_disabled_kit_shown_with_flag(self, tmp_path, monkeypatch, capsys):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"disabled_kits": ["wtf"]}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DAZZLECMD_CONFIG", str(config_path))
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        _cmd_tree(_Args(json=False, depth=None, kit=None, show_disabled=True), engine)
        out = capsys.readouterr().out
        assert "wtf" in out


class TestDzTreeJSON:

    def test_json_output_parseable(self, tmp_path, monkeypatch, capsys):
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        _cmd_tree(_Args(json=True, depth=None, kit=None, show_disabled=False), engine)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["root"] == "dazzlecmd"
        assert data["command"] == "dz"
        assert data["tools_dir"] == "projects"

    def test_json_kits_structure(self, tmp_path, monkeypatch, capsys):
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        _cmd_tree(_Args(json=True, depth=None, kit=None, show_disabled=False), engine)
        data = json.loads(capsys.readouterr().out)
        assert "core" in data["kits"]
        assert "wtf" in data["kits"]
        core_kit = data["kits"]["core"]
        assert core_kit["name"] == "core"
        assert core_kit["always_active"] is True
        assert any(
            t["fqcn"] == "core:fixpath" for t in core_kit["tools"]
        )

    def test_json_tool_records(self, tmp_path, monkeypatch, capsys):
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        _cmd_tree(_Args(json=True, depth=None, kit=None, show_disabled=False), engine)
        data = json.loads(capsys.readouterr().out)
        tools = data["kits"]["core"]["tools"]
        assert all("fqcn" in t and "short" in t for t in tools)

    def test_json_kit_filter(self, tmp_path, monkeypatch, capsys):
        engine = _mk_engine_with_projects(tmp_path, monkeypatch)
        _cmd_tree(_Args(json=True, depth=None, kit="core", show_disabled=False), engine)
        data = json.loads(capsys.readouterr().out)
        assert "core" in data["kits"]
        assert "wtf" not in data["kits"]
