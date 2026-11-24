"""Name-first grammar for ``dz relaunch`` (final DWP 4.1; measured in poc8).

    dz relaunch                                   -> list (dashboard)
    dz relaunch <name>...                         -> show those
    dz relaunch <name>... <action> [rest]         -> action on those names
    dz relaunch <action> [<one set>] [rest]       -> verb-first, also accepted

A *name* is a set (``ck3``), a member (``ck3:2``), or a view (``last``,
``last~1``, ``last:3``, ``last~1:3``, ``current``). The action word separates
names from the action's own arguments, which is why a misspelt set or a label
that is also a set name can never be misread.

Pure: ``split_targets`` takes the known set names and does no I/O.
Lift-ready (oracle S2): imports only relaunch_verbs.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

import relaunch_verbs as rv

_TOKEN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9_-]*(?:~\d+)?):(?P<n>\d+)$")
_VIEW = re.compile(r"^(last|current)(~\d+)?$", re.I)


class GrammarError(Exception):
    """A usage error; the message says how to fix it (exit code 2)."""


@dataclass
class Target:
    name: str                 # set name (lowercase) or view ("last", "last~1", "current")
    entry: Optional[str] = None
    view: bool = False


@dataclass
class Parsed:
    verb: str
    targets: List[Target] = field(default_factory=list)
    rest: List[str] = field(default_factory=list)     # the action's own arguments
    flags: List[str] = field(default_factory=list)    # global flags seen before the action


def _is_flag(tok: str) -> bool:
    return tok.startswith("-") and tok != "-" and not tok.lstrip("-").isdigit()


def _suggest(word: str, known_sets: Iterable[str]) -> str:
    w = word.lower()
    sets = difflib.get_close_matches(w, list(known_sets), n=1, cutoff=0.7)
    acts = difflib.get_close_matches(w, list(rv.BY_NAME), n=1, cutoff=0.7)
    if sets and (not acts or difflib.SequenceMatcher(None, w, sets[0]).ratio()
                 >= difflib.SequenceMatcher(None, w, acts[0]).ratio()):
        return f" -- did you mean '{sets[0]}'?"
    if acts:
        return f" -- did you mean the action '{acts[0]}'?"
    return ""


def _name_target(tok: str, known_sets: Iterable[str]) -> Target:
    known = set(known_sets)
    m = _TOKEN.match(tok)
    base, entry = (m.group("name"), m.group("n")) if m else (tok, None)
    if _VIEW.match(base):
        return Target(base.lower(), entry, view=True)
    if rv.lookup(base):
        raise GrammarError(f"'{base}' is an action, not a set")
    if base.lower() not in known:
        raise GrammarError(f"no set named '{base}'{_suggest(base, known)}")
    return Target(base.lower(), entry)


def split_targets(argv: List[str], known_sets: Iterable[str]) -> Parsed:
    known = list(known_sets)
    flags: List[str] = []
    i = 0
    while i < len(argv) and _is_flag(argv[i]):
        tok = argv[i]
        if tok == "--":
            break
        if tok.split("=", 1)[0] not in rv.GLOBAL_FLAGS and not re.match(r"^-[vqoyj]+$", tok):
            raise GrammarError(f"put '{tok}' after the action, not before it")
        flags.append(tok)
        i += 1
    words = argv[i:]
    if not words:
        return Parsed("list", [], [], flags)

    verb = rv.lookup(words[0])
    if verb:  # verb-first
        rest = words[1:]
        targets: List[Target] = []
        lower_known = {k.lower() for k in known}
        if verb.name == "swap" and rest and rest[0].lower() not in lower_known:
            # `swap 2 4 ck3` == `ck3 swap 2 4`: the set may come after the two members
            named = [t for t in rest if t.lower() in lower_known]
            if len(named) == 1:
                rest = list(rest)
                rest.remove(named[0])
                return Parsed(verb.name, [_name_target(named[0], known)], rest, flags)
        if verb.sets in ("one", "many", "optional") and rest and not _is_flag(rest[0]) \
                and verb.name not in ("new",) and rest[0] != "--":
            if not (verb.name == "drop" and rest[0] in ("rm", "disable")):
                targets.append(_name_target(rest[0], known))
                rest = rest[1:]
            elif len(rest) > 1 and rest[1].lower() in lower_known:
                # `drop rm ck3 [3]` == `ck3 drop rm [3]`: the set may follow the mode word
                targets.append(_name_target(rest[1], known))
                rest = [rest[0]] + rest[2:]
        return Parsed(verb.name, targets, rest, flags)

    targets = []
    j = 0
    while j < len(words) and not _is_flag(words[j]) and not rv.lookup(words[j]):
        if words[j] == "--":
            break
        targets.append(_name_target(words[j], known))
        j += 1
    rest = words[j:]
    # global flags may sit between names and the action
    while rest and _is_flag(rest[0]) and rest[0] != "--":
        if rest[0].split("=", 1)[0] not in rv.GLOBAL_FLAGS and not re.match(r"^-[vqoyj]+$", rest[0]):
            raise GrammarError(f"put '{rest[0]}' after the action, not before it")
        flags.append(rest[0])
        rest = rest[1:]
    if not rest:
        return Parsed("show", targets, [], flags)
    verb = rv.lookup(rest[0])
    if not verb:
        raise GrammarError(f"'{rest[0]}' is not an action{_suggest(rest[0], [])}")
    if verb.sets == "one" and len(targets) != 1:
        raise GrammarError(f"'{verb.name}' works on exactly one set (got {len(targets)})")
    if verb.sets == "none" and targets:
        raise GrammarError(f"'{verb.name}' does not take a set name")
    return Parsed(verb.name, targets, rest[1:], flags)
