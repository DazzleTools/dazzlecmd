"""Driver (2026-07-07, tester-unbounded merge-cert sweep, Task 1 step 3):
the 4 RULE-6 CONSISTENCY ROWS from
tests/checklists/v0.11.36-alpha__Feature__surface-matrix-sweep.md,
checked against a COLD `dz` per invocation, isolated DAZZLECMD_CONFIG.

Row 1: CARD<->LISTING children agree for every node with children.
Row 2: CARD<->LISTING current/default markers agree on value-aliased axes.
Row 3: CARD help line == the argparse help for every registry-backed verb.
(Row 4 -- the level-axis STATES sweep -- lives in run_states_sweep.py,
since it needs config MUTATION across 4 states and deserves its own
isolated config lifecycle.)
"""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
from surface_matrix_gen import emit  # noqa: E402


CHILD_LINE_RE = re.compile(
    r"^\s{4}(\S+(?:\s\S+)*?)\s{2,}(.+)$")


def run(args, env):
    proc = subprocess.run(["dz"] + args, env=env, capture_output=True,
                          text=True, timeout=30)
    return (proc.stdout or "") + (proc.stderr or "")


def parse_block(text, header_marker):
    """Pull the indented '    name   descriptor' lines that follow either
    'contains:' (card) or '-- structure:' (listing)."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if header_marker in ln:
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for ln in lines[start:]:
        if not ln.startswith("    "):
            break
        m = CHILD_LINE_RE.match(ln)
        if m:
            out.append(ln.strip())
        elif ln.strip():
            out.append(ln.strip())
    return out


def main():
    probes, _ = emit()
    env = dict(os.environ)
    env["DAZZLECMD_CONFIG"] = os.path.join(
        tempfile.mkdtemp(prefix="dz_consistency_"), "c.json")

    # Build node -> {info_cmd, list_cmd} pairing from probes.
    by_node = {}
    for p in probes:
        if p["class"] in ("vacant",):
            continue
        args = p["cmd"].split(" ")[1:]
        by_node.setdefault(p["node"], {})
        if args[0] == "info":
            by_node[p["node"]]["info_args"] = args
        else:
            by_node[p["node"]]["list_args"] = args

    row1_mismatches = []
    row1_checked = 0
    row2_mismatches = []
    row2_checked = 0

    for node, d in by_node.items():
        if "info_args" not in d or "list_args" not in d:
            continue  # no children -> no listing probe generated
        row1_checked += 1
        card = run(d["info_args"], env)
        listing = run(d["list_args"], env)
        card_children = parse_block(card, "contains:")
        list_children = parse_block(listing, "structure:")
        if card_children != list_children:
            row1_mismatches.append({
                "node": node, "card": card_children, "listing": list_children,
            })
        # Row 2: current/default marker agreement -- only relevant when
        # either block actually shows a "<- current" or "(default)" marker.
        card_markers = [ln for ln in card_children if "current" in ln or "default" in ln]
        list_markers = [ln for ln in list_children if "current" in ln or "default" in ln]
        if card_markers or list_markers:
            row2_checked += 1
            if card_markers != list_markers:
                row2_mismatches.append({
                    "node": node, "card": card_markers, "listing": list_markers,
                })

    print(f"ROW 1 (card<->listing children): checked={row1_checked} "
          f"mismatches={len(row1_mismatches)}")
    for m in row1_mismatches:
        print(f"  MISMATCH node={m['node']}")
        print(f"    card:    {m['card']}")
        print(f"    listing: {m['listing']}")

    print(f"ROW 2 (current/default markers): checked={row2_checked} "
          f"mismatches={len(row2_mismatches)}")
    for m in row2_mismatches:
        print(f"  MISMATCH node={m['node']}")
        print(f"    card:    {m['card']}")
        print(f"    listing: {m['listing']}")

    # Row 3: card help == argparse registry help, for every registry-backed
    # verb (dest names pulled straight from build_parser's subparsers).
    from dazzlecmd.parsers import build_parser
    p = build_parser([], engine=None)
    sub = p._subparsers._group_actions[0]
    registry_help = {a.dest: a.help for a in sub._choices_actions}

    row3_checked = 0
    row3_mismatches = []
    row3_no_card_help = []
    for node, d in by_node.items():
        if "info_args" not in d:
            continue
        leaf = node.rsplit(":", 1)[-1].lstrip(".")
        if leaf not in registry_help:
            continue
        card = run(d["info_args"], env)
        m = re.search(r"^\s*help:\s*(.+)$", card, re.MULTILINE)
        row3_checked += 1
        if not m:
            row3_no_card_help.append((node, leaf))
            continue
        card_help = m.group(1).strip()
        if card_help != registry_help[leaf]:
            row3_mismatches.append({
                "node": node, "leaf": leaf,
                "card_help": card_help, "registry_help": registry_help[leaf],
            })

    print(f"ROW 3 (card help == registry help, registry-backed nodes): "
          f"checked={row3_checked} mismatches={len(row3_mismatches)} "
          f"no_card_help={len(row3_no_card_help)}")
    for m in row3_mismatches:
        print(f"  MISMATCH node={m['node']} leaf={m['leaf']}")
        print(f"    card:     {m['card_help']!r}")
        print(f"    registry: {m['registry_help']!r}")
    for node, leaf in row3_no_card_help:
        print(f"  NOTE: registry-backed leaf {leaf!r} (node={node}) has NO "
              f"card help line at all")

    total_fail = (len(row1_mismatches) + len(row2_mismatches)
                 + len(row3_mismatches))
    print(f"\nROWS 1-3 TOTAL MISMATCHES: {total_fail}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
