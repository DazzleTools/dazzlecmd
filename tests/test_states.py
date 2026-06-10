"""Step 1 tests for the state system (``dazzlecmd_lib.states``).

Covers the four core types, the reference registry (``build_default_registry``),
the registry-enumeration property tests the state-system DWP calls for (every
REVERSIBLE edge preserves C1 + names its invariant; every GENERATIVE edge must
declare creates/loses; the REFUSED class exists for MODE), and the round-trip
harness driven against the LIVE rebind contexts:

- ALIAS rebind: a full in-memory round-trip through ``assert_round_trip`` over a
  real ``FQCNIndex`` -- and the declared edge's reversibility/invariant-name is
  cross-checked against the live receipt.
- MODE rebind: the live receipt's ``reversible`` flag and conserved-invariant
  name are cross-checked against the declared MODE edges (in-orbit REVERSIBLE,
  enter-orbit ONE_WAY, underivable-invariant REFUSED). Filesystem ops run in
  ``--dry-run`` (no mutation, no git network), so MODE is checked at the receipt
  level; the in-memory ALIAS path carries the full fs-free round-trip.

``states.py`` is imported nowhere in the dispatch hot path (Step 1 is additive),
so the byte-gate is unaffected; these tests are the additive coverage.
"""

import os
import tempfile

import pytest

from dazzlecmd_lib.engine import FQCNIndex
from dazzlecmd_lib.entity import build_entity
from dazzlecmd_lib.groupable import AliasRebindContext, CriticalityBoundaryError
from dazzlecmd_lib.testing import make_tool
from dazzlecmd_lib.states import (
    OPEN,
    ACTIVATION_VALUES,
    EntityState,
    KIND_VALUES,
    MODE_VALUES,
    Reversibility,
    StateAxis,
    Transition,
    TransitionRegistry,
    assert_round_trip,
    observe,
    build_default_registry,
)


# ---------------------------------------------------------------------------
# Fixtures (minimal, self-contained -- mirror tests/test_groupable_rebind.py)
# ---------------------------------------------------------------------------
def _alias_fixture():
    """Two canonicals (both short 'cleanup') + alias claude:cleanup -> c1."""
    idx = FQCNIndex()
    c1 = make_tool(name="cleanup", namespace="dazzletools",
                   _fqcn="dazzletools:cleanup", _short_name="cleanup",
                   _kit_import_name="dazzletools")
    c2 = make_tool(name="cleanup", namespace="core",
                   _fqcn="core:cleanup", _short_name="cleanup",
                   _kit_import_name="core")
    idx.insert_canonical(c1)
    idx.insert_canonical(c2)
    idx.insert_alias("claude:cleanup", "dazzletools:cleanup")
    return idx, c1, c2


def _sandbox_tool(tmpdir, *, with_url=True, gitmodules=False):
    """A tool entity at ``tmpdir/projects/core/mytool``; ``gitmodules=True`` makes
    ``detect_tool_state`` report SUBMODULE (in-orbit), else EMBEDDED."""
    tool_dir = os.path.join(tmpdir, "projects", "core", "mytool")
    os.makedirs(tool_dir)
    with open(os.path.join(tool_dir, "mytool.py"), "w", encoding="utf-8") as f:
        f.write("# placeholder")
    data = {
        "name": "mytool", "namespace": "core", "version": "1.0.0",
        "description": "sandbox", "directory": tool_dir, "_fqcn": "core:mytool",
        "runtime": {"type": "python", "script_path": "mytool.py"},
    }
    if with_url:
        data["source"] = {"url": "https://example.com/mytool.git"}
    if gitmodules:
        with open(os.path.join(tmpdir, ".gitmodules"), "w", encoding="utf-8") as f:
            f.write('[submodule "projects/core/mytool"]\n'
                    '\tpath = projects/core/mytool\n'
                    '\turl = https://example.com/mytool.git\n')
    return build_entity(data, entity_type="tool")


