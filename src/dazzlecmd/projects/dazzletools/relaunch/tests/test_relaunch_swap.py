"""swap: two members trade places and numbers; everything keyed by number follows (0.13.16)."""

import json

import pytest

import relaunch
import relaunch_claims as rc
import relaunch_cli_io as io
import relaunch_grammar as g
import relaunch_launch as rl
import relaunch_store as rs
import relaunch_trust as trust


@pytest.fixture(autouse=True)
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(rc, "default_liveness", lambda a: a.get("pid") in (4242, 5151))
    monkeypatch.setattr(rc, "default_boot", lambda: 1000.0)
    tabs = {"now": rc.Tab(4242, "cmd.exe", 1, "test")}
    monkeypatch.setattr(rc, "current_tab", lambda pid=None: tabs["now"])
    monkeypatch.setattr(io, "is_console", lambda: False)        # print level: nothing runs
    relaunch.main(["new", "ck3"])
    for label in ("a", "b", "c", "d"):
        (tmp_path / label).mkdir()
        relaunch.main(["ck3", "add", str(tmp_path / label), "--label", label])
    return type("W", (), {"tabs": tabs})


def roster():
    return [(m["id"], m["label"]) for m in rs.load_set("ck3")["members"]]


@pytest.mark.parametrize("line", ["ck3 swap 2 4", "swap 2 4 ck3", "swap ck3 2 4", "swap b d ck3"])
def test_every_word_order_swaps(line):
    assert relaunch.main(line.split()) == 0
    assert roster() == [(1, "a"), (2, "d"), (3, "c"), (4, "b")]     # numbers stay in order, labels moved


def test_grammar_takes_the_set_from_the_end():
    p = g.split_targets(["swap", "2", "4", "ck3"], ["ck3", "dz"])
    assert p.verb == "swap" and [t.name for t in p.targets] == ["ck3"] and p.rest == ["2", "4"]


def test_a_tabs_claim_follows_its_member(world):
    relaunch.main(["ck3", "claim", "b"])                           # this tab holds b (number 2)
    relaunch.main(["ck3", "swap", "2", "4"])
    held = [c for c in rc.load_claims() if c["set"] == "ck3"]
    assert [c["member_id"] for c in held] == [4]                    # b is number 4 now
    assert rs.find_member(rs.load_set("ck3"), "4")["label"] == "b"


def test_history_follows_its_member(world):
    relaunch.main(["ck3", "claim", "b"])
    relaunch.main(["ck3", "release"])
    relaunch.main(["ck3", "swap", "2", "4"])
    opened = rc.load_history()["opened"]["ck3"]
    assert "4" in opened and "2" not in opened


def test_an_approved_command_is_not_re_asked_after_a_swap(world):
    relaunch.main(["ck3", "add", "--label", "cmd", "--", "python", "-c", "pass"])   # number 5, approved at add
    doc = rs.load_set("ck3")
    assert trust.is_trusted(doc, rs.find_member(doc, "cmd"))
    relaunch.main(["ck3", "swap", "5", "1"])
    doc = rs.load_set("ck3")
    assert rs.find_member(doc, "1")["label"] == "cmd"
    assert trust.is_trusted(doc, rs.find_member(doc, "cmd"))


def test_the_launch_record_follows(world):
    relaunch.main(["ck3", "add", "--detach", "--label", "ed", "--", "python", "-c", "pass"])   # number 5
    rl.record_launched("ck3", 5, 1000.0)
    relaunch.main(["ck3", "swap", "5", "2"])
    assert rl.launched_this_boot("ck3", 2, 1000.0) and not rl.launched_this_boot("ck3", 5, 1000.0)


def test_the_same_member_twice_is_refused():
    assert relaunch.main(["ck3", "swap", "2", "b"]) != 0
    assert roster() == [(1, "a"), (2, "b"), (3, "c"), (4, "d")]


def test_one_member_is_a_usage_error():
    assert relaunch.main(["ck3", "swap", "2"]) != 0
    assert roster() == [(1, "a"), (2, "b"), (3, "c"), (4, "d")]
