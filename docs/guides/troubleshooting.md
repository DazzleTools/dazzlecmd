# Troubleshooting

## `dz` is not recognized after `pip install dazzlecmd` (Windows)

**The one command that always runs:**

```bash
python -m dazzlecmd setup dazzlecmd
```

### Why this happens

When Python is installed for all users and `pip install` runs without elevation, pip silently falls back to your *user* scheme -- the `dz.exe` launcher lands in `%APPDATA%\Python\Python3XY\Scripts`, a directory Windows never adds to PATH. pip prints its "not on PATH" warning only on the very first install; every later `pip install dazzlecmd` says "Requirement already satisfied" and stays silent, so the one breadcrumb evaporates. Nothing is broken about the install -- the launcher exists, the shell just cannot see it.

### What the command does

`python -m dazzlecmd setup dazzlecmd` works because `python -m` needs no PATH entry. It diagnoses the install -- scheme (system / user / venv / editable), the scripts directory that *actually* holds your launchers, effective and persisted PATH state, and any shadowing copies -- then offers the repair: appending the scripts directory to your user PATH. The write is registry-safe (the value's registry kind is preserved; `setx` is never used because it truncates long PATHs) and the prior value is backed up under `~\.dazzlecmd\` first.

Flags, per the setup verb's contract (the verb owns the space before `--`):

| Flag | Effect |
|---|---|
| `--dry-run` | Show the would-be PATH change without making it |
| `--yes` | Apply without prompting |
| `--clip` | Copy the shell-activation line (below) to your clipboard -- **your clipboard is never touched without this flag** |
| `--emit-shell-fix` | Print *exactly* the activation line on stdout (machine channel, pipe-friendly) |

### After the fix: either option works

- **Keep your current shell** -- a running shell cannot re-read the registry, so setup drops small activation scripts into your temp directory (the same idea as venv/conda `activate`) and prints the one-line command for the shell it detected you are in:

  | Shell | Run this |
  |---|---|
  | cmd | `"%TEMP%\dz-path.cmd"` |
  | PowerShell | `. "$env:TEMP\dz-path.ps1"` (must be dot-sourced) |
  | git-bash / bash | `source "$TEMP/dz-path.sh"` |

  Run it and `dz` works immediately in that very window. The scripts are idempotent -- safe to re-run.

- **Or just open a new terminal** -- the persistent fix means every shell you start from now on finds `dz` automatically. No activation step, ever.

### Linux / macOS

The same command diagnoses identically, but never edits your dotfiles: it prints the exact line for your shell's startup file (`~/.bashrc`, `~/.zshrc`, `fish_add_path` for fish) *and* the session-only `source` line for the current shell -- the same either/or as Windows.

### Special cases the diagnosis handles

- **venv installs**: you get activation guidance (`.venv\Scripts\activate`) -- a venv's Scripts dir is never offered for your permanent PATH.
- **Editable/source installs** (`pip install -e`): the scripts directory is found by probing for the launchers themselves, not by guessing from the install scheme.
- **A tool named like the aggregator**: if a real tool shadows the `dz`/`dazzlecmd` name, the self-setup says so and shows the tool's FQCN so you can reach its setup too.

### Consumer aggregators

Everything above is engine-level: any aggregator built on dazzlecmd-lib inherits it under its own name -- `python -m myagg setup myagg` emits `myagg-path.cmd` and so on.

## Still stuck?

Open an issue at <https://github.com/DazzleTools/dazzlecmd/issues> with the full output of `python -m dazzlecmd setup dazzlecmd --dry-run`.
