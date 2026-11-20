"""poc12 -- poc10 with a GUI-subsystem grandchild (pythonw.exe), the shape of VS Code's code.cmd
(code.cmd runs Code.exe, PE subsystem 2). Does any console host appear in the started tree?

Harmless: a .cmd in a temp folder runs pythonw on a probe that writes a file, sleeps 3 s, exits.
Detection: a ToolHelp snapshot taken while the probe sleeps; a conhost.exe / OpenConsole.exe whose
parent is in the started tree means a console was allocated for it.
"""
import ctypes, os, subprocess, sys, tempfile, time
from ctypes import wintypes

class PE32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("pid", wintypes.DWORD),
                ("heap", ctypes.c_void_p), ("mod", wintypes.DWORD), ("threads", wintypes.DWORD),
                ("ppid", wintypes.DWORD), ("pri", wintypes.LONG), ("flags", wintypes.DWORD), ("exe", ctypes.c_char * 260)]

def table():
    k = ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    h = k.CreateToolhelp32Snapshot(2, 0)
    e = PE32(); e.dwSize = ctypes.sizeof(PE32); out = []
    ok = k.Process32First(ctypes.c_void_p(h), ctypes.byref(e))
    while ok:
        out.append((e.pid, e.ppid, e.exe.decode(errors="replace").lower()))
        ok = k.Process32Next(ctypes.c_void_p(h), ctypes.byref(e))
    k.CloseHandle(ctypes.c_void_p(h))
    return out

def tree(root, t):
    pids, grew = {root}, True
    while grew:
        grew = False
        for pid, ppid, _ in t:
            if ppid in pids and pid not in pids:
                pids.add(pid); grew = True
    return [(p, pp, n) for p, pp, n in t if p in pids]

root = tempfile.mkdtemp(prefix="dzr-poc12-")
probe = os.path.join(root, "probe.py")
open(probe, "w").write("import sys,time\nopen(sys.argv[1],'w').write(' '.join(sys.argv[2:]))\ntime.sleep(3)\n")
D, G, NW = subprocess.DETACHED_PROCESS, subprocess.CREATE_NEW_PROCESS_GROUP, subprocess.CREATE_NO_WINDOW
for child_name, child in (("pythonw (GUI, like Code.exe)", sys.executable.replace("python.exe", "pythonw.exe")),
                          ("python (console)", sys.executable)):
    target = os.path.join(root, "fake code.cmd")
    open(target, "w").write('@echo off\r\nsetlocal\r\n"%s" "%s" %%*\r\nendlocal\r\n' % (child, probe))
    for name, flags in (("DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP", D | G), ("CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP", NW | G)):
        out = os.path.join(root, "out.txt")
        if os.path.exists(out): os.remove(out)
        p = subprocess.Popen([target, out, "C:/some folder"], creationflags=flags, close_fds=True)
        time.sleep(1.5)
        names = sorted(n for _, _, n in tree(p.pid, table()))
        p.wait(timeout=20)
        print(f"{child_name:30} {name:44} tree={names} ran={os.path.exists(out)} rc={p.returncode}")
