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
import re
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

    def _has_git_entry(path):
        """Cheap stat gate before the expensive subprocess.

        is_repo_root() spawns `git rev-parse`, ~14ms each. Calling it on
        every directory encountered cost 603 subprocesses and 8.6s to
        walk one code drive, two thirds of them on ordinary folders that
        were never repos. A repo root always has a `.git` entry -- a
        directory for a normal clone, a FILE for a worktree or submodule
        -- so an os.path.exists() first turns the subprocess into a
        confirmation step rather than a search.

        The subprocess is still required: `.git` present does not prove a
        VALID repo root, and git resolves paths against enclosing repos.
        This narrows what gets asked, it does not trust the answer.
        """
        return os.path.exists(os.path.join(path, ".git"))

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
            if _has_git_entry(entry.path) and is_repo_root(entry.path):
                found.append(entry.path)
                continue  # do not descend into a matched repo
            walk(entry.path, depth + 1)

    if _has_git_entry(root) and is_repo_root(root):
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

def read_declared_dist_name(path):
    """Return (dist_name, source) declared by a repo, or (None, None).

    THE authoritative answer to "what is this repo's PyPI identity".

    It must never be inferred from the INSTALLED distribution's name. A
    project that has been renamed leaves the old dist installed under the
    old name, and if that old name has since been taken by an unrelated
    project on PyPI, comparing against it produces an "update available"
    row whose remedy installs a stranger's code. That is not theoretical:
    our `preserve` was renamed to `dazzle-preserve`, PyPI `preserve` is
    now an unrelated key/value store, and following the recommendation
    installed it over our console entry point (issue #106).
    """
    pyproject = os.path.join(path, "pyproject.toml")
    if os.path.isfile(pyproject):
        try:
            import tomllib
            with open(pyproject, "rb") as fh:
                data = tomllib.load(fh)
            name = (data.get("project") or {}).get("name")
            if name:
                return name, "pyproject.toml [project].name"
        except Exception:  # noqa: BLE001 - malformed metadata is not fatal
            pass
    for candidate in ("setup.py", "setup.cfg"):
        target = os.path.join(path, candidate)
        if not os.path.isfile(target):
            continue
        try:
            text = open(target, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        m = re.search(r'^\s*name\s*[=:]\s*["\']?([A-Za-z0-9._-]+)',
                      text, re.MULTILINE)
        if m:
            return m.group(1), f"{candidate} name="
    return None, None


def normalize_dist(name):
    """PEP 503 normalization, so Foo_Bar and foo-bar compare equal."""
    if not name:
        return ""
    return re.sub(r'[-_.]+', '-', str(name)).strip().lower()


def pypi_project(package, opener=None, timeout=20):
    """Return (info_dict, error) for a PyPI project.

    info_dict has keys: version, urls (list of str), summary. A 404 is a
    normal, informative answer -- "not published" -- and returns
    (None, None) rather than an error.
    """
    url = f"https://pypi.org/pypi/{package}/json"
    _open = opener or urllib.request.urlopen
    try:
        with _open(url, timeout=timeout) as resp:
            payload = json.load(resp)
        info = payload.get("info") or {}
        urls = [u for u in ([info.get("home_page")]
                            + list((info.get("project_urls") or {}).values()))
                if u]
        return {
            "version": info.get("version"),
            "urls": urls,
            "summary": info.get("summary") or "",
        }, None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, None  # not published: an answer, not an error
        return None, f"{package}: HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"{package}: {exc}"
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"{package}: unparseable PyPI response ({exc})"


def pypi_owned_by(info, owners):
    """Does this PyPI project plausibly belong to one of `owners`?

    Defense in depth behind the declared-name fix. Even with the right
    name, a project we do not own must never produce an "update
    available" row: the remedy would install someone else's code. Answers
    only from the project's own declared URLs -- absence of evidence is
    reported as unknown (None), never as ownership.
    """
    if not info:
        return None
    urls = " ".join(info.get("urls") or []).lower()
    if not urls:
        return None
    for owner in owners or ():
        if not owner:
            continue
        if f"github.com/{str(owner).lower()}/" in urls:
            return True
    return False


def pypi_version(package, opener=None, timeout=20):
    """Backwards-compatible shim: just the latest version string."""
    info, err = pypi_project(package, opener=opener, timeout=timeout)
    return (info or {}).get("version"), err
