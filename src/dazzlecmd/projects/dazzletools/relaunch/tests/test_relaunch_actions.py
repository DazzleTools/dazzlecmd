"""S7: write actions and claim at the print level (safedel and the editor stubbed -- rule 1b)."""

import json
import os
import types

import pytest

import relaunch
import relaunch_actions as act
import relaunch_claims as rc
import relaunch_cli_io as io
import relaunch_store as rs


@pytest.fixture
def w(monkeypatch, tmp_path):
    alive = {4242: True}
    me = rc.Tab(4242, "cmd.exe", 1, "test")
    monkeypatch.setattr(rc, "default_liveness", lambda a: alive.get(a.get("pid"), False))
    monkeypatch.setattr(rc, "default_boot", lambda: 1000.0)
    monkeypatch.setattr(rc, "current_tab", lambda pid=None: me)
    monkeypatch.setattr(io, "is_console", lambda: False)
    trashed = []

    class FakeStore:
        def trash(self, paths):
            trashed.extend(paths)
            for p in paths:
                os.remove(p)
            return types.SimpleNamespace(success=True, folder_path=str(tmp_path / "2026-11-19__10-00-00"),
                                         errors=[])

        def list_entries(self):
            return [types.SimpleNamespace(folder_name="2026-11-19__10-00-00", deleted_at="2026-11-19 10:00",
                                          entries=[types.SimpleNamespace(original_path=p) for p in trashed])]
    monkeypatch.setattr(act, "trash_store", lambda: FakeStore())

    def no_editor(path):
        raise AssertionError("the real editor must not be started in tests")
    monkeypatch.setattr(act, "run_editor", no_editor)
    monkeypatch.setattr(act, "wait_for_enter", lambda prompt: None)
    monkeypatch.delenv("DZ_RELAUNCH_CD_FILE", raising=False)

    def other(pid):
        alive[pid] = True
        return rc.Tab(pid, "cmd.exe", 1, "test")
    return types.SimpleNamespace(me=me, alive=alive, other=other, trashed=trashed, tmp=tmp_path)


def run(argv, capsys):
    code = relaunch.main(argv)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def setup_set(capsys, tmp_path):
    a = tmp_path / "proj a"
    a.mkdir()
    assert run(["new", "CK3", "--notes", "mod"], capsys)[0] == 0
    assert run(["ck3", "add", str(a), "--label", "mod"], capsys)[0] == 0
    assert run(["ck3", "add", "--label", "codex", "--", "codex", "resume", "--last"], capsys)[0] == 0
    assert run(["ck3", "add", "--label", "build", "--shell", "cmd", "make && test"], capsys)[0] == 0
    return a


def test_new_and_add_members(w, capsys):
    setup_set(capsys, w.tmp)
    doc = rs.load_set("ck3")
    assert [m["kind"] for m in doc["members"]] == ["folder", "command", "shell"]
    assert doc["members"][1]["argv"] == ["codex", "resume", "--last"]
    assert doc["notes"] == "mod"


def test_add_here_claims_for_this_tab(w, capsys, monkeypatch):
    run(["new", "dz"], capsys)
    monkeypatch.chdir(w.tmp)
    code, out, _ = run(["dz", "add", "--here"], capsys)
    assert code == 0 and "claimed dz:1 for this tab" in out


def test_claim_prints_the_cd_line_and_next(w, capsys):
    a = setup_set(capsys, w.tmp)
    code, out, _ = run(["ck3", "claim"], capsys)
    assert code == 0
    assert f'cd /d "{a}"' in out or f"cd -- '{a}'" in out
    assert "next: ck3:2 codex  [never opened]" in out
    assert out.strip().splitlines()[-1] == "relaunch: CLAIMED ck3 1 mod"


def test_claim_writes_the_cd_file_for_the_wrapper(w, capsys, monkeypatch):
    a = setup_set(capsys, w.tmp)
    cd = w.tmp / "cd.txt"
    monkeypatch.setenv("DZ_RELAUNCH_CD_FILE", str(cd))
    monkeypatch.setenv("DZ_RELAUNCH_CD_FORMAT", "posix")
    code, out, _ = run(["ck3", "claim"], capsys)
    assert code == 0 and "this tab moves to" in out
    assert cd.read_text(encoding="utf-8").strip() == str(a)


def test_claim_command_member_shows_the_command(w, capsys):
    setup_set(capsys, w.tmp)
    code, out, _ = run(["ck3", "claim", "codex"], capsys)
    assert code == 0 and "codex resume --last" in out


