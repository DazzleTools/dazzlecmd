"""Dev/publish mode toggle for dazzlecmd-lib aggregators.

Switches tools between dev mode (symlinks to local repos) and
publish mode (git submodules). Aggregator-agnostic: works for
dazzlecmd, wtf-windows, amdead, and any future aggregator built
on dazzlecmd-lib.

Lives in the library so any aggregator can use mode-switching
identically. dazzlecmd's ``src/dazzlecmd/mode.py`` is a thin wrapper
that calls into this module.

State of the world (issue #37 Phase 3.5, this is the v0.7.47 verbatim
copy from ``src/dazzlecmd/mode.py``; Tier 1 parameterizes it):

- ``parse_gitmodules`` and the path-conversion / discovery helpers
  hardcode ``"projects/"``. Tier 1 parameterizes on ``tools_dir`` to
  resolve BLOCKERs F2/F3/F4/F8.
- ``_resolve_remote_url`` hardcodes ``.dazzlecmd.json``-schema keys.
  Tier 1 parameterizes on the schema-paths config to resolve F7.
- User-facing strings hardcode ``"dz"``. Tier 1 parameterizes on the
  aggregator's ``command`` to resolve F5.
- The destructive ops (``shutil.rmtree``) use stdlib directly. Tier 1
  adds a dirty-tree refuse-or-force gate (the CRITICAL safety item).
"""

import configparser
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Optional

from dazzlecmd_lib.entity import build_entity
from dazzlecmd_lib.contexts import (
    CriticalityBoundaryError,
    RebindError,
    RebindInvariant,
    RebindReceipt,
)
from dazzlecmd_lib.paths import (
    create_link,
    get_link_target,
    is_linked_project,
    remove_link,
)


# Tool states
# Tool states
STATE_SYMLINK = "symlink"        # Dev mode — symlink/junction to local repo
STATE_SUBMODULE = "submodule"    # Publish mode — git submodule checkout
STATE_EMBEDDED = "embedded"      # Plain directory, no submodule registered
STATE_MISSING = "missing"        # Path doesn't exist
STATE_LOCAL_ONLY = "local-only"  # Symlink with no submodule registered


def _find_gitmodules(project_root):
    """Locate the ``.gitmodules`` governing ``project_root``.

    ``.gitmodules`` always lives at the git repo's top level, which may be an
    ANCESTOR of the aggregator's ``project_root``: post-#58 the dazzlecmd
    aggregator sits at ``<repo>/src/dazzlecmd`` while ``.gitmodules`` stays at
    ``<repo>``. Walk up from ``project_root`` to the first directory that holds
    a ``.gitmodules``. Returns ``(repo_root, gitmodules_path)``, or
    ``(None, None)`` when there is no governing ``.gitmodules`` (an installed
    package -- which has neither a repo nor submodules -- or a repo with no
    submodules).
    """
    cur = os.path.abspath(project_root)
    while True:
        gm = os.path.join(cur, ".gitmodules")
        if os.path.isfile(gm):
            return cur, gm
        # A ``.git`` here with no ``.gitmodules`` is the repo top of a repo that
        # simply has no submodules -- stop, don't climb out of the repo.
        if os.path.exists(os.path.join(cur, ".git")):
            return None, None
        parent = os.path.dirname(cur)
        if parent == cur:  # filesystem root
            return None, None
        cur = parent


def parse_gitmodules(project_root, *, tools_dir):
    """Parse .gitmodules to discover submodule mappings for ``tools_dir``.

    Returns dict mapping submodule path (e.g. ``<tools_dir>/<ns>/<tool>``)
    to ``{"url": ..., "path": ..., "namespace": ..., "tool_name": ...}``.
    The keys (and the ``path`` field) are relative to the AGGREGATOR root, to
    match the lookup keys ``detect_tool_state`` builds via
    ``_tool_dir_to_submodule_path``.

    Only 3-part paths of the form ``<tools_dir>/<namespace>/<tool>`` are
    captured -- 2-part kit-level submodule paths (an entire kit registered
    as a submodule) are skipped here and handled separately by the
    aggregator engine's discover_kits logic. This is the v0.7.47 BLOCKER
    F2 fix: ``tools_dir`` is no longer hardcoded to ``"projects"``.

    ``.gitmodules`` is located at the git repo root, which may sit ABOVE
    ``project_root`` when the aggregator lives in a repo subdirectory (the #58
    layout). Submodule paths in ``.gitmodules`` are repo-root-relative and are
    re-based to aggregator-relative here so they line up with the rest of the
    mode subsystem.

    Args:
        project_root: Absolute path to the aggregator's project root.
        tools_dir: Relative directory name where tools live (e.g.,
            ``"projects"`` for dazzlecmd, ``"tools"`` for wtf-windows /
            amdead). From ``AggregatorConfig.tools_dir``.
    """
    repo_root, gitmodules_path = _find_gitmodules(project_root)
    if gitmodules_path is None:
        return {}

    config = configparser.ConfigParser()
    config.read(gitmodules_path)

    prefix = tools_dir.rstrip("/") + "/"
    mappings = {}
    for section in config.sections():
        if not section.startswith('submodule "'):
            continue

        raw_path = config[section].get("path", "")  # repo-root-relative
        url = config[section].get("url", "")
        if not raw_path:
            continue

        # Re-base the repo-relative submodule path onto the aggregator root so
        # the key matches ``_tool_dir_to_submodule_path`` (which relativizes a
        # tool dir against ``project_root``). When the aggregator IS the repo
        # root (the pre-#58 layout) this relpath is the identity, so the
        # behaviour is unchanged there.
        try:
            rel = os.path.relpath(
                os.path.join(repo_root, raw_path), project_root
            ).replace("\\", "/")
        except ValueError:
            # Different drives on Windows -- cannot relativize.
            continue

        if not rel.startswith(prefix):
            continue

        # Parse <tools_dir>/<namespace>/<tool_name>
        relative = rel[len(prefix):]
        parts = relative.split("/")
        if len(parts) != 2:
            continue

        namespace, tool_name = parts

        mappings[rel] = {
            "url": url,
            "path": rel,
            "namespace": namespace,
            "tool_name": tool_name,
        }

    return mappings


def _load_full_config(project_root):
    """Load full mode_local.json contents.

    Returns dict with keys: dev_paths, cached_manifests, origins.

    ``origins`` (schema v2, #37 reversibility) records the pre-switch on-disk
    form of each tool that entered dev mode, so ``dz mode restore <tool>`` can
    re-materialize it. Older configs without the key get an empty dict here --
    the ``setdefault`` makes the migration transparent.
    """
    config_path = os.path.join(project_root, "mode_local.json")
    if not os.path.isfile(config_path):
        return {"dev_paths": {}, "cached_manifests": {}, "origins": {}}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("dev_paths", {})
        data.setdefault("cached_manifests", {})
        data.setdefault("origins", {})
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: Could not load mode_local.json: {exc}",
              file=sys.stderr)
        return {"dev_paths": {}, "cached_manifests": {}, "origins": {}}


# mode_local.json schema version -- stamped on every save so a future format
# change can detect and migrate old configs (3.5-12). Bump when the on-disk
# shape changes. v2 (#37): added the ``origins`` key (mode-swap reversibility).
MODE_LOCAL_SCHEMA_VERSION = 2


