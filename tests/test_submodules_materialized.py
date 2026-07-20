"""Build gate: every tool submodule must be MATERIALIZED, not a bare gitlink.

Tools like core:listall live as git submodules (`.gitmodules`). A checkout
without `git submodule update --init` (or a clone without
`--recurse-submodules`) leaves an EMPTY directory at the gitlink path --
discovery then finds no `.dazzlecmd.json`, the tool is stranded, kit
aliases dangle (`f:ls -> core:listall` warns at startup), and worst of
all a wheel/sdist built from that tree SILENTLY ships without the tool
(packaging includes files on disk; absent files cannot be packaged).

This test turns that whole failure class into a red X: it fails loudly
with the exact command to run. It belongs next to the packaging leak
gate in any publish workflow. (Found live 2026-07-19: the PLZWORK->
HOMEBOX fast-forward brought the listall gitlink but nobody had
initialized it here.)
"""

import configparser
import os
import subprocess
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GITMODULES = os.path.join(_REPO_ROOT, ".gitmodules")


def _submodule_paths():
    if not os.path.isfile(_GITMODULES):
        return []
    parser = configparser.ConfigParser()
    parser.read(_GITMODULES, encoding="utf-8")
    paths = []
    for section in parser.sections():
        if parser.has_option(section, "path"):
            paths.append(parser.get(section, "path"))
    return paths


_PATHS = _submodule_paths()


@pytest.mark.skipif(not _PATHS, reason="no submodules declared")
@pytest.mark.parametrize("relpath", _PATHS)
def test_submodule_is_materialized(relpath):
    full = os.path.join(_REPO_ROOT, relpath)
    assert os.path.isdir(full), (
        f"submodule dir missing: {relpath}\n"
        f"Run: git submodule update --init {relpath}"
    )
    entries = [e for e in os.listdir(full) if e != "__pycache__"]
    assert entries, (
        f"submodule NOT initialized (empty gitlink dir): {relpath}\n"
        f"A build from this tree would SILENTLY ship without it.\n"
        f"Run: git submodule update --init {relpath}"
    )


@pytest.mark.skipif(not _PATHS, reason="no submodules declared")
@pytest.mark.parametrize("relpath", [
    p for p in _PATHS
    if os.sep.join(["projects", ""]) in (p + os.sep).replace("/", os.sep)
    or "/projects/" in p.replace(os.sep, "/")
])
def test_tool_submodule_has_manifest(relpath):
    """A tool submodule without its .dazzlecmd.json is stranded even
    when populated -- discovery needs the manifest."""
    manifest = os.path.join(_REPO_ROOT, relpath, ".dazzlecmd.json")
    assert os.path.isfile(manifest), (
        f"tool submodule {relpath} is populated but has no "
        f".dazzlecmd.json -- discovery will strand it "
        f"(the f:ls -> core:listall failure mode)."
    )
