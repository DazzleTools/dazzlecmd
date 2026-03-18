# Creating Tools

This guide walks you through creating a new tool for dazzlecmd, from scaffolding to kit registration.

## Quick Start

```bash
# Create a new tool in the dazzletools namespace
dz new my-tool --namespace dazzletools --description "Does something useful"

# Or in the core namespace (for tools that ship with dazzlecmd)
dz new my-tool --namespace core --description "A fundamental utility"
```

This creates:

```
projects/<namespace>/my-tool/
  .dazzlecmd.json    # Tool manifest
  my_tool.py         # Entry point with main(argv) stub
```

## The Entry Point

Every tool needs a `main(argv=None)` function:

```python
"""
my-tool - Does something useful
"""

import argparse
import sys


def main(argv=None):
    """Entry point for my-tool."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="dz my-tool",
        description="Does something useful",
    )
    parser.add_argument("input", help="Input file")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    # Your tool logic here
    print(f"Processing: {args.input}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

The tool must:
- Accept `argv` as a parameter (list of strings, like `sys.argv[1:]`)
- Return an integer exit code (0 for success)
- Be runnable standalone (`python my_tool.py --help`)

## The Manifest

`.dazzlecmd.json` tells dazzlecmd how to find and run your tool:

```json
{
    "name": "my-tool",
    "version": "0.1.0",
    "description": "Does something useful",
    "namespace": "dazzletools",
    "language": "python",
    "platform": "cross-platform",
    "platforms": ["windows", "linux", "macos"],
    "runtime": {
        "type": "python",
        "entry_point": "main",
        "script_path": "my_tool.py"
    },
    "pass_through": false,
    "taxonomy": {
        "category": "file-tools",
        "tags": ["utility", "files"]
    },
    "lifecycle": {
        "status": "active"
    }
}
```

See the [Manifest Reference](manifests.md) for all fields.

## Runtime Types

| Type | `pass_through` | How it runs |
|------|----------------|-------------|
| `python` | `false` | Imports module, calls `main(argv)` directly (fastest) |
| `python` | `true` | Runs via `subprocess` (for tools with non-standard signatures) |
| `shell` | N/A | Runs shell script (bash, cmd, pwsh) |
| `script` | N/A | Runs with explicit interpreter |
| `binary` | N/A | Runs executable directly |

Most tools should use `python` with `pass_through: false` for direct import.

## Kit Registration

After creating your tool, register it in a kit so `dz` can discover it:

Edit `kits/<namespace>.kit.json`:

```json
{
    "name": "dazzletools",
    "tools": [
        "dazzletools:my-tool"
    ]
}
```

The format is `namespace:tool-name`. Once registered, your tool appears in `dz list` and can be run as `dz my-tool`.

## Progressive Scaffolding

`dz new` supports three levels of project structure:

```bash
# Bare minimum: manifest + script
dz new my-tool

# Add planning files: TODO.md, NOTES.md
dz new my-tool --simple

# Full project: ROADMAP.md, tests/, private/claude/
dz new my-tool --full
```

You can layer extras onto an existing project:

```bash
dz new my-tool --full  # Adds the extra files without recreating existing ones
```

## Testing Your Tool

```bash
# Run directly
python projects/dazzletools/my-tool/my_tool.py --help

# Run through dz (after kit registration)
dz my-tool --help

# Run the dazzlecmd test suite
pytest
```

## Next Steps

- Read about [Kits](kits.md) to understand namespaces and distribution
- Read the [Manifest Reference](manifests.md) for all configuration options
- Look at existing core tools (`projects/core/`) for real-world examples
