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


def wrapper_text(shell: str, invoke: str = "dz relaunch") -> str:
    """The wrapper for ``shell`` ("cmd" or "bash"); ``invoke`` is replaceable for tests."""
    if shell == "cmd":
        return DZR_CMD_TEMPLATE.replace("{invoke}", invoke).replace("\n", "\r\n")
    if shell == "bash":
        return DZR_BASH_TEMPLATE.replace("{invoke}", invoke)
    raise ValueError(f"no wrapper for shell '{shell}' (cmd and bash are built; pwsh follows #108)")
