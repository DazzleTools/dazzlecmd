"""POC-8 (collab round 3, consultant): `dz relaunch` grammar, two shapes.

  A  name-first:  dz relaunch [flags] <name>... <verb> [verb args]
  B  names-last:  dz relaunch [flags] <verb> [verb args] <name>...

Both are throwaway parsers over the same verb table and the same fake store.
Each returns a small "intent" dict or an error string (what a person would
see). The table at the bottom runs the same intents, spelled each way, plus
typos, and prints both results side by side. Nothing is executed or written.

Usage: python poc8_grammar_name_first_vs_last.py
"""
import difflib
import re

SETS = {"safedel": ["lib", "claude", "docs"], "ck3": ["mod", "claude"], "csb-work": []}
VIEW = re.compile(r"^(last(~\d+)?|current|boot)$")
TOKEN = re.compile(r"^(?P<name>[A-Za-z0-9_~-]+):(?P<n>\d+)$")

# verb -> (takes sets: "none" | "one" | "many" | "new", sub-modes, takes entries)
VERBS = {
    "show": ("many", None, True),
    "list": ("none", None, False),
    "new": ("new", None, False),
    "add": ("one", None, False),
    "edit": ("one", None, True),
    "note": ("one", None, True),
    "claim": ("many", None, True),
    "release": ("many", None, True),
    "drop": ("one", ("rm", "disable"), True),
    "enable": ("one", None, True),
    "shell-init": ("none", None, False),
}
ALIASES = {"ls": "list"}
BOOL_FLAGS = {"-o", "--open", "-y", "--yes", "--json", "--next", "--print", "--tabs", "--no-color"}
VALUE_FLAGS = {"--label", "--notes", "--folder", "--at"}


def is_count_flag(tok):
    return re.match(r"^-[vq]+$", tok) is not None


def known_name(tok):
    return tok.lower() in SETS or VIEW.match(tok) is not None


def suggest(tok, pool):
    hit = difflib.get_close_matches(tok.lower(), list(pool), n=1, cutoff=0.6)
    return hit[0] if hit else None


def unknown_name_message(tok):
    v = suggest(tok, VERBS)
    s = suggest(tok, SETS)
    if v and not s:
        return "no set named '%s' -- did you mean the action '%s'?" % (tok, v)
    if s:
        return "no set named '%s' -- did you mean '%s'?" % (tok, s)
    return "no set named '%s' (dz relaunch list shows them)" % tok


def split_token(tok):
    """'safedel:2' -> ('safedel', '2'); plain name -> (name, None)."""
    m = TOKEN.match(tok)
    return (m.group("name"), m.group("n")) if m else (tok, None)


def finish(verb, names, rest, flags):
    """Shared back half: validate names/entries against the verb's contract."""
    wants, modes, takes_entries = VERBS[verb]
    mode = None
    if modes:
        if not rest or rest[0] not in modes:
            return "'%s' needs one of: %s" % (verb, ", ".join(modes))
        mode, rest = rest[0], rest[1:]
    entries = list(rest)
    resolved = []
    for raw in names:
        name, n = split_token(raw)
        if n is not None:
            entries.append(n)
        resolved.append(name)
    if wants == "none" and resolved:
        return "'%s' takes no set name" % verb
    if wants == "new":
        if len(resolved) != 1:
            return "'new' needs exactly one new set name"
        if resolved[0].lower() in VERBS or resolved[0].isdigit() or VIEW.match(resolved[0]):
            return "'%s' is a reserved word and cannot name a set" % resolved[0]
        return {"verb": verb, "sets": resolved, "flags": sorted(flags)}
    for name in resolved:
        if not known_name(name):
            return unknown_name_message(name)
    if wants == "one" and len(resolved) != 1:
        return "'%s' works on exactly one set (got %d)" % (verb, len(resolved))
    if wants == "many" and not resolved and verb != "show":
        return "'%s' needs a set name" % verb
    if entries and not takes_entries:
        return "'%s' takes no entry" % verb
    if entries and len(resolved) != 1:
        return "an entry needs exactly one set (got %d sets)" % len(resolved)
    out = {"verb": verb, "sets": resolved, "flags": sorted(flags)}
    if mode:
        out["mode"] = mode
    if entries:
        out["entries"] = entries
    return out


# ---------------------------------------------------------------- shape A
def parse_name_first(argv):
    names, flags = [], set()
    i = 0
    while i < len(argv):
        tok = argv[i]
        low = ALIASES.get(tok.lower(), tok.lower())
        if is_count_flag(tok) or tok in BOOL_FLAGS:
            flags.add(tok)
        elif tok in VALUE_FLAGS:
            return "put '%s' after the action, not before it" % tok
        elif tok.startswith("-"):
            return "unknown option '%s'" % tok
        elif low in VERBS:
            rest = []
            j = i + 1
            while j < len(argv):
                t = argv[j]
                if is_count_flag(t) or t in BOOL_FLAGS:
                    flags.add(t)
                elif t in VALUE_FLAGS:
                    flags.add(t + "=" + (argv[j + 1] if j + 1 < len(argv) else "?"))
                    j += 1
                else:
                    rest.append(t)
                j += 1
            if not names and VERBS[low][0] in ("one", "many", "new") and rest and not VERBS[low][1]:
                # verb typed first, nothing before it: take the names from after it
                # (only safe for verbs with no entry list of their own, or one token)
                if VERBS[low][0] == "new" or not VERBS[low][2]:
                    names, rest = rest, []
                else:
                    names, rest = rest[:1], rest[1:]
            return finish(low, names, rest, flags)
        else:
            names.append(tok)
        i += 1
    if not names:
        return {"verb": "list", "sets": [], "flags": sorted(flags)}       # bare: dashboard
    return finish("show", names, [], flags)                               # implicit show


