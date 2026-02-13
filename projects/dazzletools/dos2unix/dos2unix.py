"""
py-dos2unix: A pure‑Python, cross‑platform re‑implementation of the classic *dos2unix* / *unix2dos* utility.

Goals
-----
* Offer a drop‑in command‑line interface that mirrors the flags & behaviour of the original
  `dos2unix` package where practical.
* Work out‑of‑the‑box on CPython 3.8+ for Windows, macOS, and Linux.
* Depend **only** on the Python standard library.

Implemented flags
-----------------
Short | Long          | Description
------|---------------|------------------------------------------------------------
`-u`  | `--unix`      | Convert to Unix LF (default)
`-d`  | `--dos`       | Convert to DOS/Windows CRLF (alias `--win`)
`-m`  | `--mac`       | Convert to classic Mac CR
`-c`  | `--convmode`  | Explicitly set conversion mode (`unix`, `dos`, `mac`)
`-o`  | `--overwrite` | Write changes in‑place (default)
`-n`  | `--newfile`   | Convert *infile* → *outfile* (takes two paths)
`-b`  | `--backup`    | Keep a copy of the original file with `.bak` suffix
`-f`  | `--force`     | Force conversion of binary‑like files (skip otherwise)
`-k`  | `--keepdate`  | Preserve original modification timestamps
`-q`  | `--quiet`     | Suppress non‑fatal messages
`-h`  | `--help`      | Show help text

(See TODOs near the bottom for unimplemented `iconv` style encoding flags etc.)

Typical usage
-------------
```bash
# in‑place LF normalisation on multiple files
py dos2unix.py -u file1.txt file2.txt

# create CRLF versions, keep original timestamps, emit no output
dos2unix.py --dos --keepdate --quiet -o *.cfg

# convert stdin → stdout
cat readme.txt | python dos2unix.py -d - > win_readme.txt

# infile → outfile style (like `dos2unix -n in out`)
python dos2unix.py -n unix.txt windows.txt --dos
```

Licence: MIT
Author : Zag (ChatGPT‑o3, 2025‑04‑17)
"""

# ---------------------------------------------------------------------------
# TODO / roadmap
# ---------------------------------------------------------------------------
# * Implement character set conversion flags (-iso, -1252, etc.) using 'codecs'.
# * Add --info and --version parity.
# * Support recursive directory traversal (-r) and symlink handling like GNU dos2unix.
# * Binary‐safe streaming conversion for very large files.
# * Unit test suite (pytest) and pre‑commit hook.

import argparse
import os
import pathlib
import shutil
import stat
import sys
import tempfile
from datetime import datetime
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

CR = b"\r"
LF = b"\n"
CRLF = b"\r\n"


def is_binary(data: bytes) -> bool:
    """Return *True* if the given byte sequence looks like a binary file.

    Heuristic: presence of NUL bytes or a high ratio of non‑printables.
    """
    if not data:
        return False
    # NUL bytes almost always indicate binary
    if b"\x00" in data:
        return True
    # Rough printable ratio check on first 4 KiB
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x7F)))
    sample = data[:4096]
    non_printables = sum(ch not in text_chars for ch in sample)
    return non_printables / len(sample) > 0.30


def read_file(path: pathlib.Path) -> bytes:
    if path == pathlib.Path("-"):
        return sys.stdin.buffer.read()
    return path.read_bytes()


def write_file(path: pathlib.Path, data: bytes, keep_date: bool = False, ref_ts: Optional[float] = None):
    if path == pathlib.Path("-"):
        sys.stdout.buffer.write(data)
        return
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent))
    with os.fdopen(tmp_fd, "wb") as tmp:
        tmp.write(data)
    tmp_path = pathlib.Path(tmp_name)
    # keep permissions
    shutil.copymode(str(path), str(tmp_path), follow_symlinks=False) if path.exists() else None
    os.replace(tmp_path, path)
    if keep_date and ref_ts is not None:
        os.utime(path, (ref_ts, ref_ts))


