"""``dz new`` scaffolding command handlers + the --with component framework.

Moved out of cli.py (decomposition R2, DWP 2026-06-25__16-14-19). Holds
``dz new tool|kit|aggregator``, the template-copy helpers, the ``--with``
composable-component framework (RepoKit common/template + docker/ci), and the
shared ``_register_in_kit`` registration helper (also used by ``dz add`` --
commands/add.py imports it from here in R3). cli.py re-exports these names.
Imports nothing from cli.py -- one-directional.
"""
import json
import os
import re
import sys

def _resolve_new_defaults(engine):
    """Read the user config's ``new`` section and return a defaults dict.

    Precedence applied at call site is: CLI flag > config > built-in.
    This helper returns the config layer; callers fall back to built-ins.
    """
    if engine is None:
        return {}
    try:
        cfg = engine._get_config_dict("new") or {}
    except Exception:
        cfg = {}
    return cfg if isinstance(cfg, dict) else {}


def _find_templates_root():
    """Locate the templates directory shipped with dazzlecmd-lib.

    Prefers the lib package (installed or editable). Falls back to a
    local ``templates/`` next to this module for the legacy single-repo
    layout.
    """
    import dazzlecmd_lib
    lib_dir = os.path.dirname(dazzlecmd_lib.__file__)
    template_dir = os.path.join(lib_dir, "templates")
    if os.path.isdir(template_dir):
        return template_dir
    return os.path.join(os.path.dirname(__file__), "templates")


def _available_languages(templates_root):
    """Return the sorted list of language template directory names.

    Filters out overlay directories (``__full__`` etc.) and any
    non-directory entries.
    """
    if not os.path.isdir(templates_root):
        return []
    return sorted(
        entry for entry in os.listdir(templates_root)
        if os.path.isdir(os.path.join(templates_root, entry))
        and not entry.startswith("__")
    )


def _substitute_placeholders(text, placeholders):
    """Replace ``{key}`` markers in text with their placeholder values.

    Order matters when one placeholder is a substring of another. The
    placeholder set is small (~5 entries) and stable; iterate the dict
    and replace each in turn.
    """
    for key, value in placeholders.items():
        text = text.replace("{" + key + "}", value)
    return text


