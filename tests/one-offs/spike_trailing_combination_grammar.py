"""SPIKE (discoverability DWP Addendum 2, 2026-07-18): do combined
trailing-view spellings (.::. / :.:. / ::.. / :.. etc.) survive the
settled grammar, or do they collide with constitutional rejections?
Feed every 2-3-operator permutation of trailing {:, ., :.} to
canonicalize and report."""
import itertools
import sys
sys.path.insert(0, "C:/code/dazzlecmd-lib")
from dazzlecmd_lib.fqcn_grammar import canonicalize, FQCNParseError

OPS = [":", ".", ":."]
base = "dz:.meta:config"
results = []
for n in (2, 3):
    for combo in itertools.product(OPS, repeat=n):
        spelling = base + "".join(combo)
        try:
            canon, _ = canonicalize(spelling)
            results.append((spelling, f"ACCEPTED -> {canon}"))
        except FQCNParseError as e:
            reason = str(e)[:60]
            results.append((spelling, f"rejected ({reason}...)"))
accepted = [r for r in results if r[1].startswith("ACCEPTED")]
for s, verdict in results:
    print(f"  {s:<34} {verdict}")
print(f"\n{len(accepted)} accepted / {len(results)} permutations")
