# dz listall

Flexible directory structure listing with sorting, collection modes, and output formatting.

## Quick Start

```bash
# List current directory
dz listall -d .

# List with numeric-aware sorting
dz listall -d . -s sequence

# Show only directory structure
dz listall -d . -c dirs-only -fmt summary

# Copy listing to clipboard with Windows-style paths
dz listall -d src -o clip -dec windows

# Export to file
dz listall -d . -o file -f inventory.txt
```

## Usage

```
dz listall -d DIR [options]
```

### Required

| Flag | Description |
|------|-------------|
| `-d`, `--dir` | Directory path(s) to list (repeatable) |

### Path Styles (`-p`)

| Style | Description | Example |
|-------|-------------|---------|
| `full` | Absolute paths | `C:\code\project\src\main.py` |
| `rel` | Relative to target directory | `src\main.py` |
| `rel-base` | Relative with folder basename prefix (default) | `project\src\main.py` |
| `files-only` | Filenames only | `main.py` |

### Collection Modes (`-c`)

| Mode | Description |
|------|-------------|
| `all` | All files and directories (default) |
| `dirs-only` | Only directories |
| `dirs-1st-last-file` | First and last file per directory |
| `files-only` | Only files |

### Sort Strategies (`-s`)

| Strategy | Description |
|----------|-------------|
| `iname` | Case-insensitive alphabetical (default) |
| `name` | Case-sensitive alphabetical |
| `sequence` | Numeric-aware sort (file2 before file10) |
| `isequence` | Case-insensitive numeric-aware |
| `winsequence` | Windows Explorer style (underscores first) |
| `date` | By modification time |

### Output Targets (`-o`)

| Target | Description |
|--------|-------------|
| `stdout` | Print to terminal (default) |
| `clip` | Copy to clipboard |
| `file` | Write to file (use `-f` for filename) |
| `all` | All three targets |

### Output Formats (`-fmt`)

| Format | Description |
|--------|-------------|
| `inline` | One path per line (default) |
| `summary` | Indented tree structure |

### Decorators (`-dec`)

| Decorator | Description |
|-----------|-------------|
| `unix` | Forward slashes |
| `windows` | Backslashes |
| `rel-leader` | Prefix with `.\` or `./` |
| `no-leader` | No prefix |

### Other Flags

| Flag | Description |
|------|-------------|
| `-xd`, `--exclude` | Exclude patterns (repeatable) |
| `-cl`, `--collect-limit` | Truncate directories with more than N files |
| `-clm`, `--collect-limit-min` | Files shown in truncated dirs (default: 2) |
| `-bl`, `--base-label` | Custom label for rel-base prefix |
| `-i`, `--indent` | Indent spaces in summary mode (default: 2) |
| `-cb`, `--compact-braces` | Close braces on same line in summary mode |
| `--max-depth` | Skip subdirectories beyond this depth |
| `--strict-rel` | Error if relative path crosses drives |

## Examples

### Tree-style output
```bash
dz listall -d src -fmt summary -c all
```
```
src {
  dazzlecmd {
    __init__.py
    __main__.py
    cli.py
    importer.py
    loader.py
    mode.py
    _version.py
    templates {
      python_tool.py.tmpl
    }
  }
}
```

### Inventory for documentation
```bash
dz listall -d docs -s iname -p rel -o file -f docs-inventory.txt
```

### Multiple directories
```bash
dz listall -d src tests docs -p rel-base -s isequence
```

## Extended Help

Use `-h` with a topic name for detailed explanations:

```bash
dz listall -h path-style
dz listall -h sort
```

## Platform Notes

Works on all platforms. Decorator defaults match the current OS (backslashes on Windows, forward slashes on Unix).

## See Also

- `tree` -- built-in directory listing (less flexible)
- `find` / `dir` -- OS-level file listing
