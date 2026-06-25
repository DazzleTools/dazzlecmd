"""Kit-lifecycle command handlers: the membership / materialization axis.

Moved out of cli.py (decomposition R1, DWP 2026-06-25__16-14-19). The
``dz kit add|remove|detach|attach|management`` handlers plus the submodule
detection, pointer-materialization stub, and lifecycle-axis hint helper.
cli.py re-exports these names. Imports nothing from cli.py -- one-directional.
"""
import json
import os
import sys

from dazzlecmd.kit_verbs import LIFECYCLE_PAIRS

def _cmd_kit_add(args, project_root, engine):
    """Add a kit from a git URL via submodule."""
    import subprocess as _subprocess
    from urllib.parse import urlparse

    url = args.url
    name = args.name
    branch = args.branch
    shallow = args.shallow

    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # Derive name from URL if not provided
    if not name:
        parsed = urlparse(url)
        tail = parsed.path.rstrip("/").split("/")[-1]
        name = tail[:-4] if tail.endswith(".git") else tail
        # Strip common prefixes like "dazzle-" or "wtf-"? Leave as-is.
        if not name:
            print(
                f"Error: could not derive kit name from URL. "
                f"Pass --name explicitly.",
                file=sys.stderr,
            )
            return 1

    target_dir = os.path.join(project_root, "projects", name)
    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")

    if os.path.exists(target_dir):
        print(
            f"Error: projects/{name}/ already exists.",
            file=sys.stderr,
        )
        return 1

    if os.path.exists(registry_path):
        print(
            f"Error: kits/{name}.kit.json already exists.",
            file=sys.stderr,
        )
        return 1

    cmd = ["git", "submodule", "add"]
    if branch:
        cmd += ["-b", branch]
    if shallow:
        cmd += ["--depth", "1"]
    cmd += [url, f"projects/{name}"]

    print(f"Running: {' '.join(cmd)}")
    from dazzlecmd_lib.mode import sanitized_git_env
    try:
        result = _subprocess.run(cmd, cwd=project_root,
                                 env=sanitized_git_env())
    except FileNotFoundError:
        print(
            "Error: git not found. Install git and retry.",
            file=sys.stderr,
        )
        return 1

    if result.returncode != 0:
        print(
            f"Error: git submodule add failed with exit code {result.returncode}",
            file=sys.stderr,
        )
        return result.returncode

    # Create registry pointer
    registry = {
        "name": name,
        "always_active": False,
        "source": url,
    }
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4)
        f.write("\n")

    print(f"Added kit: {name}")
    print(f"  Registry pointer: kits/{name}.kit.json")
    print(f"  Submodule: projects/{name}/")

    # Detect nested aggregator structure
    nested_kits_dir = os.path.join(target_dir, "kits")
    if os.path.isdir(nested_kits_dir):
        print(
            f"  Note: '{name}' appears to be a nested aggregator "
            f"(has its own kits/ directory). Tools will be namespace-remapped "
            f"as '{name}:<namespace>:<tool>'."
        )

    print()
    print(f"Enable with: dz kit enable {name}")
    return 0


def _kit_is_submodule(project_root, name):
    """True if ``projects/<name>`` is registered as a git submodule.

    ``parse_gitmodules()`` is intentionally TOOL-only -- it drops 2-part KIT paths
    (its ``len(parts) != 2`` filter only keeps ``<dir>/<ns>/<tool>``). A KIT lives
    at ``projects/<name>`` (2-part), so kit-level submodule detection reads
    .gitmodules DIRECTLY for a section whose ``path`` == ``projects/<name>``. (The
    original is_submodule bug used the tool-filtered helper, so it never saw a kit
    submodule and the git-untrack never fired.)
    """
    import configparser
    gm = os.path.join(project_root, ".gitmodules")
    if not os.path.isfile(gm):
        return False
    cfg = configparser.ConfigParser()
    try:
        cfg.read(gm, encoding="utf-8")
    except configparser.Error:
        return False
    want = f"projects/{name}"
    for section in cfg.sections():
        if cfg.has_option(section, "path") and cfg.get(section, "path").strip() == want:
            return True
    return False


