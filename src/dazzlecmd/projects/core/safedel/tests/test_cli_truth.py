"""The safedel command line tells the truth (dazzlecmd 0.12.25).

Background: on 2026-11-17 ``dz safedel <path>`` was run with nobody at the
keyboard and without ``--yes``. It prompted, read end-of-file, printed
"Aborted." and exited 0; the command line that called it carried on as if the
delete had happened. These tests pin what the command does now: it refuses
with a non-zero code when nobody can answer, ``--yes`` is the one gate, the
preview is the plan the real run performs, and the last line of output is
always the verdict.

Safety (rule 1b -- a test must not be ABLE to do what it asserts is
prevented): ``main()`` is given a store under ``tmp_path`` with an explicit
registry path (no per-volume routing, nothing under the home folder), the
copy-first settings and the console check are injected (the real config file
is never read), and every test that asserts a REFUSAL uses a store whose
``execute`` raises -- a refusal that fails cannot move anything.
"""
import json
import os
import sys

import pytest

import safedel
import dazzlecmd_lib.core.safedel as sd

WINDOWS = sys.platform == "win32"
TEN_MB = 10 * 1024 * 1024

# These tests exercise the command against the engine's plan/execute API.
# Where the installed dazzlecmd-lib is older (a development checkout beside an
# installed library), the command runs its previous code path instead, and
# these tests do not apply.
pytestmark = pytest.mark.skipif(
    safedel._engine_too_old() is not None,
    reason="needs dazzlecmd-lib 0.10.37 or later: " + str(safedel._engine_too_old()))


class _GuardStore(sd.TrashStore):
    """A real store that cannot execute: planning works, moving raises."""
    def execute(self, plan):
        raise AssertionError("a refusal failed: execute() was reached")


