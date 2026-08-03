"""The single-repo detail card -- `dz dazzle-update <name>`.

USER REQUEST 2026-08-02: "It would be nice to do a search for a specific
package to see all the details about it." pip-show for the ecosystem:
one repo, every axis (identity, checkouts, install, PyPI, sets,
findings), matched by owner/repo name, dist name, or checkout folder
name, glob or substring.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent.parent))

import dazzle_update as du  # noqa: E402


def _rec(key, full_name=None, installed=None, paths=(), sets_list=(),
         declared=None):
    return {
        "key": key, "full_name": full_name or key,
        "configured_slugs": [], "redirected": False,
        "in_namespace": True, "cloned": True, "third_party": False,
        "foreign": False, "installed": installed, "declared_dist": declared,
        "declared_dist_source": "pyproject.toml", "source_version": None,
        "published": None, "pypi_owned": None, "excluded": None,
        "errors": [], "paths": list(paths), "sets": list(sets_list),
        "primary": (list(paths) or [None])[0], "primary_reason": "only",
        "checkouts": [{"path": p, "git": {"branch": "main",
                                          "upstream": "origin/main"},
                       "excluded": False} for p in paths],
    }


POP = {
    "dazzletools/dazzlesum": _rec(
        "dazzletools/dazzlesum", "DazzleTools/dazzlesum",
        installed={"name": "dazzlesum", "version": "1.4.5",
                   "path": r"C:\x\dazzle-checksum\dazzlesum"},
        paths=[r"C:\x\dazzle-checksum\dazzlesum"],
        sets_list=["dazzle"]),
    "djdarcy/dpapick3": _rec(
        "djdarcy/dpapick3", "djdarcy/DPAPIck3",
        declared="dpapick3",
        paths=[r"C:\x\DPAPIck3"]),
    "dazzletools/dazzlecmd": _rec(
        "dazzletools/dazzlecmd", "DazzleTools/dazzlecmd",
        paths=[r"C:\x\dazzlecmd\github"]),
}


class TestMatchRecords:
    def test_bare_repo_name_substring(self):
        got = du.match_records(POP, ["dazzlesum"])
        assert set(got) == {"dazzletools/dazzlesum"}

    def test_full_name_and_case(self):
        got = du.match_records(POP, ["DazzleTools/Dazzlesum"])
        assert set(got) == {"dazzletools/dazzlesum"}

    def test_dist_and_declared_names(self):
        assert set(du.match_records(POP, ["dpapick3"])) == {"djdarcy/dpapick3"}

    def test_checkout_folder_basename(self):
        got = du.match_records(POP, ["DPAPIck3"])
        assert set(got) == {"djdarcy/dpapick3"}

    def test_glob(self):
        got = du.match_records(POP, ["dazzle*"])
        assert "dazzletools/dazzlesum" in got
        assert "dazzletools/dazzlecmd" in got
        assert "djdarcy/dpapick3" not in got

    def test_substring_is_query_into_candidate_only(self):
        """'dazzlesum-extra' must not match 'dazzlesum' -- a candidate
        being a substring of the query is not a match."""
        assert du.match_records(POP, ["dazzlesum-extra"]) == {}

    def test_multiple_terms_union(self):
        got = du.match_records(POP, ["dazzlesum", "dpapick3"])
        assert len(got) == 2


class TestRenderQuery:
    def _findings(self):
        return {"stale-remote-url": [POP["dazzletools/dazzlesum"]]}

    def test_card_shows_every_axis(self, capsys):
        rc = du.render_query(POP, self._findings(), ["dazzlesum"], {})
        out = capsys.readouterr().out
        assert rc == 0
        assert "DazzleTools/dazzlesum" in out
        assert "dazzlesum 1.4.5 (editable)" in out
        assert "sets        dazzle" in out
        assert "stale-remote-url" in out

    def test_no_findings_says_so_explicitly(self, capsys):
        du.render_query(POP, {}, ["dazzlecmd"], {})
        assert "none -- not classified this run" in capsys.readouterr().out

    def test_no_match_exits_2_with_guidance(self, capsys):
        rc = du.render_query(POP, {}, ["nonexistent"], {})
        out = capsys.readouterr().out
        assert rc == 2
        assert "no repo matches" in out

    def test_json_mode_emits_matched_records(self, capsys):
        rc = du.render_query(POP, {}, ["dazzlesum"], {}, as_json=True)
        out = capsys.readouterr().out
        assert rc == 0
        payload = json.loads(out)
        assert payload["query"] == ["dazzlesum"]
        assert payload["matches"][0]["full_name"] == "DazzleTools/dazzlesum"


class TestCliGuards:
    def test_query_plus_fix_refuses(self, tmp_path, capsys):
        cfg = tmp_path / "cfg.json"
        cfg.write_text("{}", encoding="utf-8")
        rc = du.main(["dazzlesum", "--fix", "--config", str(cfg)])
        out = capsys.readouterr().out
        assert rc == 2
        assert "read-only" in out


# -- QF: the freshness architecture (cache-index + live-verified matches) --

import subprocess  # noqa: E402

sys.path.insert(0, str(_HERE.parent.parent))
from ecosystem import EcosystemConfig  # noqa: E402


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd)] + list(args), check=True,
                   capture_output=True)


def _real_repo(tmp_path):
    """Throwaway fixture repo, per the _repo_common test convention:
    identity and NO SIGNING as local repo config -- the host machine
    signs real commits globally, and a fixture that inherits that pops
    pinentry during a test run (it did)."""
    repo = tmp_path / "liverepo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def _stale_record(key, path, excluded=False):
    stale = {"branch": "STALE", "upstream": None, "ahead": 9, "behind": 9,
             "dirty_count": 9, "untracked_count": 9, "churn_count": 9}
    return {
        "key": key, "full_name": key, "configured_slugs": [],
        "redirected": False, "in_namespace": True, "cloned": True,
        "third_party": False, "foreign": False, "installed": None,
        "declared_dist": None, "declared_dist_source": None,
        "source_version": None, "published": None, "pypi_owned": None,
        "excluded": None, "excluded_paths": [], "errors": [],
        "paths": [str(path)], "sets": [], "primary": str(path),
        "primary_reason": "only", "last_activity": None,
        "git": dict(stale),
        "checkouts": [{"path": str(path), "git": dict(stale),
                       "excluded": excluded}],
    }


class TestRefreshMatched:
    def test_mutation_after_cache_is_visible(self, tmp_path):
        """AC-2: the card must show the repo as it IS, not as cached."""
        repo = _real_repo(tmp_path)
        (repo / "f.txt").write_text("changed\n", encoding="utf-8")
        rec = {"o/live": _stale_record("o/live", repo)}
        info = du.refresh_matched(rec, dict(rec), EcosystemConfig(),
                                  do_fetch=False)
        g = rec["o/live"]["checkouts"][0]["git"]
        assert info["refreshed"] == ["o/live"]
        assert g["branch"] == "main"          # was STALE
        assert g["dirty_count"] == 1          # was 9
        assert g["untracked_count"] == 0      # was 9

    def test_excluded_checkouts_are_not_refreshed(self, tmp_path):
        """querylab amendment 1: baks snapshots stay untouched."""
        repo = _real_repo(tmp_path)
        rec = {"o/x": _stale_record("o/x", repo, excluded=True)}
        info = du.refresh_matched(rec, dict(rec), EcosystemConfig(),
                                  do_fetch=False)
        assert info["refreshed"] == []
        assert rec["o/x"]["checkouts"][0]["git"]["branch"] == "STALE"

    def test_cap_limits_live_refresh_and_reports_rest(self, tmp_path):
        repo = _real_repo(tmp_path)
        rec = {f"o/r{i}": _stale_record(f"o/r{i}", repo) for i in range(4)}
        info = du.refresh_matched(rec, dict(rec), EcosystemConfig(),
                                  do_fetch=False, cap=2)
        assert len(info["refreshed"]) == 2
        assert len(info["from_cache"]) == 2

    def test_no_fetch_never_calls_fetch_all(self, tmp_path, monkeypatch):
        repo = _real_repo(tmp_path)
        monkeypatch.setattr(du, "fetch_all",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("fetched")))
        rec = {"o/live": _stale_record("o/live", repo)}
        du.refresh_matched(rec, dict(rec), EcosystemConfig(),
                           do_fetch=False)


class TestFastPathDispatch:
    def _fixture_cache(self, cfg="C:/other/cfg.json"):
        rec = {"o/hit": _stale_record("o/hit", "C:/nonexistent/hit")}
        meta = {"namespace_count": 11, "org_repo_count": 124,
                "config": cfg, "errors": []}
        return rec, meta

    def test_query_answers_from_cache_without_scanning(self, tmp_path,
                                                       monkeypatch, capsys):
        rec, meta = self._fixture_cache()
        monkeypatch.setattr(du.scancache, "load",
                            lambda **k: (rec, meta, 120.0, None))
        monkeypatch.setattr(du, "collect_local",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("full scan ran")))
        cfgp = tmp_path / "c.json"
        cfgp.write_text("{}", encoding="utf-8")
        rc = du.main(["hit", "--config", str(cfgp), "--color", "never"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "population from cache, 2m old" in out
        assert "11 namespace(s), 124 namespace repos" in out
        assert "o/hit" in out

    def test_scope_mismatch_warns_naming_both_configs(self, tmp_path,
                                                      monkeypatch, capsys):
        """QF-4 / the dazzlesum "not ours" regression, at query grain."""
        rec, meta = self._fixture_cache(cfg="C:/other/cfg.json")
        monkeypatch.setattr(du.scancache, "load",
                            lambda **k: (rec, meta, 60.0, None))
        cfgp = tmp_path / "mine.json"
        cfgp.write_text("{}", encoding="utf-8")
        du.main(["hit", "--config", str(cfgp), "--color", "never"])
        out = capsys.readouterr().out
        assert "written under config C:/other/cfg.json" in out
        assert str(cfgp) in out
        assert "population scope may differ" in out

    def test_explicit_cached_flag_still_pure_replay(self, tmp_path,
                                                    monkeypatch):
        """--cached must NOT take the fast path (no live refresh)."""
        rec, meta = self._fixture_cache()
        monkeypatch.setattr(du.scancache, "load",
                            lambda **k: (rec, meta, 60.0, None))
        monkeypatch.setattr(du, "refresh_matched",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("refreshed under --cached")))
        monkeypatch.setattr(du, "gh_status", lambda: (False, "test"))
        cfgp = tmp_path / "c.json"
        cfgp.write_text("{}", encoding="utf-8")
        rc = du.main(["hit", "--cached", "--config", str(cfgp),
                      "--color", "never", "--no-progress"])
        assert rc == 0


class TestIdentityRefresh:
    """A remote repointed since the cache was written must clear its
    finding immediately -- the card contradicting a fix the user just
    made is the worst moment to be wrong. (dazzlesum, 2026-08-02.)"""

    def test_repointed_remote_clears_redirect(self, tmp_path):
        repo = _real_repo(tmp_path)
        _git(repo, "remote", "add", "origin",
             "https://github.com/NewOrg/thing.git")
        rec = {"o/thing": _stale_record("o/thing", repo)}
        rec["o/thing"]["configured_slugs"] = ["olduser/thing"]
        rec["o/thing"]["redirected"] = True

        class R:
            def resolve(self, slug):
                return {"full_name": "NewOrg/thing", "redirected": False}

        du.refresh_matched(rec, dict(rec), EcosystemConfig(),
                           do_fetch=False, resolver=R())
        assert rec["o/thing"]["redirected"] is False
        assert rec["o/thing"]["configured_slugs"] == ["NewOrg/thing"]
        assert rec["o/thing"]["full_name"] == "NewOrg/thing"


class TestNarrowedCacheGuards:
    def test_query_warns_when_population_cache_was_narrowed(
            self, tmp_path, monkeypatch, capsys):
        """A --root scan once overwrote the shared index, silently
        shrinking the population from 184 repos to 124."""
        rec = {"o/hit": _stale_record("o/hit", "C:/nonexistent/hit")}
        meta = {"namespace_count": 1, "org_repo_count": 5, "config": None,
                "narrowed": True, "roots": ["C:/code/one-project"],
                "errors": []}
        monkeypatch.setattr(du.scancache, "load",
                            lambda **k: (rec, meta, 60.0, None))
        cfgp = tmp_path / "c.json"
        cfgp.write_text("{}", encoding="utf-8")
        du.main(["hit", "--config", str(cfgp), "--color", "never"])
        out = capsys.readouterr().out
        assert "--root-narrowed scan" in out
        assert "C:/code/one-project" in out

    def test_narrowed_scan_does_not_write_the_shared_cache(
            self, tmp_path, monkeypatch):
        """The write itself is refused, so the index cannot be
        corrupted by a scoped run in the first place."""
        monkeypatch.setattr(du.scancache, "save",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("narrowed scan wrote cache")))
        monkeypatch.setattr(du, "gh_status", lambda: (False, "test"))
        monkeypatch.setattr(du, "collect_local", lambda *a, **k: ([], []))
        monkeypatch.setattr(du, "editable_installs", lambda: [])
        cfgp = tmp_path / "c.json"
        cfgp.write_text("{}", encoding="utf-8")
        rc = du.main(["--root", str(tmp_path), "--no-fetch", "--no-progress",
                      "--color", "never", "--config", str(cfgp)])
        assert rc == 0
