# Vendored: `log_lib` → future `dazzle_loglib`

**Origin:** `C:\code\wtf-windows\src\wtf_windows\lib\log_lib` (copied 2026-06-28, verbatim).
**Status:** VENDORED + IN DEVELOPMENT (a WIP, like `help_lib`).
**Destiny:** extract to a standalone `dazzle_loglib` lib (own repo + PyPI) once clean + feature-complete.

## What it is

A "THAC0 verbosity system with named channels" -- the OUTPUT/presentation pillar that complements `help_lib`'s content pillar:
- `OutputManager` (`init_output`/`get_output`) -- the central output coordinator; single-axis THAC0 verbosity (`level <= threshold`).
- Named output **channels** with per-channel overrides (`ChannelConfig`, `parse_channel_spec`, `KNOWN_CHANNELS`, `OPT_IN_CHANNELS`, `format_channel_list`).
- A **hint registry** with context filtering + dedup (`Hint`, `register_hint(s)`, `get_hint`) -- the likely home for the CLI's "rerooting hint" (the thing `dz kit silence` suppresses).
- `trace` -- a function-tracing decorator.

Self-contained (stdlib-only: `dataclasses`, `typing`, `sys`, `functools`, `inspect`, `pathlib`). Does NOT reach into `wtf_windows`, `help_lib`, or any external package (verified).

## Why it's here

Not because `help_lib` needs it (it doesn't) -- but because output channels + verbosity + hints are a big part of how the CLI formats what it prints. `help_lib` (content) + `log_lib` (output channels/verbosity/hints) together are the CLI presentation framework.

## Extraction checklist (when ready)

- [ ] feature-complete for dazzlecmd's output/verbosity/hint needs
- [ ] no dazzlecmd-specific imports leak in (clean boundary)
- [ ] ecosystem placement decided (STACK-MAP addendum -- NOT in the frozen file-stack)
- [ ] new repo `DazzleLib/dazzle-loglib`, dist `dazzle-loglib`, import `dazzle_loglib`
- [ ] dazzlecmd swaps `dazzlecmd._vendor.log_lib` → `dazzle_loglib`; wtf-windows can adopt it too
