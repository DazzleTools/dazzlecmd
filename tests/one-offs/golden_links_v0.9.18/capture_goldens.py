"""Golden-output capture for the links tool (DWP step 1, links-fork fix).

Builds a deterministic link fixture at a FIXED temp path, runs `dz links` over
it (help / table / json), and writes the outputs next to this script. Run once
BEFORE the engine/CLI split (v0.9.18) and again AFTER the rewire; the outputs
must be byte-identical (modulo nothing -- same fixture path both runs).

Usage:
    python tests/one-offs/golden_links_v0.9.18/capture_goldens.py before
    python tests/one-offs/golden_links_v0.9.18/capture_goldens.py after
    # then: diff/fc the before_*.txt vs after_*.txt files
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(os.environ.get("TEMP", "/tmp"), "dz_links_golden_fixture")


def build_fixture():
    """Symlink + junction + hardlink + a plain file, at a stable path."""
    if os.path.isdir(FIXTURE):
        return  # reuse the exact same fixture across before/after runs
    os.makedirs(FIXTURE)
    target_dir = os.path.join(FIXTURE, "target_dir")
    os.makedirs(target_dir)
    plain = os.path.join(FIXTURE, "plain.txt")
    with open(plain, "w", encoding="utf-8") as f:
        f.write("plain contents")
    # hardlink
    os.link(plain, os.path.join(FIXTURE, "hard.txt"))
    # dir junction (PowerShell per CLAUDE rule #4; junction needs no elevation)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"New-Item -ItemType Junction -Path '{FIXTURE}\\junc' "
         f"-Target '{target_dir}' | Out-Null"],
        check=True, capture_output=True,
    )
    # file symlink (works with Developer Mode; skip silently if not permitted)
    try:
        os.symlink(plain, os.path.join(FIXTURE, "sym.txt"))
    except OSError:
        pass


def capture(tag):
    build_fixture()
    runs = {
        f"{tag}_help.txt": ["dz", "links", "--help"],
        f"{tag}_table.txt": ["dz", "links", FIXTURE],
        f"{tag}_json.txt": ["dz", "links", FIXTURE, "--json"],
    }
    for fname, cmd in runs.items():
        r = subprocess.run(cmd, capture_output=True, text=True, shell=True,
                           encoding="utf-8", errors="replace")
        with open(os.path.join(HERE, fname), "w", encoding="utf-8",
                  newline="") as f:
            f.write(r.stdout + r.stderr)
        print(f"captured {fname} (rc={r.returncode}, {len(r.stdout)}b)")


if __name__ == "__main__":
    capture(sys.argv[1] if len(sys.argv) > 1 else "before")