# ---------------------------------------------------------------- shape B
def parse_names_last(argv):
    flags, pos = set(), []
    i = 0
    while i < len(argv):
        t = argv[i]
        if is_count_flag(t) or t in BOOL_FLAGS:
            flags.add(t)
        elif t in VALUE_FLAGS:
            flags.add(t + "=" + (argv[i + 1] if i + 1 < len(argv) else "?"))
            i += 1
        elif t.startswith("-"):
            return "unknown option '%s'" % t
        else:
            pos.append(t)
        i += 1
    if not pos:
        return {"verb": "list", "sets": [], "flags": sorted(flags)}
    low = ALIASES.get(pos[0].lower(), pos[0].lower())
    if low not in VERBS:
        return finish("show", pos, [], flags)          # implicit show: every positional is a name
    wants, modes, takes_entries = VERBS[low]
    rest = pos[1:]
    mode_tok = []
    if modes and rest:
        mode_tok, rest = rest[:1], rest[1:]
    if wants in ("none",):
        return finish(low, [], mode_tok + rest, flags) if not rest else "'%s' takes no set name" % low
    if wants == "new":
        return finish(low, rest, [], flags)
    if wants == "one":
        # last positional is the set, everything before it is entries
        if not rest:
            return finish(low, [], mode_tok, flags) if modes else "'%s' needs a set name" % low
        return finish(low, rest[-1:], mode_tok + rest[:-1], flags)
    # wants == "many": entries AND several sets are both variable-length.
    # The only split available is a guess: a token that is a known set is a set.
    names = [t for t in rest if known_name(split_token(t)[0])]
    entries = [t for t in rest if not known_name(split_token(t)[0])]
    return finish(low, names, entries, flags)


# ---------------------------------------------------------------- table
CASES = [
    # (what the person means, name-first spelling, names-last spelling)
    ("dashboard",                          "",                               ""),
    ("show one set",                       "safedel",                        "safedel"),
    ("show two sets",                      "safedel ck3",                    "safedel ck3"),
    ("claim next from one set, print",     "safedel claim",                  "claim safedel"),
    ("claim and run here",                 "safedel claim -o",               "claim -o safedel"),
    ("claim from first of two with a free member", "safedel ck3 claim -o",   "claim -o safedel ck3"),
    ("claim entry 2",                      "safedel claim 2",                "claim 2 safedel"),
    ("claim entry by label",               "safedel claim lib",              "claim lib safedel"),
    ("claim entry via token",              "safedel:2 claim",                "claim safedel:2"),
    ("claim from last session view",       "last claim",                     "claim last"),
    ("claim member 2 of last~1",           "last~1:2 claim",                 "claim last~1:2"),
    ("drop one entry to trash",            "safedel drop rm 3",              "drop rm 3 safedel"),
    ("drop the whole set to trash",        "safedel drop rm",                "drop rm safedel"),
    ("disable an entry by label",          "safedel drop disable docs",      "drop disable docs safedel"),
    ("verbose, flag first",                "-vvv safedel claim",             "-vvv claim safedel"),
    ("verbose, flag last",                 "safedel drop rm 3 -vvv",         "drop rm 3 safedel -vvv"),
    ("verbose, flag in the middle",        "safedel -vvv claim -o",          "claim -vvv -o safedel"),
    ("new set",                            "work2 new",                      "new work2"),
    ("new set, verb typed first (A's fallback)", "new work2",                "new work2"),
    ("note on an entry",                   "safedel note 2 remember-this",   "note 2 remember-this safedel"),
    ("typo in the set name",               "safedl claim",                   "claim safedl"),
    ("typo in the action",                 "safedel clam",                   "clam safedel"),
    ("typo in the drop mode",              "safedel drop rmm 3",             "drop rmm 3 safedel"),
    ("entry label that is also a set name", "safedel claim ck3",             "claim ck3 safedel"),
    ("set named like an action",           "claim new",                      "new claim"),
    ("value option before the action",     "safedel --label x add",          "add --label x safedel"),
    ("two sets and an entry",              "safedel ck3 claim 2",            "claim 2 safedel ck3"),
    ("action only, no set",                "claim",                          "claim"),
]


def show(r):
    if isinstance(r, str):
        return "ERROR: " + r
    parts = [r["verb"]]
    if r.get("mode"):
        parts.append("mode=" + r["mode"])
    parts.append("sets=" + ",".join(r["sets"]) if r["sets"] else "sets=-")
    if r.get("entries"):
        parts.append("entries=" + ",".join(r["entries"]))
    if r["flags"]:
        parts.append("flags=" + " ".join(r["flags"]))
    return " ".join(parts)


if __name__ == "__main__":
    same = differ = 0
    for meaning, a, b in CASES:
        ra, rb = parse_name_first(a.split()), parse_names_last(b.split())
        mark = "same" if show(ra) == show(rb) else "DIFFER"
        same += mark == "same"
        differ += mark != "same"
        print("%s  [%s]" % (meaning, mark))
        print("   A  dz relaunch %-32s -> %s" % (a, show(ra)))
        print("   B  dz relaunch %-32s -> %s" % (b, show(rb)))
    print("\n%d cases: %d same result, %d differ" % (len(CASES), same, differ))
    import inspect
    for fn in (parse_name_first, parse_names_last):
        src = [l for l in inspect.getsource(fn).splitlines() if l.strip() and not l.strip().startswith("#")]
        print("%s: %d code lines" % (fn.__name__, len(src)))
