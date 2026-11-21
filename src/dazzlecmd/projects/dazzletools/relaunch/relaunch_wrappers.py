"""The ``dzr`` wrappers that let ``claim`` change the tab's folder.

A program cannot change the folder of the shell that started it. The wrapper
runs ``dz relaunch`` with ``DZ_RELAUNCH_CD_FILE`` pointing into a freshly
claimed temp folder; relaunch writes the member's folder there (one line), and
the wrapper -- which runs *inside* the tab's shell -- changes to it.

Measured (final DWP T1, T2, T4): the cmd form keeps spaces, ``&`` and ``!``
under /V:ON and /V:OFF and passes the exit code back; ``setlocal`` would undo
the cd; ``%RANDOM%`` repeats across tabs started together, so the temp folder
is claimed with ``mkdir`` and retried. The bash form passed 72/72 cases.
"""

from __future__ import annotations

import os
import sys

DZR_CMD_TEMPLATE = r"""@echo off
rem dzr.cmd -- run `dz relaunch` and let it change this tab's folder.
rem Printed by `dz relaunch shell-init cmd`. Must not use setlocal (it would undo the cd).
:dzr_mk
set "DZR_TMP=%TEMP%\dzr-%RANDOM%-%RANDOM%"
mkdir "%DZR_TMP%" 2>nul || goto :dzr_mk
set "DZ_RELAUNCH_CD_FILE=%DZR_TMP%\cd.txt"
set "DZ_RELAUNCH_CD_FORMAT=cmd"
{invoke} %*
set "DZR_RC=%ERRORLEVEL%"
set "DZ_RELAUNCH_CD_FORMAT="
if not exist "%DZ_RELAUNCH_CD_FILE%" goto :dzr_done
set "DZR_DIR="
set /p DZR_DIR=<"%DZ_RELAUNCH_CD_FILE%"
del "%DZ_RELAUNCH_CD_FILE%" >nul 2>&1
if not defined DZR_DIR goto :dzr_done
if "!!"=="" goto :dzr_delayed
cd /d "%DZR_DIR%"
goto :dzr_done
:dzr_delayed
cd /d "!DZR_DIR!"
:dzr_done
rmdir "%DZR_TMP%" >nul 2>&1
set "DZR_TMP="
set "DZ_RELAUNCH_CD_FILE="
set "DZR_DIR="
exit /b %DZR_RC%
"""

DZR_BASH_TEMPLATE = r"""# dzr -- run `dz relaunch` and let it change this shell's folder.
# Printed by `dz relaunch shell-init bash`; add it to ~/.bashrc.
# Note: under `set -e` a refused claim ends the shell, as any failing command does.
dzr() {
  local _dzr_tmp='' _dzr_rc=0 _dzr_dir=''
  _dzr_tmp=$(mktemp -d "${TMPDIR:-/tmp}/dzr.XXXXXX") || return 1
  DZ_RELAUNCH_CD_FILE="$_dzr_tmp/cd.txt" DZ_RELAUNCH_CD_FORMAT=posix command {invoke} "$@" || _dzr_rc=$?
  if [ -s "$_dzr_tmp/cd.txt" ]; then
    IFS= read -r _dzr_dir < "$_dzr_tmp/cd.txt" || true
  fi
  rm -f -- "$_dzr_tmp/cd.txt"
  rmdir -- "$_dzr_tmp" 2>/dev/null || true
  if [ -n "$_dzr_dir" ]; then
    cd -- "$_dzr_dir" || _dzr_rc=$?
  fi
  return "$_dzr_rc"
}
"""


# The installed bash/zsh/sh form: a file that is SOURCED (`. dzr <set> claim`), so it runs inside the
# person's shell and its cd sticks -- no edit to ~/.bashrc (dcc-patcher's rule too). It must never
# `exit` (that would close the shell), leaks no variables, and never touches the caller's "$@".
DZR_SOURCED_TEMPLATE = r"""# dzr -- run `dz relaunch` and let it change this shell's folder.
# Written by dz relaunch shell-init bash --install. Source it: . dzr <set> claim
# (or add `alias dzr='. dzr'` to your shell's rc file yourself, then: dzr <set> claim)
if ! (return 0 2>/dev/null); then
  echo "dzr: source it so it can change this shell's folder: . dzr $*" >&2
  exit 2
fi
__dzr_main() {
  local _dzr_tmp='' _dzr_rc=0 _dzr_dir=''
  _dzr_tmp=$(mktemp -d "${TMPDIR:-/tmp}/dzr.XXXXXX") || return 1
  DZ_RELAUNCH_CD_FILE="$_dzr_tmp/cd.txt" DZ_RELAUNCH_CD_FORMAT=posix command {invoke} "$@" || _dzr_rc=$?
  if [ -s "$_dzr_tmp/cd.txt" ]; then
    IFS= read -r _dzr_dir < "$_dzr_tmp/cd.txt" || true
  fi
  rm -f -- "$_dzr_tmp/cd.txt"
  rmdir -- "$_dzr_tmp" 2>/dev/null || true
  if [ -n "$_dzr_dir" ]; then
    cd -- "$_dzr_dir" || _dzr_rc=$?
  fi
  return "$_dzr_rc"
}
__dzr_main "$@"
eval "unset -f __dzr_main; return $?"
"""

MARKER = "rem dzr.cmd -- run `dz relaunch` and let it change this tab's folder."
SOURCED_MARKER = "# Written by dz relaunch shell-init bash --install."


