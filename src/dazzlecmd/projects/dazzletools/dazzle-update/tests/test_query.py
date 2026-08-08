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
    def test_query_plus_fix_no_longer_refuses_outright(self, tmp_path,
                                                       capsys):
        """CONTRACT AMENDED (Addendum 3 / #114). This test previously
        asserted the card was read-only, which was AC-4 as adjudicated
        on 2026-08-02. Two facts outgrew it: the freshness architecture
        made the card the best-verified state in the tool, and the only
        way to scope a fix was an undocumented, name-blind `--root`.

        --fix now composes with a query, gated on the match being
        unambiguous. What must NOT happen is a blind write: with no
        cache and no match the run still refuses rather than acting.
        """
        cfg = tmp_path / "cfg.json"
        cfg.write_text("{}", encoding="utf-8")
        rc = du.main(["definitely-no-such-repo-xyz", "--fix", "--dry-run",
                      "--no-fetch", "--no-progress", "--color", "never",
                      "--config", str(cfg)])
        out = capsys.readouterr().out
        assert rc == 2
        assert "read-only" not in out          # the old contract is gone
        assert "no repo matches" in out        # and it refused anyway


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


class TestJsonPurity:
    """TESTER FINDING 2026-08-03: `--json > out.json` produced a file
    that would not parse -- the provenance header and WARNING lines went
    to stdout ahead of the document. The machine-readable mode was
    emitting something no machine could read. stdout belongs to the
    document; context travels inside meta.
    """

    def test_json_mode_prints_no_warnings_to_stdout(self, capsys):
        meta = {"errors": ["a warning that must not pollute stdout"]}
        du.render_query(POP, {}, ["dazzlesum"], meta, as_json=True)
        out = capsys.readouterr().out
        json.loads(out)                       # must parse
        assert "WARNING" not in out

    def test_json_payload_carries_meta_not_prose(self, capsys):
        meta = {"errors": ["ctx"], "namespace_count": 11}
        du.render_query(POP, {}, ["dazzlesum"], meta, as_json=True)
        payload = json.loads(capsys.readouterr().out)
        assert payload["meta"]["errors"] == ["ctx"]
        assert payload["meta"]["namespace_count"] == 11

    def test_no_match_in_json_mode_still_parses(self, capsys):
        rc = du.render_query(POP, {}, ["nope"], {"errors": []}, as_json=True)
        payload = json.loads(capsys.readouterr().out)
        assert rc == 2 and payload["matches"] == []

    def test_fast_path_header_suppressed_under_json(self, tmp_path,
                                                    monkeypatch, capsys):
        rec = {"o/hit": _stale_record("o/hit", "C:/nonexistent/hit")}
        meta = {"namespace_count": 11, "org_repo_count": 124,
                "config": None, "errors": []}
        monkeypatch.setattr(du.scancache, "load",
                            lambda **k: (rec, meta, 60.0, None))
        cfgp = tmp_path / "c.json"
        cfgp.write_text("{}", encoding="utf-8")
        du.main(["hit", "--json", "--config", str(cfgp), "--color", "never"])
        out = capsys.readouterr().out
        json.loads(out)                       # must parse
        assert "population from cache" not in out


class TestRemotelessRefresh:
    def test_remoteless_checkout_is_not_a_fetch_failure(self, tmp_path,
                                                        monkeypatch):
        """TESTER FINDING 2026-08-03: a repo with no remote at all was
        counted as a fetch FAILURE during live verification -- "nothing
        to fetch from" rendered as "fetching went wrong"."""
        repo = _real_repo(tmp_path)           # no remote added
        called = {}

        def _fetch_all(paths, *a, **k):
            called["paths"] = paths
            return []

        monkeypatch.setattr(du, "fetch_all", _fetch_all)
        rec = {"o/lonely": _stale_record("o/lonely", repo)}
        info = du.refresh_matched(rec, dict(rec), EcosystemConfig(),
                                  do_fetch=True)
        assert info["fetch_failures"] == []
        assert called.get("paths") in (None, [])


class TestStaleUrlRowNamesTheStaleSlug:
    def test_row_shows_the_differing_slug_not_the_first(self, capsys):
        """A repo with several checkouts, some already repointed, showed
        configured_slugs[0] -- which after a partial fix was the CANONICAL
        name, rendering "X -> X": a redirect from a name to itself."""
        r = dict(POP["dazzletools/dazzlesum"])
        r["full_name"] = "DazzleTools/thing"
        r["git"] = {"branch": "main", "upstream": "origin/main"}
        r["configured_slugs"] = ["DazzleTools/thing", "olduser/thing"]
        meta = {"namespace_count": 1, "org_repo_count": 1, "cloned_count": 1,
                "install_count": 0, "gh_detail": "t", "roots": ["X"],
                "published_detail": "skipped", "errors": [], "clean": 0}
        du.render_text({}, {"stale-remote-url": [r]}, meta)
        out = capsys.readouterr().out
        assert "olduser/thing -> DazzleTools/thing" in out
        assert "DazzleTools/thing -> DazzleTools/thing" not in out

    def test_multiple_stale_slugs_are_counted(self, capsys):
        r = dict(POP["dazzletools/dazzlesum"])
        r["full_name"] = "DazzleTools/thing"
        r["git"] = {"branch": "main", "upstream": "origin/main"}
        r["configured_slugs"] = ["a/thing", "b/thing", "DazzleTools/thing"]
        meta = {"namespace_count": 1, "org_repo_count": 1, "cloned_count": 1,
                "install_count": 0, "gh_detail": "t", "roots": ["X"],
                "published_detail": "skipped", "errors": [], "clean": 0}
        du.render_text({}, {"stale-remote-url": [r]}, meta)
        assert "a/thing (+1 more) ->" in capsys.readouterr().out


