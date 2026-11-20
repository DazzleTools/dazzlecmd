"""Process identity: which process is this, is it still the same one, who started it.

Vendored (see ``_VENDORED.md``): written as a lift-ready, stdlib-only module
with no dazzlecmd imports, so it can move into a shared library that csb,
unlockit and dazzlecmd-lib's ``shell_fix`` can all use.

Everything that reads the operating system goes through small functions that
take their inputs explicitly (a process table, a start-time function, a clock),
so callers and tests can substitute fakes.

Identity rule: a process is "the same one" when its pid is alive, its exe name
matches, and its creation time matches. A pid alone is not identity -- PIDs are
reused, and on Windows a dead PID has been seen to come back as an unrelated
process after a restart.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

__all__ = [
    "Proc", "process_table", "process_start_time", "process_exe", "is_alive",
    "ancestor_chain", "boot_time", "same_process", "TERMINAL_HOSTS", "SHELL_EXES",
    "find_anchor",
]

_WINDOWS = sys.platform == "win32"

#: Processes that host a terminal tab: the process directly below one of these
#: is the tab's own shell. Lowercased exe names, no extension on POSIX.
TERMINAL_HOSTS = frozenset({
    "windowsterminal.exe", "code.exe", "code - insiders.exe", "cursor.exe",
    "mintty.exe", "wezterm-gui.exe", "alacritty.exe", "conemu64.exe",
    "conemu.exe", "sshd.exe", "explorer.exe",
    "gnome-terminal-server", "konsole", "xterm", "alacritty", "kitty",
    "wezterm-gui", "tmux: server", "tmux", "screen", "sshd", "terminal",
    "iterm2",
})

#: Shell executables, for the fallback when no terminal host is found.
SHELL_EXES = frozenset({
    "cmd.exe", "pwsh.exe", "powershell.exe", "bash.exe", "zsh.exe", "sh.exe",
    "fish.exe", "nu.exe",
    "bash", "zsh", "sh", "fish", "dash", "ksh", "tcsh", "csh", "nu", "pwsh",
})


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    exe: str


# --------------------------------------------------------------------------
# Windows bindings (bound on first use)
# --------------------------------------------------------------------------

_k32 = None


def _win():
    global _k32
    if _k32 is None:
        import ctypes
        import ctypes.wintypes as wt
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
        k32.OpenProcess.restype = wt.HANDLE
        k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
        k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
        k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                   ctypes.POINTER(wt.DWORD)]
        k32.CloseHandle.argtypes = [wt.HANDLE]
        k32.GetTickCount64.restype = ctypes.c_ulonglong
        _k32 = k32
    return _k32


def _entry_type():
    import ctypes
    import ctypes.wintypes as wt

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", wt.LONG), ("dwFlags", wt.DWORD),
            ("szExeFile", wt.WCHAR * 260),
        ]
    return PROCESSENTRY32W


_PQLI = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
_STILL_ACTIVE = 259


# --------------------------------------------------------------------------
# the process table
# --------------------------------------------------------------------------

def process_table() -> Dict[int, Proc]:
    """{pid: Proc} for every process this user can see."""
    if _WINDOWS:
        return _table_windows()
    if os.path.isdir("/proc/self"):
        return _table_proc()
    return _table_ps()


def _table_windows() -> Dict[int, Proc]:
    import ctypes
    import ctypes.wintypes as wt
    k32 = _win()
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (None, wt.HANDLE(-1).value):
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    entry_t = _entry_type()
    k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(entry_t)]
    k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(entry_t)]
    out: Dict[int, Proc] = {}
    try:
        entry = entry_t()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            out[entry.th32ProcessID] = Proc(entry.th32ProcessID, entry.th32ParentProcessID,
                                            entry.szExeFile)
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return out


def _table_proc() -> Dict[int, Proc]:
    out: Dict[int, Proc] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        st = _proc_stat(int(name))
        if st:
            out[int(name)] = Proc(int(name), st[1], st[0])
    return out


def _proc_stat(pid: int):
    """(comm, ppid, starttime_ticks) from /proc/<pid>/stat, or None."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            data = f.read()
    except OSError:
        return None
    lp, rp = data.find("("), data.rfind(")")
    if lp < 0 or rp < 0:
        return None
    comm = data[lp + 1:rp]
    rest = data[rp + 2:].split()
    try:
        return comm, int(rest[1]), int(rest[19])
    except (IndexError, ValueError):
        return None


def _table_ps() -> Dict[int, Proc]:
    try:
        text = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,comm="],
                              capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    out: Dict[int, Proc] = {}
    for line in text.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            out[int(parts[0])] = Proc(int(parts[0]), int(parts[1]), os.path.basename(parts[2]))
    return out


# --------------------------------------------------------------------------
# one process
# --------------------------------------------------------------------------

def process_start_time(pid: int) -> Optional[int]:
    """A creation-time value that is equal only for the same process, or None.

    Windows: the FILETIME integer. Linux: clock ticks since boot (field 22).
    Other POSIX: ``ps -o lstart`` text hashed to an int. Compare values only
    with values from this same function on this same machine.
    """
    if _WINDOWS:
        import ctypes
        import ctypes.wintypes as wt
        k32 = _win()
        h = k32.OpenProcess(_PQLI, False, pid)
        if not h:
            return None
        try:
            times = [wt.FILETIME() for _ in range(4)]
            if not k32.GetProcessTimes(h, *[ctypes.byref(t) for t in times]):
                return None
            return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        finally:
            k32.CloseHandle(h)
    st = _proc_stat(pid) if os.path.isdir("/proc/self") else None
    if st:
        return st[2]
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return hash(out) if out else None


