"""shell-init: stdout is only the wrapper; --install / --uninstall (target folder stubbed -- rule 1b)."""

import os
import types

import pytest

import relaunch
import relaunch_actions as act
import relaunch_launch as rl
import relaunch_wrappers as wr


@pytest.fixture(autouse=True)
def target(tmp_path, monkeypatch):
    folder = tmp_path / "scripts"
    folder.mkdir()
    monkeypatch.setattr(wr, "install_dir", lambda: str(folder))   # never C:\Python312\Scripts
    trashed = []
    monkeypatch.setattr(act, "trash_store", lambda: types.SimpleNamespace(
        trash=lambda paths: (trashed.extend(paths), [os.remove(p) for p in paths])))
    return types.SimpleNamespace(folder=folder, trashed=trashed)


def test_stdout_is_only_the_wrapper(capsys):
    assert relaunch.main(["shell-init", "cmd"]) == 0
    cap = capsys.readouterr()
    assert cap.out.startswith("@echo off") and "relaunch:" not in cap.out
    assert "relaunch: PRINTED dzr for cmd" in cap.err
    assert relaunch.main(["shell-init", "bash"]) == 0
    assert "relaunch:" not in capsys.readouterr().out


def test_install_then_current_then_uninstall(target, capsys):
    path = target.folder / "dzr.cmd"
    assert relaunch.main(["shell-init", "cmd", "--install"]) == 0
    assert path.read_bytes() == wr.wrapper_text("cmd").encode("ascii")
    assert relaunch.main(["shell-init", "cmd", "--install"]) == 0
    assert "already current" in capsys.readouterr().err
    assert relaunch.main(["shell-init", "cmd", "--uninstall"]) == 0
    assert target.trashed == [str(path)] and not path.exists()


def test_install_refuses_a_foreign_file(target, capsys):
    path = target.folder / "dzr.cmd"
    path.write_bytes(b"@echo off\r\necho someone else's dzr\r\n")
    before = path.read_bytes()
    assert relaunch.main(["shell-init", "cmd", "--install"]) == 3
    assert path.read_bytes() == before
    assert relaunch.main(["shell-init", "cmd", "--uninstall"]) == 3
    assert path.exists()


def test_older_relaunch_wrapper_is_replaced(target):
    path = target.folder / "dzr.cmd"
    path.write_bytes(("@echo off\r\n" + wr.MARKER + "\r\nold body\r\n").encode("ascii"))
    assert relaunch.main(["shell-init", "cmd", "--install"]) == 0
    assert path.read_bytes() == wr.wrapper_text("cmd").encode("ascii")


def test_child_env_drops_the_handover_variables():
    env = rl.child_env({"DZ_RELAUNCH_CD_FILE": "x", "DZ_RELAUNCH_CD_FORMAT": "cmd", "PATH": "p"})
    assert env == {"PATH": "p"}


def test_cd_file_in_a_vanished_folder_returns_false(tmp_path):
    env = {rl.CD_FILE_ENV: str(tmp_path / "gone" / "cd.txt"), rl.CD_FORMAT_ENV: "posix"}
    assert rl.write_cd_file("/x", env=env) is False
