"""Tests for the fixuser tool.

The OS-touching functions (registry, icacls, admin/hive checks) are isolated so
the analysis + planning + rendering logic can be exercised with no admin rights
and no real registry/ACL mutation. The mutation path (do_repair) is tested with
every OS helper monkeypatched, asserting the exact action sequence.
"""

import sys
from pathlib import Path

_TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOL_DIR))
import fixuser as fx  # noqa: E402
sys.path.pop(0)

SID = "S-1-5-21-1-2-3-1014"
REAL = "C:\\Users\\u"


# -- helpers -----------------------------------------------------------------

def make_diag(shape, acl_broken, profile_list=None, real_path=REAL,
              sid=SID, name="u", hive_loaded=False, admin=True):
    d = fx.Diagnosis()
    d.target = name
    d.sid = sid
    d.name = name
    d.shape = shape
    d.profile_list = profile_list or {}
    d.real_path = real_path
    d.real_path_source = "test"
    d.acl_broken = acl_broken
    d.hive_loaded = hive_loaded
    d.is_admin = admin
    return d


def opts(**kw):
    o = fx.Options()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


# -- parse_args --------------------------------------------------------------

def test_parse_target_only():
    o = fx.parse_args(["localuser"])
    assert o.target == "localuser" and not o.repair and o.verbosity == 0


def test_parse_repair_and_aliases():
    assert fx.parse_args(["u", "--repair"]).repair
    assert fx.parse_args(["u", "--fix"]).repair


def test_parse_flags():
    o = fx.parse_args(["u", "--harden", "--acls-only", "-y"])
    assert o.harden and o.acls_only and o.yes


def test_parse_verbosity_counts():
    assert fx.parse_args(["u", "-v"]).verbosity == 1
    assert fx.parse_args(["u", "-vvv"]).verbosity == 3
    assert fx.parse_args(["u", "-v", "-v"]).verbosity == 2


def test_parse_backup_dir():
    o = fx.parse_args(["--backup-dir", "D:\\b", "u"])
    assert o.backup_dir == "D:\\b" and o.target == "u"


def test_parse_help():
    assert fx.parse_args(["-h"]).help


