"""FIXED 2026-07-05 (lib 0.10.15-alpha): the failing assertion below
was the BUG DEMONSTRATION -- `:.level=` now routes through the level
validator via prop_commands.NODE_VALUE_ALIASES (one-node value alias).
The living regression: tests/test_meta_foreground.py::TestLevelNodeValueAlias
and the lib vectors in test_prop_commands.py::TestNodeValueAlias.
Kept as history per the one-offs doctrine."""
"""Repro: the fiber-plane axis node `:.level` accepts an unvalidated
scalar write, silently landing under a separate, non-functional shadow
key from the validated, functional `.level` property (tester-unbounded
sweep, 2026-07-04, lib e1890c7 / app 49afea0).

Background (confirmed via dazzlecmd_lib/fqcn_grammar.py:225-241): `level`
was intentionally added to FIBER_ROOTS on 2026-07-04 ("joined 2026-07-04:
the axis node is REAL post-2d (the invariant caught bare ':.level'
forgiving away, making the axis unaddressable)") -- this is the fix for
the "bare :.level forgiving away the axis node" field-find already
mentioned in project context. Because of that fix, `:.level` (fiber
plane) is now CORRECTLY and INTENTIONALLY a real, separately-addressable
axis node, distinct from `.level` / `level` / `level=<x>` (the three
documented spellings of the root PROPERTY that actually drives
LEVEL_CONTINUUM state -- see the same comment block: "The property keeps
its three spellings (dz level / dz .level / level=)").

That distinction is legitimate design, not a bug by itself. The gap this
repro documents is downstream of it: `prop_commands.py::_write()` looks
up `VALIDATED_KEYS` by the CANONICAL key string. The level-enum validator
is registered against the PROPERTY-plane key only. Since the fiber-plane
axis node canonicalizes to a DIFFERENT key (confirmed empirically below
-- setting one spelling never appears when reading the other), the
validator never fires for the fiber-plane spelling:

    dz .level=bogus    -> rc=2, rejected: "invalid level: 'bogus' ..."
    dz :.level=bogus   -> rc=0, SILENTLY stored, no warning at all

A user who mistypes an extra leading ':' on what looks like a normal
level assignment gets zero feedback that the write landed on an inert,
unvalidated shadow property instead of the real level state. This is a
believable typo trap: ':' and '.' are one keystroke apart on every
layout, and the CLI gives no "did you mean .level?" hint.

Run directly: python tests/one-offs/repro_fiber_axis_level_write_unvalidated.py
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

        # Control: the validated property-plane spelling correctly rejects.
        rc, out, err = _run([".level=bogus"], cfg)
        combined = (out + err).strip()
        ok = (rc == 2 and "invalid level" in combined)
        print(f"[{'OK' if ok else 'MISMATCH'}] .level=bogus (property plane, validated)")
        print(f"    rc={rc} output={combined!r}")
        if not ok:
            failures += 1

        # BUG: the fiber-plane axis node accepts the same bogus value silently.
        rc, out, err = _run([":.level=bogus"], cfg)
        combined = (out + err).strip()
        is_bug = (rc == 0 and "added dz:.level" in combined)
        print(f"\n[{'BUG-CONFIRMED' if is_bug else 'NOT REPRODUCED'}] "
              f":.level=bogus (fiber plane, axis node -- expected at minimum "
              f"a warning that this spelling bypasses validation)")
        print(f"    actual: rc={rc} output={combined!r}")
        if not is_bug:
            failures += 1

        # Confirm the two spellings are genuinely separate stored keys:
        # reading .level (property plane) must NOT show the fiber-plane value.
        rc, out, err = _run([".level"], cfg)
        combined = (out + err).strip()
        divergent = ("bogus" not in combined)
        print(f"\n[{'CONFIRMED DIVERGENT' if divergent else 'UNEXPECTED: same key'}] "
              f".level read after :.level=bogus")
        print(f"    actual: rc={rc} output={combined!r}")
        print(f"    -> if this ever shows 'bogus', the two spellings share a "
              f"key and the finding above should be re-read as the property "
              f"plane's OWN validator being bypassed (higher severity).")
        if not divergent:
            failures += 1

    print(f"\n{failures} of 3 checks did not match the expected/confirmed-bug "
          f"shape (0 means the gap is confirmed present and isolated as "
          f"described).")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# --- pytest-collectible versions of the same checks -------------------

def test_property_plane_level_validates(tmp_path):
    cfg = _fresh_cfg(str(tmp_path))
    rc, out, err = _run([".level=bogus"], cfg)
    assert rc == 2
    assert "invalid level" in (out + err)


def test_fiber_plane_axis_level_currently_bypasses_validation(tmp_path):
    """Documents CURRENT (gap) behavior: the fiber-plane axis node
    `:.level` accepts and silently stores a value the property-plane
    validator would reject, with zero warning.

    If this assertion starts failing (rc becomes nonzero, or a warning
    is emitted), the gap has been addressed -- update this test and
    delete this comment.
    """
    cfg = _fresh_cfg(str(tmp_path))
    rc, out, err = _run([":.level=bogus"], cfg)
    assert rc == 0
    assert "added dz:.level = 'bogus'" in (out + err)


def test_fiber_and_property_plane_level_are_separate_keys(tmp_path):
    """Confirms the two spellings are genuinely distinct storage keys
    (by design, per fqcn_grammar.py FIBER_ROOTS including 'level' as of
    2026-07-04) -- setting the fiber-plane axis node must not be visible
    when reading the property-plane spelling.
    """
    cfg = _fresh_cfg(str(tmp_path))
    _run([":.level=bogus"], cfg)
    rc, out, err = _run([".level"], cfg)
    assert "bogus" not in (out + err)
