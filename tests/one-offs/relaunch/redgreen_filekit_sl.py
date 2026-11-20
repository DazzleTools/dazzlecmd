"""Red-green audit of filekit slice SL's new tests (dz relaunch goal).

For each behaviour revert: back up the source, apply the revert, run the new
test file, record which tests went red, restore, and verify the source is
byte-identical to the backup. Never touches anything but the two source files
(restored) and pytest's temp folders.

Run: python tests/one-offs/relaunch/redgreen_filekit_sl.py
"""
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(r"C:\code\filetoolkit\github")
TEST = "tests/test_locking_and_flavor_v053.py"

REVERTS = [
    ("try_lock always succeeds (Windows branch)", "dazzle_filekit/locking.py",
     "            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)\n            return True\n        except OSError:\n            return False",
     "            return True\n        except OSError:\n            return False"),
    ("try_lock POSIX treats busy as taken", "dazzle_filekit/locking.py",
     "    except (BlockingIOError, PermissionError):\n        return False",
     "    except (BlockingIOError, PermissionError):\n        return True"),
    ("deadline never raises", "dazzle_filekit/locking.py",
     "            if clock() >= deadline:\n                raise LockTimeoutError(",
     "            if False:\n                raise LockTimeoutError("),
    ("current_flavor always posix", "dazzle_filekit/portable.py",
     '    if compat.is_windows():\n        return "windows"\n    if compat.is_wsl():\n        return "wsl"\n    return "posix"',
     '    return "posix"'),
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_tests():
    r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider",
                        "--no-cov", "-o", "addopts=", "--timeout=60"],
                       cwd=REPO, capture_output=True, text=True, timeout=600)
    failed = [l.split("::", 1)[1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    return r.returncode, failed, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]


backup_dir = Path(tempfile.mkdtemp(prefix="redgreen_sl_"))
base_rc, base_failed, base_tail = run_tests()
print("baseline:", base_tail)
assert base_rc == 0, "baseline must be green"
for label, rel, old, new in REVERTS:
    src = REPO / rel
    bak = backup_dir / (rel.replace("/", "_"))
    shutil.copy2(src, bak)
    before = sha(src)
    text = src.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"anchor not unique for: {label}"
    src.write_text(text.replace(old, new), encoding="utf-8")
    try:
        rc, failed, tail = run_tests()
    finally:
        shutil.copy2(bak, src)
    assert sha(src) == before, f"source NOT restored after: {label}"
    print(f"[{'RED' if failed else 'still GREEN'}] {label}: {tail}")
    for f in failed:
        print("     red:", f)
print("all sources restored byte-for-byte; backups in", backup_dir)
