"""S3: claims, instances, sessions, history, recency order."""

import json
import os
import subprocess
import sys
import textwrap
import time

import pytest

import relaunch_claims as rc
import relaunch_store as rs

TOOL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def make_set(name="ck3", n=4):
    doc = rs.new_set(name)
    for i in range(1, n + 1):
        rs.add_member(doc, {"kind": "folder", "label": f"m{i}", "cwd": os.getcwd()})
    rs.save_set(doc)
    return doc


class World:
    """Fake liveness and boot clock."""

    def __init__(self):
        self.alive = {}       # pid -> True/False/None
        self.boot_at = 1000.0

    def tab(self, pid, start=1):
        self.alive[pid] = True
        return rc.Tab(pid, "cmd.exe", start, "below-host:windowsterminal.exe")

    def liveness(self, anchor):
        return self.alive.get(anchor.get("pid"), False)

    def boot(self):
        return self.boot_at

    def kw(self):
        return dict(liveness=self.liveness, boot=self.boot)


@pytest.fixture
def w():
    return World()


def test_bare_claims_take_successive_members(w):
    make_set()
    a = rc.claim("ck3", w.tab(1), **w.kw())
    b = rc.claim("ck3", w.tab(2), **w.kw())
    assert (a.member["id"], b.member["id"]) == (1, 2)
    assert b.next_member["id"] == 3


def test_claim_is_idempotent_per_tab(w):
    make_set()
    t = w.tab(1)
    first = rc.claim("ck3", t, **w.kw())
    again = rc.claim("ck3", t, **w.kw())
    assert again.already and again.member["id"] == first.member["id"]
    assert len(rc.load_claims()) == 1


def test_one_claim_per_tab_across_sets(w):
    make_set("ck3")
    make_set("dz")
    t = w.tab(1)
    rc.claim("ck3", t, **w.kw())
    with pytest.raises(rc.ClaimError) as e:
        rc.claim("dz", t, **w.kw())
    assert e.value.code == "tab-holds-other"


def test_next_takes_another_and_releases_the_old(w):
    make_set()
    t = w.tab(1)
    rc.claim("ck3", t, **w.kw())
    r = rc.claim("ck3", t, take_next=True, **w.kw())
    assert r.member["id"] == 2 and r.released["member_id"] == 1
    assert [c["member_id"] for c in rc.load_claims()] == [2]


def test_duplicate_needs_permission_and_gets_instance_2(w):
    make_set()
    rc.claim("ck3", w.tab(1), "m1", **w.kw())
    with pytest.raises(rc.ClaimError) as e:
        rc.claim("ck3", w.tab(2), "m1", **w.kw())
    assert e.value.code == "held-elsewhere"
    r = rc.claim("ck3", w.tab(2), "m1", allow_duplicate=True, **w.kw())
    assert r.instance == 2


def test_dead_anchor_frees_the_member_unknown_keeps_it(w):
    make_set(n=2)
    rc.claim("ck3", w.tab(1), **w.kw())
    rc.claim("ck3", w.tab(2), **w.kw())
    w.alive[1] = False          # tab 1 closed
    w.alive[2] = None           # tab 2 unreadable -> held
    r = rc.claim("ck3", w.tab(3), **w.kw())
    assert r.member["id"] == 1
    with pytest.raises(rc.ClaimError) as e:
        rc.claim("ck3", w.tab(4), **w.kw())
    assert e.value.code == "none-free"


def test_disabled_members_are_skipped_and_refused(w):
    doc = make_set(n=2)
    rs.set_member_disabled(doc, "m1", True)
    rs.save_set(doc)
    assert rc.claim("ck3", w.tab(1), **w.kw()).member["id"] == 2
    with pytest.raises(rc.ClaimError) as e:
        rc.claim("ck3", w.tab(2), "m1", **w.kw())
    assert e.value.code == "disabled"


def test_skip_ids_are_passed_over(w):
    make_set(n=3)
    r = rc.claim("ck3", w.tab(1), skip_ids=[1], **w.kw())
    assert r.member["id"] == 2


def test_sessions_start_on_all_closed_and_on_restart(w):
    make_set()
    a = rc.claim("ck3", w.tab(1), **w.kw())
    assert (a.session, a.new_session) == (1, "restart")
    b = rc.claim("ck3", w.tab(2), **w.kw())
    assert (b.session, b.new_session) == (1, None)
    w.alive[1] = w.alive[2] = False            # every tab closed, same boot
    c = rc.claim("ck3", w.tab(3), **w.kw())
    assert (c.session, c.new_session) == (2, "all-closed")
    w.boot_at += 5000                          # the machine restarted
    d = rc.claim("ck3", w.tab(4), **w.kw())
    assert (d.session, d.new_session) == (3, "restart")


def test_boot_drift_within_tolerance_is_not_a_restart(w):
    make_set()
    rc.claim("ck3", w.tab(1), **w.kw())
    w.boot_at += 30
    assert rc.claim("ck3", w.tab(2), **w.kw()).new_session is None


