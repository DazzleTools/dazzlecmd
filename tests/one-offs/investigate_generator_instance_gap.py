"""Diagnostic (2026-07-07, tester-unbounded merge-cert investigation):
WHY does tests/one-offs/surface_matrix_gen.py show zero instance/kit/
virtual-kit node classes while the live `dz info :.` root card shows
core/dazzletools/media/wtf (kits) + claude/f/md/windows (virtual-kits)?

Hypothesis: the generator constructs AggregatorEngine via the bare
__init__ (no project_root kwarg), unlike the live CLI's
AggregatorEngine.from_project(project_root, ...). graft_instance_plane
self-feeds via engine.discover() when engine.projects is empty, but
discover() falls back to the LEGACY find_project_root() walker, which
is anchored to dazzlecmd_lib/engine.py's OWN file location (the
library's install dir), not the dazzlecmd app's. That walk can't find
tools/kits siblings from inside a standalone library checkout, so
discover() returns early and the instance plane never populates.
"""
import os
import sys
import tempfile

from dazzlecmd_lib.engine import AggregatorEngine
from dazzlecmd_lib.fqcn_tree import build_engine_tree

print("=" * 70)
print("PART A: reproduce the generator's exact construction")
print("=" * 70)

engine_a = AggregatorEngine(name="dz", command="dz",
                             config_dir=tempfile.mkdtemp())
print("before configure_tree/build:")
print("  engine_a.project_root        =", engine_a.project_root)
print("  engine_a._project_root_hint  =", engine_a._project_root_hint)
print("  engine_a.projects (initial)  =", engine_a.projects)
print("  engine_a.kits (initial)      =", engine_a.kits)

try:
    from dazzlecmd.tree_plane import configure_tree
    configure_tree(engine_a)
except Exception as exc:
    print("  configure_tree raised:", repr(exc))

tree_a = build_engine_tree(engine_a)

print("after configure_tree + build_engine_tree (self-feed attempted):")
print("  engine_a.project_root        =", engine_a.project_root)
print("  engine_a.projects (post)     =", len(engine_a.projects or []))
print("  engine_a.kits (post)         =", len(engine_a.kits or []))

roles_a = {}
for n in tree_a.nodes:
    r = tree_a.nodes[n].get("role")
    if r:
        roles_a[r] = roles_a.get(r, 0) + 1
print("  tree_a role histogram        =", roles_a or "(none)")

# What does the legacy walker actually see when called with no start_path
# (i.e. anchored to dazzlecmd_lib/engine.py's own directory)?
import dazzlecmd_lib.engine as engine_mod
legacy_anchor = os.path.dirname(os.path.abspath(engine_mod.__file__))
print()
print("legacy find_project_root() anchor (no start_path given):")
print("  ", legacy_anchor)
print("  walked result:", engine_a.find_project_root())

print()
print("=" * 70)
print("PART B: what the LIVE CLI does -- from_project(real_root, ...)")
print("=" * 70)

import dazzlecmd
from dazzlecmd_lib.aggregator_config import find_aggregator_root

real_root = find_aggregator_root(
    os.path.dirname(os.path.abspath(dazzlecmd.__file__)))
print("  find_aggregator_root(dazzlecmd package dir) =", real_root)

engine_b = AggregatorEngine.from_project(
    real_root,
    is_root=True,
    config_dir=tempfile.mkdtemp(),
)
print("  engine_b.project_root         =", engine_b.project_root)
print("  engine_b._project_root_hint   =", engine_b._project_root_hint)

try:
    configure_tree(engine_b)
except Exception as exc:
    print("  configure_tree raised:", repr(exc))

tree_b = build_engine_tree(engine_b)
print("  engine_b.projects (post)      =", len(engine_b.projects or []))
print("  engine_b.kits (post)          =", len(engine_b.kits or []))

roles_b = {}
for n in tree_b.nodes:
    r = tree_b.nodes[n].get("role")
    if r:
        roles_b[r] = roles_b.get(r, 0) + 1
print("  tree_b role histogram         =", roles_b or "(none)")

print()
print("=" * 70)
print("PART C: the minimal fix -- pass project_root to the bare ctor")
print("=" * 70)

engine_c = AggregatorEngine(name="dz", command="dz",
                             config_dir=tempfile.mkdtemp(),
                             project_root=real_root)
print("  engine_c._project_root_hint   =", engine_c._project_root_hint)
try:
    configure_tree(engine_c)
except Exception as exc:
    print("  configure_tree raised:", repr(exc))
tree_c = build_engine_tree(engine_c)
print("  engine_c.projects (post)      =", len(engine_c.projects or []))
print("  engine_c.kits (post)          =", len(engine_c.kits or []))
roles_c = {}
for n in tree_c.nodes:
    r = tree_c.nodes[n].get("role")
    if r:
        roles_c[r] = roles_c.get(r, 0) + 1
print("  tree_c role histogram         =", roles_c or "(none)")

print()
print("VERDICT:")
if roles_a.get("kit") or roles_a.get("instance"):
    print("  Part A already populates instances -- hypothesis REJECTED,"
          " look elsewhere.")
else:
    print("  Part A (generator's exact construction) = NO instance/kit"
          " nodes, confirming the gap.")
if roles_b.get("kit"):
    print("  Part B (from_project, live-CLI style) DOES populate --"
          " confirms from_project's project_root wiring is the"
          " differentiator.")
if roles_c.get("kit"):
    print("  Part C (bare ctor + project_root=... only) ALSO populates --"
          " confirms the missing project_root kwarg is sufficient root"
          " cause, independent of from_project()'s other machinery.")
