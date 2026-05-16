"""Tests for per-language scaffolding (v0.7.44 / 4b-T3 + 4d-3).

Covers each of the seven supported languages: file structure produced,
manifest schema correctness, and the Python ``--full`` overlay.
"""

import json
import os
from types import SimpleNamespace

import pytest

from dazzlecmd import cli


@pytest.fixture
def scratch_project_root(tmp_path):
    return str(tmp_path)


def _make_args(
    name="testtool",
    namespace=None,
    description="",
    long_description="",
    language=None,
    kit=None,
    simple=False,
    full=False,
):
    return SimpleNamespace(
        name=name,
        namespace=namespace,
        description=description,
        long_description=long_description,
        language=language,
        kit=kit,
        simple=simple,
        full=full,
    )


def _scaffold(scratch, language, name="t", full=False):
    """Scaffold one tool and return (rc, tool_dir)."""
    rc = cli._cmd_new_tool(
        _make_args(name=name, description=f"A {language} tool", language=language, full=full),
        scratch,
        engine=None,
    )
    tool_dir = os.path.join(scratch, "projects", "dazzletools", name)
    return rc, tool_dir


def _read_manifest(tool_dir):
    with open(os.path.join(tool_dir, ".dazzlecmd.json"), "r", encoding="utf-8") as f:
        return json.load(f)


