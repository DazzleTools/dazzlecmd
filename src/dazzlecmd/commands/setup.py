"""``dz setup`` -- run a tool's declared setup script.

Moved out of cli.py (decomposition R3, DWP 2026-06-25__16-14-19). The engine
dispatches the tool's own setup.command/setup.script; it never installs deps
itself. cli.py re-exports _cmd_setup. Imports nothing from cli.py.
"""
import os
import sys

from dazzlecmd_lib import colors as _colors

def _self_names(engine):
    """The aggregator's own identity: root token + aliases (#103).

    Static names first (self-setup must work when the engine is broken
    -- it is the thing you run when everything else isn't working),
    then whatever the engine and the ``python -m`` launch add.
    """
    names = ["dz", "dazzlecmd"]
    for candidate in (getattr(engine, "command", None),
                      getattr(engine, "name", None)):
        if candidate and candidate not in names:
            names.append(candidate)
    try:
        from dazzlecmd_lib.self_setup import python_dash_m_target
        target = python_dash_m_target()
        if target and target not in names:
            names.append(target)
    except ImportError:
        pass
    return names


def _run_self_setup(args, engine):
    """``dz setup dz`` / ``python -m dazzlecmd setup dazzlecmd`` (#103)."""
    try:
        from dazzlecmd_lib import self_setup
    except ImportError:
        print(_colors.error(
            "Error: this dazzlecmd-lib predates self-setup; upgrade "
            "dazzlecmd-lib to use the PATH bootstrap."), file=sys.stderr)
        return 1
    import dazzlecmd as _pkg
    location = os.path.dirname(getattr(_pkg, "__file__", "") or "") or None
    return self_setup.run_self_setup(
        _self_names(engine),
        package_name="dazzlecmd",
        package_location=location,
        assume_yes=getattr(args, "yes", False),
        dry_run=getattr(args, "dry_run", False),
        emit_shell_fix=getattr(args, "emit_shell_fix", False),
        clip=getattr(args, "clip", False),
    )


def _cmd_setup(args, engine):
    """Run a tool's declared setup script.

    The engine doesn't install dependencies itself — it dispatches the
    tool's own ``setup.command`` (or platform-specific variant). The tool
    author writes the setup script; the engine runs it when the user asks.

    Naming the aggregator itself (``dz setup dz``, ``dz setup
    dazzlecmd``, or the ``python -m`` package) runs the self-setup PATH
    bootstrap instead -- and does so even when the engine failed to
    build, because a broken PATH is exactly when this command matters.
    """
    tool_name = getattr(args, "tool", None)
    # Variant-2 contract (#104): the engine split everything after the
    # first `--` into level_args -- owned by the TARGET, never the verb.
    level_args = list(getattr(args, "level_args", []) or [])

    if tool_name and tool_name in _self_names(engine):
        if level_args:
            # The self-target defines no level-params yet; reserved.
            print(_colors.warn(
                "note: self-setup takes its options before '--' "
                f"(--yes/--dry-run); ignoring reserved trailing args: "
                f"{level_args}"), file=sys.stderr)
        # Shadow visibility (#103 criterion 5): if a real tool bears the
        # aggregator's name, say which one and how to reach its setup.
        if engine is not None:
            try:
                shadowed, _sctx = engine.resolve_command(tool_name)
            except Exception:
                shadowed = None
            if shadowed is not None:
                shadow_name = shadowed.fqcn or shadowed.name
                print(_colors.warn(
                    f"note: {tool_name!r} is also a tool ({shadow_name}) "
                    f"-- running the aggregator's self-setup; use "
                    f"'dz setup {shadow_name}' for the tool."),
                    file=sys.stderr)
        return _run_self_setup(args, engine)

    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # No tool specified: list tools that have setup declared (v0.7.21 polish).
    # Detection: `setup.command` OR any `setup.platforms.*` present -- catches
    # tools with ONLY platform-specific setup commands (no top-level default).
    if not tool_name:
        if level_args:
            # Tester finding (2026-07-19): a `--` tail with no target
            # was silently dropped; say so instead.
            print(_colors.warn(
                "note: no setup target given; args after '--' were "
                f"ignored: {level_args}. Usage: dz setup <target> -- "
                "<target-args>"), file=sys.stderr)
        # One-line PATH-health warning (#103): the listing is also the
        # discovery path, so guide recovery from here too.
        try:
            from dazzlecmd_lib.self_setup import first_run_hint
            hint = first_run_hint(_self_names(engine),
                                  package_name="dazzlecmd")
            if hint:
                print(_colors.warn(hint), file=sys.stderr)
        except ImportError:
            pass

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
        # Variant-2 contract (#104): forwarded level-args ride the argv
        # list verbatim -- no shell parsing, no quoting concerns.
        invocation = prefix + [full_script_path] + level_args
        # Display: human-readable form joining argv with spaces. Real
        # dispatch uses the argv list (no shell parsing, no quote
        # escaping concerns).
        display_form = " ".join(invocation)
    else:
        # Command strings run shell=True; forwarded args need
        # host-correct quoting (v0.7.46's documented forwarding, wired).
        if level_args:
            from dazzlecmd_lib.verb_contracts import join_for_shell
            cmd_str = f"{cmd_str} {join_for_shell(level_args)}"
        invocation = cmd_str
        display_form = cmd_str

    dry_run = getattr(args, "dry_run", False)
    print(f"{'[dry-run] Would run' if dry_run else 'Running'} setup for {fqcn}...")
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

    # Verb-level --dry-run: show the resolved invocation, run nothing.
    # (Distinct from `dz setup <tool> -- --dry-run`, which passes the flag
    # INTO the tool's own setup script.)
    if dry_run:
        return 0

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
