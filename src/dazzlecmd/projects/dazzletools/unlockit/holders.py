"""Who holds a path: the lock probe and the holder-detection backends.

Three native signals, chosen by measurement (2026-10-04, unelevated):

- probe_delete(): opens the path asking for DELETE access with full
  sharing, then closes it without deleting. It fails with a sharing
  violation exactly when some other opener withheld delete-sharing, so it
  answers "would delete/rmdir fail?" for files and folders, and changes
  nothing.
- restart_manager_holders(): the Windows Restart Manager, which is what
  Explorer's "file in use" dialog asks. Names the processes that have a
  FILE open or loaded (running exes and DLLs too), in milliseconds, with
  no admin rights. It refuses directories, so a folder is answered by
  registering the files inside it.
- cwd_holders(): processes whose working directory is the folder or
  under it. Nothing else sees these -- Restart Manager does not, and
  handle.exe missed all 7 holders of a folder held by a VS Code window.
  Needs psutil; without it this signal is reported unavailable.

handle.exe (Sysinternals) is an opt-in extra: unelevated, the 2019 and
2022 builds hung for over 25 s on this machine, and the 2026 build missed
the folder above. It always runs under a hard timeout.
"""

import csv
import ctypes
import ctypes.wintypes as wt
import io
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field

ERROR_FILE_NOT_FOUND = 2
ERROR_PATH_NOT_FOUND = 3
ERROR_ACCESS_DENIED = 5
ERROR_SHARING_VIOLATION = 32
ERROR_MORE_DATA = 234

DEFAULT_MAX_FILES = 5000
HANDLE_TIMEOUT = 20


@dataclass(frozen=True)
class Holder:
    pid: int
    exe: str
    reason: str      # "open" (has a file open/loaded) | "cwd" (working directory) | "handle"
    detail: str = ""  # the held file, or the working directory
    source: str = ""  # restart-manager | cwd-scan | handle.exe


@dataclass(frozen=True)
class Probe:
    state: str        # free | in-use | denied | missing | error
    winerror: int = 0


@dataclass
class Gathered:
    path: str
    is_dir: bool
    probe: Probe
    holders: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    uninspected: int = 0   # processes the working-directory scan was denied (unelevated: ~200)


# ------------------------------------------------------------------ probe

