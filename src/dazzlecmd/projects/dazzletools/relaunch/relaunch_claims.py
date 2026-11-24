"""Claims, sessions and history for ``dz relaunch``.

A *claim* records that one terminal tab holds one member of a set. The tab is
identified by its *anchor* process (the shell below the terminal host, see
``dazzlecmd._vendor.procs.find_anchor``) plus that process's exe and creation
time; a claim is stale only on positive evidence that the anchor is gone or is
a different process. Unknown (details unreadable) counts as held.

A *session* is a run of claims: a claim starts a new session when no claim in
the store is alive, or when the machine booted since the current session began
(so a restart is always noticed). History is written at claim time; reading
it ("what was open last session") never writes.

All writes happen under the store lock (dazzle-filekit ``exclusive_lock`` on
``<home>/.lock``). The lock is never held across a prompt, the csb call, an
editor, or a running child -- callers resolve those first.

Design of record: final DWP 4.3, Addendum A3, Addendum C.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import relaunch_store as rs

BOOT_TOLERANCE_S = 600
HISTORY_DEPTH = 20
LOCK_TIMEOUT_S = 5.0


class ClaimError(Exception):
    """A claim was refused; ``code`` says why (for the CLI's exit code / prompt)."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code   # "held-elsewhere" | "tab-holds-other" | "none-free" | "disabled" | "not-found"


# --------------------------------------------------------------------------
# the tab
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Tab:
    pid: int
    exe: Optional[str]
    start_time: Optional[int]
    rule: str
    wt_session: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"pid": self.pid, "exe": self.exe, "start_time": self.start_time,
                "rule": self.rule, "wt_session": self.wt_session}

    def matches(self, anchor: Dict[str, Any]) -> bool:
        """Is this recorded anchor this same tab process?"""
        if anchor.get("pid") != self.pid:
            return False
        st = anchor.get("start_time")
        return st is None or self.start_time is None or st == self.start_time


def current_tab(pid: Optional[int] = None) -> Tab:
    """Identify the tab this process runs in."""
    from dazzlecmd._vendor import procs
    table = procs.process_table()
    anchor, rule = procs.find_anchor(pid or os.getpid(), table)
    return Tab(anchor, procs.process_exe(anchor, table), procs.process_start_time(anchor), rule,
               os.environ.get("WT_SESSION"))


def default_liveness(anchor: Dict[str, Any]) -> Optional[bool]:
    from dazzlecmd._vendor import procs
    return procs.same_process(int(anchor.get("pid", 0)), anchor.get("exe"), anchor.get("start_time"))


def default_boot() -> Optional[float]:
    from dazzlecmd._vendor import procs
    return procs.boot_time()


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------

def claims_path(home: Optional[str] = None) -> str:
    return os.path.join(rs.local_dir(home), "claims.json")


def history_path(home: Optional[str] = None) -> str:
    return os.path.join(rs.local_dir(home), "history.json")


def lock_path(home: Optional[str] = None) -> str:
    return os.path.join(home or rs.relaunch_home(), ".lock")


def store_lock(home: Optional[str] = None, timeout: float = LOCK_TIMEOUT_S):
    """The store-wide lock, for write paths only (reads never call this)."""
    from dazzle_filekit.locking import exclusive_lock
    return exclusive_lock(lock_path(home), timeout=timeout)


def _read(path: str, empty: Dict[str, Any]) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return empty
    data = rs._read_json(path)
    if not isinstance(data, dict):
        raise rs.StoreError(f"{path}: not a JSON object -- fix or remove it; it was not changed")
    return data


def load_claims(home: Optional[str] = None) -> List[Dict[str, Any]]:
    return list(_read(claims_path(home), {"format": 1, "claims": []}).get("claims", []))


def load_history(home: Optional[str] = None) -> Dict[str, Any]:
    h = _read(history_path(home), {})
    h.setdefault("format", 1)
    h.setdefault("next_session", 1)
    h.setdefault("sessions", [])
    h.setdefault("opened", {})
    return h


def _write(path: str, data: Dict[str, Any]) -> None:
    from dazzle_filekit import atomic_write_json
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_json(path, data, indent=2, default=None)


# --------------------------------------------------------------------------
# pure helpers (no I/O)
# --------------------------------------------------------------------------

def live_claims(claims: Iterable[Dict[str, Any]],
                liveness: Callable[[Dict[str, Any]], Optional[bool]]) -> List[Dict[str, Any]]:
    """Claims whose anchor is alive or unknown (unknown = held)."""
    return [c for c in claims if liveness(c.get("anchor", {})) is not False]


