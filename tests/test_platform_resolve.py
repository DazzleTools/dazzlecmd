"""Tests for dazzlecmd_lib.platform_resolve."""

from __future__ import annotations

import pytest

from dazzlecmd_lib.platform_resolve import (
    deep_merge,
    resolve_platform_block,
)
from dazzlecmd_lib.platform_detect import PlatformInfo


@pytest.fixture
def linux_debian():
    return PlatformInfo(
        os="linux", subtype="debian", arch="x86_64", is_wsl=False, version="12",
    )


@pytest.fixture
def linux_arch():
    return PlatformInfo(
        os="linux", subtype="arch", arch="x86_64", is_wsl=False, version=None,
    )


@pytest.fixture
def windows_win11():
    return PlatformInfo(
        os="windows", subtype="win11", arch="x86_64", is_wsl=False, version="10.0.22621",
    )


class TestDeepMerge:
    def test_flat_override(self):
        a = {"x": 1, "y": 2}
        b = {"y": 20, "z": 30}
        assert deep_merge(a, b) == {"x": 1, "y": 20, "z": 30}

    def test_nested_dict_merges_recursively(self):
        a = {"outer": {"a": 1, "b": 2}}
        b = {"outer": {"b": 20, "c": 30}}
        assert deep_merge(a, b) == {"outer": {"a": 1, "b": 20, "c": 30}}

    def test_arrays_replaced_not_concatenated(self):
        a = {"prefer": ["node", "npx"]}
        b = {"prefer": ["bun"]}
        assert deep_merge(a, b) == {"prefer": ["bun"]}

    def test_none_removes_key(self):
        a = {"x": 1, "y": 2}
        b = {"y": None}
        assert deep_merge(a, b) == {"x": 1}

    def test_does_not_mutate_inputs(self):
        a = {"x": 1, "nested": {"a": 1}}
        b = {"nested": {"b": 2}}
        a_before = {"x": 1, "nested": {"a": 1}}
        b_before = {"nested": {"b": 2}}
        _ = deep_merge(a, b)
        assert a == a_before
        assert b == b_before

    def test_empty_a(self):
        assert deep_merge({}, {"x": 1}) == {"x": 1}

    def test_empty_b(self):
        assert deep_merge({"x": 1}, {}) == {"x": 1}

    def test_both_empty(self):
        assert deep_merge({}, {}) == {}

    def test_scalar_replaces_dict(self):
        # When b has a scalar where a has a dict, scalar wins.
        a = {"x": {"nested": 1}}
        b = {"x": "scalar"}
        assert deep_merge(a, b) == {"x": "scalar"}

    def test_dict_replaces_scalar(self):
        a = {"x": "scalar"}
        b = {"x": {"nested": 1}}
        assert deep_merge(a, b) == {"x": {"nested": 1}}


class TestResolvePlatformBlockBasics:
    def test_no_platforms_returns_base(self, linux_debian):
        base = {"type": "python", "script_path": "tool.py"}
        assert resolve_platform_block(base, None, linux_debian) == base
        assert resolve_platform_block(base, {}, linux_debian) == base

    def test_os_not_in_platforms_returns_base(self, linux_debian):
        base = {"type": "python"}
        platforms = {"windows": {"type": "binary"}}
        assert resolve_platform_block(base, platforms, linux_debian) == base

    def test_top_level_fields_merged_when_os_matches(self, linux_debian):
        base = {"type": "python"}
        platforms = {"linux": {"interpreter": "python3"}}
        result = resolve_platform_block(base, platforms, linux_debian)
        assert result == {"type": "python", "interpreter": "python3"}


class TestSubtypeResolution:
    def test_subtype_match_wins(self, linux_debian):
        base = {"type": "node"}
        platforms = {
            "linux": {
                "prefer": [{"interpreter": "node"}],
                "debian": {"prefer": [{"interpreter": "bun"}]},
                "general": {"prefer": [{"interpreter": "npx"}]},
            }
        }
        result = resolve_platform_block(base, platforms, linux_debian)
        assert result == {"type": "node", "prefer": [{"interpreter": "bun"}]}

    def test_general_fallback_when_subtype_unknown(self, linux_arch):
        base = {"type": "node"}
        platforms = {
            "linux": {
                "debian": {"prefer": [{"interpreter": "bun"}]},
                "general": {"prefer": [{"interpreter": "node"}]},
            }
        }
        result = resolve_platform_block(base, platforms, linux_arch)
        assert result == {"type": "node", "prefer": [{"interpreter": "node"}]}

    def test_no_general_and_no_subtype_falls_through_to_base(self, linux_arch):
        base = {"type": "node", "script_path": "tool.js"}
        platforms = {
            "linux": {
                "debian": {"prefer": [{"interpreter": "bun"}]},
            }
        }
        result = resolve_platform_block(base, platforms, linux_arch)
        assert result == {"type": "node", "script_path": "tool.js"}

    def test_top_level_fields_merged_before_subtype(self, linux_debian):
        base = {"type": "node"}
        platforms = {
            "linux": {
                "script_path": "linux-default.js",
                "debian": {"script_path": "debian-specific.js"},
            }
        }
        result = resolve_platform_block(base, platforms, linux_debian)
        # Subtype overrides top-level linux field
        assert result == {"type": "node", "script_path": "debian-specific.js"}

    def test_top_level_fields_win_when_no_subtype_override(self, linux_arch):
        base = {"type": "node"}
        platforms = {
            "linux": {
                "script_path": "linux-default.js",
                "debian": {"script_path": "debian-specific.js"},
            }
        }
        result = resolve_platform_block(base, platforms, linux_arch)
        assert result == {"type": "node", "script_path": "linux-default.js"}


