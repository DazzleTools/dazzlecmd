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


class FQCNCollisionError(Exception):
    """Raised when two projects declare the same FQCN during index build."""


class CircularDependencyError(Exception):
    """Raised when recursive aggregator discovery encounters a cycle."""


class FQCNIndex:
    """Dual-index lookup for Fully Qualified Collection Names.

    Maintains:
        - canonical_index: {fqcn: project} for real, on-disk tools
        - alias_index: {alias_fqcn: canonical_fqcn} for virtual-kit overlays
        - fqcn_index: alias of canonical_index (backward-compat for callers)
        - short_index: {short_name: [canonical_fqcn, ...]} for short-name
                       resolution. Only canonical FQCNs populate this -- aliases
                       don't re-enter short-name competition (that's the whole
                       point of a virtual kit: prettier FQCN without creating
                       a new short name).
        - kit_order: ordered list of top-level kit names (discovery order)

    FQCN format: ``kit[:subkit...]:tool`` — e.g., ``core:rn``,
    ``wtf:core:restarted``. The top-level kit is the first segment.

    **Experimental (v0.7.25 virtual-kits skeleton)**: separate canonical and
    alias stores with §9b collision detection. Aliases created by virtual kits
    (``{"virtual": true}`` manifests) resolve through the alias_index back to
    a canonical project. §9b rule: an alias FQCN MUST NOT equal any canonical
    FQCN -- that would let a virtual kit shadow a real tool.
    """

    def __init__(self):
        self.canonical_index = {}
        self.alias_index = {}
        # Backward-compat view: callers (tests, meta-commands) reach into
        # engine.fqcn_index.fqcn_index expecting {fqcn: project}. Point it
        # at the canonical store so the existing behavior is preserved.
        self.fqcn_index = self.canonical_index
        self.short_index = {}
        self.kit_order = []

    def insert(self, project):
        """Insert a canonical project into the index.

        Backward-compat: delegates to ``insert_canonical``. Prefer the new
        name in new code -- it makes the canonical/alias distinction explicit.
        """
        return self.insert_canonical(project)

    def insert_canonical(self, project):
        """Insert a canonical project into the index.

        The project dict must carry ``_fqcn``, ``_short_name``, and
        ``_kit_import_name`` fields (set by the engine during discovery).

        Raises:
            FQCNCollisionError: if a project with the same FQCN already
            exists as either canonical or alias.
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
        # §9b mirror: a new canonical FQCN must not collide with an existing
        # alias. In practice canonicals are inserted first, so this path is
        # rare, but it closes the loop symmetrically.
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

    def insert_alias(self, alias_fqcn, canonical_fqcn, source=None):
        """Register ``alias_fqcn`` as a pointer to ``canonical_fqcn``.

        Args:
            alias_fqcn: The new FQCN the user can type (e.g., "claude:cleanup").
            canonical_fqcn: The existing canonical FQCN it resolves to
                (e.g., "dazzletools:claude-cleanup"). MUST already be in
                the canonical_index.
            source: Optional path to the virtual-kit manifest that declared
                this alias (for diagnostics).

        Raises:
            FQCNCollisionError: if ``alias_fqcn`` already exists as a
                canonical FQCN (§9b: alias cannot shadow a real tool) or
                as a different alias.
            KeyError: if ``canonical_fqcn`` is not in the canonical_index.
        """
        if canonical_fqcn not in self.canonical_index:
            raise KeyError(
                f"Virtual kit alias '{alias_fqcn}' -> '{canonical_fqcn}': "
                f"target FQCN not found in canonical index. Check the "
                f"'tools' list in the virtual kit manifest"
                + (f" ({source})" if source else "")
                + "."
            )

        # §9b: alias MUST NOT match an existing canonical FQCN.
        # This prevents a virtual kit from silently shadowing a real tool.
        if alias_fqcn in self.canonical_index:
            raise FQCNCollisionError(
                f"Virtual kit alias '{alias_fqcn}' collides with a real "
                f"canonical FQCN. A virtual kit cannot shadow a real tool "
                f"(rule 9b). "
                + (f"(declared in {source}) " if source else "")
                + "Rename the alias or remove the virtual-kit entry."
            )

        # Different-target collision: two virtual kits both trying to
        # claim the same alias. Allowed only if they point to the same
        # canonical target (idempotent).
        if alias_fqcn in self.alias_index:
            existing_target = self.alias_index[alias_fqcn]
            if existing_target != canonical_fqcn:
                raise FQCNCollisionError(
                    f"Virtual kit alias '{alias_fqcn}' already maps to "
                    f"'{existing_target}'; cannot remap to "
                    f"'{canonical_fqcn}'. "
                    + (f"(conflicting declaration in {source})" if source else "")
                )
            return  # idempotent no-op

        self.alias_index[alias_fqcn] = canonical_fqcn

    def resolve(self, name, precedence=None, favorites=None):
        """Resolve a command name to a (project, notification) tuple.

        Args:
            name: The user-typed command name. May be an FQCN (contains ``:``)
                  or a short name.
            precedence: Optional ordered list of kit names that overrides the
                        default precedence order for short-name resolution.
            favorites: Optional dict of ``{short_name: fqcn}`` mapping. If a
                       short name is in favorites, the favorite's FQCN is
                       looked up directly, bypassing precedence resolution.
                       Stale favorites (FQCN not in index) produce a warning
                       notification and fall through to precedence.

        Returns:
            ``(project, notification)`` on success, where ``notification`` is
            a stderr-ready string if the resolution was ambiguous or stale,
            or ``None`` if unambiguous. Returns ``(None, None)`` if no
            project matches.
        """
        # Exact FQCN match -- always wins, bypasses favorites and precedence
        if ":" in name:
            # 1. Canonical FQCN direct hit
            project = self.canonical_index.get(name)
            if project is not None:
                return project, None

            # 2. Virtual-kit alias hit (experimental v0.7.25 skeleton).
            # Alias resolves to a canonical FQCN, which is then looked up
            # in canonical_index. Invariant: alias targets must exist.
            if name in self.alias_index:
                canonical_fqcn = self.alias_index[name]
                project = self.canonical_index.get(canonical_fqcn)
                if project is not None:
                    return project, None
                # Defensive -- shouldn't happen if insert_alias validated.
                return None, (
                    f"dz: alias '{name}' -> '{canonical_fqcn}' points to "
                    f"a missing canonical entry (index corruption?)."
                )

            # 3. Kit-qualified shortcut: "wtf:locked" means "search within
            # the wtf kit for a tool named locked." This handles the
            # common case where "core" (or any internal namespace) is
            # omitted. Split on the first ":" to get (kit_prefix, tool).
            # Search canonical only -- aliases already got their exact-match
            # chance above, so kit-qualified matching stays on real tools.
            kit_prefix, _, tool_suffix = name.partition(":")
            if tool_suffix and ":" not in tool_suffix:
                # Only applies to 2-segment names (kit:tool), not to
                # malformed 3+ segment names that didn't exact-match.
                matches = [
                    fqcn for fqcn in self.canonical_index
                    if fqcn.startswith(kit_prefix + ":")
                    and fqcn.rsplit(":", 1)[-1] == tool_suffix
                ]
                if len(matches) == 1:
                    return self.canonical_index[matches[0]], None
                if len(matches) > 1:
                    display = ", ".join(matches)
                    notification = (
                        f"dz: '{name}' is ambiguous within kit "
                        f"'{kit_prefix}': {display}. "
                        f"Use the full FQCN to be explicit."
                    )
                    # Pick the first alphabetically (stable)
                    return self.canonical_index[sorted(matches)[0]], notification

            return None, None

        # Short name path
        candidates = self.short_index.get(name, [])

        # Favorite short-circuit: if a favorite is set for this name, use it
        # unconditionally (before checking candidates count). Stale favorites
        # fall through to precedence with a warning.
        if favorites and name in favorites:
            favorite_fqcn = favorites[name]
            # Accept a favorite that points at a canonical FQCN or an alias.
            # Alias -> follow to canonical (same semantics as direct FQCN
            # resolution above: aliases are transparent).
            favorite_project = self.canonical_index.get(favorite_fqcn)
            if favorite_project is None and favorite_fqcn in self.alias_index:
                favorite_project = self.canonical_index.get(
                    self.alias_index[favorite_fqcn]
                )
            if favorite_project is not None:
                return favorite_project, None
            # Stale favorite -- fall through with a warning
            stale_note = (
                f"dz: warning: favorite '{name}' -> '{favorite_fqcn}' "
                f"not found (tool may have been removed, renamed, or "
                f"shadowed). Falling through to precedence."
            )
            if not candidates:
                return None, stale_note
            if len(candidates) == 1:
                return self.fqcn_index[candidates[0]], stale_note
            # Stale + ambiguous: combine the stale note with the resolution note
            order = self._effective_precedence(precedence)
            ranked = self._rank_by_precedence(candidates, order)
            picked_fqcn = ranked[0]
            other_fqcns = ranked[1:]
            project = self.fqcn_index[picked_fqcn]
            others_display = ", ".join(self._kit_of(f) for f in other_fqcns)
            combined = (
                stale_note
                + f"\ndz: '{name}' resolved to {picked_fqcn} "
                f"(also in: {others_display}). "
                f"Use 'dz {picked_fqcn}' to be explicit."
            )
            return project, combined

        if not candidates:
            return None, None

        if len(candidates) == 1:
            return self.fqcn_index[candidates[0]], None

        # Multiple candidates -- apply precedence
        order = self._effective_precedence(precedence)
        ranked = self._rank_by_precedence(candidates, order)

        picked_fqcn = ranked[0]
        other_fqcns = ranked[1:]
        project = self.fqcn_index[picked_fqcn]

        others_display = ", ".join(self._kit_of(f) for f in other_fqcns)
        notification = (
            f"dz: '{name}' resolved to {picked_fqcn} "
            f"(also in: {others_display}). "
            f"Use 'dz {picked_fqcn}' to be explicit."
        )
        return project, notification

    def all_projects(self):
        """Return all projects in insertion order (stable)."""
        return list(self.fqcn_index.values())

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
        ``self.projects``, and ``self.fqcn_index``.

        Each project is annotated with ``_fqcn``, ``_short_name``, and
        ``_kit_import_name`` fields during discovery.
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
        all_discovered = self._discover_aggregator(
            self.project_root, loading_stack, depth=0, kit_prefix=None
        )

        # Partition: all_projects has everything (for display commands like
        # `dz tree --show-disabled`); projects has active-only (for dispatch
        # and the FQCN index). Shadowing is already applied to `all_discovered`
        # at the top level of _discover_aggregator.
        self.all_projects = all_discovered
        self.projects = [p for p in all_discovered if p.get("_kit_active", True)]

        self._build_fqcn_index()
        self._maybe_emit_reroot_hint()

    def _discover_aggregator(self, project_root, loading_stack, depth, kit_prefix):
        """Recursively discover kits and tools in an aggregator tree.

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
            List of annotated project dicts from this level and all nested
            levels. Each project has ``_fqcn``, ``_short_name``, and
            ``_kit_import_name`` set.

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

        # Partition ALL kits (not just active) into flat vs. nested vs. virtual.
        # Virtual kits have no on-disk tools; they are manifest-only overlays
        # that create alias FQCNs after the canonical index is built. Skip
        # them during flat/nested discovery and process them post-hoc.
        flat_kits = []
        nested = []  # list of (kit_dict, candidate_root_dir)
        virtual_kits = []
        for kit in kits:
            kit_name = kit.get("_kit_name") or kit.get("name")
            if kit.get("virtual") is True:
                virtual_kits.append(kit)
                continue
            candidate_root = os.path.join(tools_path, kit_name)
            if os.path.isdir(os.path.join(candidate_root, "kits")):
                nested.append((kit, candidate_root))
            else:
                flat_kits.append(kit)

        # Stash virtual kits for post-canonical alias processing. Only the
        # top-level engine processes them (nested engines don't overlay).
        # Filter to active virtual kits -- an inactive virtual kit shouldn't
        # contribute aliases. (Open question for Round 3: should disabled
        # virtual kits still show aliases in `dz tree --show-disabled`?)
        if depth == 0:
            self._virtual_kits = [
                vk for vk in virtual_kits
                if (vk.get("_kit_name") or vk.get("name")) in active_kit_names
            ]

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

        # Recursive discovery for nested aggregators
        for kit, nested_root in nested:
            kit_name = kit.get("_kit_name") or kit.get("name")
            try:
                nested_projects = self._recurse_into_nested(
                    kit, nested_root, new_stack, depth, kit_prefix
                )
                # Tag nested projects with active status based on the
                # parent's view of whether this kit is active
                kit_is_active = kit_name in active_kit_names
                for p in nested_projects:
                    p["_kit_active"] = kit_is_active
                projects.extend(nested_projects)
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

        return projects

    def _recurse_into_nested(self, kit, nested_root, loading_stack, depth, kit_prefix):
        """Instantiate a child AggregatorEngine and recurse into it.

        Extracts ``tools_dir`` and ``manifest`` overrides from the parent's
        registry pointer (``_override_tools_dir``, ``_override_manifest``)
        or falls back to the child kit's own declaration or defaults.
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

        Assumes projects are already annotated with ``_fqcn``, ``_short_name``,
        and ``_kit_import_name`` by ``_discover_aggregator``.

        After canonical insertion, overlays virtual-kit aliases (from
        ``self._virtual_kits``, set during discovery) on top of the canonical
        index. Virtual-kit collisions are reported but don't abort the build.
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

        # Virtual-kit alias overlay (experimental v0.7.25 skeleton).
        self._apply_virtual_kits(getattr(self, "_virtual_kits", []))

    def _apply_virtual_kits(self, virtual_kits):
        """Insert alias FQCNs from virtual-kit manifests.

        Each virtual kit declares:
            - tools: list of canonical FQCNs to include
            - name_rewrite: optional {canonical_fqcn: alias_short_name} map
                            that rewrites the LAST segment under the virtual
                            kit's namespace.

        Alias FQCN construction:
            alias_fqcn = "<virtual_kit_name>:<alias_short_name>"
        where alias_short_name is taken from name_rewrite or defaults to
        the canonical FQCN's last segment (the tool's short name).
        """
        if not virtual_kits:
            return

        for vkit in virtual_kits:
            vk_name = vkit.get("_kit_name") or vkit.get("name")
            if not vk_name:
                continue
            tools = vkit.get("tools", []) or []
            rewrites = vkit.get("name_rewrite", {}) or {}
            source = vkit.get("_source")

            for canonical_fqcn in tools:
                # Derive alias short name
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
        """Resolve a command name to a (project, notification) tuple.

        Applies user-configured favorites first (if ``name`` is a favorite,
        return the favorite's target), then falls through to
        ``FQCNIndex.resolve()`` with the user's ``kit_precedence``.

        Returns ``(None, None)`` if no project matches.
        """
        favorites = self._get_config_dict("favorites")
        precedence = self.get_kit_precedence()
        return self.fqcn_index.resolve(
            name, precedence=precedence, favorites=favorites
        )

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
        project, notification = self.resolve_command(command_name)
        if project is not None:
            if notification and not os.environ.get("DZ_QUIET"):
                print(notification, file=sys.stderr)
            tool_argv = argv[1:]
            return self._run_tool(project, tool_argv)

        # Unknown command — let argparse produce its standard error
        sys_argv_backup = sys.argv
        sys.argv = [self.command] + list(argv)
        try:
            parser.parse_args()
        finally:
            sys.argv = sys_argv_backup
        return 1

    def _run_tool(self, project, argv):
        """Dispatch a tool via tool_dispatcher or library default.

        If a ``tool_dispatcher`` callback was set, use it. Otherwise, use
        the library's default via ``RunnerRegistry.resolve(project)``.
        """
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

        project, notification = self.resolve_command(command_name)

        if project is not None:
            if notification and not os.environ.get("DZ_QUIET"):
                print(notification, file=sys.stderr)

            tool_argv = argv[1:]
            return dispatch_tool(project, tool_argv)

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
