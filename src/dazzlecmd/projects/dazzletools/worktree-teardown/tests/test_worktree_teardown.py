"""dz worktree-teardown: the command line over the library's teardown.

The teardown itself (links first, checks, folder to the trash, prune) is
tested in dazzlecmd-lib (tests/test_core_safedel_worktree.py). These tests
cover what the command adds: consent, the plan it prints, exit codes, and the
last-line verdict.

Safety (rule 1b): every repository, worktree, link, trash store and link
registry is under ``tmp_path`` (``_make_store`` is replaced, so the real trash
store and ``~/.safedel`` are never touched); tests asserting a refusal use a
store factory that raises; ``git worktree remove`` is never run.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL_DIR))
import worktree_teardown as wt  # noqa: E402
sys.path.pop(0)

pytestmark = pytest.mark.skipif(
    wt._IMPORT_ERROR is not None,
    reason="needs dazzlecmd-lib 0.10.38 or later (the engine's teardown API)")

WINDOWS = sys.platform == "win32"


def _git(repo, *args):
    r = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.invalid",
         "-c", "user.name=t", "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _dir_link(target, link):
    if WINDOWS:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(str(target), str(link), target_is_directory=True)


@pytest.fixture
def repo(tmp_path):
    main = tmp_path / "proj"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "README.md").write_text("x\n")
    (main / ".gitignore").write_text("private/\n")
    _git(main, "add", "README.md", ".gitignore")
    _git(main, "commit", "-q", "-m", "init")
    private = main / "private"
    private.mkdir()
    (private / "notes.md").write_text("notes\n")
    wtree = tmp_path / "proj__feature"
    _git(main, "worktree", "add", "-q", "-b", "feat", str(wtree), "main")
    _dir_link(private, wtree / "private")
    return main, private, wtree


@pytest.fixture
def run(tmp_path, monkeypatch, capsys):
    """``run(argv, interactive=False, answer=None, guard=False)`` ->
    (exit code, stdout, stderr), against a temp store and registry."""
    import dazzlecmd_lib.core.safedel as sd

    def _run(argv, interactive=False, answer=None, guard=False):
        def make_store():
            if guard:
                raise AssertionError("a refusal failed: the store was opened")
            return (sd.TrashStore(store_path=str(tmp_path / "trash"),
                                  registry_path=str(tmp_path / "reg.json")),
                    str(tmp_path / "junctions.json"))
        monkeypatch.setattr(wt, "_make_store", make_store)
        monkeypatch.setattr(wt, "stdin_is_interactive", lambda: interactive)
        asked = []
        monkeypatch.setattr(wt, "_ask", lambda p: asked.append(p) or answer)
        rc = wt.main([str(a) for a in argv])
        out = capsys.readouterr()
        _run.asked = asked
        return rc, out.out, out.err
    return _run


def _last(out):
    return out.rstrip("\n").splitlines()[-1]


def test_yes_tears_down_and_leaves_the_target_alone(run, repo):
    main, private, wtree = repo

    rc, out, err = run(["--yes", wtree])

    assert rc == 0, err
    assert _last(out) == f"worktree-teardown: DONE {wtree}"
    assert not os.path.lexists(wtree)
    assert (private / "notes.md").read_text() == "notes\n"
    assert "will NOT be touched" in out and "git worktree prune" in out
    assert "dz safedel recover <batch-name>" in out
    listed = _git(main, "worktree", "list").replace("\\", "/")
    assert str(wtree).replace("\\", "/") not in listed


def test_without_yes_and_nobody_at_the_keyboard_it_refuses(run, repo):
    main, private, wtree = repo

    rc, out, err = run([wtree], interactive=False, guard=True)

    assert rc == 3
    assert _last(out) == \
        "worktree-teardown: REFUSED not interactive and --yes was not given"
    assert os.path.lexists(wtree / "private") and run.asked == []


@pytest.mark.parametrize("answer, expected_rc", [("y", 0), ("n", 3), (None, 3)])
def test_at_a_console_it_asks(run, repo, answer, expected_rc):
    main, private, wtree = repo

    rc, out, err = run([wtree], interactive=True, answer=answer)

    assert rc == expected_rc and len(run.asked) == 1
    assert os.path.lexists(wtree) is (expected_rc != 0)
    assert (private / "notes.md").exists()


def test_dry_run_shows_the_plan_and_changes_nothing(run, repo):
    main, private, wtree = repo

    rc, out, err = run(["--dry-run", wtree], guard=True)

    assert rc == 0
    assert _last(out) == ("worktree-teardown: DRY-RUN 1 link(s) and the "
                          "folder would be removed")
    assert str(wtree / "private") in out
    assert os.path.lexists(wtree / "private")


def test_a_main_checkout_is_refused(run, repo):
    main, private, wtree = repo

    rc, out, err = run(["--yes", main], guard=True)

    assert rc == 3 and "main checkout" in err
    assert _last(out).startswith("worktree-teardown: REFUSED")
    assert (main / "README.md").exists()


def test_a_teardown_that_stops_part_way_is_exit_4(run, repo, monkeypatch):
    main, private, wtree = repo
    import dazzlecmd_lib.core.safedel as sd

    def stopped(plan, store, **kw):
        return sd.TeardownResult(
            success=False, plan=plan,
            steps=["removed the link (for the test)"],
            errors=["after removing the links: the target had 2 entries and has 1"],
            batches=["2026-11-18__12-00-00"])
    monkeypatch.setattr(wt, "execute_teardown", stopped)

    rc, out, err = run(["--yes", wtree])

    assert rc == 4
    assert _last(out).startswith("worktree-teardown: STOPPED after removing the links")
    assert "STOPPED part-way" in err and "2026-11-18__12-00-00" in out


def test_a_mistyped_scope_is_a_usage_error(run, repo):
    main, private, wtree = repo
    rc, out, err = run(["--yes", "dangerous,typo", wtree], guard=True)
    assert rc == 2 and os.path.lexists(wtree)


def test_an_older_library_is_reported_not_crashed(monkeypatch, capsys):
    monkeypatch.setattr(wt, "_IMPORT_ERROR", ImportError("no plan_teardown"))
    rc = wt.main(["--yes", "anything"])
    out = capsys.readouterr()
    assert rc == 1 and "dazzlecmd-lib 0.10.38" in out.err
    assert _last(out.out) == "worktree-teardown: ERROR dazzlecmd-lib is too old"
