"""Scan for dangling .git gitfiles -- pointers whose target does not exist."""
import os, sys

ROOTS = [r"C:\code", r"C:\proj", r"C:\code\claude-projects"]
MAXDEPTH = 5
dangling, ok_files, checked = [], 0, 0

def walk(root, depth=0):
    global ok_files, checked
    if depth > MAXDEPTH:
        return
    try:
        entries = list(os.scandir(root))
    except (OSError, PermissionError):
        return
    for e in entries:
        if not e.is_dir(follow_symlinks=False):
            continue
        if e.name in (".git", "node_modules", "__pycache__", "venv", ".venv"):
            continue
        gf = os.path.join(e.path, ".git")
        if os.path.isfile(gf):
            checked += 1
            try:
                line = open(gf, encoding="utf-8", errors="replace").readline().strip()
            except OSError:
                continue
            if line.startswith("gitdir:"):
                tgt = line.split(":", 1)[1].strip()
                resolved = tgt if os.path.isabs(tgt) else os.path.normpath(os.path.join(e.path, tgt))
                if os.path.exists(resolved):
                    ok_files += 1
                else:
                    dangling.append((e.path, tgt))
        walk(e.path, depth + 1)

for r in ROOTS:
    if os.path.isdir(r):
        walk(r)

print(f"gitfile (.git-as-file) dirs checked: {checked}")
print(f"  healthy: {ok_files}")
print(f"  DANGLING: {len(dangling)}")
for p, t in dangling:
    print(f"    {p}\n       -> {t}")
