"""Unit tests for dazzle-update's ecosystem.py.

ecosystem.py had no test coverage before this session. Highest priority is
_version_tuple: a false "stale install" is worse than a missed one, because
it sends someone reinstalling for no reason. These tests stress it with
git-stamped versions, PEP 440 vs tree spelling, dev/post tails, and
malformed input -- and separately document two real gaps found while doing
so (short-vs-long numeric tuples not treated as equal; a malformed/
unparseable version on the "installed" side of a comparison always sorts
as older than a parseable one, which can produce a false stale-install
finding). Those are reported as bugs, not silently patched here.

Also covers join()'s canonical-identity keying and per-path exclusion
semantics, and confirms (via an xfail characterization test) that a
canonical repo spanning multiple checkouts (e.g. several worktrees of the
same project) currently reports only the FIRST-discovered checkout's git
state -- silently ignoring dirty/ahead/behind state in every other one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ecosystem.py lives directly in dazzle-update/ (a hyphenated directory,
# so it cannot be a package name) and is imported by adding that directory
# to sys.path -- the same idiom dazzle_update.py itself uses.
_HERE = Path(__file__).resolve().parent
_TOOL_DIR = _HERE.parent
sys.path.insert(0, str(_TOOL_DIR))

from ecosystem import (
    _is_older,  # noqa: E402
    EcosystemConfig,
    FINDING_ORDER,
    _version_tuple,
    apply_order,
    classify,
    clean_count,
    join,
    resolve_kinds,
    select_primary,
    sort_records,
)


# -- _version_tuple ----------------------------------------------------

class TestVersionTuple:
    def test_empty_and_none_are_unparseable(self):
        """None means "cannot tell" -- distinct from (), which sorted
        below every real version and drove false stale findings."""
        assert _version_tuple(None) is None
        assert _version_tuple("") is None
        assert _version_tuple("   ") is None

    def test_pep440_and_tree_spelling_are_equal(self):
        """0.10.33a0 (PEP 440) and 0.10.33-alpha (tree spelling) are the
        SAME release -- comparing them naively must not report either as
        stale against the other."""
        assert _version_tuple("0.10.33a0") == _version_tuple("0.10.33-alpha")

    def test_git_stamp_build_metadata_is_stripped(self):
        """Everything from the first '_' or '+' is build metadata."""
        stamped = "0.8.2_main_30-20260719-46503732"
        assert _version_tuple(stamped) == _version_tuple("0.8.2")

    def test_git_stamp_with_prerelease_phase_is_stripped(self):
        stamped = "0.12.5-alpha_main_332-20260722-cff6cf7"
        assert _version_tuple(stamped) == _version_tuple("0.12.5-alpha")
        assert _version_tuple(stamped) == _version_tuple("0.12.5a0")

    def test_plus_build_metadata_is_stripped(self):
        assert _version_tuple("1.2.3+local.dirty") == _version_tuple("1.2.3")

    def test_prerelease_sorts_below_same_numeric_release(self):
        assert _version_tuple("0.8.7a0") < _version_tuple("0.8.7")

    def test_docstring_ordering_claim_0_9_0_above_0_8_7a0(self):
        """The module docstring's own worked example."""
        assert _version_tuple("0.9.0") > _version_tuple("0.8.7a0")

    def test_post_release_sorts_at_or_above_plain_release(self):
        assert _version_tuple("0.12.6.post1") >= _version_tuple("0.12.6")

    def test_malformed_no_leading_digits_is_unparseable(self):
        assert _version_tuple("abc") is None

    def test_v_prefixed_tag_style_is_unparseable(self):
        """A 'v1.2.3'-style tag is still not recognized -- but it now
        reports None ("cannot tell") rather than sorting as oldest."""
        assert _version_tuple("v1.2.3") is None

    # -- gaps found while stress-testing (reported, not fixed) --

    def test_FIXED_short_and_long_numeric_tuples_are_equal(self):
        """PEP 440 treats '1.2' and '1.2.0' as the same release, but this
        loose parser does not pad/truncate numeric tuples before
        comparing, so they compare UNEQUAL (and '1.2' sorts below
        '1.2.0'). Risk: install-behind-published compares against
        arbitrary PyPI version strings, which legitimately vary in
        segment count (many packages publish '4.0' rather than '4.0.0'),
        so this can produce a false install-behind-published finding for
        a package that is actually current.

        FIXED: numeric segments are zero-padded before comparison, so
        these now compare equal. Previously they did not, which could
        report a current package as behind-published purely because PyPI
        publishes '4.0' where the tree says '4.0.0'.
        """
        assert _version_tuple("1.2") == _version_tuple("1.2.0")
        assert _version_tuple("1.2") == _version_tuple("1.2.0.0")
        assert _version_tuple("1.2.1") > _version_tuple("1.2")

    def test_FIXED_prerelease_ordinals_are_distinguished(self):
        """alpha/beta/rc of the SAME numeric release all collapse to the
        same tier (is_pre=True), so a genuine forward move from a0 to b0
        is invisible to the stale/behind-published comparisons. This is
        a false-NEGATIVE risk (a real bump goes unreported), the opposite
        direction from the false-positive risk the caller cares about
        FIXED: alpha < beta < rc, and ordinals within a tier order too.
        """
        assert _version_tuple("0.12.6a0") < _version_tuple("0.12.6b0")
        assert _version_tuple("0.12.6b0") < _version_tuple("0.12.6rc1")
        assert _version_tuple("0.12.6a0") < _version_tuple("0.12.6a1")
        assert _version_tuple("0.12.6rc1") < _version_tuple("0.12.6")

    def test_FIXED_post_release_ordinals_are_distinguished(self):
        assert _version_tuple("0.12.6.post1") < _version_tuple("0.12.6.post2")
        assert _version_tuple("0.12.6") < _version_tuple("0.12.6.post1")

    def test_FIXED_unparseable_version_never_claims_staleness(self):
        """() < any parseable tuple is always True in Python's tuple
        ordering, so an installed version string this parser cannot read
        (e.g. a 'v'-prefixed tag, or genuinely empty metadata) ALWAYS
        compares as older than a parseable source/published version --
        even when the real install is current or newer. This is the
        concrete mechanism behind a false stale-install-metadata /
        install-behind-published finding driven by formatting alone, not
        real staleness. See TestClassify::test_GAP_malformed_installed_version_forces_false_stale
        for the effect at classify() level.

        FIXED: _version_tuple returns None for unparseable input and
        _is_older() returns False whenever either side is None. "I cannot
        tell" must never render as "out of date".
        """
        assert _version_tuple("v1.2.3") is None
        assert _version_tuple("garbage-not-a-version") is None
        assert _is_older("v1.2.3", "1.2.3") is False
        assert _is_older("garbage-not-a-version", "0.0.1") is False
        # ...and a genuine comparison still works
        assert _is_older("0.8.7a0", "0.9.0") is True


