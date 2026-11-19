"""S0 probe for dz relaunch: can a removed set file be staged into the safedel
trash and found again by its original path, through the library API?

Writes only under a fresh temp folder: the trash store, its registries, and the
fake set file all live there. Exit 0 = found; 1 = not found / refused.

Run: python tests/one-offs/relaunch/probe_safedel_list_by_path.py
"""
import json
import os
import sys
import tempfile

from dazzlecmd_lib.core.safedel import TrashStore

root = tempfile.mkdtemp(prefix="relaunch_s0_")
store_dir = os.path.join(root, "trash")
sets_dir = os.path.join(root, "home", "relaunch", "sets")
os.makedirs(sets_dir)
set_file = os.path.join(sets_dir, "probe-set.json")
with open(set_file, "w", encoding="utf-8") as f:
    json.dump({"format": 1, "kind": "dz-relaunch-set", "name": "probe-set", "members": []}, f)

store = TrashStore(
    store_path=store_dir,
    registry_path=os.path.join(root, "registry.json"),
    junction_registry_path=os.path.join(root, "junctions.json"),
)
result = store.trash([set_file])
print("trash success:", result.success, "refused:", result.refused, "folder:", os.path.basename(result.folder_path or ""))
for e in result.errors:
    print("  error:", e)
if not result.success:
    print("RESULT: refused -- nothing staged")
    sys.exit(1)

print("original gone:", not os.path.exists(set_file))
hits = []
for folder in store.list_entries():
    for entry in folder.entries:
        if os.path.normcase(entry.original_path).startswith(os.path.normcase(sets_dir)):
            hits.append((folder.folder_name, folder.deleted_at, entry.original_path))
for h in hits:
    print("found:", h[0], h[1], h[2].replace(root, "<tmp>"))
print("RESULT:", "found by original path" if hits else "NOT found")
print("temp dir:", root)
sys.exit(0 if hits else 1)
