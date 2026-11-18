"""
safedel - Safe file and directory deletion with recovery.

A link-aware, metadata-preserving deletion tool that stages files to a
managed trash store instead of permanently deleting them. Designed as a
safety net for both human users and LLM agents.

Usage:
    dz safedel <path> [<path>...]       Delete files/dirs (stage to trash)
    dz safedel list [pattern]           List trash contents
    dz safedel recover [pattern]        Recover from trash
    dz safedel clean [pattern]          Permanently delete trash entries
    dz safedel status                   Show trash store statistics

Time patterns:
    last                                Most recent deletion
    today                               Everything deleted today
    today 10:46                         Deletions at that minute
    2026-04-08 10:4*                    Wildcard time matching
    --age ">30d"                        By age threshold
    --contains foo.txt                  By filename in trash
    --path "*/projects/*"               By original path pattern

Protection zones (for clean):
    Zone A (blocked):    Cannot delete. Configurable, disabled by default.
    Zone B (< 48h):      Requires --force AND interactive Y/N.
    Zone C (48h-30d):    Interactive Y/N with warnings.
    Zone D (> 30d):      Interactive by default, --yes accepted.

Consent:
    Deleting asks first. At a console it prompts; anywhere else (a script,
    an agent, a pipe) it refuses unless --yes is given. --yes can carry
    scopes: --yes delete-through-junction, --yes copy-first, ...

Exit codes (the last line of output is always "safedel: <VERDICT> ..."):
    0  everything staged          3  refused -- nothing moved
    1  unexpected error           4  partial -- some staged, some not
    2  usage error                6  a post-condition check failed
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

# The recoverable-delete engine now lives in the lib (the constitutional
# core.safedel primitive); this tool provides the CLI + trash-management UX on
# top of it. Absolute lib imports work in this plain-script CLI.
from dazzlecmd_lib.core.safedel import (
    classify,
    format_classification,
    TrashStore,
    get_trash_dir,
    cmd_list,
    cmd_recover,
    cmd_clean,
    cmd_status,
)

# This command needs the engine's plan/execute API (dazzlecmd-lib 0.10.37,
# core.safedel API version 3). dazzlecmd and dazzlecmd-lib are separate
# packages and can be at different versions on one machine -- above all on a
# development box, where the dazzlecmd checkout is installed in editable mode
# (every saved edit is live) while dazzlecmd-lib is an ordinary installed
# copy. A released install cannot be in that state (the dependency floor
# requires the newer library). When it does happen, the command says what is
# wrong and changes nothing, instead of failing as an import error inside the
# dispatcher: see `_engine_too_old` and `main`.
#
# (From 0.12.25 to 0.12.26 an older engine ran the 0.12.24 command instead,
# kept as `_cli_0_12_24.py`. That path was counted when it was written -- one
# machine needed it, until the library was installed there -- and was removed
# in 0.12.27 once it was: 2026-11-18, dazzlecmd-lib 0.10.38a0. The old
# command is in git history at v0.12.24.)
try:
    from dazzlecmd_lib.core.safedel import (
        stdin_is_interactive,
        split_yes,
        ScopeError,
        SCOPES,
        copy_first_settings,
        parse_size,
        verdict_line,
        result_verdict,
        EXIT_OK,
        EXIT_ERROR,
        EXIT_USAGE,
        EXIT_REFUSED,
    )
    _ENGINE_IMPORT_ERROR = None
except ImportError as _exc:  # an engine older than 0.10.37
    _ENGINE_IMPORT_ERROR = _exc


def _engine_too_old() -> Optional[str]:
    """None when the engine has what this command needs, else why not."""
    if _ENGINE_IMPORT_ERROR is None:
        return None
    try:
        import dazzlecmd_lib
        found = getattr(dazzlecmd_lib, "__version__", "unknown version")
    except Exception:  # noqa: BLE001
        found = "unknown version"
    return (f"dazzlecmd-lib {found} is older than this safedel command "
            f"needs (0.10.37 or later)")

# Initialize log_lib from _lib/
_lib_dir = str(Path(__file__).parent / "_lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from log_lib import OutputManager, init_output, get_output
from dazzle_filekit.metadata import is_win32_available


SUBCOMMANDS = {"list", "ls", "recover", "restore", "clean", "purge", "status", "info"}


def _check_pywin32_startup_warning():
    """Emit a warning on Windows if pywin32 is missing.

    Without pywin32, safedel cannot restore creation time (ctime) on
    recovery, and security descriptor (ACL) restoration falls back to
    attrib-command parsing. Timestamps, file data, and permissions still
    work via stdlib, but advanced metadata is degraded.
    """
    if sys.platform == "win32" and not is_win32_available():
        print(
            "  [notice] pywin32 not installed -- creation time and ACL "
            "restoration will be skipped.\n"
            "           Install with: pip install pywin32",
            file=sys.stderr,
        )


def _build_delete_parser() -> argparse.ArgumentParser:
    """Parser for the default delete action."""
    parser = argparse.ArgumentParser(
        prog="dz safedel",
        description="Safe file/directory deletion with recovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Subcommands:\n"
            "  dz safedel list [pattern]         Show trash contents\n"
            "  dz safedel recover [pattern]       Recover from trash\n"
            "  dz safedel clean [pattern]         Permanently delete entries\n"
            "  dz safedel status                  Show trash statistics\n"
            "\nExamples:\n"
            "  dz safedel myfile.txt              Delete a file (asks first at a console)\n"
            "  dz safedel --yes mydir/            Delete without a prompt (scripts, agents)\n"
            "  dz safedel --dry-run myfile.txt     Show exactly what would happen\n"
            "  dz safedel recover last             Recover most recent deletion\n"
            "  dz safedel recover today 10:4*      Recover by time pattern\n"
            "  dz safedel clean --age '>30d'       Clean old entries\n"
            "\n--yes scopes (comma-separated; bare --yes means noninteractive):\n"
            "  noninteractive            do not prompt\n"
            "  delete-through-junction   also delete what a junction points at\n"
            "  delete-through-symlink    also delete what a symlink points at\n"
            "  copy-first                make a verified copy before moving\n"
            "  no-copy-first             stage without that copy\n"
            "  dangerous                 reserved for 'dz guarded'\n"
            "  A word after --yes is read as scopes only if every part is a\n"
            "  scope name; a file named like a scope is ./dangerous or after --.\n"
            "\nExit codes (the last output line is 'safedel: <VERDICT> ...'):\n"
            "  0 staged   1 error   2 usage   3 refused, nothing moved\n"
            "  4 partial  6 a post-condition check failed\n"
        ),
    )
    parser.add_argument("paths", nargs="+", help="Files or directories to delete")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Allow recursive directory deletion")
    # --yes is taken out of the arguments before argparse runs (its optional
    # value must never swallow a path); this entry exists for --help.
    parser.add_argument("--yes", "-y", nargs="?", metavar="SCOPES",
                        help="Consent to delete without a prompt; optional "
                             "comma-separated scopes (see below). Required "
                             "when nobody is at the keyboard")
    parser.add_argument("--copy-first-max", metavar="SIZE", default=None,
                        help="Largest batch copy-first will copy (e.g. 10MB, "
                             "1g); a larger batch is refused while copy-first "
                             "is on")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would happen without changes")
    parser.add_argument("--json", "-j", dest="json_output", action="store_true",
                        help="Output in JSON format")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase verbosity (-v, -vv)")
    parser.add_argument("-q", "--quiet", action="count", default=0,
                        help="Decrease verbosity (-q shortened, -qq minimal)")
    return parser


def _build_list_parser() -> argparse.ArgumentParser:
    """Parser for the list subcommand."""
    parser = argparse.ArgumentParser(prog="dz safedel list")
    parser.add_argument("time_args", nargs="*", default=[],
                        help="Time pattern (e.g., 'today', '2026-04-08 10:4*')")
    parser.add_argument("--contains", help="Search by filename in trash")
    parser.add_argument("--path", dest="path_pattern", help="Search by original path")
    parser.add_argument("--age", help="Filter by age (e.g., '>30d')")
    parser.add_argument("--count", type=int, default=10, metavar="N",
                        help="Show only the N most recent entries "
                             "(default 10; use 0 for all).")
    parser.add_argument("--all", action="store_true",
                        help="Show all entries (same as --count 0).")
    parser.add_argument("--json", "-j", dest="json_output", action="store_true")
    return parser


def _build_recover_parser() -> argparse.ArgumentParser:
    """Parser for the recover subcommand."""
    parser = argparse.ArgumentParser(prog="dz safedel recover")
    parser.add_argument("time_args", nargs="*", default=[],
                        help="Time pattern (e.g., 'last', 'today 10:46')")
    parser.add_argument("--contains", help="Search by filename")
    parser.add_argument("--path", dest="path_pattern", help="Search by original path")
    parser.add_argument("--to", dest="to_path", help="Recover to alternate location")
    parser.add_argument("--metadata-only", action="store_true",
                        help="Apply metadata without overwriting content")
    parser.add_argument("--dry-run", "-n", action="store_true")
    return parser


def _build_clean_parser() -> argparse.ArgumentParser:
    """Parser for the clean subcommand."""
    parser = argparse.ArgumentParser(prog="dz safedel clean")
    parser.add_argument("time_args", nargs="*", default=[],
                        help="Time pattern for entries to clean")
    parser.add_argument("--age", help="Filter by age (e.g., '>30d')")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Required for Zone B (< 48h) entries")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip prompt (Zone D only)")
    parser.add_argument("-q", "--quiet", action="count", default=0,
                        help="Reduce warnings (-q shortened, -qq minimal)")
    return parser


def _init_output(verbose: int = 0, quiet: int = 0) -> OutputManager:
    """Initialize the OutputManager singleton with THAC0 verbosity.

    THAC0 mapping:
        -qq (-2): minimal output (just prompts)
        -q  (-1): shortened warnings
         0      : default (full warnings + metadata reminders)
        -v  (1) : timing and config details
        -vv (2) : debug output
    """
    verbosity = verbose - quiet
    return init_output(verbosity=verbosity)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for safedel."""
    if argv is None:
        argv = sys.argv[1:]

    too_old = _engine_too_old()
    if too_old:
        # Say what is wrong and change nothing (see the note at the imports).
        print(f"  safedel: {too_old}. Nothing was changed. Install the "
              f"matching library: pip install -U dazzlecmd-lib",
              file=sys.stderr)
        print("safedel: ERROR dazzlecmd-lib is too old")
        return 1

    if not argv:
        _build_delete_parser().print_help()
        return 0

    store = TrashStore()

    # Check if first arg is a subcommand
    first = argv[0].lower()

    if first in ("list", "ls"):
        args = _build_list_parser().parse_args(argv[1:])
        # --all is shorthand for "no limit"; otherwise honor --count (default 10).
        count = 0 if args.all else args.count
        return cmd_list(
            store,
            positional_args=args.time_args,
            contains=args.contains,
            path_pattern=args.path_pattern,
            age_filter=args.age,
            json_output=args.json_output,
            count=count,
        )

    elif first in ("recover", "restore"):
        args = _build_recover_parser().parse_args(argv[1:])
        return cmd_recover(
            store,
            positional_args=args.time_args,
            contains=args.contains,
            path_pattern=args.path_pattern,
            to_path=args.to_path,
            metadata_only=args.metadata_only,
            dry_run=args.dry_run,
        )

    elif first in ("clean", "purge"):
        args = _build_clean_parser().parse_args(argv[1:])
        _init_output(quiet=args.quiet)
        return cmd_clean(
            store,
            positional_args=args.time_args,
            age_filter=args.age,
            force=args.force,
            yes=args.yes,
            verbosity=args.quiet,
        )

    elif first in ("status", "info"):
        return cmd_status(store)

    else:
        # Default: treat all args as a delete operation.
        # --yes (and its optional scope list) comes out first, so its value
        # can never be mistaken for a path, nor a path for its value.
        try:
            argv, scopes, yes_given = split_yes(argv)
        except ScopeError as exc:
            print(f"  safedel: {exc}", file=sys.stderr)
            print(verdict_line("safedel", "USAGE", str(exc)))
            return EXIT_USAGE
        args = _build_delete_parser().parse_args(argv)
        _init_output(
            verbose=getattr(args, "verbose", 0),
            quiet=getattr(args, "quiet", 0),
        )
        json_output = getattr(args, "json_output", False)
        try:
            return _do_delete(store, args, scopes, yes_given)
        except Exception as exc:  # noqa: BLE001
            # Whatever went wrong, the caller still gets a truthful last
            # line and a non-zero code -- never a silent 0.
            import traceback
            traceback.print_exc()
            return _finish(EXIT_ERROR, "ERROR",
                           f"{type(exc).__name__}: {exc}", json_output)


