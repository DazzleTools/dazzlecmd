"""FIXED 2026-07-06 (lib 0.10.21-alpha + app 0.11.37-alpha): living
regressions in test_info_fiber_cards.py::TestMatrixSweepFixes."""
"""Repro: a child-segment name >= 14 chars glues onto its kind word with NO
separating space in BOTH the info card's "contains:" section and the `:.`
listing's "-- structure:" section.

Found during the v0.11.36-alpha surface-matrix sweep
(tests/checklists/v0.11.36-alpha__Feature__surface-matrix-sweep.md), probes
`dz info :.meta:verb:mode` and `dz :.meta:verb:mode:.` -- the child segment
"materialization" (15 chars) renders as:

    materializationContinuum

instead of (e.g.):

    materialization Continuum

Root cause: TWO duplicate renderers hardcode a fixed left-justify width of
14 with no guaranteed minimum separator:

  - dazzlecmd/src/dazzlecmd/commands/inspect.py:213 (the card's "contains:")
        print(f"    {seg:<14}{kn.get('kind', '')}{rolet}{rank}{marker}")
  - dazzlecmd-lib/dazzlecmd_lib/prop_commands.py:320 (the listing's
    "-- structure:")
        f"    {seg:<14}{kn.get('kind', '')}{role}{rank}{marker}"

Python's `f"{s:<14}"` only PADS when `len(s) < 14`; it never truncates NOR
guarantees a separating space when `len(s) >= 14`. Any future node name of
length >= 14 (not just "materialization") reproduces this. Fix belongs in
BOTH files (they are independent duplicate implementations, not shared) --
e.g. `f"    {seg:<14} "` -> still fails at len==14 exactly; a robust fix
needs `max(seg, 14 chars via a real column-formatter, or an explicit
"    {seg} ".ljust(15) style guard`.

Run (bare dz CLI, isolated config):
    python tests/one-offs/repro_contains_column_padding_overflow.py
"""
import os
import subprocess
import sys
import tempfile


def run(args, config_path):
    env = dict(os.environ)
    env["DAZZLECMD_CONFIG"] = config_path
    return subprocess.run(
        ["dz"] + args, env=env, capture_output=True, text=True
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        config_path = os.path.join(tmp, "config.json")

        card = run(["info", ":.meta:verb:mode"], config_path)
        listing = run([":.meta:verb:mode:."], config_path)

        print("--- dz info :.meta:verb:mode ---")
        print(card.stdout)
        print("--- dz :.meta:verb:mode:. ---")
        print(listing.stdout)

        glued_card = "materializationContinuum" in card.stdout
        glued_listing = "materializationContinuum" in listing.stdout

        if glued_card or glued_listing:
            print(
                "BUG CONFIRMED: 'materialization' glues directly onto "
                f"'Continuum' with no separator (card={glued_card}, "
                f"listing={glued_listing}).",
                file=sys.stderr,
            )
            return 1
        print("not reproduced (separator present) -- may be fixed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
