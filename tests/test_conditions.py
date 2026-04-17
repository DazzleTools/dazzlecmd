"""Tests for dazzlecmd_lib.conditions."""

from __future__ import annotations

import os

import pytest

from dazzlecmd_lib.conditions import (
    ConditionSyntaxError,
    evaluate_condition,
    _uname_composite,
)
from dazzlecmd_lib.platform_detect import PlatformInfo


@pytest.fixture
def linux_debian():
    return PlatformInfo(
        os="linux", subtype="debian", arch="x86_64", is_wsl=False, version="12",
    )


@pytest.fixture
def windows_win11():
    return PlatformInfo(
        os="windows", subtype="win11", arch="x86_64", is_wsl=False, version="10.0.22621",
    )


@pytest.fixture
def wsl_linux():
    return PlatformInfo(
        os="linux", subtype="ubuntu", arch="x86_64", is_wsl=True, version="22.04",
    )


class TestEmptyAndNone:
    def test_none_condition_is_true(self, linux_debian):
        assert evaluate_condition(None, linux_debian) is True

    def test_empty_dict_is_true(self, linux_debian):
        assert evaluate_condition({}, linux_debian) is True

    def test_only_metadata_keys_is_true(self, linux_debian):
        assert evaluate_condition(
            {"_schema_version": "1", "_comment": "debug"}, linux_debian
        ) is True


class TestFileExists:
    def test_file_present(self, linux_debian, tmp_path):
        f = tmp_path / "marker"
        f.write_text("")
        assert evaluate_condition({"file_exists": str(f)}, linux_debian) is True

    def test_file_absent(self, linux_debian, tmp_path):
        assert evaluate_condition(
            {"file_exists": str(tmp_path / "nope")}, linux_debian
        ) is False

    def test_dir_is_not_file(self, linux_debian, tmp_path):
        assert evaluate_condition({"file_exists": str(tmp_path)}, linux_debian) is False

    def test_empty_path(self, linux_debian):
        assert evaluate_condition({"file_exists": ""}, linux_debian) is False


class TestDirExists:
    def test_dir_present(self, linux_debian, tmp_path):
        assert evaluate_condition({"dir_exists": str(tmp_path)}, linux_debian) is True

    def test_file_is_not_dir(self, linux_debian, tmp_path):
        f = tmp_path / "afile"
        f.write_text("")
        assert evaluate_condition({"dir_exists": str(f)}, linux_debian) is False


class TestEnvVar:
    def test_set_and_nonempty(self, linux_debian, monkeypatch):
        monkeypatch.setenv("TEST_VAR_X", "value")
        assert evaluate_condition({"env_var": "TEST_VAR_X"}, linux_debian) is True

    def test_set_but_empty(self, linux_debian, monkeypatch):
        monkeypatch.setenv("TEST_VAR_X", "")
        assert evaluate_condition({"env_var": "TEST_VAR_X"}, linux_debian) is False

    def test_unset(self, linux_debian, monkeypatch):
        monkeypatch.delenv("TEST_VAR_X", raising=False)
        assert evaluate_condition({"env_var": "TEST_VAR_X"}, linux_debian) is False


class TestEnvVarEquals:
    def test_match(self, linux_debian, monkeypatch):
        monkeypatch.setenv("TEST_VAR_Y", "expected")
        assert evaluate_condition(
            {"env_var_equals": {"name": "TEST_VAR_Y", "value": "expected"}}, linux_debian
        ) is True

    def test_mismatch(self, linux_debian, monkeypatch):
        monkeypatch.setenv("TEST_VAR_Y", "actual")
        assert evaluate_condition(
            {"env_var_equals": {"name": "TEST_VAR_Y", "value": "expected"}}, linux_debian
        ) is False

    def test_unset(self, linux_debian, monkeypatch):
        monkeypatch.delenv("TEST_VAR_Y", raising=False)
        assert evaluate_condition(
            {"env_var_equals": {"name": "TEST_VAR_Y", "value": "anything"}}, linux_debian
        ) is False

    def test_missing_name_raises(self, linux_debian):
        with pytest.raises(ConditionSyntaxError):
            evaluate_condition(
                {"env_var_equals": {"value": "foo"}}, linux_debian
            )

    def test_missing_value_raises(self, linux_debian):
        with pytest.raises(ConditionSyntaxError):
            evaluate_condition(
                {"env_var_equals": {"name": "FOO"}}, linux_debian
            )


class TestCommandAvailable:
    def test_python_available(self, linux_debian):
        assert evaluate_condition({"command_available": "python"}, linux_debian) is True

    def test_nonexistent_command(self, linux_debian):
        assert evaluate_condition(
            {"command_available": "this-is-not-a-real-command-xyz"}, linux_debian
        ) is False


class TestUnameContains:
    def test_matches_os(self, linux_debian):
        assert evaluate_condition({"uname_contains": "linux"}, linux_debian) is True

    def test_matches_subtype(self, linux_debian):
        assert evaluate_condition({"uname_contains": "debian"}, linux_debian) is True

    def test_matches_arch(self, linux_debian):
        assert evaluate_condition({"uname_contains": "x86_64"}, linux_debian) is True

    def test_matches_wsl(self, wsl_linux):
        assert evaluate_condition({"uname_contains": "wsl"}, wsl_linux) is True

    def test_no_match(self, linux_debian):
        assert evaluate_condition({"uname_contains": "darwin"}, linux_debian) is False

    def test_case_insensitive(self, linux_debian):
        assert evaluate_condition({"uname_contains": "DEBIAN"}, linux_debian) is True


