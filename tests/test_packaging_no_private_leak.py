"""Regression guard: built distributions must not leak private/ docs or the wtf tree.

dazzlecmd's privacy guarantee for its PyPI artifacts is the clean-checkout build
(private/ and wtf are gitignored, so a fresh CI checkout lacks them). The enforcing
backstop is scripts/check_dist_no_leak.py, wired into the publish workflow. These
tests prove that backstop's logic is correct AND that an actual dev-tree build of
this project ships no private/ or wtf paths -- the regression that would have caught
both the bare-"*" MANIFEST.in bug (tools wiped) and the nested-private/ leak.
"""
import importlib.util
import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKER_PATH = _REPO_ROOT / "scripts" / "check_dist_no_leak.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_dist_no_leak", _CHECKER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


checker = _load_checker()


# --- unit: is_forbidden matches path *components*, not substrings -----------------

@pytest.mark.parametrize("member", [
    "pkg-1.0/src/dazzlecmd/projects/core/safedel/private/claude/notes.md",
    "pkg/private/x",
    "private/x",
    "a/b/c/d/e/private/deep/file.md",
    "pkg/src/dazzlecmd/projects/wtf/cli.py",
    "pkg/src/dazzlecmd/kits/wtf.kit.json",
])
def test_is_forbidden_flags_leaks(member):
    assert checker.is_forbidden(member) is not None


@pytest.mark.parametrize("member", [
    "pkg-1.0/src/dazzlecmd/projects/core/find/find.py",
    "pkg/src/dazzlecmd/aggregator.json",
    "pkg/src/dazzlecmd/projects/core/safedel/safedel.py",
    "pkg/privatematters/note.md",          # 'private' only as a substring of a component
    "pkg/src/dazzlecmd/projects/wtfx/tool.py",  # 'wtf' only as a substring
    "pkg/docs/what-the-format.md",
])
def test_is_forbidden_allows_clean_paths(member):
    assert checker.is_forbidden(member) is None


# --- unit: scan() over synthetic artifacts ---------------------------------------

def _make_tar(path, names):
    with tarfile.open(path, "w:gz") as tf:
        for name in names:
            data = b"x"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def _make_whl(path, names):
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, "x")


def test_scan_flags_leaky_sdist(tmp_path):
    tb = tmp_path / "pkg-1.0.tar.gz"
    _make_tar(tb, ["pkg-1.0/src/tool.py",
                   "pkg-1.0/src/projects/x/private/claude/notes.md"])
    bad = checker.scan(tb)
    assert len(bad) == 1
    assert "private" in bad[0][0]


def test_scan_passes_clean_wheel(tmp_path):
    wh = tmp_path / "pkg-1.0-py3-none-any.whl"
    _make_whl(wh, ["pkg/__init__.py", "pkg/aggregator.json", "pkg/projects/core/find/find.py"])
    assert checker.scan(wh) == []


def test_main_exit_codes(tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    _make_tar(clean / "ok-1.0.tar.gz", ["ok-1.0/src/tool.py"])
    assert checker.main(["prog", str(clean)]) == 0

    leaky = tmp_path / "leaky"
    leaky.mkdir()
    _make_tar(leaky / "bad-1.0.tar.gz", ["bad-1.0/x/private/secret.md"])
    assert checker.main(["prog", str(leaky)]) == 1

    empty = tmp_path / "empty"
    empty.mkdir()
    assert checker.main(["prog", str(empty)]) == 2


# --- integration: a real dev-tree build of THIS project must be clean -------------

@pytest.mark.skipif(importlib.util.find_spec("build") is None,
                    reason="`build` not installed; the publish workflow enforces this gate")
def test_dev_tree_sdist_has_no_leak(tmp_path):
    out = tmp_path / "dist"
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--no-isolation",
         "--outdir", str(out), str(_REPO_ROOT)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, "sdist build failed:\n%s\n%s" % (proc.stdout, proc.stderr)
    sdists = list(out.glob("*.tar.gz"))
    assert sdists, "no sdist produced"
    for s in sdists:
        leaks = checker.scan(s)
        assert leaks == [], "dev-tree sdist leaked %d path(s), e.g. %r" % (
            len(leaks), leaks[0][0] if leaks else None)
