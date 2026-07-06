"""FIXED 2026-07-06 (lib 0.10.21-alpha + app 0.11.37-alpha): living
regressions in test_info_fiber_cards.py::TestMatrixSweepFixes."""
"""Repro: `dz info :.meta:verb` (card) and `dz :.meta:verb:.` (listing) show
DIFFERENT children sets for the SAME node -- a consistency-row-1 violation
("CARD<->LISTING children agree for EVERY node with children").

Found during the v0.11.36-alpha surface-matrix sweep.

  dz info :.meta:verb  -- contains: activation, info, list, loading,
                           membership, mode, new, projection, prop, setup,
                           tree, use, version                (13 children)
  dz :.meta:verb:.     -- structure: activation, loading, membership,
                           mode, projection                   (5 children)

The listing is missing all 8 "flat-verb" children (info, list, new, prop,
setup, tree, use, version).

Root cause: those 8 nodes exist ONLY after `_graft_app_verbs`
(dazzlecmd/src/dazzlecmd/commands/inspect.py:96) runs -- it walks the
app's LIVE argparse parser and synthesizes a flat tree node for every
top-level verb that has no existing tree-node match (the `elif not hits`
branch). The CARD path (`_info_tree_node`, inspect.py:126-135) explicitly
calls `build_tree(...)` THEN `_graft_app_verbs(engine, tree)` before
resolving the node.

The LISTING path lives in the LIB, not the app:
`dazzlecmd_lib/prop_commands.py` (~line 290-292) calls
`build_tree(engine.command)` directly and NEVER calls `_graft_app_verbs`
(which is an app-only function -- the lib has no dependency on the app's
parsers module). So the lib's listing renderer only ever sees the 5
verb-axis Continuum mounts that come from the base VERB_SPACE registry,
never the 8 argparse-only flat verbs the app grafts on top.

This is exactly the "a new mount/rung/verb expands this checklist
automatically" premise from the checklist header cutting the other way:
the app-side graft reached one surface (card) but not the other
(listing), because they are two independently-built trees.

Run (bare dz CLI, isolated config):
    python tests/one-offs/repro_verb_listing_missing_flat_verbs.py
"""
import os
import re
import subprocess
import sys
import tempfile

KIND_WORDS = ("Unified", "ContinuumSpace", "Continuum")


def run(args, config_path):
    env = dict(os.environ)
    env["DAZZLECMD_CONFIG"] = config_path
    return subprocess.run(
        ["dz"] + args, env=env, capture_output=True, text=True
    )


def parse_children(text, section_marker):
    lines = text.splitlines()
    out = []
    in_section = False
    for line in lines:
        if section_marker in line:
            in_section = True
            continue
        if in_section:
            if not line.startswith("  "):
                break
            stripped = line.strip()
            if not stripped or stripped.startswith("properties:") or \
                    stripped.startswith("(no properties"):
                break
            best = None
            for kw in KIND_WORDS:
                idx = line.find(kw)
                if idx != -1 and (best is None or idx < best):
                    best = idx
            if best is None:
                continue
            out.append(line[:best].strip())
    return out


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        config_path = os.path.join(tmp, "config.json")

        card = run(["info", ":.meta:verb"], config_path)
        listing = run([":.meta:verb:."], config_path)

        print("--- dz info :.meta:verb ---")
        print(card.stdout)
        print("--- dz :.meta:verb:. ---")
        print(listing.stdout)

        card_children = parse_children(card.stdout, "contains:")
        listing_children = parse_children(listing.stdout, "-- structure:")

        print(f"card children:    {card_children}")
        print(f"listing children: {listing_children}")

        missing = sorted(set(card_children) - set(listing_children))
        if missing:
            print(
                f"BUG CONFIRMED: listing is missing {len(missing)} "
                f"children the card shows: {missing}",
                file=sys.stderr,
            )
            return 1
        print("not reproduced (children sets agree) -- may be fixed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