class TestScopeLens:
    """#115: --scope claimed to 'limit to a namespace' but only narrowed
    ENUMERATION; every on-disk repo still rendered, and worse, filtering
    the namespace list corrupted owns() so in-scope-config repos read
    'not ours'."""

    def _rec(self, key, fn):
        return {"key": key, "full_name": fn, "sets": []}

    def test_filters_by_owning_namespace(self):
        a = self._rec("dazzlelib/x", "DazzleLib/x")
        b = self._rec("dazzletools/y", "DazzleTools/y")
        findings = {"dirty": [a, b], "clean": [a]}
        got, hidden = du.apply_scope_lens(findings, ["DazzleLib"])
        assert got["dirty"] == [a]
        assert hidden == 1

    def test_case_insensitive_multi_scope(self):
        a = self._rec("dazzlelib/x", "DazzleLib/x")
        b = self._rec("dazzleml/y", "DazzleML/y")
        got, _ = du.apply_scope_lens({"dirty": [a, b]},
                                     ["dazzlelib", "DAZZLEML"])
        assert got["dirty"] == [a, b]

    def test_clean_and_excluded_do_not_count_as_hidden(self):
        b = self._rec("dazzleml/y", "DazzleML/y")
        _, hidden = du.apply_scope_lens(
            {"clean": [b], "excluded-by-policy": [b]}, ["DazzleLib"])
        assert hidden == 0

    def test_remoteless_repo_is_outside_any_namespace_scope(self):
        r = {"key": "loglib", "full_name": None, "sets": []}
        got, hidden = du.apply_scope_lens({"no-upstream": [r]}, ["DazzleLib"])
        assert got["no-upstream"] == [] and hidden == 1


class TestScopedFix:
    """#114 / Addendum 3: --fix composes with a query, gated on the match
    being unambiguous. AC-4' .. AC-4g."""

    def _rec(self, key, cloned=True, excluded=None, live=1, installed=None):
        cos = [{"path": f"C:/x/{key}/{i}", "excluded": False,
                "git": {"branch": "main", "upstream": "origin/main"}}
               for i in range(live)]
        return {"key": key, "full_name": key, "cloned": cloned,
                "excluded": excluded, "installed": installed,
                "checkouts": cos, "sets": [],
                "git": {"branch": "main", "upstream": "origin/main"}}

    # -- the uniqueness gate (AC-4b, AC-4c) --

    def test_actionable_skips_not_cloned(self):
        m = {"a": self._rec("a", cloned=False, live=0)}
        assert du.actionable_matches(m) == []

    def test_actionable_skips_fully_excluded(self):
        m = {"a": self._rec("a", excluded="path excluded by policy")}
        assert du.actionable_matches(m) == []

    def test_install_only_record_is_actionable(self):
        """No live checkout but a pip install WITH A PATH -- a reinstall
        is a real action, so it counts. The path matters: `pip install
        -e` needs somewhere to point, so an install record without one
        is not actionable (tightened after the tester's C2 finding)."""
        m = {"a": self._rec("a", live=0,
                            installed={"name": "a", "path": "C:/x/a"})}
        assert du.actionable_matches(m) == ["a"]

    def test_install_record_without_a_path_is_not_actionable(self):
        m = {"a": self._rec("a", live=0, installed={"name": "a"})}
        assert du.actionable_matches(m) == []

    def test_multi_actionable_refuses_and_lists(self, capsys):
        m = {"a": self._rec("a"), "b": self._rec("b")}
        rc = du.fix_scoped_to_query({}, {}, m, _Args())
        out = capsys.readouterr().out
        assert rc == 2
        assert "--fix needs ONE repo; this matched 2" in out
        assert "  a" in out and "  b" in out
        assert "narrow the name" in out

    def test_uncloned_sibling_does_not_create_ambiguity(self, capsys):
        """AC-4c: one real repo plus an uncloned namesake still acts."""
        m = {"a": self._rec("a"), "b": self._rec("b", cloned=False, live=0)}
        du.fix_scoped_to_query({}, {"behind-upstream": []}, m,
                               _Args(dry_run=True))
        assert "APPLYING FIXES to a" in capsys.readouterr().out

    def test_no_match_says_nothing_extra(self, capsys):
        """The 'not cloned here' line must not be asserted about a repo
        that was never found -- render_query already explained."""
        rc = du.fix_scoped_to_query({}, {}, {}, _Args())
        assert rc == 2
        assert "nothing to act on" not in capsys.readouterr().out

    def test_matched_but_nothing_actionable_says_so(self, capsys):
        m = {"a": self._rec("a", cloned=False, live=0)}
        rc = du.fix_scoped_to_query({}, {}, m, _Args())
        assert rc == 2
        assert "nothing to act on" in capsys.readouterr().out

    # -- scoping + flag composition (AC-4', AC-4f) --

    def test_only_the_matched_repo_is_acted_on(self, capsys):
        a, b = self._rec("a"), self._rec("b")
        findings = {"behind-upstream": [a, b]}
        du.fix_scoped_to_query({}, findings, {"a": a}, _Args(dry_run=True))
        out = capsys.readouterr().out
        assert "APPLYING FIXES to a" in out
        assert '"b"' not in out and " b " not in out

    def test_no_fetch_skips_pulls_but_keeps_reinstalls(self, capsys):
        a = self._rec("a")
        findings = {"behind-upstream": [a], "stale-install-metadata": []}
        du.fix_scoped_to_query({}, findings, {"a": a},
                               _Args(dry_run=True, no_fetch=True))
        out = capsys.readouterr().out
        assert "skipping pulls" in out
        assert "behind-counts" in out


