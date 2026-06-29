# In-development: `cli_lib` → future `dazzle_cli_lib`

**Origin:** dazzlecmd-AUTHORED (NOT copied from elsewhere) -- the third CLI-presentation pillar, written here, developed in-tree.
**Status:** IN DEVELOPMENT.
**Destiny:** extract to a standalone `dazzle-cli-lib` lib once clean + feature-complete -- with `dazzle-help-lib` + `dazzle-log-lib` as its dependencies (the 3-pillar split, DWP-A).

## What it is

The framework that generalizes HOW CLIs are built: it turns the `{Groupable, Continuum, ContinuumSpace}` structure into CLI surface (parser, the `-h` layout, axis-section rendering) and composes the other two pillars -- `help_lib` (contextual tips/examples) and `log_lib` (output channels + the verbosity Continuum). **cli_lib depends on help_lib + log_lib; they do NOT depend on cli_lib** (down-only).

This is where the structural display-templates belong (NOT in `help_lib`, which is tips -- the H-1 misstep this corrects).

## Current contents (DWP-D)

- `sections.py` -- `aligned_row` / `render_labeled_section` (FLAT) / `render_nested_section` (NESTED) / `Section` + `render_sections`: the section KINDS + the declarative list-driver. The WHOLE `dz kit -h` body renders through it (D-1, D-2).
- `tips.py` -- `render_tip_footer`: the continuum-scoped `TIP:` footer (D-4). The `cli_lib -> help_lib` composition (uses `help_lib.items_for_rank` + `TipFormatter`).

## Roadmap (DWP-D slices)

- D-1 (done) -- the section renderer; `dz kit -h` visibility section through it.
- D-2 (done) -- the whole `dz kit -h` body from a declarative `Section` list; `_hrow` retired.
- D-3 (done) -- `-v`/`-q`/`--show` wired to `log_lib.VERBOSITY_CONTINUUM` (`dz -vv` real).
- D-4 (done) -- the continuum-scoped `TIP:` footer (`render_tip_footer`); cli_lib -> help_lib.
- D-5 -- the `format_help` override + parser/epilog generalization (the reusable CLI builder).

## Extraction checklist (when ready)

- [ ] feature-complete (D-1..D-5)
- [ ] clean deps: cli_lib -> {help_lib, log_lib} only; no dazzlecmd-specific imports leak into the framework
- [ ] new repo `DazzleLib/dazzle-cli-lib`, dist `dazzle-cli-lib`, import `dazzle_cli_lib`
- [ ] ecosystem placement (STACK-MAP addendum -- a cross-cutting CLI lib, not the file-stack)
