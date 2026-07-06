"""The INSTANCE PLANE (B-2/B-3 -- the fiber-work plan).

Instances join the one tree UNDER THEIR CONTAINMENT PATHS (dz:core:safedel
under dz:core under dz) -- the user world keeps its flat, adhoc shape;
the machinery world keeps its hidden door; the INSTANCE-OF ring joins
them (ODR relation kind 2: handles by name, never copies).

Level derivation (the instance-ring DWP's rule-set, interim until
declared-level lands with the property mechanism):
  aggregator root          -> aggregator
  kit manifest, virtual    -> virtual-kit   (the rung is derived
                                             app-side at rank -3/2 until
                                             the lib ladder adopts it)
  kit manifest             -> kit
  tool, constitutional     -> internaltool  (engine overlaid from the lib)
  tool                     -> tool
"""

from __future__ import annotations

from fractions import Fraction


def _derive_level(kind: str, entity) -> str:
    if kind == "kit":
        if getattr(entity, "virtual", False):
            return "virtual-kit"
        return "kit"
    # tools
    try:
        from dazzlecmd_lib.core import is_constitutional
        if is_constitutional(getattr(entity, "name", "")):
            return "internaltool"
    except Exception:
        pass
    return "tool"


def graft_virtual_kit_rung(engine, tree) -> None:
    """B-4 (interim, app-derived): the `virtual-kit` rung -- named in the
    frozen ladders, absent from the shipped LEVEL_CONTINUUM -- joins the
    TREE at the mediant between tool(-2) and kit(-1): rank -3/2. The lib
    ladder adopts it properly at merge-back (densify_between)."""
    axis = f"{engine.command}:.level"
    key = f"{axis}:virtual-kit"
    if axis in tree and key not in tree:
        tree.add_node(key, obj=None, kind="rung", axis=axis,
                      rank=Fraction(-3, 2),
                      help="a LOGICAL grouping overlay (aliases over "
                           "canonical tools; f, claude, ...)")
        tree.add_edge(axis, key)


def graft_instance_plane(engine, tree) -> None:
    """Instances (kits + tools) join under containment paths, carrying
    derived `level` + `instance_of` HANDLES (list-valued, R-2) + the
    card fields. The rung's extension stays a VIEW (I-A: instances'
    parents are containment, never the rung)."""
    cmd = engine.command
    graft_virtual_kit_rung(engine, tree)

    root = cmd
    if root in tree:
        # THE ROOT'S TYPE (user guardrail 2026-07-06): the root COMPOSES
        # its child axes/namespaces -- a ContinuumSpace, never a bare
        # Unified blob.
        tree.nodes[root]["kind"] = "ContinuumSpace"
        tree.nodes[root]["role"] = "aggregator-root"
        tree.nodes[root].setdefault("level", "aggregator")
        tree.nodes[root].setdefault(
            "instance_of", [f"{cmd}:.level:aggregator"])

    for kit in (getattr(engine, "kits", None) or []):
        name = getattr(kit, "name", None)
        if not name:
            continue
        key = f"{cmd}:{name}"
        level = _derive_level("kit", kit)
        if key not in tree:
            tree.add_node(key, obj=None)
            tree.add_edge(root, key)
        node = tree.nodes[key]
        # TYPING (the guardrail): a kit COMPOSES tools -> Continuum-like
        # container; typed Unified until its member axis materializes
        # (the kind ladder governs promotion). role carries the ontology.
        node["kind"] = "Unified"
        node["role"] = level
        node["level"] = level
        node["instance_of"] = [f"{cmd}:.level:{level}"]
        node.setdefault("help", getattr(kit, "description", "") or "")
        members = list(getattr(kit, "tools", None) or [])
        if members:
            node["members"] = [f"{cmd}:{m}" for m in members]

    for tool in (getattr(engine, "projects", None) or []):
        fqcn = getattr(tool, "_fqcn", None) or getattr(tool, "name", None)
        if not fqcn:
            continue
        ns = getattr(tool, "namespace", "") or fqcn.split(":", 1)[0]
        ns_key = f"{cmd}:{ns}"
        if ns_key not in tree:  # a namespace without a kit manifest
            tree.add_node(ns_key, obj=None, kind="Unified", role="kit",
                          level="kit",
                          instance_of=[f"{cmd}:.level:kit"])
            tree.add_edge(root, ns_key)
        key = f"{cmd}:{fqcn}"
        level = _derive_level("tool", tool)
        if key not in tree:
            tree.add_node(key, obj=None)
            tree.add_edge(ns_key, key)
        node = tree.nodes[key]
        node["kind"] = "Unified"
        node["role"] = level  # tool | internaltool
        node["level"] = level
        node["instance_of"] = [f"{cmd}:.level:{level}"]
        node.setdefault("help",
                        getattr(tool, "description", "") or "")
        version = getattr(tool, "version", None)
        if version:
            node["version"] = str(version)


