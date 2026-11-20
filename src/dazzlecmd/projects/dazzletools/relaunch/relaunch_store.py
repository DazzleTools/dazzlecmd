"""Set files for ``dz relaunch``: where they live, what they hold, how they load.

A *set* is a named working set of *members*; each set is one portable JSON
file under ``<home>/sets/<name>.json`` (``sets/disabled/`` for disabled sets).
Box-local state -- claims, history, config, the path map -- lives under
``<home>/local/`` and never in a set file, so a set file can be copied to
another machine.

The store does no locking itself: callers that write take the store lock
(relaunch_claims / the CLI) around load -> modify -> save. Reads never lock and
never create files.

Design of record: final DWP 4.2, Addendum A5 (portable key), Addendum C.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

FORMAT = 1
SET_KIND = "dz-relaunch-set"
KINDS = ("folder", "command", "shell", "claude")
SHELL_DIALECTS = ("cmd", "bash", "pwsh")
TOMBSTONE_DAYS = 30
HOME_ENV = "DZ_RELAUNCH_HOME"

# Every action word, the view words, and words a later version is likely to
# need (final DWP 4.1). relaunch_verbs pins its verb table against this set.
RESERVED_NAMES = frozenset({
    # actions
    "list", "ls", "show", "new", "add", "edit", "note", "claim", "release",
    "drop", "enable", "shell-init",
    # views
    "last", "current", "boot",
    # reserved ahead of need
    "open", "tabs", "run", "start", "stop", "status", "rename", "copy", "move",
    "import", "export", "csb", "sync", "help", "set", "all", "rm", "disable",
    "launch", "detach",
})

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_LAST_N_RE = re.compile(r"^last~\d+$")


class StoreError(Exception):
    """A set file or name problem the person must fix; never auto-repaired."""


# --------------------------------------------------------------------------
# where things live
# --------------------------------------------------------------------------

def relaunch_home() -> str:
    """The store root: ``DZ_RELAUNCH_HOME`` or ``~/.dz/relaunch``."""
    env = os.environ.get(HOME_ENV)
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.expanduser("~"), ".dz", "relaunch")


def sets_dir(home: Optional[str] = None) -> str:
    return os.path.join(home or relaunch_home(), "sets")


def disabled_dir(home: Optional[str] = None) -> str:
    return os.path.join(sets_dir(home), "disabled")


def local_dir(home: Optional[str] = None) -> str:
    return os.path.join(home or relaunch_home(), "local")


def set_path(name: str, *, disabled: bool = False, home: Optional[str] = None) -> str:
    folder = disabled_dir(home) if disabled else sets_dir(home)
    return os.path.join(folder, name + ".json")


# --------------------------------------------------------------------------
# names
# --------------------------------------------------------------------------

def is_reserved(word: str) -> bool:
    w = word.lower()
    return w in RESERVED_NAMES or w.isdigit() or bool(_LAST_N_RE.match(w))


def canonical_name(display: str) -> str:
    """Validate a set name and return its stored (lowercase) form.

    Raises StoreError naming what is wrong. Matching is case-insensitive;
    the person's spelling is kept separately as ``display_name``.
    """
    if not display or not display.strip():
        raise StoreError("a set name cannot be empty")
    name = display.strip().lower()
    if is_reserved(name):
        raise StoreError(f"'{display}' is reserved (an action, a view, or a number) -- pick another name")
    if not _NAME_RE.match(name):
        raise StoreError(f"'{display}' is not a valid set name -- use letters, digits, '-' and '_', starting with a letter or digit")
    return name


def validate_label(label: str) -> str:
    lab = label.strip().lower()
    if not lab or not _NAME_RE.match(lab) or lab.isdigit() or is_reserved(lab):
        raise StoreError(f"'{label}' is not a valid member label -- letters, digits, '-' and '_', not all digits, not a reserved word")
    return lab


# --------------------------------------------------------------------------
# paths: literal storage plus a portable key
# --------------------------------------------------------------------------

def current_flavor() -> str:
    """``windows`` / ``wsl`` / ``posix`` for this runtime.

    Uses dazzle-filekit's helper when the installed filekit has it (slice SL),
    else the same decision locally.
    """
    try:
        from dazzle_filekit.portable import current_flavor as _cf  # type: ignore
        return _cf()
    except ImportError:
        pass
    # Same rule as filekit's compat.is_wsl (kept in step for older filekits).
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        if os.environ.get("WSL_DISTRO_NAME"):
            return "wsl"
        try:
            with open("/proc/version", encoding="utf-8", errors="replace") as f:
                v = f.read().lower()
            if "microsoft" in v or "wsl" in v:
                return "wsl"
        except OSError:
            pass
    return "posix"


def literal_path(path: str) -> str:
    """Normalize the *format* of a path without expanding ``~`` or variables."""
    from dazzle_filekit import normalize_cross_platform_path
    return str(normalize_cross_platform_path(path, expand=False))


def portable_key(path: str, flavor: Optional[str] = None) -> Optional[str]:
    """The runtime-neutral key for an absolute path, or None if it has none."""
    from dazzle_filekit.portable import encode_portable_path, PortablePathError
    try:
        return encode_portable_path(path, flavor=flavor or current_flavor())
    except PortablePathError:
        return None


def load_path_map(home: Optional[str] = None) -> Dict[str, str]:
    """``local/path-map.json``: key prefix -> key prefix. Missing -> {}."""
    p = os.path.join(local_dir(home), "path-map.json")
    if not os.path.isfile(p):
        return {}
    data = _read_json(p)
    mapping = data.get("map", {}) if isinstance(data, dict) else {}
    if not isinstance(mapping, dict):
        raise StoreError(f"{p}: 'map' must be an object of key-prefix pairs")
    return {str(k): str(v) for k, v in mapping.items()}


def resolve_cwd(member: Dict[str, Any], origin: Dict[str, Any],
                *, flavor: Optional[str] = None,
                path_map: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Where this member's folder is on *this* box, or None if it is not here.

    Same flavor as the set's origin: the literal ``cwd``. Otherwise the
    ``cwd_key`` is rewritten through the path map and decoded for this runtime.
    """
    cwd = member.get("cwd")
    if not cwd:
        return None
    here = flavor or current_flavor()
    if origin.get("flavor", here) == here:
        return cwd
    key = member.get("cwd_key")
    if not key:
        return None
    for src, dst in sorted((path_map or {}).items(), key=lambda kv: -len(kv[0])):
        if key == src or key.startswith(src.rstrip("/") + "/"):
            key = dst.rstrip("/") + key[len(src.rstrip("/")):]
            break
    else:
        return None
    from dazzle_filekit.portable import decode_portable_path
    return decode_portable_path(key, runtime=here)


