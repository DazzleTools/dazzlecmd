"""Extensible runtime dispatch registry for dazzlecmd-pattern aggregators.

The ``RunnerRegistry`` replaces the hard-coded ``if/elif`` chain in
``resolve_entry_point()`` with a class-based registry where each runtime
type maps to a factory function. Built-in types are registered at import
time; extension types can be registered by kits or third-party code.

Each factory is a **dumb dispatcher**: it reads the manifest, constructs
the subprocess command, and returns a callable. No build logic, no
dependency management, no environment setup.
"""

import importlib
import inspect
import os
import subprocess
import sys


class RunnerRegistry:
    """Registry mapping runtime type names to runner factory functions.

    Usage::

        RunnerRegistry.register("docker", make_docker_runner)
        runner = RunnerRegistry.resolve(project)
        if runner:
            exit_code = runner(argv)
    """

    _factories = {}

    @classmethod
    def register(cls, runtime_type, factory_fn):
        """Register a runner factory for a runtime type.

        Args:
            runtime_type: String matching ``runtime.type`` in manifests
                          (e.g., ``"python"``, ``"docker"``, ``"node"``).
            factory_fn: Callable ``(project_dict) -> runner_callable``.
                        The runner callable accepts ``(argv)`` and returns
                        an int exit code.
        """
        cls._factories[runtime_type] = factory_fn

    @classmethod
    def resolve(cls, project):
        """Resolve a project's runtime to a callable runner.

        Reads ``project["runtime"]["type"]`` (default: ``"python"``),
        looks up the registered factory, and returns a runner callable.
        Returns ``None`` if no factory is registered for the type.
        """
        runtime = project.get("runtime", {})
        runtime_type = runtime.get("type", "python")

        factory = cls._factories.get(runtime_type)
        if factory:
            return factory(project)

        print(
            f"Warning: Unknown runtime type '{runtime_type}' for {project.get('name', '?')}",
            file=sys.stderr,
        )
        return None

    @classmethod
    def registered_types(cls):
        """Return the set of currently registered runtime type names."""
        return set(cls._factories.keys())


# ---------------------------------------------------------------------------
# Built-in runner factories (public API — kits may extend or wrap these)
# ---------------------------------------------------------------------------


def make_python_runner(project):
    """Create a runner for Python tools (direct import or subprocess).

    Supports two import modes:

    1. **Package mode** (``runtime.module`` set, or ``__init__.py`` detected):
       imports the module as a dotted package path with the tool directory
       on ``sys.path``. Enables relative imports within the package.

    2. **Flat mode** (default): imports just the script basename with the
       script's parent directory on ``sys.path``.

    For ``pass_through: true`` tools, delegates to
    ``make_subprocess_runner`` instead.
    """
    if project.get("pass_through", False):
        return make_subprocess_runner(project)

    runtime = project.get("runtime", {})
    entry_point = runtime.get("entry_point", "main")
    script_path = runtime.get("script_path")
    module_path = runtime.get("module")
    tool_dir = project["_dir"]

    def runner(argv):
        if script_path:
            full_path = os.path.join(tool_dir, script_path)

            # Determine import mode
            use_module = module_path
            if not use_module:
                parent_dir = os.path.dirname(full_path)
                if os.path.isfile(os.path.join(parent_dir, "__init__.py")):
                    rel_path = script_path.replace("\\", "/")
                    if rel_path.endswith(".py"):
                        rel_path = rel_path[:-3]
                    use_module = rel_path.replace("/", ".")

            if use_module:
                if tool_dir not in sys.path:
                    sys.path.insert(0, tool_dir)

                if "." not in use_module and script_path and "/" in script_path.replace("\\", "/"):
                    script_basename = os.path.splitext(os.path.basename(script_path))[0]
                    use_module = f"{use_module}.{script_basename}"

                try:
                    mod = importlib.import_module(use_module)
                except ImportError as exc:
                    print(f"Error: Could not import {use_module}: {exc}", file=sys.stderr)
                    return 1
            else:
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
                    f"Error: {mod.__name__} has no '{entry_point}' function",
                    file=sys.stderr,
                )
                return 1

            old_argv = sys.argv
            sys.argv = [project["name"]] + list(argv)
            try:
                result = func(argv) if _accepts_args(func) else func()
                return result if isinstance(result, int) else 0
            finally:
                sys.argv = old_argv
        return 1

    return runner


def make_subprocess_runner(project):
    """Create a runner for Python pass-through tools (subprocess dispatch).

    Supports module mode (``python -m module``) for package-structured
    tools with relative imports, and script mode (``python script.py``)
    for flat scripts.
    """
    runtime = project.get("runtime", {})
    script_path = runtime.get("script_path")
    module_path = runtime.get("module")
    tool_dir = project["_dir"]

    def runner(argv):
        use_module = module_path
        if not use_module and script_path:
            full_path = os.path.join(tool_dir, script_path)
            parent_dir = os.path.dirname(full_path)
            if os.path.isfile(os.path.join(parent_dir, "__init__.py")):
                rel_path = script_path.replace("\\", "/")
                if rel_path.endswith(".py"):
                    rel_path = rel_path[:-3]
                use_module = rel_path.replace("/", ".")

        if use_module:
            result = subprocess.run(
                [sys.executable, "-m", use_module] + list(argv),
                cwd=tool_dir,
            )
            return result.returncode

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


def make_shell_runner(project):
    """Create a runner for shell scripts (bash, cmd, pwsh)."""
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
        elif shell in ("pwsh", "powershell"):
            cmd = ["pwsh", "-File", full_path] + list(argv)
        else:
            cmd = [shell, full_path] + list(argv)

        result = subprocess.run(cmd, cwd=os.getcwd())
        return result.returncode

    return runner


def make_script_runner(project):
    """Create a runner for scripts with an explicit interpreter."""
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


def make_binary_runner(project):
    """Create a runner for binary executables.

    Supports a ``dev_command`` fallback for development mode (e.g.,
    ``cargo run --`` when the release binary doesn't exist yet).
    """
    runtime = project.get("runtime", {})
    script_path = runtime.get("script_path")
    dev_command = runtime.get("dev_command")
    tool_dir = project["_dir"]

    def runner(argv):
        if not script_path:
            print(f"Error: No binary path for {project['name']}", file=sys.stderr)
            return 1
        full_path = os.path.join(tool_dir, script_path)

        if os.path.isfile(full_path):
            result = subprocess.run(
                [full_path] + list(argv),
                cwd=os.getcwd(),
            )
            return result.returncode

        # Dev-mode fallback: binary not built yet, use dev_command
        if dev_command:
            import shlex
            cmd = shlex.split(dev_command) + list(argv)
            result = subprocess.run(cmd, cwd=tool_dir)
            return result.returncode

        print(f"Error: Binary not found: {full_path}", file=sys.stderr)
        return 1

    return runner


def _accepts_args(func):
    """Check if a function accepts arguments (beyond self)."""
    try:
        sig = inspect.signature(func)
        params = [
            p for p in sig.parameters.values()
            if p.name != "self"
        ]
        return len(params) > 0
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Register built-in types at import time
# ---------------------------------------------------------------------------

RunnerRegistry.register("python", make_python_runner)
RunnerRegistry.register("shell", make_shell_runner)
RunnerRegistry.register("script", make_script_runner)
RunnerRegistry.register("binary", make_binary_runner)
