"""Recon for the "sets" DWP: what natural groupings exist, and what does
each of the four current ad-hoc mechanisms actually cover? Read-only."""
import sys, os, re, collections
sys.path.insert(0, r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools")
sys.path.insert(0, r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools\dazzle-update")
from _repo_common.discovery import find_git_repos, editable_installs
from _repo_common.gh_identity import IdentityResolver, parse_slug
from _repo_common.repo_state import detect_remotes
from ecosystem import EcosystemConfig

NS = ['DazzleTools','DazzleLib','DazzleML','DazzleNodes','DazzleProj',
      'ZeroMeld','Todo-AI','Way-of-Scarcity','Invaryon','Citizen-Tech-Collective']
cfg = EcosystemConfig(namespaces=NS, personal_namespace='djdarcy')
r = IdentityResolver()

names = set()
for p in find_git_repos(r"C:\code", max_depth=3):
    rem = detect_remotes(p)
    o = next((x for x in rem if x["name"] == "origin"), None)
    slug = (o.get("slug") or parse_slug(o.get("fetch_url"))) if o else None
    if not slug:
        continue
    info = r.resolve(slug)
    names.add(info["full_name"] or slug)

owned = {n for n in names if cfg.owns(n)}
print(f"  distinct remote-backed repos on disk : {len(names)}")
print(f"  owned by us                          : {len(owned)}")
print(f"  third-party / not ours               : {len(names) - len(owned)}")
print()

# candidate set rules
rules = {
    "dazzle-orgs":   lambda n: n.split("/")[0].lower().startswith("dazzle"),
    "dazzle-prefix": lambda n: n.split("/")[1].lower().startswith("dazzle"),
    "wtf-*":         lambda n: n.split("/")[1].lower().startswith("wtf"),
    "claude-*":      lambda n: "claude" in n.split("/")[1].lower(),
    "ComfyUI/nodes": lambda n: ("comfy" in n.split("/")[1].lower()
                                or n.split("/")[0].lower() == "dazzlenodes"),
    "UNC*":          lambda n: n.split("/")[1].lower().startswith("unc"),
    "repokit":       lambda n: "repokit" in n.split("/")[1].lower(),
    "todoai":        lambda n: n.split("/")[0].lower() == "todo-ai",
}
member = {k: {n for n in owned if f(n)} for k, f in rules.items()}
print("  candidate set          size   sample")
for k, s in sorted(member.items(), key=lambda kv: -len(kv[1])):
    sample = ", ".join(sorted(s)[:2])
    print(f"    {k:<20} {len(s):>4}   {sample[:58]}")

union = set().union(*member.values())
print()
print(f"  owned repos in >=1 candidate set : {len(union)}")
print(f"  owned repos in NO set (residue)  : {len(owned - union)}")
for n in sorted(owned - union)[:12]:
    print(f"    {n}")

overlap = collections.Counter()
for n in union:
    hits = tuple(sorted(k for k, s in member.items() if n in s))
    if len(hits) > 1:
        overlap[hits] += 1
print()
print(f"  repos in MORE than one set: {sum(overlap.values())}")
for combo, c in overlap.most_common(5):
    print(f"    {c:>3}  {' + '.join(combo)}")
