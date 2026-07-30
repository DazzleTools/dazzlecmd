"""Discovery sources -- four independent views of "what repos exist".

Each source is authoritative for something and blind to something else,
and the blind spots are close to inverted. That is the whole reason the
scanner joins four rather than trusting one:

    org listing   knows what we OWN, including repos never cloned here.
                  Blind to anything with no remote.
    pip editables knows what this environment actually EXECUTES, and
                  resolves which checkout is wired in when several exist.
                  Blind to anything not installed, and to non-Python repos.
    filesystem    knows what is physically present, including a repo with
                  no remote and no install. Very noisy on its own.
    PyPI          knows what the world can install. Meaningless for
                  unpublished alphas, but it is what catches an install
                  whose metadata has silently fallen behind its source.

Every function degrades explicitly: when a backend is unavailable the
caller is told which view is missing, because a report that silently
drops a source looks complete while being wrong.
"""

import json
import os
import subprocess
import urllib.error
import urllib.request
from importlib import metadata
from urllib.parse import unquote, urlparse

from .repo_state import is_repo_root


# -- pip / editable installs --

def _url_to_path(url):
    """Convert a file:// URL from direct_url.json to a local path."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    # Windows: file:///C:/x -> /C:/x ; strip the leading slash
    if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return os.path.normpath(path)


def iter_editable_installs(distributions=None):
    """Yield {name, version, path} for every editable (PEP 660) install.

    Editable installs record their source directory in direct_url.json
    with dir_info.editable = true. This is the only source that maps a
    package to the specific checkout the environment actually uses --
    which is what disambiguates six candidate paths for one package.
    """
    dists = distributions if distributions is not None else metadata.distributions()
    seen = set()
    for dist in dists:
        try:
            raw = dist.read_text("direct_url.json")
        except Exception:
            continue
        if not raw:
            continue
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not info.get("dir_info", {}).get("editable"):
            continue
        path = _url_to_path(info.get("url"))
        if not path:
            continue
        try:
            name = dist.metadata["Name"]
            version = dist.version
        except Exception:
            continue
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        yield {"name": name, "version": version, "path": path}


def editable_installs(distributions=None):
    """List form of iter_editable_installs, sorted by name."""
    return sorted(iter_editable_installs(distributions), key=lambda d: d["name"].lower())


# -- filesystem --

def find_git_repos(root, max_depth=3, skip_names=None):
    """Find directories under `root` that ARE git repo roots.

    Gated on is_repo_root() rather than on the presence of a .git entry:
    git resolves paths against the nearest ENCLOSING repo, so a plain
    subdirectory would otherwise be credited with its ancestor's state.

    Depth is bounded because a full walk of a code drive is dominated by
    node_modules and venvs. Nested repos below an already-matched root
    are not descended into.
    """
    skip = set(skip_names or [
        "node_modules", "venv", ".venv", "__pycache__", "site-packages",
        "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    ])
    found = []
    root = os.path.abspath(root)

    def walk(path, depth):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name in skip or entry.name.startswith("."):
                continue
            if is_repo_root(entry.path):
                found.append(entry.path)
                continue  # do not descend into a matched repo
            walk(entry.path, depth + 1)

    if is_repo_root(root):
        found.append(root)
    else:
        walk(root, 1)
    return found


# -- GitHub org listing --

def _run_gh(args, timeout=60):
    try:
        res = subprocess.run(
            ["gh"] + list(args), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        return 127, "", "gh not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"gh timed out after {timeout}s"


def list_org_repos(owner, runner=_run_gh, limit=300, include_archived=False):
    """List repos for an org or user.

    Returns (repos, error). `repos` is a list of dicts with keys
    nameWithOwner, name, isFork, isArchived, isPrivate, pushedAt. On
    failure `repos` is [] and `error` explains why -- callers must
    surface it, since an empty list from an unauthenticated gh is
    indistinguishable from an empty org otherwise.
    """
    fields = "nameWithOwner,name,isFork,isArchived,isPrivate,pushedAt"
    rc, out, err = runner(
        ["repo", "list", owner, "--limit", str(limit), "--json", fields])
    if rc != 0:
        first = (err.strip().splitlines() or ["unknown gh error"])[0]
        return [], f"{owner}: {first}"
    try:
        repos = json.loads(out or "[]")
    except json.JSONDecodeError:
        return [], f"{owner}: unparseable gh output"
    if not include_archived:
        repos = [r for r in repos if not r.get("isArchived")]
    return repos, None


# -- PyPI --

def pypi_version(package, opener=None, timeout=20):
    """Return (version, error) for a package's latest PyPI release.

    A 404 is a normal, informative answer -- "not published" -- not a
    failure, so it comes back as (None, None) rather than as an error.
    """
    url = f"https://pypi.org/pypi/{package}/json"
    _open = opener or urllib.request.urlopen
    try:
        with _open(url, timeout=timeout) as resp:
            payload = json.load(resp)
        return payload.get("info", {}).get("version"), None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, None  # not published: an answer, not an error
        return None, f"{package}: HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"{package}: {exc}"
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"{package}: unparseable PyPI response ({exc})"
