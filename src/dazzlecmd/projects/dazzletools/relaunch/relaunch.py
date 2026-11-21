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
    lines += ["", "help on one action: dz relaunch <action> -h   (e.g. dz relaunch claim -h)", "", "first run:"]
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


import relaunch_views as views  # noqa: E402

import relaunch_actions as actions  # noqa: E402

HANDLERS["list"] = views.cmd_list
HANDLERS["show"] = views.cmd_show
HANDLERS["new"] = actions.cmd_new
HANDLERS["add"] = actions.cmd_add
HANDLERS["edit"] = actions.cmd_edit
HANDLERS["note"] = actions.cmd_note
HANDLERS["release"] = actions.cmd_release
HANDLERS["drop"] = actions.cmd_drop
HANDLERS["enable"] = actions.cmd_enable
HANDLERS["claim"] = actions.cmd_claim
HANDLERS["launch"] = actions.cmd_launch


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
    def verdict(outcome, detail, code=io.EXIT_OK):
        # stdout carries only the wrapper (so `> dzr.cmd` makes a clean file); the verdict goes to stderr
        print(io.verdict_line(io.TOOL, outcome, detail), file=sys.stderr)
        return code

    if "--install" in parsed.rest or "--uninstall" in parsed.rest:
        if shell not in ("cmd", "bash"):
            return verdict("USAGE", f"--install/--uninstall are built for cmd and bash, not {shell}",
                           io.EXIT_USAGE)
        try:
            if "--uninstall" in parsed.rest:
                import relaunch_actions as actions
                remove = wr.uninstall_cmd if shell == "cmd" else wr.uninstall_bash
                outcome, path = remove(trash=actions.trash_store())
            else:
                outcome, path = wr.install_cmd() if shell == "cmd" else wr.install_bash()
        except OSError as e:
            print(f"relaunch: {e}", file=sys.stderr)
            return verdict("REFUSED", str(e), io.EXIT_REFUSED)
        works = ("`dzr <set> claim` works in every new tab" if shell == "cmd" else
                 "source it to use it: . dzr <set> claim")
        messages = {"INSTALLED": f"wrote {path} -- {works}",
                    "CURRENT": f"{path} is already current",
                    "FOREIGN": f"{path} exists and is not relaunch's -- left alone",
                    "ABSENT": f"{path} is not there",
                    "REMOVED": f"moved {path} to the safedel trash"}
        print(messages[outcome], file=sys.stderr)
        if shell == "bash" and outcome in ("INSTALLED", "CURRENT"):
            print("for plain `dzr <set> claim`, add this line to your shell's rc file yourself:\n"
                  "  alias dzr='. dzr'", file=sys.stderr)
        shadow = shutil.which("dzr") if (shell == "cmd" or sys.platform != "win32") else None
        if outcome == "INSTALLED" and shadow and os.path.normcase(shadow) != os.path.normcase(path):
            print(f"warning: `dzr` resolves to {shadow} first on PATH", file=sys.stderr)
        return verdict(outcome, path, io.EXIT_REFUSED if outcome == "FOREIGN" else io.EXIT_OK)
    sys.stdout.write(text.replace("\r\n", "\n"))
    if shell == "cmd":
        hint = (f"save it with: dz relaunch shell-init cmd --install   (writes dzr.cmd beside {where})"
                if where else "save it as dzr.cmd in a local folder on PATH")
    else:
        hint = ("or install the sourced form (no rc edit): dz relaunch shell-init bash --install, "
                "then: . dzr <set> claim   -- or add this function to ~/.bashrc yourself")
    print(f"# {hint}", file=sys.stderr)
    return verdict("PRINTED", f"dzr for {shell}")


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
    if any(t in ("-h", "--help") for t in parsed.rest + parsed.flags) and argv:
        print(rv.verb_help(parsed.verb))      # help for that action; nothing runs
        return io.EXIT_OK
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
