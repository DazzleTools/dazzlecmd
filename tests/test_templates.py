"""Tests for dazzlecmd_lib.templates."""

from __future__ import annotations

import pytest

from dazzlecmd_lib.templates import (
    VAR_REGEX,
    MAX_SUBSTITUTION_DEPTH,
    TemplateError,
    UnresolvedTemplateVariableError,
    TemplateRecursionError,
    substitute_vars,
    _substitute_string,
    _resolve_var,
)


class TestRegex:
    def test_matches_simple(self):
        m = VAR_REGEX.search("hello {{name}} world")
        assert m is not None
        assert m.group(1) == "name"

    def test_matches_with_whitespace(self):
        m = VAR_REGEX.search("{{ name }}")
        assert m is not None
        assert m.group(1) == "name"

    def test_does_not_match_bare_single_brace(self):
        assert VAR_REGEX.search("{name}") is None

    def test_does_not_match_empty(self):
        assert VAR_REGEX.search("{{}}") is None

    def test_does_not_match_digit_start(self):
        assert VAR_REGEX.search("{{1name}}") is None

    def test_matches_underscore(self):
        m = VAR_REGEX.search("{{_private}}")
        assert m is not None
        assert m.group(1) == "_private"


class TestSubstituteStringSimple:
    def test_no_vars_unchanged(self):
        assert _substitute_string("hello world", {}, context="t") == "hello world"

    def test_single_var(self):
        assert _substitute_string("hello {{name}}", {"name": "world"}, context="t") == "hello world"

    def test_multiple_vars(self):
        result = _substitute_string(
            "{{a}} and {{b}} and {{a}}",
            {"a": "X", "b": "Y"},
            context="t",
        )
        assert result == "X and Y and X"

    def test_whitespace_in_brackets(self):
        assert _substitute_string("{{ name }}", {"name": "world"}, context="t") == "world"

    def test_fast_path_no_braces(self):
        # Should not touch the string at all if no {{
        assert _substitute_string("hello world", {"unused": "var"}, context="t") == "hello world"


class TestSubstituteStringErrors:
    def test_unresolved_var_raises(self):
        with pytest.raises(UnresolvedTemplateVariableError) as exc:
            _substitute_string("hello {{missing}}", {"a": "b"}, context="test-context")
        msg = str(exc.value)
        assert "missing" in msg
        assert "test-context" in msg
        assert "['a']" in msg  # available vars listed

    def test_unresolved_empty_scope(self):
        with pytest.raises(UnresolvedTemplateVariableError) as exc:
            _substitute_string("{{x}}", {}, context="t")
        assert "[]" in str(exc.value)  # available vars shown as empty list

    def test_non_string_var_value_raises(self):
        with pytest.raises(TemplateError) as exc:
            _substitute_string("{{x}}", {"x": 42}, context="t")
        assert "must be a string" in str(exc.value)
        assert "int" in str(exc.value)


class TestRecursion:
    def test_simple_nesting(self):
        result = _substitute_string(
            "{{a}}",
            {"a": "{{b}}", "b": "final"},
            context="t",
        )
        assert result == "final"

    def test_deep_chain_within_limit(self):
        vars_map = {f"x{i}": f"{{{{x{i+1}}}}}" for i in range(9)}
        vars_map["x9"] = "final"
        result = _substitute_string("{{x0}}", vars_map, context="t")
        assert result == "final"

    def test_composition_pattern(self):
        vars_map = {
            "venv_dir": ".venv",
            "venv_bin": "{{venv_dir}}/bin",
            "venv_pip": "{{venv_bin}}/pip",
        }
        result = _substitute_string("{{venv_pip}} install", vars_map, context="t")
        assert result == ".venv/bin/pip install"

    def test_cycle_detected(self):
        vars_map = {"a": "{{b}}", "b": "{{a}}"}
        with pytest.raises(TemplateRecursionError) as exc:
            _substitute_string("{{a}}", vars_map, context="t")
        assert "cycle" in str(exc.value).lower()
        assert "a" in str(exc.value)
        assert "b" in str(exc.value)

    def test_self_reference_detected(self):
        vars_map = {"a": "{{a}}"}
        with pytest.raises(TemplateRecursionError):
            _substitute_string("{{a}}", vars_map, context="t")

    def test_max_depth_exceeded(self):
        # Build a chain longer than MAX_SUBSTITUTION_DEPTH
        vars_map = {}
        for i in range(MAX_SUBSTITUTION_DEPTH + 5):
            vars_map[f"x{i}"] = f"{{{{x{i+1}}}}}"
        vars_map[f"x{MAX_SUBSTITUTION_DEPTH + 5}"] = "final"
        with pytest.raises(TemplateRecursionError) as exc:
            _substitute_string("{{x0}}", vars_map, context="t")
        assert "max substitution depth" in str(exc.value).lower()


