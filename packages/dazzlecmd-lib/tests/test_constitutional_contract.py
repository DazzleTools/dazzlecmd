"""The constitutional tool boundary contract, enforced (links-fork DWP, S-D).

A name in ``core._CONSTITUTIONAL_NAMES`` is a DERIVED claim rendered to users
(the ``[lib]`` marker, the overlay alias, ``Absolute: dazzlecmd_lib:core:<name>``),
so it must be checked, not hand-asserted. The contract for each constitutional
name that ships a user-facing tool:

1. the lib package ``dazzlecmd_lib/core/<name>/`` exists (the ENGINE),
2. the tool imports that engine (``dazzlecmd_lib.core.<name>``), and
3. the tool defines NO duplicate of the engine's key symbols -- the tool is a
   thin CLI (argparse/display/exit codes), never a second engine.

This is exactly the bug class that shipped 2026-06-10/11: ``links`` was marked
constitutional while its tool ran a self-contained byte-identical fork of the
engine, making ``links [lib]`` a false claim. These tests fail if that ever
recurs (including for future constitutional names -- the tests iterate the
frozenset, so adding a name without honoring the contract fails CI).
"""
import os
import re

import pytest

from dazzlecmd_lib.core import constitutional_names

# Repo layout: this file lives at packages/dazzlecmd-lib/tests/, the lib at
# packages/dazzlecmd-lib/src/dazzlecmd_lib/, the tools at projects/core/<name>/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_LIB_CORE = os.path.join(_HERE, "..", "src", "dazzlecmd_lib", "core")
_TOOLS_CORE = os.path.join(_REPO, "projects", "core")

# The engine symbols a tool must NOT re-define (a duplicate engine). Keyed by
# constitutional name; extend when a new primitive joins the frozenset.
_ENGINE_KEY_SYMBOLS = {
    "links": ("def detect_link", "def scan_directory", "class LinkInfo",
              "def _is_junction_win"),
    "safedel": ("class TrashStore", "def stage_to_trash", "def classify"),
}


def _tool_source(name):
    """All .py source text of the tool (None when no on-disk tool exists --
    a constitutional primitive without a CLI face is allowed)."""
    tool_dir = os.path.join(_TOOLS_CORE, name)
    if not os.path.isdir(tool_dir):
        return None
    chunks = []
    for entry in sorted(os.listdir(tool_dir)):
        if entry.endswith(".py"):
            path = os.path.join(tool_dir, entry)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                chunks.append(f.read())
    return "\n".join(chunks)


@pytest.mark.parametrize("name", sorted(constitutional_names()))
def test_lib_engine_package_exists(name):
    """Contract 1: the engine lives in dazzlecmd_lib/core/<name>/."""
    pkg = os.path.join(_LIB_CORE, name)
    assert os.path.isdir(pkg), (
        f"'{name}' is in _CONSTITUTIONAL_NAMES but dazzlecmd_lib/core/{name}/ "
        f"does not exist -- a constitutional claim requires a lib engine."
    )
    assert os.path.isfile(os.path.join(pkg, "__init__.py"))


@pytest.mark.parametrize("name", sorted(constitutional_names()))
def test_tool_imports_the_lib_engine(name):
    """Contract 2: the user-facing tool wraps the lib engine, never its own."""
    src = _tool_source(name)
    if src is None:
        pytest.skip(f"no on-disk tool for constitutional '{name}' (allowed)")
    assert re.search(rf"from dazzlecmd_lib\.core\.{name}\b", src), (
        f"projects/core/{name} does not import dazzlecmd_lib.core.{name} -- "
        f"the '[lib]' marker would be a false claim (the links-fork bug class)."
    )


@pytest.mark.parametrize("name", sorted(constitutional_names()))
def test_tool_defines_no_duplicate_engine(name):
    """Contract 3: the tool is a thin CLI -- no second engine."""
    src = _tool_source(name)
    if src is None:
        pytest.skip(f"no on-disk tool for constitutional '{name}' (allowed)")
    key_symbols = _ENGINE_KEY_SYMBOLS.get(name)
    assert key_symbols is not None, (
        f"new constitutional name '{name}': add its engine key symbols to "
        f"_ENGINE_KEY_SYMBOLS so the no-duplicate-engine contract is enforced."
    )
    offenders = [s for s in key_symbols if s in src]
    assert not offenders, (
        f"projects/core/{name} re-defines engine symbols {offenders} -- a "
        f"duplicate engine (fork) that will drift from the lib's. Import them "
        f"from dazzlecmd_lib.core.{name} instead."
    )
