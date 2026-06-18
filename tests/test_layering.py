"""Import-layering contract -- the capstone of the dazzle-lib foundation lift (B3e).

The lift (B3a-B3c) moved the pure primitives down into the dazzle-lib bedrock.
This test LOCKS the layering so nothing drifts back:

  dazzlecmd (app)  ->  dazzlecmd_lib  ->  dazzle_lib (bedrock)        [downward only]

Contracts (stdlib AST inspection -- the same idiom as dazzle-lib's own
``tests/test_charter.py``; no import-linter dependency, and it ALWAYS runs in the
green-suite gate rather than skipping where a tool isn't installed):

  A. ``dazzlecmd_lib`` never imports the ``dazzlecmd`` APP -- the library stays
     usable on its own (the app is just one consumer of the lib).
  B. The lift-shim modules (continuum / states / contexts) import their primitives
     FROM ``dazzle_lib`` -- proving they CONSUME the bedrock, not re-implement it.
  C. ``dazzle_lib`` imports nothing from ``dazzlecmd``/``dazzlecmd_lib`` -- the
     bedrock is independent (belt-and-braces with dazzle-lib's own charter test;
     stated here from the consumer's vantage so a back-edge can't slip in).
"""

import ast
from pathlib import Path

import dazzlecmd_lib

LIB_DIR = Path(dazzlecmd_lib.__file__).parent


def _import_roots(path: Path):
    """Top-level package of every import in a module (``a.b.c`` -> ``a``)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:        # absolute imports only
                roots.add(node.module.split(".")[0])
    return roots


def _lib_modules():
    return sorted(LIB_DIR.glob("*.py"))


def test_lib_never_imports_the_app():
    """Contract A: dazzlecmd_lib must not depend on the dazzlecmd app."""
    violations = {p.name: sorted(_import_roots(p) & {"dazzlecmd"})
                  for p in _lib_modules()
                  if "dazzlecmd" in _import_roots(p)}
    assert not violations, (
        f"LAYERING VIOLATION -- dazzlecmd_lib imports the dazzlecmd APP: {violations}. "
        f"The library is a consumer-independent layer; the app depends on the lib, "
        f"never the reverse."
    )


def test_lift_shims_consume_the_bedrock():
    """Contract B: the lifted modules import their primitives from dazzle_lib."""
    for name in ("continuum.py", "states.py", "contexts.py"):
        path = LIB_DIR / name
        assert path.exists(), f"expected lift-shim module {name} in dazzlecmd_lib"
        assert "dazzle_lib" in _import_roots(path), (
            f"{name} must import its primitives FROM dazzle_lib (the bedrock) -- "
            f"the lift direction is downward; it consumes the bedrock, not re-derives it."
        )


def test_bedrock_is_independent():
    """Contract C: dazzle_lib imports nothing from dazzlecmd / dazzlecmd_lib."""
    try:
        import dazzle_lib
    except ImportError:                                # pragma: no cover
        import pytest
        pytest.skip("dazzle_lib not importable in this environment")
    bedrock_dir = Path(dazzle_lib.__file__).parent
    forbidden = {"dazzlecmd", "dazzlecmd_lib"}
    violations = {}
    for p in bedrock_dir.glob("*.py"):
        bad = _import_roots(p) & forbidden
        if bad:
            violations[p.name] = sorted(bad)
    assert not violations, (
        f"LAYERING VIOLATION -- the dazzle-lib bedrock imports a consumer: {violations}. "
        f"The bedrock must depend on nothing in the stack above it."
    )
