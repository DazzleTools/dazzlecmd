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
        assert "silence" in out and "unshadow" in out       # visibility pulled up
        assert "dz kit visibility -h" in out

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
