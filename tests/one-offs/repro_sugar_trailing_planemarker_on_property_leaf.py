"""Repro: the bare CLI-sugar trailing-':.' plane-listing intercept also
silently fires on arbitrary PROPERTY-LEAF paths, not just recognized
fiber/container nodes -- contradicting fqcn_grammar.py's own documented
grammar contract (tester-unbounded sweep, 2026-07-04, lib e1890c7 / app
49afea0).

SAME ROOT CAUSE as the sibling repro
`repro_prop_verb_trailing_fiber_listing_gap.py` (engine.py ~2057-2065):

    # trailing ':.' -> the plane listing (entity and property paths
    # alike; the split already ran, C-5 step 3)
    if trailing is not None:
        ...

That comment is explicit: the bare-sugar entry point (`dz X:.`) treats a
trailing ':.' as the plane-listing operator for ANY path shape -- fiber
AND property alike -- stripping it BEFORE canonicalize()/parse() ever
run. The sibling repro demonstrated the asymmetry this creates between
the bare sugar (accepts it) and the canonical verbs `prop list`/`prop
get` (correctly reject it, since they route straight through
canonicalize() -> parse() without this pre-strip).

THIS repro demonstrates the same mechanism produces a SEPARATE, broader
symptom the sibling repro didn't cover: applied to a plain PROPERTY-LEAF
path (never a container), the CLI can't tell "a real, recognized-but-
empty fiber plane" apart from "a nonsense trailing marker on a leaf that
either has a scalar value or was never touched at all":

  * `.note:.` on a leaf that HAS a value ("hello") silently drops the
    trailing ':.' and returns the leaf's value in LIST format
    (`dz.note = 'hello'`) instead of erroring -- the operator is just
    gone, no warning.
  * `.brandnewprop:.` on a leaf that was NEVER set returns
    `no properties set under dz.brandnewprop` (rc=0) -- textually
    IDENTICAL to the message a genuine, recognized-but-empty fiber
    container gives (`:.kit:.` -> `no properties set under dz:.kit`
    when nothing is set under kit yet). There is no way, from the
    output alone, to tell "this path doesn't exist / isn't a
    container" from "this is a real container with nothing in it yet".

This directly contradicts fqcn_grammar.py's own `canonicalize()`
docstring (~line 258-259): "Interior ``:.``/``:+`` after a forgiven
first segment ERROR on the re-parse (the property plane rejects them --
don't guess)." That contract IS honored by the canonical verbs (see the
sibling repro); it is bypassed entirely by the bare-sugar pre-strip.

Run directly: python tests/one-offs/repro_sugar_trailing_planemarker_on_property_leaf.py
(diagnostic one-off -- tests/one-offs/ is a scratchpad, not a CI-gated
regression; also pytest-collectible.)

DIAGNOSE ONLY -- do not fix here.
"""
import json
import os
import subprocess
import sys
import tempfile


def _run(argv, cfg_path):
    env = os.environ.copy()
    env["DAZZLECMD_CONFIG"] = cfg_path
    r = subprocess.run(
        [sys.executable, "-m", "dazzlecmd", *argv],
        capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


def _fresh_cfg(tmpdir):
    cfg_path = os.path.join(tmpdir, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"_schema_version": 1, "active_kits": [], "disabled_kits": []}, f)
    return cfg_path