# --------------------------------------------------------------------------
# set documents
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_set(display_name: str, *, notes: str = "", host: Optional[str] = None) -> Dict[str, Any]:
    name = canonical_name(display_name)
    now = _now()
    origin: Dict[str, Any] = {"flavor": current_flavor(), "os": sys.platform}
    if host:
        origin["host"] = host
    return {
        "format": FORMAT,
        "kind": SET_KIND,
        "name": name,
        "display_name": display_name.strip(),
        "created_at": now,
        "updated_at": now,
        "notes": notes,
        "properties": {},
        "origin": origin,
        "seeded_from": None,
        "csb_link": None,
        "next_member_id": 1,
        "members": [],
        "removed": [],
    }


def validate_member(m: Dict[str, Any], where: str = "member") -> None:
    if not isinstance(m, dict):
        raise StoreError(f"{where}: must be an object")
    mid = m.get("id")
    if not isinstance(mid, int) or mid < 1:
        raise StoreError(f"{where}: 'id' must be a positive integer")
    kind = m.get("kind")
    if kind not in KINDS:
        raise StoreError(f"{where} {mid}: unknown kind {kind!r} (expected one of {', '.join(KINDS)})")
    if kind == "folder" and not m.get("cwd"):
        raise StoreError(f"{where} {mid}: a folder member needs 'cwd'")
    if kind == "command":
        argv = m.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise StoreError(f"{where} {mid}: a command member needs 'argv', a non-empty list of strings")
    if kind == "shell":
        if m.get("shell") not in SHELL_DIALECTS:
            raise StoreError(f"{where} {mid}: a shell member needs 'shell' in {', '.join(SHELL_DIALECTS)}")
        if not isinstance(m.get("script"), str) or not m["script"].strip():
            raise StoreError(f"{where} {mid}: a shell member needs a non-empty 'script'")
    if m.get("detach") and kind not in ("command", "shell"):
        raise StoreError(f"{where} {mid}: only command and shell members can be detached")
    if kind == "claude":
        if m.get("via") != "csb" or not m.get("session_id"):
            raise StoreError(f"{where} {mid}: a claude member needs via='csb' and 'session_id'")


def validate_set(doc: Any, source: str = "set") -> Dict[str, Any]:
    if not isinstance(doc, dict):
        raise StoreError(f"{source}: not a JSON object")
    if doc.get("kind") != SET_KIND:
        raise StoreError(f"{source}: 'kind' is not {SET_KIND!r}")
    if doc.get("format") != FORMAT:
        raise StoreError(f"{source}: format {doc.get('format')!r} is not supported (expected {FORMAT})")
    name = doc.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise StoreError(f"{source}: invalid 'name' {name!r}")
    members = doc.get("members")
    if not isinstance(members, list):
        raise StoreError(f"{source}: 'members' must be a list")
    seen_ids, seen_labels = set(), set()
    for m in members:
        validate_member(m, f"{source}: member")
        if m["id"] in seen_ids:
            raise StoreError(f"{source}: member id {m['id']} appears twice")
        seen_ids.add(m["id"])
        lab = m.get("label")
        if lab:
            if lab in seen_labels:
                raise StoreError(f"{source}: label {lab!r} appears twice")
            seen_labels.add(lab)
    used = seen_ids | {t.get("member", {}).get("id") for t in doc.get("removed", []) if isinstance(t, dict)}
    nxt = doc.get("next_member_id")
    if not isinstance(nxt, int) or any(isinstance(i, int) and i >= nxt for i in used):
        raise StoreError(f"{source}: 'next_member_id' must be above every id ever used")
    return doc