# Subprocess timeouts (seconds) for the git operations a mode swap runs.
# CLONE is the long pole (a first-time `git submodule add` fetches the whole
# repo over the network); UPDATE re-checks-out an already-fetched submodule;
# QUERY covers fast local read-only calls (status/config probes).
GIT_CLONE_TIMEOUT = 120
GIT_UPDATE_TIMEOUT = 60
GIT_QUERY_TIMEOUT = 10

# Repository-location environment variables (the set `git rev-parse
# --local-env-vars` reports). git EXPORTS these to hook subprocesses
# (pre-push, post-checkout, ...), so any of our git calls running under a
# hook would silently address the HOOK'S repository instead of the one we
# name with `-C`: with GIT_DIR set, `rev-parse --show-toplevel` reports the
# cwd as toplevel (defeating own-toplevel guards) and write commands like
# `subtree add` mutate the wrong repo. We always address repos explicitly,
# so these must never be inherited. Author/committer/ssh/askpass vars are
# deliberately NOT stripped.
_GIT_REPO_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
    "GIT_INTERNAL_SUPER_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_GRAFT_FILE",
    "GIT_NAMESPACE",
    "GIT_QUARANTINE_PATH",
)


def sanitized_git_env():
    """A copy of the environment safe for spawning git against an EXPLICIT repo.

    Strips the repo-location variables above so a git subprocess resolves the
    repository from its ``-C``/``cwd`` argument -- never from ambient hook
    state. Pass as ``env=`` to every git ``subprocess`` call.
    """
    env = dict(os.environ)
    for var in _GIT_REPO_LOCATION_VARS:
        env.pop(var, None)
    return env


def _save_full_config(project_root, data):
    """Save full mode_local.json contents (stamped with the schema version)."""
    config_path = os.path.join(project_root, "mode_local.json")
    data["_schema_version"] = MODE_LOCAL_SCHEMA_VERSION
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.write("\n")
    except OSError as exc:
        print(f"Warning: Could not save mode_local.json: {exc}",
              file=sys.stderr)


def load_local_config(project_root):
    """Load dev path mappings from mode_local.json.

    Returns dict mapping qualified tool names (e.g. "core:listall")
    to local filesystem paths.
    """
    return _load_full_config(project_root).get("dev_paths", {})


def save_local_config(project_root, dev_paths):
    """Save dev path mappings to mode_local.json."""
    data = _load_full_config(project_root)
    data["dev_paths"] = dev_paths
    _save_full_config(project_root, data)


def cache_manifest(project_root, qualified_name, manifest):
    """Cache a tool's manifest for when the remote version lacks one.

    Stores a copy of the .dazzlecmd.json contents so the tool remains
    discoverable even after switching to a remote source that doesn't
    have the manifest file yet.
    """
    data = _load_full_config(project_root)
    # Strip computed/internal keys. manifest is always a DazzleEntity;
    # to_manifest() drops promoted computed fields (directory, kit_active,
    # etc.) and any _-prefixed runtime keys.
    clean = manifest.to_manifest()
    data["cached_manifests"][qualified_name] = clean
    _save_full_config(project_root, data)


def get_cached_manifest(project_root, qualified_name):
    """Retrieve a cached manifest for a tool.

    Returns the manifest dict, or None if not cached.
    """
    data = _load_full_config(project_root)
    return data.get("cached_manifests", {}).get(qualified_name)


def detect_tool_state(tool_dir, gitmodules, project_root, *, tools_dir):
    """Detect the current mode of a tool.

    Args:
        tool_dir: Absolute path to the tool directory.
        gitmodules: Dict from ``parse_gitmodules()``.
        project_root: Absolute path to the aggregator's project root.
            Needed to derive the relative path for gitmodules lookup.
        tools_dir: Relative directory name where tools live. Threads
            through to ``_tool_dir_to_submodule_path``.

    Returns:
        One of: STATE_SYMLINK, STATE_SUBMODULE, STATE_EMBEDDED,
                STATE_MISSING, STATE_LOCAL_ONLY.
    """
    # Build the relative path key for gitmodules lookup
    # tool_dir looks like .../<tools_dir>/<ns>/<name>
    # We need "<tools_dir>/<ns>/<name>"
    rel_key = _tool_dir_to_submodule_path(
        tool_dir, project_root, tools_dir=tools_dir
    )
    has_submodule = rel_key in gitmodules if rel_key else False

    if not os.path.exists(tool_dir):
        return STATE_MISSING

    if is_linked_project(tool_dir):
        if has_submodule:
            return STATE_SYMLINK  # Dev mode — has submodule to restore to
        else:
            return STATE_LOCAL_ONLY  # Permanent symlink, no submodule

    if os.path.isdir(tool_dir):
        if has_submodule:
            return STATE_SUBMODULE  # Publish mode
        else:
            return STATE_EMBEDDED  # Plain directory, no submodule

    return STATE_MISSING


def _tool_dir_to_submodule_path(tool_dir, project_root, *, tools_dir):
    """Convert absolute ``tool_dir`` to relative submodule path.

    Example with ``tools_dir="projects"``::

        tool_dir=C:/code/dazzlecmd/github/projects/core/listall
        project_root=C:/code/dazzlecmd/github
        -> "projects/core/listall"

    Returns ``None`` when ``tool_dir`` is not under ``project_root/tools_dir/``.
    This is the v0.7.47 BLOCKER F8 fix: ``os.path.relpath``-anchored
    matching replaces the brittle substring search for ``"projects/"``.

    Args:
        tool_dir: Absolute path to a tool directory.
        project_root: Absolute path to the aggregator's project root.
        tools_dir: Relative directory name where tools live.
    """
    try:
        rel = os.path.relpath(tool_dir, project_root).replace("\\", "/")
    except ValueError:
        # Different drives on Windows -- can't compute relative path.
        return None
    expected_prefix = tools_dir.rstrip("/") + "/"
    if not rel.startswith(expected_prefix):
        return None
    return rel


def resolve_dev_path(qualified_name, project_root, explicit_path=None, *,
                     tools_dir):
    """Resolve the local dev path for a tool.

    Resolution order:
    1. ``explicit_path`` argument (``--path`` flag).
    2. ``mode_local.json`` ``dev_paths`` entry.
    3. ``.gitmodules`` URL if it resolves to a local path.

    Args:
        qualified_name: Tool's qualified name (e.g., ``"core:listall"``).
        project_root: Absolute path to the aggregator's project root.
        explicit_path: User-supplied path (optional).
        tools_dir: Relative directory name where tools live. Threads
            through to ``parse_gitmodules``.

    Returns:
        Resolved path string or ``None``.
    """
    if explicit_path:
        path = os.path.abspath(explicit_path)
        if os.path.isdir(path):
            return path
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return None

    # Check mode_local.json
    local_config = load_local_config(project_root)
    if qualified_name in local_config:
        path = local_config[qualified_name]
        if os.path.isdir(path):
            return path
        print(f"Warning: Configured dev path does not exist: {path}",
              file=sys.stderr)

    # Check .gitmodules URL as local path
    gitmodules = parse_gitmodules(project_root, tools_dir=tools_dir)
    for info in gitmodules.values():
        qn = f"{info['namespace']}:{info['tool_name']}"
        if qn == qualified_name:
            url = info["url"]
            if _is_local_path(url):
                local = _normalize_local_path(url)
                if os.path.isdir(local):
                    return local

    return None


def _is_local_path(url):
    """Check if a URL is actually a local filesystem path."""
    if url.startswith(("http://", "https://", "git@", "ssh://")):
        return False
    return True