# -- join() --------------------------------------------------------------

def _cfg(**kw):
    kw.setdefault("namespaces", ["DazzleTools"])
    return EcosystemConfig(**kw)


class TestJoin:
    def test_keys_by_canonical_identity_not_url(self):
        """A clone whose configured slug still names a pre-transfer
        namespace must land on the SAME record as the org listing under
        its canonical full_name -- that's the whole point of join()."""
        org_repos = [{"full_name": "DazzleTools/dazzlesum"}]
        local_repos = [{
            "path": r"C:\code\dazzlesum",
            "slug": "djdarcy/dazzlesum",         # pre-transfer, stale URL
            "full_name": "DazzleTools/dazzlesum",  # resolved canonical name
            "redirected": True,
            "git": {"branch": "main", "upstream": "origin/main",
                    "ahead": 0, "behind": 0, "dirty_count": 0,
                    "untracked_count": 0},
        }]
        records = join(org_repos, local_repos, [], _cfg())
        assert len(records) == 1
        r = records["dazzletools/dazzlesum"]
        assert r["in_namespace"] is True
        assert r["cloned"] is True
        assert r["redirected"] is True
        assert r["configured_slugs"] == ["djdarcy/dazzlesum"]

    def test_record_excluded_only_when_every_path_excluded(self):
        """One stale sibling (a baks/ snapshot) must not suppress a live
        checkout sharing its canonical key -- excluding must require ALL
        paths to be excluded, not just one."""
        cfg = _cfg(excludes=["*/baks/*"])
        local_repos = [
            {"path": r"C:\code\proj", "full_name": "Org/proj", "slug": "Org/proj"},
            {"path": r"C:\code\baks\proj-2025", "full_name": "Org/proj",
             "slug": "Org/proj"},
        ]
        records = join([], local_repos, [], cfg)
        r = records["org/proj"]
        assert len(r["excluded_paths"]) == 1
        assert r["excluded"] is None  # NOT excluded -- live path survives

    def test_record_excluded_when_all_paths_excluded(self):
        cfg = _cfg(excludes=["*/baks/*"])
        local_repos = [
            {"path": r"C:\code\baks\proj-2025", "full_name": "Org/proj",
             "slug": "Org/proj"},
            {"path": r"C:\code\baks\proj-2026", "full_name": "Org/proj",
             "slug": "Org/proj"},
        ]
        records = join([], local_repos, [], cfg)
        r = records["org/proj"]
        assert len(r["excluded_paths"]) == 2 == len(r["paths"])
        assert r["excluded"] == "path excluded by policy"

    def test_last_activity_aggregates_max_across_paths(self):
        """last_activity DOES correctly take the max across every path --
        unlike git state (see test_GAP_multi_worktree_git_state_first_wins),
        which does not. Included here as a contrast."""
        local_repos = [
            {"path": r"C:\a", "full_name": "Org/proj", "slug": "Org/proj",
             "last_activity": 100},
            {"path": r"C:\b", "full_name": "Org/proj", "slug": "Org/proj",
             "last_activity": 999},
        ]
        records = join([], local_repos, [], _cfg())
        assert records["org/proj"]["last_activity"] == 999

    def test_FIXED_multi_worktree_reports_the_right_checkout(self):
        """Regression test for the attribution bug.

        join() used to keep only the FIRST discovered checkout's git
        state (`if entry.get('git') and not r['git']`), so whichever
        worktree sorted first alphabetically spoke for the whole repo.
        A record could report 'clean' while a sibling held 7 dirty files
        and 3 unpushed commits -- and --fix would have fast-forwarded
        that sibling, merging main's material into a feature branch.

        FIXED: every checkout is retained; repo-scoped findings ask the
        primary (pip-installed first), checkout-scoped findings ask all.
        """
        local_repos = [
            {  # discovered first (alphabetically: dev < github)
                "path": r"C:\code\dazzlecmd\dev",
                "slug": "DazzleTools/dazzlecmd", "full_name": "DazzleTools/dazzlecmd",
                "git": {"branch": "dev", "upstream": "origin/dev", "ahead": 0,
                        "behind": 0, "dirty_count": 0, "untracked_count": 0},
                "last_activity": 1000,
            },
            {  # discovered second -- this is the one that needs attention
                "path": r"C:\code\dazzlecmd\github",
                "slug": "DazzleTools/dazzlecmd", "full_name": "DazzleTools/dazzlecmd",
                "git": {"branch": "main", "upstream": "origin/main", "ahead": 3,
                        "behind": 0, "dirty_count": 7, "untracked_count": 2},
                "last_activity": 2000,
            },
        ]
        cfg = _cfg(namespaces=["DazzleTools"])
        records = join([{"full_name": "DazzleTools/dazzlecmd"}], local_repos, [], cfg)
        findings = classify(records, cfg)
        key = "dazzletools/dazzlecmd"
        fired = {kind for kind, items in findings.items()
                 if any(it["key"] == key for it in items)}
        # DESIRED behavior: the dirty, unpushed worktree's state should be
        # visible in the findings. Currently it is not (see xfail reason).
        assert "dirty" in fired
        assert "unpushed" in fired
        assert "clean" not in fired


