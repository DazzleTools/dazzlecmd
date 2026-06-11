"""Watchable, SAFE end-to-end demo of `dz mode switch` (dev) -> `dz mode restore`.

Why this exists: the installed `dz` CLI anchors its project root to its own
package location (aggregator.json), so `dz mode switch <tool>` / `dz mode restore
<tool>` ALWAYS act on the real dazzlecmd repo's tools -- you cannot safely point
the `dz` binary at a sandbox. This script drives the SAME library functions
(`mode.cmd_switch` / `mode.cmd_restore`) with an EXPLICIT throwaway project root
and an ISOLATED trash store, so it exercises the real round-trip (real junction,
real safedel backup + recovery) while touching NOTHING real:

  - a fresh temp dir is the aggregator root (never your repo),
  - the safedel TrashStore is redirected under that temp dir (never your real
    trash store),
  - everything is removed at the end.

Run it:  python tests/one-offs/verify_mode_restore_sandbox.py
Expect:  a step-by-step trace ending in  RESULT: PASS
"""
import os
import shutil
import tempfile

import dazzlecmd_lib.core.safedel as _sd
from dazzlecmd_lib import mode
from dazzlecmd_lib.entity import build_entity
from dazzlecmd_lib.paths import is_linked_project


def _banner(msg):
    print("\n" + "=" * 70 + f"\n  {msg}\n" + "=" * 70)


def main():
    root = tempfile.mkdtemp(prefix="dz_restore_demo_")
    # Redirect the safedel trash store under the sandbox so we never write to
    # the user's real trash store (the function-local `from ... import TrashStore`
    # in mode.py resolves this patched module attribute at call time).
    real_trashstore = _sd.TrashStore
    store_path = os.path.join(root, "_trash")
    reg_path = os.path.join(root, "_trash_reg.json")

    def _isolated_store(*a, **k):
        k.setdefault("store_path", store_path)
        k.setdefault("registry_path", reg_path)
        return real_trashstore(*a, **k)

    _sd.TrashStore = _isolated_store
    try:
        # --- build a throwaway EMBEDDED tool + a separate "dev repo" ---
        tool_dir = os.path.join(root, "projects", "core", "demo")
        os.makedirs(tool_dir)
        with open(os.path.join(tool_dir, "demo.py"), "w", encoding="utf-8") as f:
            f.write("EMBEDDED CONTENT -- the original on-disk form")
        dev_src = os.path.join(root, "devsrc")
        os.makedirs(dev_src)
        with open(os.path.join(dev_src, "demo.py"), "w", encoding="utf-8") as f:
            f.write("DEV CONTENT -- a different copy in the dev repo")

        project = build_entity({
            "name": "demo", "namespace": "core", "version": "1.0.0",
            "description": "throwaway sandbox tool", "directory": tool_dir,
            "_fqcn": "core:demo",
            "runtime": {"type": "python", "script_path": "demo.py"},
        }, entity_type="tool")

        print(f"Sandbox aggregator root : {root}")
        print(f"Embedded tool dir       : {tool_dir}")
        print(f"Dev repo (symlink target): {dev_src}")

        # --- 1) switch to DEV mode (the 'ungroup': embedded dir -> symlink) ---
        _banner("dz mode switch demo --path <devsrc>   (enter dev mode)")
        rc = mode.cmd_switch(
            "demo", [project], root, dev_path=dev_src, force_mode="dev",
            tools_dir="projects", command="dz",
        )
        assert rc == 0, "switch-to-dev failed"
        assert is_linked_project(tool_dir), "tool dir should now be a symlink/junction"
        origin = mode._load_full_config(root)["origins"]["core:demo"]
        print(f"\n  [check] tool dir is now a link      : {is_linked_project(tool_dir)}")
        print(f"  [check] origin recorded             : prior_state="
              f"{origin['prior_state']!r}, trash_folder={origin['trash_folder']!r}")
        cur = open(os.path.join(tool_dir, "demo.py"), encoding="utf-8").read()
        print(f"  [check] demo.py through the link    : {cur!r}  (the DEV copy)")

        # --- 2) restore (the 'group': symlink -> recovered embedded content) ---
        _banner("dz mode restore demo   (undo the dev switch)")
        rc = mode.cmd_restore(
            "demo", [project], root, tools_dir="projects", command="dz",
        )
        assert rc == 0, "restore failed"
        assert not is_linked_project(tool_dir), "tool dir should be a real dir again"
        restored = open(os.path.join(tool_dir, "demo.py"), encoding="utf-8").read()
        dev_after = open(os.path.join(dev_src, "demo.py"), encoding="utf-8").read()
        origins_after = mode._load_full_config(root)["origins"]
        print(f"\n  [check] tool dir is a link          : {is_linked_project(tool_dir)}  (expect False)")
        print(f"  [check] demo.py restored to         : {restored!r}  (the EMBEDDED original)")
        print(f"  [check] dev repo untouched          : {dev_after!r}")
        print(f"  [check] origin cleared              : {'core:demo' not in origins_after}")

        ok = (
            restored == "EMBEDDED CONTENT -- the original on-disk form"
            and dev_after == "DEV CONTENT -- a different copy in the dev repo"
            and not is_linked_project(tool_dir)
            and "core:demo" not in origins_after
        )
        _banner(f"RESULT: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    finally:
        _sd.TrashStore = real_trashstore
        shutil.rmtree(root, ignore_errors=True)
        print(f"(cleaned up sandbox {root})")


if __name__ == "__main__":
    raise SystemExit(main())