class TestCombinatorAll:
    def test_all_pass(self, linux_debian, tmp_path):
        f = tmp_path / "marker"
        f.write_text("")
        cond = {
            "all": [
                {"file_exists": str(f)},
                {"uname_contains": "linux"},
            ]
        }
        assert evaluate_condition(cond, linux_debian) is True

    def test_one_fails(self, linux_debian, tmp_path):
        cond = {
            "all": [
                {"file_exists": str(tmp_path / "nope")},
                {"uname_contains": "linux"},
            ]
        }
        assert evaluate_condition(cond, linux_debian) is False

    def test_empty_list_vacuously_true(self, linux_debian):
        assert evaluate_condition({"all": []}, linux_debian) is True


class TestCombinatorAny:
    def test_any_pass(self, linux_debian, tmp_path):
        cond = {
            "any": [
                {"file_exists": str(tmp_path / "nope")},
                {"uname_contains": "linux"},
            ]
        }
        assert evaluate_condition(cond, linux_debian) is True

    def test_all_fail(self, linux_debian, tmp_path):
        cond = {
            "any": [
                {"file_exists": str(tmp_path / "nope")},
                {"uname_contains": "darwin"},
            ]
        }
        assert evaluate_condition(cond, linux_debian) is False

    def test_empty_list_vacuously_false(self, linux_debian):
        assert evaluate_condition({"any": []}, linux_debian) is False


class TestComposition:
    def test_multiple_keys_in_same_dict_are_anded(self, linux_debian, tmp_path):
        f = tmp_path / "marker"
        f.write_text("")
        # Both should pass
        cond = {"file_exists": str(f), "uname_contains": "linux"}
        assert evaluate_condition(cond, linux_debian) is True

        # One passes, one fails -> False
        cond = {"file_exists": str(tmp_path / "nope"), "uname_contains": "linux"}
        assert evaluate_condition(cond, linux_debian) is False

    def test_nested_all_in_any(self, linux_debian):
        cond = {
            "any": [
                {"all": [{"uname_contains": "darwin"}, {"uname_contains": "linux"}]},
                {"uname_contains": "debian"},
            ]
        }
        assert evaluate_condition(cond, linux_debian) is True

    def test_nested_any_in_all(self, linux_debian):
        cond = {
            "all": [
                {"uname_contains": "linux"},
                {"any": [{"uname_contains": "debian"}, {"uname_contains": "ubuntu"}]},
            ]
        }
        assert evaluate_condition(cond, linux_debian) is True

    def test_three_level_nesting(self, linux_debian):
        cond = {
            "all": [
                {"any": [
                    {"all": [{"uname_contains": "linux"}, {"uname_contains": "debian"}]},
                    {"uname_contains": "windows"},
                ]},
            ]
        }
        assert evaluate_condition(cond, linux_debian) is True


class TestSyntaxErrors:
    def test_unknown_matcher_key_raises(self, linux_debian):
        with pytest.raises(ConditionSyntaxError) as exc:
            evaluate_condition({"made_up_matcher": "foo"}, linux_debian)
        assert "made_up_matcher" in str(exc.value)

    def test_non_dict_condition_raises(self, linux_debian):
        with pytest.raises(ConditionSyntaxError):
            evaluate_condition("not a dict", linux_debian)  # type: ignore

    def test_all_not_a_list_raises(self, linux_debian):
        with pytest.raises(ConditionSyntaxError):
            evaluate_condition({"all": "not a list"}, linux_debian)

    def test_any_not_a_list_raises(self, linux_debian):
        with pytest.raises(ConditionSyntaxError):
            evaluate_condition({"any": {"not": "a list"}}, linux_debian)


class TestSecurityEnvVarValueNotLogged:
    def test_env_var_equals_mismatch_does_not_log_values(self, linux_debian, monkeypatch):
        # Set a secret-bearing var; the condition returns False.
        monkeypatch.setenv("FAKE_SECRET", "super-secret-value")
        result = evaluate_condition(
            {"env_var_equals": {"name": "FAKE_SECRET", "value": "wrong"}}, linux_debian
        )
        # Function contract: no raise, no leak. Just False.
        assert result is False

    def test_error_message_does_not_include_env_value(self, linux_debian, monkeypatch):
        monkeypatch.setenv("FAKE_SECRET", "super-secret-value")
        # Trigger an error with missing value field
        with pytest.raises(ConditionSyntaxError) as exc:
            evaluate_condition(
                {"env_var_equals": {"name": "FAKE_SECRET"}}, linux_debian
            )
        assert "super-secret-value" not in str(exc.value)


class TestUnameComposite:
    def test_includes_all_components(self, wsl_linux):
        composite = _uname_composite(wsl_linux)
        assert "linux" in composite
        assert "ubuntu" in composite
        assert "x86_64" in composite
        assert "22.04" in composite
        assert "wsl" in composite