# -- classify() ------------------------------------------------------------

class TestClassify:
    def test_source_missing_when_install_path_gone(self, tmp_path):
        """join() attaches an install to a record only by EXACT path
        match against that record's known paths -- so the local_repos
        entry and the install entry must share the same path string for
        this to land on one record. (tmp_path/"gone" is deliberately
        never created.)"""
        cfg = _cfg()
        missing = str(tmp_path / "gone")
        local_repos = [{"path": missing, "full_name": "Org/proj",
                        "slug": "Org/proj",
                        "git": {"branch": "main"}}]
        installs = [{"name": "proj", "version": "1.0.0", "path": missing}]
        records = join([], local_repos, installs, cfg)
        findings = classify(records, cfg)
        keys = {r["key"] for r in findings["source-missing"]}
        assert "org/proj" in keys

    def test_stale_install_metadata(self, tmp_path):
        cfg = _cfg()
        proj = tmp_path / "proj"
        proj.mkdir()
        local_repos = [{"path": str(proj), "full_name": "Org/proj",
                        "slug": "Org/proj", "git": {"branch": "main"}}]
        installs = [{"name": "proj", "version": "0.9.0", "path": str(proj)}]
        records = join([], local_repos, installs, cfg,
                       source_versions={records_norm(proj): "1.0.0"})
        findings = classify(records, cfg)
        keys = {r["key"] for r in findings["stale-install-metadata"]}
        assert "org/proj" in keys

    def test_install_behind_published(self, tmp_path):
        cfg = _cfg()
        proj = tmp_path / "proj"
        proj.mkdir()
        local_repos = [{"path": str(proj), "full_name": "Org/proj",
                        "slug": "Org/proj", "git": {"branch": "main"}}]
        installs = [{"name": "proj", "version": "0.9.0", "path": str(proj)}]
        records = join([], local_repos, installs, cfg,
                       published={"proj": "2.0.0"})
        findings = classify(records, cfg)
        keys = {r["key"] for r in findings["install-behind-published"]}
        assert "org/proj" in keys

    def test_private_branch_is_local_only_not_no_upstream(self):
        """repokit projects keep `private` unpushed on purpose."""
        cfg = _cfg()
        local_repos = [{"path": r"C:\proj", "full_name": "Org/proj",
                        "slug": "Org/proj",
                        "git": {"branch": "private", "upstream": None,
                                "ahead": 0, "behind": 0, "dirty_count": 0}}]
        records = join([], local_repos, [], cfg)
        findings = classify(records, cfg)
        assert not any(r["key"] == "org/proj" for r in findings["no-upstream"])

    def test_no_upstream_when_not_local_only_branch(self):
        cfg = _cfg()
        local_repos = [{"path": r"C:\proj", "full_name": "Org/proj",
                        "slug": "Org/proj",
                        "git": {"branch": "main", "upstream": None,
                                "ahead": 0, "behind": 0, "dirty_count": 0}}]
        records = join([], local_repos, [], cfg)
        findings = classify(records, cfg)
        assert any(r["key"] == "org/proj" for r in findings["no-upstream"])

    def test_dirty_and_unpushed_both_fire_independently(self):
        cfg = _cfg()
        local_repos = [{"path": r"C:\proj", "full_name": "Org/proj",
                        "slug": "Org/proj",
                        "git": {"branch": "main", "upstream": "origin/main",
                                "ahead": 2, "behind": 0, "dirty_count": 3,
                                "untracked_count": 0}}]
        records = join([], local_repos, [], cfg)
        findings = classify(records, cfg)
        assert any(r["key"] == "org/proj" for r in findings["dirty"])
        assert any(r["key"] == "org/proj" for r in findings["unpushed"])

    def test_excluded_by_policy_short_circuits_all_other_findings(self):
        """An excluded record should not ALSO show up as dirty/unpushed/etc."""
        cfg = _cfg(excludes=["*/baks/*"])
        local_repos = [{"path": r"C:\baks\proj", "full_name": "Org/proj",
                        "slug": "Org/proj",
                        "git": {"branch": "main", "upstream": None,
                                "ahead": 0, "behind": 0, "dirty_count": 5}}]
        records = join([], local_repos, [], cfg)
        findings = classify(records, cfg)
        assert any(r["key"] == "org/proj" for r in findings["excluded-by-policy"])
        for kind in ("dirty", "no-upstream", "unpushed"):
            assert not any(r["key"] == "org/proj" for r in findings[kind])

    def test_clean_when_nothing_flagged(self):
        cfg = _cfg()
        local_repos = [{"path": r"C:\proj", "full_name": "Org/proj",
                        "slug": "Org/proj",
                        "git": {"branch": "main", "upstream": "origin/main",
                                "ahead": 0, "behind": 0, "dirty_count": 0,
                                "untracked_count": 0}}]
        records = join([], local_repos, [], cfg)
        findings = classify(records, cfg)
        assert any(r["key"] == "org/proj" for r in findings["clean"])
        # NOTE: clean_count() itself is separately known-buggy for this
        # exact case -- see TestCleanCount::test_GAP_clean_count_undercounts_clean_repos.
        # Not asserted here to keep this test scoped to classify()'s bucketing.

    def test_FIXED_malformed_installed_version_does_not_force_false_stale(
            self, tmp_path):
        """classify()-level regression test for the false stale finding.

        An installed version string the parser cannot read (here a
        'v'-prefixed tag) used to compare as "definitely oldest", firing
        stale-install-metadata purely from formatting. A false "you are
        out of date" is worse than a missed one: it sends someone
        reinstalling for no reason.

        FIXED: unknown compares as unknown, so no finding is emitted.
        """
        cfg = _cfg()
        proj = tmp_path / "proj"
        proj.mkdir()
        local_repos = [{"path": str(proj), "full_name": "Org/proj",
                        "slug": "Org/proj", "git": {"branch": "main"}}]
        installs = [{"name": "proj", "version": "v1.0.0", "path": str(proj)}]
        records = join([], local_repos, installs, cfg,
                       source_versions={records_norm(proj): "1.0.0"})
        findings = classify(records, cfg)
        keys = {r["key"] for r in findings["stale-install-metadata"]}
        assert "org/proj" not in keys

    def test_genuinely_stale_install_is_still_reported(self, tmp_path):
        """The fix must not silence real staleness -- the counterpart to
        the test above, so 'never report anything' cannot pass both."""
        cfg = _cfg()
        proj = tmp_path / "proj2"
        proj.mkdir()
        local_repos = [{"path": str(proj), "full_name": "Org/proj2",
                        "slug": "Org/proj2", "git": {"branch": "main"}}]
        installs = [{"name": "proj2", "version": "0.8.7a0", "path": str(proj)}]
        records = join([], local_repos, installs, cfg,
                       source_versions={records_norm(proj): "0.9.0"})
        findings = classify(records, cfg)
        keys = {r["key"] for r in findings["stale-install-metadata"]}
        assert "org/proj2" in keys


