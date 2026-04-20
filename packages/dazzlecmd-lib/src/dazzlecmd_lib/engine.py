"""Generic aggregator engine for dazzlecmd and compatible projects.

The AggregatorEngine is the shared core that powers any tool aggregator.
dazzlecmd, wtf-windows, and future aggregators are all instances of this
engine configured with different data (command name, directory layout,
manifest filename, etc.).

Usage:
    from dazzlecmd_lib.engine import AggregatorEngine

    engine = AggregatorEngine(
        name="my-tools",
        command="mt",
        tools_dir="tools",
        kits_dir="kits",
        manifest=".mt.json",
        description="My tool collection",
    )

    def main():
        return engine.run()
"""

import json
import os
import sys

from dazzlecmd_lib.loader import (
    discover_kits,
    discover_projects,
    get_active_kits,
)
from dazzlecmd_lib.registry import RunnerRegistry
from dazzlecmd_lib.config import ConfigManager
from dazzlecmd_lib.meta_command_registry import MetaCommandRegistry
from dazzlecmd_lib.resolution_context import ResolutionContext


class FQCNCollisionError(Exception):
    """Raised when two projects/aliases declare the same FQCN during index build."""


class CircularDependencyError(Exception):
    """Raised when recursive aggregator discovery encounters a cycle."""


