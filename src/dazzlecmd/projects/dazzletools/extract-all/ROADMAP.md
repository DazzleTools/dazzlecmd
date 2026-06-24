# extract-all — Roadmap & Known Limitations

Status: **v0.1.0 — full eager extraction**. Works correctly but uses peak
disk = total extracted size, even when the user only wants to locate a
single file.

## Current behavior

1. Extract layer 0 (source archive) into staging root.
2. Walk the tree, find every file with an archive extension (`.exe`,
   `.zip`, `.cab`, `.msi`, etc.).
3. Extract each into a sibling `<name>.extracted/` directory.
4. Recurse until no new archives are found or `--max-depth` is hit.
5. Search the resulting tree for the user's patterns and print results.
6. If `--print-locate` was passed, `shutil.rmtree(staging)` at the end.

**Peak disk usage = total extracted size of the entire archive tree.**

For a typical driver installer (NSIS wrapper → 7z payload → CAB → MSI)
this is often 3-5x the source size. Adrenalin 26.3.1 weighs ~700MB
compressed; expanded peak is likely 2-3GB.

`--print-locate` only saves disk *after* the run, not during.

## Better approaches (future work)

### A. Layer-by-layer cleanup (medium effort)

Extract layer N → search → recurse into nested archives → on unwind,
delete completed-layer contents (after copying any matched files to a
results dir).

- **Peak disk:** ≈ deepest single path's layer sizes (~10-20% of full).
- **Cost:** modest refactor of `_recursion.py` — needs post-recursion
  cleanup callbacks and a results dir for matched files.
- **Tradeoff:** loses the "browse the whole tree afterward" capability
  that the current eager approach provides.

### B. List-then-descend (most complex, lowest disk)

Use `7z l -slt <archive>` to read the archive's table of contents
*without extracting*. Only extract a nested archive when we need to
look inside it (because the listing didn't reveal a match AND the inner
files might be archives we need to descend into).

- **Peak disk:** ≈ active extraction path only (often under 500MB even
  for huge installers).
- **Cost:** significant. Requires recursive listing logic, awareness
  that files inside an archive may themselves be archives, and possibly
  format-specific handling (.cab listings, .msi tables).
- **Best for:** `--print-locate`-style "where does X live?" queries.

### C. Streaming extraction (`7z x -so | grep`)

Pipe an archive's contents to stdout and match on the fly without
landing on disk. Format-specific, complex to combine with nested
archives, but eliminates disk usage entirely for top-level matches.

## Cheap wins worth doing soon

### 1. One-walk-many-patterns (matcher refactor)

`_matcher.find_matches` currently walks the tree once per pattern. For
N patterns over a 50K-file tree that's 50K×N stat calls. Refactor to
walk once and test all patterns per filename. ~10 min of work, real
speedup for multi-pattern queries.

### 2. EXE pre-filter

Every `.exe` in the extracted tree gets passed through `7z l` to test
whether it's an archive. Installers ship hundreds of helper exes
(uninstall stubs, license viewers) that will never be archives. Filter
by file size (skip < 1MB) or magic-byte sniffing for SFX/NSIS/MSI
markers before invoking 7z.

### 3. dazzletreelib integration

Replace `os.walk` in `_matcher.py` with
`dazzletreelib.find_nodes(root, FileSystemAdapter(), predicate)`.

- **Buys:** BFS-natural shallowest-first (no sort), built-in depth
  tracking, composable predicates for multi-pattern walking.
- **Costs:** new dependency, slight verbosity vs. raw `os.walk`.
- **Verdict:** worth doing if dazzletools standardizes on
  dazzletreelib for filesystem walks across tools. Standalone, the
  current `os.walk` is fine.

## Known issues

- **No progress indicator.** 7z output is silenced (`-bso0 -bd`).
  Could parse `-bsp1` for a percent display.
- **Cycle detection hashes every archive** with full SHA-256 before
  extracting. For large archives this is measurable. Consider using
  file size + first-N-bytes as a cheaper pre-check.
- **Memory unbounded for very wide trees.** `os.walk` collects no
  state, but the matches list and seen-hashes set grow without bound.
  Not a problem in practice but worth noting.
- **Windows ACLs / NTFS streams not preserved** — 7z handles them but
  we don't pass `-snl` etc. Probably fine for inspection workflows.
