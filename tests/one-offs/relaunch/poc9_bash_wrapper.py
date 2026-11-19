"""POC-9 (collab round 3, consultant): the bash wrapper function, measured with
Git Bash the way dzr.cmd was measured.

A function sets the hand-over path (a mktemp -d folder), runs a fake dz, cds to
the folder the fake wrote, and returns the child's code. Tried with folder names
holding a space, `$`, a backquote, `!`, a single quote, `&`, and non-ASCII; with
`set -e`, `set -u`, both, and neither in the calling shell; non-interactive and
`bash -i` (history expansion on).

Safe: temp folders only; runs Git Bash and python. Usage: python poc9_bash_wrapper.py
"""
import json
import os
import subprocess
import sys
import tempfile

BASH = r"C:\Program Files\Git\bin\bash.exe"
NL = chr(10)

root = tempfile.mkdtemp(prefix="relaunch_poc9_")
names = {
    "plain": "plain",
    "space": "has space",
    "dollar": "a$HOME$b",
    "backquote": "a`echo x`b",
    "bang": "wow!dir!",
    "squote": "it's",
    "amp": "a&b;c",
    "unicode": "\u00fcn\u00ef-\u65e5\u672c",
    "dash": "-leading-dash",
}
paths = {}
for k, n in names.items():
    p = os.path.join(root, n)
    os.mkdir(p)
    paths[k] = p
with open(os.path.join(root, "map.json"), "w", encoding="utf-8") as f:
    json.dump(paths, f)

fake = os.path.join(root, "fakedz.py")
with open(fake, "w", encoding="utf-8") as f:
    f.write(NL.join([
        "import json, os, sys",
        "m = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'map.json'), encoding='utf-8'))",
        "key, code = sys.argv[1], int(sys.argv[2])",
        "out = os.environ.get('DZ_RELAUNCH_CD_FILE')",
        "if out and key != 'none':",
        "    with open(out, 'w', encoding='utf-8', newline='') as f:",
        "        f.write(m[key] + chr(10))",
        "sys.exit(code)",
        "",
    ]))

# The wrapper under test. FAKE_DZ stands where `command dz relaunch` will be.
func = NL.join([
    "dzr() {",
    "  local _dzr_tmp='' _dzr_rc=0 _dzr_dir=''",
    '  _dzr_tmp=$(mktemp -d "${TMPDIR:-/tmp}/dzr.XXXXXX") || return 1',
    '  DZ_RELAUNCH_CD_FILE="$_dzr_tmp/cd.txt" DZ_RELAUNCH_CD_FORMAT=posix FAKE_DZ "$@" || _dzr_rc=$?',
    '  if [ -s "$_dzr_tmp/cd.txt" ]; then',
    '    IFS= read -r _dzr_dir < "$_dzr_tmp/cd.txt" || true',
    "  fi",
    '  rm -f -- "$_dzr_tmp/cd.txt"',
    '  rmdir -- "$_dzr_tmp" 2>/dev/null || true',
    '  if [ -n "$_dzr_dir" ]; then',
    '    cd -- "$_dzr_dir" || _dzr_rc=$?',
    "  fi",
    '  return "$_dzr_rc"',
    "}",
    "",
])


def msys(p):
    return "/" + p[0].lower() + p[2:].replace(chr(92), "/")


fake_cmd = "'%s' '%s'" % (msys(sys.executable), msys(fake))
func = func.replace("FAKE_DZ", fake_cmd)
with open(os.path.join(root, "dzr.sh"), "w", encoding="utf-8", newline=NL) as f:
    f.write(func)
print("root:", root)
print("---- wrapper under test ----")
print(func.replace(fake_cmd, "command dz relaunch"))

here_py = "import os;print('CWD=' + ascii(os.getcwd()))"


def run(key, code, opts, interactive):
    script = NL.join([
        "cd '%s'" % msys(root),
        ". ./dzr.sh",
        opts,
        "dzr %s %d && echo RC=0 || echo RC=$?" % (key, code),
        "echo ALIVE",
        "'%s' -c \"%s\"" % (msys(sys.executable), here_py),
        "ls -d /tmp/dzr.* 2>/dev/null | wc -l | sed 's/^/LEFTOVER=/'",
        "",
    ])
    args = [BASH, "--norc", "--noprofile"] + (["-i"] if interactive else [])
    r = subprocess.run(args, input=script.encode("utf-8"), capture_output=True)
    out = r.stdout.decode("utf-8", "replace")
    lines = [l.strip() for l in out.splitlines()]
    rc = next((l for l in lines if l.startswith("RC=")), "RC=?")
    cwd = next((l[4:] for l in lines if l.startswith("CWD=")), "?")
    left = next((l for l in lines if l.startswith("LEFTOVER=")), "LEFTOVER=?")
    want = ascii(paths[key]) if key != "none" else ascii(root)
    where = "MOVED" if (key != "none" and cwd == want) else ("STAYED" if cwd == ascii(root) else "OTHER " + cwd)
    return rc, "ALIVE" in lines, where, left


print("---- results ----")
for opts in ("true", "set -e", "set -u", "set -eu"):
    for interactive in (False, True):
        row = []
        for k in names:
            rc, alive, where, left = run(k, 0, opts, interactive)
            ok = (rc == "RC=0" and alive and where == "MOVED" and left == "LEFTOVER=0")
            row.append("%s=%s" % (k, "ok" if ok else "FAIL(%s,%s,%s,%s)" % (rc, alive, where, left)))
        print("%-8s %-15s %s" % (opts, "interactive" if interactive else "non-interactive", "  ".join(row)))
print("---- exit codes and the no-file case (set -eu, non-interactive and interactive) ----")
for interactive in (False, True):
    for key, code in (("plain", 7), ("none", 3), ("none", 0)):
        rc, alive, where, left = run(key, code, "set -eu", interactive)
        print("  %-15s child=%d wrote=%-5s -> %s alive=%s cwd=%s %s"
              % ("interactive" if interactive else "non-interactive", code, key != "none", rc, alive, where, left))
