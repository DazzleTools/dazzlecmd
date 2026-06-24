#!/usr/bin/env python3
"""Tier 2 de-vendor migration: rename `preservelib` -> `dazzle_preservelib`.

safedel/_f_common used the vendored `preservelib` import (shadowed in via
safedel/_lib). De-vendoring switches to the published `dazzle-preservelib`
package, which imports as `dazzle_preservelib` and exposes every symbol the
call-sites use (copy_operation, move_operation, is_win32_available,
restore_windows_creation_time, _collect_unix_xattrs, _apply_unix_xattrs).

This is a case-sensitive rename, so PRESERVELIB_AVAILABLE (the sentinel
constant) is intentionally untouched. The shipped install-instruction error
message (separate personal-path fix) is handled by a follow-up edit, not here.
"""
import sys

CMD = "src/dazzlecmd/projects/core/safedel"
FCOMMON = "src/dazzlecmd/projects/core/_f_common"

# Files where every lowercase `preservelib` becomes `dazzle_preservelib`
RENAME_FILES = [
    f"{FCOMMON}/safe_ops.py",
    f"{FCOMMON}/__init__.py",
    f"{FCOMMON}/tests/test_safe_ops.py",
    f"{CMD}/tests/test_ctime.py",
    f"{CMD}/tests/test_xattr.py",
]

# Comment-only fixups: _lib no longer holds preservelib (it is a real dep now).
COMMENT_FIXUPS = [
    (f"{CMD}/tests/conftest.py", "for preservelib, log_lib", "for log_lib, help_lib"),
    (f"{CMD}/tests/one-offs/test_safedel_roundtrip.py", "_lib for preservelib, links",
     "_lib for log_lib, links"),
]

total = 0
for path in RENAME_FILES:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    n = text.count("preservelib")
    if n == 0:
        print(f"  WARN: {path} had no 'preservelib' to rename")
        continue
    text = text.replace("preservelib", "dazzle_preservelib")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    total += n
    print(f"  {path}: {n} 'preservelib' -> 'dazzle_preservelib'")

for path, old, new in COMMENT_FIXUPS:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"  skip (absent): {path}")
        continue
    if old in text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new))
        print(f"  {path}: comment fixup")
    else:
        print(f"  WARN: {path} missing comment {old!r}")

print(f"\nDONE: {total} occurrences renamed across {len(RENAME_FILES)} files.")
