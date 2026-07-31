"""Unit tests for working sets -- the measured rule language.

The fixtures here are not invented: they encode the ADJUDICATED ground
truth from the set-rule-language design doc. The user's verbatim
verdicts (2026-07-31) became these assertions, per the rule that a
correction carried only in prose can silently regress while a correction
that became a named test cannot:

  * wtf-privacy and wtf-restarted are NOT in the dazzle set, but ARE in
    the wtf set -- "overlap is fine as a lens", and no manifest declares
    them into dazzle.
  * wtf-windows is in BOTH: wtf.kit.json declares it into dazzle, the
    wtf product-line glob carries it into wtf.
  * DPAPIck3 is in dazzle purely by declaration (a tool requires
    dpapick3); no naming rule can see it.
  * dazzle-claude-code-config and the history-viewer are in dazzle via
    exact include ("very much part of our dazzle ecosystem" / "a fork
    that our claude tools rely on").
  * dazzle-claude-vault, dazzle-comfyui-frame-interpolation,
    dazzle-opentimestamps-client, dazzle-python-bitcoinlib are OUT --
    dazzle-adjacent, each with its own condition for joining later.
  * DazzleNodes and DazzleML repos are OUT of dazzle: adjacent sets,
    not this one. Naming them in was the original design's largest
    measured error (0.50 precision).
  * */.github is excluded even from an org the set names.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent.parent))

from sets import (  # noqa: E402
    DeclaredMembers,
    SetDefinition,
    annotate,
    kit_sources,
    load_sets,
    match_repo,
    tool_dependencies,
)


# -- match_repo ----------------------------------------------------------

class TestMatchRepo:
    def test_case_folded_both_sides(self):
        assert match_repo("DazzleTools/dazzlecmd", ["dazzletools/*"])
        assert match_repo("dazzletools/dazzlecmd", ["DazzleTools/*"])

    def test_exact_and_glob(self):
        assert match_repo("djdarcy/wtf-windows", ["djdarcy/wtf-*"])
        assert not match_repo("djdarcy/wtfoo", ["djdarcy/wtf-*"])

    def test_empty_inputs(self):
        assert not match_repo(None, ["*"])
        assert not match_repo("", ["*"])
        assert not match_repo("a/b", [])
        assert not match_repo("a/b", None)


# -- the adjudicated ground truth ---------------------------------------

def dazzle_set():
    """The worked example shipped by --init-config, verbatim."""
    return SetDefinition(
        "dazzle",
        namespaces=["DazzleTools/*", "DazzleLib/*"],
        include=["djdarcy/dazzle-claude-code-config",
                 "djdarcy/dazzle-claude-code-history-viewer"],
        exclude=["*/.github"],
        declared=True)


def wtf_set():
    return SetDefinition("wtf", namespaces=["djdarcy/wtf-*"])


def fake_declared():
    """What the real manifests declare, held constant for the tests."""
    return DeclaredMembers(slugs={"djdarcy/wtf-windows"},
                           dists={"dpapick3", "unctools"})


class TestAdjudicatedVerdicts:
    dz = dazzle_set()
    wtf = wtf_set()
    dec = fake_declared()

    def in_dazzle(self, name):
        return self.dz.contains(name, declared_members=self.dec)

    def test_wtf_privacy_out_of_dazzle_but_in_wtf(self):
        assert not self.in_dazzle("djdarcy/wtf-privacy")
        assert not self.in_dazzle("djdarcy/wtf-restarted")
        assert self.wtf.contains("djdarcy/wtf-privacy")
        assert self.wtf.contains("djdarcy/wtf-restarted")

    def test_wtf_windows_in_both(self):
        assert self.in_dazzle("djdarcy/wtf-windows")
        assert self.wtf.contains("djdarcy/wtf-windows")

    def test_dpapick3_in_by_declaration_only(self):
        assert self.in_dazzle("djdarcy/DPAPIck3")
        # ... and it is genuinely declaration doing the work:
        assert not self.dz.contains("djdarcy/DPAPIck3", declared_members=None)

    def test_claude_pair_in_by_exact_include(self):
        assert self.in_dazzle("djdarcy/dazzle-claude-code-config")
        assert self.in_dazzle("djdarcy/dazzle-claude-code-history-viewer")

    def test_adjacent_four_are_out(self):
        for name in ("djdarcy/dazzle-claude-vault",
                     "djdarcy/dazzle-comfyui-frame-interpolation",
                     "djdarcy/dazzle-opentimestamps-client",
                     "djdarcy/dazzle-python-bitcoinlib"):
            assert not self.in_dazzle(name), name

    def test_adjacent_orgs_are_out(self):
        assert not self.in_dazzle("DazzleNodes/ComfyUI-DazzleKSampler")
        assert not self.in_dazzle("DazzleML/dazzle-claude-code-config")

    def test_core_body_is_in(self):
        assert self.in_dazzle("DazzleTools/dazzlecmd")
        assert self.in_dazzle("DazzleLib/dazzlecmd-lib")

    def test_github_meta_repo_excluded_from_named_org(self):
        assert not self.in_dazzle("DazzleLib/.github")


class TestExcludeVetoesDeclared:
    def test_exclude_beats_declaration(self):
        s = SetDefinition("s", exclude=["*/.github"], declared=True)
        dec = DeclaredMembers(slugs={"someorg/.github"})
        assert not s.contains("someorg/.github", declared_members=dec)


# -- health warnings -----------------------------------------------------

class TestWarnings:
    def test_healthy_definition_is_silent(self):
        assert dazzle_set().warnings() == []
        assert wtf_set().warnings() == []

    def test_glob_in_include_warns_but_still_matches(self):
        s = SetDefinition("s", include=["djdarcy/wtf-*"])
        warns = s.warnings()
        assert len(warns) == 1 and "glob" in warns[0]
        # A config that parses must behave as written, warning or not.
        assert s.contains("djdarcy/wtf-windows")

    def test_include_count_over_threshold_warns(self):
        s = SetDefinition("s", include=[f"o/r{i}" for i in range(4)])
        assert any("4 entries" in w for w in s.warnings())

    def test_include_at_threshold_is_silent(self):
        s = SetDefinition("s", include=[f"o/r{i}" for i in range(3)])
        assert s.warnings() == []

    def test_original_design_include_list_fires(self):
        """REGRESSION, required by the design doc's Outcome Addendum.

        The rule language's own first recommendation shipped this include
        list, and it was wrong on two of three entries. The health check
        exists so that exact mistake cannot be configured silently again.
        (The original threshold of 10 would never have fired on it.)
        """
        s = SetDefinition("dazzle", include=["djdarcy/dazzle-*",
                                             "djdarcy/wtf-*",
                                             "djdarcy/DPAPIck3"])
        assert s.warnings(), "the design's own include list must warn"


# -- DeclaredMembers -----------------------------------------------------

class TestDeclaredMembers:
    def test_slug_match_case_insensitive(self):
        d = DeclaredMembers(slugs={"djdarcy/wtf-windows"})
        assert d.matches("djdarcy/WTF-Windows")

    def test_dist_match_normalizes_repo_part(self):
        d = DeclaredMembers(dists={"dpapick3"})
        assert d.matches("djdarcy/DPAPIck3")
        d2 = DeclaredMembers(dists={"some-lib"})
        assert d2.matches("owner/some_lib")

    def test_no_owner_never_matches(self):
        d = DeclaredMembers(slugs={"a/b"}, dists={"b"})
        assert not d.matches("b")
        assert not d.matches(None)


# -- derivation from manifests -------------------------------------------

def build_fake_pkg(root):
    """A miniature dazzlecmd package tree with the real manifest shapes."""
    (root / "kits").mkdir(parents=True)
    (root / "kits" / "wtf.kit.json").write_text(json.dumps({
        "name": "wtf",
        "source": "https://github.com/djdarcy/wtf-windows.git"}),
        encoding="utf-8")
    (root / "kits" / "virtual.kit.json").write_text(json.dumps({
        "name": "claude", "virtual": True}), encoding="utf-8")
    proj = root / "projects" / "dazzletools"
    (proj / "efs-recover").mkdir(parents=True)
    (proj / ".kit.json").write_text(json.dumps({
        "source": "https://github.com/DazzleTools/dazzletools-kit"}),
        encoding="utf-8")
    (proj / "efs-recover" / "requirements.txt").write_text(
        "# EFS recovery\ndpapick3>=0.3\n\nunctools\n", encoding="utf-8")
    return root


class TestDerivation:
    def test_kit_sources_reads_source_fields(self, tmp_path):
        pkg = build_fake_pkg(tmp_path)
        got = kit_sources(pkg_root=str(pkg))
        assert got == {"djdarcy/wtf-windows", "dazzletools/dazzletools-kit"}

    def test_tool_dependencies_reads_requirements(self, tmp_path):
        pkg = build_fake_pkg(tmp_path)
        got = tool_dependencies(pkg_root=str(pkg))
        assert got == {"dpapick3", "unctools"}

    def test_malformed_manifest_is_skipped(self, tmp_path):
        pkg = build_fake_pkg(tmp_path)
        (pkg / "kits" / "broken.kit.json").write_text("{not json",
                                                      encoding="utf-8")
        assert "djdarcy/wtf-windows" in kit_sources(pkg_root=str(pkg))

    def test_real_package_declares_the_known_members(self):
        """Against the LIVE tree: the derivations that motivated the
        feature must actually derive. If wtf.kit.json drops its source
        or efs-recover stops requiring dpapick3, membership changes and
        this test says so before a user notices."""
        assert "djdarcy/wtf-windows" in kit_sources()
        assert "dpapick3" in tool_dependencies()


# -- load_sets -----------------------------------------------------------

class TestLoadSets:
    def test_empty_and_missing(self):
        assert load_sets({}) == ([], [])
        assert load_sets(None) == ([], [])

    def test_parses_the_template_shape(self):
        cfg = {"dazzle": {"namespaces": ["DazzleTools/*"],
                          "include": [], "exclude": [], "declared": True},
               "wtf": {"namespaces": ["djdarcy/wtf-*"]}}
        got, warns = load_sets(cfg)
        assert [s.name for s in got] == ["dazzle", "wtf"]
        assert warns == []
        assert got[0].declared and not got[1].declared

    def test_non_mapping_top_level(self):
        got, warns = load_sets(["dazzle"])
        assert got == [] and len(warns) == 1

    def test_non_mapping_body_skipped_loudly(self):
        got, warns = load_sets({"bad": "DazzleTools/*"})
        assert got == []
        assert any("'bad'" in w for w in warns)

    def test_non_list_field_skipped_loudly(self):
        got, warns = load_sets({"bad": {"namespaces": "DazzleTools/*"}})
        assert got == []
        assert any("must be list" in w for w in warns)

    def test_unknown_keys_warn_but_set_survives(self):
        got, warns = load_sets({"s": {"namespaces": [], "regex": ".*"}})
        assert len(got) == 1
        assert any("unknown key" in w for w in warns)

    def test_underscore_keys_are_comments(self):
        got, warns = load_sets({"s": {"namespaces": ["X/*"],
                                      "_comment": "why this set exists"}})
        assert len(got) == 1 and warns == []

    def test_definition_warnings_surface_at_load(self):
        got, warns = load_sets({"s": {"include": ["djdarcy/wtf-*"]}})
        assert len(got) == 1
        assert any("glob" in w for w in warns)


# -- annotate ------------------------------------------------------------

class TestAnnotate:
    def test_stamps_overlapping_sets(self):
        records = {
            "djdarcy/wtf-windows": {"full_name": "djdarcy/wtf-windows"},
            "djdarcy/wtf-privacy": {"full_name": "djdarcy/wtf-privacy"},
            "dazzletools/dazzlecmd": {"full_name": "DazzleTools/dazzlecmd"},
        }
        annotate(records, [dazzle_set(), wtf_set()], fake_declared())
        assert records["djdarcy/wtf-windows"]["sets"] == ["dazzle", "wtf"]
        assert records["djdarcy/wtf-privacy"]["sets"] == ["wtf"]
        assert records["dazzletools/dazzlecmd"]["sets"] == ["dazzle"]

    def test_no_remote_record_gets_empty_list(self):
        records = {"somelocal": {"full_name": None}}
        annotate(records, [dazzle_set()], None)
        assert records["somelocal"]["sets"] == []


# -- the lens (dazzle_update integration) --------------------------------

import dazzle_update as du  # noqa: E402


def _rec(key, sets_list):
    return {"key": key, "full_name": key, "sets": sets_list}


class TestApplySetLens:
    def test_filters_and_counts_distinct_hidden(self):
        a = _rec("a/one", ["dazzle"])
        b = _rec("b/two", ["wtf"])
        findings = {"unpushed": [a, b], "dirty": [b], "clean": [a]}
        got, hidden = du.apply_set_lens(findings, ["dazzle"])
        assert got["unpushed"] == [a]
        assert got["dirty"] == []
        assert got["clean"] == [a]
        assert hidden == 1  # b, once, despite two findings

    def test_clean_and_excluded_do_not_count_as_hidden(self):
        b = _rec("b/two", ["wtf"])
        findings = {"clean": [b], "excluded-by-policy": [b]}
        got, hidden = du.apply_set_lens(findings, ["dazzle"])
        assert hidden == 0

    def test_lens_names_case_insensitive(self):
        a = _rec("a/one", ["Dazzle"])
        got, hidden = du.apply_set_lens({"dirty": [a]}, ["dazzle"])
        assert got["dirty"] == [a]


class TestLensFooter:
    def test_footer_states_scope_and_denominator_under_lens(self, capsys):
        """USER FINDING 2026-07-31: '4 repos clean and current' under 4
        dirty rows read as a contradiction (numeric coincidence). Under
        a lens the footer must say WHOSE clean count it is, of how many.
        """
        def rec(key, sets_list):
            return {"key": key, "full_name": key, "paths": [],
                    "configured_slugs": [], "checkouts": [], "git": {},
                    "installed": None, "redirected": False,
                    "excluded": None, "source_version": None,
                    "published": None, "sets": sets_list}
        findings = {"dirty": [rec("a/one", ["claude"])],
                    "clean": [rec("b/two", ["claude"])],
                    "not-cloned": [rec("c/three", ["claude"])]}
        meta = {"namespace_count": 1, "org_repo_count": 3,
                "cloned_count": 2, "install_count": 0,
                "gh_detail": "test", "published_detail": "skipped",
                "roots": ["X"], "errors": [], "clean": 1,
                "set_lens": ["claude"], "set_hidden": 0}
        du.render_text({}, findings, meta)
        out = capsys.readouterr().out
        # not-cloned never scanned -> excluded from the denominator
        assert "1 of 2 repo(s) in 'claude' clean and current." in out


class TestCli:
    """Only the paths that exit before any scan or network touch."""

    def _write_cfg(self, tmp_path, sets_body):
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps({"sets": sets_body}), encoding="utf-8")
        return str(p)

    def test_list_sets_prints_rules(self, tmp_path, capsys):
        cfg = self._write_cfg(tmp_path, {
            "dazzle": {"namespaces": ["DazzleTools/*"],
                       "include": ["djdarcy/dazzle-claude-code-config"],
                       "exclude": ["*/.github"], "declared": True}})
        rc = du.main(["--list-sets", "--config", cfg])
        out = capsys.readouterr().out
        assert rc == 0
        assert "dazzle" in out
        assert "DazzleTools/*" in out
        assert "declared:   yes" in out

    def test_list_sets_none_configured(self, tmp_path, capsys):
        cfg = self._write_cfg(tmp_path, {})
        rc = du.main(["--list-sets", "--config", cfg])
        assert rc == 0
        assert "no sets configured" in capsys.readouterr().out

    def test_only_set_unknown_name_exits_2(self, tmp_path, capsys):
        cfg = self._write_cfg(tmp_path, {"dazzle": {"namespaces": ["X/*"]}})
        rc = du.main(["--only-set", "nope", "--config", cfg])
        out = capsys.readouterr().out
        assert rc == 2
        assert "unknown set(s): nope" in out
        assert "configured sets: dazzle" in out

    def test_only_set_with_no_sets_exits_2(self, tmp_path, capsys):
        cfg = self._write_cfg(tmp_path, {})
        rc = du.main(["--only-set", "dazzle", "--config", cfg])
        assert rc == 2
        assert "no sets configured" in capsys.readouterr().out

    def test_set_warnings_survive_cached_replay(self, tmp_path, capsys,
                                                monkeypatch):
        """REGRESSION: the cached path rebuilt meta['errors'] from the
        cache alone, silently dropping every current-run warning -- a
        malformed set warned on a fresh scan and said NOTHING on replay.
        """
        import scancache
        monkeypatch.setattr(du, "gh_status",
                            lambda: (False, "gh unavailable (test)"))
        cache = tmp_path / "test-scan.json"
        ok, err = scancache.save({}, {
            "namespace_count": 0, "org_repo_count": 0, "cloned_count": 0,
            "install_count": 0, "gh_detail": "test", "roots": ["X"],
            "published_detail": "skipped", "errors": [], "clean": 0,
        }, path=str(cache))
        assert ok, err
        cfgp = tmp_path / "cfg.json"
        cfgp.write_text(json.dumps({
            "cache_path": str(cache),
            "sets": {"bad": "not-a-mapping"}}), encoding="utf-8")
        rc = du.main(["--cached", "--max-age", "999999", "--no-progress",
                      "--color", "never", "--config", str(cfgp)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "'bad'" in out and "skipped" in out
        # The Sources line must name THIS run's config, not whichever
        # file produced the cached scan (tester finding, 2026-07-31).
        assert str(cfgp) in out
