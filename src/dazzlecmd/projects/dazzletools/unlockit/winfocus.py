"""Find the top-level window that belongs to a process or names a path.

Self-contained on purpose: this module imports nothing from the rest of
unlockit and needs only the standard library (ctypes), so it can be lifted
into a shared library later -- fixpath's "bring the opened document's window
forward" is the expected second user. Windows-only; every Win32 entry point
is bound lazily so importing this on another platform does not fail.

Two facts shape the API (measured 2026-10-04, see the unlockit DWP):

- A PID does not identify a window. Electron apps (VS Code, Typora) run
  every window under one main process: VS Code's owned 8, Typora's 7.
  The disambiguator is the window title, which names the open file or
  folder -- see path_match_score().
- The process that holds something often has no window of its own
  (language servers, a terminal shell, a renderer). Walk up its parents
  to the first one that owns windows -- see windowed_ancestor() -- but
  stop at shell/system processes, whose windows are never the answer.
"""

import ctypes
import ctypes.wintypes as wt
import os
import re
from dataclasses import dataclass

# Ancestors we never attribute a holder to. explorer.exe launches most
# things, so walking into it would "find" a random Explorer window.
STOP_EXES = frozenset({
    "explorer.exe", "services.exe", "svchost.exe", "wininit.exe",
    "winlogon.exe", "smss.exe", "csrss.exe", "system", "[system process]",
    "sihost.exe", "userinit.exe",
})

# Segment separators Windows apps use in titles ("file - folder - App").
_TITLE_SPLIT = re.compile(r"\s+[-–—|]\s+")
# Modified / unsaved markers apps append or prepend (*, bullet, circle).
_DECORATION = "*•●○ \t"


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    exe: str


@dataclass(frozen=True)
class Window:
    hwnd: int
    pid: int
    title: str
    class_name: str
    exe: str = ""
    minimized: bool = False
    cloaked: bool = False   # hidden by DWM: another virtual desktop, or a suspended UWP shell


# ------------------------------------------------------------------ Win32 binding

_api = None


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", wt.LONG), ("dwFlags", wt.DWORD),
        ("szExeFile", wt.WCHAR * 260),
    ]


def _win():
    """Bind the Win32 functions once, on first use."""
    global _api
    if _api is None:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        try:
            dwm = ctypes.WinDLL("dwmapi")
        except OSError:
            dwm = None
        k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
        k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
        k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
        k32.OpenProcess.restype = wt.HANDLE
        k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
        k32.CloseHandle.argtypes = [wt.HANDLE]
        u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        u32.GetWindowTextLengthW.argtypes = [wt.HWND]
        u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        u32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        u32.IsWindowVisible.argtypes = [wt.HWND]
        u32.IsIconic.argtypes = [wt.HWND]
        u32.GetWindow.restype = wt.HWND
        u32.GetWindow.argtypes = [wt.HWND, wt.UINT]
        u32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
        u32.IsWindow.argtypes = [wt.HWND]
        u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
        u32.SetForegroundWindow.argtypes = [wt.HWND]
        u32.BringWindowToTop.argtypes = [wt.HWND]
        u32.GetForegroundWindow.restype = wt.HWND
        u32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
        u32.SendInput.argtypes = [wt.UINT, ctypes.c_void_p, ctypes.c_int]
        u32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wt.DWORD, ctypes.c_size_t]
        _api = (k32, u32, dwm)
    return _api


# ------------------------------------------------------------------ processes

def snapshot_processes():
    """{pid: Proc} for every process, via a Toolhelp32 snapshot (no psutil)."""
    k32, _, _ = _win()
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (None, wt.HANDLE(-1).value):
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    procs = {}
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            procs[entry.th32ProcessID] = Proc(entry.th32ProcessID, entry.th32ParentProcessID,
                                              entry.szExeFile)
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return procs


def process_start_time(pid):
    """Creation time as a FILETIME integer, or None when it cannot be read."""
    k32, _, _ = _win()
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        times = [wt.FILETIME() for _ in range(4)]
        if not k32.GetProcessTimes(h, *[ctypes.byref(t) for t in times]):
            return None
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        k32.CloseHandle(h)


