"""churn_audit -- show every file the churn classifier reclassified, with
evidence, so a human can eyeball the verdicts.

Reuses the PRODUCTION content check (_stamp_only_change) and the real
default patterns; the small porcelain loop is replicated here, so each
repo's replicated verdict is cross-checked against get_status_counts()
and any disagreement prints as MISMATCH. An audit that can silently
diverge from the thing it audits is worse than no audit.

Usage: python churn_audit.py [root]     (default C:\\code)
Read-only: status + diff only.
"""

import os
import fnmatch
import subprocess
import sys

_DZ = r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools"
sys.path.insert(0, _DZ)
sys.path.insert(0, os.path.join(_DZ, "dazzle-update"))

from _repo_common.discovery import find_git_repos  # noqa: E402
from _repo_common.repo_state import (  # noqa: E402
    get_status_counts,
    _stamp_only_change,
)
from ecosystem import EcosystemConfig  # noqa: E402


def audit(root=r"C:\code"):
    pats = [p.lower() for p in EcosystemConfig().churn_files]
    print(f"  patterns: {', '.join(pats)}")
    print()
    total_repos, churn_only, mismatches = 0, 0, 0

    for repo in find_git_repos(root, max_depth=3):
        counts = get_status_counts(repo, churn_patterns=pats)
        if not counts["churn_count"]:
            continue
        total_repos += 1

        # Replicate the gate per file; verify against production count.
        out = subprocess.run(["git", "-C", repo, "status", "--porcelain"],
                             capture_output=True, text=True,
                             timeout=30).stdout
        stamped = []
        for line in out.splitlines():
            if not line.strip() or line.startswith("??"):
                continue
            code, path = line[:2], line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            raw = path.strip('"')
            p = raw.replace("\\", "/").lower()
            base = p.rsplit("/", 1)[-1]
            if (set(code) <= {"M", " "}
                    and any(fnmatch.fnmatch(p, q) or fnmatch.fnmatch(base, q)
                            for q in pats)
                    and _stamp_only_change(repo, raw)):
                stamped.append(raw)

        only = (counts["dirty_count"] == 0
                and counts["untracked_count"] == 0)
        churn_only += only
        tag = "CHURN-ONLY (counted clean)" if only else \
            f"+ {counts['dirty_count']} dirty, {counts['untracked_count']} untracked"
        print(f"  {repo}")
        print(f"      [{tag}]")
        if len(stamped) != counts["churn_count"]:
            mismatches += 1
            print(f"      MISMATCH: audit found {len(stamped)} stamped "
                  f"file(s), production counted {counts['churn_count']}")
        for f in stamped:
            diff = subprocess.run(
                ["git", "-C", repo, "diff", "HEAD", "--", f],
                capture_output=True, text=True, timeout=30).stdout
            body = [ln for ln in diff.splitlines()
                    if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
            print(f"      {f}")
            for ln in body[:4]:
                print(f"          {ln}")
        print()

    print(f"  {total_repos} repo(s) with churn; {churn_only} churn-only "
          f"(the footer parenthetical); {mismatches} audit/production "
          f"mismatch(es)")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(audit(sys.argv[1] if len(sys.argv) > 1 else r"C:\code"))
