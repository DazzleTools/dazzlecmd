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


class FakeRunner:
    """Records commands instead of running them."""

    def __init__(self, rc=0):
        self.calls = []
        self.rc = rc

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        return _Result(self.rc)

    @property
    def targets(self):
        """The path each recorded command acted on."""
        out = []
        for c in self.calls:
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
    assert no_subprocess.calls == []


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
    ({"branch": "main", "upstream": "origin/main", "behind": 1, "ahead": 0,
      "dirty_count": 3, "untracked_count": 0}, "dirty"),
    ({"branch": "main", "upstream": "origin/main", "behind": 1, "ahead": 2,
      "dirty_count": 0, "untracked_count": 0}, "diverged"),
])
def test_pull_refuses_unsafe_states(no_subprocess, quiet, git, reason):
    ck = {"path": r"C:\a\p", "excluded": False, "git": git}
    rec = _record("o/p", "Org/proj", primary=r"C:\a\p", checkouts=[ck], git=git)
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert no_subprocess.calls == [], f"pulled despite: {reason}"


def test_pull_refuses_foreign_upstreams(no_subprocess, quiet):
    """ostris/ai-toolkit at 510 behind is tracked, not maintained here."""
    ck = _ck(r"C:\a\ai", "main", "origin/main")
    rec = _record("ostris/ai-toolkit", "ostris/ai-toolkit",
                  primary=r"C:\a\ai", checkouts=[ck], git=ck["git"],
                  foreign=True)
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert no_subprocess.calls == []


def test_clean_tracking_repo_is_pulled(no_subprocess, quiet):
    """The counterpart -- refusing everything must not pass the suite."""
    ck = _ck(r"C:\a\ok", "main", "origin/main")
    rec = _record("o/ok", "Org/ok", primary=r"C:\a\ok", checkouts=[ck],
                  git=ck["git"])
    du.apply_fixes({"behind-upstream": [rec]}, assume_yes=True)
    assert no_subprocess.targets == [r"C:\a\ok"]
    assert "--ff-only" in no_subprocess.calls[0]


# -- #106: never reinstall across a name mismatch -------------------------

def test_reinstall_refuses_across_a_dist_rename(no_subprocess, quiet):
    rec = _record("dazzletools/preserve", "DazzleTools/preserve",
                  primary=r"C:\code\preserve", checkouts=[],
                  installed={"name": "preserve", "version": "0.5.2",
                             "path": r"C:\code\preserve"},
                  declared_dist="dazzle-preserve", source_version="0.8.0")
    du.apply_fixes({"stale-install-metadata": [rec]}, assume_yes=True)
    assert no_subprocess.calls == []


def test_reinstall_refuses_when_pypi_project_is_not_ours(no_subprocess, quiet):
    rec = _record("o/p", "Org/proj", primary=r"C:\a\p", checkouts=[],
                  installed={"name": "proj", "version": "0.1",
                             "path": r"C:\a\p"},
                  declared_dist="proj", source_version="0.2",
                  pypi_owned=False)
    du.apply_fixes({"stale-install-metadata": [rec]}, assume_yes=True)
    assert no_subprocess.calls == []


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
    assert bool(no_subprocess.calls) is should_act


def test_eof_stops_without_acting(monkeypatch, no_subprocess, quiet):
    """A piped/redirected stdin must never be read as consent."""
    def boom(*_):
        raise EOFError
    monkeypatch.setattr("builtins.input", boom)
    du.apply_fixes(_one_action(), interactive=True, assume_yes=False)
    assert no_subprocess.calls == []


def test_ctrl_c_stops_without_acting(monkeypatch, no_subprocess, quiet):
    def boom(*_):
        raise KeyboardInterrupt
    monkeypatch.setattr("builtins.input", boom)
    du.apply_fixes(_one_action(), interactive=True, assume_yes=False)
    assert no_subprocess.calls == []


def test_quit_stops_remaining_actions(monkeypatch, no_subprocess, quiet):
    cks = [_ck(rf"C:\a\r{i}", "main", "origin/main") for i in range(3)]
    findings = {"behind-upstream": [
        _record(f"o/r{i}", f"Org/r{i}", primary=c["path"], checkouts=[c],
                git=c["git"]) for i, c in enumerate(cks)]}
    monkeypatch.setattr("builtins.input", lambda *_: "q")
    du.apply_fixes(findings, interactive=True, assume_yes=False)
    assert no_subprocess.calls == []


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
    assert len(no_subprocess.calls) == 3
    assert asked["n"] == 1, "asked again after 'all'"


def test_help_reprompts_without_acting(monkeypatch, no_subprocess, quiet):
    answers = iter(["?", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    du.apply_fixes(_one_action(), interactive=True, assume_yes=False)
    assert no_subprocess.calls == []


def test_unrecognized_answer_reprompts(monkeypatch, no_subprocess, quiet):
    answers = iter(["banana", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    du.apply_fixes(_one_action(), interactive=True, assume_yes=False)
    assert no_subprocess.calls == []


def test_dry_run_never_executes_regardless_of_answers(monkeypatch,
                                                      no_subprocess, quiet):
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    du.apply_fixes(_one_action(), dry_run=True, interactive=True)
    assert no_subprocess.calls == []
