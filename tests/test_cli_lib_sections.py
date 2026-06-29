"""DWP-D / D-1: cli_lib's group/axis-section renderer -- the structural display
primitive that now drives `dz kit -h`'s visibility section (the future
`dazzle-cli-lib`; this is the H-1 work, correctly homed in cli_lib not help_lib)."""
from dazzlecmd._vendor.cli_lib import (
    FLAT, NESTED, Section, aligned_row,
    render_labeled_section, render_nested_section, render_sections,
)


def test_labeled_section_header_then_aligned_rows():
    out = render_labeled_section(
        "visibility:", "a tool's presence axis",
        [("status", "show presence"), ("silence", "suppress the hint")],
        label_col=17)
    lines = out.splitlines()
    assert lines[0] == "  visibility:    a tool's presence axis"
    assert lines[1] == "    status       show presence"
    assert lines[2] == "    silence      suppress the hint"


def test_overlong_name_keeps_min_two_space_gap():
    assert aligned_row(4, "a-very-long-verb-name", "desc", label_col=10) == \
        "    a-very-long-verb-name  desc"


def test_empty_description_is_the_bare_label():
    assert render_labeled_section("group:", "", []) == "  group:"


# -- D-2: the nested (axis-exposed) section + the declarative section driver -----

def test_nested_section_blank_between_groups_not_after_last():
    """The `management:` template: header + per-group (group-row + item-rows),
    a blank line BETWEEN groups but NOT after the last (the caller adds the
    section separator -> blank-between + separator == blank-after-each)."""
    out = render_nested_section(
        "management:", "lifecycle",
        [("membership", "add<->remove  (x)", [("add", "A"), ("remove", "R")]),
         ("loading", "attach<->detach  (y)", [("attach", "AT"), ("detach", "DE")])],
        label_col=17)
    lines = out.split("\n")
    assert lines[0] == "  management:    lifecycle"
    assert lines[1] == "    membership   add<->remove  (x)"
    assert lines[2] == "      add        A"
    assert lines[3] == "      remove     R"
    assert lines[4] == ""                       # blank BETWEEN groups
    assert lines[5] == "    loading      attach<->detach  (y)"
    assert lines[7] == "      detach     DE"
    assert len(lines) == 8                       # NO trailing blank after last group


def test_render_sections_one_blank_line_between():
    s1 = Section(FLAT, "a:", "", rows=(("x", "X"),))
    s2 = Section(FLAT, "b:", "", rows=(("y", "Y"),))
    lines = render_sections([s1, s2]).split("\n")
    assert lines[0] == "  a:"
    assert lines[2] == ""                        # exactly one blank between sections
    assert lines[3] == "  b:"


def test_section_render_matches_the_underlying_functions():
    flat = Section(FLAT, "g:", "d", rows=(("n", "t"),))
    assert flat.render() == render_labeled_section("g:", "d", [("n", "t")])
    groups = [("ax", "w<->c", [("w", "ww"), ("c", "cc")])]
    nested = Section(NESTED, "m:", "d", groups=tuple(groups))
    assert nested.render() == render_nested_section("m:", "d", groups)


def test_section_custom_indents_for_the_options_shape():
    opt = Section(FLAT, "options:", "",
                  rows=(("-h, --help", "show this help message and exit"),),
                  header_indent=0, row_indent=2)
    lines = opt.render().split("\n")
    assert lines[0] == "options:"                # header at indent 0 (no indent)
    assert lines[1].startswith("  -h, --help")   # row at indent 2
