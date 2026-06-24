"""Constitutional core identity in `dz list` / `dz info`.

A tool whose engine lives in `dazzlecmd_lib.core` (safedel, links) is
constitutional: its canonical "home" is `dazzlecmd_lib:core:<name>` (bones),
of which `core:<name>` is the consumer projection (skin) shown in `dz list`.
`dz list` marks such tools `[lib]`; `dz info` shows the canonical FQCN.
"""
import os
import re
import subprocess
import sys

from dazzlecmd_lib.core import (
    is_constitutional,
    canonical_fqcn,
    constitutional_names,
)
from dazzlecmd_lib.default_meta_commands import _constitutional_entry

# The dazzlecmd aggregator now lives under src/dazzlecmd/ (the #58 packaging
# move). Anchor real-discovery engines there explicitly rather than relying on
# the CWD, which is no longer the aggregator root.
_PKG_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "dazzlecmd")


def _dz(*args):
    return subprocess.run([sys.executable, "-m", "dazzlecmd", *args],
                          capture_output=True, text=True)


# --- the lib core API ---

def test_constitutional_api():
    assert is_constitutional("safedel")
    assert is_constitutional("links")
    assert not is_constitutional("find")
    assert canonical_fqcn("safedel") == "dazzlecmd_lib:core:safedel"
    names = constitutional_names()
    assert "safedel" in names and "links" in names and "find" not in names


def test_constitutional_entry_helper():
    assert _constitutional_entry({"namespace": "core", "name": "safedel"})
    assert _constitutional_entry({"namespace": "core", "name": "links"})
    assert not _constitutional_entry({"namespace": "core", "name": "find"})
    # wrong namespace -> not constitutional even if name matches
    assert not _constitutional_entry({"namespace": "dazzletools", "name": "safedel"})


# --- CLI integration ---

def test_dz_list_marks_constitutional_tools():
    out = _dz("list").stdout
    for line in out.splitlines():
        if re.match(r"\s+safedel\b", line) or re.match(r"\s+links\b", line):
            assert "[lib]" in line, f"constitutional tool unmarked: {line!r}"
        if re.match(r"\s+find\b", line):
            assert "[lib]" not in line, f"non-constitutional marked: {line!r}"


def test_absolute_fqcn_derivation():
    """engine.absolute_fqcn is a real, always-derivable core concept."""
    import types
    from dazzlecmd_lib import AggregatorEngine
    eng = AggregatorEngine(name="dazzlecmd", project_root=_PKG_ROOT)
    native = types.SimpleNamespace(name="f-cp", namespace="core", fqcn="core:f-cp")
    assert eng.absolute_fqcn(native) == "dazzlecmd:core:f-cp"
    consti = types.SimpleNamespace(name="safedel", namespace="core", fqcn="core:safedel")
    assert eng.absolute_fqcn(consti) == "dazzlecmd_lib:core:safedel"


def test_dz_info_shows_absolute_for_constitutional():
    """No fake 'Canonical:' -- the real, lib-homed Absolute FQCN with overlay note."""
    out = _dz("info", "safedel").stdout
    assert "Canonical:" not in out            # the v0.9.7 fake field is gone
    assert "Absolute:" in out
    assert "dazzlecmd_lib:core:safedel" in out
    assert "constitutional" in out


def test_dz_info_shows_absolute_for_ordinary():
    """Ordinary tools get the derived absolute too (no asymmetry), sans note."""
    out = _dz("info", "find").stdout
    assert "Absolute:" in out
    assert "dazzlecmd:core:find" in out
    assert "constitutional" not in out


# --- absolute FQCN is ALWAYS resolvable (a real path always works) ---

