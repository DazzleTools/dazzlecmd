"""Constitutional core identity in `dz list` / `dz info`.

A tool whose engine lives in `dazzlecmd_lib.core` (safedel, links) is
constitutional: its canonical "home" is `dazzlecmd_lib:core:<name>` (bones),
of which `core:<name>` is the consumer projection (skin) shown in `dz list`.
`dz list` marks such tools `[lib]`; `dz info` shows the canonical FQCN.
"""
import re
import subprocess
import sys

from dazzlecmd_lib.core import (
    is_constitutional,
    canonical_fqcn,
    constitutional_names,
)
from dazzlecmd_lib.default_meta_commands import _constitutional_entry


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
    eng = AggregatorEngine(name="dazzlecmd")
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