class TestSubstituteVarsBlock:
    def test_dict_values_substituted(self):
        block = {"cmd": "echo {{name}}", "note": "about {{name}}"}
        result = substitute_vars(block, {"name": "world"})
        assert result == {"cmd": "echo world", "note": "about world"}

    def test_keys_not_substituted(self):
        # Even if a key "looks like" a var, we don't substitute it
        block = {"{{name}}": "value"}
        result = substitute_vars(block, {"name": "unused"})
        assert result == {"{{name}}": "value"}

    def test_nested_dict(self):
        block = {"outer": {"inner": "{{x}}"}}
        result = substitute_vars(block, {"x": "hi"})
        assert result == {"outer": {"inner": "hi"}}

    def test_list_of_strings(self):
        block = {"args": ["{{flag1}}", "{{flag2}}"]}
        result = substitute_vars(block, {"flag1": "-U", "flag2": "-V"})
        assert result == {"args": ["-U", "-V"]}

    def test_list_of_dicts_prefer_pattern(self):
        block = {
            "prefer": [
                {"interpreter": "{{bun_cmd}}"},
                {"interpreter": "{{node_cmd}}"},
            ]
        }
        result = substitute_vars(block, {"bun_cmd": "bun", "node_cmd": "node"})
        assert result == {
            "prefer": [
                {"interpreter": "bun"},
                {"interpreter": "node"},
            ]
        }

    def test_scalars_pass_through(self):
        # Non-string values: numbers, bools, None
        block = {"count": 42, "enabled": True, "missing": None, "cmd": "{{x}}"}
        result = substitute_vars(block, {"x": "hi"})
        assert result == {"count": 42, "enabled": True, "missing": None, "cmd": "hi"}

    def test_schema_version_not_substituted(self):
        # _schema_version is a protocol field, never substituted
        block = {"_schema_version": "1", "cmd": "{{x}}"}
        result = substitute_vars(block, {"x": "hi", "_schema_version": "unused"})
        assert result["_schema_version"] == "1"


class TestImmutability:
    def test_input_block_not_mutated(self):
        original = {"cmd": "echo {{x}}", "note": "{{x}}"}
        before = {"cmd": "echo {{x}}", "note": "{{x}}"}
        _ = substitute_vars(original, {"x": "hi"})
        assert original == before

    def test_nested_input_not_mutated(self):
        original = {"outer": {"inner": "{{a}}"}, "list": ["{{b}}"]}
        before = {"outer": {"inner": "{{a}}"}, "list": ["{{b}}"]}
        _ = substitute_vars(original, {"a": "A", "b": "B"})
        assert original == before


class TestContextInErrors:
    def test_context_threaded_through_dict(self):
        block = {"setup": {"command": "{{missing}}"}}
        with pytest.raises(UnresolvedTemplateVariableError) as exc:
            substitute_vars(block, {}, context="root")
        msg = str(exc.value)
        assert "root.setup.command" in msg

    def test_context_threaded_through_list(self):
        block = {"args": ["{{missing}}"]}
        with pytest.raises(UnresolvedTemplateVariableError) as exc:
            substitute_vars(block, {}, context="top")
        msg = str(exc.value)
        assert "top.args[0]" in msg


class TestLiteralEdgeCases:
    def test_triple_braces(self):
        # {{{name}}} -> regex matches the inner {{name}}, leaving 1 literal { and } outside
        result = _substitute_string("{{{name}}}", {"name": "X"}, context="t")
        assert result == "{X}"

    def test_empty_braces_literal(self):
        # {{}} doesn't match \w+ identifier; passes through
        result = _substitute_string("{{}}", {}, context="t")
        assert result == "{{}}"

    def test_unmatched_open_brace(self):
        # Single { is never a template marker
        result = _substitute_string("{ hello {{name}} }", {"name": "world"}, context="t")
        assert result == "{ hello world }"

    def test_digit_name_not_matched(self):
        # {{1name}} -- identifier must start with letter or underscore
        result = _substitute_string("{{1name}}", {}, context="t")
        assert result == "{{1name}}"


class TestCaseSensitivity:
    def test_case_sensitive_lookup(self):
        vars_map = {"foo": "lower", "FOO": "upper"}
        assert _substitute_string("{{foo}}", vars_map, context="t") == "lower"
        assert _substitute_string("{{FOO}}", vars_map, context="t") == "upper"


class TestResolveVarEdgeCases:
    def test_missing_var_lists_available(self):
        with pytest.raises(UnresolvedTemplateVariableError) as exc:
            _resolve_var("missing", {"a": "1", "b": "2"}, chain=[], context="t")
        msg = str(exc.value)
        assert "['a', 'b']" in msg

    def test_cycle_in_chain(self):
        with pytest.raises(TemplateRecursionError):
            _resolve_var("a", {"a": "{{a}}"}, chain=["a"], context="t")


class TestVarWithinVarDynamicScope:
    """Dynamic scoping: a nested {{inner}} looks up in the SAME vars_map as the
    top-level reference, regardless of where the containing var was 'declared'."""

    def test_nested_ref_uses_caller_scope(self):
        # Effective block's merged _vars has python_cmd=py AND venv_create=<composite>
        # The composite references {{python_cmd}} which resolves from THIS scope
        vars_map = {
            "python_cmd": "py",
            "venv_create": "{{python_cmd}} -m venv .venv",
        }
        result = _substitute_string("cmd: {{venv_create}}", vars_map, context="t")
        assert result == "cmd: py -m venv .venv"

    def test_override_of_ingredient_affects_composite(self):
        # Simulates Windows overriding python_cmd while inheriting venv_create
        windows_effective = {
            "python_cmd": "py",
            "venv_create": "{{python_cmd}} -m venv .venv",
        }
        linux_effective = {
            "python_cmd": "python3",
            "venv_create": "{{python_cmd}} -m venv .venv",
        }
        w = _substitute_string("{{venv_create}}", windows_effective, context="windows")
        lx = _substitute_string("{{venv_create}}", linux_effective, context="linux")
        assert w == "py -m venv .venv"
        assert lx == "python3 -m venv .venv"
