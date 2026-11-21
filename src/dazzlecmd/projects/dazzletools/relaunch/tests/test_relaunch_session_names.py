"""Claude members show their csb session name (0.13.15). csb and the spawner are stubbed -- rule 1b."""

import json
import sys

import pytest

import relaunch
import relaunch_claims as rc
import relaunch_cli_io as io
import relaunch_csb as csb
import relaunch_launch as rl
import relaunch_store as rs

SID = "265b0cca-33f7-4672-b007-bf49339d5b4c"
NAME = "CLAUDE__2026.10.3__creating-bookmark-plugin"


@pytest.fixture(autouse=True)
def world(monkeypatch):
    seen = {"csb": []}
    state = {"available": True}

    def fake_csb(args, timeout=5.0):
        seen["csb"].append(args)
        if args[:1] != ["scan"] and args[:2] != ["set", "show"]:
            raise AssertionError(f"only read-only csb calls: {args}")
        if not state["available"]:
            raise csb.CsbUnavailable("csb not found")
        if args[:1] == ["scan"]:
            return json.dumps([{"session_id": SID, "session_name": NAME}] if args[1] == SID else [])
        return json.dumps({"members": []})
    monkeypatch.setattr(csb, "run_csb", fake_csb)
    monkeypatch.setattr(rl, "spawn", lambda command, cwd, env: 0)
    monkeypatch.setattr(rl, "resolve_program", lambda name: name)
    monkeypatch.setattr(rc, "default_liveness", lambda a: a.get("pid") == 4242)
    monkeypatch.setattr(rc, "default_boot", lambda: 1000.0)
    monkeypatch.setattr(rc, "current_tab", lambda pid=None: rc.Tab(4242, "cmd.exe", 1, "test"))
    monkeypatch.setattr(io, "is_console", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    monkeypatch.delenv("DZ_RELAUNCH_OPEN_ASKS", raising=False)
    relaunch.main(["new", "cb"])
    return type("W", (), {"seen": seen, "state": state})


def test_adding_by_uuid_records_the_session_name(world):
    assert relaunch.main(["cb", "add", "--claude", SID, "--label", "session1"]) == 0
    assert rs.find_member(rs.load_set("cb"), "session1")["name_at_add"] == NAME


def test_will_run_shows_the_name_after_the_uuid(world, capsys):
    relaunch.main(["cb", "add", "--claude", SID, "--label", "session1"])
    capsys.readouterr()
    relaunch.main(["cb", "claim", "-o"])
    out = capsys.readouterr().out
    assert f"will run: csb resume {SID}  ({NAME})" in out


def test_print_level_shows_the_name_too(world, capsys, monkeypatch):
    relaunch.main(["cb", "add", "--claude", SID, "--label", "session1"])
    capsys.readouterr()
    monkeypatch.setattr(io, "is_console", lambda: False)        # no console -> print level
    relaunch.main(["cb", "claim"])
    assert f"csb resume {SID}  ({NAME})" in capsys.readouterr().out


def test_an_older_member_without_a_name_is_filled_in_once(world, capsys):
    doc = rs.load_set("cb")
    rs.add_member(doc, {"kind": "claude", "via": "csb", "session_id": SID, "name_at_add": None,
                        "label": "old"})
    rs.save_set(doc)
    relaunch.main(["cb", "claim", "-o"])
    assert rs.find_member(rs.load_set("cb"), "old")["name_at_add"] == NAME
    scans = [a for a in world.seen["csb"] if a[:1] == ["scan"]]
    relaunch.main(["cb", "claim", "-o"])
    assert [a for a in world.seen["csb"] if a[:1] == ["scan"]] == scans   # no second lookup


def test_csb_unavailable_shows_the_uuid_alone(world, capsys):
    world.state["available"] = False
    assert relaunch.main(["cb", "add", "--claude", SID, "--label", "session1"]) == 0
    capsys.readouterr()
    relaunch.main(["cb", "claim", "-o"])
    out = capsys.readouterr().out
    assert f"will run: csb resume {SID}\n" in out
