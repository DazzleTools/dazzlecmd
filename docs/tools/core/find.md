# dz find

Cross-platform file search powered by [fd](https://github.com/sharkdp/fd).

## Quick Start

```bash
dz find README.md                     # Find a specific file
dz find "*.md" --dir docs             # Find markdown files in docs/
dz find "*postmortem*" -o             # Find and open in default app
dz find -e py --count                 # Count all Python files
dz find --check                       # Verify fd is installed
```

## Why dz find instead of fd directly?

fd is excellent, but `dz find` adds the dazzlecmd action layer on top:

- **`-o` (open)**: Find a file and open it in one command -- no piping or `xargs`
- **`-l` (lister)**: Find a file and reveal it in your file manager (Directory Opus, Explorer, Finder)
- **`-c` (copy)**: Find a file and copy its path to your clipboard
- **fixpath integration**: `dz fixpath creating-tools.md -o` searches for the file when the path doesn't resolve
- **Consistent cross-platform actions**: Same flags work on Windows, macOS, and Linux -- no remembering `os.startfile` vs `open` vs `xdg-open`

If you just need search results, `fd` is perfect on its own. `dz find` is for when you want to act on what you find.

## Requirements

Requires `fd` to be installed:

| Platform | Install |
|----------|---------|
| Windows | `winget install sharkdp.fd` or `choco install fd` |
| macOS | `brew install fd` |
| Debian/Ubuntu | `apt install fd-find` |
| Arch | `pacman -S fd` |
| FreeBSD | `pkg install fd` |

Run `dz find --check` to verify installation.

## Usage

```
dz find [pattern] [--dir DIR] [options] [-o|-l|-c]
```

### Search

| Flag | Description |
|------|-------------|
| `pattern` | Glob pattern (default) or regex with `--regex` |
| `--dir DIR` | Directory to search (repeatable, default: CWD) |
| `--regex` | Use regex instead of glob |
| `--case-sensitive` | Case-sensitive (default: case-insensitive) |
| `-H`, `--hidden` | Include hidden files |
| `--no-ignore` | Don't respect .gitignore |
| `-d`, `--depth N` | Maximum search depth |
| `-t`, `--type` | Filter: `file`, `dir`, `symlink` |
| `-e`, `--extension` | Filter by extension (e.g., `md`, `py`) |
| `-S`, `--size` | Filter by size (e.g., `+1M`, `-100k`) |
| `--newer DATE` | Changed within duration/date (e.g., `1week`) |
| `--older DATE` | Changed before duration/date |
| `-E`, `--exclude` | Exclude pattern (repeatable) |

### Actions

| Flag | Description |
|------|-------------|
| `-o`, `--open` | Open first result in default app |
| `-l`, `--lister` | Open containing folder of first result |
| `-c`, `--copy` | Copy result path(s) to clipboard |

### Output

| Flag | Description |
|------|-------------|
| `--first` | Act on first result only (skip selection) |
| `--all` | Act on all results |
| `--count` | Print count of matches only |

## Examples

```bash
# Find by extension in a specific directory
dz find -e json --dir kits

# Find files modified in the last week
dz find "*.py" --newer 1week

# Find large log files
dz find "*.log" -S +1M

# Regex search
dz find --regex "test_.*\.py$" --dir tests

# Find and copy path to clipboard
dz find "*.md" -c

# Exclude directories
dz find -e py -E node_modules -E __pycache__

# Search with depth limit
dz find "*.json" -d 2
```

## Integration with fixpath

`dz fixpath` uses `dz find` (via fd) as a fallback when a bare filename doesn't resolve:

```bash
# fixpath tries to fix the path, then searches if it's a bare filename
dz fixpath creating-tools.md -o

# Explicit search mode
dz fixpath -f "*postmortem*"

# Skip path fixing, go straight to search
dz fixpath --skip "kits.md"
```

## Platform Notes

fd works on Windows, Linux, macOS, and BSD. On Debian/Ubuntu, the binary is named `fdfind` (due to a naming conflict with `fdclone`). `dz find` checks both names automatically.

## See Also

- [fd documentation](https://github.com/sharkdp/fd)
- [dz fixpath](fixpath.md) -- uses dz find as a search fallback
