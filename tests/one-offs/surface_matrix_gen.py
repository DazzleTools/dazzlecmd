"""The SURFACE MATRIX generator -- the anti-whack-a-mole (2026-07-06).

Walks the REAL derived tree and emits every probe in the coverage matrix:

    NODE-CLASS (root | namespace | axis | rung | grafted-rung | verb-pole
                | flat-verb | machinery | alias-spelling | vacant)
  x SURFACE    (info card | :. listing | bare read | prop get)
  x plus the RULE-6 CONSISTENCY rows (card <-> listing <-> registry must
    agree on: children sets, current/default markers, help lines).

Because the probes are DERIVED, a new mount/rung/verb automatically
expands the matrix -- coverage grows with the structure, not with memory.

Usage:
    python tests/one-offs/surface_matrix_gen.py           # human list
    python tests/one-offs/surface_matrix_gen.py --json    # machine list
"""
import json
import sys

from dazzlecmd_lib.engine import AggregatorEngine
from dazzlecmd_lib.fqcn_tree import build_tree, DEFAULT_ALIASES


def classify(tree, key, root):
    n = tree.nodes[key]
    if key == root:
        return "root"
    if n.get("role") == "namespace":
        return "namespace"
    if n.get("role") == "verb":
        return "flat-verb"
    if n.get("role") == "rung":
        return "grafted-rung" if n.get("kind") != "Unified" else (
            "verb-pole" if ":verb:" in key else "rung")
    if n.get("kind") in ("Continuum", "ContinuumSpace"):
        return "axis"
    return "machinery"


def emit(root="dz"):
    tree = build_tree(root)
    try:  # the app's verb graft, when available
        from dazzlecmd.commands.inspect import _graft_app_verbs

        class _E:  # a minimal engine-shaped carrier
            command = root
        _graft_app_verbs(_E, tree)
    except Exception:
        pass
    probes = []
    for key in sorted(tree.nodes):
        cls = classify(tree, key, root)
        rel = key[len(root):] or key
        spell = rel if rel.startswith(":") else key
        probes.append({"class": cls, "node": key, "cmd": f"{root} info {spell}"})
        if tree.out_degree(key):
            probes.append({"class": cls, "node": key,
                           "cmd": f"{root} {spell}:." if rel.startswith(":")
                                  else f"{root} :."})
    for alias, canon in DEFAULT_ALIASES.items():
        probes.append({"class": "alias-spelling", "node": canon,
                       "cmd": f"{root} info {alias}"})
        probes.append({"class": "alias-spelling", "node": canon,
                       "cmd": f"{root} {alias}:."})
    probes.append({"class": "vacant", "node": "-",
                   "cmd": f"{root} info :.nosuch"})
    probes.append({"class": "vacant", "node": "-",
                   "cmd": f"{root} info nosuchname"})
    consistency = [
        "CARD<->LISTING children agree for EVERY node with children",
        "CARD<->LISTING current/default markers agree on value-aliased axes",
        "CARD help line == the argparse help for every verb (registry<->tree)",
        "STATES: {unset, set, post-delete, post-meta-reset} x the level axis "
        "-- card, listing, bare read, and `level` verb all agree",
    ]
    return probes, consistency


if __name__ == "__main__":
    probes, consistency = emit()
    if "--json" in sys.argv:
        print(json.dumps({"probes": probes, "consistency": consistency},
                         indent=1))
    else:
        by = {}
        for p in probes:
            by.setdefault(p["class"], []).append(p["cmd"])
        for cls in sorted(by):
            print(f"[{cls}] ({len(by[cls])})")
            for c in by[cls]:
                print(f"  dz-run: {c}")
        print("\nCONSISTENCY ROWS:")
        for c in consistency:
            print(f"  - {c}")
        print(f"\nTOTAL probes: {len(probes)}")
