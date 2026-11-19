"""POC-3 (collab round 2, consultant): stand-in for relaunch's launcher, so the
"csb resume as a grandchild" question can be settled in a real tab BEFORE any
relaunch code exists.

It does what the planned launcher does and nothing else:
  - refuses to start the child unless stdin and stdout are a console
    (override with --force-no-tty to see the refusal path is the only difference)
  - removes DZ_APP_NAME / DZ_COMMAND / DZ_CANONICAL_FQCN / DZ_INVOKED_FQCN from
    the child's environment (and sets them first, to prove the scrub)
  - ignores Ctrl-C in THIS process while the child runs, so Ctrl-C belongs to
    the child (pass --no-sigint-guard to see the unguarded behaviour)
  - never execs; waits; prints the child's exit code on stderr and returns it

Usage (a human runs this in a real terminal tab; the consultant did not):
    python poc3_grandchild_launcher.py [--no-sigint-guard] [--cwd DIR] -- <program> [args...]
e.g.
    python poc3_grandchild_launcher.py -- csb resume <session-uuid>

The program is resolved with dazzlecmd_lib.paths.which_with_pathext when that
is importable, else used as given.
"""
import os
import signal
import subprocess
import sys

SCRUB = ("DZ_APP_NAME", "DZ_COMMAND", "DZ_CANONICAL_FQCN", "DZ_INVOKED_FQCN")


def main(argv):
    guard = True
    force = False
    cwd = None
    while argv and argv[0] != "--":
        flag = argv.pop(0)
        if flag == "--no-sigint-guard":
            guard = False
        elif flag == "--force-no-tty":
            force = True
        elif flag == "--cwd":
            cwd = argv.pop(0)
        else:
            print("unknown flag: %s" % flag, file=sys.stderr)
            return 2
    if not argv or len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    child = argv[1:]

    if not (sys.stdin.isatty() and sys.stdout.isatty()) and not force:
        print("poc3: not a console -- would PRINT, not run: %s" % " ".join(child))
        return 0

    try:
        from dazzlecmd_lib.paths import which_with_pathext
        resolved = which_with_pathext(child[0])
    except Exception as exc:  # the POC must still run without the lib
        print("poc3: resolver unavailable (%s); using the name as given" % exc, file=sys.stderr)
        resolved = None
    if resolved:
        child[0] = str(resolved)

    for name in SCRUB:
        os.environ[name] = "poc3-should-not-leak"
    env = {k: v for k, v in os.environ.items() if k not in SCRUB}

    print("poc3: CLAIMED (pretend) -- starting %s" % child[0])
    sys.stdout.flush()
    old = None
    if guard:
        old = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        proc = subprocess.Popen(child, cwd=cwd, env=env)
        code = proc.wait()
    finally:
        if guard:
            signal.signal(signal.SIGINT, old)
    print("poc3: child exited %s" % code, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
