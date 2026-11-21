#!/usr/bin/env bash
# End-to-end check of the sourced `dzr` on Linux, with the real `dz`.
#
# Everything happens in a temp folder: a temp PATH folder holding `dz` (or a shim that runs
# dazzlecmd from PYTHONPATH), a temp relaunch store (DZ_RELAUNCH_HOME), and temp member folders.
# Nothing touches ~/.bashrc, ~/.dz, or any real install. Safe to rerun.
#
# USAGE
#   On a Linux box with dazzlecmd installed:   bash linux_dzr_sourced_smoke.sh
#   From Git Bash on Windows, via WSL with the source trees on PYTHONPATH:
#     wsl.exe -d Ubuntu-22.04 bash /mnt/c/code/dazzlecmd/github/tests/one-offs/relaunch/linux_dzr_sourced_smoke.sh
#   Set DZ_PY to the python that can import dazzlecmd (default: the WSL suite venv, else python3).
set -u
T=$(mktemp -d "${TMPDIR:-/tmp}/dzr-smoke.XXXXXX")
trap 'rm -rf -- "$T"' EXIT
mkdir -p "$T/bin" "$T/home" "$T/proj a" "$T/proj b"
export DZ_RELAUNCH_HOME="$T/home"

if command -v dz >/dev/null 2>&1 && [ -z "${DZ_FROM_SOURCE:-}" ]; then
  REAL_DZ=$(command -v dz)
  printf '#!/bin/sh\nexec "%s" "$@"\n' "$REAL_DZ" > "$T/bin/dz"
else
  PY=${DZ_PY:-${XDG_CACHE_HOME:-$HOME/.cache}/dazzlecmd-venv/bin/python}
  [ -x "$PY" ] || PY=python3
  SRC=${DZ_SRC_PATH:-/mnt/c/code/dazzlecmd/github/src:/mnt/c/code/dazzlecmd-lib:/mnt/c/code/dazzle-lib:/mnt/c/code/filetoolkit/github:/mnt/c/code/UNCtools/local:/mnt/c/code/dazzle-preservelib:/mnt/c/code/dazzle-loglib}
  printf '#!/bin/sh\nPYTHONPATH="%s" exec "%s" -m dazzlecmd "$@"\n' "$SRC" "$PY" > "$T/bin/dz"
fi
chmod +x "$T/bin/dz"
export PATH="$T/bin:$PATH"

pass=0; fail=0
check() { if eval "$2"; then echo "  [OK]   $1"; pass=$((pass+1)); else echo "  [FAIL] $1"; fail=$((fail+1)); fi; }

echo "== install"
out=$(dz relaunch shell-init bash --install 2>&1); echo "$out" | sed 's/^/     /'
check "dzr written beside dz" '[ -f "$T/bin/dzr" ]'
check "dzr has no CR bytes" '! grep -q $'"'"'\r'"'"' "$T/bin/dzr"'
check "install prints the alias line" 'echo "$out" | grep -q "alias dzr="'
out2=$(dz relaunch shell-init bash --install 2>&1)
check "second install says already current" 'echo "$out2" | grep -q "already current"'

echo "== a set with two folders"
dz relaunch new smoke >/dev/null 2>&1
dz relaunch smoke add "$T/proj a" --label a >/dev/null 2>&1
dz relaunch smoke add "$T/proj b" --label b >/dev/null 2>&1
check "set has two members" 'dz relaunch smoke 2>/dev/null | grep -q "proj b"'

echo "== . dzr in this shell"
cd /
. dzr smoke claim >/dev/null 2>&1; rc=$?
check ". dzr smoke claim returns 0" '[ "$rc" = 0 ]'
check "the shell moved into a member folder" 'case "$PWD" in "$T/proj a"|"$T/proj b") true;; *) false;; esac'
first=$PWD
. dzr smoke claim --next >/dev/null 2>&1
check "claim --next moves to the other member" '[ "$PWD" != "$first" ] && case "$PWD" in "$T/proj "*) true;; *) false;; esac'
. dzr nosuchset claim >/dev/null 2>&1; rc=$?
check "a refused claim returns non-zero" '[ "$rc" != 0 ]'
check "...and this shell is still here, nothing leaked" '! type __dzr_main >/dev/null 2>&1'

echo "== the optional alias"
shopt -s expand_aliases
alias dzr='. dzr'
cd /
dzr smoke release --all >/dev/null 2>&1
dzr smoke claim >/dev/null 2>&1
check "alias dzr='. dzr' works" 'case "$PWD" in "$T/proj "*) true;; *) false;; esac'

echo "== uninstall"
dz relaunch shell-init bash --uninstall >/dev/null 2>&1
check "dzr removed" '[ ! -e "$T/bin/dzr" ]'

echo
echo "dzr sourced smoke: $pass passed, $fail failed"
[ "$fail" = 0 ]
