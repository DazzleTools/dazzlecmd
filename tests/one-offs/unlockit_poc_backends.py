"""POC for unlockit: which lock-detection backend sees what, and how fast.

Spawns two short-lived child processes (our own, killed at the end, and
each exits on its own after 60 s regardless):
  - one holding a file open (Python's open() omits FILE_SHARE_DELETE, so
    delete/rename of that file fails -- the classic "file in use")
  - one whose working directory is a folder (blocks deleting the folder)

Then asks each backend who holds them:
  - Restart Manager (rstrtmgr.dll via ctypes) -- what Explorer's "file in
    use" dialog uses; no admin, no external binary
  - handle64.exe -nobanner -v <path> -- Sysinternals, needs admin to see
    other processes' handles

Finally maps PIDs to top-level windows (read-only: EnumWindows only, no
focus or close). Run: python tests/one-offs/unlockit_poc_backends.py
"""
import ctypes
import ctypes.wintypes as wt
import os
import shutil
import subprocess
import sys
import tempfile
import time

# The 2022 handle64.exe and 2019 handle.exe both hang >25 s unelevated on
# this machine; the 2026 build answers at once. Measured 2026-10-04.
HANDLE_EXE = r"Z:\wintools\handle64.2026.01.05.exe"

# ---------------------------------------------------------------- Restart Manager
CCH_RM_SESSION_KEY = 32
CCH_RM_MAX_APP_NAME = 255
CCH_RM_MAX_SVC_NAME = 63
ERROR_MORE_DATA = 234


class RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [("dwProcessId", wt.DWORD), ("ProcessStartTime", wt.FILETIME)]


class RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", RM_UNIQUE_PROCESS),
        ("strAppName", wt.WCHAR * (CCH_RM_MAX_APP_NAME + 1)),
        ("strServiceShortName", wt.WCHAR * (CCH_RM_MAX_SVC_NAME + 1)),
        ("ApplicationType", ctypes.c_int),
        ("AppStatus", wt.ULONG),
        ("TSSessionId", wt.DWORD),
        ("bRestartable", wt.BOOL),
    ]


RM_APP_TYPES = {0: "Unknown", 1: "MainWindow", 2: "OtherWindow", 3: "Service",
                4: "Explorer", 5: "Console", 1000: "Critical"}


def rm_who_holds(paths):
    rm = ctypes.WinDLL("rstrtmgr")
    session = wt.DWORD()
    key = ctypes.create_unicode_buffer(CCH_RM_SESSION_KEY + 1)
    rc = rm.RmStartSession(ctypes.byref(session), 0, key)
    if rc:
        return f"RmStartSession rc={rc}"
    try:
        arr = (wt.LPCWSTR * len(paths))(*paths)
        rc = rm.RmRegisterResources(session, len(paths), arr, 0, None, 0, None)
        if rc:
            return f"RmRegisterResources rc={rc}"
        needed, count, reasons = wt.UINT(), wt.UINT(0), wt.DWORD()
        rc = rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reasons))
        if rc not in (0, ERROR_MORE_DATA):
            return f"RmGetList rc={rc}"
        if needed.value == 0:
            return []
        infos = (RM_PROCESS_INFO * needed.value)()
        count = wt.UINT(needed.value)
        rc = rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), infos, ctypes.byref(reasons))
        if rc:
            return f"RmGetList(2) rc={rc}"
        return [(i.Process.dwProcessId, i.strAppName, RM_APP_TYPES.get(i.ApplicationType, i.ApplicationType),
                 i.strServiceShortName) for i in infos[:count.value]]
    finally:
        rm.RmEndSession(session)


# ---------------------------------------------------------------- handle64
def handle_who_holds(path):
    if not os.path.exists(HANDLE_EXE):
        return "handle64 not found"
    r = subprocess.run([HANDLE_EXE, "-accepteula", "-nobanner", "-v", path],
                       capture_output=True, text=True, timeout=25,
                       stdin=subprocess.DEVNULL)
    return f"rc={r.returncode}\n{r.stdout.strip()}\n{r.stderr.strip()}".strip()