class TestLanguagePython:
    def test_scaffolds_minimum(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "python", name="py1")
        assert rc == 0
        assert os.path.isfile(os.path.join(tool_dir, ".dazzlecmd.json"))
        assert os.path.isfile(os.path.join(tool_dir, "py1.py"))

    def test_manifest_runtime_is_python(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "python", name="py2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "python"
        assert m["runtime"]["type"] == "python"
        assert m["runtime"]["entry_point"] == "main"
        assert m["runtime"]["script_path"] == "py2.py"

    def test_full_overlay_adds_readme_and_tests(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "python", name="py3", full=True)
        assert os.path.isfile(os.path.join(tool_dir, "README.md"))
        assert os.path.isfile(os.path.join(tool_dir, "tests", "test_py3.py"))

    def test_hyphenated_name_underscore_substitution(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "python", name="my-cool-tool")
        m = _read_manifest(tool_dir)
        # script_path uses name_underscore
        assert m["runtime"]["script_path"] == "my_cool_tool.py"
        assert os.path.isfile(os.path.join(tool_dir, "my_cool_tool.py"))


class TestLanguageRust:
    def test_scaffolds_cargo_and_main(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "rust", name="rs1")
        assert rc == 0
        assert os.path.isfile(os.path.join(tool_dir, "Cargo.toml"))
        assert os.path.isfile(os.path.join(tool_dir, "src", "main.rs"))
        assert os.path.isfile(os.path.join(tool_dir, ".dazzlecmd.json"))

    def test_manifest_runtime_is_binary(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "rust", name="rs2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "rust"
        assert m["runtime"]["type"] == "binary"
        assert "rs2" in m["runtime"]["binary_path"]


class TestLanguageNode:
    def test_scaffolds_package_and_index(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "node", name="n1")
        assert rc == 0
        assert os.path.isfile(os.path.join(tool_dir, "package.json"))
        assert os.path.isfile(os.path.join(tool_dir, "index.js"))

    def test_manifest_runtime_is_node(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "node", name="n2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "node"
        assert m["runtime"]["type"] == "node"
        assert m["runtime"]["script_path"] == "index.js"


class TestLanguagePowerShell:
    def test_scaffolds_ps1(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "powershell", name="psw1")
        assert rc == 0
        assert os.path.isfile(os.path.join(tool_dir, "psw1.ps1"))

    def test_manifest_runtime_is_shell_powershell(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "powershell", name="psw2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "powershell"
        assert m["runtime"]["type"] == "shell"
        assert m["runtime"]["shell"] == "powershell"
        assert m["runtime"]["script_path"] == "psw2.ps1"


class TestLanguageCCpp:
    def test_scaffolds_makefile_and_main_c(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "c_cpp", name="c1")
        assert rc == 0
        assert os.path.isfile(os.path.join(tool_dir, "Makefile"))
        assert os.path.isfile(os.path.join(tool_dir, "main.c"))

    def test_manifest_runtime_is_binary(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "c_cpp", name="c2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "c_cpp"
        assert m["runtime"]["type"] == "binary"
        assert m["runtime"]["binary_path"] == "c2"


class TestLanguageDocker:
    def test_scaffolds_dockerfile(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "docker", name="d1")
        assert rc == 0
        assert os.path.isfile(os.path.join(tool_dir, "Dockerfile"))

    def test_manifest_runtime_is_docker(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "docker", name="d2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "docker"
        assert m["runtime"]["type"] == "docker"
        assert "d2" in m["runtime"]["image"]


class TestLanguageGeneric:
    def test_scaffolds_readme_no_source(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "generic", name="g1")
        assert rc == 0
        # Generic ships README + manifest only; no source file.
        assert os.path.isfile(os.path.join(tool_dir, "README.md"))
        assert os.path.isfile(os.path.join(tool_dir, ".dazzlecmd.json"))
        # No language-specific source file
        assert not any(
            os.path.isfile(os.path.join(tool_dir, fname))
            for fname in ("main.py", "main.rs", "main.c", "index.js")
        )

    def test_manifest_runtime_is_placeholder_binary(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "generic", name="g2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "generic"
        assert m["runtime"]["type"] == "binary"
        # build_hint must mention "Edit" so the user knows it's a placeholder
        assert "Edit" in m["runtime"]["build_hint"]


class TestLanguageBash:
    def test_scaffolds_sh(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "bash", name="bsh1")
        assert rc == 0
        assert os.path.isfile(os.path.join(tool_dir, "bsh1.sh"))

    def test_manifest_runtime_is_shell_bash(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "bash", name="bsh2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "bash"
        assert m["runtime"]["type"] == "shell"
        assert m["runtime"]["shell"] == "bash"
        assert m["runtime"]["script_path"] == "bsh2.sh"
        # Bash is POSIX-only; platform metadata reflects that.
        assert m["platform"] == "linux"
        assert "windows" not in m["platforms"]

    def test_entry_has_bash_hashbang(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "bash", name="bsh3")
        with open(os.path.join(tool_dir, "bsh3.sh"), "r", encoding="utf-8") as f:
            first_line = f.readline().rstrip("\n")
        assert first_line == "#!/usr/bin/env bash"


class TestLanguageCmd:
    def test_scaffolds_cmd(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "cmd", name="cmd1")
        assert rc == 0
        assert os.path.isfile(os.path.join(tool_dir, "cmd1.cmd"))

    def test_manifest_runtime_is_shell_cmd(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "cmd", name="cmd2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "cmd"
        assert m["runtime"]["type"] == "shell"
        assert m["runtime"]["shell"] == "cmd"
        assert m["runtime"]["script_path"] == "cmd2.cmd"
        # cmd.exe is Windows-only.
        assert m["platform"] == "windows"
        assert m["platforms"] == ["windows"]

    def test_entry_has_echo_off(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "cmd", name="cmd3")
        with open(os.path.join(tool_dir, "cmd3.cmd"), "r", encoding="utf-8") as f:
            content = f.read()
        assert content.startswith("@echo off")
        assert "%*" in content  # passthrough of all args


class TestLanguageBinary:
    def test_scaffolds_manifest_and_readme_only(self, scratch_project_root):
        rc, tool_dir = _scaffold(scratch_project_root, "binary", name="bin1")
        assert rc == 0
        assert os.path.isfile(os.path.join(tool_dir, ".dazzlecmd.json"))
        assert os.path.isfile(os.path.join(tool_dir, "README.md"))
        # binary template ships NO source file (no build configuration either)
        assert not any(
            os.path.isfile(os.path.join(tool_dir, fname))
            for fname in ("main.py", "main.c", "main.rs", "index.js",
                          "bin1.py", "bin1.sh", "bin1.cmd", "Cargo.toml",
                          "Makefile", "Dockerfile")
        )

    def test_manifest_runtime_is_binary(self, scratch_project_root):
        _, tool_dir = _scaffold(scratch_project_root, "binary", name="bin2")
        m = _read_manifest(tool_dir)
        assert m["language"] == "binary"
        assert m["runtime"]["type"] == "binary"
        # Default binary_path matches the tool name (drop-in pattern)
        assert m["runtime"]["binary_path"] == "bin2"
        # build_hint mentions dropping the binary in the dir, OR PATH lookup
        assert "binary" in m["runtime"]["build_hint"].lower()
        # Cross-platform by default (binaries can be anything)
        assert m["platforms"] == ["windows", "linux", "macos"]


class TestAvailableLanguagesError:
    def test_unknown_language_error_lists_all_ten(
        self, scratch_project_root, capsys
    ):
        rc = cli._cmd_new_tool(
            _make_args(name="bad", language="cobol"),
            scratch_project_root,
            engine=None,
        )
        assert rc == 2
        err = capsys.readouterr().err
        assert "'cobol' not supported" in err
        for lang in (
            "python", "rust", "node", "powershell",
            "c_cpp", "docker", "generic", "bash", "cmd", "binary",
        ):
            assert lang in err


class TestTemplatePlaceholderSubstitution:
    """Verify placeholder substitution in BOTH file contents and filenames."""

    def test_filename_placeholder_substituted(self, scratch_project_root):
        """The python entry file uses {name_underscore} in its filename."""
        _, tool_dir = _scaffold(scratch_project_root, "python", name="abc-def")
        assert os.path.isfile(os.path.join(tool_dir, "abc_def.py"))
        # Original {name_underscore}.py should NOT exist
        assert not os.path.isfile(os.path.join(tool_dir, "{name_underscore}.py"))

    def test_description_in_manifest(self, scratch_project_root):
        rc = cli._cmd_new_tool(
            _make_args(
                name="desc-test",
                language="rust",
                description="A specific Rust tool description",
            ),
            scratch_project_root, engine=None,
        )
        assert rc == 0
        tool_dir = os.path.join(scratch_project_root, "projects", "dazzletools", "desc-test")
        m = _read_manifest(tool_dir)
        assert m["description"] == "A specific Rust tool description"
        # Cargo.toml also uses {description}
        with open(os.path.join(tool_dir, "Cargo.toml"), "r", encoding="utf-8") as f:
            cargo_content = f.read()
        assert "A specific Rust tool description" in cargo_content


class TestKitRegistrationCrossLanguage:
    """A scaffolded non-Python tool can still register in a kit (--kit flag)."""

    def test_rust_tool_registers_in_kit(self, scratch_project_root, tmp_path):
        # Create a minimal kit manifest first
        kit_dir = os.path.join(scratch_project_root, "projects", "core")
        os.makedirs(kit_dir, exist_ok=True)
        kit_manifest = os.path.join(kit_dir, ".kit.json")
        with open(kit_manifest, "w", encoding="utf-8") as f:
            json.dump({"name": "core", "tools_dir": ".", "tools": []}, f)

        rc = cli._cmd_new_tool(
            _make_args(name="rstool", language="rust", kit="core"),
            scratch_project_root, engine=None,
        )
        assert rc == 0

        with open(kit_manifest, "r", encoding="utf-8") as f:
            kit = json.load(f)
        # Registered as fully-qualified namespace:name
        assert any(t == "dazzletools:rstool" for t in kit.get("tools", []))
