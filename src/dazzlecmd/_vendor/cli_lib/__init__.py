"""cli_lib -- the CLI-building framework (in-development; future `dazzle-cli-lib`).

The third CLI-presentation pillar: it turns the ``{Groupable, Continuum,
ContinuumSpace}`` structure into CLI surface (parser, the ``-h`` layout, the axis
sections) and COMPOSES ``help_lib`` (tips at a coordinate) + ``log_lib`` (verbosity
+ output channels). cli_lib depends on help_lib + log_lib; they do not depend on it.

See ``_VENDORED.md`` and the DWP ``2026-06-28__23-10-48__...cli-lib-core.md``.
"""
from .sections import (
    FLAT, NESTED, Section, aligned_row,
    render_labeled_section, render_nested_section, render_sections,
)
from .tips import render_tip_footer

__all__ = [
    "aligned_row", "render_labeled_section", "render_nested_section",
    "render_sections", "Section", "FLAT", "NESTED",
    "render_tip_footer",
]