def test_absolute_to_local_normalization():
    from dazzlecmd_lib import AggregatorEngine
    eng = AggregatorEngine(name="dazzlecmd", project_root=_PKG_ROOT)
    assert eng._absolute_to_local("dazzlecmd:core:f-cp") == "core:f-cp"
    assert eng._absolute_to_local("dazzlecmd:f-cp") == "f-cp"
    assert eng._absolute_to_local("core:f-cp") == "core:f-cp"   # already local
    assert eng._absolute_to_local("f-cp") == "f-cp"             # short untouched
    # Cross-home absolutes are NOT string-rewritten here (#180): a
    # constitutional tool's home resolves through the real OVERLAY alias in
    # the FQCN index, so _absolute_to_local leaves it untouched.
    assert (eng._absolute_to_local("dazzlecmd_lib:core:safedel")
            == "dazzlecmd_lib:core:safedel")
    assert (eng._absolute_to_local("dazzlecmd_lib:core:nope")
            == "dazzlecmd_lib:core:nope")


def test_absolute_fqcn_resolves_in_info():
    """`dz info <absolute>` resolves to the tool (was 'not found')."""
    assert "Name:        safedel" in _dz("info", "dazzlecmd_lib:core:safedel").stdout
    assert "Name:        f-cp" in _dz("info", "dazzlecmd:core:f-cp").stdout


def test_absolute_fqcn_dispatches():
    """`dz <absolute> ...` dispatches the tool (was 'invalid choice')."""
    assert "dz f-cp" in _dz("dazzlecmd:core:f-cp", "--help").stdout
    assert "dz safedel" in _dz("dazzlecmd_lib:core:safedel", "--help").stdout


def test_dz_list_lib_legend():
    """The dz list epilogue explains [lib] + the absolute FQCN."""
    out = _dz("list").stdout
    assert "[lib] constitutional primitive" in out
    assert "dazzlecmd_lib:core:<name>" in out


def test_legend_entry_word_wraps_with_hanging_indent(capsys):
    """The footer marker legend wraps at WORD boundaries (no mid-word breaks like
    'ali'/'as') and hangs continuation lines under the start of the text, so the
    marker stands out -- mirroring tool-description wrapping."""
    from dazzlecmd_lib.default_meta_commands import _print_legend_entry
    width = 40
    _print_legend_entry(
        "[lib]",
        "constitutional primitive -- use 'dz info <name>' for alias details now",
        width,
    )
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert len(lines) > 1                                  # it actually wrapped
    assert lines[0].startswith("  [lib] ")                 # marker on line 1
    indent = len("  [lib] ")
    for cont in lines[1:]:
        assert cont.startswith(" " * indent)               # hanging indent
        assert cont[indent:indent + 1] != " "              # text starts, not padding
    assert all(len(ln) <= width for ln in lines)           # fits -> terminal won't re-wrap
    # word-boundary: 'alias' is never split (the reported 'ali'/'as' break)
    assert "alias" in out
    assert not any(ln.rstrip().endswith("ali") for ln in lines)


# --- the overlay is a REAL index entry (#180), not a string shim ---

def test_overlay_alias_is_a_real_index_entry():
    """The constitutional home is registered in the FQCN index as an overlay
    alias -- a real, dispatchable grouping artifact, not a `_absolute_to_local`
    string rewrite."""
    from dazzlecmd_lib import AggregatorEngine
    eng = AggregatorEngine(name="dazzlecmd", project_root=_PKG_ROOT)
    eng.discover()
    idx = eng.fqcn_index
    # The home FQCN points at the surfaced canonical...
    assert idx.alias_index.get("dazzlecmd_lib:core:safedel") == "core:safedel"
    # ...tagged `overlay` so display surfaces can exclude it (shown via [lib]).
    assert idx._alias_sources.get("dazzlecmd_lib:core:safedel") == "overlay"
    # It must never shadow a real canonical (§9b).
    assert "dazzlecmd_lib:core:safedel" not in idx.canonical_index


def test_overlay_dispatch_shows_overlay_provenance():
    """`dz info <home-fqcn>` resolves through the real alias and says so."""
    out = _dz("info", "dazzlecmd_lib:core:safedel").stdout
    assert "Name:        safedel" in out
    assert "overlay" in out  # the overlay-provenance banner, not virtual-kit


def test_overlay_alias_excluded_from_alias_rows():
    """The overlay alias is dispatch-only: it does NOT clutter `dz list
    --show alias` (which enumerates virtual-kit aliases)."""
    out = _dz("list", "--show", "alias").stdout
    assert "dazzlecmd_lib:core:safedel" not in out
