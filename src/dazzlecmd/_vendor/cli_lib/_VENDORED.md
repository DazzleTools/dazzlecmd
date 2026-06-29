# In-development: `cli_lib` → future `dazzle_cli_lib`

**Origin:** dazzlecmd-AUTHORED (NOT copied from elsewhere) -- the third CLI-presentation pillar, written here, developed in-tree.
**Status:** IN DEVELOPMENT.
**Destiny:** extract to a standalone `dazzle-cli-lib` lib once clean + feature-complete -- with `dazzle-help-lib` + `dazzle-log-lib` as its dependencies (the 3-pillar split, DWP-A).

## What it is

The framework that generalizes HOW CLIs are built: it turns the `{Groupable, Continuum, ContinuumSpace}` structure into CLI surface (parser, the `-h` layout, axis-section rendering) and composes the other two pillars -- `help_lib` (contextual tips/examples) and `log_lib` (output channels + the verbosity Continuum). **cli_lib depends on help_lib + log_lib; they do NOT depend on cli_lib** (down-only).

This is where the structural display-templates belong (NOT in `help_lib`, which is tips -- the H-1 misstep this corrects).

## Current contents (DWP-D)

- `sections.py` -- `render_labeled_section` / `aligned_row`: the group/axis-section primitive (D-1). `dz kit -h`'s visibility section renders through it.

## Roadmap (DWP-D slices)

- D-1 (done) -- the section renderer; `dz kit -h` visibility section through it.
- D-2 -- generate ALL of `dz kit -h` from the registry + `DisplayMeta`; retire `render_kit_help` hand-coding.
- D-3 -- `-v`/`-q`/`--show channel:level` declarations wired to `log_lib.VERBOSITY_CONTINUUM`.
- D-4 -- the tip hook (`help_lib.items_for_rank` at a coordinate); continuum-scoped `TIP:`.
- D-5 -- the `format_help` override + parser/epilog generalization (the reusable CLI builder).

## Extraction checklist (when ready)

- [ ] feature-complete (D-1..D-5)
- [ ] clean deps: cli_lib -> {help_lib, log_lib} only; no dazzlecmd-specific imports leak into the framework
- [ ] new repo `DazzleLib/dazzle-cli-lib`, dist `dazzle-cli-lib`, import `dazzle_cli_lib`
- [ ] ecosystem placement (STACK-MAP addendum -- a cross-cutting CLI lib, not the file-stack)
