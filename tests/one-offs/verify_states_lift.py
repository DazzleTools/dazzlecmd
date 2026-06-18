"""Verify the B3b states lift preserved the executable logic VERBATIM.

move-code post-move check: the generic types I wrote into dazzle_lib/states.py
must be code-identical to the pre-lift dazzlecmd_lib/states.py definitions, modulo
exactly TWO deliberate Step-4 modifications: (1) reworded docstrings, and (2) the
``fqcn``/``fqcn_fate`` -> ``identity``/``identity_fate`` rename that neutralized
the bedrock's identity vocabulary (the aggregator FQCN concept doesn't belong in
the domain-neutral bedrock). We strip docstrings AND apply that exact rename to
the baseline before comparing ASTs -- so the rename is allowed but ANY OTHER
change to a field default, a validation branch, an error message, or a method
body fails. This proves the lift changed nothing except the one decided rename.

Baseline (verbatim): git HEAD's packages/dazzlecmd-lib/src/dazzlecmd_lib/states.py
(the file BEFORE the partial-shim edit). New: C:/code/dazzle-lib/dazzle_lib/states.py
"""

import ast
import subprocess
import sys

GENERIC_NAMES = [
    "_Open", "OPEN", "_admits", "Reversibility", "StateAxis", "EntityState",
    "Transition", "CompositeTransition", "TransitionRegistry", "_Unset",
    "_UNSET", "assert_round_trip", "observe",
]


def _strip_docstrings(node):
    """Return a copy of node with every docstring (first Constant-str stmt of a
    module/class/function) removed, so docstring rewording doesn't count."""
    for n in ast.walk(node):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = n.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                n.body = body[1:]
    return node


def _defs_by_name(tree):
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            out[node.name] = node
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = node
    return out


def main():
    orig_src = subprocess.run(
        ["git", "show", "HEAD:packages/dazzlecmd-lib/src/dazzlecmd_lib/states.py"],
        capture_output=True, text=True, check=True,
    ).stdout
    # Apply the decided identity-vocabulary neutralization to the baseline so the
    # comparison allows exactly it (and nothing else). Order matters:
    #   1) the REVERSIBLE error message dropped the dazzlecmd "(C1)" label,
    #   2) fqcn_fate -> identity_fate (before the bare-fqcn pass),
    #   3) fqcn -> identity.
    # Docstrings are stripped before comparing, so docstring hits are harmless.
    orig_src = (orig_src
                .replace("fqcn (C1); got ", "identity; got ")
                .replace("fqcn_fate", "identity_fate")
                .replace("fqcn", "identity"))
    with open(r"C:/code/dazzle-lib/dazzle_lib/states.py", encoding="utf-8") as f:
        new_src = f.read()

    orig_defs = _defs_by_name(ast.parse(orig_src))
    new_defs = _defs_by_name(ast.parse(new_src))

    mismatches = []
    missing = []
    for name in GENERIC_NAMES:
        if name not in orig_defs:
            mismatches.append(f"{name}: NOT FOUND in original baseline")
            continue
        if name not in new_defs:
            missing.append(name)
            continue
        a = ast.dump(_strip_docstrings(orig_defs[name]))
        b = ast.dump(_strip_docstrings(new_defs[name]))
        if a != b:
            mismatches.append(f"{name}: AST DIFFERS (logic changed, not just docstring)")

    print(f"checked {len(GENERIC_NAMES)} generic definitions")
    if missing:
        print(f"MISSING from new module: {missing}")
    if mismatches:
        print("FAIL -- the lift was NOT verbatim:")
        for m in mismatches:
            print(f"  - {m}")
        sys.exit(1)
    print("OK -- every lifted definition is AST-identical to the verbatim baseline")
    print("     (docstrings/comments excluded; logic, defaults, branches, messages preserved)")


if __name__ == "__main__":
    main()
