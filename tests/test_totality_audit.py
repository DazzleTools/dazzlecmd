"""B-1 / F10 -- THE TOTALITY RATCHET (the plan's first slice).

THE INVARIANT (D7): everything the system knows must be FQCN-reachable;
the stranded set is measured incompleteness and may only SHRINK. The
committed baseline (tests/totality_baseline.json) is the ratchet's
pawl: any item stranded today that was NOT stranded at baseline = a
regression (CI fails on growth); items LEAVING the stranded set = the
plan working (the test passes and names the progress so the baseline
can be re-committed smaller).
"""
import json
import os
import tempfile

import pytest

from dazzlecmd.meta_audit import totality_audit, render_stranded_report

BASELINE = os.path.join(os.path.dirname(__file__), "totality_baseline.json")


def _run_audit():
    import dazzlecmd
    from dazzlecmd_lib.engine import AggregatorEngine
    engine = AggregatorEngine(name="dazzlecmd", command="dz",
                              config_dir=tempfile.mkdtemp())
    engine.project_root = os.path.dirname(dazzlecmd.__file__)
    return totality_audit(engine)


def _key(rec):
    return f"{rec['source']}::{rec['item']}"


class TestTotalityRatchet:
    def test_the_stranded_set_only_shrinks(self):
        result = _run_audit()
        current = {_key(r) for r in result["stranded"]}
        with open(BASELINE, encoding="utf-8") as fh:
            baseline = set(json.load(fh)["stranded_keys"])
        grown = current - baseline
        assert not grown, (
            "TOTALITY REGRESSION -- items stranded now that were homed "
            f"(or absent) at baseline: {sorted(grown)}\n"
            "Every new item must arrive with its home (or the baseline "
            "must be consciously re-committed with a design note)."
        )
        healed = baseline - current
        if healed:  # the ratchet advanced -- report, then tighten
            print(f"\nRATCHET PROGRESS: {len(healed)} item(s) homed since "
                  f"baseline -- re-commit tests/totality_baseline.json:\n  "
                  + "\n  ".join(sorted(healed)[:12]))

    def test_the_report_names_every_home(self):
        result = _run_audit()
        assert all(r.get("homes_with") for r in result["stranded"]), (
            "every stranded item must name the mechanism that homes it "
            "-- the report IS the backlog")

    def test_homed_items_exist(self):
        result = _run_audit()
        assert result["homed"] > 0 and result["tree_nodes"] > 0


if __name__ == "__main__":  # regenerate the baseline deliberately
    result = _run_audit()
    with open(BASELINE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"generated": "by test_totality_audit.py __main__",
                   "homed": result["homed"],
                   "tree_nodes": result["tree_nodes"],
                   "stranded_keys": sorted(_key(r)
                                           for r in result["stranded"])},
                  fh, indent=2)
    print(render_stranded_report(result))
    print(f"\nbaseline written: {BASELINE}")


class TestMetadataRing:
    """B-5 (the plan; instance-ring DWP F4): instance metadata reads
    derive from the item's own data; claimed keys are read-only."""

    def test_version_derives_and_is_read_only(self, capsys=None):
        import tempfile, os, dazzlecmd
        from dazzlecmd_lib.engine import AggregatorEngine
        from dazzlecmd_lib import prop_commands
        from dazzlecmd.commands.inspect import _graft_app_verbs
        from dazzlecmd.tree_plane import (graft_instance_plane,
                                          derived_instance_read)
        e = AggregatorEngine(name="dazzlecmd", command="dz",
                             config_dir=tempfile.mkdtemp())
        e.project_root = os.path.dirname(dazzlecmd.__file__)
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            e.discover()
        e.tree_extensions += [_graft_app_verbs, graft_instance_plane]
        e.derived_reads.append(derived_instance_read)
        assert derived_instance_read(e, "dz:core:safedel.version") == "0.1.1"
        assert derived_instance_read(e, "dz:core:safedel.level") == "internaltool"
        assert derived_instance_read(e, "dz.level") is None  # root untouched
        assert e._intercept_path_form([":core:safedel.version=9"]) == ("result", 2)

    def test_b6_members_and_aliases_are_relations(self):
        import tempfile, os, dazzlecmd, io, contextlib
        from dazzlecmd_lib.engine import AggregatorEngine
        from dazzlecmd_lib.fqcn_tree import build_engine_tree
        from dazzlecmd.commands.inspect import _graft_app_verbs
        from dazzlecmd.tree_plane import graft_instance_plane
        e = AggregatorEngine(name="dazzlecmd", command="dz",
                             config_dir=tempfile.mkdtemp())
        e.project_root = os.path.dirname(dazzlecmd.__file__)
        with contextlib.redirect_stdout(io.StringIO()):
            e.discover()
        e.tree_extensions += [_graft_app_verbs, graft_instance_plane]
        tree = build_engine_tree(e)
        f = tree.nodes["dz:f"]
        assert "dz:core:safedel" in f["members"]          # followable
        assert all(m in tree for m in f["members"])       # they RESOLVE
        assert "f:rm" in tree.nodes["dz:core:safedel"]["aliases"]

    def test_b8_expose_generates_and_classifier_verdicts(self):
        import tempfile, os, dazzlecmd
        from dazzlecmd_lib.engine import AggregatorEngine
        from dazzlecmd.tree_plane import (exposed_generated_commands,
                                          classify_verb)
        e = AggregatorEngine(name="dazzlecmd", command="dz",
                             config_dir=tempfile.mkdtemp())
        assert exposed_generated_commands(e) == []          # off by default
        e.property_store.set("dz:.meta:verb:management.expose", True)
        cmds = exposed_generated_commands(e)
        assert cmds and cmds[0][0] == "management"          # flips on
        from dazzlecmd.parsers import build_parser
        p = build_parser([], engine=e)
        assert "management" in p._subparsers._group_actions[0].choices
        # D8's pinned demotion exhibits:
        assert classify_verb(e, "use")[0] == "property-backed"
        assert classify_verb(e, "reset")[0] == "property-backed"
        assert classify_verb(e, "version")[0] == "property-backed"
        assert classify_verb(e, "add")[0] == "handler-backed"