# ---------------------------------------------------------------------------
# The four core types
# ---------------------------------------------------------------------------
class TestStateAxis:
    def test_admits_fixed_values(self):
        ax = StateAxis(name="mode", values=MODE_VALUES)
        assert ax.admits("symlink")
        assert not ax.admits("bogus")

    def test_open_valued_axis_admits_anything(self):
        ax = StateAxis(name="routing", values=None)
        assert ax.admits("anything:at:all")
        assert ax.admits("")


class TestEntityState:
    def test_access_and_get(self):
        s = EntityState("core:t", {"mode": "submodule", "visibility": "visible"})
        assert s.fqcn == "core:t"
        assert s["mode"] == "submodule"
        assert s.get("activation", "active") == "active"

    def test_subset_restriction_equality(self):
        s = EntityState("core:t", {"mode": "submodule", "visibility": "visible"})
        assert s.on("mode") == EntityState("core:t", {"mode": "submodule"})
        # restriction drops the untouched axis -> not equal to the full state
        assert s.on("mode") != s

    def test_is_frozen(self):
        s = EntityState("core:t", {"mode": "submodule"})
        with pytest.raises(Exception):
            s.fqcn = "other:t"  # frozen dataclass


class TestTransitionConstruction:
    def test_generative_must_declare_creates_or_loses(self):
        with pytest.raises(ValueError, match="creates and/or loses"):
            Transition(axis="kind", from_values=("tool",), to_value="aggregator",
                       verb="ungroup", reversibility=Reversibility.GENERATIVE)

    def test_generative_well_formed_is_accepted(self):
        t = Transition(axis="kind", from_values=("tool",), to_value="aggregator",
                       verb="ungroup", reversibility=Reversibility.GENERATIVE,
                       creates=("own_repo",), loses=("in_tree_coupling",),
                       fqcn_fate="reborn")
        assert t.creates == ("own_repo",)
        assert t.fqcn_fate == "reborn"

    def test_reversible_must_preserve_c1(self):
        with pytest.raises(ValueError, match="preserve"):
            Transition(axis="mode", from_values=("symlink",), to_value="submodule",
                       verb="rebind", reversibility=Reversibility.REVERSIBLE,
                       fqcn_fate="reborn")

    def test_reversible_property(self):
        t = Transition(axis="routing", from_values=(OPEN,), to_value=OPEN,
                       verb="rebind", reversibility=Reversibility.REVERSIBLE)
        assert t.reversible is True
        t2 = Transition(axis="mode", from_values=("embedded",), to_value=OPEN,
                        verb="rebind", reversibility=Reversibility.ONE_WAY)
        assert t2.reversible is False


class TestTransitionRegistry:
    def test_declare_rejects_unregistered_axis(self):
        reg = TransitionRegistry()
        with pytest.raises(KeyError):
            reg.declare(Transition(axis="ghost", from_values=(OPEN,), to_value=OPEN,
                                   verb="rebind", reversibility=Reversibility.REVERSIBLE))

    def test_declare_rejects_typo_endpoint(self):
        reg = TransitionRegistry()
        reg.register_axis(StateAxis(name="mode", values=MODE_VALUES))
        with pytest.raises(ValueError, match="not admitted"):
            reg.declare(Transition(axis="mode", from_values=("sumbodule",), to_value=OPEN,
                                   verb="rebind", reversibility=Reversibility.ONE_WAY))

    def test_register_axis_rejects_duplicate(self):
        reg = TransitionRegistry()
        reg.register_axis(StateAxis(name="mode", values=MODE_VALUES))
        with pytest.raises(ValueError, match="already registered"):
            reg.register_axis(StateAxis(name="mode", values=MODE_VALUES))

    def test_lookup_and_find(self):
        reg = build_default_registry()
        t = reg.lookup(verb="rebind", axis="mode", from_value="submodule")
        assert t.reversibility is Reversibility.REVERSIBLE
        assert reg.find(verb="rebind", axis="mode", from_value="nope-no-such-state") is None
        with pytest.raises(LookupError):
            reg.lookup(verb="rebind", axis="mode", from_value="nope-no-such-state")


