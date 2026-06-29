"""Continuum-scoped tips -- the `cli_lib -> help_lib` composition (D-4).

`cli_lib` owns CLI structure; `help_lib` owns contextual tips. This is the seam
where cli_lib COMPOSES help_lib: a consumer declares a registry of `help_lib.
HelpContent` tips (each with detail `contexts`), and cli_lib renders the footer for
a DETAIL COORDINATE -- `help_lib.items_for_rank` selects which tips show at that
rung of the detail Continuum (minimal < standard < full). A `full`-only tip stays
hidden at `standard`; raise the coordinate and it appears.

This is the first realization of the architecture's down-edge `cli_lib -> {help_lib,
log_lib}` (help_lib does NOT import cli_lib).
"""
from typing import Sequence

from ..help_lib.detail import items_for_rank
from ..help_lib.formatters import TipFormatter


def render_tip_footer(tips: Sequence, *, detail_rank: int = 0,
                      prog: str = "dz") -> str:
    """Render the `TIP:` lines for ``tips`` visible at ``detail_rank`` (a rung on the
    help-detail Continuum; default ``standard`` = 0). Returns "" when nothing shows
    at that coordinate -- the caller spaces it. Each tip is a ``help_lib.HelpContent``
    with a ``contexts`` set; ``items_for_rank`` is the coordinate query."""
    selected = items_for_rank(tips, detail_rank)
    if not selected:
        return ""
    return "\n".join(TipFormatter.format_list(selected, prog=prog))
