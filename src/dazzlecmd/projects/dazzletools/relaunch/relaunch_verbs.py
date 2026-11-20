"""The declarative verb table for ``dz relaunch`` -- parser, help and grammar all read it.

Lift-ready (oracle suggestion S1): imports nothing from relaunch, so it can move
into a shared CLI library later. ``relaunch_store.RESERVED_NAMES`` must contain
every name and alias here; a test pins that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class Verb:
    name: str
    summary: str
    aliases: Tuple[str, ...] = ()
    writes: bool = False           # takes the store lock
    sets: str = "one"              # "none" | "one" | "many" | "optional"
    examples: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)


VERBS: Tuple[Verb, ...] = (
    Verb("list", "every set: members, what is claimed, what this tab holds", ("ls",), sets="none",
         examples=(("dz relaunch", "the same dashboard, bare"),
                   ("dz relaunch list --removed all", "include removed sets and members"))),
    Verb("show", "one set's roster, or one member's card", sets="many",
         examples=(("dz relaunch ck3", "show is implicit after a set name"),
                   ("dz relaunch ck3:2", "one member's card"),
                   ("dz relaunch last", "what was open last session, per set"))),
    Verb("new", "create a set", writes=True,
         examples=(("dz relaunch new ck3", "an empty set"),
                   ("dz relaunch new today --from-csb current", "one Claude member per open session"))),
    Verb("add", "add a member: a folder, a command, a shell script, or a Claude session", writes=True,
         examples=(("dz relaunch ck3 add --here", "this tab's folder (and claim it)"),
                   ("dz relaunch ck3 add C:\\code\\ck3 -- codex resume --last", "a command, run in that folder"),
                   ("dz relaunch ck3 add --claude CK3__2026-10-24__worker", "a Claude session, through csb"),
                   ("dz relaunch ck3 add C:\\code\\ck3\\mod --shell cmd \"build.cmd && run-tests.cmd\"",
                    "a compound action, written in cmd syntax"),
                   ("dz relaunch ck3 add --here --label mod --notes \"mod build tab\"",
                    "a label to claim it by, and a note for the roster"),
                   ("dz relaunch ck3 add C:\\code\\ck3\\docs --at 1",
                    "first in the claim order (default: last)"))),
    Verb("edit", "change a member's fields, or open the set file in an editor", writes=True,
         examples=(("dz relaunch ck3 edit 2 --label docs", "one field"),
                   ("dz relaunch ck3 edit", "the whole set in your editor, checked on save"))),
    Verb("note", "set a note on a set or a member", writes=True,
         examples=(("dz relaunch ck3 note 2 \"mod build tab\"", ""),)),
    Verb("claim", "take the next member for this tab (or a named one); -o runs it here", writes=True,
         sets="many",
         examples=(("dz relaunch ck3 claim", "next member, last session's first; shows what to do"),
                   ("dz relaunch ck3 claim -o", "and run it in this tab (asks first; -y skips)"),
                   ("dz relaunch ck3 claim --next", "this tab is done with its member: take another"),
                   ("dz relaunch ck3 claim 2 --yes", "a second copy of a member open elsewhere"))),
    Verb("launch", "start the set's detached members (programs that need no tab, e.g. an editor)",
         writes=True,
         examples=(("dz relaunch ck3 add --detach --label vscode -- code C:\\code\\ck3-save-migrator",
                    "a member that needs no tab"),
                   ("dz relaunch ck3 launch", "after a restart: start each one not yet started since this boot"),
                   ("dz relaunch ck3 launch vscode", "start that one again"))),
    Verb("release", "let go of this tab's member, a named one, or all in a set", writes=True,
         sets="optional",
         examples=(("dz relaunch release", "this tab's claim"),
                   ("dz relaunch ck3 release --all", "every claim in the set"))),
    Verb("drop", "remove (to the safedel trash) or disable a set or members", writes=True,
         examples=(("dz relaunch ck3 drop disable 3", "hide member 3 from claims"),
                   ("dz relaunch ck3 drop rm", "the whole set, recoverable with dz safedel recover"))),
    Verb("enable", "undo drop disable", writes=True,
         examples=(("dz relaunch ck3 enable 3", ""),)),
    Verb("shell-init", "print the dzr wrapper that lets claim change this tab's folder", sets="none",
         examples=(("dz relaunch shell-init cmd", "for Command Prompt"),
                   ("dz relaunch shell-init bash", "for bash (put it in ~/.bashrc)"))),
)

#: Per-verb usage line and options (flag, what it does), for `dz relaunch <verb> -h`.
USAGE: Dict[str, Tuple[str, Tuple[Tuple[str, str], ...]]] = {
    "list": ("dz relaunch [list] [--removed [only|all]] [--disabled] [--json]", (
        ("--removed [only|all]", "removed sets (in the safedel trash) and removed members; 'all' adds the live sets"),
        ("--disabled", "include disabled sets"),
        ("--json", "one JSON object instead of text"))),
    "show": ("dz relaunch <set>|<set>:<id>|last[~N][:<n>] ... [--json]", (
        ("<set>", "the roster: each member, who holds it, its last-session tag, and what claim takes next"),
        ("<set>:<id>", "one member's card (kind, what it opens, state, notes)"),
        ("last, last~N", "what was opened in the last session (or N sessions before), across sets"),
        ("last:<n>", "the n-th member of that view"),
        ("--json", "one JSON object instead of text"))),
    "new": ("dz relaunch new <set> [--here] [--notes TEXT] [--from-csb VIEW|SET]", (
        ("<set>", "letters, digits, '-' and '_'; matched without case; action words and numbers are refused"),
        ("--here", "start with this tab's folder as the first member"),
        ("--notes TEXT", "a note on the set"),
        ("--from-csb VIEW|SET", "one Claude member per session in a csb view (current, last, boot) or named csb set"))),
    "add": ("dz relaunch <set> add [<folder> | --here] [--label L] [--notes T] [--at N]\n"
            "                          [--shell DIALECT SCRIPT | --claude SESSION | -- COMMAND ARGS...]", (
        ("<folder>", "a folder member (stored exactly as given, no ~ or %VAR% expansion)"),
        ("--here", "this tab's current folder -- and this tab claims the new member"),
        ("-- COMMAND ARGS...", "a command member: any program and its arguments, run in the folder if one is given"),
        ("--shell DIALECT SCRIPT", "a shell member: SCRIPT in cmd, bash or pwsh syntax (for && chains, pipes, scripts)"),
        ("--claude SESSION", "a Claude session, by exact csb session name or UUID (resumed with csb)"),
        ("--label L", "a short name to claim it by (dz relaunch <set> claim L)"),
        ("--notes T", "a note shown in the roster and the member card"),
        ("--at N", "insert at position N in the claim order (default: last)"))),
    "edit": ("dz relaunch <set> edit [<member>] [--label L] [--notes T] [--folder F] [-- COMMAND ARGS...]", (
        ("<member> + flags", "change those fields of one member (id or label)"),
        ("-- COMMAND ARGS...", "replace a command member's program and arguments"),
        ("(no flags)", "open the whole set file in $EDITOR / notepad; press Enter to apply; refused (your copy kept) if the set changed meanwhile"))),
    "note": ("dz relaunch <set> note [<member>] \"TEXT\"", (
        ("\"TEXT\"", "the set's note"),
        ("<member> \"TEXT\"", "that member's note"))),
    "claim": ("dz relaunch <set>... claim [<member>] [-o [-y]] [--next] [--yes] [--print]", (
        ("(no member)", "the next free member, last session's first; this tab keeps it until the tab closes or the machine restarts"),
        ("<member>", "that member (id or label)"),
        ("-o, --open", "run the member in this tab: shows what will run and asks [y/N]"),
        ("-y, --yes", "skip the question; also allows a second copy of a member open in another tab"),
        ("--next", "this tab is done with its member: take the next one"),
        ("--print", "only show what to do, even with -o"),
        ("<set> <set> ...", "several sets: the first with a free member is used"),
        ("(prompt off)", "DZ_RELAUNCH_OPEN_ASKS=0, or DZ_RELAUNCH_OPEN_ASKS=0 in ~/.dz/relaunch/.env, or \"open_asks\": false in ~/.dz/relaunch/local/config.json"))),
    "launch": ("dz relaunch <set> launch [<member>...] [-y]", (
        ("(no member)", "start every detached member not yet started since this boot -- no tab, no window, no claim"),
        ("<member>...", "start those detached members, even if already started"),
        ("-y, --yes", "skip the question (an edited or copied command still asks)"),
        ("(make one)", "dz relaunch <set> add --detach -- <program> <args>, or edit <member> --detach"))),
    "release": ("dz relaunch [<set>] release [<member> | --all]", (
        ("(nothing)", "let go of this tab's member"),
        ("<member>", "let go of that member, whichever tab holds it"),
        ("--all", "let go of every claim in the set"))),
    "drop": ("dz relaunch <set> drop rm|disable [<member>...] [--yes]", (
        ("rm", "remove: a whole set goes to the safedel trash (recoverable); members are kept for 30 days"),
        ("disable", "hide: a set moves to sets/disabled/, a member is skipped by claim"),
        ("--yes", "remove a whole set without asking (required when nobody is at the console)"))),
    "enable": ("dz relaunch <set> enable [<member>...]", (
        ("(nothing)", "bring back a disabled set"),
        ("<member>...", "bring back disabled members"))),
    "shell-init": ("dz relaunch shell-init cmd|bash", (
        ("cmd", "print dzr.cmd -- save it in a local folder on PATH (the one holding dz.exe)"),
        ("bash", "print the dzr() function -- add it to ~/.bashrc"),
        ("(why)", "a program cannot change its shell's folder; dzr runs dz relaunch and does the cd itself"))),
}


def verb_help(name: str) -> str:
    """The `-h` text for one action: usage, what it does, options, examples."""
    v = lookup(name)
    usage, opts = USAGE.get(v.name, (f"dz relaunch {v.name}", ()))
    alias = f" (alias: {', '.join(v.aliases)})" if v.aliases else ""
    lines = [f"usage: {usage}", "", f"{v.name}{alias} -- {v.summary}", ""]
    if opts:
        lines.append("options:")
        w = max(len(f) for f, _ in opts)
        for flag, text in opts:
            lines.append(f"  {flag:<{w}}  {text}")
        lines.append("")
    if v.examples:
        lines.append("examples:")
        w = max(len(c) for c, _ in v.examples)
        for cmd, why in v.examples:
            lines.append(f"  {cmd:<{w}}" + (f"   # {why}" if why else ""))
        lines.append("")
    lines.append("All actions: dz relaunch --help.  Exit codes: 0 ok, 1 error, 2 usage, 3 refused, 4 partial.")
    return "\n".join(lines)


BY_NAME: Dict[str, Verb] = {}
for _v in VERBS:
    BY_NAME[_v.name] = _v
    for _a in _v.aliases:
        BY_NAME[_a] = _v

VIEWS = ("last", "current")

#: Flags that take no value and may appear anywhere, even before the action.
GLOBAL_FLAGS = frozenset({
    "-v", "--verbose", "-q", "--quiet", "--json", "-j", "--no-color",
    "-o", "--open", "-y", "--yes", "-h", "--help",
})


def lookup(word: str):
    return BY_NAME.get(word.lower())
