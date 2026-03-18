# dz links

Detect and display all types of filesystem links and shortcuts.

## Quick Start

```bash
# Scan current directory for any links
dz links

# Recursive scan
dz links -r

# Find broken links
dz links --broken

# Show only symlinks and junctions
dz links --type symlink,junction

# Verbose output with inodes and full paths
dz links -v ~/Desktop
```

## Detected Link Types

| Type | Extension/Mechanism | Detection Method |
|------|---------------------|------------------|
| `symlink` | OS-level symbolic link | `os.path.islink()` |
| `junction` | Windows directory reparse point | ctypes `DeviceIoControl` + reparse tag |
| `hardlink` | Multiple directory entries, same inode | `st_nlink > 1` + `FindFirstFileNameW` |
| `shortcut` | `.lnk` Shell Link files | Binary parser (MS-SHLLINK format) |
| `urlshortcut` | `.url` Internet Shortcut files | INI-format parser |
| `dazzlelink` | `.dazzlelink` JSON descriptors | JSON parser |

## Usage

```
dz links [-r] [-t TYPE] [-b] [-j] [-v] [paths ...]
```

| Flag | Description |
|------|-------------|
| `-r`, `--recursive` | Scan directories recursively |
| `-t`, `--type TYPE` | Filter by link type (comma-separated) |
| `-b`, `--broken` | Show only broken links |
| `-j`, `--json` | Output as JSON |
| `-v`, `--verbose` | Show inode, size, full paths |
| `paths` | Files or directories to scan (default: `.`) |

## Examples

### Default output
```
  private/      junction     -> C:\code\dazzlecmd\local\private
  config.lnk    shortcut     -> C:\Users\Me\AppData\config.json

  2 link(s) found: 1 junction, 1 shortcut
```

### Verbose output (`-v`)
```
  tab02.txt
    path:    C:\Users\Me\Desktop\window04\tab02.txt
    target:  C:\Users\Me\Desktop\Notepad Organize\window06\tab01.txt
    type:    hardlink
    links:   2
    inode:   5629499534945078
    size:    848 bytes
```

### JSON output (`-j`)
```json
[
  {
    "path": "C:\\code\\project\\private",
    "name": "private",
    "link_type": "junction",
    "target": "C:\\code\\project-local\\private",
    "broken": false,
    "link_count": 1,
    "inode": 16044073676680806,
    "size": 0,
    "is_dir": true
  }
]
```

### Scan Start Menu for shortcuts
```bash
dz links -r "C:\ProgramData\Microsoft\Windows\Start Menu\Programs"
```

### Find broken shortcuts
```bash
dz links -r --broken "C:\ProgramData\Microsoft\Windows\Start Menu"
```

## Path Input

Accepts any path format -- MSYS (`/c/path`), forward slashes, native Windows, or WSL (`/mnt/c/`). All are canonicalized before scanning.

## .lnk Parser

The `.lnk` binary parser handles the full MS-SHLLINK format:
- Resolves targets via StringData relative paths (most reliable)
- Falls back to LinkInfo local base path
- Handles network/UNC paths
- Supports Unicode and CP1252 encodings

## Platform Notes

| Feature | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Symlinks | Yes | Yes | Yes |
| Junctions | Yes (ctypes) | N/A | N/A |
| Hardlink targets | Yes (`FindFirstFileNameW`) | Link count only | Link count only |
| `.lnk` parsing | Yes | Yes (if files present) | Yes (if files present) |
| `.url` parsing | Yes | Yes | Yes |

## Optional Dependencies

| Package | What it adds |
|---------|-------------|
| `dazzle-filekit` | Enhanced path normalization |
| `unctools` | UNC path conversion |

## See Also

- [dz fixpath](fixpath.md) -- shares the path canonicalization engine
- [dazzlelink](https://github.com/DazzleTools/dazzlelink) -- `.dazzlelink` file management
