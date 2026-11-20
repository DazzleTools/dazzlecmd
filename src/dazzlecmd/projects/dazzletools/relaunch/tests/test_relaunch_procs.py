"""S2: the vendored process-identity module (src/dazzlecmd/_vendor/procs)."""

import os
import re
import subprocess
import sys

import pytest

from dazzlecmd._vendor import procs as p

P = p.Proc

# The ancestry measured on the maintainer's box (investigation A 2.4, round 1 M10):
# python <- bash <- claude <- python(csb) <- cmd (the tab) <- WindowsTerminal <- explorer
MEASURED = {
    10: P(10, 11, "python.exe"),
    11: P(11, 12, "bash.exe"),
    12: P(12, 13, "claude-dcc.exe"),
    13: P(13, 14, "python.exe"),
    14: P(14, 15, "cmd.exe"),
    15: P(15, 16, "WindowsTerminal.exe"),
    16: P(16, 0, "explorer.exe"),
}
STARTS = {16: 1, 15: 2, 14: 3, 13: 4, 12: 5, 11: 6, 10: 7}


def _start(pid):
    return STARTS.get(pid)


def test_anchor_is_the_shell_below_the_terminal_host():
    assert p.find_anchor(10, MEASURED, _start) == (14, "below-host:windowsterminal.exe")


def test_nearest_host_wins_for_a_terminal_started_from_a_terminal():
    table = dict(MEASURED)
    # VS Code launched from the tab, and a shell in VS Code's terminal
    table[20] = P(20, 14, "Code.exe")
    table[21] = P(21, 20, "pwsh.exe")
    table[22] = P(22, 21, "python.exe")
    starts = {**STARTS, 20: 8, 21: 9, 22: 10}
    assert p.find_anchor(22, table, starts.get) == (21, "below-host:code.exe")


def test_no_host_falls_back_to_outermost_shell():
    table = {1: P(1, 2, "python"), 2: P(2, 3, "bash"), 3: P(3, 4, "bash"), 4: P(4, 0, "init")}
    starts = {4: 1, 3: 2, 2: 3, 1: 4}
    assert p.find_anchor(1, table, starts.get) == (3, "outermost-shell")


def test_reused_parent_pid_stops_the_walk():
    table = {1: P(1, 2, "python.exe"), 2: P(2, 0, "WindowsTerminal.exe")}
    starts = {1: 5, 2: 9}   # the "parent" started after the child: a reused pid
    assert p.ancestor_chain(1, table, starts.get) == [1]


def test_same_process_rules():
    alive = {1: True, 2: True, 3: False, 4: None}.get
    exe = {1: "cmd.exe", 2: "notepad.exe", 4: None}.get
    start = {1: 100, 2: 100, 4: None}.get
    kw = dict(alive=alive, exe_of=exe, start_of=start)
    assert p.same_process(1, "cmd.exe", 100, **kw) is True
    assert p.same_process(1, "cmd.exe", 101, **kw) is False     # start time differs
    assert p.same_process(2, "cmd.exe", 100, **kw) is False     # exe differs (reused pid)
    assert p.same_process(3, "cmd.exe", 100, **kw) is False     # dead
    assert p.same_process(4, "cmd.exe", 100, **kw) is None      # unknown = held


def test_real_child_identity_and_death():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        start = p.process_start_time(child.pid)
        exe = p.process_exe(child.pid)
        assert start is not None and exe
        assert p.same_process(child.pid, exe, start) is True
    finally:
        child.kill()
        child.wait()
    assert p.same_process(child.pid, exe, start) is False


def test_boot_time_is_in_the_past_and_stable():
    a = p.boot_time()
    b = p.boot_time()
    assert a is not None and a < __import__("time").time()
    assert abs(a - b) < 5


def test_vendored_module_imports_nothing_from_dazzlecmd():
    src = open(p.__file__, encoding="utf-8").read()
    assert not re.search(r"^\s*(from|import)\s+dazzlecmd\b", src, re.M)
