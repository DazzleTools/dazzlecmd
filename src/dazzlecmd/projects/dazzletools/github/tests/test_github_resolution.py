"""
Tests for dz github repo resolution.

Covers how the tool decides *which* GitHub project a command refers to:

  - the upward walk (scan_ancestors_for_repo) that handles a nested
    remote-less repo, i.e. the `private/` convention, including the
    `.git`-as-a-file case produced by worktrees
  - the downward scan (scan_subdirs_for_repo) it mirrors
  - the target classification that keeps a bare issue number from being
    read as a repo name to search for

Fixtures build real git repos on disk rather than mocking git, because
the behavior under test is precisely how git reports repo boundaries.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Locate the tool module without polluting sys.path globally.
_TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL_DIR))
import github as ghtool  # noqa: E402
sys.path.pop(0)


FAKE_URL = "https://github.com/Fake-Org/fake-project.git"
FAKE_SLUG = "Fake-Org/fake-project"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_from_ambient_repos(tmp_path, monkeypatch):
    """Stop git's upward search at tmp_path.

    Temp directories are not guaranteed to sit outside a repo -- on this
    box %TEMP% lives under a home directory that is itself a git repo, so
    without a ceiling every "not in a repo" fixture would silently be
    inside one and the tests would assert the wrong thing.
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES",
                       str(tmp_path).replace("\\", "/"))


def _git(*args, cwd):
    """Run git with identity and signing forced off.

    Signing is disabled explicitly: `commit.gpgsign` / `tag.gpgsign` are
    commonly true in a user's global config, and a test that inherits that
    blocks on a GPG pinentry dialog waiting for a human. Tests must never
    reach for the user's key.
    """
    return subprocess.run(
        ["git",
         "-c", "user.email=t@example.com", "-c", "user.name=T",
         "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
         *args],
        cwd=str(cwd), capture_output=True, text=True,
    )


def _init_repo(path, origin=None):
    """Create a git repo at path, optionally with an origin remote."""
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", cwd=path)
    if origin:
        _git("remote", "add", "origin", origin, cwd=path)
    return path


def _commit(path, name="seed.txt"):
    """Make one commit so the repo has a HEAD (needed for worktrees)."""
    (path / name).write_text("seed\n", encoding="utf-8")
    _git("add", name, cwd=path)
    _git("commit", "-qm", "seed", cwd=path)


@pytest.fixture
def nested(tmp_path):
    """The reported shape: a remote-less `private/` repo inside a project.

        outer/                 repo, origin -> Fake-Org/fake-project
          private/             repo, NO remotes
            claude/issues/     where issue drafts get written
    """
    outer = _init_repo(tmp_path / "outer", origin=FAKE_URL)
    inner = _init_repo(outer / "private")           # deliberately no remote
    deep = inner / "claude" / "issues"
    deep.mkdir(parents=True)
    return {"outer": outer, "inner": inner, "deep": deep}


# ---------------------------------------------------------------------------
# scan_ancestors_for_repo -- the upward walk
# ---------------------------------------------------------------------------

def test_finds_parent_project_from_inside_remoteless_repo(nested):
    slug, root = ghtool.scan_ancestors_for_repo(start=str(nested["deep"]))
    assert slug == FAKE_SLUG
    assert Path(root) == nested["outer"]


def test_finds_parent_from_the_remoteless_repo_root_itself(nested):
    """The walk starts at the enclosing repo, not merely at cwd."""
    slug, _ = ghtool.scan_ancestors_for_repo(start=str(nested["inner"]))
    assert slug == FAKE_SLUG


def test_no_qualifying_ancestor_returns_none(tmp_path):
    """A remote-less repo with no GitHub ancestor is not an error."""
    orphan = _init_repo(tmp_path / "orphan")
    deep = orphan / "a" / "b"
    deep.mkdir(parents=True)

    slug, root = ghtool.scan_ancestors_for_repo(start=str(deep))
    assert slug is None
    assert root is None


