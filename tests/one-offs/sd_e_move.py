"""SD-E verbatim function-mover (DWP 2026-06-26__22-56-24).

Cuts named top-level `def`/assignment blocks from a source module and appends
them BYTE-EXACT (via `ast` line spans) to a destination module. Used to fold the
`render_*` cluster from `default_meta_commands.py` into `rendering.py` without
any hand-transcription (copy-don't-rewrite). The byte-gate is the parity oracle;
this script only relocates source, it never edits logic.

Usage:  python sd_e_move.py <src.py> <dst.py> name1 name2 ...
"""
import ast
import re
import sys


def move(src_path, dst_path, names):
    src = open(src_path, encoding="utf-8").read()
    lines = src.split("\n")
    tree = ast.parse(src)

    spans = []  # (start_idx, end_idx_inclusive, name)  0-based
    for node in tree.body:
        nm = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nm = node.name
        elif isinstance(node, ast.Assign):
            tgts = [t.id for t in node.targets if isinstance(t, ast.Name)]
            nm = next((t for t in tgts if t in names), None)
        if nm in names:
            spans.append((node.lineno - 1, node.end_lineno - 1, nm))
    spans.sort()

    found = {nm for _, _, nm in spans}
    missing = [n for n in names if n not in found]
    if missing:
        print(f"NOT FOUND: {missing}", file=sys.stderr)
        sys.exit(2)

    blocks = ["\n".join(lines[s:e + 1]) for s, e, _ in spans]

    keep = list(lines)
    for s, e, _ in sorted(spans, reverse=True):
        del keep[s:e + 1]
    new_src = re.sub(r"\n{4,}", "\n\n\n", "\n".join(keep))

    dst = open(dst_path, encoding="utf-8").read().rstrip("\n")
    new_dst = dst + "\n\n\n" + "\n\n\n".join(blocks) + "\n"

    open(src_path, "w", encoding="utf-8", newline="\n").write(new_src)
    open(dst_path, "w", encoding="utf-8", newline="\n").write(new_dst)
    for s, e, nm in spans:
        print(f"moved {nm}: {e - s + 1} lines")


if __name__ == "__main__":
    move(sys.argv[1], sys.argv[2], set(sys.argv[3:]))
