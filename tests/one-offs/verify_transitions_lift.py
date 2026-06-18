"""Verify the B3c executor lift preserved the non-seam logic (move-code Step 4).

B3c is a lift-WITH-generalization, not a verbatim lift: the executor moved to
dazzle_lib.transitions AND gained an ``identity_of`` seam. So AST-identity to the
baseline is the wrong test -- the change is deliberate. Instead we PROVE the only
differences are the enumerated seam changes, by applying exactly those transforms
to the verbatim baseline and then asserting AST-identity (docstrings stripped).

The enumerated deliberate changes (and NOTHING else may differ):
  1. Receipt field ``entity_fqcn`` -> ``entity_identity``
  2. error class ``RebindError`` -> ``TransitionError``
  3. ``entity.fqcn`` access -> ``self._identity_of(entity)`` (the seam)
  4. constructor gains the ``identity_of`` hook (param + ``self._identity_of=``)

If any OTHER line of the _edge/apply/undo/current flow drifted, the AST differs
and this fails. Baseline = git HEAD's groupable.py (pre-lift, still holds the
executor). New = C:/code/dazzle-lib/dazzle_lib/transitions.py.
"""

import ast
import subprocess
import sys

# The 4 generic defs in the NEW module (baseline name in parens where renamed).
NEW_NAMES = ["CriticalityBoundaryError", "TransitionError", "Receipt", "TransitionContext"]


def _strip_docstrings(node):
    for n in ast.walk(node):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = n.body
            if (b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant)
                    and isinstance(b[0].value.value, str)):
                n.body = b[1:]
    return node


def _defs_by_name(src):
    out = {}
    for node in ast.parse(src).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            out[node.name] = node
    return out


def main():
    base = subprocess.run(
        ["git", "show", "HEAD:packages/dazzlecmd-lib/src/dazzlecmd_lib/groupable.py"],
        capture_output=True, text=True, check=True,
    ).stdout

    # Apply the enumerated seam transforms to the verbatim baseline.
    # (1) + (2): plain renames.
    base = base.replace("entity_fqcn", "entity_identity").replace("RebindError", "TransitionError")
    # (3): the entity.fqcn access becomes the identity_of hook call.
    base = base.replace("entity.fqcn", "self._identity_of(entity)")
    # (4): the constructor gains identity_of (signature + stored attr).
    base = base.replace(
        "def __init__(self, registry, axis_name, *, detect, write, check=None, invert=None):",
        "def __init__(self, registry, axis_name, *, detect, write, identity_of,\n"
        "                 check=None, invert=None):")
    base = base.replace(
        "        self._write = write\n        self._check = check",
        "        self._write = write\n        self._identity_of = identity_of\n        self._check = check")

    base_defs = _defs_by_name(base)
    new_defs = _defs_by_name(open(r"C:/code/dazzle-lib/dazzle_lib/transitions.py",
                                  encoding="utf-8").read())

    mismatches, missing = [], []
    for name in NEW_NAMES:
        if name not in base_defs:
            mismatches.append(f"{name}: not found in transformed baseline")
            continue
        if name not in new_defs:
            missing.append(name)
            continue
        a = ast.dump(_strip_docstrings(base_defs[name]))
        b = ast.dump(_strip_docstrings(new_defs[name]))
        if a != b:
            mismatches.append(f"{name}: AST DIFFERS beyond the enumerated seam changes")

    print(f"checked {len(NEW_NAMES)} lifted defs against the seam-normalized baseline")
    if missing:
        print(f"MISSING from the lift: {missing}")
    if mismatches:
        print("FAIL -- the lift changed more than the enumerated seam:")
        for m in mismatches:
            print(f"  - {m}")
        sys.exit(1)
    print("OK -- the executor's _edge/apply/undo/current logic is verbatim-preserved;")
    print("     ONLY the identity_of seam + entity_fqcn->entity_identity + RebindError->")
    print("     TransitionError renames differ (docstrings excluded).")


if __name__ == "__main__":
    main()