def _normalize_local_path(path_str):
    """Normalize a path from .gitmodules to a local filesystem path."""
    # Convert /c/code/... to C:\code\... on Windows
    if sys.platform == "win32" and len(path_str) >= 3:
        if path_str[0] == "/" and path_str[2] == "/":
            drive = path_str[1].upper()
            return drive + ":" + path_str[2:].replace("/", "\\")
    return os.path.abspath(path_str)


# ============================================================================
# Status Command
# ============================================================================

STATE_LABELS = {
    STATE_SYMLINK: "DEV (symlink)",
    STATE_SUBMODULE: "PUBLISH (submodule)",
    STATE_EMBEDDED: "EMBEDDED",
    STATE_MISSING: "MISSING",
    STATE_LOCAL_ONLY: "LOCAL-ONLY (symlink, no submodule)",
}


def cmd_status(projects, project_root, tool_filter=None, kit_filter=None, *,
               tools_dir, command):
    """Show mode status for tools.

    Args:
        projects: List of project dicts from ``discover_projects()``.
        project_root: Absolute path to the aggregator's project root.
        tool_filter: Optional tool name to filter to.
        kit_filter: Optional kit name to filter by namespace.
        tools_dir: Relative directory name where tools live (BLOCKER F3
            fix -- replaces hardcoded ``"projects"``).
        command: CLI command name for user-facing strings (BLOCKER F5
            fix -- replaces hardcoded ``"dz"``).

    Returns:
        int exit code.
    """
    gitmodules = parse_gitmodules(project_root, tools_dir=tools_dir)

    # Merge discovered projects with undiscovered tools from directory scan
    # and cached manifests — ensures tools are visible even when their
    # remote version lacks the manifest
    all_projects = list(projects)
    known_names = {p.name for p in all_projects}
    data = _load_full_config(project_root)
    cached = data.get("cached_manifests", {})

    # Scan <tools_dir>/ for directories not in discovered projects
    projects_dir = os.path.join(project_root, tools_dir)
    if os.path.isdir(projects_dir):
        for ns in sorted(os.listdir(projects_dir)):
            ns_dir = os.path.join(projects_dir, ns)
            if not os.path.isdir(ns_dir) or ns.startswith("."):
                continue
            # Skip a nested aggregator-as-kit (it has its own kits/): its subdirs
            # (src/, kits/, tests/, ...) are NOT tools -- the engine namespace-remaps
            # its real tools as <ns>:<inner-ns>:<tool>. Flat-scanning them here would
            # surface phantom rows like `src wtf` / `kits wtf`.
            if os.path.isdir(os.path.join(ns_dir, "kits")):
                continue
            for name in sorted(os.listdir(ns_dir)):
                if name in known_names or name.startswith("."):
                    continue
                tool_dir = os.path.join(ns_dir, name)
                if not os.path.isdir(tool_dir):
                    continue
                qualified = f"{ns}:{name}"
                if qualified in cached:
                    payload = dict(cached[qualified])
                else:
                    payload = {"name": name, "description": "(no manifest)"}
                payload["directory"] = tool_dir
                payload["namespace"] = ns
                payload.setdefault("name", name)
                entry = build_entity(payload, entity_type="tool")
                all_projects.append(entry)
                known_names.add(name)

    filtered = all_projects
    if tool_filter:
        filtered = [p for p in filtered if p.name == tool_filter]
        if not filtered:
            print(f"Tool '{tool_filter}' not found. Use '{command} list' to see "
                  "available tools.")
            return 1
    if kit_filter:
        filtered = [p for p in filtered if p.namespace == kit_filter]

    if not filtered:
        print("No tools found.")
        return 0

    # Calculate column widths
    name_width = max(len(p.name) for p in filtered)
    ns_width = max(len(p.namespace) for p in filtered)

    print()
    header = (f"  {'Name':<{name_width}}  {'Namespace':<{ns_width}}  "
              f"{'Mode':<30}  Details")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for project in filtered:
        tool_dir = project.directory
        state = detect_tool_state(
            tool_dir, gitmodules, project_root, tools_dir=tools_dir
        )
        label = STATE_LABELS.get(state, state)

        name = project.name
        ns = project.namespace

        # Build details column
        details = ""
        if state == STATE_SYMLINK or state == STATE_LOCAL_ONLY:
            target = get_link_target(tool_dir)
            if target:
                details = f"-> {target}"
        elif state == STATE_SUBMODULE:
            rel_key = _tool_dir_to_submodule_path(
                tool_dir, project_root, tools_dir=tools_dir
            )
            if rel_key and rel_key in gitmodules:
                details = gitmodules[rel_key]["url"]

        print(f"  {name:<{name_width}}  {ns:<{ns_width}}  "
              f"{label:<30}  {details}")

    print(f"\n  {len(filtered)} tool(s)")
    return 0


# ============================================================================
# Switch Command
# ============================================================================

def cmd_switch(tool_name, projects, project_root, dev_path=None,
               force_mode=None, dry_run=False, url=None, force=False, *,
               tools_dir, command, schema=None, immediate=False):
    """Toggle a tool between dev and publish mode.

    Args:
        tool_name: Name of the tool to switch.
        projects: List of project dicts.
        project_root: Absolute path to the aggregator's project root.
        dev_path: Explicit path for dev mode (optional).
        force_mode: ``"dev"`` or ``"publish"`` to force a specific mode.
        dry_run: If True, show what would happen without doing it.
        url: Explicit remote URL for first-time submodule registration.
        force: If True, bypass the dirty-tree safety gate at every
            destructive `shutil.rmtree` call site. Without this, the
            switch refuses when the tool's working tree has uncommitted
            changes (T1-E safety primitive). Caller is responsible for
            surfacing the option to the user (e.g., `--force` CLI flag).
        tools_dir: Relative directory name where tools live.
        command: CLI command name for user-facing strings.
        schema: ``AggregatorSchema`` (or dict) for resolving the remote URL
            from a tool's manifest. If ``None``, defaults to dazzlecmd's
            historical schema (``source.url`` then ``lifecycle.graduated_to``).

    Returns:
        int exit code.
    """
    # Find the tool — first in discovered projects (by short name OR exact
    # FQCN), then by directory scan. Exact-match only: `mode switch` rewrites a
    # submodule, so it must act on exactly what was named and never follow the
    # fuzzy precedence/favorites resolver to a different tool.
    matches = [
        p for p in projects
        if p.name == tool_name or (p.fqcn or "") == tool_name
    ]
    if matches:
        project = matches[0]
        # Normalize an FQCN argument to the resolved short name so the
        # downstream qualified-name and directory logic is unchanged.
        tool_name = project.name
    else:
        # Tool not in discovered projects — scan directories and cache
        project = _find_undiscovered_tool(
            tool_name, project_root, tools_dir=tools_dir
        )
        if project is None:
            print(f"Error: Tool '{tool_name}' not found. Use '{command} list' "
                  "to see available tools.", file=sys.stderr)
            return 1

    tool_dir = project.directory
    namespace = project.namespace
    qualified = f"{namespace}:{tool_name}"

    gitmodules = parse_gitmodules(project_root, tools_dir=tools_dir)
    state = detect_tool_state(
        tool_dir, gitmodules, project_root, tools_dir=tools_dir
    )

    if dry_run:
        print("[DRY-RUN] No changes will be made\n")

    # Determine target mode
    if force_mode:
        target = force_mode
    else:
        target = _determine_target(state)

    if target is None:
        _print_no_toggle(tool_name, state, command=command, tools_dir=tools_dir)
        return 1

    print(f"Tool:    {qualified}")
    print(f"Current: {STATE_LABELS.get(state, state)}")
    print(f"Target:  {'DEV (symlink)' if target == 'dev' else 'PUBLISH (submodule)'}")
    print()

    if target == "dev":
        return _switch_to_dev(
            project, project_root, gitmodules, dev_path, dry_run, force,
            tools_dir=tools_dir, command=command, immediate=immediate,
        )
    else:
        return _switch_to_publish(
            project, project_root, gitmodules, dry_run, force, url=url,
            tools_dir=tools_dir, command=command, schema=schema,
            immediate=immediate,
        )


