"""
worktree-teardown - Remove a git worktree without deleting through its links.

`git worktree remove` is not safe for a worktree that holds a junction or a
symlink (for example a `private/` link to the main checkout's notes). Measured
on git 2.52.0.windows.1: it deletes THROUGH the link and empties what the link
points at -- with --force, and also without it when the linked folder is
gitignored. This command never runs it. It:

    1. removes every link inside the worktree -- only the link -- into the
       safedel trash (what each pointed at is recorded and not touched);
    2. checks each target still holds what it held;
    3. moves the worktree folder into the safedel trash;
    4. checks the folder is gone and the targets are still intact;
    5. runs `git worktree prune` in the main repository.

It stops at the first step whose check fails and says what it had done.

Usage:
    dz worktree-teardown <worktree>             Show the plan and ask
    dz worktree-teardown --yes <worktree>       Do it without a prompt
    dz worktree-teardown --dry-run <worktree>   Show the plan only

Everything it removes goes to the safedel trash: `dz safedel list` shows the
batches, and `dz safedel recover <batch-name>` brings one back (after
recovering the folder, `git worktree repair` re-attaches it).

Exit codes (the last line of output is "worktree-teardown: <VERDICT> ..."):
    0  done                      3  refused -- nothing was changed
    1  error                     4  stopped part-way; see the report
    2  usage error
"""

import argparse
import sys
from typing import List, Optional

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_REFUSED, EXIT_PARTIAL = 0, 1, 2, 3, 4

try:
    from dazzlecmd_lib.core.safedel import (
        TrashStore,
        plan_teardown,
        execute_teardown,
        default_registry_path,
        stdin_is_interactive,
        split_yes,
        ScopeError,
        verdict_line,
    )
    _IMPORT_ERROR = None
except ImportError as _exc:   # dazzlecmd-lib older than 0.10.38
    _IMPORT_ERROR = _exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dz worktree-teardown",
        description="Remove a git worktree without deleting through the "
                    "junctions or symlinks inside it. Never runs "
                    "`git worktree remove`.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "What it does, in order: removes the links inside the worktree "
            "(links only),\nchecks their targets, moves the folder to the "
            "safedel trash, checks again,\nthen `git worktree prune`. "
            "Recover with `dz safedel recover <batch-name>`.\n\n"
            "Exit codes: 0 done, 1 error, 2 usage, 3 refused (nothing "
            "changed),\n4 stopped part-way. The last output line is the "
            "verdict."
        ),
    )
    parser.add_argument("worktree", help="The worktree folder to remove")
    # --yes is taken out of the arguments before argparse runs (as in
    # dz safedel); this entry exists for --help.
    parser.add_argument("--yes", "-y", nargs="?", metavar="SCOPES",
                        help="Proceed without a prompt. Required when nobody "
                             "is at the keyboard")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show the plan and change nothing")
    return parser


def _finish(code: int, outcome: str, detail: str) -> int:
    sys.stderr.flush()
    print(verdict_line("worktree-teardown", outcome, detail))
    sys.stdout.flush()
    return code


def _ask(prompt: str) -> Optional[str]:
    try:
        sys.stderr.write(prompt)
        sys.stderr.flush()
        return input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\n")
        return None


def _make_store():
    """The trash store and the link registry for a real run. A function so
    tests can substitute a temp store."""
    return TrashStore(), default_registry_path()


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if _IMPORT_ERROR is not None:
        print("  worktree-teardown needs dazzlecmd-lib 0.10.38 or later "
              f"({_IMPORT_ERROR}). Nothing was changed.", file=sys.stderr)
        print("worktree-teardown: ERROR dazzlecmd-lib is too old")
        return EXIT_ERROR

    try:
        argv, scopes, yes_given = split_yes(list(argv))
    except ScopeError as exc:
        print(f"  worktree-teardown: {exc}", file=sys.stderr)
        return _finish(EXIT_USAGE, "USAGE", str(exc))
    args = _build_parser().parse_args(argv)

    plan = plan_teardown(args.worktree)

    if plan.refused:
        print("\n  worktree-teardown: REFUSED -- nothing will be changed.\n")
        sys.stdout.flush()
        for reason in plan.refusals:
            print(f"  REFUSED: {reason}", file=sys.stderr)
        return _finish(EXIT_REFUSED, "REFUSED", plan.refusals[0])

    print("\n  worktree-teardown: this will happen:\n")
    for line in plan.describe():
        print(line)
    for w in plan.warnings:
        print(f"  * {w}")
    print()

    if args.dry_run:
        print("  DRY RUN: nothing was changed.")
        return _finish(EXIT_OK, "DRY-RUN",
                       f"{len(plan.links)} link(s) and the folder would be removed")

    if not yes_given:
        if not stdin_is_interactive():
            print("  REFUSED: nobody is at the keyboard and --yes was not "
                  "given. Nothing was changed. Re-run with --yes.",
                  file=sys.stderr)
            return _finish(EXIT_REFUSED, "REFUSED",
                           "not interactive and --yes was not given")
        if _ask("  Proceed? [y/N]: ") != "y":
            print("  Aborted. Nothing was changed.", file=sys.stderr)
            return _finish(EXIT_REFUSED, "REFUSED", "declined at the prompt")

    store, registry = _make_store()
    result = execute_teardown(plan, store, registry_path=registry,
                              scopes=scopes)

    for step in result.steps:
        print(f"  done: {step}")
    if result.batches:
        print("\n  In the safedel trash (recover with "
              "`dz safedel recover <batch-name>`):")
        for name in result.batches:
            print(f"    {name}")

    if result.success:
        return _finish(EXIT_OK, "DONE", plan.worktree)

    for err in result.errors:
        print(f"  ERROR: {err}", file=sys.stderr)
    if result.steps:
        print("\n  STOPPED part-way. The steps marked done above were "
              "carried out; nothing after the failure was attempted.",
              file=sys.stderr)
        return _finish(EXIT_PARTIAL, "STOPPED",
                       result.errors[0] if result.errors else "a step failed")
    if result.refused:
        return _finish(EXIT_REFUSED, "REFUSED",
                       result.errors[0] if result.errors else "refused")
    return _finish(EXIT_ERROR, "ERROR",
                   result.errors[0] if result.errors else "failed")


if __name__ == "__main__":
    sys.exit(main())
