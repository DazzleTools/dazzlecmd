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
"""

import argparse
import sys
from typing import List, Optional

from _classifier import classify, format_classification
from _store import TrashStore
from _platform import get_trash_dir
from _recover import cmd_list, cmd_recover, cmd_clean, cmd_status


SUBCOMMANDS = {"list", "ls", "recover", "restore", "clean", "purge", "status", "info"}


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
            "  dz safedel myfile.txt              Delete a file (stages to trash)\n"
            "  dz safedel -r mydir/               Delete a directory tree\n"
            "  dz safedel --dry-run myfile.txt     Show what would happen\n"
            "  dz safedel recover last             Recover most recent deletion\n"
            "  dz safedel recover today 10:4*      Recover by time pattern\n"
            "  dz safedel clean --age '>30d'       Clean old entries\n"
        ),
    )
    parser.add_argument("paths", nargs="+", help="Files or directories to delete")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Allow recursive directory deletion")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip interactive confirmation")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would happen without changes")
    parser.add_argument("--json", "-j", dest="json_output", action="store_true",
                        help="Output in JSON format")
    return parser


def _build_list_parser() -> argparse.ArgumentParser:
    """Parser for the list subcommand."""
    parser = argparse.ArgumentParser(prog="dz safedel list")
    parser.add_argument("time_args", nargs="*", default=[],
                        help="Time pattern (e.g., 'today', '2026-04-08 10:4*')")
    parser.add_argument("--contains", help="Search by filename in trash")
    parser.add_argument("--path", dest="path_pattern", help="Search by original path")
    parser.add_argument("--age", help="Filter by age (e.g., '>30d')")
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


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for safedel."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        _build_delete_parser().print_help()
        return 0

    store = TrashStore()

    # Check if first arg is a subcommand
    first = argv[0].lower()

    if first in ("list", "ls"):
        args = _build_list_parser().parse_args(argv[1:])
        return cmd_list(
            store,
            positional_args=args.time_args,
            contains=args.contains,
            path_pattern=args.path_pattern,
            age_filter=args.age,
            json_output=args.json_output,
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
        # Default: treat all args as a delete operation
        args = _build_delete_parser().parse_args(argv)
        return _do_delete(store, args)


def _do_delete(store: TrashStore, args: argparse.Namespace) -> int:
    """Execute the delete operation."""
    paths = args.paths
    dry_run = args.dry_run
    yes = args.yes

    if not paths:
        print("  No paths specified.", file=sys.stderr)
        return 1

    # Classify all paths first and show report
    from _classifier import classify, format_classification

    classifications = [classify(p) for p in paths]

    # Show what we're about to do
    print("\n  safedel: staging for deletion:\n")
    for c in classifications:
        print(format_classification(c))
        print()

    # Check for non-existent paths
    missing = [c for c in classifications if not c.exists]
    if missing:
        for c in missing:
            print(f"  WARNING: {c.path} does not exist", file=sys.stderr)

    existing = [c for c in classifications if c.exists]
    if not existing:
        print("  Nothing to delete.", file=sys.stderr)
        return 1

    if dry_run:
        print("  DRY RUN: No files were modified.")
        return 0

    # Interactive confirmation (unless --yes)
    if not yes:
        is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
        if is_tty:
            try:
                answer = input("  Proceed with deletion? [y/N]: ").strip().lower()
                if answer != "y":
                    print("  Aborted.")
                    return 0
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                return 0
        # Non-TTY without --yes: proceed (the safety is in the trash store)

    # Execute
    result = store.trash([c.path for c in existing])

    # Report
    if result.success:
        print(f"\n  Staged to trash: {result.folder_name}")
    else:
        print(f"\n  Staged with errors: {result.folder_name}", file=sys.stderr)

    for entry in result.entries:
        status = "OK" if entry.content_preserved else "metadata only"
        print(f"    {entry.original_name} ({entry.file_type}) [{status}]")

    if result.warnings:
        for w in result.warnings:
            print(f"  * {w}")

    if result.errors:
        for e in result.errors:
            print(f"  ERROR: {e}", file=sys.stderr)

    # Recovery instructions
    print(f"\n  To recover:  dz safedel recover last")
    print(f"  To list:     dz safedel list {result.folder_name[:10]}*")
    print(f"  Trash store: {store.store_path}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