class _Args:
    """Minimal args stand-in; the real parser is exercised by the CLI."""

    def __init__(self, dry_run=False, yes=False, no_fetch=False, json=False):
        self.dry_run = dry_run
        self.yes = yes
        self.no_fetch = no_fetch
        self.json = json


class TestScopedFixCli:
    def test_json_plus_fix_still_refuses(self, tmp_path, capsys):
        """AC-4e."""
        cfg = tmp_path / "c.json"
        cfg.write_text("{}", encoding="utf-8")
        rc = du.main(["anything", "--fix", "--json", "--config", str(cfg)])
        out = capsys.readouterr().out
        assert rc == 2
        assert "not available in --json mode" in out


class TestTesterFindings0812614:
    """Four defects found by an independent tester against the #114/#115
    work, all in the same two paths, all variations of one theme: state
    or intent asserted without being measured."""

    def _cached_meta(self, **kw):
        m = {"namespace_count": 11, "org_repo_count": 124,
             "cloned_count": 5, "install_count": 0, "gh_detail": "t",
             "published_detail": "skipped", "roots": ["X"], "errors": [],
             "clean": 0, "config": None}
        m.update(kw)
        return m

    def test_A_cached_replay_drops_the_previous_runs_scope_lens(
            self, tmp_path, monkeypatch, capsys):
        """FINDING A: a --scope run wrote its lens into the cache, so
        every later plain --cached printed 'SCOPE showing only DazzleLib'
        above 69 rows from other namespaces. Live on the real cache."""
        rec = {"o/hit": _stale_record("o/hit", "C:/nonexistent/hit")}
        meta = self._cached_meta(scope_lens=["DazzleLib"], scope_hidden=91,
                                 set_lens=["dazzle"], set_hidden=7)
        monkeypatch.setattr(du.scancache, "load",
                            lambda **k: (rec, meta, 60.0, None))
        monkeypatch.setattr(du, "gh_status", lambda: (False, "test"))
        cfgp = tmp_path / "c.json"
        cfgp.write_text("{}", encoding="utf-8")
        du.main(["--cached", "--max-age", "999999", "--no-progress",
                 "--color", "never", "--config", str(cfgp)])
        out = capsys.readouterr().out
        assert "SCOPE" not in out
        assert "SET LENS" not in out

    def test_D_stale_no_fetch_warning_does_not_bleed_into_replay(
            self, tmp_path, monkeypatch, capsys):
        """FINDING D: same root cause -- stale_behind described the run
        that WROTE the cache, not this one."""
        rec = {"o/hit": _stale_record("o/hit", "C:/nonexistent/hit")}
        meta = self._cached_meta(stale_behind=True)
        monkeypatch.setattr(du.scancache, "load",
                            lambda **k: (rec, meta, 60.0, None))
        monkeypatch.setattr(du, "gh_status", lambda: (False, "test"))
        cfgp = tmp_path / "c.json"
        cfgp.write_text("{}", encoding="utf-8")
        du.main(["--cached", "--max-age", "999999", "--no-progress",
                 "--color", "never", "--config", str(cfgp)])
        out = capsys.readouterr().out
        assert "pull status unknown" not in out

    def test_B_cached_plus_fix_refuses_instead_of_no_op(self, tmp_path,
                                                        capsys):
        """FINDING B: --fix was accepted and silently ignored on the
        cached path -- no plan, no error, no reason."""
        cfgp = tmp_path / "c.json"
        cfgp.write_text("{}", encoding="utf-8")
        rc = du.main(["--cached", "--fix", "--dry-run", "--config",
                      str(cfgp), "--color", "never"])
        out = capsys.readouterr().out
        assert rc == 2
        assert "does not act on replayed data" in out

    def test_C_bulk_fix_plus_json_refuses(self, tmp_path, capsys):
        """FINDING C: bulk --fix --json rendered TEXT to a caller that
        asked for a document."""
        cfgp = tmp_path / "c.json"
        cfgp.write_text("{}", encoding="utf-8")
        rc = du.main(["--fix", "--json", "--config", str(cfgp)])
        out = capsys.readouterr().out
        assert rc == 2
        assert "not available in --json mode" in out

    def test_C2_install_only_record_is_actionable(self):
        """FINDING C2: the query gate was STRICTER than the bulk path it
        scopes -- an installed-but-uncloned dist (dazzle-dz) was refused
        by `--fix <name>` while bulk --fix would reinstall it."""
        m = {"dazzle-dz": {"key": "dazzle-dz", "full_name": None,
                           "cloned": False, "excluded": None,
                           "checkouts": [],
                           "installed": {"name": "dazzle-dz",
                                         "path": "C:/x/alias"}}}
        assert du.actionable_matches(m) == ["dazzle-dz"]


