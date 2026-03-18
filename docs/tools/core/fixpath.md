# dz fixpath

Fix mangled paths and optionally open, copy, or browse files.

## Quick Start

```bash
# Fix a mangled path (mixed slashes, prompt artifacts, etc.)
dz fixpath "C:\code\project\private/claude/file.md"

# Fix and open in default application (Typora for .md, etc.)
dz fixpath -o "private/claude/issues/issue_43.md"

# Fix and open containing folder in file manager
dz fixpath -l "C:\code\project>private/claude/file.md"

# Fix and copy to clipboard
dz fixpath -c "/c/code/project/README.md"
```

## What It Fixes

| Problem | Example | Result |
|---------|---------|--------|
| Mixed slashes | `C:\code\project/private/file.md` | `C:\code\project\private\file.md` |
| cmd.exe prompt `>` | `C:\code\project>private/file.md` | `C:\code\project\private\file.md` |
| MSYS/Git Bash paths | `/c/code/project/file.md` | `C:\code\project\file.md` |
| WSL paths | `/mnt/c/Users/foo/file.md` | `C:\Users\foo\file.md` |
| Extended-length prefix | `\\?\C:\code\file.md` | `C:\code\file.md` |
| Surrounding quotes | `"C:\code\file.md"` | `C:\code\file.md` |
| URL encoding | `C:/code/my%20project/file.md` | `C:\code\my project\file.md` |
| PowerShell prefix | `PS C:\code\file.md` | `C:\code\file.md` |
| Tilde | `~/code/file.md` | `C:\Users\You\code\file.md` |
| Trailing prompt chars | `/path/file.md$ ` | `/path/file.md` |
| MSYS-mangled WSL | `C:\Program Files\Git\mnt\c\Users\...` | `C:\Users\...` |
| UNC forward slash | `//server/share/path` | `\\server\share\path` |
| UNC shell-mangled | `\server\share` (shell ate one `\`) | `\\server\share` |

If the fixed path doesn't exist, fixpath probes alternate platform formats (WSL, MSYS, Windows) to find the actual file.

## Usage

```
dz fixpath [-o] [-l] [-c] [--verify] [-q] [paths ...]
dz fixpath config [show | default <action> | lister <name>]
```

### Action Flags

Every mode prints the fixed path to stdout. Flags add behavior on top:

| Flag | Description |
|------|-------------|
| (none) | Fix and print only |
| `-o`, `--open` | Also open file in default application |
| `-l`, `--lister` | Also open containing folder (select file) |
| `-c`, `--copy` | Also copy fixed path to clipboard |
| `--verify` | Show whether the path exists |
| `-q`, `--quiet` | Suppress warnings |

### Multiple Paths

```bash
dz fixpath "path1" "path2" "path3"
```

### Pipe from stdin

```bash
echo "C:\code\project/file.md" | dz fixpath
```

## Configuration

fixpath stores per-user settings in `~/.dazzlecmd/fixpath.json`.

### Set Default Action

```bash
dz fixpath config default copy     # Always copy to clipboard
dz fixpath config default open     # Always open in default app
dz fixpath config default lister   # Always open folder
dz fixpath config default print    # Just print (reset to default)
```

### Set File Manager

```bash
dz fixpath config lister dopus      # Directory Opus
dz fixpath config lister totalcmd   # Total Commander
dz fixpath config lister explorer   # Windows Explorer (default)
dz fixpath config lister --reset    # Reset to OS default
```

You can also pass any executable path for a custom file manager.

### View Config

```bash
dz fixpath config show
```

## Platform Notes

| Feature | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Path fixing | Full support | Full support | Full support |
| `--open` | `os.startfile` | `open` | `xdg-open` |
| `--lister` | `explorer /select,` (or dopus/totalcmd) | `open -R` | `xdg-open` (directory only) |
| `--copy` | `clip.exe` | `pbcopy` | `xclip`, `xsel`, or `wl-copy` |

For clipboard on Linux, install one of: `xclip`, `xsel`, or `wl-clipboard`. Or install `teeclip` for a unified solution: `pip install teeclip`.

## UNC Paths (Network)

fixpath handles UNC paths (`\\server\share`) with some caveats around shell escaping.

### What Works

| Input | Output |
|-------|--------|
| `//server/share/path` | `\\server\share\path` |
| `\\server\share\path` (in cmd.exe) | `\\server\share\path` |
| `\\server\share\path` (in Git Bash) | `\\server\share\path` (reconstructed from shell-mangled `\server\share`) |

### Shell Escaping

Shells eat backslashes. When you type `\\server\share` in Git Bash, Python receives `\server\share` (single backslash). fixpath detects this: if a `\server\share` path doesn't exist as a local path, it reconstructs the UNC form.

**Reliable approach**: use forward slashes for UNC in any shell:
```bash
dz fixpath //server/share/path
```

### Drive Letter Conversion

When `unctools` is installed, fixpath converts UNC paths to mapped drive letters when possible:

```bash
# If Z: maps to \\server\share:
dz fixpath //server/share/docs/file.txt
# -> Z:\docs\file.txt
```

If no mapping exists, the UNC path is preserved as-is.

## Optional Dependencies

| Package | What it adds |
|---------|-------------|
| `dazzle-filekit` | Enhanced path normalization and cross-platform resolution |
| `unctools` | UNC path conversion (network drives) |
| `teeclip` | Cross-platform clipboard support |

All optional -- fixpath works without them, with graceful fallbacks.

## See Also

- [dz links](links.md) -- uses the same path canonicalization engine
- [teeclip](https://pypi.org/project/teeclip/) -- cross-platform clipboard tool
- [dazzle-filekit](https://pypi.org/project/dazzle-filekit/) -- file operations toolkit
