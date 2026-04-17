"""Tests for dazzlecmd_lib.schema_version."""

from __future__ import annotations

import pytest

from dazzlecmd_lib.schema_version import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    SCHEMA_VERSION_FIELD,
    UnsupportedSchemaVersionError,
    get_schema_version,
    check_schema_version,
)


class TestConstants:
    def test_current_version_is_string(self):
        assert isinstance(CURRENT_SCHEMA_VERSION, str)

    def test_current_version_in_supported(self):
        assert CURRENT_SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS

    def test_field_name_is_underscore_schema_version(self):
        assert SCHEMA_VERSION_FIELD == "_schema_version"


class TestGetSchemaVersion:
    def test_explicit_version(self):
        assert get_schema_version({"_schema_version": "1"}) == "1"

    def test_default_when_absent(self):
        assert get_schema_version({}) == CURRENT_SCHEMA_VERSION

    def test_custom_default(self):
        assert get_schema_version({}, default="2") == "2"

    def test_numeric_version_coerced_to_string(self):
        assert get_schema_version({"_schema_version": 1}) == "1"

    def test_non_dict_returns_default(self):
        assert get_schema_version(None, default="1") == "1"  # type: ignore
        assert get_schema_version("not a dict", default="1") == "1"  # type: ignore


class TestCheckSchemaVersion:
    def test_supported_version_passes(self):
        assert check_schema_version({"_schema_version": "1"}) == "1"

    def test_missing_version_uses_default(self):
        assert check_schema_version({}) == CURRENT_SCHEMA_VERSION

    def test_unsupported_version_raises(self):
        with pytest.raises(UnsupportedSchemaVersionError) as exc:
            check_schema_version({"_schema_version": "999"})
        assert "999" in str(exc.value)
        assert "1" in str(exc.value)  # lists supported versions

    def test_error_message_includes_context(self):
        with pytest.raises(UnsupportedSchemaVersionError) as exc:
            check_schema_version({"_schema_version": "2"}, context="test-tool override")
        assert "test-tool override" in str(exc.value)

    def test_unsupported_version_error_type(self):
        with pytest.raises(ValueError):
            # UnsupportedSchemaVersionError subclasses ValueError
            check_schema_version({"_schema_version": "99"})
