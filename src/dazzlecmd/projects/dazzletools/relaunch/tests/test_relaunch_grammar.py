"""S4: grammar, verb table, continuum, verdict and log output."""

import os

import pytest

import relaunch
import relaunch_cli_io as io
import relaunch_continuum as cont
import relaunch_grammar as g
import relaunch_store as rs
import relaunch_verbs as rv

KNOWN = ["safedel", "ck3", "dz"]


def p(s):
    return g.split_targets(s.split(), KNOWN)


@pytest.mark.parametrize("line,verb,targets,rest", [
    ("", "list", [], []),
    ("ck3", "show", [("ck3", None)], []),
    ("ck3 dz", "show", [("ck3", None), ("dz", None)], []),
    ("ck3:2", "show", [("ck3", "2")], []),
    ("last", "show", [("last", None)], []),
    ("last~1:3", "show", [("last~1", "3")], []),
    ("ck3 claim", "claim", [("ck3", None)], []),
    ("ck3 claim -o", "claim", [("ck3", None)], ["-o"]),
    ("-v ck3 claim 2 --yes", "claim", [("ck3", None)], ["2", "--yes"]),
    ("ck3 dz claim", "claim", [("ck3", None), ("dz", None)], []),
    ("ck3 drop rm 3", "drop", [("ck3", None)], ["rm", "3"]),
    ("ck3 add --here", "add", [("ck3", None)], ["--here"]),
    ("claim ck3 2", "claim", [("ck3", None)], ["2"]),            # verb-first, one set
    ("drop rm 3", "drop", [], ["rm", "3"]),
    ("drop rm ck3", "drop", [("ck3", None)], ["rm"]),
    ("drop rm ck3 3", "drop", [("ck3", None)], ["rm", "3"]),
    ("drop disable dz", "drop", [("dz", None)], ["disable"]),
    ("new work2", "new", [], ["work2"]),
    ("shell-init cmd", "shell-init", [], ["cmd"]),
    ("ls", "list", [], []),
    ("release", "release", [], []),
    ("last claim", "claim", [("last", None)], []),
    ("ck3 claim ck3", "claim", [("ck3", None)], ["ck3"]),        # a label that is also a set name
])
def test_grammar_table(line, verb, targets, rest):
    r = p(line)
    assert r.verb == verb
    assert [(t.name, t.entry) for t in r.targets] == targets
    assert r.rest == rest


@pytest.mark.parametrize("line,msg", [
    ("safedl claim", "did you mean 'safedel'"),       # typo in the set
    ("ck3 clam", "did you mean the action 'claim'"),
    ("clam", "did you mean the action 'claim'"),
    ("claim new", "'new' is an action, not a set"),
    ("ck3 --label x add", "after the action"),
    ("ck3 dz add --here", "exactly one set"),
    ("ck3 shell-init cmd", "does not take a set"),
])
def test_grammar_errors(line, msg):
    with pytest.raises(g.GrammarError, match=msg):
        p(line)


def test_every_verb_and_view_is_reserved():
    for name in list(rv.BY_NAME) + list(rv.VIEWS):
        assert rs.is_reserved(name), name


def test_action_continuum():
    assert cont.ACTION.levels() == ("print", "open", "tabs")
    assert cont.resolve_action() == "print"
    assert cont.resolve_action(open_flag=True) == "open"
    assert cont.resolve_action(open_flag=True, console=False) == "print"
    with pytest.raises(cont.LevelNotBuilt):
        cont.resolve_action(tabs_flag=True)
    assert cont.TRUST.levels() == ("none", "hashed", "signed")


def test_verdict_is_the_last_line(capsys):
    code = io.finish("CLAIMED", "ck3 2 lib", io.EXIT_OK)
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0 and out[-1] == "relaunch: CLAIMED ck3 2 lib"


def test_verdict_inside_json(capsys):
    import json
    io.finish("REFUSED", "x", io.EXIT_REFUSED, json_mode=True, payload={"a": 1})
    doc = json.loads(capsys.readouterr().out)
    assert doc == {"a": 1, "verdict": "REFUSED", "detail": "x", "exit_code": 3}


def test_main_reports_usage_errors_with_exit_2(capsys):
    assert relaunch.main(["nosuchset"]) == io.EXIT_USAGE
    assert "relaunch: USAGE" in capsys.readouterr().out


def test_help_lists_every_verb(capsys):
    assert relaunch.main(["--help"]) == 0
    out = capsys.readouterr().out
    for v in rv.VERBS:
        assert v.name in out


@pytest.mark.parametrize("verb", [v.name for v in rv.VERBS])
def test_every_action_has_help_with_options_and_examples(verb, capsys):
    assert relaunch.main([verb, "-h"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: dz relaunch")
    assert "examples:" in out and "options:" in out


def test_help_after_a_set_runs_nothing(capsys, monkeypatch):
    import relaunch_claims as rc
    doc = rs.new_set("ck3")
    rs.add_member(doc, {"kind": "folder", "cwd": os.getcwd()})
    rs.save_set(doc)
    monkeypatch.setattr(rc, "claim", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claimed!")))
    assert relaunch.main(["ck3", "claim", "-h"]) == 0
    out = capsys.readouterr().out
    assert "usage: dz relaunch <set>... claim" in out and "-o, --open" in out
    assert not os.path.exists(rs.local_dir()) or not os.listdir(rs.local_dir())


def test_log_file_receives_diagnostics(tmp_path):
    log = tmp_path / "relaunch.log"
    io.setup_output(verbose=3, log_file=str(log))
    io.diag("anchor", "anchor=35792 rule=below-host:windowsterminal.exe")
    io.close_output()
    assert "anchor=35792" in log.read_text(encoding="utf-8")
