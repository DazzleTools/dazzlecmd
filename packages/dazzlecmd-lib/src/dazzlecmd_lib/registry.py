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


# Shell profiles: per-shell dispatch characteristics.
#
# Each profile defines how a shell is invoked for the four dispatch modes:
# run a script file, run a command string, keep the shell open, and chain
# env-source + tool script. Profiles are consulted by ``make_shell_runner``
# to build argv at dispatch time.
#
# Fields:
#   script_flag      - flag to invoke a script file (None means "just pass
#                      the script path after the shell binary"). Example:
#                      cmd needs "/c", pwsh needs "-File", bash needs None.
#   string_flag      - flag that treats the next arg as a command string to
#                      execute. Example: bash "-c", cmd "/c", pwsh "-Command".
#                      Used when env-chain is declared (combined string).
#   interactive_flag - flag that keeps the shell open after running (cmd "/k",
#                      pwsh "-NoExit"). None means interactive=true is not
#                      supported for this shell.
#   source_template  - how to source/invoke an env script; {script} and
#                      {args_space} placeholders. None means shell_env is not
#                      supported (e.g., perl).
#   chain_sep        - separator between env-source and tool script (cmd/bash
#                      "&&", pwsh ";").
#   needs_shell_true - whether chained command string requires subprocess
#                      shell=True (cmd's && operator needs it; bash's doesn't).
SHELL_PROFILES = {
    "cmd": {
        "script_flag": "/c",
        "string_flag": "/c",
        "interactive_flag": "/k",
        "source_template": "{script}{args_space}",
        "chain_sep": " && ",
        "needs_shell_true": True,
    },
    "bash": {
        "script_flag": None,
        "string_flag": "-c",
        "interactive_flag": "-i",
        "source_template": "source {script}{args_space}",
        "chain_sep": " && ",
        "needs_shell_true": False,
    },
    "sh": {
        "script_flag": None,
        "string_flag": "-c",
        "interactive_flag": None,
        "source_template": ". {script}{args_space}",
        "chain_sep": " && ",
        "needs_shell_true": False,
    },
    "zsh": {
        "script_flag": None,
        "string_flag": "-c",
        "interactive_flag": "-i",
        "source_template": "source {script}{args_space}",
        "chain_sep": " && ",
        "needs_shell_true": False,
    },
    "csh": {
        "script_flag": None,
        "string_flag": "-c",
        "interactive_flag": None,
        "source_template": "source {script}{args_space}",
        "chain_sep": " && ",
        "needs_shell_true": False,
    },
    "pwsh": {
        "script_flag": "-File",
        "string_flag": "-Command",
        "interactive_flag": "-NoExit",
        "source_template": ". {script}{args_space}",
        "chain_sep": "; ",
        "needs_shell_true": False,
    },
    "powershell": {
        "script_flag": "-File",
        "string_flag": "-Command",
        "interactive_flag": "-NoExit",
        "source_template": ". {script}{args_space}",
        "chain_sep": "; ",
        "needs_shell_true": False,
    },
    # Note: perl, ruby, lua, php, R, and other scripting-language interpreters
    # are NOT shells and do not belong here. They fail the "shell criteria":
    # no chain operators, no source/dot-source syntax, no interactive
    # keep-open semantics, not commonly invoked as a user shell. Use
    # ``runtime.type: "script"`` with ``interpreter: "<name>"`` for those.
}


def _format_source(template, script, args):
    """Render a source_template with script + args."""
    args_space = ""
    if args:
        args_space = " " + " ".join(str(a) for a in args)
    return template.format(script=script, args_space=args_space)