def ancestor_chain(pid, procs, start_time=None, max_depth=32):
    """[pid, parent, grandparent, ...] as far as the parent links are real.

    A parent PID is only a number: when the parent has exited, Windows may
    hand that number to an unrelated, newer process. A parent that started
    after its child is therefore not the parent, and the walk stops there.
    """
    start_time = start_time or process_start_time
    chain = [pid]
    seen = {pid}
    child_start = start_time(pid)
    while len(chain) < max_depth:
        proc = procs.get(chain[-1])
        if proc is None or proc.ppid in seen or proc.ppid == 0:
            break
        parent = procs.get(proc.ppid)
        if parent is None:
            break
        parent_start = start_time(parent.pid)
        if child_start is not None and parent_start is not None and parent_start > child_start:
            break
        chain.append(parent.pid)
        seen.add(parent.pid)
        child_start = parent_start
    return chain


def windowed_ancestor(pid, procs, windows_by_pid, start_time=None, stop_exes=STOP_EXES):
    """The first process in pid's ancestry (pid itself included) that owns a
    window, or None. Stops before shell/system processes (STOP_EXES)."""
    for p in ancestor_chain(pid, procs, start_time=start_time):
        proc = procs.get(p)
        if proc is not None and proc.exe.lower() in stop_exes:
            return None
        if windows_by_pid.get(p):
            return p
    return None


# ------------------------------------------------------------------ windows

def _is_cloaked(dwm, hwnd):
    if dwm is None:
        return False
    val = wt.DWORD()
    rc = dwm.DwmGetWindowAttribute(wt.HWND(hwnd), 14, ctypes.byref(val), ctypes.sizeof(val))  # DWMWA_CLOAKED
    return rc == 0 and val.value != 0


def list_windows(procs=None):
    """Visible, titled, unowned top-level windows -- the ones a user would
    call "a window" -- with their process and exe name. Read-only."""
    k32, u32, dwm = _win()
    procs = procs if procs is not None else snapshot_processes()
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def visit(hwnd, _):
        if not u32.IsWindowVisible(hwnd) or u32.GetWindow(hwnd, 4):  # GW_OWNER
            return True
        if u32.GetWindowLongW(hwnd, -20) & 0x80:  # GWL_EXSTYLE & WS_EX_TOOLWINDOW
            return True
        n = u32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        title = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, title, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, cls, 256)
        pid = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = procs.get(pid.value)
        out.append(Window(hwnd=int(hwnd), pid=pid.value, title=title.value, class_name=cls.value,
                          exe=proc.exe if proc else "", minimized=bool(u32.IsIconic(hwnd)),
                          cloaked=_is_cloaked(dwm, hwnd)))
        return True

    u32.EnumWindows(visit, 0)
    return out


def windows_by_pid(windows):
    grouped = {}
    for w in windows:
        grouped.setdefault(w.pid, []).append(w)
    return grouped


# ------------------------------------------------------------------ ranking

def _segments(title):
    """Title split into its ' - ' parts, each stripped of unsaved markers and
    of a trailing parenthetical ('CHANGELOG.md (Working Tree)')."""
    segs = []
    for raw in _TITLE_SPLIT.split(title):
        seg = raw.strip(_DECORATION)
        seg = re.sub(r"\s*\(.*\)\s*$", "", seg).strip(_DECORATION)
        if seg:
            segs.append(seg)
    return segs


def path_match_score(title, path):
    """How strongly a window title names this path. 0 means not at all.

    Whole-segment matches only, never substrings: a folder called "code"
    must not match "Visual Studio Code", and "git-repokit-common" must not
    match a window on "git-repokit-common__extra-targets".

      full path as a segment   10
      the leaf name             5   (file or folder itself)
      its parent folder         2   (VS Code titles name the workspace folder)
      the folder above that     1
    """
    norm = os.path.normcase(os.path.normpath(path))
    parts = [p for p in norm.replace("/", "\\").split("\\") if p and not p.endswith(":")]
    weights = list(zip(reversed(parts), (5, 2, 1)))
    score = 0
    for seg in _segments(title):
        s = os.path.normcase(seg)
        if s.replace("/", "\\").rstrip("\\") == norm.rstrip("\\"):
            score = max(score, 10)
            continue
        for name, weight in weights:
            if s == name:
                score = max(score, weight)
    return score