class TestFixConverges:
    """USER FINDING 2026-08-07: "The point of --fix is that it just keeps
    fixing till there is nothing left to fix. Not multiple runs of the
    same command which is tedious."

    Fixes cascade: a pull rewrites the source tree, which makes the
    editable install stale, which is a NEW finding. One pass could not
    converge, so the user re-ran the same command until it went quiet.
    """

    def _rec(self, key, path="C:/x/a"):
        return {"key": key, "full_name": key, "cloned": True,
                "excluded": None, "installed": {"name": key, "path": path},
                "checkouts": [{"path": path, "excluded": False,
                               "git": {"branch": "main",
                                       "upstream": "origin/main"}}],
                # A record with checkouts MUST name its primary, or
                # --fix refuses rather than guess which to touch. That
                # rail is correct; the fixture was simply incomplete.
                "primary": path, "primary_reason": "only checkout",
                "sets": [], "git": {"branch": "main",
                                    "upstream": "origin/main"}}

    def test_reports_what_it_applied(self, monkeypatch, capsys):
        """apply_fixes must tell the caller whether it made progress --
        the loop stops on a pass that applies nothing."""
        r = self._rec("o/a")

        class _Res:
            returncode = 0
            stdout = stderr = ""

        monkeypatch.setattr(du.subprocess, "run", lambda *a, **k: _Res())
        tally = {}
        du.apply_fixes({"stale-install-metadata": [r]}, dry_run=False,
                       assume_yes=True, interactive=False,
                       report_applied=tally)
        assert tally["applied"] == 1

    def test_dry_run_reports_zero_applied(self, capsys):
        """A dry run applies nothing, and must say zero rather than
        report the count it WOULD have done -- otherwise the loop would
        read a preview as progress."""
        r = self._rec("o/a")
        tally = {}
        du.apply_fixes({"stale-install-metadata": [r]}, dry_run=True,
                       assume_yes=True, interactive=False,
                       report_applied=tally)
        assert tally["applied"] == 0

    def test_dry_run_does_not_claim_convergence(self, capsys, monkeypatch):
        """A dry run cannot iterate -- nothing changed for a second pass
        to observe. It must say so rather than imply it finished."""
        r = self._rec("o/a")
        monkeypatch.setattr(du, "refresh_matched",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("re-measured during dry run")))
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args(dry_run=True))
        out = capsys.readouterr().out
        assert "dry run shows one pass" in out

    def test_stops_when_a_pass_applies_nothing(self, capsys, monkeypatch):
        calls = {"n": 0}

        def _apply(findings, report_applied=None, **kw):
            calls["n"] += 1
            if report_applied is not None:
                report_applied["applied"] = 0
            return 0

        monkeypatch.setattr(du, "apply_fixes", _apply)
        monkeypatch.setattr(du, "refresh_matched",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("re-measured after no progress")))
        r = self._rec("o/a")
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args(yes=True))
        assert calls["n"] == 1

    def test_pass_cap_is_bounded_and_says_so(self, capsys, monkeypatch):
        """A repo that never converges must stop and report, not spin."""
        r = self._rec("o/a")

        def _apply(findings, report_applied=None, **kw):
            if report_applied is not None:
                report_applied["applied"] = 1      # always "progress"
            return 0

        monkeypatch.setattr(du, "apply_fixes", _apply)
        monkeypatch.setattr(du, "refresh_matched", lambda *a, **k: None)
        monkeypatch.setattr(du, "classify",
                            lambda *a, **k: {"stale-install-metadata": [r]})
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args(yes=True))
        out = capsys.readouterr().out
        assert f"stopped after {du.MAX_FIX_PASSES} passes" in out

    def test_reports_when_nothing_is_left(self, capsys, monkeypatch):
        r = self._rec("o/a")
        seq = [{"applied": 1}, {"applied": 0}]

        def _apply(findings, report_applied=None, **kw):
            if report_applied is not None:
                report_applied.update(seq.pop(0))
            return 0

        monkeypatch.setattr(du, "apply_fixes", _apply)
        monkeypatch.setattr(du, "refresh_matched", lambda *a, **k: None)
        monkeypatch.setattr(du, "classify", lambda *a, **k: {})
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args(yes=True))
        assert "nothing left to fix" in capsys.readouterr().out


