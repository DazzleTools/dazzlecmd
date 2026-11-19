"""POC-4 (collab round 1, consultant): what happens to a stored argv list when
the program is a .cmd shim (npm style) and it is run with subprocess, no shell?

Safe: temp folder only; runs python and cmd.exe on a shim that only echoes argv.
"""
import json, os, shutil, subprocess, sys, tempfile

root = tempfile.mkdtemp(prefix="relaunch_poc4_")
echo = os.path.join(root, "echoargs.py")
open(echo, "w").write("import sys, json; print('ARGV=' + json.dumps(sys.argv[1:]))\n")
shim = os.path.join(root, "myshim.cmd")
open(shim, "w", newline="\r\n").write('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, echo))
# npm also writes an extensionless POSIX script beside the .cmd
open(os.path.join(root, "myshim"), "w", newline="\n").write("#!/bin/sh\nexit 0\n")

env = dict(os.environ); env["PATH"] = root + os.pathsep + env["PATH"]
print("python", sys.version.split()[0])
print("shutil.which('myshim') ->", shutil.which("myshim", path=env["PATH"]))
for name in ("codex", "pi", "claude", "csb"):
    print("shutil.which(%r) -> %s" % (name, shutil.which(name)))

def attempt(label, argv0, args):
    try:
        r = subprocess.run([argv0] + args, capture_output=True, text=True, env=env, timeout=20)
        got = [l for l in r.stdout.splitlines() if l.startswith("ARGV=")]
        if got:
            back = json.loads(got[-1][5:])
            print("  %-34s %s  %s" % (label, "SAME" if back == args else "DIFFERENT", "" if back == args else "-> %r" % (back,)))
        else:
            print("  %-34s NO-ARGV rc=%s out=%r err=%r" % (label, r.returncode, r.stdout[:120], r.stderr[:160]))
    except Exception as e:
        print("  %-34s EXC %s: %s" % (label, type(e).__name__, e))

cases = {
    "plain": ["resume", "--last"],
    "space": ["--msg", "hello world"],
    "amp": ["a&b"],
    "amp+space": ["a & b"],
    "pipe": ["x|y"],
    "percent": ["%TEMP%"],
    "caret": ["a^b"],
    "bang": ["wow!"],
    "quote": ['say "hi"'],
    "inject": ['x" & echo INJECTED & rem "'],
    "lt-gt": ["a<b>c"],
    "dashdash": ["--", "-x"],
}
print("\nbare name `myshim` (only .cmd + POSIX script on PATH), no shell:")
attempt("plain", "myshim", cases["plain"])
print("\nfull path to myshim.cmd, list argv, no shell (CreateProcess routes via cmd.exe):")
for k, a in cases.items():
    attempt(k, shim, a)
print("\ncontrol: python.exe directly with the same args (a real .exe):")
for k, a in cases.items():
    attempt(k, sys.executable, [echo] + a) if False else None
r_ok = 0
for k, a in cases.items():
    r = subprocess.run([sys.executable, echo] + a, capture_output=True, text=True)
    back = json.loads(r.stdout.strip()[5:]); r_ok += (back == a)
print("  %d/%d SAME" % (r_ok, len(cases)))