def probe_delete(path):
    """Would deleting this path hit a sharing violation? Changes nothing."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wt.HANDLE
    k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID,
                                wt.DWORD, wt.DWORD, wt.HANDLE]
    k32.CloseHandle.argtypes = [wt.HANDLE]
    h = k32.CreateFileW(path, 0x00010000,            # DELETE
                        0x1 | 0x2 | 0x4,             # share read, write, delete
                        None, 3,                     # OPEN_EXISTING
                        0x02000000,                  # FILE_FLAG_BACKUP_SEMANTICS (directories)
                        None)
    if h in (None, wt.HANDLE(-1).value):
        err = ctypes.get_last_error()
        if err == ERROR_SHARING_VIOLATION:
            return Probe("in-use", err)
        if err == ERROR_ACCESS_DENIED:
            return Probe("denied", err)
        if err in (ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND):
            return Probe("missing", err)
        return Probe("error", err)
    k32.CloseHandle(h)
    return Probe("free")


# ------------------------------------------------------------------ Restart Manager

class _RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [("dwProcessId", wt.DWORD), ("ProcessStartTime", wt.FILETIME)]


class _RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", _RM_UNIQUE_PROCESS),
        ("strAppName", wt.WCHAR * 256),
        ("strServiceShortName", wt.WCHAR * 64),
        ("ApplicationType", ctypes.c_int),
        ("AppStatus", wt.ULONG),
        ("TSSessionId", wt.DWORD),
        ("bRestartable", wt.BOOL),
    ]


class RestartManagerError(OSError):
    pass


def _rm_query(files):
    """[(pid, app_name)] for processes holding any of `files`."""
    rm = ctypes.WinDLL("rstrtmgr")
    session = wt.DWORD()
    key = ctypes.create_unicode_buffer(33)
    rc = rm.RmStartSession(ctypes.byref(session), 0, key)
    if rc:
        raise RestartManagerError(rc, "RmStartSession failed")
    try:
        arr = (wt.LPCWSTR * len(files))(*files)
        rc = rm.RmRegisterResources(session, len(files), arr, 0, None, 0, None)
        if rc:
            raise RestartManagerError(rc, "RmRegisterResources failed")
        needed, count, reasons = wt.UINT(), wt.UINT(0), wt.DWORD()
        rc = rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reasons))
        while rc == ERROR_MORE_DATA:
            infos = (_RM_PROCESS_INFO * needed.value)()
            count = wt.UINT(needed.value)
            rc = rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), infos, ctypes.byref(reasons))
            if rc == 0:
                return [(i.Process.dwProcessId, i.strAppName) for i in infos[:count.value]]
        if rc:
            raise RestartManagerError(rc, "RmGetList failed")
        return []
    finally:
        rm.RmEndSession(session)


def restart_manager_holders(files, per_file_limit=64):
    """Holders of any of `files`. With few files, each is asked about on its
    own so the report can say which file a process holds; with many, they
    are asked about in one batch and the held file is not named."""
    if not files:
        return []
    if len(files) <= per_file_limit:
        found = []
        for f in files:
            found += [Holder(pid, name, "open", f, "restart-manager") for pid, name in _rm_query([f])]
        return found
    return [Holder(pid, name, "open", "", "restart-manager") for pid, name in _rm_query(files)]


def files_under(root, limit=DEFAULT_MAX_FILES):
    """(files, truncated): regular files under root, never crossing a
    junction or symlink -- those lead outside the folder being deleted."""
    files, stack = [], [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                continue
            if stat.S_ISDIR(st.st_mode):
                stack.append(e.path)
            else:
                files.append(e.path)
                if len(files) >= limit:
                    return files, True
    return files, False


# ------------------------------------------------------------------ working directories

def cwd_holders(path, exclude_pids=()):
    """(holders, denied): processes whose working directory is path or
    under it, and how many processes could not be inspected. Returns None
    when psutil is not installed."""
    try:
        import psutil
    except ImportError:
        return None
    target = os.path.normcase(os.path.abspath(path)).rstrip("\\")
    found, denied = [], 0
    for proc in psutil.process_iter(["pid", "name"]):
        if proc.info["pid"] in exclude_pids:
            continue
        try:
            cwd = proc.cwd()
        except psutil.AccessDenied:
            denied += 1
            continue
        except (psutil.Error, OSError):
            continue
        norm = os.path.normcase(cwd).rstrip("\\")
        if norm == target or norm.startswith(target + "\\"):
            found.append(Holder(proc.info["pid"], proc.info["name"] or "", "cwd", cwd, "cwd-scan"))
    return found, denied


# ------------------------------------------------------------------ handle.exe (opt-in)

def find_handle_exe(explicit=None):
    """An explicit path, else handle64.exe / handle.exe on PATH."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for name in ("handle64.exe", "handle.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def parse_handle_csv(text):
    """Holders from `handle -v` output (CSV: Process,PID,Type,Handle,Name)."""
    found = []
    rows = csv.reader(io.StringIO(text))
    for row in rows:
        if len(row) < 5 or not row[1].strip().isdigit():
            continue  # header, banner, "No matching handles found."
        found.append(Holder(int(row[1]), row[0].strip(), "handle", row[4].strip(), "handle.exe"))
    return found


def handle_holders(path, exe, timeout=HANDLE_TIMEOUT, run=subprocess.run):
    """Holders according to handle.exe. Raises subprocess.TimeoutExpired
    when it hangs, which unelevated builds do."""
    r = run([exe, "-accepteula", "-nobanner", "-v", path], capture_output=True, text=True,
            timeout=timeout, stdin=subprocess.DEVNULL)
    return parse_handle_csv(r.stdout)


# ------------------------------------------------------------------ all together

def gather(path, use_handle=False, handle_exe=None, max_files=DEFAULT_MAX_FILES, exclude_pids=()):
    """Probe the path and ask every backend who holds it."""
    path = os.path.abspath(path)
    is_dir = os.path.isdir(path)
    g = Gathered(path=path, is_dir=is_dir, probe=probe_delete(path))
    if g.probe.state == "missing":
        return g

    if is_dir:
        files, truncated = files_under(path, max_files)
        if truncated:
            g.notes.append(f"only the first {max_files} files inside were checked for open handles "
                           f"(--max-files to raise)")
    else:
        files = [path]
    try:
        g.holders += [h for h in restart_manager_holders(files) if h.pid not in exclude_pids]
    except RestartManagerError as e:
        g.notes.append(f"Restart Manager could not answer ({e})")

    if is_dir:
        res = cwd_holders(path, exclude_pids)
        if res is None:
            g.notes.append("working-directory check unavailable: install psutil to see processes "
                           "whose current directory is inside this folder")
        else:
            found, g.uninspected = res
            g.holders += found

    if use_handle:
        exe = find_handle_exe(handle_exe)
        if exe is None:
            g.notes.append("--handle: handle.exe not found (put handle64.exe on PATH or pass --handle-exe)")
        else:
            try:
                g.holders += [h for h in handle_holders(path, exe) if h.pid not in exclude_pids]
            except subprocess.TimeoutExpired:
                g.notes.append(f"--handle: {os.path.basename(exe)} gave no answer in {HANDLE_TIMEOUT}s "
                               f"(older builds hang when not elevated)")
            except OSError as e:
                g.notes.append(f"--handle: could not run {exe} ({e})")
    return g
