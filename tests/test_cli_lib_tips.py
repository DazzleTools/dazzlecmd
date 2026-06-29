"""DWP-D / D-4: `cli_lib.render_tip_footer` -- the `cli_lib -> help_lib`
composition. Which `TIP:` lines show is a coordinate query (`items_for_rank`) on
the help-detail Continuum: a `full`-only tip is hidden at `standard` and appears
when the coordinate is raised."""
from dazzlecmd._vendor.cli_lib import render_tip_footer
from dazzlecmd._vendor.help_lib.core import HelpContent


def _tip(tid, desc, contexts):
    return HelpContent(id=tid, command="dz do it", description=desc,
                       contexts=set(contexts))


def test_standard_rung_shows_standard_not_full():
    tips = [_tip("s", "standard tip", {"standard"}),
            _tip("f", "full tip", {"full"})]
    out = render_tip_footer(tips, detail_rank=0)
    assert "TIP: standard tip" in out
    assert "full tip" not in out


def test_full_rung_includes_full():
    tips = [_tip("s", "standard tip", {"standard"}),
            _tip("f", "full tip", {"full"})]
    out = render_tip_footer(tips, detail_rank=1)
    assert "standard tip" in out and "full tip" in out


def test_empty_when_nothing_shows():
    full_only = [_tip("f", "full tip", {"full"})]
    assert render_tip_footer(full_only, detail_rank=0) == ""   # full hidden at std
    assert render_tip_footer([], detail_rank=1) == ""          # empty registry
