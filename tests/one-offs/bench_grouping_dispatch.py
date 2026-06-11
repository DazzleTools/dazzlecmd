"""Benchmark: does routing alias creation through a Groupable verb/context add
meaningful runtime vs the current direct ``fqcn_index.insert_alias`` call?

Overlay (group) and virtual-kit (ungroup) currently materialize aliases by
calling ``insert_alias`` directly. The proposed change routes them through a
``ProjectionContext.apply()`` (mirroring ``AliasRebindContext``) so the
{group, ungroup} symmetry is enforced, not just declared. The only added work
per alias is: construct a context + construct a receipt dataclass + one extra
method call. This measures that overhead at realistic and stress scales and puts
it next to the real ``engine.discover()`` budget.

Run:  python tests/one-offs/bench_grouping_dispatch.py
"""
import time
from dataclasses import dataclass
from types import SimpleNamespace

from dazzlecmd_lib.engine import FQCNIndex, AggregatorEngine


# --- a faithful stand-in for the proposed ProjectionContext ----------------
@dataclass
class _ProjectionReceipt:
    entity_fqcn: str
    sub_kind: str
    alias_fqcn: str
    canonical_fqcn: str
    conserved: str
    reversible: bool


@dataclass
class _ProjectionContext:
    """What the real Groupable verb path would do per alias: insert + receipt."""
    index: object
    source: str = "overlay"

    def apply(self, entity, target_canonical):
        alias_fqcn = entity.fqcn
        self.index.insert_alias(alias_fqcn, target_canonical, source=self.source)
        return _ProjectionReceipt(
            entity_fqcn=target_canonical, sub_kind="overlay",
            alias_fqcn=alias_fqcn, canonical_fqcn=target_canonical,
            conserved="canonical_fqcn", reversible=True,
        )


def _make_state(n):
    """Fresh index with n canonicals + n (alias_entity, canonical_fqcn) pairs."""
    idx = FQCNIndex(command="dz")
    pairs = []
    for i in range(n):
        canon = f"core:t{i}"
        idx.insert_canonical(SimpleNamespace(
            fqcn=canon, short_name=f"t{i}", kit_import_name="core", directory=None,
        ))
        pairs.append((SimpleNamespace(fqcn=f"dazzlecmd_lib:core:t{i}"), canon))
    return idx, pairs


def _raw(idx, pairs):
    for ent, canon in pairs:
        idx.insert_alias(ent.fqcn, canon, source="overlay")


def _routed(idx, pairs):
    for ent, canon in pairs:
        _ProjectionContext(idx).apply(ent, canon)


def _bench(fn, n, repeats):
    """Avg seconds to insert n aliases (fresh state each repeat, setup excluded)."""
    total = 0.0
    for _ in range(repeats):
        idx, pairs = _make_state(n)
        t0 = time.perf_counter()
        fn(idx, pairs)
        total += time.perf_counter() - t0
    return total / repeats


def main():
    print("=" * 68)
    print("  Per-op overhead: direct insert_alias vs verb-routed (apply+receipt)")
    print("=" * 68)
    print(f"  {'N aliases':>10} | {'raw (us)':>12} | {'routed (us)':>12} | "
          f"{'delta/op (us)':>14}")
    print("  " + "-" * 60)
    for n, repeats in ((13, 4000), (100, 1000), (1000, 100)):
        raw = _bench(_raw, n, repeats)
        routed = _bench(_routed, n, repeats)
        per_op = (routed - raw) / n * 1e6
        print(f"  {n:>10} | {raw*1e6:>12.1f} | {routed*1e6:>12.1f} | "
              f"{per_op:>14.3f}")

    print()
    print("=" * 68)
    print("  Real-world budget: full engine.discover()")
    print("=" * 68)
    times = []
    for _ in range(7):
        eng = AggregatorEngine(name="dazzlecmd")
        t0 = time.perf_counter()
        eng.discover()
        times.append(time.perf_counter() - t0)
    times.sort()
    n_alias = len(eng.fqcn_index.alias_index)
    n_canon = len(eng.fqcn_index.canonical_index)
    median = times[len(times) // 2]
    print(f"  discover() median : {median*1e3:.1f} ms  "
          f"(min {times[0]*1e3:.1f} / max {times[-1]*1e3:.1f})")
    print(f"  index built       : {n_canon} canonicals, {n_alias} aliases")
    print()
    # Project the routed overhead onto the real alias count.
    raw13 = _bench(_raw, 13, 4000)
    routed13 = _bench(_routed, 13, 4000)
    per_op = (routed13 - raw13) / 13
    projected = per_op * max(n_alias, 1)
    print(f"  projected added cost if ALL {n_alias} aliases routed through the "
          f"verb:")
    print(f"    ~{projected*1e6:.1f} us  =  {projected/median*100:.4f}% of a "
          f"discover()")


if __name__ == "__main__":
    main()