def instance_card_sections(engine, name):
    """Card sections for an instance (the user's clarity directive:
    what's IDENTITY, what's a FIBER, what's internal). Returns
    (level_line, fibers_lines) -- level joins the identity block;
    the Fibers block carries the ring (instance_of now; aliases and
    members join at B-5/B-6)."""
    try:
        from dazzlecmd_lib.fqcn_tree import build_engine_tree
        tree = build_engine_tree(engine)
        hits = [n for n in tree.nodes
                if n.rsplit(":", 1)[-1] == name
                and tree.nodes[n].get("instance_of")]
        if len(hits) != 1:
            return None, []
        node = tree.nodes[hits[0]]
        level = node.get("level", "?")
        handles = node.get("instance_of") or []
        level_line = f"{'Level:':<13}{level}"
        cmd = engine.command
        fibers = [
            f"  instance of  {h}   ({cmd} info "
            f"{h[len(cmd):] if h.startswith(cmd + ':') else h})"
            for h in handles
        ]
        for m in (node.get("members") or [])[:0]:  # members render at B-6
            pass
        return level_line, fibers
    except Exception:
        return None, []


def instance_level_line(engine, name):
    """The HEADLINE reflection (AC-F2): the Level line for a legacy tool
    card -- `Level: internaltool  (dz:.level:internaltool)`, the handle
    followable via `dz info`. Returns None when the tree has no verdict."""
    try:
        from dazzlecmd_lib.fqcn_tree import build_engine_tree
        tree = build_engine_tree(engine)
        hits = [n for n in tree.nodes
                if n.rsplit(":", 1)[-1] == name
                and tree.nodes[n].get("instance_of")]
        if len(hits) == 1:
            node = tree.nodes[hits[0]]
            handles = node["instance_of"]
            return (f"Level:       {node.get('level', '?')}   "
                    f"({', '.join(handles)})")
    except Exception:
        pass
    return None


# --- B-5: the metadata ring's derived reads (instance-ring DWP F4;
# the plan B-5; rides lib 0.10.22's engine.derived_reads tier) --------
_DERIVED_INSTANCE_FIELDS = ("version", "level", "help")


def derived_instance_read(engine, key):
    """A derived read for INSTANCE metadata: `dz:core:safedel.version`
    answers from the item's own manifest data (via the tree), read-only
    (the authority model). Root-level keys (`dz.level`) never match --
    the node part must step past the root, so the foreground property
    stays user-writable."""
    node_key, dot, prop = key.partition(".")
    if not dot or prop not in _DERIVED_INSTANCE_FIELDS:
        return None
    if ":" not in node_key[len(engine.command):].lstrip(":"):
        pass  # single-segment instances (kits) are fine; root is not
    if node_key == engine.command:
        return None  # the root's properties are NOT instance metadata
    try:
        from dazzlecmd_lib.fqcn_tree import build_engine_tree, resolve_path
        tree = build_engine_tree(engine)
        node_key = resolve_path(tree, node_key)
        if node_key in tree and tree.nodes[node_key].get("instance_of"):
            return tree.nodes[node_key].get(prop)
    except Exception:
        return None
    return None
