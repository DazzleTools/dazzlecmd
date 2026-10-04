"""Tests for unlockit (step 1: detect and report; nothing is focused, closed or ended).

Two kinds:
- Pure tests drive title ranking, ancestry walking and grouping with fake
  process tables and window lists. The window titles in VSCODE_TITLES are
  the real ones measured on 2026-10-04 when a VS Code window held
  C:\\code\\git-repokit-common__extra-targets.
- Real tests (Windows only) lock files and folders with short-lived child
  processes of our own -- each exits by itself after 60 s and is killed when
  its test ends -- and check that the probe, Restart Manager and the
  working-directory scan name them. handle.exe is never run; it is faked.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL_DIR))
import holders as hd  # noqa: E402
import unlockit as ul  # noqa: E402
import winfocus as wf  # noqa: E402
sys.path.pop(0)

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tool")

_REAL_FOCUS = wf.focus


@pytest.fixture(autouse=True)
def no_real_focus(monkeypatch):
    """No test may raise a real window on the developer's desktop. Tests of
    focus() itself call _REAL_FOCUS against a faked Win32 layer."""
    def refuse(*a, **k):
        raise AssertionError("a test tried to focus a real window")
    monkeypatch.setattr(wf, "focus", refuse)

TARGET = r"C:\code\git-repokit-common__extra-targets"
VSCODE_TITLES = [
    "CHANGELOG.md (Working Tree) (CHANGELOG.md) - git-repokit-common - Visual Studio Code",
    "tsconfig.json (Index) (tsconfig.json (Index)) - claude-bookmarks - Visual Studio Code",
    "test_sync_versions_extra_targets.py - git-repokit-common__extra-targets - Visual Studio Code",
    "macydek-qwen21-convrot-test.yaml - ai-toolkit - Visual Studio Code",
    "move_private_to_local.py - local - Visual Studio Code",
    "Untitled (Workspace) - Visual Studio Code",
    "test_plugins_verb.py (Index) (test_plugins_verb.py) - local - Visual Studio Code",
    "check_trigger.py - skills - Visual Studio Code",
]
HOLDING_TITLE = VSCODE_TITLES[2]


def win(hwnd, pid, title, exe="Code.exe"):
    return wf.Window(hwnd=hwnd, pid=pid, title=title, class_name="Chrome_WidgetWin_1", exe=exe)


def no_times(_pid):
    return None


# ------------------------------------------------------------------ title ranking

def test_leaf_folder_in_title_wins_over_its_prefix_sibling():
    windows = [win(i, 31176, t) for i, t in enumerate(VSCODE_TITLES)]
    assert wf.best_window(windows, TARGET).title == HOLDING_TITLE


def test_parent_folder_name_never_matches_inside_a_longer_segment():
    # "code" is the target's parent folder; "Visual Studio Code" must not count.
    assert wf.path_match_score("move_private_to_local.py - local - Visual Studio Code", TARGET) == 0
    assert wf.path_match_score(VSCODE_TITLES[0], TARGET) == 0


def test_title_decorations_are_stripped_before_matching():
    path = r"C:\notes\claude\_todo\ACTIVE-WORK.md"
    assert wf.path_match_score("ACTIVE-WORK.md\u2022 - Typora", path) == 5
    assert wf.path_match_score("*ACTIVE-WORK.md - Notepad", path) == 5
    assert wf.path_match_score("ACTIVE-WORK.md (Working Tree) - x - Visual Studio Code", path) == 5


def test_full_path_in_title_outranks_a_leaf_match():
    path = r"C:\a\b\ACTIVE-WORK.md"
    full = win(1, 9, r"C:\a\b\ACTIVE-WORK.md - Notepad++", "notepad++.exe")
    leaf = win(2, 9, "ACTIVE-WORK.md - Notepad++", "notepad++.exe")
    assert wf.best_window([leaf, full], path) is full


def test_tied_titles_pick_nothing_rather_than_guess():
    path = r"C:\x\ACTIVE-WORK.md"
    a, b = win(1, 9, "ACTIVE-WORK.md - Typora"), win(2, 9, "ACTIVE-WORK.md - Typora")
    assert wf.best_window([a, b], path) is None


def test_a_lone_window_is_the_answer_even_without_a_title_match():
    only = win(1, 9, "Something else - App")
    assert wf.best_window([only], TARGET) is only


def test_no_title_names_the_path_gives_none():
    windows = [win(i, 9, t) for i, t in enumerate(VSCODE_TITLES) if t != HOLDING_TITLE]
    assert wf.best_window(windows, TARGET) is None


# ------------------------------------------------------------------ ancestry

def procs_of(*rows):
    return {pid: wf.Proc(pid, ppid, exe) for pid, ppid, exe in rows}


def test_ancestor_walk_stops_at_a_reused_parent_pid():
    procs = procs_of((30, 20, "child.exe"), (20, 10, "imposter.exe"), (10, 0, "root.exe"))
    starts = {30: 100, 20: 500, 10: 50}   # 20 started after its "child": PID was reused
    assert wf.ancestor_chain(30, procs, start_time=starts.get) == [30]


def test_ancestor_walk_survives_a_parent_cycle():
    procs = procs_of((1, 2, "a.exe"), (2, 1, "b.exe"))
    assert wf.ancestor_chain(1, procs, start_time=no_times) == [1, 2]


def test_windowed_ancestor_climbs_to_the_window_owner():
    procs = procs_of((22704, 69692, "cmd.exe"), (69692, 31176, "Code.exe"), (31176, 5000, "Code.exe"),
                     (5000, 1, "explorer.exe"))
    by_pid = {31176: [win(1, 31176, HOLDING_TITLE)]}
    assert wf.windowed_ancestor(22704, procs, by_pid, start_time=no_times) == 31176


def test_windowed_ancestor_never_attributes_to_explorer():
    procs = procs_of((7, 5000, "python.exe"), (5000, 1, "explorer.exe"))
    by_pid = {5000: [win(1, 5000, "Downloads", "explorer.exe")]}
    assert wf.windowed_ancestor(7, procs, by_pid, start_time=no_times) is None


# ------------------------------------------------------------------ grouping

@pytest.fixture
def vscode_world(monkeypatch):
    """Process table and windows shaped like the measured VS Code case."""
    monkeypatch.setattr(wf, "process_start_time", no_times)
    procs = procs_of(
        (31176, 5000, "Code.exe"), (32188, 31176, "Code.exe"), (69692, 31176, "Code.exe"),
        (22704, 69692, "cmd.exe"), (32404, 32188, "python.exe"), (5248, 32188, "Code.exe"),
        (900, 5000, "python.exe"), (5000, 1, "explorer.exe"),
    )
    windows = [win(0x100 + i, 31176, t) for i, t in enumerate(VSCODE_TITLES)]
    return procs, windows


def cwd(pid, exe="x.exe", where=TARGET):
    return hd.Holder(pid, exe, "cwd", where, "cwd-scan")


def test_holders_under_one_window_become_one_group(vscode_world):
    procs, windows = vscode_world
    groups = ul.group_holders([cwd(22704), cwd(32404), cwd(5248)], TARGET, procs, windows)
    assert len(groups) == 1
    assert groups[0].window.title == HOLDING_TITLE
    assert sorted(h.pid for h in groups[0].holders) == [5248, 22704, 32404]
    assert {h.exe for h in groups[0].holders} == {"cmd.exe", "python.exe", "Code.exe"}


def test_windowless_holder_gets_its_own_group_after_windows(vscode_world):
    procs, windows = vscode_world
    groups = ul.group_holders([cwd(900), cwd(22704)], TARGET, procs, windows)
    assert [g.window is None for g in groups] == [False, True]
    assert groups[1].owner_pid == 900 and groups[1].window_count == 0


def test_owner_whose_titles_never_name_the_path_is_not_guessed(vscode_world):
    procs, windows = vscode_world
    others = [w for w in windows if w.title != HOLDING_TITLE]
    groups = ul.group_holders([cwd(22704)], TARGET, procs, others)
    assert groups[0].window is None and groups[0].window_count == 7


def test_the_shell_unlockit_runs_from_is_flagged(vscode_world):
    procs, windows = vscode_world
    groups = ul.group_holders([cwd(22704)], TARGET, procs, windows, self_chain={22704, 69692})
    assert groups[0].is_self


def test_the_same_holding_is_reported_once(vscode_world):
    procs, windows = vscode_world
    groups = ul.group_holders([cwd(22704), cwd(22704)], TARGET, procs, windows)
    assert len(groups[0].holders) == 1


# ------------------------------------------------------------------ focus (faked Win32)

class FakeUser32:
    """Just enough of user32 for focus(): a foreground window that moves
    only when an attempt whose name is in `grants` asks for it."""

    def __init__(self, target, foreground=0x999, minimized=False, exists=True, grants=()):
        self.target, self.fg, self.minimized, self.exists = target, foreground, minimized, exists
        self.grants, self.calls, self._granting = set(grants), [], False

    def IsWindow(self, h): return self.exists
    def IsIconic(self, h): return self.minimized
    def GetForegroundWindow(self): return self.fg
    def GetWindowTextLengthW(self, h): return 5
    def GetWindowTextW(self, h, buf, n): buf.value = "Other"
    def ShowWindow(self, h, cmd): self.calls.append(("ShowWindow", cmd)); self.minimized = False
    def SetForegroundWindow(self, h):
        self.calls.append("SetForegroundWindow")
        if self._granting:
            self.fg = h


def run_focus(monkeypatch, u32, attempts=("plain", "input-nudge", "alt-key")):
    monkeypatch.setattr(wf, "_win", lambda: (None, u32, None))
    called = []

    def make(name):
        def attempt(u, k, hwnd):
            called.append(name)
            u._granting = name in u.grants
            u.SetForegroundWindow(hwnd)
        return (name, attempt)
    t = [0.0]

    def clock():
        t[0] += 0.1
        return t[0]
    result = _REAL_FOCUS(u32.target, attempts=[make(n) for n in attempts], sleep=lambda s: None, clock=clock)
    return result, called


def test_focus_stops_at_the_first_attempt_that_works(monkeypatch):
    u32 = FakeUser32(0x42, grants={"input-nudge"})
    result, called = run_focus(monkeypatch, u32)
    assert result == wf.FocusResult(True, "input-nudge") and called == ["plain", "input-nudge"]


def test_focus_restores_a_minimized_window_before_asking(monkeypatch):
    u32 = FakeUser32(0x42, minimized=True, grants={"plain"})
    run_focus(monkeypatch, u32)
    assert u32.calls[0] == ("ShowWindow", 9) and u32.calls[1] == "SetForegroundWindow"


def test_focus_on_the_foreground_window_does_nothing(monkeypatch):
    u32 = FakeUser32(0x42, foreground=0x42)
    result, called = run_focus(monkeypatch, u32)
    assert result.method == "already" and called == [] and u32.calls == []


def test_focus_refused_everywhere_names_who_kept_it(monkeypatch):
    u32 = FakeUser32(0x42)
    result, called = run_focus(monkeypatch, u32)
    assert not result.ok and result.method == "refused" and '"Other"' in result.detail
    assert called == ["plain", "input-nudge", "alt-key"]


def test_focus_on_a_closed_window_reports_it_gone(monkeypatch):
    result, called = run_focus(monkeypatch, FakeUser32(0x42, exists=False))
    assert result.method == "gone" and called == []


# ------------------------------------------------------------------ --focus choice

def group(window=None, count=0, exe="Code.exe"):
    gr = ul.Group(1, exe, window, count)
    gr.holders.append(cwd(1))
    return gr


def test_bare_focus_picks_the_only_windowed_group():
    a = group(win(1, 1, "a"), 1)
    assert ul.pick_group([a, group()], 0) == (a, None)


def test_bare_focus_refuses_to_choose_between_windows():
    gr, why = ul.pick_group([group(win(1, 1, "a"), 1), group(win(2, 2, "b"), 1)], 0)
    assert gr is None and "--focus N" in why


def test_focus_on_an_ambiguous_owner_explains_instead_of_guessing():
    gr, why = ul.pick_group([group(None, 15, "WindowsTerminal.exe")], 1)
    assert gr is None and "15 windows" in why


def test_focus_number_out_of_range():
    gr, why = ul.pick_group([group(win(1, 1, "a"), 1)], 3)
    assert gr is None and "1-1" in why


def test_cli_focus_raises_the_chosen_window_and_exits_0(monkeypatch, capsys, tmp_path):
    target = tmp_path / "busy"
    target.mkdir()
    holder = hd.Holder(4242, "x.exe", "cwd", str(target), "cwd-scan")
    monkeypatch.setattr(hd, "gather", lambda *a, **k: hd.Gathered(str(target), True, hd.Probe("in-use", 32), [holder]))
    monkeypatch.setattr(wf, "snapshot_processes", lambda: {4242: wf.Proc(4242, 0, "x.exe")})
    monkeypatch.setattr(wf, "process_start_time", no_times)
    monkeypatch.setattr(wf, "list_windows", lambda procs=None: [win(0x42, 4242, "busy - X", "x.exe")])
    focused = []
    monkeypatch.setattr(wf, "focus", lambda hwnd: focused.append(hwnd) or wf.FocusResult(True, "plain"))
    assert ul.main([str(target), "--focus"]) == ul.EXIT_FREE
    assert focused == [0x42] and 'focused: "busy - X"' in capsys.readouterr().out


def test_cli_focus_with_nothing_to_raise_exits_2_without_focusing(monkeypatch, capsys, tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("x")
    monkeypatch.setattr(hd, "gather", lambda *a, **k: hd.Gathered(str(f), False, hd.Probe("free")))
    monkeypatch.setattr(wf, "list_windows", lambda procs=None: [])
    assert ul.main([str(f), "--focus"]) == ul.EXIT_ERROR   # autouse fixture fails the test if focus() runs
    assert "could not focus" in capsys.readouterr().err


# ------------------------------------------------------------------ handle.exe (faked)

def test_handle_csv_rows_parse_and_noise_is_ignored():
    text = ("Process,PID,Type,Handle,Name\n"
            "Code.exe,31176,File,0x1A4,C:\\x\\a.md\n"
            "No matching handles found.\n")
    assert hd.parse_handle_csv(text) == [hd.Holder(31176, "Code.exe", "handle", "C:\\x\\a.md", "handle.exe")]


def test_a_hanging_handle_exe_becomes_a_note_not_a_hang(monkeypatch, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    monkeypatch.setattr(hd, "probe_delete", lambda p: hd.Probe("free"))
    monkeypatch.setattr(hd, "restart_manager_holders", lambda files: [])
    monkeypatch.setattr(hd, "find_handle_exe", lambda explicit=None: r"C:\fake\handle64.exe")

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("handle64.exe", hd.HANDLE_TIMEOUT)
    monkeypatch.setattr(hd, "handle_holders", hang)
    g = hd.gather(str(f), use_handle=True)
    assert any("no answer" in n for n in g.notes)


def test_uninspected_count_appears_only_when_no_holder_was_found():
    g = hd.Gathered(path=r"C:\x", is_dir=True, probe=hd.Probe("in-use", 32), uninspected=204)
    assert "204 processes could not be inspected" in ul._status_line(g, 0)
    assert "could not be inspected" not in ul._status_line(g, 3)


def test_access_denied_is_not_reported_as_a_lock():
    g = hd.Gathered(path=r"C:\x", is_dir=False, probe=hd.Probe("denied", 5))
    line = ul._status_line(g, 0)
    assert "not a lock" in line and "sharing violation" not in line


# ------------------------------------------------------------------ real locks (own child processes)

class Child:
    """A python child that holds a file open or sits in a folder. Exits on
    its own after 60 s; killed at fixture teardown."""

    def __init__(self, code, cwd=None):
        self.p = subprocess.Popen([sys.executable, "-c", code + "\nprint('ready', flush=True)\n"
                                   "import time; time.sleep(60)"],
                                  cwd=cwd, stdout=subprocess.PIPE, text=True)
        assert self.p.stdout.readline().strip() == "ready"
        self.pid = self.p.pid

    def stop(self):
        self.p.kill()
        self.p.wait()
        self.p.stdout.close()


@pytest.fixture
def children():
    made = []

    def make(code="pass", cwd=None):
        c = Child(code, cwd)
        made.append(c)
        return c
    yield make
    for c in made:
        c.stop()


@windows_only
def test_probe_tells_free_held_and_missing_apart(tmp_path, children):
    f = tmp_path / "doc.md"
    f.write_text("x")
    assert hd.probe_delete(str(f)).state == "free"
    children(f"h = open(r'{f}')")
    assert hd.probe_delete(str(f)) == hd.Probe("in-use", 32)
    assert hd.probe_delete(str(tmp_path / "nope.md")).state == "missing"


@windows_only
def test_probe_changes_nothing(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("keep me")
    hd.probe_delete(str(f))
    hd.probe_delete(str(tmp_path))
    assert f.read_text() == "keep me"


@windows_only
def test_restart_manager_names_the_file_holder(tmp_path, children):
    f = tmp_path / "doc.md"
    f.write_text("x")
    c = children(f"h = open(r'{f}')")
    found = hd.restart_manager_holders([str(f)])
    assert [(h.pid, h.reason, h.detail) for h in found] == [(c.pid, "open", str(f))]


@windows_only
def test_a_folder_reports_which_file_inside_is_held(tmp_path, children):
    sub = tmp_path / "proj" / "notes"
    sub.mkdir(parents=True)
    held = sub / "held.md"
    held.write_text("x")
    (sub / "free.md").write_text("x")
    c = children(f"h = open(r'{held}')")
    g = hd.gather(str(tmp_path / "proj"))
    opens = [h for h in g.holders if h.reason == "open"]
    assert [(h.pid, h.detail) for h in opens] == [(c.pid, str(held))]


@windows_only
def test_cwd_scan_finds_inside_but_not_a_prefix_sibling(tmp_path, children):
    target = tmp_path / "busy"
    (target / "deep").mkdir(parents=True)
    sibling = tmp_path / "busy-other"
    sibling.mkdir()
    inside = children(cwd=str(target / "deep"))
    outside = children(cwd=str(sibling))
    res = hd.cwd_holders(str(target))
    if res is None:
        pytest.skip("psutil not installed")
    pids = {h.pid for h in res[0]}
    assert inside.pid in pids and outside.pid not in pids


@windows_only
def test_folder_walk_does_not_cross_a_junction(tmp_path):
    _winapi = pytest.importorskip("_winapi")
    root = tmp_path / "root"
    root.mkdir()
    (root / "own.txt").write_text("x")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "foreign.txt").write_text("x")
    link = root / "link"
    _winapi.CreateJunction(str(elsewhere), str(link))
    try:
        files, truncated = hd.files_under(str(root))
        assert [os.path.basename(f) for f in files] == ["own.txt"] and not truncated
    finally:
        os.rmdir(link)   # removes the junction only, never its target


@windows_only
def test_cli_json_names_the_holder_and_exits_1(tmp_path, children, capsys):
    target = tmp_path / "busy"
    target.mkdir()
    c = children(cwd=str(target))
    rc = ul.main([str(target), "--json"])
    out = json.loads(capsys.readouterr().out)
    pids = {h["pid"] for g in out["groups"] for h in g["holders"]}
    if "working-directory check unavailable" in " ".join(out["notes"]):
        pytest.skip("psutil not installed")
    assert rc == ul.EXIT_HELD and c.pid in pids and out["state"] == "in-use"


@windows_only
def test_cli_free_file_exits_0_and_missing_exits_2(tmp_path, capsys):
    f = tmp_path / "doc.md"
    f.write_text("x")
    assert ul.main([str(f)]) == ul.EXIT_FREE
    assert "Free" in capsys.readouterr().out
    assert ul.main([str(tmp_path / "nope.md")]) == ul.EXIT_ERROR


@windows_only
def test_cli_text_shows_the_holding_window_title(tmp_path, children, capsys, monkeypatch):
    """Report shape with a real holder but a fake window list, so the test
    does not depend on what windows happen to be open."""
    target = tmp_path / "busy"
    target.mkdir()
    c = children(cwd=str(target))
    monkeypatch.setattr(wf, "list_windows", lambda procs=None: [win(0x42, c.pid, "busy - FakeEditor", "python.exe")])
    rc = ul.main([str(target)])
    out = capsys.readouterr().out
    if "working-directory check unavailable" in out:
        pytest.skip("psutil not installed")
    assert rc == ul.EXIT_HELD
    assert '[1] window: "busy - FakeEditor"' in out
    assert f"pid {c.pid}" in out and "working directory is here" in out
