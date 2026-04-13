"""Generic aggregator engine for dazzlecmd and compatible projects.

The AggregatorEngine is the shared core that powers any tool aggregator.
dazzlecmd, wtf-windows, and future aggregators are all instances of this
engine configured with different data (command name, directory layout,
manifest filename, etc.).

Usage:
    from dazzlecmd.engine import AggregatorEngine

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

from dazzlecmd.loader import (
    discover_kits,
    discover_projects,
    get_active_kits,
    resolve_entry_point,
)


class FQCNCollisionError(Exception):
    """Raised when two projects declare the same FQCN during index build."""


class CircularDependencyError(Exception):
    """Raised when recursive aggregator discovery encounters a cycle."""


class FQCNIndex:
    """Dual-index lookup for Fully Qualified Collection Names.

    Maintains:
        - fqcn_index: {fqcn: project} for exact-match dispatch
        - short_index: {short_name: [fqcn, ...]} for short-name resolution
        - kit_order: ordered list of top-level kit names (discovery order)

    FQCN format: ``kit[:subkit...]:tool`` — e.g., ``core:rn``,
    ``wtf:core:restarted``. The top-level kit is the first segment.
    """

    def __init__(self):
        self.fqcn_index = {}
        self.short_index = {}
        self.kit_order = []

    def insert(self, project):
        """Insert a project into the index.

        The project dict must carry ``_fqcn``, ``_short_name``, and
        ``_kit_import_name`` fields (set by the engine during discovery).

        Raises:
            FQCNCollisionError: if a project with the same FQCN already exists.
        """
        fqcn = project["_fqcn"]
        short = project["_short_name"]
        kit = project["_kit_import_name"]

        if fqcn in self.fqcn_index:
            existing = self.fqcn_index[fqcn]
            raise FQCNCollisionError(
                f"Duplicate FQCN '{fqcn}': "
                f"{existing.get('_dir', '?')} vs {project.get('_dir', '?')}"
            )

        self.fqcn_index[fqcn] = project
        self.short_index.setdefault(short, []).append(fqcn)
        if kit not in self.kit_order:
            self.kit_order.append(kit)

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
            project = self.fqcn_index.get(name)
            if project is not None:
                return project, None

            # Kit-qualified shortcut: "wtf:locked" means "search within
            # the wtf kit for a tool named locked." This handles the
            # common case where "core" (or any internal namespace) is
            # omitted. Split on the first ":" to get (kit_prefix, tool).
            kit_prefix, _, tool_suffix = name.partition(":")
            if tool_suffix and ":" not in tool_suffix:
                # Only applies to 2-segment names (kit:tool), not to
                # malformed 3+ segment names that didn't exact-match.
                matches = [
                    fqcn for fqcn in self.fqcn_index
                    if fqcn.startswith(kit_prefix + ":")
                    and fqcn.rsplit(":", 1)[-1] == tool_suffix
                ]
                if len(matches) == 1:
                    return self.fqcn_index[matches[0]], None
                if len(matches) > 1:
                    display = ", ".join(matches)
                    notification = (
                        f"dz: '{name}' is ambiguous within kit "
                        f"'{kit_prefix}': {display}. "
                        f"Use the full FQCN to be explicit."
                    )
                    # Pick the first alphabetically (stable)
                    return self.fqcn_index[sorted(matches)[0]], notification

            return None, None

        # Short name path
        candidates = self.short_index.get(name, [])

        # Favorite short-circuit: if a favorite is set for this name, use it
        # unconditionally (before checking candidates count). Stale favorites
        # fall through to precedence with a warning.
        if favorites and name in favorites:
            favorite_fqcn = favorites[name]
            favorite_project = self.fqcn_index.get(favorite_fqcn)
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
        """
        self.name = name
        self.command = command
        self.tools_dir = tools_dir
        self.kits_dir = kits_dir
        self.manifest = manifest
        self.description = description or f"{name} - tool aggregator"
        self.version_info = version_info
        self.is_root = is_root

        # Resolved at run time
        self.project_root = None
        self.kits = []
        self.active_kits = []
        self.projects = []
        self.fqcn_index = FQCNIndex()
        self._precedence_cache = None
        self._config_cache = None

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

        # Partition ALL kits (not just active) into flat vs. nested
        flat_kits = []
        nested = []  # list of (kit_dict, candidate_root_dir)
        for kit in kits:
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
        """
        self.fqcn_index = FQCNIndex()
        for project in self.projects:
            # Safety net: annotate if discovery path didn't (unit tests etc.)
            if "_fqcn" not in project:
                self._annotate_project_fqcn(project, kit_prefix=None)
            try:
                self.fqcn_index.insert(project)
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

    _SCHEMA_VERSION = 1

    def _config_path(self):
        """Return the active config file path.

        Computed lazily via ``os.path.expanduser("~/.dazzlecmd/config.json")``
        so that tests that monkey-patch ``HOME`` / ``USERPROFILE`` after
        import see the right path. Overridable entirely via the
        ``DAZZLECMD_CONFIG`` environment variable.
        """
        override = os.environ.get("DAZZLECMD_CONFIG")
        if override:
            return override
        return os.path.expanduser("~/.dazzlecmd/config.json")

    def _config_dir(self):
        """Return the directory containing the active config file."""
        return os.path.dirname(self._config_path())

    def _get_user_config(self):
        """Return the parsed ``~/.dazzlecmd/config.json`` as a dict.

        Reads the file once and caches. Tolerates:

        - Missing file (returns empty dict)
        - Malformed JSON (warns on stderr, returns empty dict)
        - Missing keys (callers apply their own defaults)

        Individual key type validation is the caller's responsibility --
        e.g., ``_get_config_list("kit_precedence")`` validates that the
        value is a list before returning it.
        """
        if self._config_cache is not None:
            return self._config_cache

        path = self._config_path()
        if not os.path.isfile(path):
            self._config_cache = {}
            return self._config_cache

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"Warning: could not read {path}: {exc}",
                file=sys.stderr,
            )
            self._config_cache = {}
            return self._config_cache

        if not isinstance(config, dict):
            print(
                f"Warning: {path} is not a JSON object, ignoring",
                file=sys.stderr,
            )
            self._config_cache = {}
            return self._config_cache

        self._config_cache = config
        return self._config_cache

    def _get_config_list(self, key, default=None):
        """Return a list-valued config key, validated.

        Returns ``default`` (or ``None``) if the key is absent or malformed.
        Emits a stderr warning on malformed values.
        """
        config = self._get_user_config()
        value = config.get(key)
        if value is None:
            return default
        if not isinstance(value, list):
            print(
                f"Warning: config key '{key}' is not a list, ignoring",
                file=sys.stderr,
            )
            return default
        return value

    def _get_config_dict(self, key, default=None):
        """Return a dict-valued config key, validated."""
        config = self._get_user_config()
        value = config.get(key)
        if value is None:
            return default if default is not None else {}
        if not isinstance(value, dict):
            print(
                f"Warning: config key '{key}' is not a dict, ignoring",
                file=sys.stderr,
            )
            return default if default is not None else {}
        return value

    def _write_user_config(self, updates):
        """Merge ``updates`` into the user config and write atomically.

        ``updates`` is a dict of top-level keys to set. Keys not mentioned
        in ``updates`` are preserved (merge semantics). The write is atomic:
        data is written to a temp file in the same directory, then
        ``os.replace()`` moves it into place. Creates the config directory
        on first write.

        Schema version field is injected if missing. The config cache is
        invalidated so subsequent reads see the new state.

        Example:
            engine._write_user_config({"active_kits": ["core", "wtf"]})
        """
        path = self._config_path()
        dir_ = self._config_dir()

        # Read existing config so we can merge (tolerant of missing/malformed)
        existing = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    existing = loaded
            except (json.JSONDecodeError, OSError):
                # Malformed existing config -- start fresh rather than
                # propagate the corruption. User's explicit write intent
                # takes precedence over unreadable old state.
                existing = {}

        existing.setdefault("_schema_version", self._SCHEMA_VERSION)
        existing.update(updates)

        os.makedirs(dir_, exist_ok=True)

        # Atomic write: temp file in same dir, then os.replace().
        # tempfile.NamedTemporaryFile's delete=False gives us a stable path.
        import tempfile
        fd, tmp_path = tempfile.mkstemp(
            prefix=".config.json.", suffix=".tmp", dir=dir_
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=4, sort_keys=False)
                f.write("\n")
            os.replace(tmp_path, path)
        except Exception:
            # Clean up temp file on any error before it lands
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        # Invalidate cache so subsequent _get_user_config reads see the write
        self._config_cache = None
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

        This is the main entry point for the CLI. Equivalent to cli.py:main().
        """
        # Import here to avoid circular imports -- cli.py uses the engine,
        # and the engine delegates display/dispatch back to cli functions
        from dazzlecmd.cli import (
            build_parser,
            dispatch_meta,
            dispatch_tool,
        )

        if argv is None:
            argv = sys.argv[1:]

        self.discover()

        if self.project_root is None:
            # No project root found -- show basic help
            parser = build_parser([], engine=self)
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

        # Meta-commands (only if is_root). Meta-commands never contain ":"
        # and take precedence over tool dispatch to prevent collision
        # notifications on routine meta-command invocations.
        if self.is_root:
            meta_commands = {
                "list", "info", "kit", "new", "version", "add", "mode",
                "tree",
            }
            if command_name in meta_commands or command_name.startswith("-"):
                sys_argv_backup = sys.argv
                sys.argv = [self.command] + list(argv)
                try:
                    args = parser.parse_args()
                    if hasattr(args, "_meta"):
                        return dispatch_meta(
                            args, self.projects, self.kits, self.project_root,
                            engine=self,
                        )
                finally:
                    sys.argv = sys_argv_backup
                return 0

        # Tool dispatch via FQCN resolver. This handles both short names
        # (with precedence-aware resolution) and explicit FQCNs.
        project, notification = self.resolve_command(command_name)

        if project is not None:
            # Emit ambiguity notification to stderr BEFORE running the tool
            # so the user sees it first. Silenceable via DZ_QUIET=1.
            if notification and not os.environ.get("DZ_QUIET"):
                print(notification, file=sys.stderr)

            tool_argv = argv[1:]
            return dispatch_tool(project, tool_argv)

        # Unknown command -- let argparse produce its standard error
        sys_argv_backup = sys.argv
        sys.argv = [self.command] + list(argv)
        try:
            parser.parse_args()
        finally:
            sys.argv = sys_argv_backup
        return 1

    @property
    def reserved_commands(self):
        """Commands reserved by the engine (not available as tool names)."""
        if self.is_root:
            return {
                "new", "add", "list", "info", "kit", "search",
                "build", "tree", "version", "enhance", "graduate", "mode",
            }
        return set()
