"""Regression tests for issue #106 -- dist-rename name collision.

The incident, on 2026-07-30: our `preserve` project was renamed to
`dazzle-preserve`. A stale install still carried the OLD dist name.
dazzle-update compared that old name against PyPI, where `preserve` now
belongs to an unrelated third party at 2.0.1, and reported

    DazzleTools/preserve    installed 0.5.2 < PyPI 2.0.1

Following that recommendation installed a stranger's package over our
console entry point.

The failure chain was: stale installed dist name -> assumed to be the
repo's PyPI identity -> version-compared against a foreign project ->
"update available" whose remedy installs foreign code.

These tests pin each link. They are deliberately paranoid about the
DIRECTION of failure: a false "you are up to date" costs a delayed
upgrade, while a false "update available" can execute arbitrary foreign
code. The safe default everywhere here is to refuse and report.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent.parent))

from _repo_common.discovery import (  # noqa: E402
    normalize_dist,
    pypi_owned_by,
    pypi_project,
    read_declared_dist_name,
)
from ecosystem import (  # noqa: E402
    EcosystemConfig,
    classify,
    join,
)


def _cfg(**kw):
    kw.setdefault("namespaces", ["DazzleTools"])
    return EcosystemConfig(**kw)


# -- link 1: the repo's declared name is authoritative --------------------

def test_declared_name_read_from_setup_py(tmp_path):
    """The real shape: preserve/setup.py declares name="dazzle-preserve"."""
    repo = tmp_path / "preserve"
    repo.mkdir()
    (repo / "setup.py").write_text(
        'from setuptools import setup\nsetup(\n    name="dazzle-preserve",\n'
        '    version="0.8.0",\n)\n', encoding="utf-8")
    name, source = read_declared_dist_name(repo)
    assert name == "dazzle-preserve"
    assert "setup.py" in source


def test_declared_name_read_from_pyproject(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "dazzle-thing"\nversion = "1.0"\n', encoding="utf-8")
    name, source = read_declared_dist_name(repo)
    assert name == "dazzle-thing"
    assert "pyproject" in source


def test_pyproject_wins_over_setup_py(tmp_path):
    repo = tmp_path / "both"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "modern-name"\n', encoding="utf-8")
    (repo / "setup.py").write_text('setup(name="legacy-name")\n', encoding="utf-8")
    assert read_declared_dist_name(repo)[0] == "modern-name"


def test_no_metadata_returns_none(tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    assert read_declared_dist_name(repo) == (None, None)


def test_malformed_pyproject_does_not_raise(tmp_path):
    repo = tmp_path / "broken"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project\nname = oops", encoding="utf-8")
    assert read_declared_dist_name(repo)[0] is None


@pytest.mark.parametrize("a,b", [
    ("dazzle-preserve", "dazzle_preserve"),
    ("Dazzle.Preserve", "dazzle-preserve"),
    ("DAZZLE--PRESERVE", "dazzle-preserve"),
])
def test_normalize_dist_follows_pep503(a, b):
    assert normalize_dist(a) == normalize_dist(b)


# -- link 2: a rename is its own finding, and blocks comparison -----------

def _renamed_fixture(tmp_path):
    """The incident: installed as 'preserve', repo declares 'dazzle-preserve'."""
    repo = tmp_path / "preserve"
    repo.mkdir()
    local = [{"path": str(repo), "full_name": "DazzleTools/preserve",
              "slug": "DazzleTools/preserve",
              "git": {"branch": "main", "upstream": "origin/main", "ahead": 0,
                      "behind": 0, "dirty_count": 0, "untracked_count": 0}}]
    installs = [{"name": "preserve", "version": "0.5.2", "path": str(repo)}]
    from ecosystem import norm
    return local, installs, {norm(str(repo)): ("dazzle-preserve", "setup.py name=")}


def test_rename_is_reported_as_its_own_category(tmp_path):
    cfg = _cfg()
    local, installs, declared = _renamed_fixture(tmp_path)
    records = join([], local, installs, cfg, declared_dists=declared)
    findings = classify(records, cfg)
    keys = {r["key"] for r in findings["stale-dist-name"]}
    assert "dazzletools/preserve" in keys


def test_rename_blocks_the_published_comparison_entirely(tmp_path):
    """The load-bearing assertion.

    Even with a foreign PyPI version present in the data, a renamed dist
    must NOT produce an install recommendation.
    """
    cfg = _cfg()
    local, installs, declared = _renamed_fixture(tmp_path)
    records = join([], local, installs, cfg,
                   declared_dists=declared,
                   published={"dazzle-preserve": "2.0.1"})
    findings = classify(records, cfg)
    keys = {r["key"] for r in findings["install-behind-published"]}
    assert "dazzletools/preserve" not in keys, (
        "a renamed dist produced an update recommendation -- this is the "
        "exact chain that installed foreign code in issue #106")


def test_matching_names_still_allow_a_real_upgrade_finding(tmp_path):
    """The fix must not silence genuine behind-published findings."""
    cfg = _cfg()
    repo = tmp_path / "proj"
    repo.mkdir()
    local = [{"path": str(repo), "full_name": "DazzleTools/proj",
              "slug": "DazzleTools/proj", "git": {"branch": "main"}}]
    installs = [{"name": "dazzle-proj", "version": "1.0.0", "path": str(repo)}]
    from ecosystem import norm
    records = join([], local, installs, cfg,
                   declared_dists={norm(str(repo)): ("dazzle-proj", "pyproject")},
                   published={"dazzle-proj": "2.0.0"},
                   pypi_meta={"dazzle-proj": {"owned": True, "urls": []}})
    findings = classify(records, cfg)
    keys = {r["key"] for r in findings["install-behind-published"]}
    assert "dazzletools/proj" in keys


# -- link 3: ownership check (defense in depth) --------------------------

def test_ownership_true_for_our_namespace():
    info = {"urls": ["https://github.com/djdarcy/preserve"], "version": "0.8.0"}
    assert pypi_owned_by(info, ["DazzleTools", "djdarcy"]) is True


def test_ownership_false_for_a_stranger():
    """The real foreign project from the incident."""
    info = {"urls": ["https://github.com/evhart/preserve/"], "version": "2.0.1"}
    assert pypi_owned_by(info, ["DazzleTools", "djdarcy"]) is False


def test_ownership_unknown_when_no_urls_declared():
    """Absence of evidence is NOT evidence of ownership."""
    assert pypi_owned_by({"urls": [], "version": "1.0"}, ["djdarcy"]) is None
    assert pypi_owned_by(None, ["djdarcy"]) is None


def test_unowned_pypi_project_becomes_a_collision_not_an_upgrade(tmp_path):
    cfg = _cfg()
    repo = tmp_path / "proj"
    repo.mkdir()
    local = [{"path": str(repo), "full_name": "DazzleTools/proj",
              "slug": "DazzleTools/proj", "git": {"branch": "main"}}]
    installs = [{"name": "proj", "version": "0.5.2", "path": str(repo)}]
    from ecosystem import norm
    records = join([], local, installs, cfg,
                   declared_dists={norm(str(repo)): ("proj", "setup.py name=")},
                   published={"proj": "2.0.1"},
                   pypi_meta={"proj": {"owned": False,
                                       "urls": ["https://github.com/evhart/proj"]}})
    findings = classify(records, cfg)
    assert "dazzletools/proj" in {r["key"] for r in findings["pypi-name-collision"]}
    assert "dazzletools/proj" not in {
        r["key"] for r in findings["install-behind-published"]}


# -- pypi_project metadata extraction ------------------------------------

def _opener(payload):
    class _Resp(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(url, timeout=20):
        return _Resp(json.dumps(payload))
    return opener


def test_pypi_project_collects_urls_for_the_ownership_check():
    payload = {"info": {"version": "0.8.0",
                        "home_page": "https://github.com/djdarcy/preserve",
                        "project_urls": {"Source": "https://github.com/djdarcy/preserve"},
                        "summary": "ours"}}
    info, err = pypi_project("dazzle-preserve", opener=_opener(payload))
    assert err is None
    assert info["version"] == "0.8.0"
    assert any("djdarcy" in u for u in info["urls"])


def test_pypi_404_still_means_not_published_not_an_error():
    def opener(url, timeout=20):
        raise urllib.error.HTTPError(url, 404, "nope", {}, None)
    info, err = pypi_project("never-published", opener=opener)
    assert info is None and err is None
