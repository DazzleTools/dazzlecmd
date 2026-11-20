"""poc11 -- is "launched in session N" (history) a sound record for `launch` once per restart?

Collab 2026-11-19 detach-and-install, Q2. No process is started and no window can appear:
this only calls relaunch_claims with a temp store, an injected boot time and injected liveness.

Predictions to falsify:
  P1  after a restart, before any claim, "the current session" is already the new one
  P2  if `launch` opens a session itself, the claims that follow stay in that session
"""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src", "dazzlecmd", "projects", "dazzletools", "relaunch"))
home = tempfile.mkdtemp(prefix="dzr-poc11-")
os.environ["DZ_RELAUNCH_HOME"] = home
import relaunch_store as rs, relaunch_claims as rc

doc = rs.new_set("ck3")
rs.add_member(doc, {"kind": "folder", "cwd": home})
rs.add_member(doc, {"kind": "folder", "cwd": home})
rs.save_set(doc, home)
tab1 = rc.Tab(1111, "cmd.exe", 1, "poc")
tab2 = rc.Tab(2222, "cmd.exe", 2, "poc")
alive = lambda a: True
dead = lambda a: False

r = rc.claim("ck3", tab1, home=home, liveness=alive, boot=lambda: 1000.0)
print("boot A: first claim -> session", r.session, r.new_session)

# --- restart: boot time changes, every old anchor is dead, nobody has claimed yet
h = rc.load_history(home)
cur = rc.current_session(h)
print("P1 after restart, before any claim: current_session =", cur["n"], "boot_at", cur["boot_at"],
      "-> a `launch` keyed on this number sees the PRE-restart session")
print("   needs_new_session(boot B) says:", rc.needs_new_session(h, False, 99999.0))

# --- suppose `launch` opened session 2 itself (as claim does), holding no claim
h["sessions"].insert(0, {"n": h["next_session"], "started_at": "x", "boot_at": 99999.0, "began": "restart"})
h["next_session"] += 1
rc._write(rc.history_path(home), h)
print("launch opened session", rc.current_session(rc.load_history(home))["n"])
r = rc.claim("ck3", tab2, home=home, liveness=dead, boot=lambda: 99999.0)
print("P2 first claim after that launch -> session", r.session, "reason:", r.new_session,
      "-> launch's record (session 2) no longer matches; a second `launch` would start everything again")
