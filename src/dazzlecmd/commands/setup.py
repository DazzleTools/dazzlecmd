"""``dz setup`` -- run a tool's declared setup script.

Moved out of cli.py (decomposition R3, DWP 2026-06-25__16-14-19). The engine
dispatches the tool's own setup.command/setup.script; it never installs deps
itself. cli.py re-exports _cmd_setup. Imports nothing from cli.py.
"""
import os
import sys

from dazzlecmd_lib import colors as _colors

def _cmd_setup(args, engine):
    """Run a tool's declared setup script.

    The engine doesn't install dependencies itself — it dispatches the
    tool's own ``setup.command`` (or platform-specific variant). The tool
    author writes the setup script; the engine runs it when the user asks.
    """
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    tool_name = getattr(args, "tool", None)

    # No tool specified: list tools that have setup declared (v0.7.21 polish).
    # Detection: `setup.command` OR any `setup.platforms.*` present -- catches
    # tools with ONLY platform-specific setup commands (no top-level default).
    if not tool_name:
        source = getattr(engine, "all_projects", engine.projects)

        def _has_setup(p):
            setup = p.setup
            if not setup or not isinstance(setup, dict):
                return False
            if setup.get("command"):
                return True
            platforms = setup.get("platforms")
            if isinstance(platforms, dict) and platforms:
                return True
            return False

        has_setup = [p for p in source if _has_setup(p)]
        if not has_setup:
            print("No tools have setup commands declared.")
            return 0

        # Sort alphabetically by FQCN for stable output
        has_setup.sort(key=lambda p: p.fqcn or p.name or "")

        # Dynamic column width: longest FQCN, with sane floor/ceiling
        max_fqcn_width = max(
            len(p.fqcn or p.name or "") for p in has_setup
        )
        fqcn_width = max(20, min(max_fqcn_width, 50))

        print("Tools with setup declared:")
        for p in has_setup:
            fqcn = p.fqcn or p.name or "?"
            note = (p.setup or {}).get("note") or "-"
            print(f"  {fqcn:<{fqcn_width}}  {note}")
        print(f"\nRun: dz setup <tool> to execute a tool's setup.")
        return 0

    # Resolve the tool name (supports FQCN, kit-qualified, short name,
    # alias FQCN). Context is unused here; setup doesn't surface
    # resolution provenance.
    project, _ctx = engine.resolve_command(tool_name)
    if project is None:
        # Try all_projects for disabled-kit tools
        source = getattr(engine, "all_projects", engine.projects)
        matches = [p for p in source if p.name == tool_name or p.fqcn == tool_name]
        if matches:
            project = matches[0]
        else:
            print(
                _colors.warn(f"Tool '{tool_name}' not found."),
                file=sys.stderr,
            )
            return 1

    if not project.setup:
        print(f"Tool '{project.fqcn or tool_name}' has no setup command declared.")
        print("Add a 'setup' block to the tool's manifest to enable this.")
        return 0

    # Resolve via shared library: applies platforms.<os>.<subtype> fallback,
    # normalizes flat-string platform values to {"command": <str>}, validates
    # _schema_version. See dazzlecmd_lib.setup_resolve.
    from dazzlecmd_lib.setup_resolve import (
        InvalidSetupBlockError,
        resolve_setup_block,
    )
    from dazzlecmd_lib.schema_version import UnsupportedSchemaVersionError
    import json as _json
    try:
        effective = resolve_setup_block(project)
    except InvalidSetupBlockError as exc:
        # v0.7.46: setup.command + setup.script XOR violation. Surface
        # the structured message cleanly instead of a Python traceback.
        print(_colors.error(f"Error: {exc}"), file=sys.stderr)
        return 1
    except UnsupportedSchemaVersionError as exc:
        print(_colors.error(f"Error: {exc}"), file=sys.stderr)
        return 1
    except _json.JSONDecodeError as exc:
        # Malformed user-override JSON (v0.7.22). Surface clean error with
        # path + parse position; no Python traceback.
        print(
            _colors.error(f"Error: user override file is not valid JSON: {exc}"),
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        # Override file exists but can't be read (permissions, etc.).
        print(
            _colors.error(f"Error: cannot read user override file: {exc}"),
            file=sys.stderr,
        )
        return 1

    # Determine the runnable form: either a shell `command` string or a
    # `script` file pointer. v0.7.46 (4d-3 follow-up) added `setup.script`
    # as a sibling of `setup.command`; XOR-validated by setup_resolve.
    cmd_str = effective.get("command") if effective else None
    script_path = effective.get("script") if effective else None

    tool_dir = project.directory or "."
    fqcn = project.fqcn or tool_name

    if not cmd_str and not script_path:
        from dazzlecmd_lib.platform_detect import get_platform_info
        pi = get_platform_info()
        tag = pi.os + (f".{pi.subtype}" if pi.subtype else "")
        print(
            _colors.warn(
                f"No setup command or script available for platform '{tag}'. "
                f"Add setup.command, setup.script, setup.platforms.{pi.os}, "
                f"or setup.platforms.{pi.os}.general to the manifest."
            ),
            file=sys.stderr,
        )
        return 1

    # Build the dispatch command. `command` runs via the system shell;
    # `script` runs via an interpreter inferred from the file extension.
    import subprocess as _subprocess
    if script_path:
        from dazzlecmd_lib.setup_resolve import infer_setup_script_interpreter
        prefix = infer_setup_script_interpreter(script_path)
        if prefix is None:
            print(
                _colors.error(
                    f"Error: setup.script '{script_path}' has an unsupported "
                    f"extension. Supported: .py, .sh, .cmd, .bat, .ps1."
                ),
                file=sys.stderr,
            )
            return 1
        # Resolve the script path relative to the tool directory. Reject
        # absolute paths to keep the setup contract scoped to the tool.
        if os.path.isabs(script_path):
            print(
                _colors.error(
                    f"Error: setup.script must be relative to the tool "
                    f"directory; got absolute path '{script_path}'."
                ),
                file=sys.stderr,
            )
            return 1
        full_script_path = os.path.join(tool_dir, script_path)
        if not os.path.isfile(full_script_path):
            print(
                _colors.error(
                    f"Error: setup.script '{script_path}' not found at "
                    f"{full_script_path}."
                ),
                file=sys.stderr,
            )
            return 1
        invocation = prefix + [full_script_path]
        # Display: human-readable form joining argv with spaces. Real
        # dispatch uses the argv list (no shell parsing, no quote
        # escaping concerns).
        display_form = " ".join(invocation)
    else:
        invocation = cmd_str
        display_form = cmd_str

    print(f"Running setup for {fqcn}...")
    if effective.get("note"):
        print(f"  Note: {effective['note']}")
    if script_path:
        print(f"  Script: {script_path}")
        print(f"  Invocation: {display_form}")
    else:
        print(f"  Command: {display_form}")
    print(f"  Working dir: {tool_dir}")
    print()
    sys.stdout.flush()

    # `script` path uses argv (shell=False); `command` path keeps shell=True
    # for legacy back-compat (existing setup.command strings often use && and
    # other shell operators).
    if script_path:
        result = _subprocess.run(invocation, cwd=tool_dir, shell=False)
    else:
        result = _subprocess.run(invocation, shell=True, cwd=tool_dir)
    if result.returncode == 0:
        print(f"\nSetup for {fqcn} completed successfully.")
    else:
        print(f"\nSetup for {fqcn} failed with exit code {result.returncode}.", file=sys.stderr)
    return result.returncode
