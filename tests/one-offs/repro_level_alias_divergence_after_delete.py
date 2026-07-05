"""FIXED 2026-07-05 (lib 0.10.16-alpha e0afa69 + app 0.11.32-alpha):
register_key_default gives BOTH spellings the same unset answer
("tool (default)", exit 0). Living regressions:
test_meta_foreground.py::TestLevelNodeValueAlias (app) and
test_prop_commands.py::TestTesterHoldFixes (lib). Kept as history."""
"""Repro: `dz level` and `dz :.level` disagree after `dz prop delete :.level`.

Found while running the v0.8.1 bedrock checklist, Section 1.5
(dazzle-lib's tests/checklists/v0.8.1__Feature__nucleus-rank-addressing-
and-level-alias.md). The checklist asked to "confirm dz level after shows
gentle default; flag for review, don't fail" -- but the actual finding is
sharper than a review question: the two spellings of the "one-node value
alias" (dazzlecmd/src/dazzlecmd/commands/meta.py's docstring: "dz .level,
dz prop get .level, and dz level are one value") give DIFFERENT answers
with DIFFERENT exit codes once the property is unset.

Root cause:
  - `dz level` (no value) dispatches to `meta._cmd_meta_use`, which reads
    via `foreground_level(engine)` ->
    `engine.property_store.get(key, DEFAULT_FOREGROUND)` -- a default
    fallback of "tool" is baked in (meta.py:80-85, DEFAULT_FOREGROUND="tool").
  - `dz :.level` dispatches through the node-value alias to
    `prop_commands.cmd_get`, which calls
    `engine.property_store.get(key)` -- NO default -- so it prints
    "<key> is not set" and returns exit 1.

Net effect: after `dz prop delete :.level` (or `dz meta reset`), the two
"one value" read paths diverge:
  dz level    -> "tool"              exit 0
  dz :.level  -> "dz.level is not set" exit 1

This breaks the stated invariant that both spellings read one validated
value. Either `cmd_get` needs a way to consult the same gentle-default
fallback the alias's owner registers, or `foreground_level()` needs to
stop defaulting silently -- the current split is inconsistent regardless
of which is "the intended" behavior.

Run (bare dz CLI, isolated config): python tests/one-offs/repro_level_alias_divergence_after_delete.py
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

        run(["level=aggregator"], config_path)  # seed a value
        before_level = run(["level"], config_path)
        before_alias = run([":.level"], config_path)
        print(f"before delete: dz level -> {before_level.stdout.strip()!r} "
              f"(exit {before_level.returncode})")
        print(f"before delete: dz :.level -> {before_alias.stdout.strip()!r} "
              f"(exit {before_alias.returncode})")

        run(["prop", "delete", ":.level"], config_path)

        after_level = run(["level"], config_path)
        after_alias = run([":.level"], config_path)
        print(f"after delete:  dz level -> {after_level.stdout.strip()!r} "
              f"(exit {after_level.returncode})")
        print(f"after delete:  dz :.level -> {after_alias.stdout.strip()!r} "
              f"(exit {after_alias.returncode})")

        diverges = (
            after_level.returncode != after_alias.returncode
            or after_level.stdout.strip() != after_alias.stdout.strip()
        )
        if diverges:
            print(
                "BUG CONFIRMED: the two 'one value' read paths disagree "
                "after delete.",
                file=sys.stderr,
            )
            return 1
        print("not reproduced (both paths agree) -- may be fixed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
