"""Extensible runtime dispatch registry for dazzlecmd-pattern aggregators.

The ``RunnerRegistry`` replaces the hard-coded ``if/elif`` chain in
``resolve_entry_point()`` with a class-based registry where each runtime
type maps to a factory function. Built-in types are registered at import
time; extension types can be registered by kits or third-party code.

Each factory is a **dumb dispatcher**: it reads the manifest, constructs
the subprocess command, and returns a callable. No build logic, no
dependency management, no environment setup.

Conditional dispatch (v0.7.19) adds a ``resolve_runtime()`` preprocessor
that inspects ``runtime.platforms`` and ``runtime.prefer`` to produce an
effective runtime block for the current host BEFORE any runner factory
sees the project. Runners stay dumb; the resolver handles platform logic.
"""

import copy
import importlib
import inspect
import os
import shutil
import subprocess
import sys

from dazzlecmd_lib.conditions import evaluate_condition
from dazzlecmd_lib.platform_detect import PlatformInfo, get_platform_info
from dazzlecmd_lib.platform_resolve import deep_merge, resolve_platform_block
from dazzlecmd_lib.resolution_trace import ResolutionTrace
from dazzlecmd_lib.schema_version import check_schema_version


class NoRuntimeResolutionError(RuntimeError):
    """Raised when conditional dispatch cannot pick a dispatch target.

    The message contains the full resolution trace: platform info, each
    prefer entry tried, and why each failed. Authors reading the message
    should see exactly what to add to their manifest to make it work.
    """


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

        Runs ``resolve_runtime()`` first to apply conditional dispatch
        (``runtime.platforms`` + ``runtime.prefer``). The resulting effective
        runtime type is then looked up in the registered factories.

        Returns ``None`` if no factory is registered for the type. Raises
        ``NoRuntimeResolutionError`` when ``prefer`` is declared but no
        entry matches the current host.
        """
        project = resolve_runtime(project)
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
        # CALL prefix is required for env vars set in the env script to
        # propagate to the tool script that follows. Without CALL, cmd
        # invokes the .cmd/.bat as a child process and its environment
        # changes never reach the next step of the && chain.
        "source_template": "CALL {script}{args_space}",
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
            # Resolve relative shell_env.script paths against tool_dir (consistent
            # with runtime.script_path). Absolute paths and anything starting with
            # an env-var expansion (e.g. %USERPROFILE%, $HOME) pass through
            # unchanged so the shell can interpret them.
            if not os.path.isabs(env_script) and not env_script.startswith(("%", "$")):
                candidate = os.path.join(tool_dir, env_script)
                if os.path.isfile(candidate):
                    env_script = candidate
            env_cmd = _format_source(profile["source_template"], env_script, env_args)
            tool_cmd = " ".join([full_path] + [str(a) for a in argv])
            combined = env_cmd + profile["chain_sep"] + tool_cmd

            # In env-chain mode, the shell must interpret the combined command
            # string, which requires the string_flag (e.g. cmd /c, bash -c,
            # pwsh -Command) -- OR the interactive_flag (cmd /k, pwsh -NoExit)
            # if keep-open is requested. `shell_args` (user-supplied pre-exec
            # shell configuration like /E:ON /V:ON) goes BEFORE the exec-style
            # flag, not in place of it. The combined string is the final arg;
            # && / ; chaining is interpreted by the invoked shell itself, not
            # by subprocess -- so no shell=True wrapping.
            if interactive is True or interactive == "exec":
                if profile["interactive_flag"] is None:
                    # Already validated earlier, but belt-and-braces
                    print(
                        f"Error: interactive mode not supported for shell '{shell}'",
                        file=sys.stderr,
                    )
                    return 1
                exec_style_flag = profile["interactive_flag"]
            else:
                exec_style_flag = profile["string_flag"]

            if shell_args is not None:
                # Pre-exec shell config (e.g. /E:ON /V:ON) followed by the
                # exec-style flag and the combined command string. Convention:
                # author should NOT include /c or /k in shell_args when
                # shell_env is declared; engine appends one automatically.
                cmd = [shell] + list(shell_args) + [exec_style_flag, combined]
            else:
                cmd = [shell, exec_style_flag, combined]
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

        # Hand off via os.execvp (interactive=="exec"): dz process is replaced
        if interactive == "exec":
            try:
                os.execvp(cmd[0], cmd)
                # execvp does not return on success
            except OSError as exc:
                print(f"Error: execvp failed: {exc}", file=sys.stderr)
                return 1

        # subprocess.run with list argv: the invoked shell (via its -c / /c /
        # -Command / etc.) interprets && / ; chaining natively. No shell=True
        # wrapping required -- and using shell=True on Windows would double-wrap
        # cmd.exe in an outer cmd /c, breaking env-chain dispatch.
        result = subprocess.run(cmd, cwd=os.getcwd())
        return result.returncode

    return runner


def make_script_runner(project):
    """Create a runner for scripts with an explicit interpreter.

    Supports an optional ``interpreter_args`` field (list) that places
    flags between the interpreter and the script path. Useful for:

    - ``cscript //Nologo //B tool.js`` (Windows JScript/WSH)
    - ``perl -w -T tool.pl`` (taint mode, warnings)
    - ``ruby -r require_this tool.rb``
    - ``lua -E tool.lua``

    When absent, dispatches as ``[interpreter, script, args]`` (original
    behavior preserved).
    """
    runtime = project.get("runtime", {})
    script_path = runtime.get("script_path")
    interpreter = runtime.get("interpreter", "python")
    interpreter_args = runtime.get("interpreter_args", [])
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
            [interpreter] + list(interpreter_args) + [full_path] + list(argv),
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
# Node runtime (Node.js, npm, npx, and alternative JS engines)
# ---------------------------------------------------------------------------

# Node interpreter profiles: per-interpreter dispatch characteristics.
#
# Fields:
#   subcommand - subcommand inserted between interpreter and script
#                (bun/deno use ``run``; node/tsx/ts-node use None)
#
# Unknown interpreters fall through to a generic ``[interp, script, argv]``
# pattern with a stderr warning. Extend this dict for new JS runtimes.
NODE_INTERPRETERS = {
    "node":    {"subcommand": None},
    "tsx":     {"subcommand": None},
    "ts-node": {"subcommand": None},
    "bun":     {"subcommand": "run"},
    "deno":    {"subcommand": "run"},
}


def make_node_runner(project):
    """Create a runner for Node.js ecosystem tools.

    Three mutually-exclusive dispatch modes:

    1. ``script_path``: dispatch ``[interpreter, <subcommand?>, args..., script, argv]``.
       Default interpreter is ``node`` for ``.js``; ``.ts`` files require an
       explicit ``interpreter`` (tsx, ts-node, bun, or deno).
    2. ``npm_script``: dispatch ``npm run <script> -- <argv>``. Reads
       package.json, finds the named script, runs it via shell.
    3. ``npx``: dispatch ``npx <package> <argv>``. One-shot package
       invocation; npx downloads the package on first use.

    Exactly one mode must be declared. Multiple → error.

    Optional ``interpreter_args`` list: flags between interpreter (and
    its subcommand, if any) and the script. Used for deno permissions
    (``--allow-read``), node memory flags (``--max-old-space-size=4096``),
    bun options, etc.
    """
    runtime = project.get("runtime", {})
    script_path = runtime.get("script_path")
    npm_script = runtime.get("npm_script")
    npx_target = runtime.get("npx")
    interpreter = runtime.get("interpreter")
    interpreter_args = runtime.get("interpreter_args", [])
    tool_dir = project["_dir"]

    # Validate mutual exclusion: exactly one dispatch mode
    declared = [
        m for m in ("script_path", "npm_script", "npx")
        if runtime.get(m)
    ]
    if len(declared) == 0:
        def error_runner(argv):
            print(
                f"Error: node runtime for {project['name']} declares no "
                f"dispatch mode. Set exactly one of: script_path, npm_script, npx.",
                file=sys.stderr,
            )
            return 1
        return error_runner
    if len(declared) > 1:
        def error_runner(argv):
            print(
                f"Error: node runtime for {project['name']} declares multiple "
                f"dispatch modes ({', '.join(declared)}). Set exactly one of: "
                f"script_path, npm_script, npx.",
                file=sys.stderr,
            )
            return 1
        return error_runner

    def runner(argv):
        # npm_script mode
        if npm_script:
            cmd = ["npm", "run", npm_script, "--"] + list(argv)
            result = subprocess.run(cmd, cwd=tool_dir)
            return result.returncode

        # npx mode
        if npx_target:
            cmd = ["npx", npx_target] + list(argv)
            result = subprocess.run(cmd, cwd=tool_dir)
            return result.returncode

        # script_path mode.
        #
        # TypeScript detection runs BEFORE file-existence check: declaring a
        # .ts file without an interpreter is a configuration error regardless
        # of whether the script exists yet. Authors writing a new tool get the
        # actionable error ("set runtime.interpreter") instead of the generic
        # "script not found" that would appear if the file check ran first.
        is_typescript = script_path.lower().endswith((".ts", ".tsx", ".mts", ".cts"))
        effective_interpreter = interpreter
        if effective_interpreter is None:
            if is_typescript:
                print(
                    f"Error: TypeScript file '{script_path}' requires an "
                    f"explicit interpreter. Set runtime.interpreter to one of: "
                    f"tsx, ts-node, bun, deno.",
                    file=sys.stderr,
                )
                return 1
            effective_interpreter = "node"

        full_path = os.path.join(tool_dir, script_path)
        if not os.path.isfile(full_path):
            print(f"Error: Script not found: {full_path}", file=sys.stderr)
            return 1

        # Build argv using the interpreter profile
        profile = NODE_INTERPRETERS.get(effective_interpreter)
        if profile is None:
            print(
                f"Warning: Unknown node interpreter '{effective_interpreter}' "
                f"for {project['name']}. Dispatching as "
                f"'{effective_interpreter} <args> <script> <argv>'. "
                f"Known interpreters: {', '.join(sorted(NODE_INTERPRETERS.keys()))}.",
                file=sys.stderr,
            )
            cmd = [effective_interpreter] + list(interpreter_args) + [full_path] + list(argv)
        else:
            prefix = [effective_interpreter]
            if profile["subcommand"]:
                prefix.append(profile["subcommand"])
            cmd = prefix + list(interpreter_args) + [full_path] + list(argv)

        result = subprocess.run(cmd, cwd=tool_dir)
        return result.returncode

    return runner


# ---------------------------------------------------------------------------
# Conditional dispatch resolver
# ---------------------------------------------------------------------------


def _check_prefer_preconditions(entry, tool_dir):
    """Infer preconditions from declared fields and check them.

    Returns (passed: bool, reason: str). Reasons are short and actionable;
    they go into the resolution trace when the entry is rejected.

    Checks (in order):
        - interpreter declared -> must be on PATH
        - npx declared         -> `npx` must be on PATH
        - npm_script declared  -> `npm` must be on PATH
        - script_path declared -> file must exist at resolved path

    Script paths that are absolute are checked as-is. Relative paths are
    joined against tool_dir (consistent with every runner's file lookup).
    """
    interpreter = entry.get("interpreter")
    if interpreter:
        if not shutil.which(interpreter):
            return False, f"interpreter '{interpreter}' not on PATH"

    if entry.get("npx"):
        if not shutil.which("npx"):
            return False, "npx not on PATH"

    if entry.get("npm_script"):
        if not shutil.which("npm"):
            return False, "npm not on PATH"

    script_path = entry.get("script_path")
    if script_path:
        full = script_path if os.path.isabs(script_path) else os.path.join(
            tool_dir or "", script_path
        )
        if not os.path.isfile(full):
            return False, f"script_path '{script_path}' not found"

    return True, "preconditions passed"


def _format_trace_as_error(trace, project):
    """Render a failed-resolution ResolutionTrace into a multi-line error message.

    Rendering lives here (runtime layer) per the design decision that trace
    DATA is shared but RENDERING is per-layer. The setup layer will have its
    own renderer with install-flavored phrasing.
    """
    name = project.get("name", "?")
    pi = trace.platform_info
    lines = [
        f"No runtime dispatch matched for {name!r} on this host.",
        "",
        f"Platform:  {pi.os}" + (f".{pi.subtype}" if pi.subtype else "") +
        f" ({pi.arch})" + (" [wsl]" if pi.is_wsl else ""),
        "",
        "Tried:",
    ]
    for i, a in enumerate(trace.attempts, 1):
        status = "MATCH" if a.passed else "fail"
        lines.append(f"  {i}. [{status}] {a.label} -- {a.reason}")
    lines.append("")
    lines.append(
        "Fix: add a matching `prefer` entry, declare `platforms.<os>.general`, "
        "or install the missing interpreter/command."
    )
    return "\n".join(lines)


def resolve_runtime(project, *, platform_info=None):
    """Preprocess a project's runtime spec for conditional dispatch.

    Returns a project dict whose ``runtime`` key has been replaced with the
    effective block for the current host. The original project is not
    mutated; a shallow copy is returned when resolution changes anything.

    Resolution order:
        1. Validate runtime._schema_version (if declared).
        2. Merge platform overrides via ``resolve_platform_block``.
        3. If the effective runtime has a ``prefer`` array, iterate entries;
           the first entry whose ``detect_when`` (if declared) AND inferred
           preconditions pass is selected and merged into the effective block.
        4. Return the shallow-copied project with the new runtime block.

    The mutual-exclusion invariant (one dispatch mode per runtime block)
    stays the responsibility of each runner factory -- they already enforce
    it and surface clear errors.

    Backwards compatibility: a runtime without ``platforms`` or ``prefer``
    is returned unchanged (fast path).

    Args:
        project: Project dict with ``_dir`` and ``runtime`` keys.
        platform_info: Override for testing; defaults to ``get_platform_info()``.

    Raises:
        NoRuntimeResolutionError: when ``prefer`` is declared and no entry
            matches the current host.
        UnsupportedSchemaVersionError: when ``_schema_version`` is unsupported.
    """
    runtime = project.get("runtime", {})
    if not isinstance(runtime, dict) or not runtime:
        return project

    # Schema version check (cheap; runs on every dispatch)
    check_schema_version(
        runtime, context=f"runtime for {project.get('name', '?')}"
    )

    has_platforms = "platforms" in runtime
    has_prefer = "prefer" in runtime

    if not has_platforms and not has_prefer:
        return project  # fast path

    if platform_info is None:
        platform_info = get_platform_info()

    # Step 1: merge platform overrides into the base runtime
    if has_platforms:
        base_runtime = {k: v for k, v in runtime.items() if k != "platforms"}
        effective = resolve_platform_block(
            base_runtime, runtime["platforms"], platform_info
        )
    else:
        effective = {k: v for k, v in runtime.items() if k != "platforms"}

    # Step 2: prefer iteration (if present in the effective block)
    prefer = effective.get("prefer")
    if prefer is not None:
        if not isinstance(prefer, list):
            raise ValueError(
                f"runtime.prefer must be a list, got {type(prefer).__name__}"
            )
        tool_dir = project.get("_dir", "")
        trace = ResolutionTrace(platform_info=platform_info, layer="runtime")

        for i, entry in enumerate(prefer):
            if not isinstance(entry, dict):
                trace.record(
                    f"prefer[{i}]", passed=False,
                    reason=f"not a dict: {type(entry).__name__}",
                )
                continue

            detect_when = entry.get("detect_when")
            if detect_when is not None:
                if not evaluate_condition(detect_when, platform_info):
                    trace.record(
                        f"prefer[{i}]", passed=False,
                        reason="detect_when did not match",
                        detail=entry,
                    )
                    continue

            ok, reason = _check_prefer_preconditions(entry, tool_dir)
            if not ok:
                trace.record(
                    f"prefer[{i}]", passed=False, reason=reason, detail=entry,
                )
                continue

            label_bits = []
            for k in ("interpreter", "npx", "npm_script", "script_path"):
                if k in entry:
                    label_bits.append(f"{k}={entry[k]}")
                    break
            label = f"prefer[{i}]: " + (label_bits[0] if label_bits else "entry")
            trace.record(label, passed=True, reason="matched", detail=entry)
            break

        if not trace.has_match():
            raise NoRuntimeResolutionError(_format_trace_as_error(trace, project))

        # Merge the selected entry over the effective block (minus prefer and
        # detect_when, which aren't dispatch fields)
        selected = trace.selected().detail or {}
        selected_dispatch = {
            k: v for k, v in selected.items() if k != "detect_when"
        }
        effective_without_prefer = {
            k: v for k, v in effective.items() if k != "prefer"
        }
        effective = deep_merge(effective_without_prefer, selected_dispatch)

    resolved_project = dict(project)
    resolved_project["runtime"] = effective
    return resolved_project


# ---------------------------------------------------------------------------
# Register built-in types at import time
# ---------------------------------------------------------------------------

RunnerRegistry.register("python", make_python_runner)
RunnerRegistry.register("shell", make_shell_runner)
RunnerRegistry.register("script", make_script_runner)
RunnerRegistry.register("binary", make_binary_runner)
RunnerRegistry.register("node", make_node_runner)