# ---------------------------------------------------------------------------
# The reference registry
# ---------------------------------------------------------------------------
class TestDefaultRegistry:
    def test_axes_registered(self):
        reg = build_default_registry()
        names = {a.name for a in reg.axes()}
        assert names == {"kind", "mode", "visibility", "activation", "routing", "containment"}
        assert reg.axis("kind").read_only is True
        assert reg.axis("routing").values is None  # open-valued

    def test_mode_values_match_mode_module(self):
        """Drift guard: the MODE axis values must equal mode.STATE_* literals."""
        from dazzlecmd_lib import mode
        assert set(MODE_VALUES) == {
            mode.STATE_SYMLINK, mode.STATE_SUBMODULE, mode.STATE_EMBEDDED,
            mode.STATE_MISSING, mode.STATE_LOCAL_ONLY,
        }

    def test_activation_axis_values(self):
        reg = build_default_registry()
        assert reg.axis("activation").values == ACTIVATION_VALUES


# ---------------------------------------------------------------------------
# Registry-enumeration property tests (the DWP's F3.2 contract)
# ---------------------------------------------------------------------------
class TestRegistryProperties:
    def test_every_reversible_preserves_c1_and_names_invariant(self):
        reg = build_default_registry()
        revs = reg.by_reversibility(Reversibility.REVERSIBLE)
        assert revs  # there is at least one (alias + in-orbit mode)
        for t in revs:
            assert t.fqcn_fate == "preserved", t
            assert t.conserved, f"REVERSIBLE edge must name its conserved invariant: {t}"

    def test_no_generative_yet_but_contract_enforced(self):
        """Graduation's GENERATIVE edges land in the group/ungroup pass (Step 5).
        Until then the registry has none -- but the type enforces their contract."""
        reg = build_default_registry()
        assert reg.by_reversibility(Reversibility.GENERATIVE) == ()

    def test_mode_declares_a_refused_class(self):
        reg = build_default_registry()
        refused = [t for t in reg.for_axis("mode")
                   if t.reversibility is Reversibility.REFUSED_AT_BOUNDARY]
        assert refused, "MODE rebind must declare a REFUSED_AT_BOUNDARY class"
        assert all(t.conserved == "remote_url" for t in refused)

    def test_routing_edge_is_open_and_reversible(self):
        reg = build_default_registry()
        routing = reg.for_axis("routing")
        assert len(routing) == 1
        t = routing[0]
        assert t.from_values == (OPEN,) and t.to_value is OPEN
        assert t.reversibility is Reversibility.REVERSIBLE
        assert t.conserved == "single_hop_rule"


# ---------------------------------------------------------------------------
# assert_round_trip harness
# ---------------------------------------------------------------------------
class TestRoundTripHarness:
    def test_detects_broken_identity(self):
        box = {"v": "A"}
        def apply():
            box["v"] = "B"
            return "receipt"
        def invert(_receipt):
            box["v"] = "C"  # wrong -- does not restore
        with pytest.raises(AssertionError, match="not the identity"):
            assert_round_trip(lambda: box["v"], apply, invert)

    def test_expected_new_mismatch_raises(self):
        box = {"v": "A"}
        def apply():
            box["v"] = "B"
            return "receipt"
        def invert(_receipt):
            box["v"] = "A"
        with pytest.raises(AssertionError, match="expected"):
            assert_round_trip(lambda: box["v"], apply, invert, expected_new="Z")

    def test_clean_round_trip_returns_receipt(self):
        box = {"v": "A"}
        def apply():
            box["v"] = "B"
            return "the-receipt"
        def invert(_receipt):
            box["v"] = "A"
        out = assert_round_trip(lambda: box["v"], apply, invert, expected_new="B")
        assert out == "the-receipt"


