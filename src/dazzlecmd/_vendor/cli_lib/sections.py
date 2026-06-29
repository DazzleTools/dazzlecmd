"""Structured (group/axis) section rendering -- the CLI display primitive.

`cli_lib` owns how a CLI is STRUCTURED (axes -> verbs -> glosses, the `-h` layout).
This is the group-section primitive: a labeled header + indented, column-aligned
`name  description` rows -- exactly what `dz kit -h`'s axis sections need. It is the
STRUCTURAL complement to `help_lib` (command-examples + tips) and `log_lib` (output
channels + verbosity).

Section KINDS (D-2): a section is FLAT (a header + flat rows -- `render_labeled_
section`) or NESTED (a header + per-group group-row + item-rows -- `render_nested_
section`). `Section` is the descriptor and `render_sections` the list-driver: the
consumer declares a list of `Section`s (its CONTENT) and `cli_lib` renders the
LAYOUT. The framework owns the kinds; the consumer owns the list -- so a future
aggregator declares its sections and gets its `-h` for free.
"""
from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple


def aligned_row(indent: int, name: str, text: str, label_col: int = 17) -> str:
    """One ``<indent><name>  <text>`` row, ``text`` aligned to start at ``label_col``
    (a >=2-space gap when the name overruns). Empty ``text`` -> the bare label."""
    prefix = " " * indent + name
    if not text:
        return prefix
    gap = max(2, label_col - len(prefix))
    return prefix + " " * gap + text


def render_labeled_section(label: str, description: str,
                           rows: Iterable[Tuple[str, str]], *,
                           label_col: int = 17,
                           header_indent: int = 2,
                           row_indent: int = 4) -> str:
    """Render one GROUP/axis help section: a ``<label>  <description>`` header, then
    each ``(name, description)`` in ``rows`` as an indented, column-aligned row.
    Returns the section as a string with NO trailing newline (the caller spaces
    sections)."""
    lines = [aligned_row(header_indent, label, description, label_col)]
    for name, desc in rows:
        lines.append(aligned_row(row_indent, name, desc, label_col))
    return "\n".join(lines)


def render_nested_section(label: str, description: str,
                          groups: Iterable[Tuple[str, str,
                                                 Iterable[Tuple[str, str]]]], *,
                          label_col: int = 17,
                          header_indent: int = 2,
                          group_indent: int = 4,
                          item_indent: int = 6) -> str:
    """Render an AXIS-EXPOSED (grouped) section -- the ``management:`` template.

    A ``<label>  <description>`` header, then each ``(group_label, group_text,
    items)`` group as a group-row (the unifying axis, itself a runnable
    sub-command / FQCN namespace -- ``dz kit membership ...``) followed by its
    indented item-rows (the axis's poles). A blank line is emitted BETWEEN groups
    (not after the last) -- the caller adds the section separator, so blank-between
    + separator == "a blank after each group". No trailing newline.

    This is the GROUPED display-projection of a set of ``{P, not-P}`` axes: the
    axis is shown and the poles nest under it. Its sibling :func:`render_labeled_
    section` is the UNGROUPED projection (poles listed flat, axis not exposed) --
    the ``visibility:`` template.
    """
    lines = [aligned_row(header_indent, label, description, label_col)]
    group_list = list(groups)
    for idx, (g_label, g_text, items) in enumerate(group_list):
        lines.append(aligned_row(group_indent, g_label, g_text, label_col))
        for name, text in items:
            lines.append(aligned_row(item_indent, name, text, label_col))
        if idx != len(group_list) - 1:
            lines.append("")        # blank BETWEEN groups; caller spaces sections
    return "\n".join(lines)


# The two templates as section KINDS (the user's framing, 2026-06-29):
#   FLAT   = the brief/"visibility" template (ungrouped -- poles listed, axis hidden)
#   NESTED = the axis-exposed/"management" template (grouped -- axis is a sub-command)
# Same {P, not-P} axis data, two display-projections == {grouping, ungrouping}.
FLAT = "flat"
NESTED = "nested"


@dataclass(frozen=True)
class Section:
    """One CLI help section as DATA -- the descriptor a consumer declares and
    :func:`render_sections` lays out. ``cli_lib`` owns the KINDS; the consumer
    owns the list. ``kind=FLAT`` uses ``rows`` (``(name, text)`` pairs);
    ``kind=NESTED`` uses ``groups`` (``(group_label, group_text, items)`` triples).
    ``header_indent``/``row_indent`` let a section depart from the 2/4 default
    (e.g. the ``options:`` block at 0/2)."""

    kind: str
    label: str
    description: str = ""
    rows: Tuple[Tuple[str, str], ...] = ()
    groups: Tuple[Tuple[str, str, Tuple[Tuple[str, str], ...]], ...] = ()
    header_indent: int = 2
    row_indent: int = 4

    def render(self, *, label_col: int = 17) -> str:
        if self.kind == NESTED:
            return render_nested_section(
                self.label, self.description, self.groups,
                label_col=label_col, header_indent=self.header_indent)
        return render_labeled_section(
            self.label, self.description, self.rows,
            label_col=label_col, header_indent=self.header_indent,
            row_indent=self.row_indent)


def render_sections(sections: Sequence[Section], *,
                    label_col: int = 17) -> str:
    """Render a list of :class:`Section`s, one blank line between each. The
    declarative driver: a consumer hands ``cli_lib`` its section LIST (content)
    and gets the LAYOUT -- a higher-level argparse-epilog. No leading/trailing
    blank (the caller frames it with the prose preamble/footer)."""
    return "\n\n".join(s.render(label_col=label_col) for s in sections)
