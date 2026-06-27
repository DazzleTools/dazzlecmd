"""Re-bless the 4 dz_info_* byte-gate goldens after SD-A slice 3.

`dz info <tool>` now appends a `Current state:` (mode) section -- the
deliberate, user-approved change (full-subsumption Option A). This regenerates
the affected baselines using the SAME capture method as run_byte_gate.py
(subprocess + the temp DAZZLECMD_CONFIG), so the gate stays the oracle.

Only the 4 dz_info_* goldens change; list/mode_status/tree are untouched here.
"""
import os
import subprocess
import tempfile

BASE = r"C:\code\dazzlecmd\github\tests\one-offs\baselines_v0.10.11"

INFO_CMDS = [
    ("dz_info_core_find", "dz info core:find"),
    ("dz_info_core_safedel", "dz info core:safedel"),
    ("dz_info_core_listall", "dz info core:listall"),
    ("dz_info_dazzletools_git", "dz info dazzletools:git"),
]

cfg_content = '{"list_view":"default","_schema_version":1,"active_kits":["media","wtf"],"disabled_kits":[]}'

with tempfile.TemporaryDirectory() as T:
    cfg_path = os.path.join(T, "c.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(cfg_content)
    env = os.environ.copy()
    env["DAZZLECMD_CONFIG"] = cfg_path

    for name, cmd in INFO_CMDS:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, env=env,
            encoding="utf-8", errors="replace",
        )
        actual = result.stdout + result.stderr
        path = os.path.join(BASE, f"{name}.txt")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(actual)
        print(f"re-blessed {name} ({len(actual.splitlines())} lines)")

print("done -- run run_byte_gate.py to confirm 10 OK")
