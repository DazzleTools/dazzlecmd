"""FIXED 2026-07-06 (lib 0.10.21-alpha + app 0.11.37-alpha): living
regressions in test_info_fiber_cards.py::TestMatrixSweepFixes."""
"""Repro: `dz info :.meta:verb:loading:attach` (and `...detach`) show NO
"help:" line on their card, even though `dz attach` / `dz detach` are real,
working top-level bare-verb commands with real argparse help text
("Attach a kit (loading warm pole)" / "Detach a kit to a pointer (loading
cold pole)", dazzlecmd/src/dazzlecmd/parsers.py:341-351).

Found during the v0.11.36-alpha surface-matrix sweep (consistency row 3:
"CARD help line == the argparse help for every verb (registry<->tree)").

Root cause: `_graft_app_verbs`
(dazzlecmd/src/dazzlecmd/commands/inspect.py:96-123) maps each top-level
argparse verb to a tree node by matching on the LAST SEGMENT NAME only:

    by_segment.setdefault(n.rsplit(":", 1)[-1].lstrip("."), []).append(n)
    ...
    for name, help_text in pairs:
        hits = by_segment.get(name, [])
        if len(hits) == 1:
            tree.nodes[hits[0]].setdefault("help", help_text)
        elif not hits:
            ...  # synthesize a flat node
        # NOTE: no `else` -- an AMBIGUOUS match (len(hits) > 1) is silently
        # dropped. No help is attached anywhere.

"attach"/"detach" are ambiguous: the segment name "attach" appears at BOTH
`dz:.level:kit:loading:attach` (the presence-space machinery, mounted
because "loading" is not one of KIT_PRESENCE_SPACE's native axes -- see
fqcn_tree.py's `_default_mounts`) AND `dz:.meta:verb:loading:attach` (the
verb registry, mounted from VERB_SPACE). Two hits -> silently dropped.

By contrast "enable"/"disable" (the activation axis) escape this by
ACCIDENT of naming: `dz:.level:kit:activation`'s native rungs are named
"active"/"inactive" (state names), not "enable"/"disable" (verb names), so
"enable"/"disable" match exactly ONE tree node each and correctly receive
their help text.

The SAME ambiguity mechanism would also silently drop help for
membership's add/remove and projection's favorite/unfavorite IF those were
ever hoisted to top-level bare verbs (today they are not -- only reachable
via `dz kit add|remove|favorite|unfavorite` -- so no argparse pair exists
for them at the top level and the question does not arise yet, but the
underlying silent-drop is still a latent defect for any FUTURE hoist that
collides with an existing rung-name).

Run (bare dz CLI, isolated config):
    python tests/one-offs/repro_verb_help_ambiguous_segment_drop.py
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

        # Control: the CLI command really does have help text registered.
        attach_argparse_help = run(["attach", "-h"], config_path)
        print("--- dz attach -h ---")
        print(attach_argparse_help.stdout)

        # The card that should surface that same help text.
        attach_card = run(["info", ":.meta:verb:loading:attach"], config_path)
        detach_card = run(["info", ":.meta:verb:loading:detach"], config_path)
        print("--- dz info :.meta:verb:loading:attach ---")
        print(attach_card.stdout)
        print("--- dz info :.meta:verb:loading:detach ---")
        print(detach_card.stdout)

        # Control: activation's enable/disable DO get their help line
        # (same mechanism, but unambiguous segment names).
        enable_card = run(["info", ":.meta:verb:activation:enable"], config_path)
        print("--- dz info :.meta:verb:activation:enable (control, expected help:) ---")
        print(enable_card.stdout)

        missing_attach_help = "help:" not in attach_card.stdout
        missing_detach_help = "help:" not in detach_card.stdout
        has_enable_help = "help:" in enable_card.stdout

        if missing_attach_help and missing_detach_help and has_enable_help:
            print(
                "BUG CONFIRMED: attach/detach cards omit 'help:' despite a "
                "real registered argparse help string; activation's "
                "enable/disable (same code path) show it fine.",
                file=sys.stderr,
            )
            return 1
        print("not reproduced -- may be fixed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
