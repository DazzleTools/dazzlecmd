"""Tests for the link-mirror CLI (thin argparse layer over
dazzle_preservelib.linkmirror -- the engine has its own suite there).

Covers dz-territory concerns only: argument handling, exit codes
(0 nothing-to-do/success, 1 error, 2 pending/conflicts), display and JSON
output, and the dry-run-by-default contract.
"""

import json
import os
import platform
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from link_mirror import main  # noqa: E402

IS_WINDOWS = platform.system() == "Windows"


def _symlinks_available(tmp_path):
    t = tmp_path / "_probe_t.txt"
    t.write_text("x", encoding="utf-8")
    try:
        os.symlink(str(t), str(tmp_path / "_probe_l"))
    except (OSError, NotImplementedError):
        return False
    os.unlink(str(tmp_path / "_probe_l"))
    return True


@pytest.fixture()
def trees(tmp_path):
    if not _symlinks_available(tmp_path):
        pytest.skip("symlink creation not permitted")
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    for b in (src, dst):
        (b / "data").mkdir(parents=True)
        (b / "data" / "file.txt").write_text("payload", encoding="utf-8")
        (b / "links").mkdir()
    sep = "\\" if IS_WINDOWS else "/"
    os.symlink(f"..{sep}data{sep}file.txt", str(src / "links" / "rel_link"))
    os.symlink(f"data{sep}missing.txt", str(src / "links" / "broken_link"))
    return src, dst


def test_missing_dirs_error():
    assert main(["Z:\\no\\such\\src" if IS_WINDOWS else "/no/such/src",
                 "Z:\\no\\such\\dst" if IS_WINDOWS else "/no/such/dst"]) == 1


def test_dry_run_default_exit_2_and_no_writes(trees, capsys):
    src, dst = trees
    rc = main([str(src), str(dst)])
    out = capsys.readouterr().out
    assert rc == 2  # pending work found
    assert "would create: 2" in out
    assert not os.path.lexists(str(dst / "links" / "rel_link"))


def test_apply_then_idempotent_exit_0(trees, capsys):
    src, dst = trees
    assert main([str(src), str(dst), "--apply"]) == 0
    assert os.path.lexists(str(dst / "links" / "rel_link"))
    assert os.path.lexists(str(dst / "links" / "broken_link"))
    capsys.readouterr()
    rc = main([str(src), str(dst)])  # second dry-run: nothing pending
    out = capsys.readouterr().out
    assert rc == 0
    assert "already satisfied: 2" in out


def test_verify_after_apply_ok(trees, capsys):
    src, dst = trees
    assert main([str(src), str(dst), "--apply", "--verify"]) == 0
    out = capsys.readouterr().out
    assert "verify: OK" in out


def test_conflict_reported_untouched_exit_2(trees, capsys):
    src, dst = trees
    os.symlink("wrong", str(dst / "links" / "rel_link"))
    rc = main([str(src), str(dst), "--apply"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "CONFLICT" in out
    assert os.readlink(str(dst / "links" / "rel_link")) == "wrong"


def test_json_output_shape(trees, capsys):
    src, dst = trees
    rc = main([str(src), str(dst), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert data["dry_run"] is True
    assert data["plan"]["create"] == 2
    assert data["backend"] == "walk"
    assert data["errors"] == []


def test_save_and_load_manifest_roundtrip(trees, tmp_path, capsys):
    src, dst = trees
    mf = tmp_path / "manifest.json"
    assert main([str(src), str(dst), "--save-manifest", str(mf)]) == 2
    capsys.readouterr()
    rc = main([str(src), str(dst), "--load-manifest", str(mf), "--apply"])
    assert rc == 0
    assert os.path.lexists(str(dst / "links" / "rel_link"))


def test_rewrite_prefix_policy_applied(trees, capsys):
    src, dst = trees
    # absolute link whose target starts with the source root
    os.symlink(str(src / "data" / "file.txt"), str(src / "links" / "abs_link"))
    rc = main([
        str(src), str(dst), "--apply",
        "--rewrite-prefix", str(src), str(dst),
    ])
    assert rc == 0
    stored = os.readlink(str(dst / "links" / "abs_link"))
    assert str(dst) in stored
    assert str(src) not in stored.replace(str(dst), "")
