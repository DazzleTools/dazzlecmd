# dazzlecmd (`dz`)

Unified CLI for the DazzleTools collection - many tools, one command.

## Overview

DazzleCMD aggregates many small standalone tools into a single discoverable, version-tracked interface. Instead of remembering where dozens of scripts live or which repo they're in, just use `dz <tool> [args]`.

Tools live as projects within the `projects/` directory, organized by namespace. Each tool keeps its own versioning and structure — dazzlecmd provides the discovery and dispatch layer.

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
# List available tools
dz list

# Run a tool (passes all arguments through)
dz dos2unix myfile.txt
dz delete-nul C:\projects
dz rn *.txt --dry-run

# Get info about a tool
dz info dos2unix

# Show version
dz --version

# List available kits
dz kit list

# Create a new tool project
dz new my-tool                # Bare minimum (blank canvas)
dz new my-tool --simple       # + TODO.md, NOTES.md
dz new my-tool --full         # + ROADMAP.md, private/claude/, tests/
```

## Project Structure

```
dazzlecmd/
├── src/dazzlecmd/          # Installable Python package
│   ├── cli.py              # Main entry point and dispatch
│   ├── loader.py           # Kit-aware project discovery
│   └── templates/          # Scaffolding templates
├── projects/               # Tool projects organized by namespace
│   └── dazzletools/        # Default namespace
│       ├── dos2unix/
│       ├── delete-nul/
│       └── ...
├── kits/                   # Kit definitions (*.kit.json)
│   ├── core.kit.json
│   └── dazzletools.kit.json
├── config/                 # Schema and configuration
└── scripts/                # Version management and git hooks
```

## Kits

Kits are curated collections of tools. The `core` kit (CLI framework) and `dazzletools` kit (default utilities) are always active.

## Adding Tools

Each tool lives in `projects/<namespace>/<tool>/` with a `.dazzlecmd.json` manifest describing how to run it. Tools can be Python scripts, shell scripts, compiled binaries, or any executable — dazzlecmd handles dispatch.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)
