"""Read-only probe (collab round 1, consultant): this process's ancestry, the
console's own process list, and every direct child of each terminal host --
to test the "outermost process below a known terminal host" anchor rule.
"""
import ctypes, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..",
                "src", "dazzlecmd", "projects", "dazzletools", "unlockit"))
import winfocus as wf

procs = wf.snapshot_processes()
chain = wf.ancestor_chain(os.getpid(), procs)
print("ancestry (self first):")
for pid in chain:
    print("  %6d %s" % (pid, procs[pid].exe if hasattr(procs[pid], "exe") else procs[pid]))
print("WT_SESSION", os.environ.get("WT_SESSION"), "| TERM_PROGRAM", os.environ.get("TERM_PROGRAM"),
      "| stdin tty", sys.stdin.isatty(), "| stdout tty", sys.stdout.isatty())

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
buf = (ctypes.c_uint32 * 64)()
n = k32.GetConsoleProcessList(buf, 64)
print("GetConsoleProcessList ->", n, [(int(buf[i]), getattr(procs.get(int(buf[i])), "exe", "?")) for i in range(min(n, 64))])
print("GetConsoleWindow ->", k32.GetConsoleWindow())

hosts = {"windowsterminal.exe", "openconsole.exe", "conhost.exe", "code.exe", "mintty.exe", "wezterm-gui.exe", "explorer.exe"}
from collections import Counter, defaultdict
kids = defaultdict(Counter)
for p in procs.values():
    par = procs.get(p.ppid)
    if par is not None and par.exe.lower() in hosts:
        kids[par.exe.lower()][p.exe.lower()] += 1
print("\ndirect children of terminal-host-like processes (counts):")
for h, c in kids.items():
    print("  %-22s %s" % (h, dict(c.most_common(12))))
# conhost / OpenConsole: are they ever a PARENT of a shell, or only a child/sibling?
print("\nparents of conhost.exe / OpenConsole.exe instances:")
c2 = Counter()
for p in procs.values():
    if p.exe.lower() in ("conhost.exe", "openconsole.exe"):
        par = procs.get(p.ppid)
        c2[(p.exe.lower(), par.exe.lower() if par else "<dead parent>")] += 1
for k, v in c2.most_common(15):
    print("  %-16s child of %-28s x%d" % (k[0], k[1], v))
# shells whose recorded parent is gone
orph = Counter()
for p in procs.values():
    if p.exe.lower() in ("cmd.exe", "pwsh.exe", "powershell.exe", "bash.exe") and p.ppid not in procs:
        orph[p.exe.lower()] += 1
print("\nshells whose parent pid is not running:", dict(orph))
