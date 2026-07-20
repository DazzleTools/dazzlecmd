# DazzleCMD (`dz`)

[![PyPI](https://img.shields.io/pypi/v/dazzlecmd?color=green)](https://pypi.org/project/dazzlecmd/)
[![Release Date](https://img.shields.io/github/release-date/DazzleTools/dazzlecmd?color=green)](https://github.com/DazzleTools/dazzlecmd/releases)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/license-GPL%20v3-green.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![Installs](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/djdarcy/d10d1c2194e7a4842e323a9dacef2e08/raw/installs.json)](https://dazzletools.github.io/dazzlecmd/stats/#installs)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](#cross-platform)

> **A tool for tools: many tools, one command.**

A unified framework for tools -- and for how tools build on each other. DazzleCMD aggregates many small standalone tools into one discoverable, version-tracked interface, and lets them nest and grow into user collections (called "kits") and standalone aggregators. Instead of remembering where dozens of scripts live or hunting through folders, `dz <tool> [args]` works anywhere and is easy to fetch and run across multiple machines.

## Why DazzleCMD?

Have you ever accumulated a collection of small utilities and handy scripts over the years -- spread across multiple folders, computers, some on network drives, some local, most not on GitHub -- and found yourself constantly forgetting where things live or what they're called?

Or maybe you've written a quick Python script to solve a problem, used it a few times, then couldn't find it six months later when you needed it again? And when you did find it, it wasn't on the `$PATH` and it was tedious to invoke due to the long filepath? Or you have tools that are useful but too small to justify their own GitHub repo, but also too valuable to leave scattered and unversioned?

Enter `dz`...

DazzleCMD provides a single entry point for all your tools. Each tool keeps its own structure and versioning. Dazzlecmd simply provides the discovery and dispatch layer. Tools that grow complex enough can "graduate" to their own repos (which can in turn be nested internal to "dz" as git submodules). Tools that stay small stay organized, easy to find, and simple to track.

It isn't for just *your* tools either: `dz kit add <github-url>`. This pulls your own collection (or anyone else's kit or aggregator) onto any machine with a single command, making every tool instantly runnable, regardless of whatever language it happens to be written in. DazzleCMD provides package-manager convenience (think pip or brew) for scripts that never had to *become* packages first, making a plain folder of utilities cross-platform and shareable.

### And in the future...

Tools you *didn't* write are fair game too. 

On the roadmap: **recipes** -- wrap the commands you already use (`grep`, `fd`, `sed`, that one `ffmpeg` incantation) with the exact flags and environment variables that took an afternoon to get right. `dz grep.recipe` will list the grep invocations you've saved and `dz grep.env` the environment variables it cares about; `dz grep:recipe:1` replays one, remembered environment included -- *dot to look, colon to run*. It's an annotation system *and* the runtime for those annotations: instead of spelunking `.bash_history`, keeping a notes file, or maintaining machine-specific `setenv.sh`/`setenv.cmd` scripts, the working knowledge around your commands gets versioned with your repo. Pull it down on any machine (Windows, Linux, macOS, BSD) and it arrives ready to run.

In other words, `dz` quietly aims to be a portable build environment, growing outward from the dispatch layer (design: [#87](https://github.com/DazzleTools/dazzlecmd/issues/87)).

## Features

- **Unified Dispatch**: Run any tool with `dz <tool> [args]` -- argparse-based with per-tool subparsers
- **Kit System**: Curated tool collections -- `core` ships with dazzlecmd, `dazzletools` bundles the default collection
- **Polyglot Support**: Python, shell, batch, compiled binaries -- dispatch handles runtime differences transparently
- **Progressive Scaffolding**: `dz new tool my-tool` starts minimal (blank canvas), `--simple` adds TODO/NOTES, `--full` adds roadmap and tests
- **Namespace Organization**: Tools grouped under `projects/<namespace>/<tool>/` to prevent collisions at scale
- **Platform-Aware**: Each tool declares both a quick-glance platform category and specific verified OS list
- **No Modification Required**: Existing scripts work as-is -- dazzlecmd wraps them, doesn't rewrite them

#### Argparse for a whole toolbox

If `argparse` turns one script into a tidy CLI, `dz` does the same for a whole *collection* of tools -- across languages and runtimes. Each tool keeps its own language and environment (a Python script, a shell one-liner, a compiled C/C++ or C# binary, even a Dockerized step); `dz` is the single discoverable front door and dispatches to whatever each tool actually is. The pattern holds even when the only thing the tools share is the problem they solve. "Many tools, one command" is a way to assemble a project-specific CLI fast, without first turning every script into a package.

## Installation

```bash
pip install dazzlecmd
```

This installs the `dz` command (and its long form `dazzlecmd`). The PyPI package alias `dazzle-dz` installs the same tool. On most systems `dz` is immediately available; if your shell can't find it, see the next section.

**On externally-managed Python** (PEP 668 -- recent Debian/Ubuntu and similar block a system-wide `pip install`): install into a virtual environment, or use [pipx](https://pipx.pypa.io) (whose `pipx ensurepath` handles PATH for you):

```bash
pipx install dazzlecmd
# or: python -m venv .venv && .venv/bin/pip install dazzlecmd
```

Or install from source:

```bash
git clone https://github.com/DazzleTools/dazzlecmd.git
cd dazzlecmd
pip install -e .
```

### Problems running after installing?

**`dz` not found after install?** One command diagnoses and fixes it (it runs even though `dz` doesn't):

```bash
python -m dazzlecmd setup dazzlecmd
```

Then either run the printed activation line to use `dz` in your **current** shell (venv/conda-style), or just open a **new** terminal -- both work. Details, flags (`--yes`, `--dry-run`, `--clip`, `--emit-shell-fix`), and Linux/macOS notes: [docs/guides/troubleshooting.md](docs/guides/troubleshooting.md).

## Usage

```bash
# List all available tools
dz list

# Run a tool (all arguments pass through)
dz dos2unix myfile.txt
dz rn "(.*)\.bak" "\1.txt" *.bak
dz delete-nul C:\projects
dz links -r --type symlink,junction    # Find all symlinks and junctions recursively
dz links --broken                      # Find broken links in current directory

# Get detailed info about a tool
dz info dos2unix

# List kits and their contents
dz kit list
dz kit list core
dz kit list dazzletools

# Create a new tool (also: dz new kit, dz new aggregator)
dz new tool my-tool             # manifest + script
dz new tool my-tool --simple    # + TODO.md, NOTES.md
dz new tool my-tool --full      # + ROADMAP.md, private/claude/, tests/

# Version info
dz --version
```

## Included Tools

dazzlecmd ships with three kits plus a set of verb-grouped overlays:

- **core** (always active) -- `f-cp`, `f-mv`, `find`, `fixpath`, `links`, `listall`, `rn`, `safedel`
- **dazzletools** (always active) -- 19 cross-platform utilities, grouped into text/files, git/repo, Claude Code, Windows sysadmin, and archives
- **media** (opt-in: `dz kit enable media`) -- 7 `ffmpeg`-based video/audio/image/gif tools
- **virtual kits** -- `f:` / `md:` / `windows:` / `claude:` overlays that expose alias names for related tools under a shared prefix (`dz f:cp`, `dz md:unwrap`)

See the **[Tool Reference](docs/tools/README.md)** for the full per-kit listing, or run `dz list` to see what's active on your machine.

## How It Works

1. **Discovery**: On startup, `dz` scans `projects/<namespace>/<tool>/` for `.dazzlecmd.json` manifests
2. **Kit Filtering**: Only tools belonging to active kits are loaded
3. **Parser Assembly**: Each discovered tool gets an argparse subparser
4. **Dispatch**: When you run `dz <tool> [args]`, the runtime type determines how the tool executes:
   - `python` with `pass_through: false` → imports the module and calls the entry point directly (in-process)
   - `python` with `pass_through: true` → runs via subprocess (for tools with non-standard signatures)
   - `shell` / `script` / `binary` / `node` → subprocess with the appropriate interpreter
   - `docker` → runs the tool inside a container (`docker run`)

New runtime types can be registered by kits or third-party code (the dispatch is a pluggable factory registry), so the list above is the built-in set, not a hard limit.

## Tool Manifests

Each tool has a `.dazzlecmd.json` manifest. Only `name`, `version`, and `description` are required; the rest describe how the tool is dispatched, classified, and where it runs:

```json
{
    "name": "dos2unix",
    "version": "0.1.0",
    "description": "Pure-Python cross-platform line ending converter (dos2unix/unix2dos)",
    "namespace": "dazzletools",
    "language": "python",
    "platform": "cross-platform",
    "platforms": ["windows", "linux", "macos"],
    "runtime": {
        "type": "python",
        "entry_point": "main",
        "script_path": "dos2unix.py"
    },
    "pass_through": false,
    "taxonomy": {
        "category": "file-tools",
        "tags": ["text", "line-endings", "conversion", "dos2unix", "unix2dos"]
    },
    "lifecycle": {
        "status": "active"
    }
}
```

Optional fields not shown above (see [`config/dazzlecmd.schema.json`](config/dazzlecmd.schema.json) for the full schema): `dependencies` (python / system / external requirements), `build`, `fallback`, `kit`, and `source`.

## Project Structure

Most of what makes `dz` actually run lives in **`dazzlecmd_lib`** (the engine: discovery, dispatch, the kit/aggregator/state machinery, rendering) -- the `dz` CLI package is a comparatively thin entry point that drives it. The engine lives in its own repository, [DazzleLib/dazzlecmd-lib](https://github.com/DazzleLib/dazzlecmd-lib), and is published as its own package (`dazzlecmd-lib`) so other aggregators can build on the same engine. `dz` installs it as a dependency.

```
dazzlecmd/
├── packages/
│   └── dazzle-dz-alias/      # the `dazzle-dz` alias package (same tool, second name)
├── src/dazzlecmd/            # the `dz` CLI package (thin -- drives the engine)
│   ├── cli.py                # entry point + re-export facade
│   ├── parsers.py            # the argparse builder
│   ├── commands/             # per-verb handlers (kit, new, add, mode, setup)
│   ├── loader.py             # repo-local discovery shim
│   └── templates/            # scaffolding templates for dz new
├── projects/                 # Tool projects by namespace
│   ├── core/                 # Core tools (always active)
│   │   ├── f-cp/  f-mv/  find/  fixpath/  links/  listall/  rn/  safedel/
│   │   └── _f_common/        # shared metadata-preserving adapter for f-cp/f-mv
│   ├── dazzletools/          # DazzleTools collection (always active, 19 tools)
│   │   ├── dos2unix/  split/  srch-path/  delete-nul/  md-rm-img/  md-unwrap/
│   │   ├── git/  git-snapshot/  github/  private-init/
│   │   ├── claude-cleanup/  claude-session-metadata/  claudeview/  ...
│   │   ├── safe-icacls/  fixuser/  redact-msinfo/  extract-all/
│   │   └── .kit.json         # in-repo kit manifest (the tool list)
│   └── media/                # Media kit (opt-in: dz kit enable media, 7 tools)
│       ├── vid2gif/  vidresize/  img2vid/  crossfade/  song-to-vid/  ...
│       └── .kit.json
├── kits/                     # Kit registry pointers + virtual kits (*.kit.json)
├── config/                   # JSON schema for manifests
├── docs/                     # Guides + the per-kit tool reference (docs/tools/)
└── scripts/                  # Version management and git hooks
```

## Cross-Platform

| Platform | Status |
|----------|--------|
| Windows  | Supported |
| Linux    | Supported |
| macOS    | Supported |

Individual tools may have platform-specific requirements -- check `dz info <tool>` for details. See [Platform Support](docs/platform-support.md) for the full matrix.

## Documentation

- **[Core Tool Docs](docs/tools/core/)** -- detailed documentation for each core tool
- **[Creating Tools](docs/guides/creating-tools.md)** -- build your own dz tool
- **[Kits Guide](docs/guides/kits.md)** -- how the kit system works, the recursive architecture
- **[Manifest Reference](docs/guides/manifests.md)** -- `.dazzlecmd.json` schema
- **[Glossary](docs/glossary.md)** -- the vocabulary `dz` uses: tools, kits, levels, the lifecycle verbs, and how commands are addressed
- **[Platform Support](docs/platform-support.md)** -- OS compatibility matrix

## Related Projects

- [dazzlecmd-lib](https://github.com/DazzleLib/dazzlecmd-lib) -- the engine `dz` runs on: discovery, dispatch, the kit/aggregator/state machinery, and rendering. Published separately so other aggregators can build on the same core
- [wtf-windows](https://github.com/djdarcy/wtf-windows) -- "Many diagnostics, one command": a Windows-diagnostics CLI built on the DazzleCMD pattern (a downstream aggregator)
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
