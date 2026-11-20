"""Trust for runnable members (Addendum A7): the ``hashed`` level.

When relaunch writes a command or shell member it records a hash of what that
member runs in ``local/trust.json``. At ``claim -o`` a member whose hash does
not match (edited outside relaunch, or a set from another box) is shown and
asked about even with ``-y``. ``signed`` (GPG) is a later level.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional

import relaunch_store as rs

RUNNABLE = ("command", "shell")


def _path(home: Optional[str] = None) -> str:
    return os.path.join(rs.local_dir(home), "trust.json")


def member_hash(m: Dict[str, Any]) -> str:
    fields = {"kind": m["kind"], "argv": m.get("argv"), "shell": m.get("shell"),
              "script": m.get("script"), "cwd": m.get("cwd")}
    return "sha256:" + hashlib.sha256(json.dumps(fields, sort_keys=True).encode("utf-8")).hexdigest()


def _load(home=None) -> Dict[str, Any]:
    p = _path(home)
    if not os.path.isfile(p):
        return {"format": 1, "approved": {}}
    data = rs._read_json(p)
    data.setdefault("approved", {})
    return data


def record(set_name: str, m: Dict[str, Any], home=None) -> None:
    if m["kind"] not in RUNNABLE:
        return
    from dazzle_filekit import atomic_write_json
    data = _load(home)
    data["approved"].setdefault(set_name, {})[str(m["id"])] = member_hash(m)
    os.makedirs(rs.local_dir(home), exist_ok=True)
    atomic_write_json(_path(home), data, indent=2, default=None)


def is_trusted(doc: Dict[str, Any], m: Dict[str, Any], home=None) -> bool:
    if m["kind"] not in RUNNABLE:
        return True
    return _load(home)["approved"].get(doc["name"], {}).get(str(m["id"])) == member_hash(m)