def test_outside_any_repo_returns_none(tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    assert ghtool.scan_ancestors_for_repo(start=str(plain)) == (None, None)


def test_skips_remoteless_levels_to_reach_the_project(tmp_path):
    """Two nested remote-less repos: the walk keeps going, not just one hop."""
    outer = _init_repo(tmp_path / "outer", origin=FAKE_URL)
    mid = _init_repo(outer / "mid")
    inner = _init_repo(mid / "inner")

    slug, root = ghtool.scan_ancestors_for_repo(start=str(inner))
    assert slug == FAKE_SLUG
    assert Path(root) == outer


def test_nearest_qualifying_ancestor_wins(tmp_path):
    """With two GitHub-remote ancestors, the closer one is chosen."""
    far = _init_repo(tmp_path / "far", origin="https://github.com/Far/far.git")
    near = _init_repo(far / "near", origin=FAKE_URL)
    inner = _init_repo(near / "private")

    slug, root = ghtool.scan_ancestors_for_repo(start=str(inner))
    assert slug == FAKE_SLUG
    assert Path(root) == near


def test_max_levels_bounds_the_walk(tmp_path):
    """The walk is bounded; an out-of-range project is not reached."""
    outer = _init_repo(tmp_path / "outer", origin=FAKE_URL)
    a = _init_repo(outer / "a")
    b = _init_repo(a / "b")

    assert ghtool.scan_ancestors_for_repo(start=str(b), max_levels=1) == \
        (None, None)
    assert ghtool.scan_ancestors_for_repo(start=str(b), max_levels=5)[0] == \
        FAKE_SLUG


def test_honors_explicit_remote_name(tmp_path):
    """--remote <name> is respected at each level, not silently 'origin'."""
    outer = _init_repo(tmp_path / "outer")
    _git("remote", "add", "upstream", FAKE_URL, cwd=outer)
    inner = _init_repo(outer / "private")

    assert ghtool.scan_ancestors_for_repo(start=str(inner))[0] is None
    assert ghtool.scan_ancestors_for_repo(
        start=str(inner), remote="upstream")[0] == FAKE_SLUG


def test_ancestor_with_git_as_a_file_is_detected(tmp_path):
    """A worktree's .git is a FILE, not a directory.

    Naive `isdir('.git')` marker detection misses this; delegating the
    upward search to git itself does not.
    """
    outer = _init_repo(tmp_path / "outer", origin=FAKE_URL)
    _commit(outer)
    wt = tmp_path / "wt"
    res = _git("worktree", "add", "-q", str(wt), cwd=outer)
    if res.returncode != 0:
        pytest.skip(f"git worktree unavailable: {res.stderr.strip()}")

    assert (wt / ".git").is_file(), "expected .git to be a file in a worktree"

    inner = _init_repo(wt / "private")
    slug, root = ghtool.scan_ancestors_for_repo(start=str(inner))
    assert slug == FAKE_SLUG
    assert Path(root) == wt


# ---------------------------------------------------------------------------
# Target classification -- a bare number is an issue, not a repo name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target", ["61", "1", "0", "12345"])
def test_digits_are_never_repo_names(target):
    assert ghtool._looks_like_repo_name(target) is False


@pytest.mark.parametrize("target", ["issues", "pr", "release", "wiki", "ci"])
def test_page_commands_are_not_repo_names(target):
    assert ghtool._looks_like_repo_name(target) is False


@pytest.mark.parametrize("target", [None, "", "isu", "."])
def test_commands_and_empty_are_not_repo_names(target):
    assert ghtool._looks_like_repo_name(target) is False


@pytest.mark.parametrize("target", ["preserve", "git-repokit", "b612", "cs61a"])
def test_bare_words_remain_repo_names(target):
    """The implicit repo finder must keep working, including alphanumerics."""
    assert ghtool._looks_like_repo_name(target) is True


# ---------------------------------------------------------------------------
# main() dispatch -- resolution end to end, with gh stubbed out
# ---------------------------------------------------------------------------

@pytest.fixture
def calls(monkeypatch):
    """Capture what main() ultimately asks gh to browse."""
    seen = []

    def fake_browse(slug, *extra, no_browser=False):
        seen.append((slug, extra))
        return 0

    monkeypatch.setattr(ghtool, "check_gh", lambda: True)
    monkeypatch.setattr(ghtool, "gh_browse", fake_browse)
    return seen


def test_main_opens_issue_in_parent_project(nested, calls, monkeypatch):
    """The reported bug: `dz github 61` from inside private/."""
    monkeypatch.chdir(nested["deep"])
    rc = ghtool.main(["-n", "61"])
    assert rc == 0
    assert calls == [(FAKE_SLUG, ("61",))]


def test_main_opens_parent_home_with_no_target(nested, calls, monkeypatch):
    monkeypatch.chdir(nested["deep"])
    assert ghtool.main(["-n"]) == 0
    assert calls == [(FAKE_SLUG, ())]


def test_main_announces_ancestor_resolution(nested, calls, monkeypatch, capsys):
    monkeypatch.chdir(nested["deep"])
    ghtool.main(["-n", "61"])
    err = capsys.readouterr().err
    assert "Resolved via parent repo" in err
    assert FAKE_SLUG in err


def test_main_does_not_announce_when_repo_resolves_locally(nested, calls,
                                                           monkeypatch,
                                                           capsys):
    """Standing in the project itself, nothing was 'resolved via' anywhere."""
    monkeypatch.chdir(nested["outer"])
    ghtool.main(["-n", "61"])
    assert "Resolved via parent repo" not in capsys.readouterr().err


def test_main_never_repo_searches_a_bare_number(nested, calls, monkeypatch):
    """The failure mode from the report: '61' becoming a repo search."""
    searched = []
    monkeypatch.setattr(
        ghtool, "cmd_repo",
        lambda name, nb, force_refresh=False: searched.append(name) or 0)
    monkeypatch.chdir(nested["deep"])
    ghtool.main(["-n", "61"])
    assert searched == [], f"issue number leaked into a repo search: {searched}"


def test_main_explicit_repo_subcommand_still_works(nested, calls, monkeypatch):
    """`dz github repo <name>` is the unambiguous form and works anywhere."""
    searched = []
    monkeypatch.setattr(
        ghtool, "cmd_repo",
        lambda name, nb, force_refresh=False: searched.append(name) or 0)
    monkeypatch.chdir(nested["deep"])
    assert ghtool.main(["-n", "repo", "preserve"]) == 0
    assert searched == ["preserve"]


def test_main_bare_word_means_the_same_thing_as_at_the_project_root(
        nested, calls, monkeypatch):
    """A word must not change meaning one directory down.

    At a project root `dz github roadmap` searches that project's issues.
    From inside its remote-less private/ store it used to run a GitHub-wide
    search for repositories named "roadmap" -- the reported bug's failure
    mode, reached by a different input class than the digit case.
    """
    searched, issues = [], []
    monkeypatch.setattr(
        ghtool, "cmd_repo",
        lambda name, nb, force_refresh=False: searched.append(name) or 0)
    monkeypatch.setattr(
        ghtool, "cmd_isu",
        lambda slug, target, nb: issues.append((slug, target)) or 0)

    monkeypatch.chdir(nested["deep"])
    assert ghtool.main(["-n", "roadmap"]) == 0

    assert searched == [], f"word leaked into a repo search: {searched}"
    assert issues == [(FAKE_SLUG, "roadmap")]


def test_main_bare_word_is_a_repo_name_when_nothing_encloses_us(
        tmp_path, calls, monkeypatch):
    """With no parent project there is nothing for a word to refer to.

    The implicit repo finder must survive outside a project -- it is only
    displaced where a resolved project gives the word a better meaning.
    """
    searched = []
    monkeypatch.setattr(
        ghtool, "cmd_repo",
        lambda name, nb, force_refresh=False: searched.append(name) or 0)
    orphan = _init_repo(tmp_path / "orphan")   # a repo, but no GitHub ancestor
    monkeypatch.chdir(orphan)

    assert ghtool.main(["-n", "preserve"]) == 0
    assert searched == ["preserve"]


def test_main_degrades_gracefully_with_no_ancestor(tmp_path, calls,
                                                   monkeypatch, capsys):
    orphan = _init_repo(tmp_path / "orphan")
    deep = orphan / "a"
    deep.mkdir()
    monkeypatch.chdir(deep)

    assert ghtool.main(["-n", "61"]) == 1
    assert calls == []
    assert "no enclosing repo has one either" in capsys.readouterr().err


def test_main_downward_scan_still_works(tmp_path, calls, monkeypatch):
    """The mirror path must not regress: cwd is not a repo, child is."""
    parent = tmp_path / "workspace"
    parent.mkdir()
    _init_repo(parent / "project", origin=FAKE_URL)
    monkeypatch.chdir(parent)

    assert ghtool.main(["-n"]) == 0
    assert calls == [(FAKE_SLUG, ())]


# ---------------------------------------------------------------------------
# Cross-repo issue references -- '<repo>#<issue>'
# ---------------------------------------------------------------------------

FAKE_CACHE = [
    {"name": "dazzlecmd", "fullName": "DazzleTools/dazzlecmd",
     "url": "https://github.com/DazzleTools/dazzlecmd", "description": ""},
    {"name": "dazzlecmd-extras", "fullName": "DazzleTools/dazzlecmd-extras",
     "url": "https://github.com/DazzleTools/dazzlecmd-extras",
     "description": ""},
    {"name": "dazzle-lib", "fullName": "DazzleLib/dazzle-lib",
     "url": "https://github.com/DazzleLib/dazzle-lib", "description": ""},
]


@pytest.fixture
def org_cache(monkeypatch):
    """A fresh repo cache, with every network path armed to explode.

    Resolution for an issue jump must be answerable from the cache alone:
    no gh subprocess (AC-9), no cache refresh, and above all no global
    GitHub search (AC-7) -- a typo'd name resolving to a stranger's repo
    would open THEIR issue N, which looks exactly like a real answer.
    """
    monkeypatch.setattr(ghtool, "_load_cache", lambda: (FAKE_CACHE, True))
    monkeypatch.setattr(ghtool, "gh", _boom("gh must not run on a cache hit"))
    monkeypatch.setattr(ghtool, "_fetch_all_repos",
                        _boom("cache refresh not expected"))
    monkeypatch.setattr(ghtool, "_global_search_fallback",
                        _boom("global search is forbidden for issue refs"))


def _boom(msg):
    def _raise(*a, **k):
        raise AssertionError(msg)
    return _raise


# -- the parse --

@pytest.mark.parametrize("target,expected", [
    ("dazzlecmd#112", ("dazzlecmd", "112")),
    ("OWNER/REPO#7", ("OWNER/REPO", "7")),
    ("#112", ("", "112")),
    ("dazzlecmd#", ("dazzlecmd", "")),
    ("#", ("", "")),
    ("a#b#c", ("a", "b#c")),          # split on the FIRST '#'
    ("dazzlecmd#roadmap", ("dazzlecmd", "roadmap")),
])
def test_split_issue_ref(target, expected):
    assert ghtool._split_issue_ref(target) == expected


@pytest.mark.parametrize("target", [None, "", "dazzlecmd", "112", "isu", "."])
def test_split_issue_ref_none_without_hash(target):
    assert ghtool._split_issue_ref(target) is None


def test_hash_targets_are_never_repo_names():
    """GitHub forbids '#' in repository names; the classifier must too."""
    assert ghtool._looks_like_repo_name("dazzlecmd#112") is False
    assert ghtool._looks_like_repo_name("#112") is False


# -- the resolver --

def test_resolver_exact_match_wins_over_substrings(org_cache):
    """'dazzlecmd' is a substring of two entries and an exact match of one."""
    assert ghtool.resolve_repo_name("dazzlecmd") == "DazzleTools/dazzlecmd"


def test_resolver_owner_repo_passes_through_untouched(monkeypatch):
    """OWNER/REPO needs no cache at all (AC-2)."""
    monkeypatch.setattr(ghtool, "_load_cache",
                        _boom("cache must not be consulted"))
    assert ghtool.resolve_repo_name("Some-Org/some-repo") == \
        "Some-Org/some-repo"


def test_resolver_miss_returns_none_without_global_search(org_cache, capsys):
    assert ghtool.resolve_repo_name("zzznosuchrepo") is None
    assert "zzznosuchrepo" in capsys.readouterr().err


def test_resolver_ambiguity_prompt_cancels_cleanly(org_cache, capsys):
    """'dazzle' matches substrings with no exact hit -> prompt; a closed
    stdin (this test process) cancels rather than crashing or guessing."""
    assert ghtool.resolve_repo_name("dazzle") is None
    err = capsys.readouterr().err
    assert "dazzle" in err and "Cancelled" in err


# -- main() dispatch --

def test_main_issue_ref_needs_no_cwd(tmp_path, calls, monkeypatch, org_cache):
    """The headline case: proj#N from a directory that is not a repo."""
    plain = tmp_path / "nowhere"
    plain.mkdir()
    monkeypatch.chdir(plain)

    assert ghtool.main(["-n", "dazzlecmd#112"]) == 0
    assert calls == [("DazzleTools/dazzlecmd", ("112",))]


def test_main_issue_ref_keyword_reaches_the_other_repo(tmp_path, calls,
                                                       monkeypatch, org_cache):
    """proj#roadmap -> semantic lookup against the RESOLVED repo, not cwd."""
    looked = []
    monkeypatch.setattr(
        ghtool, "cmd_isu",
        lambda slug, target, nb: looked.append((slug, target)) or 0)
    monkeypatch.chdir(tmp_path)

    assert ghtool.main(["-n", "dazzlecmd#roadmap"]) == 0
    assert looked == [("DazzleTools/dazzlecmd", "roadmap")]


def test_main_issue_ref_empty_part_is_the_issues_tab(tmp_path, calls,
                                                     monkeypatch, org_cache):
    looked = []
    monkeypatch.setattr(
        ghtool, "cmd_isu",
        lambda slug, target, nb: looked.append((slug, target)) or 0)
    monkeypatch.chdir(tmp_path)

    assert ghtool.main(["-n", "dazzlecmd#"]) == 0
    assert looked == [("DazzleTools/dazzlecmd", None)]


def test_main_bare_ref_uses_the_current_project(nested, calls, monkeypatch):
    """'#112' inside a repo -> that repo's issue 112."""
    monkeypatch.chdir(nested["outer"])
    assert ghtool.main(["-n", "#112"]) == 0
    assert calls == [(FAKE_SLUG, ("112",))]


def test_main_bare_ref_walks_to_the_ancestor(nested, calls, monkeypatch):
    """'#112' from inside private/ -> the PARENT's issue 112, via the
    existing ancestor walk rather than a second resolution pipeline."""
    monkeypatch.chdir(nested["deep"])
    assert ghtool.main(["-n", "#112"]) == 0
    assert calls == [(FAKE_SLUG, ("112",))]


def test_main_bare_ref_word_never_becomes_a_repo_search(tmp_path, calls,
                                                        monkeypatch):
    """'#roadmap' declared itself an issue; even where a bare word would
    be read as a repo name (a non-repo dir), '#' forbids that reading."""
    searched = []
    monkeypatch.setattr(
        ghtool, "cmd_repo",
        lambda name, nb, force_refresh=False: searched.append(name) or 0)
    plain = tmp_path / "nowhere"
    plain.mkdir()
    monkeypatch.chdir(plain)

    rc = ghtool.main(["-n", "#roadmap"])
    assert searched == [], f"'#' target leaked into a repo search: {searched}"
    assert rc == 1  # nothing to resolve against out here


def test_main_unknown_repo_part_fails_with_the_escape_hatch(tmp_path, calls,
                                                            monkeypatch,
                                                            org_cache, capsys):
    monkeypatch.chdir(tmp_path)
    assert ghtool.main(["-n", "zzznosuchrepo#5"]) == 1
    assert calls == []
    assert "OWNER/REPO#5" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Mutation-audit anchors -- each test here was written to kill a specific
# surviving mutant from the v0.12.18 sweep (tests/mutation/). They exist
# because the behaviors they pin were demonstrated to be UNPINNED: the
# original suite stayed green with each of these bugs introduced.
# ---------------------------------------------------------------------------

def test_resolver_exact_match_folds_case_of_cache_names(monkeypatch):
    """Kills M1 (drop .lower() on the cache name).

    Cache names carry GitHub's display case (ComfyUI, Dazzle-Locate32);
    a lowercase query must still exact-match them. Note the trap the
    first draft of this test fell into: querying in UPPERCASE against a
    lowercase cache does NOT catch the mutant, because the QUERY is
    folded separately -- the cache entry itself must be mixed-case.
    """
    cache = [
        {"name": "MixedCase", "fullName": "Org/MixedCase",
         "url": "https://github.com/Org/MixedCase", "description": ""},
        {"name": "mixedcase-extras", "fullName": "Org/mixedcase-extras",
         "url": "https://github.com/Org/mixedcase-extras", "description": ""},
    ]
    monkeypatch.setattr(ghtool, "_load_cache", lambda: (cache, True))
    assert ghtool.resolve_repo_name("mixedcase") == "Org/MixedCase"


def test_resolver_exact_match_folds_case_of_the_query(monkeypatch):
    """Kills R1 (round 2: compare against raw `name`, not `name_lower`).

    The dual of the M1 anchor above: M1 required a mixed-case CACHE
    entry to show itself; this one requires a mixed-case QUERY. The
    fold has two sides and each mutant broke exactly one, so each
    anchor pins exactly one -- both are needed.
    """
    cache = [
        {"name": "MixedCase", "fullName": "Org/MixedCase",
         "url": "https://github.com/Org/MixedCase", "description": ""},
        {"name": "mixedcase-extras", "fullName": "Org/mixedcase-extras",
         "url": "https://github.com/Org/mixedcase-extras", "description": ""},
    ]
    monkeypatch.setattr(ghtool, "_load_cache", lambda: (cache, True))
    assert ghtool.resolve_repo_name("MIXEDCASE") == "Org/MixedCase"


def test_auto_select_uses_candidate_order_not_cache_order(monkeypatch):
    """Kills R2 (round 2: auto-select reads found[0], not candidates[0]).

    The exact match must win even when the cache happens to list a
    longer substring match FIRST -- cache order is arbitrary and must
    never leak into which repo gets auto-selected.
    """
    cache = [
        {"name": "dazzle-toolkit", "fullName": "Org/dazzle-toolkit",
         "url": "https://github.com/Org/dazzle-toolkit", "description": ""},
        {"name": "toolkit", "fullName": "Org/toolkit",
         "url": "https://github.com/Org/toolkit", "description": ""},
    ]
    monkeypatch.setattr(ghtool, "_load_cache", lambda: (cache, True))
    assert ghtool.resolve_repo_name("toolkit") == "Org/toolkit"


def test_refresh_flag_reaches_the_implicit_repo_lookup(tmp_path, calls,
                                                       monkeypatch):
    """Kills R8 (round 2: force_refresh dropped at the not-in-a-repo
    call site). `--refresh preserve` from a non-repo directory must
    thread the flag through to the repo finder, not silently answer
    from a stale cache."""
    seen = []
    monkeypatch.setattr(
        ghtool, "cmd_repo",
        lambda name, nb, force_refresh=False:
            seen.append((name, force_refresh)) or 0)
    plain = tmp_path / "nowhere"
    plain.mkdir()
    monkeypatch.chdir(plain)

    assert ghtool.main(["-n", "--refresh", "preserve"]) == 0
    assert seen == [("preserve", True)]


def test_prompt_selection_picks_the_numbered_candidate(org_cache, monkeypatch):
    """Kills M4 (off-by-one in the prompt index).

    The prompt is 1-based, the list 0-based; answering '1' must select
    the FIRST listed candidate. Nothing else in the suite ever answers
    the prompt -- every other test lets it cancel.
    """
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")
    # 'dazzle' matches all three cache entries, none exactly; the list
    # is sorted by name length, so candidate 1 is 'dazzlecmd'.
    assert ghtool.resolve_repo_name("dazzle") == "DazzleTools/dazzlecmd"


def test_resolver_refresh_actually_refreshes(monkeypatch):
    """Kills M6 (and->or on the cache/refresh gate).

    refresh=True must bypass the cache and consult the refetched list --
    otherwise `--refresh` combined with a '#' target is silently a no-op
    and keeps answering from stale data.
    """
    fetched = [{"name": "dazzlecmd", "fullName": "Fresh-Org/dazzlecmd",
                "url": "https://github.com/Fresh-Org/dazzlecmd",
                "description": ""}]
    monkeypatch.setattr(ghtool, "_load_cache", lambda: (FAKE_CACHE, True))
    monkeypatch.setattr(ghtool, "_fetch_all_repos", lambda: fetched)
    assert ghtool.resolve_repo_name("dazzlecmd", refresh=True) == \
        "Fresh-Org/dazzlecmd"


def test_bare_hash_with_refresh_still_opens_issues_tab(nested, calls,
                                                       monkeypatch):
    """Kills M12 (is None -> falsy in the refresh-only early exit).

    After a bare '#' is parsed, the target is an EMPTY STRING that means
    "this repo's issues tab" -- not "no target". `--refresh '#'` must
    refresh AND open, not swallow the request. Same falsy-after-rewrite
    bug family as the #111 word-case regression.
    """
    looked = []
    monkeypatch.setattr(
        ghtool, "cmd_isu",
        lambda slug, target, nb: looked.append((slug, target)) or 0)
    monkeypatch.setattr(ghtool, "_fetch_all_repos", lambda: [])
    monkeypatch.chdir(nested["outer"])

    assert ghtool.main(["-n", "--refresh", "#"]) == 0
    assert looked == [(FAKE_SLUG, None)]


# ---------------------------------------------------------------------------
# Real CLI invocation -- no mocks in the path
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_real_cli_resolves_parent_project(nested):
    """End-to-end through a real subprocess, per the unit+CLI doctrine.

    Asserts on the resolution announcement rather than the final URL so the
    test stays hermetic -- reaching GitHub is gh's job, not this tool's.
    """
    script = _TOOL_DIR / "github.py"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run(
        [sys.executable, str(script), "-n", "61"],
        cwd=str(nested["deep"]), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=120,
    )
    combined = res.stdout + res.stderr
    if "not installed" in combined or "cli.github.com" in combined:
        pytest.skip("gh CLI unavailable")
    assert FAKE_SLUG in combined, combined


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_real_cli_issue_ref_owner_repo_form(tmp_path):
    """OWNER/REPO#N end to end -- no cache, no cwd, real subprocess.

    Uses a real public repo so gh can build the URL; skips when gh or
    the network is unavailable rather than failing on environment.
    """
    script = _TOOL_DIR / "github.py"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run(
        [sys.executable, str(script), "-n", "DazzleTools/dazzlecmd#112"],
        cwd=str(tmp_path), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=120,
    )
    combined = res.stdout + res.stderr
    if "not installed" in combined or "cli.github.com" in combined:
        pytest.skip("gh CLI unavailable")
    if res.returncode != 0:
        pytest.skip(f"gh/network unavailable: {combined.strip()[:120]}")
    assert "DazzleTools/dazzlecmd/issues/112" in res.stdout, combined