def cmd_restore(tool_name, projects, project_root, dry_run=False, *,
                tools_dir, command, schema=None):
    """Restore a tool to its prior on-disk form -- the inverse of ``mode switch``
    into dev mode (#37). Entering dev mode ungroups the tool from the working
    tree (a symlink replaces its content); ``restore`` groups it back.

    Reads the origin recorded by ``_record_origin`` and re-materializes the
    prior form by its mechanism:

    - **EMBEDDED** origin -> recover the backed-up content from the safedel
      trash (the only path that needs the backup; there is no remote to clone).
    - **SUBMODULE** origin -> re-clone via the existing publish path
      (``git submodule update --init``); the backup is not needed.

    Refuses cleanly when there is no origin, the tool is not in dev mode, or the
    trash backup is gone. For the EMBEDDED path the symlink is removed BEFORE
    recovery (safedel refuses an occupied target); a recovery failure re-creates
    the symlink as best-effort rollback so we never silently lose the tool.
    """
    matches = [
        p for p in projects
        if p.name == tool_name or (p.fqcn or "") == tool_name
    ]
    if matches:
        project = matches[0]
        tool_name = project.name
    else:
        project = _find_undiscovered_tool(
            tool_name, project_root, tools_dir=tools_dir
        )
        if project is None:
            print(f"Error: Tool '{tool_name}' not found. Use '{command} list' "
                  "to see available tools.", file=sys.stderr)
            return 1

    tool_dir = project.directory
    namespace = project.namespace
    qualified = f"{namespace}:{tool_name}"

    data = _load_full_config(project_root)
    origin = data.get("origins", {}).get(qualified)
    if not origin:
        print(f"No restore origin recorded for '{qualified}'. Nothing to do.")
        print(f"  (Origins are recorded when '{command} mode switch' enters "
              "dev mode from an embedded dir or submodule.)")
        return 0

    gitmodules = parse_gitmodules(project_root, tools_dir=tools_dir)
    state = detect_tool_state(
        tool_dir, gitmodules, project_root, tools_dir=tools_dir
    )
    if state not in (STATE_SYMLINK, STATE_LOCAL_ONLY):
        print(f"Tool '{qualified}' is not in dev mode (current: "
              f"{STATE_LABELS.get(state, state)}); restore not applicable.")
        return 0

    prior_state = origin.get("prior_state")
    original_path = origin.get("original_path")
    if (original_path
            and os.path.normpath(original_path) != os.path.normpath(tool_dir)):
        print(f"  [warning] recorded origin path '{original_path}' differs from "
              f"the current tool dir '{tool_dir}' (tool moved/renamed?); "
              "restoring to the current location.", file=sys.stderr)

    dev_path = data.get("dev_paths", {}).get(qualified)

    print(f"Tool:    {qualified}")
    print(f"Current: {STATE_LABELS.get(state, state)}")
    print(f"Target:  {STATE_LABELS.get(prior_state, prior_state)} (restore)")
    print()

    if prior_state == STATE_SUBMODULE:
        if dry_run:
            print(f"  Would restore the submodule checkout at {tool_dir} "
                  "(git submodule update --init).")
            return 0
        # Re-clone via the existing publish path. It clears the origin on
        # success (intentional move to publish).
        rc = _switch_to_publish(
            project, project_root, gitmodules, dry_run=False, force=False,
            tools_dir=tools_dir, command=command, schema=schema,
        )
        if rc == 0:
            print(f"Restored '{qualified}' to SUBMODULE.")
        return rc

    if prior_state == STATE_EMBEDDED:
        trash_folder = origin.get("trash_folder")
        if not trash_folder:
            print(f"Error: the origin for '{qualified}' is EMBEDDED but records "
                  "no trash backup; cannot restore automatically.",
                  file=sys.stderr)
            return 1
        from dazzlecmd_lib.core.safedel import TrashStore, recover_folder
        store = TrashStore()
        if store.get_folder(trash_folder) is None:
            print(f"Error: backup '{trash_folder}' not found in the trash store "
                  "(it may have been cleaned). Cannot restore automatically.",
                  file=sys.stderr)
            print(f"  Inspect the trash with: {command} safedel list",
                  file=sys.stderr)
            return 1

        if dev_path:
            print(f"  Note: your dev work in {dev_path} is untouched -- only the "
                  "symlink here is removed.")
        if dry_run:
            print(f"  Would remove the symlink at {tool_dir}.")
            print(f"  Would recover backup '{trash_folder}' to {tool_dir}.")
            return 0

        # Remove the symlink first (safedel refuses an occupied target), then
        # recover. On recovery failure, re-create the symlink (best-effort
        # rollback) so the tool is never left STATE_MISSING.
        if is_linked_project(tool_dir):
            if not remove_link(tool_dir):
                print(f"Error: could not remove the symlink at {tool_dir}.",
                      file=sys.stderr)
                return 1
        rc = recover_folder(store, trash_folder)
        if rc != 0:
            print(f"Error: recovery of backup '{trash_folder}' failed.",
                  file=sys.stderr)
            if dev_path and create_link(dev_path, tool_dir):
                print(f"  Re-created the dev symlink {tool_dir} -> {dev_path} "
                      "(restore rolled back; nothing lost).", file=sys.stderr)
            return 1

        _clear_origin(qualified, project_root)
        # No longer in dev mode -- drop the remembered dev path too.
        dp = load_local_config(project_root)
        if qualified in dp:
            dp.pop(qualified, None)
            save_local_config(project_root, dp)
        print(f"Restored '{qualified}' to EMBEDDED.")
        return 0

    print(f"Error: unknown prior_state {prior_state!r} recorded for "
          f"'{qualified}'.", file=sys.stderr)
    return 1


