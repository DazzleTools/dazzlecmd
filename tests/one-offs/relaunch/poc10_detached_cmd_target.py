"""poc10 -- does a detached Popen work when the target is a .cmd (like VS Code's code.cmd)?

Question (collab 2026-11-19 detach-and-install, Q3): the design starts detached members with
DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP. Prediction to falsify: "a .cmd target runs, gets its
arguments, returns at once, shows no console window, and does not hold the caller's pipes".

Harmless: every target is a .cmd in a temp folder that runs a probe which writes a JSON file.
Never starts VS Code. Run: python poc10_detached_cmd_target.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

PROBE = r'''
import ctypes, json, os, sys, time
k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
k32.GetConsoleWindow.restype = ctypes.c_void_p
hwnd = k32.GetConsoleWindow()
out = sys.argv[1]
info = {"argv": sys.argv[2:], "cwd": os.getcwd(), "console_hwnd": bool(hwnd),
        "console_visible": bool(hwnd and u32.IsWindowVisible(ctypes.c_void_p(hwnd))),
        "cd_file_env": os.environ.get("DZ_RELAUNCH_CD_FILE"),
        "stdout_ok": None}
try:
    sys.stdout.write("x"); sys.stdout.flush(); info["stdout_ok"] = True
except Exception as e:
    info["stdout_ok"] = repr(e)
json.dump(info, open(out, "w"))
time.sleep(4)
json.dump(dict(info, survived=True), open(out, "w"))
'''

LAUNCHER = r'''
import os, subprocess, sys, time
variant, target, out, cwd = sys.argv[1:5]
D, G, NW = subprocess.DETACHED_PROCESS, subprocess.CREATE_NEW_PROCESS_GROUP, subprocess.CREATE_NO_WINDOW
kw = {"design":        dict(creationflags=D | G, close_fds=True),
      "design+devnull": dict(creationflags=D | G, close_fds=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
      "nowindow":      dict(creationflags=NW | G, close_fds=True),
      "nowindow+devnull": dict(creationflags=NW | G, close_fds=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
      "plain":         dict()}[variant]
t = time.time()
p = subprocess.Popen([target, out, "arg with space", "second"], cwd=cwd, **kw)
print(f"popen returned in {time.time()-t:.3f}s pid={p.pid}")
'''


def main():
    root = tempfile.mkdtemp(prefix="dzr-poc10-")
    probe = os.path.join(root, "probe.py")
    launcher = os.path.join(root, "launcher.py")
    open(probe, "w").write(PROBE)
    open(launcher, "w").write(LAUNCHER)
    target = os.path.join(root, "fake code.cmd")          # a space in the path, like Program Files
    open(target, "w").write('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, probe))
    work = os.path.join(root, "work dir")
    os.mkdir(work)
    rows = []
    for variant in ("design", "design+devnull", "nowindow", "nowindow+devnull", "plain"):
        out = os.path.join(root, variant.replace("+", "_") + ".json")
        t = time.time()
        # the caller holds pipes, as a test harness / `for /f` / an agent's shell tool would
        r = subprocess.run([sys.executable, launcher, variant, target, out, work],
                           capture_output=True, text=True, timeout=30,
                           env=dict(os.environ, DZ_RELAUNCH_CD_FILE=r"C:\gone\cd.txt"))
        caller_s = time.time() - t
        first = None
        for _ in range(20):
            if os.path.exists(out):
                try:
                    first = json.load(open(out)); break
                except ValueError:
                    pass
            time.sleep(0.1)
        time.sleep(5)
        final = json.load(open(out)) if os.path.exists(out) else None
        rows.append((variant, r.returncode, r.stdout.strip(), r.stderr.strip()[:200], round(caller_s, 2), first, final))
    for row in rows:
        v, rc, so, se, cs, first, final = row
        print(f"\n== {v}\n  launcher rc={rc} {so} {se}\n  caller (holding pipes) got control back after {cs}s")
        print(f"  probe: {final}")
    print("\nroot:", root)


if __name__ == "__main__":
    main()
