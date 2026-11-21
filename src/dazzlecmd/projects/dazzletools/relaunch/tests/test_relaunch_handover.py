"""S5: the folder hand-over and the dzr wrappers (run for real against a fake dz)."""

import os
import shutil
import subprocess
import sys

import pytest

import relaunch
import relaunch_launch as rl
import relaunch_wrappers as wr

FAKE_DZ = (
    "import os,sys\n"
    "t=os.environ['DEMO_TARGET']\n"
    "if not os.path.isdir(t):\n"
    "    sys.exit(3)\n"
    "sys.path.insert(0, os.environ['TOOL_DIR'])\n"
    "import relaunch_launch as rl\n"
    "_, handover = rl.handover_from_argv(sys.argv[1:])   # what relaunch.main does for dzr.cmd\n"
    "os.environ.update(handover)\n"
    "ok = rl.write_cd_file(t)\n"
    "sys.exit(0 if ok else 7)\n"
)
TOOL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_cd_file_not_used_without_the_wrapper(tmp_path):
    assert rl.write_cd_file(str(tmp_path), env={}) is None


def test_cd_file_written_for_posix(tmp_path):
    f = tmp_path / "cd.txt"
    env = {rl.CD_FILE_ENV: str(f), rl.CD_FORMAT_ENV: "posix"}
    assert rl.write_cd_file("/home/u/x y", env=env) is True
    assert f.read_bytes() == b"/home/u/x y\n"


def test_cd_file_refuses_a_lossy_encoding(tmp_path, monkeypatch):
    f = tmp_path / "cd.txt"
    monkeypatch.setattr(rl, "_console_encoding", lambda: "cp437")
    env = {rl.CD_FILE_ENV: str(f), rl.CD_FORMAT_ENV: "cmd"}
    assert rl.write_cd_file("C:\\code\\\u6f22\u5b57", env=env) is False
    assert not f.exists()


@pytest.mark.parametrize("shell,folder,expected", [
    ("cmd", r"C:\a b", 'cd /d "C:\\a b"'),
    ("bash", "/a/it's", "cd -- '/a/it'\\''s'"),
    ("pwsh", "C:\\it's", "Set-Location -LiteralPath 'C:\\it''s'"),
])
def test_cd_line(shell, folder, expected):
    assert rl.cd_line(folder, shell) == expected


