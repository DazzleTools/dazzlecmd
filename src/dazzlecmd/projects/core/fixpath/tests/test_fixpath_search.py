"""
Tests for fixpath's search pipeline and on-disk casing.

Pins the contract fixed in v0.12.22:
  - Everything (es.exe) queries are scoped server-side with -path, so the
    -n result cap cannot drop a local match that ranks past it globally.
  - A scoped Everything query that finds nothing returns None (letting fd
    run) instead of substituting results from elsewhere on the drive.
  - Local tiers run first; a drive-wide Everything search is a last resort,
    only with no --search-on / --dir, and it is announced on stderr.
  - fix_path returns an existing path in its on-disk casing.

No test touches the real es.exe, fd, or Everything index: subprocess.run and
the search helpers are replaced with fakes, and every action that could open,
copy, or browse a file is patched to raise.
"""

import fnmatch
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL_DIR))
import fixpath as fp  # noqa: E402
sys.path.pop(0)


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    """Structural safety: no test may open, browse, or copy a real file."""
    def _refuse(*_a, **_k):
        raise AssertionError("test attempted a real file action")
    monkeypatch.setattr(fp, "action_open", _refuse)
    monkeypatch.setattr(fp, "action_lister", _refuse)
    monkeypatch.setattr(fp, "action_copy", _refuse)


# ---------------------------------------------------------------------------
# A fake es.exe: a global index with Everything's semantics for -n and -path
# ---------------------------------------------------------------------------

class FakeEverything:
    """Emulates es.exe: filename glob match over a global index, -path
    filtering BEFORE the -n cap (as the real tool does), and a record of
    every command line it received."""

    def __init__(self, index):
        self.index = list(index)
        self.calls = []

    def run(self, cmd, **_kwargs):
        self.calls.append(list(cmd))
        args = cmd[1:]
        cap, scope, query = None, None, None
        i = 0
        while i < len(args):
            if args[i] == "-n":
                cap = int(args[i + 1]); i += 2
            elif args[i] == "-path":
                scope = args[i + 1]; i += 2
            else:
                query = args[i]; i += 1
        hits = [p for p in self.index
                if fnmatch.fnmatch(os.path.basename(p).lower(), query.lower())]
        if scope:
            prefix = scope.rstrip("\\/").lower() + "\\"
            hits = [p for p in hits if p.lower().startswith(prefix)]
        if cap:
            hits = hits[:cap]
        return subprocess.CompletedProcess(cmd, 0, stdout="\n".join(hits) + "\n",
                                           stderr="")


@pytest.fixture
def fake_es(monkeypatch):
    def _install(index):
        fake = FakeEverything(index)
        monkeypatch.setattr(fp, "_find_everything", lambda: "es.exe")
        monkeypatch.setattr(fp.subprocess, "run", fake.run)
        return fake
    return _install


LOCAL_DIR = r"C:\proj\private"
LOCAL_FILE = r"C:\proj\private\claude\_todo\ACTIVE-WORK.md"


def _global_index(n_far=40):
    """n_far same-substring files elsewhere, ranked BEFORE the local one."""
    far = [rf"C:\other{i}\notes\2026__active-work-idea-{i}.md" for i in range(n_far)]
    return far + [LOCAL_FILE]


# ---------------------------------------------------------------------------
# _run_everything_search
# ---------------------------------------------------------------------------

def test_scoped_query_finds_local_file_past_the_global_cap(fake_es):
    # The reported bug: 61 global matches, local one at #53, -n 20.
    fake_es(_global_index(n_far=52))
    got = fp._run_everything_search("active-work.md", [LOCAL_DIR])
    assert got == [LOCAL_FILE]


def test_scoped_query_passes_path_to_es(fake_es):
    fake = fake_es(_global_index())
    fp._run_everything_search("active-work.md", [LOCAL_DIR])
    assert ["-path", os.path.abspath(LOCAL_DIR)] == fake.calls[0][3:5]