def convert_line_endings(blob: bytes, mode: str) -> bytes:
    """Return *blob* with line endings converted according to *mode*.

    mode: 'unix'→LF, 'dos'→CRLF, 'mac'→CR
    """
    # Normalise to LF first
    blob = blob.replace(CRLF, LF).replace(CR, LF)
    if mode == "unix":
        return blob
    elif mode == "dos":
        return blob.replace(LF, CRLF)
    elif mode == "mac":
        return blob.replace(LF, CR)
    else:
        raise ValueError(f"Unknown conversion mode: {mode}")


def process_path(path: pathlib.Path, *, mode: str, overwrite: bool, new_out: Optional[pathlib.Path],
                 backup: bool, force: bool, keepdate: bool, quiet: bool):
    """Convert *path* according to CLI options."""
    if not quiet:
        print(f"{path} -> {('stdout' if new_out == pathlib.Path('-') else new_out) if new_out else path}")
    original_ts = path.stat().st_mtime if path.exists() else None

    # Read
    data = read_file(path)
    if not force and is_binary(data):
        if not quiet:
            print(f"Skipping binary file: {path}")
        return

    converted = convert_line_endings(data, mode)

    # Non‑destructive option ‑n infile outfile
    if new_out is not None:
        write_file(new_out, converted, keep_date=keepdate and original_ts is not None, ref_ts=original_ts)
        return

    # In‑place overwrite
    if backup and path != pathlib.Path("-"):
        shutil.copy2(path, f"{path}.bak")
    write_file(path, converted, keep_date=keepdate and original_ts is not None, ref_ts=original_ts)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dos2unix.py",
        description="Convert text files between DOS, Unix, and classic Mac line endings.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    conv_group = p.add_mutually_exclusive_group()
    conv_group.add_argument("-u", "--unix", dest="mode", action="store_const", const="unix",
                            help="convert to Unix (LF)")
    conv_group.add_argument("-d", "--dos", "--win", dest="mode", action="store_const", const="dos",
                            help="convert to DOS/Windows (CRLF)")
    conv_group.add_argument("-m", "--mac", dest="mode", action="store_const", const="mac",
                            help="convert to classic MacOS (CR)")

    p.add_argument("-c", "--convmode", dest="mode", choices=["unix", "dos", "mac"],
                   help="explicitly set conversion mode")

    io_group = p.add_mutually_exclusive_group()
    io_group.add_argument("-o", "--overwrite", action="store_true", default=True,
                          help="overwrite specified files (default)")
    io_group.add_argument("-n", "--newfile", nargs=2, metavar=("INFILE", "OUTFILE"),
                          help="convert INFILE and write result to OUTFILE")

    p.add_argument("files", nargs="*", metavar="FILE", help="files to process (use '-' for stdin/stdout)")
    p.add_argument("-b", "--backup", action="store_true", help="create .bak backup when overwriting")
    p.add_argument("-f", "--force", action="store_true", help="force convert binary files")
    p.add_argument("-k", "--keepdate", action="store_true", help="preserve original timestamps")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress informative messages")

    return p


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def main(argv: Iterable[str] | None = None):
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = build_parser()
    ns = parser.parse_args(argv)

    # Determine conversion mode
    mode = ns.mode or "unix"  # default same as classic dos2unix

    if ns.newfile:
        # single infile→outfile pair expected
        in_path, out_path = map(pathlib.Path, ns.newfile)
        process_path(in_path, mode=mode, overwrite=False, new_out=out_path, backup=False,
                     force=ns.force, keepdate=ns.keepdate, quiet=ns.quiet)
        return

    if not ns.files:
        parser.error("no input files specified (use '-' for stdin)")

    for file_arg in ns.files:
        path = pathlib.Path(file_arg)
        process_path(path, mode=mode, overwrite=True, new_out=None, backup=ns.backup,
                     force=ns.force, keepdate=ns.keepdate, quiet=ns.quiet)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Allow piping to `head` without traceback
        pass
