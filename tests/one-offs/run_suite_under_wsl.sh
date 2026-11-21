#!/usr/bin/env bash
# Run the dazzlecmd suite under real Linux, from a Windows dev box, via WSL.
#
# WHY THIS EXISTS
# Several tests only run on POSIX (symlink loops, xattrs), and os.path means
# different things on each side, so a Windows-only run can stay green while
# Linux is broken. The first native run (2026-11-09) found 18 Linux-only
# failures: 13 from no `python` command on PATH, 2 from git being unable to
# read this worktree from WSL, 1 from no PyPA `build`, and 1 stale test that
# had never run on Windows (POSIX-only skipif).
#
# USAGE (from Git Bash on the Windows host)
#     bash tests/one-offs/run_suite_under_wsl.sh                    # root tests (no tool projects)
#     bash tests/one-offs/run_suite_under_wsl.sh src/dazzlecmd/projects/core/safedel/tests
#     PYTEST_ARGS="-x -v" bash tests/one-offs/run_suite_under_wsl.sh tests/test_paths.py
#     WSL_DISTRO=Ubuntu-22.04 bash tests/one-offs/run_suite_under_wsl.sh
#
# WSL_DISTRO is optional; unset means the machine's default distro.
#
# The Dazzle stack (dazzlecmd, dazzlecmd-lib, dazzle-lib, dazzle-filekit,
# unctools, dazzle-preservelib, dazzle-loglib) is imported from the local source
# trees via PYTHONPATH, so nothing is written into the Windows working trees.
# Only third-party deps go into a venv inside WSL at ~/.cache/dazzlecmd-venv.
# Override a sibling path with DAZZLECMD_LIB_SRC, DAZZLE_LIB_SRC, FILEKIT_SRC,
# UNCTOOLS_SRC, PRESERVELIB_SRC or LOGLIB_SRC (Git Bash form, /c/...).
#
# Known limit: this checkout is a git worktree whose .git file holds a C:/
# path, which git under WSL cannot follow. Git-reading tests skip with that
# message rather than fail.
set -u

REPO_WIN="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
to_wsl() { printf '%s' "$1" | sed -E 's#^/([a-zA-Z])/#/mnt/\L\1/#'; }

REPO_WSL="$(to_wsl "$REPO_WIN")"
PY_PATH="$REPO_WSL/src"
for src in "${DAZZLECMD_LIB_SRC:-/c/code/dazzlecmd-lib}" \
           "${DAZZLE_LIB_SRC:-/c/code/dazzle-lib}" \
           "${FILEKIT_SRC:-/c/code/filetoolkit/github}" \
           "${UNCTOOLS_SRC:-/c/code/UNCtools/local}" \
           "${PRESERVELIB_SRC:-/c/code/dazzle-preservelib}" \
           "${LOGLIB_SRC:-/c/code/dazzle-loglib}"; do
    PY_PATH="$PY_PATH:$(to_wsl "$src")"
done
TARGET="${1:-tests/}"

DISTRO_ARGS=()
if [ -n "${WSL_DISTRO:-}" ]; then
    DISTRO_ARGS=(-d "$WSL_DISTRO")
fi

echo "  distro : ${WSL_DISTRO:-<default>}"
echo "  repo   : $REPO_WSL"
echo "  target : $TARGET"
echo

# -e runs bash directly. `wsl.exe -- cmd` hands the command line to WSL's
# shell to be parsed again, which expands $VENV to an empty string first.
wsl.exe "${DISTRO_ARGS[@]}" -e bash -lc "
set -u
VENV=\${XDG_CACHE_HOME:-\$HOME/.cache}/dazzlecmd-venv
if [ ! -x \"\$VENV/bin/python\" ]; then
    echo '  creating venv ...'
    python3 -m venv \"\$VENV\" || exit 1
    \"\$VENV/bin/pip\" install -q --upgrade pip
    # third-party deps only -- the Dazzle stack comes from PYTHONPATH.
    # build/setuptools/wheel: the sdist privacy test builds an sdist. --upgrade
    # because the distro venv ships setuptools 59.6 (Ubuntu 22.04) and the
    # project's build backend needs >=61; a plain install keeps the old one.
    \"\$VENV/bin/pip\" install -q --upgrade pytest 'pydantic>=2.0' 'networkx>=3.0' \\
        build 'setuptools>=61' wheel || exit 1
fi
cd '$REPO_WSL' || exit 1
# The venv's bin/ first on PATH, as Linux CI's setup-python does: tests that
# look for a 'python' command find one (the distro ships only 'python3').
export PATH=\"\$VENV/bin:\$PATH\"
PYTHONPATH='$PY_PATH' \"\$VENV/bin/python\" -m pytest '$TARGET' -q -p no:cacheprovider \\
    ${PYTEST_ARGS:-}
"
rc=$?
echo
if [ "$rc" -eq 0 ]; then
    echo "  LINUX RESULT: pass"
else
    echo "  LINUX RESULT: FAIL (exit $rc)"
fi
exit "$rc"
