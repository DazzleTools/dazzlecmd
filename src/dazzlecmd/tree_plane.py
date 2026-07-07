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
    axis = f"{engine.command}:.meta:level"
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
    # the ROOT's two spellings are ONE node (ODR alias): the NAME
    # ("dazzlecmd", used by Absolute FQCNs) aliases to the COMMAND
    # ("dz", the tree root) -- prefix-aware, so dazzlecmd:core:find
    # and dazzlecmd:.level resolve on the tree like dz-spelled paths.
    name = getattr(engine, "name", None)
    if name and name != cmd:
        tree.graph.setdefault("aliases", {})[name] = cmd

    root = cmd
    if root in tree:
        # THE ROOT'S TYPE (user guardrail 2026-07-06): the root COMPOSES
        # its child axes/namespaces -- a ContinuumSpace, never a bare
        # Unified blob.
        tree.nodes[root]["kind"] = "ContinuumSpace"
        tree.nodes[root]["role"] = "aggregator-root"
        tree.nodes[root].setdefault("level", "aggregator")
        tree.nodes[root].setdefault(
            "instance_of", [f"{cmd}:.meta:level:aggregator"])

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
        node["instance_of"] = [f"{cmd}:.meta:level:{level}"]
        node.setdefault("help", getattr(kit, "description", "") or "")
        members = list(getattr(kit, "tools", None) or [])
        if members:
            node["members"] = [f"{cmd}:{m}" for m in members]
        # B-6 (the aliases-on-cards directive): a virtual kit's
        # name_rewrite entries are ALIAS declarations (ODR kind 1) --
        # attach each spelling to its TARGET tool's node
        for canonical, short in (getattr(kit, "name_rewrite", None)
                                 or {}).items():
            target = f"{cmd}:{canonical}"
            if target not in tree:
                tree.add_node(target, obj=None)
            tree.nodes[target].setdefault("aliases", []).append(
                f"{name}:{short}")

    for tool in (getattr(engine, "projects", None) or []):
        fqcn = getattr(tool, "_fqcn", None) or getattr(tool, "name", None)
        if not fqcn:
            continue
        ns = getattr(tool, "namespace", "") or fqcn.split(":", 1)[0]
        ns_key = f"{cmd}:{ns}"
        if ns_key not in tree:  # a namespace without a kit manifest
            tree.add_node(ns_key, obj=None, kind="Unified", role="kit",
                          level="kit",
                          instance_of=[f"{cmd}:.meta:level:kit"])
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
        node["instance_of"] = [f"{cmd}:.meta:level:{level}"]
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
        short = name.rsplit(":", 1)[-1]  # absolute spellings enrich too
        hits = [n for n in tree.nodes
                if n.rsplit(":", 1)[-1] == short
                and tree.nodes[n].get("instance_of")]
        if len(hits) != 1:
            return None, []
        node = tree.nodes[hits[0]]
        level = node.get("level", "?")
        handles = node.get("instance_of") or []
        level_line = f"{'Level:':<13}{level}"
        cmd = engine.command

        def _follow(h):
            return h[len(cmd):] if h.startswith(cmd + ":") else h

        fibers = [
            f"  instance of  {h}   ({cmd} info {_follow(h)})"
            for h in handles
        ]
        for m in (node.get("members") or []):  # B-6: followable members
            fibers.append(
                f"  member       {m}   ({cmd} info {_follow(m)})")
        for a in (node.get("aliases") or []):  # B-6: alias spellings
            fibers.append(f"  alias        {a}   (runs the same tool)")
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
        # the intercept runs PRE-discovery (the fast-path rider); an
        # INSTANCE key is worth the discovery cost -- run it on demand
        # (found live: the hook silently missed and a write landed)
        if not (getattr(engine, "projects", None) or []):
            import contextlib
            import io as _io
            with contextlib.redirect_stdout(_io.StringIO()):
                engine.discover()
        from dazzlecmd_lib.fqcn_tree import build_engine_tree, resolve_path
        tree = build_engine_tree(engine)
        node_key = resolve_path(tree, node_key)
        if node_key in tree and tree.nodes[node_key].get("instance_of"):
            return tree.nodes[node_key].get(prop)
    except Exception:
        return None
    return None


# --- B-7: the one alias registry (ODR DWP D10) + kit-frame PROJECTIONS
# (ODR DWP Case 2; the plan B-7; convergence DWP F11) ------------------

