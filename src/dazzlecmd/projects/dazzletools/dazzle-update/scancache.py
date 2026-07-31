"""Scan-result cache.

A full sweep fetches ~140 remotes and makes a dozen gh calls; it costs
about a minute. Re-running it just to answer "show me only the dirty
ones" is waste, so the joined result is cached and can be replayed.

The cache stores what was OBSERVED, never a verdict. Age is always
reported alongside replayed output: a stale answer presented as current
is exactly the failure this whole tool exists to prevent, and it would
be perverse to reintroduce it in the cache layer.
"""

import json
import os
import time

SCHEMA = 1


def default_path():
    base = (os.environ.get("LOCALAPPDATA")
            or os.environ.get("XDG_CACHE_HOME")
            or os.path.expanduser("~/.cache"))
    return os.path.join(base, "dazzlecmd", "dazzle-update-scan.json")


def save(records, meta, path=None, now=None):
    """Persist a scan. Best effort -- a cache failure is never fatal."""
    path = path or default_path()
    payload = {
        "schema": SCHEMA,
        "saved_at": now if now is not None else time.time(),
        "meta": meta,
        "records": {k: v for k, v in records.items()},
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True, default=str)
        os.replace(tmp, path)
        return True, None
    except OSError as exc:
        return False, str(exc)


def load(path=None, max_age=None, now=None):
    """Return (records, meta, age_seconds, error).

    `max_age` in seconds; None accepts any age. A cache older than
    max_age is refused rather than silently used.
    """
    path = path or default_path()
    if not os.path.isfile(path):
        return None, None, None, "no cached scan found"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return None, None, None, f"unreadable cache: {exc}"

    if payload.get("schema") != SCHEMA:
        return None, None, None, "cache written by a different version"

    saved = payload.get("saved_at") or 0
    age = (now if now is not None else time.time()) - saved
    if max_age is not None and age > max_age:
        return None, None, age, (
            f"cached scan is {format_age(age)} old (limit {format_age(max_age)})")
    return payload.get("records") or {}, payload.get("meta") or {}, age, None


def namespace_cache_path(path=None):
    """Where cached GitHub namespace listings live."""
    base = path or default_path()
    return base.replace("-scan.json", "-namespaces.json")


def load_namespaces(path=None, ttl=None, now=None):
    """Return (payload, age, error) for cached org listings.

    Org membership changes on the order of days, but listing eleven
    namespaces costs ~4.7s of sequential `gh repo list` calls on every
    single run -- the bulk of the wait before scanning even begins. This
    is the one axis where reuse is honest: it never affects fetch, which
    must stay live.
    """
    p = namespace_cache_path(path)
    if not os.path.isfile(p):
        return None, None, "no cached namespace listing"
    try:
        with open(p, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return None, None, f"unreadable namespace cache: {exc}"
    if payload.get("schema") != SCHEMA:
        return None, None, "namespace cache written by a different version"
    age = (now if now is not None else time.time()) - (payload.get("saved_at") or 0)
    if ttl is not None and age > ttl:
        return None, age, f"namespace cache is {format_age(age)} old (ttl {format_age(ttl)})"
    return payload.get("namespaces") or {}, age, None


def save_namespaces(namespaces, path=None, now=None):
    """Persist org listings. Best effort; failure is never fatal."""
    p = namespace_cache_path(path)
    payload = {"schema": SCHEMA,
               "saved_at": now if now is not None else time.time(),
               "namespaces": namespaces}
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True, default=str)
        os.replace(tmp, p)
        return True, None
    except OSError as exc:
        return False, str(exc)


def format_age(seconds):
    """Human age: '3m', '2h 10m', '4d'."""
    if seconds is None:
        return "unknown"
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"
