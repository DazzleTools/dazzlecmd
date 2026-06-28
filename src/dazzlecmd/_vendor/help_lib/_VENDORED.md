# Vendored: `help_lib` → future `dazzle_helplib`

**Origin:** `C:\code\wtf-windows\src\wtf_windows\lib\help_lib` (copied 2026-06-28, verbatim).
**Status:** VENDORED + IN DEVELOPMENT. The original was a work-in-progress, not feature-complete.
**Destiny:** extract to a standalone `dazzle_helplib` lib (own repo + PyPI) once it is clean and feature-complete -- the same develop-in-tree-then-extract path `dazzlecmd-lib` took.

## What it is

A "universal help system for CLI applications" that separates **content** from **presentation**:
- `HelpContent` / `DetailedHelpContent` -- a command-example/topic + its description (with `{prog}` substitution, contexts, priority).
- `HelpSection` -- a collection of related items + aligned-example formatting.
- `HelpBuilder` -- orchestrates sections; `build_minimal_help` / `build_standard_help` / `get_random_tip`.
- `formatters` (`ExampleFormatter` / `TipFormatter`), `content_registry`.

Self-contained (stdlib-only: `dataclasses`, `typing`, `random`). **No `log_lib` dependency** (verified -- the original `wtf_windows/lib/__init__.py` notes the three libs are "intended to become independent").

## What it is NOT (yet) -- the development gap

Today it renders **command-example** help (the `dz --help` epilog shape). It does NOT yet render the **axis-group structured help** the CLI homogenization needs: an axis → its verbs → glosses, with nesting (terse/full), on/off compaction, and `hidden` axes. Building that (the `DisplayMeta`-fed templates) is the work this vendored copy exists to host -- see DWP `2026-06-28__14-53-18__dev-workflow-process__display-templates-and-axis-metadata-in-lib.md`.

## Extraction checklist (when ready)

- [ ] feature-complete for the axis-template use case (the DWP-1 templates)
- [ ] no dazzlecmd-specific imports leak into the framework (clean boundary)
- [ ] decide its ecosystem placement (a STACK-MAP addendum -- it is NOT in the frozen file-stack map)
- [ ] new repo `DazzleLib/dazzle-helplib`, dist `dazzle-helplib`, import `dazzle_helplib`
- [ ] dazzlecmd swaps `dazzlecmd._vendor.help_lib` → `dazzle_helplib`; wtf-windows can adopt it too
