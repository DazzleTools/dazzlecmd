"""Step 4a tests for the hide/expose verbs (the visibility ladder).

hide/expose are ladder-walk operators over the monotone channel presets
(Visible/Silenced/Hidden/Shadowed). The verbs WRITE the existing config keys --
which ARE the per-channel suppression sets -- so a tool at Hidden is in both
silenced_hints (hints) and hidden_tools (display): the monotone effect falls out
of the existing filters with no new engine logic. Dispatch always survives
(C2 = canonical_dispatch); shadowing a constitutional (always_active) item is
refused (C3). Frame-relative writes are refused until #79. All moves are
reversible (round-trippable via ctx.undo).
"""

import json

import pytest

from dazzlecmd.engine import AggregatorEngine
from dazzlecmd_lib.groupable import (
    CriticalityBoundaryError,
    Frame,
    RebindError,
    Receipt,
    TransitionContext,
    VisibilityContext,
    VisibilityInvariant,
    VisibilityReceipt,
    level_for_channels,
)
from dazzlecmd_lib.states import Reversibility, assert_round_trip, build_default_registry
from dazzlecmd_lib.testing import make_tool


def _engine(tmp_path, monkeypatch, initial=None):
    cfg = dict(initial or {"_schema_version": 1})
    (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("DAZZLECMD_CONFIG", str(tmp_path / "config.json"))
    return AggregatorEngine(
        name="dazzlecmd", command="dz", tools_dir="projects", kits_dir="kits",
        manifest=".dazzlecmd.json", version_info=("0.0.0", "0.0.0_test"),
    )


def _tool(**over):
    base = dict(name="rn", _fqcn="core:rn", _short_name="rn", _kit_import_name="core")
    base.update(over)
    return make_tool(**base)


def _read_cfg(tmp_path):
    return json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Ladder walks + the cumulative (monotone) config representation
# ---------------------------------------------------------------------------
class TestLadderWalks:
    def test_hide_to_hidden_is_cumulative(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        ctx = VisibilityContext(engine)
        tool = _tool()
        r = tool.hide(to="hidden", context=ctx)
        assert isinstance(r, VisibilityReceipt)
        assert r.previous_state == "visible" and r.new_state == "hidden"
        # Monotone: Hidden suppresses {hints, display} -> in BOTH keys.
        cfg = _read_cfg(tmp_path)
        assert "core:rn" in cfg["hidden_tools"]                 # display
        assert "core:rn" in cfg["silenced_hints"]["tools"]      # hints
        assert "core:rn" not in cfg.get("shadowed_tools", [])   # not resolution

    def test_hide_to_silenced_only_hints(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        ctx = VisibilityContext(engine)
        _tool().hide(to="silenced", context=ctx)
        cfg = _read_cfg(tmp_path)
        assert "core:rn" in cfg["silenced_hints"]["tools"]
        assert "core:rn" not in cfg.get("hidden_tools", [])

    def test_receipt_channel_deltas(self, tmp_path, monkeypatch):
        ctx = VisibilityContext(_engine(tmp_path, monkeypatch))
        r = _tool().hide(to="hidden", context=ctx)
        assert set(r.channels_suppressed) == {"hints", "display"}
        assert r.channels_restored == ()
        assert r.invariant.conserved_quantity_name == "canonical_dispatch"
        assert r.reversible is True

    def test_expose_walks_up_and_restores_channels(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        ctx = VisibilityContext(engine)
        tool = _tool()
        tool.hide(to="hidden", context=ctx)
        r = tool.expose(to="visible", context=ctx)
        assert r.verb == "expose" and r.new_state == "visible"
        assert set(r.channels_restored) == {"hints", "display"}
        assert ctx.current_level(tool) == "visible"
        cfg = _read_cfg(tmp_path)
        assert "core:rn" not in cfg.get("hidden_tools", [])
        assert "core:rn" not in cfg["silenced_hints"]["tools"]


# ---------------------------------------------------------------------------
# Direction enforcement (P / -P duals, not one generic set_visibility)
# ---------------------------------------------------------------------------
class TestDirection:
    def test_hide_backwards_raises(self, tmp_path, monkeypatch):
        ctx = VisibilityContext(_engine(tmp_path, monkeypatch))
        tool = _tool()
        tool.hide(to="hidden", context=ctx)
        with pytest.raises(ValueError, match="backwards"):
            tool.hide(to="silenced", context=ctx)   # silenced < hidden

    def test_expose_backwards_raises(self, tmp_path, monkeypatch):
        ctx = VisibilityContext(_engine(tmp_path, monkeypatch))
        tool = _tool()  # currently visible
        with pytest.raises(ValueError, match="backwards"):
            tool.expose(to="hidden", context=ctx)   # hidden > visible

    def test_unknown_level_raises(self, tmp_path, monkeypatch):
        ctx = VisibilityContext(_engine(tmp_path, monkeypatch))
        with pytest.raises(ValueError, match="unknown visibility level"):
            _tool().hide(to="invisible", context=ctx)

    def test_requires_context(self, tmp_path, monkeypatch):
        with pytest.raises(TypeError):
            _tool().hide(to="hidden", context=None)
        with pytest.raises(TypeError):
            _tool().expose(to="visible", context=None)


# ---------------------------------------------------------------------------
# C3 -- constitutional items may be Hidden, never Shadowed
# ---------------------------------------------------------------------------
class TestC3:
    def test_shadow_constitutional_refused(self, tmp_path, monkeypatch):
        ctx = VisibilityContext(_engine(tmp_path, monkeypatch))
        tool = _tool(always_active=True)
        with pytest.raises(CriticalityBoundaryError, match="constitutional"):
            tool.hide(to="shadowed", context=ctx)

    def test_hide_constitutional_is_allowed(self, tmp_path, monkeypatch):
        """Hidden is the MAXIMUM veil a constitutional item may take."""
        ctx = VisibilityContext(_engine(tmp_path, monkeypatch))
        tool = _tool(always_active=True)
        r = tool.hide(to="hidden", context=ctx)
        assert r.new_state == "hidden"

    def test_shadow_ordinary_tool_is_allowed(self, tmp_path, monkeypatch):
        ctx = VisibilityContext(_engine(tmp_path, monkeypatch))
        r = _tool().hide(to="shadowed", context=ctx)
        assert r.new_state == "shadowed" and r.reversible is True


# ---------------------------------------------------------------------------
# Frame -- defined, but frame-relative writes refused until #79
# ---------------------------------------------------------------------------
class TestFrame:
    def test_frame_relative_refused(self, tmp_path, monkeypatch):
        ctx = VisibilityContext(_engine(tmp_path, monkeypatch), frame=Frame("env1"))
        with pytest.raises(CriticalityBoundaryError, match="frame-relative"):
            _tool().hide(to="hidden", context=ctx)

    def test_frame_type_shape(self):
        f = Frame("prod", kind="environment")
        assert f.name == "prod" and f.kind == "environment"
        assert f.channel_overrides is None   # reserved, unwired


# ---------------------------------------------------------------------------
# visibility_in + round-trip via undo + registry cross-check
# ---------------------------------------------------------------------------
class TestVisibilityInAndRoundTrip:
    def test_visibility_in_global_path(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        ctx = VisibilityContext(engine)
        tool = _tool()
        assert tool.visibility_in() == "visible"            # no context -> stub
        assert tool.visibility_in(context=ctx) == "visible"
        tool.hide(to="silenced", context=ctx)
        assert tool.visibility_in(context=ctx) == "silenced"

    def test_round_trip_via_undo(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path, monkeypatch)
        ctx = VisibilityContext(engine)
        tool = _tool()
        assert_round_trip(
            read=lambda: ctx.current_level(tool),
            apply=lambda: tool.hide(to="hidden", context=ctx),
            invert=ctx.undo,
            expected_new="hidden",
        )
        assert ctx.current_level(tool) == "visible"

    def test_undo_without_apply_raises(self, tmp_path, monkeypatch):
        ctx = VisibilityContext(_engine(tmp_path, monkeypatch))
        fake = VisibilityReceipt(
            entity_fqcn="core:rn", sub_kind="visibility",
            previous_state="visible", new_state="hidden",
            invariant=VisibilityInvariant(conserved_value="core:rn"),
        )
        with pytest.raises(RebindError, match="prior apply"):
            ctx.undo(fake)

    def test_registry_declares_visibility_reversible(self):
        reg = build_default_registry()
        for verb in ("hide", "expose"):
            edges = reg.for_verb(verb)
            assert edges, f"registry must declare {verb} edges"
            for t in edges:
                assert t.axis == "visibility"
                assert t.reversibility is Reversibility.REVERSIBLE
                assert t.conserved == "canonical_dispatch"


def test_level_for_channels_monotone():
    assert level_for_channels(set()) == "visible"
    assert level_for_channels({"hints"}) == "silenced"
    assert level_for_channels({"hints", "display"}) == "hidden"
    assert level_for_channels({"hints", "display", "resolution"}) == "shadowed"
    # non-preset set maps to the highest level it satisfies
    assert level_for_channels({"display"}) == "hidden"


# ---------------------------------------------------------------------------
# B2 -- the generic TransitionContext (the N-Contexts -> 1 collapse) and the
# proof that visibility now SOURCES reversible/conserved from the registry.
# ---------------------------------------------------------------------------
class TestTransitionContextGeneric:
    """The generic executor, exercised standalone over an in-memory substrate --
    proving it is engine-independent and sources policy from the declared edge."""

    def _toy(self):
        """A toy visibility substrate (fqcn -> level) + detect/write hooks."""
        store = {}
        def detect(e):
            return store.get(e.fqcn, "visible")
        def write(e, target, prev):
            store[e.fqcn] = target
            return {"from": prev}
        return store, detect, write

    def test_apply_sources_conserved_and_reversible_from_registry(self):
        reg = build_default_registry()
        store, detect, write = self._toy()
        tc = TransitionContext(reg, "visibility", detect=detect, write=write, identity_of=lambda e: e.fqcn)
        ent = _tool()
        r = tc.apply(ent, "hidden", verb="hide")
        assert isinstance(r, Receipt)
        assert r.axis == "visibility"
        assert r.previous_state == "visible" and r.new_state == "hidden"
        # conserved + reversible come FROM the declared edge, not a literal (F3).
        edge = next(t for t in reg.for_verb("hide") if t.axis == "visibility")
        assert r.conserved == edge.conserved == "canonical_dispatch"
        assert r.reversible is edge.reversible is True
        assert r.verb == "hide" and r.payload == {"from": "visible"}
        assert store[ent.fqcn] == "hidden"

    def test_undo_uses_invert_hook(self):
        reg = build_default_registry()
        store, detect, write = self._toy()
        tc = TransitionContext(reg, "visibility", detect=detect, write=write,
                               invert=lambda rc: (rc.previous_state, "expose"),
                               identity_of=lambda e: e.fqcn)
        ent = _tool()
        r = tc.apply(ent, "hidden", verb="hide")
        u = tc.undo(r)
        assert store[ent.fqcn] == "visible"        # restored
        assert u.verb == "expose" and u.new_state == "visible"

    def test_check_hook_refuses_before_write(self):
        reg = build_default_registry()
        store, detect, _ = self._toy()
        def write(e, t, p):
            raise AssertionError("write must not run when check refuses")
        def check(e, t, v, p):
            raise ValueError("nope")
        tc = TransitionContext(reg, "visibility", detect=detect, write=write, check=check,
                               identity_of=lambda e: e.fqcn)
        with pytest.raises(ValueError, match="nope"):
            tc.apply(_tool(), "hidden", verb="hide")
        assert store == {}                         # nothing written

    def test_unknown_verb_raises_lookuperror(self):
        reg = build_default_registry()
        _, detect, write = self._toy()
        tc = TransitionContext(reg, "visibility", detect=detect, write=write, identity_of=lambda e: e.fqcn)
        with pytest.raises(LookupError):
            tc.apply(_tool(), "hidden", verb="bogus")

    def test_undo_without_apply_raises(self):
        reg = build_default_registry()
        _, detect, write = self._toy()
        tc = TransitionContext(reg, "visibility", detect=detect, write=write, identity_of=lambda e: e.fqcn)
        with pytest.raises(RebindError):
            tc.undo(Receipt("core:x", "visibility", "hidden", "visible",
                            "canonical_dispatch", True, "expose"))


def test_visibility_receipt_sources_invariant_from_registry(tmp_path, monkeypatch):
    """AC4: after B2 the VisibilityReceipt's conserved-name + reversible trace to
    the DECLARED visibility edge (the registry is on the visibility runtime path),
    not a hardcoded literal."""
    eng = _engine(tmp_path, monkeypatch)
    r = VisibilityContext(eng).apply(_tool(), "hidden", verb="hide")
    edge = next(t for t in build_default_registry().for_verb("hide")
                if t.axis == "visibility")
    assert r.invariant.conserved_quantity_name == edge.conserved == "canonical_dispatch"
    assert r.reversible is edge.reversible is True
