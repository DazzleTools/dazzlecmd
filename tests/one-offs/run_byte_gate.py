"""Byte-gate oracle for default_meta_commands.py migration.

Runs each dz command, captures output, and compares against baselines.
Any diff beyond dz_tree line 1 (version string) is a failure.
"""
import os
import subprocess
import sys
import tempfile

BASE = r"C:\code\dazzlecmd\github\tests\one-offs\baselines_v0.7.54"

CMDS = [
    ("dz_list", "dz list"),
    ("dz_list_all", "dz list --show all"),
    ("dz_list_canonical", "dz list --show canonical"),
    ("dz_list_alias", "dz list --show alias"),
    ("dz_mode_status", "dz mode status"),
    ("dz_info_core_find", "dz info core:find"),
    ("dz_info_core_safedel", "dz info core:safedel"),
    ("dz_info_core_listall", "dz info core:listall"),
    ("dz_info_dazzletools_git", "dz info dazzletools:git"),
    ("dz_tree", "dz tree"),
]

cfg_content = '{"list_view":"default","_schema_version":1,"active_kits":["media","wtf"],"disabled_kits":[]}'

failures = []
oks = []

with tempfile.TemporaryDirectory() as T:
    cfg_path = os.path.join(T, "c.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(cfg_content)

    env = os.environ.copy()
    env["DAZZLECMD_CONFIG"] = cfg_path

    for name, cmd in CMDS:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, env=env,
            encoding="utf-8", errors="replace"
        )
        actual = result.stdout + result.stderr

        baseline_path = os.path.join(BASE, f"{name}.txt")
        with open(baseline_path, "r", encoding="utf-8", errors="replace") as f:
            baseline = f.read()

        if name == "dz_tree":
            # Only line 1 (version banner) may differ
            actual_lines = actual.splitlines()
            baseline_lines = baseline.splitlines()
            # Skip line 0 for comparison
            actual_rest = actual_lines[1:] if len(actual_lines) > 1 else []
            baseline_rest = baseline_lines[1:] if len(baseline_lines) > 1 else []
            if actual_rest != baseline_rest:
                failures.append((name, baseline_rest, actual_rest))
            else:
                oks.append(name)
                if actual_lines and baseline_lines and actual_lines[0] != baseline_lines[0]:
                    print(f"OK {name} (line 1 differs as expected: {baseline_lines[0]!r} -> {actual_lines[0]!r})")
                else:
                    print(f"OK {name}")
        else:
            if actual.rstrip("\n") != baseline.rstrip("\n"):
                # Show unified diff
                import difflib
                diff = list(difflib.unified_diff(
                    baseline.splitlines(), actual.splitlines(),
                    fromfile=f"baseline/{name}", tofile=f"actual/{name}",
                    lineterm=""
                ))
                failures.append((name, diff))
                print(f"FAIL {name}")
                for line in diff[:30]:
                    print(f"  {line}")
            else:
                oks.append(name)
                print(f"OK {name}")

print()
print(f"Results: {len(oks)} OK, {len(failures)} FAIL")
if failures:
    sys.exit(1)
else:
    sys.exit(0)
