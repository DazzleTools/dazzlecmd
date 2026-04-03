"""Kit-aware project discovery and loading for dazzlecmd."""

import json
import os
import sys
import importlib
import subprocess


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

        # Look for in-repo kit manifest (source of truth for tools/structure)
        in_repo = _load_in_repo_kit_manifest(projects_dir, kit_name)

        if in_repo:
            # In-repo manifest is the base; registry overrides activation
            kit = dict(in_repo)
            # Registry overrides these fields only
            if "always_active" in registry:
                kit["always_active"] = registry["always_active"]
            if "source" in registry:
                kit["source"] = registry["source"]
        else:
            # No in-repo manifest -- registry IS the full definition (legacy mode)
            kit = dict(registry)

        kit.setdefault("always_active", False)
        kit.setdefault("tools", [])
        kit["_source"] = filepath
        kit["_kit_name"] = kit_name
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


def get_active_kits(kits):
    """Return kits that should be active.

    Phase 1: all kits are active.
    Future: respect user config for kit selection.
    """
    return list(kits)


def discover_projects(projects_dir, active_kits=None):
    """Walk projects/<namespace>/<tool>/ directories for tool manifests.

    Scans the default projects/ directory, plus any kit-specific tools_dir
    paths declared by active kits. Kits can declare a custom manifest
    filename via the "manifest" field (default: ".dazzlecmd.json").

    Returns a list of project dicts with resolved metadata.
    Each project dict has at minimum: name, namespace, description, runtime, _dir.

    If active_kits is provided, only projects listed in active kits are returned.
    If active_kits is None, all discovered projects are returned.
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
            manifest_name = kit.get("manifest", ".dazzlecmd.json")
            for tool_ref in kit.get("tools", []):
                kit_tools.add(tool_ref)
                # Track manifest name per namespace
                if ":" in tool_ref:
                    ns = tool_ref.split(":")[0]
                    kit_manifest_names[ns] = manifest_name

            # If kit declares a tools_dir, queue it for scanning
            tools_dir = kit.get("tools_dir")
            if tools_dir:
                abs_tools_dir = os.path.join(project_root, tools_dir)
                if os.path.isdir(abs_tools_dir):
                    extra_tool_dirs.append((abs_tools_dir, manifest_name))

    # Scan default projects/<namespace>/<tool>/
    _scan_tool_dirs(projects_dir, ".dazzlecmd.json", kit_tools,
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
    # Track already-discovered tool names to avoid duplicates from
    # multiple scan paths
    seen = {p["name"] for p in projects}

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

            if tool_name in seen:
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
                seen.add(tool_name)
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


def _load_cached_manifest(projects_dir, namespace, tool_name, tool_dir):
    """Try to load a tool's manifest from the mode cache.

    When a tool is in remote/submodule mode and the remote repo doesn't
    include .dazzlecmd.json, the manifest was cached in mode_local.json
    during the switch. This function retrieves it so the tool remains
    discoverable by dz list and other commands.
    """
    try:
        from dazzlecmd.mode import get_cached_manifest
        project_root = os.path.dirname(projects_dir)
        qualified = f"{namespace}:{tool_name}"
        cached = get_cached_manifest(project_root, qualified)
        if cached is None:
            return None
        # Apply same defaults as _load_manifest
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

    Returns a function that accepts (argv) and runs the tool, or None if
    the runtime type is not supported.
    """
    runtime = project.get("runtime", {})
    runtime_type = runtime.get("type", "python")
    tool_dir = project["_dir"]

    if runtime_type == "python":
        if project.get("pass_through", False):
            return _make_subprocess_runner(project)
        else:
            return _make_python_runner(project)
    elif runtime_type == "shell":
        return _make_shell_runner(project)
    elif runtime_type == "script":
        return _make_script_runner(project)
    elif runtime_type == "binary":
        return _make_binary_runner(project)
    else:
        print(
            f"Warning: Unknown runtime type '{runtime_type}' for {project['name']}",
            file=sys.stderr,
        )
        return None


