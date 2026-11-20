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
                   ("dz relaunch ck3 add --claude CK3__2026-10-24__worker", "a Claude session, through csb"))),
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
