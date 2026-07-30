"""Unit tests for _repo_common.discovery.

Network and environment are injected throughout: gh, PyPI, and the
installed-distribution set are all fakes. The filesystem source is
exercised against real throwaway repos, because its correctness depends
on git's actual path-resolution behavior and a mock would assume away
the very bug it must prevent.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_MODULE_DIR = _HERE.parent
sys.path.insert(0, str(_MODULE_DIR.parent))  # projects/dazzletools/

from _repo_common.discovery import (  # noqa: E402
    _url_to_path,
    editable_installs,
    find_git_repos,
    list_org_repos,
    pypi_version,
)


# -- helpers --

def _run(cwd, *args):
    res = subprocess.run(
        ["git"] + list(args), cwd=str(cwd), capture_output=True,
        text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{res.stderr}")
    return res.stdout


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _run(path, "init", "-b", "main")
    _run(path, "config", "user.email", "t@example.invalid")
    _run(path, "config", "user.name", "T")
    _run(path, "config", "commit.gpgsign", "false")
    (path / "f.txt").write_text("x\n", encoding="utf-8")
    _run(path, "add", "f.txt")
    _run(path, "commit", "-m", "init")
    return path


class _FakeDist:
    """Minimal stand-in for importlib.metadata.Distribution."""

    def __init__(self, name, version, url=None, editable=False, raw=None):
        self.metadata = {"Name": name}
        self.version = version
        if raw is not None:
            self._raw = raw
        elif url is None:
            self._raw = None
        else:
            self._raw = json.dumps(
                {"url": url, "dir_info": {"editable": editable}})

    def read_text(self, filename):
        return self._raw if filename == "direct_url.json" else None


# -- path conversion --

@pytest.mark.skipif(os.name != "nt", reason="Windows path form")
def test_url_to_path_strips_leading_slash_on_windows():
    assert _url_to_path("file:///C:/code/dazzle-lib") == r"C:\code\dazzle-lib"


def test_url_to_path_decodes_percent_escapes():
    got = _url_to_path("file:///tmp/with%20space")
    assert got is not None and "with space" in got


def test_url_to_path_rejects_non_file_urls():
    assert _url_to_path("https://example.invalid/x") is None
    assert _url_to_path(None) is None


# -- pip editable axis --

def test_editable_installs_selects_only_editables():
    dists = [
        _FakeDist("dazzle-filekit", "0.3.4",
                  url="file:///C:/code/filetoolkit/github", editable=True),
        _FakeDist("requests", "2.0", url=None),                       # wheel
        _FakeDist("somepkg", "1.0",
                  url="file:///C:/code/somepkg", editable=False),     # non-editable
    ]
    got = editable_installs(dists)
    assert [d["name"] for d in got] == ["dazzle-filekit"]
    assert got[0]["version"] == "0.3.4"


def test_editable_installs_resolves_which_checkout_is_wired_in():
    """The property that disambiguates several clones of one package.

    dazzlecmd has multiple worktrees plus stale full copies; only pip
    knows which directory the environment actually executes.
    """
    dists = [_FakeDist("dazzlecmd", "0.12.5a0",
                       url="file:///C:/code/dazzlecmd/github", editable=True)]
    got = editable_installs(dists)
    assert got[0]["path"].replace("\\", "/").endswith("code/dazzlecmd/github")


def test_editable_installs_tolerates_corrupt_direct_url():
    dists = [
        _FakeDist("broken", "1.0", raw="{not json"),
        _FakeDist("fine", "1.0", url="file:///tmp/fine", editable=True),
    ]
    assert [d["name"] for d in editable_installs(dists)] == ["fine"]


def test_editable_installs_deduplicates_by_name():
    dists = [
        _FakeDist("dup", "1.0", url="file:///tmp/a", editable=True),
        _FakeDist("DUP", "2.0", url="file:///tmp/b", editable=True),
    ]
    assert len(editable_installs(dists)) == 1


# -- filesystem axis --

def test_find_git_repos_finds_repo_roots(tmp_path):
    _init_repo(tmp_path / "alpha")
    _init_repo(tmp_path / "beta")
    (tmp_path / "not_a_repo").mkdir()
    found = {Path(p).name for p in find_git_repos(tmp_path)}
    assert found == {"alpha", "beta"}


def test_find_git_repos_ignores_plain_subdirectories(tmp_path):
    """The ancestor-leak guard, at the discovery layer.

    A subdirectory of a repo resolves to that repo via git's upward
    search. Without the is_repo_root gate, every such directory would be
    reported as its own repo.
    """
    repo = _init_repo(tmp_path / "solo")
    (repo / "src").mkdir()
    (repo / "src" / "deep").mkdir()
    found = find_git_repos(tmp_path)
    assert [Path(p).name for p in found] == ["solo"]


def test_find_git_repos_does_not_descend_into_a_matched_repo(tmp_path):
    outer = _init_repo(tmp_path / "outer")
    _init_repo(outer / "inner")
    found = [Path(p).name for p in find_git_repos(tmp_path)]
    assert found == ["outer"]


def test_find_git_repos_skips_noise_directories(tmp_path):
    _init_repo(tmp_path / "node_modules" / "pkg")
    _init_repo(tmp_path / "real")
    found = [Path(p).name for p in find_git_repos(tmp_path)]
    assert found == ["real"]


def test_find_git_repos_respects_max_depth(tmp_path):
    _init_repo(tmp_path / "a" / "b" / "c" / "deep")
    assert find_git_repos(tmp_path, max_depth=2) == []
    assert len(find_git_repos(tmp_path, max_depth=4)) == 1


def test_find_git_repos_handles_a_root_that_is_itself_a_repo(tmp_path):
    repo = _init_repo(tmp_path / "solo")
    found = find_git_repos(repo)
    assert [Path(p).name for p in found] == ["solo"]


def test_find_git_repos_tolerates_unreadable_root(tmp_path):
    assert find_git_repos(tmp_path / "does-not-exist") == []


# -- org listing --

def _gh(payload, rc=0, err=""):
    def runner(args, timeout=60):
        return (rc, json.dumps(payload) if rc == 0 else "", err)
    return runner


def test_list_org_repos_filters_archived_by_default():
    payload = [
        {"nameWithOwner": "O/live", "isArchived": False},
        {"nameWithOwner": "O/old", "isArchived": True},
    ]
    repos, err = list_org_repos("O", runner=_gh(payload))
    assert err is None
    assert [r["nameWithOwner"] for r in repos] == ["O/live"]


def test_list_org_repos_can_include_archived():
    payload = [{"nameWithOwner": "O/old", "isArchived": True}]
    repos, _ = list_org_repos("O", runner=_gh(payload), include_archived=True)
    assert len(repos) == 1


def test_list_org_repos_surfaces_failure_rather_than_empty():
    """An unauthenticated gh returning nothing must not read as 'no repos'."""
    repos, err = list_org_repos(
        "O", runner=_gh(None, rc=1, err="gh: Not Found (HTTP 404)"))
    assert repos == []
    assert err is not None and "O:" in err


def test_list_org_repos_reports_missing_gh():
    repos, err = list_org_repos(
        "O", runner=_gh(None, rc=127, err="gh not found on PATH"))
    assert repos == []
    assert "not found" in err


def test_list_org_repos_handles_unparseable_output():
    def runner(args, timeout=60):
        return (0, "<html>not json</html>", "")
    repos, err = list_org_repos("O", runner=runner)
    assert repos == []
    assert "unparseable" in err


# -- PyPI --

def _opener(payload=None, http_error=None, exc=None):
    class _Resp(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(url, timeout=20):
        if http_error is not None:
            raise urllib.error.HTTPError(url, http_error, "err", {}, None)
        if exc is not None:
            raise exc
        return _Resp(json.dumps(payload))
    return opener


def test_pypi_version_reads_latest():
    version, err = pypi_version(
        "dazzle-lib", opener=_opener({"info": {"version": "0.8.2"}}))
    assert (version, err) == ("0.8.2", None)


def test_pypi_404_is_an_answer_not_an_error():
    """dazzle-loglib is not published; that is information, not failure."""
    version, err = pypi_version("dazzle-loglib", opener=_opener(http_error=404))
    assert version is None
    assert err is None


def test_pypi_server_error_is_an_error():
    version, err = pypi_version("x", opener=_opener(http_error=503))
    assert version is None
    assert "503" in err


def test_pypi_network_failure_is_reported():
    version, err = pypi_version(
        "x", opener=_opener(exc=urllib.error.URLError("offline")))
    assert version is None
    assert err is not None


def test_pypi_unparseable_payload_is_reported():
    def opener(url, timeout=20):
        class _R(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return _R("<html>")
    version, err = pypi_version("x", opener=opener)
    assert version is None
    assert "unparseable" in err
