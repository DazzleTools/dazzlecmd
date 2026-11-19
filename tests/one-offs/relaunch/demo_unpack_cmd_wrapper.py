"""Demo for /unpack-test: why a child process can't cd its parent cmd, and how a
.cmd wrapper with a temp-file hand-over does it. Writes only under a fresh temp dir.

Each case is a "tab": one batch file run by one cmd process, line by line, so
`echo %CD%` at the end shows where that tab ended up. The target folder name
contains a space, '&' and '!' and reaches the fake dz through an environment
variable (DEMO_TARGET), the way the real dz would read it from a group file --
it never appears on a command line.

Run: python tests/one-offs/relaunch/demo_unpack_cmd_wrapper.py
"""
import os
import subprocess
import sys
import tempfile

root = tempfile.mkdtemp(prefix="relaunch_demo_")
start = os.path.join(root, "start")
target = os.path.join(root, "proj with space & bang!")
os.makedirs(start)
os.makedirs(target)

# Stand-in for `dz relaunch claim`: tries os.chdir (to show it does not stick),
# prints the folder to stdout when DEMO_EMIT=1 (the for /f style), and writes
# it to DZ_RELAUNCH_CD_FILE when that is set (the temp-file style).
fake_dz = os.path.join(root, "fake_dz.py")
with open(fake_dz, "w", encoding="utf-8") as f:
    f.write(
        "import os,sys\n"
        "t=os.environ['DEMO_TARGET']\n"
        "if not os.path.isdir(t):\n"
        "    print('fake dz: no such folder', file=sys.stderr); sys.exit(3)\n"
        "os.chdir(t)\n"
        "print('  (child says: my own cwd is now', os.path.basename(os.getcwd()) + ')', file=sys.stderr)\n"
        "if os.environ.get('DEMO_EMIT'): print(t)\n"
        "p=os.environ.get('DZ_RELAUNCH_CD_FILE')\n"
        "if p: open(p,'w',encoding='mbcs').write(t+'\\n')\n"
    )
py = sys.executable
dz = f'"{py}" "{fake_dz}"'


def write(name, body):
    path = os.path.join(root, name)
    with open(path, "w", encoding="ascii", newline="\r\n") as f:
        f.write(body)
    return path


# What the real `dz relaunch shell-init cmd` would print, with `dz relaunch claim %*`
# replaced by the fake.
dzr = write(
    "dzr.cmd",
    "@echo off\n"
    'set "DZ_RELAUNCH_CD_FILE=%TEMP%\\dzr-%RANDOM%-%RANDOM%.txt"\n'
    f"{dz} %*\n"
    'set "DZR_RC=%ERRORLEVEL%"\n'
    'if not exist "%DZ_RELAUNCH_CD_FILE%" goto :dzr_done\n'
    'set "DZR_DIR="\n'
    'set /p DZR_DIR=<"%DZ_RELAUNCH_CD_FILE%"\n'
    'del "%DZ_RELAUNCH_CD_FILE%" >nul 2>&1\n'
    "if not defined DZR_DIR goto :dzr_done\n"
    'if "!!"=="" goto :dzr_delayed\n'
    'cd /d "%DZR_DIR%"\n'
    "goto :dzr_done\n"
    ":dzr_delayed\n"
    'cd /d "!DZR_DIR!"\n'
    ":dzr_done\n"
    'set "DZ_RELAUNCH_CD_FILE="\n'
    'set "DZR_DIR="\n'
    "exit /b %DZR_RC%\n",
)
setlocal_dzr = write(
    "dzr_setlocal.cmd",
    "@echo off\nsetlocal\n"
    'set "DZ_RELAUNCH_CD_FILE=%TEMP%\\dzr-sl-%RANDOM%.txt"\n'
    f"{dz}\n"
    'set /p DZR_DIR=<"%DZ_RELAUNCH_CD_FILE%"\n'
    'cd /d "%DZR_DIR%"\n',
)
forf = write(
    "dzr_forf.cmd",
    "@echo off\n"
    "set DEMO_EMIT=1\n"
    f"for /f \"delims=\" %%D in ('{dz}') do cd /d \"%%D\"\n"
    "set DEMO_EMIT=\n",
)


def tab(label, lines, v_on=True, env_extra=None):
    body = "@echo off\n" f'cd /d "{start}"\n' + "".join(l + "\n" for l in lines)
    body += "<nul set /p =  tab is now in: \ncd\n"   # bare `cd` prints the folder safely
    t = write("tab.cmd", body)
    env = dict(os.environ)
    env["DEMO_TARGET"] = target
    env.update(env_extra or {})
    flag = "/V:ON" if v_on else "/V:OFF"
    r = subprocess.run(["cmd", "/d", flag, "/c", t], capture_output=True, text=True, env=env)
    print(f"--- {label}   [cmd {flag}]")
    print((r.stdout + r.stderr).rstrip().replace(root, "<tmp>"))
    print()


simple = os.path.join(root, "proj with space")
os.makedirs(simple)
S = {"DEMO_TARGET": simple}
print("start folder :", start.replace(root, "<tmp>"))
print("simple target:", simple.replace(root, "<tmp>"))
print("hard target  :", target.replace(root, "<tmp>"), "\n")
tab("1. simple target: run the fake dz directly (it calls os.chdir)", [dz], env_extra=S)
tab("2. simple target: temp-file wrapper dzr.cmd", [f'call "{dzr}"'], env_extra=S)
tab("3. simple target: a wrapper that uses setlocal", [f'call "{setlocal_dzr}"'], env_extra=S)
tab("4. hard target: the for /f wrapper (dz prints the folder on stdout)", [f'call "{forf}"'])
tab("5. hard target: temp-file wrapper dzr.cmd", [f'call "{dzr}"'])
tab("6. hard target: temp-file wrapper dzr.cmd", [f'call "{dzr}"'], v_on=False)
tab("7. dzr.cmd when dz fails: exit code comes back, tab stays put",
    [f'call "{dzr}"', "echo   errorlevel after dzr: %ERRORLEVEL%"],
    env_extra={"DEMO_TARGET": os.path.join(root, "gone")})
print("temp dir left for inspection:", root)
