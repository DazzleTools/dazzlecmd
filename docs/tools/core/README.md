# Core Kit

The core kit ships with every dazzlecmd installation. These are fundamental, universally useful tools -- the "coreutils" of dazzlecmd.

## Tools

| Tool | Description | Platform |
|------|-------------|----------|
| [find](find.md) | Cross-platform file search powered by fd | Cross-platform |
| [fixpath](fixpath.md) | Fix mangled paths, search for files, open/copy/browse | Cross-platform |
| [links](links.md) | Detect and display all filesystem link types | Cross-platform |
| [listall](listall.md) | Flexible directory structure listing with sorting and output formatting | Cross-platform |
| [rn](rn.md) | Rename files using regular expressions | Cross-platform |

## Design Principles

Core tools are:
- **Zero-dependency** -- they work with Python's standard library alone (optional deps enhance but aren't required)
- **Cross-platform** -- tested on Windows, expected to work on Linux and macOS
- **Self-contained** -- each tool is a single Python file with a `main(argv)` entry point
- **Discoverable** -- `dz list`, `dz info <tool>`, and `dz <tool> --help` provide all the information you need

## Always Active

Core tools are loaded regardless of kit selection. They're registered in `kits/core.kit.json` with `"always_active": true`.
