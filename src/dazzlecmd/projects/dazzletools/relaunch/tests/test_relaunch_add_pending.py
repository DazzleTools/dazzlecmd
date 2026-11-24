"""add --claude <name> when csb cannot see the session yet (0.13.16). csb and spawner stubbed -- rule 1b."""

import json

import pytest

import relaunch
import relaunch_claims as rc
import relaunch_cli_io as io
import relaunch_csb as csb
import relaunch_launch as rl
import relaunch_store as rs

NAME = "CK3__2026-11-24__worker-tools"
SID = "05ff5bbe-6d3c-4ffd-93de-74070af5c41b"


@pytest.fixture(autouse=True)
def world(monkeypatch):
    state = {"known": {}, "dupes": False}
    calls = {"spawn": []}

    def fake_csb(args, timeout=5.0):
        if args[:1] == ["scan"]:
            q = args[1]
            rows = [{"session_id": sid, "session_name": n} for n, sid in state["known"].items()
                    if q in (n, sid)]
            if state["dupes"] and q == NAME:
                rows = [{"session_id": "a" * 8, "session_name": NAME}, {"session_id": "b" * 8, "session_name": NAME}]
            return json.dumps(rows)
        if args[:2] == ["set", "show"]:
            return json.dumps({"members": []})
        raise AssertionError(f"only read-only csb calls: {args}")
    monkeypatch.setattr(csb, "run_csb", fake_csb)
    monkeypatch.setattr(rl, "spawn", lambda command, cwd, env: calls["spawn"].append(command) or 0)
    monkeypatch.setattr(rl, "resolve_program", lambda name: name)
    monkeypatch.setattr(rc, "default_liveness", lambda a: a.get("pid") == 4242)
    monkeypatch.setattr(rc, "default_boot", lambda: 1000.0)
    monkeypatch.setattr(rc, "current_tab", lambda pid=None: rc.Tab(4242, "cmd.exe", 1, "test"))
    monkeypatch.setattr(io, "is_console", lambda: True)
    monkeypatch.delenv("DZ_RELAUNCH_OPEN_ASKS", raising=False)
    relaunch.main(["new", "ck3"])
    return type("W", (), {"state": state, "calls": calls})


def answer(monkeypatch, text):
    monkeypatch.setattr("builtins.input", lambda prompt="": text)


def member():
    return rs.find_member(rs.load_set("ck3"), "wt")


def test_unknown_name_asks_and_yes_adds_it_by_name(world, monkeypatch, capsys):
    answer(monkeypatch, "y")
    assert relaunch.main(["ck3", "add", "--claude", NAME, "--label", "wt"]) == 0
    m = member()
    assert m["name_at_add"] == NAME and not m.get("session_id")
    assert "not found yet" in capsys.readouterr().out
    relaunch.main(["ck3"])
    assert "(not found yet)" in capsys.readouterr().out


def test_no_adds_nothing(world, monkeypatch):
    answer(monkeypatch, "n")
    assert relaunch.main(["ck3", "add", "--claude", NAME, "--label", "wt"]) == 3
    assert rs.load_set("ck3")["members"] == []


def test_yes_flag_skips_the_question(world, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(AssertionError("asked")))
    assert relaunch.main(["ck3", "add", "--claude", NAME, "--label", "wt", "-y"]) == 0
    assert member()["name_at_add"] == NAME


def test_no_console_refuses_and_names_yes(world, monkeypatch, capsys):
    monkeypatch.setattr(io, "is_console", lambda: False)
    assert relaunch.main(["ck3", "add", "--claude", NAME, "--label", "wt"]) == 3
    assert "--yes" in capsys.readouterr().out
    assert rs.load_set("ck3")["members"] == []


def test_several_sessions_with_the_name_are_refused_without_a_question(world, monkeypatch):
    world.state["dupes"] = True
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(AssertionError("asked")))
    assert relaunch.main(["ck3", "add", "--claude", NAME, "--label", "wt"]) == 3
    assert rs.load_set("ck3")["members"] == []


def test_once_csb_sees_it_the_id_is_recorded_and_resume_is_by_id(world, monkeypatch, capsys):
    relaunch.main(["ck3", "add", "--claude", NAME, "--label", "wt", "-y"])
    world.state["known"][NAME] = SID                       # csb has caught up
    answer(monkeypatch, "y")
    relaunch.main(["ck3", "claim", "-o"])
    assert member()["session_id"] == SID
    assert world.calls["spawn"] == [["csb", "resume", SID]]


def test_still_unknown_at_claim_resumes_by_name(world, monkeypatch, capsys):
    relaunch.main(["ck3", "add", "--claude", NAME, "--label", "wt", "-y"])
    answer(monkeypatch, "y")
    relaunch.main(["ck3", "claim", "-o"])
    assert world.calls["spawn"] == [["csb", "resume", NAME]]
    assert not member().get("session_id")


def test_a_known_name_adds_exactly_as_before(world, monkeypatch):
    world.state["known"][NAME] = SID
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(AssertionError("asked")))
    assert relaunch.main(["ck3", "add", "--claude", NAME, "--label", "wt"]) == 0
    assert member()["session_id"] == SID
