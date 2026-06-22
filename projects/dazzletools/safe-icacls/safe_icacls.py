"""
safe-icacls (sicacls) - a loop-safe passthrough wrapper around Windows icacls.

WHY THIS EXISTS
---------------
`icacls <dir> /T ...` recurses into EVERY child, including reparse points
(junctions and symlinks). A user profile ships self-referential junctions --
the classic one is:

    C:\\Users\\<user>\\AppData\\Local\\Application Data  ->  ...\\AppData\\Local

so `icacls /T` walks ...\\Application Data\\Application Data\\Application Data\\...
forever. (`takeown /R` happens NOT to follow junctions, which is why it
finishes while icacls hangs.) The legacy compatibility junctions
(`My Documents`, `Local Settings`, `Cookies`, ...) are also ACL'd Everyone:Deny
by design, which is what makes File Explorer's "failed to enumerate objects
in the container" appear.

WHAT THIS DOES
--------------
safe-icacls is a TRANSPARENT passthrough: every normal icacls argument is
accepted and forwarded unchanged. The ONLY thing it changes is recursion.

  * No `/T` in the args      -> pure passthrough. icacls runs verbatim.
  * `/T` present             -> safe mode. We walk the tree ourselves in
                                Python, pruning reparse points (never
                                descending into a junction/symlink), and run
                                icacls per object WITHOUT `/T`. Reparse points
                                get the operation applied to the LINK itself
                                (`/L`) and are not followed.

This reproduces `/T` semantics (apply to the root and everything beneath it)
minus the one behavior that loops: following reparse points.

Wrapper-only flags are all prefixed `--safe-*` (plus `--unsafe`) so they can
never collide with icacls's `/`-style options:

  --safe-dry-run        Print the icacls commands that WOULD run; change nothing.
  --safe-verbose        Print every icacls invocation and its result.
  --safe-dirs-only      Apply only to directories (rely on (OI)(CI) inheritance
                        for files). Much faster for inheriting grants; NOT
                        sufficient for non-inheriting ops like /setowner.
  --safe-skip-reparse   Do not touch reparse points at all (default: apply /L
                        to the link object, best-effort).
  --safe-progress N     Emit a progress line every N objects (default 1000;
                        0 disables).
  --unsafe              Force pure passthrough even with /T (let native icacls
                        recurse -- may loop on junctions). Escape hatch.

EXAMPLES
--------
  # The original failing case -- now loop-safe:
  dz safe-icacls "C:\\Users\\localuser" /grant Administrators:(OI)(CI)F /T /C

  # Short alias, dry run first:
  dz sicacls "C:\\Users\\localuser" /setowner Extreme /T --safe-dry-run

  # Non-recursive call is an ordinary icacls passthrough:
  dz safe-icacls "C:\\path\\file.txt" /grant Users:R
"""

import os
import stat
import subprocess
import sys

REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

# Wrapper flags we consume; everything else is forwarded to icacls.
_BOOL_FLAGS = {
    "--safe-dry-run", "--safe-verbose", "--safe-dirs-only",
    "--safe-skip-reparse", "--unsafe", "-h", "--help",
}
_VALUE_FLAGS = {"--safe-progress"}


def find_icacls():
    """Return the path to icacls.exe, or None on non-Windows / not found."""
    import shutil
    return shutil.which("icacls")


def _decode(b):
    """Decode icacls bytes using the console codepage, never raising."""
    if not b:
        return ""
    enc = "mbcs" if sys.platform == "win32" else "utf-8"
    return b.decode(enc, errors="replace")


