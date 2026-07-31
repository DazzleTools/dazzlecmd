"""Is fork-ness orthogonal to set membership? Measure, don't assume."""
import sys, os, json, subprocess
sys.path.insert(0, r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools")
sys.path.insert(0, r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools\dazzle-update")
from _repo_common.discovery import find_git_repos
from _repo_common.gh_identity import IdentityResolver, parse_slug
from _repo_common.repo_state import detect_remotes
from ecosystem import EcosystemConfig

NS = ['DazzleTools','DazzleLib','DazzleML','DazzleNodes','DazzleProj',
      'ZeroMeld','Todo-AI','Way-of-Scarcity','Invaryon','Citizen-Tech-Collective']
cfg = EcosystemConfig(namespaces=NS, personal_namespace='djdarcy')
r = IdentityResolver()

names = set()
for p in find_git_repos(r"C:\code", max_depth=3):
    o = next((x for x in detect_remotes(p) if x["name"] == "origin"), None)
    slug = (o.get("slug") or parse_slug(o.get("fetch_url"))) if o else None
    if slug:
        names.add(r.resolve(slug)["full_name"] or slug)
owned = sorted(n for n in names if cfg.owns(n))

# fork status straight from GitHub
forks = {}
for ns in NS + ['djdarcy']:
    out = subprocess.run(["gh","repo","list",ns,"--limit","300","--json",
                          "nameWithOwner,isFork,parent"],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode == 0:
        for e in json.loads(out.stdout or "[]"):
            forks[e["nameWithOwner"]] = (e.get("isFork"),
                                         (e.get("parent") or {}).get("nameWithOwner"))

in_set = lambda n: (n.split("/")[0].lower().startswith("dazzle")
                    or n.split("/")[1].lower().startswith(("dazzle","wtf","comfyui","unc"))
                    or "comfy" in n.split("/")[1].lower()
                    or "claude" in n.split("/")[1].lower()
                    or "repokit" in n.split("/")[1].lower()
                    or n.split("/")[0].lower() == "todo-ai")

quad = {"set+orig":[], "set+fork":[], "noset+orig":[], "noset+fork":[], "unknown":[]}
for n in owned:
    if n not in forks:
        quad["unknown"].append(n); continue
    isf, _ = forks[n]
    key = ("set" if in_set(n) else "noset") + ("+fork" if isf else "+orig")
    quad[key].append(n)

print("  quadrant                      count")
for k in ("set+orig","set+fork","noset+orig","noset+fork","unknown"):
    print(f"    {k:<26} {len(quad[k]):>4}")
print()
print("  OWNED, IN NO SET, NOT A FORK  (ad-hoc projects):")
for n in quad["noset+orig"]: print(f"    {n}")
print()
print("  OWNED FORKS IN NO SET (the DPAPIck3 shape):")
for n in quad["noset+fork"]:
    print(f"    {n:<40} <- {forks[n][1]}")
print()
print("  OWNED FORKS THAT *ARE* IN A SET (orthogonality proof):")
for n in quad["set+fork"]:
    print(f"    {n:<40} <- {forks[n][1]}")
