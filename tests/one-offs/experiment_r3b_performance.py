"""Round 3b experiment: Performance of kit-qualified shortcut resolution.

Gemini's unhedged gut call (Meta-C): the list comprehension in
FQCNIndex.resolve() at engine.py:242-249 will not scale. With N canonical
tools, each kit-qualified shortcut miss is O(N).

This script quantifies that claim. Generates synthetic FQCNs at several
scales and times:
    (a) Direct canonical hit (baseline, dict lookup)
    (b) Alias hit (dict lookup through alias_index)
    (c) Kit-qualified shortcut hit (the suspect list comprehension)
    (d) Miss (falls through entire list comprehension then returns None)

Compares against a precomputed index proposal: {(kit, short_name): fqcn}.
"""

import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "packages", "dazzlecmd-lib", "src"))

from dazzlecmd_lib.engine import FQCNIndex


def make_synthetic(n_canonical, n_aliases_per_kit=5, n_kits=None):
    """Build an FQCNIndex with n_canonical synthetic tools."""
    if n_kits is None:
        n_kits = max(5, n_canonical // 20)
    idx = FQCNIndex()

    # Distribute tools across kits
    tools_per_kit = n_canonical // n_kits
    for k in range(n_kits):
        kit = f"kit{k:04d}"
        for t in range(tools_per_kit):
            tool = f"tool{t:04d}"
            fqcn = f"{kit}:{tool}"
            project = {
                "_fqcn": fqcn,
                "_short_name": tool,
                "_kit_import_name": kit,
                "name": tool,
                "namespace": kit,
            }
            idx.insert_canonical(project)

    # Add some aliases via a "virtual" kit
    for k in range(n_aliases_per_kit):
        alias_fqcn = f"virt:alias{k:04d}"
        target_kit = k % n_kits
        target_fqcn = f"kit{target_kit:04d}:tool{k:04d}"
        if target_fqcn in idx.canonical_index:
            idx.insert_alias(alias_fqcn, target_fqcn)

    return idx, n_kits, tools_per_kit


def time_calls(fn, iterations=1000):
    """Return mean microseconds per call."""
    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1_000_000  # microseconds


def build_precomputed_shortcut_index(canonical_index):
    """Simulate Gemini's proposed O(1) shortcut index.

    Maps (kit_prefix, tool_short) -> fqcn for every canonical.
    For 3+ segment FQCNs (e.g., wtf:core:locked), the kit_prefix is the
    segment immediately before the short name (core), not the top-level.
    Same ambiguity model as the current list comprehension.
    """
    shortcut = {}
    ambiguous = {}
    for fqcn in canonical_index:
        segments = fqcn.split(":")
        if len(segments) < 2:
            continue
        tool_short = segments[-1]
        # Every possible kit_prefix segment preceding the tool
        for i in range(len(segments) - 1):
            kit = segments[i]
            key = (kit, tool_short)
            if key in shortcut:
                # Turn into ambiguity set
                existing = shortcut[key]
                ambiguous.setdefault(key, {existing}).add(fqcn)
            shortcut[key] = fqcn
    return shortcut, ambiguous


def current_shortcut_resolve(idx, name):
    """Replicate the current O(n) list comprehension logic."""
    kit_prefix, _, tool_suffix = name.partition(":")
    if tool_suffix and ":" not in tool_suffix:
        matches = [
            fqcn for fqcn in idx.canonical_index
            if fqcn.startswith(kit_prefix + ":")
            and fqcn.rsplit(":", 1)[-1] == tool_suffix
        ]
        if len(matches) == 1:
            return idx.canonical_index[matches[0]]
        if len(matches) > 1:
            return idx.canonical_index[sorted(matches)[0]]
    return None


def precomputed_shortcut_resolve(shortcut_idx, name):
    """O(1) lookup using precomputed index."""
    kit_prefix, _, tool_suffix = name.partition(":")
    if tool_suffix and ":" not in tool_suffix:
        return shortcut_idx.get((kit_prefix, tool_suffix))
    return None


def run_scale(n_canonical):
    """Run the benchmark at a given scale."""
    print(f"\n=== Scale: {n_canonical} canonical tools ===")
    idx, n_kits, tools_per_kit = make_synthetic(n_canonical)
    shortcut_idx, _ambig = build_precomputed_shortcut_index(idx.canonical_index)

    # Pick a canonical to test with
    first_fqcn = f"kit0000:tool0000"
    last_fqcn = f"kit{n_kits-1:04d}:tool{tools_per_kit-1:04d}"
    miss_name = "nonexistent:whatever"

    # Ensure canonical exists
    assert first_fqcn in idx.canonical_index
    assert last_fqcn in idx.canonical_index

    print(f"  kits: {n_kits}, tools_per_kit: {tools_per_kit}")
    print(f"  canonical_index size: {len(idx.canonical_index)}")
    print(f"  shortcut_index size:  {len(shortcut_idx)}")

    # 1. Direct canonical hit (baseline)
    t = time_calls(lambda: idx.canonical_index.get(first_fqcn))
    print(f"  (a) direct canonical dict.get: {t:>8.2f} us")

    # 2. Full resolve() for canonical hit
    t = time_calls(lambda: idx.resolve(first_fqcn))
    print(f"  (b) full resolve() canonical:  {t:>8.2f} us")

    # 3. Current list comprehension for kit-qualified shortcut
    # When a short name alone is typed as "kit:tool" that IS the canonical FQCN,
    # it hits the direct path first. We need a case where FQCN lookup MISSES
    # but kit-qualified shortcut HITS.
    # Example: if canonical is "wtf:core:locked", then "wtf:locked" is the shortcut.
    # Our synthetic is flat so we need to build a 3-segment entry.

    # Build a separate index with 3-segment FQCNs
    idx2 = FQCNIndex()
    for k in range(n_kits):
        kit = f"kit{k:04d}"
        for t_num in range(tools_per_kit):
            tool = f"tool{t_num:04d}"
            fqcn = f"{kit}:subns:{tool}"  # 3-segment
            project = {
                "_fqcn": fqcn,
                "_short_name": tool,
                "_kit_import_name": kit,
                "name": tool,
                "namespace": f"{kit}:subns",
            }
            idx2.insert_canonical(project)
    shortcut_idx2, _ = build_precomputed_shortcut_index(idx2.canonical_index)
    shortcut_name = f"kit0000:tool0000"  # 2-segment shortcut to 3-segment canonical
    assert shortcut_name not in idx2.canonical_index
    # Verify current path resolves it
    p = current_shortcut_resolve(idx2, shortcut_name)
    assert p is not None, f"Current path failed to resolve {shortcut_name}"

    t = time_calls(lambda: current_shortcut_resolve(idx2, shortcut_name), iterations=500)
    print(f"  (c) current shortcut O(n):     {t:>8.2f} us  <-- suspect path")

    t = time_calls(lambda: precomputed_shortcut_resolve(shortcut_idx2, shortcut_name))
    print(f"  (d) precomputed shortcut O(1): {t:>8.2f} us")

    # 4. Miss case (fully scans list comprehension)
    t = time_calls(lambda: current_shortcut_resolve(idx2, miss_name), iterations=500)
    print(f"  (e) current shortcut MISS:     {t:>8.2f} us  <-- worst case")

    t = time_calls(lambda: precomputed_shortcut_resolve(shortcut_idx2, miss_name))
    print(f"  (f) precomputed shortcut MISS: {t:>8.2f} us")


if __name__ == "__main__":
    print("Round 3b Experiment: FQCN resolver performance")
    print("=" * 60)
    for n in [20, 200, 2000, 20000]:
        run_scale(n)