class TestFailureIsNotProgress:
    """A command that FAILED is not work that was applied.

    Found by reading the code against my own tester brief: `done += 1`
    fired regardless of exit code. Two consequences -- the summary said
    "1 applied" for a command that failed (pre-existing), and once
    --fix began iterating on progress, a FAILING action counted as
    progress and would be retried up to the pass cap (introduced by the
    convergence loop).
    """

    def _rec(self):
        return {"key": "o/a", "full_name": "o/a", "cloned": True,
                "excluded": None, "declared_dist": None, "pypi_owned": None,
                "installed": {"name": "o/a", "path": "C:/x/a"},
                "checkouts": [], "sets": [], "git": {}}

    def _run(self, monkeypatch, returncode):
        class _Res:
            pass
        _Res.returncode = returncode
        _Res.stdout = ""
        _Res.stderr = "boom" if returncode else ""
        monkeypatch.setattr(du.subprocess, "run", lambda *a, **k: _Res())
        tally = {}
        du.apply_fixes({"stale-install-metadata": [self._rec()]},
                       dry_run=False, assume_yes=True, interactive=False,
                       report_applied=tally)
        return tally

    def test_failure_is_not_counted_as_applied(self, monkeypatch, capsys):
        tally = self._run(monkeypatch, returncode=1)
        assert tally["applied"] == 0
        assert tally["failed"] == 1

    def test_failure_is_reported_in_the_summary(self, monkeypatch, capsys):
        self._run(monkeypatch, returncode=1)
        assert "1 failed" in capsys.readouterr().out

    def test_success_still_counts(self, monkeypatch, capsys):
        tally = self._run(monkeypatch, returncode=0)
        assert tally["applied"] == 1 and tally["failed"] == 0

    def test_success_summary_omits_the_failed_clause(self, monkeypatch,
                                                     capsys):
        self._run(monkeypatch, returncode=0)
        assert "failed" not in capsys.readouterr().out

    def test_a_failing_action_does_not_drive_another_pass(self, monkeypatch,
                                                          capsys):
        """The loop's stop condition depends on this: without it a repo
        whose pull keeps failing would be retried MAX_FIX_PASSES times."""
        calls = {"n": 0}

        def _apply(findings, report_applied=None, **kw):
            calls["n"] += 1
            if report_applied is not None:
                report_applied.update({"applied": 0, "failed": 1})
            return 0

        monkeypatch.setattr(du, "apply_fixes", _apply)
        monkeypatch.setattr(du, "refresh_matched",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("re-measured after a failure")))
        r = self._rec()
        r["primary"] = "C:/x/a"
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args(yes=True))
        assert calls["n"] == 1


class TestQuitStopsTheLoop:
    """'q' means stop asking, not stop this pass.

    Found by an independent tester probing the convergence loop's
    bounds. Actions applied BEFORE the quit counted as progress, so the
    loop re-measured and prompted again -- declining to continue
    produced another round of prompts, which is the opposite of what
    the user asked for. On a write path that is a consent failure, not
    a cosmetic one.
    """

    def _rec(self, k):
        return {"key": k, "full_name": k, "cloned": True, "excluded": None,
                "installed": {"name": k, "path": "C:/x/" + k},
                "declared_dist": None, "pypi_owned": None, "checkouts": [],
                "sets": [], "git": {}, "primary": "C:/x/" + k}

    def test_quit_is_reported_even_when_work_was_applied(self, monkeypatch):
        class _Res:
            returncode = 0
            stdout = stderr = ""
        monkeypatch.setattr(du.subprocess, "run", lambda *a, **k: _Res())
        answers = iter(["yes", "quit"])
        monkeypatch.setattr(du, "_confirm", lambda *a, **k: next(answers))
        tally = {}
        du.apply_fixes(
            {"stale-install-metadata": [self._rec("o/a"), self._rec("o/b")]},
            dry_run=False, assume_yes=False, interactive=True,
            report_applied=tally)
        assert tally["applied"] == 1      # work DID happen
        assert tally["quit"] is True      # and the user still said stop

    def test_loop_stops_on_quit_despite_progress(self, monkeypatch, capsys):
        calls = {"n": 0}

        def _apply(findings, report_applied=None, **kw):
            calls["n"] += 1
            if report_applied is not None:
                report_applied.update({"applied": 1, "quit": True})
            return 0

        monkeypatch.setattr(du, "apply_fixes", _apply)
        monkeypatch.setattr(du, "refresh_matched",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("re-measured after quit")))
        r = self._rec("o/a")
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args(yes=True))
        assert calls["n"] == 1

    def test_progress_without_quit_still_iterates(self, monkeypatch, capsys):
        """The guard must not over-correct into never looping."""
        calls = {"n": 0}

        def _apply(findings, report_applied=None, **kw):
            calls["n"] += 1
            if report_applied is not None:
                report_applied.update({"applied": 1, "quit": False})
            return 0

        monkeypatch.setattr(du, "apply_fixes", _apply)
        monkeypatch.setattr(du, "refresh_matched", lambda *a, **k: None)
        monkeypatch.setattr(du, "classify", lambda *a, **k: {})
        r = self._rec("o/a")
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args(yes=True))
        assert calls["n"] == 1
        assert "nothing left to fix" in capsys.readouterr().out