def _find_undiscovered_tool(tool_name, project_root, *, tools_dir):
    """Find a tool by scanning ``<tools_dir>/`` directories even without a manifest.

    Used when a tool exists on disk (e.g. as a submodule) but has no
    per-tool manifest so ``discover_projects()`` didn't find it. Falls
    back to cached manifests in ``mode_local.json``.

    Args:
        tool_name: Name of the tool to look for.
        project_root: Absolute path to the aggregator's project root.
        tools_dir: Relative directory name where tools live (BLOCKER F4
            fix -- replaces hardcoded ``"projects"``).

    Returns:
        A Tool entity or ``None``. All return paths return a real
        DazzleEntity so ``cmd_switch`` and its helpers can use attribute
        access unconditionally.
    """
    projects_dir = os.path.join(project_root, tools_dir)
    if not os.path.isdir(projects_dir):
        return None

    # Scan <tools_dir>/<namespace>/<tool_name>
    for namespace in os.listdir(projects_dir):
        ns_dir = os.path.join(projects_dir, namespace)
        if not os.path.isdir(ns_dir) or namespace.startswith("."):
            continue
        # Skip a nested aggregator-as-kit (its tools are namespace-remapped, not
        # flat <ns>:<tool>; the engine resolves them) -- don't mis-resolve one of
        # its subdirs (src/, kits/, ...) as a tool.
        if os.path.isdir(os.path.join(ns_dir, "kits")):
            continue
        tool_dir = os.path.join(ns_dir, tool_name)
        if os.path.exists(tool_dir) or is_linked_project(tool_dir):
            qualified = f"{namespace}:{tool_name}"
            # Try cached manifest first; build entity from it + the computed fields.
            cached = get_cached_manifest(project_root, qualified)
            if cached:
                data = dict(cached)
                data["directory"] = tool_dir
                data["namespace"] = namespace
                data.setdefault("name", tool_name)
                return build_entity(data, entity_type="tool")
            # No manifest cached — build a minimal entity.
            return build_entity(
                {
                    "name": tool_name,
                    "namespace": namespace,
                    "directory": tool_dir,
                },
                entity_type="tool",
            )

    # Check if any cached manifest matches (tool may have been removed from disk)
    data = _load_full_config(project_root)
    for qn, manifest in data.get("cached_manifests", {}).items():
        if ":" in qn:
            ns, name = qn.split(":", 1)
        else:
            ns, name = "", qn
        if name == tool_name:
            tool_dir = os.path.join(projects_dir, ns, name)
            payload = dict(manifest)
            payload["directory"] = tool_dir
            payload["namespace"] = ns
            payload.setdefault("name", tool_name)
            return build_entity(payload, entity_type="tool")

    return None


def _determine_target(state):
    """Given current state, determine which mode to switch to.

    Returns "dev", "publish", or None if toggle is not possible.
    """
    if state == STATE_SYMLINK:
        return "publish"
    elif state == STATE_SUBMODULE:
        return "dev"
    elif state == STATE_MISSING:
        return None  # Ambiguous — use --dev or --publish
    elif state == STATE_EMBEDDED:
        # Switch the embedded checkout to a dev symlink (3.5-1). The embedded
        # directory is removed RECOVERABLY (staged to safedel's trash store;
        # #38) before the symlink is created, so enabling this is data-safe.
        # A bare toggle defaults to dev (the common "work on it locally"
        # intent); `--publish` registers a submodule instead.
        return "dev"
    elif state == STATE_LOCAL_ONLY:
        return None  # No submodule registered
    return None


def _print_no_toggle(tool_name, state, *, command, tools_dir):
    """Print a helpful message when toggle is not possible.

    The ``command`` parameter is the aggregator's CLI name (e.g., ``"dz"``,
    ``"wtf"``, ``"amdead"``); ``tools_dir`` is the aggregator's tool-root
    directory name (e.g., ``"projects"`` or ``"tools"``). Both substitute
    into user-facing hint text; BLOCKER F5 fix.
    """
    if state == STATE_EMBEDDED:
        print(f"Error: '{tool_name}' is embedded (no submodule registered).",
              file=sys.stderr)
        print("  This tool lives directly in the repo -- no mode toggle "
              "available.", file=sys.stderr)
    elif state == STATE_LOCAL_ONLY:
        print(f"Error: '{tool_name}' is a local-only symlink (no submodule "
              "registered).", file=sys.stderr)
        print("  To enable mode switching, register a submodule first:",
              file=sys.stderr)
        print(f"    git submodule add <url> {tools_dir}/<ns>/{tool_name}",
              file=sys.stderr)
    elif state == STATE_MISSING:
        print(f"Error: '{tool_name}' is missing from disk.",
              file=sys.stderr)
        print("  Use --dev or --publish to specify which mode to restore.",
              file=sys.stderr)
    else:
        print(f"Error: Cannot toggle '{tool_name}' (state: {state}).",
              file=sys.stderr)


