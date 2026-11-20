"""Read actions for ``dz relaunch``: the dashboard, a set's roster, a member's card,
and the ``last`` session view. None of these takes the lock or writes a file.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

import relaunch_claims as rc
import relaunch_cli_io as io
import relaunch_store as rs


def _tab() -> Optional[rc.Tab]:
    try:
        return rc.current_tab()
    except Exception:
        return None


def _state(claims, set_name, member, tab) -> str:
    mine = [c for c in claims if c["set"] == set_name and c["member_id"] == member["id"]]
    if member.get("disabled"):
        return "disabled"
    if member.get("detach"):
        return "detached (launch)"
    if not mine:
        return "free"
    if tab and any(tab.matches(c.get("anchor", {})) for c in mine):
        return "this tab"
    c = mine[0]
    extra = f" x{len(mine)}" if len(mine) > 1 else ""
    return f"claimed (pid {c['anchor'].get('pid')}){extra}"


def _describe(m: Dict[str, Any]) -> str:
    k = m["kind"]
    if k == "folder":
        return m.get("cwd", "")
    if k == "command":
        return " ".join(m["argv"]) + (f"   in {m['cwd']}" if m.get("cwd") else "")
    if k == "shell":
        return f"[{m['shell']}] {m['script']}" + (f"   in {m['cwd']}" if m.get("cwd") else "")
    return f"csb session {m.get('name_at_add') or m['session_id']}"


def _session_live(claims) -> bool:
    return bool(claims)


def roster(doc, claims, history, tab) -> Tuple[List[str], Dict[str, Any]]:
    live = _session_live(claims)
    boot = rc.default_boot()
    held = [c["member_id"] for c in claims if c["set"] == doc["name"]]
    nxt = rc.order_free(doc, held, history)
    rows, data = [], []
    head = f"{doc['display_name']}  ({len(doc['members'])} members, {len(set(held))} claimed)"
    if doc.get("notes"):
        head += f"  -- {doc['notes']}"
    rows.append(head)
    for m in doc["members"]:
        st = _state(claims, doc["name"], m, tab)
        tg = rc.tag(history, doc["name"], m["id"], live, boot)
        mark = "->" if nxt and m["id"] == nxt[0]["id"] else "  "
        rows.append(f" {mark}{m['id']:>3}  {m['kind']:<7} {(m.get('label') or ''):<12} {st:<22} [{tg}]")
        rows.append(f"            {_describe(m)}")
        if m.get("notes"):
            rows.append(f"            note: {m['notes']}")
        data.append({"id": m["id"], "label": m.get("label"), "kind": m["kind"], "state": st,
                     "tag": tg, "describe": _describe(m), "notes": m.get("notes", "")})
    if nxt:
        rows.append(f"next: dz relaunch {doc['name']} claim   (takes {nxt[0]['id']} "
                    f"{nxt[0].get('label') or nxt[0]['kind']} "
                    f"[{rc.tag(history, doc['name'], nxt[0]['id'], live, boot)}])")
    else:
        rows.append("next: nothing free -- every enabled member is claimed")
    return rows, {"set": doc["name"], "members": data,
                  "next": nxt[0]["id"] if nxt else None}


def member_card(doc, m, claims, history, tab) -> Tuple[List[str], Dict[str, Any]]:
    st = _state(claims, doc["name"], m, tab)
    tg = rc.tag(history, doc["name"], m["id"], _session_live(claims), rc.default_boot())
    rows = [f"{doc['name']}:{m['id']}  {m.get('label') or ''}",
            f"  kind:   {m['kind']}",
            f"  what:   {_describe(m)}",
            f"  state:  {st}",
            f"  last:   {tg}"]
    if m.get("notes"):
        rows.append(f"  note:   {m['notes']}")
    if m.get("properties"):
        rows.append(f"  props:  {m['properties']}")
    data = {k: v for k, v in m.items()}
    data.update({"state": st, "tag": tg, "set": doc["name"]})
    return rows, data


def session_view(history, token: str, home=None) -> Tuple[List[Tuple[str, Dict[str, Any]]], Optional[int]]:
    """Members opened in session ``last`` / ``last~N`` (N sessions before), in set order."""
    claims_now = rc.snapshot(home)[0]
    live = _session_live(claims_now)
    sessions = [s["n"] for s in history.get("sessions", [])]
    if not sessions:
        return [], None
    back = int(token.split("~")[1]) if "~" in token else 0
    ref_index = (1 if live else 0) + back
    if token.startswith("current"):
        ref_index = 0
    if ref_index >= len(sessions):
        return [], None
    n = sessions[ref_index]
    out = []
    for set_name, members in sorted(history.get("opened", {}).items()):
        try:
            doc = rs.load_set(set_name, home)
        except rs.StoreError:
            continue
        for m in doc["members"]:
            if n in members.get(str(m["id"]), []):
                out.append((set_name, m))
    return out, n


def cmd_list(parsed, json_mode: bool) -> int:
    rest = parsed.rest
    if "--removed" in rest:
        import relaunch_actions as actions
        removed = actions.removed_rows()
        if "all" not in rest:
            if json_mode:
                return io.finish("LISTED", f"{len(removed)} removed", io.EXIT_OK, json_mode=True,
                                 payload={"removed": removed})
            for r in removed:
                extra = f"  recover: dz safedel recover {r['recover']}" if r.get("recover") else ""
                print(f"  {r['what']:<7} {r['name']:<24} removed {r.get('removed', '')}{extra}")
            if not removed:
                print("nothing removed")
            return io.finish("LISTED", f"{len(removed)} removed")
    include_disabled = "--disabled" in rest or ("--removed" in rest and "all" in rest)
    sets = rs.list_sets(include_disabled=include_disabled)
    claims, history = rc.snapshot()
    tab = _tab()
    live = _session_live(claims)
    rows, data = [], []
    if not sets:
        msg = ("no sets yet -- start with: dz relaunch new <name>, then in each tab: "
               "dz relaunch <name> add --here")
        if json_mode:
            return io.finish("LISTED", "0 sets", io.EXIT_OK, json_mode=True, payload={"sets": []})
        print(msg)
        return io.finish("LISTED", "0 sets")
    for d in sets:
        if "_error" in d:
            rows.append(f"  {d['name']:<20} UNREADABLE: {d['_error']}")
            data.append({"set": d["name"], "error": d["_error"]})
            continue
        held = {c["member_id"] for c in claims if c["set"] == d["name"]}
        mine = [c for c in claims if c["set"] == d["name"] and tab and tab.matches(c.get("anchor", {}))]
        last_n = sum(1 for m in d["members"]
                     if rc.tag(history, d["name"], m["id"], live).startswith("open last session"))
        flag = " (disabled)" if d.get("_disabled") else ""
        here = f"  <- this tab: {mine[0]['member_id']}" if mine else ""
        rows.append(f"  {d['name']:<20}{flag} {len(d['members'])} members, {len(held)} claimed, "
                    f"{last_n} open last session{here}")
        data.append({"set": d["name"], "members": len(d["members"]), "claimed": len(held),
                     "open_last_session": last_n, "disabled": bool(d.get("_disabled")),
                     "this_tab": mine[0]["member_id"] if mine else None})
    if json_mode:
        return io.finish("LISTED", f"{len(sets)} sets", io.EXIT_OK, json_mode=True, payload={"sets": data})
    print("\n".join(rows))
    return io.finish("LISTED", f"{len(sets)} sets")


def cmd_show(parsed, json_mode: bool) -> int:
    claims, history = rc.snapshot()
    tab = _tab()
    out_rows, out_data = [], []
    for t in parsed.targets or []:
        if t.view:
            members, n = session_view(history, t.name)
            if t.entry is not None:
                idx = int(t.entry)
                if not (1 <= idx <= len(members)):
                    raise rs.StoreError(f"{t.name} has {len(members)} members -- valid indices are 1-{len(members)}")
                set_name, m = members[idx - 1]
                rows, data = member_card(rs.load_set(set_name), m, claims, history, tab)
                out_rows += rows
                out_data.append(data)
                continue
            if n is None:
                out_rows.append(f"{t.name}: no such session yet")
                continue
            out_rows.append(f"session {n} ({t.name}): {len(members)} members")
            for i, (set_name, m) in enumerate(members, 1):
                out_rows.append(f"  {i:>3}  {set_name}:{m['id']:<4} {m['kind']:<7} {m.get('label') or ''}")
                out_data.append({"index": i, "set": set_name, "id": m["id"], "kind": m["kind"],
                                 "label": m.get("label")})
            continue
        doc = rs.load_set(t.name)
        if t.entry is not None:
            rows, data = member_card(doc, rs.find_member(doc, t.entry), claims, history, tab)
        else:
            rows, data = roster(doc, claims, history, tab)
        out_rows += rows + [""]
        out_data.append(data)
    if json_mode:
        return io.finish("SHOWN", f"{len(out_data)} items", io.EXIT_OK, json_mode=True,
                         payload={"items": out_data})
    print("\n".join(out_rows).rstrip())
    return io.finish("SHOWN", ", ".join(t.name + (f":{t.entry}" if t.entry else "") for t in parsed.targets))
