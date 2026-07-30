"""Measure the real population of canonical identities spanning many paths.

Recon for the multi-checkout attribution DWP. Read-only.
"""
import sys, os, json
sys.path.insert(0, r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools")
from _repo_common.discovery import find_git_repos, editable_installs
from _repo_common.gh_identity import IdentityResolver, parse_slug
from _repo_common.repo_state import (detect_remotes, get_branch, get_upstream,
                                     get_ahead_behind, get_status_counts)

repos = find_git_repos(r"C:\code", max_depth=3)
r = IdentityResolver()
installs = {os.path.normcase(os.path.abspath(i["path"])): i
            for i in editable_installs()}

by_key = {}
for p in repos:
    rem = detect_remotes(p)
    origin = next((x for x in rem if x["name"] == "origin"), None)
    slug = (origin.get("slug") or parse_slug(origin.get("fetch_url"))) if origin else None
    key = (r.canonical_key(slug) if slug else os.path.normcase(os.path.abspath(p)))
    up = get_upstream(p)
    behind, ahead = get_ahead_behind(p, upstream=up)
    c = get_status_counts(p)
    by_key.setdefault(key, []).append({
        "path": p, "branch": get_branch(p), "upstream": up,
        "behind": behind, "ahead": ahead,
        "dirty": c["dirty_count"], "untracked": c["untracked_count"],
        "installed": os.path.normcase(os.path.abspath(p)) in installs,
    })

multi = {k: v for k, v in by_key.items() if len(v) > 1}
print(f"total canonical identities : {len(by_key)}")
print(f"spanning >1 local path     : {len(multi)}")
print(f"total paths in those       : {sum(len(v) for v in multi.values())}")

dist = {}
for v in multi.values():
    dist[len(v)] = dist.get(len(v), 0) + 1
print(f"path-count distribution    : {dict(sorted(dist.items()))}")

# How often does the alphabetically-first path differ from the right one?
wrong_by_alpha = mixed_upstream = has_install = no_signal = 0
examples = []
for k, v in multi.items():
    first = sorted(v, key=lambda d: d["path"])[0]
    inst = [d for d in v if d["installed"]]
    withup = [d for d in v if d["upstream"]]
    if len(set(bool(d["upstream"]) for d in v)) > 1:
        mixed_upstream += 1
    if inst:
        has_install += 1
        if os.path.normcase(inst[0]["path"]) != os.path.normcase(first["path"]):
            wrong_by_alpha += 1
            examples.append((k, first, inst[0]))
    elif not withup:
        no_signal += 1

print(f"identities w/ an editable install : {has_install}")
print(f"  ...where alpha-first != installed: {wrong_by_alpha}  <-- MISATTRIBUTED TODAY")
print(f"identities w/ MIXED upstream state: {mixed_upstream}  <-- can hide behind-counts")
print(f"identities w/ no install & no upstream anywhere: {no_signal}")
print()
print("=== misattribution examples ===")
for k, first, inst in examples[:6]:
    print(f"  {k}")
    print(f"    reported (alpha-first): {first['path']}  [{first['branch']}] up={first['upstream']}")
    print(f"    correct  (pip-installed): {inst['path']}  [{inst['branch']}] up={inst['upstream']}")
print()
print("=== identities where NO path is installed but several have upstreams ===")
n = 0
for k, v in multi.items():
    if not any(d["installed"] for d in v) and sum(1 for d in v if d["upstream"]) > 1:
        n += 1
        if n <= 5:
            print(f"  {k}: " + ", ".join(f"{os.path.basename(d['path'])}[{d['branch']}]" for d in v))
print(f"  total such identities: {n}")
