"""Regression test for the generic verb x level dispatcher (B4-dispatch,
DWP 2026-06-25__16-01-41 -- the cli.py decomposition R5 step).

Promoted from the spike tests/one-offs/thinking/spike_verb_level_dispatch.py,
now exercising the REAL verb_plan / _dispatch_verb_target against a real,
isolated AggregatorEngine. Covers the DWP acceptance checks AC-D1..AC-D7:
the inspect/toggle unifier, the one-path routing for both verb kinds, the
no-ladder contract, off-level pruning (no wrong-level action), and the
unknown-verb / unresolved-target fallthrough.
"""
import inspect

from dazzlecmd import cli
from dazzlecmd import dispatch as _dispatch_mod
from dazzlecmd.cli import verb_plan, _dispatch_verb_target
from dazzlecmd_lib.engine import AggregatorEngine
from dazzlecmd_lib.testing import make_tool, make_kit


def _engine(tmp_path):
    eng = AggregatorEngine(name="dazzlecmd", command="dz",
                           config_dir=str(tmp_path))
    eng.fqcn_index.insert_canonical(make_tool(
        name="thetool", namespace="core", _fqcn="core:thetool",
        short_name="thetool", kit_import_name="core"))
    eng.kits = [make_kit(name="thekit")]
    return eng


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _stub_table(monkeypatch):
    """Replace the handler table with recording stubs so a test asserts WHICH
    <level>_<verb> tag was hit, independent of render output."""
    calls = []

    def mk(tag):
        def handler(res, args, projects, kits, project_root, engine):
            calls.append((tag, getattr(res.entity, "name", res.entity)))
            return 0
        return handler

    table = {t: mk(t) for t in ("tool_info", "kit_info", "aggregator_info")}
    # R6/R7 decomposition: the LIVE table binds in dazzlecmd.dispatch
    # (cli re-exports it); patch the module the dispatcher actually reads.
    monkeypatch.setattr(_dispatch_mod, "_VERB_LEVEL_HANDLERS", table)
    return calls


# --- verb_plan: the inspect/toggle unifier (AC-D3 keying) -------------------

def test_verb_plan_inspect_verb_keys_per_level():
    applies_at, mutating, tag_fn = verb_plan("info")
    assert applies_at is None
    assert mutating is False
    assert tag_fn("tool") == "tool_info"
    assert tag_fn("kit") == "kit_info"
    assert tag_fn("aggregator") == "aggregator_info"


def test_verb_plan_toggle_verb_keys_via_meta_tag_for():
    applies_at, mutating, tag_fn = verb_plan("enable")
    assert mutating is True
    assert "kit" in applies_at
    assert tag_fn("kit") == "kit_enable"


def test_verb_plan_unknown_verb_is_none():
    assert verb_plan("teleport") is None


# --- the dispatcher: one path routes every level (AC-D3) --------------------

def test_info_routes_to_tool_handler(tmp_path, monkeypatch):
    calls = _stub_table(monkeypatch)
    eng = _engine(tmp_path)
    rc = _dispatch_verb_target(
        "info", "thetool", _Args(), [], [], str(tmp_path), eng)
    assert rc == 0
    assert calls and calls[0][0] == "tool_info"


def test_info_routes_to_kit_handler(tmp_path, monkeypatch):
    calls = _stub_table(monkeypatch)
    eng = _engine(tmp_path)
    rc = _dispatch_verb_target(
        "info", "thekit", _Args(), [], [], str(tmp_path), eng)
    assert rc == 0
    assert calls and calls[0][0] == "kit_info"


def test_info_routes_to_aggregator_handler(tmp_path, monkeypatch):
    calls = _stub_table(monkeypatch)
    eng = _engine(tmp_path)
    rc = _dispatch_verb_target(
        "info", "dz", _Args(), [], [], str(tmp_path), eng)
    assert rc == 0
    assert calls and calls[0][0] == "aggregator_info"


# --- the contract: AC-D1 no ladder, AC-D6 prune, fallthrough ---------------

def test_dispatcher_has_no_verb_or_level_ladder():
    src = inspect.getsource(_dispatch_verb_target)
    assert '== "info"' not in src
    assert '== "kit"' not in src
    assert '== "tool"' not in src
    assert '== "aggregator"' not in src
    assert "res.level ==" not in src


def test_toggle_verb_pruned_off_its_level_does_not_act(tmp_path, monkeypatch):
    calls = _stub_table(monkeypatch)
    eng = _engine(tmp_path)
    # `enable` applies_at={kit}; on a TOOL it is pruned -> target does not
    # resolve at any allowed level -> None, and NO handler runs (no wrong-level
    # mutation).
    rc = _dispatch_verb_target(
        "enable", "thetool", _Args(), [], [], str(tmp_path), eng)
    assert rc is None
    assert not calls


def test_unknown_verb_returns_none(tmp_path):
    eng = _engine(tmp_path)
    rc = _dispatch_verb_target(
        "teleport", "thekit", _Args(), [], [], str(tmp_path), eng)
    assert rc is None


def test_unresolved_target_returns_none(tmp_path):
    eng = _engine(tmp_path)
    rc = _dispatch_verb_target(
        "info", "no_such_thing", _Args(), [], [], str(tmp_path), eng)
    assert rc is None
