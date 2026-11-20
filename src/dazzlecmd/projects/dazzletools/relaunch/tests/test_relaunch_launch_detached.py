"""Detached members and `launch` (spawners stubbed -- no real program starts; rule 1b)."""

import json
import os
import sys

import pytest

import relaunch
import relaunch_claims as rc
import relaunch_cli_io as io
import relaunch_launch as rl
import relaunch_store as rs


@pytest.fixture(autouse=True)
def w(monkeypatch):
    started, boot = [], {"t": 1000.0}

    def fake_detached(command, cwd, env):
        started.append((command, cwd, env))

    def no_spawn(command, cwd, env):
        raise AssertionError("claim -o must not run in these tests")
    monkeypatch.setattr(rl, "spawn_detached", fake_detached)
    monkeypatch.setattr(rl, "spawn", no_spawn)
    monkeypatch.setattr(rl, "resolve_program", lambda name: sys.executable if name == "python" else name)
    alive = {4242: True}
    monkeypatch.setattr(rc, "default_liveness", lambda a: alive.get(a.get("pid"), False))
    monkeypatch.setattr(rc, "default_boot", lambda: boot["t"])
    monkeypatch.setattr(rc, "current_tab", lambda pid=None: rc.Tab(4242, "cmd.exe", 1, "test"))
    monkeypatch.setattr(io, "is_console", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    monkeypatch.delenv("DZ_RELAUNCH_OPEN_ASKS", raising=False)
    relaunch.main(["new", "ck3"])
    relaunch.main(["ck3", "add", os.getcwd(), "--label", "repo"])
    relaunch.main(["ck3", "add", "--detach", "--label", "vscode", "--", "python", "-c", "pass"])
    return type("W", (), {"started": started, "boot": boot})


def test_bare_claim_never_takes_a_detached_member(capsys):
    assert relaunch.main(["ck3", "claim"]) == 0
    assert relaunch.main(["ck3", "claim", "--next"]) == 3          # only repo is a tab member
    assert "nothing left to claim" in capsys.readouterr().out
    doc = rs.load_set("ck3")
    assert rs.find_member(doc, "vscode")["detach"] is True


def test_explicit_claim_of_a_detached_member_points_at_launch(capsys):
    assert relaunch.main(["ck3", "claim", "vscode"]) == 3
    assert "dz relaunch ck3 launch vscode" in capsys.readouterr().err


def test_launch_starts_once_per_boot_and_member_forces(w, capsys):
    assert relaunch.main(["ck3", "launch"]) == 0
    assert len(w.started) == 1 and w.started[0][0] == [sys.executable, "-c", "pass"]
    assert relaunch.main(["ck3", "launch"]) == 0                    # same boot: nothing
    assert len(w.started) == 1 and "nothing to launch" in capsys.readouterr().out
    assert relaunch.main(["ck3", "launch", "vscode"]) == 0          # named: always
    assert len(w.started) == 2
    w.boot["t"] += 5000                                             # a restart
    assert relaunch.main(["ck3", "launch"]) == 0
    assert len(w.started) == 3


def test_launch_asks_and_no_means_nothing(w, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert relaunch.main(["ck3", "launch"]) == 3
    assert w.started == []


def test_launch_without_console_only_prints(w, monkeypatch):
    monkeypatch.setattr(io, "is_console", lambda: False)
    assert relaunch.main(["ck3", "launch", "-y"]) == 0
    assert w.started == []


def test_launch_env_is_scrubbed(w, monkeypatch):
    monkeypatch.setenv("DZ_RELAUNCH_CD_FILE", "x")
    monkeypatch.setenv("DZ_COMMAND", "relaunch")
    relaunch.main(["ck3", "launch", "-y"])
    env = w.started[0][2]
    assert "DZ_RELAUNCH_CD_FILE" not in env and "DZ_COMMAND" not in env


def test_only_command_or_shell_members_can_detach():
    doc = rs.load_set("ck3")
    m = rs.find_member(doc, "repo")
    m["detach"] = True
    with pytest.raises(rs.StoreError, match="only command and shell"):
        rs.validate_member(m)


def test_edit_toggles_detach(capsys):
    assert relaunch.main(["ck3", "edit", "vscode", "--no-detach"]) == 0
    assert "detach" not in rs.find_member(rs.load_set("ck3"), "vscode")
    assert relaunch.main(["ck3", "edit", "vscode", "--detach"]) == 0
    assert rs.find_member(rs.load_set("ck3"), "vscode")["detach"] is True
