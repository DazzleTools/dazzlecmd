# Core Kit

The core kit ships with every dazzlecmd installation. These are fundamental, universally useful tools -- the "coreutils" of dazzlecmd.

## Tools

| Tool | Description | Platform |
|------|-------------|----------|
| `f-cp` | Safe copy with full metadata preservation (mtime/atime/ctime, ACLs, attributes) and clobber protection | Cross-platform |
| `f-mv` | Safe move with full metadata preservation; always verifies the copy before deleting the source | Cross-platform |
| [find](find.md) | Cross-platform file search powered by fd (with `--` fd passthrough and `-0`/`--print0`) | Cross-platform |
| [fixpath](fixpath.md) | Fix mangled paths, search for files, open/copy/browse | Cross-platform |
| [links](links.md) | Detect and display all filesystem link types | Cross-platform |
| [listall](listall.md) | Flexible directory structure listing with sorting and output formatting | Cross-platform |
| [rn](rn.md) | Rename files using regular expressions | Cross-platform |
| `safedel` | Safe, link-aware, recoverable deletion -- stages files to a trash store instead of destroying them | Cross-platform |

`f-cp` / `f-mv` need [`preservelib`](https://github.com/dazzletools) (and `pywin32` on Windows for `ctime`/ACLs); the rest are stdlib (`find` shells out to `fd`). Tools without a linked page above are documented via `dz info <tool>` and `dz <tool> --help`.

## Design Principles

Core tools are:
- **Zero-dependency** -- they work with Python's standard library alone (optional deps enhance but aren't required)
- **Cross-platform** -- tested on Windows, expected to work on Linux and macOS
- **Self-contained** -- each tool is a single Python file with a `main(argv)` entry point
- **Discoverable** -- `dz list`, `dz info <tool>`, and `dz <tool> --help` provide all the information you need

## Always Active

Core tools are loaded regardless of kit selection. They're registered in `kits/core.kit.json` with `"always_active": true`.
