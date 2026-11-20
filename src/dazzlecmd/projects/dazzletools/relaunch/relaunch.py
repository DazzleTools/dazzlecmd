"""dz relaunch -- remember working sets of terminal tabs and bring them back after a restart.

CLI only: grammar -> handler. The work lives in relaunch_store (sets),
relaunch_claims (claims, sessions), relaunch_launch (hand-over, running) and
relaunch_csb (csb, read-only). Design of record: the final DWP in this tool's
private vault (2026-11-19__16-28-56__dev-workflow-process__relaunch-final-design.md).
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import relaunch_cli_io as io  # noqa: E402
import relaunch_grammar as grammar  # noqa: E402
import relaunch_store as rs  # noqa: E402
import relaunch_verbs as rv  # noqa: E402

#: action name -> handler(parsed, json_mode) -> exit code. Filled per slice.
HANDLERS: Dict[str, Callable] = {}


def handler(name: str):
    def deco(fn):
        HANDLERS[name] = fn
        return fn
    return deco


def help_text() -> str:
    lines = [
        "usage: dz relaunch [<set>...] [<action>] [options]",
        "",
        "Remember working sets of terminal tabs -- folders, commands, shell scripts and",
        "Claude sessions -- and bring them back after a restart, one short command per tab.",
        "Restores folders and programs; not scrollback, window layout or splits.",
        "",
        "actions:",
    ]
    for v in rv.VERBS:
        alias = f" ({', '.join(v.aliases)})" if v.aliases else ""
        lines.append(f"  {v.name + alias:<16} {v.summary}")
    lines += ["", "first run:"]
    first = [("dz relaunch new ck3", "create a set"),
             ("dz relaunch ck3 add --here", "add this tab's folder (run it in each tab)"),
             ("dz relaunch shell-init cmd", "print the dzr wrapper so claim can change folders")]
    after = [("dz relaunch", "what was open, per set"),
             ("dz relaunch ck3 claim", "in each new tab: the next member, last session's first"),
             ("dz relaunch ck3 claim -o", "and run it here (asks first; -y skips)")]
    for cmd, why in first:
        lines.append(f"  {cmd:<44} # {why}")
    lines += ["", "after a restart:"]
    for cmd, why in after:
        lines.append(f"  {cmd:<44} # {why}")
    lines += ["", "the words:",
              "  set      a named working set, one file under ~/.dz/relaunch/sets/",
              "  member   one entry: a folder, a command, a shell script, or a Claude session",
              "  claim    this tab's hold on one member; freed when the tab closes or the machine restarts",
              "  session  a run of claims; a restart (or closing every tab) starts the next one",
              "",
              "names: <set>, <set>:<id>, last, last~N, last:<n>. Exit codes: 0 ok, 1 error,",
              "2 usage, 3 refused (nothing changed), 4 partial. The last line is the verdict."]
    return "\n".join(lines)


@handler("shell-init")
def _shell_init(parsed, json_mode: bool) -> int:
    import shutil
    import relaunch_wrappers as wr
    shell = (parsed.rest[0] if parsed.rest else ("cmd" if sys.platform == "win32" else "bash")).lower()
    try:
        text = wr.wrapper_text(shell)
    except ValueError as e:
        print(f"relaunch: {e}", file=sys.stderr)
        return io.finish("USAGE", str(e), io.EXIT_USAGE, json_mode=json_mode)
    dz = shutil.which("dz")
    where = os.path.dirname(dz) if dz else None
    if json_mode:
        return io.finish("PRINTED", f"dzr for {shell}", io.EXIT_OK, json_mode=True,
                         payload={"shell": shell, "text": text, "suggested_folder": where})
    sys.stdout.write(text.replace("\r\n", "\n"))
    if shell == "cmd":
        hint = (f"save it as dzr.cmd in a folder on PATH that is local (not a network drive), "
                f"e.g. {where}" if where else "save it as dzr.cmd in a local folder on PATH")
    else:
        hint = "add it to ~/.bashrc, then: dzr <set> claim"
    print(f"\n# {hint}", file=sys.stderr)
    return io.finish("PRINTED", f"dzr for {shell}", io.EXIT_OK)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        print(help_text())
        return io.EXIT_OK
    json_mode = "--json" in argv or "-j" in argv
    try:
        known = [d["name"] for d in rs.list_sets(include_disabled=True) if "name" in d]
        parsed = grammar.split_targets(argv, known)
    except grammar.GrammarError as e:
        print(f"relaunch: {e}", file=sys.stderr)
        return io.finish("USAGE", str(e), io.EXIT_USAGE, json_mode=json_mode)
    except rs.StoreError as e:
        print(f"relaunch: {e}", file=sys.stderr)
        return io.finish("ERROR", str(e), io.EXIT_ERROR, json_mode=json_mode)
    fn = HANDLERS.get(parsed.verb)
    if fn is None:
        msg = f"'{parsed.verb}' is not built yet in this version"
        print(f"relaunch: {msg}", file=sys.stderr)
        return io.finish("USAGE", msg, io.EXIT_USAGE, json_mode=json_mode)
    try:
        return fn(parsed, json_mode)
    except (rs.StoreError, grammar.GrammarError) as e:
        print(f"relaunch: {e}", file=sys.stderr)
        return io.finish("ERROR", str(e), io.EXIT_ERROR, json_mode=json_mode)
    finally:
        io.close_output()


if __name__ == "__main__":
    sys.exit(main())