class FQCNIndex:
    """Two-tier naming index for Fully Qualified Collection Names.

    The engine maintains two distinct kinds of FQCN:

    - **Canonical FQCN**: filesystem-governed. Every on-disk tool has
      exactly one. Format: ``<kit>[:<sub>]*:<tool>`` — e.g., ``core:rn``,
      ``wtf:core:restarted``.
    - **Alias FQCN**: declared by a virtual-kit manifest (a kit with
      ``"virtual": true``). Points to a canonical. Resolution is
      transparent: wherever a canonical works, the alias works too.

    Invariants:

    - §9b: an alias FQCN MUST NOT equal any canonical FQCN. A virtual kit
      cannot shadow a real tool. Mirror rule: a canonical added after an
      alias claims the same FQCN is rejected.
    - Alias shorts populate ``short_index`` the same as canonical shorts
      (revised in v0.7.28 — rule 7c relaxed). Virtual kits are first-class
      kits; their aliases contribute to short-name resolution via the
      existing precedence mechanism. When an alias short collides with a
      canonical short (or another alias short), the effective precedence
      order determines the winner and a notification is emitted.
    - Aliases are single-hop. Transitive aliases (alias -> alias -> ...)
      are rejected at insert time (Phase 4e). Phase 5 adds a single
      exception for ``deprecation.relocated_to_fqcn`` pointers.

    Data members:

    - ``canonical_index: {fqcn: project}`` — canonical FQCN dispatch
    - ``alias_index: {alias_fqcn: canonical_fqcn}`` — alias -> target
    - ``short_index: {short_name: [canonical_fqcn, ...]}`` — populated by
      both ``insert_canonical`` (canonical's short name) and ``insert_alias``
      (alias's last segment). Values are canonical FQCNs in either case —
      dispatch always lands on a canonical project.
    - ``shortcut_candidates: {(kit_first, tool_last): [canonical_fqcn, ...]}`` —
      O(1) lookup for 2-segment "kit-qualified shortcut" resolution
      (e.g., ``wtf:locked`` -> ``wtf:core:locked``). Replaces the O(n)
      list comprehension with a precomputed index, sorted for stable
      tiebreaks on ambiguity. Populated by ``insert_canonical``.
    - ``kit_order`` — ordered list of top-level canonical kit names
      (discovery order), used for precedence rank defaults.
    """

    def __init__(self):
        self.canonical_index = {}
        self.alias_index = {}
        self.short_index = {}
        self.shortcut_candidates = {}
        self.kit_order = []

    # -- insertion --------------------------------------------------------

    def insert_canonical(self, project):
        """Register a canonical project.

        The project dict must carry ``_fqcn``, ``_short_name``, and
        ``_kit_import_name`` (set by the engine during discovery).

        Raises ``FQCNCollisionError`` if the FQCN is already present as
        canonical OR alias (§9b mirror).
        """
        fqcn = project["_fqcn"]
        short = project["_short_name"]
        kit = project["_kit_import_name"]

        if fqcn in self.canonical_index:
            existing = self.canonical_index[fqcn]
            raise FQCNCollisionError(
                f"Duplicate canonical FQCN '{fqcn}': "
                f"{existing.get('_dir', '?')} vs {project.get('_dir', '?')}"
            )
        # §9b mirror: canonicals cannot collide with existing aliases.
        # (Canonicals typically load first in practice, but this closes
        # the invariant symmetrically.)
        if fqcn in self.alias_index:
            target = self.alias_index[fqcn]
            raise FQCNCollisionError(
                f"Canonical FQCN '{fqcn}' collides with existing alias "
                f"(-> '{target}'). Remove or rename the alias first."
            )

        self.canonical_index[fqcn] = project
        self.short_index.setdefault(short, []).append(fqcn)
        if kit not in self.kit_order:
            self.kit_order.append(kit)

        # Populate shortcut_candidates. Every 2+-segment canonical
        # contributes one (first_segment, last_segment) entry. Multiple
        # entries under the same key are tracked for ambiguity detection.
        segments = fqcn.split(":")
        if len(segments) >= 2:
            key = (segments[0], segments[-1])
            bucket = self.shortcut_candidates.setdefault(key, [])
            bucket.append(fqcn)
            bucket.sort()  # stable alphabetical tiebreaker

    def insert_alias(self, alias_fqcn, canonical_fqcn, source=None):
        """Register ``alias_fqcn`` as a pointer to ``canonical_fqcn``.

        The canonical MUST already be in ``canonical_index`` — aliases
        cannot point to other aliases (single-hop rule) nor to non-existent
        targets. Virtual-kit processing happens AFTER canonical discovery
        to satisfy this ordering.

        Idempotent re-registration with the same target is a silent no-op.
        Different-target conflict is rejected (first virtual kit wins).

        Raises:
            FQCNCollisionError: when ``alias_fqcn`` equals an existing
                canonical FQCN (§9b shadowing prevention) or conflicts
                with an existing alias pointing to a different target.
            KeyError: when ``canonical_fqcn`` is not in the canonical index.
        """
        if canonical_fqcn not in self.canonical_index:
            raise KeyError(
                f"Virtual kit alias '{alias_fqcn}' -> '{canonical_fqcn}': "
                f"target FQCN not found in canonical index. "
                f"Check the 'tools' list in the virtual kit manifest"
                + (f" ({source})" if source else "")
                + "."
            )

        # §9b: alias MUST NOT shadow a canonical.
        if alias_fqcn in self.canonical_index:
            raise FQCNCollisionError(
                f"Virtual kit alias '{alias_fqcn}' collides with a real "
                f"canonical FQCN. A virtual kit cannot shadow a real tool "
                f"(rule 9b). "
                + (f"(declared in {source}) " if source else "")
                + "Rename the alias or remove the virtual-kit entry."
            )

        # Conflict with a different existing alias is rejected; same-target
        # is idempotent (two virtual kits declaring the same alias to the
        # same canonical is harmless).
        if alias_fqcn in self.alias_index:
            existing = self.alias_index[alias_fqcn]
            if existing != canonical_fqcn:
                raise FQCNCollisionError(
                    f"Virtual kit alias '{alias_fqcn}' already maps to "
                    f"'{existing}'; cannot remap to '{canonical_fqcn}'. "
                    + (f"(conflicting declaration in {source})" if source else "")
                )
            return  # idempotent no-op

        self.alias_index[alias_fqcn] = canonical_fqcn

        # Rule 7c (v0.7.28 relaxation): alias shorts populate short_index
        # the same as canonical shorts. Virtual kits are first-class kits;
        # their aliases contribute to short-name resolution via the
        # existing precedence mechanism. This makes `dz cleanup` resolve
        # to the canonical target when 'claude:cleanup' is aliased with
        # alias short 'cleanup'. Collisions with canonical shorts (or
        # other alias shorts) are resolved by _effective_precedence.
        # The short_index value list stores the CANONICAL FQCN (what
        # actually dispatches), not the alias — resolution returns the
        # canonical project with a ResolutionContext reflecting the
        # alias traversal.
        alias_short = alias_fqcn.rsplit(":", 1)[-1]
        short_bucket = self.short_index.setdefault(alias_short, [])
        if canonical_fqcn not in short_bucket:
            short_bucket.append(canonical_fqcn)

    # -- resolution -------------------------------------------------------

    def resolve(self, name, precedence=None, favorites=None):
        """Resolve a user-typed name to a ``(project, ResolutionContext)`` tuple.

        Args:
            name: The user-typed command name. May be an FQCN (contains
                ``:``), an alias FQCN, or a short name.
            precedence: Optional ordered list of kit names that overrides
                the default precedence for short-name resolution.
            favorites: Optional ``{short_name: fqcn}`` mapping. When a
                favorite is set for the input name, its target is used
                (unconditionally, bypassing precedence). Stale favorites
                (target missing from the index) produce a warning
                notification and fall through to precedence.

        Returns:
            ``(project, context)`` on success, where ``context`` is a
            ``ResolutionContext`` documenting HOW resolution happened.
            Returns ``(None, None)`` when nothing matches.

        Notes:
            Favorites can point to either a canonical FQCN or an alias
            FQCN. In the alias case, the context records both
            ``alias_fqcn`` AND ``resolution_kind="favorite"`` — the
            favorite traversed an alias en route to the canonical.
        """
        # -- FQCN-shaped input (contains ':') --
        if ":" in name:
            # 1. Canonical direct hit
            project = self.canonical_index.get(name)
            if project is not None:
                return project, ResolutionContext(
                    original_input=name,
                    canonical_fqcn=name,
                    resolution_kind="canonical",
                )

            # 2. Alias direct hit (follow single-hop to canonical)
            if name in self.alias_index:
                canonical_fqcn = self.alias_index[name]
                project = self.canonical_index.get(canonical_fqcn)
                if project is not None:
                    return project, ResolutionContext(
                        original_input=name,
                        canonical_fqcn=canonical_fqcn,
                        resolution_kind="alias",
                        alias_fqcn=name,
                    )
                # Defensive: alias_index must always point at a real
                # canonical. This branch only hits on index corruption.
                return None, ResolutionContext(
                    original_input=name,
                    canonical_fqcn=canonical_fqcn,
                    resolution_kind="alias",
                    alias_fqcn=name,
                    notification=(
                        f"dz: alias '{name}' -> '{canonical_fqcn}' points "
                        f"to a missing canonical entry (index corruption?)."
                    ),
                )

            # 3. Kit-qualified shortcut (O(1) via shortcut_candidates).
            # Only applies to 2-segment inputs; 3+ segments that didn't
            # exact-match are simply unresolved. Shortcuts search
            # canonical_index only -- aliases had their direct-hit chance
            # in step 2.
            kit_prefix, _, tool_suffix = name.partition(":")
            if tool_suffix and ":" not in tool_suffix:
                matches = self.shortcut_candidates.get(
                    (kit_prefix, tool_suffix), []
                )
                if len(matches) == 1:
                    fqcn = matches[0]
                    return self.canonical_index[fqcn], ResolutionContext(
                        original_input=name,
                        canonical_fqcn=fqcn,
                        resolution_kind="kit_shortcut",
                    )
                if len(matches) > 1:
                    picked = matches[0]  # already sorted on insert
                    display = ", ".join(matches)
                    return self.canonical_index[picked], ResolutionContext(
                        original_input=name,
                        canonical_fqcn=picked,
                        resolution_kind="kit_shortcut",
                        notification=(
                            f"dz: '{name}' is ambiguous within kit "
                            f"'{kit_prefix}': {display}. "
                            f"Use the full FQCN to be explicit."
                        ),
                    )

            return None, None

        # -- Short-name input --
        candidates = self.short_index.get(name, [])

        # Favorite short-circuit: an explicit user pin trumps precedence.
        # Favorites may target a canonical OR an alias; we follow the
        # alias single-hop if needed. Stale favorites (dead target) fall
        # through to precedence with a warning.
        if favorites and name in favorites:
            favorite_fqcn = favorites[name]
            favorite_alias = None
            favorite_project = self.canonical_index.get(favorite_fqcn)
            if favorite_project is None and favorite_fqcn in self.alias_index:
                canonical_target = self.alias_index[favorite_fqcn]
                favorite_project = self.canonical_index.get(canonical_target)
                if favorite_project is not None:
                    favorite_alias = favorite_fqcn
                    favorite_fqcn = canonical_target
            if favorite_project is not None:
                return favorite_project, ResolutionContext(
                    original_input=name,
                    canonical_fqcn=favorite_fqcn,
                    resolution_kind="favorite",
                    alias_fqcn=favorite_alias,
                )
            # Stale favorite -- warn and fall through to precedence.
            stale_note = (
                f"dz: warning: favorite '{name}' -> '{favorites[name]}' "
                f"not found (tool may have been removed, renamed, or "
                f"shadowed). Falling through to precedence."
            )
            if not candidates:
                return None, ResolutionContext(
                    original_input=name,
                    canonical_fqcn="",
                    resolution_kind="favorite",
                    notification=stale_note,
                )
            # Ambiguous or single-candidate fall-through -- let the
            # precedence/single-match logic below produce the context,
            # and we'll prepend the stale warning to its notification.
            _stale_prefix = stale_note
        else:
            _stale_prefix = None

        if not candidates:
            return None, None

        if len(candidates) == 1:
            fqcn = candidates[0]
            return self.canonical_index[fqcn], ResolutionContext(
                original_input=name,
                canonical_fqcn=fqcn,
                resolution_kind="precedence",
                notification=_stale_prefix,
            )

        order = self._effective_precedence(precedence)
        ranked = self._rank_by_precedence(candidates, order)
        picked_fqcn = ranked[0]
        other_fqcns = ranked[1:]
        others_display = ", ".join(self._kit_of(f) for f in other_fqcns)

        precedence_note = (
            f"dz: '{name}' resolved to {picked_fqcn} "
            f"(also in: {others_display}). "
            f"Use 'dz {picked_fqcn}' to be explicit."
        )
        if _stale_prefix:
            notification = _stale_prefix + "\n" + precedence_note
        else:
            notification = precedence_note

        return self.canonical_index[picked_fqcn], ResolutionContext(
            original_input=name,
            canonical_fqcn=picked_fqcn,
            resolution_kind="precedence",
            notification=notification,
        )

    def all_projects(self):
        """Return all canonical projects in insertion order (stable)."""
        return list(self.canonical_index.values())

    def _effective_precedence(self, override):
        """Return the effective kit precedence list.

        If ``override`` is provided, use it verbatim with any unknown kits
        appended at the end. Otherwise default: ``core`` first, then
        ``dazzletools``, then remaining kits in discovery order.
        """
        if override:
            tail = [k for k in self.kit_order if k not in override]
            return list(override) + tail

        default_priority = ["core", "dazzletools"]
        ordered = [k for k in default_priority if k in self.kit_order]
        tail = [k for k in self.kit_order if k not in ordered]
        return ordered + tail

    def _rank_by_precedence(self, fqcns, order):
        """Sort FQCNs by their top-level kit's position in ``order``."""
        def kit_rank(fqcn):
            kit = self._kit_of(fqcn)
            try:
                return order.index(kit)
            except ValueError:
                return len(order)

        return sorted(fqcns, key=kit_rank)

    @staticmethod
    def _kit_of(fqcn):
        """Return the top-level kit name from an FQCN."""
        return fqcn.split(":", 1)[0]