class TestCleanCount:
    def test_FIXED_clean_count_matches_the_clean_bucket(self):
        """Regression test for the footer that lied on every run.

        clean_count() used to sum record keys across every findings
        bucket except 'excluded-by-policy' -- INCLUDING 'clean' itself --
        and return total_in_scope minus that set. A clean record was
        therefore subtracted from its own count, so the footer
        ('N repos clean and current.') printed 0 where it should have
        printed 2. Observed live: '24 repos clean and current' on a box
        where zero scanned git repos were actually clean.

        FIXED: the count now reads the clean bucket directly. Deriving it
        by subtraction also assumed every in-scope record was either
        flagged or clean, which is false for install-only records that
        hit no check at all.
        """
        cfg = _cfg()
        local_repos = [
            {"path": r"C:\dirty", "full_name": "Org/dirty", "slug": "Org/dirty",
             "git": {"branch": "main", "upstream": "origin/main", "ahead": 0,
                     "behind": 0, "dirty_count": 5, "untracked_count": 0}},
            {"path": r"C:\clean1", "full_name": "Org/clean1", "slug": "Org/clean1",
             "git": {"branch": "main", "upstream": "origin/main", "ahead": 0,
                     "behind": 0, "dirty_count": 0, "untracked_count": 0}},
            {"path": r"C:\clean2", "full_name": "Org/clean2", "slug": "Org/clean2",
             "git": {"branch": "main", "upstream": "origin/main", "ahead": 0,
                     "behind": 0, "dirty_count": 0, "untracked_count": 0}},
        ]
        records = join([], local_repos, [], cfg)
        findings = classify(records, cfg)
        assert len(findings["clean"]) == 2
        assert clean_count(records, findings) == 2


