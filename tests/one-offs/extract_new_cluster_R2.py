"""R2 of the cli.py decomposition (DWP 2026-06-25__16-14-19): extract the
NEW/SCAFFOLD cluster (+ the shared _register_in_kit helper) out of cli.py into
commands/new.py.

_register_in_kit is shared by _cmd_add (stays in cli.py until R3) and
_cmd_new_tool (moving now). It moves into new.py; cli.py re-exports it so the
still-resident _cmd_add keeps resolving it, and R3's commands/add.py will import
it from commands/new.py (one-directional add->new, acyclic).

Pure-move, verifying. Run from repo root:
  python tests/one-offs/extract_new_cluster_R2.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI = os.path.join(ROOT, "src", "dazzlecmd", "cli.py")
NEWMOD = os.path.join(ROOT, "src", "dazzlecmd", "commands", "new.py")

M_REG = "def _register_in_kit("            # shared helper start (in the add region)
M_MODE = "def _cmd_mode_status("           # first def AFTER _register_in_kit (stays)
M_NEW = "def _resolve_new_defaults("       # NEW cluster start
M_STALE = "# Phase 3 command handlers"     # stale comment marking NEW cluster end (dropped)
M_R1 = "# Kit-lifecycle handlers moved"    # R1 re-export comment (kept; block starts 1 line above)

HEADER = '''\
"""``dz new`` scaffolding command handlers + the --with component framework.

Moved out of cli.py (decomposition R2, DWP 2026-06-25__16-14-19). Holds
``dz new tool|kit|aggregator``, the template-copy helpers, the ``--with``
composable-component framework (RepoKit common/template + docker/ci), and the
shared ``_register_in_kit`` registration helper (also used by ``dz add`` --
commands/add.py imports it from here in R3). cli.py re-exports these names.
Imports nothing from cli.py -- one-directional.
"""
import json
import os
import re
import sys
'''

REEXPORT = '''\
# ---------------------------------------------------------------------------
# NEW/SCAFFOLD handlers moved to commands/new.py (cli.py decomposition R2,
# DWP 2026-06-25__16-14-19). Re-exported for dispatch_meta + back-compat
# (_cmd_add, tests, and one-offs import several of these from dazzlecmd.cli).
# ---------------------------------------------------------------------------
from dazzlecmd.commands.new import (  # noqa: F401,E402
    _resolve_new_defaults,
    _find_templates_root,
    _available_languages,
    _substitute_placeholders,
    _copy_template_tree,
    _cmd_new_tool,
    _cmd_new_kit,
    _scaffold_starter_tool,
    _with_copy_component,
    _ComponentUnavailable,
    _REPOKIT_COMMON_URL_DEFAULT,
    _REPOKIT_TEMPLATE_URL_DEFAULT,
    _GIT_SUBTREE_TIMEOUT,
    _run_git,
    _with_common,
    _with_template,
    _WITH_COMPONENTS,
    _WITH_ALL,
    _parse_with_spec,
    _apply_with_components,
    _cmd_new_aggregator,
    _layer_extras,
    _register_in_kit,
)
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


def main():
    with io.open(CLI, encoding="utf-8", newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)

    iA0 = _only(lines, M_REG)
    iA1 = _only(lines, M_MODE)
    iB0 = _only(lines, M_NEW)
    iStale = _only(lines, M_STALE)
    iR1c = _only(lines, M_R1)
    iR1block = iR1c - 1  # the "# ----" separator line just above the R1 comment
    assert iA0 < iA1 < iB0 < iStale < iR1block, "markers out of order"
    assert lines[iR1block].startswith("# ---"), f"unexpected R1 boundary: {lines[iR1block]!r}"

    reg_body = _rstrip_blanks(lines[iA0:iA1])          # _register_in_kit
    new_body = _rstrip_blanks(lines[iB0:iStale])        # the NEW cluster funcs

    print(f"_register_in_kit: {len(reg_body)} lines")
    print(f"NEW cluster:      {len(new_body)} lines")

    # commands/new.py = header + NEW cluster + _register_in_kit (appended).
    body = nl.join(new_body) + nl + nl + nl + nl.join(reg_body)
    content = HEADER.replace("\n", nl) + nl + body.rstrip() + nl
    with io.open(NEWMOD, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    print(f"  wrote {os.path.relpath(NEWMOD, ROOT)} "
          f"({len(content.splitlines())} lines)")

    # Rebuild cli.py:
    #   [:iA0]            everything up to _register_in_kit (incl. _cmd_add)
    #   [iA1:iB0]         _cmd_mode_* handlers (the gap left by removing _register_in_kit)
    #   <new re-export>
    #   [iR1block:]       the R1 kit re-export block onward (drops NEW cluster + stale comment)
    reexport = REEXPORT.replace("\n", nl).split(nl)
    new_lines = (lines[:iA0]
                 + lines[iA1:iB0]
                 + reexport + ["", ""]
                 + lines[iR1block:])
    with io.open(CLI, "w", encoding="utf-8", newline="") as fh:
        fh.write(nl.join(new_lines))
    print(f"  rewrote cli.py: {len(lines)} -> {len(new_lines)} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