def _write(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _dir_link(target, link):
    link.parent.mkdir(parents=True, exist_ok=True)
    if WINDOWS:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        return "junction"
    os.symlink(str(target), str(link), target_is_directory=True)
    return "symlink"


@pytest.fixture
def cli(tmp_path, monkeypatch, capsys):
    """Run ``safedel.main`` against a temp store.

    ``cli(argv, interactive=False, guard=False, copy_first="off", answer=None)``
    returns ``(exit code, stdout, stderr)``.
    """
    def run(argv, interactive=False, guard=False, copy_first="off",
            answer=None, max_bytes=TEN_MB):
        cls = _GuardStore if guard else sd.TrashStore
        monkeypatch.setattr(
            safedel, "TrashStore",
            lambda: cls(store_path=str(tmp_path / "trash"),
                        registry_path=str(tmp_path / "reg.json")))
        monkeypatch.setattr(safedel, "stdin_is_interactive", lambda: interactive)
        monkeypatch.setattr(safedel, "copy_first_settings",
                            lambda: (copy_first, max_bytes))
        asked = []

        def fake_ask(prompt):
            asked.append(prompt)
            return answer
        monkeypatch.setattr(safedel, "_ask", fake_ask)
        rc = safedel.main([str(a) for a in argv])
        out = capsys.readouterr()
        run.asked = asked
        return rc, out.out, out.err
    return run


def _last_line(out):
    return out.rstrip("\n").splitlines()[-1]


# -- the 2026-11-17 case -----------------------------------------------------


def test_no_yes_and_nobody_at_the_keyboard_is_refused_non_zero(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli([f], interactive=False, guard=True)

    assert rc == 3                                   # was 0 on 2026-11-17
    assert _last_line(out) == \
        "safedel: REFUSED not interactive and --yes was not given"
    assert "--yes" in err and f.read_bytes() == b"A"
    assert cli.asked == []                           # no prompt was attempted
    assert not (tmp_path / "trash").exists()


def test_yes_stages_and_the_last_line_says_so(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli(["--yes", f])

    assert rc == 0 and not f.exists()
    assert _last_line(out) == "safedel: STAGED 1"
    assert cli.asked == []


# -- the prompt --------------------------------------------------------------


def test_at_a_console_it_asks_and_yes_proceeds(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli([f], interactive=True, answer="y")

    assert rc == 0 and not f.exists()
    assert len(cli.asked) == 1 and "[y/N]" in cli.asked[0]
    assert _last_line(out) == "safedel: STAGED 1"


@pytest.mark.parametrize("answer", ["n", "", "yes please", None])
def test_anything_but_y_is_a_refusal_with_a_non_zero_code(cli, tmp_path, answer):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli([f], interactive=True, answer=answer, guard=True)

    assert rc == 3 and f.read_bytes() == b"A"
    assert _last_line(out) == "safedel: REFUSED declined at the prompt"


def test_json_does_not_stand_in_for_yes(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli(["--json", f], interactive=True, guard=True)

    data = json.loads(out)                           # still one JSON object
    assert rc == 3 and data["exit_code"] == 3
    assert data["verdict"].startswith("safedel: REFUSED")
    assert f.exists() and cli.asked == []


def test_json_with_yes_reports_verdict_and_code_as_fields(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli(["--yes", "--json", f])

    data = json.loads(out)
    assert rc == 0 and data["exit_code"] == 0
    assert data["verdict"] == "safedel: STAGED 1"
    assert data["staged"] == 1 and data["entries"][0]["status"] == "OK"
    assert data["recover_command"] == f"dz safedel recover {data['folder_name']}"


# -- scoped --yes ------------------------------------------------------------


def test_yes_does_not_swallow_the_path_after_it(cli, tmp_path):
    f = _write(tmp_path / "src" / "dangerous-looking.txt", b"A")

    rc, out, err = cli(["--yes", f])

    assert rc == 0 and not f.exists()


def test_a_mistyped_scope_is_a_usage_error_not_consent(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli(["--yes", "dangerous,delete-thru-junction", f], guard=True)

    assert rc == 2 and f.exists()
    assert "known scope" in err


def test_a_file_named_like_a_scope_is_reached_after_double_dash(
        cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = _write(tmp_path / "dangerous", b"A")

    rc, out, err = cli(["--yes", "--", "dangerous"])

    assert rc == 0 and not f.exists()


# -- the preview is the plan -------------------------------------------------


def test_dry_run_prints_the_plan_and_moves_nothing(cli, tmp_path):
    tree = tmp_path / "src" / "tree"
    _write(tree / "one.txt", b"1")
    _write(tree / "sub" / "two.txt", b"22")

    rc, out, err = cli(["--dry-run", tree], guard=True)

    assert rc == 0 and (tree / "one.txt").exists()
    assert "2 file(s), 1 folder(s)" in out
    assert "move into the trash" in out
    assert _last_line(out) == "safedel: DRY-RUN 1 would be staged"
    assert not (tmp_path / "trash").exists()


def test_a_dry_run_of_a_batch_that_would_be_refused_says_so(cli, tmp_path):
    a = _write(tmp_path / "src" / "a" / "x.json", b"A")
    b = _write(tmp_path / "src" / "b" / "x.json", b"B")

    rc, out, err = cli(["--dry-run", a, b], guard=True)

    assert rc == 3                                   # the code the real run would give
    assert _last_line(out).startswith("safedel: REFUSED")
    assert "share a name" in err


def test_the_real_run_shows_the_same_plan_before_acting(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    _, dry_out, _ = cli(["--dry-run", f])
    plan_block = dry_out.split("DRY RUN")[0].rstrip()
    rc, real_out, _ = cli(["--yes", f])

    assert rc == 0
    assert str(f) in plan_block and "move into the trash" in plan_block
    assert real_out.startswith(plan_block)           # same preview, then the act


# -- refusals reach the caller as code 3 -------------------------------------


def test_same_name_batch_is_refused_whole(cli, tmp_path):
    a = _write(tmp_path / "src" / "a" / "x.json", b"A")
    b = _write(tmp_path / "src" / "b" / "x.json", b"B")

    rc, out, err = cli(["--yes", a, b], guard=True)

    assert rc == 3 and a.exists() and b.exists()
    assert _last_line(out).startswith("safedel: REFUSED")


def test_every_path_missing_is_code_3(cli, tmp_path):
    rc, out, err = cli(["--yes", tmp_path / "nope"], guard=True)
    assert rc == 3 and _last_line(out).startswith("safedel: REFUSED nothing to delete")


def test_one_missing_path_is_partial_code_4(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli(["--yes", f, tmp_path / "typo.txt"])

    assert rc == 4 and not f.exists()
    assert _last_line(out) == "safedel: PARTIAL staged 1, not staged 1"


def test_delete_through_scope_reaches_the_engine(cli, tmp_path):
    kept = _write(tmp_path / "data" / "private" / "f.txt", b"F").parent
    link = tmp_path / "wt" / "private"
    kind = _dir_link(kept, link)
    scope = ("delete-through-junction" if kind == "junction"
             else "delete-through-symlink")

    rc, out, err = cli(["--yes", scope, link])

    assert rc == 0, err
    assert not os.path.lexists(link) and not kept.exists()
    assert _last_line(out) == "safedel: STAGED 2"


def test_a_link_without_the_scope_loses_only_the_link(cli, tmp_path):
    kept = _write(tmp_path / "data" / "private" / "f.txt", b"F").parent
    link = tmp_path / "wt" / "private"
    _dir_link(kept, link)

    rc, out, err = cli(["--yes", link])

    assert rc == 0 and not os.path.lexists(link)
    assert (kept / "f.txt").read_bytes() == b"F"
    assert "what it points at is not touched" in out


# -- copy-first --------------------------------------------------------------


def test_copy_first_is_on_for_non_interactive_callers_in_auto_mode(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A" * 10)

    rc, out, err = cli(["--yes", "--json", f], interactive=False, copy_first="auto")

    data = json.loads(out)
    assert rc == 0 and data["copy_first"] is True
    assert data["entries"][0]["copy_first"]["verified"] is True
    assert os.path.isfile(os.path.join(data["folder_path"], "copy-first", "a.txt"))


def test_copy_first_is_off_at_a_console_in_auto_mode(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A" * 10)

    rc, out, err = cli(["--yes", "--json", f], interactive=True, copy_first="auto")

    data = json.loads(out)
    assert rc == 0 and data["copy_first"] is False
    assert not os.path.exists(os.path.join(data["folder_path"], "copy-first"))


@pytest.mark.parametrize("argv_scope, mode, expected", [
    ("copy-first", "off", True),          # the scope forces it on
    ("no-copy-first", "always", False),   # ... and off
])
def test_scopes_override_the_configured_mode(cli, tmp_path, argv_scope, mode, expected):
    f = _write(tmp_path / "src" / "a.txt", b"A" * 10)

    rc, out, err = cli(["--yes", argv_scope, "--json", f], copy_first=mode)

    assert rc == 0 and json.loads(out)["copy_first"] is expected


def test_an_oversize_batch_is_refused_and_names_both_overrides(cli, tmp_path):
    f = _write(tmp_path / "src" / "big.bin", b"z" * 500)

    rc, out, err = cli(["--yes", f], copy_first="always", max_bytes=100, guard=True)

    assert rc == 3 and f.exists()
    assert "no-copy-first" in err and "--copy-first-max" in err


def test_copy_first_max_raises_the_limit_for_one_call(cli, tmp_path):
    f = _write(tmp_path / "src" / "big.bin", b"z" * 500)

    rc, out, err = cli(["--yes", "--copy-first-max", "1k", f],
                       copy_first="always", max_bytes=100)

    assert rc == 0 and not f.exists()


def test_a_bad_copy_first_max_is_a_usage_error(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")
    rc, out, err = cli(["--yes", "--copy-first-max", "lots", f], guard=True)
    assert rc == 2 and f.exists()


# -- nothing ends silently ---------------------------------------------------


def test_an_unexpected_exception_still_ends_with_a_verdict(cli, tmp_path, monkeypatch):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    def explode(self, *a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(sd.TrashStore, "plan", explode)

    rc, out, err = cli(["--yes", f])

    assert rc == 1
    assert _last_line(out) == "safedel: ERROR RuntimeError: disk on fire"
    assert f.exists()


def test_a_failed_post_condition_is_code_6(cli, tmp_path, monkeypatch):
    from dazzlecmd_lib.core.safedel import _store
    f = _write(tmp_path / "src" / "a.txt", b"A")
    monkeypatch.setattr(
        _store, "stage_to_trash",
        lambda path, dest, c: _store.StagingResult(
            success=True, source_path=path,
            dest_path=os.path.join(dest, "a.txt"), method="rename"))

    rc, out, err = cli(["--yes", f])

    assert rc == 6
    assert _last_line(out).startswith("safedel: POSTCONDITION-FAILED")
    assert "CHECK FAILED" in err


# -- an engine older than this command ---------------------------------------


def test_an_older_engine_runs_the_previous_command_and_says_so(
        monkeypatch, capsys):
    """dazzlecmd and dazzlecmd-lib can be at different versions on one
    machine (a dev box with an editable dazzlecmd and an installed lib). The
    command must keep working there, not become an import error for every
    session. The previous command is stubbed: nothing real is run."""
    monkeypatch.setattr(safedel, "_ENGINE_IMPORT_ERROR",
                        ImportError("cannot import name 'stdin_is_interactive'"))
    seen = []
    monkeypatch.setattr(safedel, "_run_previous_cli",
                        lambda argv: seen.append(list(argv)) or 0)

    rc = safedel.main(["--yes", "some-path"])

    err = capsys.readouterr().err
    assert rc == 0 and seen == [["--yes", "some-path"]]
    assert "older than this safedel command needs" in err
    assert "running the previous command" in err


def test_a_current_engine_never_takes_the_older_engine_path(cli, tmp_path,
                                                            monkeypatch):
    def _boom(argv):
        raise AssertionError("the previous command ran against a current engine")
    monkeypatch.setattr(safedel, "_run_previous_cli", _boom)
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli(["--yes", f])

    assert rc == 0 and safedel._engine_too_old() is None
    assert "previous command" not in err


def test_the_previous_command_file_is_the_0_12_24_cli():
    """The file the older-engine path runs is present and is a CLI: it has a
    ``main`` and still has the 0.12.24 delete flow (its own ``_do_delete``
    taking two arguments). Loaded as a module; nothing is executed."""
    import importlib.util
    import inspect
    path = os.path.join(os.path.dirname(safedel.__file__), "_cli_0_12_24.py")
    spec = importlib.util.spec_from_file_location("_prev_cli_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
    assert list(inspect.signature(module._do_delete).parameters) == ["store", "args"]


def test_the_report_names_this_batch_not_last(cli, tmp_path):
    f = _write(tmp_path / "src" / "a.txt", b"A")

    rc, out, err = cli(["--yes", f])

    name = os.listdir(tmp_path / "trash")[0]
    assert f"dz safedel recover {name}" in out
    assert "recover last" not in out
