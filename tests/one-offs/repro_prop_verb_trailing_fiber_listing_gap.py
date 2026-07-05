"""Repro: canonical `prop {list,get}` verbs reject the documented trailing
':.' listing spelling that the CLI sugar accepts (tester-unbounded sweep,
2026-07-04, lib e1890c7 / app 49afea0).

`dz :.` and `dz :.kit:.` (bare CLI sugar) succeed and perform a family
listing. In dazzlecmd-lib/dazzlecmd_lib/engine.py (~line 2052-2066), the
sugar intercept calls `parse_cli()`, which detects a bare trailing ':.'
and returns it separately as `trailing`; when present, the engine calls
`prop_commands.cmd_list(self, unparse(parsed))` -- i.e. the TRAILING
MARKER IS STRIPPED before cmd_list/canonicalize/parse ever see it.

The canonical explicit verbs (`dz prop list <path>` / `dz prop get <path>`,
wired in dazzlecmd/dispatch.py ~line 125-126: `_pc.cmd_list(engine,
args.path)`) do NOT run `args.path` through that same trailing-strip. It
goes straight to `_canonical` -> `canonicalize` -> `fqcn_grammar.parse()`,
which correctly rejects ANY trailing operator per grammar contract (a
bare `:.` with nothing after it "at index N" is a malformed path by the
parser's own rules -- see fqcn_grammar.py's docstring: "a trailing
operator" is explicitly one of the documented malformed cases).

prop_commands.py's own module docstring states the design contract this
violates: "One implementation serves BOTH surfaces (v2 contract R1.8):
the explicit verbs ... and the CLI sugar ... which routes to
:func:`cmd_upsert` via the intercept." The trailing-':.' strip is real
sugar-only special-casing that the canonical verb doesn't share, so the
EXACT listing spelling `prop -h` documents ("Sugar: ... 'dz :.' lists")
fails one level down at the canonical form.

Run directly: python tests/one-offs/repro_prop_verb_trailing_fiber_listing_gap.py
(also collectible by pytest, but this is a diagnostic one-off, not a
CI-gated regression -- see project convention: tests/one-offs/ is a
scratchpad, not part of the regression suite.)

DIAGNOSE ONLY -- do not fix here.
"""
import subprocess
import sys


def _run(*argv):
    r = subprocess.run(
        [sys.executable, "-m", "dazzlecmd", *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


CASES = [
    ("sugar bare fiber-root listing (control, expected to PASS)", [":."], 0),
    ("sugar kit-fiber trailing listing (control, expected to PASS)", [":.kit:."], 0),
    ("canonical `prop list :.` (BUG: currently errors, should match sugar)",
     ["prop", "list", ":."], 0),
    ("canonical `prop get :.` (BUG: currently errors, should match sugar)",
     ["prop", "get", ":."], 0),
    ("canonical `prop list :.kit:.` (BUG: currently errors, should match sugar)",
     ["prop", "list", ":.kit:."], 0),
]


def main():
    failures = 0
    for label, argv, expected_rc in CASES:
        rc, out, err = _run(*argv)
        ok = (rc == expected_rc)
        status = "OK" if ok else "MISMATCH"
        if not ok:
            failures += 1
        print(f"[{status}] {label}")
        print(f"    argv={argv} expected_rc={expected_rc} actual_rc={rc}")
        if (out + err).strip():
            print(f"    output: {(out + err).strip()[:200]!r}")
    print(f"\n{failures} of {len(CASES)} cases diverge from the sugar-parity expectation.")
    return failures


if __name__ == "__main__":
    sys.exit(main())


def test_sugar_bare_fiber_root_listing_succeeds():
    rc, out, err = _run(":.")
    assert rc == 0
    assert "Traceback" not in err


def test_sugar_kit_fiber_trailing_listing_succeeds():
    rc, out, err = _run(":.kit:.")
    assert rc == 0
    assert "Traceback" not in err


def test_canonical_prop_list_bare_fiber_root_currently_fails():
    """Documents the CURRENT (buggy) behavior: this fails today, rc=2.

    If this assertion starts failing (rc becomes 0), the gap has been
    closed -- flip this test to assert success and delete this comment.
    """
    rc, out, err = _run("prop", "list", ":.")
    assert rc == 2
    assert "expected a segment name after ':.'" in err


def test_canonical_prop_get_bare_fiber_root_currently_fails():
    rc, out, err = _run("prop", "get", ":.")
    assert rc == 2
    assert "expected a segment name after ':.'" in err


def test_canonical_prop_list_kit_fiber_trailing_currently_fails():
    rc, out, err = _run("prop", "list", ":.kit:.")
    assert rc == 2
    assert "expected a segment name after ':.'" in err
