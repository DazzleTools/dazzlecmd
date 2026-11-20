"""S8: claim -o (prompt, overrides, trust, refusal rules, env scrub) and csb read-only."""

import json
import os
import sys
import types

import pytest

import relaunch
import relaunch_claims as rc
import relaunch_cli_io as io
import relaunch_csb as csb
import relaunch_launch as rl
import relaunch_store as rs
import relaunch_trust as trust


@pytest.fixture(autouse=True)
def guard(monkeypatch):
    """No test reaches a real program or csb unless it opts in (rule 1b)."""
    calls = {"spawn": [], "csb": []}

    def no_spawn(command, cwd, env):
        calls["spawn"].append((command, cwd))
        return 0

    def no_csb(args, timeout=5.0):
        raise AssertionError(f"real csb must not run in tests: {args}")
    monkeypatch.setattr(rl, "spawn", no_spawn)
    monkeypatch.setattr(csb, "run_csb", no_csb)
    alive = {4242: True}
    me = rc.Tab(4242, "cmd.exe", 1, "test")
    monkeypatch.setattr(rc, "default_liveness", lambda a: alive.get(a.get("pid"), False))
    monkeypatch.setattr(rc, "default_boot", lambda: 1000.0)
    monkeypatch.setattr(rc, "current_tab", lambda pid=None: me)
    monkeypatch.setattr(io, "is_console", lambda: True)
    monkeypatch.setattr(rl, "resolve_program", lambda name: sys.executable if name in ("python", "csb") else name)
    monkeypatch.delenv("DZ_RELAUNCH_OPEN_ASKS", raising=False)
    return calls


def answer(monkeypatch, text):
    monkeypatch.setattr("builtins.input", lambda prompt="": text)


def make(capsys):
    relaunch.main(["new", "w"])
    relaunch.main(["w", "add", "--label", "py", "--", "python", "-c", "print(1)"])
    capsys.readouterr()


def test_open_asks_and_no_means_nothing_runs(guard, monkeypatch, capsys):
    make(capsys)
    answer(monkeypatch, "n")
    assert relaunch.main(["w", "claim", "-o"]) == 3
    assert guard["spawn"] == []


def test_open_yes_runs_the_member(guard, monkeypatch, capsys):
    make(capsys)
    answer(monkeypatch, "y")
    assert relaunch.main(["w", "claim", "-o"]) == 0
    assert guard["spawn"][0][0] == [sys.executable, "-c", "print(1)"]
    assert "relaunch: STARTING w 1 py" in capsys.readouterr().out


def test_dash_y_skips_the_prompt(guard, monkeypatch, capsys):
    make(capsys)
    answer(monkeypatch, "n")                         # would refuse if asked
    assert relaunch.main(["w", "claim", "-o", "-y"]) == 0
    assert len(guard["spawn"]) == 1


@pytest.mark.parametrize("how", ["env", "dotenv", "config"])
def test_prompt_overrides(guard, monkeypatch, capsys, how):
    make(capsys)
    if how == "env":
        monkeypatch.setenv("DZ_RELAUNCH_OPEN_ASKS", "0")
    elif how == "dotenv":
        with open(os.path.join(rs.relaunch_home(), ".env"), "w") as f:
            f.write("DZ_RELAUNCH_OPEN_ASKS=0\n")
    else:
        with open(os.path.join(rs.local_dir(), "config.json"), "w") as f:
            json.dump({"open_asks": False}, f)
    answer(monkeypatch, "n")
    assert relaunch.main(["w", "claim", "-o"]) == 0
    assert len(guard["spawn"]) == 1


def test_dotenv_in_the_current_folder_is_ignored(guard, monkeypatch, capsys, tmp_path):
    make(capsys)
    (tmp_path / ".env").write_text("DZ_RELAUNCH_OPEN_ASKS=0\n")
    monkeypatch.chdir(tmp_path)
    answer(monkeypatch, "n")
    assert relaunch.main(["w", "claim", "-o"]) == 3
    assert guard["spawn"] == []


def test_hand_edited_command_asks_even_with_yes(guard, monkeypatch, capsys):
    make(capsys)
    doc = rs.load_set("w")
    doc["members"][0]["argv"] = ["python", "-c", "print('changed')"]
    rs.save_set(doc)                                   # written outside relaunch's add/edit
    answer(monkeypatch, "n")
    assert relaunch.main(["w", "claim", "-o", "-y"]) == 3
    assert "not the one relaunch recorded" in capsys.readouterr().out
    answer(monkeypatch, "y")
    relaunch.main(["release"])
    assert relaunch.main(["w", "claim", "-o", "-y"]) == 0
    assert trust.is_trusted(rs.load_set("w"), rs.load_set("w")["members"][0])