class TestConsentCarriesAcrossPasses:
    """USER FINDING 2026-08-08, verbatim: "Shouldn't the 'a' (for all)
    apply to all fixes?"

        apply? [y/N/a/q/?] a
          Claude-Session-Backup: pull ok
        re-checking Claude-Session-Backup after pass 1...
        REINSTALL  Claude-Session-Backup
        apply? [y/N/a/q/?]          <-- asked again

    `a` upgraded assume_yes on a LOCAL inside apply_fixes, which died
    with the call; the next pass began from args.yes again. Exactly the
    escape `q` made before it was reported out -- the loop wraps code
    that owns its own consent semantics, and every internal signal is
    invisible to the outer layer unless deliberately surfaced. `q` was
    fixed in 0.12.15 and this one was not noticed at the same time.

    Consent is a property of the RUN: follow-on work a pull creates is
    remaining work of the same run, which is what "all remaining" said.
    """

    def _rec(self, k):
        return {"key": k, "full_name": k, "cloned": True, "excluded": None,
                "installed": {"name": k, "path": "C:/x/" + k},
                "declared_dist": None, "pypi_owned": None, "checkouts": [],
                "sets": [], "git": {}, "primary": "C:/x/" + k}

    def test_all_is_reported_out_of_the_pass(self, monkeypatch):
        """apply_fixes must SAY that consent was granted mid-pass."""
        class _Res:
            returncode = 0
            stdout = stderr = ""
        monkeypatch.setattr(du.subprocess, "run", lambda *a, **k: _Res())
        monkeypatch.setattr(du, "_confirm", lambda *a, **k: "all")
        tally = {}
        du.apply_fixes({"stale-install-metadata": [self._rec("o/a")]},
                       dry_run=False, assume_yes=False, interactive=True,
                       report_applied=tally)
        assert tally["assume_yes"] is True

    def test_answering_n_does_not_grant_consent(self, monkeypatch):
        """The counterpart -- reporting it out must not report it ON."""
        monkeypatch.setattr(du, "_confirm", lambda *a, **k: "no")
        tally = {}
        du.apply_fixes({"stale-install-metadata": [self._rec("o/a")]},
                       dry_run=False, assume_yes=False, interactive=True,
                       report_applied=tally)
        assert tally["assume_yes"] is False

    def test_the_loop_stops_asking_after_all(self, monkeypatch):
        """THE REPORTED CASE: pass 2 must not re-prompt."""
        seen = []

        def _apply(findings, report_applied=None, **kw):
            seen.append(kw.get("assume_yes"))
            if report_applied is not None:
                report_applied.update({"applied": 1, "quit": False,
                                       "assume_yes": True})
            return 0

        monkeypatch.setattr(du, "apply_fixes", _apply)
        monkeypatch.setattr(du, "refresh_matched", lambda *a, **k: None)
        # Without --yes the scoped path requires a terminal to confirm
        # in; pytest has none, so without this the loop never runs and
        # the test passes by asserting nothing.
        monkeypatch.setattr(du.sys.stdin, "isatty", lambda: True)
        r = self._rec("o/a")
        monkeypatch.setattr(du, "classify",
                            lambda *a, **k: {"stale-install-metadata": [r]})
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args())
        assert seen[0] is False, "first pass should honour args.yes"
        assert all(s is True for s in seen[1:]), (
            f"re-asked after 'all' was granted: {seen}")
        assert len(seen) > 1, "loop did not iterate; test proves nothing"

    def test_consent_is_not_invented_when_never_granted(self, monkeypatch):
        """Carrying consent must not manufacture it."""
        seen = []

        def _apply(findings, report_applied=None, **kw):
            seen.append(kw.get("assume_yes"))
            if report_applied is not None:
                report_applied.update({"applied": 1, "quit": False,
                                       "assume_yes": False})
            return 0

        monkeypatch.setattr(du, "apply_fixes", _apply)
        monkeypatch.setattr(du, "refresh_matched", lambda *a, **k: None)
        # Without --yes the scoped path requires a terminal to confirm
        # in; pytest has none, so without this the loop never runs and
        # the test passes by asserting nothing.
        monkeypatch.setattr(du.sys.stdin, "isatty", lambda: True)
        r = self._rec("o/a")
        monkeypatch.setattr(du, "classify",
                            lambda *a, **k: {"stale-install-metadata": [r]})
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args())
        assert all(s is False for s in seen), (
            f"consent appeared without being given: {seen}")


