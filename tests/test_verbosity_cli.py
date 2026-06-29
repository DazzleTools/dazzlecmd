"""D-3: the global ``-v``/``-q``/``--show`` flags wired to the log_lib verbosity
Continuum -- graded diagnostics on the (non-opt-in) ``general`` channel, gated by
the THAC0 threshold. These are VERTICAL-SLICE tests: real `python -m dazzlecmd`
invocations, because the value is the gate working END-TO-END (not in a mock).

The byte-gate covers default-verbosity stdout; it does NOT exercise the verbosity
flags -- this file does.
"""
import subprocess
import sys

from dazzlecmd.cli import _init_verbosity


def _run(*argv):
    """Run `python -m dazzlecmd <argv>`; return (returncode, stdout, stderr)."""
    r = subprocess.run(
        [sys.executable, "-m", "dazzlecmd", *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


class _NS:
    """A throwaway argparse-namespace stand-in."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


# -- the flag -> verbosity-coordinate mapping (unit) --------------------------

def test_init_verbosity_maps_v_minus_q():
    assert _init_verbosity(_NS(verbose=2, quiet=0)).verbosity == 2
    assert _init_verbosity(_NS(verbose=0, quiet=2)).verbosity == -2
    assert _init_verbosity(_NS(verbose=3, quiet=1)).verbosity == 2   # they compose
    assert _init_verbosity(_NS()).verbosity == 0                     # safe defaults


# -- the graded gate, end-to-end (the vertical slice) -------------------------

def test_default_emits_no_diagnostics():
    _rc, _out, err = _run("list")
    assert "meta-command:" not in err
    assert "discovered" not in err


def test_dash_v_shows_only_the_command_line():
    _rc, _out, err = _run("-v", "list")
    assert "meta-command: list" in err
    assert "discovered" not in err            # level 2 still gated at -v


def test_dash_vv_adds_discovery_counts():
    _rc, _out, err = _run("-vv", "list")
    assert "meta-command: list" in err
    assert "discovered" in err
    assert "parsed args:" not in err          # level 3 still gated at -vv


def test_dash_vvv_adds_parsed_args():
    _rc, _out, err = _run("-vvv", "list")
    assert "parsed args:" in err


def test_v_and_q_compose_to_silence():
    _rc, _out, err = _run("-v", "-q", "list")
    assert "meta-command:" not in err


# -- the --show collision guard (AC-D3-5) -------------------------------------

def test_list_show_view_still_works_under_global_show():
    # `list --show <view>` must keep selecting the view (distinct dest from the
    # global `--show CHANNEL`), and the global form must not error.
    rc_view, out_view, _e = _run("list", "--show", "alias")
    assert rc_view == 0 and out_view.strip()         # the alias view rendered
    rc_chan, _o, err_chan = _run("--show", "timing:2", "list")
    assert rc_chan == 0
    assert "Traceback" not in err_chan
