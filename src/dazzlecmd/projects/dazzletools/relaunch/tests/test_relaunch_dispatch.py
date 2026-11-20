"""S9: dz relaunch through the real dispatcher (registered in the dazzletools kit)."""

import os
import subprocess
import sys


def _dz(args, home):
    env = dict(os.environ, DZ_RELAUNCH_HOME=str(home), NO_COLOR="1")
    return subprocess.run([sys.executable, "-m", "dazzlecmd", "relaunch", *args],
                          capture_output=True, text=True, env=env, timeout=120)


def test_help_through_dz(relaunch_home):
    r = _dz(["--help"], relaunch_home)
    assert r.returncode == 0 and "dz relaunch" in r.stdout and "claim" in r.stdout


def test_dashboard_and_new_through_dz(relaunch_home):
    r = _dz([], relaunch_home)
    assert r.returncode == 0 and r.stdout.strip().splitlines()[-1] == "relaunch: LISTED 0 sets"
    r = _dz(["new", "probe"], relaunch_home)
    assert r.returncode == 0 and "relaunch: CREATED probe" in r.stdout
    assert os.path.isfile(os.path.join(str(relaunch_home), "sets", "probe.json"))