class TestPathQueries:
    """USER FINDING 2026-08-08: `dz dazzle-update .` from a project
    directory listed 12 unrelated repos. `.` went through SUBSTRING
    matching, so a single dot matched every record with a dot anywhere
    in its name or paths.

    A path-shaped term asks "the project HERE" and is now resolved to a
    repository root, then matched by location.
    """

    def test_dot_and_dotdot_are_paths(self):
        assert du._looks_like_path(".")
        assert du._looks_like_path("..")

    def test_explicit_locations_are_paths(self):
        assert du._looks_like_path("C:/code/thing")
        assert du._looks_like_path("./sub/dir")
        assert du._looks_like_path("/abs/dir")

    def test_a_bare_relative_pair_is_treated_as_a_NAME(self):
        """`sub/dir` is ambiguous -- it could be a relative path or an
        owner/repo. It is read as a name unless it actually exists as a
        directory holding a .git, because guessing the other way broke
        `dz dazzle-update DazzleTools/dazzlesum`."""
        assert not du._looks_like_path("sub/dir")
        assert not du._looks_like_path("DazzleTools/dazzlesum")

    def test_a_bare_name_is_still_a_name(self):
        """`dz dazzle-update listall` must keep meaning the project,
        even when a folder of that name exists in the cwd."""
        assert not du._looks_like_path("listall")
        assert not du._looks_like_path("dazzle*")

    def test_wsl_gitdir_is_translated(self):
        got = du._wsl_to_windows("/mnt/c/code/x/.git/worktrees/y")
        assert got == "C:" + "\\" + "code" + "\\" + "x" + "\\" + ".git" \
            + "\\" + "worktrees" + "\\" + "y"
        assert du._wsl_to_windows("/home/user/x") is None

    def test_resolves_a_real_repo_to_its_root(self, tmp_path):
        repo = _real_repo(tmp_path)
        sub = repo / "nested"
        sub.mkdir()
        root, note = du.resolve_path_query(".", cwd=str(sub))
        assert Path(root) == Path(repo)

    def test_wsl_worktree_resolves_via_its_owner(self, tmp_path):
        """The reported case: a worktree whose gitdir git cannot follow
        still names the repository that owns it."""
        wt = tmp_path / "github"
        wt.mkdir()
        (wt / ".git").write_text(
            "gitdir: /mnt/c/code/proj/dazzlesum/.git/worktrees/github\n",
            encoding="utf-8")
        root, note = du.resolve_path_query(".", cwd=str(wt))
        assert root == "C:" + "\\" + "code" + "\\" + "proj" + "\\" + "dazzlesum"
        assert "WSL" in note

    def test_dangling_pointer_says_why(self, tmp_path):
        wt = tmp_path / "orphan"
        wt.mkdir()
        (wt / ".git").write_text(
            "gitdir: " + str(tmp_path / "gone"), encoding="utf-8")
        root, note = du.resolve_path_query(".", cwd=str(wt))
        assert root is None
        assert "does not exist" in note or "not inside a git" in note

    def test_non_repo_directory_says_so(self, tmp_path, monkeypatch):
        """GIT_CEILING_DIRECTORIES is required, not tidiness: pytest's
        tmp_path lives under the user profile, and on this machine the
        HOME DIRECTORY is itself a git repo (it tracks ~/.claude). git
        walks up and finds it, so without a ceiling this test asserts
        against the wrong repository -- and the resolver is right to
        report what git reports."""
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
        root, note = du.resolve_path_query(".", cwd=str(tmp_path))
        assert root is None
        assert "not inside a git repository" in note

    def test_missing_directory_is_reported(self):
        root, note = du.resolve_path_query("definitely-not-here-xyz")
        assert root is None and "not a directory" in note

    def test_match_by_path_finds_the_owning_record(self):
        a = "C:" + "\\" + "code" + "\\" + "a"
        b = "C:" + "\\" + "code" + "\\" + "b"
        recs = {"o/a": {"key": "o/a", "full_name": "o/a", "paths": [a]},
                "o/b": {"key": "o/b", "full_name": "o/b", "paths": [b]}}
        assert set(du.match_by_path(recs, a)) == {"o/a"}

    def test_match_by_path_matches_a_directory_inside_a_checkout(self):
        a = "C:" + "\\" + "code" + "\\" + "a"
        recs = {"o/a": {"key": "o/a", "full_name": "o/a", "paths": [a]}}
        deep = a + "\\" + "src" + "\\" + "deep"
        assert set(du.match_by_path(recs, deep)) == {"o/a"}

    def test_a_sibling_path_does_not_match(self):
        """C:/code/ab must not match a checkout at C:/code/a."""
        a = "C:" + "\\" + "code" + "\\" + "a"
        recs = {"o/a": {"key": "o/a", "full_name": "o/a", "paths": [a]}}
        assert du.match_by_path(recs, a + "b") == {}