def main():
    failures = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = _fresh_cfg(tmpdir)

        # Baseline: plain leaf read of a never-set property -> "is not set", rc=1
        rc, out, err = _run([".brandnewprop"], cfg)
        combined = (out + err).strip()
        ok = (rc == 1 and "is not set" in combined)
        print(f"[{'OK' if ok else 'MISMATCH'}] plain leaf read, never set (control)")
        print(f"    rc={rc} output={combined!r}")
        if not ok:
            failures += 1

        # Set a leaf value, confirm plain read.
        rc, out, err = _run([".note=hello"], cfg)
        rc, out, err = _run([".note"], cfg)
        combined = (out + err).strip()
        ok = (rc == 0 and combined == "hello")
        print(f"\n[{'OK' if ok else 'MISMATCH'}] plain leaf read after set (control)")
        print(f"    rc={rc} output={combined!r}")
        if not ok:
            failures += 1

        # BUG: trailing ':.' on a VALUED leaf silently drops the marker.
        rc, out, err = _run([".note:."], cfg)
        combined = (out + err).strip()
        is_bug = (rc == 0 and combined == "dz.note = 'hello'")
        print(f"\n[{'BUG-CONFIRMED' if is_bug else 'NOT REPRODUCED'}] "
              f".note:. (trailing marker on a VALUED leaf)")
        print(f"    expected: an error (property plane rejects trailing ':.' "
              f"per fqcn_grammar.py's own contract), or at minimum a distinct "
              f"signal that ':.' was not honored as a listing request")
        print(f"    actual:   rc={rc} output={combined!r}")
        if not is_bug:
            failures += 1

        # BUG: trailing ':.' on a NEVER-SET leaf reads as a legitimate
        # empty container -- indistinguishable from a real fiber plane.
        rc, out, err = _run([".brandnewprop:."], cfg)
        combined = (out + err).strip()
        is_bug = (rc == 0 and combined == "no properties set under dz.brandnewprop")
        print(f"\n[{'BUG-CONFIRMED' if is_bug else 'NOT REPRODUCED'}] "
              f".brandnewprop:. (trailing marker on a NEVER-SET, non-container leaf)")
        print(f"    expected: an error or a signal distinguishing 'not a "
              f"container' from 'real container, zero entries'")
        print(f"    actual:   rc={rc} output={combined!r}")
        if not is_bug:
            failures += 1

        # Control: a GENUINE fiber container with zero entries gives the
        # SAME message as the bogus leaf case above -- confirming the two
        # are indistinguishable from the CLI's output.
        rc, out, err = _run([":.kit:."], cfg)
        combined = (out + err).strip()
        print(f"\n[CONTROL] :.kit:. (real, recognized, empty fiber container)")
        print(f"    rc={rc} output={combined!r}")
        print(f"    -> compare to .brandnewprop:. above: SAME wording, SAME rc, "
              f"even though .brandnewprop is not a container at all.")

    print(f"\n{failures} of 2 bug-confirmation checks did not reproduce "
          f"(0 means both are confirmed present).")
    return 0  # diagnostic driver; use the pytest functions below for CI-style assertions


if __name__ == "__main__":
    sys.exit(main())


# --- pytest-collectible versions of the same checks -------------------

def _run_pytest(argv, cfg_path):
    return _run(argv, cfg_path)


def test_valued_leaf_trailing_planemarker_currently_silently_ignored(tmp_path):
    """Documents CURRENT (buggy) behavior: trailing ':.' on a leaf that
    HAS a value silently drops the marker and returns the value in list
    format, instead of erroring per fqcn_grammar.py's own contract.

    If this assertion starts failing, the gap has likely been closed --
    flip it to assert an error and delete this comment.
    """
    cfg = _fresh_cfg(str(tmp_path))
    _run_pytest([".note=hello"], cfg)
    rc, out, err = _run_pytest([".note:."], cfg)
    assert rc == 0
    assert (out + err).strip() == "dz.note = 'hello'"


def test_neverset_leaf_trailing_planemarker_currently_reads_as_empty_container(tmp_path):
    """Documents CURRENT (buggy) behavior: a never-set, non-container
    leaf path with a trailing ':.' reads as "no properties set under
    X" -- textually identical to a real, empty fiber container -- with
    no signal that the path isn't a container at all.
    """
    cfg = _fresh_cfg(str(tmp_path))
    rc, out, err = _run_pytest([".brandnewprop:."], cfg)
    assert rc == 0
    assert (out + err).strip() == "no properties set under dz.brandnewprop"