def records_norm(path):
    """Mirror ecosystem.norm() for building source_versions test fixtures
    without importing the private helper under a different name."""
    from ecosystem import norm
    return norm(path)


# -- apply_order() ---------------------------------------------------------

class TestApplyOrder:
    def test_empty_configured_returns_built_in_order(self):
        order, unknown = apply_order(None)
        assert order == FINDING_ORDER
        assert unknown == []

        order, unknown = apply_order([])
        assert order == FINDING_ORDER
        assert unknown == []

    def test_partial_list_puts_named_first_rest_follows_built_in_order(self):
        """Naming three kinds must not hide the other kinds -- that's
        what --only/--skip are for. A config 'order' only reorders."""
        order, unknown = apply_order(["dirty", "unpushed"])
        assert order[:2] == ["dirty", "unpushed"]
        assert set(order) == set(FINDING_ORDER)
        assert len(order) == len(FINDING_ORDER)
        # everything else follows in built-in order, dirty/unpushed removed
        expected_tail = [k for k in FINDING_ORDER if k not in ("dirty", "unpushed")]
        assert order[2:] == expected_tail
        assert unknown == []

    def test_unknown_names_reported_separately_not_silently_dropped(self):
        order, unknown = apply_order(["dirty", "not-a-real-kind"])
        assert unknown == ["not-a-real-kind"]
        assert "not-a-real-kind" not in order
        assert order[0] == "dirty"

    def test_aliases_resolved_before_ordering(self):
        order, unknown = apply_order(["ahead", "pull"])  # aliases
        assert order[:2] == ["unpushed", "behind-upstream"]
        assert unknown == []