def _cmd_tab(tmp_path, target, v_on):
    fake = tmp_path / "fake_dz.py"
    fake.write_text(FAKE_DZ, encoding="utf-8")
    dzr = tmp_path / "dzr.cmd"
    dzr.write_bytes(wr.wrapper_text("cmd", invoke=f'"{sys.executable}" "{fake}"').encode("ascii"))
    start = tmp_path / "start"
    start.mkdir(exist_ok=True)
    tab = tmp_path / "tab.cmd"
    tab.write_bytes((f'@echo off\r\ncd /d "{start}"\r\ncall "{dzr}"\r\n'
                     f'echo rc=%ERRORLEVEL%\r\ncd\r\n').encode("ascii"))
    env = dict(os.environ, DEMO_TARGET=str(target), TOOL_DIR=TOOL_DIR)
    r = subprocess.run(["cmd", "/d", "/V:ON" if v_on else "/V:OFF", "/c", str(tab)],
                       capture_output=True, text=True, env=env, timeout=60)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    return lines[-2], lines[-1], start


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe wrapper")
@pytest.mark.parametrize("v_on", [True, False])
@pytest.mark.parametrize("name", ["proj with space", "a&b", "bang!dir"])
def test_dzr_cmd_moves_the_tab(tmp_path, name, v_on):
    target = tmp_path / name
    target.mkdir()
    rc, cwd, _ = _cmd_tab(tmp_path, target, v_on)
    assert rc == "rc=0"
    assert cwd == str(target)


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe wrapper")
def test_dzr_cmd_never_sets_the_handover_variable_in_the_tab(tmp_path):
    """If cmd's "Terminate batch job? Y" stops dzr.cmd mid-run, nothing may linger in the tab:
    the hand-over travels as an argument, so cmd never holds DZ_RELAUNCH_CD_FILE at all."""
    fake = tmp_path / "fake_dz.py"
    fake.write_text("import os,sys\n"
                    "sys.exit(5 if 'DZ_RELAUNCH_CD_FILE' in os.environ else\n"
                    "         (0 if any(a.startswith('--cd-file=') for a in sys.argv) else 6))\n",
                    encoding="utf-8")
    dzr = tmp_path / "dzr.cmd"
    dzr.write_bytes(wr.wrapper_text("cmd", invoke=f'"{sys.executable}" "{fake}"').encode("ascii"))
    tab = tmp_path / "tab.cmd"
    tab.write_bytes(f'@echo off\r\ncall "{dzr}" x claim\r\necho rc=%ERRORLEVEL%\r\n'.encode("ascii"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("DZ_RELAUNCH_")}
    r = subprocess.run(["cmd", "/d", "/c", str(tab)], capture_output=True, text=True, env=env, timeout=60)
    assert r.stdout.strip().splitlines()[-1] == "rc=0", r.stdout + r.stderr


def test_main_applies_the_handover_for_one_run_only(tmp_path, monkeypatch):
    import relaunch
    monkeypatch.delenv(rl.CD_FILE_ENV, raising=False)
    seen = {}
    monkeypatch.setattr(relaunch, "_main", lambda argv: seen.update(argv=argv, env=os.environ.get(rl.CD_FILE_ENV)) or 0)
    assert relaunch.main([f"--cd-file={tmp_path / 'cd.txt'}", "--cd-format=cmd", "ck3", "claim"]) == 0
    assert seen["argv"] == ["ck3", "claim"] and seen["env"] == str(tmp_path / "cd.txt")
    assert rl.CD_FILE_ENV not in os.environ                      # restored after the run


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe wrapper")
def test_dzr_cmd_passes_failure_back_and_stays(tmp_path):
    rc, cwd, start = _cmd_tab(tmp_path, tmp_path / "gone", True)
    assert rc == "rc=3"
    assert cwd == str(start)


def _git_bash():
    for p in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash") or ""):
        if p and os.path.isfile(p) and "system32" not in p.lower():
            return p
    return None


@pytest.mark.skipif(_git_bash() is None, reason="no bash available")
@pytest.mark.parametrize("name", ["plain", "has space", "a$HOME$b", "it's"])
def test_dzr_bash_moves_the_shell(tmp_path, name):
    bash = _git_bash()
    target = tmp_path / name
    target.mkdir()
    fake = tmp_path / "fake_dz.py"
    fake.write_text(FAKE_DZ, encoding="utf-8")
    py = sys.executable.replace("\\", "/")
    func = wr.wrapper_text("bash", invoke=f"'{py}' '{str(fake).replace(chr(92), '/')}'")
    script = tmp_path / "t.sh"
    script.write_text(func + "\nset -u\ndzr\necho \"rc=$?\"\npwd -W 2>/dev/null || pwd\n", encoding="utf-8")
    env = dict(os.environ, DEMO_TARGET=str(target), TOOL_DIR=TOOL_DIR)
    r = subprocess.run([bash, str(script)], capture_output=True, text=True, env=env, timeout=60)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert lines[-2] == "rc=0", r.stdout + r.stderr
    assert os.path.normcase(os.path.normpath(lines[-1])) == os.path.normcase(str(target))


def test_shell_init_prints_the_wrapper(capsys):
    assert relaunch.main(["shell-init", "cmd"]) == 0
    cap = capsys.readouterr()
    out = cap.out
    assert 'dz relaunch --cd-file="%DZR_TMP%\\cd.txt" --cd-format=cmd %*' in out
    assert "setlocal" not in out.split("Must not use setlocal")[1]
    assert out.strip().splitlines()[-1] == "exit /b %DZR_RC%"      # nothing after the wrapper
    assert "relaunch: PRINTED dzr for cmd" in cap.err


def test_shell_init_unknown_shell_is_usage(capsys):
    assert relaunch.main(["shell-init", "fish"]) == 2
