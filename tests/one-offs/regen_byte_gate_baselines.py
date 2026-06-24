"""Regenerate the byte-gate baselines from current `dz` output.

Companion to run_byte_gate.py. Captures each command's stdout+stderr under
the same fixed config and writes them as the new baseline .txt files, so the
byte-gate can be re-based after an intentional, reviewed change to the tool
set or output format.

Usage:
    python tests/one-offs/regen_byte_gate_baselines.py <target_dir>

The CMDS list and config MUST stay in sync with run_byte_gate.py.
"""
import os
import subprocess
import sys

# Keep in sync with run_byte_gate.py
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


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    target = sys.argv[1]
    os.makedirs(target, exist_ok=True)

    import tempfile
    with tempfile.TemporaryDirectory() as T:
        cfg_path = os.path.join(T, "c.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(cfg_content)
        env = os.environ.copy()
        env["DAZZLECMD_CONFIG"] = cfg_path

        for name, cmd in CMDS:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, env=env,
                encoding="utf-8", errors="replace",
            )
            out = result.stdout + result.stderr
            path = os.path.join(target, f"{name}.txt")
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(out)
            print(f"wrote {name}.txt ({len(out)} bytes)")

    print(f"\nRegenerated {len(CMDS)} baselines into {target}")


if __name__ == "__main__":
    main()
