"""The sourced `dzr` for bash: install rules, and its behaviour in a real bash.

Rule 1b: the install folder, the home folder and the trash are stubbed; the bash runs use a
stub `dz` that only writes a folder name, so nothing real is claimed, run or deleted.
"""

import os
import shutil
import subprocess
import sys
import types

import pytest

import relaunch
import relaunch_actions as act
import relaunch_wrappers as wr


@pytest.fixture(autouse=True)
def target(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(wr, "install_dir", lambda: str(scripts))
    monkeypatch.setattr(wr, "_home", lambda: str(home))
    trashed = []
    monkeypatch.setattr(act, "trash_store", lambda: types.SimpleNamespace(
        trash=lambda paths: (trashed.extend(paths), [os.remove(p) for p in paths])))
    return types.SimpleNamespace(scripts=scripts, home=home, trashed=trashed)


def _posix_host(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")


# --- install rules -------------------------------------------------------------

def test_installed_file_is_lf_with_the_marker(target, monkeypatch):
    _posix_host(monkeypatch)
    assert relaunch.main(["shell-init", "bash", "--install"]) == 0
    data = (target.scripts / "dzr").read_bytes()
    assert b"\r" not in data
    assert wr.SOURCED_MARKER.encode() in data[:300]
    assert data == wr.wrapper_text("sourced").encode("ascii")


def test_install_current_foreign_uninstall(target, monkeypatch, capsys):
    _posix_host(monkeypatch)
    path = target.scripts / "dzr"
    assert relaunch.main(["shell-init", "bash", "--install"]) == 0
    err = capsys.readouterr().err
    assert ". dzr <set> claim" in err and "alias dzr='. dzr'" in err
    assert relaunch.main(["shell-init", "bash", "--install"]) == 0
    assert "already current" in capsys.readouterr().err
    assert relaunch.main(["shell-init", "bash", "--uninstall"]) == 0
    assert target.trashed == [str(path)] and not path.exists()
    path.write_bytes(b"#!/bin/sh\necho someone else's dzr\n")
    assert relaunch.main(["shell-init", "bash", "--install"]) == 3
    assert path.read_bytes() == b"#!/bin/sh\necho someone else's dzr\n"
    assert relaunch.main(["shell-init", "bash", "--uninstall"]) == 3


def test_windows_host_uses_home_bin_and_removes_it_only_if_ours(target, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    homebin = target.home / "bin"
    assert relaunch.main(["shell-init", "bash", "--install"]) == 0
    assert (homebin / "dzr").exists() and not (target.scripts / "dzr").exists()
    assert relaunch.main(["shell-init", "bash", "--uninstall"]) == 0
    assert not homebin.exists()                       # we made it, it was empty
    homebin.mkdir()
    (homebin / "other-tool").write_text("x")
    assert relaunch.main(["shell-init", "bash", "--install"]) == 0
    assert relaunch.main(["shell-init", "bash", "--uninstall"]) == 0
    assert homebin.exists() and (homebin / "other-tool").exists()   # not ours: left alone


def test_printed_function_still_offered(capsys):
    assert relaunch.main(["shell-init", "bash"]) == 0
    cap = capsys.readouterr()
    assert cap.out.startswith("# dzr") and "dzr() {" in cap.out
    assert "shell-init bash --install" in cap.err


# --- behaviour in a real bash --------------------------------------------------

def _bash():
    git_bash = r"C:\Program Files\Git\bin\bash.exe"
    if sys.platform == "win32":
        return git_bash if os.path.exists(git_bash) else None   # not System32's WSL launcher
    return shutil.which("bash")


STUB_DZ = b"""#!/bin/sh
# stub dz for tests: `dz relaunch go [rc]` writes the target folder; anything else writes nothing
if [ "$2" = "go" ] && [ -n "$DZ_RELAUNCH_CD_FILE" ]; then
  printf '%s\\n' "$DZR_TEST_TARGET" > "$DZ_RELAUNCH_CD_FILE"
fi
exit "${3:-0}"
"""


@pytest.fixture
def shell(tmp_path):
    bash = _bash()
    if not bash:
        pytest.skip("no bash on this machine")
    binf = tmp_path / "bin"
    binf.mkdir()
    (binf / "dz").write_bytes(STUB_DZ)
    (binf / "dzr").write_bytes(wr.wrapper_text("sourced").encode("ascii"))
    os.chmod(binf / "dz", 0o755)
    (tmp_path / "tgt dir").mkdir()

    def run(script):
        prelude = ('base=$PWD; export PATH="$base/bin:$PATH"; '
                   'export DZR_TEST_TARGET="$base/tgt dir"; cd / || exit 9; ')
        p = subprocess.run([bash, "--norc", "--noprofile", "-c", prelude + script],
                           cwd=str(tmp_path), capture_output=True, text=True, timeout=60)
        return p
    return run


def test_dot_dzr_changes_this_shells_folder(shell):
    p = shell('. dzr go; echo "rc=$? pwd=$PWD"')
    assert "rc=0" in p.stdout and p.stdout.strip().endswith("/tgt dir"), p.stdout + p.stderr


def test_refusal_passes_the_status_back_and_the_shell_survives(shell):
    p = shell('. dzr fail 3; echo "rc=$?"; echo still-alive; '
              'type __dzr_main >/dev/null 2>&1 && echo leaked-fn || echo no-fn; '
              '[ -z "${_dzr_rc+x}${_dzr_tmp+x}${_dzr_dir+x}" ] && echo no-vars || echo leaked-vars; '
              'echo "pwd=$PWD"')
    out = p.stdout
    assert "rc=3" in out and "still-alive" in out, out + p.stderr
    assert "no-fn" in out and "no-vars" in out and "pwd=/" in out


def test_callers_arguments_are_left_alone(shell):
    p = shell('set -- keep these; . dzr go; echo "args=$1,$2"; '
              'set -- keep these; . dzr; echo "args=$1,$2"')
    assert p.stdout.count("args=keep,these") == 2, p.stdout + p.stderr


def test_running_it_without_the_dot_is_refused(shell, tmp_path):
    bash = _bash()
    p = subprocess.run([bash, "--norc", "-c", 'bash "$PWD/bin/dzr" go'],
                       cwd=str(tmp_path), capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and "source it" in p.stderr, p.stdout + p.stderr
