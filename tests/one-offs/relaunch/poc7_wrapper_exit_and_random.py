"""POC-7 (collab round 2, consultant):
 1) the wrapper's `set "DZR_RC=%ERRORLEVEL%"` ... `exit /b %DZR_RC%` lines, under
    /V:ON, typed at a prompt (commands fed on stdin) and `call`ed from a batch:
    does the shell survive, is ERRORLEVEL the child's code, did the cd apply?
 2) do cmd processes started together produce the same %RANDOM%-%RANDOM%?
 3) does a mkdir-claimed temp folder give each of 25 simultaneous wrappers its own?
Safe: temp folders only; runs cmd.exe and python.
Usage: python poc7_wrapper_exit_and_random.py [--debug]
"""
import collections
import os
import subprocess
import sys
import tempfile

BS = chr(92)   # backslash, kept out of string literals on purpose
NL = chr(10)

root = tempfile.mkdtemp(prefix="relaunch_poc7_")
target = os.path.join(root, "target dir")
os.mkdir(target)
start = os.path.join(root, "start")
os.mkdir(start)
py = sys.executable
fake = os.path.join(root, "fakedz.py")
with open(fake, "w") as fh:
    fh.write(NL.join([
        "import os, sys",
        "f = os.environ.get('DZ_RELAUNCH_CD_FILE')",
        "code = int(sys.argv[1]); write = sys.argv[2] == 'w'",
        "if f and write:",
        "    open(f, 'w').write(%r + chr(10))" % target,
        "sys.exit(code)",
        "",
    ]))


def wrapper(name, pick_file_lines, cleanup_lines):
    body = ["@echo off"] + pick_file_lines + [
        '"%s" "%s" %%*' % (py, fake),
        'set "DZR_RC=%ERRORLEVEL%"',
        'if not exist "%DZ_RELAUNCH_CD_FILE%" goto :dzr_done',
        'set "DZR_DIR="',
        'set /p DZR_DIR=<"%DZ_RELAUNCH_CD_FILE%"',
        'del "%DZ_RELAUNCH_CD_FILE%" >nul 2>&1',
        'if not defined DZR_DIR goto :dzr_done',
        'if "!!"=="" goto :dzr_delayed',
        'cd /d "%DZR_DIR%"',
        'goto :dzr_done',
        ':dzr_delayed',
        'cd /d "!DZR_DIR!"',
        ':dzr_done'] + cleanup_lines + [
        'set "DZ_RELAUNCH_CD_FILE="',
        'set "DZR_DIR="',
        'exit /b %DZR_RC%']
    p = os.path.join(root, name)
    with open(p, "w", newline="\r\n") as f:
        f.write(NL.join(body) + NL)
    return p


w_rand = wrapper("dzr_rand.cmd",
                 ['set "DZ_RELAUNCH_CD_FILE=%TEMP%' + BS + 'dzr-%RANDOM%-%RANDOM%.txt"'], [])
w_mk = wrapper("dzr_mk.cmd", [
    ':dzr_mk',
    'set "DZR_TMP=%TEMP%' + BS + 'dzr-%RANDOM%-%RANDOM%"',
    'mkdir "%DZR_TMP%" 2>nul || goto :dzr_mk',
    'set "DZ_RELAUNCH_CD_FILE=%DZR_TMP%' + BS + 'cd.txt"'],
    ['rmdir "%DZR_TMP%" >nul 2>&1', 'set "DZR_TMP="'])

debug = "--debug" in sys.argv
print("root:", root)
print("== 1) exit /b and ERRORLEVEL, /V:ON ==")


def summarize(kind, wname, code, wr, out):
    if debug:
        print(repr(out))
    lines = [l.strip() for l in out.replace("\r", "").split(NL)]
    rc = [l for l in lines if l.startswith("RC=")]
    cwd = "target" if target in lines else ("start" if start in lines else "?")
    leak = [l for l in lines if l.startswith("VARS=")]
    print("  %-6s %-5s child=%d wrote=%s -> %s alive=%s cwd=%s %s"
          % (kind, wname, code, wr, rc[-1] if rc else "RC=?", "ALIVE" in lines, cwd,
             leak[-1] if leak else ""))


for wname, wp in (("rand", w_rand), ("mkdir", w_mk)):
    for code, wr in ((0, "w"), (7, "w"), (3, "n")):
        # typed at the prompt: cmd reads these lines from stdin, as an interactive shell does
        script = "\r\n".join([
            "@echo off",
            'cd /d "%s"' % start,
            '"%s" %d %s' % (wp, code, wr),
            "echo RC=%ERRORLEVEL%",
            "echo ALIVE",
            "cd",
            "echo VARS=[%DZR_RC%][%DZR_DIR%][%DZ_RELAUNCH_CD_FILE%]",
            ""])
        r = subprocess.run("cmd /d /E:ON /V:ON", input=script.encode(), capture_output=True, cwd=root)
        summarize("typed", wname, code, wr, r.stdout.decode("oem", "replace"))
        # called from another batch file
        caller = os.path.join(root, "caller.cmd")
        with open(caller, "w", newline="\r\n") as f:
            f.write(NL.join([
                "@echo off",
                'cd /d "%s"' % start,
                'call "%s" %d %s' % (wp, code, wr),
                "echo RC=%ERRORLEVEL%",
                "echo ALIVE",
                "cd",
                ""]))
        r = subprocess.run('cmd /d /E:ON /V:ON /c "%s"' % caller, capture_output=True, cwd=root)
        summarize("called", wname, code, wr, r.stdout.decode("oem", "replace"))

print("== 2) %RANDOM%-%RANDOM% from 25 cmd started together, 4 rounds ==")
for rnd in range(4):
    ps = [subprocess.Popen("cmd /d /c echo %RANDOM%-%RANDOM%", stdout=subprocess.PIPE) for _ in range(25)]
    vals = [p.communicate()[0].decode().strip() for p in ps]
    c = collections.Counter(vals)
    print("  round %d: %d distinct of 25; largest group sharing one value: %d"
          % (rnd, len(c), max(c.values())))

print("== 3) mkdir-claimed temp folder, 25 wrappers started together ==")
probe = os.path.join(root, "mkprobe.cmd")
with open(probe, "w", newline="\r\n") as f:
    f.write(NL.join([
        "@echo off",
        ":dzr_mk",
        'set "DZR_TMP=%TEMP%' + BS + 'dzrprobe-%RANDOM%-%RANDOM%"',
        'mkdir "%DZR_TMP%" 2>nul || goto :dzr_mk',
        "echo %DZR_TMP%",
        "ping -n 2 127.0.0.1 >nul",
        'rmdir "%DZR_TMP%"',
        ""]))
for rnd in range(3):
    ps = [subprocess.Popen('cmd /d /c "%s"' % probe, stdout=subprocess.PIPE) for _ in range(25)]
    vals = [p.communicate()[0].decode().strip() for p in ps]
    print("  round %d: %d distinct folders of 25" % (rnd, len(set(vals))))