def claim_of_tab(claims: Iterable[Dict[str, Any]], tab: Tab) -> Optional[Dict[str, Any]]:
    for c in claims:
        if tab.matches(c.get("anchor", {})):
            return c
    return None


def current_session(history: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return history["sessions"][0] if history.get("sessions") else None


def recency(history: Dict[str, Any], set_name: str, member_id: int) -> Optional[int]:
    """The most recent session number in which this member was opened, or None."""
    nums = history.get("opened", {}).get(set_name, {}).get(str(member_id), [])
    return max(nums) if nums else None


def order_free(doc: Dict[str, Any], held_ids: Iterable[int], history: Dict[str, Any],
               skip_ids: Iterable[int] = ()) -> List[Dict[str, Any]]:
    """Free, enabled members: most recently opened session first, never-opened last (set order)."""
    held, skip = set(held_ids), set(skip_ids)
    free = [m for m in doc["members"] if m["id"] not in held and m["id"] not in skip
            and not m.get("detach")
            and not m.get("disabled")]
    pos = {m["id"]: i for i, m in enumerate(doc["members"])}

    def key(m):
        r = recency(history, doc["name"], m["id"])
        return (0, -r, pos[m["id"]]) if r is not None else (1, 0, pos[m["id"]])
    return sorted(free, key=key)


def tag(history: Dict[str, Any], set_name: str, member_id: int, session_live: bool,
        boot_now: Optional[float] = None) -> str:
    """The recency tag shown beside a member (Addendum A3).

    ``session_live``: some claim of the current session is still alive. Then
    "last session" is the one before it; otherwise it is the current (ended) one.
    """
    r = recency(history, set_name, member_id)
    if r is None:
        return "never opened"
    cur = current_session(history)
    if cur is None:
        return "never opened"
    if session_live and r == cur["n"]:
        return "open this session"
    last = cur["n"] - 1 if session_live else cur["n"]
    ago = last - r + 1
    if ago > 1:
        return f"last open {ago} sessions ago"
    after = _session(history, r + 1)
    if after is not None:
        why = "before restart" if after.get("began") == "restart" else "closed this boot"
    else:
        s = _session(history, r)
        b = s.get("boot_at") if s else None
        if boot_now is not None and b is not None and abs(boot_now - b) > BOOT_TOLERANCE_S:
            why = "before restart"
        else:
            why = "closed this boot"
    return f"open last session -- {why}"


def _session(history: Dict[str, Any], n: int) -> Optional[Dict[str, Any]]:
    for s in history.get("sessions", []):
        if s.get("n") == n:
            return s
    return None


def needs_new_session(history: Dict[str, Any], any_live: bool, boot: Optional[float]) -> Optional[str]:
    """'restart' / 'all-closed' when a claim must start a new session, else None."""
    cur = current_session(history)
    if cur is None:
        return "restart" if boot is not None else "all-closed"
    cur_boot = cur.get("boot_at")
    if boot is not None and cur_boot is not None and abs(boot - cur_boot) > BOOT_TOLERANCE_S:
        return "restart"
    if not any_live:
        return "all-closed"
    return None


# --------------------------------------------------------------------------
# claim / release
# --------------------------------------------------------------------------

@dataclass
class ClaimResult:
    set_name: str
    member: Dict[str, Any]
    instance: int
    already: bool                    # this tab already held it (idempotent re-claim)
    session: int
    new_session: Optional[str]       # "restart" | "all-closed" | None
    next_member: Optional[Dict[str, Any]] = None
    next_tag: str = ""
    member_tag: str = ""
    released: Optional[Dict[str, Any]] = None
    added_open: bool = False          # this claim marked the member opened in its session


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def claim(set_name: str, tab: Tab, member_ref: Optional[str] = None, *,
          allow_duplicate: bool = False, take_next: bool = False, level: str = "print",
          skip_ids: Iterable[int] = (), home: Optional[str] = None,
          liveness: Callable[[Dict[str, Any]], Optional[bool]] = None,
          boot: Callable[[], Optional[float]] = None,
          lock_timeout: float = LOCK_TIMEOUT_S) -> ClaimResult:
    """Take a member of ``set_name`` for ``tab`` (see module docstring).

    ``skip_ids`` are members to pass over for a bare claim (csb reports them
    open -- advisory). Raises ClaimError with a ``code`` on refusal.
    """
    liveness = liveness or default_liveness
    boot_now = (boot or default_boot)()
    with store_lock(home, lock_timeout):
        doc = rs.load_set(set_name, home)
        claims = load_claims(home)
        history = load_history(home)
        live = live_claims(claims, liveness)
        mine = claim_of_tab(live, tab)
        released = None

        if mine is not None and mine["set"] != doc["name"]:
            raise ClaimError(f"this tab already holds {mine['set']}:{mine['member_id']} -- "
                             f"release it first (dz relaunch {mine['set']} release)", "tab-holds-other")

        if mine is not None and not take_next:
            if member_ref is None or rs.find_member(doc, member_ref)["id"] == mine["member_id"]:
                m = rs.find_member(doc, str(mine["member_id"]))
                cur = current_session(history)
                return _finish(doc, m, mine["instance"], True, cur["n"] if cur else 0, None,
                               live, history, skip_ids)
            raise ClaimError(f"this tab already holds {doc['name']}:{mine['member_id']} -- "
                             f"use --next, or release it first", "tab-holds-other")

        others = [c for c in live if c is not mine]
        held_here = [c["member_id"] for c in others if c["set"] == doc["name"]]

        if member_ref is not None:
            m = rs.find_member(doc, member_ref)
            if m.get("detach"):
                raise ClaimError(f"{doc['name']}:{m['id']} is detached (it needs no tab) -- "
                                 f"start it with: dz relaunch {doc['name']} launch {m.get('label') or m['id']}",
                                 "detached")
            if m.get("disabled"):
                raise ClaimError(f"{doc['name']}:{m['id']} is disabled -- enable it first", "disabled")
            if m["id"] in held_here and not allow_duplicate:
                raise ClaimError(f"{doc['name']}:{m['id']} ({m.get('label') or m['kind']}) is open in "
                                 f"another tab -- --yes starts a second copy", "held-elsewhere")
        else:
            exclude = set(held_here)
            if mine is not None:
                exclude.add(mine["member_id"])
            candidates = order_free(doc, exclude, history, skip_ids)
            if take_next and mine is not None:
                # --next walks forward: members already opened in this session go last,
                # so a tab stepping through a set never bounces back to what it just left
                cur = current_session(history)
                this_n = cur["n"] if cur else None
                candidates.sort(key=lambda c: this_n in history.get("opened", {}).get(
                    doc["name"], {}).get(str(c["id"]), []))
            if not candidates:
                n = len([x for x in doc["members"] if not x.get("disabled") and not x.get("detach")])
                raise ClaimError(f"all {n} members of {doc['name']} are claimed -- nothing left to claim",
                                 "none-free")
            m = candidates[0]

        taken = {c["instance"] for c in others if c["set"] == doc["name"] and c["member_id"] == m["id"]}
        instance = 1
        while instance in taken:
            instance += 1

        # this tab swapping its own member (--next) keeps the session going
        any_live_besides_me = bool(others) or mine is not None
        reason = needs_new_session(history, any_live_besides_me, boot_now)
        if reason:
            n = history["next_session"]
            history["sessions"].insert(0, {"n": n, "started_at": _now_iso(), "boot_at": boot_now,
                                           "began": reason})
            history["next_session"] = n + 1
        session_n = history["sessions"][0]["n"]

        new_claims = [c for c in live if c is not mine]
        if mine is not None:
            released = mine
        new_claims.append({"set": doc["name"], "member_id": m["id"], "instance": instance,
                           "claimed_at": _now_iso(), "session": session_n, "level": level,
                           "anchor": tab.as_dict(), "boot_at": boot_now})
        opened = history["opened"].setdefault(doc["name"], {}).setdefault(str(m["id"]), [])
        added_open = session_n not in opened
        if added_open:
            opened.insert(0, session_n)
            del opened[HISTORY_DEPTH:]
        _write(claims_path(home), {"format": 1, "claims": new_claims})
        _write(history_path(home), history)
        res = _finish(doc, m, instance, False, session_n, reason, new_claims, history, skip_ids)
        res.released = released
        res.added_open = added_open
        return res


def swap_member_refs_unlocked(set_name: str, a: int, b: int, home: Optional[str] = None) -> None:
    """Exchange member ids ``a`` and ``b`` in claims and history. The caller holds the store lock
    (``swap`` renumbers the two members in the same lock, so nothing sees a half-swapped set)."""
    swap = {a: b, b: a}
    claims = load_claims(home)
    for c in claims:
        if c.get("set") == set_name and c.get("member_id") in swap:
            c["member_id"] = swap[c["member_id"]]
    history = load_history(home)
    opened = history.get("opened", {}).get(set_name)
    if opened is not None:
        ka, kb = str(a), str(b)
        va, vb = opened.pop(ka, None), opened.pop(kb, None)
        if va is not None:
            opened[kb] = va
        if vb is not None:
            opened[ka] = vb
    _write(claims_path(home), {"format": 1, "claims": claims})
    _write(history_path(home), history)


def unclaim(result: "ClaimResult", tab: Tab, *, home: Optional[str] = None,
            liveness: Callable[[Dict[str, Any]], Optional[bool]] = None,
            lock_timeout: float = LOCK_TIMEOUT_S) -> bool:
    """Undo a claim this command just made -- a declined ``claim -o`` gives the member back.

    Removes exactly what ``claim`` added, under the store lock: this tab's claim row; the member's
    opened mark for that session, if this claim added it and no other live claim of the member
    shares the session; the session itself, if this claim started it, nothing else belongs to it
    and it is still the newest (so the next claim does not start a phantom session -- the 0.13.10
    shape). A claim the tab already held before the command is never undone. Returns True if a
    claim was removed.
    """
    if result.already:
        return False
    liveness = liveness or default_liveness
    mid = result.member["id"]
    anchor = tab.as_dict()
    with store_lock(home, lock_timeout):
        claims = load_claims(home)
        history = load_history(home)
        keep, dropped = [], False
        for c in claims:
            if (not dropped and c.get("set") == result.set_name and c.get("member_id") == mid
                    and c.get("instance") == result.instance and c.get("anchor") == anchor):
                dropped = True
                continue
            keep.append(c)
        if not dropped:
            return False
        live_rest = live_claims(keep, liveness)
        if result.added_open and not any(c["set"] == result.set_name and c["member_id"] == mid
                                         and c.get("session") == result.session for c in live_rest):
            opened = history.get("opened", {}).get(result.set_name, {}).get(str(mid), [])
            if result.session in opened:
                opened.remove(result.session)
        if result.new_session:
            sessions = history.get("sessions", [])
            if (sessions and sessions[0].get("n") == result.session
                    and history.get("next_session") == result.session + 1
                    and not any(c.get("session") == result.session for c in live_rest)):
                sessions.pop(0)
                history["next_session"] = result.session
        _write(claims_path(home), {"format": 1, "claims": keep})
        _write(history_path(home), history)
        return True


def _finish(doc, m, instance, already, session_n, reason, live, history, skip_ids) -> ClaimResult:
    held = [c["member_id"] for c in live if c["set"] == doc["name"]]
    nxt = order_free(doc, held + [m["id"]], history, skip_ids)
    res = ClaimResult(doc["name"], m, instance, already, session_n, reason)
    res.member_tag = tag(history, doc["name"], m["id"], session_live=True)
    if nxt:
        res.next_member = nxt[0]
        res.next_tag = tag(history, doc["name"], nxt[0]["id"], session_live=True)
    return res


def release(tab: Tab, set_name: Optional[str] = None, member_ref: Optional[str] = None, *,
            all_in_set: bool = False, home: Optional[str] = None,
            liveness: Callable[[Dict[str, Any]], Optional[bool]] = None,
            lock_timeout: float = LOCK_TIMEOUT_S) -> List[Dict[str, Any]]:
    """Drop claims: this tab's, a named member's, or every claim in a set. Returns what was dropped."""
    liveness = liveness or default_liveness
    with store_lock(home, lock_timeout):
        claims = live_claims(load_claims(home), liveness)
        if all_in_set:
            if not set_name:
                raise ClaimError("--all needs a set name", "not-found")
            name = rs.canonical_name(set_name) if not rs.is_reserved(set_name) else set_name.lower()
            drop = [c for c in claims if c["set"] == name]
        elif member_ref is not None:
            doc = rs.load_set(set_name, home)
            mid = rs.find_member(doc, member_ref)["id"]
            drop = [c for c in claims if c["set"] == doc["name"] and c["member_id"] == mid]
        else:
            drop = [c for c in claims if tab.matches(c.get("anchor", {}))
                    and (set_name is None or c["set"] == set_name.lower())]
        keep = [c for c in claims if c not in drop]
        _write(claims_path(home), {"format": 1, "claims": keep})
        return drop


def snapshot(home: Optional[str] = None,
             liveness: Callable[[Dict[str, Any]], Optional[bool]] = None
             ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """(live claims, history) for read verbs -- takes no lock and writes nothing."""
    return live_claims(load_claims(home), liveness or default_liveness), load_history(home)
