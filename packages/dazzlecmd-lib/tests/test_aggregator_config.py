"""Tests for ``dazzlecmd_lib.aggregator_config``.

Covers:
- Loading the 3 real-world drafts (dazzlecmd, wtf-windows, amdead)
- Field validation (missing required, wrong types, unknown meta_commands)
- Schema-version checking
- Discovery pattern interpolation
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from dazzlecmd_lib.aggregator_config import (
    AGGREGATOR_CONFIG_FILENAME,
    AggregatorConfig,
    AggregatorConfigError,
    AggregatorDiscovery,
    AggregatorSchema,
    CURRENT_SCHEMA_VERSION,
    find_aggregator_root,
    load_aggregator_config,
)
from dazzlecmd_lib.reserved import (
    DEFAULT_META_COMMANDS_USER,
    DEFAULT_RESERVED_COMMANDS,
)


# Canonical aggregator.json fixtures -- one per real-world consumer.
# These are the production drafts for dazzlecmd / wtf-windows / amdead and
# double as the test corpus. Live in the public test tree so tests run
# without any private/ dependency.
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "aggregator-json"


def _write_config(tmp_path: Path, payload: dict) -> Path:
    cfg = tmp_path / AGGREGATOR_CONFIG_FILENAME
    cfg.write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


class TestRealWorldDrafts:
    """Parse the 3 actual aggregator.json drafts and verify field values."""

    def _load_draft(self, tmp_path, draft_name):
        # Copy the draft to a tmp dir as aggregator.json
        src = FIXTURES_DIR / f"{draft_name}.aggregator.json"
        assert src.is_file(), f"Draft not found: {src}"
        dest = tmp_path / AGGREGATOR_CONFIG_FILENAME
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return load_aggregator_config(str(tmp_path))

    def test_dazzlecmd_draft_parses(self, tmp_path):
        cfg = self._load_draft(tmp_path, "dazzlecmd")
        assert cfg.name == "dazzlecmd"
        assert cfg.command == "dz"
        assert cfg.tools_dir == "projects"
        assert cfg.kits_dir == "kits"
        assert cfg.manifest_name == ".dazzlecmd.json"
        assert "add" in cfg.enabled_meta_commands
        assert "mode" in cfg.enabled_meta_commands
        assert "new" in cfg.enabled_meta_commands
        # dazzlecmd has no extras -- ``find``/``git``/``safedel`` etc. are
        # ACTUAL TOOLS in projects/core/, not reserved-but-unused names.
        # The DEFAULT_RESERVED_COMMANDS already cover all meta-command
        # names; the extra_reserved_commands list is empty for dazzlecmd.
        # Defaults are still reserved (they always are, by construction)
        assert "list" in cfg.reserved_commands
        # Regression guard: ``find`` is an installed tool and must NOT
        # be reserved -- pre-fix, the fixture listed it and the discovery
        # layer silently skipped it.
        assert "find" not in cfg.reserved_commands
        # Schema decoupling
        assert cfg.schema.remote_url_paths == ("source.url", "lifecycle.remote")
        # Discovery
        assert "projects/*/*" in cfg.resolved_discovery_patterns()

    def test_wtf_windows_draft_parses(self, tmp_path):
        cfg = self._load_draft(tmp_path, "wtf-windows")
        assert cfg.name == "wtf-windows"
        assert cfg.command == "wtf"
        assert cfg.tools_dir == "tools"
        assert cfg.manifest_name == ".wtf.json"
        # wtf's enabled lib built-ins: list/info/kit/version only. It
        # drops tree/setup, and registers mode/new/add IMPERATIVELY with
        # custom handlers (so they're reserved, not lib-enabled).
        assert cfg.enabled_meta_commands == frozenset(
            {"list", "info", "kit", "version"}
        )
        assert "tree" not in cfg.enabled_meta_commands
        assert "setup" not in cfg.enabled_meta_commands
        assert "mode" not in cfg.enabled_meta_commands
        # mode/new/add/enhance/graduate are reserved (block tool names)
        # but not lib-enabled meta-commands.
        for name in ("mode", "new", "add", "enhance", "graduate"):
            assert name in cfg.reserved_commands
        # Schema matches wtf's real tool manifests (source.url; the lib's
        # hardcoded lifecycle.graduated_to fallback covers the rest).
        assert cfg.schema.remote_url_paths == ("source.url",)
        # Discovery interpolates tools/
        assert "tools/*/*" in cfg.resolved_discovery_patterns()

    def test_amdead_draft_parses(self, tmp_path):
        cfg = self._load_draft(tmp_path, "amdead")
        assert cfg.name == "AMDead"
        assert cfg.command == "amdead"
        assert cfg.tools_dir == "tools"
        assert cfg.manifest_name == ".amdead.json"
        # amdead is restricted: no add/mode/new
        assert "add" not in cfg.enabled_meta_commands
        assert "mode" not in cfg.enabled_meta_commands
        assert "new" not in cfg.enabled_meta_commands
        # But the 6-user-meta-command set IS registered
        assert cfg.enabled_meta_commands == DEFAULT_META_COMMANDS_USER
        # Discovery interpolates tools/
        assert "tools/*/*" in cfg.resolved_discovery_patterns()


class TestFieldValidation:
    """Required fields, type checking, unknown meta-commands."""

    def _minimal_valid(self):
        return {
            "_schema_version": 1,
            "name": "test",
            "command": "t",
            "tools_dir": "projects",
            "kits_dir": "kits",
            "manifest_name": ".test.json",
        }

    def test_minimal_valid_config(self, tmp_path):
        _write_config(tmp_path, self._minimal_valid())
        cfg = load_aggregator_config(str(tmp_path))
        assert cfg.name == "test"
        assert cfg.command == "t"
        assert cfg.enabled_meta_commands == DEFAULT_META_COMMANDS_USER
        assert cfg.reserved_commands == DEFAULT_RESERVED_COMMANDS

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(AggregatorConfigError, match="not found"):
            load_aggregator_config(str(tmp_path))

    def test_missing_required_field(self, tmp_path):
        payload = self._minimal_valid()
        del payload["name"]
        _write_config(tmp_path, payload)
        with pytest.raises(AggregatorConfigError, match="'name' missing"):
            load_aggregator_config(str(tmp_path))

    def test_invalid_json(self, tmp_path):
        (tmp_path / AGGREGATOR_CONFIG_FILENAME).write_text(
            "{not valid json", encoding="utf-8"
        )
        with pytest.raises(AggregatorConfigError, match="not valid JSON"):
            load_aggregator_config(str(tmp_path))

    def test_wrong_schema_version(self, tmp_path):
        payload = self._minimal_valid()
        payload["_schema_version"] = 99
        _write_config(tmp_path, payload)
        with pytest.raises(
            AggregatorConfigError, match="unsupported _schema_version 99"
        ):
            load_aggregator_config(str(tmp_path))

    def test_unknown_meta_command_rejected(self, tmp_path):
        payload = self._minimal_valid()
        payload["enabled_meta_commands"] = ["list", "info", "bogus"]
        _write_config(tmp_path, payload)
        with pytest.raises(
            AggregatorConfigError, match="not in the reserved set"
        ):
            load_aggregator_config(str(tmp_path))

    def test_empty_string_name_rejected(self, tmp_path):
        payload = self._minimal_valid()
        payload["name"] = ""
        _write_config(tmp_path, payload)
        with pytest.raises(AggregatorConfigError, match="must be a non-empty string"):
            load_aggregator_config(str(tmp_path))

    def test_meta_commands_must_be_list(self, tmp_path):
        payload = self._minimal_valid()
        payload["enabled_meta_commands"] = "list,info"  # string, not list
        _write_config(tmp_path, payload)
        with pytest.raises(AggregatorConfigError, match="must be a list"):
            load_aggregator_config(str(tmp_path))


class TestDiscoveryPatternInterpolation:
    """`${tools_dir}` is expanded from the same JSON."""

    def test_interpolates_tools_dir(self, tmp_path):
        payload = {
            "_schema_version": 1,
            "name": "test",
            "command": "t",
            "tools_dir": "src/tools",
            "kits_dir": "kits",
            "manifest_name": ".t.json",
            "discovery": {
                "tool_patterns": ["${tools_dir}/*/*", "extras/*"],
            },
        }
        _write_config(tmp_path, payload)
        cfg = load_aggregator_config(str(tmp_path))
        patterns = cfg.resolved_discovery_patterns()
        assert "src/tools/*/*" in patterns
        assert "extras/*" in patterns  # not interpolated, no placeholder


class TestSchemaDecoupling:
    """`schema.remote_url_paths` allows aggregators to use different manifest layouts."""

    def test_default_schema_paths(self, tmp_path):
        payload = {
            "_schema_version": 1,
            "name": "test",
            "command": "t",
            "tools_dir": "projects",
            "kits_dir": "kits",
            "manifest_name": ".test.json",
        }
        _write_config(tmp_path, payload)
        cfg = load_aggregator_config(str(tmp_path))
        # Defaults match dazzlecmd's historical behavior
        assert cfg.schema.remote_url_paths == ("source.url", "lifecycle.remote")
        assert cfg.schema.lifecycle_path == "lifecycle"

    def test_custom_schema_paths(self, tmp_path):
        payload = {
            "_schema_version": 1,
            "name": "test",
            "command": "t",
            "tools_dir": "projects",
            "kits_dir": "kits",
            "manifest_name": ".test.json",
            "schema": {
                "remote_url_paths": ["repo.url"],
                "lifecycle_path": "_lifecycle",
            },
        }
        _write_config(tmp_path, payload)
        cfg = load_aggregator_config(str(tmp_path))
        assert cfg.schema.remote_url_paths == ("repo.url",)
        assert cfg.schema.lifecycle_path == "_lifecycle"


# ---------------------------------------------------------------------------
# T1-M1: find_aggregator_root() -- project-root discovery via aggregator.json
# ---------------------------------------------------------------------------


class TestFindAggregatorRoot:
    """Walks up looking for aggregator.json."""

    def test_returns_dir_when_aggregator_json_present(self, tmp_path):
        """Direct hit: start_path already contains aggregator.json."""
        (tmp_path / AGGREGATOR_CONFIG_FILENAME).write_text("{}")
        result = find_aggregator_root(str(tmp_path))
        assert result == os.path.abspath(str(tmp_path))

    def test_walks_up_to_find_ancestor(self, tmp_path):
        """Start deep, find marker at an ancestor."""
        (tmp_path / AGGREGATOR_CONFIG_FILENAME).write_text("{}")
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        result = find_aggregator_root(str(nested))
        assert result == os.path.abspath(str(tmp_path))

    def test_returns_none_when_marker_absent(self, tmp_path):
        """No aggregator.json at any ancestor -> None."""
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        # No marker placed -- and tmp_path is under $TEMP which on Windows
        # is under $HOME but doesn't have an aggregator.json ancestor.
        result = find_aggregator_root(str(nested), max_depth=3)
        assert result is None

    def test_honors_max_depth(self, tmp_path):
        """Marker beyond max_depth ancestors is not found."""
        (tmp_path / AGGREGATOR_CONFIG_FILENAME).write_text("{}")
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        # max_depth=2 means we only check deep, deep/.., deep/../..
        # -- never reaches tmp_path which is 5 levels up.
        result = find_aggregator_root(str(deep), max_depth=2)
        assert result is None

    def test_returns_self_when_max_depth_zero_and_marker_present(self, tmp_path):
        """max_depth=0 checks only start_path itself, not ancestors."""
        (tmp_path / AGGREGATOR_CONFIG_FILENAME).write_text("{}")
        result = find_aggregator_root(str(tmp_path), max_depth=0)
        assert result == os.path.abspath(str(tmp_path))

    def test_default_is_cwd_only_no_lib_fallback(self, tmp_path, monkeypatch):
        """With start_path=None and a marker-free cwd, returns None.

        v0.7.52: the old lib-``__file__`` fallback was removed. It made
        every aggregator that called this bare resolve to dazzlecmd (the
        lib lives co-located with dazzlecmd in dev mode). The None default
        is now cwd-only; entry points must pass an explicit anchor.
        """
        empty = tmp_path / "no_marker_here"
        empty.mkdir()
        monkeypatch.chdir(str(empty))
        assert find_aggregator_root() is None

    def test_explicit_anchor_ignores_cwd(self, tmp_path, monkeypatch):
        """An explicit start_path is honored regardless of cwd.

        Regression guard for the v0.7.52 impersonation bug: an entry
        point anchored to its own package must resolve to ITS project
        even when invoked from inside a DIFFERENT aggregator's tree.
        Here ``other_agg`` (with its own aggregator.json) is the cwd,
        but the anchored call resolves to ``my_agg``.
        """
        my_agg = tmp_path / "my_agg"
        my_pkg = my_agg / "src" / "mypkg"
        my_pkg.mkdir(parents=True)
        (my_agg / AGGREGATOR_CONFIG_FILENAME).write_text("{}")

        other_agg = tmp_path / "other_agg"
        other_agg.mkdir()
        (other_agg / AGGREGATOR_CONFIG_FILENAME).write_text("{}")

        # Stand inside the OTHER aggregator's tree...
        monkeypatch.chdir(str(other_agg))
        # ...but anchor to my package -> resolves to MY aggregator, not other.
        result = find_aggregator_root(str(my_pkg))
        assert result == os.path.abspath(str(my_agg))


def test_action_verb_reserved_ahead_of_framework():
    """'action' is reserved BEFORE the dz-action metadata framework lands
    (dazzlecmd#87) so no tool can squat the verb. Pins the forward
    reservation -- removing it would let a kit tool shadow the planned
    `dz action <type> <dot-expr>` surface."""
    assert "action" in DEFAULT_RESERVED_COMMANDS
