"""Write actions for ``dz relaunch``: new, add, edit, note, release, drop, enable,
``list --removed``, and ``claim`` at the print level (``-o`` arrives in S8).

Every write is load -> change -> save under the store lock; the lock is never
held across a prompt or an editor. Seams that would act outside the store --
the safedel trash, the editor -- are module-level functions tests replace.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

import relaunch_claims as rc
import relaunch_cli_io as io
import relaunch_launch as rl
import relaunch_store as rs


# --------------------------------------------------------------------------
# seams (replaced in tests -- rule 1b)
# --------------------------------------------------------------------------

def trash_store():
    """The safedel trash store (dazzlecmd-lib)."""
    from dazzlecmd_lib.core.safedel import TrashStore
    return TrashStore()


def run_editor(path: str) -> None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or (
        "notepad" if sys.platform == "win32" else "vi")
    subprocess.run([editor, path])


def wait_for_enter(prompt: str) -> None:
    if io.is_console():
        sys.stderr.write(prompt)
        sys.stderr.flush()
        try:
            input()
        except EOFError:
            pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _parser(prog: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"dz relaunch {prog}", add_help=True)
    p.add_argument("--json", "-j", action="store_true")
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.add_argument("-q", "--quiet", action="count", default=0)
    return p


def _split_dashdash(rest: List[str]):
    if "--" in rest:
        i = rest.index("--")
        return rest[:i], rest[i + 1:]
    return rest, None


def _one_set(parsed) -> str:
    if len(parsed.targets) != 1 or parsed.targets[0].view:
        raise rs.StoreError(f"'{parsed.verb}' needs exactly one set name")
    return parsed.targets[0].name


# --------------------------------------------------------------------------
# new / add / note / edit
# --------------------------------------------------------------------------

def cmd_new(parsed, json_mode: bool) -> int:
    p = _parser("new")
    p.add_argument("name")
    p.add_argument("--notes", default="")
    p.add_argument("--here", action="store_true")
    p.add_argument("--from-csb", metavar="VIEW_OR_SET")
    a = p.parse_args(parsed.rest)
    name = rs.canonical_name(a.name)
    if rs.find_set_file(name):
        raise rs.StoreError(f"a set named '{name}' already exists")
    members = []
    if a.from_csb:
        import relaunch_csb as csb
        members = csb.members_from(a.from_csb)
    with rc.store_lock():
        doc = rs.new_set(a.name, notes=a.notes)
        for m in members:
            rs.add_member(doc, m)
        if a.here:
            rs.add_member(doc, {"kind": "folder", "cwd": os.getcwd()})
        if a.from_csb:
            doc["seeded_from"] = {"csb": a.from_csb, "at": rs._now()}
        rs.save_set(doc)
    print(f"created {name} with {len(doc['members'])} members")
    return io.finish("CREATED", f"{name} {len(doc['members'])} members", json_mode=json_mode,
                     payload={"set": name, "members": len(doc["members"])})


def cmd_add(parsed, json_mode: bool) -> int:
    rest, argv = _split_dashdash(parsed.rest)
    p = _parser("<set> add")
    p.add_argument("folder", nargs="?")
    p.add_argument("--here", action="store_true")
    p.add_argument("--label")
    p.add_argument("--notes", default="")
    p.add_argument("--at", type=int)
    p.add_argument("--shell", nargs=2, metavar=("DIALECT", "SCRIPT"))
    p.add_argument("--claude", metavar="SESSION")
    a = p.parse_args(rest)
    set_name = _one_set(parsed)
    cwd = os.getcwd() if a.here else (os.path.abspath(a.folder) if a.folder else None)
    if a.claude:
        import relaunch_csb as csb
        member = csb.member_for(a.claude)
        if cwd:
            member["cwd"] = cwd
    elif a.shell:
        member = {"kind": "shell", "shell": a.shell[0], "script": a.shell[1]}
        if cwd:
            member["cwd"] = cwd
    elif argv:
        member = {"kind": "command", "argv": argv}
        if cwd:
            member["cwd"] = cwd
    elif cwd:
        member = {"kind": "folder", "cwd": cwd}
    else:
        raise rs.StoreError("add what? give a folder, --here, --shell DIALECT SCRIPT, --claude SESSION, or -- <command>")
    if a.label:
        member["label"] = a.label
    member["notes"] = a.notes
    with rc.store_lock():
        doc = rs.load_set(set_name)
        m = rs.add_member(doc, member, at=a.at)
        rs.save_set(doc)
    print(f"added {set_name}:{m['id']} ({m['kind']}) -> {m.get('cwd') or ' '.join(m.get('argv', [])) or m.get('script') or m.get('session_id')}")
    if a.here:
        try:
            rc.claim(set_name, rc.current_tab(), str(m["id"]))
            print(f"claimed {set_name}:{m['id']} for this tab")
        except rc.ClaimError as e:
            print(f"(not claimed: {e})", file=sys.stderr)
    return io.finish("ADDED", f"{set_name} {m['id']} {m['kind']}", json_mode=json_mode,
                     payload={"set": set_name, "member": m})


def cmd_note(parsed, json_mode: bool) -> int:
    set_name = _one_set(parsed)
    rest = parsed.rest
    if not rest:
        raise rs.StoreError("note needs text: dz relaunch <set> note [<member>] \"text\"")
    with rc.store_lock():
        doc = rs.load_set(set_name)
        if len(rest) >= 2:
            target = rs.find_member(doc, rest[0])
            target["notes"] = " ".join(rest[1:])
            where = f"{set_name}:{target['id']}"
        else:
            doc["notes"] = rest[0]
            where = set_name
        rs.save_set(doc)
    return io.finish("NOTED", where, json_mode=json_mode)


def _hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def cmd_edit(parsed, json_mode: bool) -> int:
    rest, argv = _split_dashdash(parsed.rest)
    p = _parser("<set> edit")
    p.add_argument("member", nargs="?")
    p.add_argument("--label")
    p.add_argument("--notes")
    p.add_argument("--folder")
    a = p.parse_args(rest)
    set_name = _one_set(parsed)
    if a.member or a.label or a.notes is not None or a.folder or argv:
        with rc.store_lock():
            doc = rs.load_set(set_name)
            m = rs.find_member(doc, a.member) if a.member else None
            if m is None:
                raise rs.StoreError("field edits need a member: dz relaunch <set> edit <member> --label ...")
            if a.label:
                m["label"] = rs.validate_label(a.label)
            if a.notes is not None:
                m["notes"] = a.notes
            if a.folder:
                m["cwd"] = rs.literal_path(os.path.abspath(a.folder))
                m["cwd_key"] = rs.portable_key(m["cwd"], doc.get("origin", {}).get("flavor"))
            if argv:
                if m["kind"] != "command":
                    raise rs.StoreError(f"{set_name}:{m['id']} is a {m['kind']} member; only command members take -- argv")
                m["argv"] = argv
            rs.validate_member(m)
            rs.save_set(doc)
        return io.finish("EDITED", f"{set_name} {m['id']}", json_mode=json_mode)
    # editor mode: no lock while the editor is open; hash check on save
    src = rs.find_set_file(set_name)
    if not src:
        raise rs.StoreError(f"no set named '{set_name}'")
    work = os.path.join(rs.local_dir(), f"{set_name}.edit.json")
    os.makedirs(rs.local_dir(), exist_ok=True)
    shutil.copyfile(src, work)
    start_hash = _hash(src)
    run_editor(work)
    wait_for_enter(f"edit {work}, save it, then press Enter here to apply ")
    try:
        new_doc = rs.load_set_file(work)
    except rs.StoreError as e:
        print(f"relaunch: the edited file is not valid -- kept at {work}: {e}", file=sys.stderr)
        return io.finish("REFUSED", f"invalid edit kept at {work}", io.EXIT_REFUSED, json_mode=json_mode)
    old_doc = rs.load_set_file(src)
    if new_doc["name"] != old_doc["name"]:
        return io.finish("REFUSED", f"the set's name cannot change in the editor; kept at {work}",
                         io.EXIT_REFUSED, json_mode=json_mode)
    with rc.store_lock():
        if _hash(src) != start_hash:
            return io.finish("REFUSED", f"{set_name} changed while you edited -- your copy is kept at {work}",
                             io.EXIT_REFUSED, json_mode=json_mode)
        new_doc["_path"] = src
        rs.save_set(new_doc)
    os.remove(work)
    return io.finish("EDITED", set_name, json_mode=json_mode)


# --------------------------------------------------------------------------
# drop / enable / removed
# --------------------------------------------------------------------------

def cmd_drop(parsed, json_mode: bool) -> int:
    set_name = _one_set(parsed)
    rest = list(parsed.rest)
    yes = "--yes" in rest or "-y" in rest
    rest = [r for r in rest if r not in ("--yes", "-y")]
    if not rest or rest[0] not in ("rm", "disable"):
        raise rs.StoreError("drop needs a mode: dz relaunch <set> drop rm|disable [<member>...]")
    mode, refs = rest[0], rest[1:]
    if refs:
        with rc.store_lock():
            doc = rs.load_set(set_name)
            done = []
            for r in refs:
                if mode == "rm":
                    done.append(rs.remove_member(doc, r)["id"])
                else:
                    done.append(rs.set_member_disabled(doc, r, True)["id"])
            rs.save_set(doc)
        verb = "REMOVED" if mode == "rm" else "DISABLED"
        return io.finish(verb, f"{set_name} {' '.join(map(str, done))}", json_mode=json_mode)
    path = rs.find_set_file(set_name)
    if not path:
        raise rs.StoreError(f"no set named '{set_name}'")
    if mode == "disable":
        with rc.store_lock():
            target = rs.set_path(set_name, disabled=True)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.replace(path, target)
        return io.finish("DISABLED", set_name, json_mode=json_mode)
    if not yes:
        ok = io.confirm(f"remove the whole set '{set_name}' (to the safedel trash)?")
        if ok is None:
            return io.finish("REFUSED", "removing a whole set needs --yes when nobody is at the console",
                             io.EXIT_REFUSED, json_mode=json_mode)
        if not ok:
            return io.finish("REFUSED", "not removed", io.EXIT_REFUSED, json_mode=json_mode)
    with rc.store_lock():
        result = trash_store().trash([path])
    if not getattr(result, "success", False):
        return io.finish("ERROR", f"safedel refused: {'; '.join(getattr(result, 'errors', []))}",
                         io.EXIT_ERROR, json_mode=json_mode)
    print(f"removed {set_name} -- recover with: dz safedel recover {os.path.basename(result.folder_path)}")
    return io.finish("REMOVED", set_name, json_mode=json_mode)


def cmd_enable(parsed, json_mode: bool) -> int:
    set_name = _one_set(parsed)
    refs = parsed.rest
    with rc.store_lock():
        if not refs:
            src = rs.set_path(set_name, disabled=True)
            if not os.path.isfile(src):
                raise rs.StoreError(f"'{set_name}' is not a disabled set")
            os.replace(src, rs.set_path(set_name))
            return io.finish("ENABLED", set_name, json_mode=json_mode)
        doc = rs.load_set(set_name)
        for r in refs:
            rs.set_member_disabled(doc, r, False)
        rs.save_set(doc)
    return io.finish("ENABLED", f"{set_name} {' '.join(refs)}", json_mode=json_mode)


def removed_rows() -> List[Dict[str, Any]]:
    """Removed sets (safedel trash, by original path) and member tombstones."""
    rows = []
    sets_root = os.path.normcase(os.path.abspath(rs.sets_dir()))
    try:
        for folder in trash_store().list_entries():
            for e in folder.entries:
                if os.path.normcase(e.original_path).startswith(sets_root):
                    rows.append({"what": "set", "name": os.path.basename(e.original_path)[:-5],
                                 "removed": str(folder.deleted_at), "recover": folder.folder_name})
    except Exception as e:  # the trash is optional for this view
        rows.append({"what": "note", "name": f"safedel trash not readable: {e}"})
    for d in rs.list_sets(include_disabled=True):
        for t in d.get("removed", []) or []:
            rows.append({"what": "member", "name": f"{d['name']}:{t['member']['id']}",
                         "label": t["member"].get("label"), "removed": t.get("removed_at")})
    return rows


# --------------------------------------------------------------------------
# release / claim (print)
# --------------------------------------------------------------------------

def cmd_release(parsed, json_mode: bool) -> int:
    rest = parsed.rest
    all_ = "--all" in rest
    refs = [r for r in rest if not r.startswith("-")]
    set_name = parsed.targets[0].name if parsed.targets else None
    dropped = rc.release(rc.current_tab(), set_name, refs[0] if refs else None, all_in_set=all_)
    for c in dropped:
        print(f"released {c['set']}:{c['member_id']}")
    if not dropped:
        return io.finish("NOTHING", "no claim to release", json_mode=json_mode)
    return io.finish("RELEASED", str(len(dropped)), json_mode=json_mode)


def action_lines(m: Dict[str, Any], folder: Optional[str]) -> List[str]:
    """What the person does next for a member (print level)."""
    k = m["kind"]
    lines = []
    if folder:
        wrote = rl.write_cd_file(folder)
        if wrote:
            lines.append(f"this tab moves to {folder}")
        else:
            lines.append(rl.cd_line(folder))
            if wrote is None:
                lines.append("(dzr can do that for you: dz relaunch shell-init)")
    if k == "command":
        lines.append(" ".join(_quote(a) for a in m["argv"]))
    elif k == "shell":
        lines.append(m["script"])
    elif k == "claude":
        lines.append(f"csb resume {m['session_id']}")
    return lines


def _quote(a: str) -> str:
    return f'"{a}"' if (" " in a or not a) else a


def cmd_claim(parsed, json_mode: bool) -> int:
    rest = list(parsed.rest) + [f for f in parsed.flags if f in ("-o", "--open", "-y", "--yes")]
    take_next = "--next" in rest
    yes = "--yes" in rest or "-y" in rest
    open_flag = "-o" in rest or "--open" in rest
    tabs_flag = "--tabs" in rest
    print_only = "--print" in rest
    refs = [r for r in rest if not r.startswith("-")]
    import relaunch_continuum as cont
    try:
        level = cont.resolve_action(open_flag=open_flag and not print_only, tabs_flag=tabs_flag,
                                    console=io.is_console())
    except cont.LevelNotBuilt as e:
        return io.finish("USAGE", str(e), io.EXIT_USAGE, json_mode=json_mode)
    targets = parsed.targets or []
    if not targets:
        raise rs.StoreError("claim needs a set: dz relaunch <set> claim")
    tab = rc.current_tab()
    last_err = None
    for t in targets:
        set_name, ref = t.name, (t.entry or (refs[0] if refs else None))
        if t.view:
            import relaunch_views as views
            _, hist = rc.snapshot()
            members, _ = views.session_view(hist, t.name)
            if not ref:
                raise rs.StoreError(f"claim from {t.name} needs an index: dz relaunch {t.name}:<n> claim")
            idx = int(ref)
            if not 1 <= idx <= len(members):
                raise rs.StoreError(f"{t.name} has {len(members)} members -- valid indices are 1-{len(members)}")
            set_name, m0 = members[idx - 1]
            ref = str(m0["id"])
        skip = []
        if ref is None:
            try:
                import relaunch_csb as csb
                skip = csb.open_member_ids(rs.load_set(set_name))
            except Exception:
                skip = []
        try:
            r = rc.claim(set_name, tab, ref, allow_duplicate=yes, take_next=take_next,
                         level=level, skip_ids=skip)
        except rc.ClaimError as e:
            if e.code == "held-elsewhere" and not yes:
                ok = io.confirm(f"{e} -- start a second copy?")
                if ok:
                    r = rc.claim(set_name, tab, ref, allow_duplicate=True, take_next=take_next, level=level)
                else:
                    return io.finish("REFUSED", str(e), io.EXIT_REFUSED, json_mode=json_mode)
            elif e.code == "none-free" and len(targets) > 1:
                last_err = e
                continue
            else:
                print(f"relaunch: {e}", file=sys.stderr)
                return io.finish("REFUSED", str(e), io.EXIT_REFUSED, json_mode=json_mode)
        return _report_claim(r, level, json_mode)
    return io.finish("REFUSED", str(last_err), io.EXIT_REFUSED, json_mode=json_mode)


def _report_claim(r: rc.ClaimResult, level: str, json_mode: bool) -> int:
    m = r.member
    doc = rs.load_set(r.set_name)
    folder = rs.resolve_cwd(m, doc.get("origin", {}), path_map=rs.load_path_map()) if m.get("cwd") else None
    if m.get("cwd") and folder is None:
        print(f"note: {m['cwd']} is not on this box (no path map entry)", file=sys.stderr)
    label = m.get("label") or m["kind"]
    again = " (this tab already had it)" if r.already else ""
    inst = f" (copy {r.instance})" if r.instance > 1 else ""
    if r.new_session:
        why = "after a restart" if r.new_session == "restart" else "after every tab closed"
        print(f"session {r.session} started {why}")
    print(f"claimed {r.set_name}:{m['id']} {label}{inst}{again}  [{r.member_tag}]")
    if level == "open":
        import relaunch_launch as launch
        if hasattr(launch, "open_member"):
            return launch.open_member(r, doc, folder, json_mode=json_mode)
        print("note: claim -o is not built in this version -- showing what to do instead",
              file=sys.stderr)
    for line in action_lines(m, folder):
        print(f"  {line}")
    if r.next_member:
        nm = r.next_member
        print(f"next: {r.set_name}:{nm['id']} {nm.get('label') or nm['kind']}  [{r.next_tag}]")
    else:
        print("next: nothing left to claim in this set")
    return io.finish("CLAIMED", f"{r.set_name} {m['id']} {label}", json_mode=json_mode,
                     payload={"set": r.set_name, "member": m["id"], "instance": r.instance,
                              "already": r.already, "session": r.session,
                              "next": r.next_member["id"] if r.next_member else None})
