"""Tests for dazzlecmd_lib.setup_resolve."""

from __future__ import annotations

import pytest

from dazzlecmd_lib.setup_resolve import resolve_setup_block, _normalize_platforms
from dazzlecmd_lib.platform_detect import PlatformInfo
from dazzlecmd_lib.schema_version import UnsupportedSchemaVersionError


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


class TestNoSetupBlock:
    def test_no_setup_key_returns_none(self, linux_debian):
        assert resolve_setup_block({"name": "x"}, platform_info=linux_debian) is None

    def test_empty_setup_returns_none(self, linux_debian):
        assert resolve_setup_block({"name": "x", "setup": {}}, platform_info=linux_debian) is None

    def test_none_setup_returns_none(self, linux_debian):
        assert resolve_setup_block({"name": "x", "setup": None}, platform_info=linux_debian) is None


class TestBaseOnlySetup:
    def test_command_only(self, linux_debian):
        project = {
            "name": "x",
            "setup": {"command": "pip install foo"}
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result == {"command": "pip install foo"}

    def test_command_and_note(self, linux_debian):
        project = {
            "name": "x",
            "setup": {"command": "pip install foo", "note": "Installs foo"}
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result == {"command": "pip install foo", "note": "Installs foo"}


class TestFlatStringShorthand:
    def test_flat_string_normalized_to_command_dict(self, linux_debian):
        project = {
            "name": "x",
            "setup": {
                "command": "pip install foo",
                "platforms": {
                    "linux": "apt install python3-foo",
                    "windows": "python -m pip install foo",
                    "macos": "brew install foo"
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "apt install python3-foo"

    def test_flat_string_windows(self, windows_win11):
        project = {
            "name": "x",
            "setup": {
                "command": "default",
                "platforms": {"windows": "choco install foo"}
            }
        }
        result = resolve_setup_block(project, platform_info=windows_win11)
        assert result["command"] == "choco install foo"

    def test_flat_string_falls_through_to_base_when_no_os_match(self, windows_win11):
        project = {
            "name": "x",
            "setup": {
                "command": "default",
                "platforms": {"linux": "apt install foo"}
            }
        }
        result = resolve_setup_block(project, platform_info=windows_win11)
        assert result["command"] == "default"


class TestNestedDictForm:
    def test_nested_dict_command(self, linux_debian):
        project = {
            "name": "x",
            "setup": {
                "platforms": {
                    "linux": {"command": "apt install python3-foo"}
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "apt install python3-foo"

    def test_subtype_match_wins(self, linux_debian):
        project = {
            "name": "x",
            "setup": {
                "command": "default",
                "platforms": {
                    "linux": {
                        "debian": {"command": "apt install"},
                        "rhel":   {"command": "dnf install"},
                        "general": {"command": "pip install"}
                    }
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "apt install"

    def test_general_fallback_for_unknown_subtype(self, linux_arch):
        project = {
            "name": "x",
            "setup": {
                "platforms": {
                    "linux": {
                        "debian": {"command": "apt install"},
                        "general": {"command": "pip install"}
                    }
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_arch)
        assert result["command"] == "pip install"

    def test_top_level_field_then_subtype_override(self, linux_debian):
        project = {
            "name": "x",
            "setup": {
                "platforms": {
                    "linux": {
                        "command": "default-linux",
                        "debian": {"command": "debian-specific"}
                    }
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "debian-specific"

    def test_top_level_field_preserved_when_no_subtype_match(self, linux_arch):
        project = {
            "name": "x",
            "setup": {
                "platforms": {
                    "linux": {
                        "command": "default-linux",
                        "debian": {"command": "debian-specific"}
                    }
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_arch)
        assert result["command"] == "default-linux"


class TestMixedFlatAndNested:
    def test_mixed_in_same_platforms_block(self, linux_debian):
        project = {
            "name": "x",
            "setup": {
                "platforms": {
                    "linux": "apt install foo",         # flat
                    "windows": {"command": "cinst foo"} # nested
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "apt install foo"


class TestBaseFieldsPreserved:
    def test_note_from_base_survives_platform_override(self, linux_debian):
        project = {
            "name": "x",
            "setup": {
                "command": "base",
                "note": "Base note",
                "platforms": {"linux": "platform-specific"}
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "platform-specific"
        assert result["note"] == "Base note"

    def test_platform_note_overrides_base(self, linux_debian):
        project = {
            "name": "x",
            "setup": {
                "command": "base",
                "note": "Base note",
                "platforms": {
                    "linux": {"command": "linux cmd", "note": "Linux note"}
                }
            }
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["note"] == "Linux note"


class TestSchemaVersion:
    def test_v1_explicit(self, linux_debian):
        project = {
            "name": "x",
            "setup": {"_schema_version": "1", "command": "pip install"}
        }
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "pip install"

    def test_unversioned_defaults_to_v1(self, linux_debian):
        project = {"name": "x", "setup": {"command": "pip install"}}
        result = resolve_setup_block(project, platform_info=linux_debian)
        assert result["command"] == "pip install"

    def test_unsupported_version_raises(self, linux_debian):
        project = {
            "name": "x",
            "setup": {"_schema_version": "999", "command": "pip install"}
        }
        with pytest.raises(UnsupportedSchemaVersionError) as exc:
            resolve_setup_block(project, platform_info=linux_debian)
        assert "999" in str(exc.value)


class TestNormalizePlatforms:
    def test_empty_dict_unchanged(self):
        assert _normalize_platforms({}) == {}

    def test_string_values_converted(self):
        result = _normalize_platforms({
            "linux": "apt install",
            "windows": "choco install"
        })
        assert result == {
            "linux": {"command": "apt install"},
            "windows": {"command": "choco install"}
        }

    def test_dict_values_passed_through(self):
        original = {"linux": {"command": "apt install", "debian": {"command": "apt"}}}
        result = _normalize_platforms(original)
        assert result == original

    def test_mixed(self):
        result = _normalize_platforms({
            "linux": "apt install",
            "windows": {"command": "choco install", "win11": {"command": "winget install"}}
        })
        assert result["linux"] == {"command": "apt install"}
        assert "win11" in result["windows"]

    def test_non_dict_input_returned_unchanged(self):
        # Defensive: shouldn't happen in practice, but don't crash
        assert _normalize_platforms("not a dict") == "not a dict"  # type: ignore


class TestImmutability:
    def test_original_project_not_mutated(self, linux_debian):
        project = {
            "name": "x",
            "setup": {
                "command": "base",
                "platforms": {
                    "linux": "apt install",
                    "windows": {"command": "choco install"}
                }
            }
        }
        original_setup = {
            "command": "base",
            "platforms": {
                "linux": "apt install",
                "windows": {"command": "choco install"}
            }
        }
        _ = resolve_setup_block(project, platform_info=linux_debian)
        assert project["setup"] == original_setup