class AggregatorEngine:
    """A configurable CLI tool aggregator.

    Each instance represents a specific aggregator (dazzlecmd, wtf-windows,
    etc.) with its own command name, directory layout, and manifest format.
    The engine handles kit discovery, tool loading, parser building, and
    dispatch.
    """

    def __init__(
        self,
        name="dazzlecmd",
        command="dz",
        tools_dir="projects",
        kits_dir="kits",
        manifest=".dazzlecmd.json",
        description=None,
        version_info=None,
        is_root=True,
        parser_builder=None,
        meta_dispatcher=None,
        tool_dispatcher=None,
        meta_commands=None,
        include_default_meta_commands=True,
        extra_reserved_commands=None,
        config_dir=None,
        project_root=None,
    ):
        """Initialize the aggregator engine.

        Args:
            name: Human-readable name (e.g., "dazzlecmd", "wtf-windows")
            command: CLI command name (e.g., "dz", "wtf")
            tools_dir: Directory name for tool projects (e.g., "projects", "tools")
            kits_dir: Directory name for kit definitions (e.g., "kits")
            manifest: Default manifest filename (e.g., ".dazzlecmd.json", ".wtf.json")
            description: One-line description for --help
            version_info: Tuple of (display_version, full_version) or None
            is_root: If True, register meta-commands (list, info, kit, etc.).
                     If False (imported as kit), suppress meta-commands.
            parser_builder: Escape-hatch callable
                ``(projects, engine) -> argparse.ArgumentParser``. When set,
                bypasses the ``meta_registry`` path entirely — the engine
                delegates parser construction to this callback. Used by
                aggregators that need non-argparse CLIs or custom parser
                structure that the registry doesn't support.
            meta_dispatcher: Escape-hatch callable
                ``(args, projects, kits, project_root, engine) -> int``.
                When ``parser_builder`` is set, this handles meta-command
                dispatch. When ``parser_builder`` is None, the registry's
                own dispatch is used and this is ignored.
            tool_dispatcher: Escape-hatch callable ``(project, argv) -> int``.
                Dispatches to a tool's entry point. Used regardless of
                whether the registry path is active.
            meta_commands: Set of meta-command names (escape-hatch use).
                When ``parser_builder`` is set, this set determines which
                args are treated as meta vs tool dispatch. When the registry
                path is active, derived from ``meta_registry.registered()``.
            include_default_meta_commands: If True (default) and the registry
                path is active (``parser_builder`` is None), library defaults
                (list, info, kit, version, tree, setup) are auto-registered
                at construction. Set False to start with an empty registry.
            extra_reserved_commands: Additional names reserved from use as
                tool names beyond registered meta-commands. Typical use:
                reserve planned-but-unimplemented future commands.
            config_dir: Path to the aggregator's config directory. Defaults
                to ``~/.<command>`` when unset (e.g., ``~/.dz`` for
                ``command="dz"``). Per-aggregator config isolation means
                two aggregators in the same environment don't share config.
                Pass ``str`` or ``pathlib.Path``.
        """
        self.name = name
        self.command = command
        self.tools_dir = tools_dir
        self.kits_dir = kits_dir
        self.manifest = manifest
        self.description = description or f"{name} - tool aggregator"
        self.version_info = version_info
        self.is_root = is_root

        # Escape-hatch CLI callbacks: when parser_builder is set, the
        # registry path is bypassed and parser construction / meta
        # dispatch flow through these callbacks. Preserved for backward
        # compatibility with aggregators that predate the registry
        # (dazzlecmd's own cli.py uses these today) and for aggregators
        # that need non-argparse CLIs.
        self._build_parser = parser_builder
        self._dispatch_meta = meta_dispatcher
        self._dispatch_tool = tool_dispatcher
        self._meta_commands = meta_commands

        # Per-engine meta-command registry (primary path for new adopters).
        # Auto-populated with library defaults unless opted out. Aggregators
        # customize via engine.meta_registry.register / override / unregister.
        self.meta_registry = MetaCommandRegistry()
        if is_root and include_default_meta_commands:
            # Deferred import to avoid circular dep at module load
            from dazzlecmd_lib import default_meta_commands
            default_meta_commands.register_all(self.meta_registry)

        # Additional reserved names beyond registry contents.
        self._extra_reserved = set(extra_reserved_commands or ())

        # Optional epilog builder: callable (projects) -> str. Set as
        # attribute post-construction for aggregators with custom help text.
        self.epilog_builder = None

        # Config manager: per-aggregator by default (~/.<command>/config.json).
        # Aggregators can override by passing config_dir explicitly.
        if config_dir is None:
            default_config_dir = os.path.join(
                os.path.expanduser("~"), f".{command}"
            )
            self.config = ConfigManager(config_dir=default_config_dir)
        else:
            self.config = ConfigManager(config_dir=str(config_dir))

        # Route user-override file lookup through the same per-aggregator
        # directory (config_dir/overrides). The DAZZLECMD_OVERRIDES_DIR
        # env var still takes precedence (test isolation).
        from dazzlecmd_lib import user_overrides as _user_overrides
        _user_overrides.set_override_root(
            os.path.join(self.config.config_dir(), "overrides")
        )

        # Resolved at run time. project_root can be set via constructor
        # (for installed aggregators whose tools live at a known path that
        # find_project_root's library-__file__ walk can't reach) or
        # discovered at run() time via find_project_root().
        self._project_root_hint = project_root
        self.project_root = None
        self.kits = []
        self.active_kits = []
        self.projects = []
        self.fqcn_index = FQCNIndex()
        self._precedence_cache = None

    def find_project_root(self, start_path=None):
        """Find the project root by looking for tools_dir/ and kits_dir/.

        Walks up from start_path (or the engine module location) looking
        for a directory that contains both the tools and kits directories.
        """
        if start_path:
            current = os.path.abspath(start_path)
        else:
            current = os.path.dirname(os.path.abspath(__file__))

        for _ in range(5):
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
            if (os.path.isdir(os.path.join(current, self.tools_dir)) and
                    os.path.isdir(os.path.join(current, self.kits_dir))):
                return current

        return None

    def discover(self, project_root=None):
        """Run the full discovery pipeline recursively.

        Walks the aggregator tree rooted at ``project_root``, descending into
        nested aggregators (kits whose directory contains a ``kits/``
        subdirectory). Populates ``self.kits``, ``self.active_kits``,
        ``self.projects``, ``self.fqcn_index``, and applies virtual-kit
        aliases (Phase 4e Commit 2).

        Each project is annotated with ``_fqcn``, ``_short_name``, and
        ``_kit_import_name`` fields during discovery. Virtual kits are
        collected across all aggregator levels (cross-aggregator Option A)
        and applied as aliases after the canonical FQCN index is built.
        """
        if project_root:
            self.project_root = project_root
        elif self.project_root is None:
            # Precedence: explicit hint at construction > find_project_root walk
            if self._project_root_hint is not None:
                self.project_root = str(self._project_root_hint)
            else:
                self.project_root = self.find_project_root()

        if self.project_root is None:
            return

        loading_stack = frozenset()
        all_discovered, all_virtual_kits = self._discover_aggregator(
            self.project_root, loading_stack, depth=0, kit_prefix=None
        )

        # Partition: all_projects has everything (for display commands like
        # `dz tree --show-disabled`); projects has active-only (for dispatch
        # and the FQCN index). Shadowing is already applied to `all_discovered`
        # at the top level of _discover_aggregator.
        self.all_projects = all_discovered
        self.projects = [p for p in all_discovered if p.get("_kit_active", True)]
        self.all_virtual_kits = all_virtual_kits

        # Make cross-aggregator virtual kits visible to `dz kit list` and
        # `dz kit status`. Root-level virtuals are already in `self.kits`
        # (populated at depth==0 in _discover_aggregator). Nested virtuals
        # arrive here in all_virtual_kits with their names already
        # prefixed by _rewrite_virtual_kit; append them so the display
        # path sees every virtual kit regardless of where it was declared.
        root_kit_names = {
            k.get("_kit_name") or k.get("name") for k in self.kits
        }
        for vk in all_virtual_kits:
            vk_name = vk.get("_kit_name") or vk.get("name")
            if vk_name and vk_name not in root_kit_names:
                self.kits.append(vk)
                if vk.get("_kit_active", True):
                    self.active_kits.append(vk)
                root_kit_names.add(vk_name)

        self._build_fqcn_index()
        # Second pass: install alias FQCNs from virtual kits. Runs AFTER
        # canonical index is complete so aliases can validate their
        # targets (rule 9b requires canonical_index to be populated first).
        self._apply_virtual_kits(all_virtual_kits)
        self._maybe_emit_reroot_hint()
        self._maybe_emit_stale_favorites_warning()

    def _maybe_emit_stale_favorites_warning(self):
        """Scan favorites for references to FQCNs no longer in the index.

        A favorite entry ``short -> fqcn`` is stale when ``fqcn`` is
        neither a canonical FQCN nor an alias FQCN in the current
        resolution set. Common causes: a kit was disabled, a tool was
        removed, or a virtual kit that provided the alias is gone.

        Emits ONE grouped stderr warning (not N individual ones) and
        respects ``silenced_hints``. Manual remediation via
        ``dz kit favorite --remove <short>`` or re-pointing the favorite
        to a live FQCN.
        """
        if not self.is_root:
            return
        favorites = self._get_config_dict("favorites")
        if not favorites:
            return

        idx = self.fqcn_index
        stale = []
        for short, fqcn in favorites.items():
            if not isinstance(fqcn, str) or not fqcn:
                continue
            if fqcn in idx.canonical_index or fqcn in idx.alias_index:
                continue
            stale.append((short, fqcn))

        if not stale:
            return

        # Respect silenced_hints: a stale favorite whose target kit is
        # silenced should not trigger a warning.
        silenced = self._get_config_dict("silenced_hints", default={}) or {}
        silenced_tool_set = set(silenced.get("tools", []) or [])
        silenced_kit_set = set(silenced.get("kits", []) or [])

        reportable = []
        for short, fqcn in stale:
            if fqcn in silenced_tool_set:
                continue
            kit_prefix = fqcn.split(":", 1)[0]
            if kit_prefix in silenced_kit_set:
                continue
            reportable.append((short, fqcn))

        if not reportable:
            return
        if os.environ.get("DZ_QUIET"):
            return

        count = len(reportable)
        details = ", ".join(f"'{s}' -> '{f}'" for s, f in reportable[:3])
        more = f" (+{count - 3} more)" if count > 3 else ""
        print(
            f"dz: warning: {count} stale favorite(s) detected: {details}{more}. "
            f"These point to FQCNs not in the current index (virtual kit "
            f"removed, tool deleted, or kit disabled). Run "
            f"'dz kit favorite list' to inspect; remove stale entries "
            f"with 'dz kit favorite --remove <short>' or re-point them "
            f"via 'dz kit favorite <short> <new-fqcn>'.",
            file=sys.stderr,
        )

    def _discover_aggregator(self, project_root, loading_stack, depth, kit_prefix):
        """Recursively discover kits, tools, and virtual-kit manifests.

        Args:
            project_root: Absolute path to the aggregator root being scanned.
            loading_stack: Frozenset of ``os.path.realpath()`` values for
                           aggregators currently being loaded. Used for
                           cycle detection.
            depth: Current recursion depth (0 at top level).
            kit_prefix: Accumulated FQCN prefix, or ``None`` at top level.
                        For wtf imported into dazzlecmd, this is ``"wtf"``.
                        For a hypothetical third level, ``"wtf:subkit"``.

        Returns:
            ``(projects, virtual_kit_manifests)`` tuple. ``projects`` are
            annotated project dicts (each with ``_fqcn``, ``_short_name``,
            ``_kit_import_name``, ``_kit_active``). ``virtual_kit_manifests``
            are virtual kits (``"virtual": true``) with their ``name``,
            ``tools``, and ``name_rewrite`` fields rewritten to the root
            FQCN namespace via ``_rewrite_virtual_kit``. The root engine
            applies them to the FQCN index after canonical discovery
            completes.

        Raises:
            CircularDependencyError: if ``project_root`` is already in
                                     ``loading_stack``.
        """
        real_root = os.path.realpath(project_root)
        if real_root in loading_stack:
            stack_display = " -> ".join(sorted(loading_stack)) + f" -> {real_root}"
            raise CircularDependencyError(
                f"Circular aggregator import detected: {stack_display}"
            )

        new_stack = loading_stack | {real_root}

        kits_path = os.path.join(project_root, self.kits_dir)
        tools_path = os.path.join(project_root, self.tools_dir)

        kits = discover_kits(kits_path, tools_path)
        # At the top level, compute which kits are active so we can tag
        # projects with _kit_active. We discover ALL kits (not just active)
        # so that display commands like `dz tree --show-disabled` can show
        # disabled kits with their full tool trees.
        user_config = self._get_user_config() if (depth == 0 and self.is_root) else None
        active_kits = get_active_kits(kits, user_config=user_config)
        active_kit_names = {
            k.get("_kit_name") or k.get("name") for k in active_kits
        }

        # Expose discovered kits at the top level (for meta-commands like
        # `dz kit list` and `dz kit status`)
        if depth == 0:
            self.kits = kits
            self.active_kits = active_kits

        # Partition ALL kits (not just active) into flat, nested, and
        # virtual. Virtual kits have no on-disk tools -- they're overlay
        # manifests processed in a second pass by _apply_virtual_kits
        # after the canonical FQCN index is built.
        flat_kits = []
        nested = []  # list of (kit_dict, candidate_root_dir)
        local_virtual_kits = []
        for kit in kits:
            if kit.get("virtual") is True:
                local_virtual_kits.append(kit)
                continue
            kit_name = kit.get("_kit_name") or kit.get("name")
            candidate_root = os.path.join(tools_path, kit_name)
            if os.path.isdir(os.path.join(candidate_root, "kits")):
                nested.append((kit, candidate_root))
            else:
                flat_kits.append(kit)

        # Flat discovery for non-aggregator kits. Pass self.manifest so
        # child engines with custom manifest names (e.g., .wtf.json) work.
        projects = discover_projects(
            tools_path, flat_kits, default_manifest=self.manifest
        )

        # Annotate flat projects with FQCN metadata and active status
        for project in projects:
            self._annotate_project_fqcn(project, kit_prefix)
            kit = project.get("_kit_import_name", "")
            project["_kit_active"] = kit in active_kit_names

        # Rewrite local virtual kits into the root FQCN namespace (adds
        # kit_prefix to their own name, to each target in `tools`, and to
        # each key in `name_rewrite`). At depth 0, this is a no-op copy.
        # At nested levels, rewriting isolates the virtual kit under the
        # parent aggregator's namespace — e.g., wtf-windows's `claude`
        # virtual kit becomes `wtf:claude` from the root's perspective,
        # aliasing `wtf:core:locked` (not `core:locked`).
        collected_virtuals = []
        for vk in local_virtual_kits:
            vk_name = vk.get("_kit_name") or vk.get("name")
            rewritten = self._rewrite_virtual_kit(vk, kit_prefix)
            rewritten["_kit_active"] = vk_name in active_kit_names
            collected_virtuals.append(rewritten)

        # Recursive discovery for nested aggregators. Each nested call
        # returns both projects and virtual-kit manifests; we collect
        # both and tag them with the parent's view of active status.
        for kit, nested_root in nested:
            kit_name = kit.get("_kit_name") or kit.get("name")
            try:
                nested_projects, nested_virtuals = self._recurse_into_nested(
                    kit, nested_root, new_stack, depth, kit_prefix
                )
                kit_is_active = kit_name in active_kit_names
                for p in nested_projects:
                    p["_kit_active"] = kit_is_active
                projects.extend(nested_projects)
                # A nested virtual kit is active only if its containing
                # aggregator is active at the parent's level. This
                # overrides whatever the child determined; the parent's
                # view of kit activation is authoritative.
                for vk in nested_virtuals:
                    vk["_kit_active"] = kit_is_active and vk.get("_kit_active", True)
                collected_virtuals.extend(nested_virtuals)
            except CircularDependencyError:
                # Propagate cycle errors — these are unrecoverable
                raise
            except Exception as exc:
                kit_name = kit.get("_kit_name") or kit.get("name", "?")
                print(
                    f"Warning: failed to discover nested aggregator "
                    f"'{kit_name}' at {nested_root}: {exc}",
                    file=sys.stderr,
                )

        # Shadowing: at the top level, filter out projects whose FQCN is
        # listed in the user's shadowed_tools config. This removes them from
        # engine.projects before the FQCN index is built, so they don't
        # appear in dz list, aren't dispatchable, and their short names are
        # freed for other tools with the same short name.
        #
        # Applied only at depth == 0 so the user's shadow list is consulted
        # once for the entire aggregator tree.
        if depth == 0:
            shadowed = self._get_config_list("shadowed_tools", default=[]) or []
            if shadowed:
                shadowed_set = set(shadowed)
                projects = [
                    p for p in projects
                    if p.get("_fqcn", "") not in shadowed_set
                ]

        return projects, collected_virtuals

    def _recurse_into_nested(self, kit, nested_root, loading_stack, depth, kit_prefix):
        """Instantiate a child AggregatorEngine and recurse into it.

        Extracts ``tools_dir`` and ``manifest`` overrides from the parent's
        registry pointer (``_override_tools_dir``, ``_override_manifest``)
        or falls back to the child kit's own declaration or defaults.

        Returns the child's ``(projects, virtual_kit_manifests)`` tuple
        unchanged — the parent handles active-status tagging. The child's
        virtual kits are already rewritten with ``nested_prefix`` because
        the child's own ``_discover_aggregator`` calls ``_rewrite_virtual_kit``
        during its partition pass.
        """
        kit_name = kit.get("_kit_name") or kit.get("name")

        # Determine the child's tools_dir and manifest. Order of preference:
        #   1. Parent's registry pointer override (_override_tools_dir)
        #   2. Child kit manifest's tools_dir field
        #   3. Child kit manifest's manifest field
        #   4. Defaults (projects/, .dazzlecmd.json)
        child_tools_dir = (
            kit.get("_override_tools_dir")
            or kit.get("tools_dir")
            or "projects"
        )
        child_manifest = (
            kit.get("_override_manifest")
            or kit.get("manifest")
            or ".dazzlecmd.json"
        )

        # Normalize absolute tools_dir to a relative name (child treats it
        # as relative to its own project_root). This happens when
        # discover_kits has already resolved tools_dir via _load_in_repo_kit_manifest.
        if os.path.isabs(str(child_tools_dir)):
            child_tools_dir = os.path.basename(
                str(child_tools_dir).rstrip("/\\")
            )

        # Instantiate child engine as a non-root aggregator
        child = AggregatorEngine(
            name=kit_name,
            command=kit_name,
            tools_dir=str(child_tools_dir),
            kits_dir="kits",  # convention
            manifest=str(child_manifest),
            is_root=False,
        )

        # Accumulate the FQCN prefix
        nested_prefix = f"{kit_prefix}:{kit_name}" if kit_prefix else kit_name

        return child._discover_aggregator(
            nested_root, loading_stack, depth + 1, nested_prefix
        )

    def _rewrite_virtual_kit(self, vk, kit_prefix):
        """Rewrite a virtual-kit manifest into the root FQCN namespace.

        Cross-aggregator Option A: when a virtual kit lives inside a
        nested aggregator (``kit_prefix`` is non-empty), prefix its own
        ``name``, its ``tools`` list entries, and its ``name_rewrite`` map
        keys with ``kit_prefix``. At the top level (``kit_prefix is None``),
        this is a no-op shallow copy.

        Example: wtf-windows ships ``virtual-claude.kit.json`` with
        ``name: "claude"``, ``tools: ["core:locked"]``,
        ``name_rewrite: {"core:locked": "why-locked"}``. When wtf is
        embedded in dazzlecmd, this rewrite produces
        ``name: "wtf:claude"``, ``tools: ["wtf:core:locked"]``,
        ``name_rewrite: {"wtf:core:locked": "why-locked"}``. The eventual
        alias FQCN becomes ``wtf:claude:why-locked`` — namespaced under
        wtf, unambiguous from root's perspective, and unable to collide
        with dazzlecmd's own root-level virtual kits.

        Returns a new dict; does not mutate ``vk``.
        """
        rewritten = dict(vk)
        if not kit_prefix:
            return rewritten

        prefix = f"{kit_prefix}:"
        original_name = vk.get("_kit_name") or vk.get("name") or ""
        rewritten["name"] = f"{prefix}{original_name}"
        rewritten["_kit_name"] = rewritten["name"]
        rewritten["_original_name"] = original_name

        rewritten["tools"] = [
            f"{prefix}{t}" for t in (vk.get("tools") or [])
        ]
        rewritten["name_rewrite"] = {
            f"{prefix}{k}": v for k, v in (vk.get("name_rewrite") or {}).items()
        }
        return rewritten

    def _apply_virtual_kits(self, virtual_kits):
        """Install alias FQCNs from each active virtual-kit manifest.

        Runs once at the root level, AFTER ``_build_fqcn_index`` has
        populated ``canonical_index``. Alias targets must exist in
        ``canonical_index`` (single-hop rule); ``insert_alias`` rejects
        dangling pointers with ``KeyError``.

        Manifest fields consulted:

        - ``tools`` — list of canonical FQCNs the virtual kit overlays
        - ``name_rewrite`` — optional ``{canonical_fqcn: alias_short}``
          map. Missing entries default to the canonical FQCN's last
          segment (the tool's short name).

        Rule 9a (warning, not error): if a virtual kit's name matches a
        canonical kit's name, emit a stderr warning. The migration use
        case (replace canonical ``claude`` kit with virtual ``claude``
        overlay over time) is legitimate — rule 9b still catches
        per-alias shadowing attempts.
        """
        if not virtual_kits:
            return

        canonical_kit_names = set(self.fqcn_index.kit_order)

        for vk in virtual_kits:
            if not vk.get("_kit_active", True):
                continue

            vk_name = vk.get("_kit_name") or vk.get("name")
            if not vk_name:
                continue

            if vk_name in canonical_kit_names:
                original = vk.get("_original_name") or vk_name
                print(
                    f"Warning: virtual kit '{vk_name}' shares its name "
                    f"with a canonical kit. Rule 9b still catches "
                    f"per-alias shadowing attempts; if this is "
                    f"intentional (e.g., migrating a canonical kit to a "
                    f"virtual overlay), you can ignore this warning. "
                    f"(Original manifest name: '{original}'.)",
                    file=sys.stderr,
                )

            tools = vk.get("tools") or []
            rewrites = vk.get("name_rewrite") or {}
            source = vk.get("_source")

            for canonical_fqcn in tools:
                short = rewrites.get(canonical_fqcn)
                if not short:
                    short = canonical_fqcn.rsplit(":", 1)[-1]
                alias_fqcn = f"{vk_name}:{short}"

                try:
                    self.fqcn_index.insert_alias(
                        alias_fqcn, canonical_fqcn, source=source
                    )
                except (FQCNCollisionError, KeyError) as exc:
                    print(
                        f"Warning: virtual kit '{vk_name}': {exc}",
                        file=sys.stderr,
                    )

    def _annotate_project_fqcn(self, project, kit_prefix):
        """Set ``_fqcn``, ``_short_name``, ``_kit_import_name`` on a project.

        ``kit_prefix`` is the accumulated parent FQCN path, or ``None`` at
        the top level.
        """
        namespace = project.get("namespace", "")
        short = project["name"]
        local = f"{namespace}:{short}" if namespace else short

        if kit_prefix:
            fqcn = f"{kit_prefix}:{local}"
            import_kit = kit_prefix.split(":", 1)[0]
        else:
            fqcn = local
            import_kit = namespace or short

        project["_fqcn"] = fqcn
        project["_short_name"] = short
        project["_kit_import_name"] = import_kit

    def _build_fqcn_index(self):
        """Populate ``self.fqcn_index`` from ``self.projects``.

        Inserts canonical projects only. Virtual-kit aliases are applied
        in a second pass by ``_apply_virtual_kits`` (Commit 2 — Phase 4e).

        Assumes projects are already annotated with ``_fqcn``, ``_short_name``,
        and ``_kit_import_name`` by ``_discover_aggregator``.
        """
        self.fqcn_index = FQCNIndex()
        for project in self.projects:
            # Safety net: annotate if discovery path didn't (unit tests etc.)
            if "_fqcn" not in project:
                self._annotate_project_fqcn(project, kit_prefix=None)
            try:
                self.fqcn_index.insert_canonical(project)
            except FQCNCollisionError as exc:
                print(f"Warning: {exc}", file=sys.stderr)

    def _maybe_emit_reroot_hint(self):
        """Hint at rerooting when discovery surfaces deeply-nested tools.

        Nesting is unlimited, but tools that live many segments deep in the
        FQCN tree are awkward to type. If such a tool sees frequent use, the
        user may prefer to *reroot* it -- extract that subtree as a standalone
        aggregator (e.g., publish to PyPI) so users can invoke it directly
        without typing the full path.

        Example: ``dz safedel`` is currently inside dazzlecmd's core kit.
        When safedel is published as its own PyPI package, users will type
        ``safedel`` directly, while ``dz safedel`` continues to work because
        dazzlecmd imports the safedel kit. Both paths coexist; the user
        chooses primacy based on usage.

        The hint fires once per top-level discovery, only when at least one
        non-silenced tool's FQCN has 3+ colons (4+ segments). Silenceable
        globally via ``DZ_QUIET=1``, or per-tool/per-kit via the config keys
        ``silenced_hints.tools`` and ``silenced_hints.kits``.
        """
        if not self.is_root:
            return
        if not self.projects:
            return
        if os.environ.get("DZ_QUIET"):
            return

        # Consult silenced_hints to filter out tools the user has acknowledged.
        # A tool is silenced if its FQCN is in silenced_hints.tools OR its
        # top-level kit (_kit_import_name) is in silenced_hints.kits.
        silenced = self._get_config_dict("silenced_hints", default={})
        silenced_tool_set = set(silenced.get("tools", []) or [])
        silenced_kit_set = set(silenced.get("kits", []) or [])

        candidates = [
            p for p in self.projects
            if p.get("_fqcn", "") not in silenced_tool_set
            and p.get("_kit_import_name", "") not in silenced_kit_set
        ]
        if not candidates:
            return

        max_colons = max(p.get("_fqcn", "").count(":") for p in candidates)
        if max_colons < 3:
            return

        deepest = max(
            candidates, key=lambda p: p.get("_fqcn", "").count(":")
        )
        fqcn = deepest["_fqcn"]
        segments = max_colons + 1
        print(
            f"dz: hint: deeply nested tool '{fqcn}' ({segments} segments). "
            f"If used often, consider rerooting -- extract this subtree as a "
            f"standalone install so it can be invoked directly. Set DZ_QUIET=1 "
            f"or 'dz kit silence {fqcn}' to silence.",
            file=sys.stderr,
        )

    # ----------------------------------------------------------------
    # User config read/write path
    # ----------------------------------------------------------------
    #
    # Config file: ~/.dazzlecmd/config.json
    #
    # Schema (Phase 3):
    #     {
    #         "_schema_version": 1,
    #         "kit_precedence": [...],
    #         "active_kits": [...],
    #         "disabled_kits": [...],
    #         "favorites": {"short": "fqcn", ...},
    #         "silenced_hints": {"tools": [...], "kits": [...]},
    #         "shadowed_tools": [...],
    #         "kit_discovery": "auto"
    #     }
    #
    # All keys are optional. Missing keys fall back to sensible defaults.
    # Malformed entries (wrong type, bad JSON) are tolerated with a stderr
    # warning and the malformed key is treated as absent.

    def _config_path(self):
        """Return the active config file path (delegates to ConfigManager)."""
        return self.config.config_path()

    def _config_dir(self):
        """Return the directory containing the active config file."""
        return self.config.config_dir()

    def _get_user_config(self):
        """Return the parsed config as a dict (delegates to ConfigManager)."""
        return self.config.read()

    def _get_config_list(self, key, default=None):
        """Return a list-valued config key, validated."""
        return self.config.get_list(key, default)

    def _get_config_dict(self, key, default=None):
        """Return a dict-valued config key, validated."""
        return self.config.get_dict(key, default)

    def _write_user_config(self, updates):
        """Merge ``updates`` into the config and write atomically (delegates to ConfigManager)."""
        self.config.write(updates)
        self._precedence_cache = None

    def get_kit_precedence(self):
        """Return the user's ``kit_precedence`` list from config, or None.

        Thin backwards-compat wrapper over ``_get_config_list("kit_precedence")``.
        Kept for callers that exist from Phase 2 (v0.7.9).
        """
        return self._get_config_list("kit_precedence")

    def resolve_command(self, name):
        """Resolve a command name to a ``(project, ResolutionContext)`` tuple.

        Thin wrapper over ``FQCNIndex.resolve()`` that supplies user
        configuration (``favorites`` and ``kit_precedence``) from the
        engine's ConfigManager.

        Returns ``(None, None)`` if no project matches.
        """
        favorites = self._get_config_dict("favorites")
        precedence = self.get_kit_precedence()
        return self.fqcn_index.resolve(
            name, precedence=precedence, favorites=favorites
        )

    def find_project(self, name):
        """Alias-aware canonical lookup for a user-typed name.

        Primary entry point for callers that need to resolve a tool name
        (short name, canonical FQCN, alias FQCN, or kit-qualified
        shortcut) to a concrete project. Use this in place of raw
        ``[p for p in projects if p.get("_fqcn") == name]`` comparisons
        -- those patterns are alias-blind and silently fail on virtual-
        kit aliases.

        Equivalent to ``resolve_command(name)`` today. Kept as a distinct
        method name so intent reads clearly at call sites ("I want a
        project by name") and to give us room to specialise later if
        engine-level concerns (e.g., permission checks) need to layer in.

        Returns ``(project, context)`` on success, ``(None, None)``
        on miss.
        """
        return self.resolve_command(name)

    def run(self, argv=None):
        """Run the aggregator: discover, parse, dispatch.

        This is the main entry point for the CLI. Two dispatch paths:

        1. **Registry path** (default): when ``parser_builder`` is None,
           the engine builds the parser from ``meta_registry`` + tool
           subparsers and dispatches meta-commands via the registry's
           own ``dispatch()``. Tool dispatch uses ``tool_dispatcher`` if
           provided, else the library default (``RunnerRegistry.resolve``).

        2. **Escape-hatch path**: when ``parser_builder`` is provided,
           the engine delegates parser construction and meta-dispatch to
           the provided callbacks. Used by aggregators with non-argparse
           CLIs or custom parser structure. Backward-compat with
           aggregators that predate the registry.
        """
        if argv is None:
            argv = sys.argv[1:]

        self.discover()

        # Choose dispatch path based on whether an explicit parser_builder
        # was passed at construction.
        if self._build_parser is not None:
            return self._run_escape_hatch(argv)
        return self._run_registry(argv)

    def _run_registry(self, argv):
        """Registry-driven run path (primary).

        Builds the parser from the meta_registry + tool subparsers,
        locks the registry, and dispatches meta-commands via the
        registry or tool commands via FQCN resolution.
        """
        import argparse as _argparse
        from dazzlecmd_lib import cli_helpers as _ch

        # Handle --version / -V before any parsing (matches the
        # behavior of the escape-hatch path).
        if argv and argv[0] in ("--version", "-V"):
            if self.version_info:
                display, full = self.version_info
                print(f"{self.name} {display} ({full})")
            else:
                print(self.name)
            return 0

        # Build root parser
        epilog = None
        if self.epilog_builder is not None:
            try:
                epilog = self.epilog_builder(self.projects)
            except Exception as exc:
                print(
                    f"Warning: epilog_builder raised {exc!r}; using default",
                    file=sys.stderr,
                )

        parser = _argparse.ArgumentParser(
            prog=self.command,
            description=self.description,
            epilog=epilog,
            formatter_class=_argparse.RawDescriptionHelpFormatter,
        )
        _ch.add_version_flag(parser, self.version_info, app_name=self.name)

        subparsers = parser.add_subparsers(
            dest="command", metavar="<command>", help=_argparse.SUPPRESS
        )

        # Register meta-command subparsers from the registry
        if self.is_root:
            self.meta_registry.build_parsers(subparsers)

        # Register one subparser per discovered tool (reserved-filtered)
        reserved = self.reserved_commands
        _ch.build_tool_subparsers(subparsers, self.projects, reserved)

        # Lock the registry: dispatch has begun, no more registrations.
        self.meta_registry.lock()
        try:
            return self._dispatch_registry_path(parser, argv, reserved)
        finally:
            # Unlock so the registry can be reused for another run()
            # (test scenarios; normally only one run per engine).
            self.meta_registry.unlock()

    def _dispatch_registry_path(self, parser, argv, reserved):
        if not argv:
            parser.print_help()
            return 0

        command_name = argv[0]

        # Meta-command path (only if is_root)
        if self.is_root and (
            command_name in reserved or command_name.startswith("-")
        ):
            sys_argv_backup = sys.argv
            sys.argv = [self.command] + list(argv)
            try:
                args = parser.parse_args()
                if hasattr(args, "_meta"):
                    return self.meta_registry.dispatch(
                        args, self, self.projects, self.kits, self.project_root
                    )
            finally:
                sys.argv = sys_argv_backup
            return 0

        # Tool dispatch
        project, context = self.resolve_command(command_name)
        if project is not None:
            if context is not None and context.notification and not os.environ.get("DZ_QUIET"):
                print(context.notification, file=sys.stderr)
            tool_argv = argv[1:]
            return self._run_tool(project, tool_argv, context=context)

        # Unknown command — let argparse produce its standard error
        sys_argv_backup = sys.argv
        sys.argv = [self.command] + list(argv)
        try:
            parser.parse_args()
        finally:
            sys.argv = sys_argv_backup
        return 1

    def _run_tool(self, project, argv, context=None):
        """Dispatch a tool via tool_dispatcher or library default.

        If a ``tool_dispatcher`` callback was set, use it. Otherwise, use
        the library's default via ``RunnerRegistry.resolve(project)``.

        When a ``ResolutionContext`` is provided (Phase 4e Commit 4),
        injects ``DZ_CANONICAL_FQCN`` and ``DZ_INVOKED_FQCN`` into
        ``os.environ`` for the duration of the call. Tools that write
        persistent state (caches, logs, checkpoints) MUST key on
        ``DZ_CANONICAL_FQCN`` to avoid divergent state across invocation
        paths (alias vs canonical vs short name all converge on the
        same canonical tool).
        """
        env_backup = {}
        try:
            if context is not None:
                # Preserve prior values so nested dispatches don't stomp
                # each other. In practice dz only runs one tool per
                # invocation so this is belt-and-suspenders.
                env_backup["DZ_CANONICAL_FQCN"] = os.environ.get("DZ_CANONICAL_FQCN")
                env_backup["DZ_INVOKED_FQCN"] = os.environ.get("DZ_INVOKED_FQCN")
                os.environ["DZ_CANONICAL_FQCN"] = context.canonical_fqcn or ""
                os.environ["DZ_INVOKED_FQCN"] = context.original_input or context.canonical_fqcn or ""

            if self._dispatch_tool is not None:
                return self._dispatch_tool(project, argv)
            # Library default: RunnerRegistry-based dispatch.
            runner = RunnerRegistry.resolve(project)
            if runner is None:
                print(
                    f"Error: could not resolve runtime for {project.get('name', '?')}",
                    file=sys.stderr,
                )
                return 1
            try:
                return runner(argv)
            except KeyboardInterrupt:
                return 130
            except Exception as exc:
                print(
                    f"Error running {project.get('name', '?')}: {exc}",
                    file=sys.stderr,
                )
                return 1
        finally:
            # Restore env vars to their prior state so dz's own process
            # environment isn't permanently modified by a tool dispatch.
            if context is not None:
                for key, value in env_backup.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def _run_escape_hatch(self, argv):
        """Escape-hatch run path: delegate parser + meta dispatch to callbacks.

        Backward-compat with aggregators that predate the registry
        (dazzlecmd's own cli.py today).
        """
        build_parser = self._build_parser
        dispatch_meta = self._dispatch_meta
        dispatch_tool = self._dispatch_tool

        if dispatch_tool is None:
            print(
                f"Error: {self.name} engine was configured with parser_builder "
                f"but no tool_dispatcher. Both callbacks are required on the "
                f"escape-hatch path.",
                file=sys.stderr,
            )
            return 1

        if self.project_root is None:
            parser = build_parser(
                self.projects if self.projects else [], engine=self
            )
            if argv and argv[0] in ("--version", "-V") and self.version_info:
                display, full = self.version_info
                print(f"{self.name} {display} ({full})")
                return 0
            parser.print_help()
            return 0

        parser = build_parser(self.projects, engine=self)

        if not argv:
            parser.print_help()
            return 0

        command_name = argv[0]

        if self.is_root:
            meta_commands = self._meta_commands or {
                "list", "info", "kit", "new", "version", "add", "mode",
                "tree", "setup",
            }
            if command_name in meta_commands or command_name.startswith("-"):
                sys_argv_backup = sys.argv
                sys.argv = [self.command] + list(argv)
                try:
                    args = parser.parse_args()
                    if hasattr(args, "_meta") and dispatch_meta is not None:
                        return dispatch_meta(
                            args, self.projects, self.kits, self.project_root,
                            engine=self,
                        )
                finally:
                    sys.argv = sys_argv_backup
                return 0

        project, context = self.resolve_command(command_name)

        if project is not None:
            if context is not None and context.notification and not os.environ.get("DZ_QUIET"):
                print(context.notification, file=sys.stderr)

            tool_argv = argv[1:]
            # Inject DZ_CANONICAL_FQCN + DZ_INVOKED_FQCN env vars (v0.7.28).
            # Tools writing persistent state (caches, logs, checkpoints)
            # MUST key on DZ_CANONICAL_FQCN to avoid divergent state
            # across invocation paths.
            env_backup = {}
            if context is not None:
                env_backup["DZ_CANONICAL_FQCN"] = os.environ.get("DZ_CANONICAL_FQCN")
                env_backup["DZ_INVOKED_FQCN"] = os.environ.get("DZ_INVOKED_FQCN")
                os.environ["DZ_CANONICAL_FQCN"] = context.canonical_fqcn or ""
                os.environ["DZ_INVOKED_FQCN"] = context.original_input or context.canonical_fqcn or ""
            try:
                return dispatch_tool(project, tool_argv)
            finally:
                if context is not None:
                    for key, value in env_backup.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value

        sys_argv_backup = sys.argv
        sys.argv = [self.command] + list(argv)
        try:
            parser.parse_args()
        finally:
            sys.argv = sys_argv_backup
        return 1

    @property
    def reserved_commands(self):
        """Commands reserved from use as tool names.

        Returns the union of:
        - ``meta_registry.registered()`` — all currently-registered meta
          commands (auto-updates as aggregators register/unregister)
        - ``extra_reserved_commands`` passed at construction time

        Returns an empty set when ``is_root=False`` (embedded mode, no
        meta-commands should conflict with kit's tool names).

        Aggregators using the escape-hatch path (``parser_builder=``) may
        manage their own reserved set independently of this property.
        """
        if not self.is_root:
            return set()
        return set(self.meta_registry.registered()) | self._extra_reserved