def alias_registry(engine):
    """D10: aliases are DATA declared once -- every surface projects
    from THIS dict (alias -> {"to": canonical, "provenance": str}).
    Seeded here: the root name/command pair + virtual-kit rewrites.
    The tree builder consumes it below; the FQCN dispatch tiers and the
    property value-aliases unify onto it at merge-back (D10 ledger)."""
    reg = getattr(engine, "_alias_registry", None)
    if reg is None:
        reg = {}
        cmd = engine.command
        name = getattr(engine, "name", None)
        if name and name != cmd:
            reg[name] = {"to": cmd, "provenance": "system:root-name"}
        for kit in (getattr(engine, "kits", None) or []):
            for canonical, short in (getattr(kit, "name_rewrite", None)
                                     or {}).items():
                reg[f"{cmd}:{kit.name}:{short}"] = {
                    "to": f"{cmd}:{canonical}",
                    "provenance": f"virtual-kit:{kit.name}"}
        engine._alias_registry = reg
    return reg


def graft_kit_frame_projections(engine, tree):
    """ODR Case 2 made real: the kit-frame verb view. The DEFINING home
    of each kit-applicable verb axis is the verb space
    (`dz:.meta:verb:<axis>`); `dz:.level:kit:management:<axis>` is a
    PROJECTION -- a derived node carrying the kit frame plus a SOURCE
    handle back to its definition. Supersedes the Row-3 heuristic with
    declared relations."""
    cmd = engine.command
    kit_rung = f"{cmd}:.level:kit"
    verb_root = f"{cmd}:.meta:verb"
    if kit_rung not in tree or verb_root not in tree:
        return
    mgmt = f"{kit_rung}:management"
    if mgmt not in tree:
        tree.add_node(mgmt, obj=None, kind="ContinuumSpace",
                      role="projection", source=verb_root,
                      help="the verb space, seen from the kit frame")
        tree.add_edge(kit_rung, mgmt)
    for axis in ("membership", "loading", "activation"):
        src_axis = f"{verb_root}:{axis}"
        if src_axis not in tree:
            continue
        proj_axis = f"{mgmt}:{axis}"
        if proj_axis not in tree:
            tree.add_node(proj_axis, obj=None, kind="Continuum",
                          role="projection", source=src_axis)
            tree.add_edge(mgmt, proj_axis)
        for pole in tree.successors(src_axis):
            pole_seg = pole.rsplit(":", 1)[-1]
            proj_pole = f"{proj_axis}:{pole_seg}"
            if proj_pole not in tree:
                tree.add_node(proj_pole, obj=None, kind="Unified",
                              role="projection", source=pole,
                              help=tree.nodes[pole].get("help", ""))
                tree.add_edge(proj_axis, proj_pole)


def register_aliases_on_tree(engine, tree):
    """The registry -> the tree's alias table (ONE source, projected)."""
    for alias, rec in alias_registry(engine).items():
        tree.graph.setdefault("aliases", {}).setdefault(alias, rec["to"])


# --- B-8: the expose property + the generator spike (convergence DWP
# D1/D2/D8; the plan B-8). The generated command = the ONE with a
# handler but no top-level surface: `dz management` (the quick-read). --
GENERATED_ROUTES = {
    # exposed node -> (command name, help, the _meta route it reuses)
    "management": ("management",
                   "Kit lifecycle state -- the composed axis quick-read",
                   "kit_management"),
}


def exposed_generated_commands(engine):
    """D2: `expose` is a PROPERTY -- the CLI surface is the exposed
    projection of the graph. A node opts in via the store
    (`dz :.meta:verb:management.expose=true`); flipping it adds/removes
    the generated command from `dz -h` LIVE (the B-8 AC)."""
    out = []
    try:
        store = engine.property_store
        for node_name, (cmd_name, help_text, meta) in GENERATED_ROUTES.items():
            key = f"{engine.command}:.meta:verb:{node_name}.expose"
            if store.get(key) is True:
                out.append((cmd_name, help_text, meta))
    except Exception:
        pass
    return out


def classify_verb(engine, name):
    """D8 -- the sufficiency classifier: HANDLER-backed verbs earn a
    generated command; PROPERTY-backed verbs dissolve into assignment
    (+ optional alias). The pinned demotion exhibits: use, reset."""
    PROPERTY_BACKED = {"use": "dz level=<rung> (the assignment surface)",
                       "reset": "dz prop delete .level (+ the default)",
                       "version": "dz.version (a derived property read)"}
    if name in PROPERTY_BACKED:
        return ("property-backed", PROPERTY_BACKED[name])
    return ("handler-backed", None)