def _finish(code: int, outcome: str, detail: str, json_output: bool,
            payload: Optional[dict] = None) -> int:
    """The one way the delete action ends: the verdict, then the code.

    Text mode: the verdict is the LAST line on stdout, so a caller who reads
    only the tail of the output still sees what happened. JSON mode: the
    same facts are fields of the one JSON object (a trailing text line
    would make the output unparseable).
    """
    line = verdict_line("safedel", outcome, detail)
    if json_output:
        import json
        out = dict(payload or {})
        out["verdict"] = line
        out["exit_code"] = code
        print(json.dumps(out, indent=2, default=str))
    else:
        sys.stderr.flush()
        print(line)
    sys.stdout.flush()
    return code


def _ask(prompt: str) -> Optional[str]:
    """Ask on stderr (so ``dz safedel x > log`` still shows the question) and
    read one line from stdin. None when no answer can be read."""
    try:
        sys.stderr.write(prompt)
        sys.stderr.flush()
        return input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\n")
        return None


def _do_delete(store: TrashStore, args: argparse.Namespace,
               scopes=(), yes_given: bool = False) -> int:
    """Plan the delete, show the plan, get consent, perform it, report."""
    paths = args.paths
    dry_run = args.dry_run
    json_output = getattr(args, "json_output", False)

    if not paths:
        print("  No paths specified.", file=sys.stderr)
        return _finish(EXIT_USAGE, "USAGE", "no paths given", json_output)

    interactive = stdin_is_interactive()

    # Copy-first: forced on or off by a scope, else by the configured mode.
    mode, max_bytes = copy_first_settings()
    if args.copy_first_max is not None:
        try:
            max_bytes = parse_size(args.copy_first_max)
        except ValueError:
            msg = f"--copy-first-max: not a size: {args.copy_first_max!r}"
            print(f"  safedel: {msg}", file=sys.stderr)
            return _finish(EXIT_USAGE, "USAGE", msg, json_output)
    if "no-copy-first" in scopes:
        use_copy_first = False
    elif "copy-first" in scopes:
        use_copy_first = True
    else:
        use_copy_first = (mode == "always"
                          or (mode == "auto" and not interactive))

    plan = store.plan(paths, scopes=scopes, copy_first=use_copy_first,
                      copy_first_max=max_bytes)

    # The preview IS the plan the real run will perform.
    if not json_output:
        if plan.refused:
            # Say so BEFORE the list, so nobody reads "move into the trash"
            # below as something that is about to happen.
            print("\n  safedel: REFUSED -- nothing will be moved. "
                  "This is what was asked for:\n")
        else:
            print("\n  safedel: this will happen:\n")
        for line in plan.describe():
            print(line)
        for w in plan.warnings:
            print(f"  * {w}")
        for c in (i.classification for i in plan.items):
            for w in c.warnings:
                print(f"  * {w}")
        print()

    payload = {
        "success": False,
        "dry_run": bool(dry_run),
        "scopes": list(scopes),
        "copy_first": bool(plan.copy_first),
        "trash_store": plan.store_path,
        "planned": [
            {"path": i.path, "kind": i.classification.file_type.value,
             "action": i.action, "copy_first": i.copy_first,
             "link_target": i.classification.link_target,
             "via_link": i.via_link}
            for i in plan.items
        ],
        "missing": list(plan.missing),
        "refusals": list(plan.refusals),
        "warnings": list(plan.warnings),
        "errors": [],
    }

    if plan.refused:
        sys.stdout.flush()    # the list above first, then the reasons
        for reason in plan.refusals:
            print(f"  REFUSED: {reason}", file=sys.stderr)
        payload["errors"] = list(plan.refusals)
        return _finish(EXIT_REFUSED, "REFUSED", plan.refusals[0],
                       json_output, payload)

    if dry_run:
        if not json_output:
            print("  DRY RUN: nothing was changed.")
        payload["success"] = True
        detail = f"{len(plan.items)} would be staged"
        if plan.missing:
            detail += f", {len(plan.missing)} missing"
        return _finish(EXIT_OK, "DRY-RUN", detail, json_output, payload)

    # Consent. --yes is required unless a person is at the keyboard to ask.
    if not yes_given:
        if not interactive or json_output:
            why = ("nobody is at the keyboard" if not interactive
                   else "--json cannot prompt")
            print(f"  REFUSED: {why} and --yes was not given. Nothing was "
                  f"moved. Re-run with --yes to delete.", file=sys.stderr)
            return _finish(EXIT_REFUSED, "REFUSED",
                           "not interactive and --yes was not given",
                           json_output, payload)
        answer = _ask("  Proceed with deletion? [y/N]: ")
        if answer != "y":
            print("  Aborted. Nothing was moved.", file=sys.stderr)
            return _finish(EXIT_REFUSED, "REFUSED", "declined at the prompt",
                           json_output, payload)

    # Execute exactly the plan that was shown.
    result = store.execute(plan)
    code, outcome, detail = result_verdict(result)

    payload.update({
        "success": result.success,
        "folder_name": result.folder_name,
        "folder_path": result.folder_path,
        "entries": [
            {
                "original_path": e.original_path,
                "original_name": e.original_name,
                "file_type": e.file_type,
                "link_target": e.link_target,
                "content_preserved": e.content_preserved,
                "copy_first": e.copy_first,
                "status": _entry_status(e),
            }
            for e in result.entries
        ],
        "staged": result.staged_count,
        "not_staged": result.not_staged_count,
        "postcondition_failures": list(result.postcondition_failures),
        "warnings": result.warnings,
        "errors": result.errors,
        "recover_command": (f"dz safedel recover {result.folder_name}"
                            if result.folder_name else None),
    })

    if not json_output:
        _print_delete_report(result)
    return _finish(code, outcome, detail, json_output, payload)