# ---------------------------------------------------------------- delete probe
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateFileW.restype = wt.HANDLE
kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
DELETE = 0x00010000
SHARE_ALL = 0x1 | 0x2 | 0x4
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000  # needed to open a directory
INVALID_HANDLE_VALUE = wt.HANDLE(-1).value


def probe_delete_access(path):
    """Would a delete/rmdir hit a sharing violation? Opens with DELETE access
    and full sharing, then closes WITHOUT setting delete disposition -- the
    open fails (winerror 32) only if some other opener withheld
    FILE_SHARE_DELETE. Changes nothing."""
    h = kernel32.CreateFileW(path, DELETE, SHARE_ALL, None, OPEN_EXISTING,
                             FILE_FLAG_BACKUP_SEMANTICS, None)
    if h == INVALID_HANDLE_VALUE:
        return f"BLOCKED winerror={ctypes.get_last_error()}"
    kernel32.CloseHandle(h)
    return "free (delete access granted)"


def cwd_holders(path):
    """Processes whose working directory is the path or inside it."""
    try:
        import psutil
    except ImportError:
        return "psutil not installed"
    target = os.path.normcase(os.path.abspath(path))
    hits = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            cwd = os.path.normcase(p.cwd())
        except (psutil.Error, OSError):
            continue
        if cwd == target or cwd.startswith(target + os.sep):
            hits.append((p.info["pid"], p.info["name"], cwd))
    return hits


def report(label, p):
    print(f"\n===== {label}: {p}")
    print(f"[probe] {probe_delete_access(p)}")
    t = time.perf_counter()
    print(f"[RM] {time.perf_counter() - t:.3f}s -> {rm_who_holds([p])}")
    t = time.perf_counter()
    res = cwd_holders(p)
    print(f"[cwd scan] {time.perf_counter() - t:.3f}s -> {res}")
    t = time.perf_counter()
    try:
        res = handle_who_holds(p)
    except subprocess.TimeoutExpired:
        res = "TIMEOUT"
    print(f"[handle64] {time.perf_counter() - t:.3f}s ->\n{res}")


# ---------------------------------------------------------------- windows
user32 = ctypes.WinDLL("user32", use_last_error=True)
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def windows_for_pids(pids):
    out = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            out.append((pid.value, hwnd, cls.value, buf.value))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def main():
    tmp = tempfile.mkdtemp(prefix="unlockit-poc-")
    f = os.path.join(tmp, "LOCKED-7731.md")
    d = os.path.join(tmp, "busy-dir")
    os.makedirs(d)
    with open(f, "w") as fh:
        fh.write("x")
    holder = subprocess.Popen([sys.executable, "-c",
                               f"import time; h=open(r'{f}'); time.sleep(60)"])
    sitter = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=d)
    time.sleep(1.0)
    print(f"holder pid={holder.pid}  (file)   sitter pid={sitter.pid}  (cwd)")
    try:
        try:
            os.remove(f)
            print("file delete: SUCCEEDED (not locked?)")
        except OSError as e:
            print(f"file delete: {e.__class__.__name__} winerror={getattr(e, 'winerror', None)}")
        for label, p in (("file", f), ("dir", d)):
            report(label, p)
        for p in sys.argv[1:]:  # real-world targets, read-only probes only
            report("target", p)
        # window mapping, read-only, on whatever processes hold Typora windows
        typora = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Typora.exe", "/FO", "CSV", "/NH"],
                                capture_output=True, text=True).stdout
        pids = {int(line.split('","')[1]) for line in typora.splitlines() if line.startswith('"Typora')}
        print(f"\n[windows] Typora pids: {sorted(pids)}")
        for w in windows_for_pids(pids):
            print(f"  pid={w[0]} hwnd={w[1]:#x} class={w[2]!r} title={w[3]!r}")
    finally:
        for p in (holder, sitter):
            p.kill()
            p.wait()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
