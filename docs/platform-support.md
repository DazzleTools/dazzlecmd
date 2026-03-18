# Platform Support

dazzlecmd is designed to work across Windows, Linux, and macOS. The framework itself is pure Python (3.8+) with no required dependencies. Individual tools may have platform-specific capabilities.

## Framework Support

| Component | Windows | Linux | macOS |
|-----------|---------|-------|-------|
| `dz` CLI | Tested | Tested (CI) | Expected |
| Kit discovery | Tested | Tested (CI) | Expected |
| Tool dispatch | Tested | Tested (CI) | Expected |
| `dz new` scaffolding | Tested | Tested (CI) | Expected |
| `dz add --link` | Tested (junction/symlink) | Expected (symlink) | Expected (symlink) |
| `dz mode` toggle | Tested | Expected | Expected |

## Core Tool Support

| Tool | Windows | Linux | macOS | Notes |
|------|---------|-------|-------|-------|
| **fixpath** | Full | Full | Full | `--lister` uses `xdg-open` (dir only) on Linux |
| **links** | Full (6 types) | Partial (4 types) | Partial (4 types) | Junctions are Windows-only; hardlink targets need `FindFirstFileNameW` (Windows) |
| **listall** | Full | Full | Full | Decorators default to OS-native separators |
| **rn** | Full | Full | Full | |

### links: Per-Type Platform Matrix

| Link Type | Windows | Linux | macOS |
|-----------|---------|-------|-------|
| Symlinks | Yes | Yes | Yes |
| Junctions | Yes (ctypes) | N/A | N/A |
| Hardlinks (detection) | Yes | Yes | Yes |
| Hardlinks (target resolution) | Yes (`FindFirstFileNameW`) | Count only | Count only |
| `.lnk` shortcuts | Yes | Yes (if files present) | Yes (if files present) |
| `.url` shortcuts | Yes | Yes | Yes |
| `.dazzlelink` | Yes | Yes | Yes |

### fixpath: Per-Feature Platform Matrix

| Feature | Windows | Linux | macOS |
|---------|---------|-------|-------|
| Path fixing | Full | Full | Full |
| `--open` | `os.startfile` | `xdg-open` | `open` |
| `--lister` | Explorer, Directory Opus, Total Commander | `xdg-open` (directory) | `open -R` (Finder, select) |
| `--copy` | `clip.exe` | `xclip`/`xsel`/`wl-copy` | `pbcopy` |

## CI Testing

The CI pipeline (`main.yml`) tests on Ubuntu with Python 3.8-3.13. Windows testing is done on the primary development machine (Windows 11).

## Known Limitations

- **Windows junctions** require `ctypes` access to `kernel32.dll` -- not available in all Python environments (e.g., some sandboxed containers)
- **Linux clipboard** requires an external tool (`xclip`, `xsel`, or `wl-clipboard`). Install `teeclip` for a unified solution.
- **macOS** is expected to work but not regularly tested. File issues if you encounter problems.