def _entry_status(entry) -> str:
    """Report label for one entry of a finished batch.

    Says what actually happened, not what the classifier thought could
    happen: an item that was refused (for example, a second item with the
    same name in one call) has no content_path and stays where it was.
    """
    if not entry.content_preserved:
        return "metadata only"          # links: the target is recorded
    if entry.content_path:
        return "OK"
    return "NOT staged -- left in place"


def _print_delete_report(result) -> None:
    """Print the human-readable report for a finished delete batch."""
    if result.success:
        print(f"\n  Staged to trash: {result.folder_name}")
    else:
        print(f"\n  Staged with errors: {result.folder_name}", file=sys.stderr)

    for entry in result.entries:
        print(f"    {entry.original_name} ({entry.file_type}) "
              f"[{_entry_status(entry)}]")

    if result.warnings:
        for w in result.warnings:
            print(f"  * {w}")

    if result.errors:
        for e in result.errors:
            print(f"  ERROR: {e}", file=sys.stderr)

    if result.postcondition_failures:
        print("\n  CHECK FAILED -- the disk is not in the state reported "
              "above:", file=sys.stderr)
        for f in result.postcondition_failures:
            print(f"    {f}", file=sys.stderr)

    copied = [e for e in result.entries if e.copy_first]
    if copied:
        print(f"\n  Copy-first: {len(copied)} item(s) also have a verified "
              f"copy (SHA-256 of content; the copy's own timestamps are new) "
              f"under {os.path.join(result.folder_path, 'copy-first')}")

    # Recovery instructions name THIS batch: "last" can be another session's
    # deletion. The store is the one this batch actually went to (often the
    # per-volume store), not the central default.
    print(f"\n  To recover:  dz safedel recover {result.folder_name}")
    print(f"  To list:     dz safedel list {result.folder_name[:10]}*")
    print(f"  Trash store: {os.path.dirname(result.folder_path)}")


if __name__ == "__main__":
    sys.exit(main())
