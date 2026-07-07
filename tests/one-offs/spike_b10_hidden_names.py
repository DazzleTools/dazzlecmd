"""B-10 -- the hidden-name spike (convergence DWP D4; the plan B-10).

HYPOTHESIS: `:.x` is not a third mechanism -- it is `:` (select) applied
to a HIDDEN NAME (a dot-led child). If a naive tokenizer that knows only
{`:` select, mid-segment `.` property, leading-`.` hidden name} produces
the SAME canonical key as the shipped grammar for every representative
spelling, the fiber operator is SUGAR, not structure -- and the grammar
can (at merge-back) unify on two primitives instead of three.

ADOPTION BAR (D4): total equivalence. One divergence = report + stop.
"""
import sys

sys.path.insert(0, "C:/code/dazzlecmd/fiber-work/src")

from dazzlecmd_lib.fqcn_grammar import canonicalize


def naive_canonical(text, implicit_root="dz"):
    """The two-primitive reading: ':' selects (a leading '.' just makes
    the name hidden); the LAST mid-segment '.' splits off a property."""
    if not text:
        return None
    s = text
    if s.startswith(":"):
        s = implicit_root + s
    elif s.startswith("."):
        # a bare '.prop' = the root's property (same in both readings)
        s = implicit_root + s
    segs = s.split(":")
    out, prop = [], None
    for i, seg in enumerate(segs):
        if not seg:
            return None  # empty segment -- not this spike's territory
        is_last = i == len(segs) - 1
        if is_last and "." in seg.lstrip("."):
            # a mid-segment dot on the final segment = the property step
            head, _, prop = seg.rpartition(".")
            # careful: '.meta' alone has no mid dot; '.meta.note' does
            if head in ("", "."):
                head, prop = seg, None
            out.append(head)
        else:
            out.append(seg)
    key = ":".join(out)
    return key + ("." + prop if prop else "")


VECTORS = [
    # the fiber plane
    ":.meta", ":.meta:verb", ":.meta:verb:management",
    ":.meta:verb:management:membership", ":.meta:level",
    ":.meta:level:kit", ":.meta:level:internaltool",
    # entity plane
    ":core", ":core:safedel", ":media:crossfade",
    "dz:core:safedel", "dz:.meta:level",
    # properties on each plane
    ".note", ".level", ":core:safedel.version",
    ":.meta:verb:management.expose", "dz.level",
    # mixed depth
    ":.meta:verb:mode", ":.meta:verb:mode:tracking",
]


def main():
    diverged = []
    for v in VECTORS:
        try:
            shipped, _forgiven = canonicalize(v, implicit_root="dz")
        except Exception as e:
            shipped = f"<error: {type(e).__name__}>"
        naive = naive_canonical(v)
        mark = "==" if shipped == naive else "!!"
        if shipped != naive:
            diverged.append((v, shipped, naive))
        print(f"  {mark} {v!r:44} shipped={shipped!r:44} naive={naive!r}")
    print()
    if diverged:
        print(f"VERDICT: NOT equivalent ({len(diverged)} divergence(s)) "
              f"-- D4's bar not met; the fiber operator carries real "
              f"structure. Report + stop (no adoption).")
    else:
        print("VERDICT: TOTAL EQUIVALENCE -- ':.x' is ':' + a hidden "
              "name. Grammar unification (two primitives) goes to the "
              "merge-back ledger.")
    return 1 if diverged else 0


if __name__ == "__main__":
    raise SystemExit(main())
