"""claim -o: a "no" gives the member back (0.13.15). Spawner and csb stubbed -- rule 1b."""

import sys

import pytest

import relaunch
import relaunch_claims as rc
import relaunch_cli_io as io
import relaunch_csb as csb
import relaunch_launch as rl
import relaunch_store as rs


@pytest.fixture(autouse=True)
def world(monkeypatch):
    calls = {"spawn": []}
    monkeypatch.setattr(rl, "spawn", lambda command, cwd, env: calls["spawn"].append(command) or 0)
    monkeypatch.setattr(csb, "run_csb", lambda args, timeout=5.0: (_ for _ in ()).throw(
        AssertionError(f"real csb must not run: {args}")))
    alive = {4242: True, 5151: True}
    tabs = {"now": rc.Tab(4242, "cmd.exe", 1, "test")}
    monkeypatch.setattr(rc, "default_liveness", lambda a: alive.get(a.get("pid"), False))
    monkeypatch.setattr(rc, "default_boot", lambda: 1000.0)
    monkeypatch.setattr(rc, "current_tab", lambda pid=None: tabs["now"])
    monkeypatch.setattr(io, "is_console", lambda: True)
    monkeypatch.setattr(rl, "resolve_program", lambda name: sys.executable if name == "python" else name)
    monkeypatch.delenv("DZ_RELAUNCH_OPEN_ASKS", raising=False)
    relaunch.main(["new", "w"])
    relaunch.main(["w", "add", "--label", "a", "--", "python", "-c", "print(1)"])
    relaunch.main(["w", "add", "--label", "b", "--", "python", "-c", "print(2)"])
    return type("W", (), {"calls": calls, "tabs": tabs})


def answer(monkeypatch, text=None, raise_=None):
    def ask(prompt=""):
        if raise_:
            raise raise_
        return text
    monkeypatch.setattr("builtins.input", ask)


def held():
    claims = rc.live_claims(rc.load_claims(), rc.default_liveness)
    return sorted((c["member_id"], c["anchor"]["pid"]) for c in claims)


def sessions():
    h = rc.load_history()
    return [s["n"] for s in h.get("sessions", [])], h.get("next_session")


@pytest.mark.parametrize("how", [dict(text="n"), dict(text=""), dict(raise_=KeyboardInterrupt()),
                                 dict(raise_=EOFError())], ids=["n", "enter", "ctrl-c", "eof"])
def test_a_no_releases_the_member_and_runs_nothing(world, monkeypatch, capsys, how):
    answer(monkeypatch, **how)
    before = sessions()
    assert relaunch.main(["w", "claim", "-o"]) == 3
    out = capsys.readouterr()
    assert "released w:1 a" in out.out and "Traceback" not in out.err
    assert held() == [] and world.calls["spawn"] == []
    assert sessions() == before                                   # no phantom session
    doc = rs.load_set("w")
    assert "never opened" in rc.tag(rc.load_history(), "w", 1, session_live=True)


def test_yes_keeps_the_claim_and_runs(world, monkeypatch, capsys):
    answer(monkeypatch, "y")
    relaunch.main(["w", "claim", "-o"])
    assert held() == [(1, 4242)] and len(world.calls["spawn"]) == 1


def test_already_held_is_kept_on_no(world, monkeypatch, capsys):
    answer(monkeypatch, "y")
    relaunch.main(["w", "claim", "-o"])                           # tab holds a, ran it
    answer(monkeypatch, "n")
    assert relaunch.main(["w", "claim", "-o"]) == 3               # same tab, same member, says no
    assert "still holds w:1 a" in capsys.readouterr().out
    assert held() == [(1, 4242)]


def test_the_next_claim_after_a_decline_uses_the_same_session(world, monkeypatch, capsys):
    before = sessions()                                           # before any claim
    answer(monkeypatch, "n")
    relaunch.main(["w", "claim", "-o"])
    answer(monkeypatch, "y")
    relaunch.main(["w", "claim", "-o"])
    assert sessions()[1] == before[1] + 1                         # one session for the whole run, not two


def test_another_tabs_claim_survives_a_decline(world, monkeypatch, capsys):
    answer(monkeypatch, "y")
    world.tabs["now"] = rc.Tab(5151, "cmd.exe", 2, "other")
    relaunch.main(["w", "claim", "-o"])                           # the other tab takes a and runs it
    world.tabs["now"] = rc.Tab(4242, "cmd.exe", 1, "test")
    answer(monkeypatch, "n")
    relaunch.main(["w", "claim", "-o"])                           # this tab is offered b, says no
    assert held() == [(1, 5151)]
    h = rc.load_history()
    assert h["opened"]["w"]["1"]                                   # a's opened mark is untouched


def test_ctrl_c_at_the_question_is_a_no():
    assert io.confirm("q?", ask=lambda p: (_ for _ in ()).throw(KeyboardInterrupt())) is False