class TestUncoveredPathQuery:
    """USER FINDING 2026-08-08, the second half. Standing in the broken
    dazzlesum worktree, `dz dazzle-update .` answered with THREE
    checkouts, none of them the directory the user was in, while `git
    pull` there failed outright -- and `--fix` would have acted on a
    SIBLING checkout, refusing only because that other tree happened to
    be dirty.

    Resolving to the owner is right: it is the only true answer git can
    give about that directory. Presenting the owner's state as "the
    project HERE" without saying so is the substitution this tool exists
    to refuse, and acting elsewhere on the strength of "here" is that
    same substitution with write access.
    """

    def setup_method(self):
        du._PATH_NOTES_SAID.clear()
        du._UNCOVERED_PATH_QUERY.clear()

    teardown_method = setup_method

    def _rec(self, key, paths, installed=None):
        cos = [{"path": p, "excluded": False,
                "git": {"branch": "main", "upstream": "origin/main"}}
               for p in paths]
        return {"key": key, "full_name": key, "cloned": True,
                "excluded": None, "installed": installed, "paths": list(paths),
                "checkouts": cos, "sets": [], "primary": (paths or [None])[0],
                "git": {"branch": "main", "upstream": "origin/main"}}

    # -- the disclosure --

    def test_a_directory_absent_from_the_record_is_disclosed(
            self, tmp_path, monkeypatch, capsys):
        owner = tmp_path / "owner"
        owner.mkdir()
        elsewhere = tmp_path / "wt"
        elsewhere.mkdir()
        monkeypatch.setattr(du, "resolve_path_query",
                            lambda q, cwd=None: (str(owner), None))
        monkeypatch.chdir(elsewhere)
        recs = {"o/a": self._rec("o/a", [str(owner)])}

        got = du.match_records(recs, ["."])
        out = capsys.readouterr().out

        # The owner is still the answer -- the note qualifies it, it
        # does not withhold it.
        assert set(got) == {"o/a"}
        assert "NOT among the checkouts below" in out
        assert str(elsewhere) in out
        assert du._UNCOVERED_PATH_QUERY

    def test_no_disclosure_when_the_directory_IS_the_checkout(
            self, tmp_path, monkeypatch, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.setattr(du, "resolve_path_query",
                            lambda q, cwd=None: (str(repo), None))
        monkeypatch.chdir(repo)
        recs = {"o/a": self._rec("o/a", [str(repo)])}

        du.match_records(recs, ["."])

        assert "NOT among the checkouts" not in capsys.readouterr().out
        assert not du._UNCOVERED_PATH_QUERY

    def test_a_subdirectory_of_a_checkout_is_covered(
            self, tmp_path, monkeypatch, capsys):
        """Standing in `src/` of a checkout is standing IN it."""
        repo = tmp_path / "repo"
        deep = repo / "src" / "pkg"
        deep.mkdir(parents=True)
        monkeypatch.setattr(du, "resolve_path_query",
                            lambda q, cwd=None: (str(repo), None))
        monkeypatch.chdir(deep)
        recs = {"o/a": self._rec("o/a", [str(repo)])}

        du.match_records(recs, ["."])

        assert "NOT among the checkouts" not in capsys.readouterr().out
        assert not du._UNCOVERED_PATH_QUERY

    def test_a_name_query_never_sets_the_flag(self, capsys):
        """`dz dazzle-update dazzlesum` from anywhere is a question
        about a NAME; where the user is standing is irrelevant to it."""
        du.match_records(POP, ["dazzlesum"])
        assert not du._UNCOVERED_PATH_QUERY

    # -- the write guard --

    def test_fix_refuses_when_the_cwd_is_not_a_known_checkout(self, capsys):
        du._UNCOVERED_PATH_QUERY.add(
            "C:" + "\\" + "code" + "\\" + "proj" + "\\" + "github")
        r = self._rec("o/a", ["C:/code/proj/other"])
        rc = du.fix_scoped_to_query({"o/a": r}, {"behind-upstream": [r]},
                                    {"o/a": r}, _Args(dry_run=True))
        out = capsys.readouterr().out
        assert rc == 2
        assert "refusing to --fix from here" in out
        assert "C:" + "\\" + "code" + "\\" + "proj" + "\\" + "github" in out
        assert "APPLYING FIXES" not in out

    def test_the_refusal_names_the_way_out(self, capsys):
        du._UNCOVERED_PATH_QUERY.add(
            "C:" + "\\" + "code" + "\\" + "proj" + "\\" + "github")
        r = self._rec("o/a", ["C:/code/proj/other"])
        du.fix_scoped_to_query({"o/a": r}, {"behind-upstream": [r]},
                               {"o/a": r}, _Args(dry_run=True))
        out = capsys.readouterr().out
        assert "name the repository explicitly" in out

    def test_fix_proceeds_normally_when_the_cwd_is_covered(self, capsys):
        r = self._rec("o/a", ["C:/code/proj"],
                      installed={"name": "a", "path": "C:/code/proj"})
        du.fix_scoped_to_query({"o/a": r}, {"stale-install-metadata": [r]},
                               {"o/a": r}, _Args(dry_run=True))
        out = capsys.readouterr().out
        assert "refusing to --fix from here" not in out
        assert "APPLYING FIXES to o/a" in out

    def test_a_new_run_does_not_inherit_the_previous_run_s_guard(
            self, tmp_path, capsys):
        """main() is importable and re-callable, so a set that describes
        THIS invocation must be cleared by it. Otherwise one path query
        arms the guard and every later call in the process refuses to
        --fix a directory it was never asked about -- the same shape as
        a --scope lens narrating the run after it."""
        du._UNCOVERED_PATH_QUERY.add(r"C:\somewhere\else")
        cfg = tmp_path / "c.json"
        cfg.write_text("{}", encoding="utf-8")

        du.main(["--list-kinds", "--config", str(cfg)])

        assert not du._UNCOVERED_PATH_QUERY, (
            "a stale guard survived into a new invocation")
