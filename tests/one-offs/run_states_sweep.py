"""Driver (2026-07-07, tester-unbounded merge-cert sweep, Task 1 Row 4):
STATES x SURFACES for the level axis -- {unset, set, post-delete,
post-meta-reset} x {card, listing, bare read, `dz level` verb} must
agree. Sequential mutation against ONE isolated DAZZLECMD_CONFIG
(never ~/.dz).
"""
import os
import re
import subprocess
import sys
import tempfile


def run(args, env):
    proc = subprocess.run(["dz"] + args, env=env, capture_output=True,
                          text=True, timeout=30)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def read_surfaces(env):
    surfaces = {}

    rc, card = run(["info", ":.meta:level"], env)
    m = re.search(r"^\s*current:\s*(\S+)(\s*\(default\))?", card, re.MULTILINE)
    surfaces["card"] = (m.group(1), bool(m.group(2))) if m else (None, None)

    rc, listing = run([":.meta:level:."], env)
    m = re.search(r"^\s*(\S+)\s+.*<- current(\s*\(default\))?", listing,
                  re.MULTILINE)
    surfaces["listing"] = (m.group(1), bool(m.group(2))) if m else (None, None)

    rc, bare = run([":.meta:level"], env)
    lines = [ln for ln in bare.splitlines() if ln.strip()]
    val_line = lines[-1] if lines else ""
    m = re.match(r"^(\S+)(\s*\(default\))?", val_line)
    surfaces["bare"] = (m.group(1), bool(m.group(2))) if m else (None, None)

    rc, verb = run(["level"], env)
    lines = [ln for ln in verb.splitlines() if ln.strip()]
    val_line = lines[-1] if lines else ""
    m = re.match(r"^(\S+)(\s*\(default\))?", val_line)
    surfaces["verb"] = (m.group(1), bool(m.group(2))) if m else (None, None)

    return surfaces, {"card": card, "listing": listing, "bare": bare,
                       "verb": verb}


def check_state(name, env, raws_out):
    surfaces, raws = read_surfaces(env)
    raws_out[name] = raws
    values = {k: v[0] for k, v in surfaces.items()}
    defaults = {k: v[1] for k, v in surfaces.items()}
    agree_value = len(set(values.values())) == 1
    # default-marker agreement: only meaningful where the marker concept
    # applies to all 4 (it does for this axis in every state)
    agree_default = len(set(defaults.values())) == 1
    ok = agree_value and agree_default
    print(f"[{name}] surfaces={surfaces} value_agree={agree_value} "
          f"default_marker_agree={agree_default} -> {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    cfg_dir = tempfile.mkdtemp(prefix="dz_states_sweep_")
    env = dict(os.environ)
    env["DAZZLECMD_CONFIG"] = os.path.join(cfg_dir, "c.json")
    print(f"config isolated to: {env['DAZZLECMD_CONFIG']}")

    raws = {}
    results = {}

    # 1. unset -- fresh config, nothing written yet
    results["unset"] = check_state("unset", env, raws)

    # 2. set -- an explicit non-default rung
    rc, out = run(["level", "kit"], env)
    assert rc == 0, f"set failed: {out}"
    results["set"] = check_state("set", env, raws)

    # 3. post-delete -- explicit property delete
    rc, out = run(["prop", "delete", ":.meta:level"], env)
    assert rc == 0, f"delete failed: {out}"
    results["post-delete"] = check_state("post-delete", env, raws)

    # re-set so meta-reset has something non-default to reset FROM
    rc, out = run(["level", "supra"], env)
    assert rc == 0, f"re-set failed: {out}"

    # 4. post-meta-reset
    rc, out = run(["meta", "reset"], env)
    assert rc == 0, f"meta reset failed: {out}"
    results["post-meta-reset"] = check_state("post-meta-reset", env, raws)

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\nSTATES SWEEP: {passed}/{total} states PASS")

    if passed != total:
        print("\n--- raw output for failing states ---")
        for name, ok in results.items():
            if not ok:
                print(f"=== {name} ===")
                for surf, txt in raws[name].items():
                    print(f"  -- {surf} --")
                    print("  " + txt.replace("\n", "\n  "))

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
