"""The TOTALITY AUDIT (B-1 / F10) -- the plan's ratchet.

THE TOTALITY INVARIANT (D7, the one-graph convergence DWP): every item
the system knows about must be FQCN-reachable from the root. An
unreachable item is MEASURED INCOMPLETENESS -- the stranded report IS
the development backlog, generated programmatically. This module
enumerates every item source, resolves each against the derived tree,
and reports the stranded set. The companion regression test ratchets:
the stranded set may only SHRINK.

Each stranded record names the mechanism that will home it (the
`homes_with` field) -- the report reads as a build plan.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# The two-tier reserved-property registry (issue #101). Stranded until
# the registry becomes an addressable node (the schema/F7 work).
RESERVED_VOCABULARY = (
    "kind", "ranks", "shape", "schema", "expose", "level", "default",
    "invariant", "subtype", "applies_at",
    "help", "version", "note", "recipe", "description", "tags",
    "members", "instance_of", "source", "current",
)


def _tree_for(engine):
    # the adopted mechanism (main 0.11.35-39 / lib 0.10.21): ONE tree
    # every surface shares -- build_engine_tree + engine.tree_extensions.
    from dazzlecmd_lib.fqcn_tree import build_engine_tree
    try:
        from dazzlecmd.commands.inspect import _graft_app_verbs
        from dazzlecmd.tree_plane import graft_instance_plane
        from dazzlecmd.tree_plane import (graft_kit_frame_projections,
                                          register_aliases_on_tree)
        for ext in (_graft_app_verbs, graft_instance_plane,
                    graft_kit_frame_projections, register_aliases_on_tree):
            if ext not in engine.tree_extensions:
                engine.tree_extensions.append(ext)
    except Exception:
        pass
    return build_engine_tree(engine)


def _resolve(tree, key: str) -> bool:
    from dazzlecmd_lib.fqcn_tree import resolve_path
    return resolve_path(tree, key) in tree


def totality_audit(engine, projects: Optional[list] = None,
                   kits: Optional[list] = None) -> Dict[str, Any]:
    """Enumerate every item source; return {"homed": int, "stranded":
    [records]} where each record = {item, source, homes_with}.
    When projects/kits are omitted, runs the engine's own discovery
    (the real population, not a synthetic one)."""
    cmd = engine.command
    if projects is None and kits is None:
        try:
            engine.discover()
            projects = list(getattr(engine, "projects", []) or [])
            kits = list(getattr(engine, "kits", []) or [])
        except Exception:
            projects, kits = [], []
    tree = _tree_for(engine)
    stranded: List[Dict[str, str]] = []
    homed = 0

    def check(item: str, key: str, source: str, homes_with: str) -> None:
        nonlocal homed
        if _resolve(tree, key):
            homed += 1
        else:
            stranded.append({"item": item, "source": source,
                             "homes_with": homes_with})

    # 1. discovered INSTANCES (tools + kits) -- the F1 plane
    def _fqcn_of(obj):
        for attr in ("_fqcn", "fqcn", "name"):
            v = getattr(obj, attr, None) or (
                obj.get(attr) if isinstance(obj, dict) else None)
            if v:
                return str(v)
        return str(obj)
    for p in (projects or []):
        check(_fqcn_of(p), f"{cmd}:{_fqcn_of(p)}", "discovery:tool",
              "F1 instance plane")
    for k in (kits or []):
        check(_fqcn_of(k), f"{cmd}:{_fqcn_of(k)}", "discovery:kit",
              "F1 instance plane")

    # 2. the parser's verbs (grafted by 2f slice 2 -- should be HOMED)
    try:
        from dazzlecmd.parsers import build_parser
        sub = build_parser([], engine=None)._subparsers._group_actions[0]
        for action in sub._choices_actions:
            name = action.dest
            hits = [n for n in tree.nodes
                    if n.rsplit(":", 1)[-1].lstrip(".") == name]
            if hits:
                homed += 1
            else:
                stranded.append({"item": name, "source": "parser:verb",
                                 "homes_with": "2f verb grafting"})
    except Exception:
        pass

    # 3. store keys -- homed when their NODE prefix resolves
    for key in engine.property_store.list_prefix(""):
        node = key.split(".", 1)[0]
        check(key, node, "store:key", "the owning node's plane")

    # 4. channels (log_lib's legacy flat names) -- until the verbosity
    #    mount / 2e union
    try:
        from dazzlecmd._vendor.log_lib.channels import KNOWN_CHANNELS
        for ch in KNOWN_CHANNELS:
            check(ch, f"{cmd}:.meta:verbosity:{ch}", "log_lib:channel",
                  "2e verbosity mount + channel union")
    except Exception:
        pass

    # 5. config.json top-level keys -- the F9 config ring
    try:
        for ck in (engine.config.data or {}):
            check(ck, f"{cmd}:.meta:config:{ck}", "config:key",
                  "F9 the config ring")
    except Exception:
        pass

    # 6. the reserved vocabulary (#101) -- the registry node (F7/schema)
    for name in RESERVED_VOCABULARY:
        check(name, f"{cmd}:.meta:prop:{name}", "registry:#101",
              "F7/schema: the registry node")

    # 7. THE TYPING TEST (user guardrail 2026-07-06): every node must
    #    BE one of the four ladder types (its obj's type, or its declared
    #    kind for derived nodes). Untyped nodes are stranded-class items.
    LADDER = {"Unified", "Groupable", "Continuum", "ContinuumSpace"}
    for nkey in tree.nodes:
        kind = tree.nodes[nkey].get("kind", "")
        base = kind.split(" ", 1)[0]
        if base in LADDER:
            homed += 1
        elif kind in ("namespace", "rung", "verb", "pending",
                      "aggregator-root", "kit", "tool", "virtual-kit"):
            # legacy role-as-kind spellings -- typed implicitly as
            # Unified; stranded until the renderers/grafts declare
            # kind=<ladder type> + role=<word> everywhere
            stranded.append({"item": nkey, "source": "tree:untyped",
                             "homes_with": "the typing alignment "
                                           "(kind=type + role)"})
        else:
            stranded.append({"item": nkey, "source": "tree:unknown-kind",
                             "homes_with": "the typing alignment"})

    # 8. THE ODR CHECK (ODR DWP: enforcement + D10): every projection
    #    names a resolvable SOURCE; every alias resolves on the tree.
    for nkey in tree.nodes:
        n = tree.nodes[nkey]
        if n.get("role") == "projection":
            src = n.get("source")
            if src and src in tree:
                # V-C's FAITHFULNESS check: a projection presents its
                # source TRULY -- its child segments must be a subset
                # of the source's child segments
                mine = {c.rsplit(":", 1)[-1] for c in tree.successors(nkey)}
                theirs = {c.rsplit(":", 1)[-1]
                          for c in tree.successors(src)}
                if mine <= theirs:
                    homed += 1
                else:
                    stranded.append({
                        "item": f"{nkey} (extra: {sorted(mine - theirs)})",
                        "source": "odr:unfaithful-projection",
                        "homes_with": "children must be a subset of the "
                                      "source's"})
            else:
                stranded.append({"item": nkey, "source": "odr:projection",
                                 "homes_with": "a resolvable source handle"})
    for alias, target in (tree.graph.get("aliases") or {}).items():
        if target in tree:
            homed += 1
        else:
            stranded.append({"item": f"{alias} -> {target}",
                             "source": "odr:alias",
                             "homes_with": "alias target must resolve"})

    return {"homed": homed, "stranded": stranded,
            "tree_nodes": len(tree.nodes)}


def render_stranded_report(result: Dict[str, Any]) -> str:
    lines = [f"totality: {result['homed']} homed, "
             f"{len(result['stranded'])} stranded "
             f"(tree: {result['tree_nodes']} nodes)"]
    by_home: Dict[str, List[str]] = {}
    for r in result["stranded"]:
        by_home.setdefault(r["homes_with"], []).append(
            f"{r['item']}  [{r['source']}]")
    for home, items in sorted(by_home.items()):
        lines.append(f"  homes with {home}: ({len(items)})")
        for it in sorted(items)[:8]:
            lines.append(f"    {it}")
        if len(items) > 8:
            lines.append(f"    ... +{len(items) - 8} more")
    return "\n".join(lines)
