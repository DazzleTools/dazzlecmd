"""Churn filtering -- hook-restamped files must not read as work.

USER FINDING 2026-08-02: `dz dazzle-update` listed dazzlelink and
dazzle-linklib as DIRTY when the only outstanding change in each was
`_version.py`, which the repokit commit hook rewrites with build
metadata after every commit. A report that counts the tooling's own
stamps as dirt trains the reader to ignore the dirty section.

Design: reclassify, never hide. Churn moves out of dirty_count into its
own count, rows show it as 'N churn', a NOTE names how many repos were
affected, a repo with churn AND a real edit stays dirty, and --fix
still refuses to pull over churn (the pull usually touches the very
file the hook restamps).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent.parent))

import dazzle_update as du  # noqa: E402
from ecosystem import (  # noqa: E402
    DEFAULT_CHURN_FILES,
    EcosystemConfig,
    classify,
)


def _record(key, dirty=0, untracked=0, churn=0, ahead=0, behind=0,
            upstream="origin/main"):
    git = {"branch": "main", "upstream": upstream, "ahead": ahead,
           "behind": behind, "dirty_count": dirty,
           "untracked_count": untracked, "churn_count": churn}
    return {
        "key": key, "full_name": key, "paths": [f"C:/x/{key}"],
        "configured_slugs": [], "redirected": False, "cloned": True,
        "in_namespace": True, "installed": None, "source_version": None,
        "published": None, "declared_dist": None, "pypi_owned": None,
        "excluded": None, "excluded_paths": [], "third_party": False,
        "foreign": False, "errors": [], "last_activity": None,
        "git": git, "primary": f"C:/x/{key}", "primary_reason": "only",
        "checkouts": [{"path": f"C:/x/{key}", "git": git,
                       "excluded": False}],
        "sets": [],
    }


class TestConfigMerge:
    def test_default_is_both_stamp_conventions(self):
        """Both MEASURED on a real machine (2026-08-02): _version.py is
        the current repokit stamp, version.py the older convention the
        DazzleNodes-era projects still use."""
        cfg = EcosystemConfig()
        assert cfg.churn_files == DEFAULT_CHURN_FILES
        assert cfg.churn_files == ["_version.py", "version.py"]

    def test_configured_merges_with_default(self):
        cfg = EcosystemConfig(churn_files=["*.build-id"])
        assert cfg.churn_files == ["_version.py", "version.py", "*.build-id"]

    def test_replace_uses_only_configured(self):
        cfg = EcosystemConfig(churn_files=["mine.txt"],
                              churn_files_replace=True)
        assert cfg.churn_files == ["mine.txt"]

    def test_replace_with_empty_disables(self):
        cfg = EcosystemConfig(churn_files=[], churn_files_replace=True)
        assert cfg.churn_files == []


class TestClassification:
    def test_churn_only_repo_is_clean(self):
        records = {"a": _record("o/a", churn=1)}
        findings = classify(records, EcosystemConfig())
        assert records["a"] not in findings["dirty"]
        assert records["a"] in findings["clean"]

    def test_churn_plus_real_edit_stays_dirty(self):
        """The trap this feature must not fall into: a real edit beside
        the stamp must never read clean."""
        records = {"a": _record("o/a", dirty=1, churn=1)}
        findings = classify(records, EcosystemConfig())
        assert records["a"] in findings["dirty"]


class TestRendering:
    def test_row_shows_churn_bit(self):
        name, detail = du._fmt_repo(_record("o/a", churn=2))
        assert "2 churn" in detail

    def test_note_line_reports_reclassification(self, capsys):
        meta = {"namespace_count": 1, "org_repo_count": 1,
                "cloned_count": 1, "install_count": 0,
                "gh_detail": "test", "published_detail": "skipped",
                "roots": ["X"], "errors": [], "clean": 1,
                "churn_repos": 2, "churn_files": ["_version.py"]}
        du.render_text({}, {"clean": [_record("o/a", churn=1)]}, meta)
        out = capsys.readouterr().out
        assert "auto-stamp churn in 2 repo(s) (_version.py)" in out
        assert "not counted dirty" in out

    def test_footer_accounts_for_invisible_churn_only_repos(self, capsys):
        """USER FINDING 2026-08-02 (second round): churn-only repos land
        in `clean`, whose section is hidden by default -- so they were
        visible NOWHERE. The footer must account for them."""
        meta = {"namespace_count": 1, "org_repo_count": 2,
                "cloned_count": 2, "install_count": 0,
                "gh_detail": "test", "published_detail": "skipped",
                "roots": ["X"], "errors": [], "clean": 2}
        findings = {"clean": [_record("o/a", churn=1), _record("o/b")]}
        du.render_text({}, findings, meta)
        out = capsys.readouterr().out
        assert ("2 repos clean and current "
                "(1 with only auto-stamp churn).") in out

    def test_footer_unchanged_when_no_churn(self, capsys):
        meta = {"namespace_count": 1, "org_repo_count": 1,
                "cloned_count": 1, "install_count": 0,
                "gh_detail": "test", "published_detail": "skipped",
                "roots": ["X"], "errors": [], "clean": 1}
        du.render_text({}, {"clean": [_record("o/a")]}, meta)
        assert "1 repos clean and current." in capsys.readouterr().out

    def test_count_churn_repos_skips_out_of_scope(self):
        records = {
            "a": _record("o/a", churn=1),
            "b": _record("o/b", churn=1),
            "c": _record("o/c", churn=1),
        }
        records["b"]["excluded"] = "path excluded by policy"
        records["c"]["third_party"] = True
        assert du.count_churn_repos(records) == 1


class TestFixGate:
    def test_fix_refuses_pull_over_churn(self, capsys):
        r = _record("o/a", churn=1, behind=2)
        rc = du.apply_fixes({"behind-upstream": [r]}, dry_run=True,
                            assume_yes=True, interactive=False)
        out = capsys.readouterr().out
        assert "auto-stamp churn present" in out
        assert rc == 0

    def test_fix_still_refuses_plain_dirty_without_falling_through(self,
                                                                   capsys):
        """REGRESSION: adding the churn branch briefly swallowed the
        dirty branch's `continue`, so a dirty repo was refused AND then
        re-evaluated -- one condition away from being pulled anyway."""
        r = _record("o/a", dirty=1, behind=2)
        du.apply_fixes({"behind-upstream": [r]}, dry_run=True,
                       assume_yes=True, interactive=False)
        out = capsys.readouterr().out
        assert out.count("o/a") == 1
        assert "dirty tree" in out
        assert "Would pull" not in out and "pulled" not in out


class TestSetupGuard:
    """A scan that finds nothing must not read as a clean machine.

    On a new box the one machine-specific setting is `roots`; when it
    points at the wrong place the tool found 0 repos, knew 125 existed
    in the user's namespaces, and printed "Nothing needs attention".
    """

    def _meta(self, cloned, org=125, **kw):
        m = {"namespace_count": 11, "org_repo_count": org,
             "cloned_count": cloned, "install_count": 0,
             "gh_detail": "test", "published_detail": "skipped",
             "roots": ["D:/wrong"], "errors": [], "clean": 0}
        m.update(kw)
        return m

    def test_zero_repos_prints_setup_help(self, capsys):
        du.render_text({}, {}, self._meta(0))
        out = capsys.readouterr().out
        assert "SETUP" in out
        assert "no git repos found under D:/wrong" in out
        assert "125 repo(s) exist in your namespaces" in out
        assert "--init-config" in out

    def test_zero_repos_footer_does_not_claim_calm(self, capsys):
        du.render_text({}, {}, self._meta(0))
        out = capsys.readouterr().out
        assert "Nothing needs attention." not in out
        assert "Nothing was scanned" in out

    def test_nothing_scanned_outranks_the_no_fetch_caveat(self, capsys):
        """Mentioning stale behind-counts first implies a scan happened."""
        du.render_text({}, {}, self._meta(0, stale_behind=True))
        out = capsys.readouterr().out
        assert "Nothing was scanned" in out
        assert "behind-counts were not refreshed" not in out

    def test_no_namespace_info_still_advises(self, capsys):
        """Unauthenticated gh: we cannot say repos exist, but the roots
        advice still applies."""
        du.render_text({}, {}, self._meta(0, org=0))
        out = capsys.readouterr().out
        assert "SETUP" in out
        assert "exist in your namespaces" not in out

    def test_populated_scan_prints_no_setup_block(self, capsys):
        du.render_text({}, {}, self._meta(42))
        assert "SETUP" not in capsys.readouterr().out
