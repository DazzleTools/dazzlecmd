"""POC-1 (collab round 1, consultant): does a .cmd file's `cd /d` persist in the
calling cmd, what does setlocal do to it, and which wrapper shape applies a
directory emitted by a child program safely under `cmd /V:ON` and `/V:OFF`?

Safe: works only inside a fresh temp folder; runs cmd.exe and python only.
Usage: python poc1_cmd_cd_and_wrapper.py
"""
import json, os, subprocess, sys, tempfile

root = tempfile.mkdtemp(prefix="relaunch_poc1_")
start = os.path.join(root, "start"); os.mkdir(start)
targets = {
    "plain": "plain",
    "space_amp": "has space & amp",
    "bang": "bang!dir!x",
    "pct": "pct%TEMP%dir",
    "caret_paren": "c^aret (paren)",
    "semi": ";leading-semicolon",
    "unicode": "ünï-日本",
}
tpaths = {}
for k, name in targets.items():
    p = os.path.join(root, name); os.mkdir(p); tpaths[k] = p
json.dump(tpaths, open(os.path.join(root, "map.json"), "w", encoding="utf-8"))

emit = os.path.join(root, "fake_emit.py")
open(emit, "w", encoding="utf-8").write(r'''
import json, os, sys
m = json.load(open(os.path.join(os.path.dirname(__file__), "map.json"), encoding="utf-8"))
args = sys.argv[1:]
if args[0] == "--file":
    enc = args[1]; out = args[2]; key = args[3]
    with open(out, "w", encoding=enc, newline="\r\n") as f:
        f.write(m[key] + "\n")
else:
    enc = args[0]; key = args[1]
    sys.stdout.buffer.write((m[key] + "\r\n").encode(enc, "replace"))
''')
here = os.path.join(root, "here.py")
open(here, "w").write("import os;print('CWD=' + ascii(os.getcwd()))\n")

def w(name, body):
    p = os.path.join(root, name)
    open(p, "w", encoding="ascii", newline="\r\n").write(body)
    return p

py = sys.executable
# --- part 1: raw batch semantics -------------------------------------------
w("x_plain.cmd", '@cd /d "%~1"\n')
w("x_setlocal.cmd", '@setlocal\n@cd /d "%~1"\n')
w("x_tunnel.cmd", '@setlocal\n@set "T=%~1"\n@endlocal & cd /d "%T%"\n')
# --- part 2: wrappers --------------------------------------------------------
w("wrap_forf.cmd",
  '@echo off\n'
  'for /f "usebackq delims=" %%D in (`""' + py + '" "' + emit + '" %2 %1"`) do cd /d "%%D"\n')
w("wrap_file.cmd",
  '@echo off\n'
  'set "DZR_OUT=%TEMP%\dzr-%RANDOM%-%RANDOM%.txt"\n'
  '"' + py + '" "' + emit + '" --file %2 "%DZR_OUT%" %1\n'
  'if errorlevel 1 goto :dzr_done\n'
  'if not exist "%DZR_OUT%" goto :dzr_done\n'
  'set "DZR_DIR="\n'
  'set /p DZR_DIR=<"%DZR_OUT%"\n'
  'del "%DZR_OUT%" >nul 2>&1\n'
  'if not defined DZR_DIR goto :dzr_done\n'
  'if "!!"=="" goto :dzr_delayed\n'
  'cd /d "%DZR_DIR%"\n'
  'goto :dzr_done\n'
  ':dzr_delayed\n'
  'cd /d "!DZR_DIR!"\n'
  ':dzr_done\n'
  'set "DZR_OUT="\n'
  'set "DZR_DIR="\n')

def run(vflag, inner):
    inner = inner.replace("@B@", root + os.sep)
    line = 'cmd /d /E:ON %s /s /c "cd /d "%s" & %s & "%s" "%s""' % (vflag, start, inner, py, here)
    r = subprocess.run(line, capture_output=True, cwd=root)
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("oem", "replace")
    got = [l for l in out.splitlines() if l.startswith("CWD=")]
    return (got[-1][4:] if got else "<none>"), out

def verdict(got, want):
    return "MOVED" if got == ascii(want) else ("STAYED" if got == ascii(start) else "OTHER " + got)

print("root:", root)
print("\n== part 1: batch cd semantics (target=plain) ==")
for v in ("/V:OFF", "/V:ON"):
    for b in ("x_plain.cmd", "x_setlocal.cmd", "x_tunnel.cmd"):
        got, _ = run(v, 'call "@B@%s" "%s"' % (b, tpaths["plain"]))
        print("%-7s call %-15s -> %s" % (v, b, verdict(got, tpaths["plain"])))
    got, _ = run(v, '"@B@%s" "%s"' % ("x_plain.cmd", tpaths["plain"]))
    print("%-7s (no call) x_plain.cmd -> %s   [note: without `call`, control never returns to the & chain]" % (v, verdict(got, tpaths["plain"])))

print("\n== part 2: wrappers, per target ==")
for wrap, encs in (("wrap_forf.cmd", ("oem", "utf-8")), ("wrap_file.cmd", ("oem", "utf-8"))):
    for enc in encs:
        for v in ("/V:OFF", "/V:ON"):
            row = []
            for k in targets:
                got, out = run(v, 'call "@B@%s" %s %s' % (wrap, k, enc))
                row.append("%s=%s" % (k, verdict(got, tpaths[k]).split()[0]))
            if "--debug" in sys.argv: print(out)
            print("%-14s enc=%-5s %-7s %s" % (wrap, enc, v, "  ".join(row)))
