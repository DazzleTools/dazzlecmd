"""Tests for the kit inverse-verb registry + the grouped ``dz kit -h`` epilog
(the kit-lifecycle command-grouping DWP, 2026-06-19, steps 1-2).

The registry is the single declared source for the kit ``{P, not-P}`` verb-pairs;
the epilog renders from it; and it must stay consistent with the actual CLI grammar
(the AC4 guard -- adding a pair without wiring the verb, or vice versa, fails here).
"""
import argparse

from dazzlecmd.cli import build_parser
from dazzlecmd.kit_verbs import (
    LIFECYCLE_PAIRS,
    FAVORITE_PAIR,
    VISIBILITY_PAIRS,
    GENERIC_VERBS,
    ALL_PAIRS,
    COUPLING_ALIGNED,
    COUPLING_INDEPENDENT,
    render_kit_help,
)


def _kit_parser(parser):
    """The `dz kit` subparser from a built top-level parser."""
    sub = next(a for a in parser._actions
               if isinstance(a, argparse._SubParsersAction))
    return sub.choices["kit"]


def _subparser_choices(parser, *path):
    """Walk the argparse subparser tree along ``path`` and return the set of
    subcommand names at the leaf (e.g. ``("kit",)`` -> kit's verbs;
    ``("kit", "visibility")`` -> the visibility verbs)."""
    node = parser
    for name in path:
        sub = next(a for a in node._actions
                   if isinstance(a, argparse._SubParsersAction))
        node = sub.choices[name]
    sub = next(a for a in node._actions
               if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


class TestKitVerbRegistry:
    def test_lifecycle_is_a_warm_to_cold_aligned_gradient(self):
        # Declared warm-first; ranks strictly coldward -1 -> -3; all ALIGNED
        # (the implicit coldward cascade -- detach already disables).
        assert [p.rank for p in LIFECYCLE_PAIRS] == [-1, -2, -3]
        assert all(p.coupling == COUPLING_ALIGNED for p in LIFECYCLE_PAIRS)
        assert [p.axis for p in LIFECYCLE_PAIRS] == \
            ["activation", "loading", "membership"]

    def test_independent_axes_are_rank0_optin(self):
        independents = (FAVORITE_PAIR, *VISIBILITY_PAIRS)
        assert all(p.coupling == COUPLING_INDEPENDENT for p in independents)
        assert all(p.rank == 0 for p in independents)

    def test_every_pair_has_distinct_warm_and_cold(self):
        for p in ALL_PAIRS:
            assert p.warm and p.cold and p.warm != p.cold

    def test_kit_help_is_hierarchical_by_axis(self):
        out = render_kit_help(_kit_parser(build_parser([])))
        for header in ("inspect:", "management:", "visibility:", "favorite:"):
            assert header in out
        for p in LIFECYCLE_PAIRS:                            # axis + its verbs nested
            assert p.axis in out and p.warm in out and p.cold in out
        # visibility verbs ARE listed (discovery) but addressed as a sub-group
        # (`dz kit visibility <verb>`), not bare `dz kit <verb>`.
        assert "silence" in out and "unshadow" in out
        assert "dz kit visibility" in out

    def test_registry_verbs_are_real_subcommands(self):
        # AC4: the declared registry is consistent with the actual CLI grammar.
        parser = build_parser([])
        kit_cmds = _subparser_choices(parser, "kit")
        for name, _gloss in GENERIC_VERBS:
            assert name in kit_cmds, f"generic verb {name!r} not a kit subcommand"
        for p in (*LIFECYCLE_PAIRS, FAVORITE_PAIR):
            assert p.warm in kit_cmds and p.cold in kit_cmds, \
                f"pair {p.warm}/{p.cold} not both kit subcommands"
        vis_cmds = _subparser_choices(parser, "kit", "visibility")
        for p in VISIBILITY_PAIRS:
            assert p.warm in vis_cmds and p.cold in vis_cmds, \
                f"visibility pair {p.warm}/{p.cold} not under `dz kit visibility`"

    def test_visibility_verbs_hoist_to_flat_kit_aliases(self):
        # Vertical-slice contract: `dz kit <verb>` parses IDENTICALLY to
        # `dz kit visibility <verb>` for every visibility verb -- same _meta +
        # level/direction, so they route to the SAME handler (the alias mode for
        # the visibility axis, as the lifecycle axis already has). This is the test
        # that would have caught `dz kit status media` erroring.
        parser = build_parser([])
        for verb in ("status", "silence", "unsilence", "hide", "unhide",
                     "shadow", "unshadow"):
            flat = parser.parse_args(["kit", verb, "media"])
            nested = parser.parse_args(["kit", "visibility", verb, "media"])
            assert flat._meta == nested._meta, \
                f"{verb}: flat {flat._meta!r} != nested {nested._meta!r}"
            assert getattr(flat, "level", None) == getattr(nested, "level", None)
            assert getattr(flat, "direction", None) == getattr(nested, "direction", None)
            assert flat.fqcn == nested.fqcn == "media"

    def test_kit_help_is_wired_and_dedups_the_positional_restatement(self):
        # `dz kit -h` reaches the custom render AND argparse's default positional
        # restatement is gone (the duplication the user flagged).
        kit_help = _kit_parser(build_parser([])).format_help()
        assert "kit verbs by presence axis:" in kit_help
        assert "positional arguments" not in kit_help        # no restatement
        assert "enable" in kit_help and "attach" in kit_help  # verbs still listed once


class TestKitAxisGroups:
    """The nested per-axis groups -- the same shape as `dz kit visibility`."""

    def test_axis_groups_exist_as_kit_subcommands(self):
        parser = build_parser([])
        kit_cmds = _subparser_choices(parser, "kit")
        for axis in ("activation", "loading", "membership"):
            assert axis in kit_cmds

    def test_each_axis_group_holds_its_warm_and_cold_verbs(self):
        parser = build_parser([])
        for pair in LIFECYCLE_PAIRS:
            verbs = _subparser_choices(parser, "kit", pair.axis)
            assert pair.warm in verbs and pair.cold in verbs

    def test_nested_verb_routes_to_same_handler_as_flat(self):
        # `dz kit activation enable foo` == `dz kit enable foo` (same _meta + args).
        parser = build_parser([])
        nested = parser.parse_args(["kit", "activation", "enable", "foo"])
        flat = parser.parse_args(["kit", "enable", "foo"])
        assert nested._meta == flat._meta == "kit_enable"
        assert nested.name == flat.name == "foo"

    def test_nested_verb_preserves_all_flags(self):
        # The shared spec carries every flag onto the nested form too.
        parser = build_parser([])
        a = parser.parse_args(
            ["kit", "membership", "remove", "foo", "--dry-run", "--yes", "--force"])
        assert a._meta == "kit_remove"
        assert a.name == "foo" and a.dry_run and a.yes and a.force

    def test_axis_with_no_verb_routes_to_state_view(self):
        parser = build_parser([])
        a = parser.parse_args(["kit", "loading"])
        assert a._meta == "kit_axis_loading"   # dispatch -> _cmd_kit_management(axis="loading")

    def test_management_is_a_real_command_with_optional_kit(self):
        parser = build_parser([])
        assert "management" in _subparser_choices(parser, "kit")
        assert parser.parse_args(["kit", "management"])._meta == "kit_management"
        one = parser.parse_args(["kit", "management", "core"])
        assert one._meta == "kit_management" and one.name == "core"


class TestKitAxisOnOffPoles:
    """The universal ``on``/``off`` poles under each lifecycle axis (SD-0 slice 2).

    ``on`` -> the WARM verb, ``off`` -> the COLD verb -- same args + ``_meta`` +
    handler (three-forms-one-handler, AC0-2/AC0-3). ``on``/``off`` are GROUPED
    synonyms (need the axis noun); they are NOT flat ``dz kit`` subcommands."""

    def test_on_off_exist_under_each_axis(self):
        parser = build_parser([])
        for pair in LIFECYCLE_PAIRS:
            verbs = _subparser_choices(parser, "kit", pair.axis)
            assert "on" in verbs and "off" in verbs, pair.axis

    def test_on_routes_to_warm_off_to_cold(self):
        # For every lifecycle axis: `dz kit <axis> on` == `<axis> <warm>`,
        # `<axis> off` == `<axis> <cold>` (same canonical _meta).
        parser = build_parser([])
        arg = {"membership": "https://x/y.git"}   # add takes a url, not a name
        for pair in LIFECYCLE_PAIRS:
            a = arg.get(pair.axis, "foo")
            on = parser.parse_args(["kit", pair.axis, "on", a])
            warm = parser.parse_args(["kit", pair.axis, pair.warm, a])
            off = parser.parse_args(["kit", pair.axis, "off", "foo"])
            cold = parser.parse_args(["kit", pair.axis, pair.cold, "foo"])
            assert on._meta == warm._meta, pair.axis
            assert off._meta == cold._meta, pair.axis

    def test_on_off_carry_the_specials_flags(self):
        # The shared arg-adder gives on/off every flag the special has.
        parser = build_parser([])
        a = parser.parse_args(
            ["kit", "membership", "off", "foo", "--dry-run", "--yes", "--force"])
        assert a._meta == "kit_remove"
        assert a.name == "foo" and a.dry_run and a.yes and a.force

    def test_three_forms_collapse_to_one_handler(self):
        # `dz kit loading on foo` == `dz kit loading attach foo` (parser-level
        # collapse; the hoisted `dz attach` form is wired later by SD-1).
        parser = build_parser([])
        on = parser.parse_args(["kit", "loading", "on", "foo"])
        special = parser.parse_args(["kit", "loading", "attach", "foo"])
        assert on._meta == special._meta == "kit_attach"
        assert on.name == special.name == "foo"

    def test_on_off_are_grouped_only_not_flat_kit_subcommands(self):
        # on/off need an axis context -- they are NOT bare `dz kit` verbs.
        kit_cmds = _subparser_choices(build_parser([]), "kit")
        assert "on" not in kit_cmds and "off" not in kit_cmds


class TestLibVerbAxisConsistency:
    """No-drift guard: the dazzlecmd-lib ``VERB_AXES`` registry (the future single
    source of truth, SD-0) must agree with this repo's kit verb pairs until B5
    folds them into one. If they drift, fix it here -- don't let two sources
    silently disagree."""

    def test_lib_registry_matches_github_kit_pairs(self):
        import pytest
        # verb_axis ships in dazzlecmd-lib >= 0.9.0; skip cleanly on an older lib
        # (the runtime floor stays 0.8.55 until a later slice wires it in).
        va_mod = pytest.importorskip("dazzlecmd_lib.verb_axis")
        VERB_AXES = va_mod.VERB_AXES
        lib = {va.axis: (va.warm, va.cold, va.coupling) for va in VERB_AXES}
        # the 3 lifecycle axes
        for pair in LIFECYCLE_PAIRS:
            assert lib[pair.axis] == (pair.warm, pair.cold, pair.coupling), \
                f"lib VERB_AXES[{pair.axis}] drifted from kit_verbs LIFECYCLE_PAIRS"
        # the projection axis = the favorite pair (favorite/unfavorite)
        assert lib["projection"] == (
            FAVORITE_PAIR.warm, FAVORITE_PAIR.cold, FAVORITE_PAIR.coupling)


class TestKitInfoDetail:
    """`dz kit info <kit>` -- the identity card + current state (SD-3, B3 /
    AC3-2/AC3-5/AC3-6). `dz info <kit>` folds the dynamic axis state INTO the
    identity/provenance field-set (the standalone `status` verb was removed --
    info-only, reduction infra kept). Absent fields render `(none)` (never
    dropped); `--json` mirrors the human card."""

    def test_info_requires_a_kit_name(self):
        parser = build_parser([])
        assert parser.parse_args(["kit", "info", "foo"]).name == "foo"
        assert parser.parse_args(["kit", "info", "foo"])._meta == "kit_info"

    def test_info_is_an_inspect_verb_in_help(self):
        # info joins list/focus/reset under the `inspect:` group (GENERIC_VERBS).
        assert "info" in {name for name, _ in GENERIC_VERBS}
        out = render_kit_help(_kit_parser(build_parser([])))
        assert "info" in out

    def _engine(self, **kw):
        import types
        defaults = dict(
            kit_name="demo", name="demo", virtual=False, tools=[1, 2, 3],
            version="1.2.3", description="A demo kit.", kit_import_name=None,
            directory=None, kit_source="/x/demo.kit.json", always_active=False)
        defaults.update(kw)
        kit = types.SimpleNamespace(**defaults)
        # `_get_user_config` is needed for the 'Current state' section (the
        # activation rung reads disabled_kits).
        return types.SimpleNamespace(
            kits=[kit], command="dz", _get_user_config=lambda: {})

    def test_card_renders_identity_fields(self, tmp_path, capsys):
        from dazzlecmd.cli import render_kit_info
        assert render_kit_info("demo", self._engine(), str(tmp_path)) == 0
        out = capsys.readouterr().out
        for label in ("Name:", "Kind:", "Description:", "Version:", "Tools:",
                      "Source:", "Always-active:"):
            assert label in out, label
        assert "kit" in out and "3 tool(s)" in out and "1.2.3" in out

    def test_card_includes_the_current_state_section(self, tmp_path, capsys):
        # The user's 'fold state into info' decision: the identity card is
        # followed by the per-axis state (the verb-axis registry projection).
        from dazzlecmd.cli import render_kit_info
        render_kit_info("demo", self._engine(), str(tmp_path))
        out = capsys.readouterr().out
        assert "Current state:" in out
        for axis in ("activation", "loading", "membership"):
            assert axis in out, axis
        assert "active" in out and "loaded" in out and "member" in out

    def test_virtual_kit_says_virtual_and_aliases(self, tmp_path, capsys):
        from dazzlecmd.cli import render_kit_info
        render_kit_info("demo", self._engine(virtual=True, tools=[1, 2]),
                        str(tmp_path))
        out = capsys.readouterr().out
        assert "virtual kit" in out and "2 alias(es)" in out

    def test_absent_fields_show_none_not_dropped(self, tmp_path, capsys):
        # AC3-2: directory/import-name unset -> "(none)", and the default
        # entity version "0.0.0" is treated as unset.
        from dazzlecmd.cli import render_kit_info
        render_kit_info("demo", self._engine(version="0.0.0", directory=None),
                        str(tmp_path))
        out = capsys.readouterr().out
        assert "(none)" in out
        assert "Directory:     (none)" in out or "Directory:    (none)" in out

    def test_json_mirrors_the_card_and_state(self, tmp_path, capsys):
        import json
        from dazzlecmd.cli import render_kit_info
        render_kit_info("demo", self._engine(), str(tmp_path), as_json=True)
        payload = json.loads(capsys.readouterr().out)
        assert payload["name"] == "demo"
        assert payload["kind"] == "kit"
        assert payload["tools"] == "3 tool(s)"
        assert payload["directory"] is None       # absent -> null, not "(none)"
        assert payload["state"]["activation"] == "active"   # the merged state
        assert set(payload["state"]) == {
            "activation", "loading", "membership", "tracking"}   # + mode fiber

    def test_info_unknown_kit_returns_1(self, tmp_path, capsys):
        import types
        from dazzlecmd.cli import render_kit_info
        engine = types.SimpleNamespace(
            kits=[], command="dz", _get_user_config=lambda: {})
        assert render_kit_info("nope", engine, str(tmp_path)) == 1


def test_kit_help_body_sections_present_and_ordered():
    """Structural regression guard for the `render_sections`-driven `dz kit -h`
    body (D-2). The byte-gate does NOT cover `dz kit -h`, so this pins the section
    skeleton: the five sections present + in order, `management:` genuinely nested
    (each lifecycle axis row + its two verb rows @6), the flat sections' rows
    col-aligned, the footer. Byte-identity to the pre-D-2 output is proven
    separately (capture-diff, the D-2 DWP)."""
    from dazzlecmd._vendor.cli_lib import aligned_row
    body = render_kit_help(_kit_parser(build_parser([])))

    # the five sections, in order (options: header sits at column 0)
    order = ["  inspect:", "  management:", "  visibility:",
             "  favorite:", "\noptions:"]
    positions = [body.index(marker) for marker in order]   # raises if absent
    assert positions == sorted(positions)                  # strictly ordered

    # management = the NESTED/axis-exposed template: each lifecycle axis is a
    # group-row (@4) with its warm + cold verbs nested under it (@6).
    for pair in LIFECYCLE_PAIRS:
        assert f"\n    {pair.axis}" in body                # axis row, indent 4
        assert f"\n      {pair.warm}" in body              # verb row, indent 6
        assert f"\n      {pair.cold}" in body

    # the FLAT/brief template: inspect rows render from their own glosses, col-17.
    for name, gloss in GENERIC_VERBS:
        assert aligned_row(4, name, gloss) in body

    # favorite is flat with both poles present
    assert f"\n    {FAVORITE_PAIR.warm}" in body
    assert f"\n    {FAVORITE_PAIR.cold}" in body

    # the footer
    assert body.rstrip().endswith(
        "Run 'dz kit <verb> --help' for a specific verb.")


def test_kit_help_body_matches_golden():
    """Exact byte-snapshot of the `dz kit -h` body (everything `render_kit_help`
    owns past the argparse usage line). The byte-gate does NOT cover `dz kit -h`,
    so this is the CI forward-lock against ANY drift -- gloss, spacing, order. On
    an intentional change, regenerate `tests/goldens/kit_help_body.txt` from the
    live body. Complements the structural test above (this catches gloss/spacing;
    that one gives a diagnostic failure on a structural break)."""
    import os
    golden = os.path.join(os.path.dirname(__file__), "goldens",
                          "kit_help_body.txt")
    with open(golden, "r", newline="", encoding="utf-8") as f:
        expected = f.read()
    full = render_kit_help(_kit_parser(build_parser([])))
    body = full[full.index("Each presence axis"):]
    assert body == expected
