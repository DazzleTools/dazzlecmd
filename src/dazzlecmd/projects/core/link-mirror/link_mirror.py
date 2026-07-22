"""
link-mirror - Reconcile NTFS links between a source tree and a mirrored copy

After a file-level mirror (robocopy, Beyond Compare, preserve COPY) the
destination holds the regular files but frequently NOT the links: symlinks
and junctions are silently dropped and hardlink groups are materialized as
independent duplicate files. This tool scans the source for every link
object, diffs against the destination, and recreates what is missing --
same kind, verbatim target bytes (relative unresolved, broken unrepaired),
and the link's own creation/modified/accessed timestamps.

Safety posture (mirrors safedel's caution):
  - DRY-RUN by default: without --apply nothing is written, ever.
  - Additive only: existing entries are never modified; mismatches are
    reported as conflicts and left alone.
  - Hardlink reconciliation (the one destructive capability: replacing a
    duplicated file with a hardlink to its group canonical) is opt-in via
    --hardlinks recreate, sha256-guarded, and atomic.
  - Idempotent: re-running reports everything as satisfied.

This is the thin CLI over the engine ``dazzle_preservelib.linkmirror``
(the same engine/CLI split as the safedel and links tools): scanning,
diffing, creation, timestamp restoration, and verification all live in the
library; this file owns only dz-territory concerns -- argument parsing,
report display, exit codes.

Exit codes:
  0  nothing to do / apply+verify succeeded
  1  errors (creation failures, fidelity check failures, scan errors)
  2  pending work or conflicts found (dry-run with creates, or conflicts)
"""

import argparse
import json
import os
import sys


def _load_engine():
    """Import the engine lazily so --help works even without the library."""
    try:
        from dazzle_preservelib import linkmirror
        return linkmirror
    except ImportError as e:
        print(
            "Error: dazzle-preservelib is required for link-mirror "
            f"(import failed: {e})",
            file=sys.stderr,
        )
        return None


# -- Display --

def _safe(s):
    """Make a path/target printable on any console encoding.

    NTFS names can contain unpaired UTF-16 surrogates (carried through the
    engine via surrogatepass); printing those raises UnicodeEncodeError on
    both UTF-8 and codepage consoles. Escape only what the console cannot
    encode; normal Unicode passes through untouched.
    """
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        s.encode(enc)
        return s
    except UnicodeEncodeError:
        return s.encode(enc, "backslashreplace").decode(enc, "replace")


def _fmt_counts(counts):
    order = [
        "create", "satisfied", "conflict", "parent_missing",
        "excluded", "hardlink_report", "hardlink_link",
    ]
    parts = [f"{counts[k]} {k}" for k in order if counts.get(k)]
    return ", ".join(parts) if parts else "nothing to do"


def display_plan(plan, verbose=False):
    counts = plan.counts()
    print(f"  source: {plan.source_root}")
    print(f"  dest:   {plan.dest_root}")
    print(f"  plan:   {_fmt_counts(counts)}")
    if verbose or counts.get("conflict") or counts.get("parent_missing"):
        for item in plan.items:
            if item.action in ("satisfied",) and not verbose:
                continue
            if item.action == "create":
                print(f"    CREATE  [{item.record.kind}] "
                      f"{_safe(item.record.rel_path)} -> {_safe(item.target)}")
            elif item.action == "satisfied":
                print(f"    ok      [{item.record.kind}] {_safe(item.record.rel_path)}")
            elif item.action in ("conflict", "parent_missing"):
                print(f"    CONFLICT {_safe(item.record.rel_path)}: {_safe(item.detail)}")
            elif item.action == "excluded":
                print(f"    excluded {_safe(item.record.rel_path)}: {_safe(item.detail)}")
            elif item.action == "hardlink_report":
                print(f"    hardlink {_safe(item.detail)}")
            elif item.action == "hardlink_link":
                print(f"    HARDLINK {_safe(item.record.rel_path)} -> {_safe(item.target)}")


def display_result(result):
    label = "would create" if result.dry_run else "created"
    print(f"  {label}: {len(result.created)} link(s)")
    if result.hardlinked:
        label = "would hardlink" if result.dry_run else "hardlinked"
        print(f"  {label}: {len(result.hardlinked)} duplicate(s)")
    if result.skipped_satisfied:
        print(f"  already satisfied: {result.skipped_satisfied}")
    if result.parents_restored:
        print(f"  parent dir timestamps restored: {len(result.parents_restored)}")
    for c in result.conflicts:
        print(f"  CONFLICT: {_safe(c)}")
    for e in result.errors:
        print(f"  ERROR: {_safe(e)}")


def display_verify(report, verbose=False):
    status = "OK" if report.ok else "MISMATCH"
    print(f"  verify: {status} -- {report.satisfied}/{report.checked} "
          f"satisfied, {len(report.issues)} issue(s), "
          f"{report.excluded} excluded")
    for issue in report.issues:
        print(f"    {issue.problem.upper():<10} [{issue.kind}] "
              f"{_safe(issue.rel_path)}: {_safe(issue.detail)}")
    if verbose:
        for note in report.notes:
            print(f"  note: {note}")


# -- Scan backend selection --

