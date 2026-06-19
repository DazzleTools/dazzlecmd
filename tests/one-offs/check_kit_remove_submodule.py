"""One-off: validate `dz kit remove`'s submodule git-surgery in an ISOLATED tmp git
repo. No real-repo mutation, no root-anchoring -- `_cmd_kit_remove` takes project_root,
so we point it at a throwaway aggregator with a real file:// submodule. Verifies the
v0.9.51 bug fix (is_submodule detection + non-destructive untrack + recoverable safedel)."""
import os
import sys
import json
import shutil
import types
import tempfile
import subprocess


def git(args, cwd, check=True):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    r = subprocess.run(["git"] + args, cwd=str(cwd), env=env,
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"SETUP git {args} FAILED ({r.returncode}): {r.stderr.strip()}")
        sys.exit(2)
    return r


tmp = tempfile.mkdtemp(prefix="kitrm_")
ok = True
def chk(label, cond, extra=""):
    global ok
    print(f"  {'[OK]' if cond else '[XX]'} {label}" + (f"  -- {extra}" if extra else ""))
    ok = ok and bool(cond)

try:
    # 1. a bare source repo with one commit
    bare = os.path.join(tmp, "src.git")
    git(["init", "--bare", "-b", "main", bare], tmp)
    work = os.path.join(tmp, "work")
    git(["clone", bare, work], tmp)
    open(os.path.join(work, "f.txt"), "w").write("x")
    git(["add", "."], work); git(["commit", "-m", "i"], work)
    git(["push", "origin", "main"], work)

    # 2. an aggregator repo with the kit added as a real submodule + registry pointer
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo); git(["init", "-b", "main", repo], tmp)
    open(os.path.join(repo, "seed.txt"), "w").write("x")
    git(["add", "."], repo); git(["commit", "-m", "seed"], repo)
    bare_uri = "file:///" + bare.replace("\\", "/").lstrip("/")
    git(["-c", "protocol.file.allow=always", "submodule", "add", bare_uri,
         "projects/dummytest"], repo)
    git(["commit", "-m", "add submodule"], repo)
    os.makedirs(os.path.join(repo, "kits"), exist_ok=True)
    json.dump({"name": "dummytest", "always_active": False, "source": bare_uri},
              open(os.path.join(repo, "kits", "dummytest.kit.json"), "w"))

    # 3. isolate config + fake the trash store (recoverable backup -> a tmp dir)
    trashdir = os.path.join(tmp, "trash"); os.makedirs(trashdir)
    import dazzlecmd_lib.core.safedel as sd

    class _FakeTS:
        def trash(self, paths, dry_run=False):
            for p in paths:
                shutil.move(str(p), os.path.join(trashdir, os.path.basename(str(p))))
            return types.SimpleNamespace(success=True, folder_name="x", errors=[])
    sd.TrashStore = lambda *a, **k: _FakeTS()

    cfg = os.path.join(tmp, "config.json")
    open(cfg, "w").write('{"active_kits": ["dummytest"], "disabled_kits": []}')
    os.environ["DAZZLECMD_CONFIG"] = cfg
    from dazzlecmd.engine import AggregatorEngine
    eng = AggregatorEngine(); eng.kits = []

    from dazzlecmd.cli import _cmd_kit_remove, _kit_is_submodule
    print("== detection ==")
    chk("_kit_is_submodule sees the 2-part kit submodule", _kit_is_submodule(repo, "dummytest"))

    class _A:
        name = "dummytest"; dry_run = False; yes = True; force = False
    print("== _cmd_kit_remove ==")
    rc = _cmd_kit_remove(_A(), repo, eng)

    chk("rc == 0", rc == 0, f"rc={rc}")
    chk("projects/dummytest gone (untracked + trashed)",
        not os.path.exists(os.path.join(repo, "projects", "dummytest")))
    chk("worktree recoverable (in fake trash)",
        os.path.exists(os.path.join(trashdir, "dummytest")))
    chk("kits/dummytest.kit.json deregistered",
        not os.path.exists(os.path.join(repo, "kits", "dummytest.kit.json")))
    gm = os.path.join(repo, ".gitmodules")
    chk(".gitmodules has no dummytest section",
        (not os.path.isfile(gm)) or "dummytest" not in open(gm, encoding="utf-8").read())
    gc = git(["config", "--get-regexp", "submodule.*dummytest"], repo, check=False)
    chk(".git/config submodule entry cleared",
        gc.returncode != 0 or not gc.stdout.strip(), gc.stdout.strip())
    st = git(["status", "--porcelain"], repo).stdout
    chk("no orphan 'AD' gitlink left in the index", "AD " not in st, st.replace("\n", " | "))
    chk(".git/modules cache dropped",
        not os.path.isdir(os.path.join(repo, ".git", "modules", "projects", "dummytest")))

    print("\nfinal git status:\n" + (st or "  (clean)"))
    print("\nRESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
