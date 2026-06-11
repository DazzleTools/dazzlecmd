"""One-off: wire the 4d-6 RepoKit appliers into cli.py (replaces the stubs)."""
import io

P = "src/dazzlecmd/cli.py"
s = io.open(P, encoding="utf-8").read()

OLD_BLOCK = '''def _with_copy_component(component_dir_name):
    """An applier that copies templates/__with__/<name>/ into the target."""
    def _apply(target_dir, placeholders):
        src = os.path.join(_find_templates_root(), "__with__", component_dir_name)
        if not os.path.isdir(src):
            raise _ComponentUnavailable(f"template dir missing: {src}")
        return _copy_template_tree(src, target_dir, placeholders)
    return _apply


def _with_repokit_stub(what, hint):
    def _apply(target_dir, placeholders):
        raise _ComponentUnavailable(f"{what} lands with RepoKit integration "
                                    f"(4d-6). {hint}")
    return _apply


_WITH_COMPONENTS = {
    "docker-test": _with_copy_component("docker-test"),
    "docker-deploy": _with_copy_component("docker-deploy"),
    "ci": _with_copy_component("ci"),
    "common": _with_repokit_stub(
        "git-repokit-common subtree",
        "Meanwhile: git subtree add --prefix=scripts "
        "https://github.com/DazzleTools/git-repokit-common.git main --squash"),
    "template": _with_repokit_stub(
        "git-repokit-template files",
        "Meanwhile copy README/LICENSE/CONTRIBUTING from the template repo."),
}'''

NEW_BLOCK = '''def _with_copy_component(component_dir_name):
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
    """Run git, return (rc, combined_output). Missing git -> (127, message)."""
    import subprocess as _sp
    try:
        r = _sp.run(["git"] + args_list, cwd=cwd, capture_output=True,
                    text=True, timeout=timeout)
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
    rc, _out = _run_git(["rev-parse", "--git-dir"], target_dir, 10)
    if rc != 0:
        for cmd in (["init", "-q"], ["add", "-A"],
                    ["commit", "-q", "-m", "Initial scaffold"]):
            rc, out = _run_git(cmd, target_dir, 30)
            if rc != 0:
                raise _ComponentUnavailable(
                    f"could not initialize git in the target ({out}); "
                    f"git init + commit, then: git subtree add "
                    f"--prefix=scripts {url} main --squash")
        print("  [with:common] initialized git repository (subtree requires "
              "a commit)")
    rc, out = _run_git(["subtree", "add", "--prefix=scripts", url,
                        "main", "--squash"], target_dir, _GIT_SUBTREE_TIMEOUT)
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
        _sh.rmtree(tmp, ignore_errors=True)

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
}'''

assert s.count(OLD_BLOCK) == 1, "stub block not found verbatim"
s = s.replace(OLD_BLOCK, NEW_BLOCK)

OLD_CALL = "            added = _WITH_COMPONENTS[name](target_dir, placeholders)"
NEW_CALL = "            added = _WITH_COMPONENTS[name](target_dir, placeholders, defaults)"
assert s.count(OLD_CALL) == 1
s = s.replace(OLD_CALL, NEW_CALL)

OLD_SIG = "def _apply_with_components(target_dir, components, placeholders):"
NEW_SIG = "def _apply_with_components(target_dir, components, placeholders, defaults=None):"
assert s.count(OLD_SIG) == 1
s = s.replace(OLD_SIG, NEW_SIG)

OLD_SITE = "        _apply_with_components(target, with_components, placeholders)"
NEW_SITE = ("        _apply_with_components(target, with_components, placeholders,\n"
            "                               defaults=new_defaults)")
assert s.count(OLD_SITE) == 1
s = s.replace(OLD_SITE, NEW_SITE)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("4d-6 appliers wired (4 replacements)")
