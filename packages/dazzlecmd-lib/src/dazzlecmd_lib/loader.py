"""Kit-aware project discovery and loading for dazzlecmd-lib.

This module handles kit and project discovery from the filesystem.
Runtime dispatch (runner factories) lives in ``dazzlecmd_lib.registry``.
"""

import json
import os
import sys


def discover_kits(kits_dir, projects_dir=None):
    """Discover kits using hybrid approach: in-repo manifests + registry pointers.

    1. Read registry pointers from kits/*.kit.json (activation state, source URLs)
    2. For each registered kit, look for in-repo manifest at projects/<kit>/.kit.json
       or projects/<kit>/kits/*.kit.json (the kit's own self-description)
    3. Merge: in-repo manifest is the source of truth for tools, tools_dir, manifest;
       registry pointer overrides activation state (always_active, disabled)

    Returns a list of kit dicts, each containing at minimum:
        name, tools, always_active
    """
    kits = []
    if not os.path.isdir(kits_dir):
        return kits

    if projects_dir is None:
        projects_dir = os.path.join(os.path.dirname(kits_dir), "projects")

    for filename in sorted(os.listdir(kits_dir)):
        if not filename.endswith(".kit.json"):
            continue
        filepath = os.path.join(kits_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: Could not load kit {filename}: {exc}", file=sys.stderr)
            continue

        kit_name = registry.get("name", filename.replace(".kit.json", ""))

        # Virtual kits are manifest-only overlays: the registry pointer IS
        # the full definition. Skip in-repo manifest lookup entirely --
        # otherwise a virtual kit accidentally named after a canonical kit
        # would inherit the canonical's tool list. (The skeleton experiment
        # surfaced this bug; v0.7.26 fixes it structurally.)
        is_virtual = registry.get("virtual") is True

        in_repo = None if is_virtual else _load_in_repo_kit_manifest(
            projects_dir, kit_name
        )

        if in_repo:
            # In-repo manifest is the base; registry overrides activation
            # and carries any explicit parent-level overrides.
            kit = dict(in_repo)
            # Registry overrides these fields only
            if "always_active" in registry:
                kit["always_active"] = registry["always_active"]
            if "source" in registry:
                kit["source"] = registry["source"]
            # Parent-level overrides (used when a nested aggregator's
            # in-repo manifest is missing tools_dir/manifest declarations)
            for override_key in ("_override_tools_dir", "_override_manifest"):
                if override_key in registry:
                    kit[override_key] = registry[override_key]
        else:
            # No in-repo manifest OR virtual kit -- registry IS the full definition.
            kit = dict(registry)

        kit.setdefault("always_active", False)
        kit.setdefault("tools", [])
        kit["_source"] = filepath
        kit["_kit_name"] = kit_name
        # Tag virtual kits and preserve their alias-rewrite map so the
        # engine's _apply_virtual_kits pass can process them after the
        # canonical FQCN index is built.
        if is_virtual:
            kit["virtual"] = True
            kit.setdefault("name_rewrite", registry.get("name_rewrite", {}))
        kits.append(kit)

    return kits


def _load_in_repo_kit_manifest(projects_dir, kit_name):
    """Load a kit's self-describing manifest from its project directory.

    Looks for:
    1. projects/<kit>/.kit.json (single kit manifest at project root)
    2. projects/<kit>/kits/<kit>.kit.json (kit's own kits directory)
    3. projects/<kit>/kits/*.kit.json (first found in kit's kits dir)

    Returns the manifest dict or None if not found.
    """
    kit_dir = os.path.join(projects_dir, kit_name)
    if not os.path.isdir(kit_dir):
        return None

    # Option 1: .kit.json at project root
    root_manifest = os.path.join(kit_dir, ".kit.json")
    if os.path.isfile(root_manifest):
        try:
            with open(root_manifest, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            # Resolve tools_dir relative to the kit's project directory
            if "tools_dir" in manifest:
                tools_dir = manifest["tools_dir"]
                if tools_dir == ".":
                    manifest["tools_dir"] = kit_dir
                else:
                    manifest["tools_dir"] = os.path.join(kit_dir, tools_dir)
            return manifest
        except (json.JSONDecodeError, OSError):
            pass

    # Option 2: kits/ subdirectory (aggregator-style kit)
    kit_kits_dir = os.path.join(kit_dir, "kits")
    if os.path.isdir(kit_kits_dir):
        # Try kit-named file first, then any .kit.json
        for candidate in [f"{kit_name}.kit.json", "core.kit.json"]:
            candidate_path = os.path.join(kit_kits_dir, candidate)
            if os.path.isfile(candidate_path):
                try:
                    with open(candidate_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    # Resolve tools_dir relative to the kit's project directory
                    if "tools_dir" in manifest:
                        manifest["tools_dir"] = os.path.join(
                            kit_dir, manifest["tools_dir"]
                        )
                    else:
                        # Default tools_dir for aggregator kits
                        manifest.setdefault("tools_dir", kit_dir)
                    return manifest
                except (json.JSONDecodeError, OSError):
                    pass

        # Fallback: first .kit.json found
        for fname in sorted(os.listdir(kit_kits_dir)):
            if fname.endswith(".kit.json"):
                fpath = os.path.join(kit_kits_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    if "tools_dir" in manifest:
                        manifest["tools_dir"] = os.path.join(
                            kit_dir, manifest["tools_dir"]
                        )
                    else:
                        manifest.setdefault("tools_dir", kit_dir)
                    return manifest
                except (json.JSONDecodeError, OSError):
                    pass

    return None


def get_active_kits(kits, user_config=None):
    """Return kits that should be active.

    Resolution precedence (highest to lowest):

    1. ``DZ_KITS`` environment variable (if set): full override. Format is a
       comma-separated list of kit names; empty string means "no kits
       active" (meta-commands only). Ignores config entirely.
    2. ``user_config["disabled_kits"]``: any kit here is excluded.
    3. ``user_config["active_kits"]``: if set and non-empty, only these
       kits are considered active (except always_active kits, which remain
       active unless explicitly disabled).
    4. Default: all discovered kits are active (legacy Phase 1 behavior).

    Overlap rule: if a kit appears in both ``active_kits`` and
    ``disabled_kits``, ``disabled_kits`` wins and a stderr warning is
    emitted.

    Args:
        kits: List of kit dicts from ``discover_kits``.
        user_config: Optional dict from ``engine._get_user_config()``. If
                     None, defaults to all kits active (legacy behavior).

    Returns:
        Filtered list of active kit dicts.
    """
    all_kits = list(kits)

    # Layer 1: DZ_KITS env var (full override, ignores config entirely)
    env_kits = os.environ.get("DZ_KITS")
    if env_kits is not None:
        requested = {k.strip() for k in env_kits.split(",") if k.strip()}
        return [
            k for k in all_kits
            if (k.get("_kit_name") or k.get("name")) in requested
        ]

    if user_config is None:
        # Legacy path: no config, all kits active
        return all_kits

    active_list = user_config.get("active_kits")
    disabled_list = user_config.get("disabled_kits") or []

    if not isinstance(active_list, list):
        active_list = None
    if not isinstance(disabled_list, list):
        disabled_list = []

    active_set = set(active_list) if active_list else None
    disabled_set = set(disabled_list)

    # Warn about overlap (disabled wins)
    if active_set and disabled_set:
        overlap = active_set & disabled_set
        if overlap:
            print(
                f"Warning: kits in both active_kits and disabled_kits "
                f"(disabled wins): {sorted(overlap)}",
                file=sys.stderr,
            )

    result = []
    for kit in all_kits:
        name = kit.get("_kit_name") or kit.get("name")
        if name in disabled_set:
            # Explicitly disabled: always wins, even for always_active kits
            continue
        if active_set is None:
            # No active_kits filter: include everything not disabled
            result.append(kit)
            continue
        # active_kits is set: include only listed kits, but always_active
        # kits remain active unless explicitly disabled
        if name in active_set or kit.get("always_active"):
            result.append(kit)

    return result


def discover_projects(projects_dir, active_kits=None, default_manifest=".dazzlecmd.json"):
    """Walk projects/<namespace>/<tool>/ directories for tool manifests.

    Scans the default projects/ directory, plus any kit-specific tools_dir
    paths declared by active kits. Kits can declare a custom manifest
    filename via the "manifest" field (default: ``default_manifest``).

    Args:
        projects_dir: The base directory to scan.
        active_kits: If provided, only projects listed in active kits are
                     returned. If None, all discovered projects are returned.
        default_manifest: Manifest filename to try when a kit does not
                          declare one. Child engines pass their own default
                          (e.g., ``.wtf.json``) instead of ``.dazzlecmd.json``.

    Returns a list of project dicts with resolved metadata.
    Each project dict has at minimum: name, namespace, description, runtime, _dir.
    """
    projects = []
    if not os.path.isdir(projects_dir):
        return projects

    # Build set of qualified tool names from active kits, and collect
    # kit-specific tools_dir paths and manifest filenames
    kit_tools = None
    kit_manifest_names = {}  # namespace -> manifest filename
    extra_tool_dirs = []     # (base_dir, manifest_name) for kit-specific paths
    project_root = os.path.dirname(projects_dir)

    if active_kits is not None:
        kit_tools = set()
        for kit in active_kits:
            manifest_name = kit.get("manifest", default_manifest)
            for tool_ref in kit.get("tools", []):
                kit_tools.add(tool_ref)
                # Track manifest name per namespace. FQCNs may have 2+
                # segments (``core:rn`` or ``wtf:core:restarted``); the
                # namespace for flat scanning is the LAST segment before
                # the tool name.
                if ":" in tool_ref:
                    ns = tool_ref.rsplit(":", 1)[0].split(":")[-1]
                    kit_manifest_names[ns] = manifest_name

            # If kit declares a tools_dir, queue it for scanning
            tools_dir = kit.get("tools_dir")
            if tools_dir:
                abs_tools_dir = os.path.join(project_root, tools_dir)
                if os.path.isdir(abs_tools_dir):
                    extra_tool_dirs.append((abs_tools_dir, manifest_name))

    # Scan default projects/<namespace>/<tool>/
    _scan_tool_dirs(projects_dir, default_manifest, kit_tools,
                    kit_manifest_names, projects)

    # Scan kit-specific tools_dir paths
    for base_dir, manifest_name in extra_tool_dirs:
        _scan_tool_dirs(base_dir, manifest_name, kit_tools,
                        kit_manifest_names, projects)

    return projects


def _scan_tool_dirs(base_dir, default_manifest, kit_tools,
                    kit_manifest_names, projects):
    """Scan a base directory for tools in <namespace>/<tool>/ layout.

    Looks for manifest files in each tool directory. Uses the kit's
    declared manifest name if available, otherwise falls back to
    default_manifest.
    """
    # Track already-discovered tool identities. Dedup by (namespace, tool_name)
    # to preserve distinct tools that share a short name across kits
    # (e.g., core:find and wtf:core:find).
    seen = {(p.get("namespace", ""), p["name"]) for p in projects}

    for namespace in sorted(os.listdir(base_dir)):
        ns_dir = os.path.join(base_dir, namespace)
        if not os.path.isdir(ns_dir) or namespace.startswith("."):
            continue

        # Determine manifest filename for this namespace
        manifest_name = kit_manifest_names.get(namespace, default_manifest)

        for tool_name in sorted(os.listdir(ns_dir)):
            tool_dir = os.path.join(ns_dir, tool_name)
            if not os.path.isdir(tool_dir) or tool_name.startswith("."):
                continue

            key = (namespace, tool_name)
            if key in seen:
                continue

            manifest_path = os.path.join(tool_dir, manifest_name)

            try:
                if os.path.isfile(manifest_path):
                    project = _load_manifest(
                        manifest_path, namespace, tool_name, tool_dir
                    )
                elif manifest_name != ".dazzlecmd.json":
                    # Try .dazzlecmd.json as fallback even for external kits
                    fallback = os.path.join(tool_dir, ".dazzlecmd.json")
                    if os.path.isfile(fallback):
                        project = _load_manifest(
                            fallback, namespace, tool_name, tool_dir
                        )
                    else:
                        project = _load_cached_manifest(
                            base_dir, namespace, tool_name, tool_dir
                        )
                else:
                    project = _load_cached_manifest(
                        base_dir, namespace, tool_name, tool_dir
                    )

                if project is None:
                    continue

                # Filter by kit membership
                qualified = f"{namespace}:{tool_name}"
                if kit_tools is not None and qualified not in kit_tools:
                    continue

                projects.append(project)
                seen.add(key)
            except Exception as exc:
                print(
                    f"Warning: Could not load project {namespace}/{tool_name}: {exc}",
                    file=sys.stderr,
                )


def _load_manifest(manifest_path, namespace, tool_name, tool_dir):
    """Load and validate a tool manifest.

    Handles both .dazzlecmd.json and external manifest formats (e.g.,
    .wtf.json). Normalizes field locations so the rest of the system
    sees a consistent structure.
    """
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Required fields
    if "name" not in manifest:
        print(f"Warning: {manifest_path} missing 'name' field", file=sys.stderr)
        return None

    manifest["namespace"] = namespace
    manifest["_dir"] = tool_dir
    manifest["_manifest_path"] = manifest_path

    # Defaults
    manifest.setdefault("version", "0.0.0")
    manifest.setdefault("description", "")
    manifest.setdefault("platform", "cross-platform")
    manifest.setdefault("runtime", {"type": "python"})

    # Normalize pass_through: some formats nest it inside runtime
    runtime = manifest.get("runtime", {})
    if "pass_through" not in manifest:
        manifest["pass_through"] = runtime.pop("pass_through", False)

    return manifest


# Module-level hook for manifest caching. The dazzlecmd CLI sets this
# to mode.get_cached_manifest so tools in submodule mode (without a
# manifest on disk) remain discoverable. The library leaves it as None
# — no cached manifest support unless the host application injects one.
_manifest_cache_fn = None


def set_manifest_cache_fn(fn):
    """Set the manifest cache lookup function.

    Called by the host application (e.g., dazzlecmd's cli.py) to inject
    the mode cache. ``fn`` should accept ``(project_root, qualified_name)``
    and return a manifest dict or None.
    """
    global _manifest_cache_fn
    _manifest_cache_fn = fn


def _load_cached_manifest(projects_dir, namespace, tool_name, tool_dir):
    """Try to load a tool's manifest from the mode cache.

    Uses the manifest cache function injected via
    ``set_manifest_cache_fn()``. Returns None if no cache function is
    set or the cache has no entry for this tool.
    """
    if _manifest_cache_fn is None:
        return None
    try:
        project_root = os.path.dirname(projects_dir)
        qualified = f"{namespace}:{tool_name}"
        cached = _manifest_cache_fn(project_root, qualified)
        if cached is None:
            return None
        cached["namespace"] = namespace
        cached["_dir"] = tool_dir
        cached["_manifest_path"] = None
        cached["_cached"] = True
        cached.setdefault("version", "0.0.0")
        cached.setdefault("description", "")
        cached.setdefault("platform", "cross-platform")
        cached.setdefault("pass_through", False)
        cached.setdefault("runtime", {"type": "python"})
        return cached
    except Exception:
        return None


def resolve_entry_point(project):
    """Resolve a project's runtime info to a callable dispatch function.

    Delegates to ``RunnerRegistry.resolve()``. The registry is populated
    with built-in types (python, shell, script, binary) at import time
    in ``dazzlecmd_lib.registry``. Extension types can be registered by
    kits or third-party code.

    Returns a function that accepts (argv) and returns an int exit code,
    or None if no factory is registered for the runtime type.
    """
    from dazzlecmd_lib.registry import RunnerRegistry
    return RunnerRegistry.resolve(project)
