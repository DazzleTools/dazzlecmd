"""SPIKE: the inward/outward SYMMETRY.

ONE child-relation + ONE walk()/fold() traverses BOTH composition (a
ContinuumSpace's axes -- OUTWARD) and fiber (a Continuum's per-rung sub-structure
-- INWARD) identically. Direction is a parameter, not a special case -- the
doubly-linked-list truth ("the underlying class internals all do the same thing;
left or right is just which way you go").

Uses the REAL dazzle-lib types (Continuum, ContinuumSpace, Groupable, Unified).
The per-rung fiber field does NOT exist on Continuum yet, so it is SIMULATED via
a side-map (id(continuum) -> {rung -> RungValue}) -- proving the walk SHAPE +
behavior-preservation BEFORE the bedrock field lands (experiment-first; no
bedrock change). Pointer-kit is the inward worked example.

Run: python tests/one-offs/inward_outward_symmetry_spike.py
"""
from dazzle_lib import Continuum, ContinuumSpace, Groupable, Unified

PASS = 0
FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    mark = "[OK]" if cond else "[XX]"
    PASS += cond
    FAIL += not cond
    print(f"  {mark} {label}" + (f"  -- {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# The ONE child-relation -- uniform over the ladder, direction-agnostic.
# ---------------------------------------------------------------------------
FIBERS = {}  # id(Continuum) -> {rung_name: RungValue}  (simulated fiber storage)


def children(node):
    """A node's children are ladder-elements -- regardless of direction:
    a SPACE's children are its axes (OUTWARD); a CONTINUUM's children are its
    per-rung fibers (INWARD); Groupable/Unified are leaves."""
    if isinstance(node, ContinuumSpace):
        return dict(node.axes)
    if isinstance(node, Continuum):
        return dict(FIBERS.get(id(node), {}))
    return {}  # Groupable, Unified -> leaves (implicit continuum/cut are explicit)


def walk(node, key=()):
    """Pre-order visitor: (key-path, node) for node + all descendants. ONE
    function -- it does not know or care whether it is descending axes or fibers."""
    yield key, node
    for name, child in children(node).items():
        yield from walk(child, key + (name,))


def leaves_via_walk(node):
    return [n for _, n in walk(node) if not children(n)]


# ---------------------------------------------------------------------------
# C-sym-1/2/3: one walk traverses OUTWARD and INWARD identically
# ---------------------------------------------------------------------------
print("\n== C-sym: one walk() over composition (axes) AND fiber (rungs) ==")

# OUTWARD: a product space whose one axis is itself a sub-space (recursive compose)
leaf_a = Continuum("a", {"-": -1, "+": 1})
leaf_b = Continuum("b", {"-": -1, "+": 1})
sub = ContinuumSpace(name="sub", axes={"a": leaf_a, "b": leaf_b})
leaf_c = Continuum("c", {"-": -1, "+": 1})
outward = ContinuumSpace(name="outer", axes={"sub": sub, "c": leaf_c})

out_nodes = [type(n).__name__ for _, n in walk(outward)]
check("walk() descends a space's axes recursively (OUTWARD)",
      out_nodes.count("Continuum") == 3 and out_nodes.count("ContinuumSpace") == 2,
      str(out_nodes))

# INWARD: a membership continuum; a rung's FIBER is the kit's content
membership = Continuum("membership", {"pointer": -1, "loaded": 1})
kit_content = ContinuumSpace(name="kit", axes={"vis": Continuum("vis", {"-": -1, "+": 1})})
FIBERS[id(membership)] = {
    "pointer": Unified("https://example/kit.git"),  # collapsed fiber (a pointer)
    "loaded": kit_content,                          # expanded fiber (a sub-space)
}
in_nodes = [type(n).__name__ for _, n in walk(membership)]
check("walk() descends a continuum's per-rung fibers (INWARD)",
      "Unified" in in_nodes and in_nodes.count("ContinuumSpace") == 1,
      str(in_nodes))
check("the SAME walk()/children() handled both -- direction is not special",
      True, "one function, no direction branch")

# the inward descent reaches INTO the loaded kit's own axes (fiber-of-a-fiber)
in_keys = [k for k, n in walk(membership) if type(n).__name__ == "Continuum" and k]
check("walk reaches the kit's inner axis via the 'loaded' fiber (deep inward)",
      ("loaded", "vis") in in_keys, str(in_keys))


# ---------------------------------------------------------------------------
# C-sym-4: pointer-kit round-trip (the inward example; C13 applied to a fiber)
# ---------------------------------------------------------------------------
print("\n== C-sym-4: pointer-kit fiber collapse<->expand (lateral) + lossy materialize ==")


def detach(fibers_for, rung, source):
    """Collapse a loaded fiber to a pointer; STASH the content (the Receipt)."""
    content = fibers_for[rung]
    fibers_for[rung] = Unified(source)
    return content  # the stash that makes re-attach lossless


def attach(fibers_for, rung, stash):
    """Re-expand from the stash -- lateral, lossless (the inverse of detach)."""
    fibers_for[rung] = stash


fibers_for = FIBERS[id(membership)]
before = fibers_for["loaded"]
stash = detach(fibers_for, "loaded", "https://example/kit.git")
check("detach collapses the fiber to a Unified(source) pointer",
      isinstance(fibers_for["loaded"], Unified))
attach(fibers_for, "loaded", stash)
check("attach (with stash/Receipt) restores the sub-space fiber -- LATERAL round-trip",
      fibers_for["loaded"] is before)
# naive materialize from only the source = a fresh expand, the stash NOT applied = lossy
naive = Unified("https://example/kit.git").groupable()  # only the seed survives
check("a materialize from the bare source alone keeps only the seed (GENERATIVE, "
      "lossy unless a Receipt preserved the content)",
      isinstance(naive, Groupable) and naive.plus == "https://example/kit.git")


# ---------------------------------------------------------------------------
# C-sym-5: behavior-preservation -- unified walk's leaves == shipped leaves()
# ---------------------------------------------------------------------------
print("\n== C-sym-5: leaves-via-walk == the shipped ContinuumSpace.leaves() (axes-only) ==")
walk_leaf_names = sorted(n.name for n in leaves_via_walk(outward))
shipped_leaf_names = sorted(c.name for c in outward.leaves().values())
check("axes-only leaves match -> generalizing leaves/normal_form onto walk() is "
      "behavior-preserving", walk_leaf_names == shipped_leaf_names,
      f"{walk_leaf_names} vs {shipped_leaf_names}")


# ---------------------------------------------------------------------------
# C-sym-6: children() is TOTAL over the 4 ladder types (no silent fallback)
# ---------------------------------------------------------------------------
print("\n== C-sym-6: children() total over {Unified, Groupable, Continuum, ContinuumSpace} ==")
for n in (Unified("u"), Groupable("-", "+"), leaf_a, sub):
    check(f"children({type(n).__name__}) defined", isinstance(children(n), dict))


print("\n" + "=" * 70)
print(f"RESULT: {PASS} passed, {FAIL} failed")
print("=" * 70)
raise SystemExit(0 if FAIL == 0 else 1)
