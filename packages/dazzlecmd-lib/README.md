# dazzlecmd-lib

Engine library for building dazzlecmd-pattern tool aggregators.

## Quick Start

```python
from dazzlecmd_lib.engine import AggregatorEngine

def main():
    engine = AggregatorEngine(
        name="my-tools",
        command="mt",
        tools_dir="tools",
        kits_dir="kits",
        manifest=".mt.json",
        description="My tool collection",
        parser_builder=build_parser,
        meta_dispatcher=dispatch_meta,
        tool_dispatcher=dispatch_tool,
    )
    return engine.run()
```

## What's included

- **AggregatorEngine**: configurable CLI tool aggregator with recursive kit discovery
- **FQCNIndex**: dual-index lookup (exact FQCN + short-name precedence resolution)
- **RunnerRegistry**: extensible runtime dispatch (python, shell, binary, docker, etc.)
- **ConfigManager**: user config read/write with atomic writes and merge semantics
- **Kit discovery**: manifest-driven tool/kit loading with namespace remapping

## What's NOT included

- CLI commands (`dz list`, `dz kit enable`, etc.) -- those live in the `dazzlecmd` package
- Scaffolding UI (`dz new tool`, `dz new aggregator`) -- reference implementation
- Dev/publish mode toggle -- dazzlecmd-specific workflow
- Tool import via symlinks -- dazzlecmd-specific workflow

## License

GPL-3.0-or-later
