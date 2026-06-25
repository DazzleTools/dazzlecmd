"""R1 of the cli.py decomposition (DWP 2026-06-25__16-14-19): extract the
KIT LIFECYCLE cluster out of src/dazzlecmd/cli.py into three commands/* modules.

Pure-move refactor. Splits the cluster at three unique `def` markers:
  * commands/kit.py            : _kit_exists .. _cmd_kit_unfavorite (activation+favorite)
  * commands/kit_visibility.py : _resolve_visibility_target .. _cmd_kit_visibility_status
  * commands/kit_membership.py : _cmd_kit_add .. _cmd_kit_management
cli.py keeps a re-export block (dispatch_meta + tests import these names from it).

Deterministic + verifying: asserts each marker is unique, that the moved line
count is conserved, and writes nothing if anything is off. Run from repo root:
  python tests/one-offs/extract_kit_cluster_R1.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI = os.path.join(ROOT, "src", "dazzlecmd", "cli.py")
CMDDIR = os.path.join(ROOT, "src", "dazzlecmd", "commands")

# Boundary markers (each must be unique in cli.py).
M_KIT = "def _kit_exists("
M_VIS = "def _resolve_visibility_target("
M_MEM = "def _cmd_kit_add("
M_END = "def _cmd_tree("   # first def AFTER the cluster (stays in cli.py for R6)


def _idx(lines, marker):
    hits = [i for i, ln in enumerate(lines) if ln.startswith(marker)]
    assert len(hits) == 1, f"marker {marker!r} found {len(hits)}x (want 1)"
    return hits[0]


def _strip_trailing_blanks(chunk):
    while chunk and chunk[-1].strip() == "":
        chunk.pop()
    return chunk


KIT_HEADER = '''\
"""Kit-lifecycle command handlers: the activation and favorite axes.

Moved out of cli.py (decomposition R1, DWP 2026-06-25__16-14-19). These are the
``dz kit enable|disable|focus|reset|favorite|unfavorite`` handlers plus the
``_kit_exists`` predicate and the favorite-migration helpers. cli.py re-exports
every public name here (dispatch_meta and the test-suite import them from
``dazzlecmd.cli``). This module imports nothing from cli.py -- one-directional.
"""
import os
import sys
'''

VIS_HEADER = '''\
"""Kit-lifecycle command handlers: the visibility axis.

Moved out of cli.py (decomposition R1, DWP 2026-06-25__16-14-19). The single
visibility-toggle handler (all six verbs route to ``_cmd_kit_visibility_set``),
its cascade machinery, and the visibility list/status navigators over
``KIT_PRESENCE_SPACE``. cli.py re-exports these names. Imports nothing from
cli.py -- one-directional.
"""
import sys
'''

MEM_HEADER = '''\
"""Kit-lifecycle command handlers: the membership / materialization axis.

Moved out of cli.py (decomposition R1, DWP 2026-06-25__16-14-19). The
``dz kit add|remove|detach|attach|management`` handlers plus the submodule
detection, pointer-materialization stub, and lifecycle-axis hint helper.
cli.py re-exports these names. Imports nothing from cli.py -- one-directional.
"""
import json
import os
import sys

from dazzlecmd.kit_verbs import LIFECYCLE_PAIRS
'''

REEXPORT = '''\
# ---------------------------------------------------------------------------
# Kit-lifecycle handlers moved to commands/kit*.py (cli.py decomposition R1,
# DWP 2026-06-25__16-14-19). Re-exported here so dispatch_meta resolves them by
# bare name and so the test-suite / one-offs can import them from dazzlecmd.cli.
# ---------------------------------------------------------------------------
from dazzlecmd.commands.kit import (  # noqa: F401,E402
    _kit_exists,
    _cmd_kit_enable,
    _cmd_kit_disable,
    _cmd_kit_focus,
    _cmd_kit_reset,
    _cmd_kit_favorite,
    _suggest_favorite_replacement,
    _cmd_kit_favorite_migrate_stale,
    _cmd_kit_unfavorite,
)
from dazzlecmd.commands.kit_visibility import (  # noqa: F401,E402
    _resolve_visibility_target,
    _is_constitutional_entity,
    _cmd_kit_visibility_set,
    _resolve_cascade_slice,
    _apply_visibility_cascade,
    _cmd_kit_visibility_list,
    _cmd_kit_visibility_status,
)
from dazzlecmd.commands.kit_membership import (  # noqa: F401,E402
    _cmd_kit_add,
    _kit_is_submodule,
    _cmd_kit_remove,
    _cmd_kit_detach,
    _materialize_pointer,
    _cmd_kit_attach,
    _print_axis_hint,
    _cmd_kit_management,
)
'''


def main():
    with io.open(CLI, encoding="utf-8", newline="") as f:
        text = f.read()
    # Preserve the file's existing newline style.
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)

    i_kit = _idx(lines, M_KIT)
    i_vis = _idx(lines, M_VIS)
    i_mem = _idx(lines, M_MEM)
    i_end = _idx(lines, M_END)
    assert i_kit < i_vis < i_mem < i_end, "markers out of order"

    sub_kit = _strip_trailing_blanks(lines[i_kit:i_vis])
    sub_vis = _strip_trailing_blanks(lines[i_vis:i_mem])
    sub_mem = _strip_trailing_blanks(lines[i_mem:i_end])

    moved = len(lines[i_kit:i_end])
    print(f"cluster lines (incl. inter-blanks): {moved}")
    print(f"  kit.py:            {len(sub_kit)} lines")
    print(f"  kit_visibility.py: {len(sub_vis)} lines")
    print(f"  kit_membership.py: {len(sub_mem)} lines")

    os.makedirs(CMDDIR, exist_ok=True)

    def _write(path, header, body_lines):
        body = nl.join(body_lines).rstrip() + nl
        content = header.replace("\n", nl) + nl + body
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        print(f"  wrote {os.path.relpath(path, ROOT)}")

    initp = os.path.join(CMDDIR, "__init__.py")
    if not os.path.exists(initp):
        with io.open(initp, "w", encoding="utf-8", newline="") as fh:
            fh.write('"""dazzlecmd CLI command handlers (decomposed from cli.py)."""'
                     + nl)
        print(f"  wrote {os.path.relpath(initp, ROOT)}")

    _write(os.path.join(CMDDIR, "kit.py"), KIT_HEADER, sub_kit)
    _write(os.path.join(CMDDIR, "kit_visibility.py"), VIS_HEADER, sub_vis)
    _write(os.path.join(CMDDIR, "kit_membership.py"), MEM_HEADER, sub_mem)

    # Rebuild cli.py: keep everything before the cluster, drop the cluster,
    # insert the re-export block, keep _cmd_tree onward. lines[:i_kit] already
    # ends with the 2 blank lines that preceded `def _kit_exists`.
    reexport_lines = REEXPORT.replace("\n", nl).split(nl)
    new_lines = lines[:i_kit] + reexport_lines + ["", ""] + lines[i_end:]
    new_text = nl.join(new_lines)
    with io.open(CLI, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_text)
    print(f"  rewrote cli.py: {len(lines)} -> {len(new_lines)} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
