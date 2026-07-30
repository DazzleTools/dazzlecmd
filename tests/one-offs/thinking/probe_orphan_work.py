"""Does 'any path has an upstream' safely mean 'nothing is at risk'?

Tests the proposed roll-up rule: if ANY checkout of a canonical identity
has an upstream, treat the repo as accounted-for. The hole would be a
checkout on an UNBACKED branch holding commits that exist nowhere else.
Read-only.
"""
import sys, os
sys.path.insert(0, r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools")
from _repo_common.discovery import find_git_repos
from _repo_common.gh_identity import IdentityResolver, parse_slug
from _repo_common.repo_state import (detect_remotes, get_branch, get_upstream, git)

LOCAL_BY_DESIGN = {"private"}

repos = find_git_repos(r"C:\code", max_depth=3)
r = IdentityResolver()
by_key = {}
for p in repos:
    rem = detect_remotes(p)
    origin = next((x for x in rem if x["name"] == "origin"), None)
    slug = (origin.get("slug") or parse_slug(origin.get("fetch_url"))) if origin else None
    key = r.canonical_key(slug) if slug else os.path.normcase(os.path.abspath(p))
    by_key.setdefault(key, []).append(p)

multi = {k: v for k, v in by_key.items() if len(v) > 1}
at_risk = []
for key, paths in multi.items():
    if not any(get_upstream(p) for p in paths):
        continue                      # nothing backed up anywhere; not this test
    for p in paths:
        if get_upstream(p):
            continue                  # this checkout IS backed up
        br = (get_branch(p) or "")
        if br.lower() in LOCAL_BY_DESIGN:
            continue                  # local-only by design
        # commits on this branch reachable from NO remote ref anywhere
        rc, out, _ = git("log", "--oneline", "HEAD", "--not", "--remotes",
                         "--max-count=200", cwd=p)
        n = len([l for l in out.splitlines() if l.strip()]) if rc == 0 else 0
        if n:
            at_risk.append((key, p, br, n))

print(f"identities spanning >1 path            : {len(multi)}")
print(f"UNBACKED checkouts holding unique work : {len(at_risk)}")
print()
if at_risk:
    print("=== work that 'accounted for' would HIDE ===")
    for key, p, br, n in sorted(at_risk, key=lambda t: -t[3]):
        print(f"  {key}")
        print(f"    {p}")
        print(f"    branch {br!r}: {n} commit(s) on no remote anywhere")
else:
    print("no orphan work found -- the roll-up rule would be safe as-is")
