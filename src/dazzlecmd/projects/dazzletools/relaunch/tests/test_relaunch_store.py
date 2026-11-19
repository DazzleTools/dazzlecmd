"""S1: the set store -- names, kinds, ids, tombstones, strict loading, portable keys."""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

import relaunch_store as rs


def _make(tmp_path, name="SafeDel"):
    doc = rs.new_set(name, notes="n")
    rs.add_member(doc, {"kind": "folder", "label": "lib", "cwd": str(tmp_path / "lib")})
    rs.add_member(doc, {"kind": "command", "label": "codex", "cwd": str(tmp_path),
                        "argv": ["codex", "resume", "--last", "a b", 'q"uote']})
    rs.add_member(doc, {"kind": "shell", "label": "build", "shell": "cmd",
                        "script": "cd docs && make.bat html"})
    rs.add_member(doc, {"kind": "claude", "label": "claude", "via": "csb",
                        "session_id": "3b7e878d-0000-0000-0000-000000000000"})
    return doc


def test_home_comes_from_env(relaunch_home):
    assert rs.relaunch_home() == os.path.abspath(str(relaunch_home))


def test_round_trip_keeps_members_and_unknown_keys(tmp_path):
    doc = _make(tmp_path)
    doc["future_field"] = {"x": 1}
    doc["members"][0]["future_member_field"] = "kept"
    path = rs.save_set(doc)
    assert path == rs.set_path("safedel")
    back = rs.load_set("SAFEDEL")
    assert back["display_name"] == "SafeDel"
    assert [m["kind"] for m in back["members"]] == ["folder", "command", "shell", "claude"]
    assert back["members"][1]["argv"] == ["codex", "resume", "--last", "a b", 'q"uote']
    assert back["future_field"] == {"x": 1}
    assert back["members"][0]["future_member_field"] == "kept"
    on_disk = json.load(open(path, encoding="utf-8"))
    assert not any(k.startswith("_") for k in on_disk)


def test_corrupt_file_is_refused_and_left_unchanged():
    os.makedirs(rs.sets_dir())
    p = rs.set_path("broken")
    with open(p, "w", encoding="utf-8") as f:
        f.write("{not json")
    before = open(p, "rb").read()
    with pytest.raises(rs.StoreError) as e:
        rs.load_set("broken")
    assert "not valid JSON" in str(e.value) and p in str(e.value)
    assert open(p, "rb").read() == before


def test_invalid_member_is_named():
    os.makedirs(rs.sets_dir())
    doc = rs.new_set("x")
    doc["members"] = [{"id": 1, "kind": "command", "argv": []}]
    doc["next_member_id"] = 2
    with open(rs.set_path("x"), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    with pytest.raises(rs.StoreError, match="member 1"):
        rs.load_set("x")


@pytest.mark.parametrize("bad", ["new", "claim", "3", "LAST", "last~2", "tabs", "open", "a b", "", "-x"])
def test_reserved_and_invalid_names_refused(bad):
    with pytest.raises(rs.StoreError):
        rs.canonical_name(bad)


def test_valid_name_is_lowercased():
    assert rs.canonical_name("CK3-save_updater") == "ck3-save_updater"


def test_ids_are_never_reused_and_removed_go_to_tombstones(tmp_path):
    doc = _make(tmp_path)
    removed = rs.remove_member(doc, "codex")
    assert removed["id"] == 2
    new = rs.add_member(doc, {"kind": "folder", "label": "docs", "cwd": str(tmp_path)})
    assert new["id"] == 5
    assert doc["removed"][0]["member"]["label"] == "codex"
    rs.save_set(doc)
    assert rs.load_set("safedel")["removed"][0]["member"]["id"] == 2


def test_old_tombstones_are_pruned_on_write(tmp_path):
    doc = _make(tmp_path)
    rs.remove_member(doc, "lib")
    old = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["removed"][0]["removed_at"] = old
    rs.save_set(doc)
    assert rs.load_set("safedel")["removed"] == []


def test_duplicate_label_refused(tmp_path):
    doc = _make(tmp_path)
    with pytest.raises(rs.StoreError, match="already has"):
        rs.add_member(doc, {"kind": "folder", "label": "LIB", "cwd": str(tmp_path)})


@pytest.mark.parametrize("member,msg", [
    ({"kind": "folder"}, "needs 'cwd'"),
    ({"kind": "shell", "shell": "fish", "script": "x"}, "shell"),
    ({"kind": "claude", "session_id": "u"}, "via='csb'"),
    ({"kind": "nope", "cwd": "x"}, "unknown kind"),
])
def test_kind_validation(member, msg):
    doc = rs.new_set("k")
    with pytest.raises(rs.StoreError, match=msg):
        rs.add_member(doc, member)


def test_find_member_by_id_or_label(tmp_path):
    doc = _make(tmp_path)
    assert rs.find_member(doc, "2")["label"] == "codex"
    assert rs.find_member(doc, "CLAUDE")["id"] == 4
    with pytest.raises(rs.StoreError):
        rs.find_member(doc, "99")


def test_disabled_set_found_and_listed(tmp_path):
    doc = _make(tmp_path, "hidden")
    doc["_disabled"] = True
    rs.save_set(doc)
    assert rs.find_set_file("hidden").endswith(os.path.join("disabled", "hidden.json"))
    assert [d["name"] for d in rs.list_sets()] == []
    assert [d["name"] for d in rs.list_sets(include_disabled=True)] == ["hidden"]


def test_list_reports_unreadable_files_instead_of_hiding_them():
    os.makedirs(rs.sets_dir())
    with open(rs.set_path("bad"), "w", encoding="utf-8") as f:
        f.write("[]")
    rows = rs.list_sets()
    assert rows[0]["name"] == "bad" and "_error" in rows[0]


def test_paths_are_stored_literally_with_a_portable_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SOME_VAR", "expanded")
    doc = rs.new_set("p")
    raw = str(tmp_path / "%SOME_VAR%" / "x")
    m = rs.add_member(doc, {"kind": "folder", "cwd": raw})
    assert "%SOME_VAR%" in m["cwd"]          # not expanded
    assert m["cwd_key"]                       # a key was recorded


def test_portable_key_resolves_through_a_path_map():
    member = {"cwd": "C:\\code\\x", "cwd_key": "C/code/x"}
    origin = {"flavor": "windows"}
    assert rs.resolve_cwd(member, origin, flavor="windows") == "C:\\code\\x"
    mapped = rs.resolve_cwd(member, origin, flavor="posix",
                            path_map={"C/code": "ROOT/home/u/code"})
    assert mapped == "/home/u/code/x"
    assert rs.resolve_cwd(member, origin, flavor="posix", path_map={}) is None


def test_path_map_file_is_read(relaunch_home):
    os.makedirs(rs.local_dir())
    with open(os.path.join(rs.local_dir(), "path-map.json"), "w", encoding="utf-8") as f:
        json.dump({"map": {"C/code": "ROOT/home/u/code"}}, f)
    assert rs.load_path_map() == {"C/code": "ROOT/home/u/code"}