def test_scoped_query_with_no_local_match_returns_none_not_global(fake_es):
    fake_es(_global_index(n_far=5)[:-1])  # drop the local file
    assert fp._run_everything_search("active-work.md", [LOCAL_DIR]) is None


def test_unscoped_query_when_dirs_is_none(fake_es):
    fake = fake_es(_global_index(n_far=3))
    got = fp._run_everything_search("active-work.md", None)
    assert "-path" not in fake.calls[0]
    assert len(got) == 4


def test_multiple_scopes_are_merged_without_duplicates(fake_es):
    fake_es([LOCAL_FILE, r"C:\b\active-work.md"])
    got = fp._run_everything_search("active-work.md", [LOCAL_DIR, r"C:\b", LOCAL_DIR])
    assert got == [LOCAL_FILE, r"C:\b\active-work.md"]


# ---------------------------------------------------------------------------
# _search_for_file: tier order and the announced last resort
# ---------------------------------------------------------------------------

# Realistic answers: real es.exe/fd output carries a drive letter, and the
# CWD tier keeps only same-drive results. tmp_path lives on the temp drive.
_DRIVE = os.path.splitdrive(os.path.abspath(tempfile.gettempdir()))[0]
LOCAL = _DRIVE + r"\here\claude\_todo\ACTIVE-WORK.md"
FD_LOCAL = _DRIVE + r"\here\fd\ACTIVE-WORK.md"
FAR = _DRIVE + r"\somewhere\else\ACTIVE-WORK.md"
OTHER_DRIVE = r"Q:\other\drive\ACTIVE-WORK.md"

@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    """Replace both search engines with scripted fakes; record every call.

    ``es_answers`` maps a scope key ('cwd' / 'drive' / 'anywhere') to the
    Everything result for that scope; fd answers come from ``fd_answers``
    keyed by search root.
    """
    monkeypatch.chdir(tmp_path)
    cwd = os.path.abspath(".")
    drive = os.path.splitdrive(cwd)[0].upper()
    state = {"es_calls": [], "fd_calls": [], "es_answers": {}, "fd_answers": {}}

    def fake_es(pattern, dirs, max_results=None, dir_only=False):
        if dirs is None:
            key = "anywhere"
        elif dirs == [drive + os.sep]:
            key = "drive"
        elif dirs == ["."]:
            key = "cwd"
        else:
            key = "walkup"
        state["es_calls"].append(key)
        return state["es_answers"].get(key)

    def fake_fd(pattern, dirs, max_results=None, dir_only=False):
        state["fd_calls"].append(dirs[0])
        return state["fd_answers"].get(dirs[0], [])

    monkeypatch.setattr(fp, "_everything_indexes_drive", lambda _d: True)
    monkeypatch.setattr(fp, "_run_everything_search", fake_es)
    monkeypatch.setattr(fp, "_run_fd_search", fake_fd)
    state["drive"] = drive
    return state


def test_local_hit_wins_and_drive_search_never_runs(pipeline):
    pipeline["es_answers"]["cwd"] = [LOCAL]
    pipeline["es_answers"]["drive"] = [FAR]
    assert fp._search_for_file("active-work.md", None, {}) == [LOCAL]
    assert "drive" not in pipeline["es_calls"]


def test_fd_runs_when_scoped_everything_finds_nothing(pipeline):
    pipeline["fd_answers"]["."] = [FD_LOCAL]
    pipeline["es_answers"]["drive"] = [FAR]
    assert fp._search_for_file("active-work.md", None, {}) == [FD_LOCAL]
    assert "drive" not in pipeline["es_calls"]


def test_drive_wide_last_resort_is_announced(pipeline, capsys):
    pipeline["es_answers"]["drive"] = [FAR]
    assert fp._search_for_file("active-work.md", None, {}) == [FAR]
    assert pipeline["es_calls"][-1] == "drive"
    err = capsys.readouterr().err
    assert "showing matches elsewhere on " + pipeline["drive"] in err


def test_last_resort_runs_only_after_walk_up(pipeline):
    pipeline["es_answers"]["drive"] = [FAR]
    fp._search_for_file("active-work.md", None, {})
    # CWD first, then at least one walk-up level, and the drive query last
    calls = pipeline["es_calls"]
    assert calls[0] == "cwd" and calls[-1] == "drive"
    assert "walkup" in calls[1:-1]


