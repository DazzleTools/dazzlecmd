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

## Public API -- frozen until 1.0 (Gate I)

As of dazzlecmd-lib **0.8.0**, the DazzleEntity object model and the Groupable
verb/state contracts are **settled**. These surfaces follow semantic versioning
and will not change incompatibly before 1.0 (each module declares its public
names in `__all__`):

- **`dazzlecmd_lib.entity`** -- the typed object model: `DazzleEntity` (+ the
  `Tool` / `Kit` / `Aggregator` discriminated union, `AnyDazzleEntity`,
  `ENTITY_ADAPTER`), the `Groupable` capability mixin, and
  `build_entity` / `detect_type` / `reserve_field_axis`. Access is by typed
  attribute (`entity.runtime`, `entity.fqcn`) plus `extra_get` / `extra_set` /
  `has_extra` for the untyped remainder. The dict shim was removed in 0.8.0.
  **The `extra` contract** (exactly three categories live there, each for a
  stated reason): (1) genuinely polymorphic blocks (`source` -- kit str vs tool
  dict, consumed schema-driven via `aggregator_config.remote_url_paths`);
  (2) `_`-prefixed manifest data (`_vars`, `_schema_version` -- a Pydantic
  field-naming constraint); (3) novel/unmodeled keys (`extra="allow"`,
  open-world manifests). Everything else -- including the nested-aggregator
  keys `tools_dir` / `manifest` and the engine overrides
  `override_tools_dir` / `override_manifest` -- is a typed field.
- **`dazzlecmd_lib.groupable`** -- the five state-transition verbs as the
  `{P, not-P}` boundary primitive (`rebind` / `hide` / `expose` / `group` /
  `ungroup`). Each verb on `Groupable` delegates to a typed `*Context`
  (`AliasRebindContext`, `ModeRebindContext` [in `mode`], `VisibilityContext`,
  `ContainmentContext`) and returns a frozen `*Receipt` carrying a C2 `*Invariant`;
  `CriticalityBoundaryError` marks a refused (criticality) transition. Plus the
  visibility ladder (`VISIBILITY_LADDER` / `VISIBILITY_CHANNELS`) and `Frame`.
- **`dazzlecmd_lib.states`** -- the state system: `StateAxis` / `EntityState`
  (observed, not stored) / `Transition` / `CompositeTransition` /
  `TransitionRegistry`; `Reversibility` (the criticality algebra);
  `assert_round_trip` (the `group o ungroup = identity` harness); `observe` (the
  platform-to-model bridge); `build_default_registry`.
- **`dazzlecmd_lib.aggregator_config`** -- the declarative aggregator schema.

The engine / loader / dispatch internals (`AggregatorEngine`, `FQCNIndex`, ...)
remain free to evolve; the contract above is the stable seam consumers build on.

## License

GPL-3.0-or-later