class TestPlatformsOverridesBase:
    def test_platform_block_overrides_base(self, windows_win11):
        base = {"type": "node", "script_path": "tool.js", "interpreter": "node"}
        platforms = {
            "windows": {
                "type": "script",
                "script_path": "tool_wsh.js",
                "interpreter": "cscript",
            }
        }
        result = resolve_platform_block(base, platforms, windows_win11)
        assert result["type"] == "script"
        assert result["script_path"] == "tool_wsh.js"
        assert result["interpreter"] == "cscript"

    def test_base_fields_preserved_when_not_overridden(self, linux_debian):
        base = {"type": "node", "name": "mytool"}
        platforms = {"linux": {"interpreter": "bun"}}
        result = resolve_platform_block(base, platforms, linux_debian)
        assert result["name"] == "mytool"
        assert result["type"] == "node"
        assert result["interpreter"] == "bun"


class TestArrayReplacement:
    def test_prefer_array_replaced_by_subtype(self, linux_debian):
        base = {"prefer": [{"interpreter": "node"}, {"interpreter": "npx"}]}
        platforms = {
            "linux": {
                "debian": {"prefer": [{"interpreter": "bun"}]},
            }
        }
        result = resolve_platform_block(base, platforms, linux_debian)
        assert result["prefer"] == [{"interpreter": "bun"}]

    def test_base_prefer_kept_when_no_override(self, linux_debian):
        base = {"prefer": [{"interpreter": "node"}]}
        platforms = {"windows": {"prefer": [{"interpreter": "bun"}]}}
        result = resolve_platform_block(base, platforms, linux_debian)
        assert result["prefer"] == [{"interpreter": "node"}]


class TestEdgeCases:
    def test_malformed_platforms_not_dict(self, linux_debian):
        base = {"type": "python"}
        result = resolve_platform_block(base, "not a dict", linux_debian)  # type: ignore
        assert result == base

    def test_malformed_os_block_not_dict(self, linux_debian):
        base = {"type": "python"}
        platforms = {"linux": "not a dict"}
        result = resolve_platform_block(base, platforms, linux_debian)
        assert result == base

    def test_empty_os_block(self, linux_debian):
        base = {"type": "python"}
        platforms = {"linux": {}}
        result = resolve_platform_block(base, platforms, linux_debian)
        assert result == base

    def test_subtype_none_falls_to_general(self):
        info = PlatformInfo(
            os="linux", subtype=None, arch="x86_64", is_wsl=False, version=None,
        )
        base = {}
        platforms = {
            "linux": {
                "general": {"interpreter": "python3"},
                "debian": {"interpreter": "python3.11"},
            }
        }
        result = resolve_platform_block(base, platforms, info)
        assert result == {"interpreter": "python3"}

    def test_does_not_mutate_inputs(self, linux_debian):
        base = {"type": "node", "prefer": [{"a": 1}]}
        platforms = {
            "linux": {
                "debian": {"prefer": [{"b": 2}]},
            }
        }
        base_before = {"type": "node", "prefer": [{"a": 1}]}
        platforms_before = {
            "linux": {
                "debian": {"prefer": [{"b": 2}]},
            }
        }
        _ = resolve_platform_block(base, platforms, linux_debian)
        assert base == base_before
        assert platforms == platforms_before

    def test_metadata_keys_preserved_in_top_level(self, linux_debian):
        base = {}
        platforms = {
            "linux": {
                "_schema_version": "1",
                "interpreter": "bun",
            }
        }
        result = resolve_platform_block(base, platforms, linux_debian)
        assert result["_schema_version"] == "1"
        assert result["interpreter"] == "bun"
