"""The manifest<->entity boundary contract as a standing regression.

The boundary between dict-land (manifests on disk -- the source of truth) and
entity-land (the typed model) is a group/ungroup pair: ``build_entity`` groups a
manifest into typed form; ``to_manifest`` ungroups it back. The conserved
invariant (C2) is THE MANIFEST'S OWN CONTENT: every key the author wrote must
survive the round-trip with its value intact. This is L2-SEMANTIC identity --
the projection may ADD materialized defaults (the L2.5-byte gap, measured and
accepted), but may never LOSE or CHANGE user data.

Promoted from ``tests/one-offs/thinking/boundary_contract_experiments.py``
(2026-06-10), which ran the contract over all 41 real manifests in the repo:
0 lost / 0 changed post-v0.8.32 (the `_vars` strip bug was the one violation,
fixed). These tests pin the contract over the live repo population AND a
synthetic worst-case manifest, driven through the states.py harness -- the same
``assert_round_trip`` that checks every other group/ungroup identity.
"""
import glob
import json
import os

import pytest

from dazzlecmd_lib.entity import build_entity
from dazzlecmd_lib.states import assert_round_trip

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _find_manifests():
    out = []
    for p in glob.glob(os.path.join(REPO, "projects", "**", ".dazzlecmd.json"),
                       recursive=True):
        try:
            with open(p, encoding="utf-8") as f:
                out.append((p, "tool", json.load(f)))
        except (json.JSONDecodeError, OSError):
            continue
    for pattern, kind in ((os.path.join(REPO, "kits", "*.kit.json"), "kit"),
                          (os.path.join(REPO, "projects", "*", ".kit.json"), "kit")):
        for p in glob.glob(pattern):
            try:
                with open(p, encoding="utf-8") as f:
                    out.append((p, kind, json.load(f)))
            except (json.JSONDecodeError, OSError):
                continue
    return out


def _assert_l2_round_trip(manifest, kind):
    """Drive manifest -> entity -> manifest through the states.py harness;
    the conserved invariant is the manifest's own keys (L2 restriction)."""
    original_keys = list(manifest.keys())
    holder = {"data": dict(manifest)}

    def read():
        return {k: holder["data"].get(k) for k in original_keys}

    def apply():
        holder["entity"] = build_entity(dict(holder["data"]), entity_type=kind)
        return holder["entity"]

    def invert(entity):
        holder["data"] = entity.to_manifest()

    assert_round_trip(read, apply, invert)


class TestBoundaryRoundTrip:
    def test_live_repo_population(self):
        """Every real manifest in this checkout round-trips losslessly."""
        manifests = _find_manifests()
        if not manifests:
            pytest.skip("no repo manifests found (not running from a checkout)")
        for path, kind, m in manifests:
            try:
                _assert_l2_round_trip(m, kind)
            except AssertionError as exc:
                raise AssertionError(
                    f"boundary identity broken for {os.path.relpath(path, REPO)}: {exc}"
                ) from None

    def test_worst_case_synthetic_manifest(self):
        """A manifest exercising every category the contract names: typed
        fields, `_`-prefixed manifest data (the fixed bug), the polymorphic
        source (both wild forms), nested blocks, and a novel key."""
        for source_form in ("https://example.com/x.git", {"url": "https://example.com/x.git"}):
            m = {
                "name": "worst-case",
                "namespace": "core",
                "version": "1.2.3",
                "runtime": {"type": "python", "script_path": "x.py",
                            "_vars": {"inner": "block-level"}},
                "_vars": {"venv": ".venv312"},          # the fixed strip bug
                "_schema_version": 2,
                "source": source_form,                   # both polymorphic forms
                "tools_dir": "src/tools",                # promoted in v0.8.32
                "manifest": ".x.json",
                "taxonomy": {"tags": ["a"]},
                "novel_future_key": {"anything": [1, 2]},  # open world
            }
            _assert_l2_round_trip(m, "tool")

    def test_l2_gap_is_additive_only(self):
        """The L2.5 gap (materialized defaults) only ADDS keys -- the projection
        is a superset of the source manifest, never a rewrite."""
        m = {"name": "minimal", "namespace": "core"}
        e = build_entity(dict(m), entity_type="tool")
        back = e.to_manifest()
        for k, v in m.items():
            assert back[k] == v
        assert set(m) <= set(back)
