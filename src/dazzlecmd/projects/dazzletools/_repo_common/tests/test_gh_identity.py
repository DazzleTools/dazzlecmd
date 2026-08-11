"""Unit tests for _repo_common.gh_identity.

gh is injected as a fake runner throughout: these tests must not depend
on network access, on the developer's gh auth state, or on GitHub's
current view of any repo. The three redirect cases asserted below are
the real ones observed on PLZWORK on 2026-07-26.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_MODULE_DIR = _HERE.parent
sys.path.insert(0, str(_MODULE_DIR.parent))  # projects/dazzletools/

from _repo_common.gh_identity import (  # noqa: E402
    IdentityResolver,
    gh_status,
    load_cache,
    parse_slug,
    save_cache,
)


# -- fake gh runners --

def _ok(payload):
    """A runner that returns payload for any repos/ query."""
    def runner(args, timeout=30):
        if args[:1] == ["auth"]:
            return (0, "Logged in", "")
        return (0, json.dumps(payload), "")
    return runner


def _mapping(table):
    """A runner resolving repos/<slug> via a slug -> (full_name, id) table."""
    def runner(args, timeout=30):
        if args[:1] == ["auth"]:
            return (0, "Logged in", "")
        slug = args[1].split("repos/", 1)[1]
        if slug not in table:
            return (1, "", "gh: Not Found (HTTP 404)")
        full, rid = table[slug]
        return (0, json.dumps({"full_name": full, "id": rid}), "")
    return runner


def _fails(rc, err):
    def runner(args, timeout=30):
        return (rc, "", err)
    return runner


# -- parse_slug --

@pytest.mark.parametrize("url,expected", [
    ("https://github.com/DazzleTools/dazzlecmd.git", "DazzleTools/dazzlecmd"),
    ("https://github.com/DazzleTools/dazzlecmd", "DazzleTools/dazzlecmd"),
    ("git@github.com:DazzleLib/dazzle-lib.git", "DazzleLib/dazzle-lib"),
    ("git@github.com:DazzleLib/dazzle-lib", "DazzleLib/dazzle-lib"),
    ("ssh://git@github.com/djdarcy/DPAPIck3.git", "djdarcy/DPAPIck3"),
    ("https://github.com/DazzleTools/dazzlecmd/", "DazzleTools/dazzlecmd"),
])
def test_parse_slug_handles_url_forms(url, expected):
    assert parse_slug(url) == expected


@pytest.mark.parametrize("url", [
    "", None, "https://gitlab.com/someone/thing.git",
    "/c/code/local-only", "not a url",
])
def test_parse_slug_returns_none_for_non_github(url):
    assert parse_slug(url) is None


# -- redirect detection: the bug this module exists to prevent --

def test_detects_the_three_real_redirects():
    """Regression test for the observed transfer-redirect cases.

    Each of these was cloned locally under a pre-transfer URL and was
    wrongly reported as 'not cloned' by URL-string matching.
    """
    table = {
        "djdarcy/dazzlesum": ("DazzleTools/dazzlesum", 1009633247),
        "djdarcy/dazzle-tree-lib": ("DazzleLib/dazzle-tree-lib", 111),
        "djdarcy/process-delta": ("DazzleTools/process-delta", 222),
    }
    r = IdentityResolver(runner=_mapping(table))
    for stale, (canonical, rid) in table.items():
        info = r.resolve(stale)
        assert info["redirected"] is True, stale
        assert info["full_name"] == canonical
        assert info["repo_id"] == rid
        assert info["error"] is None


def test_canonical_key_unifies_stale_and_current_urls():
    """The property that makes the org-vs-local diff correct."""
    table = {
        "djdarcy/dazzlesum": ("DazzleTools/dazzlesum", 1009633247),
        "DazzleTools/dazzlesum": ("DazzleTools/dazzlesum", 1009633247),
    }
    r = IdentityResolver(runner=_mapping(table))
    assert r.canonical_key("djdarcy/dazzlesum") == \
        r.canonical_key("DazzleTools/dazzlesum")


def test_non_redirected_repo_is_not_flagged():
    r = IdentityResolver(runner=_mapping(
        {"DazzleTools/dazzlecmd": ("DazzleTools/dazzlecmd", 1)}))
    info = r.resolve("DazzleTools/dazzlecmd")
    assert info["redirected"] is False
    assert info["full_name"] == "DazzleTools/dazzlecmd"


def test_case_difference_alone_is_not_a_redirect():
    """GitHub slugs are case-insensitive; casing must not raise a finding."""
    r = IdentityResolver(runner=_mapping(
        {"dazzletools/DazzleCmd": ("DazzleTools/dazzlecmd", 1)}))
    assert r.resolve("dazzletools/DazzleCmd")["redirected"] is False


# -- caching --

def test_repeated_slugs_cost_one_call():
    calls = []

    def counting(args, timeout=30):
        calls.append(args)
        return (0, json.dumps({"full_name": "O/R", "id": 5}), "")

    r = IdentityResolver(runner=counting)
    for _ in range(5):
        r.resolve("O/R")
    assert len(calls) == 1


def test_cache_roundtrips_to_disk(tmp_path):
    r = IdentityResolver(runner=_ok({"full_name": "O/R", "id": 7}))
    r.resolve("O/R")
    path = tmp_path / "nested" / "cache.json"
    assert save_cache(str(path), r.cache) is True
    assert load_cache(str(path))["O/R"]["full_name"] == "O/R"


def test_load_cache_tolerates_missing_or_corrupt(tmp_path):
    assert load_cache(str(tmp_path / "absent.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_cache(str(bad)) == {}


def test_preseeded_cache_avoids_any_call():
    def explode(args, timeout=30):
        raise AssertionError("resolver must not call gh when cached")

    seeded = {"O/R": {"slug": "O/R", "full_name": "O/R", "repo_id": 1,
                      "redirected": False, "error": None}}
    r = IdentityResolver(runner=explode, cache=seeded)
    assert r.resolve("O/R")["full_name"] == "O/R"


# -- degradation: must report, never guess --

def test_missing_gh_is_reported_not_swallowed():
    r = IdentityResolver(runner=_fails(127, "gh not found on PATH"))
    info = r.resolve("O/R")
    assert info["full_name"] is None
    assert "not found" in info["error"]
    assert info["redirected"] is False


def test_unresolvable_slug_falls_back_to_slug_key_not_a_wrong_answer():
    """Offline, grouping still works -- but no redirect is ever claimed."""
    r = IdentityResolver(runner=_fails(1, "gh: Not Found (HTTP 404)"))
    info = r.resolve("Owner/Gone")
    assert info["full_name"] is None
    assert info["redirected"] is False
    assert r.canonical_key("Owner/Gone") == "owner/gone"


def test_timeout_is_reported():
    r = IdentityResolver(runner=_fails(124, "gh timed out after 30s"))
    assert "timed out" in r.resolve("O/R")["error"]


def test_gh_status_flags_unauthenticated_as_unavailable():
    """Unauthenticated gh hides private repos -- a false negative, so it
    must not be treated as a working inventory source."""
    available, detail = gh_status(runner=_fails(1, "You are not logged in"))
    assert available is False
    assert "not authenticated" in detail


def test_gh_status_flags_missing_binary():
    available, detail = gh_status(runner=_fails(127, "gh not found on PATH"))
    assert available is False
    assert "not found" in detail


def test_gh_status_reports_healthy():
    available, detail = gh_status(runner=_ok({}))
    assert available is True
    assert "authenticated" in detail


def test_empty_slug_is_handled():
    r = IdentityResolver(runner=_ok({}))
    info = r.resolve("")
    assert info["full_name"] is None
    assert info["error"] == "empty slug"


# -- is_repo_slug (bare-slug shape; added for dazzlecmd#120) --

from _repo_common.gh_identity import is_repo_slug  # noqa: E402


@pytest.mark.parametrize("good", [
    "owner/repo", "DazzleTools/dazzlecmd", "a/b",
    "owner/repo.with.dots", "owner/repo-with-dashes",
])
def test_is_repo_slug_accepts_two_segments(good):
    assert is_repo_slug(good) is True


@pytest.mark.parametrize("bad", [
    None, "", "owner", "owner/repo/extra", "a/", "/b", "/",
    "a b/c", "a/b c", "a\tb/c",
    "https://github.com/owner/repo",   # a URL is parse_slug's job
])
def test_is_repo_slug_rejects_everything_else(bad):
    assert is_repo_slug(bad) is False


def test_parse_slug_and_is_repo_slug_divide_the_labor():
    """A bare slug is not a URL and a URL is not a bare slug -- each
    function owns exactly one side (the dazzlecmd#120 fix sketch
    originally confused them)."""
    assert parse_slug("owner/repo") is None
    assert is_repo_slug("owner/repo") is True
    assert parse_slug("https://github.com/owner/repo.git") == "owner/repo"
    assert is_repo_slug("https://github.com/owner/repo.git") is False
