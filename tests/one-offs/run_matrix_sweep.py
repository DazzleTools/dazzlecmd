"""Driver (2026-07-07, tester-unbounded merge-cert sweep, Task 1): execute
every probe from surface_matrix_gen.py as a COLD `dz` subprocess run
(fresh process per probe, isolated DAZZLECMD_CONFIG), and classify:
  - class == "vacant"      -> PASS iff exit code != 0
  - anything else          -> PASS iff exit code == 0 and stdout is
                               non-empty / has no traceback marker

Writes a JSON report to the path given as argv[1] (default: stdout only
summary). Never touches ~/.dz -- DAZZLECMD_CONFIG is pointed at a fresh
tempfile for the whole sweep (all probes here are read-only: `info` /
`:.` listing reads, never verb execution).
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from surface_matrix_gen import emit  # noqa: E402


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else None

    probes, consistency = emit()

    cfg_dir = tempfile.mkdtemp(prefix="dz_matrix_sweep_")
    cfg_path = os.path.join(cfg_dir, "c.json")
    env = dict(os.environ)
    env["DAZZLECMD_CONFIG"] = cfg_path

    results = []
    for p in probes:
        cmd_str = p["cmd"]
        args = cmd_str.split(" ")
        assert args[0] == "dz"
        proc = subprocess.run(["dz"] + args[1:], env=env,
                              capture_output=True, text=True, timeout=30)
        combined = (proc.stdout or "") + (proc.stderr or "")
        head = "\n".join(combined.splitlines()[:6])
        has_traceback = "Traceback (most recent call last)" in combined
        if p["class"] == "vacant":
            ok = proc.returncode != 0
        else:
            ok = (proc.returncode == 0 and combined.strip() != ""
                  and not has_traceback)
        results.append({
            "class": p["class"], "node": p["node"], "cmd": cmd_str,
            "exit": proc.returncode, "ok": ok, "head": head,
        })

    by_class = {}
    for r in results:
        by_class.setdefault(r["class"], {"pass": 0, "fail": 0, "fails": []})
        key = "pass" if r["ok"] else "fail"
        by_class[r["class"]][key] += 1
        if not r["ok"]:
            by_class[r["class"]]["fails"].append(r)

    total = len(results)
    total_pass = sum(1 for r in results if r["ok"])
    print(f"TOTAL probes: {total}  PASS: {total_pass}  FAIL: {total - total_pass}")
    print(f"config isolated to: {cfg_path}")
    print()
    for cls in sorted(by_class):
        c = by_class[cls]
        print(f"[{cls}] pass={c['pass']} fail={c['fail']}")
        for f in c["fails"]:
            print(f"    FAIL exit={f['exit']} cmd={f['cmd']}")
            print(f"         head: {f['head']!r}")

    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"results": results, "consistency": consistency,
                       "cfg_path": cfg_path}, fh, indent=1)
        print(f"\nfull report written to: {out_path}")

    return 0 if total_pass == total else 1


if __name__ == "__main__":
    sys.exit(main())
