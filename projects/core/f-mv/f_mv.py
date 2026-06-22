"""dz f-mv: safe move with metadata preservation and clobber protection.

Argparse shim over _f_common.safe_ops.safe_mv. The shim's job is to
translate CLI flags into safe_mv's kwargs, render the OpResult as
text or JSON, and return the dz-convention exit code. All policy
decisions and safety invariants live in _f_common; the shim does
not get to weaken them.

Invocations:
    dz f-mv src.txt dst/                  Move src.txt into dst/ (refuse-to-clobber)
    dz f-mv -f src.txt existing.txt       Force overwrite
    dz f-mv -n src.txt existing.txt       Skip if dest exists
    dz f-mv --on-conflict newer s/ d/     Source-newer-wins
    dz f-mv --dry-run -v s/ d/            Show plan, no writes
    dz f-mv --json s/ d/                  Machine-readable result
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# Add projects/core/ to sys.path so _f_common (sibling dir) imports.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from _f_common.safe_ops import (  # noqa: E402
    ConflictPolicy,
    OpResult,
    safe_mv,
    EXIT_OK,
    EXIT_USER_ERROR,
)


# Status prefixes for text output. Plain ASCII -- Windows codepage 437
# and 1252 both render these without escapes. No em-dashes, no arrows.
STATUS_OK = "[OK]"
STATUS_FAIL = "[FAIL]"
STATUS_SKIP = "[SKIP]"
STATUS_WARN = "[WARN]"
STATUS_INFO = "[INFO]"
STATUS_DRY = "[DRY]"


def build_parser() -> argparse.ArgumentParser:
    """argparse setup. Surface is a v1 subset of design doc Section 5.

    The full surface (Section 5) includes --diff, --explain, --list-conflicts,
    -i/--interactive, --backup, --include/--exclude, -L/-P/-H, --link,
    --via-safedel, etc. Those land incrementally as features need them;
    the core flags below cover the safe-by-default + force-overwrite +
    dry-run + visibility use cases the user explicitly called out.
    """
    p = argparse.ArgumentParser(
        prog="dz f-mv",
        description=(
            "Safe move: hash verify BEFORE source deletion, refuse-to-clobber "
            "default, full metadata preservation (mtime/atime, ctime on "
            "Windows, ACLs, attributes). The verify step is the safety gate "
            "-- if the destination doesn't match the source hash, the source "
            "is preserved. There is no --no-verify on f-mv; this is intentional."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "What dz f-mv gives you over system mv / Windows move:\n"
            "  - Hash verify BEFORE source deletion: a botched copy never\n"
            "    costs you the source -- system mv on cross-volume can copy\n"
            "    + delete without verifying byte-for-byte\n"
            "  - ctime preservation on Windows: destination creation-time\n"
            "    matches source (system 'move' resets to now on cross-volume;\n"
            "    requires pywin32 -- warned if unavailable)\n"
            "  - Refuse-to-clobber: won't silently overwrite (use -f or\n"
            "    --on-conflict overwrite to opt in)\n"
            "  - Cross-platform: same flags + semantics on Windows and Linux\n"
            "  - Safe alternative to 'git stash' for metadata-sensitive files:\n"
            "    move files out of a workspace + back in without losing\n"
            "    atime/mtime/ctime (git stash destroys these on round-trip)\n"
            "\n"
            "Exit codes:\n"
            "  0  All operations succeeded\n"
            "  1  User error (bad args, mutually-exclusive flags)\n"
            "  2  System error (permission denied, disk full, etc.)\n"
            "  3  Verify failed; source preserved (the safety invariant)\n"
            "  4  Conflict detected with no policy to resolve it\n"
            "  5  Partial success\n"
            "  64 --dry-run noticed an issue (CI gating)\n"
            "\n"
            "Examples:\n"
            "  dz f-mv src.txt dst/                Move into dst/\n"
            "  dz f-mv src.txt newname.txt         Move with rename (POSIX-style)\n"
            "  dz f-mv -f src.txt existing.txt     Force overwrite\n"
            "  dz f-mv -n src.txt dst/             Skip if dest exists\n"
            "  dz f-mv --on-conflict newer s/ d/   Newer-source-wins\n"
            "  dz f-mv --dry-run -v s/ d/          Plan without writing\n"
            "  dz f-mv --json s/ d/                Machine-readable output\n"
        ),
    )

    # Positional sources and destination.
    p.add_argument("sources", nargs="+", help="Source file or directory paths")
    p.add_argument("dest", help="Destination path (file or directory)")

    # Conflict policy. The four shortcuts and explicit --on-conflict are
    # mutually exclusive; we enforce this after parsing because argparse
    # mutex groups don't compose well with positionals.
    p.add_argument(
        "--on-conflict",
        choices=[pol.value for pol in ConflictPolicy],
        default=None,
        help="How to handle existing destinations. Default: fail (refuse to clobber)",
    )
    p.add_argument(
        "-f", "--force",
        action="store_true",
        help="Shortcut for --on-conflict overwrite",
    )
    p.add_argument(
        "-n", "--no-clobber",
        action="store_true",
        help="Shortcut for --on-conflict skip",
    )

    # Recursion (for directory sources).
    p.add_argument(
        "-r", "-R", "--recursive",
        dest="recursive",
        action="store_true",
        help="Recurse into directory sources",
    )

    # Pre-flight and destination handling.
    p.add_argument(
        "--mkdir-p",
        action="store_true",
        help="Create missing destination directories",
    )

    # Hashing.
    p.add_argument(
        "--hash",
        choices=["SHA256", "SHA1", "MD5", "SHA512"],
        default="SHA256",
        help="Hash algorithm for verification. Default: SHA256",
    )

    # Visibility.
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan; perform no filesystem writes",
    )
    p.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (stackable: -v info, -vv debug)",
    )
    p.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-error output",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit results as JSON lines (one record per file)",
    )

    # NOTE: --verify / --no-verify is INTENTIONALLY ABSENT on f-mv.
    # safe_mv always verifies; verify is the gate for source deletion.
    # If the user wants unverified semantics, they use dz f-cp + manual
    # delete.

    return p


def resolve_policy(args) -> ConflictPolicy:
    """Translate -f / -n / --on-conflict into a single ConflictPolicy.

    Mutual exclusion is enforced here. argparse's add_mutually_exclusive_group
    would work for two flags, but combining three boolean shortcuts AND
    an explicit value flag is cleaner with manual logic.
    """
    flags_used = []
    if args.force:
        flags_used.append("-f/--force")
    if args.no_clobber:
        flags_used.append("-n/--no-clobber")
    if args.on_conflict is not None:
        flags_used.append("--on-conflict")

    if len(flags_used) > 1:
        raise ValueError(
            "Conflicting policy flags: " + ", ".join(flags_used) +
            ". Use only one of -f, -n, or --on-conflict."
        )

    if args.force:
        return ConflictPolicy.OVERWRITE
    if args.no_clobber:
        return ConflictPolicy.SKIP
    if args.on_conflict is not None:
        return ConflictPolicy(args.on_conflict)
    return ConflictPolicy.FAIL


def render_result_text(result: OpResult, verbose: int, quiet: bool) -> None:
    """Human-readable status output. Status prefix + one line per file."""
    if quiet and result.ok:
        return  # quiet mode suppresses all non-error output on success

    prefix_op = STATUS_DRY if result.dry_run else (STATUS_OK if result.ok else STATUS_FAIL)

    summary_parts = [f"processed={result.files_processed}"]
    if result.files_skipped:
        summary_parts.append(f"skipped={result.files_skipped}")
    if result.files_failed:
        summary_parts.append(f"failed={result.files_failed}")
    print(f"{prefix_op} dz f-mv  {' '.join(summary_parts)}  exit={result.exit_code}")

    # Honest reporting on every safety-relevant flag.
    if result.verify_failed:
        print(f"{STATUS_FAIL} verify failed -- source preserved (no deletion occurred)")
    if not result.ctime_restored:
        print(f"{STATUS_WARN} ctime not preserved on at least one file (pywin32 missing?)")
    if result.cross_device:
        print(f"{STATUS_INFO} cross-device move (copy + verify + delete)")
    if result.preflight_failed:
        print(f"{STATUS_FAIL} pre-flight check failed (space/permission/install)")

    if result.warnings and verbose >= 1:
        for w in result.warnings:
            print(f"{STATUS_WARN} {w}")

    if result.errors:
        for err in result.errors:
            print(f"{STATUS_FAIL} {err}", file=sys.stderr)


def render_result_json(result: OpResult) -> None:
    """Machine-readable output. One JSON object per call (not per-file in v1)."""
    record = {
        "tool": "dz f-mv",
        "ok": result.ok,
        "exit_code": result.exit_code,
        "files_processed": result.files_processed,
        "files_skipped": result.files_skipped,
        "files_failed": result.files_failed,
        "ctime_restored": result.ctime_restored,
        "cross_device": result.cross_device,
        "verify_failed": result.verify_failed,
        "preflight_failed": result.preflight_failed,
        "dry_run": result.dry_run,
        "errors": result.errors,
        "warnings": result.warnings,
    }
    print(json.dumps(record))


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for dz f-mv."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        policy = resolve_policy(args)
    except ValueError as exc:
        print(f"{STATUS_FAIL} {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    # mkdir-p handled inside safe_mv -- the adapter knows whether to
    # create dest itself (directory mode) or dest's parent (rename
    # mode) based on POSIX rename detection.
    result = safe_mv(
        sources=args.sources,
        dest=args.dest,
        policy=policy,
        dry_run=args.dry_run,
        hash_algorithm=args.hash,
        mkdir_p=args.mkdir_p,
    )

    if args.json:
        render_result_json(result)
    else:
        render_result_text(result, verbose=args.verbose, quiet=args.quiet)

    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