def test_parse_unknown_option_raises():
    try:
        fx.parse_args(["u", "--bogus"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_parse_two_positionals_raises():
    try:
        fx.parse_args(["a", "b"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


# -- is_temp_path ------------------------------------------------------------

def test_is_temp_path():
    assert fx.is_temp_path("C:\\Users\\TEMP")
    assert fx.is_temp_path("C:\\Users\\TEMP\\")
    assert fx.is_temp_path("C:\\Users\\temp")      # case-insensitive
    assert not fx.is_temp_path("C:\\Users\\localuser")
    assert not fx.is_temp_path(None)
    assert not fx.is_temp_path("")


# -- classify_shape ----------------------------------------------------------

def test_shape_healthy():
    pl = {SID: {"path": REAL, "state": 0}}
    assert fx.classify_shape(SID, pl) == "healthy"


def test_shape_healthy_state_missing():
    pl = {SID: {"path": REAL, "state": None}}
    assert fx.classify_shape(SID, pl) == "healthy"


def test_shape_state_nonzero():
    pl = {SID: {"path": REAL, "state": 32768}}
    assert fx.classify_shape(SID, pl) == "state_nonzero"


def test_shape_temp_active_no_bak():
    pl = {SID: {"path": "C:\\Users\\TEMP", "state": 18948}}
    assert fx.classify_shape(SID, pl) == "temp_active_no_bak"


def test_shape_bak_only():
    pl = {SID + ".bak": {"path": REAL, "state": 32768}}
    assert fx.classify_shape(SID, pl) == "bak_only"


def test_shape_temp_active_with_bak():
    pl = {SID: {"path": "C:\\Users\\TEMP", "state": 18948},
          SID + ".bak": {"path": REAL, "state": 32768}}
    assert fx.classify_shape(SID, pl) == "temp_active_with_bak"


def test_shape_missing():
    assert fx.classify_shape(SID, {}) == "missing"


# -- determine_real_path -----------------------------------------------------

def test_real_path_from_bak():
    pl = {SID: {"path": "C:\\Users\\TEMP"}, SID + ".bak": {"path": REAL}}
    path, _ = fx.determine_real_path(SID, "u", pl)
    assert path == REAL


def test_real_path_from_active():
    pl = {SID: {"path": REAL}}
    path, _ = fx.determine_real_path(SID, "u", pl)
    assert path == REAL


def test_real_path_derived_from_name():
    pl = {SID: {"path": "C:\\Users\\TEMP"}}
    path, src = fx.determine_real_path(SID, "u", pl, exists=lambda p: True)
    assert path.endswith("\\Users\\u") and "derived" in src


def test_real_path_unknown_when_derived_missing():
    pl = {SID: {"path": "C:\\Users\\TEMP"}}
    path, src = fx.determine_real_path(SID, "u", pl, exists=lambda p: False)
    assert path is None and "does not exist" in src


# -- analyze -----------------------------------------------------------------

def test_analyze_healthy():
    pl = {SID: {"path": REAL, "state": 0}}
    acls = {REAL: True, REAL + "\\NTUSER.DAT": True}
    d = fx.analyze("u", SID, "u", pl, acls, hive_loaded=False, admin=True)
    assert d.shape == "healthy" and d.acl_broken is False and d.healthy


def test_analyze_acl_broken():
    pl = {SID: {"path": REAL, "state": 0}}
    acls = {REAL: True, REAL + "\\UsrClass.dat": False}
    d = fx.analyze("u", SID, "u", pl, acls, hive_loaded=False, admin=True)
    assert d.acl_broken is True and not d.healthy


def test_analyze_acl_unchecked_not_broken():
    # registry-only mode: no acl results -> don't claim broken
    pl = {SID: {"path": REAL, "state": 0}}
    d = fx.analyze("u", SID, "u", pl, {}, hive_loaded=False, admin=True)
    assert d.acl_broken is None and d.healthy


def test_analyze_registry_broken_flag():
    pl = {SID + ".bak": {"path": REAL}}
    d = fx.analyze("u", SID, "u", pl, {}, hive_loaded=False, admin=True)
    assert d.registry_broken and not d.healthy


# -- build_plan --------------------------------------------------------------

def _ops(plan):
    return [a["op"] for a in plan]


def test_plan_bak_only():
    d = make_diag("bak_only", acl_broken=True,
                  profile_list={SID + ".bak": {"path": REAL, "state": 32768}})
    plan = fx.build_plan(d, opts(repair=True))
    assert _ops(plan) == ["grant_acl", "rename_key", "set_dword", "set_dword"]
    assert plan[1]["old"] == SID + ".bak" and plan[1]["new"] == SID


def test_plan_temp_active_with_bak():
    d = make_diag("temp_active_with_bak", acl_broken=True)
    plan = fx.build_plan(d, opts(repair=True))
    assert _ops(plan) == ["grant_acl", "rename_key", "rename_key", "set_dword", "set_dword"]
    assert plan[1]["new"] == SID + ".temp"      # park temp first
    assert plan[2]["old"] == SID + ".bak"        # then promote bak


def test_plan_temp_active_no_bak_with_real_path():
    d = make_diag("temp_active_no_bak", acl_broken=True, real_path=REAL)
    plan = fx.build_plan(d, opts(repair=True))
    assert "set_path" in _ops(plan)
    sp = [a for a in plan if a["op"] == "set_path"][0]
    assert sp["path"] == REAL


def test_plan_temp_active_no_bak_without_real_path_is_manual():
    d = make_diag("temp_active_no_bak", acl_broken=True, real_path=None)
    plan = fx.build_plan(d, opts(repair=True))
    assert any(a["op"] == "manual" for a in plan)


def test_plan_state_nonzero_no_grant_when_acl_ok():
    d = make_diag("state_nonzero", acl_broken=False)
    plan = fx.build_plan(d, opts(repair=True))
    assert _ops(plan) == ["set_dword"]           # State only; no ACL grant


def test_plan_registry_only_skips_acls():
    d = make_diag("bak_only", acl_broken=True)
    plan = fx.build_plan(d, opts(repair=True, registry_only=True))
    assert "grant_acl" not in _ops(plan)


def test_plan_acls_only_skips_registry():
    d = make_diag("bak_only", acl_broken=True)
    plan = fx.build_plan(d, opts(repair=True, acls_only=True))
    assert _ops(plan) == ["grant_acl"]


def test_plan_harden_adds_reprotect():
    d = make_diag("bak_only", acl_broken=True)
    plan = fx.build_plan(d, opts(repair=True, harden=True))
    assert "harden_acl" in _ops(plan)
    h = [a for a in plan if a["op"] == "harden_acl"][0]
    assert any(SID in g for g in h["grants"]) and any(fx.SID_SYSTEM in g for g in h["grants"])


def test_plan_grant_uses_sid_full_inherit():
    d = make_diag("bak_only", acl_broken=True)
    plan = fx.build_plan(d, opts(repair=True))
    g = [a for a in plan if a["op"] == "grant_acl"][0]
    assert g["grants"] == [f"*{SID}:(OI)(CI)F"]


# -- _principal_matches ------------------------------------------------------

def test_principal_matches():
    names = {"u", "PlzWork\\u"}
    assert fx._principal_matches("PlzWork\\u", names, SID)
    assert fx._principal_matches("u", names, SID)
    assert fx._principal_matches(SID, names, SID)
    assert fx._principal_matches("*" + SID, names, SID)
    assert not fx._principal_matches("BUILTIN\\Users", names, SID)


# -- render / verbosity ------------------------------------------------------

def test_render_shape_name_at_v0(capsys):
    d = make_diag("bak_only", acl_broken=True,
                  profile_list={SID + ".bak": {"path": REAL, "state": 32768}})
    fx.render(d, fx.build_plan(d, opts(repair=False)), opts(verbosity=0))
    out = capsys.readouterr().out
    assert "BAK-ONLY" in out                       # label shown at v0
    assert "needs repair" in out
    assert "the active '<SID>' key is gone" not in out   # explanation is v1


def test_render_explanation_at_v1(capsys):
    d = make_diag("bak_only", acl_broken=True,
                  profile_list={SID + ".bak": {"path": REAL, "state": 32768}})
    fx.render(d, fx.build_plan(d, opts(repair=False)), opts(verbosity=1))
    out = capsys.readouterr().out
    assert "the active '<SID>' key is gone" in out


def test_render_raw_values_at_v2(capsys):
    d = make_diag("bak_only", acl_broken=True,
                  profile_list={SID + ".bak": {"path": REAL, "state": 32768}})
    fx.render(d, fx.build_plan(d, opts(repair=False)), opts(verbosity=2))
    out = capsys.readouterr().out
    assert SID + ".bak" in out and "state=" in out


def test_render_unresolved_sid(capsys):
    d = fx.Diagnosis()
    d.target = "ghost"
    d.sid = None
    fx.render(d, [], opts(verbosity=0))
    out = capsys.readouterr().out
    assert "could not resolve 'ghost'" in out


def test_render_healthy_nothing_to_do(capsys):
    d = make_diag("healthy", acl_broken=False, profile_list={SID: {"path": REAL, "state": 0}})
    fx.render(d, fx.build_plan(d, opts()), opts(verbosity=0))
    out = capsys.readouterr().out
    assert "nothing to do" in out


# -- do_repair: refusals -----------------------------------------------------

def test_repair_refuses_without_admin(capsys):
    d = make_diag("bak_only", acl_broken=True, admin=False)
    rc = fx.do_repair(d, fx.build_plan(d, opts(repair=True)), opts(repair=True, yes=True))
    assert rc == 1 and "elevated" in capsys.readouterr().err


def test_repair_refuses_when_hive_loaded(capsys):
    d = make_diag("bak_only", acl_broken=True, hive_loaded=True)
    rc = fx.do_repair(d, fx.build_plan(d, opts(repair=True)), opts(repair=True, yes=True))
    assert rc == 1 and "loaded" in capsys.readouterr().err


# -- do_repair: execution sequence (all OS helpers mocked) -------------------

def test_repair_executes_bak_only_sequence(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(fx, "backup_profile_list", lambda dest: calls.append(("backup", dest)) or True)
    monkeypatch.setattr(fx, "snapshot_acls", lambda nodes, dest: calls.append(("snapshot", len(nodes))) or True)
    monkeypatch.setattr(fx, "loop_safe_grant", lambda p, g, verbose=False: calls.append(("grant", p, tuple(g))) or 0)
    monkeypatch.setattr(fx, "rename_profile_key", lambda old, new: calls.append(("rename", old, new)))
    monkeypatch.setattr(fx, "set_profile_dword", lambda k, n, v: calls.append(("dword", n, v)))
    monkeypatch.setattr(fx.os, "makedirs", lambda *a, **k: None)

    d = make_diag("bak_only", acl_broken=True,
                  profile_list={SID + ".bak": {"path": REAL, "state": 32768}})
    o = opts(repair=True, yes=True, backup_dir=str(tmp_path))
    rc = fx.do_repair(d, fx.build_plan(d, o), o)

    assert rc == 0
    kinds = [c[0] for c in calls]
    assert kinds[0] == "backup"                       # backup before mutating
    assert ("grant", REAL, (f"*{SID}:(OI)(CI)F",)) in calls
    assert ("rename", SID + ".bak", SID) in calls
    assert ("dword", "State", 0) in calls
    assert ("dword", "RefCount", 0) in calls
    # grant happens before the registry rename
    assert kinds.index("grant") < kinds.index("rename")


def test_repair_missing_shape_is_noop(capsys):
    d = make_diag("missing", acl_broken=None, real_path=None, profile_list={})
    o = opts(repair=True, yes=True)
    rc = fx.do_repair(d, fx.build_plan(d, o), o)
    assert rc in (0, 2)
    assert "Nothing to repair" in capsys.readouterr().out