def is_alive(pid: int) -> Optional[bool]:
    """True alive, False gone, None when it cannot be told (access denied)."""
    if pid <= 0:
        return False
    if _WINDOWS:
        import ctypes
        import ctypes.wintypes as wt
        k32 = _win()
        h = k32.OpenProcess(_PQLI, False, pid)
        if not h:
            err = ctypes.get_last_error()
            return None if err == 5 else False   # 5 = ERROR_ACCESS_DENIED
        try:
            code = wt.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return None
            return code.value == _STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def process_exe(pid: int, table: Optional[Dict[int, Proc]] = None) -> Optional[str]:
    """The exe's base name (lowercased on Windows), or None."""
    if table is not None and pid in table:
        name = table[pid].exe
        return name.lower() if _WINDOWS else name
    if _WINDOWS:
        import ctypes
        import ctypes.wintypes as wt
        k32 = _win()
        h = k32.OpenProcess(_PQLI, False, pid)
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wt.DWORD(len(buf))
            if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return None
            return os.path.basename(buf.value).lower()
        finally:
            k32.CloseHandle(h)
    st = _proc_stat(pid) if os.path.isdir("/proc/self") else None
    return st[0] if st else None


def same_process(pid: int, exe: Optional[str], start_time: Optional[int], *,
                 alive: Callable[[int], Optional[bool]] = None,
                 exe_of: Callable[[int], Optional[str]] = None,
                 start_of: Callable[[int], Optional[int]] = None) -> Optional[bool]:
    """Is ``pid`` still the process recorded as (exe, start_time)?

    True: alive and both match. False: positive evidence it is gone or a
    different process (dead, exe differs, start time differs). None: alive but
    its details cannot be read (e.g. an elevated process seen from a normal
    one) -- callers must treat None as *held*, never as gone.
    """
    alive = alive or is_alive
    exe_of = exe_of or process_exe
    start_of = start_of or process_start_time
    a = alive(pid)
    if a is False:
        return False
    if a is None:
        return None
    cur_exe = exe_of(pid)
    if exe and cur_exe and cur_exe.lower() != exe.lower():
        return False
    cur_start = start_of(pid)
    if start_time is not None and cur_start is not None:
        return cur_start == start_time
    return None


# --------------------------------------------------------------------------
# lineage and the tab anchor
# --------------------------------------------------------------------------

def ancestor_chain(pid: int, table: Dict[int, Proc],
                   start_of: Optional[Callable[[int], Optional[int]]] = None,
                   max_depth: int = 64) -> List[int]:
    """[pid, parent, grandparent, ...] as far as the parent links are real.

    A parent that started after its child is not its parent (the real one
    exited and its number was reused), so the walk stops there.
    """
    start_of = start_of or process_start_time
    chain = [pid]
    seen = {pid}
    child_start = start_of(pid)
    while len(chain) < max_depth:
        proc = table.get(chain[-1])
        if proc is None or proc.ppid in seen or proc.ppid == 0:
            break
        parent = table.get(proc.ppid)
        if parent is None:
            break
        parent_start = start_of(parent.pid)
        if child_start is not None and parent_start is not None and parent_start > child_start:
            break
        chain.append(parent.pid)
        seen.add(parent.pid)
        child_start = parent_start
    return chain


def find_anchor(pid: int, table: Dict[int, Proc],
                start_of: Optional[Callable[[int], Optional[int]]] = None):
    """The process that stands for "this terminal tab", and the rule used.

    Returns (anchor_pid, rule). Rules, in order:
      ``below-host:<exe>``  -- the process directly below the NEAREST terminal
                              host ancestor (the tab's own shell);
      ``outermost-shell``   -- no host found: the outermost shell in the chain;
      ``self``              -- nothing better: ``pid`` itself.
    """
    chain = ancestor_chain(pid, table, start_of)
    names = [(table[p].exe.lower() if p in table else "") for p in chain]
    for i in range(1, len(chain)):
        if names[i] in TERMINAL_HOSTS:
            return chain[i - 1], f"below-host:{names[i]}"
    shells = [chain[i] for i in range(len(chain)) if names[i] in SHELL_EXES]
    if shells:
        return shells[-1], "outermost-shell"
    return pid, "self"


# --------------------------------------------------------------------------
# boot time
# --------------------------------------------------------------------------

def boot_time(clock: Callable[[], float] = time.time) -> Optional[float]:
    """When this machine booted, as epoch seconds, or None.

    Accurate to seconds and drifting slowly (about 6 s over two days measured
    on Windows): compare two readings with a tolerance, never as a key.
    """
    now = clock()
    if _WINDOWS:
        try:
            return now - _win().GetTickCount64() / 1000.0
        except (OSError, AttributeError):
            return None
    try:
        with open("/proc/uptime", encoding="utf-8") as f:
            return now - float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    try:
        out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True,
                             text=True, timeout=5).stdout
        sec = out.split("sec =")[1].split(",")[0].strip()
        return float(sec)
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None