def _copy_template_tree(src_dir, dest_dir, placeholders):
    """Recursively copy ``src_dir`` into ``dest_dir`` with placeholder
    substitution applied to file contents AND filenames.

    Files ending in ``.tmpl`` have the suffix stripped on output. Files
    without the suffix are copied verbatim (no substitution). Subdirectory
    names also receive placeholder substitution so e.g. ``src/`` stays
    ``src/`` but a hypothetical ``{name}-pkg/`` would be renamed.

    Overlay subdirectories matching ``__*__`` (e.g., ``__full__``) are
    skipped in the recursion -- callers apply them separately.

    Returns the list of relative paths created (for the success message).
    """
    created = []
    for entry in sorted(os.listdir(src_dir)):
        if entry.startswith("__") and entry.endswith("__"):
            continue
        src_path = os.path.join(src_dir, entry)
        dest_entry = _substitute_placeholders(entry, placeholders)
        if os.path.isdir(src_path):
            sub_dest = os.path.join(dest_dir, dest_entry)
            os.makedirs(sub_dest, exist_ok=True)
            sub_created = _copy_template_tree(src_path, sub_dest, placeholders)
            created.extend(os.path.join(dest_entry, p) for p in sub_created)
            continue
        # File
        if dest_entry.endswith(".tmpl"):
            dest_entry = dest_entry[:-len(".tmpl")]
            with open(src_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = _substitute_placeholders(content, placeholders)
            dest_path = os.path.join(dest_dir, dest_entry)
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            import shutil
            dest_path = os.path.join(dest_dir, dest_entry)
            shutil.copy2(src_path, dest_path)
        created.append(dest_entry)
    return created


def _cmd_new_tool(args, project_root, engine=None):
    """Create a new tool project with progressive scaffolding.

    Per-language template dispatch (v0.7.44, 4b-T3 + 4d-3): the
    ``--language`` flag (with config and built-in fallbacks) selects a
    template directory under
    ``packages/dazzlecmd-lib/src/dazzlecmd_lib/templates/<language>/``.
    The whole tree is copied to the new tool's directory with placeholder
    substitution. For Python, ``--full`` additionally applies the
    ``python/__full__/`` overlay (README + test stub).
    """
    new_defaults = _resolve_new_defaults(engine)

    name = args.name
    namespace = (
        args.namespace
        or new_defaults.get("default_namespace")
        or "dazzletools"
    )
    description = args.description or f"A new dazzlecmd tool: {name}"
    long_description = getattr(args, "long_description", "") or ""
    language = (
        args.language
        or new_defaults.get("default_language")
        or "python"
    )

    templates_root = _find_templates_root()
    available = _available_languages(templates_root)
    if language not in available:
        source = (
            "config 'new.default_language'"
            if args.language is None and new_defaults.get("default_language")
            else "--language flag"
        )
        avail_str = ", ".join(available) if available else "(none found)"
        print(
            f"Error: language {language!r} not supported (from {source}).\n"
            f"Available: {avail_str}.",
            file=sys.stderr,
        )
        return 2

    projects_dir = os.path.join(project_root, "projects", namespace)
    tool_dir = os.path.join(projects_dir, name)

    if os.path.exists(tool_dir):
        if args.simple or args.full:
            return _layer_extras(tool_dir, name, args)
        print(f"Error: Project '{namespace}/{name}' already exists at {tool_dir}")
        return 1

    os.makedirs(tool_dir, exist_ok=True)

    placeholders = {
        "name": name,
        "name_underscore": name.replace("-", "_"),
        "description": description,
        "long_description": long_description,
        "namespace": namespace,
    }

    lang_template_dir = os.path.join(templates_root, language)
    created = _copy_template_tree(lang_template_dir, tool_dir, placeholders)

    # Python --full overlay: copy the python/__full__/ tree as well.
    if args.full and language == "python":
        full_dir = os.path.join(lang_template_dir, "__full__")
        if os.path.isdir(full_dir):
            extra = _copy_template_tree(full_dir, tool_dir, placeholders)
            created.extend(extra)

    print(f"Created project: {namespace}/{name}")
    print(f"  {tool_dir}/")
    for rel_path in created:
        print(f"  - {rel_path}")

    # Universal --simple/--full extras (TODO.md, NOTES.md, ROADMAP.md, etc.)
    if args.simple or args.full:
        _layer_extras(tool_dir, name, args)

    kit_name = getattr(args, "kit", None)
    if kit_name:
        _register_in_kit(project_root, kit_name, namespace, name)

    return 0


def _cmd_new_kit(args, project_root):
    """``dz new kit <name>`` -- create a LOCAL kit inside this aggregator.

    A kit is a directory of tools registered into the parent's discovery
    (Tier 2 synthesis OQ-A2: semantically distinct from an aggregator, which
    has its own dispatch). Creates ``projects/<name>/.kit.json`` (the in-tree
    manifest that travels with the kit if it ever migrates) and
    ``kits/<name>.kit.json`` (the registry pointer controlling activation).
    """
    name = args.name.strip().lower()
    if not re.match(r"^[a-z][a-z0-9_-]*$", name):
        print(f"Error: invalid kit name '{args.name}' (use lowercase letters, "
              "digits, '-', '_').", file=sys.stderr)
        return 1

    kit_dir = os.path.join(project_root, "projects", name)
    kit_manifest = os.path.join(kit_dir, ".kit.json")
    registry_path = os.path.join(project_root, "kits", f"{name}.kit.json")
    for existing in (kit_manifest, registry_path):
        if os.path.exists(existing):
            print(f"Error: {existing} already exists.", file=sys.stderr)
            return 1

    os.makedirs(kit_dir, exist_ok=True)
    manifest = {
        "name": name,
        "version": "0.1.0",
        "description": args.description or f"{name} kit",
        "tools_dir": ".",
        "manifest": ".dazzlecmd.json",
        "tools": [],
    }
    with open(kit_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
        f.write("\n")

    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    # OQ-J: warn against cross-embedding loops until #65's display dedup ships
    # everywhere. (Comment field, not a schema key the loader acts on.)
    registry = {
        "name": name,
        "always_active": False,
        "_note": "Registry pointer: controls activation only. Do not point a "
                 "parent aggregator back at a child that embeds this one.",
    }
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4)
        f.write("\n")

    created = [os.path.relpath(kit_manifest, project_root),
               os.path.relpath(registry_path, project_root)]

    if getattr(args, "with_starter", False):
        rc = _scaffold_starter_tool(project_root, kit=name)
        if rc == 0:
            manifest["tools"].append(f"{name}:hello")
            with open(kit_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=4)
                f.write("\n")
            created.append(os.path.join("projects", name, "hello", ""))

    print(f"Created kit '{name}':")
    for path in created:
        print(f"  {path}")
    print(f"\nEnable it with: dz kit enable {name}")
    return 0


def _scaffold_starter_tool(project_root, kit, tool_name="hello"):
    """Generate a starter 'hello' tool from the python template into
    ``projects/<kit>/<tool_name>/``. Returns 0/1."""
    templates_root = _find_templates_root()
    src = os.path.join(templates_root, "python")
    if not os.path.isdir(src):
        print("Warning: python template not found; skipping starter tool.",
              file=sys.stderr)
        return 1
    dest = os.path.join(project_root, "projects", kit, tool_name)
    os.makedirs(dest, exist_ok=True)
    placeholders = {
        "name": tool_name,
        "name_underscore": tool_name.replace("-", "_"),
        "namespace": kit,
        "description": "Starter tool -- replace me",
        "long_description": "",
    }
    _copy_template_tree(src, dest, placeholders)
    return 0


# --- `--with` composable scaffolding components (4d-5, Tier-2 synthesis) ----
#
# Each component is a function (target_dir, placeholders) -> list-of-added
# (relative paths), raising ComponentUnavailable with a reason when it cannot
# apply. Composition is BEST-EFFORT (OQ-D1): a failed component warns and the
# rest continue; a summary prints at the end. `common`/`template` (RepoKit,
# network/external) land in 4d-6 -- until then they report unavailable with
# the install pointer rather than failing silently.

class _ComponentUnavailable(Exception):
    pass


def _with_copy_component(component_dir_name):
    """An applier that copies templates/__with__/<name>/ into the target."""
    def _apply(target_dir, placeholders, defaults):
        src = os.path.join(_find_templates_root(), "__with__", component_dir_name)
        if not os.path.isdir(src):
            raise _ComponentUnavailable(f"template dir missing: {src}")
        return _copy_template_tree(src, target_dir, placeholders)
    return _apply


_REPOKIT_COMMON_URL_DEFAULT = (
    "https://github.com/DazzleTools/git-repokit-common.git")
_REPOKIT_TEMPLATE_URL_DEFAULT = (
    "https://github.com/DazzleTools/git-repokit-template.git")
_GIT_SUBTREE_TIMEOUT = 180  # network fetch of a whole repo


def _run_git(args_list, cwd, timeout):
    """Run git, return (rc, combined_output). Missing git -> (127, message).

    Runs with a sanitized environment (repo-location GIT_* vars stripped) so
    the repository is always resolved from ``cwd`` -- never from ambient hook
    state (git exports GIT_DIR to hook subprocesses, which would silently
    point every call here at the HOOK'S repository).
    """
    import subprocess as _sp
    from dazzlecmd_lib.mode import sanitized_git_env
    try:
        r = _sp.run(["git"] + args_list, cwd=cwd, capture_output=True,
                    text=True, timeout=timeout, env=sanitized_git_env())
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, "git not found on PATH"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _with_common(target_dir, placeholders, defaults):
    """`--with common`: the git-repokit-common subtree at scripts/ (4d-6).

    `git subtree add` requires a repo with at least one commit; a fresh
    scaffold has neither, so this initializes git + an initial commit first
    (clearly announced -- it is the documented next step anyway). Source URL:
    config `new.repokit_common_url` > the DazzleTools default. RepoKit
    unavailable (no git / network / bad URL) raises ComponentUnavailable with
    the manual command (OQ-G1: hint and proceed, never block).
    """
    url = (defaults or {}).get("repokit_common_url") or _REPOKIT_COMMON_URL_DEFAULT
    if os.path.isdir(os.path.join(target_dir, "scripts")):
        raise _ComponentUnavailable("scripts/ already exists in the target")
    # The target must be its OWN repo toplevel. Ambient rev-parse discovery
    # walks up to any ancestor repo (e.g. a scaffold under the user's HOME,
    # which is itself a git repo on this layout) -- subtree-ing into THAT
    # would pollute the wrong repository. If the discovered toplevel is not
    # the target itself, initialize a fresh (nested-safe) repo at the target.
    rc, _top = _run_git(["rev-parse", "--show-toplevel"], target_dir, 10)
    _is_own_repo = (
        rc == 0 and _top.strip()
        and os.path.normcase(os.path.realpath(_top.strip()))
        == os.path.normcase(os.path.realpath(target_dir))
    )
    if not _is_own_repo:
        # core.autocrlf=false locally: on Windows a global autocrlf=true
        # rewrites line endings right after the commit, leaving the tree
        # "modified" and making git-subtree refuse ("working tree has
        # modifications"). The generated scaffold is LF on disk already.
        for cmd in (["init", "-q"], ["config", "core.autocrlf", "false"],
                    ["add", "-A"],
                    ["commit", "-q", "-m", "Initial scaffold"]):
            rc, out = _run_git(cmd, target_dir, 30)
            if rc != 0:
                raise _ComponentUnavailable(
                    f"could not initialize git in the target ({out}); "
                    f"git init + commit, then: git subtree add "
                    f"--prefix=scripts {url} main --squash")
        print("  [with:common] initialized git repository (subtree requires "
              "a commit)")
    # git-subtree insists on running from the EXACT toplevel string (Windows
    # temp-path normalization can differ from the cwd we hold) -- resolve it.
    rc, toplevel = _run_git(["rev-parse", "--show-toplevel"], target_dir, 10)
    run_cwd = toplevel.strip() if rc == 0 and toplevel.strip() else target_dir
    # Refresh the stat cache first: files written milliseconds before the
    # commit leave racy-git index entries, and subtree's diff-index check
    # misreads them as "working tree has modifications".
    _run_git(["status", "--porcelain"], run_cwd, 10)
    rc, out = _run_git(["subtree", "add", "--prefix=scripts", url,
                        "main", "--squash"], run_cwd, _GIT_SUBTREE_TIMEOUT)
    if rc != 0:
        tail = out.splitlines()[-1] if out else "unknown"
        raise _ComponentUnavailable(
            f"subtree add failed ({tail}); retry later with: "
            f"git subtree add --prefix=scripts {url} main --squash")
    print("  [with:common] run scripts/install-hooks to enable the git hooks")
    return ["scripts/ (git-repokit-common subtree)"]


def _with_template(target_dir, placeholders, defaults):
    """`--with template`: project-shape files from git-repokit-template.

    Source resolution (OQ-D2, local-first): config `new.repokit_template_path`
    if set + valid -> copy with substitution; else shallow-clone the template
    URL; else the lib-bundled minimal fallback (README exists from the
    scaffold; this adds LICENSE/CONTRIBUTING stubs) with a clear
    "fallback minimal" warning (OQ-G2). Existing files are NEVER overwritten
    (the scaffold's README/.gitignore win).
    """
    import shutil as _sh
    import tempfile as _tf
    d = defaults or {}

    def _copy_no_clobber(src_root):
        added = []
        for entry in sorted(os.listdir(src_root)):
            if entry in (".git", "__pycache__"):
                continue
            sp = os.path.join(src_root, entry)
            dest_name = entry[:-len(".tmpl")] if entry.endswith(".tmpl") else entry
            dp = os.path.join(target_dir, dest_name)
            if os.path.exists(dp):
                continue  # never clobber scaffold output
            if os.path.isdir(sp):
                _sh.copytree(sp, dp)
                added.append(dest_name + "/")
            else:
                with open(sp, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                content = _substitute_placeholders(content, placeholders)
                with open(dp, "w", encoding="utf-8") as f:
                    f.write(content)
                added.append(dest_name)
        return added

    local = d.get("repokit_template_path")
    if local and os.path.isdir(local):
        added = _copy_no_clobber(local)
        print(f"  [with:template] source: local path {local}")
        return added

    url = d.get("repokit_template_url") or _REPOKIT_TEMPLATE_URL_DEFAULT
    tmp = _tf.mkdtemp(prefix="repokit_tmpl_")
    try:
        rc, _out = _run_git(["clone", "--depth", "1", url, tmp],
                            target_dir, _GIT_SUBTREE_TIMEOUT)
        if rc == 0:
            added = _copy_no_clobber(tmp)
            print(f"  [with:template] source: {url}")
            return added
    finally:
        # Windows: the clone's read-only .git objects make a plain rmtree
        # fail silently (ignore_errors) and leak the temp dir -- chmod+retry.
        def _on_rm_error(func, path, _exc):
            import stat as _stat
            try:
                os.chmod(path, _stat.S_IWRITE)
                func(path)
            except OSError:
                pass
        _sh.rmtree(tmp, onerror=_on_rm_error)

    # Bundled minimal fallback (OQ-G2)
    fallback = os.path.join(_find_templates_root(), "repokit_fallback")
    if not os.path.isdir(fallback):
        raise _ComponentUnavailable(
            f"template repo unreachable ({url}) and no bundled fallback")
    added = _copy_no_clobber(fallback)
    print("  [with:template] WARNING: template repo unreachable -- used the "
          "bundled FALLBACK-MINIMAL stubs; replace with the real "
          "git-repokit-template when available")
    return added


_WITH_COMPONENTS = {
    "docker-test": _with_copy_component("docker-test"),
    "docker-deploy": _with_copy_component("docker-deploy"),
    "ci": _with_copy_component("ci"),
    "common": _with_common,
    "template": _with_template,
}
_WITH_ALL = ("common", "template", "docker-test", "docker-deploy", "ci")


def _parse_with_spec(spec):
    """Parse a --with comma-list; expand `all`; reject unknown names."""
    requested = [c.strip().lower() for c in (spec or "").split(",") if c.strip()]
    expanded = []
    for c in requested:
        for name in (_WITH_ALL if c == "all" else (c,)):
            if name not in _WITH_COMPONENTS:
                raise ValueError(
                    f"unknown --with component '{c}' "
                    f"(valid: {', '.join([*_WITH_COMPONENTS, 'all'])})")
            if name not in expanded:
                expanded.append(name)
    return expanded


def _apply_with_components(target_dir, components, placeholders, defaults=None):
    """Apply components best-effort; print the summary; return 0 always
    (composition failures are warnings, not scaffold failures -- OQ-D1)."""
    ok, skipped = [], []
    for name in components:
        try:
            added = _WITH_COMPONENTS[name](target_dir, placeholders, defaults)
            ok.append(name)
            for rel in added:
                print(f"  [with:{name}] {rel}")
        except _ComponentUnavailable as exc:
            skipped.append((name, str(exc)))
        except Exception as exc:  # best-effort: never kill the scaffold
            skipped.append((name, f"failed: {exc}"))
    if ok or skipped:
        parts = []
        if ok:
            parts.append("ok: " + ", ".join(ok))
        if skipped:
            parts.append("skipped: " + "; ".join(f"{n} ({r})" for n, r in skipped))
        print(f"\n--with summary: {' | '.join(parts)}")
    return 0


def _cmd_new_aggregator(args, engine=None):
    """``dz new aggregator <name>`` -- scaffold a STANDALONE aggregator project.

    Always standalone (Tier 2 synthesis OQ-A2): own pyproject.toml, console
    entry point, aggregator.json, tools dir, kit registry, smoke test. The
    generated cli.py is the canonical thin dazzlecmd-lib consumer (the wtf
    pattern): ``AggregatorEngine.from_project(...)`` + ``engine.run()``, with
    a commented ``nest_all_under`` stub for when #47 ships (OQ-E: manual
    uncomment, no auto-rewrites of user code).

    Defaults resolve CLI flag > user config ``new`` section > built-in (4d-7).
    The target directory is ``./<name>`` relative to the CURRENT directory --
    a new project beside wherever you are, never inside dazzlecmd's tree.
    """
    name = args.name.strip()
    if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", name):
        print(f"Error: invalid project name '{args.name}'.", file=sys.stderr)
        return 1

    new_defaults = _resolve_new_defaults(engine)
    command = args.command or name.lower().replace("_", "-")
    tools_dir = args.tools_dir or new_defaults.get("tools_dir") or "projects"
    manifest = args.manifest or new_defaults.get("manifest") or ".dazzlecmd.json"
    description = args.description or f"{name} -- a dazzlecmd-lib aggregator"

    try:
        with_components = _parse_with_spec(getattr(args, "with_components", None))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    target = os.path.abspath(name)
    if os.path.exists(target):
        print(f"Error: {target} already exists.", file=sys.stderr)
        return 1

    # Inside-an-aggregator guard: the target is CWD-relative, so running this
    # from within an existing aggregator's tree nests the new standalone
    # project inside that repo (untracked litter + a stray aggregator.json).
    # Never destructive (the exists-check above refuses collisions), and
    # occasionally intentional -- so warn loudly and proceed.
    from dazzlecmd_lib.aggregator_config import find_aggregator_root
    enclosing = find_aggregator_root(os.getcwd())
    if enclosing:
        print(
            f"Note: you are inside the aggregator at {enclosing} -- the new "
            f"standalone project will be created NESTED in that repo's "
            f"working tree at {target} (it will show up untracked there). "
            f"cd elsewhere first if you wanted an independent sibling project.",
            file=sys.stderr,
        )

    templates_root = _find_templates_root()
    src = os.path.join(templates_root, "aggregator")
    if not os.path.isdir(src):
        print(f"Error: aggregator template not found at {src}.", file=sys.stderr)
        return 1

    from dazzlecmd_lib._version import __version__ as _lib_version
    placeholders = {
        "name": name,
        "name_underscore": name.lower().replace("-", "_"),
        "command": command,
        "description": description,
        "tools_dir": tools_dir,
        "manifest": manifest,
        "lib_min_version": _lib_version,
    }

    os.makedirs(target)
    created = _copy_template_tree(src, target, placeholders)

    # The discovery directories (template trees can't carry empty dirs).
    os.makedirs(os.path.join(target, tools_dir), exist_ok=True)
    os.makedirs(os.path.join(target, "kits"), exist_ok=True)

    if getattr(args, "with_starter", False):
        core_dir = os.path.join(target, tools_dir, "core")
        os.makedirs(core_dir, exist_ok=True)
        with open(os.path.join(core_dir, ".kit.json"), "w", encoding="utf-8") as f:
            json.dump({
                "name": "core", "version": "0.1.0",
                "description": f"Core tools for {name}",
                "tools_dir": ".", "manifest": manifest,
                "tools": ["core:hello"],
            }, f, indent=4)
            f.write("\n")
        with open(os.path.join(target, "kits", "core.kit.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"name": "core", "always_active": True}, f, indent=4)
            f.write("\n")
        # Reuse the python tool template for the hello tool (tools_dir-aware).
        hello_root = os.path.join(target, tools_dir, "core", "hello")
        os.makedirs(hello_root, exist_ok=True)
        py_src = os.path.join(templates_root, "python")
        if os.path.isdir(py_src):
            _copy_template_tree(py_src, hello_root, {
                "name": "hello", "name_underscore": "hello",
                "namespace": "core",
                "description": "Starter tool -- replace me",
                "long_description": "",
            })
            created.append(os.path.join(tools_dir, "core", "hello", ""))

    if with_components:
        _apply_with_components(target, with_components, placeholders,
                               defaults=new_defaults)

    print(f"Created aggregator '{name}' at {target}")
    for path in sorted(created):
        print(f"  {path}")
    print(
        f"\nNext steps:\n"
        f"  cd {name}\n"
        f"  pip install -e .\n"
        f"  {command} list\n"
        f"  git init && git add -A   # version it (RepoKit integration: --with common, later)"
    )
    return 0


def _layer_extras(tool_dir, name, args):
    """Add extra files to an existing project."""
    added = []

    if args.simple or args.full:
        # --simple: add TODO.md and NOTES.md
        for filename in ["TODO.md", "NOTES.md"]:
            filepath = os.path.join(tool_dir, filename)
            if not os.path.exists(filepath):
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"# {filename.replace('.md', '')} - {name}\n\n")
                added.append(filename)

    if args.full:
        # --full: add ROADMAP.md, private/claude/, tests/
        roadmap = os.path.join(tool_dir, "ROADMAP.md")
        if not os.path.exists(roadmap):
            with open(roadmap, "w", encoding="utf-8") as f:
                f.write(f"# Roadmap - {name}\n\n## Planned\n\n## In Progress\n\n## Done\n\n")
            added.append("ROADMAP.md")

        for subdir in ["private/claude", "tests"]:
            dirpath = os.path.join(tool_dir, subdir)
            if not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
                added.append(f"{subdir}/")

    if added:
        print(f"  Added: {', '.join(added)}")
    return 0


#


def _register_in_kit(project_root, kit_name, namespace, tool_name):
    """Add a tool reference to a kit's tools array.

    Writes to the kit's **in-repo manifest** (``projects/<kit>/.kit.json``)
    when present, falling back to the registry pointer
    (``kits/<kit>.kit.json``) only for registry-only kits.

    Why in-repo manifest first: ``loader.discover_kits`` merges in-repo
    fields OVER the registry pointer when both exist (loader.py:55-71).
    The in-repo manifest's ``tools`` list authoritatively overrides
    whatever the registry pointer carries. Pre-fix, this function wrote
    only to the registry pointer, which the merge silently ignored for
    every kit with an in-repo manifest (``core``, ``dazzletools``, ...).
    The registered entry never surfaced in ``dz list`` because the
    in-repo manifest's untouched ``tools`` list won the merge.
    """
    in_repo_manifest = os.path.join(
        project_root, "projects", kit_name, ".kit.json"
    )
    registry_pointer = os.path.join(
        project_root, "kits", f"{kit_name}.kit.json"
    )

    # Prefer in-repo manifest (authoritative when present).
    if os.path.isfile(in_repo_manifest):
        target = in_repo_manifest
        target_label = f"{kit_name} (in-repo manifest)"
    elif os.path.isfile(registry_pointer):
        target = registry_pointer
        target_label = f"{kit_name} (registry pointer)"
    else:
        print(
            f"  Warning: Kit '{kit_name}' not found (looked at "
            f"'{in_repo_manifest}' and '{registry_pointer}')",
            file=sys.stderr,
        )
        return

    try:
        with open(target, "r", encoding="utf-8") as f:
            kit = json.load(f)

        qualified = f"{namespace}:{tool_name}"
        if qualified not in kit.get("tools", []):
            kit.setdefault("tools", []).append(qualified)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(kit, f, indent=4)
                f.write("\n")
            print(f"  Registered in kit: {target_label}")
        else:
            print(f"  Already in kit: {target_label}")
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Warning: Could not update kit: {exc}", file=sys.stderr)
