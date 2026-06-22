#!/usr/bin/env python3
"""
claude-recover-sesslogs - salvage the conversation logs of sessions that
worked in a now-missing path.

During the gitignore-era loss, many Claude Code sessions' main transcripts
(projects/<slug>/<uuid>.jsonl) were never committed -- but the logger's
channel files (.sesslog / .shell / .convo) often survive on disk under
~/.claude/sesslogs/. Those sessions are invisible to csb (it indexes by
main transcript, which is gone). This tool finds them by FOLDER AFFINITY
-- how heavily each session's channels mention the target path -- and
copies the survivors out to a recovery folder.

Validated manually 2026-06-19 against C:\\code\\Prime-Square-Sum (recovered
27 files / 4.9 MB across 7 sessions). See dazzlecmd#90.

Usage via dz:
    dz claude-recover-sesslogs C:\\code\\Prime-Square-Sum            # dry-run, ranked report
    dz claude-recover-sesslogs C:\\code\\Prime-Square-Sum --apply    # copy to <path>/private/old-sesslogs
    dz claude-recover-sesslogs <path> --apply --include-cross-refs   # also other-project sessions
    dz claude-recover-sesslogs <path> --threshold 50 --apply        # tighten the affinity cut

v0.1.0 scans the on-disk ~/.claude/sesslogs/ (incl. bak/ overflow). Pulling
git-history-only channel blobs (deleted from disk) is a planned follow-up
(dazzlecmd#90), built on csb's git_ops as a library.
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

CHANNEL_RE = re.compile(r"\.(sesslog|shell|convo)[^/\\]*\.log$", re.IGNORECASE)
# Session sesslog dir convention: <Name>__<uuid>_<USER>
_UUID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.IGNORECASE
)


def claude_dir() -> Path:
    """The Claude data directory, honoring relocation (matches csb / logger):
    CLAUDE_DIR > CLAUDE_CONFIG_DIR > ~/.claude."""
    env = os.environ.get("CLAUDE_DIR") or os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def affinity_pattern(target_path: str) -> re.Pattern:
    """Build a case-insensitive regex matching the target's basename in any
    separator/slug form. 'Prime-Square-Sum' -> matches 'Prime-Square-Sum',
    'prime-square-sum', the slug 'C--code-Prime-Square-Sum', etc."""
    base = os.path.basename(str(target_path).rstrip("/\\")) or str(target_path)
    tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", base) if t]
    if not tokens:
        return re.compile(re.escape(base), re.IGNORECASE)
    return re.compile(r"[^a-zA-Z0-9]+".join(re.escape(t) for t in tokens), re.IGNORECASE)


def _slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()


def count_mentions(path: Path, pat: re.Pattern) -> int:
    """Count lines in a channel file that mention the target (cheap, line-based)."""
    n = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if pat.search(line):
                    n += 1
    except OSError:
        return 0
    return n


def scan(sesslogs_root: Path, pat: re.Pattern):
    """Return {session_dir_name: {"dir": Path, "bak": Path|None, "files": [(Path,int)],
    "total": int}} for sessions whose channels mention the target."""
    sessions = {}
    if not sesslogs_root.is_dir():
        return sessions

    def consider(channel_file: Path, session_name: str, bak: bool):
        c = count_mentions(channel_file, pat)
        if c <= 0:
            return
        rec = sessions.setdefault(
            session_name,
            {"dir": sesslogs_root / session_name, "bak": None, "files": [], "total": 0},
        )
        rec["files"].append((channel_file, c, bak))
        rec["total"] += c

    for entry in sorted(sesslogs_root.iterdir()):
        if entry.name == "bak" and entry.is_dir():
            for sub in sorted(entry.iterdir()):
                if sub.is_dir():
                    for f in sub.iterdir():
                        if f.is_file() and CHANNEL_RE.search(f.name):
                            consider(f, sub.name, bak=True)
            continue
        if entry.is_dir():
            for f in entry.iterdir():
                if f.is_file() and CHANNEL_RE.search(f.name):
                    consider(f, entry.name, bak=False)
    return sessions


def classify(session_name: str, target_path: str) -> str:
    """'native' if the target's slug appears in the session dir name, else
    'cross-ref' (an other-project session that merely touched the path).

    Truncation-tolerant: the logger truncates long session dir names, so a
    combined session like '...and__prime-squa' (cut from 'prime-square-sum')
    is still recognized via a prefix of the target slug."""
    base_slug = _slugify(os.path.basename(str(target_path).rstrip("/\\")))
    if not base_slug:
        return "cross-ref"
    sess_slug = _slugify(session_name)
    if base_slug in sess_slug:
        return "native"
    # tolerate dir-name truncation: a >=10-char prefix of the target slug
    if len(base_slug) > 10 and base_slug[:10] in sess_slug:
        return "native"
    return "cross-ref"


def recover_session(rec, dest_dir: Path, dry_run: bool):
    """Copy a session's channel files (+ bak overflow) into dest_dir,
    preserving timestamps. Returns (n_files, n_bytes)."""
    n, total = 0, 0
    for f, _c, is_bak in rec["files"]:
        sub = dest_dir / ("bak" if is_bak else "")
        out = sub / f.name
        if not dry_run:
            sub.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out)  # copy2 preserves mtime/atime
        try:
            total += f.stat().st_size
        except OSError:
            pass
        n += 1
    return n, total


def _human(n: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.0f}T"


def write_manifest(dest_root: Path, recovered: list, target_path: str):
    lines = [
        "# Recovered sesslogs",
        "",
        f"Source path: `{target_path}`",
        f"Recovered from: `{claude_dir() / 'sesslogs'}` (on-disk channels)",
        "",
        "| session | uuid | tier | mentions | files | size |",
        "|---|---|---|---|---|---|",
    ]
    for r in recovered:
        m = _UUID_RE.search(r["name"])
        uuid = m.group(1) if m else "?"
        lines.append(
            f"| {r['name'][:48]} | {uuid[:8]} | {r['tier']} | {r['total']} | "
            f"{r['nfiles']} | {_human(r['bytes'])} |"
        )
    (dest_root / "manifest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="claude-recover-sesslogs",
        description="Salvage logger channels of sessions that worked in a now-missing path.",
    )
    p.add_argument("target_path", help="The project path whose sessions you want to recover")
    p.add_argument("--dest", default=None,
                   help="Recovery destination (default: <target>/private/old-sesslogs)")
    p.add_argument("--threshold", type=int, default=30,
                   help="Minimum path-mention count to include a session (default: 30)")
    p.add_argument("--include-cross-refs", action="store_true",
                   help="Also recover other-project sessions that touched the path "
                        "(into a _cross-project/ subfolder)")
    p.add_argument("--apply", action="store_true",
                   help="Actually copy files (default is a dry-run report)")
    p.add_argument("--verbose", "-v", action="store_true", help="Per-file detail")
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    target = args.target_path
    dest_root = Path(args.dest).expanduser() if args.dest \
        else Path(target).expanduser() / "private" / "old-sesslogs"
    pat = affinity_pattern(target)
    sesslogs_root = claude_dir() / "sesslogs"

    sessions = scan(sesslogs_root, pat)
    # rank by total mentions; drop sub-threshold
    ranked = sorted(
        ({"name": name, **rec} for name, rec in sessions.items() if rec.get("total", 0) >= args.threshold),
        key=lambda r: r["total"], reverse=True,
    )
    if not ranked:
        print(f"No sessions mention '{os.path.basename(target)}' >= {args.threshold} times "
              f"under {sesslogs_root}.")
        return 0

    dry = not args.apply
    print(f"{'[DRY-RUN] ' if dry else ''}recover '{os.path.basename(target)}' "
          f"-> {dest_root}\n")
    recovered = []
    for r in ranked:
        tier = classify(r["name"], target)
        if tier == "cross-ref" and not args.include_cross_refs:
            print(f"  skip (cross-ref, --include-cross-refs to keep): "
                  f"{r['total']:>5} mentions  {r['name'][:60]}")
            continue
        sub = "_cross-project/" if tier == "cross-ref" else ""
        dest_dir = dest_root / sub / r["name"]
        nfiles, nbytes = recover_session(r, dest_dir, dry)
        recovered.append({"name": r["name"], "tier": tier, "total": r["total"],
                          "nfiles": nfiles, "bytes": nbytes})
        print(f"  {tier:<9} {r['total']:>5} mentions  [{_human(nbytes)}, {nfiles}f]  {r['name'][:60]}")
        if args.verbose:
            for f, c, is_bak in sorted(r["files"], key=lambda x: -x[1]):
                print(f"        {c:>5}  {'bak/' if is_bak else ''}{f.name[:70]}")

    if not dry and recovered:
        write_manifest(dest_root, recovered, target)
        print(f"\nRecovered {len(recovered)} session(s) -> {dest_root} (+ manifest.md)")
    elif dry:
        print(f"\n{len(recovered)} session(s) would be recovered. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