def _home() -> str:
    """The person's home folder. (Seam: tests replace it.)"""
    return os.path.expanduser("~")


def bash_install_dir() -> tuple:
    """Where the sourced ``dzr`` goes: (folder, needs_creating).

    Beside ``dz`` on Linux/macOS -- on PATH for whoever runs dz, never needing root. On a Windows
    host (Git Bash) the dz folder is on the Windows PATH, where an extensionless sh file would be
    picked by Windows resolvers and fail (dcc-patcher v0.1.11), so it goes to ~/bin, which Git for
    Windows puts first on Git Bash's PATH and Windows never searches.
    """
    if sys.platform == "win32":
        folder = os.path.join(_home(), "bin")
        return folder, not os.path.isdir(folder)
    return install_dir(), False


def _installed_record_path() -> str:
    import relaunch_store as rs
    return os.path.join(rs.local_dir(), "installed.json")


def _record(key: str, value) -> None:
    import json
    from dazzle_filekit import atomic_write_json
    p = _installed_record_path()
    data = {}
    if os.path.isfile(p):
        try:
            data = json.load(open(p, encoding="utf-8"))
        except ValueError:
            data = {}
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write_json(p, data, indent=2, default=None)


def _recorded(key: str):
    import json
    p = _installed_record_path()
    try:
        return json.load(open(p, encoding="utf-8")).get(key)
    except (OSError, ValueError):
        return None


def install_bash(folder: str = None) -> tuple:
    """Write the sourced ``dzr`` (LF bytes). Returns (outcome, path)."""
    created = False
    if folder is None:
        folder, created = bash_install_dir()
    path = os.path.join(folder, "dzr")
    text = wrapper_text("sourced").encode("ascii")
    if os.path.exists(path):
        current = open(path, "rb").read()
        if current == text:
            return "CURRENT", path
        if SOURCED_MARKER.encode("ascii") not in current[:300]:
            return "FOREIGN", path
    if created:
        os.makedirs(folder, exist_ok=True)
        _record("bash_dir_created", folder)
    with open(path, "wb") as f:
        f.write(text)
    return "INSTALLED", path


def uninstall_bash(folder: str = None, trash=None) -> tuple:
    if folder is None:
        folder, _ = bash_install_dir()
    path = os.path.join(folder, "dzr")
    if not os.path.exists(path):
        return "ABSENT", path
    if SOURCED_MARKER.encode("ascii") not in open(path, "rb").read()[:300]:
        return "FOREIGN", path
    trash.trash([path])
    made = _recorded("bash_dir_created")
    if made and os.path.normcase(os.path.abspath(made)) == os.path.normcase(os.path.abspath(folder)):
        try:
            os.rmdir(folder)            # only if empty, and only because we made it
        except OSError:
            pass
        _record("bash_dir_created", None)
    return "REMOVED", path


def install_dir() -> str:
    """The folder holding dz.exe -- already on PATH. (Seam: tests replace it.)"""
    import shutil
    dz = shutil.which("dz")
    if not dz:
        raise OSError("dz was not found on PATH, so there is no folder to install dzr.cmd into -- "
                      "save it by hand: dz relaunch shell-init cmd > <a folder on PATH>\\dzr.cmd")
    return os.path.dirname(os.path.abspath(dz))


def _fixed_drive(folder: str) -> bool:
    if sys.platform != "win32":
        return True
    import ctypes
    root = os.path.splitdrive(os.path.abspath(folder))[0] + "\\"
    return ctypes.windll.kernel32.GetDriveTypeW(root) == 3   # DRIVE_FIXED


def install_cmd(folder: str = None) -> tuple:
    """Write dzr.cmd into ``folder`` (default: beside dz.exe). Returns (outcome, path)."""
    folder = folder or install_dir()
    if not _fixed_drive(folder):
        raise OSError(f"{folder} is not on a local fixed drive -- it may be missing right after a restart")
    path = os.path.join(folder, "dzr.cmd")
    text = wrapper_text("cmd").encode("ascii")
    if os.path.exists(path):
        current = open(path, "rb").read()
        if current == text:
            return "CURRENT", path
        if MARKER.encode("ascii") not in current[:300]:
            return "FOREIGN", path
    with open(path, "wb") as f:
        f.write(text)
    return "INSTALLED", path


def uninstall_cmd(folder: str = None, trash=None) -> tuple:
    folder = folder or install_dir()
    path = os.path.join(folder, "dzr.cmd")
    if not os.path.exists(path):
        return "ABSENT", path
    if MARKER.encode("ascii") not in open(path, "rb").read()[:300]:
        return "FOREIGN", path
    trash.trash([path])
    return "REMOVED", path


def wrapper_text(shell: str, invoke: str = "dz relaunch") -> str:
    """The wrapper for ``shell`` ("cmd" or "bash"); ``invoke`` is replaceable for tests."""
    if shell == "cmd":
        return DZR_CMD_TEMPLATE.replace("{invoke}", invoke).replace("\n", "\r\n")
    if shell == "bash":
        return DZR_BASH_TEMPLATE.replace("{invoke}", invoke)
    if shell == "sourced":
        return DZR_SOURCED_TEMPLATE.replace("{invoke}", invoke)
    raise ValueError(f"no wrapper for shell '{shell}' (cmd and bash are built; pwsh follows #108)")