def make_shell_runner(project):
    """Create a runner for shell scripts with rich per-shell semantics.

    Manifest fields (all under ``runtime``):

    - ``shell`` (required): one of ``SHELL_PROFILES`` keys (cmd, bash, sh, zsh,
      csh, pwsh, powershell, perl). Unsupported shells error at dispatch.
    - ``script_path`` (required): the tool script to run
    - ``shell_args`` (list, optional): flags inserted between shell and script.
      When present, **replaces** the default exec flag entirely. Example:
      ``["/E:ON", "/V:ON", "/c"]`` for cmd with extensions + delayed expansion.
      When absent, the profile's ``exec_flag`` (or ``interactive_flag`` when
      ``interactive`` is truthy) is used.
    - ``shell_env`` (dict, optional): env-setup script chained before the tool
      script. Shape: ``{"script": "<path>", "args": [...]}``. The engine uses
      the profile's ``source_template`` + ``chain_sep`` to build a combined
      command. Error if the shell's profile has ``source_template=None``
      (e.g., perl).
    - ``interactive`` (bool or str "exec", optional; default False):
        * ``False``: normal dispatch. subprocess.run with ``exec_flag``.
        * ``True``: use ``interactive_flag`` so the shell stays open after the
          tool runs (user must ``exit`` to return). subprocess.run blocks.
          Error if the shell's profile has ``interactive_flag=None``.
        * ``"exec"``: hand off via ``os.execvp`` — dz process is replaced by
          the shell. No return to dz. Platform caveat: on Windows, Python
          emulates exec by spawning and exiting, so PIDs differ.
    """
    runtime = project.get("runtime", {})
    script_path = runtime.get("script_path")
    shell = runtime.get("shell", "bash")
    shell_args = runtime.get("shell_args")
    shell_env = runtime.get("shell_env")
    interactive = runtime.get("interactive", False)
    tool_dir = project["_dir"]

    def runner(argv):
        if not script_path:
            print(f"Error: No script_path for shell tool {project['name']}", file=sys.stderr)
            return 1

        profile = SHELL_PROFILES.get(shell)
        if profile is None:
            supported = ", ".join(sorted(SHELL_PROFILES.keys()))
            print(
                f"Error: Unknown shell '{shell}' for {project['name']}. "
                f"Supported shells: {supported}. "
                f"For scripting-language interpreters (perl, ruby, lua, "
                f"etc.), use runtime.type: \"script\" with interpreter: "
                f"\"{shell}\" instead.",
                file=sys.stderr,
            )
            return 1

        full_path = os.path.join(tool_dir, script_path)
        if not os.path.isfile(full_path):
            print(f"Error: Script not found: {full_path}", file=sys.stderr)
            return 1

        # Validate interactive mode up-front
        if (interactive is True or interactive == "exec") and profile["interactive_flag"] is None:
            print(
                f"Error: interactive mode not supported for shell '{shell}'. "
                f"Supported interactive shells: cmd, bash, zsh, pwsh, powershell",
                file=sys.stderr,
            )
            return 1

        # Build the command. Four dispatch paths:
        #   (a) shell_env declared -> always use string_flag with combined command
        #   (b) shell_args provided -> user controls flags; pass script path after
        #   (c) interactive -> use interactive_flag with script path
        #   (d) default -> script_flag (may be None) with script path
        if shell_env is not None:
            if profile["source_template"] is None:
                print(
                    f"Error: shell_env not supported for shell '{shell}'. "
                    f"Supported: cmd, bash, sh, zsh, csh, pwsh, powershell",
                    file=sys.stderr,
                )
                return 1
            env_script = shell_env.get("script")
            env_args = shell_env.get("args", [])
            if not env_script:
                print(
                    f"Error: shell_env must include 'script' field for {project['name']}",
                    file=sys.stderr,
                )
                return 1
            env_cmd = _format_source(profile["source_template"], env_script, env_args)
            tool_cmd = " ".join([full_path] + [str(a) for a in argv])
            combined = env_cmd + profile["chain_sep"] + tool_cmd
            if shell_args is not None:
                # User-provided flags; append combined command as final arg
                cmd = [shell] + list(shell_args) + [combined]
            elif interactive is True or interactive == "exec":
                cmd = [shell, profile["interactive_flag"], combined]
            else:
                cmd = [shell, profile["string_flag"], combined]
            use_shell_true = profile["needs_shell_true"]
        else:
            # No env chain: run script directly
            if shell_args is not None:
                cmd = [shell] + list(shell_args) + [full_path] + list(argv)
            elif interactive is True or interactive == "exec":
                cmd = [shell, profile["interactive_flag"], full_path] + list(argv)
            elif profile["script_flag"] is not None:
                cmd = [shell, profile["script_flag"], full_path] + list(argv)
            else:
                # Shells where invoking a script takes no flag (bash, sh, zsh, csh, perl)
                cmd = [shell, full_path] + list(argv)
            use_shell_true = False

        # Hand off via os.execvp (interactive=="exec"): dz process is replaced
        if interactive == "exec":
            try:
                os.execvp(cmd[0], cmd)
                # execvp does not return on success
            except OSError as exc:
                print(f"Error: execvp failed: {exc}", file=sys.stderr)
                return 1

        # Normal dispatch (interactive=False) or blocking keep-open (interactive=True)
        if use_shell_true:
            # cmd.exe && chaining requires shell=True to interpret the operator
            result = subprocess.run(" ".join(cmd), shell=True, cwd=os.getcwd())
        else:
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
    """Create a runner for compiled binary executables.

    Dispatch precedence:

    1. If ``DAZZLECMD_FORCE_DEV=1`` and ``dev_command`` is set, always
       use ``dev_command`` regardless of whether the binary exists.
       Useful during active development (``cargo run``, ``go run``, etc.).
    2. If ``runtime.script_path`` (the binary path) exists on disk, run it.
    3. If the binary does NOT exist but ``dev_command`` is set, fall back
       to ``dev_command``.  This handles the "hasn't been compiled yet"
       case for Rust/C/Go workflows.
    4. Otherwise, error with "Binary not found".

    Manifest example::

        {
            "runtime": {
                "type": "binary",
                "script_path": "target/release/my-tool",
                "dev_command": "cargo run --"
            }
        }
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

        # Force dev mode via env var (active development override)
        force_dev = os.environ.get("DAZZLECMD_FORCE_DEV", "").strip() == "1"
        if force_dev and dev_command:
            import shlex
            cmd = shlex.split(dev_command) + list(argv)
            result = subprocess.run(cmd, cwd=tool_dir)
            return result.returncode

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
