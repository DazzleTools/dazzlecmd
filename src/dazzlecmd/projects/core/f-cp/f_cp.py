"""dz f-cp: safe copy with metadata preservation and clobber protection.

Argparse shim over _f_common.safe_ops.safe_cp. Mirror of f_mv.py, with
two differences: tool name is f-cp, and --verify / --no-verify is
exposed (copy has no source-deletion invariant, so disabling verify
is a legitimate caller choice, not a safety violation).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from _f_common.safe_ops import (  # noqa: E402
    ConflictPolicy,
    OpResult,
    safe_cp,
    EXIT_OK,
    EXIT_USER_ERROR,
)


STATUS_OK = "[OK]"
STATUS_FAIL = "[FAIL]"
STATUS_SKIP = "[SKIP]"
STATUS_WARN = "[WARN]"
STATUS_INFO = "[INFO]"
STATUS_DRY = "[DRY]"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dz f-cp",
        description=(
            "Safe copy with cryptographic hash verification, "
            "refuse-to-clobber default, and full metadata preservation "
            "(mtime/atime, ctime on Windows, ACLs, attributes). Use this "
            "when you want a verified clone -- system cp/copy/robocopy "
            "are faster and adequate for casual copies."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "What dz f-cp gives you over system cp / copy / robocopy:\n"
            "  - Hash verify (SHA256 default): proves the copy is byte-identical\n"
            "  - Refuse-to-clobber: won't silently overwrite (use -f or\n"
            "    --on-conflict overwrite to opt in)\n"
            "  - ctime preservation on Windows: destination creation-time\n"
            "    matches source (system 'copy' resets to now; requires pywin32,\n"
            "    warned if unavailable -- useful for true file cloning)\n"
            "  - Cross-platform: same flags + semantics on Windows and Linux\n"
            "  - Honest reporting: partial-preservation failures appear in\n"
            "    OpResult.warnings (e.g. ACL restore failed); ctime_restored\n"
            "    reflects whether ctime was actually preserved\n"
            "\n"
            "For casual copies, system cp / robocopy / Windows copy are\n"
            "faster and entirely adequate. Reach for dz f-cp when integrity\n"
            "matters: backups, archives, or cloning files where the\n"
            "destination must be indistinguishable from the source.\n"
            "\n"
            "Exit codes:\n"
            "  0  All operations succeeded\n"
            "  1  User error (bad args, mutually-exclusive flags)\n"
            "  2  System error (permission denied, disk full, etc.)\n"
            "  4  Conflict detected with no policy to resolve it\n"
            "  5  Partial success\n"
            "  64 --dry-run noticed an issue (CI gating)\n"
            "\n"
            "Examples:\n"
            "  dz f-cp src.txt dst/                Copy into dst/\n"
            "  dz f-cp src.txt newname.txt         Copy with rename (POSIX-style)\n"
            "  dz f-cp -f src.txt existing.txt     Force overwrite\n"
            "  dz f-cp -n src.txt dst/             Skip if dest exists\n"
            "  dz f-cp --on-conflict newer s/ d/   Newer-source-wins\n"
            "  dz f-cp --dry-run -v s/ d/          Plan without writing\n"
            "  dz f-cp --no-verify s/ d/           Skip hash verification (faster)\n"
        ),
    )

    p.add_argument("sources", nargs="+", help="Source file or directory paths")
    p.add_argument("dest", help="Destination path (file or directory)")

    p.add_argument(
        "--on-conflict",
        choices=[pol.value for pol in ConflictPolicy],
        default=None,
        help="How to handle existing destinations. Default: fail",
    )
    p.add_argument("-f", "--force", action="store_true",
                   help="Shortcut for --on-conflict overwrite")
    p.add_argument("-n", "--no-clobber", action="store_true",
                   help="Shortcut for --on-conflict skip")

    p.add_argument("-r", "-R", "--recursive", dest="recursive", action="store_true",
                   help="Recurse into directory sources")
    p.add_argument("--mkdir-p", action="store_true",
                   help="Create missing destination directories")

    # Verification: --no-verify is allowed on cp (no source-deletion invariant).
    p.add_argument("--no-verify", dest="verify", action="store_false", default=True,
                   help="Skip hash verification after copy (faster but unsafe)")
    p.add_argument("--hash", choices=["SHA256", "SHA1", "MD5", "SHA512"],
                   default="SHA256",
                   help="Hash algorithm for verification. Default: SHA256")

    p.add_argument("--dry-run", action="store_true",
                   help="Print plan; perform no filesystem writes")
    p.add_argument("-v", "--verbose", action="count", default=0,
                   help="Increase verbosity (stackable)")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="Suppress non-error output")
    p.add_argument("--json", action="store_true",
                   help="Emit results as JSON lines")

    return p


def resolve_policy(args) -> ConflictPolicy:
    """Translate -f / -n / --on-conflict into a single ConflictPolicy."""
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
    if quiet and result.ok:
        return

    prefix_op = STATUS_DRY if result.dry_run else (STATUS_OK if result.ok else STATUS_FAIL)

    summary_parts = [f"processed={result.files_processed}"]
    if result.files_skipped:
        summary_parts.append(f"skipped={result.files_skipped}")
    if result.files_failed:
        summary_parts.append(f"failed={result.files_failed}")
    print(f"{prefix_op} dz f-cp  {' '.join(summary_parts)}  exit={result.exit_code}")

    if result.verify_failed:
        print(f"{STATUS_FAIL} verify failed -- destination may be incomplete")
    if not result.ctime_restored:
        print(f"{STATUS_WARN} ctime not preserved on at least one file (pywin32 missing?)")
    if result.cross_device:
        print(f"{STATUS_INFO} cross-device copy")
    if result.preflight_failed:
        print(f"{STATUS_FAIL} pre-flight check failed (space/permission/install)")

    if result.warnings and verbose >= 1:
        for w in result.warnings:
            print(f"{STATUS_WARN} {w}")

    if result.errors:
        for err in result.errors:
            print(f"{STATUS_FAIL} {err}", file=sys.stderr)


def render_result_json(result: OpResult) -> None:
    record = {
        "tool": "dz f-cp",
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
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        policy = resolve_policy(args)
    except ValueError as exc:
        print(f"{STATUS_FAIL} {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    # mkdir-p handled inside safe_cp -- the adapter knows whether to
    # create dest itself (directory mode) or dest's parent (rename
    # mode) based on POSIX rename detection.
    result = safe_cp(
        sources=args.sources,
        dest=args.dest,
        policy=policy,
        verify=args.verify,
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