def _cmd_kit_remove(args, project_root, engine):
    """Remove a kit -- the strong-remove pole of the kit lifecycle.

    Deregisters the kit (git untrack for a submodule + the registry entry, via the
    membership ``ungroup`` verb / KitMembershipContext), safedel-trashes its files
    (recoverable -- NEVER a raw delete), and drops any active/disabled config refs.
    Constitutional / ``always_active`` kits are refused (C3). The weak, keep-as-a-
    pointer form is ``dz kit detach`` (a later slice).
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # Resolve the kit entity (for C3); it may not be loaded -- that's fine.
    kit = None
    for k in (getattr(engine, "kits", []) or []):
        if (getattr(k, "kit_name", None) or getattr(k, "name", None)) == name:
            kit = k
            break

    # C3: constitutional / always_active kits may not be removed.
    if kit is not None and getattr(kit, "always_active", False):
        print(f"Refused: '{name}' is constitutional (always_active) -- it may not be "
              f"removed (C3). Run `dz kit disable {name}` or clear always_active first.",
              file=sys.stderr)
        return 1

    target_dir = os.path.join(project_root, "projects", name)
    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")

    if not os.path.exists(target_dir) and not os.path.exists(registry_path):
        print(f"Error: no kit '{name}' found (neither projects/{name}/ nor "
              f"kits/{name}.kit.json exists).", file=sys.stderr)
        return 1

    # Record the source URL BEFORE any mutation (the re-add hint; crash-safe).
    source = None
    if os.path.exists(registry_path):
        try:
            with open(registry_path, encoding="utf-8") as f:
                source = (json.load(f) or {}).get("source")
        except Exception:  # noqa: BLE001
            source = None

    # Is it a git submodule? (governs the untrack mechanism + the dirty-guard.)
    from dazzlecmd_lib.mode import (
        sanitized_git_env, _check_dirty_tree, _print_dirty_refusal,
    )
    rel = f"projects/{name}"
    # Detect a KIT submodule directly -- parse_gitmodules is TOOL-only and drops
    # 2-part kit paths (the original is_submodule bug used it and always got False).
    is_submodule = _kit_is_submodule(project_root, name)

    # Dirty-tree guard for a submodule worktree -- refuse without --force.
    if is_submodule and os.path.isdir(target_dir):
        dirty = _check_dirty_tree(target_dir)
        if dirty and not getattr(args, "force", False):
            _print_dirty_refusal(name, target_dir, dirty,
                                 getattr(engine, "command", "dz"))
            return 1

    # The plan (shared by --dry-run and the live run).
    plan = []
    if is_submodule:
        plan.append(f"untrack the submodule (git submodule deinit + git rm projects/{name})")
    if os.path.exists(registry_path):
        plan.append(f"deregister kits/{name}.kit.json (membership ungroup)")
    if os.path.isdir(target_dir):
        plan.append(f"safedel projects/{name}/ -> recoverable trash")
    plan.append(f"drop '{name}' from active_kits / disabled_kits")

    if getattr(args, "dry_run", False):
        print(f"Dry run -- `dz kit remove {name}` would:")
        for step in plan:
            print(f"  - {step}")
        return 0

    # Confirmation unless --yes.
    if not getattr(args, "yes", False):
        try:
            resp = input(f"Remove kit '{name}'? Its files go to the recoverable "
                         f"trash. [y/N] ")
        except EOFError:
            resp = ""
        if resp.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 0

    # 1. git untrack for a submodule. Drop the gitlink from the INDEX with --cached
    # (KEEPS the worktree on disk so step 3's safedel can back it up), then remove
    # the .gitmodules + .git/config submodule sections via git's own config editor
    # (format-preserving; touches only the one section). We deliberately do NOT use
    # `git submodule deinit` / `git rm -f`: both empty/delete the worktree, which
    # would destroy the files BEFORE safedel can recover them. `dz kit add` names the
    # submodule by its path, so the section is `submodule.projects/<name>`.
    if is_submodule:
        import subprocess as _subprocess
        import shutil as _shutil
        env = sanitized_git_env()
        sub = f"submodule.{rel}"
        try:
            r = _subprocess.run(["git", "rm", "-f", "--cached", "--", rel],
                                cwd=project_root, env=env)
        except FileNotFoundError:
            print("Error: git not found.", file=sys.stderr)
            return 1
        if r.returncode != 0:
            print(f"Error: `git rm --cached {rel}` failed (exit {r.returncode}); "
                  f"nothing else changed.", file=sys.stderr)
            return r.returncode
        # Surgically drop the .gitmodules section (other submodules untouched), then
        # stage it; clear the .git/config entry (non-zero if absent -- tolerated).
        _subprocess.run(["git", "config", "--file", ".gitmodules",
                         "--remove-section", sub], cwd=project_root, env=env)
        gm = os.path.join(project_root, ".gitmodules")
        if os.path.isfile(gm):
            with open(gm, encoding="utf-8") as _f:
                gm_empty = not _f.read().strip()
            if gm_empty:
                os.remove(gm)   # no submodules left -> drop the empty file
        _subprocess.run(["git", "add", "-A", "--", ".gitmodules"],
                        cwd=project_root, env=env)
        _subprocess.run(["git", "config", "--remove-section", sub],
                        cwd=project_root, env=env)   # .git/config; ok if absent
        # Drop git's cached submodule repo (regenerable from the remote) so a later
        # re-add of the same name doesn't collide. git marks its objects read-only,
        # so clear the bit on error (Windows) rather than silently leaving the cache.
        cached = os.path.join(project_root, ".git", "modules", "projects", name)
        if os.path.isdir(cached):
            import stat as _stat

            def _clear_ro(func, _p, _exc):
                try:
                    os.chmod(_p, _stat.S_IWRITE)
                    func(_p)
                except OSError:
                    pass
            _shutil.rmtree(cached, onerror=_clear_ro)

    # 2. Deregister the registry entry via the membership `ungroup` verb.
    if os.path.exists(registry_path):
        import types as _types
        from dazzlecmd_lib.contexts import KitMembershipContext
        ref = kit if kit is not None else _types.SimpleNamespace(
            name=name, kit_name=name, always_active=False)
        KitMembershipContext(
            project_root, getattr(engine, "kits", []),
            boundary_fqcn=getattr(engine, "command", "dz"),
        ).apply(ref, None, verb="ungroup")

    # 3. safedel the kit dir (recoverable; never a raw delete).
    trashed = False
    if os.path.isdir(target_dir):
        from dazzlecmd_lib.core.safedel import TrashStore
        try:
            trashed = bool(TrashStore().trash([target_dir]).success)
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: safedel of projects/{name}/ failed: {exc}",
                  file=sys.stderr)

    # 4. Deactivate -- drop any dangling active/disabled config refs.
    config = engine._get_user_config()
    active = [k for k in (config.get("active_kits") or []) if k != name]
    disabled = [k for k in (config.get("disabled_kits") or []) if k != name]
    engine._write_user_config({"active_kits": active, "disabled_kits": disabled})

    print(f"Removed kit: {name}")
    if trashed:
        print("  Files -> trash (recover with `dz safedel recover last`)")
    if source:
        print(f"  Re-add with: dz kit add {source}")
    return 0


def _cmd_kit_detach(args, project_root, engine):
    """Detach a kit -- the weak, keep-as-a-pointer pole of the kit lifecycle.

    A ``CompositeTransition`` across two presence axes: write a
    ``pointer:{materialized:true}`` block to the kit's registry (LOADING -> pointer:
    discovery then LISTS the kit but loads none of its tools) AND disable it (the
    implicit loading->activation cascade -- a detached kit is also deactivated). The
    files are KEPT on disk (``materialized:true``); de-materializing is a separate
    step (#80). Re-attach with ``dz kit attach``. Constitutional / ``always_active``
    kits are refused (C3 -- they must stay loaded). The strong, delete-the-files form
    is ``dz kit remove``.
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    # Resolve the kit entity (for C3); it may not be loaded -- that's fine.
    kit = None
    for k in (getattr(engine, "kits", []) or []):
        if (getattr(k, "kit_name", None) or getattr(k, "name", None)) == name:
            kit = k
            break

    # C3: constitutional / always_active kits must stay loaded -- refuse.
    if kit is not None and getattr(kit, "always_active", False):
        print(f"Refused: '{name}' is constitutional (always_active) -- it must stay "
              f"loaded and may not be detached (C3). Clear always_active first.",
              file=sys.stderr)
        return 1

    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")
    if not os.path.exists(registry_path):
        print(f"Error: no registered kit '{name}' found (kits/{name}.kit.json does "
              f"not exist). Only registered kits can be detached.", file=sys.stderr)
        return 1

    # The membership context owns the registry substrate -> the pointer block.
    import types as _types
    from dazzlecmd_lib.contexts import KitMembershipContext, ActivationContext
    ref = kit if kit is not None else _types.SimpleNamespace(
        name=name, kit_name=name, always_active=False)
    membership = KitMembershipContext(
        project_root, getattr(engine, "kits", []),
        boundary_fqcn=getattr(engine, "command", "dz"),
    )
    already = membership.pointer_of(ref) is not None

    if getattr(args, "dry_run", False):
        print(f"Dry run -- `dz kit detach {name}` would:")
        if already:
            print("  - (already a pointer; re-affirm the pointer block)")
        print(f"  - write pointer:{{materialized:true}} to kits/{name}.kit.json "
              f"(loading -> pointer; files kept on disk)")
        print(f"  - disable '{name}' (the implicit loading -> activation cascade)")
        return 0

    # 1. LOADING -> pointer: write the pointer block (content kept on disk).
    membership.set_pointer(ref, materialized=True)
    # 2. ACTIVATION -> inactive: the implicit cascade -- a detached kit is disabled.
    ActivationContext(engine).disable(name)

    print(f"Detached kit: {name}")
    print("  Now a pointer (listed, not loaded); files kept on disk.")
    print(f"  Re-attach with: dz kit attach {name}")
    return 0


def _materialize_pointer(project_root, name, source):
    """STUB (#80): fetch a not-yet-materialized pointer kit's content into
    ``projects/<name>/``. This is the deferred fetch tail of the pointer-kit
    lifecycle -- a ``materialized:false`` pointer is "declared but absent" and
    cannot be loaded until its content is fetched. Returns ``(ok, message)``;
    today it always defers (fetch is not yet implemented)."""
    return (False,
            f"'{name}' is an unfetched pointer (materialized:false) -- fetching "
            f"its content (#80) is not yet implemented. "
            + (f"Source: {source}." if source else "No source recorded."))


def _cmd_kit_attach(args, project_root, engine):
    """Attach a kit -- the inverse of ``dz kit detach`` (slice 4 step 3).

    A pointer kit (LOADING=pointer) is loaded again AND enabled: ``clear_pointer``
    (pointer -> loaded -- discovery loads its tools) composed with the activation
    ``enable``. Note the cascade ASYMMETRY: detach's ``loading->inactive`` is FORCED
    (you cannot dispatch what isn't loaded), but attach's ``loading->active`` is a
    FREE choice -- we default to enable (the corrected detach-saga meaning: "upon
    attach -> enable"). A ``materialized:false`` pointer (the #80 not-fetched case)
    needs a fetch first -> the deferred ``_materialize_pointer`` stub. Attaching a
    kit that isn't a pointer is a friendly no-op (use ``dz kit enable`` for that).
    """
    name = args.name
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1

    kit = None
    for k in (getattr(engine, "kits", []) or []):
        if (getattr(k, "kit_name", None) or getattr(k, "name", None)) == name:
            kit = k
            break

    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")
    if not os.path.exists(registry_path):
        print(f"Error: no registered kit '{name}' found (kits/{name}.kit.json does "
              f"not exist).", file=sys.stderr)
        return 1

    import types as _types
    from dazzlecmd_lib.contexts import KitMembershipContext, ActivationContext
    ref = kit if kit is not None else _types.SimpleNamespace(
        name=name, kit_name=name, always_active=False)
    membership = KitMembershipContext(
        project_root, getattr(engine, "kits", []),
        boundary_fqcn=getattr(engine, "command", "dz"),
    )

    pointer = membership.pointer_of(ref)
    if pointer is None:
        # Not a pointer -> nothing to attach (loading is already on).
        print(f"'{name}' is not detached (already loaded); nothing to attach. "
              f"Use `dz kit enable {name}` to activate it.")
        return 0
    materialized = (bool(pointer.get("materialized", True))
                    if isinstance(pointer, dict) else True)

    if getattr(args, "dry_run", False):
        print(f"Dry run -- `dz kit attach {name}` would:")
        if not materialized:
            print(f"  - fetch '{name}' content first (#80 -- not yet implemented)")
        print(f"  - clear the pointer block on kits/{name}.kit.json "
              f"(pointer -> loaded; tools load again)")
        print(f"  - enable '{name}' (attach defaults to active)")
        return 0

    # A not-yet-materialized (#80) pointer needs its content fetched before it can
    # load -- that is the deferred stub; refuse cleanly until it lands.
    if not materialized:
        source = None
        try:
            with open(registry_path, encoding="utf-8") as f:
                source = (json.load(f) or {}).get("source")
        except Exception:  # noqa: BLE001
            source = None
        ok, msg = _materialize_pointer(project_root, name, source)
        if not ok:
            print(f"Cannot attach: {msg}", file=sys.stderr)
            return 1

    # 1. LOADING -> loaded: drop the pointer block so discovery loads its tools.
    membership.clear_pointer(ref)
    # 2. ACTIVATION -> active: attach defaults to enable (the free-choice pole).
    ActivationContext(engine).enable(name)

    print(f"Attached kit: {name}")
    print("  Loaded again and enabled.")
    return 0


def _print_axis_hint(axis):
    pair = next((p for p in LIFECYCLE_PAIRS if p.axis == axis), None)
    if pair:
        print(f"\nChange with `dz kit {axis} {pair.warm}|{pair.cold} <kit>` "
              f"(or the flat alias `dz kit {pair.warm}|{pair.cold} <kit>`).")


def _cmd_kit_management(args, project_root, engine, axis=None):
    """Show kit lifecycle STATE -- the state-on-invoke view (like ``dz kit
    visibility``). ``management`` is the COMPOSED lifecycle axis ({KitOff..KitOn})
    that fuses the activation/loading/membership sub-axes (a kit must be a member to
    load, loaded to activate). ``axis=None`` (``dz kit management [<kit>]``) shows
    each kit's POSITION on that unified continuum; ``axis=<sub-axis>``
    (``dz kit activation|loading|membership``) shows that one sub-axis."""
    if engine is None:
        print("Error: engine unavailable", file=sys.stderr)
        return 1
    import types as _types
    from dazzlecmd_lib.contexts import KitMembershipContext
    membership = KitMembershipContext(
        project_root, getattr(engine, "kits", []),
        boundary_fqcn=getattr(engine, "command", "dz"))
    disabled = set((engine._get_user_config() or {}).get("disabled_kits") or [])
    want = getattr(args, "name", None)

    rows = []
    for k in (getattr(engine, "kits", []) or []):
        kname = getattr(k, "kit_name", None) or getattr(k, "name", None)
        if want and kname != want:
            continue
        always = bool(getattr(k, "always_active", False))
        ref = _types.SimpleNamespace(name=kname, kit_name=kname, always_active=always)
        rows.append({
            "name": kname,
            "always": always,
            "pointer": membership.pointer_of(ref) is not None,
            "disabled": (not always) and (kname in disabled),
        })
    if not rows:
        if want:
            print(f"No kit '{want}' found.", file=sys.stderr)
            return 1
        print("No kits.")
        return 0

    w = max(len(r["name"]) for r in rows)
    if axis is None:
        print("Kit management state -- position on the lifecycle continuum")
        print("(member > loaded > active; colder = more let go):\n")
        for r in rows:
            if r["pointer"]:
                pos = "detached (pointer; not loaded)"
            elif r["disabled"]:
                pos = "disabled (loaded, inactive)"
            else:
                pos = "active"
            tag = "  [always-active]" if r["always"] else ""
            print(f"  {r['name']:<{w}}  {pos}{tag}")
        print("\nMove with `dz kit enable|disable|attach|detach|add|remove <kit>`;")
        print("inspect a sub-axis with `dz kit activation|loading|membership`.")
    elif axis == "activation":
        print("Activation sub-axis (active vs disabled):\n")
        for r in rows:
            st = "disabled" if r["disabled"] else "active"
            tag = "  [always-active]" if r["always"] else ""
            print(f"  {r['name']:<{w}}  {st}{tag}")
        _print_axis_hint("activation")
    elif axis == "loading":
        print("Loading sub-axis (loaded vs pointer):\n")
        for r in rows:
            print(f"  {r['name']:<{w}}  {'pointer' if r['pointer'] else 'loaded'}")
        _print_axis_hint("loading")
    elif axis == "membership":
        print("Membership sub-axis (registered members):\n")
        for r in rows:
            print(f"  {r['name']}")
        _print_axis_hint("membership")
    else:
        print(f"Unknown lifecycle axis: {axis}", file=sys.stderr)
        return 1
    return 0
