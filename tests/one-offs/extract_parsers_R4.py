"""R4 of the cli.py decomposition (DWP 2026-06-25__16-14-19): extract the PARSERS
cluster (build_parser + _build_categorized_help + _register_meta_commands) out of
cli.py into a top-level dazzlecmd/parsers.py.

find_project_root (tiny legacy wrapper) and the default_meta_commands re-export
import stay in cli.py. The parser builder lives between those two pieces, so this
is a two-range extraction. cli.py re-exports build_parser (main() + tests need
it) plus the two helpers (defensive).

Pure-move, verifying. Run from repo root:
  python tests/one-offs/extract_parsers_R4.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI = os.path.join(ROOT, "src", "dazzlecmd", "cli.py")
PARSERS = os.path.join(ROOT, "src", "dazzlecmd", "parsers.py")

M_BP = "def build_parser("
M_IMPC = "# Display helpers: canonical"     # the re-export comment (stays in cli.py)
M_CAT = "def _build_categorized_help("
M_DISP = "def dispatch_meta("

HEADER = '''\
"""argparse construction for the dazzlecmd CLI.

Moved out of cli.py (decomposition R4, DWP 2026-06-25__16-14-19). Holds
build_parser (the top-level parser + dynamic tool subparsers), the categorized
--help epilog builder, and _register_meta_commands (every built-in subparser and
its `_meta` dispatch tag). cli.py re-exports build_parser (the engine wiring +
tests import it from dazzlecmd.cli). Imports nothing from cli.py.
"""
import argparse
import sys

from dazzlecmd._version import DISPLAY_VERSION, __version__
from dazzlecmd._constants import RESERVED_COMMANDS
from dazzlecmd.kit_verbs import (
    add_flat_verb,
    build_lifecycle_axis_groups,
    render_kit_help,
)
from dazzlecmd_lib.default_meta_commands import MIN_DESC_WIDTH, TERM_SIZE_FALLBACK
'''

REEXPORT = '''\
# ---------------------------------------------------------------------------
# The parser builder moved to dazzlecmd/parsers.py (cli.py decomposition R4,
# DWP 2026-06-25__16-14-19). Re-exported so AggregatorEngine.run()'s wiring in
# main() and the test-suite keep importing build_parser from dazzlecmd.cli.
# ---------------------------------------------------------------------------
from dazzlecmd.parsers import (  # noqa: F401,E402
    build_parser,
    _build_categorized_help,
    _register_meta_commands,
)'''


def _only(lines, marker):
    hits = [i for i, ln in enumerate(lines) if ln.startswith(marker)]
    assert len(hits) == 1, f"marker {marker!r} found {len(hits)}x (want 1)"
    return hits[0]


def _rstrip_blanks(chunk):
    chunk = list(chunk)
    while chunk and chunk[-1].strip() == "":
        chunk.pop()
    return chunk


def main():
    with io.open(CLI, encoding="utf-8", newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)

    iBP = _only(lines, M_BP)
    iImp = _only(lines, M_IMPC)
    iCat = _only(lines, M_CAT)
    iDisp = _only(lines, M_DISP)
    assert iBP < iImp < iCat < iDisp, "markers out of order"

    bp_body = _rstrip_blanks(lines[iBP:iImp])           # build_parser
    reg_body = _rstrip_blanks(lines[iCat:iDisp])         # _build_categorized_help + _register_meta_commands
    print(f"build_parser: {len(bp_body)}  cathelp+register: {len(reg_body)} lines")

    body = nl.join(bp_body) + nl + nl + nl + nl.join(reg_body)
    content = HEADER.replace("\n", nl) + nl + body.rstrip() + nl
    with io.open(PARSERS, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    print(f"  wrote {os.path.relpath(PARSERS, ROOT)} ({len(content.splitlines())} lines)")

    # Rebuild cli.py:
    #   [:iBP]          imports + find_project_root (build_parser removed)
    #   <re-export>
    #   [iImp:iCat]     the default_meta_commands re-export import block (stays)
    #   [iDisp:]        dispatch_meta onward (cathelp + register removed)
    reexport = REEXPORT.replace("\n", nl).split(nl)
    new_lines = (lines[:iBP]
                 + reexport + ["", ""]
                 + lines[iImp:iCat]
                 + lines[iDisp:])
    with io.open(CLI, "w", encoding="utf-8", newline="") as fh:
        fh.write(nl.join(new_lines))
    print(f"  rewrote cli.py: {len(lines)} -> {len(new_lines)} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
