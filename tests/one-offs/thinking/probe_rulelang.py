"""How much can each rule FORM express, measured against the real population?
Tests the four candidate rule languages the user enumerated."""
import sys, os, json, subprocess
sys.path.insert(0, r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools")
sys.path.insert(0, r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools\dazzle-update")
from _repo_common.discovery import find_git_repos, editable_installs
from _repo_common.gh_identity import IdentityResolver, parse_slug
from _repo_common.repo_state import detect_remotes

r = IdentityResolver()
names = set()
for p in find_git_repos(r"C:\code", max_depth=3):
    o = next((x for x in detect_remotes(p) if x["name"] == "origin"), None)
    s = (o.get("slug") or parse_slug(o.get("fetch_url"))) if o else None
    if s:
        names.add(r.resolve(s)["full_name"] or s)

DAZZLE_ORGS = {"dazzletools","dazzlelib","dazzleml","dazzlenodes","dazzleproj"}
org_only   = {n for n in names if n.split("/")[0].lower() in DAZZLE_ORGS}
text_only  = {n for n in names if "dazzle" in n.lower()}

# ground truth for "the dazzlecmd stack": what dz actually ships or depends on
ships = set()
for i in editable_installs():
    nm = (i["name"] or "").lower()
    if nm.startswith(("dazzle","dz")) or nm in ("dazzlecmd","dazzlesum","dazzlelink"):
        ships.add(nm)

print(f"  total identities on disk        : {len(names)}")
print(f"  ORG-ONLY rule  (5 Dazzle orgs)  : {len(org_only)}")
print(f"  TEXT-ONLY rule ('dazzle' in name): {len(text_only)}")
print(f"  both agree on                   : {len(org_only & text_only)}")
print()
print(f"  in ORG but NOT matched by text  : {len(org_only - text_only)}")
for n in sorted(org_only - text_only)[:14]:
    print(f"    {n}")
print()
print(f"  matched by TEXT but NOT in org  : {len(text_only - org_only)}")
for n in sorted(text_only - org_only)[:14]:
    print(f"    {n}")
print()
noise = [n for n in org_only if n.endswith("/.github")]
print(f"  org rule sweeps in meta-repos   : {len(noise)}  {sorted(noise)[:3]}")