def test_no_console_prints_instead_of_running(guard, monkeypatch, capsys):
    make(capsys)
    monkeypatch.setattr(io, "is_console", lambda: False)
    assert relaunch.main(["w", "claim", "-o", "-y"]) == 0
    assert guard["spawn"] == []


def test_cmd_shim_refuses_special_arguments():
    m = {"kind": "command", "argv": ["pi", "fix the build & run tests"]}
    with pytest.raises(rl.LaunchRefused, match="shell member"):
        rl.build_command(m, which=lambda n: r"C:\npm\pi.cmd")
    ok = {"kind": "command", "argv": ["pi", "--resume", "plain words"]}
    assert rl.build_command(ok, which=lambda n: r"C:\npm\pi.cmd")[0][1:] == ["--resume", "plain words"]


def test_shell_member_command_forms():
    if sys.platform == "win32":
        line, _ = rl.build_command({"kind": "shell", "shell": "cmd", "script": "a && b"})
        assert line == 'cmd /d /s /c "a && b"'
    argv, _ = rl.build_command({"kind": "shell", "shell": "bash", "script": "a && b"}, which=lambda n: "/bin/bash")
    assert argv == ["/bin/bash", "-c", "a && b"]


def test_child_env_drops_dz_variables():
    env = rl.child_env({"DZ_COMMAND": "relaunch", "DZ_CANONICAL_FQCN": "x", "PATH": "p"})
    assert env == {"PATH": "p"}


def test_real_child_receives_argv_byte_for_byte(tmp_path, monkeypatch):
    """AC-ANY-ARGV with a real (harmless) echo child: the stored argv arrives unchanged."""
    out = tmp_path / "argv.json"
    echo = tmp_path / "echo.py"
    echo.write_text(f"import json,sys; json.dump(sys.argv[1:], open(r'{out}','w'))", encoding="utf-8")
    weird = ["a b", 'q"uote', "--", "&", "%PATH%", "x|y"]
    m = {"kind": "command", "argv": [sys.executable, str(echo)] + weird}
    command, _ = rl.build_command(m, which=lambda n: n)
    import subprocess
    code = subprocess.run(command, env=rl.child_env()).returncode
    assert code == 0 and json.load(open(out)) == weird


def test_csb_runner_refuses_write_commands(monkeypatch):
    monkeypatch.undo()
    import importlib
    fresh = importlib.reload(csb)
    for args in (["set", "add", "x", "y"], ["set", "new", "x"], ["set", "rm", "x"], ["set", "forget", "x"],
                 ["resume", "x"]):
        with pytest.raises(ValueError, match="read-only"):
            fresh.run_csb(args)


def test_csb_reads(monkeypatch):
    replies = {
        ("set", "show", "current", "--json"): {"members": [
            {"session_id": "s1", "live_status": "unverified"}, {"session_id": "s2", "live_status": None}]},
        ("scan", "CK3__worker", "--json"): [{"session_id": "s9", "session_name": "CK3__worker"},
                                           {"session_id": "s8", "session_name": "CK3__worker-2"}],
        ("set", "show", "last", "--json"): {"members": [{"session_id": "s1", "session_name": "A"},
                                                        {"session_id": "s3", "session_name": "B"}]},
    }
    monkeypatch.setattr(csb, "run_csb", lambda args, timeout=5.0: json.dumps(replies[tuple(args)]))
    doc = {"members": [{"id": 1, "kind": "claude", "session_id": "s1"},
                       {"id": 2, "kind": "claude", "session_id": "s2"},
                       {"id": 3, "kind": "folder", "cwd": "x"}]}
    assert csb.open_member_ids(doc) == [1]
    assert csb.member_for("CK3__worker")["session_id"] == "s9"
    assert [m["session_id"] for m in csb.members_from("last")] == ["s1", "s3"]


def test_csb_missing_never_blocks(monkeypatch):
    def gone(args, timeout=5.0):
        raise csb.CsbUnavailable("csb is not installed")
    monkeypatch.setattr(csb, "run_csb", gone)
    assert csb.open_session_ids() is None
    assert csb.open_member_ids({"members": [{"id": 1, "kind": "claude", "session_id": "s1"}]}) == []