def is_reparse(path):
    """True if `path` is a reparse point (junction, symlink, or other)."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & REPARSE)


def _entry_is_reparse(entry):
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & REPARSE)


# -- argument parsing ---------------------------------------------------------

class WrapperArgs:
    def __init__(self):
        self.dry_run = False
        self.verbose = False
        self.dirs_only = False
        self.skip_reparse = False
        self.unsafe = False
        self.help = False
        self.progress = 1000
        self.icacls_args = []


def parse_args(argv):
    """Split argv into wrapper options and icacls passthrough args.

    Wrapper flags are distinctively `--safe-*` / `--unsafe` / `-h`; icacls
    never uses `--`, so the separation is unambiguous regardless of order.
    """
    wa = WrapperArgs()
    i = 0
    while i < len(argv):
        tok = argv[i]
        low = tok.lower()
        if low in _BOOL_FLAGS:
            if low in ("-h", "--help"):
                wa.help = True
            elif low == "--safe-dry-run":
                wa.dry_run = True
            elif low == "--safe-verbose":
                wa.verbose = True
            elif low == "--safe-dirs-only":
                wa.dirs_only = True
            elif low == "--safe-skip-reparse":
                wa.skip_reparse = True
            elif low == "--unsafe":
                wa.unsafe = True
        elif low in _VALUE_FLAGS:
            i += 1
            if i >= len(argv):
                raise SystemExit(f"error: {tok} requires a value")
            try:
                wa.progress = int(argv[i])
            except ValueError:
                raise SystemExit(f"error: {tok} value must be an integer")
        else:
            wa.icacls_args.append(tok)
        i += 1
    return wa


def split_path_and_ops(icacls_args):
    """Return (path, ops) where path is the first non-option token.

    icacls grammar puts the target name FIRST and options start with `/`,
    so the path can only be token 0. Checking only token 0 (rather than the
    first non-option token anywhere) avoids mistaking an option argument
    like `X:F` or `Someone` for the path when no real path precedes it.
    `ops` is every other token with any `/T` removed (we drive recursion).
    """
    path = None
    path_index = None
    if icacls_args and not icacls_args[0].startswith("/"):
        path = icacls_args[0]
        path_index = 0
    ops = [
        tok for idx, tok in enumerate(icacls_args)
        if idx != path_index and tok.lower() != "/t"
    ]
    return path, ops


# -- icacls invocation --------------------------------------------------------

def run_icacls(icacls, target, ops, dry_run=False):
    """Run `icacls <target> <ops...>`. Return (rc, combined_output)."""
    cmd = [icacls, target] + ops
    if dry_run:
        return 0, "DRYRUN " + subprocess.list2cmdline(cmd)
    try:
        proc = subprocess.run(cmd, capture_output=True)
    except OSError as exc:
        return 1, f"failed to launch icacls: {exc}"
    out = _decode(proc.stdout) + _decode(proc.stderr)
    return proc.returncode, out.strip()


def passthrough(icacls, icacls_args):
    """Run icacls verbatim, inheriting stdio. Return icacls's exit code."""
    try:
        return subprocess.run([icacls] + icacls_args).returncode
    except OSError as exc:
        print(f"error: could not run icacls: {exc}", file=sys.stderr)
        return 1


# -- safe recursive walk ------------------------------------------------------

class Stats:
    def __init__(self):
        self.dirs = 0
        self.files = 0
        self.reparse = 0
        self.errors = 0          # non-reparse object failures
        self.reparse_errors = 0  # reparse-point failures (often expected)


def _apply(icacls, target, ops, wa, stats, is_link=False, kind="dir"):
    """Apply ops to one object, recording stats and printing as configured."""
    use_ops = list(ops)
    if is_link and not any(o.lower() == "/l" for o in use_ops):
        use_ops.append("/L")
    rc, out = run_icacls(icacls, target, use_ops, dry_run=wa.dry_run)
    failed = rc != 0
    if wa.dry_run or wa.verbose:
        tag = "LINK" if is_link else kind.upper()
        print(f"[{tag}] {target}")
        if out and (wa.verbose or wa.dry_run):
            print(f"       {out}")
    if failed and not wa.dry_run:
        if is_link:
            stats.reparse_errors += 1
        else:
            stats.errors += 1
        if not wa.verbose:  # verbose already printed it
            print(f"  ! {target}: {out}", file=sys.stderr)


