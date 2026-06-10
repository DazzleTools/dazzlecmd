# Changelog -- dazzlecmd-lib

All notable changes to the `dazzlecmd-lib` package are documented here.

The library is a standalone framework for building dazzlecmd-pattern tool aggregators. Existing consumers include [dazzlecmd](https://github.com/DazzleTools/dazzlecmd) itself, [amdead](https://github.com/DazzleTools/amdead), and `wtf-windows`. The library does not require dazzlecmd to be installed; it is meant to stand alone.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/). The library is pre-1.0 and reserves the right to make breaking changes during MINOR bumps until 1.0.

The library ships co-located with dazzlecmd today (in the `packages/dazzlecmd-lib/` subdirectory of the dazzlecmd repository). Future repo extraction is tracked as item X-1 in the dazzlecmd master closeout plan; once extracted, this CHANGELOG continues unchanged in its own repo.

## [0.8.11] - 2026-06-10

Ships with dazzlecmd v0.9.9 -- absolute FQCNs are now always RESOLVABLE (dispatch + info), not just derivable (FQCN-identity, the "always honored" follow-up). Additive.

### Added

- `AggregatorEngine._absolute_to_local(name)` -- normalizes an absolute FQCN to its dispatchable local form (inverse of `absolute_fqcn`): `dazzlecmd:core:f-cp` -> `core:f-cp`, `dazzlecmd_lib:core:safedel` -> `core:safedel`. Called at the top of `resolve_command`, so BOTH dispatch (`dz <absolute>`) and `dz info <absolute>` honor a real path -- it resolves like the prefixless name. Chained prefixes (`dazzlecmd:wtf:core:restarted`) reduce to the surfaced form.
- `dz list` epilogue legend for `[lib]`: explains the constitutional engine home + that names show prefixless while the absolute prepends the aggregator (both resolve).

### Fixed

- `dz info dazzlecmd_lib:core:safedel` (and `dz dazzlecmd:core:f-cp`) previously failed ("not found" / "invalid choice"); a real absolute path now always resolves.

## [0.8.10] - 2026-06-10

Ships with dazzlecmd v0.9.8 -- absolute FQCN as a real derivable core concept; walk back the v0.9.7 fake `Canonical:` field (FQCN-identity DWP Phase 0-1). Additive.

### Added

- `AggregatorEngine.absolute_fqcn(project)` -- the true, globally-unique absolute FQCN, ALWAYS derivable (derived, not stored): `<aggregator>:<namespace>:<name>` for native tools (`dazzlecmd:core:f-cp`), or the lib home `dazzlecmd_lib:core:<name>` for constitutional tools (overlaid here). The prefixless `project.fqcn` is a projection of this.

### Changed

- `dz info` shows `Absolute:` (the derived absolute FQCN) for EVERY tool, replacing the v0.9.7 `Canonical:` line -- which was constitutional-only AND not dispatchable (`dz dazzlecmd_lib:core:safedel` -> invalid choice; a fake rival FQCN). Constitutional tools are annotated `(constitutional; overlaid from dazzlecmd_lib)`. Fixes the asymmetry.

## [0.8.9] - 2026-06-10

Ships with dazzlecmd v0.9.7 -- constitutional core identity surfaced in `dz list` / `dz info` (#179 follow-up). Additive.

### Added

- `dazzlecmd_lib.core.is_constitutional(name)` / `constitutional_names()` / `canonical_fqcn(name)` -- the constitutional-identity API. A tool whose engine lives in `dazzlecmd_lib.core` (safedel, links) has canonical FQCN `dazzlecmd_lib:core:<name>` (Scheme O / "bones"); `core:<name>` is the consumer projection (Scheme P / "skin").
- `dz list` marks constitutional core tools `[lib]`; `dz info` shows their canonical FQCN (`Canonical: dazzlecmd_lib:core:safedel (constitutional)`). Surfaces the real home of the relocated primitives.

### Changed

- `core/__init__.py` docstring updated: safedel + links are now CURRENT inhabitants (were "future"), reflecting the v0.9.4-v0.9.6 relocation.

## [0.8.8] - 2026-06-10

Ships with dazzlecmd v0.9.6 -- the safedel tool imports the engine from the lib; the duplicate tool-side engine is removed (slice 3 of 3; #38 reframe / #179). One engine, in the lib.

### Changed

- The `projects/core/safedel/` TOOL now imports the engine from `dazzlecmd_lib.core.safedel` (its CLI + 12 test files + `api.py` shim rewired to lib imports); the tool's duplicate engine modules are removed (preserved in `private/revisions/`). The tool keeps only the CLI, the `api` shim, and its `log_lib` usage.
- New **Windows-only** runtime dependency: `unctools>=0.1.0; sys_platform=='win32'` -- the trash engine's per-volume routing (`_volumes`) needs Windows drive-type detection (network/removable/fixed); POSIX uses the in-module stubs. (Editable-installed in dev; flagged for review -- could be replaced with stdlib `GetDriveType` later.)

### Fixed

- `core.safedel._recover`: a function-level `from _timepattern import ...` (a bare import the slice-1 relocation's line-start sed missed) is now relative. It was latent -- masked by the tool's duplicate copy on `sys.path` until that copy was removed.

## [0.8.7] - 2026-06-10

Ships with dazzlecmd v0.9.5 -- the mode swap removes via the lib `core.safedel` primitive; the safedel-absent FALLBACK is deleted (slice 2 of 3; #38 reframe / #179). CLI byte-identical.

### Removed

- `mode._load_safedel_api` + `_SAFEDEL_API_CACHE_KEY` (the v0.8.4 tool-loading shim) and the "safedel absent -> `shutil.rmtree`" FALLBACK branch. The recoverable-delete capability is now internal to the lib (`dazzlecmd_lib.core.safedel`), so it is always available to every aggregator -- there is no absent case to fall back from, and no dead-code fallback path.

### Changed

- `mode._remove_tool_dir_recoverable` -> `mode._remove_tool_dir`: removes a tool directory via `dazzlecmd_lib.core.safedel.TrashStore().trash()` by default (recoverable). A backup FAILURE aborts the swap unless `--force`.

### Added

- `immediate` parameter on the swap path (`cmd_switch` / `_switch_to_dev` / `_switch_to_publish`) -- a deliberate CHOICE to delete the old tool directory immediately with no recovery backup. NOT a fallback: the recoverable path is the default and always works.

## [0.8.6] - 2026-06-10

Ships with dazzlecmd v0.9.4 -- the recoverable-delete engine becomes a constitutional lib primitive (slice 1 of 3; #38 reframe / #37 Bucket D). Additive; CLI byte-identical.

### Added

- `dazzlecmd_lib.core.safedel` -- the recoverable-delete engine (`TrashStore`, `stage_to_trash`, `safe_delete`, `classify`, the `cmd_recover`/`cmd_list`/`cmd_clean`/`cmd_status` recovery surface) relocated from the `projects/core/safedel/` tool into the constitutional `dazzlecmd_lib.core` namespace. Every aggregator built on the lib now gets recoverable deletion **automatically** -- it is no longer an opt-in tool that may be absent. This is the foundation for removing the mode-swap "safedel absent -> rmtree" fallback (the capability is internal to the lib, so there is no absent case to fall back from). Metadata preservation comes from `dazzle_filekit.metadata`; link detection from `dazzlecmd_lib.core.links`.
- `dazzlecmd_lib.core.links` now also re-exports the link DETECTION surface (`detect_link`, `LinkInfo`, `canonicalize_path`, the `LINK_*` varieties), relocated from the `links` tool so lib code imports it as a normal package instead of via a sibling-tool `sys.path` hack.

### Changed

- New runtime dependency: `dazzle-filekit>=0.2.2` -- the canonical home of the cross-platform metadata-preservation code (ACLs/ADS/timestamps/xattrs) the trash engine uses.

This slice is purely additive (the lib gains the engine). mode.py's adoption (removing the fallback + the `--immediate` choice) and the tool's rewire to import from the lib follow in the next two slices.

## [0.8.5] - 2026-06-10

Ships with dazzlecmd v0.9.3 -- EMBEDDED-swap enablement + config schema stamp (#37 Phase-3.5 Bucket D, items 3.5-1 / 3.5-12). Additive; CLI byte-identical.

### Added

- `mode.MODE_LOCAL_SCHEMA_VERSION` (= 1) -- `mode_local.json` is now stamped with a `_schema_version` on every save (`_save_full_config`), so a future on-disk format change can detect and migrate old configs (item 3.5-12).

### Changed

- `mode._determine_target` returns `"dev"` for `STATE_EMBEDDED` (was `None`) -- a bare `dz mode switch <embedded-tool>` now toggles an embedded checkout to a dev symlink instead of refusing with "no mode toggle available" (item 3.5-1). This was gated on data safety: it is enabled now that the swap removes the embedded directory RECOVERABLY via safedel (the v0.8.4 adoption), so the only-local embedded content is staged to the trash store before removal.

## [0.8.4] - 2026-06-10

Ships with dazzlecmd v0.9.2 -- safedel adoption in the mode swap (#38 / Phase-3.5 item 3.5-10). Additive; CLI byte-identical.

### Added

- `mode._load_safedel_api(project_root, tools_dir)` -- loads safedel's public API (`<tools_dir>/core/safedel/api.py`) if present, anchored on the aggregator's `project_root` so it resolves identically in a dev checkout and a pip install. Returns `None` (graceful) when safedel isn't on disk.
- `mode._remove_tool_dir_recoverable(...)` -- the mode swap now stages a tool directory to safedel's recoverable trash store before removing it (recover via `<command> safedel recover last`), instead of an unrecoverable `shutil.rmtree`. Applied at both delete sites (`_switch_to_dev`, `_switch_to_publish`).

### Changed

- When safedel is present (dazzlecmd always ships it), a backup FAILURE aborts the swap before any deletion unless `--force`. When safedel is absent (e.g. wtf-windows / amdead, which don't ship it), the swap falls back to `shutil.rmtree` with a note -- the dirty-tree gate (T1-E) remains the safety boundary, preserving the "a clean tree switches freely" contract.

**Implementation note (two empirical revisions to the #38 DWP):** (1) safedel's modules use BARE imports (`from _store import ...`) and run as a plain-script CLI, so `api.py` matches that convention and the loader puts the safedel dir on `sys.path` -- it is NOT turned into a dotted `projects.core.*` package (which would break safedel's CLI), and no `__init__.py` is added. (2) The DWP recommended REFUSE-by-default when safedel is unavailable; implementation used the backward-compatible fallback above instead, because the only aggregator shipping safedel is dazzlecmd (which always gets the recoverable path) and an existing test encodes the clean-tree-switches-freely contract a hard refusal would break. The policy is a single clearly-marked branch, trivially flippable to strict-refuse.

## [0.8.3] - 2026-06-10

Ships with dazzlecmd v0.8.34 -- #84 certification cleanup. Additive.

### Removed

- Orphaned `_CAP_DEFERRED` ClassVar in `entity.py` (defined, zero references -- no `NotImplementedError` stub remained), so "the stubs are gone" is literally true at the Gate-I freeze.

## [0.8.2] - 2026-06-10

Ships with dazzlecmd v0.8.32 -- the post-shim untyped-access review (the DWP the 0.8.0 quick-decision deserved). Additive; byte-identical.

### Fixed

- `to_manifest()` no longer strips `_vars` (or `_schema_version`) from the manifest projection. Pre-fix every `_`-prefixed key was dropped -- including `_vars` (user template variables, #41) -- so `mode.cache_manifest` silently lost a tool's template variables on mode switch. A `_MANIFEST_UNDERSCORE_KEYS` whitelist now separates `_`-prefixed MANIFEST data (preserved) from computed annotations (`_fqcn`, still stripped). This was a real data-loss bug.

### Changed

- `tools_dir` / `manifest` promoted to typed fields (kit-manifest schema keys for nested-aggregator child layout; the Stage-5 sweep had missed them). Absent values stay out of the `to_manifest` projection.
- `_override_tools_dir` / `_override_manifest` -> computed fields `override_tools_dir` / `override_manifest`; `loader` normalizes the registry's raw keys at the single pre-`build_entity` chokepoint.
- `extra_get` now documents its three-category contract (also in the README): (1) polymorphic blocks (`source`), (2) `_`-prefixed manifest data (`_vars` / `_schema_version`, a Pydantic field-naming constraint), (3) novel/unmodeled keys.

## [0.8.1] - 2026-06-10

Ships with dazzlecmd v0.8.31 -- Gate I. Additive (README + `__all__`).

### Added

- `entity.__all__` + `groupable.__all__` (`states` already had one) -- explicit, star-import-checkable public surfaces.
- A "Public API -- frozen until 1.0 (Gate I)" section in the README documenting the settled surface + the access model (typed attributes + `extra_get`/`extra_set`).

**Gate I:** with the dict shim gone (0.8.0), all five Groupable verbs live, and the state system in place, the DazzleEntity object model + the Groupable verb/state contracts are declared FROZEN until 1.0.

## [0.8.0] - 2026-06-10

Ships with dazzlecmd v0.8.30. **BREAKING** (pre-1.0 MINOR) -- the close of the DazzleEntity migration.

### Removed -- BREAKING

- The DazzleEntity dict shim: `__getitem__` / `__setitem__` / `get` / `__contains__` / `keys` / `values` / `items`, plus `_LEGACY_KEY_MAP` and the `_warn_on_shim` ratchet. Consumers that treated entities as dicts must migrate: `entity["x"]` -> `entity.x` (typed) or `entity.extra_get("x")` (untyped); `entity["x"] = v` -> `entity.x = v` or `entity.extra_set("x", v)`; `entity["_fqcn"]` -> `entity.fqcn`. (Known consumers reconciled to this break: amdead, wtf-windows.)

### Added

- `DazzleEntity.extra_get` / `extra_set` / `has_extra` -- the typed-entity accessor for the untyped remainder (the polymorphic `source` block, `_vars`, `_schema_version`, nested `manifest`).

### Changed

- ~293 call sites migrated from dict-access to attribute / `extra_get` across prod (loader / engine / default_meta_commands / registry / cli_helpers / setup_resolve) and tests; behavior preserved (dazzlecmd's CLI byte-identical). The break is for LIBRARY CONSUMERS using dict-access -- dazzlecmd itself is unaffected at the CLI.

## [0.7.24] - 2026-06-10

Ships with dazzlecmd v0.8.29 -- state system Step 5; all five Groupable verbs now live. Additive; byte-identical.

### Added

- `states.CompositeTransition` -- a multi-axis move as ordered composition of single-axis legs; composite-criticality is computed from leg INTERACTION (a leg's `creates` feeding a later leg's conserved invariant => generative), NOT the union of leg classes. Plus `TransitionRegistry.register_composite` / `composites` / `composite`.
- `build_default_registry`: the CONTAINMENT axis + reversible `group`/`ungroup` edges (conserved = `local_incorporability`) + the GENERATIVE graduation composite (creates `own_repo`/`remote_url`, loses `in_tree_coupling`, `fqcn_fate=reborn`).
- `groupable.ContainmentInvariant` / `ContainmentReceipt` / `ContainmentContext` (in-tree membership move; apply/undo; C3 refusal on ungrouping a constitutional item; graduation refused until #73).
- `Groupable.group(target, *, context)` / `ungroup(target=None, *, context)` live delegates.

## [0.7.23] - 2026-06-10

Ships with dazzlecmd v0.8.27 -- state system Step 4a, the hide/expose verbs. Additive; byte-identical.

### Added

- `groupable`: `VISIBILITY_CHANNELS` + `VISIBILITY_LADDER` (monotone presets: Visible -> Silenced -> Hidden -> Shadowed) + `level_for_channels`; `Frame` (consumer/projection context; reserved unwired `channel_overrides`); `VisibilityInvariant` (C2 = `canonical_dispatch`), `VisibilityReceipt`, `VisibilityContext` (global path; writes the existing per-channel config keys; undo; frame-relative writes refused until #79).
- `entity.Groupable.hide(to=, *, context)` / `expose(to=, *, context)` -- live ladder-walk delegates; first real C3 enforcement (shadowing a constitutional `always_active` item raises `CriticalityBoundaryError`). `visibility_in(frame=None, *, context=None)` real for the global path.
- The VISIBILITY hide/expose transitions in `build_default_registry` (REVERSIBLE, conserved = `canonical_dispatch`).

## [0.7.22] - 2026-06-10

Ships with dazzlecmd v0.8.26 -- state system Step 3, the Hidden visibility level. Render-only; no-op when `hidden_tools` is empty (byte-identical).

### Added

- `engine.AggregatorEngine.filter_hidden(projects, *, reveal=False)` -- the render-only chokepoint shared by list/tree/epilog. A hidden tool is omitted from display but stays fully dispatchable (short name still claimed, FQCN still resolves); discovery, the FQCN index, dispatch, and collision/precedence never consult `hidden_tools`.
- `hidden_tools` config key (documented alongside `silenced_hints` / `shadowed_tools`).

## [0.7.21] - 2026-06-10

Ships with dazzlecmd v0.8.25 -- state system Step 2, context-level undo. Additive (undo is on no dispatch path); byte-identical.

### Added

- `groupable.RebindContext.undo(receipt)` (protocol) + impls: `AliasRebindContext.undo` (entity-free; the context looks up the current owner and repoints back to `receipt.previous_state`; always reversible) and `mode.ModeRebindContext.undo` (re-drives the inverse switch iff `receipt.reversible`; a one-way orbit entry refuses with `CriticalityBoundaryError`). The `assert_round_trip` harness's `invert` is now just `ctx.undo`.

## [0.7.20] - 2026-06-09

Ships with dazzlecmd v0.8.24 -- state system slice 0, the foundation the Groupable verbs build on. Additive (`states` is imported nowhere on the dispatch hot path); byte-identical.

### Added

- `dazzlecmd_lib.states` (NEW, generic -- imports nothing from engine/mode/groupable): `StateAxis` / `EntityState` (frozen, OBSERVED not stored) / `Transition` / `TransitionRegistry`; the `Reversibility` taxonomy (REVERSIBLE / ONE_WAY / REFUSED_AT_BOUNDARY / GENERATIVE) with contract enforcement; `assert_round_trip(read, apply, invert)` (substrate-agnostic L2-semantic identity harness); `observe(...)` (the platform->model bridge -- an unmodelable real reading raises rather than being stored); `build_default_registry()` (KIND/MODE/VISIBILITY/ACTIVATION + ROUTING axes; retro-declares the live rebind transitions; reserves `CompositeTransition`).

## [0.7.19] - 2026-06-09

Ships with dazzlecmd v0.8.23.

### Changed

- `requires-python` raised to `>=3.9`. The DazzleEntity model imports `typing.Annotated` (a 3.9+ runtime feature for the discriminated union), so the lib has effectively required 3.9+ since the 0.8.x rearchitecture; Python 3.8 is EOL and was dropped rather than shimmed.

## [0.7.18] - 2026-06-09

Ships with dazzlecmd v0.8.22 -- CI hotfix.

### Fixed

- Declare `pydantic>=2.0` as a runtime dependency. The DazzleEntity model imports Pydantic v2 unconditionally (a hard runtime dep since the 0.8.x rearchitecture), but the lib declared no core dependencies -- so a clean `pip install` (CI) died with `ModuleNotFoundError: No module named 'pydantic'` on `dz --version`. (`colorama` / `distro` stay optional -- both imported best-effort.)

## [0.7.17] - 2026-06-09

Ships with dazzlecmd v0.8.21 -- behavioral phase (#84) `rebind` Phase 2 (mode-switch) + a latent-bug fix it surfaced.

### Added

- `mode.ModeRebindContext` -- the dev↔publish `RebindContext`. Invariant = the remote URL; reverses within the `SUBMODULE↔SYMLINK` orbit; criticality = invariant-derivability (no remote URL → `CriticalityBoundaryError`); entering the orbit is one-way (`reversible=False`). Delegates to `_switch_to_dev`/`_switch_to_publish`; non-zero exit → `groupable.RebindError` (new).

### Fixed

- `mode._resolve_remote_url` couldn't read `source.url` / `lifecycle.graduated_to` from a `DazzleEntity` (`_dotted_lookup`'s `isinstance(dict)` guard returned `None`) -- a latent Phase-1 migration regression that broke `dz mode switch --publish` without `--url`. Now resolves against `to_manifest()`. Works for entity and dict callers.

### Refs

Ships with dazzlecmd v0.8.21. Refs dazzlecmd #84, #77, #73, #37.

## [0.7.16] - 2026-06-09

Ships with dazzlecmd v0.8.20 -- behavioral phase (#84) `rebind` PoC Phase 1 (alias). Additive; no breaking change.

### Added

- `groupable` (NEW module): `RebindReceipt`, `RebindInvariant` (C2 descriptor), `CriticalityBoundaryError`, `RebindContext` protocol, `AliasRebindContext`.
- `engine.FQCNIndex.repoint_alias(alias_fqcn, new_canonical_fqcn)` -- the alias-rebind primitive (single-hop/existence guards + `short_index` re-bookkeeping; `insert_alias` refuses different-target remaps by design).

### Changed

- `entity.Groupable.rebind` implemented (was `NotImplementedError`): `rebind(target, *, context)` delegates to a `RebindContext`, preserving C1. Other four verbs remain deferred; `Frame` reserved.

### Refs

Ships with dazzlecmd v0.8.20. Refs dazzlecmd #84, #77, #73.

## [0.7.15] - 2026-06-08

Ships with dazzlecmd v0.8.18 -- Phase 1 Stage 3 (ratchet enforcement). Byte-identical.

### Changed

- `registry.RunnerRegistry.resolve` -- `project.get("runtime", {})` -> `project.runtime` (the last typed-field shim straggler on the dispatch path). With this, no in-scope production code reaches an entity's typed fields via the dict shim; a test-time ratchet gate (`tests/test_ratchet_enforcement.py` in the dazzlecmd repo) enforces it going forward.

### Refs

Ships with dazzlecmd v0.8.18. Refs dazzlecmd #37, #73, #77.

## [0.7.14] - 2026-06-07

Ships with dazzlecmd v0.8.17 -- fixes two pre-existing bugs.

### Fixed

- `default_meta_commands.render_kit_status` filtered by the manifest `always_active` flag only, so it ignored `active_kits` / `disabled_kits`. `kit_status_handler` now passes `engine.active_kits` (the config-resolved active set) and `render_kit_status` is a pure renderer of the set it's given — matching `kit list`.
- `mode.cmd_switch` matched `p.name == tool_name` only, so a fully-qualified name (e.g. `core:find`) wasn't accepted. It now also matches an exact `p.fqcn` (exact match only — never the fuzzy resolver, since `mode switch` rewrites a submodule) and normalizes the argument to the resolved short name. Also fixes a leftover `p["name"]` dict-shim access.

### Refs

Ships with dazzlecmd v0.8.17. Refs dazzlecmd #37.

## [0.7.13] - 2026-06-07

Ships with dazzlecmd v0.8.16 -- Phase 1 Stage 2 cleanups. Byte-identical; no API change beyond a tightened internal contract (the functions below now require DazzleEntity inputs, which all loader/engine-produced values already are).

### Changed

- `engine._rewrite_virtual_kit` + `registry.resolve_runtime` — dropped the dead `else dict(...)` clone-guard branches; clone+write is now `x.model_copy()` + attribute writes (`.name`/`.tools`/`.name_rewrite`/`.runtime`/...).
- `mode.cache_manifest` — dropped the dict fallback; `clean = manifest.to_manifest()` (entity-only).
- `mode.cmd_status` — undiscovered-tool entries are built as `Tool` entities via `build_entity`; status reads use attribute access.

### Refs

Ships with dazzlecmd v0.8.16. Refs dazzlecmd #37, #73, #77.

## [0.7.12] - 2026-06-07

Ships with dazzlecmd v0.8.15 -- completes the `engine.py` sweep (the FQCN-index core). Byte-identical; no API change. All six production files are now entity-native.

### Changed

- `FQCNIndex.insert_canonical` + `_build_fqcn_index` migrated to attribute access (set-once `project.fqcn`, `(p.fqcn or "")` realpath-dedup reads, `project.fqcn is None` first-pass check, `alias_project.auto_realpath_alias`/`.canonical_fqcn` writes). Their direct-call test fixtures moved to `dazzlecmd_lib.testing.make_tool` entities first (fixtures-first).

### Refs

Ships with dazzlecmd v0.8.15. Refs dazzlecmd #37, #73, #77.

## [0.7.11] - 2026-06-07

Ships with dazzlecmd v0.8.14 -- `engine.py` attribute sweep (the last production file). Byte-identical; no API change.

### Changed

- `engine` -- discovery-pipeline entity reads/writes migrated to attribute access across `discover()`, `_discover_aggregator`, `_recurse_into_nested`, `_rewrite_virtual_kit`, `_apply_virtual_kits`, `_annotate_project_fqcn`, the reroot-hint scan, and dispatch. `project.fqcn = ...` goes through the set-once C1 property. Clone-guard `rewritten[...]` writes and extra keys (`tools_dir`/`manifest`/`_override_*`) stay dict access.
- `FQCNIndex.insert_canonical` + `_build_fqcn_index` deferred to the next commit (their direct-call tests use raw dict fixtures; fixtures-first).

### Refs

Ships with dazzlecmd v0.8.14. Refs dazzlecmd #37, #73, #77.

## [0.7.10] - 2026-06-07

Ships with dazzlecmd v0.8.13 -- `mode.py` attribute sweep + the `_find_undiscovered_tool` dict-or-entity unification. Byte-identical; no API change.

### Changed

- `mode._find_undiscovered_tool` returns a real `Tool` entity (via `build_entity`) from all paths, so `cmd_switch`'s project is always an entity.
- `mode` -- entity reads in the switch paths migrated to attribute access. `cache_manifest` guard kept; config/gitmodules dicts stay dict access.

### Refs

Ships with dazzlecmd v0.8.13. Refs dazzlecmd #37, #73, #77.

## [0.7.9] - 2026-06-07

Ships with dazzlecmd v0.8.11 -- `registry` attribute sweep (runtime resolution + runner factories). Byte-identical; dispatch verified; no API change.

### Changed

- `registry` -- entity field reads in `resolve_runtime` + runner factories migrated to attribute access. Nested-block manipulation, clone-site guards, the post-clone `["runtime"]=` write (entity-or-dict duality), and `_vars` (.get) stay as-is.

### Refs

Ships with dazzlecmd v0.8.11. Refs dazzlecmd #37, #73, #77.

## [0.7.8] - 2026-06-07

Ships with dazzlecmd v0.8.10 -- `loader` attribute sweep. Byte-identical; no API change.

### Changed

- `loader` -- entity-read sites (`get_active_kits`, `discover_projects`, `_scan_tool_dirs`) migrated to attribute access. Raw-construction dict access (pre-`build_entity`) stays dict access; extra keys stay `.get()`.

### Refs

Ships with dazzlecmd v0.8.10. Refs dazzlecmd #37, #73, #77.

## [0.7.7] - 2026-06-07

Ships with dazzlecmd v0.8.9 -- completes the `default_meta_commands` attribute sweep (`render_tree` + virtual-kit paths, deferred in 0.7.6). Byte-identical; no API change.

### Changed

- `default_meta_commands` -- `render_tree` (ASCII + JSON), the `build_list_entries` virtual-kit iteration, and the `render_list` empty-virtual-kit injection migrated to attribute access. `default_meta_commands.py` is now fully migrated off the dict shim for entity access.

### Refs

Ships with dazzlecmd v0.8.9. Refs dazzlecmd #37, #73, #77.

## [0.7.6] - 2026-06-07

Ships with dazzlecmd v0.8.8 -- Phase 1 Stage 6b (first prod file): the `default_meta_commands` attribute sweep. Byte-identical; no API change.

### Changed

- `default_meta_commands` -- dict-style entity access migrated to typed attribute access across the list/info/kit/setup render paths (~50 sites). Nested-block values + extra keys stay dict access; `.get(key, default)` on Optional fields became `entity.field or default`. `render_tree` deferred until its dict-fixture tests migrate.

### Refs

Ships with dazzlecmd v0.8.8. Refs dazzlecmd #37, #73, #77.

## [0.7.5] - 2026-06-07

Ships with dazzlecmd v0.8.7 -- Phase 1 Stage 6a: the entity test factory. Test-support addition; no runtime API change.

### Added

- `dazzlecmd_lib.testing` -- public test factory (`make_tool` / `make_kit` / `make_aggregator`) wrapping `build_entity` for concise typed-entity construction in tests. Normalizes legacy `_`-prefixed keys and applies the set-once `fqcn`. Permanent (not a transitional shim); usable by any consumer's test suite.

### Refs

Ships with dazzlecmd v0.8.7. Refs dazzlecmd #37, #73, #77.

## [0.7.4] - 2026-06-07

Ships with dazzlecmd v0.8.6 -- Phase 1 Stage 5: type the full manifest schema. Additive + byte-identical; the shim still works, attribute access now also works for every modeled field.

### Changed

- `DazzleEntity` now declares the known manifest fields as typed fields (`language`, `platform`, `runtime`, `pass_through`, `taxonomy`, `lifecycle`, `platforms` [list], `dependencies`, `setup`, `long_description`, `always_active`, `virtual`, `tools`, `name_rewrite`) with defaults matching their dominant `.get(key, default)` call sites. `extra="allow"` retained for novel keys (read via `model_extra`); `source` left in extra (polymorphic str-vs-dict across kit/tool); `_`-prefixed manifest keys stay in extra.

### Refs

Ships with dazzlecmd v0.8.6. Refs dazzlecmd #37, #73, #77.

## [0.7.3] - 2026-06-07

Ships with dazzlecmd v0.8.5 -- Phase 1 Stage 4: the test-time migration ratchet foundation. No production behavior change (ratchet off by default).

### Changed

- The shim deprecation ratchet (`_warn_on_shim`) now warns **only for typed-field/property access**, not for extra/nested-block dict access (which has no safe attribute form). `get()` no longer double-warns (routes through `_raw_get`). Ratchet stays off by default, so consumers and production are unaffected.

### Refs

Ships with dazzlecmd v0.8.5. Refs dazzlecmd #37, #73, #77.

## [0.7.2] - 2026-06-07

Ships with dazzlecmd v0.8.4 -- Phase 1 Stage 3: promote computed runtime values to typed fields. Public API unchanged; the migration is internal and a legacy-key alias map keeps dict access working, so consumers (dazzlecmd, amdead, wtf-windows) need no change.

### Changed

- `DazzleEntity` — 11 computed runtime values promoted from `_`-prefixed extra keys to typed fields: `short_name`, `kit_import_name`, `directory`, `manifest_path`, `cached`, `kit_source`, `kit_name`, `kit_active`, `auto_realpath_alias`, `canonical_fqcn`, `original_name`. `fqcn` stays a set-once property. `_LEGACY_KEY_MAP` routes legacy `["_dir"]`/`["_fqcn"]` access (read + write) to the promoted field/property; `_COMPUTED_FIELDS` drives `to_manifest()` stripping so computed values never serialize as manifest data.
- `loader` — writes promoted field names into the manifest dict before `build_entity` so validation populates the fields.
- `mode.cache_manifest` — uses `to_manifest()` for entities so computed fields aren't cached.

### Notes

- Internal behavior change: `"<promoted_key>" in entity` is now always true (the field exists) — check the value, not membership. `_fqcn` stays a property, so its membership semantics are unchanged.

### Refs

Ships with dazzlecmd v0.8.4. Refs dazzlecmd #37, #73, #77.

## [0.7.1] - 2026-06-07

Ships with dazzlecmd v0.8.2 -- Phase 1 Stage 1. The `DazzleEntity` backward-compat shim becomes a faithful read-Mapping.

### Fixed

- A `DazzleEntity` passed where a dict was expected no longer crashes on `.items()` / `.keys()` / `.values()`. The shim previously implemented only `__getitem__` / `__setitem__` / `get` / `__contains__`; code iterating an entity as a mapping (e.g. a downstream `cache_manifest`-style `{k: v for k, v in manifest.items()}`) raised `AttributeError`.

### Added

- `DazzleEntity.keys()` / `values()` / `items()` — a faithful read-Mapping view (declared fields + extra, including computed `_`-prefixed keys, consistent with `__contains__`). Each routes through the deprecation ratchet (`_warn_on_shim`). A no-warn `_raw_get` backs them so they warn once per call. `__iter__` / `__len__` are intentionally NOT overridden, preserving pydantic's `dict(model)` contract.

### Refs

Ships with dazzlecmd v0.8.2. Refs dazzlecmd #37, #73, #77 (the DazzleEntity Phase 1 migration arc).

## [0.7.0] - 2026-06-07

Ships with dazzlecmd v0.8.1 -- the DazzleEntity foundational redesign. The library gains a typed object model; the aggregator-facing public API is unchanged (the migration is internal, and a backward-compat shim keeps existing dict access working), so consumers (dazzlecmd, amdead, wtf-windows) need no code change to adopt 0.7.0.

### Added

- `dazzlecmd_lib.entity` -- the object model. `Groupable` (the universal grouping/ungrouping capability mixin: 5 verbs + the C1/C2/C3 canonical-identity contract); `DazzleEntity(Groupable, BaseModel)` (base for on-tree co-level occupants; `extra="allow"` + a backward-compat dict shim, set-once canonical FQCN, `to_manifest`); the `Tool`/`Kit`/`Aggregator` discriminated union (open for future `Property`/`Environment`) with `detect_type` / `build_entity` and `AmbiguousEntityTypeError`.
- `dazzlecmd_lib.core` -- the constitutional namespace, with `core.links` as its first inhabitant: the four public link primitives (`is_linked_project`, `get_link_target`, `create_link`, `remove_link`) relocated verbatim from `paths`. `paths` re-exports them with import identity preserved, so existing `from dazzlecmd_lib.paths import is_linked_project` keeps working.
- `AggregatorConfig.presentation` -- reserved `Optional[dict]` slot for future per-aggregator presentation / projection config. Parsed + validated-as-object when present; not yet consumed.

### Changed

- `aggregator_config` -- `AggregatorConfig` / `AggregatorSchema` / `AggregatorDiscovery` converted from frozen dataclasses to frozen Pydantic models. Field names, defaults, validation, and error messages unchanged; `config.schema.*` / `config.discovery.*` access is identical.
- `loader` -- `discover_kits` / `_load_manifest` / `_load_cached_manifest` construct typed `DazzleEntity` instances (via `build_entity`) instead of bare dicts. The loader is the sole entity author (one canonical instance per canonical FQCN).
- `engine` -- `FQCNIndex` carries entities; `_annotate_project_fqcn` calls `reserve_field_axis(...)`, the single point that rejects `.` in name / namespace segments, reserving `.` for the future field-access axis. Entity-clone sites use `model_copy()` instead of `dict()`.

### Refs

Ships with dazzlecmd v0.8.1. Refs dazzlecmd #37, #73, #77 (the co-level / DazzleEntity design arc).

## [0.6.15] - 2026-06-07

Ships with dazzlecmd v0.7.54. Cosmetic Windows-codepage fix; no API change.

### Changed

- `mode._print_no_toggle()` -- replaced a Unicode em dash with `--` in the embedded-tool "no mode toggle" stderr message (codepage safety on Windows cmd / PowerShell).

### Refs

Ships with dazzlecmd v0.7.54. Refs dazzlecmd #37.

## [0.6.14] - 2026-05-26

Ships with dazzlecmd v0.7.52. Removes the cwd-first footgun from `find_aggregator_root()` that let an entry point impersonate a sibling aggregator based on the invocation directory.

### Changed

- `find_aggregator_root(start_path=None)` no longer falls back to the library's own `__file__` when cwd misses. v0.6.13's two-stage default (cwd, then lib `__file__`) caused two bugs: (1) cwd-first made `dz` load a sibling aggregator's `aggregator.json` when run from inside its tree; (2) the lib-`__file__` fallback made every aggregator that called this bare resolve to dazzlecmd (the library is co-located with dazzlecmd in dev mode). Now `start_path=None` walks `os.getcwd()` only -- a deliberate "find from here" for tests/ad-hoc. **Production entry points must pass an explicit anchor** (their package's `__file__` directory); the docstring documents this contract and the impersonation hazard of calling it bare.

### Refs

Ships with dazzlecmd v0.7.52. Refs dazzlecmd #37 (Phase 3.5 EPIC). Fixes the impersonation regression surfaced by the wtf-windows T1-M2 migration.

## [0.6.13] - 2026-05-24

Ships with dazzlecmd v0.7.51 (Phase 3.5 T1-M1 + issue #74). Two additive helpers + two engine.py injection blocks. Together they form the runtime+static duo that makes downstream aggregator adoption a "write `aggregator.json` + 5-line main()" exercise instead of a "fork dazzlecmd's main() and edit kwargs" exercise.

### Added

- `find_aggregator_root(start_path=None, max_depth=12)` -- walks up looking for `aggregator.json`. The canonical project-root discovery helper for any dazzlecmd-lib-based aggregator. Two-stage fallback when `start_path` is None: first `os.getcwd()`, then `os.path.dirname(__file__)` of this module itself (covers the dev-mode case where the lib lives co-located with the project tree and the user invokes the CLI from outside that tree).
- `DZ_APP_NAME` and `DZ_COMMAND` env-var injection in `engine.AggregatorEngine._run_tool()` and `_run_escape_hatch()`. Reflects engine identity (not per-invocation context); always injected before tool dispatch; restored to prior values in `finally`. Subprocess tool scripts read these to render branding strings without each aggregator hand-rolling its own `AGGREGATOR_APP_NAME` bridge.

### Changed

- `engine.AggregatorEngine._run_tool()` and `_run_escape_hatch()` -- the `env_backup` dict now accumulates branding vars (always set) plus FQCN vars (context-gated). The restore block in `finally:` is no longer gated on `context is not None` since the dict is the source of truth and may have branding entries even without a context.

### Refs

Ships with dazzlecmd v0.7.51. Refs dazzlecmd #37 (Phase 3.5 EPIC). Closes dazzlecmd #74 (env-var injection for child-process branding).

## [0.6.12] - 2026-05-19

Ships with dazzlecmd v0.7.50 (Phase 3.5 Tier 1 commit 3 -- T1-E safety primitive). Adds a dirty-tree refuse-or-force gate at the destructive `shutil.rmtree(tool_dir)` call sites in `mode.py`, closing the CRITICAL hazard flagged by the senior-engineer audit of v0.7.48. The gate refuses by default; callers opt into the destructive behavior via the new `force` keyword parameter on `cmd_switch`.

### Added

- `_check_dirty_tree(tool_dir)` -- returns `git status --porcelain` output for `tool_dir` if it is its own git worktree root, else empty string. The worktree-root check (via `git rev-parse --show-toplevel` + realpath comparison) prevents the function from reporting an ancestor repo's dirty state when `tool_dir` happens to live inside one (e.g., a tool path under `$HOME` would otherwise pick up `~/.git`'s state).
- `_print_dirty_refusal(tool_name, tool_dir, dirty_output, command)` -- prints the standard refusal message. Truncates the displayed dirty list at 10 lines and substitutes the aggregator's `command` into the recovery hint.

### Changed

- `cmd_switch(tool_name, projects, project_root, dev_path=None, force_mode=None, dry_run=False, url=None, *, tools_dir, command, schema=None)` -> `cmd_switch(..., url=None, force=False, *, tools_dir, command, schema=None)`. New positional-with-default `force` parameter. Default value `False` preserves the safe behavior (refuse destructive switch on dirty tree); callers opt into the destructive behavior explicitly.
- `_switch_to_dev(project, project_root, gitmodules, explicit_path, dry_run, *, tools_dir, command)` -> `_switch_to_dev(..., dry_run, force, *, tools_dir, command)`. New required positional `force` parameter; gates the `shutil.rmtree(tool_dir)` call site.
- `_switch_to_publish(project, project_root, gitmodules, dry_run, url=None, *, tools_dir, command, schema=None)` -> `_switch_to_publish(..., dry_run, force, url=None, *, tools_dir, command, schema=None)`. New required positional `force` parameter; gates the `shutil.rmtree(tool_dir)` call site.

### Refs

Ships with dazzlecmd v0.7.50. Refs dazzlecmd #37 (Phase 3.5 EPIC).

## [0.6.11] - 2026-05-19

Ships with dazzlecmd v0.7.49 (Phase 3.5 Tier 1 commit 2.5). Senior-engineer audit cleanup of v0.6.10's parameterization. Two surgical fixes inside `mode.py`: thread `tools_dir` through `_print_no_toggle` so the STATE_LOCAL_ONLY hint substitutes the aggregator's tool-root directory name instead of printing a literal placeholder; restore `_resolve_remote_url`'s default probe order to match the v0.7.47 verbatim baseline byte-for-byte (drop the unintentional `lifecycle.remote` probe drift).

### Changed

- `_print_no_toggle(tool_name, state, *, command)` -> `_print_no_toggle(tool_name, state, *, command, tools_dir)`. Required `tools_dir` keyword-only parameter. The STATE_LOCAL_ONLY error hint substitutes `tools_dir` into the suggested `git submodule add` command line (was a literal `<tools-dir>` placeholder). The single in-library call site in `cmd_switch` already had `tools_dir` in scope.
- `_resolve_remote_url(project, explicit_url=None, *, schema=None)` default probe list. When `schema=None`, the function now probes only `("source.url",)` followed by the always-tried `lifecycle.graduated_to` fallback -- matches the v0.7.47 baseline. The previous `("source.url", "lifecycle.remote")` default added an undocumented probe of a new key that didn't exist in the baseline; aggregators that legitimately want a custom probe order should declare it in their `AggregatorSchema.remote_url_paths`.

### Tests

`tests/test_mode_parameterization.py::test_fallback_chain` updated to assert the schema-supplied path list ordering rather than the now-removed default `lifecycle.remote` probe. 1203 passed, 14 skipped (was 1204 in v0.6.10; -1 deleted shim test in the dazzlecmd test suite).

### Refs

Ships with dazzlecmd v0.7.49. Refs dazzlecmd #37 (Phase 3.5 EPIC).

## [0.6.10] - 2026-05-18

Ships with dazzlecmd v0.7.48 (Phase 3.5 Tier 1 commit 2). Parameterizes the verbatim-moved `mode` module so every function takes the aggregator's `tools_dir` / `command` / manifest `schema` as required keyword-only parameters instead of baking dazzlecmd-specific values into the implementation. Resolves the senior-engineer audit's BLOCKERs F2/F3/F4/F5/F7/F8 + F1 (the latter via the `add_from_local` import-side fix in dazzlecmd's importer.py). 25 new tests in `tests/test_mode_parameterization.py` prove the library works for any tools_dir layout (parametric over `projects/`, `tools/`, and `src/tools/`) and any manifest schema.

### Changed

- `parse_gitmodules(project_root)` -> `parse_gitmodules(project_root, *, tools_dir)`. The hardcoded `"projects/"` prefix check becomes `tools_dir.rstrip("/") + "/"`; the 3-part path assumption becomes a 2-part check on the suffix after the prefix.
- `_tool_dir_to_submodule_path(tool_dir)` -> `_tool_dir_to_submodule_path(tool_dir, project_root, *, tools_dir)`. The substring search for `"projects/"` becomes `os.path.relpath(tool_dir, project_root)` followed by a prefix check on `tools_dir`. Prevents the F8 regression where a parent path containing `"projects"` (e.g., `C:\code\my-projects\dz`) would substring-match incorrectly.
- `detect_tool_state(tool_dir, gitmodules)` -> `detect_tool_state(tool_dir, gitmodules, project_root, *, tools_dir)`. Threads project_root + tools_dir to `_tool_dir_to_submodule_path`.
- `resolve_dev_path(qualified_name, project_root, explicit_path=None)` -> `resolve_dev_path(qualified_name, project_root, explicit_path=None, *, tools_dir)`.
- `cmd_status(projects, project_root, tool_filter=None, kit_filter=None)` -> `cmd_status(projects, project_root, tool_filter=None, kit_filter=None, *, tools_dir, command)`. The undiscovered-tool scan uses `os.path.join(project_root, tools_dir)` instead of the hardcoded `"projects"`; user-facing error strings substitute `command` instead of hardcoded `"dz"`.
- `cmd_switch(tool_name, projects, project_root, ...)` -> `cmd_switch(tool_name, projects, project_root, ..., *, tools_dir, command, schema=None)`. Threads tools_dir + command + schema to `_find_undiscovered_tool`, `parse_gitmodules`, `detect_tool_state`, `_print_no_toggle`, `_switch_to_dev`, `_switch_to_publish`.
- `_find_undiscovered_tool(tool_name, project_root)` -> `_find_undiscovered_tool(tool_name, project_root, *, tools_dir)`.
- `_print_no_toggle(tool_name, state)` -> `_print_no_toggle(tool_name, state, *, command)`. Substitutes the aggregator's CLI name into the "register a submodule first" hint.
- `_switch_to_dev(project, project_root, gitmodules, explicit_path, dry_run)` -> `_switch_to_dev(project, project_root, gitmodules, explicit_path, dry_run, *, tools_dir, command)`.
- `_switch_to_publish(project, project_root, gitmodules, dry_run, url=None)` -> `_switch_to_publish(project, project_root, gitmodules, dry_run, url=None, *, tools_dir, command, schema=None)`. Default-submodule-path construction uses `tools_dir` instead of hardcoded `"projects"`.
- `_resolve_remote_url(project, explicit_url=None)` -> `_resolve_remote_url(project, explicit_url=None, *, schema=None)`. The new `schema` parameter is an `AggregatorSchema` (or dict-like) with ordered `remote_url_paths`; the function probes each path in order via dotted-key lookup. When `schema=None`, defaults to `("source.url", "lifecycle.remote")` matching dazzlecmd's historical behavior. `lifecycle.graduated_to` is always tried as a final fallback because it represents tool-graduation semantics, not aggregator-specific manifest layout.

### Added

- `_dotted_lookup(obj, dotted_path)` -- internal helper for walking dotted paths into a nested dict (e.g., `"source.url"`). Returns the value or `None`. Used by `_resolve_remote_url` to implement schema-driven remote URL resolution.

### Refs

Ships with dazzlecmd v0.7.48. Refs dazzlecmd #37 (Phase 3.5 EPIC).

## [0.6.9] - 2026-05-18

Ships with dazzlecmd v0.7.47 (Phase 3.5 Tier 1 commit 1 of N). Aggregator-decoupling scaffolding: `aggregator.json` declarative configuration, the `reserved` module (namespace contract + user-vs-dev meta-command sets), `AggregatorEngine.from_project()` canonical constructor, and a verbatim-moved `dazzlecmd_lib.mode` module that any aggregator can consume. Link helpers (`create_link`/`remove_link`) join `is_linked_project` and `get_link_target` in `dazzlecmd_lib.paths`. Parameterization of the moved mode code for BLOCKERs F1-F8 lands in v0.6.10 (Tier 1 commit 2); the verbatim move and the parameterization are separate passes per the X-28 copy-don't-rewrite discipline.

### Added

- `aggregator_config` module -- declarative aggregator schema. `AggregatorConfig` dataclass (frozen) + nested `AggregatorSchema` / `AggregatorDiscovery` blocks + `load_aggregator_config(project_root)` + `AggregatorConfigError`. 11 top-level fields cover identity (name, command, description), layout (tools_dir, kits_dir, manifest_name), command policy (enabled_meta_commands, extra_reserved_commands), manifest schema decoupling, and discovery patterns. `${tools_dir}` interpolation in `discovery.tool_patterns` lets pattern values stay declarative without duplicating the literal directory name. Required at every aggregator project root for `AggregatorEngine.from_project()`.
- `reserved` module -- the namespace contract. `DEFAULT_RESERVED_COMMANDS` (9 names) is the cross-aggregator name-block list; `DEFAULT_META_COMMANDS_USER` (6 names) is the minimal user-facing registration set; `DEFAULT_META_COMMANDS_DEV_EXTRAS` (add/mode/new) is the opt-in dev-mode addition. The distinction between reserved (blocked from tool naming) and registered (exposed as CLI subcommand) is documented in the module docstring -- reserving a name does not register it.
- `AggregatorEngine.from_project(project_root, **overrides)` classmethod -- canonical engine constructor reading `aggregator.json`. Maps schema fields onto `__init__` kwargs. Caller-supplied `overrides` win (intended for tests + ad-hoc construction).
- `mode` module -- verbatim copy of dazzlecmd's `src/dazzlecmd/mode.py` (730 LOC) with the single import line swapped from `dazzlecmd.importer` to `dazzlecmd_lib.paths`. No behavior changes in this commit; Tier 1 commit 2 parameterizes the hardcoded `"projects/"` / `"dz"` / `.dazzlecmd.json`-schema usages to support wtf-windows / amdead / future aggregators.
- `paths` link helpers -- `create_link()` (tries symlink first, falls back to junction on Windows), `_create_link_windows()`, `_create_link_unix()`, `remove_link()`. Moved verbatim from `dazzlecmd.importer` so library code can create/remove links without depending on the dazzlecmd package layout.

### Refs

- Ships with dazzlecmd v0.7.47. Refs dazzlecmd #37 (Phase 3.5 EPIC).

## [0.6.8] - 2026-05-17

Ships with dazzlecmd v0.7.46 (Tier 2C -- setup API formalization). Four additions to the library's setup/runtime/platform surface: `setup.script` as a file-pointer alternative to inline `setup.command`; `runtime.venv` shorthand that synthesizes a python interpreter from a venv directory + platform conventions; a new `SetupRequiredError` exception type that translates missing-interpreter dispatch failures into actionable `dz setup <fqcn>` hints; and a new `PlatformInfo.id_like` field that exposes the Linux ID_LIKE chain so tool setup scripts can write distro-family decisions without enumeration. Bundled templates updated so newly-scaffolded tools ship with working setup blocks out of the box, the Python `--full` overlay adds an installer-detection setup script with `--dry-run` support, and the library's first real-world consumer (`dz find`'s `dz_setup.py`) demonstrates the full API on every supported platform.

### Added

- `platform_detect.PlatformInfo.id_like` -- new tuple field exposing the Linux `/etc/os-release` `ID_LIKE` chain (e.g. `("ubuntu", "debian")` for Ubuntu, `("centos", "rhel", "fedora")` for CentOS Stream). Always includes the subtype itself first so `"debian" in pi.id_like` works whether the host IS debian or just debian-derived (Ubuntu/Mint/Kali/Pop/Raspbian/etc.). Empty tuple on non-Linux or when `ID_LIKE` isn't declared. Detection via the optional `distro` package (uses `distro.like()`) OR the stdlib `/etc/os-release` parser fallback.
- `setup_resolve.InvalidSetupBlockError` -- raised when a setup block declares both `command` and `script` at the same level (top-level or within a single platform branch). XOR validation runs both at the top of the resolved block and for each per-platform branch after normalization.
- `setup_resolve.SETUP_SCRIPT_INTERPRETERS` -- public dict mapping `.py` / `.sh` / `.cmd` / `.bat` / `.ps1` extensions to their argv prefixes (e.g. `[".ps1"] = ["powershell", "-File"]`). Engines that consume `setup.script` use this for dispatch.
- `setup_resolve.infer_setup_script_interpreter(path)` -- helper that returns the argv prefix list for a given script path (case-insensitive on the extension) or `None` for unrecognized extensions.
- `registry.SetupRequiredError` -- raised by `_make_python_interpreter_runner` when the resolved interpreter is a separator-bearing path that doesn't exist, or when `subprocess.run` raises `FileNotFoundError` on a bare-name interpreter. Carries the tool's `fqcn` and a `has_setup` flag so consumers can pick between "Run: dz setup <fqcn>" and "Ask the tool's creator" hints.
- `registry._setup_required_message(project, missing_what)` -- shared message builder used by both pre-flight existence checks and post-subprocess `FileNotFoundError` catches.
- `runtime.venv` shorthand in `make_python_runner`. When `runtime.venv` is declared and `runtime.interpreter` is not, the runner synthesizes the interpreter as `<venv>/Scripts/python.exe` on Windows or `<venv>/bin/python` on POSIX. Explicit `runtime.interpreter` wins on collision. Path-resolution shorthand only -- the runner does not create the venv.
- Setup blocks in bundled `templates/rust/`, `templates/node/`, `templates/c_cpp/`, and `templates/docker/` `.dazzlecmd.json.tmpl` (`cargo build`, `npm install`, `make`, `docker build -t {name}:latest .`).
- Bundled `templates/python/__full__/.dazzlecmd.json.tmpl` (override of base manifest using `runtime.venv` + `setup.script`), `templates/python/__full__/dz_setup.py.tmpl` (installer-detection script targeting uv, poetry, pdm, pipenv, conda, pip+pyproject, pip+requirements, or empty-venv fallback; now ships with a `--dry-run` flag per the v0.7.46 convention), and `templates/python/__full__/requirements.txt.tmpl` (starter).

### Changed

- `platform_detect._detect_linux_subtype` -- now returns a 4-tuple `(subtype, version, id_like, raw)` instead of a 3-tuple to expose ID_LIKE parsing. Internal helper; external consumers should use `get_platform_info()`.
- `setup_resolve.resolve_setup_block` -- XOR validation now runs both at the top-level block and (post-normalization) inside each per-platform branch. The docstring documents `setup.script` as a sibling of `setup.command` and explains the file-pointer dispatch model.
- `registry._make_python_interpreter_runner` -- adds pre-flight existence check for separator-bearing interpreter paths (skipped for env-var-prefixed paths like `%USERPROFILE%\...` because the shell expands them at dispatch). `FileNotFoundError` from subprocess in both module-mode and script-mode paths is now translated to `SetupRequiredError`.
- `templates/rust/.dazzlecmd.json.tmpl` and `templates/c_cpp/.dazzlecmd.json.tmpl` -- migrated from `runtime.binary_path` (which the binary runner never consumed) to `runtime.script_path` (the canonical field) plus a `runtime.dev_command` (`cargo run --` / `make run`) for the "binary not built yet" case. The old `build_hint` advisory text was removed; the same information now lives in `setup.note`.

### Refs

- Ships with dazzlecmd v0.7.46. Refs dazzlecmd #33, #35.

## [0.6.7] - 2026-05-16

Ships with dazzlecmd v0.7.45. Adds three more language templates to the bundled scaffolding set: `bash` (POSIX shell scripts), `cmd` (Windows batch files), and `binary` (pre-built executable registration). Pure template addition; no library API change. The seven-language set bundled in v0.6.6 (python, rust, node, powershell, c_cpp, docker, generic) is now ten.

### Added

- `templates/bash/.dazzlecmd.json.tmpl` + `templates/bash/{name}.sh.tmpl` -- bash scaffold with `#!/usr/bin/env bash`, `set -euo pipefail`, `$*` passthrough; `runtime.shell: "bash"`, `platforms: ["linux", "macos"]`.
- `templates/cmd/.dazzlecmd.json.tmpl` + `templates/cmd/{name}.cmd.tmpl` -- cmd scaffold with `@echo off`, `setlocal`/`endlocal`, `%*` passthrough, `exit /b 0`; `runtime.shell: "cmd"`, `platforms: ["windows"]`.
- `templates/binary/.dazzlecmd.json.tmpl` + `templates/binary/README.md.tmpl` -- binary scaffold for pre-built executables. Manifest has `runtime.type: "binary"`, `binary_path: "{name}"` (drop-in default), cross-platform metadata. README explains drop-in vs PATH-lookup vs absolute-path patterns and clarifies when to pick `binary` over `generic`.

### Refs

Ships with dazzlecmd v0.7.45.
Refs dazzlecmd #35.

## [0.6.5] - 2026-05-16

Ships with dazzlecmd v0.7.43 (closes dazzlecmd #67). Engine + cli_helpers updates so shadowed tools win short-name dispatch: `_dispatch_registry_path` attempts tool lookup before the meta-command path, and the build-time conflict warning is reworded to reflect the new precedence. See dazzlecmd CHANGELOG `[0.7.43]` for full details. CHANGELOG entry retroactively added in 0.6.6 commit.

### Changed

- `engine._dispatch_registry_path` -- tool lookup precedes meta-command lookup. Non-shadowed reserved names route to the meta-command path as before (resolve_command returns None for names without a registered tool).
- `cli_helpers.build_tool_subparsers` -- shadowed-tool warning reworded ("tool wins short-name dispatch" instead of "skipping").

### Refs

- Closes dazzlecmd #67. Ships with dazzlecmd v0.7.43.

## [0.6.6] - 2026-05-16

Ships with dazzlecmd v0.7.44 (Tier 2A.2). Bundles per-language scaffolding templates under `dazzlecmd_lib/templates/`: seven directories (`python`, `rust`, `node`, `powershell`, `c_cpp`, `docker`, `generic`) with manifest + entry-point source templates for each. Python additionally ships a `__full__/` overlay (README + pytest stub) for `dz new tool --full --language python`. No library API change; the lib continues to expose its existing `AggregatorEngine`, `FQCNIndex`, `default_meta_commands`, etc. The new content is the templates themselves.

### Added

- **Seven per-language template directories** under `src/dazzlecmd_lib/templates/`:
  - `python/` -- `.dazzlecmd.json.tmpl`, `{name_underscore}.py.tmpl`, and `__full__/README.md.tmpl` + `__full__/tests/test_{name_underscore}.py.tmpl`
  - `rust/` -- `.dazzlecmd.json.tmpl`, `Cargo.toml.tmpl`, `src/main.rs.tmpl`
  - `node/` -- `.dazzlecmd.json.tmpl`, `package.json.tmpl`, `index.js.tmpl`
  - `powershell/` -- `.dazzlecmd.json.tmpl`, `{name}.ps1.tmpl`
  - `c_cpp/` -- `.dazzlecmd.json.tmpl`, `Makefile.tmpl`, `main.c.tmpl`
  - `docker/` -- `.dazzlecmd.json.tmpl`, `Dockerfile.tmpl`
  - `generic/` -- `.dazzlecmd.json.tmpl`, `README.md.tmpl` (for tools that already exist as a binary or script)
- **Recursive package-data globs** in `pyproject.toml` so subdirectory template files ship in the wheel.

### Changed

- Templates dir layout migrated from flat (`dazzlecmd.json.tmpl` + `python_tool.py.tmpl` at the root) to per-language subdirs. Consumers calling into the new `dz new tool --language X` flow get scaffolds appropriate to X; the consumer-facing API surface (the engine, default_meta_commands, render functions) is unchanged.

### Tests

Coverage in dazzlecmd's `tests/test_cmd_new_tool_languages.py` (20 new tests). Lib-package-internal test surface remains the responsibility of the consumer (see X-1 / X-8 in the closeout plan for the dedicated lib test suite).

### Refs

Ships with dazzlecmd v0.7.44.
Companion to Tier 2A.2 work; refs #35 (`dz new` redesign).

## [0.6.4] - 2026-05-14

Ships with dazzlecmd v0.7.41 (closes dazzlecmd #65). Adds realpath-based auto-aliasing at discovery time so the same on-disk script reached via two FQCNs (junction loop, symlink, cross-embedded aggregators with shared physical files) collapses to one canonical + one auto-realpath alias. Display surfaces inherit the `[+]` marker semantics for free; dispatch via any FQCN still works.

### Added

- **`AggregatorEngine._realpath_index`** -- per-engine `{realpath: canonical_fqcn}` map populated during `_build_fqcn_index`.
- **`FQCNIndex._alias_sources`** -- side-table `{alias_fqcn: source}` where `source` is `"auto-realpath"` for realpath dedup or the virtual-kit manifest path for declared aliases. Consumed by `render_info` for accurate provenance banners.
- **`render_info` auto-realpath provenance banner** -- distinct DIM banner shown when the user dispatches via an auto-realpath alias FQCN, distinguishing it from virtual-kit alias resolutions.

### Changed

- **`_build_fqcn_index`** -- groups projects by `realpath(_dir)`; per group, shortest FQCN wins canonical (segment count then alphabetical); rest register as auto-realpath aliases. Marks demoted projects with `_auto_realpath_alias=True` and `_canonical_fqcn=<winner>`.
- **`engine.projects` filter** -- auto-realpath aliases excluded from the active dispatch list after `_build_fqcn_index`. Custom list handlers (consumer-side `_wtf_list_handler` etc.) see one project per physical script automatically without each handler needing dedup logic.
- **`_apply_virtual_kits`** -- when the virtual-kit's declared target was demoted to an auto-realpath alias, the new alias points directly at the actual canonical instead of raising KeyError. Single-hop alias invariant preserved.
- **`build_list_entries`** -- omits projects marked `_auto_realpath_alias` from canonical iteration; omits auto-realpath alias entries from alias iteration (they would otherwise render under bogus "(virtual kit '<path>')" section headers). The `[+]` marker on the canonical signals their existence.
- **`render_list` footer** -- `[+]` marker explanation updated to acknowledge both virtual-kit overlays and auto-realpath dedup.

### Fixed

- **Duplicate rows in `dz list`-class commands** when the same physical script is reachable via two FQCNs.
- **"missing canonical" warnings from virtual-kit application** when the virtual kit targets an FQCN that was demoted to an auto-realpath alias.

### Tests

Coverage in dazzlecmd's `tests/test_engine_recursive.py::TestRealpathDedup` (9 new tests). All 1068 dazzlecmd tests pass; lib-package-internal test surface remains the responsibility of the consumer (see X-1 / X-8 in the closeout plan for the dedicated lib test suite).

### Refs

Closes dazzlecmd #65.
Companion to dazzlecmd v0.7.41.

## [0.6.3] - 2026-05-13

Ships with dazzlecmd v0.7.40 (Tier 2A.1 -- closes dazzlecmd #61). Adds the rendering-side of the `long_description` mini-manpage feature -- the schema field landed in dazzlecmd v0.7.40 (scaffolding side); this surface is the rendering complement so the feature is end-to-end usable in one release.

### Added

- **`render_info` renders `long_description`** -- when the manifest's optional `long_description` field is non-empty, render a `Details:` section below the standard field rows. BOLD section header (when color enabled); body indented two spaces and wrapped to terminal width using the existing `_wrap_description` helper. Multi-line `long_description` content preserves paragraph breaks (blank lines in input render as blank lines in output).

### Tests

- +6 new in `tests/test_default_meta_commands.py::TestRenderInfoLongDescription` covering: present-renders-with-header, absent-no-block, missing-field-backward-compat, whitespace-only-no-block, wraps-to-terminal-width, multi-line-preserved.
- 1053 passed, 13 skipped (up from 1047 in dazzlecmd v0.7.39 / lib v0.6.2).

### Notes

This commit closes the rendering gap that the v0.7.40 scaffolding side would have left open. Per the cross-phase-dependencies-park-partials feedback, we ship the smallest self-sufficient slice: scaffold the field + render the field in the same release.

## [0.6.2] - 2026-05-12

Ships with dazzlecmd v0.7.39 (bug-fix patch -- closes dazzlecmd #64). Fixes a regression in `render_kit_list` that v0.6.1's honest `kit["tools"]` populate exposed, plus four hardcoded `'dz'` strings in user-facing hint and warning text that gave non-dazzlecmd consumers bad advice.

### Fixed

- **`render_kit_list` FQCN matching** (`default_meta_commands.py:1178-1207`) -- the kit-tool-to-project lookup used `ref.split(":", 1)` which only handles 2-segment refs. For multi-segment FQCNs (e.g. `dz:core:find`, `wtf:core:locked`) produced by the v0.6.1 post-recursion populate, the splitter yielded the wrong `name_part` and every tool rendered as `(not found)`. Now matches by `_fqcn` first; falls back to legacy `ns:name` parsing for backward compat. Display column shows the project's leaf name, not the full FQCN.

- **Hardcoded `'dz'` in `FQCNIndex` precedence-note** (`engine.py:412/414`) -- non-dazzlecmd consumers now see `"Use 'wtf core:locked' to be explicit"` instead of `"Use 'dz core:locked' to be explicit"`.

- **Hardcoded `'dz'` in deeply-nested-tool hint** (`engine.py:1244-1248`) -- now `"{cmd} kit silence ..."`.

- **Hardcoded `'dz'` in stale-favorite warning** (`engine.py:742-749`) -- now `"{cmd} kit favorite list"` / `"{cmd} kit favorite --remove ..."`.

- **Hardcoded `'dz'` in short-name-collision hint in `render_list`** (`default_meta_commands.py:445-447`) -- uses `getattr(engine, "command", None) or "dz"`.

### Changed

- **`FQCNIndex.__init__` signature** -- adds `command="dz"` kwarg. Backward-compatible default; engine passes `self.command` so consumer-specific messages render correctly. Legacy callers that instantiate `FQCNIndex()` directly without an engine context continue to work.

### Known deferred

- **DockerRunner image-not-found hint** (`registry.py:1200`) still emits `Try: dz setup <fqcn>`. The runner factory doesn't have `engine.command` plumbed in; fixing requires either threading the engine through or stashing command on the project at discovery. Low priority (only fires when Docker pre-flight fails).

### Tests

- +4 new (1025 total in main repo, up from 1021): 3 in `TestRenderKitList` covering FQCN-match path, leaf-name display, and legacy `ns:name` fallback; 1 in `TestRerootHint::test_hint_uses_engine_command` regression guard.

## [0.6.1] - 2026-05-12

Ships with dazzlecmd v0.7.38 (bug-fix patch -- closes dazzlecmd #63). Fixes a structural bug in `discover_kits` / `_load_in_repo_kit_manifest` that made the "aggregator-as-kit" embedding path produce wrong identity fields and a misconstructed `tools_dir`. The forward direction (dazzlecmd embeds wtf-windows) happened to work because the inner kits' declared structural fields aligned by coincidence; the inverse direction (wtf-windows embeds dazzlecmd) broke because dazzlecmd's per-kit pointers are minimal. Empirically surfaced during a recursion-proof experiment.

### Fixed

- **`_load_in_repo_kit_manifest` Pattern 2 (aggregator-as-kit)** -- `loader.py:88`. The old code picked the first inner kit file (alphabetically) and merged ALL its fields into the outer pointer, including identity fields like `name`, `tools`, `description`, `version`. The new code:
  - Detects single-kit-using-kits-subdir-convention case (exactly one inner kit, named after the outer pointer) and merges fully (legacy compatibility).
  - Detects aggregator-as-kit case (multiple inner kits OR no name-matching kit) and extracts ONLY structural hints (`tools_dir`, `manifest`) from the first non-virtual inner kit that declares them. Never identity fields.
  - Keeps `tools_dir` RELATIVE, so the engine's `_recurse_into_nested` joins it with `nested_root` correctly.
  - Returns `None` if no inner kits declare hints -- engine falls back to defaults (`tools_dir="projects"`, `manifest=".dazzlecmd.json"`).

- **`discover_kits` always sets `kit["name"]` from the registry pointer** -- `loader.py:73-83`. Identity now always comes from the registry-derived `kit_name`. Previously the kit dict's `name` field could come from an inner kit's manifest or the registry pointer depending on which Pattern-2 branch was taken. The merge accidentally hid the intended semantic.

- **`_discover_aggregator` populates aggregator-as-kit's `tools` list post-recursion** -- `engine.py:864-872`. After the nested aggregator's projects are discovered, the parent kit's `tools` field is populated with the FQCNs of contributed projects. Makes `dz kit list` show the correct tool count for embedded aggregators. Pre-v0.6.1 the count came from the buggy merge.

### Recursion proof

The "any aggregator can attach to any other" architectural claim is now **empirically validated in both directions**:

- Forward (dazzlecmd embeds wtf-windows): unchanged from v0.6.0 (no regression).
- Inverse (wtf-windows embeds dazzlecmd): `wtf list` shows all 19 dazzlecmd tools + 2 wtf own. `wtf kit list` shows `dz 22 tool(s) (always active)`. Three-tier recursion `dz:wtf:core:locked` works (wtf embeds dazzlecmd embeds wtf, with the deeply-nested-tool hint firing).

### Tests

- +5 new tests in `tests/test_library.py::TestAggregatorAsKitDiscovery` covering: pointer-name preservation in aggregator case, structural-hint extraction from inner kits, no-hints fallback to engine defaults, Pattern 1 single-kit unchanged regression guard, end-to-end engine recursion populating `kit.tools` with discovered FQCNs. Full suite 1021 passed, 13 skipped.

## [0.6.0] - 2026-05-12

Ships with dazzlecmd v0.7.37 (Tier 1 commit 9, final -- closes #49). New top-level module `dazzlecmd_lib.colors` lands a slim ANSI color taxonomy that all the default meta-command renderers consume. Consumers (dazzlecmd, amdead, wtf-windows, sysdiagnose, future personal aggregators) inherit color output on every render surface automatically -- no per-consumer wiring required.

Slim by design: 8-color ANSI palette (RESET / BOLD / DIM / RED / GREEN / YELLOW / CYAN / BRIGHT_RED), broadly supported across PuTTY, cmd.exe, PowerShell, Windows Terminal, conhost.exe with VT processing, bash, zsh, WSL. No 256-color or truecolor (RGB) codes because those break older terminals. colorama is an optional Windows-only extra; modern Windows 1511+ handles ANSI natively via `ENABLE_VIRTUAL_TERMINAL_PROCESSING` so colorama isn't required for most users. Disable color via `NO_COLOR=1` (community standard) or `DZ_COLOR=never` (project-specific). Force color through a pipe via `DZ_COLOR=always` or `FORCE_COLOR=1`.

### Added

- **`dazzlecmd_lib.colors`** -- new module. Public API: `RESET`, `BOLD`, `DIM`, `RED`, `GREEN`, `YELLOW`, `CYAN`, `BRIGHT_RED` (ANSI escape strings), `should_use_color(stream=None) -> bool` (env-aware TTY probe; precedence `NO_COLOR > DZ_COLOR=always|FORCE_COLOR > DZ_COLOR=never > stream.isatty()`), `colorize(text, *codes) -> str` (wrap text in ANSI codes terminated with RESET), `colorize_for(stream, text, *codes) -> str` (convenience wrapper combining `should_use_color(stream)` + `colorize` for explicit-stream/explicit-codes call sites), `warn(text, stream=None) -> str` (YELLOW; defaults stream to `sys.stderr`), `error(text, stream=None) -> str` (BRIGHT_RED; defaults stream to `sys.stderr`). The semantic `warn` / `error` wrappers are the recommended pattern for stderr advisories and errors; `colorize_for` and `colorize` remain available for non-standard styling. On Windows the module lazily initializes colorama; forced-color paths (`DZ_COLOR=always` / `FORCE_COLOR`) call `colorama.init(strip=False)` so ANSI bytes survive into redirected pipes (colorama's default strips them).

- **`[color]` optional extra** -- `colorama>=0.4.0` declared as a Windows-only optional dependency. Install via `pip install dazzlecmd-lib[color]` for legacy cmd.exe (codepage 437/1252) terminals. Most modern Windows installations don't need it because Win10 1511+ supports ANSI natively.

### Changed

- **`render_list`** -- section headers BOLD; virtual-kit annotation `(virtual: <vk_name>)` DIM; shadow `[*]` marker BOLD+RED; dual-presence `[+]` marker CYAN; flat-fallback header row BOLD. Column-width math handles ANSI codes correctly via a plain/styled label split.

- **`render_info`** -- alias provenance line (both qualified and standard variants) DIM; "Shadow status:" banner BOLD+YELLOW. Tool field labels stay plain (BOLD on every label would be noisy).

- **`render_tree`** -- root header BOLD; kit names BOLD; markers `[always_active]` / `[aggregator]` / `[disabled]` / `[virtual]` DIM; shadow `[shadowed]` marker BOLD+RED (consistency with `render_list`); virtual-kit alias arrows (`->`) DIM.

- **`render_kit_list`** -- kit names BOLD; `(always active)` annotation DIM; `cross-platform` platform value DIM (OS-specific values like `windows` / `linux` stay plain to stand out); `(not found)` marker DIM.

- **`render_kit_status`** -- kit names BOLD.

- **stderr warning paths in `default_meta_commands.py` and `cli_helpers.py`** -- user-facing meta-command stderr writes now use `colorize_for(sys.stderr, ...)` with YELLOW for advisories (tool-not-found, no-setup, conflicts-with-reserved) or BRIGHT_RED for errors (tree-requires-engine, kit-not-found, override-file-parse-failure, override-file-read-failure, generic setup-resolve failure). engine/loader/registry subprocess-orchestration stderr paths are intentionally untouched in this commit; sweep deferred to a follow-up so the higher-risk plumbing paths get their own attention.

### Notes

- `colors.py` is documented with detection-priority commentary in the module docstring, plus per-function docstrings showing the recommended usage patterns. The `_init_windows_ansi(force=False)` helper is module-private but documented for maintainers; `force=True` is the escape hatch for forced-color piped output on Windows.

- Test fixtures (`reset_ansi_init`, `clear_color_env`, `_TTYStream`, `_NonTTYStream`) in `tests/test_colors.py` are the recommended pattern for any future test that exercises color-detection paths.

## [0.5.0] - 2026-05-07

Ships with dazzlecmd v0.7.34 (Tier 1 commit 6 -- the X-22-narrow CLI collapse). The library reaches full byte-equivalence parity with dazzlecmd's pre-collapse `_cmd_list` / `_cmd_info` / `_cmd_tree` so dazzlecmd can collapse those commands to thin wrappers without losing any user-visible surface.

### Added

- **`tree_parser_factory --show-disabled`** -- the `dz tree` parser now accepts `--show-disabled`, matching dazzlecmd's pre-collapse CLI parser. Library consumers (amdead, wtf-windows, sysdiagnose, future personal aggregators) inherit the flag automatically.

- **`render_tree` engine-aware tree behaviors** -- when `args.show_disabled` is set, the function uses `engine.all_projects` in place of the supplied `projects`. Kit headers render `[always_active]` / `[aggregator]` / `[disabled]` markers, computed from `engine.kits` (always_active flag, presence of a nested `kits/` subdir) and from `engine._get_user_config()` (`active_kits` / `disabled_kits`). Virtual-kit headers also render `[disabled]` when the kit's state computes as disabled. JSON output gains `always_active`, `is_aggregator`, and `state` keys per kit.

### Changed

- **`render_info` "tool not found" message** -- now `f"Tool '{tool_name}' not found. Use '{engine.command} list' to see available tools."` printed to stdout. Previously the message was `f"Tool {tool_name!r} not found. Run 'list' to see available tools."` printed to stderr. The new wording uses the consumer's command name (so amdead users see `Use 'amdead list' to see available tools.` rather than a bare `list` hint), and prints to stdout to match dazzlecmd's pre-collapse CLI behavior. Behavior change for any consumer that was relying on the message going to stderr or the exact prior wording. Justified for v0.5.0 because both consumers (amdead, wtf) get a more useful message and the pre-1.0 lib version policy permits the minor wording change.

### Notes

- `render_tree` and `render_info` were ported from dazzlecmd's `cli.py` (lines 2098-2312 and 1119-1220 respectively) per copy-don't-rewrite discipline. The dazzlecmd CLI's `_cmd_tree` then collapsed to a thin wrapper calling `render_tree`. Same pattern as the v0.4.0 (info-parity port) and v0.4.1 (link-helpers port) commits.

- The library's `_wrap_description` is now also imported by dazzlecmd's `cli.py` as a back-compat shim (the remaining consumer is `_cmd_kit_list`'s virtual-kit listing path; Category C, deferred to a future X-22-full collapse).

## [0.4.1] - 2026-05-07

Ships with dazzlecmd v0.7.33 (Tier 1 commit 5 of the master closeout plan).

### Added

- **`dazzlecmd_lib.paths.is_linked_project(tool_dir)`** -- cross-platform symlink/junction detection. On Windows, uses `ctypes.windll.kernel32.GetFileAttributesW` to detect the `FILE_ATTRIBUTE_REPARSE_POINT` flag (catches both symlinks AND junctions); falls back to `os.path.islink` if the ctypes call fails. On POSIX, uses `os.path.islink` directly. Public API.

- **`dazzlecmd_lib.paths.get_link_target(tool_dir)`** -- returns the resolved target of a symlink/junction, or `None` for non-links. Uses `os.readlink`. Public API.

- **`render_info` "Linked to:" display line** -- when a project's `_dir` is a symlink/junction, surfaces the link target. Library consumers (amdead, wtf-windows, sysdiagnose, future personal aggregators) get this surface for free.

### Notes

- Helpers were ported verbatim from `dazzlecmd.importer:141-168` per copy-don't-rewrite discipline. dazzlecmd's `importer` keeps the import surface stable via a back-compat re-export.

## [0.4.0] - 2026-05-07

Ships with dazzlecmd v0.7.32 (info-parity port).

### Added

- **`render_info` parity with dazzlecmd's `_cmd_info`** -- library consumers now get the full info display surface. The library `render_info` is the canonical implementation; dazzlecmd's CLI continues to use its own copy until the v0.7.34 X-22-narrow collapse.
- **`--raw` flag in `info_parser_factory`** -- shows raw manifest fields without runtime resolution.
- **`--platform` flag in `info_parser_factory`** -- previews platform-conditional dispatch resolution (`runtime.platforms` + `prefer`).
- **Runtime-dispatch helpers** -- `_RUNTIME_DISPATCH_FIELDS` constant + `_print_runtime_dispatch_fields`, `_print_runtime_resolved`, `_print_runtime_raw`, `_print_runtime_platform_preview` (private but stable).
- **Qualified-alias provenance variant** -- `render_info` shows the provenance line in two forms: standard FQCN-only and qualified-alias (`dazzletools:claude:foo` style).
- **Pass-through marker** -- `render_info` flags pass-through tools (`pass_through: true`).
- **Python deps display** -- `render_info` lists `runtime.deps` for Python tools.
- **Setup hint with `engine.command`** -- the "run setup" hint uses the consumer's command name (e.g., `amdead setup foo`, not a hardcoded `dz setup foo`).

## [0.3.0] - 2026-05-07

Ships with dazzlecmd v0.7.31 (render_list parity port).

### Added

- **`render_list` parity with dazzlecmd's `_cmd_list`** -- library consumers get the full list display: `--show {default,canonical,alias,all}` modes, sectioned virtual-kit layout with `[+]` markers (dual-presence indicator), engine-aware FQCN/alias resolution.
- **Public `build_list_entries(projects, engine, show_mode, kit_filter)`** -- data-layer API for non-dazzlecmd consumers that want to compose their own renderers without inheriting the library's display.
- **`render_tree` virtual-kit branches** -- library tree command displays virtual kits as branches alongside canonical kits.
- **`_wrap_description` helper** -- terminal-aware description wrapping for list/tree displays.

## [0.2.0] - 2026-05-06

Ships with dazzlecmd v0.7.30 (closes dazzlecmd #56 -- shadow-aware warning + discoverability).

### Added

- **Shadow-aware behavior in `render_info`** -- when a tool is shadowed by a higher-precedence registration, the info display surfaces the shadow chain so users can see what's hiding what.
- **Shadow-aware behavior in `render_tree`** -- shadowed tools are flagged in the tree display.
- **Shadow detection helpers** -- ported from dazzlecmd's CLI to give all library consumers the same shadow visibility.

## [0.1.0] - 2026-04-15

Initial extraction (dazzlecmd v0.7.13 -- Phase 4b step 1+2).

### Added

- **`AggregatorEngine`** -- configurable CLI tool aggregator with recursive kit discovery.
- **`FQCNIndex`** -- dual-index lookup (exact FQCN + short-name precedence resolution).
- **`RunnerRegistry`** -- extensible runtime dispatch (python, shell, binary, docker, etc.).
- **`ConfigManager`** -- user config read/write with atomic writes and merge semantics.
- **Kit discovery** -- manifest-driven tool/kit loading with namespace remapping.
- **Default meta-command implementations** -- `render_list`, `render_info`, `render_tree`, `render_kit_list`, `render_kit_status`, `render_version`, `render_setup` (initial versions; parity with dazzlecmd CLI grew in subsequent MINORs).
