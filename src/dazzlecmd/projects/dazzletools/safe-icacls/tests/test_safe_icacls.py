"""
Tests for safe-icacls.

Two layers:

  * Pure-logic tests (cross-platform): argument splitting, path/ops
    extraction, /T removal, and main()'s passthrough-vs-safe routing with
    icacls mocked out.
  * Junction-pruning tests (Windows-only): build a REAL self-referential
    junction and assert safe_walk visits every object once and applies /L
    to the link WITHOUT descending into it (the whole point of the tool).

icacls itself is mocked everywhere (run_icacls / passthrough are
monkeypatched), so no test mutates a real ACL or requires elevation.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Locate the tool module without polluting sys.path globally.
_TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL_DIR))
import safe_icacls as si  # noqa: E402
sys.path.pop(0)

WIN = sys.platform == "win32"


# ---------------------------------------------------------------------------
# parse_args -- wrapper flags vs icacls passthrough
# ---------------------------------------------------------------------------

def test_parse_args_separates_wrapper_and_icacls():
    wa = si.parse_args([
        "C:\\dir", "/grant", "X:F", "/T", "/C",
        "--safe-dry-run", "--safe-verbose",
    ])
    assert wa.dry_run is True
    assert wa.verbose is True
    assert wa.icacls_args == ["C:\\dir", "/grant", "X:F", "/T", "/C"]


def test_parse_args_progress_value():
    wa = si.parse_args(["C:\\d", "/T", "--safe-progress", "50"])
    assert wa.progress == 50


def test_parse_args_progress_requires_int():
    with pytest.raises(SystemExit):
        si.parse_args(["C:\\d", "--safe-progress", "notanint"])


def test_parse_args_help_and_unsafe_and_dirs_only():
    wa = si.parse_args(["--help"])
    assert wa.help is True
    wa = si.parse_args(["C:\\d", "/T", "--unsafe", "--safe-dirs-only",
                        "--safe-skip-reparse"])
    assert wa.unsafe and wa.dirs_only and wa.skip_reparse


def test_parse_args_passes_unknown_tokens_through():
    # Anything not a recognized --safe-* / --unsafe / -h goes to icacls.
    wa = si.parse_args(["C:\\d", "/setowner", "Someone", "/inheritance:e"])
    assert wa.icacls_args == ["C:\\d", "/setowner", "Someone", "/inheritance:e"]


# ---------------------------------------------------------------------------
# split_path_and_ops -- path first, /T stripped, ops preserved
# ---------------------------------------------------------------------------

def test_split_path_and_ops_basic():
    path, ops = si.split_path_and_ops(
        ["C:\\dir", "/grant", "X:F", "/T", "/C"]
    )
    assert path == "C:\\dir"
    assert ops == ["/grant", "X:F", "/C"]   # /T removed, rest kept


def test_split_path_and_ops_strips_T_case_insensitive():
    _, ops = si.split_path_and_ops(["C:\\dir", "/grant", "X:F", "/t"])
    assert "/t" not in ops and "/T" not in ops


def test_split_path_and_ops_no_path():
    path, ops = si.split_path_and_ops(["/grant", "X:F"])
    assert path is None
    assert ops == ["/grant", "X:F"]


# ---------------------------------------------------------------------------
# main() routing -- passthrough vs safe walk (icacls mocked)
# ---------------------------------------------------------------------------

@pytest.fixture
def routing(monkeypatch):
    """Capture which dispatch path main() takes."""
    calls = {"passthrough": None, "safe_walk": None}

    monkeypatch.setattr(si, "find_icacls", lambda: "icacls")
    monkeypatch.setattr(
        si, "passthrough",
        lambda icacls, args: calls.__setitem__("passthrough", list(args)) or 0,
    )

    def fake_walk(icacls, path, ops, wa):
        calls["safe_walk"] = (path, list(ops))
        return si.Stats()

    monkeypatch.setattr(si, "safe_walk", fake_walk)
    return calls


def test_main_no_T_is_passthrough(routing):
    rc = si.main(["C:\\f.txt", "/grant", "X:R"])
    assert rc == 0
    assert routing["passthrough"] == ["C:\\f.txt", "/grant", "X:R"]
    assert routing["safe_walk"] is None


def test_main_T_uses_safe_walk(routing):
    rc = si.main(["C:\\dir", "/grant", "X:F", "/T"])
    assert rc == 0
    assert routing["safe_walk"] == ("C:\\dir", ["/grant", "X:F"])
    assert routing["passthrough"] is None


def test_main_unsafe_forces_passthrough_even_with_T(routing):
    si.main(["C:\\dir", "/grant", "X:F", "/T", "--unsafe"])
    assert routing["passthrough"] == ["C:\\dir", "/grant", "X:F", "/T"]
    assert routing["safe_walk"] is None


def test_main_save_with_T_falls_back_to_passthrough(routing, capsys):
    si.main(["C:\\dir", "/save", "acl.txt", "/T"])
    assert routing["safe_walk"] is None
    assert routing["passthrough"] is not None
    assert "cannot be decomposed" in capsys.readouterr().err


def test_main_help_prints_usage(capsys):
    rc = si.main(["--help"])
    assert rc == 0
    assert "loop-safe" in capsys.readouterr().out.lower()


def test_main_no_args_prints_help(capsys):
    rc = si.main([])
    assert rc == 0
    assert "WHY THIS EXISTS" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Junction pruning -- the core guarantee (Windows-only, real junction)
# ---------------------------------------------------------------------------

def _make_junction(link, target):
    """Create a real NTFS junction. Returns True on success."""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"New-Item -ItemType Junction -Path '{link}' -Target '{target}' "
         f"| Out-Null"],
        capture_output=True,
    )
    return r.returncode == 0 and os.path.exists(link)


@pytest.fixture
def junction_tree(tmp_path):
    """A tree with a self-referential junction: loop -> root."""
    root = tmp_path / "tree"
    (root / "sub1").mkdir(parents=True)
    (root / "sub2").mkdir()
    (root / "file1.txt").write_text("x")
    (root / "sub1" / "file2.txt").write_text("y")
    if not _make_junction(str(root / "loop"), str(root)):
        pytest.skip("could not create junction (needs Windows/NTFS)")
    return root


@pytest.mark.skipif(not WIN, reason="reparse points are a Windows concept")
def test_real_junction_is_detected(junction_tree):
    assert si.is_reparse(str(junction_tree / "loop")) is True
    assert si.is_reparse(str(junction_tree / "sub1")) is False


@pytest.mark.skipif(not WIN, reason="reparse points are a Windows concept")
def test_safe_walk_prunes_junction_and_visits_each_object_once(
    junction_tree, monkeypatch
):
    calls = []

    def record(icacls, target, ops, dry_run=False):
        calls.append((target, list(ops)))
        return 0, ""

    monkeypatch.setattr(si, "run_icacls", record)

    wa = si.parse_args([str(junction_tree), "--safe-progress", "0"])
    stats = si.safe_walk("icacls", str(junction_tree), ["/grant", "X:F"], wa)

    targets = [c[0] for c in calls]
    # Every real object visited exactly once.
    assert stats.dirs == 3 and stats.files == 2 and stats.reparse == 1
    assert targets.count(str(junction_tree)) == 1

    # The junction itself was touched, with /L, exactly once...
    loop = str(junction_tree / "loop")
    loop_calls = [c for c in calls if c[0] == loop]
    assert len(loop_calls) == 1
    assert any(o.lower() == "/l" for o in loop_calls[0][1])

    # ...and we NEVER descended into it (no loop\anything path). If we had
    # followed the junction this would recurse forever.
    assert not any(os.path.join(loop, "") in t or t.startswith(loop + os.sep)
                   for t in targets)


@pytest.mark.skipif(not WIN, reason="reparse points are a Windows concept")
def test_safe_walk_skip_reparse_omits_junction(junction_tree, monkeypatch):
    calls = []
    monkeypatch.setattr(
        si, "run_icacls",
        lambda i, t, o, dry_run=False: calls.append(t) or (0, ""),
    )
    wa = si.parse_args([str(junction_tree), "--safe-skip-reparse",
                        "--safe-progress", "0"])
    stats = si.safe_walk("icacls", str(junction_tree), ["/grant", "X:F"], wa)
    assert stats.reparse == 0
    assert str(junction_tree / "loop") not in calls


@pytest.mark.skipif(not WIN, reason="reparse points are a Windows concept")
def test_safe_walk_dirs_only_skips_files(junction_tree, monkeypatch):
    calls = []
    monkeypatch.setattr(
        si, "run_icacls",
        lambda i, t, o, dry_run=False: calls.append(t) or (0, ""),
    )
    wa = si.parse_args([str(junction_tree), "--safe-dirs-only",
                        "--safe-progress", "0"])
    stats = si.safe_walk("icacls", str(junction_tree), ["/grant", "X:F"], wa)
    assert stats.files == 0
    assert str(junction_tree / "file1.txt") not in calls
