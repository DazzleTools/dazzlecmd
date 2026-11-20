"""S6: read actions -- dashboard, roster, member card, last view -- never write."""

import json
import os

import pytest

import relaunch
import relaunch_claims as rc
import relaunch_store as rs


@pytest.fixture
def world(monkeypatch):
    alive = {}

    def liveness(anchor):
        return alive.get(anchor.get("pid"), False)

    monkeypatch.setattr(rc, "default_liveness", liveness)
    monkeypatch.setattr(rc, "default_boot", lambda: 1000.0)
    me = rc.Tab(4242, "cmd.exe", 1, "test")
    alive[4242] = True
    monkeypatch.setattr(rc, "current_tab", lambda pid=None: me)

    def tab(pid):
        alive[pid] = True
        return rc.Tab(pid, "cmd.exe", 1, "test")
    return {"alive": alive, "me": me, "tab": tab}


def make_set():
    doc = rs.new_set("CK3", notes="the mod")
    rs.add_member(doc, {"kind": "folder", "label": "mod", "cwd": os.getcwd()})
    rs.add_member(doc, {"kind": "command", "label": "codex", "argv": ["codex", "resume"]})
    rs.add_member(doc, {"kind": "folder", "label": "docs", "cwd": os.getcwd(), "notes": "writing"})
    rs.save_set(doc)


def _files(root):
    out = {}
    for dp, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(dp, f)
            out[p] = os.path.getmtime(p)
    return out


def test_empty_dashboard_says_how_to_start(world, capsys):
    assert relaunch.main([]) == 0
    out = capsys.readouterr().out
    assert "dz relaunch new" in out and out.strip().splitlines()[-1] == "relaunch: LISTED 0 sets"


def test_read_actions_write_nothing(world, relaunch_home, capsys):
    make_set()
    rc.claim("ck3", world["me"])
    before = _files(relaunch_home)
    for argv in ([], ["ck3"], ["show", "ck3"], ["ck3:2"], ["last"], ["list", "--json"]):
        relaunch.main(argv)
    assert _files(relaunch_home) == before
    assert not os.path.exists(rc.lock_path()) or rc.lock_path() in before


def test_roster_marks_this_tab_and_the_next_member(world, capsys):
    make_set()
    rc.claim("ck3", world["me"])                  # me holds 1
    rc.claim("ck3", world["tab"](7))              # another tab holds 2
    capsys.readouterr()
    assert relaunch.main(["ck3"]) == 0
    out = capsys.readouterr().out
    assert "this tab" in out and "claimed (pid 7)" in out
    assert "next: dz relaunch ck3 claim   (takes 3 docs [never opened])" in out
    assert "note: writing" in out


def test_member_card(world, capsys):
    make_set()
    assert relaunch.main(["ck3:2"]) == 0
    out = capsys.readouterr().out
    assert "ck3:2  codex" in out and "codex resume" in out and "free" in out


def test_last_view_and_token(world, capsys):
    make_set()
    rc.claim("ck3", world["me"], "docs")
    world["alive"][4242] = False                  # every tab closed
    capsys.readouterr()
    assert relaunch.main(["last"]) == 0
    out = capsys.readouterr().out
    assert "session 1 (last): 1 members" in out and "ck3:3" in out
    assert relaunch.main(["last:1"]) == 0
    assert "ck3:3  docs" in capsys.readouterr().out
    assert relaunch.main(["last:5"]) == 1
    assert "valid indices are 1-1" in capsys.readouterr().err


def test_dashboard_json(world, capsys):
    make_set()
    rc.claim("ck3", world["me"])
    capsys.readouterr()
    assert relaunch.main(["--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["sets"][0] == {"set": "ck3", "members": 3, "claimed": 1, "open_last_session": 0,
                              "disabled": False, "this_tab": 1}
    assert doc["verdict"] == "LISTED"