def _check_dirty_tree(tool_dir):
    """Return ``git status --porcelain`` output for ``tool_dir``.

    Empty string means clean OR not a git checkout (no work to lose).
    Non-empty means the working tree has uncommitted changes (modified
    tracked files, staged changes, untracked files, unmerged paths) --
    blowing this away would destroy them.

    Tier 1 T1-E safety primitive. The senior-engineer audit flagged the
    `shutil.rmtree(tool_dir)` call sites in `_switch_to_dev` and
    `_switch_to_publish` as the CRITICAL hazard of the mode subsystem:
    a user mid-experiment in a submodule checkout (or a local-only dir
    that happens to be its own git repo) loses everything when the
    switch fires. Callers gate the rmtree on this check and refuse
    unless the user opts in via ``force=True``.
    """
    if not os.path.isdir(tool_dir):
        return ""
    # Verify tool_dir is its OWN git worktree, not just inside some
    # ancestor's repo (e.g., a parent monorepo, a user's $HOME/.git, a
    # CI checkout). Without this guard `git status` walks up the tree
    # and reports the ancestor's dirty state for a non-git tool_dir.
    try:
        toplevel = subprocess.run(
            ["git", "-C", tool_dir, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=GIT_QUERY_TIMEOUT,
            env=sanitized_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if toplevel.returncode != 0:
        return ""
    found_top = os.path.realpath(toplevel.stdout.strip())
    asked_top = os.path.realpath(tool_dir)
    if found_top != asked_top:
        # tool_dir is inside an ancestor's repo, not its own. No tracked
        # state to preserve at this layer.
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", tool_dir, "status", "--porcelain"],
            capture_output=True, text=True, timeout=GIT_QUERY_TIMEOUT,
            env=sanitized_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        # `git` missing, or `tool_dir` somehow unreachable. Don't block
        # on tooling we can't run; the rmtree itself will surface any
        # actual filesystem error.
        return ""
    if result.returncode != 0:
        # Not a git checkout (`fatal: not a git repository`). No tracked
        # state to preserve, so no dirty content from git's perspective.
        return ""
    return result.stdout


def _print_dirty_refusal(tool_name, tool_dir, dirty_output, command):
    """Print the standard refusal-to-overwrite message and return 1."""
    print(f"Error: '{tool_name}' has uncommitted changes; refusing to switch.",
          file=sys.stderr)
    # Limit displayed lines so the error stays readable even if dozens of
    # files are dirty. The full output is one `git status` away.
    lines = dirty_output.splitlines()
    for line in lines[:10]:
        print(f"  {line}", file=sys.stderr)
    if len(lines) > 10:
        print(f"  ... and {len(lines) - 10} more", file=sys.stderr)
    print("  Either commit/stash your work in:", file=sys.stderr)
    print(f"    git -C {tool_dir} status", file=sys.stderr)
    print(f"  Or rerun with: {command} mode switch <tool> --force "
          "(DATA LOSS WARNING).", file=sys.stderr)


def _rmtree_or_error(tool_dir):
    """``shutil.rmtree`` with the standard error message. Returns 0 or 1."""
    import shutil
    try:
        shutil.rmtree(tool_dir)
        return 0
    except OSError as exc:
        print(f"Error: Could not remove {tool_dir}: {exc}", file=sys.stderr)
        return 1


def _remove_tool_dir(tool_dir, *, tool_name, command, force, immediate=False):
    """Remove ``tool_dir`` for a mode swap. Returns ``(rc, trash_folder)``:
    ``rc`` is 0 (ok) or 1 (failed/aborted); ``trash_folder`` is the safedel
    backup's folder name on a recoverable success, else ``None``.

    The ``trash_folder`` is the pointer ``_record_origin`` stores so ``dz mode
    restore`` can recover the exact backed-up content (#37). It is ``None`` for
    the ``--immediate`` and ``--force`` rmtree paths (no backup made).

    The caller has already cleared the dirty-tree gate (T1-E). Removal is
    RECOVERABLE by default: ``tool_dir`` is staged to the trash store via the
    constitutional ``dazzlecmd_lib.core.safedel`` primitive (recover with
    ``<command> safedel recover last``). That primitive lives in the library, so
    it is ALWAYS available to every aggregator -- there is NO "safedel absent"
    fallback path.

    ``immediate=True`` is a deliberate user CHOICE (the ``--immediate`` flag):
    delete the directory directly with no recovery backup. It is NOT a fallback
    -- the recoverable path is the default and always works; ``immediate`` is
    simply a different selected behavior. A recoverable-delete FAILURE (e.g. an
    unwritable trash store) aborts the swap with nothing deleted unless
    ``force`` is given.
    """
    if immediate:
        print(f"  Removing {tool_dir} immediately (--immediate; no recovery "
              "backup).")
        return _rmtree_or_error(tool_dir), None

    from dazzlecmd_lib.core.safedel import TrashStore
    folder_name = None
    try:
        result = TrashStore().trash([tool_dir])
        ok = result.success
        folder_name = result.folder_name if ok else None
        errors = "" if ok else "; ".join(result.errors)
    except Exception as exc:  # noqa: BLE001
        ok, errors = False, str(exc)

    if ok:
        print(f"  Backed up to trash (recover with: {command} safedel "
              "recover last)")
        return 0, folder_name

    print(f"Error: recoverable delete of {tool_dir} failed: "
          f"{errors or 'unknown error'}", file=sys.stderr)
    if force:
        print("  --force given; removing without a recovery backup.",
              file=sys.stderr)
        return _rmtree_or_error(tool_dir), None
    print(f"  Swap aborted (nothing deleted). Use: {command} mode switch "
          "<tool> --immediate to delete without a backup.", file=sys.stderr)
    return 1, None


def _switch_to_dev(project, project_root, gitmodules, explicit_path,
                   dry_run, force, *, tools_dir, command, immediate=False):
    """Switch a tool from publish mode (submodule) to dev mode (symlink).

    Threads ``tools_dir`` and ``command`` through to the parameterized
    inner calls (BLOCKERs F2/F3/F4/F5/F8). ``force`` overrides the
    dirty-tree safety gate at the destructive `rmtree` (T1-E).
    """
    tool_dir = project.directory
    tool_name = project.name
    namespace = project.namespace
    qualified = f"{namespace}:{tool_name}"
    state = detect_tool_state(
        tool_dir, gitmodules, project_root, tools_dir=tools_dir
    )

    if state == STATE_SYMLINK or state == STATE_LOCAL_ONLY:
        print("Already in dev mode (symlink).")
        target = get_link_target(tool_dir)
        if target:
            print(f"  -> {target}")
        return 0

    # Resolve dev path
    dev_path = resolve_dev_path(
        qualified, project_root, explicit_path, tools_dir=tools_dir
    )
    if dev_path is None:
        print(f"Error: Cannot determine dev path for '{tool_name}'.",
              file=sys.stderr)
        print(f"  Specify with: {command} mode switch <tool> --path /local/repo",
              file=sys.stderr)
        print("  Or add to mode_local.json:", file=sys.stderr)
        print(f'    {{"dev_paths": {{"{qualified}": "/path/to/repo"}}}}',
              file=sys.stderr)
        return 1

    if dry_run:
        if os.path.exists(tool_dir):
            if not is_linked_project(tool_dir):
                dirty = _check_dirty_tree(tool_dir)
                if dirty and not force:
                    print(f"  [WARNING] Would refuse: {tool_dir} has "
                          "uncommitted changes (rerun with --force).")
            print(f"  Would remove: {tool_dir}")
        print(f"  Would create symlink: {tool_dir} -> {dev_path}")
        _dry_run_save_path(qualified, dev_path, project_root)
        return 0

    # Remove existing directory (submodule checkout). Track the safedel backup
    # folder so we can record a restore origin (#37) after the symlink lands.
    trash_folder = None
    removed_form = None  # the prior on-disk form, for the origin record
    if os.path.exists(tool_dir):
        if is_linked_project(tool_dir):
            remove_link(tool_dir)
        else:
            # Refuse if the working tree has uncommitted changes that
            # an rmtree would silently destroy (T1-E safety gate).
            if not force:
                dirty = _check_dirty_tree(tool_dir)
                if dirty:
                    _print_dirty_refusal(tool_name, tool_dir, dirty, command)
                    return 1
            # Remove the submodule working tree recoverably via the
            # constitutional core.safedel primitive (#38 / item 3.5-10);
            # --immediate skips the backup as a deliberate choice.
            rc, trash_folder = _remove_tool_dir(
                tool_dir, tool_name=tool_name, command=command,
                force=force, immediate=immediate,
            )
            if rc != 0:
                return 1
            # `state` was EMBEDDED or SUBMODULE here (a real dir, not a link).
            removed_form = state

    # Create symlink
    link_mode = create_link(dev_path, tool_dir)
    if link_mode is None:
        print(f"Error: Could not create link to {dev_path}",
              file=sys.stderr)
        return 1

    # Remember dev path for future toggles
    _remember_dev_path(qualified, dev_path, project_root)

    # Record the restore origin (#37) now that the symlink is in place. Only
    # for a destroyed on-disk form (EMBEDDED/SUBMODULE) -- a tool that was
    # already a symlink returned early above. For EMBEDDED the trash folder is
    # the recovery pointer; for SUBMODULE restore re-clones from .gitmodules
    # (per the #37 DWP), so trash_folder is intentionally not stored.
    if removed_form in (STATE_EMBEDDED, STATE_SUBMODULE):
        _record_origin(
            qualified, removed_form, project_root,
            trash_folder=(trash_folder if removed_form == STATE_EMBEDDED
                          else None),
            original_path=tool_dir,
        )

    print(f"Switched to DEV mode ({link_mode})")
    print(f"  {tool_dir} -> {dev_path}")
    return 0


def _switch_to_publish(project, project_root, gitmodules, dry_run, force,
                       url=None, *, tools_dir, command, schema=None,
                       immediate=False):
    """Switch a tool from dev mode (symlink) to publish mode (submodule).

    Threads ``tools_dir``, ``command``, and ``schema`` through to the
    parameterized inner calls (BLOCKERs F2/F4/F5/F7/F8). ``force``
    overrides the dirty-tree safety gate at the destructive `rmtree`
    (T1-E).
    """
    tool_dir = project.directory
    tool_name = project.name
    namespace = project.namespace

    state = detect_tool_state(
        tool_dir, gitmodules, project_root, tools_dir=tools_dir
    )
    if state == STATE_SUBMODULE:
        print("Already in publish mode (submodule).")
        return 0

    rel_key = _tool_dir_to_submodule_path(
        tool_dir, project_root, tools_dir=tools_dir
    )
    if not rel_key:
        rel_key = f"{tools_dir.rstrip('/')}/{namespace}/{tool_name}"

    has_submodule = rel_key in gitmodules

    # Cache the manifest before switching — the remote version may not
    # have the per-tool manifest yet, so we preserve it for future discovery
    qualified = f"{namespace}:{tool_name}"
    if project.name:
        cache_manifest(project_root, qualified, project)

    if not has_submodule:
        # First-time: need to register the submodule
        remote_url = _resolve_remote_url(project, url, schema=schema)
        if not remote_url:
            print(f"Error: No remote URL known for '{tool_name}'.",
                  file=sys.stderr)
            print(f"  Provide one with: {command} mode switch <tool> "
                  "--publish --url <url>", file=sys.stderr)
            print("  Or add to the tool manifest:", file=sys.stderr)
            print('    "source": {"url": "<url>"}', file=sys.stderr)
            return 1

        if dry_run:
            if is_linked_project(tool_dir):
                print(f"  Would remove symlink: {tool_dir}")
            elif os.path.isdir(tool_dir):
                dirty = _check_dirty_tree(tool_dir)
                if dirty and not force:
                    print(f"  [WARNING] Would refuse: {tool_dir} has "
                          "uncommitted changes (rerun with --force).")
            print(f"  Would run: git submodule add {remote_url} "
                  f"{rel_key}")
            print("  Note: .gitmodules will be updated (uncommitted)")
            return 0

        # Remove existing link/dir before git submodule add
        if is_linked_project(tool_dir):
            if not remove_link(tool_dir):
                print(f"Error: Could not remove symlink at {tool_dir}",
                      file=sys.stderr)
                return 1
        elif os.path.isdir(tool_dir):
            # Refuse if the working tree has uncommitted changes that
            # an rmtree would silently destroy (T1-E safety gate).
            if not force:
                dirty = _check_dirty_tree(tool_dir)
                if dirty:
                    _print_dirty_refusal(tool_name, tool_dir, dirty, command)
                    return 1
            # Remove the existing dir recoverably before submodule add via
            # the constitutional core.safedel primitive (#38 / item 3.5-10);
            # --immediate skips the backup as a deliberate choice.
            rc, _ = _remove_tool_dir(
                tool_dir, tool_name=tool_name, command=command,
                force=force, immediate=immediate,
            )
            if rc != 0:
                return 1

        # Register and clone the submodule
        try:
            result = subprocess.run(
                ["git", "-C", project_root, "submodule", "add",
                 remote_url, rel_key],
                capture_output=True, text=True, timeout=GIT_CLONE_TIMEOUT,
                env=sanitized_git_env(),
            )
            if result.returncode != 0:
                print(f"Error: git submodule add failed: "
                      f"{result.stderr.strip()}", file=sys.stderr)
                return 1
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Error: git submodule add failed: {exc}",
                  file=sys.stderr)
            return 1

        # Intentional move to publish -- drop any stale dev-restore origin (#37).
        _clear_origin(qualified, project_root)
        print("Switched to REMOTE mode (submodule - first time)")
        print(f"  {remote_url}")
        print("  Note: .gitmodules updated (uncommitted)")
        return 0

    # Existing submodule — just restore it
    submodule_path = rel_key

    if dry_run:
        if is_linked_project(tool_dir):
            print(f"  Would remove symlink: {tool_dir}")
        print(f"  Would run: git submodule update --init {submodule_path}")
        return 0

    # Remove symlink
    if is_linked_project(tool_dir):
        if not remove_link(tool_dir):
            print(f"Error: Could not remove symlink at {tool_dir}",
                  file=sys.stderr)
            return 1

    # Restore submodule
    try:
        result = subprocess.run(
            ["git", "-C", project_root, "submodule", "update", "--init",
             submodule_path],
            capture_output=True, text=True, timeout=GIT_UPDATE_TIMEOUT,
            env=sanitized_git_env(),
        )
        if result.returncode != 0:
            print(f"Error: git submodule update failed: "
                  f"{result.stderr.strip()}", file=sys.stderr)
            return 1
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Error: git submodule update failed: {exc}",
              file=sys.stderr)
        return 1

    # Intentional move to publish -- drop any stale dev-restore origin (#37).
    _clear_origin(qualified, project_root)
    print("Switched to REMOTE mode (submodule)")
    print(f"  {gitmodules[rel_key]['url']}")
    return 0


