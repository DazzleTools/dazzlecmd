"""Hands-on demo: watch dz kit detach -> attach round-trip on a throwaway repo.

Builds a sandbox aggregator with a real submodule kit, then drives the
detach/attach engine directly (the CLI is root-anchored to dz's install
tree, so a sandbox must call the engine with an explicit root -- this is
exactly what the tester-unbounded run does). Prints each step so you can
SEE what changes. Sandbox lives under %TEMP%; nothing touches the real repo.

Run:  python tests/one-offs/demo_detach_attach.py
      python tests/one-offs/demo_detach_attach.py --keep   (leave sandbox for poking)
"""
import json
import os
import subprocess
import sys
import tempfile

from dazzlecmd_lib import mode


def git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=str(cwd), text=True,
                       capture_output=True, env=mode.sanitized_git_env())
    if r.returncode != 0:
        print(f"  ! git {' '.join(args)} -> {r.stderr.strip()}")
    return r.stdout


def init_repo(path):
    os.makedirs(path, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    # No GPG -- avoids the Kleopatra popup (project convention for sandboxes).
    git(path, "config", "commit.gpgsign", "false")
    git(path, "config", "tag.gpgsign", "false")
    git(path, "config", "user.name", "demo")
    git(path, "config", "user.email", "demo@demo")
    git(path, "config", "protocol.file.allow", "always")


def banner(text):
    print("\n" + "=" * 64 + f"\n  {text}\n" + "=" * 64)


def show_tracking(parent, label):
    print(f"\n-- git ls-files ({label}):")
    for line in git(parent, "ls-files").splitlines():
        print(f"     {line}")


def main():
    keep = "--keep" in sys.argv
    root = tempfile.mkdtemp(prefix="dz-detach-demo-")
    remote = os.path.join(root, "demo_remote")
    parent = os.path.join(root, "myagg")

    banner("SETUP: a kit 'remote' + a parent aggregator that embeds it as a submodule")
    init_repo(remote)
    with open(os.path.join(remote, "aggregator.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "demo", "description": "a demo kit"}, f)
    git(remote, "add", "-A")
    git(remote, "commit", "-q", "-m", "kit init")

    init_repo(parent)
    with open(os.path.join(parent, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("mode_local.json\n")
    os.makedirs(os.path.join(parent, "kits"))
    with open(os.path.join(parent, "kits", "demo.kit.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "demo", "always_active": False,
                   "source": remote.replace(os.sep, "/")}, f, indent=4)
    git(parent, "add", "-A")
    git(parent, "commit", "-q", "-m", "base")
    git(parent, "submodule", "add", remote.replace(os.sep, "/"), "projects/demo")
    git(parent, "commit", "-q", "-m", "add demo kit")
    print(f"  sandbox: {parent}")
    show_tracking(parent, "BEFORE -- kit is a tracked submodule")
    before = git(parent, "ls-files", "-s")

    banner("DRY-RUN: dz kit detach demo --dry-run  (shows the plan, changes nothing)")
    mode.cmd_kit_detach("demo", parent, dry_run=True)

    banner("DETACH: dz kit detach demo")
    mode.cmd_kit_detach("demo", parent)
    show_tracking(parent, "AFTER detach -- kit no longer tracked")
    print("\n-- but the files are STILL ON DISK:")
    print("     projects/demo/aggregator.json exists:",
          os.path.isfile(os.path.join(parent, "projects", "demo", "aggregator.json")))
    print("     kits/demo.kit.json exists:",
          os.path.isfile(os.path.join(parent, "kits", "demo.kit.json")))
    print("\n-- .gitignore now has a managed block:")
    with open(os.path.join(parent, ".gitignore"), encoding="utf-8") as f:
        for line in f.read().splitlines():
            print(f"     {line}")
    print("\n-- the hookup record (so attach can undo this):")
    print("    ", json.dumps(mode._get_hookup("kit:demo", parent), indent=2)
          .replace("\n", "\n     "))
    print("\n-- git status (everything is STAGED for your review, never committed):")
    for line in git(parent, "status", "--short").splitlines():
        print(f"     {line}")

    git(parent, "commit", "-q", "-m", "detach demo")  # commit so attach is clean

    banner("ATTACH: dz kit attach demo  (the inverse)")
    mode.cmd_kit_attach("demo", parent)
    show_tracking(parent, "AFTER attach -- kit tracked again")
    after = git(parent, "ls-files", "-s")

    banner("RESULT")
    print("  Round-trip byte-identical (ls-files matches pre-detach):",
          after == before)
    print("  Hookup record cleared:",
          mode._get_hookup("kit:demo", parent) is None)
    gi = open(os.path.join(parent, ".gitignore"), encoding="utf-8").read()
    print("  Managed ignore block removed:", ">>> dz detach" not in gi)

    if keep:
        print(f"\n  Sandbox kept for poking: {parent}")
    else:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
        print("\n  (sandbox cleaned; re-run with --keep to inspect it)")


if __name__ == "__main__":
    main()