def _make_python_runner(project):
    """Create a runner that imports and calls a Python entry point."""
    runtime = project.get("runtime", {})
    entry_point = runtime.get("entry_point", "main")
    script_path = runtime.get("script_path")
    tool_dir = project["_dir"]

    def runner(argv):
        if script_path:
            full_path = os.path.join(tool_dir, script_path)
            module_dir = os.path.dirname(full_path)
            module_name = os.path.splitext(os.path.basename(full_path))[0]

            if module_dir not in sys.path:
                sys.path.insert(0, module_dir)

            try:
                mod = importlib.import_module(module_name)
            except ImportError as exc:
                print(f"Error: Could not import {module_name}: {exc}", file=sys.stderr)
                return 1

            func = getattr(mod, entry_point, None)
            if func is None:
                print(
                    f"Error: {module_name} has no '{entry_point}' function",
                    file=sys.stderr,
                )
                return 1

            # Call with argv — most tools expect sys.argv-style args
            old_argv = sys.argv
            sys.argv = [project["name"]] + list(argv)
            try:
                result = func(argv) if _accepts_args(func) else func()
                return result if isinstance(result, int) else 0
            finally:
                sys.argv = old_argv
        return 1

    return runner


def _make_subprocess_runner(project):
    """Create a runner that calls a Python script via subprocess."""
    runtime = project.get("runtime", {})
    script_path = runtime.get("script_path")
    tool_dir = project["_dir"]

    def runner(argv):
        if not script_path:
            print(f"Error: No script_path for pass-through tool {project['name']}", file=sys.stderr)
            return 1
        full_path = os.path.join(tool_dir, script_path)
        if not os.path.isfile(full_path):
            print(f"Error: Script not found: {full_path}", file=sys.stderr)
            return 1
        result = subprocess.run(
            [sys.executable, full_path] + list(argv),
            cwd=os.getcwd(),
        )
        return result.returncode

    return runner


def _make_shell_runner(project):
    """Create a runner for shell scripts."""
    runtime = project.get("runtime", {})
    script_path = runtime.get("script_path")
    shell = runtime.get("shell", "bash")
    tool_dir = project["_dir"]

    def runner(argv):
        if not script_path:
            print(f"Error: No script_path for shell tool {project['name']}", file=sys.stderr)
            return 1
        full_path = os.path.join(tool_dir, script_path)
        if not os.path.isfile(full_path):
            print(f"Error: Script not found: {full_path}", file=sys.stderr)
            return 1

        if shell == "cmd":
            cmd = ["cmd", "/c", full_path] + list(argv)
        elif shell == "pwsh" or shell == "powershell":
            cmd = ["pwsh", "-File", full_path] + list(argv)
        else:
            cmd = [shell, full_path] + list(argv)

        result = subprocess.run(cmd, cwd=os.getcwd())
        return result.returncode

    return runner


def _make_script_runner(project):
    """Create a runner for scripts with explicit interpreter."""
    runtime = project.get("runtime", {})
    script_path = runtime.get("script_path")
    interpreter = runtime.get("interpreter", "python")
    tool_dir = project["_dir"]

    def runner(argv):
        if not script_path:
            print(f"Error: No script_path for script tool {project['name']}", file=sys.stderr)
            return 1
        full_path = os.path.join(tool_dir, script_path)
        if not os.path.isfile(full_path):
            print(f"Error: Script not found: {full_path}", file=sys.stderr)
            return 1
        result = subprocess.run(
            [interpreter, full_path] + list(argv),
            cwd=os.getcwd(),
        )
        return result.returncode

    return runner


def _make_binary_runner(project):
    """Create a runner for binary executables."""
    runtime = project.get("runtime", {})
    script_path = runtime.get("script_path")
    tool_dir = project["_dir"]

    def runner(argv):
        if not script_path:
            print(f"Error: No binary path for {project['name']}", file=sys.stderr)
            return 1
        full_path = os.path.join(tool_dir, script_path)
        if not os.path.isfile(full_path):
            print(f"Error: Binary not found: {full_path}", file=sys.stderr)
            return 1
        result = subprocess.run(
            [full_path] + list(argv),
            cwd=os.getcwd(),
        )
        return result.returncode

    return runner


def _accepts_args(func):
    """Check if a function accepts arguments (beyond self)."""
    import inspect
    try:
        sig = inspect.signature(func)
        params = [
            p for p in sig.parameters.values()
            if p.name != "self"
        ]
        return len(params) > 0
    except (ValueError, TypeError):
        return False
