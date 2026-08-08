"""Unit tests for --fix: target selection, refusals, and the confirm gate.

DELIBERATELY ISOLATED FROM THE PAYLOAD. Every test here injects a fake
subprocess runner and fake input; nothing in this file can execute git or
pip, and no real repository is reachable from it. Driving the live CLI to
exercise a confirmation prompt means one bug in the guard writes to 140
repos -- the apparatus must not be wired to the thing it is testing.

The regression that motivated most of this: apply_fixes() selected its
target as `record["paths"][0]`, which is discovery order (alphabetical).
For dazzlecmd that is `fiber-work`, a feature branch. A real --fix run
would have reinstalled -- or fast-forwarded -- into someone's in-progress
work. Display had already been fixed to use the primary checkout; the
write path had not, which is the half that matters.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent.parent))

import dazzle_update as du  # noqa: E402


# -- fakes ---------------------------------------------------------------

class _Result:
    def __init__(self, rc=0, stderr=""):
        self.returncode = rc
        self.stdout = ""
        self.stderr = stderr


def _is_probe(cmd):
    """Read-only queries the guard asks before deciding.

    The distinction is the whole point of this apparatus: `.calls` now
    contains both the questions and the answers-acted-on, and only the
    latter can change a repository. A test asserting "did not act" must
    not be satisfied merely because nothing was ASKED.
    """
    return any(t in cmd for t in ("diff", "ls-files"))


class FakeRunner:
    """Records commands instead of running them.

    Also answers the collision probe, since apply_fixes now measures
    before refusing. The default answer is "nothing local, nothing
    incoming", i.e. a clean fast-forward; tests that care pass explicit
    path lists.
    """

    def __init__(self, rc=0, dirty=(), untracked=(), incoming=(), adds=()):
        self.calls = []
        self.rc = rc
        self._answers = {"dirty": list(dirty), "untracked": list(untracked),
                         "incoming": list(incoming), "adds": list(adds)}

    def _answer_for(self, cmd):
        if "ls-files" in cmd:
            return self._answers["untracked"]
        if "--diff-filter=A" in cmd:
            return self._answers["adds"]
        if "HEAD..@{u}" in cmd:
            return self._answers["incoming"]
        return self._answers["dirty"]

    def __call__(self, cmd, **kw):
        cmd = list(cmd)
        self.calls.append(cmd)
        if _is_probe(cmd):
            r = _Result(0)
            r.stdout = "\0".join(self._answer_for(cmd))
            return r
        return _Result(self.rc)

    @property
    def actions(self):
        """Only the commands that would change something."""
        return [c for c in self.calls if not _is_probe(c)]

    @property
    def targets(self):
        """The path each ACTION acted on -- probes are questions, not acts."""
        out = []
        for c in self.actions:
            if "-C" in c:
                out.append(c[c.index("-C") + 1])
            elif "-e" in c:
                out.append(c[c.index("-e") + 1])
        return out


@pytest.fixture
def no_subprocess(monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(du.subprocess, "run", runner)
    return runner


@pytest.fixture
def collide(monkeypatch):
    """A runner whose probe reports an incoming change to a file the
    working tree has modified -- a pull git would reject."""
    runner = FakeRunner(dirty=["src/app.py"], incoming=["src/app.py"])
    monkeypatch.setattr(du.subprocess, "run", runner)
    return runner


@pytest.fixture
def quiet(monkeypatch):
    lines = []
    monkeypatch.setattr(du, "safe_print", lambda t="", **kw: lines.append(str(t)))
    return lines


def _record(key, full_name, primary, checkouts, git=None, installed=None,
            **extra):
    r = {
        "key": key, "full_name": full_name, "primary": primary,
        "primary_reason": extra.pop("primary_reason", "test"),
        "checkouts": checkouts, "git": git or {},
        "installed": installed, "paths": [c["path"] for c in checkouts],
        "source_version": extra.pop("source_version", None),
        "declared_dist": extra.pop("declared_dist", None),
        "pypi_owned": extra.pop("pypi_owned", None),
        "foreign": extra.pop("foreign", False),
        "excluded_paths": [],
    }
    r.update(extra)
    return r


def _ck(path, branch, upstream, dirty=0, untracked=0):
    return {"path": path, "excluded": False,
            "git": {"branch": branch, "upstream": upstream, "ahead": 0,
                    "behind": 1, "dirty_count": dirty,
                    "untracked_count": untracked}}


# -- THE regression: never act on paths[0] --------------------------------

def test_fix_targets_the_primary_not_the_first_path(no_subprocess, quiet):
    """The dazzlecmd shape: fiber-work sorts first, github is primary."""
    fiber = _ck(r"C:\code\dazzlecmd\fiber-work", "fiber-work", None, dirty=2)
    github = _ck(r"C:\code\dazzlecmd\github", "main", "origin/main")
    rec = _record("dazzletools/dazzlecmd", "DazzleTools/dazzlecmd",
                  primary=r"C:\code\dazzlecmd\github",
                  checkouts=[fiber, github],
                  git=github["git"],
                  installed={"name": "dazzlecmd", "version": "0.12.5a0",
                             "path": r"C:\code\dazzlecmd\github"},
                  source_version="0.12.6")
    du.apply_fixes({"stale-install-metadata": [rec]}, assume_yes=True)
    assert no_subprocess.targets == [r"C:\code\dazzlecmd\github"]
    assert all("fiber-work" not in t for t in no_subprocess.targets), (
        "acted on a feature-branch worktree -- the exact regression")


def test_no_primary_refuses_rather_than_guessing(no_subprocess, quiet):
    a = _ck(r"C:\a\one", "main", "origin/main")
    b = _ck(r"C:\a\two", "main", "origin/main")
    rec = _record("o/p", "Org/proj", primary=None, checkouts=[a, b],
                  git=a["git"], primary_reason="2 tracking checkouts, ambiguous")
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert no_subprocess.actions == []


def test_install_only_record_uses_its_install_path(no_subprocess, quiet):
    """A subpackage has no checkouts; its single install path is unambiguous."""
    rec = _record("dazzle-dz", None, primary=None, checkouts=[],
                  installed={"name": "dazzle-dz", "version": "0.12.5a1",
                             "path": r"C:\code\dazzlecmd\github\packages\alias"},
                  source_version="0.12.6a0")
    du.apply_fixes({"stale-install-metadata": [rec]}, assume_yes=True)
    assert no_subprocess.targets == [r"C:\code\dazzlecmd\github\packages\alias"]


# -- pull refusals --------------------------------------------------------

@pytest.mark.parametrize("git,reason", [
    ({"branch": "main", "upstream": None, "behind": 1, "ahead": 0,
      "dirty_count": 0, "untracked_count": 0}, "no upstream"),
    ({"branch": "main", "upstream": "origin/main", "behind": 1, "ahead": 2,
      "dirty_count": 0, "untracked_count": 0}, "diverged"),
])
def test_pull_refuses_unsafe_states(no_subprocess, quiet, git, reason):
    """States refused on their own terms, before any measuring: without a
    tracking branch there is nothing to fast-forward FROM, and a diverged
    branch needs a merge, which this tool does not perform."""
    ck = {"path": r"C:\a\p", "excluded": False, "git": git}
    rec = _record("o/p", "Org/proj", primary=r"C:\a\p", checkouts=[ck], git=git)
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert no_subprocess.actions == [], f"pulled despite: {reason}"


def test_pull_refuses_foreign_upstreams(no_subprocess, quiet):
    """ostris/ai-toolkit at 510 behind is tracked, not maintained here."""
    ck = _ck(r"C:\a\ai", "main", "origin/main")
    rec = _record("ostris/ai-toolkit", "ostris/ai-toolkit",
                  primary=r"C:\a\ai", checkouts=[ck], git=ck["git"],
                  foreign=True)
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert no_subprocess.actions == []


def test_clean_tracking_repo_is_pulled(no_subprocess, quiet):
    """The counterpart -- refusing everything must not pass the suite."""
    ck = _ck(r"C:\a\ok", "main", "origin/main")
    rec = _record("o/ok", "Org/ok", primary=r"C:\a\ok", checkouts=[ck],
                  git=ck["git"])
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert no_subprocess.targets == [r"C:\a\ok"]
    assert "--ff-only" in no_subprocess.actions[0]


# -- the pull guard measures rather than assumes --------------------------
#
# USER REPORT 2026-08-08: `dz dazzle-update . --fix` refused dazzlesum
# with "dirty tree", on a tree holding ONE untracked file that the
# incoming commits did not touch. The pull was a clean fast-forward.
# tests/one-offs/thinking/pulllab.py runs both predicates against real
# git across 12 scenarios: the old one blocked 5 pulls git completes.

def test_uncommitted_work_alone_no_longer_blocks_a_pull(no_subprocess, quiet):
    """THE REPORTED CASE. dirty_count and untracked_count are non-zero,
    and the probe reports no overlap with what is coming in."""
    ck = _ck(r"C:\a\ok", "main", "origin/main", dirty=3, untracked=1)
    rec = _record("o/ok", "Org/ok", primary=r"C:\a\ok", checkouts=[ck],
                  git=ck["git"])
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert no_subprocess.targets == [r"C:\a\ok"]


def test_a_measured_collision_refuses_and_names_the_file(collide, quiet):
    ck = _ck(r"C:\a\p", "main", "origin/main", dirty=1)
    rec = _record("o/p", "Org/proj", primary=r"C:\a\p", checkouts=[ck],
                  git=ck["git"])
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert collide.actions == []
    joined = "\n".join(quiet)
    assert "src/app.py" in joined, "refused without saying what is in the way"
    assert "would overwrite uncommitted work" in joined
    assert "dirty tree" not in joined


def test_an_untracked_file_the_pull_adds_is_a_collision(monkeypatch, quiet):
    """The half the old guard was reaching for. An untracked path can
    only be hit by an incoming ADD -- a path upstream MODIFIES exists in
    HEAD, so it is tracked here too."""
    runner = FakeRunner(untracked=[".vscode/settings.json"],
                        adds=[".vscode/settings.json"],
                        incoming=[".vscode/settings.json"])
    monkeypatch.setattr(du.subprocess, "run", runner)
    ck = _ck(r"C:\a\p", "main", "origin/main", untracked=1)
    rec = _record("o/p", "Org/proj", primary=r"C:\a\p", checkouts=[ck],
                  git=ck["git"])
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert runner.actions == []
    assert ".vscode/settings.json" in "\n".join(quiet)


def test_many_collisions_are_summarized_not_dumped(monkeypatch, quiet):
    """A refusal listing forty paths buries the row it belongs to. Show
    three and count the rest -- but SAY there is a rest, because a
    silently truncated list reads as the whole answer."""
    paths = [f"src/mod{i}.py" for i in range(9)]
    runner = FakeRunner(dirty=paths, incoming=paths)
    monkeypatch.setattr(du.subprocess, "run", runner)
    ck = _ck(r"C:\a\p", "main", "origin/main", dirty=9)
    rec = _record("o/p", "Org/proj", primary=r"C:\a\p", checkouts=[ck],
                  git=ck["git"])
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    joined = "\n".join(quiet)
    assert runner.actions == []
    assert "src/mod0.py" in joined
    assert "(+6 more)" in joined, "truncated without saying so"
    assert "src/mod8.py" not in joined


def test_exactly_three_collisions_are_not_reported_as_truncated(monkeypatch,
                                                                quiet):
    """The off-by-one: three fit, so there is no '+0 more'."""
    paths = [f"src/mod{i}.py" for i in range(3)]
    runner = FakeRunner(dirty=paths, incoming=paths)
    monkeypatch.setattr(du.subprocess, "run", runner)
    ck = _ck(r"C:\a\p", "main", "origin/main", dirty=3)
    rec = _record("o/p", "Org/proj", primary=r"C:\a\p", checkouts=[ck],
                  git=ck["git"])
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    joined = "\n".join(quiet)
    assert "more)" not in joined
    assert "src/mod2.py" in joined


def test_an_unmeasurable_repo_refuses_rather_than_pulling(monkeypatch, quiet):
    """A failed measurement must never read as permission."""
    class Broken(FakeRunner):
        def __call__(self, cmd, **kw):
            cmd = list(cmd)
            self.calls.append(cmd)
            return _Result(128, stderr="fatal: no upstream configured")

    runner = Broken()
    monkeypatch.setattr(du.subprocess, "run", runner)
    ck = _ck(r"C:\a\p", "main", "origin/main")
    rec = _record("o/p", "Org/proj", primary=r"C:\a\p", checkouts=[ck],
                  git=ck["git"])
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert runner.actions == []
    assert "could not determine" in "\n".join(quiet)


# -- #106: never reinstall across a name mismatch -------------------------

def test_reinstall_refuses_across_a_dist_rename(no_subprocess, quiet):
    rec = _record("dazzletools/preserve", "DazzleTools/preserve",
                  primary=r"C:\code\preserve", checkouts=[],
                  installed={"name": "preserve", "version": "0.5.2",
                             "path": r"C:\code\preserve"},
                  declared_dist="dazzle-preserve", source_version="0.8.0")
    du.apply_fixes({"stale-install-metadata": [rec]}, assume_yes=True)
    assert no_subprocess.actions == []


def test_reinstall_refuses_when_pypi_project_is_not_ours(no_subprocess, quiet):
    rec = _record("o/p", "Org/proj", primary=r"C:\a\p", checkouts=[],
                  installed={"name": "proj", "version": "0.1",
                             "path": r"C:\a\p"},
                  declared_dist="proj", source_version="0.2",
                  pypi_owned=False)
    du.apply_fixes({"stale-install-metadata": [rec]}, assume_yes=True)
    assert no_subprocess.actions == []


# -- the confirm gate -----------------------------------------------------

def _one_action():
    ck = _ck(r"C:\a\ok", "main", "origin/main")
    return {"behind-upstream": [
        _record("o/ok", "Org/ok", primary=r"C:\a\ok", checkouts=[ck],
                git=ck["git"])]}


@pytest.mark.parametrize("answer,should_act", [
    ("y", True), ("yes", True),
    ("n", False), ("no", False),
    ("", False),          # bare Enter is the safe answer
])
def test_confirm_answers(monkeypatch, no_subprocess, quiet, answer, should_act):
    monkeypatch.setattr("builtins.input", lambda *_: answer)
    du.apply_fixes(_one_action(), interactive=True, assume_yes=False)
    assert bool(no_subprocess.actions) is should_act


def test_eof_stops_without_acting(monkeypatch, no_subprocess, quiet):
    """A piped/redirected stdin must never be read as consent."""
    def boom(*_):
        raise EOFError
    monkeypatch.setattr("builtins.input", boom)
    du.apply_fixes(_one_action(), interactive=True, assume_yes=False)
    assert no_subprocess.actions == []


def test_ctrl_c_stops_without_acting(monkeypatch, no_subprocess, quiet):
    def boom(*_):
        raise KeyboardInterrupt
    monkeypatch.setattr("builtins.input", boom)
    du.apply_fixes(_one_action(), interactive=True, assume_yes=False)
    assert no_subprocess.actions == []


def test_quit_stops_remaining_actions(monkeypatch, no_subprocess, quiet):
    cks = [_ck(rf"C:\a\r{i}", "main", "origin/main") for i in range(3)]
    findings = {"behind-upstream": [
        _record(f"o/r{i}", f"Org/r{i}", primary=c["path"], checkouts=[c],
                git=c["git"]) for i, c in enumerate(cks)]}
    monkeypatch.setattr("builtins.input", lambda *_: "q")
    du.apply_fixes(findings, interactive=True, assume_yes=False)
    assert no_subprocess.actions == []


def test_all_applies_the_rest_without_asking(monkeypatch, no_subprocess, quiet):
    cks = [_ck(rf"C:\a\r{i}", "main", "origin/main") for i in range(3)]
    findings = {"behind-upstream": [
        _record(f"o/r{i}", f"Org/r{i}", primary=c["path"], checkouts=[c],
                git=c["git"]) for i, c in enumerate(cks)]}
    asked = {"n": 0}

    def once(*_):
        asked["n"] += 1
        return "a"
    monkeypatch.setattr("builtins.input", once)
    du.apply_fixes(findings, interactive=True, assume_yes=False)
    assert len(no_subprocess.actions) == 3
    assert asked["n"] == 1, "asked again after 'all'"


def test_help_reprompts_without_acting(monkeypatch, no_subprocess, quiet):
    answers = iter(["?", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    du.apply_fixes(_one_action(), interactive=True, assume_yes=False)
    assert no_subprocess.actions == []


def test_unrecognized_answer_reprompts(monkeypatch, no_subprocess, quiet):
    answers = iter(["banana", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    du.apply_fixes(_one_action(), interactive=True, assume_yes=False)
    assert no_subprocess.actions == []


def test_dry_run_never_executes_regardless_of_answers(monkeypatch,
                                                      no_subprocess, quiet):
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    du.apply_fixes(_one_action(), dry_run=True, interactive=True)
    assert no_subprocess.actions == []