# ---------------------------------------------------------------------------
# Live cross-check: ALIAS rebind (full in-memory round-trip via the harness)
# ---------------------------------------------------------------------------
class TestLiveAliasRoundTrip:
    def test_alias_round_trip_and_declaration_agreement(self):
        idx, c1, c2 = _alias_fixture()
        alias = "claude:cleanup"

        def read():
            return idx.alias_index[alias]

        def apply():
            return c1.rebind("core:cleanup", context=AliasRebindContext(idx, alias))

        def invert(receipt):
            # Receiver = current owner (the alias now points at c2); rebind back.
            c2.rebind(receipt.previous_state, context=AliasRebindContext(idx, alias))

        receipt = assert_round_trip(read, apply, invert, expected_new="core:cleanup")
        assert idx.alias_index[alias] == "dazzletools:cleanup"  # restored (L2)

        # The live receipt agrees with the declared routing edge.
        reg = build_default_registry()
        t = reg.lookup(verb="rebind", axis="routing", from_value="dazzletools:cleanup")
        assert t.reversibility is Reversibility.REVERSIBLE
        assert t.reversible == receipt.reversible is True
        assert t.conserved == receipt.invariant.conserved_quantity_name == "single_hop_rule"


# ---------------------------------------------------------------------------
# Live cross-check: MODE rebind (receipt-level; dry-run, no fs mutation)
# ---------------------------------------------------------------------------
class TestLiveModeAgreement:
    def test_in_orbit_reversible_matches_declaration(self):
        from dazzlecmd_lib.mode import ModeRebindContext
        reg = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            tool = _sandbox_tool(tmp, with_url=True, gitmodules=True)  # SUBMODULE
            dev_src = os.path.join(tmp, "devsrc")
            os.makedirs(dev_src)
            ctx = ModeRebindContext(project_root=tmp, tools_dir="projects",
                                    dev_path=dev_src, dry_run=True)
            r = tool.rebind("dev", context=ctx)
            assert r.reversible is True

            t = reg.lookup(verb="rebind", axis="mode", from_value="submodule")
            assert t.reversibility is Reversibility.REVERSIBLE
            assert t.reversible == r.reversible
            assert t.conserved == r.invariant.conserved_quantity_name == "remote_url"

    def test_enter_orbit_one_way_matches_declaration(self):
        from dazzlecmd_lib.mode import ModeRebindContext
        reg = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp:
            tool = _sandbox_tool(tmp, with_url=True)  # EMBEDDED + url
            ctx = ModeRebindContext(project_root=tmp, tools_dir="projects", dry_run=True)
            r = tool.rebind("publish", context=ctx)
            assert r.reversible is False

            t = reg.lookup(verb="rebind", axis="mode", from_value="embedded")
            assert t.reversibility is Reversibility.ONE_WAY
            assert t.reversible is False
            assert t.conserved == r.invariant.conserved_quantity_name == "remote_url"

    def test_underivable_invariant_is_refused_and_declared(self):
        from dazzlecmd_lib.mode import ModeRebindContext
        reg = build_default_registry()
        # The registry declares the REFUSED class...
        assert reg.by_reversibility(Reversibility.REFUSED_AT_BOUNDARY)
        # ...and live, an underivable conserved invariant refuses pre-flight.
        with tempfile.TemporaryDirectory() as tmp:
            tool = _sandbox_tool(tmp, with_url=False)  # no remote URL derivable
            ctx = ModeRebindContext(project_root=tmp, tools_dir="projects", dry_run=True)
            with pytest.raises(CriticalityBoundaryError):
                tool.rebind("publish", context=ctx)


