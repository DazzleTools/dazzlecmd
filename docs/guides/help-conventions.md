# Tool Help Conventions

When a user types `<aggregator> <tool> -h` (or `--help`, or `-?`), dazzlecmd-lib does NOT intercept the flag. The argv after the tool name is passed to the tool's runner **exactly as the user typed it**, with no parsing, filtering, or substitution. This is by design: dazzlecmd is a dumb dispatcher, and tools should behave as if they were invoked directly from the CLI.

Concretely:

- **Python tools** (`runtime.type: python`) handle `-h` inside their own `argparse.ArgumentParser` — no work needed; argparse's `add_help=True` default does it.
- **PowerShell, bash, cmd, and binary tools** see `-h` in their own argv. PowerShell does not natively treat `-h` as a help flag (it has `Get-Help` for that); bash and cmd scripts handle whatever the author writes. If the tool's script doesn't handle `-h`, the tool **runs** with `-h` as just another argv entry — which is often a footgun for long-running or destructive tools.

The fix is to handle `-h` in your tool script, with whichever idiom fits the runtime. The snippets below are copy-paste ready.

---

## PowerShell tools

PowerShell's native help mechanism is `Get-Help`, which reads the script's `param()` block automatically and any comment-based help (`<# .SYNOPSIS / .DESCRIPTION / .PARAMETER #>`) the author wrote. Wire `-h` / `--help` / `-?` to it:

```powershell
# At the top of your .ps1 tool, BEFORE the param() block:
if ($args -contains '-h' -or $args -contains '--help' -or $args -contains '-?') {
    Get-Help $MyInvocation.MyCommand.Path -Full
    exit 0
}

param(
    [int]$Duration = 0,
    [int]$Interval = 30,
    # ... etc ...
)
```

`Get-Help` produces output that includes the parameter signature, types, and any comment-based help. Authors who want richer help add blocks like:

```powershell
<#
.SYNOPSIS
    Quantify zombie growth rate over time.

.DESCRIPTION
    Tracks Proc/Thre/MiP2/PsIn/EtwS/FMsl/WfpH/WfpM (the documented
    per-zombie tags) and scans the broader pool-tag space for the
    same signature.

.PARAMETER Duration
    Minutes to run; 0 means run forever (default: 0).

.PARAMETER Interval
    Seconds between samples (default: 30).

.EXAMPLE
    measure.ps1 -Duration 10 -Interval 5

.NOTES
    CSV at <repo>/logs/measure/. Requires admin for nonpaged pool reads.
#>
```

`Get-Help -Full` includes synopsis, description, syntax, parameter table, examples, and notes — all from one block.

### Why the lib doesn't do this automatically

A previous iteration of dazzlecmd-lib (commit `724fe0a`, reverted) intercepted `-h` / `--help` / `-?` in the dispatcher and spawned `Get-Help` itself. That violated the project's dumb-dispatcher principle: the lib was special-casing specific flags, accumulating per-flag knowledge it shouldn't carry. The current design is transparent: the lib dispatches; the tool decides what `-h` means. This means tool authors who want `-h` handling write the snippet above — but the lib stays small and predictable, and tools behave identically to direct invocation.

### Optional: shared helper

If your aggregator has many PowerShell tools, factor the help check into a dot-source helper:

```powershell
# tools/_lib/Show-DazzleHelp.ps1
function Test-HelpFlag {
    param([string[]]$Argv)
    return ($Argv -contains '-h' -or $Argv -contains '--help' -or $Argv -contains '-?')
}

function Show-DazzleHelp {
    param([string]$ScriptPath = $MyInvocation.PSCommandPath)
    Get-Help $ScriptPath -Full
}
```

Then at the top of each tool:

```powershell
. "$PSScriptRoot/../_lib/Show-DazzleHelp.ps1"
if (Test-HelpFlag $args) { Show-DazzleHelp $MyInvocation.MyCommand.Path; exit 0 }

param( ... )
```

---

## Bash / sh / zsh tools

```bash
#!/usr/bin/env bash
case " $* " in
    *" -h "* | *" --help "* | *" -? "*)
        cat <<EOF
Usage: $(basename "$0") [options]

  -Duration N    Duration in seconds (default: 60)
  -Quiet         Suppress per-sample output

Examples:
  $(basename "$0") -Duration 30
EOF
        exit 0
        ;;
esac

# ... rest of script ...
```

For more sophisticated help, use `getopts` and a dedicated `usage()` function that prints help and exits.

---

## Windows cmd / batch tools

```cmd
@echo off
if /i "%~1"=="-h" goto :help
if /i "%~1"=="--help" goto :help
if /i "%~1"=="-?" goto :help
if /i "%~1"=="/?" goto :help
goto :main

:help
echo Usage: %~n0 [options]
echo.
echo   -Duration N    Duration in seconds (default: 60)
echo   -Quiet         Suppress per-sample output
exit /b 0

:main
rem ... rest of script ...
```

---

## Binary tools

If your binary already supports `--help` or `-h`, no work is needed — the user's `-h` reaches the binary and the binary handles it.

If your binary doesn't have a built-in help mode, the lib won't add one. Either rebuild the binary with `--help` support, or wrap it in a small script (bash / cmd / PS) that intercepts `-h` and prints help before invoking the binary.

---

## Opt-out from any future lib behavior

The manifest field `runtime.handles_help` was added during the issue #67 iteration as an opt-out for tools that hand-roll their own `-h` handling. As of the redesign (commit landing Option A — tool wins for shadowed names; no per-flag intercept in the lib), the field is unused — the lib never intercepts `-h`, so there's nothing to opt out of. The field is kept in the schema as a future-proofing hint in case the lib ever adds opt-in help behavior; today it has no effect.

---

## Discoverability via `<aggregator> info <tool>` and `<aggregator> list`

Tool authors who want their tool's manifest description / notes to be discoverable without invoking the script can rely on:

```
<aggregator> info <tool>        # prints manifest description, notes, runtime info
<aggregator> list               # prints all tools with one-line descriptions
<aggregator> tree               # tree view of kits and tools
```

These meta-commands read from the manifest only — no script invocation. They're the lib's contribution to discoverability; per-tool `-h` handling is the script author's contribution.

---

## Summary

| Runtime | `-h` handling responsibility | Recommended idiom |
|---|---|---|
| Python | argparse (built-in) | `argparse.ArgumentParser(add_help=True)` (the default) |
| PowerShell | tool author | `if ($args -contains '-h') { Get-Help $MyInvocation.MyCommand.Path -Full; exit 0 }` at top of script |
| bash / sh / zsh | tool author | Explicit case statement OR `getopts` + `usage()` function |
| cmd / batch | tool author | `if /i "%~1"=="-h" goto :help` blocks |
| binary | binary author | Built-in `--help` if the binary supports it; otherwise wrap in a script |