# -- resolve_kinds() ---------------------------------------------------------

class TestResolveKinds:
    def test_canonical_names_pass_through(self):
        kinds, bad = resolve_kinds(["dirty", "clean"])
        assert kinds == ["dirty", "clean"]
        assert bad == []

    def test_aliases_map_to_canonical(self):
        kinds, bad = resolve_kinds(["behind", "pull", "ahead", "push",
                                    "ok", "current", "missing", "clone"])
        assert kinds == ["behind-upstream", "unpushed", "clean", "not-cloned"]
        assert bad == []

    def test_case_and_whitespace_insensitive(self):
        kinds, bad = resolve_kinds(["  DIRTY ", "Behind"])
        assert kinds == ["dirty", "behind-upstream"]
        assert bad == []

    def test_unknown_names_reported_as_bad(self):
        kinds, bad = resolve_kinds(["dirty", "bogus", "also-bogus"])
        assert kinds == ["dirty"]
        assert bad == ["bogus", "also-bogus"]

    def test_duplicates_deduplicated(self):
        kinds, bad = resolve_kinds(["dirty", "dirty", "behind"])
        assert kinds == ["dirty", "behind-upstream"]

    def test_none_and_empty_input(self):
        assert resolve_kinds(None) == ([], [])
        assert resolve_kinds([]) == ([], [])


# -- sort_records() ---------------------------------------------------------

def _rec(name, activity):
    return {"key": name.lower(), "full_name": name, "last_activity": activity}


class TestSortRecords:
    def test_newest_default_sorts_descending_by_activity(self):
        items = [_rec("a", 100), _rec("b", 300), _rec("c", 200)]
        out = sort_records(items, "newest")
        assert [r["full_name"] for r in out] == ["b", "c", "a"]

    def test_oldest_sorts_ascending_by_activity(self):
        items = [_rec("a", 100), _rec("b", 300), _rec("c", 200)]
        out = sort_records(items, "oldest")
        assert [r["full_name"] for r in out] == ["a", "c", "b"]

    def test_name_sorts_alphabetically_case_insensitive(self):
        items = [_rec("Zeta", 1), _rec("alpha", 2), _rec("Beta", 3)]
        out = sort_records(items, "name")
        assert [r["full_name"] for r in out] == ["alpha", "Beta", "Zeta"]

    def test_records_with_no_activity_sort_last_when_newest(self):
        items = [_rec("has-date", 100), _rec("no-date", None)]
        out = sort_records(items, "newest")
        assert out[-1]["full_name"] == "no-date"

    def test_records_with_no_activity_sort_last_when_oldest(self):
        items = [_rec("has-date", 100), _rec("no-date", None)]
        out = sort_records(items, "oldest")
        assert out[-1]["full_name"] == "no-date"

    def test_default_mode_is_newest(self):
        items = [_rec("a", 100), _rec("b", 300)]
        assert sort_records(items) == sort_records(items, "newest")


# -- select_primary() ----------------------------------------------------