def _read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise StoreError(f"{path}: not valid JSON ({e.msg} at line {e.lineno}) -- fix or remove the file; it was not changed")
    except OSError as e:
        raise StoreError(f"{path}: cannot read ({e.strerror})")


def find_set_file(name: str, home: Optional[str] = None) -> Optional[str]:
    """Path of the set file for ``name`` (enabled first), or None."""
    n = name.strip().lower()
    for disabled in (False, True):
        p = set_path(n, disabled=disabled, home=home)
        if os.path.isfile(p):
            return p
    return None


def load_set(name: str, home: Optional[str] = None) -> Dict[str, Any]:
    p = find_set_file(name, home)
    if not p:
        raise StoreError(f"no set named '{name}'")
    return load_set_file(p)


def load_set_file(path: str) -> Dict[str, Any]:
    doc = validate_set(_read_json(path), path)
    doc["_path"] = path
    doc["_disabled"] = os.path.basename(os.path.dirname(path)) == "disabled"
    return doc


def list_sets(*, include_disabled: bool = False, home: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every readable set, sorted by name. Unreadable files are reported, not hidden."""
    out: List[Dict[str, Any]] = []
    folders = [sets_dir(home)] + ([disabled_dir(home)] if include_disabled else [])
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(folder, fn)
            try:
                out.append(load_set_file(p))
            except StoreError as e:
                out.append({"_path": p, "_error": str(e), "name": fn[:-5]})
    return sorted(out, key=lambda d: d.get("name", ""))


def _prune_tombstones(doc: Dict[str, Any], now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    keep = []
    for t in doc.get("removed", []):
        try:
            when = datetime.strptime(t["removed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            keep.append(t)
            continue
        if now - when < timedelta(days=TOMBSTONE_DAYS):
            keep.append(t)
    doc["removed"] = keep


def save_set(doc: Dict[str, Any], home: Optional[str] = None) -> str:
    """Write a set file atomically (caller holds the store lock). Returns its path."""
    from dazzle_filekit import atomic_write_json
    out = {k: v for k, v in doc.items() if not k.startswith("_")}
    _prune_tombstones(out)
    out["updated_at"] = _now()
    validate_set(out, out.get("name", "set"))
    path = doc.get("_path") or set_path(out["name"], disabled=bool(doc.get("_disabled")), home=home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_json(path, out, indent=2, sort_keys=False, default=None)
    doc["_path"] = path
    doc["updated_at"] = out["updated_at"]
    doc["removed"] = out["removed"]
    return path


# --------------------------------------------------------------------------
# members
# --------------------------------------------------------------------------

def find_member(doc: Dict[str, Any], ref: str) -> Dict[str, Any]:
    """A member by id ("2") or label ("lib"). Raises StoreError if absent."""
    r = str(ref).strip().lower()
    for m in doc["members"]:
        if (r.isdigit() and m["id"] == int(r)) or m.get("label") == r:
            return m
    raise StoreError(f"set '{doc['name']}' has no member '{ref}'")


def add_member(doc: Dict[str, Any], member: Dict[str, Any], *, at: Optional[int] = None) -> Dict[str, Any]:
    """Give ``member`` the next id, validate it, append (or insert at position)."""
    m = copy.deepcopy(member)
    m["id"] = doc["next_member_id"]
    m.setdefault("disabled", False)
    m.setdefault("notes", "")
    m.setdefault("properties", {})
    if m.get("label"):
        m["label"] = validate_label(m["label"])
        if any(x.get("label") == m["label"] for x in doc["members"]):
            raise StoreError(f"set '{doc['name']}' already has a member labelled '{m['label']}'")
    if m.get("cwd"):
        m["cwd"] = literal_path(m["cwd"])
        key = portable_key(m["cwd"], doc.get("origin", {}).get("flavor"))
        if key:
            m["cwd_key"] = key
    validate_member(m)
    if at is None:
        doc["members"].append(m)
    else:
        doc["members"].insert(max(0, at - 1), m)
    doc["next_member_id"] = m["id"] + 1
    return m


def remove_member(doc: Dict[str, Any], ref: str) -> Dict[str, Any]:
    """Move a member to the ``removed`` tombstones; its id is never reused."""
    m = find_member(doc, ref)
    doc["members"] = [x for x in doc["members"] if x is not m]
    doc.setdefault("removed", []).append({"removed_at": _now(), "member": m})
    return m


def set_member_disabled(doc: Dict[str, Any], ref: str, disabled: bool) -> Dict[str, Any]:
    m = find_member(doc, ref)
    m["disabled"] = disabled
    return m
