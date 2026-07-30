"""Canonical repo identity -- resolve a remote URL to what it really is.

A remote URL is a mutable POINTER, not an identity. GitHub keeps serving
the old path after a repo is transferred or renamed, so a clone can fetch
successfully for years while its configured URL names a namespace the
repo no longer lives in.

That is not hypothetical. On this box, three repos were found pointing at
a pre-transfer personal namespace and silently following redirects:

    djdarcy/dazzlesum      -> DazzleTools/dazzlesum      (id 1009633247)
    djdarcy/dazzle-tree-lib -> DazzleLib/dazzle-tree-lib
    djdarcy/process-delta  -> DazzleTools/process-delta

Matching org listings against configured URLs therefore reports cloned
repos as missing -- it did, for exactly those three, turning a true count
of 7 uncloned repos into a false 10. Identity must come from the resolved
full_name (or numeric id), never from the URL string.

Resolution needs the `gh` CLI. When it is absent or unauthenticated this
module says so explicitly rather than guessing: a silent fallback to
URL-matching would reintroduce the very bug it exists to prevent.
"""

import json
import os
import re
import subprocess

# github.com/OWNER/REPO in https, ssh, and scp-like forms, with or
# without a trailing .git
_SLUG_RE = re.compile(r'github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$')


class GhUnavailable(Exception):
    """Raised when gh cannot answer -- never swallowed into a guess."""


def parse_slug(url):
    """Extract OWNER/REPO from a GitHub remote URL, or None."""
    if not url:
        return None
    m = _SLUG_RE.search(url.strip())
    return m.group(1) if m else None


def _run_gh(args, timeout=30):
    """Run gh and return (rc, stdout, stderr). Never raises on failure."""
    try:
        res = subprocess.run(
            ["gh"] + list(args),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        return 127, "", "gh not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"gh timed out after {timeout}s"


def gh_status(runner=_run_gh):
    """Return (available, detail) describing gh's usability.

    Callers surface `detail` verbatim. An unauthenticated gh can still
    see public repos but silently omits private ones, which is a
    dangerous false negative for an inventory -- so it is reported as a
    distinct state rather than folded into "available".
    """
    rc, _out, err = runner(["auth", "status"])
    if rc == 127:
        return (False, "gh CLI not found on PATH")
    if rc == 124:
        return (False, "gh timed out")
    if rc != 0:
        return (False, "gh present but not authenticated: private repos "
                       "would be invisible (" + (err.strip().splitlines() or [""])[0] + ")")
    return (True, "gh authenticated")


class IdentityResolver:
    """Resolves slugs to canonical identity, memoizing within a run.

    One network call per distinct slug. The cache is keyed on the slug as
    written, so two clones pointing at the same stale URL cost one call.
    """

    def __init__(self, runner=_run_gh, cache=None):
        self._runner = runner
        self._cache = dict(cache) if cache else {}

    @property
    def cache(self):
        return dict(self._cache)

    def resolve(self, slug):
        """Return a dict describing what `slug` actually is.

        Keys:
            slug        -- what was asked for
            full_name   -- canonical OWNER/REPO, or None if unresolved
            repo_id     -- numeric GitHub id, or None
            redirected  -- True when full_name differs from slug
            error       -- None, or a human-readable reason
        """
        if slug in self._cache:
            return dict(self._cache[slug])

        result = {
            "slug": slug, "full_name": None, "repo_id": None,
            "redirected": False, "error": None,
        }
        if not slug:
            result["error"] = "empty slug"
            self._cache[slug] = result
            return dict(result)

        rc, out, err = self._runner(
            ["api", f"repos/{slug}", "--jq", "{full_name: .full_name, id: .id}"])
        if rc == 127:
            result["error"] = "gh CLI not found on PATH"
        elif rc == 124:
            result["error"] = "gh timed out"
        elif rc != 0:
            first = (err.strip().splitlines() or ["unknown gh error"])[0]
            result["error"] = first
        else:
            try:
                payload = json.loads(out.strip() or "{}")
            except json.JSONDecodeError:
                payload = {}
            full = payload.get("full_name")
            if full:
                result["full_name"] = full
                result["repo_id"] = payload.get("id")
                result["redirected"] = (full.lower() != slug.lower())
            else:
                result["error"] = "gh returned no full_name"

        self._cache[slug] = result
        return dict(result)

    def canonical_key(self, slug):
        """Best available identity key for grouping.

        Falls back to the lowercased slug when resolution failed, so an
        offline run still groups consistently -- it just cannot detect
        redirects, which callers must report rather than hide.
        """
        info = self.resolve(slug)
        if info["full_name"]:
            return info["full_name"].lower()
        return (slug or "").lower()


def load_cache(path):
    """Load a persisted resolution cache, or {} if unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(path, cache):
    """Persist a resolution cache. Best effort; failure is not fatal."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2, sort_keys=True)
        return True
    except OSError:
        return False
