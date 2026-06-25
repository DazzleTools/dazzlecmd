"""R3 of the cli.py decomposition (DWP 2026-06-25__16-14-19): extract the ADD,
MODE, and SETUP clusters out of cli.py into commands/{add,mode,setup}.py.

_cmd_version (6 lines) stays resident in cli.py (the DWP fold-if-tiny rule).
commands/add.py imports _register_in_kit from commands/new.py (one-directional
add->new, set up in R2). cli.py re-exports the moved handlers.

Pure-move, verifying. Run from repo root:
  python tests/one-offs/extract_setup_mode_add_R3.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI = os.path.join(ROOT, "src", "dazzlecmd", "cli.py")
CMD = os.path.join(ROOT, "src", "dazzlecmd", "commands")

M_ADD = "def _cmd_add("
M_MODE = "def _cmd_mode_status("
M_R2 = "# NEW/SCAFFOLD handlers moved"   # R2 re-export comment; "# ---" sits 1 line above
M_SETUP = "def _cmd_setup("
M_DISPATCH = "def dispatch_tool("

ADD_HEADER = '''\
"""``dz add`` -- import an existing repo as a dazzlecmd tool.

Moved out of cli.py (decomposition R3, DWP 2026-06-25__16-14-19). Imports the
shared _register_in_kit helper from commands/new.py (one-directional add->new).
cli.py re-exports _cmd_add. Imports nothing from cli.py.
"""
import os
import sys

from dazzlecmd._constants import RESERVED_COMMANDS
from dazzlecmd.commands.new import _register_in_kit
'''

MODE_HEADER = '''\
"""``dz mode`` -- dev/publish mode handlers (thin wrappers over dazzlecmd.mode).

Moved out of cli.py (decomposition R3, DWP 2026-06-25__16-14-19). Each handler
lazily imports its implementation from dazzlecmd.mode; this module needs no
top-level imports. cli.py re-exports these handlers.
"""
'''

SETUP_HEADER = '''\
"""``dz setup`` -- run a tool's declared setup script.

Moved out of cli.py (decomposition R3, DWP 2026-06-25__16-14-19). The engine
dispatches the tool's own setup.command/setup.script; it never installs deps
itself. cli.py re-exports _cmd_setup. Imports nothing from cli.py.
"""
import os
import sys

from dazzlecmd_lib import colors as _colors
'''

REEXPORT = '''\
# ---------------------------------------------------------------------------
# ADD / MODE / SETUP handlers moved to commands/{add,mode,setup}.py
# (cli.py decomposition R3, DWP 2026-06-25__16-14-19). Re-exported for
# dispatch_meta + back-compat (tests import _cmd_setup et al. from dazzlecmd.cli).
# ---------------------------------------------------------------------------
from dazzlecmd.commands.add import _cmd_add  # noqa: F401,E402
from dazzlecmd.commands.mode import (  # noqa: F401,E402
    _cmd_mode_status,
    _cmd_mode_switch,
    _cmd_mode_restore,
)
from dazzlecmd.commands.setup import _cmd_setup  # noqa: F401,E402
'''


def _only(lines, marker):
    hits = [i for i, ln in enumerate(lines) if ln.startswith(marker)]
    assert len(hits) == 1, f"marker {marker!r} found {len(hits)}x (want 1)"
    return hits[0]


def _rstrip_blanks(chunk):
    chunk = list(chunk)
    while chunk and chunk[-1].strip() == "":
        chunk.pop()
    return chunk


def _write(path, header, body_lines, nl):
    body = nl.join(body_lines).rstrip()
    content = header.replace("\n", nl) + nl + body + nl
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    print(f"  wrote {os.path.relpath(path, ROOT)} ({len(content.splitlines())} lines)")


def main():
    with io.open(CLI, encoding="utf-8", newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)

    iAdd = _only(lines, M_ADD)
    iMode = _only(lines, M_MODE)
    iR2c = _only(lines, M_R2)
    iA1 = iR2c - 1                       # the "# ---" separator above the R2 block
    iSetup = _only(lines, M_SETUP)
    iDisp = _only(lines, M_DISPATCH)
    assert iAdd < iMode < iA1 < iSetup < iDisp, "markers out of order"
    assert lines[iA1].startswith("# ---"), f"unexpected Range-A end: {lines[iA1]!r}"

    add_body = _rstrip_blanks(lines[iAdd:iMode])
    mode_body = _rstrip_blanks(lines[iMode:iA1])
    setup_body = _rstrip_blanks(lines[iSetup:iDisp])
    print(f"add: {len(add_body)}  mode: {len(mode_body)}  setup: {len(setup_body)} lines")

    _write(os.path.join(CMD, "add.py"), ADD_HEADER, add_body, nl)
    _write(os.path.join(CMD, "mode.py"), MODE_HEADER, mode_body, nl)
    _write(os.path.join(CMD, "setup.py"), SETUP_HEADER, setup_body, nl)

    # Rebuild cli.py:
    #   [:iAdd]          everything up to _cmd_add (incl. _cmd_version, stays)
    #   <re-export>
    #   [iA1:iSetup]     R2+R1 re-export blocks + _cmd_tree (up to _cmd_setup)
    #   [iDisp:]         dispatch_tool + main (drops _cmd_setup)
    reexport = REEXPORT.replace("\n", nl).split(nl)
    new_lines = (lines[:iAdd]
                 + reexport + ["", ""]
                 + lines[iA1:iSetup]
                 + lines[iDisp:])
    with io.open(CLI, "w", encoding="utf-8", newline="") as fh:
        fh.write(nl.join(new_lines))
    print(f"  rewrote cli.py: {len(lines)} -> {len(new_lines)} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