def _scan(lm, args):
    """Run the chosen scanner backend, returning a LinkManifest."""
    include_hardlinks = args.hardlinks != "skip"
    skip = frozenset(args.skip or ())

    if args.load_manifest:
        with open(args.load_manifest, "r", encoding="utf-8") as f:
            return lm.LinkManifest.from_dict(json.load(f))

    backend = args.backend
    if backend in ("auto", "mft"):
        try:
            from dazzle_preservelib.linkmirror import mft
            if backend == "mft" or mft.is_mft_available(args.source):
                return mft.mft_scan(args.source, stat_confirm=include_hardlinks)
        except Exception as e:  # noqa: BLE001 - fall back to walk on any failure
            is_access = e.__class__.__name__ == "MftAccessDenied"
            if backend == "mft":
                print(f"Error: MFT scan failed: {e}", file=sys.stderr)
                if is_access:
                    print("Hint: the MFT backend requires an elevated console.",
                          file=sys.stderr)
                return None
            print(f"  (MFT backend unavailable, using walk: {e})")

    return lm.walk_scan(
        args.source, include_hardlinks=include_hardlinks, skip_rel_dirs=skip,
    )


# -- CLI --

def build_parser():
    parser = argparse.ArgumentParser(
        prog="dz link-mirror",
        description=(
            "Recreate links (symlinks/junctions/hardlink groups) that a "
            "file-level mirror dropped. Dry-run by default; --apply writes."
        ),
    )
    parser.add_argument("source", help="Source tree root (holds the links)")
    parser.add_argument("dest", help="Destination tree root (already holds the files)")
    parser.add_argument(
        "--apply", action="store_true",
        help="Create the missing links (default: dry-run report only)",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify source/destination link parity (runs after --apply if both given)",
    )
    parser.add_argument(
        "--backend", choices=["auto", "walk", "mft"], default="auto",
        help="Scanner backend (default auto: MFT when elevated+available, else walk)",
    )
    parser.add_argument(
        "--hardlinks", choices=["skip", "report", "recreate"], default="report",
        help=(
            "skip: don't scan for hardlinks (fastest); report (default): "
            "list groups, change nothing; recreate: replace destination "
            "duplicates with real hardlinks (sha256-guarded, needs --apply)"
        ),
    )
    parser.add_argument(
        "--rewrite-prefix", nargs=2, metavar=("OLD", "NEW"),
        help=(
            "Rewrite absolute link targets starting with OLD to NEW "
            "(e.g. --rewrite-prefix D:\\ B:\\). Default: verbatim targets."
        ),
    )
    parser.add_argument(
        "--skip", action="append", metavar="RELDIR",
        help="Source-relative directory to prune from the walk scan (repeatable)",
    )
    parser.add_argument(
        "--save-manifest", metavar="FILE",
        help="Write the scanned link manifest to FILE (JSON) for reuse/audit",
    )
    parser.add_argument(
        "--load-manifest", metavar="FILE",
        help="Skip scanning; load a manifest previously saved with --save-manifest",
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Machine-readable JSON output",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="List every plan item, including satisfied ones",
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    args = build_parser().parse_args(argv)

    lm = _load_engine()
    if lm is None:
        return 1

    if not os.path.isdir(args.source):
        print(f"Error: source is not a directory: {args.source}", file=sys.stderr)
        return 1
    if not os.path.isdir(args.dest):
        print(f"Error: dest is not a directory: {args.dest}", file=sys.stderr)
        return 1

    manifest = _scan(lm, args)
    if manifest is None:
        return 1

    if args.save_manifest:
        with open(args.save_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)
        print(f"  manifest saved: {args.save_manifest} "
              f"({len(manifest.records)} records)")

    policy = None
    if args.rewrite_prefix:
        policy = lm.make_prefix_rewrite_policy(*args.rewrite_prefix)

    hardlink_mode = "report" if args.hardlinks == "skip" else args.hardlinks
    plan = lm.build_plan(
        manifest, args.dest, target_policy=policy, hardlink_mode=hardlink_mode,
    )
    result = lm.apply_plan(plan, dry_run=not args.apply)

    report = None
    if args.verify:
        report = lm.verify_mirror(manifest, args.dest, target_policy=policy)

    if args.json_output:
        out = {
            "source": plan.source_root,
            "dest": plan.dest_root,
            "backend": manifest.backend,
            "scan_errors": manifest.errors,
            "plan": plan.counts(),
            "dry_run": result.dry_run,
            "created": result.created,
            "hardlinked": result.hardlinked,
            "conflicts": result.conflicts,
            "errors": result.errors,
        }
        if report is not None:
            out["verify"] = {
                "ok": report.ok,
                "satisfied": report.satisfied,
                "checked": report.checked,
                "issues": [
                    {"rel_path": i.rel_path, "kind": i.kind,
                     "problem": i.problem, "detail": i.detail}
                    for i in report.issues
                ],
                "notes": report.notes,
            }
        print(json.dumps(out, indent=2))
    else:
        display_plan(plan, verbose=args.verbose)
        display_result(result)
        if manifest.errors:
            print(f"  scan errors: {len(manifest.errors)} "
                  f"(first: {_safe(manifest.errors[0])})")
        if report is not None:
            display_verify(report, verbose=args.verbose)

    if result.errors or manifest.errors:
        return 1
    if report is not None and not report.ok:
        return 2
    if result.dry_run and (result.created or result.hardlinked):
        return 2
    if result.conflicts:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