def _resolve_remote_url(project, explicit_url=None, *, schema=None):
    """Resolve remote URL for a tool from its manifest.

    Resolution order:
    1. ``explicit_url`` argument (``--url`` flag).
    2. Each path in ``schema.remote_url_paths`` (dotted lookup into the
       project manifest), in order. First non-empty value wins.
    3. ``lifecycle.graduated_to`` (always tried as a final fallback;
       semantically meaningful across schemas).
    4. ``None``.

    BLOCKER F7 fix: callers pass an ``AggregatorSchema`` (or dict-like
    object) describing where the remote URL lives in their manifest
    layout. When ``schema`` is ``None`` (e.g., tests or ad-hoc callers),
    the default is ``("source.url",)`` -- matches dazzlecmd's historical
    behavior byte-for-byte.

    Args:
        project: The tool's parsed manifest dict.
        explicit_url: User-supplied URL (optional).
        schema: ``AggregatorSchema`` (or duck-typed object) with a
            ``remote_url_paths`` attribute/key listing dotted paths to try.
            Falls back to ``("source.url",)``.

    Returns:
        Resolved URL string or ``None``.
    """
    if explicit_url:
        return explicit_url

    # ``project`` may be a DazzleEntity; its nested manifest blocks (source,
    # lifecycle) live in extra. ``_dotted_lookup`` walks plain dicts, so resolve
    # against the manifest projection. (Pre-entity-migration this was a raw dict
    # and worked; entities silently returned None here -- e.g. `dz mode switch
    # <tool> --publish` without --url couldn't read source.url. This restores
    # it for entity AND dict callers.)
    manifest = project.to_manifest() if hasattr(project, "to_manifest") else project

    # Determine the list of dotted paths to probe.
    default_paths = ("source.url",)
    if schema is None:
        remote_paths = default_paths
    else:
        # Accept dataclass-like object or dict
        remote_paths = getattr(
            schema, "remote_url_paths",
            schema.get("remote_url_paths") if isinstance(schema, dict)
            else default_paths
        )

    for dotted in remote_paths:
        value = _dotted_lookup(manifest, dotted)
        if value:
            return value

    # Historical fallback that's outside the configurable paths because
    # it represents tool-graduation semantics, not manifest layout.
    lifecycle = manifest.get("lifecycle", {})
    if lifecycle.get("graduated_to"):
        return lifecycle["graduated_to"]

    return None


def _dotted_lookup(obj, dotted_path):
    """Walk a dotted path into a nested dict. Returns the value or ``None``.

    Example: ``_dotted_lookup({"source": {"url": "git@..."}}, "source.url")``
    returns ``"git@..."``.
    """
    current = obj
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _remember_dev_path(qualified_name, dev_path, project_root):
    """Save a dev path to mode_local.json for future toggles."""
    local_config = load_local_config(project_root)
    local_config[qualified_name] = dev_path
    save_local_config(project_root, local_config)