def test_last_sessions_members_come_back_first_with_tags(w):
    make_set(n=4)
    rc.claim("ck3", w.tab(1), "m3", **w.kw())          # session 1: only m3 used
    w.alive[1] = False
    r = rc.claim("ck3", w.tab(2), **w.kw())            # session 2
    assert r.member["id"] == 3                         # recency beats set order
    assert r.next_member["id"] == 1 and r.next_tag == "never opened"
    claims, hist = rc.snapshot(liveness=w.liveness)
    assert rc.tag(hist, "ck3", 3, session_live=True) == "open this session"


def test_tags_name_why_the_last_session_ended(w):
    make_set(n=3)
    rc.claim("ck3", w.tab(1), "m1", **w.kw())          # session 1
    w.alive[1] = False
    rc.claim("ck3", w.tab(2), "m2", **w.kw())          # session 2 (all-closed)
    w.alive[2] = False
    w.boot_at += 5000
    rc.claim("ck3", w.tab(3), "m3", **w.kw())          # session 3 (restart)
    _, hist = rc.snapshot(liveness=w.liveness)
    assert rc.tag(hist, "ck3", 2, session_live=True) == "open last session -- before restart"
    assert rc.tag(hist, "ck3", 1, session_live=True) == "last open 2 sessions ago"
    w.alive[3] = False                                  # everything closed, no new claim yet
    _, hist = rc.snapshot(liveness=w.liveness)
    assert rc.tag(hist, "ck3", 3, session_live=False, boot_now=w.boot_at) == \
        "open last session -- closed this boot"
    assert rc.tag(hist, "ck3", 3, session_live=False, boot_now=w.boot_at + 9999) == \
        "open last session -- before restart"


def test_release_this_tab_and_all(w):
    make_set()
    t1, t2 = w.tab(1), w.tab(2)
    rc.claim("ck3", t1, **w.kw())
    rc.claim("ck3", t2, **w.kw())
    assert [c["member_id"] for c in rc.release(t1, liveness=w.liveness)] == [1]
    assert len(rc.release(t2, "ck3", all_in_set=True, liveness=w.liveness)) == 1
    assert rc.load_claims() == []


def test_snapshot_reads_without_writing(w, relaunch_home):
    make_set()
    rc.claim("ck3", w.tab(1), **w.kw())
    before = {p: os.path.getmtime(os.path.join(dp, p))
              for dp, _, fs in os.walk(relaunch_home) for p in fs}
    names_before = sorted(before)
    rc.snapshot(liveness=w.liveness)
    after = {p: os.path.getmtime(os.path.join(dp, p))
             for dp, _, fs in os.walk(relaunch_home) for p in fs}
    assert sorted(after) == names_before and after == before


CLAIMER = textwrap.dedent("""
    import json, os, sys, time
    sys.path.insert(0, sys.argv[1])
    import relaunch_claims as rc
    go = sys.argv[2]
    while not os.path.exists(go):
        time.sleep(0.005)
    from dazzlecmd._vendor import procs
    me = os.getpid()
    tab = rc.Tab(me, procs.process_exe(me), procs.process_start_time(me), "test")
    try:
        r = rc.claim("ck3", tab, boot=lambda: 1000.0, lock_timeout=30)
        print(json.dumps({"ok": r.member["id"]}), flush=True)
    except rc.ClaimError as e:
        print(json.dumps({"err": e.code}), flush=True)
    # stay alive (like a real tab) until the test has every answer
    done = sys.argv[3]
    deadline = time.time() + 60
    while not os.path.exists(done) and time.time() < deadline:
        time.sleep(0.01)
""")


def _race(tmp_path, n_procs):
    go, done = tmp_path / "go", tmp_path / "done"
    procs = [subprocess.Popen([sys.executable, "-c", CLAIMER, TOOL_DIR, str(go), str(done)],
                              stdout=subprocess.PIPE, text=True) for _ in range(n_procs)]
    time.sleep(0.5)
    go.write_text("go")
    out = []
    try:
        for p in procs:
            out.append(json.loads(p.stdout.readline().strip()))
    finally:
        done.write_text("done")
        for p in procs:
            p.communicate(timeout=120)
    return out


def test_concurrent_claims_never_share_a_member(tmp_path):
    make_set(n=4)
    out = _race(tmp_path, 6)
    got = [o["ok"] for o in out if "ok" in o]
    assert sorted(got) == [1, 2, 3, 4]
    assert [o["err"] for o in out if "err" in o] == ["none-free", "none-free"]


def test_concurrent_claims_replace_stale_ones_once(tmp_path):
    make_set(n=4)
    stale = [{"set": "ck3", "member_id": i, "instance": 1, "claimed_at": "x", "session": 1,
              "level": "print", "anchor": {"pid": 999990 + i, "exe": "cmd.exe", "start_time": 1,
                                           "rule": "test"}, "boot_at": 1000.0}
             for i in range(1, 5)]
    os.makedirs(rs.local_dir(), exist_ok=True)
    with open(rc.claims_path(), "w", encoding="utf-8") as f:
        json.dump({"format": 1, "claims": stale}, f)
    out = _race(tmp_path, 5)
    got = [o["ok"] for o in out if "ok" in o]
    assert sorted(got) == [1, 2, 3, 4]
