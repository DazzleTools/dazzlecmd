"""Tests for ``dz new <type> <name>`` sub-parser surface (v0.7.40 / 4d-1).

Covers:
- ``dz new tool <name>`` creates the expected file structure
- Generated manifest includes ``long_description`` field (v0.7.37 schema)
- User-config ``new`` section defaults apply with correct precedence (CLI > config > built-in)
- ``dz new kit`` / ``dz new aggregator`` stubs return non-zero with planned-shape message
- Bare ``dz new`` (no type) returns 2 with helpful usage hint
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dazzlecmd import cli


@pytest.fixture
def scratch_project_root(tmp_path):
    """Provide a clean project root for scaffolding tests."""
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
    """Build the args namespace ``_cmd_new_tool`` expects."""
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


def _make_engine_with_config(config_dict):
    """Build a mock engine returning ``config_dict`` from ``_get_config_dict('new')``."""
    engine = MagicMock()
    engine._get_config_dict.return_value = config_dict
    return engine


class TestNewToolScaffold:
    """``dz new tool <name>`` produces the expected files."""

    def test_creates_tool_directory_and_files(self, scratch_project_root):
        rc = cli._cmd_new_tool(
            _make_args(name="hello", description="A test tool"),
            scratch_project_root,
            engine=None,
        )
        assert rc == 0

        tool_dir = os.path.join(
            scratch_project_root, "projects", "dazzletools", "hello"
        )
        assert os.path.isdir(tool_dir)
        assert os.path.isfile(os.path.join(tool_dir, ".dazzlecmd.json"))
        assert os.path.isfile(os.path.join(tool_dir, "hello.py"))

    def test_manifest_includes_long_description_field(self, scratch_project_root):
        cli._cmd_new_tool(
            _make_args(
                name="foo",
                description="short desc",
                long_description="The longer mini-manpage form spanning thoughts.",
            ),
            scratch_project_root,
            engine=None,
        )
        manifest_path = os.path.join(
            scratch_project_root, "projects", "dazzletools", "foo",
            ".dazzlecmd.json",
        )
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert "long_description" in manifest
        assert manifest["long_description"] == (
            "The longer mini-manpage form spanning thoughts."
        )

    def test_manifest_long_description_defaults_empty(self, scratch_project_root):
        """When --long-description is not passed, the field is the empty string."""
        cli._cmd_new_tool(
            _make_args(name="empty"),
            scratch_project_root,
            engine=None,
        )
        manifest_path = os.path.join(
            scratch_project_root, "projects", "dazzletools", "empty",
            ".dazzlecmd.json",
        )
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert manifest["long_description"] == ""

    def test_existing_project_errors(self, scratch_project_root):
        cli._cmd_new_tool(
            _make_args(name="dup"), scratch_project_root, engine=None,
        )
        rc = cli._cmd_new_tool(
            _make_args(name="dup"), scratch_project_root, engine=None,
        )
        assert rc == 1


class TestNewToolConfigDefaults:
    """User-config ``new`` section applies with correct precedence."""

    def test_config_namespace_default_applies(self, scratch_project_root):
        engine = _make_engine_with_config({"default_namespace": "from-config"})
        cli._cmd_new_tool(
            _make_args(name="a"), scratch_project_root, engine=engine,
        )
        # Tool lands in projects/from-config/a, not projects/dazzletools/a.
        assert os.path.isdir(
            os.path.join(scratch_project_root, "projects", "from-config", "a")
        )

    def test_cli_namespace_overrides_config(self, scratch_project_root):
        engine = _make_engine_with_config({"default_namespace": "from-config"})
        cli._cmd_new_tool(
            _make_args(name="b", namespace="from-cli"),
            scratch_project_root,
            engine=engine,
        )
        assert os.path.isdir(
            os.path.join(scratch_project_root, "projects", "from-cli", "b")
        )
        # Negative: did NOT land in the config-default location.
        assert not os.path.isdir(
            os.path.join(scratch_project_root, "projects", "from-config", "b")
        )

    def test_builtin_namespace_when_no_config(self, scratch_project_root):
        cli._cmd_new_tool(
            _make_args(name="c"), scratch_project_root, engine=None,
        )
        assert os.path.isdir(
            os.path.join(scratch_project_root, "projects", "dazzletools", "c")
        )

    def test_config_unknown_language_rejected(self, scratch_project_root, capsys):
        """When config defaults specify a language with no template dir,
        the scaffold fails with a clear error listing the available languages.

        v0.7.44 (4b-T3 + 4d-3) replaced v0.7.40's python-only guard with
        a generic "template dir not found" validation. The available set
        is the directories under templates/ (currently c_cpp, docker,
        generic, node, powershell, python, rust).
        """
        engine = _make_engine_with_config({"default_language": "klingon"})
        rc = cli._cmd_new_tool(
            _make_args(name="d"), scratch_project_root, engine=engine,
        )
        assert rc == 2
        err = capsys.readouterr().err
        assert "'klingon' not supported" in err
        # Source reference: config, not CLI flag
        assert "config 'new.default_language'" in err
        # Tool dir must NOT have been created
        assert not os.path.isdir(
            os.path.join(scratch_project_root, "projects", "dazzletools", "d")
        )

    def test_cli_unknown_language_rejected(self, scratch_project_root, capsys):
        """CLI --language with an unknown value is rejected with a
        message pointing at the --language flag as the source.
        """
        engine = _make_engine_with_config({"default_language": "rust"})
        rc = cli._cmd_new_tool(
            _make_args(name="e", language="brainfuck"),
            scratch_project_root,
            engine=engine,
        )
        assert rc == 2
        err = capsys.readouterr().err
        assert "'brainfuck' not supported" in err
        assert "--language flag" in err

    def test_python_language_explicitly_accepted(self, scratch_project_root):
        """Explicit ``--language python`` works (no rejection)."""
        rc = cli._cmd_new_tool(
            _make_args(name="py-explicit", language="python"),
            scratch_project_root, engine=None,
        )
        assert rc == 0
        manifest_path = os.path.join(
            scratch_project_root, "projects", "dazzletools", "py-explicit",
            ".dazzlecmd.json",
        )
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["language"] == "python"

    def test_default_language_python_works(self, scratch_project_root):
        """Built-in default ('python' when no CLI and no config) is allowed."""
        rc = cli._cmd_new_tool(
            _make_args(name="py-default"),
            scratch_project_root, engine=None,
        )
        assert rc == 0

    def test_missing_config_section_falls_back_silently(self, scratch_project_root):
        engine = MagicMock()
        engine._get_config_dict.return_value = None  # no 'new' section
        rc = cli._cmd_new_tool(
            _make_args(name="f"), scratch_project_root, engine=engine,
        )
        assert rc == 0
        assert os.path.isdir(
            os.path.join(scratch_project_root, "projects", "dazzletools", "f")
        )

    def test_malformed_config_does_not_crash(self, scratch_project_root):
        """A non-dict value in the 'new' config section is ignored gracefully."""
        engine = MagicMock()
        engine._get_config_dict.return_value = "not-a-dict"
        rc = cli._cmd_new_tool(
            _make_args(name="g"), scratch_project_root, engine=engine,
        )
        assert rc == 0


class TestNewKitAndAggregatorAreReal:
    """v0.9.20 (4d-2): the v0.7.40 stubs are GONE -- `dz new kit` and
    `dz new aggregator` are real implementations. Full coverage lives in
    tests/test_cli_new_scaffold.py; these pin the stub removal."""

    def test_stubs_are_removed(self):
        assert not hasattr(cli, "_cmd_new_kit_stub")
        assert not hasattr(cli, "_cmd_new_aggregator_stub")
        assert callable(cli._cmd_new_kit)
        assert callable(cli._cmd_new_aggregator)


class TestRegisterInKit:
    """v0.7.40 fix: ``_register_in_kit`` writes to the kit's in-repo
    manifest (authoritative for tools) rather than the registry pointer
    (which the loader's merge order silently overrides).
    """

    def test_writes_to_in_repo_manifest_when_present(self, tmp_path, capsys):
        """When ``projects/<kit>/.kit.json`` exists, register there."""
        # Set up: in-repo manifest at projects/mykit/.kit.json + an empty
        # registry pointer at kits/mykit.kit.json
        kits_dir = tmp_path / "kits"
        kits_dir.mkdir()
        (kits_dir / "mykit.kit.json").write_text(
            json.dumps({"name": "mykit", "always_active": True}),
            encoding="utf-8",
        )
        kit_dir = tmp_path / "projects" / "mykit"
        kit_dir.mkdir(parents=True)
        in_repo = kit_dir / ".kit.json"
        in_repo.write_text(
            json.dumps({
                "name": "mykit",
                "tools_dir": ".",
                "tools": ["mykit:existing"],
            }),
            encoding="utf-8",
        )

        cli._register_in_kit(str(tmp_path), "mykit", "mykit", "newtool")

        # In-repo manifest got the new entry; registry pointer untouched.
        in_repo_dict = json.loads(in_repo.read_text(encoding="utf-8"))
        assert "mykit:newtool" in in_repo_dict["tools"]
        assert "mykit:existing" in in_repo_dict["tools"]  # preserved
        registry_dict = json.loads(
            (kits_dir / "mykit.kit.json").read_text(encoding="utf-8")
        )
        assert "tools" not in registry_dict  # not polluted

        out = capsys.readouterr().out
        assert "in-repo manifest" in out

    def test_falls_back_to_registry_pointer_when_no_in_repo(self, tmp_path, capsys):
        """Registry-only kits (no in-repo manifest) get the entry in the
        registry pointer."""
        kits_dir = tmp_path / "kits"
        kits_dir.mkdir()
        (kits_dir / "regonly.kit.json").write_text(
            json.dumps({"name": "regonly", "always_active": False}),
            encoding="utf-8",
        )
        # No projects/regonly/ directory at all

        cli._register_in_kit(str(tmp_path), "regonly", "regonly", "tool1")

        registry_dict = json.loads(
            (kits_dir / "regonly.kit.json").read_text(encoding="utf-8")
        )
        assert "regonly:tool1" in registry_dict["tools"]
        out = capsys.readouterr().out
        assert "registry pointer" in out

    def test_warns_when_neither_target_exists(self, tmp_path, capsys):
        cli._register_in_kit(str(tmp_path), "ghost-kit", "ns", "name")
        err = capsys.readouterr().err
        assert "Warning: Kit 'ghost-kit' not found" in err

    def test_duplicate_entry_no_double_write(self, tmp_path, capsys):
        """Re-registering the same tool prints 'Already in kit' and
        does NOT duplicate the entry."""
        kit_dir = tmp_path / "projects" / "k"
        kit_dir.mkdir(parents=True)
        in_repo = kit_dir / ".kit.json"
        in_repo.write_text(
            json.dumps({"name": "k", "tools": ["k:dup"]}),
            encoding="utf-8",
        )

        cli._register_in_kit(str(tmp_path), "k", "k", "dup")

        in_repo_dict = json.loads(in_repo.read_text(encoding="utf-8"))
        # Count of "k:dup" entries should still be 1
        assert in_repo_dict["tools"].count("k:dup") == 1
        out = capsys.readouterr().out
        assert "Already in kit" in out


class TestResolveNewDefaults:
    """The ``_resolve_new_defaults`` helper handles engine variants safely."""

    def test_none_engine_returns_empty_dict(self):
        assert cli._resolve_new_defaults(None) == {}

    def test_engine_with_dict_config_returns_it(self):
        engine = _make_engine_with_config({"default_language": "python"})
        result = cli._resolve_new_defaults(engine)
        assert result == {"default_language": "python"}

    def test_engine_with_none_config_returns_empty(self):
        engine = MagicMock()
        engine._get_config_dict.return_value = None
        assert cli._resolve_new_defaults(engine) == {}

    def test_engine_with_non_dict_config_returns_empty(self):
        engine = MagicMock()
        engine._get_config_dict.return_value = ["unexpected", "list"]
        assert cli._resolve_new_defaults(engine) == {}

    def test_engine_raising_exception_returns_empty(self):
        engine = MagicMock()
        engine._get_config_dict.side_effect = RuntimeError("boom")
        assert cli._resolve_new_defaults(engine) == {}