class TestSelectPrimary:
    """Which checkout speaks for a repo that has several.

    Found by an independent reviewer reading the code, then confirmed
    empirically: an earlier version returned the FIRST default-branch
    match it walked, which is directory order. That reintroduced the
    arbitrary pick the function exists to eliminate, one rule deeper.
    The live dazzlecmd layout has three tracking checkouts on `main`.
    """

    @staticmethod
    def _ck(path, branch, upstream, dirty=0, excluded=False):
        return {"path": path, "excluded": excluded,
                "git": {"branch": branch, "upstream": upstream,
                        "dirty_count": dirty, "untracked_count": 0}}

    def _rec(self, checkouts, installed=None, excluded_paths=()):
        return {"checkouts": checkouts, "installed": installed,
                "excluded_paths": list(excluded_paths)}

    def test_no_checkouts(self):
        assert select_primary(self._rec([]))[0] is None

    def test_single_checkout_wins_trivially(self):
        c = self._ck(r"C:\a", "main", "origin/main")
        got, why = select_primary(self._rec([c]))
        assert got is c and "only checkout" in why

    def test_pip_installed_path_beats_a_tracking_sibling(self):
        """Rule 1 over rule 2, deliberately.

        For two real repos the INSTALLED checkout has no upstream while a
        tidier sibling has one. "What does this environment run" is
        answered by pip, not by which copy looks cleaner.
        """
        installed = self._ck(r"C:\a\local", "private", None)
        sibling = self._ck(r"C:\a\github", "main", "origin/main")
        rec = self._rec([sibling, installed],
                        installed={"path": r"C:\a\local"})
        got, why = select_primary(rec)
        assert got is installed
        assert "pip-installed" in why

    def test_pip_path_matches_case_insensitively_on_windows(self):
        c = self._ck(r"C:\Code\Proj", "main", "origin/main")
        rec = self._rec([c], installed={"path": r"c:\code\proj"})
        assert select_primary(rec)[0] is c

    def test_sole_tracking_checkout_wins(self):
        untracked = self._ck(r"C:\a\feat", "feature/x", None)
        tracked = self._ck(r"C:\a\github", "main", "origin/main")
        got, why = select_primary(self._rec([untracked, tracked]))
        assert got is tracked and "only checkout with an upstream" in why

    def test_two_tracking_checkouts_both_on_main_REFUSES(self):
        """The regression this class was written for."""
        a = self._ck(r"C:\a\github", "main", "origin/main")
        b = self._ck(r"C:\a\mirror", "main", "origin/main")
        got, why = select_primary(self._rec([a, b]))
        assert got is None, "picked arbitrarily instead of refusing"
        assert "ambiguous" in why

    def test_tracking_checkouts_on_distinct_branches_picks_the_default(self):
        feat = self._ck(r"C:\a\feat", "feature/x", "origin/feature/x")
        main = self._ck(r"C:\a\github", "main", "origin/main")
        got, why = select_primary(self._rec([feat, main]))
        assert got is main and "only tracking checkout on main" in why

    def test_tracking_but_none_on_a_default_branch_refuses(self):
        a = self._ck(r"C:\a\x", "feature/a", "origin/feature/a")
        b = self._ck(r"C:\a\y", "feature/b", "origin/feature/b")
        got, why = select_primary(self._rec([a, b]))
        assert got is None and "none on a default branch" in why

    def test_excluded_checkouts_are_not_eligible(self):
        live = self._ck(r"C:\a\github", "main", "origin/main")
        stale = self._ck(r"C:\a\github - Copy", "main", "origin/main")
        rec = self._rec([stale, live], excluded_paths=[r"C:\a\github - Copy"])
        got, why = select_primary(rec)
        assert got is live

    def test_all_excluded_falls_back_rather_than_returning_nothing(self):
        """If every path is excluded the record is excluded anyway, but
        select_primary must not crash or invent a checkout."""
        a = self._ck(r"C:\a\one", "main", "origin/main")
        rec = self._rec([a], excluded_paths=[r"C:\a\one"])
        got, _ = select_primary(rec)
        assert got is a

    def test_installed_path_not_among_checkouts_falls_through(self):
        """A broken editable pointing outside the scan must not win."""
        c = self._ck(r"C:\a\github", "main", "origin/main")
        rec = self._rec([c], installed={"path": r"C:\somewhere\else"})
        got, why = select_primary(rec)
        assert got is c
        assert "pip-installed" not in why
