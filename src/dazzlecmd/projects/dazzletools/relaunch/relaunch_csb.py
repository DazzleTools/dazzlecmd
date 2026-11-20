"""csb, read-only: resolve Claude sessions and see which are open.

relaunch never reads csb's files and never runs a csb command that writes
(``set new|add|rm|forget``); the write-back slice is a later arc. One csb
call per relaunch command at most, with a timeout; when csb is missing or
silent, Claude members show "csb did not answer" and nothing blocks.
csb's ``live_status`` is advisory: on this box every live session reads
``unverified`` (measured), so it can only skip members, never block them.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

TIMEOUT_S = 5.0
READ_ONLY_ARGS = (("set", "show"), ("set", "list"), ("scan",), ("--version",))
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


class CsbUnavailable(Exception):
    pass


def run_csb(args: List[str], timeout: float = TIMEOUT_S) -> str:
    """Run a read-only csb command and return stdout (the seam tests replace)."""
    if not any(tuple(args[:len(p)]) == p for p in READ_ONLY_ARGS):
        raise ValueError(f"relaunch only runs read-only csb commands, not: csb {' '.join(args)}")
    from dazzlecmd_lib.paths import which_with_pathext
    exe = which_with_pathext("csb")
    if not exe:
        raise CsbUnavailable("csb is not installed (Claude members need it)")
    try:
        r = subprocess.run([exe] + args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CsbUnavailable(f"csb did not answer within {timeout:g}s")
    if r.returncode != 0:
        raise CsbUnavailable((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip()
                             else f"csb exited {r.returncode}")
    return r.stdout


def _json(args: List[str]) -> Any:
    try:
        return json.loads(run_csb(args))
    except json.JSONDecodeError as e:
        raise CsbUnavailable(f"csb returned something that is not JSON ({e.msg})")


def open_session_ids() -> Optional[set]:
    """Session ids csb believes are open now (running or unverified), or None if csb is unavailable."""
    try:
        doc = _json(["set", "show", "current", "--json"])
    except CsbUnavailable:
        return None
    return {m.get("session_id") for m in doc.get("members", [])
            if m.get("live_status") in ("running", "unverified")}


def open_member_ids(set_doc: Dict[str, Any]) -> List[int]:
    """Claude members of a set that csb reports open -- for a bare claim to skip."""
    claude = [m for m in set_doc["members"] if m["kind"] == "claude"]
    if not claude:
        return []
    live = open_session_ids() or set()
    return [m["id"] for m in claude if m.get("session_id") in live]


def member_for(query: str) -> Dict[str, Any]:
    """A claude member for a session given by UUID or exact session name."""
    if _UUID.match(query):
        return {"kind": "claude", "via": "csb", "session_id": query.lower(), "name_at_add": None}
    rows = _json(["scan", query, "--json"])
    exact = [r for r in rows if r.get("session_name") == query]
    if not exact:
        raise CsbUnavailable(f"csb knows no session named exactly '{query}'")
    if len({r["session_id"] for r in exact}) > 1:
        raise CsbUnavailable(f"several sessions are named '{query}' -- give the UUID instead")
    return {"kind": "claude", "via": "csb", "session_id": exact[0]["session_id"], "name_at_add": query}


def members_from(view_or_set: str) -> List[Dict[str, Any]]:
    """One claude member per session in a csb view (current, last, boot) or named set."""
    doc = _json(["set", "show", view_or_set, "--json"])
    out = []
    for m in doc.get("members", []):
        if m.get("session_id"):
            out.append({"kind": "claude", "via": "csb", "session_id": m["session_id"],
                        "name_at_add": m.get("session_name"),
                        "label": None})
    return out