def test_claim_again_in_the_same_tab(w, capsys):
    setup_set(capsys, w.tmp)
    run(["ck3", "claim"], capsys)
    code, out, _ = run(["ck3", "claim"], capsys)
    assert code == 0 and "this tab already had it" in out


def test_duplicate_without_console_is_refused_then_yes_allows(w, capsys):
    setup_set(capsys, w.tmp)
    rc.claim("ck3", w.other(7), "mod")
    code, out, err = run(["ck3", "claim", "mod"], capsys)
    assert code == 3 and "REFUSED" in out
    code, out, _ = run(["ck3", "claim", "mod", "--yes"], capsys)
    assert code == 0 and "(copy 2)" in out


def test_none_free_and_multi_set_claim(w, capsys):
    setup_set(capsys, w.tmp)
    for pid in (7, 8, 9):
        rc.claim("ck3", w.other(pid))
    code, out, _ = run(["ck3", "claim"], capsys)
    assert code == 3 and "nothing left to claim" in out
    run(["new", "dz"], capsys)
    run(["dz", "add", str(w.tmp)], capsys)
    code, out, _ = run(["ck3", "dz", "claim"], capsys)
    assert code == 0 and "claimed dz:1" in out


def test_release(w, capsys):
    setup_set(capsys, w.tmp)
    run(["ck3", "claim"], capsys)
    code, out, _ = run(["release"], capsys)
    assert code == 0 and "released ck3:1" in out
    assert rc.load_claims() == []


def test_note_and_field_edit(w, capsys):
    setup_set(capsys, w.tmp)
    assert run(["ck3", "note", "2", "agent tab"], capsys)[0] == 0
    assert run(["ck3", "edit", "2", "--label", "cx", "--", "codex", "--fresh"], capsys)[0] == 0
    m = rs.find_member(rs.load_set("ck3"), "2")
    assert (m["notes"], m["label"], m["argv"]) == ("agent tab", "cx", ["codex", "--fresh"])


def test_editor_mode_applies_and_detects_conflicts(w, capsys, monkeypatch):
    setup_set(capsys, w.tmp)

    def editor(path):
        doc = json.load(open(path, encoding="utf-8"))
        doc["notes"] = "edited"
        json.dump(doc, open(path, "w", encoding="utf-8"))
    monkeypatch.setattr(act, "run_editor", editor)
    assert run(["ck3", "edit"], capsys)[0] == 0
    assert rs.load_set("ck3")["notes"] == "edited"

    def racing_editor(path):
        editor(path)
        d = rs.load_set("ck3")
        d["notes"] = "someone else"
        rs.save_set(d)
    monkeypatch.setattr(act, "run_editor", racing_editor)
    code, out, _ = run(["ck3", "edit"], capsys)
    assert code == 3 and "changed while you edited" in out
    assert rs.load_set("ck3")["notes"] == "someone else"
    assert os.path.exists(os.path.join(rs.local_dir(), "ck3.edit.json"))


def test_drop_disable_enable_and_rm_member(w, capsys):
    setup_set(capsys, w.tmp)
    assert run(["ck3", "drop", "disable", "3"], capsys)[0] == 0
    assert rs.find_member(rs.load_set("ck3"), "3")["disabled"] is True
    assert run(["ck3", "enable", "3"], capsys)[0] == 0
    assert run(["ck3", "drop", "rm", "2"], capsys)[0] == 0
    doc = rs.load_set("ck3")
    assert [m["id"] for m in doc["members"]] == [1, 3] and doc["removed"][0]["member"]["id"] == 2
    assert run(["ck3", "drop", "disable"], capsys)[0] == 0
    assert rs.find_set_file("ck3").endswith(os.path.join("disabled", "ck3.json"))
    assert run(["ck3", "enable"], capsys)[0] == 0
    assert not rs.find_set_file("ck3").endswith(os.path.join("disabled", "ck3.json"))


def test_drop_rm_whole_set_needs_yes_and_goes_to_safedel(w, capsys):
    setup_set(capsys, w.tmp)
    path = rs.find_set_file("ck3")
    code, out, _ = run(["ck3", "drop", "rm"], capsys)
    assert code == 3 and os.path.exists(path) and w.trashed == []
    code, out, _ = run(["ck3", "drop", "rm", "--yes"], capsys)
    assert code == 0 and w.trashed == [path] and "dz safedel recover" in out
    code, out, _ = run(["list", "--removed"], capsys)
    assert "set" in out and "ck3" in out


def test_list_removed_shows_member_tombstones(w, capsys):
    setup_set(capsys, w.tmp)
    run(["ck3", "drop", "rm", "codex"], capsys)
    code, out, _ = run(["list", "--removed"], capsys)
    assert code == 0 and "ck3:2" in out