def rank_windows(windows, path):
    """[(score, Window)] best first; windows that do not name the path are
    kept (score 0) so a caller can still show them."""
    scored = [(path_match_score(w.title, path), w) for w in windows]
    return sorted(scored, key=lambda sw: -sw[0])


def window_title(hwnd):
    _, u32, _ = _win()
    n = u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(max(n, 0) + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


# ------------------------------------------------------------------ focus

@dataclass(frozen=True)
class FocusResult:
    ok: bool
    method: str        # which attempt brought it forward, or why none did
    detail: str = ""


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("mi", _MOUSEINPUT)]


def _try_plain(u32, k32, hwnd):
    u32.SetForegroundWindow(hwnd)


def _try_input_nudge(u32, k32, hwnd):
    # Windows lets the process that sent the last input event take the
    # foreground. A zero-distance relative mouse move is input with no
    # visible effect.
    inp = _INPUT(type=0, mi=_MOUSEINPUT(0, 0, 0, 0x0001, 0, 0))  # INPUT_MOUSE, MOUSEEVENTF_MOVE
    u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
    u32.SetForegroundWindow(hwnd)


def _try_alt_key(u32, k32, hwnd):
    # The long-standing variant of the same rule: tap Alt, then ask.
    u32.keybd_event(0x12, 0, 0, 0)   # VK_MENU down
    u32.keybd_event(0x12, 0, 2, 0)   # VK_MENU up (KEYEVENTF_KEYUP)
    u32.SetForegroundWindow(hwnd)


def _try_attach_input(u32, k32, hwnd):
    # Share input state with the current foreground thread for a moment,
    # which makes this thread allowed to change the foreground.
    fg = u32.GetForegroundWindow()
    fg_tid = u32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = k32.GetCurrentThreadId()
    attached = bool(fg_tid) and fg_tid != me and u32.AttachThreadInput(me, fg_tid, True)
    try:
        u32.BringWindowToTop(hwnd)
        u32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            u32.AttachThreadInput(me, fg_tid, False)


FOCUS_ATTEMPTS = (
    ("plain", _try_plain),
    ("input-nudge", _try_input_nudge),
    ("alt-key", _try_alt_key),
    ("attach-input", _try_attach_input),
)


def focus(hwnd, settle=0.6, attempts=FOCUS_ATTEMPTS, sleep=None, clock=None):
    """Bring a top-level window to the front and confirm it got there.

    Restores it first if minimized. Windows refuses SetForegroundWindow to
    a process that is not already in the foreground, so each entry in
    `attempts` is a progressively stronger way past that rule; after each,
    the foreground is polled for up to `settle` seconds. Returns which
    attempt worked, or ok=False naming the window that kept the focus.
    """
    import time
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    k32, u32, _ = _win()
    if not u32.IsWindow(hwnd):
        return FocusResult(False, "gone", "the window no longer exists")
    if u32.GetForegroundWindow() == hwnd:
        return FocusResult(True, "already")
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, 9)  # SW_RESTORE
    for name, attempt in attempts:
        attempt(u32, k32, hwnd)
        deadline = clock() + settle
        while True:
            if u32.GetForegroundWindow() == hwnd:
                return FocusResult(True, name)
            if clock() >= deadline:
                break
            sleep(0.05)
    fg = u32.GetForegroundWindow()
    return FocusResult(False, "refused", f"Windows kept the focus on \"{window_title(fg) if fg else '?'}\"; "
                                         f"the window's taskbar button may be flashing")


def best_window(windows, path):
    """The single window that best names the path, or None when no window
    names it, or when two tie for the top score. A lone candidate window
    wins even at score 0: there is nothing to disambiguate."""
    if len(windows) == 1:
        return windows[0]
    ranked = rank_windows(windows, path)
    if not ranked or ranked[0][0] == 0:
        return None
    if len(ranked) > 1 and ranked[1][0] == ranked[0][0]:
        return None
    return ranked[0][1]