def _record_origin(qualified, prior_state, project_root,
                   trash_folder=None, original_path=None):
    """Record a tool's pre-switch on-disk form in ``mode_local.json['origins']``.

    Called from ``_switch_to_dev`` AFTER the dev symlink is created, so a swap
    that aborted partway never leaves a phantom origin. The record is what
    ``dz mode restore <tool>`` reads to re-materialize the prior form (#37):

    - ``prior_state``  -- ``STATE_EMBEDDED`` or ``STATE_SUBMODULE`` (the form
      before the switch). Drives the restore MECHANISM: EMBEDDED -> recover the
      backed-up content from the safedel trash; SUBMODULE -> re-clone via
      ``git submodule update --init`` (no trash needed).
    - ``trash_folder`` -- the ``TrashResult.folder_name`` from the safedel
      backup (EMBEDDED case only; ``None`` for SUBMODULE, which is
      reconstructible from ``.gitmodules``).
    - ``original_path`` -- the ``tool_dir`` at switch time. Cross-check: if the
      tool was later renamed, this won't match the current dir and restore warns.

    Overwrites any prior origin for ``qualified`` (flat dict, one record per
    tool -- multi-level undo is a future schema, see the #37 DWP).
    """
    import datetime
    data = _load_full_config(project_root)
    data.setdefault("origins", {})[qualified] = {
        "prior_state": prior_state,
        "trash_folder": trash_folder,
        "original_path": original_path,
        "switch_timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _save_full_config(project_root, data)


def _clear_origin(qualified, project_root):
    """Drop a tool's origin record from ``mode_local.json['origins']`` (#37).

    Called when an origin becomes stale: after ``dz mode restore`` succeeds (the
    tool is back to its prior form), or when the user intentionally overrides the
    origin by forcing a direction (``mode switch --dev``/``--publish``) or lands
    in publish mode. A no-op when no record exists.
    """
    data = _load_full_config(project_root)
    if data.setdefault("origins", {}).pop(qualified, None) is not None:
        _save_full_config(project_root, data)


def _dry_run_save_path(qualified_name, dev_path, project_root):
    """Show what path would be saved in dry-run mode."""
    print(f"  Would save dev path to mode_local.json: "
          f"{qualified_name} -> {dev_path}")


# Mode state -> the "mode" a rebind would invert to. Only the two in-orbit
# states map to a mode; out-of-orbit states have no inverse mode (one-way entry).
_STATE_TO_MODE = {STATE_SUBMODULE: "publish", STATE_SYMLINK: "dev"}


@dataclass
class ModeRebindContext:
    """A ``RebindContext`` for dev<->publish mode switching (the filesystem
    coupling change) -- the second ``rebind`` sub-kind after alias.

    The first PERSISTENT rebind: the filesystem IS the store, so no separate
    persistence layer is needed (unlike alias rebind, which is in-memory only).

    The conserved invariant (C2) is the REMOTE URL: publish is a submodule
    re-derivable from it, so ``publish<->dev`` reverses WITHIN the orbit
    (SUBMODULE<->SYMLINK). The criticality predicate is invariant-DERIVABILITY,
    NOT a state blocklist (DWP hole-review H3): if ``_resolve_remote_url`` yields
    nothing, the published state can't be restored -> ``CriticalityBoundaryError``.
    Entering the orbit from EMBEDDED/LOCAL_ONLY is permitted (when a URL is
    derivable) but ONE-WAY -> the receipt's ``reversible`` is False.

    Delegates the actual switch to the existing ``_switch_to_dev`` /
    ``_switch_to_publish`` (so ``entity.py`` stays decoupled from the filesystem
    layer); a non-zero exit code is surfaced as ``RebindError``.
    """

    project_root: str
    tools_dir: str = "projects"
    command: str = "dz"
    schema: Any = None
    dev_path: Optional[str] = None      # explicit dev path (dev direction)
    explicit_url: Optional[str] = None  # explicit remote URL (publish direction)
    dry_run: bool = False
    force: bool = False

    def apply(self, entity, target: str) -> RebindReceipt:
        if target not in ("dev", "publish"):
            raise ValueError(
                f"mode rebind target must be 'dev' or 'publish', got {target!r}"
            )
        # Criticality (C2 invariant-derivability): the conserved quantity for
        # dev<->publish is the remote URL. Checked BEFORE any filesystem touch --
        # if it can't be derived, publish can't be restored, so refuse.
        remote_url = _resolve_remote_url(entity, self.explicit_url, schema=self.schema)
        if remote_url is None:
            raise CriticalityBoundaryError(
                f"rebind({target!r}) refused for {entity.fqcn}: no remote URL "
                f"derivable -- the dev<->publish invariant (the remote) cannot "
                f"be preserved, so the transition would be irreversible."
            )

        gitmodules = parse_gitmodules(self.project_root, tools_dir=self.tools_dir)
        state = detect_tool_state(
            entity.directory, gitmodules, self.project_root, tools_dir=self.tools_dir
        )
        in_orbit = state in (STATE_SUBMODULE, STATE_SYMLINK)
        prior_mode = _STATE_TO_MODE.get(state)

        if target == "dev":
            rc = _switch_to_dev(
                entity, self.project_root, gitmodules, self.dev_path,
                self.dry_run, self.force,
                tools_dir=self.tools_dir, command=self.command,
            )
        else:
            rc = _switch_to_publish(
                entity, self.project_root, gitmodules, self.dry_run, self.force,
                url=self.explicit_url,
                tools_dir=self.tools_dir, command=self.command, schema=self.schema,
            )
        if rc != 0:
            raise RebindError(
                f"mode rebind({target!r}) failed for {entity.fqcn} (exit {rc})"
            )

        # Capture the entity so undo() can re-drive the inverse switch: unlike
        # the alias context (whose subject -- the alias -- is fixed at
        # construction), the mode context receives its subject at apply time, and
        # the filesystem substrate is keyed by the entity's directory.
        self._applied_entity = entity
        return RebindReceipt(
            entity_fqcn=entity.fqcn,        # C1 -- unchanged by the rebind
            sub_kind="mode-switch",
            previous_state=prior_mode,      # rebind(prior_mode) inverts, iff reversible
            new_state=target,
            invariant=RebindInvariant(
                conserved_quantity_name="remote_url",
                conserved_value=remote_url,
                restore_path="re-derived from .gitmodules / source.url / lifecycle.graduated_to",
            ),
            reversible=in_orbit,
        )

    def undo(self, receipt) -> RebindReceipt:
        """Invert a prior ``apply``: switch back to ``receipt.previous_state``
        (the prior mode), iff the transition was reversible.

        A one-way entry into the orbit (EMBEDDED/LOCAL_ONLY -> publish/dev,
        ``reversible=False``) is a mini-graduation and cannot be auto-inverted ->
        ``CriticalityBoundaryError``. Re-drives the same mechanism on the entity
        captured at ``apply`` time (the substrate is the filesystem, keyed by the
        entity's directory), so ``undo`` must follow an ``apply`` on this context.
        """
        if not receipt.reversible:
            short = receipt.entity_fqcn.split(":")[-1]
            raise CriticalityBoundaryError(
                f"cannot undo mode rebind for {receipt.entity_fqcn}: the transition "
                f"was one-way (reversible=False) -- entering the orbit from outside "
                f"is not auto-invertible by this context (which drives the in-orbit "
                f"dev<->publish mechanism). If the prior form was an embedded "
                f"directory, recover it with '{self.command} mode restore {short}' "
                f"(#37); a LOCAL_ONLY entry has nothing to recover."
            )
        entity = getattr(self, "_applied_entity", None)
        if entity is None:
            raise RebindError(
                "ModeRebindContext.undo() requires a prior apply() on this context "
                "(the entity to invert was not captured)."
            )
        return self.apply(entity, receipt.previous_state)