# ---------------------------------------------------------------------------
# Platform integration: the model vs the REAL dazzlecmd / dazzlecmd-lib platform
# ---------------------------------------------------------------------------
class TestPlatformIntegration:
    """Proves the state vocabulary actually SPANS the real platform -- not just
    that the types are internally consistent. ``observe()`` validates a platform
    reading against the registered axes; these tests feed it readings taken from
    the REAL substrate readers (the discriminated-union ``type``,
    ``detect_tool_state``, ``kit_active``, ``visibility_in``) and from a full
    real discovery pass over this repo. If the platform ever produces a state the
    model can't express, ``observe()`` raises and the relevant test fails.
    """

    def test_observe_validates_and_rejects(self):
        reg = build_default_registry()
        s = observe(reg, "core:x", kind="tool", mode="embedded",
                    visibility="visible", activation="active")
        assert s.fqcn == "core:x" and s["mode"] == "embedded"
        with pytest.raises(ValueError, match="not admitted"):
            observe(reg, "core:x", mode="frobnicated")
        with pytest.raises(KeyError, match="unknown axis"):
            observe(reg, "core:x", flavor="spicy")

    def test_kind_axis_equals_the_discriminated_union(self):
        """The KIND axis must cover exactly the concrete entity subtypes; a new
        subtype added without extending KIND_VALUES would fail here (by design)."""
        from dazzlecmd_lib.entity import Aggregator, Kit, Tool
        type_literals = {c.model_fields["type"].default for c in (Tool, Kit, Aggregator)}
        assert type_literals == set(KIND_VALUES)

    def test_mode_axis_spans_detect_tool_state_outputs(self):
        """Every value ``detect_tool_state`` can return must be a MODE value."""
        reg = build_default_registry()
        from dazzlecmd_lib import mode
        for v in (mode.STATE_SYMLINK, mode.STATE_SUBMODULE, mode.STATE_EMBEDDED,
                  mode.STATE_MISSING, mode.STATE_LOCAL_ONLY):
            assert reg.axis("mode").admits(v), v

    def test_visibility_axis_covers_engine_ladder(self):
        """The VISIBILITY axis covers the full ladder (engine ``silenced_hints`` /
        ``shadowed_tools`` + the planned ``hidden_tools``). ``visibility_in()`` is
        still the 'visible' stub until hide/expose (Step 4) wires the substrate;
        assert the stub is a model value AND the whole ladder is admitted."""
        reg = build_default_registry()
        tool = make_tool(name="x", namespace="core", _fqcn="core:x",
                         _short_name="x", _kit_import_name="core")
        assert reg.axis("visibility").admits(tool.visibility_in())
        for v in ("visible", "silenced", "hidden", "shadowed"):
            assert reg.axis("visibility").admits(v)

    def test_observe_real_discovered_entities(self, tmp_path, monkeypatch):
        """The strongest fidelity check: run REAL discovery over this repo and
        observe every discovered tool across the axes the platform can read today
        (KIND from the type, MODE from ``detect_tool_state``, ACTIVATION from
        ``kit_active``, VISIBILITY from ``visibility_in``). Every reading must be a
        value the model admits."""
        from dazzlecmd.engine import AggregatorEngine
        from dazzlecmd_lib.mode import detect_tool_state, parse_gitmodules

        reg = build_default_registry()
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.isdir(os.path.join(repo_root, "projects")):
            pytest.skip("not running from a dazzlecmd checkout (no projects/ dir)")

        monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
        engine = AggregatorEngine(name="dazzlecmd", command="dz",
                                  tools_dir="projects", kits_dir="kits",
                                  manifest=".dazzlecmd.json",
                                  version_info=("0.0.0", "0.0.0_test"))
        engine.discover(project_root=repo_root)
        assert engine.projects, "real discovery found no projects"
        gitmodules = parse_gitmodules(repo_root, tools_dir="projects")

        kinds_seen, modes_seen, observed = set(), set(), 0
        for ent in engine.projects:
            readings = {
                "kind": ent.type,
                "visibility": ent.visibility_in(),
                "activation": "active" if getattr(ent, "kit_active", True) else "inactive",
            }
            directory = getattr(ent, "directory", None)
            if directory:
                readings["mode"] = detect_tool_state(
                    directory, gitmodules, repo_root, tools_dir="projects")
                modes_seen.add(readings["mode"])
            kinds_seen.add(ent.type)
            # The real platform reading must be expressible in the model.
            st = observe(reg, ent.fqcn, **readings)
            assert st.fqcn == ent.fqcn
            observed += 1

        assert observed == len(engine.projects)
        assert "tool" in kinds_seen
        assert modes_seen and modes_seen <= set(MODE_VALUES)