def safe_walk(icacls, path, ops, wa):
    """Walk `path` applying `ops` per object, never descending reparse points."""
    stats = Stats()

    # Root may itself be a reparse point.
    if is_reparse(path):
        if not wa.skip_reparse:
            _apply(icacls, path, ops, wa, stats, is_link=True)
            stats.reparse += 1
        else:
            print(f"  ~ skipped reparse root: {path}", file=sys.stderr)
        _summary(stats, wa)
        return stats

    if not os.path.isdir(path):
        # A single file (or wildcard / nonexistent). One object, no descent.
        _apply(icacls, path, ops, wa, stats, kind="file")
        stats.files += 1
        _summary(stats, wa)
        return stats

    stack = [path]
    processed = 0
    while stack:
        current = stack.pop()
        _apply(icacls, current, ops, wa, stats, kind="dir")
        stats.dirs += 1
        processed += 1
        if wa.progress and processed % wa.progress == 0:
            print(f"  ... {processed} objects (at {current})", file=sys.stderr)

        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            print(f"  ! cannot list {current}: {exc}", file=sys.stderr)
            stats.errors += 1
            continue

        for entry in entries:
            if _entry_is_reparse(entry):
                if wa.skip_reparse:
                    continue
                _apply(icacls, entry.path, ops, wa, stats, is_link=True)
                stats.reparse += 1
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            if is_dir:
                stack.append(entry.path)
            elif not wa.dirs_only:
                _apply(icacls, entry.path, ops, wa, stats, kind="file")
                stats.files += 1
                processed += 1

    _summary(stats, wa)
    return stats


def _summary(stats, wa):
    verb = "would process" if wa.dry_run else "processed"
    parts = [f"dirs={stats.dirs}", f"files={stats.files}",
             f"reparse={stats.reparse}"]
    if stats.errors:
        parts.append(f"errors={stats.errors}")
    if stats.reparse_errors:
        parts.append(f"reparse-skipped(denied)={stats.reparse_errors}")
    print(f"safe-icacls {verb}: " + "  ".join(parts), file=sys.stderr)


# -- help ---------------------------------------------------------------------

def print_help():
    print(__doc__.strip())


# -- entry point --------------------------------------------------------------

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    wa = parse_args(argv)

    if wa.help or not wa.icacls_args:
        print_help()
        return 0

    icacls = find_icacls()
    if not icacls:
        print("error: icacls not found. safe-icacls is Windows-only "
              "(icacls ships with Windows in System32).", file=sys.stderr)
        return 1

    recursive = any(a.lower() == "/t" for a in wa.icacls_args)

    # Pure passthrough paths.
    if wa.unsafe:
        if recursive:
            print("warning: --unsafe with /T runs native icacls recursion; "
                  "this may loop forever on self-referential junctions.",
                  file=sys.stderr)
        return passthrough(icacls, wa.icacls_args)
    if not recursive:
        return passthrough(icacls, wa.icacls_args)

    # /save and /restore use single-file semantics that per-object
    # decomposition would corrupt -- we cannot make them loop-safe by
    # splitting. Be honest and pass through with a warning.
    lowered = [a.lower() for a in wa.icacls_args]
    if "/save" in lowered or "/restore" in lowered:
        op = "/save" if "/save" in lowered else "/restore"
        print(f"warning: {op} with /T cannot be decomposed safely "
              f"(single-file ACL stream). Passing through to native icacls; "
              f"it may loop if the tree contains self-referential junctions. "
              f"Target a junction-free subtree to be safe.", file=sys.stderr)
        return passthrough(icacls, wa.icacls_args)

    # Safe recursive mode.
    path, ops = split_path_and_ops(wa.icacls_args)
    if path is None:
        print("error: no target path found. safe-icacls expects the path "
              "first, like icacls (e.g. safe-icacls C:\\dir /grant ... /T).",
              file=sys.stderr)
        return 1

    stats = safe_walk(icacls, path, ops, wa)
    return 1 if stats.errors else 0


if __name__ == "__main__":
    sys.exit(main())