def test_indexed_walk_up_uses_everything_not_fd(pipeline):
    # An fd crawl of a high ancestor takes tens of seconds; fd runs only at CWD.
    fp._search_for_file("active-work.md", None, {})
    assert pipeline["fd_calls"] == ["."]


def test_walk_up_hit_beats_the_drive_wide_tier(pipeline):
    pipeline["es_answers"]["walkup"] = [LOCAL]
    pipeline["es_answers"]["drive"] = [FAR]
    assert fp._search_for_file("active-work.md", None, {}) == [LOCAL]
    assert "drive" not in pipeline["es_calls"]


def test_unindexed_walk_up_uses_fd(pipeline, monkeypatch):
    monkeypatch.setattr(fp, "_everything_indexes_drive", lambda _d: False)
    fp._search_for_file("active-work.md", None, {})
    assert pipeline["fd_calls"][0] == "."
    assert len(pipeline["fd_calls"]) >= 2
    assert pipeline["es_calls"] == []


def test_quiet_suppresses_the_last_resort_note(pipeline, capsys):
    pipeline["es_answers"]["drive"] = [FAR]
    assert fp._search_for_file("active-work.md", None, {}, quiet=True) == [FAR]
    assert capsys.readouterr().err == ""


def test_explicit_local_scope_is_strict(pipeline):
    pipeline["es_answers"]["drive"] = [FAR]
    assert fp._search_for_file("active-work.md", None, {}, search_on={"local"}) == []
    assert "drive" not in pipeline["es_calls"]


def test_explicit_dir_scope_is_strict(pipeline, tmp_path):
    pipeline["es_answers"]["drive"] = [FAR]
    got = fp._search_for_file("active-work.md", [str(tmp_path)], {})
    assert got == []
    assert "drive" not in pipeline["es_calls"]


def test_anywhere_uses_an_unscoped_query(pipeline):
    pipeline["es_answers"]["anywhere"] = [OTHER_DRIVE]
    got = fp._search_for_file("active-work.md", None, {}, search_on={"anywhere"})
    assert got == [OTHER_DRIVE]
    assert "anywhere" in pipeline["es_calls"]


# ---------------------------------------------------------------------------
# On-disk casing
# ---------------------------------------------------------------------------

def _case_insensitive_fs(tmp_path):
    probe = tmp_path / "CaseProbe.txt"
    probe.write_text("x")
    return (tmp_path / "caseprobe.txt").exists()


def test_true_case_returns_on_disk_spelling(tmp_path):
    if not _case_insensitive_fs(tmp_path):
        pytest.skip("filesystem is case-sensitive")
    real = tmp_path / "Claude" / "_todo" / "ACTIVE-WORK.md"
    real.parent.mkdir(parents=True)
    real.write_text("x")
    typed = str(tmp_path / "claude" / "_TODO" / "active-work.md")
    assert fp._true_case(typed) == str(real)


def test_true_case_leaves_missing_path_unchanged(tmp_path):
    typed = str(tmp_path / "no" / "such" / "file.md")
    assert fp._true_case(typed) == typed


def test_fix_path_returns_on_disk_casing(tmp_path):
    if not _case_insensitive_fs(tmp_path):
        pytest.skip("filesystem is case-sensitive")
    real = tmp_path / "ACTIVE-WORK.md"
    real.write_text("x")
    assert fp.fix_path(str(tmp_path / "active-work.md")) == str(real)


def test_main_print_only_emits_on_disk_casing(tmp_path, monkeypatch, capsys):
    if not _case_insensitive_fs(tmp_path):
        pytest.skip("filesystem is case-sensitive")
    real = tmp_path / "Sub" / "ACTIVE-WORK.md"
    real.parent.mkdir()
    real.write_text("x")
    monkeypatch.chdir(tmp_path)
    rc = fp.main(["-p", "sub/active-work.md"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == str(real)
