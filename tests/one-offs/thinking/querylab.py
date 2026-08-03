"""querylab -- test Candidate B (cache-index + live-verified matches)
BEFORE building it into dazzle_update.

Implements the QF-1 refresh pipeline here, out-of-tree, from production
primitives, and measures the design's claims against the real machine:

  E1  staleness census: cached git state vs live, ALL records.
      This is the B-vs-C evidence: if nothing drifts, pure cache wins;
      every drifted record is a lie candidate-C's card would tell.
  E2  end-to-end B timing per query scenario (single, multi-checkout,
      narrow glob, wide glob vs cap, miss).

Usage: python querylab.py [e1|e2|all]
Read-only except `git fetch` on E2's matched repos (normal tool behavior).
"""

import os
import sys
import time

_DZ = r"C:\code\dazzlecmd\github\src\dazzlecmd\projects\dazzletools"
sys.path.insert(0, _DZ)
sys.path.insert(0, os.path.join(_DZ, "dazzle-update"))

import scancache  # noqa: E402
import dazzle_update as du  # noqa: E402
from ecosystem import EcosystemConfig  # noqa: E402
from _repo_common.repo_state import (  # noqa: E402
    fetch_remote,
    get_ahead_behind,
    get_branch,
    get_status_counts,
    get_upstream,
)

CHURN = EcosystemConfig().churn_files
AXES = ("branch", "upstream", "ahead", "behind",
        "dirty_count", "untracked_count", "churn_count")


def live_git(path):
    u = get_upstream(path)
    behind, ahead = get_ahead_behind(path, upstream=u)
    c = get_status_counts(path, churn_patterns=CHURN)
    return {"branch": get_branch(path), "upstream": u,
            "ahead": ahead, "behind": behind,
            "dirty_count": c["dirty_count"],
            "untracked_count": c["untracked_count"],
            "churn_count": c.get("churn_count", 0)}


def refresh_matched(matched, do_fetch=True, cap=8):
    """The QF-1 prototype: live truth for matched records only."""
    refreshed, skipped = 0, 0
    for r in list(matched.values()):
        if refreshed >= cap:
            skipped += 1
            continue
        touched = False
        for c in r.get("checkouts") or []:
            p = c.get("path")
            if not p or not os.path.isdir(p):
                continue
            if do_fetch:
                fetch_remote(p, timeout=30)
            c["git"] = live_git(p)
            touched = True
        refreshed += touched
    return refreshed, skipped


def e1_staleness_census():
    rec, meta, age, err = scancache.load(max_age=None)
    if err:
        print(f"  no cache: {err}")
        return
    print(f"  cache age: {scancache.format_age(age)}; "
          f"{len(rec)} records")
    t0 = time.perf_counter()
    drifted, checked, examples = 0, 0, []
    for key, r in rec.items():
        for c in r.get("checkouts") or []:
            p = c.get("path")
            if not p or not os.path.isdir(p):
                continue
            checked += 1
            cached = c.get("git") or {}
            live = live_git(p)   # NO fetch: measures what C's card would say
            diffs = {a: (cached.get(a), live.get(a)) for a in AXES
                     if cached.get(a) != live.get(a)}
            if diffs:
                drifted += 1
                if len(examples) < 12:
                    name = r.get("full_name") or key
                    examples.append((name, p, diffs))
    dt = time.perf_counter() - t0
    print(f"  checked {checked} checkouts in {dt:.1f}s")
    print(f"  DRIFTED from cache: {drifted} checkout(s) -- each one is an "
          f"axis candidate-C's card would misreport right now")
    for name, p, diffs in examples:
        print(f"    {name}  ({os.path.basename(p)})")
        for a, (old, new) in diffs.items():
            print(f"        {a}: cached {old!r} -> live {new!r}")


def e2_timings():
    scenarios = [
        ("single name", ["dazzlesum"]),
        ("multi-checkout", ["dazzlecmd"]),
        ("narrow glob", ["wtf-*"]),
        ("wide glob (cap 8)", ["dazzle*"]),
        ("miss", ["no-such-repo-xyz"]),
    ]
    print(f"  {'scenario':<20}{'load+match':>11}{'matches':>9}"
          f"{'refresh':>9}{'skipped':>9}{'total':>8}")
    for label, q in scenarios:
        t0 = time.perf_counter()
        rec, meta, age, err = scancache.load(max_age=None)
        matched = du.match_records(rec, q)
        t1 = time.perf_counter()
        refreshed, skipped = refresh_matched(matched, do_fetch=True, cap=8)
        t2 = time.perf_counter()
        print(f"  {label:<20}{t1 - t0:>10.2f}s{len(matched):>9}"
              f"{t2 - t1:>8.2f}s{skipped:>9}{t2 - t0:>7.2f}s")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("e1", "all"):
        print("== E1: staleness census (cache vs live, no fetch) ==")
        e1_staleness_census()
        print()
    if which in ("e2", "all"):
        print("== E2: candidate-B end-to-end timings ==")
        e2_timings()
