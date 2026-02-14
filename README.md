# DazzleCMD (`dz`)

[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL%20v3-green.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](#cross-platform)

> **Many tools, one command.**

A unified CLI that aggregates many small standalone tools into a single discoverable, version-tracked interface. Instead of remembering where dozens of scripts live or hunting through folders, just use `dz <tool> [args]`.

## Why DazzleCMD?

Have you ever accumulated a collection of small utilities and handy scripts over the years -- spread across multiple folders, computers, some on network drives, some local, most not on GitHub -- and found yourself constantly forgetting where things live or what they're called?

Or maybe you've written a quick Python script to solve a problem, used it a few times, then couldn't find it six months later when you needed it again? Or you have tools that are useful but too small to justify their own GitHub repo, but also too valuable to leave scattered and unversioned?

Enter `dz`...

DazzleCMD provides a single entry point for all your tools. Each tool keeps its own structure and versioning. Dazzlecmd simply provides the discovery and dispatch layer. Tools that grow complex enough can "graduate" to their own repos (which can in turn be nested internal to "dz" as git submodules). Tools that stay small stay organized, easy to find, and simple to track.

## Features

- **Unified Dispatch**: Run any tool with `dz <tool> [args]` -- argparse-based with per-tool subparsers
- **Kit System**: Curated tool collections -- `core` ships with dazzlecmd, `dazzletools` bundles the default collection
- **Polyglot Support**: Python, shell, batch, compiled binaries -- dispatch handles runtime differences transparently
- **Progressive Scaffolding**: `dz new my-tool` starts minimal (blank canvas), `--simple` adds TODO/NOTES, `--full` adds roadmap and tests
- **Namespace Organization**: Tools grouped under `projects/<namespace>/<tool>/` to prevent collisions at scale
- **Platform-Aware**: Each tool declares both a quick-glance platform category and specific verified OS list
- **No Modification Required**: Existing scripts work as-is -- dazzlecmd wraps them, doesn't rewrite them

## Installation

```bash
pip install dazzle-dz
```

Or install from source:

```bash
git clone https://github.com/DazzleTools/dazzlecmd.git
cd dazzlecmd
pip install -e .
```

## Usage

```bash
# List all available tools
dz list

# Run a tool (all arguments pass through)
dz dos2unix myfile.txt
dz rn "(.*)\.bak" "\1.txt" *.bak
dz delete-nul C:\projects

# Get detailed info about a tool
dz info dos2unix

# List kits and their contents
dz kit list
dz kit list core
dz kit list dazzletools

# Create a new tool project
dz new my-tool                  # Bare minimum: manifest + script
dz new my-tool --simple         # + TODO.md, NOTES.md
dz new my-tool --full           # + ROADMAP.md, tests/, private/

# Version info
dz --version
```

## Included Tools

### Core Kit
These are the tools that ship with dazzlecmd. They are available everywhere and always active.

| Tool | Description | Platform |
|------|-------------|----------|
| `rn` | Rename files using regular expressions | Cross-platform |

### DazzleTools Kit
The default [DazzleTools](https://github.com/DazzleTools) collection.

| Tool | Description | Platform |
|------|-------------|----------|
| `dos2unix` | Pure-Python line ending converter (dos2unix/unix2dos) | Cross-platform |
| `delete-nul` | Delete Windows NUL device files created by accidental `>nul` redirection | Windows |
| `srch-path` | Search the system PATH for executables | Cross-platform |
| `split` | Split text by separator with optional token filtering | Cross-platform |

## How It Works

1. **Discovery**: On startup, `dz` scans `projects/<namespace>/<tool>/` for `.dazzlecmd.json` manifests
2. **Kit Filtering**: Only tools belonging to active kits are loaded
3. **Parser Assembly**: Each discovered tool gets an argparse subparser
4. **Dispatch**: When you run `dz <tool> [args]`, the runtime type determines how the tool executes:
   - `python` with `pass_through: false` → imports the module and calls the entry point directly
   - `python` with `pass_through: true` → runs via subprocess (for tools with non-standard signatures)
   - `shell` / `script` / `binary` → subprocess with appropriate interpreter

## Tool Manifests

Each tool has a `.dazzlecmd.json` manifest:

```json
{
    "name": "dos2unix",
    "version": "0.1.0",
    "description": "Pure-Python line ending converter",
    "namespace": "dazzletools",
    "language": "python",
    "platform": "cross-platform",
    "platforms": ["windows", "linux", "macos"],
    "runtime": {
        "type": "python",
        "entry_point": "main",
        "script_path": "dos2unix.py"
    },
    "taxonomy": {
        "category": "file-tools",
        "tags": ["text", "line-endings", "conversion"]
    }
}
```

## Project Structure

```
dazzlecmd/
├── src/dazzlecmd/            # Installable Python package
│   ├── cli.py                # Entry point, argparse dispatch
│   ├── loader.py             # Kit-aware project discovery
│   └── templates/            # Scaffolding templates for dz new
├── projects/                 # Tool projects by namespace
│   ├── core/                 # Core tools (ships with dazzlecmd)
│   │   └── rn/
│   └── dazzletools/          # DazzleTools collection
│       ├── dos2unix/
│       ├── delete-nul/
│       └── ...
├── kits/                     # Kit definitions (*.kit.json)
├── config/                   # JSON schema for manifests
└── scripts/                  # Version management and git hooks
```

## Cross-Platform

| Platform | Status |
|----------|--------|
| Windows  | Supported |
| Linux    | Supported |
| macOS    | Supported |

Individual tools may have platform-specific requirements -- check `dz info <tool>` for details.

## Related Projects

- [git-repokit](https://github.com/DazzleTools/git-repokit) -- Standardized Git repository creation tool
- [preserve](https://github.com/DazzleTools/preserve) -- Cross-platform file preservation with path normalization and verification
- [dazzlesum](https://github.com/DazzleTools/dazzlesum) -- Cross-platform file checksum utility

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

Like the project?

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)

## License

Copyright (C) 2026 Dustin Darcy

This project is licensed under the GNU General Public License v3.0 -- see the [LICENSE](LICENSE) file for details.
